"""Terrain-corrected Sun / Earth visibility, transitions, intervals and position-sensitivity bands (Stage 5).

Combines the Stage 3 ephemeris (apparent az/el and angular size of the body) with the Stage 4 terrain horizon.

Definitions (docs/stage0/02_Scientific_Methodology.md section 6, decision E2). For each body and time the
engine computes THREE states and always labels which one a metric uses:
  centre_visible    disc-centre elevation > terrain horizon at the centre azimuth
  any_part_visible  some part of the disc is above the terrain horizon
  fully_visible     the whole disc is above the terrain horizon
Headline: Sun = any_part_visible (any direct illumination); Earth = centre_visible (antenna pointing).
This is geometric line of sight / direct illumination only: not link availability, not irradiance.

Disc model: a circle of angular radius rho on the sky. At azimuth offset d from the centre the disc spans
elevations el +/- rho*sqrt(1 - t^2) with d = t * rho / cos(el) (t in [-1, 1], clamped to +/-180 deg).
The terrain horizon is read between its 0.25-deg samples as the MAX of the two bracketing samples, so
sampling can only make the result more obstructed, never less (visibility is never over-stated by
interpolation).

Honesty rules (decision S7):
  * A step whose horizon (at any azimuth the disc spans) is `truncated` or has a `data_gap` is flagged
    `horizon_complete = false`. A step that looks visible there is `unverified_visible`: the horizon is a lower
    bound, so "visible" is an upper bound on truth. Such results are labelled, never presented as certain.
  * Transitions are found by bisection on the visibility PREDICATE (not by interpolating elevations), to 1 s.
    An event shorter than the sampling step that falls entirely between two samples is not detected.
  * Intervals touching the window boundary are marked open_start / open_end and excluded from the
    `*_closed_only` extrema.

Position sensitivity (user requirement at Stage 5 approval): every headline result is recomputed with the
observer displaced by the assumed position uncertainty (default 100 m, configurable) in `n_directions`
compass directions, with the SAME ephemeris and DEM. The spread is attached to each interval boundary, each
metric and each time step. It is a sensitivity to the INPUT position, not an error bar on the astronomy or
terrain computation, and it is a sample of displacements, not a proven bound. It is computed only where the
terrain data support it (complete horizon at the nominal and every displaced position); otherwise its status
is `not_computed` with the reason. It is never extrapolated.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import numpy as np

from .ephemeris import MAX_SAMPLES, EphemerisService, format_utc
from .errors import InvalidInputError, LunarNavError
from .frames import destination_deg
from .horizon import HorizonProfile, HorizonService
from .provenance import calculation_metadata
from .sites import validate_coordinates

DEFAULT_POSITION_BAND_M = 100.0
DEFAULT_DIRECTIONS = 8
MAX_POSITION_BAND_M = 5000.0
N_DISC_POINTS = 41
BISECT_TOL_S = 1.0
MATCH_WINDOW_S = 12 * 3600.0
HEADLINE = {"sun": "any_part", "earth": "centre"}
STATE_NAMES = ("centre", "any_part", "fully")
BAND_METRIC_KEYS = (
    "total_visible_s", "visible_fraction", "n_visible_intervals",
    "longest_visible_s_closed_only", "longest_visible_s_including_open",
    "longest_not_visible_s_closed_only", "longest_not_visible_s_including_open",
)


# ---------------------------------------------------------------- horizon lookup and disc states

def horizon_lookup(profile: HorizonProfile, az_deg: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Horizon elevation (deg) at arbitrary azimuths = max of the two bracketing samples, and a bool array
    that is True where any bracketing sample is truncated / data_gap / has no valid value. Missing (NaN)
    horizon counts as -90 deg (nothing known to block) and is therefore also flagged incomplete."""
    n = profile.n_azimuths
    a = (np.asarray(az_deg, dtype=float) % 360.0) / (360.0 / n)
    i0 = np.floor(a).astype(np.intp) % n
    on_grid = np.abs(a - np.round(a)) < 1e-9
    i0 = np.where(on_grid, np.round(a).astype(np.intp) % n, i0)
    i1 = np.where(on_grid, i0, (i0 + 1) % n)
    h = profile.horizon_elevation_deg
    h0, h1 = h[i0], h[i1]
    value = np.where(np.isnan(h0), h1, np.where(np.isnan(h1), h0, np.maximum(h0, h1)))
    bad = profile.truncated | profile.data_gap | np.isnan(h)
    incomplete = bad[i0] | bad[i1]
    return np.where(np.isnan(value), -90.0, value), incomplete


