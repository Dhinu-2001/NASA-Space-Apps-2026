"""Lunar site model, coordinate validation and the curated catalogue.

Coordinate convention (docs/stage0/02_Scientific_Methodology.md section 2):
  * Body: Moon, MOON_ME frame, sphere R = 1737.4 km.
  * Latitude: planetocentric degrees, south negative, valid range [-90, 90].
  * Longitude: EAST-positive degrees. Inputs in [-180, 360] are accepted and normalised to
    [-180, 180). (The two ends of the input range, 180 and -180, are the same meridian.)

Catalogue policy (decision C7): every curated site carries at least one primary-source reference
with a URL. Proposed/candidate sites are labelled as such and are never presented as confirmed.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from .errors import InvalidInputError

LON_CONVENTION = "east_positive"
LAT_CONVENTION = "planetocentric"
BODY = "Moon"
REFERENCE_RADIUS_M = 1_737_400.0


class SiteKind(StrEnum):
    CONFIRMED_LANDING = "confirmed_landing"  # a spacecraft actually reached the surface here
    INTENDED_TARGET = "intended_target"  # pre-landing target; may differ from where it landed
    CANDIDATE_REGION = "candidate_region"  # proposed, not selected/landed
    CUSTOM = "custom"  # user-entered coordinates


@dataclass(frozen=True)
class SourceRef:
    label: str
    url: str
    description: str
    quote: str  # exact wording/values taken from the source


@dataclass(frozen=True)
class Site:
    id: str
    name: str
    lat_deg: float
    lon_deg_east: float
    kind: SiteKind
    sources: tuple[SourceRef, ...] = ()
    # Independently published surface altitude above the 1737.4 km sphere (metres), if any.
    reference_height_m: float | None = None
    reference_height_source: str | None = None
    notes: str = ""
    lon_convention: str = field(default=LON_CONVENTION)
    lat_convention: str = field(default=LAT_CONVENTION)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "lat_deg": self.lat_deg,
            "lon_deg_east": self.lon_deg_east,
            "kind": self.kind.value,
            "lat_convention": self.lat_convention,
            "lon_convention": self.lon_convention,
            "reference_height_m": self.reference_height_m,
            "reference_height_source": self.reference_height_source,
            "notes": self.notes,
            "sources": [s.__dict__ for s in self.sources],
        }


def _finite_number(value: object, field_name: str) -> float:
    # bool is an int subclass; True/False must never be accepted as coordinates.
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise InvalidInputError(f"{field_name} must be a number.", field=field_name)
    v = float(value)
    if not math.isfinite(v):
        raise InvalidInputError(f"{field_name} must be finite.", field=field_name)
    return v


def normalise_longitude(lon_deg: float) -> float:
    """Map any east-positive longitude to [-180, 180).

    In-range values are returned bit-for-bit unchanged (no floating-point round trip), so
    catalogue and user coordinates are never perturbed.
    """
    if -180.0 <= lon_deg < 180.0:
        return lon_deg
    return ((lon_deg + 180.0) % 360.0) - 180.0


def validate_coordinates(lat_deg: object, lon_deg: object) -> tuple[float, float]:
    """Validate and normalise a lunar (lat, lon). Returns (lat, lon_east in [-180, 180)).

    Raises InvalidInputError (with `field`) for non-numeric, non-finite or out-of-range input.
    Longitude is accepted in [-180, 360]; anything beyond is rejected rather than wrapped, so a
    typo such as 1000 is reported instead of silently becoming 280.
    """
    lat = _finite_number(lat_deg, "lat")
    lon = _finite_number(lon_deg, "lon")
    if not -90.0 <= lat <= 90.0:
        raise InvalidInputError("lat must be within [-90, 90] degrees.", field="lat",
                                details={"value": lat})
    if not -180.0 <= lon <= 360.0:
        raise InvalidInputError("lon must be within [-180, 360] degrees (east-positive).",
                                field="lon", details={"value": lon})
    return lat, normalise_longitude(lon)


def custom_site(lat_deg: object, lon_deg: object, name: str | None = None) -> Site:
    lat, lon = validate_coordinates(lat_deg, lon_deg)
    return Site(
        id=f"custom:{lat:.6f},{lon:.6f}",
        name=name or f"Custom ({lat:.4f}, {lon:.4f})",
        lat_deg=lat,
        lon_deg_east=lon,
        kind=SiteKind.CUSTOM,
        notes="User-entered coordinates; no source reference.",
    )


def _parse_site(raw: dict[str, Any]) -> Site:
    kind = SiteKind(raw["kind"])
    if kind is SiteKind.CUSTOM:
        raise ValueError(f"catalogue must not contain custom sites: {raw['id']}")
    sources = tuple(SourceRef(**s) for s in raw.get("sources", ()))
    if not sources:
        raise ValueError(f"catalogue site {raw['id']} has no primary-source reference")
    for s in sources:
        if not s.url.startswith("https://"):
            raise ValueError(f"site {raw['id']}: source url must be https: {s.url}")
    lat, lon = validate_coordinates(raw["lat_deg"], raw["lon_deg_east"])
    return Site(
        id=raw["id"], name=raw["name"], lat_deg=lat, lon_deg_east=lon, kind=kind,
        sources=sources, reference_height_m=raw.get("reference_height_m"),
        reference_height_source=raw.get("reference_height_source"), notes=raw.get("notes", ""),
    )


def load_catalogue(path: Path) -> tuple[Site, ...]:
    """Load and strictly validate the curated catalogue (raises on any policy violation)."""
    doc = json.loads(path.read_text(encoding="utf-8"))
    if doc.get("lon_convention") != LON_CONVENTION or doc.get("lat_convention") != LAT_CONVENTION:
        raise ValueError("catalogue coordinate convention does not match engine convention")
    sites = tuple(_parse_site(r) for r in doc["sites"])
    ids = [s.id for s in sites]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate site ids in catalogue")
    return sites
