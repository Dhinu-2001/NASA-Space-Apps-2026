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
               CapabilityStatus.VALIDATED),
    Capability("dem", "LOLA DEM ingestion and elevation lookup", 2,
               CapabilityStatus.VALIDATED),
    Capability("ephemeris", "Sun and Earth azimuth/elevation (SPICE)", 3,
               CapabilityStatus.VALIDATED),
    Capability("horizon", "Terrain horizon profile", 4,
               CapabilityStatus.VALIDATED),
    Capability("visibility", "Terrain-corrected Sun/Earth visibility and intervals", 5,
               CapabilityStatus.VALIDATED),
    Capability("scenarios", "Scenario comparison and delay simulator", 6,
               CapabilityStatus.VALIDATED),
    Capability("engineering", "Solar energy availability (idealised direct-beam upper bound)", 8,
               CapabilityStatus.VALIDATED),
    # Integration approved by the owner 2026-11-15, but NOT validated: it has not had the independent verification pass IM-2's terrain had.
    Capability("terrain_chandrayaan3", "Chandrayaan-3 60 m terrain (LDEM_60S_60MPP_ADJ) through the unchanged pipeline", 11,
               CapabilityStatus.IMPLEMENTED_UNVALIDATED),
)