def disc_states(profile: HorizonProfile, az_deg: np.ndarray, el_deg: np.ndarray, rho_deg: np.ndarray
                ) -> dict[str, np.ndarray]:
    """Per-time visibility states of a sky disc (centre az/el, angular radius rho) against a horizon."""
    az = np.atleast_1d(np.asarray(az_deg, dtype=float))
    el = np.atleast_1d(np.asarray(el_deg, dtype=float))
    rho = np.atleast_1d(np.asarray(rho_deg, dtype=float))
    h_c, inc_c = horizon_lookup(profile, az)
    t = np.linspace(-1.0, 1.0, N_DISC_POINTS)
    cos_el = np.maximum(np.cos(np.radians(np.clip(el, -89.0, 89.0))), 1e-3)
    offset = np.clip(t[None, :] * (rho / cos_el)[:, None], -180.0, 180.0)
    h_pts, inc_pts = horizon_lookup(profile, az[:, None] + offset)
    half = rho[:, None] * np.sqrt(1.0 - t[None, :] ** 2)
    top, bot = el[:, None] + half, el[:, None] - half
    return {
        "centre": el > h_c,
        "any_part": (top > h_pts).any(axis=1),
        "fully": (bot > h_pts).all(axis=1),
        "horizon_at_centre_deg": h_c,
        "complete": ~(inc_c | inc_pts.any(axis=1)),
    }


# ---------------------------------------------------------------- one observer position

@dataclass
class _Run:
    lat: float
    lon: float
    h_radius_m: float                     # height above the reference sphere used for the ephemeris observer
    profile: HorizonProfile
    az: dict[str, np.ndarray] = field(default_factory=dict)
    el: dict[str, np.ndarray] = field(default_factory=dict)
    rho: dict[str, np.ndarray] = field(default_factory=dict)
    st: dict[str, dict[str, np.ndarray]] = field(default_factory=dict)


# ---------------------------------------------------------------- transitions and intervals

def _bisect(pred: Callable[[float], bool], t_lo: float, t_hi: float, s_lo: bool) -> float:
    """Time (s) of the state change inside (t_lo, t_hi), localised to BISECT_TOL_S on the predicate."""
    lo, hi = t_lo, t_hi
    while hi - lo > BISECT_TOL_S:
        mid = 0.5 * (lo + hi)
        if pred(mid) == s_lo:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def find_transitions(times_s: np.ndarray, state: np.ndarray, pred: Callable[[float], bool] | None
                     ) -> list[tuple[float, bool]]:
    """[(time_s, new_state)] for every sampled state change; refined by bisection when `pred` is given."""
    out: list[tuple[float, bool]] = []
    for i in np.flatnonzero(state[1:] != state[:-1]):
        lo, hi = float(times_s[i]), float(times_s[i + 1])
        t = _bisect(pred, lo, hi, bool(state[i])) if pred is not None else hi
        out.append((t, bool(state[i + 1])))
    return out


