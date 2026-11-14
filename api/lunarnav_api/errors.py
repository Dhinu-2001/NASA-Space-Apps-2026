"""Consistent error handling: every failure returns the ErrorBody shape."""

from __future__ import annotations

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from lunarnav.errors import ErrorCode, LunarNavError

log = structlog.get_logger("lunarnav_api.errors")

_STATUS = {
    ErrorCode.INVALID_INPUT: 422,
    ErrorCode.OUT_OF_DEM_COVERAGE: 422,
    ErrorCode.DATA_MISSING: 503,
    ErrorCode.EPHEMERIS_OUT_OF_RANGE: 422,
    ErrorCode.NOT_IMPLEMENTED: 501,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.INTERNAL: 500,
}


def _body(request: Request, code: ErrorCode, message: str, field=None, details=None) -> dict:
    return {
        "code": code.value,
        "message": message,
        "field": field,
        "details": details or {},
        "request_id": getattr(request.state, "request_id", None),
    }


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(LunarNavError)
    async def _engine_error(request: Request, exc: LunarNavError) -> JSONResponse:
        log.warning("engine_error", code=exc.code.value, message=exc.message)
        return JSONResponse(
            _body(request, exc.code, exc.message, exc.field, exc.details),
            status_code=_STATUS[exc.code],
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        errs = exc.errors()
        field = ".".join(str(p) for p in errs[0]["loc"][1:]) if errs else None
        return JSONResponse(
            _body(
                request,
                ErrorCode.INVALID_INPUT,
                "Request validation failed.",
                field or None,
                {"errors": [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in errs]},
            ),
            status_code=422,
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_exception", exc_type=type(exc).__name__)
        return JSONResponse(
            _body(request, ErrorCode.INTERNAL, "Internal server error."), status_code=500
        )
