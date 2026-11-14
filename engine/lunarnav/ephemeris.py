"""SPICE-backed Sun/Earth ephemeris for an observer on the lunar surface (Stage 3).

Method (docs/stage3/EPHEMERIS_METHOD.md):
  UTC -> ET (LSK) -> apparent topocentric state of the target seen from a fixed point on the Moon
  (SPICE `spkcpo`, light time + stellar aberration `LT+S`, output in MOON_ME) -> local ENU basis
  -> azimuth, elevation, range, angular diameter.

The local ENU basis is built from the *site* (not from SPICE), so the site definition is explicit
and unit-tested. No fixed or fabricated positions exist anywhere: every number comes from the
verified DE440 kernels. Missing or modified kernels raise `DataMissingError`; times outside the
validated window raise `EphemerisOutOfRangeError`. There is no fallback.

SPICE keeps process-global state and is not thread-safe, so every SPICE call is serialised by a
module lock.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import spiceypy as sp
from spiceypy.utils.exceptions import SpiceyError

from . import MODEL_VERSION
from .dem import sha256_file
from .errors import DataMissingError, EphemerisOutOfRangeError, InvalidInputError
from .frames import (
    EARTH_EQUATORIAL_RADIUS_KM,
    REFERENCE_RADIUS_KM,
    SUN_RADIUS_KM,
    angular_diameter_deg,
    enu_basis,
    site_position_km,
    vector_to_azel,
)
from .sites import validate_coordinates

# Required kernels, in load order (later kernels may depend on earlier ones: FK needs the PCK).
REQUIRED_KERNELS: tuple[tuple[str, str], ...] = (
    ("naif0012.tls", "lsk"),
    ("de440s.bsp", "planetary_spk"),
    ("moon_pa_de440_200625.bpc", "lunar_orientation_pck"),
    ("moon_de440_250416.tf", "lunar_frame_kernel"),
)

BODIES: dict[str, dict[str, Any]] = {
    "sun": {"spice": "SUN", "radius_km": SUN_RADIUS_KM,
            "radius_source": "IAU 2015 Resolution B3 nominal solar radius 695 700 km"},
    "earth": {"spice": "EARTH", "radius_km": EARTH_EQUATORIAL_RADIUS_KM,
              "radius_source": "IAU 2015 Resolution B3 nominal Earth equatorial radius 6378.1 km"},
}

# Window over which Stage 3 results were validated against JPL Horizons (half-open).
VALIDATED_START = datetime(2025, 1, 1, tzinfo=UTC)
VALIDATED_END = datetime(2036, 1, 1, tzinfo=UTC)

MAX_SAMPLES = 50_000
FRAME = "MOON_ME"
ABCORR = "LT+S"

_SPICE_LOCK = threading.RLock()
_LOADED_TOKEN: object | None = None


def parse_utc(value: object, field_name: str = "time_utc") -> datetime:
    """Strict ISO-8601 UTC parser: requires an explicit `Z` or `+00:00`; rejects local time."""
    if not isinstance(value, str):
        raise InvalidInputError(f"{field_name} must be an ISO-8601 UTC string", field=field_name)
    text = value.strip()
    if not text.endswith(("Z", "+00:00")):
        raise InvalidInputError(
            f"{field_name} must be UTC with an explicit 'Z' suffix (e.g. 2027-01-15T00:00:00Z); "
            "local or offset times are not accepted",
            field=field_name,
        )
    try:
        dt = datetime.fromisoformat(text)  # Python >= 3.11 parses a trailing 'Z'
    except ValueError as exc:
        raise InvalidInputError(f"{field_name} is not a valid ISO-8601 UTC time: {exc}",
                                field=field_name) from exc
    if dt.tzinfo is None or dt.utcoffset() != timedelta(0):
        raise InvalidInputError(f"{field_name} must be in UTC", field=field_name)
    return dt.astimezone(UTC)


def format_utc(dt: datetime) -> str:
    """ISO-8601 UTC with trailing Z; fractional seconds only when non-zero."""
    dt = dt.astimezone(UTC)
    base = dt.strftime("%Y-%m-%dT%H:%M:%S")
    if dt.microsecond:
        base += f".{dt.microsecond:06d}".rstrip("0")
    return base + "Z"


def check_validated_range(dt: datetime, field_name: str = "time_utc") -> None:
    if not (VALIDATED_START <= dt < VALIDATED_END):
        raise EphemerisOutOfRangeError(
            f"{field_name} {format_utc(dt)} is outside the validated range "
            f"{format_utc(VALIDATED_START)} to {format_utc(VALIDATED_END)} (exclusive). "
            "The kernels cover more, but results outside this range have not been validated "
            "against JPL Horizons and UTC after the last known leap second is an assumption.",
            field=field_name,
            details={"validated_start": format_utc(VALIDATED_START),
                     "validated_end_exclusive": format_utc(VALIDATED_END)},
        )


@dataclass(frozen=True)
class KernelRecord:
    file: str
    role: str
    sha256: str
    size_bytes: int
    source_url: str


@dataclass(frozen=True)
class Observer:
    lat_deg: float
    lon_deg_east: float
    height_m: float = 0.0


@dataclass
class BodySeries:
    azimuth_deg: list[float] = field(default_factory=list)
    elevation_deg: list[float] = field(default_factory=list)
    range_km: list[float] = field(default_factory=list)
    angular_diameter_deg: list[float] = field(default_factory=list)
    light_time_s: list[float] = field(default_factory=list)


@dataclass(frozen=True)
class EphemerisResult:
    times_utc: list[str]
    bodies: dict[str, BodySeries]
    observer: Observer
    provenance: dict[str, Any]
    data_class: str = "calculated"


def _validate_height(height_m: object) -> float:
    if isinstance(height_m, bool) or not isinstance(height_m, int | float):
        raise InvalidInputError("height_m must be a number", field="height_m")
    h = float(height_m)
    if not (-10_000.0 <= h <= 20_000.0):  # also rejects NaN (all comparisons with NaN are False)
        raise InvalidInputError(
            "height_m must be within -10000..20000 m above the 1737.4 km reference sphere",
            field="height_m")
    return h


class EphemerisService:
    """Loads the pinned kernel set (checksum-verified) and evaluates Sun/Earth as seen from a site."""

    def __init__(self, data_dir: Path) -> None:
        self.kernel_dir = Path(data_dir) / "kernels"
        self.manifest_path = Path(data_dir) / "manifests" / "kernels.json"
        self._records: tuple[KernelRecord, ...] | None = None
        self._token = object()

    # ---------------------------------------------------------------- kernels
    def _read_records(self) -> tuple[KernelRecord, ...]:
        if not self.manifest_path.exists():
            raise DataMissingError(
                f"Kernel manifest not found: {self.manifest_path}",
                details={"rebuild": r".\.venv\Scripts\python.exe scripts\fetch_kernels.py"})
        files = json.loads(self.manifest_path.read_text(encoding="utf-8"))["files"]
        records = []
        for name, role in REQUIRED_KERNELS:
            entry = files.get(name)
            if not entry or not entry.get("sha256"):
                raise DataMissingError(f"Kernel {name} is not in the manifest", field=name)
            records.append(KernelRecord(name, role, entry["sha256"], int(entry["size_bytes"]),
                                        entry["source_url"]))
        return tuple(records)

    def load(self) -> None:
        """Verify every kernel against the manifest and load them. Idempotent."""
        global _LOADED_TOKEN
        with _SPICE_LOCK:
            if _LOADED_TOKEN is self._token and self._records is not None:
                return
            records = self._read_records()
            for rec in records:
                path = self.kernel_dir / rec.file
                if not path.exists():
                    raise DataMissingError(
                        f"Required SPICE kernel missing: {rec.file}",
                        field=rec.file,
                        details={"rebuild": r".\.venv\Scripts\python.exe scripts\fetch_kernels.py"})
                if path.stat().st_size != rec.size_bytes or sha256_file(path) != rec.sha256:
                    raise DataMissingError(
                        f"Kernel {rec.file} does not match the pinned checksum; refusing to use it",
                        field=rec.file,
                        details={"expected_sha256": rec.sha256})
            sp.kclear()
            _LOADED_TOKEN = None
            for rec in records:
                sp.furnsh(str(self.kernel_dir / rec.file))
            # Guard the frame decision made in Stage 2: MOON_ME must be the DE421-aligned alias
            # (id 31001), never MOON_PA (31000), which is ~875 m rotated against the LOLA DEM.
            if sp.namfrm(FRAME) != 31001:
                raise DataMissingError(
                    f"Frame {FRAME} did not resolve to NAIF id 31001; frame kernel is wrong")
            self._records = records
            _LOADED_TOKEN = self._token

    # ---------------------------------------------------------------- time
    def utc_to_et(self, dt: datetime) -> float:
        self.load()
        with _SPICE_LOCK:
            return float(sp.str2et(dt.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S.%f") + " UTC"))

    def et_to_utc(self, et: float) -> str:
        self.load()
        with _SPICE_LOCK:
            return str(sp.et2utc(et, "ISOC", 6))

    # ---------------------------------------------------------------- provenance
    def provenance(self) -> dict[str, Any]:
        self.load()
        assert self._records is not None
        return {
            "model_version": MODEL_VERSION,
            "engine": "SPICE (SpiceyPy)",
            "spiceypy_version": sp.__version__,
            "cspice_toolkit": sp.tkvrsn("TOOLKIT"),
            "kernels": [
                {"file": r.file, "role": r.role, "sha256": r.sha256, "source_url": r.source_url}
                for r in self._records
            ],
            "frame": FRAME,
            "aberration_correction": ABCORR,
            "observer_model": (
                f"fixed point at planetocentric lat/lon on a sphere of R={REFERENCE_RADIUS_KM} km "
                "plus height above that sphere, body-fixed in MOON_ME"),
            "refraction": "none (airless)",
            "bodies": {k: {"radius_km": v["radius_km"], "radius_source": v["radius_source"]}
                       for k, v in BODIES.items()},
            "time_scale": "UTC input; ET/TDB via naif0012.tls (leap seconds through 2017-01-01; "
                          "no later leap second assumed)",
            "validated_range": [format_utc(VALIDATED_START), format_utc(VALIDATED_END)],
            "unmodelled": ["gravitational light deflection", "atmospheric refraction",
                           "terrain (not applied until Stage 4/5)"],
        }

    # ---------------------------------------------------------------- core
    def _observe(self, spice_name: str, radius_km: float, et: float, obs_pos: Any, basis: Any):
        try:
            state, light_time = sp.spkcpo(spice_name, et, FRAME, "OBSERVER", ABCORR,
                                          list(obs_pos), "MOON", FRAME)
        except SpiceyError as exc:
            if "INSUFFDATA" in str(exc) or "SPKINSUFFDATA" in str(exc):
                raise EphemerisOutOfRangeError(
                    "Ephemeris data are not available for that time in the loaded kernels") from exc
            raise
        az, el, rng = vector_to_azel(state[:3], basis)
        return az, el, rng, angular_diameter_deg(radius_km, rng), float(light_time)

    def series(
        self,
        lat_deg: object,
        lon_deg_east: object,
        start_utc: datetime,
        step_seconds: float,
        n_samples: int,
        bodies: tuple[str, ...] = ("sun", "earth"),
        height_m: object = 0.0,
    ) -> EphemerisResult:
        lat, lon = validate_coordinates(lat_deg, lon_deg_east)
        height = _validate_height(height_m)
        if not bodies or any(b not in BODIES for b in bodies):
            raise InvalidInputError(f"bodies must be a non-empty subset of {sorted(BODIES)}",
                                    field="bodies")
        if isinstance(step_seconds, bool) or not isinstance(step_seconds, int | float) \
                or not (1.0 <= step_seconds <= 86_400.0 * 30):
            raise InvalidInputError("step_seconds must be between 1 and 2592000",
                                    field="step_seconds")
        if not isinstance(n_samples, int) or isinstance(n_samples, bool) \
                or not (1 <= n_samples <= MAX_SAMPLES):
            raise InvalidInputError(f"number of samples must be 1..{MAX_SAMPLES}",
                                    field="step_seconds")
        last = start_utc + timedelta(seconds=step_seconds * (n_samples - 1))
        check_validated_range(start_utc, "start_utc")
        check_validated_range(last, "end_utc")

        self.load()
        obs_pos = site_position_km(lat, lon, height)
        basis = enu_basis(lat, lon)
        out = {b: BodySeries() for b in bodies}
        times: list[str] = []
        with _SPICE_LOCK:
            et0 = self.utc_to_et(start_utc)
            # ET advances uniformly with UTC because no leap second lies in the validated range.
            # (Asserted below by round-tripping the last sample.)
            for i in range(n_samples):
                et = et0 + i * step_seconds
                times.append(format_utc(start_utc + timedelta(seconds=i * step_seconds)))
                for b in bodies:
                    spec = BODIES[b]
                    az, el, rng, diam, lt = self._observe(
                        spec["spice"], spec["radius_km"], et, obs_pos, basis)
                    s = out[b]
                    s.azimuth_deg.append(az)
                    s.elevation_deg.append(el)
                    s.range_km.append(rng)
                    s.angular_diameter_deg.append(diam)
                    s.light_time_s.append(lt)
            if abs(self.utc_to_et(last) - (et0 + (n_samples - 1) * step_seconds)) > 1e-3:
                raise EphemerisOutOfRangeError(
                    "A leap second falls inside the requested span; uniform stepping is not valid")
        return EphemerisResult(times_utc=times, bodies=out,
                               observer=Observer(lat, lon, height), provenance=self.provenance())

    def at(self, lat_deg: object, lon_deg_east: object, time_utc: datetime,
           bodies: tuple[str, ...] = ("sun", "earth"), height_m: object = 0.0) -> EphemerisResult:
        """Single-instant convenience wrapper around `series`."""
        return self.series(lat_deg, lon_deg_east, time_utc, 1.0, 1, bodies, height_m)
