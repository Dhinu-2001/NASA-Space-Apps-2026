"""Rebuild every piece of data a deployment needs from the official NASA sources (one command).

Steps (each script is resumable and checksum-verified; safe to re-run):
  1. NAIF SPICE kernels            scripts/fetch_kernels.py                (~45 MB, MD5 verified against NAIF's PDS4 labels)
  2. LOLA DEM windows              scripts/extract_dem_window.py <ids>     (range reads from NASA PGDA; ~250 MB in total)
  3. verification                  scripts/verify_data.py
  4. (optional) warm the caches    scripts/warm_cache.py                   (so the first demo views are instant)

The PGDA server is slow and occasionally drops connections: expect 30-60 minutes for the 80 km window and the Chandrayaan-3
window together; interrupted downloads resume. If you already have a data bundle (scripts/pack_data.py), unpack it instead.

Faster: install a prepared bundle (made by scripts/pack_data.py) instead of re-downloading from NASA:
  python scripts/provision_data.py --from-bundle <https URL | file path> [--sha256 <hex of the archive>]
The bundle is checked before anything is used: the archive's SHA-256 (when given), then every file against the SHA256SUMS inside it,
then the application's own manifest checks (scripts/verify_data.py). Only kernels/, dem_cache/ and results/ are taken from it; the
catalogue, manifests and validation data always come from the repository, never from the bundle.

Usage: python scripts/provision_data.py [--skip-large] [--no-chandrayaan3] [--warm] [--from-bundle SRC [--sha256 HEX]]
  --skip-large        only the small IM-2/IM-1 windows (about 5 MB); the 80 km IM-2 window and the Chandrayaan-3 window are skipped,
                      so IM-2 results use the 10 km + 320 m windows and Chandrayaan-3 reports 'terrain data insufficient'
  --no-chandrayaan3   skip the 108 MB Chandrayaan-3 window
  --warm              run scripts/warm_cache.py at the end
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
SMALL = ["im2_20m_r10km", "im2_320m_r160km", "im1_20m_r2km"]
LARGE = ["im2_20m_r80km"]
CH3 = ["ch3_60m_r200km"]


def run(label: str, *args: str) -> int:
    print(f"\n=== {label}\n$ {' '.join(args)}", flush=True)
    return subprocess.call([PY, *args], cwd=ROOT)


BUNDLE_DIRS = ("kernels", "dem_cache", "results")   # the only top-level folders taken from a bundle
SKIPPED_DIRS = ("catalogue", "manifests", "validation")   # present in bundles made by pack_data.py; always come from the repository


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _fetch(src: str, dest: Path) -> None:
    """Copy a local file, or download a URL (https or file:), to dest. Progress every ~25 MB."""
    if "://" not in src:
        shutil.copyfile(src, dest)
        return
    if not src.startswith(("https://", "file:")):
        raise SystemExit(f"refusing to download the bundle over a non-https URL: {src}")
    done = 0
    with urllib.request.urlopen(src, timeout=60) as r, dest.open("wb") as out:
        while chunk := r.read(1 << 20):
            out.write(chunk)
            done += len(chunk)
            if done // (25 << 20) != (done - len(chunk)) // (25 << 20):
                print(f"  downloaded {done / 1e6:.0f} MB", flush=True)
    print(f"  downloaded {done / 1e6:.0f} MB in total", flush=True)


def install_bundle(src: str, expected_sha256: str | None, data_dir: Path) -> int:
    """Download/copy a bundle, verify it, and unpack kernels/, dem_cache/ and results/ into data_dir. Returns 0 on success.

    Nothing is trusted: the archive digest (if given), every member path (no absolute paths, no '..', no links, only the three
    allowed folders) and every file against the bundle's SHA256SUMS are checked; a failure raises/returns non-zero and removes
    what was unpacked.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    archive = data_dir / "bundle.download.tar.gz"
    staging = data_dir / ".bundle-staging"
    shutil.rmtree(staging, ignore_errors=True)
    try:
        print(f"=== fetching the data bundle: {src}", flush=True)
        _fetch(src, archive)
        digest = _sha256(archive)
        print(f"  archive SHA-256 {digest}", flush=True)
        if expected_sha256 and digest != expected_sha256.lower():
            print(f"ERROR: archive SHA-256 does not match the expected value ({expected_sha256}); nothing was installed.")
            return 2
        if not expected_sha256:
            print("  note: no --sha256 given, so the archive itself is not pinned; its files are still checked against its own"
                  " SHA256SUMS and the repository's manifests.")
        staging.mkdir()
        with tarfile.open(archive, "r:gz") as tar:
            members = tar.getmembers()
            for m in members:
                parts = Path(m.name).parts
                if m.name == "SHA256SUMS":
                    continue
                if m.name.startswith("/") or ".." in parts or not parts or parts[0] not in BUNDLE_DIRS + SKIPPED_DIRS or not (m.isfile() or m.isdir()):
                    print(f"ERROR: unsafe or unexpected entry in the bundle: {m.name!r}; nothing was installed.")
                    return 2
            wanted = [m for m in members if m.name != "SHA256SUMS" and Path(m.name).parts[0] in BUNDLE_DIRS]
            tar.extractall(staging, members=wanted, filter="data")
            sums_member = next((m for m in members if m.name == "SHA256SUMS"), None)
            if sums_member is None:
                print("ERROR: the bundle has no SHA256SUMS; nothing was installed.")
                return 2
            sums = tar.extractfile(sums_member).read().decode().splitlines()  # type: ignore[union-attr]
        bad = 0
        checked = 0
        for line in sums:
            digest_hex, _, rel = line.partition("  ")
            if not rel or Path(rel).parts[0] not in BUNDLE_DIRS:
                continue   # catalogue/manifests/validation entries are ignored: they come from the repository
            f = staging / rel
            checked += 1
            if not f.is_file() or _sha256(f) != digest_hex:
                print(f"ERROR: {rel} does not match the bundle's SHA256SUMS")
                bad += 1
        if bad or not checked:
            print("Bundle verification failed; nothing was installed.")
            return 2
        for d in BUNDLE_DIRS:
            if (staging / d).is_dir():
                target = data_dir / d
                target.mkdir(parents=True, exist_ok=True)
                for item in (staging / d).iterdir():
                    dest = target / item.name
                    if dest.is_dir() and not dest.is_symlink():
                        shutil.rmtree(dest)
                    elif dest.exists() or dest.is_symlink():
                        dest.unlink()
                    shutil.move(str(item), str(dest))
        print(f"=== bundle installed: {checked} files verified against SHA256SUMS", flush=True)
        return 0
    finally:
        archive.unlink(missing_ok=True)
        shutil.rmtree(staging, ignore_errors=True)


def main(argv: list[str]) -> int:
    if "--from-bundle" in argv:
        i = argv.index("--from-bundle")
        src = argv[i + 1] if i + 1 < len(argv) else ""
        if not src:
            print("--from-bundle needs a URL or file path")
            return 2
        sha = argv[argv.index("--sha256") + 1] if "--sha256" in argv and argv.index("--sha256") + 1 < len(argv) else None
        rc = install_bundle(src, sha, ROOT / "data")
        if rc:
            return rc
        rc = run("verification", "-I", "scripts/verify_data.py")
        return rc
    windows = list(SMALL)
    if "--skip-large" not in argv:
        windows += LARGE
        if "--no-chandrayaan3" not in argv:
            windows += CH3
    rc = run("1/4 SPICE kernels", "scripts/fetch_kernels.py")
    if rc:
        return rc
    rc = run("2/4 LOLA DEM windows", "scripts/extract_dem_window.py", *windows)
    if rc:
        print("A window failed; re-run this command to resume where it stopped.")
        return rc
    rc = run("3/4 verification", "-I", "scripts/verify_data.py")
    if rc == 0 and "--warm" in argv:
        rc = run("4/4 warm caches", "-I", "scripts/warm_cache.py")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
