"""Stage 11: installing a prepared data bundle (scripts/provision_data.py --from-bundle). Needs no kernels or DEM, no network."""

import hashlib
import importlib.util
import io
import tarfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "provision_data.py"
spec = importlib.util.spec_from_file_location("provision_data", SCRIPT)
pd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pd)


def make_bundle(path: Path, files: dict[str, bytes], sums_override: dict[str, str] | None = None, extra: list[tarfile.TarInfo] | None = None):
    sums = []
    with tarfile.open(path, "w:gz") as tar:
        for name, body in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(body)
            tar.addfile(info, io.BytesIO(body))
            digest = (sums_override or {}).get(name) or hashlib.sha256(body).hexdigest()
            sums.append(f"{digest}  {name}")
        for e in extra or []:
            tar.addfile(e)
        body = ("\n".join(sums) + "\n").encode()
        info = tarfile.TarInfo("SHA256SUMS")
        info.size = len(body)
        tar.addfile(info, io.BytesIO(body))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_installs_verified_files_and_ignores_repository_owned_folders(tmp_path):
    b = tmp_path / "b.tar.gz"
    digest = make_bundle(b, {"kernels/a.bsp": b"kernel", "dem_cache/w.tif": b"dem", "manifests/kernels.json": b"EVIL"})
    data = tmp_path / "data"
    (data / "manifests").mkdir(parents=True)
    (data / "manifests" / "kernels.json").write_text("repo version")
    assert pd.install_bundle(str(b), digest, data) == 0
    assert (data / "kernels" / "a.bsp").read_bytes() == b"kernel"
    assert (data / "dem_cache" / "w.tif").read_bytes() == b"dem"
    assert (data / "manifests" / "kernels.json").read_text() == "repo version"   # never replaced by the bundle


def test_rejects_wrong_archive_digest_and_installs_nothing(tmp_path):
    b = tmp_path / "b.tar.gz"
    make_bundle(b, {"kernels/a.bsp": b"kernel"})
    data = tmp_path / "data"
    assert pd.install_bundle(str(b), "0" * 64, data) == 2
    assert not (data / "kernels").exists()


def test_rejects_a_file_that_does_not_match_the_bundles_sums(tmp_path):
    b = tmp_path / "b.tar.gz"
    digest = make_bundle(b, {"kernels/a.bsp": b"kernel"}, sums_override={"kernels/a.bsp": "f" * 64})
    data = tmp_path / "data"
    assert pd.install_bundle(str(b), digest, data) == 2
    assert not (data / "kernels").exists()


@pytest.mark.parametrize("name", ["../evil.txt", "/abs/evil.txt", "other/evil.txt", "kernels/../../evil.txt"])
def test_rejects_unsafe_or_unexpected_member_paths(tmp_path, name):
    b = tmp_path / "b.tar.gz"
    digest = make_bundle(b, {name: b"x"})
    data = tmp_path / "data"
    assert pd.install_bundle(str(b), digest, data) == 2
    assert not (tmp_path / "evil.txt").exists()


def test_rejects_links(tmp_path):
    b = tmp_path / "b.tar.gz"
    link = tarfile.TarInfo("kernels/link")
    link.type = tarfile.SYMTYPE
    link.linkname = "/etc/passwd"
    digest = make_bundle(b, {"kernels/a.bsp": b"k"}, extra=[link])
    assert pd.install_bundle(str(b), digest, tmp_path / "data") == 2


def test_rejects_a_bundle_without_sums(tmp_path):
    b = tmp_path / "b.tar.gz"
    with tarfile.open(b, "w:gz") as tar:
        info = tarfile.TarInfo("kernels/a.bsp")
        info.size = 1
        tar.addfile(info, io.BytesIO(b"k"))
    assert pd.install_bundle(str(b), None, tmp_path / "data") == 2


def test_refuses_plain_http_download():
    with pytest.raises(SystemExit):
        pd._fetch("http://example.invalid/x.tar.gz", Path("unused"))
