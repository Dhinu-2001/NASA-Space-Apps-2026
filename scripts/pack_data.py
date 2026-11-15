"""Pack the data a deployment needs into one archive (so a host can be provisioned in minutes instead of re-downloading from NASA).

Contents: data/kernels, data/dem_cache, data/catalogue, data/manifests, data/validation, and (with --with-cache) the warmed
results in data/results. A SHA256SUMS file inside the archive records every file. The application ALSO verifies each kernel and
DEM window against the checksums in data/manifests at load time and refuses a mismatch, so a corrupted or tampered bundle cannot
produce results.

Usage:  python scripts/pack_data.py [--with-cache] [--out lunarnav-data.tar.gz]
Unpack: tar xzf lunarnav-data.tar.gz -C <data directory>      (the archive paths start at kernels/, dem_cache/, ...)
"""

from __future__ import annotations

import hashlib
import io
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def main(argv: list[str]) -> int:
    out = Path(argv[argv.index("--out") + 1]) if "--out" in argv else ROOT / "lunarnav-data.tar.gz"
    parts = ["kernels", "dem_cache", "catalogue", "manifests", "validation"] + (["results"] if "--with-cache" in argv else [])
    files = []
    for part in parts:
        base = DATA / part
        if not base.exists():
            print(f"missing {base}: nothing to pack for '{part}'")
            return 1
        files += [p for p in sorted(base.rglob("*")) if p.is_file() and p.name != ".gitkeep" and ".partial" not in p.parts and ".tmp" not in p.name]
    sums = []
    with tarfile.open(out, "w:gz", compresslevel=6) as tar:
        for p in files:
            h = hashlib.sha256()
            with p.open("rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
            rel = p.relative_to(DATA).as_posix()
            sums.append(f"{h.hexdigest()}  {rel}")
            tar.add(p, arcname=rel)
        body = ("\n".join(sums) + "\n").encode()
        info = tarfile.TarInfo("SHA256SUMS")
        info.size = len(body)
        tar.addfile(info, io.BytesIO(body))
    print(f"packed {len(files)} files into {out} ({out.stat().st_size / 1e6:.0f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
