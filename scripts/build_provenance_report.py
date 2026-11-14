"""Generate docs/stage9/PROVENANCE.md from the manifests and the live provenance record (Stage 9 task 12).

The report is machine-generated so it cannot drift from what is installed. Re-run after any data change:
    .\\.venv\\Scripts\\python.exe -I scripts\\build_provenance_report.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from lunarnav import MODEL_VERSION
from lunarnav.ephemeris import EphemerisService
from lunarnav.provenance import build_provenance

DATA = ROOT / "data"


def git(*args: str) -> str:
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)
    return r.stdout.strip()


def main() -> None:
    eph = EphemerisService(DATA)
    prov = build_provenance(DATA, eph.provenance(), ROOT)
    kernels = json.loads((DATA / "manifests" / "kernels.json").read_text(encoding="utf-8"))["files"]
    products = json.loads((DATA / "manifests" / "dem_products.json").read_text(encoding="utf-8"))
    json.loads((DATA / "manifests" / "dem_windows.json").read_text(encoding="utf-8"))["windows"]
    fixture = json.loads((DATA / "validation" / "horizons_stage3_reference.json").read_text(encoding="utf-8"))
    L: list[str] = []
    a = L.append
    a("# Data provenance report\n")
    a(f"Generated {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')} by `scripts/build_provenance_report.py` from the "
      f"manifests in `data/manifests/` and the live `GET /provenance` record. Model version **{MODEL_VERSION}**, "
      f"code commit **{prov['git_commit']}**.\n")
    a("Heavy scientific data (SPICE kernels, DEM windows) are **not in Git** (decision G1); they are rebuilt by script and "
      "**verified by SHA-256 at load**. A file whose checksum differs is refused (`DATA_MISSING`), never used.\n")

    a("## 1. Data classes\n")
    a("| Class | Meaning |\n|---|---|")
    for k, v in prov["data_classes"].items():
        a(f"| `{k}` | {v} |")
    a("\nEvery API result states its class (`data_class`): DEM heights are `measured_interpolated`; everything the engine "
      "derives is `calculated`; labelled inputs chosen by the project are `assumption`.\n")

    a("## 2. SPICE kernels (NAIF) — ephemeris and lunar orientation\n")
    a("| File | Role | Size (bytes) | SHA-256 | Authoritative MD5 (NAIF) | Source |\n|---|---|---|---|---|---|")
    for k in prov["spice_kernels"]:
        m = kernels[k["file"]]
        a(f"| `{k['file']}` | {k['role']} | {m['size_bytes']:,} | `{k['sha256']}` | `{m.get('authoritative_md5', '—')}` | {k['source_url']} |")
    a("\nThe MD5 values were published by NAIF and checked on download; the SHA-256 values are pinned in the manifest and "
      "verified every time the kernels are loaded. Frame: `MOON_ME` (asserted to be NAIF id 31001 at load). "
      "`MOON_PA` is never used with the DEM.\n")

    a("## 3. Terrain (LOLA digital elevation models, NASA GSFC PGDA)\n")
    for pid, p in products["products"].items():
        a(f"* **{pid}** — {p['title']}. Publisher: {p['publisher']}. DOI `{p.get('doi', '—')}`. "
          f"[Landing page]({p['landing_page']}); file `{p['file_url']}` ({p['file_size_bytes']:,} bytes; "
          f"header verified {p['verified_utc']}). Never downloaded in full: windows are range-read.")
        a("  * Companion layers listed by the provider but **not used**: " + "; ".join(p["companion_layers_listed_on_landing_page"]))
    a("\n### Extracted windows used by the engine\n")
    a("| Window | Product | Pixel | Size | Overview | Valid | Height range (m) | SHA-256 |\n|---|---|---|---|---|---|---|---|")
    for w in prov["dem_windows"]:
        a(f"| `{w['window_id']}` | {w['product_id']} | {w['pixel_size_m']:g} m | {w['width']}×{w['height']} | "
          f"{w['overview_level'] if w['overview_level'] is not None else '— (native)'} | {w['valid_fraction']:.4f} | "
          f"{w['z_min_m']:.0f} … {w['z_max_m']:.0f} | `{w['sha256']}` |")
    a("\nEach window is a **real extract** of the cited LOLA product (HTTP range reads; nothing resampled by this project). "
      "Overview windows are area-averaged by the data provider (verified in Stage 4: 1.0 m rms against a 16×16 mean of the 20 m "
      "data). Heights are metres above the 1737.4 km reference sphere; grid is south-polar stereographic in `MOON_ME` (DE421).\n")
    a("Source URL for all windows: " + ", ".join(sorted({w["source_url"] for w in prov["dem_windows"]})) + "\n")

    a("## 4. Landing-site catalogue\n")
    cat = prov["site_catalogue"]
    a(f"Catalogue version `{cat['catalogue_version']}`, SHA-256 `{cat['sha256']}`. Only sites whose coordinates are supported by "
      "a primary source are included; none is estimated.\n")
    for s in cat["sites"]:
        a(f"* **{s['name']}** (`{s['id']}`, {s['kind'].replace('_', ' ')}): " + "; ".join(f"[{x['label']}]({x['url']})" for x in s["sources"]))
    a("")

    a("## 5. Validation oracle (JPL Horizons)\n")
    f = prov["validation_fixtures"]["horizons_stage3_reference"]
    a(f"`{f['file']}` — SHA-256 `{f['sha256']}`. {f['note']}. Retrieved {fixture['retrieved_utc']} from "
      f"{fixture['endpoint']} (Horizons API v{fixture['horizons_signature']['version']}); {len(fixture['sites'])} observers × "
      f"{len(fixture['epochs_utc'])} epochs × {{Sun, Earth}} = 220 rows. Request: `CENTER='coord@301'` geodetic lunar surface "
      "observer, apparent airless, DE441 and MEAN_ME. Recorded by `scripts/fetch_horizons_reference.py`; the fixture is tracked in "
      "Git (small). **Horizons shares JPL's ephemerides with the engine, so this validates the implementation, not the "
      "ephemerides themselves.**\n")

    a("## 6. Constants and assumptions\n")
    for k, v in prov["constants"].items():
        a(f"* `{k}`: {v}")
    a("\nProject assumptions (labelled wherever shown): observer height 2.0 m above the DEM surface (C9), landing-position uncertainty "
      "±100 m (user decision), 14-day mission-delay window, validated time range 2025-01-01 to 2035-12-31 (C8/E5).\n")

    a("## 7. Software\n")
    a("| Package | Version |\n|---|---|")
    for k, v in prov["software"].items():
        a(f"| {k} | {v} |")
    from importlib import metadata
    for pkg in ("fastapi", "pydantic", "uvicorn"):
        try:
            a(f"| {pkg} (API layer) | {metadata.version(pkg)} |")
        except metadata.PackageNotFoundError:
            pass
    a("\nPinned dependency list: `requirements.lock.txt` (backend), `web/package-lock.json` (frontend). CSPICE toolkit: "
      f"{eph.provenance()['cspice_toolkit']}.\n")

    a("## 8. Code history (Git)\n")
    a("```\n" + git("log", "--oneline", "--no-decorate") + "\n```\n")

    a("## 9. Reproducing a result\n")
    a("Every visibility and scenario result carries a deterministic `provenance` block (model version, kernel and DEM-window "
      "SHA-256, frame, aberration correction, horizon algorithm version, every parameter, no timestamps). With the same code "
      "(`git_commit`), the same data (checksums above) and the same inputs, the result is identical; this is asserted by "
      "`tests/validation/test_regression_golden.py`. Scenario ids are the SHA-256 of the canonical inputs + model version + DEM "
      "fingerprint.\n")
    a("Rebuild the data: `scripts/fetch_kernels.py`, `scripts/inspect_kernels.py`, `scripts/extract_dem_window.py` "
      "(see `docs/DEV_SETUP.md`).\n")
    out = ROOT / "docs" / "stage9" / "PROVENANCE.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
