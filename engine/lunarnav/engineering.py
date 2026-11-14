"""Stage 8 (deliberately narrow): idealised direct-beam solar ENERGY AVAILABILITY derived from Stage 5/6 results.

What this is: the electrical energy a flat panel of stated area and efficiency would produce IF it faced the Sun
whenever any part of the Sun's disc is above the terrain horizon, at a constant irradiance. It is therefore an
UPPER BOUND on direct-beam energy at the given site/window. It is `data_class: calculated`, and every input that is not
a measurement is a labelled assumption.

What this is NOT: a power-system model. There is no incidence-angle model (a panel is assumed to track the Sun), no
partial-disc irradiance fraction, no panel temperature, degradation, lander self-shadowing, battery or thermal model.
It is never presented as "battery state" or as a mission power budget.

Reuse rule (owner instruction): nothing astronomical, terrain or visibility is recomputed here. The visible times, their
position-sensitivity bands, the geometric counterpart and the open-interval flags are READ from a Stage 6 scenario result;
this module only multiplies them by `eta * A * I`. Because energy is linear in visible time, the position band of the
energy is the position band of the visible time scaled by the same factor, with no new uncertainty invented.
"""

from __future__ import annotations

import math
from typing import Any

from .errors import InvalidInputError

# Total solar irradiance at 1 AU. Nominal value used by IAU 2015 Resolution B3 (1361 W/m^2). An ASSUMPTION here:
# the Earth-Sun distance varies about +/-3.4 % over the year (irradiance +/-6.9 %), which is NOT modelled.
SOLAR_CONSTANT_W_M2 = 1361.0
IRRADIANCE_RANGE_W_M2 = (1000.0, 1500.0)
MAX_AREA_M2 = 10_000.0

ASSUMPTIONS = [
    ("Panel faces the Sun whenever any part of the Sun's disc is above the terrain horizon (sun-tracking; no incidence-angle "
    "loss). A fixed panel would produce less."),
    "A partly visible Sun counts as fully illuminating the panel (the whole-disc energy is given as a lower bracket).",
    ("Constant irradiance equal to the stated value (default: 1361 W/m^2, the nominal solar constant at 1 AU); the +/-3.4 % "
    "Earth-Sun distance variation over the year is not modelled."),
    "Constant panel efficiency, as supplied by the user; no temperature or degradation effect, no dust, no lander self-shadowing.",
    "Terrain is the LOLA DEM horizon; boulders and the lander body are not modelled (see docs/stage9/KNOWN_LIMITATIONS.md).",
]
LIMITATIONS = [
    "Idealised direct-beam energy: an upper bound, not a power budget and not battery state.",
    ("Position sensitivity is carried from the visibility result (+/- the stated position uncertainty); it is a sensitivity to the "
    "input position, not an error bar on the physics, and a sample of displacements, not a proven bound."),
    "The whole-disc bracket has no position band (the band is computed for the headline state only).",
]


def _num(v: Any, name: str) -> float:
    if isinstance(v, bool) or not isinstance(v, int | float) or not math.isfinite(v):
        raise InvalidInputError(f"{name} must be a finite number", field=name)
    return float(v)


def validate_panel(area_m2: Any, efficiency: Any, irradiance_w_m2: Any = None) -> tuple[float, float, float, bool]:
    """Returns (area, efficiency, irradiance, irradiance_is_default). Raises a typed error naming the field."""
    area = _num(area_m2, "area_m2")
    if not 0.0 < area <= MAX_AREA_M2:
        raise InvalidInputError(f"area_m2 must be in (0, {MAX_AREA_M2:g}] square metres", field="area_m2")
    eff = _num(efficiency, "efficiency")
    if not 0.0 < eff <= 1.0:
        raise InvalidInputError("efficiency must be a fraction in (0, 1] (e.g. 0.30 for 30 %)", field="efficiency")
    if irradiance_w_m2 is None:
        return area, eff, SOLAR_CONSTANT_W_M2, True
    irr = _num(irradiance_w_m2, "irradiance_w_m2")
    lo, hi = IRRADIANCE_RANGE_W_M2
    if not lo <= irr <= hi:
        raise InvalidInputError(f"irradiance_w_m2 must be in [{lo:g}, {hi:g}] W/m^2", field="irradiance_w_m2")
    return area, eff, irr, False


