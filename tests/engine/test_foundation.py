from lunarnav import MODEL_VERSION
from lunarnav.capabilities import CAPABILITIES, CapabilityStatus
from lunarnav.errors import ErrorCode, InvalidInputError, LunarNavError


def test_model_version_is_set():
    assert MODEL_VERSION.startswith("0.1.0")


def test_no_capability_claims_to_be_built_in_stage_1():
    # Guards the "no scientific functionality falsely presented as complete" gate.
    assert all(c.status is CapabilityStatus.NOT_IMPLEMENTED for c in CAPABILITIES)


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