def build_intervals(t_start: float, t_end: float, initial: bool, transitions: list[tuple[float, bool]]
                    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(true_intervals, false_intervals) covering [t_start, t_end] with open_start/open_end flags."""
    bounds = [t_start] + [t for t, _ in transitions] + [t_end]
    states = [initial] + [s for _, s in transitions]
    true_iv: list[dict[str, Any]] = []
    false_iv: list[dict[str, Any]] = []
    for k, s in enumerate(states):
        iv = {"start_s": bounds[k], "end_s": bounds[k + 1], "open_start": k == 0, "open_end": k == len(states) - 1,
              "duration_s": bounds[k + 1] - bounds[k]}
        (true_iv if s else false_iv).append(iv)
    return true_iv, false_iv


def interval_metrics(true_iv: list[dict[str, Any]], false_iv: list[dict[str, Any]], window_s: float
                     ) -> dict[str, Any]:
    def longest(ivs: list[dict[str, Any]]) -> tuple[float | None, float | None, bool]:
        closed = [i["duration_s"] for i in ivs if not i["open_start"] and not i["open_end"]]
        top = max((i["duration_s"] for i in ivs), default=None)
        # An open interval's true length is >= what we observe, so if one ties or leads, the extremum is unsettled.
        unsettled = top is not None and any(
            (i["open_start"] or i["open_end"]) and i["duration_s"] >= top - 1e-9 for i in ivs)
        return (max(closed) if closed else None, top, unsettled)

    vc, va, v_open = longest(true_iv)
    dc, da, d_open = longest(false_iv)
    total = sum(i["duration_s"] for i in true_iv)
    return {
        "window_s": window_s,
        "total_visible_s": total,
        "visible_fraction": total / window_s if window_s > 0 else None,
        "n_visible_intervals": len(true_iv),
        "longest_visible_s_closed_only": vc,
        "longest_visible_s_including_open": va,
        "longest_visible_includes_open_interval": v_open,
        "longest_not_visible_s_closed_only": dc,
        "longest_not_visible_s_including_open": da,
        "longest_not_visible_includes_open_interval": d_open,
    }


def _utc(start: datetime, t_s: float) -> str:
    """UTC string for an offset in seconds, rounded to the whole second (events are localised to 1 s)."""
    return format_utc(start + timedelta(seconds=round(t_s)))


# ---------------------------------------------------------------- result container

@dataclass
class VisibilityResult:
    data: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return self.data


class VisibilityService:
    """Computes visibility series, transitions, intervals and position-sensitivity bands."""

    def __init__(self, ephemeris: EphemerisService, horizon: HorizonService) -> None:
        self.eph = ephemeris
        self.hz = horizon

    # ---- building one run -------------------------------------------------
    def _run(self, lat: float, lon: float, observer_height_m: float, start: datetime, step_s: float, n: int,
             bodies: tuple[str, ...], hz_kwargs: dict[str, Any]) -> _Run:
        prof = self.hz.profile(lat, lon, observer_height_m, **hz_kwargs)
        h_radius = float(prof.meta["observer"]["observer_radius_height_m"])
        res = self.eph.series(lat, lon, start, step_s, n, bodies, h_radius)
        run = _Run(lat, lon, h_radius, prof)
        for b in bodies:
            s = res.bodies[b]
            run.az[b], run.el[b] = np.array(s.azimuth_deg), np.array(s.elevation_deg)
            run.rho[b] = np.array(s.angular_diameter_deg) / 2.0
            run.st[b] = disc_states(prof, run.az[b], run.el[b], run.rho[b])
        return run

    def _predicate(self, run: _Run, body: str, state: str, start: datetime) -> Callable[[float], bool]:
        def pred(t_s: float) -> bool:
            r = self.eph.series(run.lat, run.lon, start + timedelta(seconds=t_s), 1.0, 1, (body,),
                                run.h_radius_m)
            b = r.bodies[body]
            return bool(disc_states(run.profile, np.array(b.azimuth_deg), np.array(b.elevation_deg),
                                    np.array(b.angular_diameter_deg) / 2.0)[state][0])
        return pred

    def _geo_predicate(self, run: _Run, body: str, head: str, start: datetime) -> Callable[[float], bool]:
        def pred(t_s: float) -> bool:
            r = self.eph.series(run.lat, run.lon, start + timedelta(seconds=t_s), 1.0, 1, (body,),
                                run.h_radius_m)
            b = r.bodies[body]
            el = b.elevation_deg[0]
            return bool(el + b.angular_diameter_deg[0] / 2.0 > 0.0) if head == "any_part" else bool(el > 0.0)
        return pred

    def _transitions(self, run: _Run, body: str, state: str, times_s: np.ndarray, start: datetime,
                     refine: bool) -> list[tuple[float, bool]]:
        pred = self._predicate(run, body, state, start) if refine else None
        return find_transitions(times_s, run.st[body][state], pred)

    # ---- public API -------------------------------------------------------
    def evaluate(
        self, lat_deg: Any, lon_deg_east: Any, start: datetime, step_s: float, n_samples: int,
        observer_height_m: float, bodies: tuple[str, ...] = ("sun", "earth"), *,
        position_uncertainty_m: float | None = DEFAULT_POSITION_BAND_M, n_directions: int = DEFAULT_DIRECTIONS,
        refine: bool = True, include_series: bool = True, horizon_kwargs: dict[str, Any] | None = None,
    ) -> VisibilityResult:
        lat, lon = validate_coordinates(lat_deg, lon_deg_east)
        for b in bodies:
            if b not in HEADLINE:
                raise InvalidInputError(f"bodies must be from {sorted(HEADLINE)}", field="bodies")
        if not bodies or len(set(bodies)) != len(bodies):
            raise InvalidInputError("bodies must be a non-empty list of unique names", field="bodies")
        if not isinstance(n_samples, int) or isinstance(n_samples, bool) or not 1 <= n_samples <= MAX_SAMPLES:
            raise InvalidInputError(f"number of samples must be 1..{MAX_SAMPLES}", field="step_seconds")
        band = position_uncertainty_m
        if band is not None and (isinstance(band, bool) or not isinstance(band, int | float)
                                 or not math.isfinite(band) or not 0.0 <= band <= MAX_POSITION_BAND_M):
            raise InvalidInputError(f"position_uncertainty_m must be in [0, {MAX_POSITION_BAND_M:g}]",
                                    field="position_uncertainty_m")
        if not isinstance(n_directions, int) or isinstance(n_directions, bool) or not 4 <= n_directions <= 72:
            raise InvalidInputError("n_directions must be an integer in [4, 72]", field="n_directions")
        hzk = dict(horizon_kwargs or {})

        times_s = np.arange(n_samples) * float(step_s)
        window_s = float(times_s[-1])
        nominal = self._run(lat, lon, observer_height_m, start, step_s, n_samples, bodies, hzk)

        # ---- position-sensitivity runs (or an explicit reason why not) ----
        shifts: list[_Run] = []
        sens_status: dict[str, Any]
        if band is None or band == 0.0 or n_samples < 1:
            sens_status = {"status": "not_computed", "reason": "position_uncertainty_m is 0 or not requested"}
        else:
            sens_status = {"status": "computed"}
            reason = self._data_support_problem(nominal.profile)
            if reason is None:
                try:
                    for k in range(n_directions):
                        la, lo = destination_deg(lat, lon, 360.0 * k / n_directions, band)
                        shifts.append(self._run(la, lo, observer_height_m, start, step_s, n_samples, bodies, hzk))
                        problem = self._data_support_problem(shifts[-1].profile)
                        if problem is not None:
                            reason = f"displaced position {k + 1}/{n_directions}: {problem}"
                            break
                except LunarNavError as e:  # displaced point outside DEM coverage / NoData: do not extrapolate
                    reason = f"displaced position lacks terrain data ({e.message})"
            if reason is not None:
                shifts = []
                sens_status = {"status": "not_computed", "reason": reason}

        out_bodies: dict[str, Any] = {}
        for b in bodies:
            out_bodies[b] = self._body_result(b, nominal, shifts, times_s, start, window_s, refine, include_series,
                                              sens_status["status"] == "computed")

        pos_block = {
            **sens_status,
            "data_class": "calculated",
            "kind": "sensitivity of the result to the INPUT observer position; not an error bar on the astronomy "
                    "or terrain calculation, which are exact for the given inputs",
            "assumed_position_uncertainty_m": band,
            "assumption": f"observer position uncertain by +/-{band:g} m" if band is not None else None,
            "n_directions": n_directions if shifts else None,
            "method": "full recomputation (ephemeris, horizon, visibility, boundary bisection) at displaced "
                      "positions on a circle of the stated radius; boundary band = [earliest, latest] over the "
                      "nominal and displaced runs",
            "limitations": "a sample of displacements, not a proven bound; applies only where terrain data "
                           "support it; assumes the DEM itself is correct",
        }
        n_steps = n_samples
        data = {
            "data_class": "calculated",
            "observer": {"lat_deg": lat, "lon_deg_east": lon, "observer_height_above_surface_m": observer_height_m,
                         "ground_height_m": nominal.profile.meta["observer"]["ground_height_m"],
                         "frame": "MOON_ME"},
            "window": {"start_utc": format_utc(start), "end_utc": format_utc(start + timedelta(seconds=window_s)),
                       "step_seconds": step_s, "n_samples": n_steps,
                       "note": "the window ends at the last sample, which may be before the requested end"},
            "definitions": {
                "headline": {"sun": "any_part_visible (any direct illumination reaches the observer)",
                             "earth": "centre_visible (disc centre above the terrain horizon; geometric line of "
                                      "sight, not link availability)"},
                "states": ["centre_visible", "any_part_visible", "fully_visible"],
                "disc_model": f"circle of the ephemeris angular radius, {N_DISC_POINTS} points across its azimuth span",
                "horizon_interpolation": "max of the two bracketing horizon samples (never over-states visibility)",
            },
            "horizon": {"az_step_deg": nominal.profile.meta["parameters"]["az_step_deg"],
                        "windows": [w["window_id"] for w in nominal.profile.meta["windows"]],
                        "summary": nominal.profile.summary(),
                        "served_from": nominal.profile.served_from,
                        "cache_key": nominal.profile.meta.get("cache_key")},
            "bodies": out_bodies,
            "position_sensitivity": pos_block,
            "provenance": calculation_metadata(
                self.eph.provenance(), nominal.profile.meta,
                {"start_utc": format_utc(start), "step_seconds": step_s, "n_samples": n_samples,
                 "observer_height_above_surface_m": observer_height_m, "bodies": list(bodies),
                 "position_uncertainty_m": band, "n_directions": n_directions, "refine": refine,
                 "bisection_tolerance_s": BISECT_TOL_S, "match_window_s": MATCH_WINDOW_S,
                 "disc_points": N_DISC_POINTS, "az_step_deg": nominal.profile.meta["parameters"]["az_step_deg"]}),
            "limitations": [
                "Geometric line of sight / direct illumination only. Not irradiance, not link availability.",
                "Events shorter than the sampling step that fall entirely between samples are not detected.",
                ("Steps flagged horizon_complete=false are lower bounds on obstruction: 'visible' there is "
                "unverified (upper bound)."),
                ("Terrain horizon is from a DEM (interpolated between LOLA tracks); boulders and the lander "
                "body are not modelled."),
            ],
        }
        return VisibilityResult(data)

    # ---- helpers ----------------------------------------------------------
    @staticmethod
    def _data_support_problem(prof: HorizonProfile) -> str | None:
        s = prof.summary()
        if s["n_truncated"] or s["n_data_gap"]:
            return (f"terrain coverage is insufficient to certify the horizon ({s['n_truncated']} truncated and "
                    f"{s['n_data_gap']} data-gap azimuths of {s['n_azimuths']}); sensitivity is not extrapolated")
        return None

    def _body_result(self, body: str, nom: _Run, shifts: list[_Run], times_s: np.ndarray, start: datetime,
                     window_s: float, refine: bool, include_series: bool, have_sens: bool) -> dict[str, Any]:
        head = HEADLINE[body]
        st = nom.st[body]
        n = times_s.size
        res: dict[str, Any] = {"headline_state": f"{head}_visible"}

        # sensitivity per step
        sens_deg = None
        robust = None
        if have_sens:
            h_nom = st["horizon_at_centre_deg"]
            sens_deg = np.zeros(n)
            robust = np.ones(n, dtype=bool)
            for r in shifts:
                sens_deg = np.maximum(sens_deg, np.abs(r.st[body]["horizon_at_centre_deg"] - h_nom))
                robust &= r.st[body][head] == st[head]
        unverified = st[head] & ~st["complete"]

        if include_series:
            geo_head = (nom.el[body] + nom.rho[body] > 0) if head == "any_part" else (nom.el[body] > 0)
            res["series"] = {
                "times_s": [float(t) for t in times_s],
                "azimuth_deg": [round(float(v), 6) for v in nom.az[body]],
                "elevation_deg": [round(float(v), 6) for v in nom.el[body]],
                "angular_radius_deg": [round(float(v), 6) for v in nom.rho[body]],
                "terrain_horizon_at_centre_deg": [round(float(v), 6) for v in st["horizon_at_centre_deg"]],
                "geometric_headline_above_local_horizontal": [bool(v) for v in geo_head],
                "centre_visible": [bool(v) for v in st["centre"]],
                "any_part_visible": [bool(v) for v in st["any_part"]],
                "fully_visible": [bool(v) for v in st["fully"]],
                "partially_visible": [bool(a and not f) for a, f in zip(st["any_part"], st["fully"], strict=True)],
                "headline_visible": [bool(v) for v in st[head]],
                "horizon_complete": [bool(v) for v in st["complete"]],
                "unverified_visible": [bool(v) for v in unverified],
                "position_sensitivity_deg": None if sens_deg is None else [round(float(v), 6) for v in sens_deg],
                "headline_state_robust_to_position": None if robust is None else [bool(v) for v in robust],
            }
        res["terrain_effect"] = {
            "headline_visible_steps": int(st[head].sum()),
            "geometric_headline_steps": int(((nom.el[body] + nom.rho[body] > 0) if head == "any_part"
                                             else (nom.el[body] > 0)).sum()),
            "steps_blocked_by_terrain_only": int((((nom.el[body] + nom.rho[body] > 0) if head == "any_part"
                                                   else (nom.el[body] > 0)) & ~st[head]).sum()),
            "n_steps": n,
        }
        res["completeness"] = {"steps_with_incomplete_horizon": int((~st["complete"]).sum()),
                               "unverified_visible_steps": int(unverified.sum()),
                               "visibility_is_upper_bound": bool(unverified.any())}

        # transitions / intervals / metrics for each state; sensitivity bands on the headline
        res["states"] = {}
        for name in STATE_NAMES:
            trans = self._transitions(nom, body, name, times_s, start, refine)
            true_iv, false_iv = build_intervals(0.0, window_s, bool(st[name][0]), trans)
            entry: dict[str, Any] = {
                "refined_to_s": BISECT_TOL_S if refine else None,
                "intervals": [self._fmt_interval(i, start) for i in true_iv],
                "not_visible_intervals": [self._fmt_interval(i, start) for i in false_iv],
                "transitions": [{"time_utc": _utc(start, t), "time_s": t,
                                 "to": "visible" if s else "not_visible"} for t, s in trans],
                "metrics": interval_metrics(true_iv, false_iv, window_s),
            }
            if name == head:
                entry["is_headline"] = True
                entry["position_sensitivity"] = self._interval_bands(
                    body, name, nom, shifts, times_s, start, window_s, refine, true_iv, false_iv, trans,
                    entry["metrics"]) if have_sens else {"status": "not_computed"}
                if have_sens:
                    self._attach_bands(entry, start)
            res["states"][name] = entry
        # Geometric (terrain-free) counterpart: same body/definition, horizon = local horizontal (0 deg).
        # Kept alongside the terrain-corrected result everywhere so the gap is always visible. It does not
        # depend on the terrain; shifting the observer 100 m rotates the local vertical by only ~0.003 deg.
        geo = (nom.el[body] + nom.rho[body] > 0) if head == "any_part" else (nom.el[body] > 0)
        geo_pred = self._geo_predicate(nom, body, head, start) if refine else None
        g_trans = find_transitions(times_s, geo, geo_pred)
        g_true, g_false = build_intervals(0.0, window_s, bool(geo[0]), g_trans)
        res["geometric"] = {
            "definition": f"{head}_visible against the local horizontal (elevation > 0), no terrain",
            "intervals": [self._fmt_interval(i, start) for i in g_true],
            "not_visible_intervals": [self._fmt_interval(i, start) for i in g_false],
            "transitions": [{"time_utc": _utc(start, t), "time_s": t, "to": "visible" if s else "not_visible"}
                            for t, s in g_trans],
            "metrics": interval_metrics(g_true, g_false, window_s),
            "position_sensitivity": {
                "status": "not_applicable",
                "reason": "terrain-independent; a 100 m observer shift rotates the local vertical by "
                          f"{math.degrees(100.0 / 1_737_400.0):.4f} deg"},
        }
        res["headline"] = {"state": f"{head}_visible", "intervals": res["states"][head]["intervals"],
                           "not_visible_intervals": res["states"][head]["not_visible_intervals"],
                           "metrics": res["states"][head]["metrics"],
                           "position_sensitivity": res["states"][head]["position_sensitivity"]}
        return res

    @staticmethod
    def _fmt_interval(iv: dict[str, Any], start: datetime) -> dict[str, Any]:
        return {"start_utc": _utc(start, iv["start_s"]), "end_utc": _utc(start, iv["end_s"]),
                "start_s": iv["start_s"], "end_s": iv["end_s"], "duration_s": iv["duration_s"],
                "open_start": iv["open_start"], "open_end": iv["open_end"]}

    def _interval_bands(self, body: str, state: str, nom: _Run, shifts: list[_Run], times_s: np.ndarray,
                        start: datetime, window_s: float, refine: bool, true_iv: list[dict[str, Any]],
                        false_iv: list[dict[str, Any]], trans: list[tuple[float, bool]],
                        nom_metrics: dict[str, Any]) -> dict[str, Any]:
        """Spread of every boundary and metric over the displaced runs (nominal included)."""
        runs_trans: list[list[tuple[float, bool]]] = []
        runs_metrics: list[dict[str, Any]] = []
        for r in shifts:
            tr = self._transitions(r, body, state, times_s, start, refine)
            runs_trans.append(tr)
            t_iv, f_iv = build_intervals(0.0, window_s, bool(r.st[body][state][0]), tr)
            runs_metrics.append(interval_metrics(t_iv, f_iv, window_s))

        # per-transition band: nearest same-type transition (rise/fall) in each displaced run, within the
        # match window; unmatched ones make the band explicitly incomplete.
        bands: list[dict[str, Any]] = []
        for t0, new_state in trans:
            times = [t0]
            missing = 0
            for tr in runs_trans:
                cand = [t for t, s in tr if s == new_state and abs(t - t0) <= MATCH_WINDOW_S]
                if cand:
                    times.append(min(cand, key=lambda t: abs(t - t0)))
                else:
                    missing += 1
            bands.append({
                "nominal_time_s": t0,
                "earliest_s": min(times), "latest_s": max(times),
                "earliest_utc": _utc(start, min(times)), "latest_utc": _utc(start, max(times)),
                "band_width_s": max(times) - min(times),
                "displaced_runs_without_matching_event": missing,
                "band_complete": missing == 0,
            })
        matched = {round(t, 3) for b in bands for t in (b["earliest_s"], b["latest_s"])}
        extra = sum(1 for tr in runs_trans for t, s in tr
                    if not any(abs(t - t0) <= MATCH_WINDOW_S and s == ns for t0, ns in trans)
                    and round(t, 3) not in matched)

        def span(key: str) -> list[float | None]:
            vals = [m[key] for m in runs_metrics + [nom_metrics] if m[key] is not None]
            return [min(vals), max(vals)] if vals else [None, None]

        return {
            "status": "computed", "data_class": "calculated",
            "boundary_bands": bands,
            "events_only_in_displaced_runs": extra,
            "metric_bands": {k: span(k) for k in BAND_METRIC_KEYS},
            # Metrics of each displaced run (same direction order as `directions_deg`) and of the nominal run.
            # A comparison of two dates at the SAME site uses these pairwise: the position error is one physical
            # offset shared by both dates, so deltas must be formed per displacement, not from two bands.
            "directions_deg": [360.0 * k / len(shifts) for k in range(len(shifts))],
            "per_displacement_metrics": [{k: m[k] for k in BAND_METRIC_KEYS} for m in runs_metrics],
            "nominal_metrics": {k: nom_metrics[k] for k in BAND_METRIC_KEYS},
            "max_boundary_band_width_s": max((b["band_width_s"] for b in bands), default=0.0),
        }

    def _attach_bands(self, entry: dict[str, Any], start: datetime) -> None:
        """Copy each boundary's band onto the interval that starts / ends at it, so a reader of an interval
        always sees how far its start and end could move."""
        bands = {round(b["nominal_time_s"], 3): b for b in entry["position_sensitivity"]["boundary_bands"]}
        for key in ("intervals", "not_visible_intervals"):
            for iv in entry[key]:
                for side, flag in (("start", "open_start"), ("end", "open_end")):
                    b = None if iv[flag] else bands.get(round(iv[f"{side}_s"], 3))
                    iv[f"{side}_band"] = None if b is None else {
                        "earliest_utc": b["earliest_utc"], "latest_utc": b["latest_utc"],
                        "width_s": b["band_width_s"], "complete": b["band_complete"]}
