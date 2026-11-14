from lunarnav import MODEL_VERSION
from lunarnav.capabilities import CAPABILITIES, CapabilityStatus
from lunarnav.errors import ErrorCode, InvalidInputError, LunarNavError


def test_model_version_is_set():
    assert MODEL_VERSION.startswith("0.5.0")


def test_capability_statuses_are_honest_for_stage_5():
    # Guards the "no scientific functionality falsely presented as complete" gate. Only gates the user has
    # explicitly approved are 'validated' (ephemeris: Stage 3, horizon: Stage 4); Stage 5 awaits approval.
    status = {c.key: c.status for c in CAPABILITIES}
    for key in ("sites", "dem", "visibility"):
        assert status[key] is CapabilityStatus.IMPLEMENTED_UNVALIDATED
    for key in ("ephemeris", "horizon"):
        assert status[key] is CapabilityStatus.VALIDATED
    for key in ("scenarios", "engineering"):
        assert status[key] is CapabilityStatus.NOT_IMPLEMENTED


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
