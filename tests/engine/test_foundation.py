from lunarnav import MODEL_VERSION
from lunarnav.capabilities import CAPABILITIES, CapabilityStatus
from lunarnav.errors import ErrorCode, InvalidInputError, LunarNavError


def test_model_version_is_set():
    assert MODEL_VERSION.startswith("0.10.0")


def test_capability_statuses_are_honest_for_stage_8():
    # Only gates the user has explicitly approved are 'validated' (sites/dem S2, ephemeris S3, horizon S4,
    # visibility S5, scenarios S6, engineering S8 - approved 2026-11-15 after independent verification).
    status = {c.key: c.status for c in CAPABILITIES}
    for key in ("sites", "dem", "ephemeris", "horizon", "visibility", "scenarios", "engineering"):
        assert status[key] is CapabilityStatus.VALIDATED, key
    assert {c.key for c in CAPABILITIES} == {"sites", "dem", "ephemeris", "horizon", "visibility", "scenarios", "engineering"}


def test_typed_error_carries_code_field_and_details():
    err = InvalidInputError("bad lat", field="lat", details={"value": 123})
    assert isinstance(err, LunarNavError)
    assert err.code is ErrorCode.INVALID_INPUT
    assert err.field == "lat" and err.details == {"value": 123}


def test_engine_has_no_web_framework_dependency():
    # Static check: engine sources must never import web frameworks (NFR-4).
    import pathlib

    import lunarnav

    for path in pathlib.Path(lunarnav.__file__).parent.rglob("*.py"):
        src = path.read_text(encoding="utf-8")
        assert "fastapi" not in src and "starlette" not in src, path
