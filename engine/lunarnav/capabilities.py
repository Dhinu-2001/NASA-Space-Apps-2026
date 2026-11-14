"""Honest registry of what the engine can and cannot do.

Every scientific capability is listed with a status so neither the API nor the UI can imply that
unbuilt science exists. Statuses change only when the owning stage passes its gate.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CapabilityStatus(StrEnum):
    NOT_IMPLEMENTED = "not_implemented"
    IMPLEMENTED_UNVALIDATED = "implemented_unvalidated"
    VALIDATED = "validated"


@dataclass(frozen=True)
class Capability:
    key: str
    title: str
    stage: int
    status: CapabilityStatus = CapabilityStatus.NOT_IMPLEMENTED


CAPABILITIES: tuple[Capability, ...] = (
    Capability("sites", "Site catalogue and coordinate validation", 2,
               CapabilityStatus.IMPLEMENTED_UNVALIDATED),
    Capability("dem", "LOLA DEM ingestion and elevation lookup", 2,
               CapabilityStatus.IMPLEMENTED_UNVALIDATED),
    Capability("ephemeris", "Sun and Earth azimuth/elevation (SPICE)", 3,
               CapabilityStatus.VALIDATED),
    Capability("horizon", "Terrain horizon profile", 4,
               CapabilityStatus.VALIDATED),
    Capability("visibility", "Terrain-corrected Sun/Earth visibility and intervals", 5,
               CapabilityStatus.VALIDATED),
    Capability("scenarios", "Scenario comparison and delay simulator", 6,
               CapabilityStatus.VALIDATED),
    Capability("engineering", "Solar power, antenna mask, slope", 8),
)
