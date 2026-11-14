"""Download and verify the NAIF kernels planned for Stage 3 (download + verification ONLY).

- Canonical source: NAIF generic_kernels (URLs below).
- Authoritative checksum: the MD5 in the NAIF PDS4 CLPS SPICE archive label (.xml) for the same
  file name. NAIF's generic_kernels directories publish no checksum files.
- We additionally record SHA-256 (our own integrity/reproducibility record).
- Resumable; any checksum mismatch discards the file and restarts that file from byte 0.
- Output: data/kernels/<file> (git-ignored) and data/manifests/kernels.json (tracked).

Stdlib only. Usage: python scripts/fetch_kernels.py
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KERNEL_DIR = ROOT / "data" / "kernels"
MANIFEST = ROOT / "data" / "manifests" / "kernels.json"
GEN = "https://naif.jpl.nasa.gov/pub/naif/generic_kernels"
PDS = "https://naif.jpl.nasa.gov/pub/naif/pds/pds4/clps/clps_spice/spice_kernels"

# (role, file name, canonical URL, PDS4 label URL)
KERNELS = [
    ("lsk", "naif0012.tls", f"{GEN}/lsk/naif0012.tls", f"{PDS}/lsk/naif0012.xml"),
    (
        "lunar_frame_kernel",
        "moon_de440_250416.tf",
        f"{GEN}/fk/satellites/moon_de440_250416.tf",
        f"{PDS}/fk/moon_de440_250416.xml",
    ),
    (
        "lunar_orientation_pck",
        "moon_pa_de440_200625.bpc",
        f"{GEN}/pck/moon_pa_de440_200625.bpc",
        f"{PDS}/pck/moon_pa_de440_200625.xml",
    ),
    (
        "lunar_orientation_pck_comments",
        "moon_pa_de440_200625.cmt",
        f"{GEN}/pck/moon_pa_de440_200625.cmt",
        None,
    ),
    ("planetary_spk", "de440s.bsp", f"{GEN}/spk/planets/de440s.bsp", f"{PDS}/spk/de440s.xml"),
]


def http(url: str, headers: dict | None = None, method: str = "GET", timeout: int = 60):
    req = urllib.request.Request(url, headers=headers or {}, method=method)
    return urllib.request.urlopen(req, timeout=timeout)


def remote_size(url: str) -> tuple[int, str | None]:
    with http(url, method="HEAD") as r:
        return int(r.headers["Content-Length"]), r.headers.get("Last-Modified")


def label_md5(url: str) -> str:
    with http(url) as r:
        text = r.read().decode("utf-8", "replace")
    m = re.search(r"<md5_checksum>([0-9a-f]{32})</md5_checksum>", text)
    if not m:
        raise RuntimeError(f"no md5_checksum in {url}")
    return m.group(1)


def hashes(path: Path) -> tuple[str, str]:
    md5, sha = hashlib.md5(), hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            md5.update(chunk)
            sha.update(chunk)
    return md5.hexdigest(), sha.hexdigest()


def download(url: str, dest: Path, size: int, attempts: int = 60) -> None:
    part = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(1, attempts + 1):
        have = part.stat().st_size if part.exists() else 0
        if have == size:
            break
        try:
            with http(url, {"Range": f"bytes={have}-"}, timeout=45) as r:
                if have and r.status != 206:
                    have = 0
                    part.unlink(missing_ok=True)
                with part.open("ab" if have else "wb") as f:
                    while chunk := r.read(1 << 16):
                        f.write(chunk)
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            print(f"  attempt {attempt}: {type(e).__name__}: {e}", flush=True)
            time.sleep(2)
    if not part.exists() or part.stat().st_size != size:
        raise RuntimeError(f"incomplete download for {dest.name}")
    part.replace(dest)


def main() -> int:
    KERNEL_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {"files": {}}
    ok = True
    for role, name, url, label in KERNELS:
        dest = KERNEL_DIR / name
        entry = {"role": role, "file": name, "source_url": url, "pds4_label_url": label}
        print(f"[{name}] ...", flush=True)
        try:
            size, last_mod = remote_size(url)
            entry.update(remote_size_bytes=size, remote_last_modified=last_mod)
            expected_md5 = label_md5(label) if label else None
            for round_ in (1, 2):
                if not dest.exists() or dest.stat().st_size != size:
                    download(url, dest, size)
                md5, sha = hashes(dest)
                if expected_md5 is None or md5 == expected_md5:
                    break
                print(f"  MD5 mismatch (round {round_}); discarding and re-downloading", flush=True)
                dest.unlink()
            verified = expected_md5 is not None and md5 == expected_md5
            entry.update(
                status="downloaded_verified" if verified else (
                    "downloaded_unverified_no_authoritative_checksum" if expected_md5 is None
                    else "CHECKSUM_MISMATCH"),
                size_bytes=dest.stat().st_size,
                md5=md5,
                sha256=sha,
                authoritative_md5=expected_md5,
                authoritative_md5_source=label,
                downloaded_utc=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            )
            ok &= entry["status"] != "CHECKSUM_MISMATCH"
        except Exception as e:  # noqa: BLE001 - report and continue with remaining files
            entry.update(status="FAILED", error=f"{type(e).__name__}: {e}")
            ok = False
        manifest["files"][name] = entry
        MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        print(f"  -> {entry['status']}", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