def _scale(v: float | None, k: float) -> float | None:
    return None if v is None else v * k


def _band(b: list[float | None] | None, k: float) -> list[float | None]:
    if not b or b[0] is None or b[1] is None:
        return [None, None]
    return [b[0] * k, b[1] * k]


def solar_energy(scenario: dict[str, Any], area_m2: Any, efficiency: Any, irradiance_w_m2: Any = None) -> dict[str, Any]:
    """Idealised direct-beam solar energy for a SUPPORTED Stage 6 scenario result (see module docstring)."""
    area, eff, irr, irr_default = validate_panel(area_m2, efficiency, irradiance_w_m2)
    if scenario.get("status") != "supported":
        raise InvalidInputError("solar_energy needs a supported scenario; insufficient scenarios carry no figures",
                                field="scenario")
    peak_w = eff * area * irr                      # W of electrical output while illuminated (idealised)
    sun = scenario["bodies"]["sun"]
    tc, geo = sun["terrain_corrected"], sun["geometric"]
    w = scenario["window"]
    window_s = float((w["n_samples"] - 1) * w["step_seconds"])
    k_wh = peak_w / 3600.0                         # Wh per second of illumination
    window_h = window_s / 3600.0

    vis = tc["total_visible_s"]
    energy = {"nominal": vis["nominal"] * k_wh, "band": _band(vis["band"], k_wh)}
    mean_k = peak_w / window_s if window_s > 0 else 0.0
    mean_power = {"nominal": vis["nominal"] * mean_k, "band": _band(vis["band"], mean_k)}
    sunlit = {"nominal": vis["nominal"] / 3600.0, "band": _band(vis["band"], 1 / 3600.0)}
    dark = tc["longest_not_visible_s"]
    geo_s = geo["total_visible_s"]["nominal"]
    fr = tc.get("state_fractions") or {}
    bracket = None
    if fr.get("fully") is not None:
        bracket = {
            "whole_disc_energy_wh": fr["fully"] * window_s * k_wh,
            "any_part_energy_wh": fr["any_part"] * window_s * k_wh,
            "note": "Lower bracket: only periods when the WHOLE Sun disc is above the terrain count. Upper bracket = the headline "
                    "(any part of the disc). Nominal positions only; no position band for the whole-disc figure.",
        }
    return {
        "data_class": "calculated",
        "kind": "idealised direct-beam solar energy: an UPPER BOUND, not a power budget and not battery state",
        "status": "supported",
        "scenario_id": scenario["id"],
        "spec": scenario["spec"],
        "panel": {
            "area_m2": area, "efficiency": eff, "irradiance_w_m2": irr,
            "irradiance_is_default_assumption": irr_default,
            "peak_electrical_power_w": peak_w,
            "formula": "E[Wh] = efficiency x area[m^2] x irradiance[W/m^2] x illuminated time[h]",
        },
        "window_hours": window_h,
        "terrain_corrected": {
            "headline_state": sun["headline_state"],
            "energy_wh": energy,
            "mean_power_w": mean_power,
            "sunlit_hours": sunlit,
            "longest_without_direct_sunlight": {
                "hours": _scale(dark["including_open"], 1 / 3600.0),
                "band_hours": _band(dark.get("band_including_open"), 1 / 3600.0),
                "includes_open_interval": dark["includes_open_interval"],
                "note": "no energy is produced in this interval; if cut off by the window edge, its true length is at least this",
            },
        },
        "geometric": {
            "energy_wh": geo_s * k_wh,
            "mean_power_w": geo_s * mean_k,
            "sunlit_hours": geo_s / 3600.0,
            "note": "same panel against the local horizontal with no terrain (position-independent)",
        },
        "terrain_effect": {
            "energy_wh_terrain_minus_geometric": energy["nominal"] - geo_s * k_wh,
            "note": "negative: terrain removes sunlight the geometry allows; positive: the terrain horizon lies below the local horizontal",
        },
        "partial_disc_bracket": bracket,
        "position_sensitivity": scenario["position_sensitivity"],
        "assumptions": ASSUMPTIONS,
        "limitations": LIMITATIONS,
        "provenance": scenario.get("provenance"),
    }
