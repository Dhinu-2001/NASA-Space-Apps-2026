"""Typed errors shared by the engine and API.

Principle (decision S7): missing/invalid scientific data is an explicit error or incomplete-data
status. It is never silently replaced by a geometric or synthetic fallback.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    INVALID_INPUT = "INVALID_INPUT"
    OUT_OF_DEM_COVERAGE = "OUT_OF_DEM_COVERAGE"
    DATA_MISSING = "DATA_MISSING"
    EPHEMERIS_OUT_OF_RANGE = "EPHEMERIS_OUT_OF_RANGE"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    INTERNAL = "INTERNAL"


class LunarNavError(Exception):
    """Base class for all expected, user-reportable engine errors."""

    code: ErrorCode = ErrorCode.INTERNAL

    def __init__(
        self,
        message: str,
        *,
        field: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.field = field
        self.details = details or {}


class InvalidInputError(LunarNavError):
    code = ErrorCode.INVALID_INPUT


class OutOfDemCoverageError(LunarNavError):
    code = ErrorCode.OUT_OF_DEM_COVERAGE


class DataMissingError(LunarNavError):
    code = ErrorCode.DATA_MISSING


class EphemerisOutOfRangeError(LunarNavError):
    code = ErrorCode.EPHEMERIS_OUT_OF_RANGE


class NotImplementedYetError(LunarNavError):
    code = ErrorCode.NOT_IMPLEMENTED
