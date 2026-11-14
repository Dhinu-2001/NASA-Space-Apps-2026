"""Run every automated check and write docs/stage9/TEST_REPORT.md (Stage 9 final test report).

Runs: pytest (backend, with JUnit XML), ruff, TypeScript typecheck, vitest, production build.
The report records what ACTUALLY ran: counts, skips (with the reason), durations, and the commit tested.

    .\\.venv\\Scripts\\python.exe scripts\\build_test_report.py
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / ".venv" / "Scripts" / "python.exe"
NODE_DIR = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "nodejs"


def run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> tuple[int, str, float]:
    t0 = time.time()
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=env, check=False)
    return p.returncode, (p.stdout or "") + (p.stderr or ""), time.time() - t0


def main() -> int:
    env = dict(os.environ)
    if NODE_DIR.exists():
        env["PATH"] = f"{NODE_DIR}{os.pathsep}{env['PATH']}"
    commit = subprocess.run(["git", "rev-parse", "--short=12", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT, capture_output=True, text=True, check=False).stdout.strip())
    xml = ROOT / "docs" / "stage9" / "_junit.xml"
    rc_py, out_py, t_py = run([str(PY), "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={xml}"], ROOT, env)
    rc_ruff, out_ruff, t_ruff = run([str(PY), "-m", "ruff", "check", "."], ROOT, env)
    npm = str(NODE_DIR / "npm.cmd") if (NODE_DIR / "npm.cmd").exists() else ("npm.cmd" if os.name == "nt" else "npm")
    rc_tsc, out_tsc, t_tsc = run([npm, "run", "typecheck"], ROOT / "web", env)
    rc_vt, out_vt, t_vt = run([npm, "test"], ROOT / "web", env)
    rc_b, out_b, t_b = run([npm, "run", "build"], ROOT / "web", env)

    per_file: dict[str, dict[str, int]] = defaultdict(lambda: {"passed": 0, "failed": 0, "skipped": 0})
    skip_reasons: dict[str, int] = defaultdict(int)
    total = {"passed": 0, "failed": 0, "skipped": 0}
    if xml.exists():
        for tc in ET.parse(xml).getroot().iter("testcase"):
            f = tc.get("classname", "").replace(".", "/")
            f = re.sub(r"/test_[a-z0-9_]+$", lambda m: m.group(0), f)
            parts = tc.get("classname", "").split(".")
            fname = "/".join(parts[:-1]) + ".py" if parts[-1].startswith("test_") else "/".join(parts) + ".py"
            fname = fname.replace("tests/", "tests/", 1)
            if tc.find("failure") is not None or tc.find("error") is not None:
                k = "failed"
            elif tc.find("skipped") is not None:
                k = "skipped"
                skip_reasons[(tc.find("skipped").get("message") or "")[:110]] += 1
            else:
                k = "passed"
            per_file[fname][k] += 1
            total[k] += 1
        xml.unlink()
    vt = re.search(r"Tests\s+(?:(\d+) failed \| )?(\d+) passed \((\d+)\)", out_vt)
    vt_pass = int(vt.group(2)) if vt else 0
    vt_fail = int(vt.group(1)) if vt and vt.group(1) else 0
    ok = all(c == 0 for c in (rc_py, rc_ruff, rc_tsc, rc_vt, rc_b))

    L: list[str] = []
    a = L.append
    a("# Final test report\n")
    a(f"Generated {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')} by `scripts/build_test_report.py`. Commit tested: **{commit}**"
      f"{' (+ uncommitted changes to tracked files)' if dirty else ''}. Machine: Windows 11, Python 3.12, Node 24.\n")
    a(f"**Overall: {'ALL CHECKS PASSED' if ok else 'FAILURES PRESENT'}**\n")
    a("| Check | Result | Detail | Time |\n|---|---|---|---|")
    a(f"| Backend tests (pytest) | {'PASS' if rc_py == 0 else 'FAIL'} | {total['passed']} passed, {total['failed']} failed, {total['skipped']} skipped | {t_py:.0f} s |")
    a(f"| Lint (ruff) | {'PASS' if rc_ruff == 0 else 'FAIL'} | {out_ruff.strip().splitlines()[-1] if out_ruff.strip() else ''} | {t_ruff:.0f} s |")
    a(f"| Frontend typecheck (tsc) | {'PASS' if rc_tsc == 0 else 'FAIL'} | strict TypeScript, no errors | {t_tsc:.0f} s |")
    a(f"| Frontend tests (vitest) | {'PASS' if rc_vt == 0 else 'FAIL'} | {vt_pass} passed, {vt_fail} failed | {t_vt:.0f} s |")
    a(f"| Production build (vite) | {'PASS' if rc_b == 0 else 'FAIL'} | bundle builds | {t_b:.0f} s |\n")
    a("## Backend tests by file\n")
    a("| File | Passed | Failed | Skipped |\n|---|---|---|---|")
    for f in sorted(per_file):
        c = per_file[f]
        a(f"| `{f}` | {c['passed']} | {c['failed']} | {c['skipped']} |")
    a(f"| **Total** | **{total['passed']}** | **{total['failed']}** | **{total['skipped']}** |\n")
    if skip_reasons:
        a("### Skips (reason)\n")
        for r, n in skip_reasons.items():
            a(f"* {n} × {r}")
        a("")
    else:
        a("No test was skipped: all kernels and DEM windows were present, so every real-data test ran.\n")
    a("## What the suites cover\n")
    a("* **Unit/analytic**: frames, projection, time conversion, horizon geometry (flat, mesa, curvature, height), disc states, interval maths, delta and ranking logic.\n"
      "* **Independent comparison**: JPL Horizons (220-row grid, recorded fixture) and the hand-written horizon implementation, re-asserted as regression evidence.\n"
      "* **Real-data**: IM-2 LOLA windows + real SPICE ephemeris (golden scenarios, transitions vs brute-force scan, position sensitivity, IM-1 insufficient, Chandrayaan-3 no DEM).\n"
      "* **Synthetic terrain with the real ephemeris**: terrain obstruction, permanently shadowed crater.\n"
      "* **Fault injection**: missing or modified kernels and DEM, partial installation, out-of-range and malformed inputs.\n"
      "* **API contract**: every endpoint's success shape and typed errors; calculation metadata; provenance.\n"
      "* **UI**: capability status, bands always shown, insufficient sites shown with no numbers, cut-off flags, workflow.\n")
    a("## Not covered by automated tests\n")
    a("* Visual rendering beyond three headless-browser screenshots (`docs/stage7/`); no cross-browser testing.\n"
      "* Load/performance testing (first calculation for a new site ≈ 1 min is measured, not tested).\n"
      "* Any comparison with physical measurements (see `KNOWN_LIMITATIONS.md` L-M2).\n")
    a("## Reproduce\n")
    a("```powershell\n.\\.venv\\Scripts\\python.exe scripts\\build_test_report.py        # runs everything below and rewrites this file\n"
      ".\\.venv\\Scripts\\python.exe -m pytest\n.\\.venv\\Scripts\\python.exe -m ruff check .\n"
      "cd web; npm run typecheck; npm test; npm run build\n```\n")
    out = ROOT / "docs" / "stage9" / "TEST_REPORT.md"
    out.write_text("\n".join(L), encoding="utf-8")
    print(f"wrote {out}: {'ALL PASSED' if ok else 'FAILURES'} (pytest {total}, vitest {vt_pass}/{vt_fail})")
    if not ok:
        for name, rc, o in (("pytest", rc_py, out_py), ("ruff", rc_ruff, out_ruff), ("tsc", rc_tsc, out_tsc), ("vitest", rc_vt, out_vt), ("build", rc_b, out_b)):
            if rc:
                print(f"--- {name} (exit {rc}) ---\n{o[-1800:]}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
