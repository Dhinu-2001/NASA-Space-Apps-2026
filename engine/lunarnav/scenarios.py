"""Stage 6: scenarios, multi-site / multi-date comparison and the mission delay simulator.

A scenario = (site, start date, duration, step, observer height, position uncertainty, ...). Its identity is
the SHA-256 of its canonical definition + model version + the DEM fingerprint (decision C5): the same inputs
always give the same id, and a changed model or DEM gives a new one. Results are cached as JSON files
(data/results/scenarios, git-ignored); no database.

Rules carried from the Stage 5 approval (user instructions):
  * A site whose terrain data do not support a position-sensitivity figure is reported as
    `terrain_data_insufficient` with the reason and NO numbers: not ranked, not scored, no "estimated" column,
    no upper-bound stand-in. Currently IM-2 is supported; IM-1 and Chandrayaan-3 are not.
  * Geometric and terrain-corrected results are both present in every scenario and every delta, so the gap
    between them is always visible.
  * Position sensitivity is carried into deltas. Two dates at the SAME site share one physical position error,
    so the delta band is formed per displacement (paired differences over the nominal run and every displaced
    run). Different sites have independent position errors, so their delta band is interval arithmetic of the
    two metric bands (conservative).
  * Totals/fractions are the robust headline; event timestamps carry their band; intervals touching the window
    edge are flagged open and any extremum or delta that involves one is marked unsettled.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from . import MODEL_VERSION
from .ephemeris import format_utc, parse_utc
from .errors import DataMissingError, InvalidInputError, OutOfDemCoverageError
from .sites import load_catalogue
from .visibility import DEFAULT_DIRECTIONS, DEFAULT_POSITION_BAND_M, VisibilityService

DEFAULT_OBSERVER_HEIGHT_M = 2.0  # decision C9: an assumption, reported as such
MAX_SCENARIOS = 12
MAX_DURATION_DAYS = 60.0
MAX_DELAY_DAYS = 365.0
MAX_OFFSETS = 10
MAX_SAMPLES = 20_000
BODIES = ("sun", "earth")
INSUFFICIENT = "terrain_data_insufficient"
SUPPORTED = "supported"


@dataclass(frozen=True)
class ScenarioSpec:
    site_id: str | None
    lat_deg: float
    lon_deg_east: float
    start_utc: datetime
    duration_days: float
    step_seconds: float
    observer_height_m: float
    observer_height_is_default: bool
    position_uncertainty_m: float
    n_directions: int
    az_step_deg: float
    label: str | None = None

    @property
    def n_samples(self) -> int:
        return math.floor(self.duration_days * 86400.0 / self.step_seconds + 1e-9) + 1

    def canonical(self) -> dict[str, Any]:
        """The identity-defining content (the label is not part of it)."""
        return {
            "site_id": self.site_id, "lat_deg": self.lat_deg, "lon_deg_east": self.lon_deg_east,
            "start_utc": format_utc(self.start_utc), "duration_days": self.duration_days,
            "step_seconds": self.step_seconds, "observer_height_m": self.observer_height_m,
            "position_uncertainty_m": self.position_uncertainty_m, "n_directions": self.n_directions,
            "az_step_deg": self.az_step_deg,
        }

    def public(self) -> dict[str, Any]:
        return {**self.canonical(), "observer_height_is_default_assumption": self.observer_height_is_default,
                "label": self.label, "n_samples": self.n_samples}


def _is_num(v: Any) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool) and math.isfinite(v)


class ScenarioStore:
    """JSON file cache of scenario results keyed by scenario id (git-ignored, regenerable)."""

    def __init__(self, data_dir: Path) -> None:
        self.dir = Path(data_dir) / "results" / "scenarios"

    def load(self, scenario_id: str) -> dict[str, Any] | None:
        if not (len(scenario_id) == 64 and all(c in "0123456789abcdef" for c in scenario_id)):
            return None
        path = self.dir / f"{scenario_id}.json"
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return doc if doc.get("id") == scenario_id and doc.get("model_version") == MODEL_VERSION else None

    def save(self, scenario_id: str, result: dict[str, Any]) -> None:
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            tmp = self.dir / f"{scenario_id}.tmp"
            tmp.write_text(json.dumps(result, sort_keys=True), encoding="utf-8")
            os.replace(tmp, self.dir / f"{scenario_id}.json")
        except OSError:
            pass  # cache only; the computed result is still returned


class ScenarioService:
    def __init__(self, data_dir: Path, visibility: VisibilityService) -> None:
        self.data_dir = Path(data_dir)
        self.vis = visibility
        self.store = ScenarioStore(self.data_dir)
        self.catalogue = {s.id: s for s in load_catalogue(self.data_dir / "catalogue" / "sites.json")}

    # ---------------------------------------------------------------- specs
    def make_spec(self, site: dict[str, Any], start_utc: Any, *, duration_days: Any = 30.0,
                  step_seconds: Any = 900.0, observer_height_m: Any = None,
                  position_uncertainty_m: Any = DEFAULT_POSITION_BAND_M, n_directions: Any = DEFAULT_DIRECTIONS,
                  az_step_deg: Any = 0.25, label: str | None = None) -> ScenarioSpec:
        site_id = site.get("site_id")
        has_coords = site.get("lat") is not None or site.get("lon") is not None
        if site_id and has_coords:
            raise InvalidInputError("Give either site_id or lat/lon, not both", field="site")
        if site_id:
            cat = self.catalogue.get(site_id)
            if cat is None:
                raise InvalidInputError(f"Unknown site_id '{site_id}'", field="site_id",
                                        details={"known": sorted(self.catalogue)})
            lat, lon = cat.lat_deg, cat.lon_deg_east
        else:
            if site.get("lat") is None or site.get("lon") is None:
                raise InvalidInputError("Give a site_id, or both lat and lon", field="site")
            lat, lon = site["lat"], site["lon"]
        if not (_is_num(lat) and _is_num(lon)):
            raise InvalidInputError("lat and lon must be finite numbers", field="site")
        if not _is_num(duration_days) or not 0.0 < duration_days <= MAX_DURATION_DAYS:
            raise InvalidInputError(f"duration_days must be in (0, {MAX_DURATION_DAYS:g}]", field="duration_days")
        if not _is_num(step_seconds) or not 60.0 <= step_seconds <= 86400.0:
            raise InvalidInputError("step_seconds must be in [60, 86400]", field="step_seconds")
        if not _is_num(position_uncertainty_m) or not 0.0 < position_uncertainty_m <= 5000.0:
            raise InvalidInputError(
                "position_uncertainty_m must be in (0, 5000]: scenario results always carry the position "
                "sensitivity (a 0 band would silently drop it)", field="position_uncertainty_m")
        if observer_height_m is not None and not _is_num(observer_height_m):
            raise InvalidInputError("observer_height_m must be a finite number", field="observer_height_m")
        is_default = observer_height_m is None
        spec = ScenarioSpec(
            site_id=site_id, lat_deg=float(lat), lon_deg_east=float(lon), start_utc=parse_utc(start_utc, "start_utc"),
            duration_days=float(duration_days), step_seconds=float(step_seconds),
            observer_height_m=DEFAULT_OBSERVER_HEIGHT_M if is_default else float(observer_height_m),
            observer_height_is_default=is_default, position_uncertainty_m=float(position_uncertainty_m),
            n_directions=n_directions if isinstance(n_directions, int) and not isinstance(n_directions, bool) else -1,
            az_step_deg=float(az_step_deg) if _is_num(az_step_deg) else -1.0, label=label)
        if spec.n_samples > MAX_SAMPLES:
            raise InvalidInputError(f"scenario would need {spec.n_samples} samples; limit {MAX_SAMPLES}",
                                    field="step_seconds")
        return spec

    def dem_fingerprint(self) -> str:
        wins = sorted((k, v.sha256) for k, v in self.vis.hz.registry.windows.items())
        return hashlib.sha256(json.dumps(wins).encode()).hexdigest()

    def scenario_id(self, spec: ScenarioSpec) -> str:
        blob = json.dumps({"spec": spec.canonical(), "model_version": MODEL_VERSION,
                           "dem": self.dem_fingerprint()}, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()

    # ---------------------------------------------------------------- evaluate one scenario
    def evaluate(self, spec: ScenarioSpec, use_cache: bool = True) -> dict[str, Any]:
        sid = self.scenario_id(spec)
        if use_cache:
            hit = self.store.load(sid)
            if hit is not None:
                hit = {**hit, "spec": spec.public(), "served_from": "disk"}  # label may differ; id does not
                return hit
        base = {"id": sid, "model_version": MODEL_VERSION, "spec": spec.public(), "served_from": "computed"}
        try:
            res = self.vis.evaluate(
                spec.lat_deg, spec.lon_deg_east, spec.start_utc, spec.step_seconds, spec.n_samples,
                spec.observer_height_m, BODIES, position_uncertainty_m=spec.position_uncertainty_m,
                n_directions=spec.n_directions, refine=True, include_series=False,
                horizon_kwargs={"az_step_deg": spec.az_step_deg}).to_dict()
        except (OutOfDemCoverageError, DataMissingError) as e:
            out = {**base, "status": INSUFFICIENT, "reason": e.message, "reason_code": e.code.value,
                   "note": "No visibility numbers are given for a site without supporting terrain data."}
            self._save(sid, out)
            return out
        ps = res["position_sensitivity"]
        if ps["status"] != "computed":
            out = {**base, "status": INSUFFICIENT, "reason": ps["reason"], "reason_code": "TERRAIN_NOT_CERTIFIED",
                   "horizon_summary": res["horizon"]["summary"],
                   "note": "No visibility numbers are given for a site without supporting terrain data."}
            self._save(sid, out)
            return out
        out = {**base, "status": SUPPORTED, "observer": res["observer"], "window": res["window"],
               "horizon": res["horizon"], "definitions": res["definitions"],
               "position_sensitivity": {k: ps[k] for k in ("status", "data_class", "kind", "assumed_position_uncertainty_m",
                                                           "assumption", "n_directions", "method", "limitations")},
               "bodies": {b: self._summarise_body(res["bodies"][b]) for b in BODIES},
               "limitations": res["limitations"]}
        self._save(sid, out)
        return out

    def _save(self, sid: str, out: dict[str, Any]) -> None:
        self.store.save(sid, out)

    @staticmethod
    def _summarise_body(b: dict[str, Any]) -> dict[str, Any]:
        head = b["headline"]
        m, ps = head["metrics"], head["position_sensitivity"]
        mb = ps["metric_bands"]

        def longest(kind: str) -> dict[str, Any]:
            return {"closed_only": m[f"longest_{kind}_s_closed_only"],
                    "including_open": m[f"longest_{kind}_s_including_open"],
                    "includes_open_interval": m[f"longest_{kind}_includes_open_interval"],
                    "band_closed_only": mb[f"longest_{kind}_s_closed_only"],
                    "band_including_open": mb[f"longest_{kind}_s_including_open"]}

        bands = {round(x["nominal_time_s"], 3): x for x in ps["boundary_bands"]}
        state = b["headline_state"].replace("_visible", "")
        events = []
        for t in b["states"][state]["transitions"]:
            x = bands[round(t["time_s"], 3)]
            events.append({"type": "becomes_visible" if t["to"] == "visible" else "becomes_not_visible",
                           "time_utc": t["time_utc"], "time_s": t["time_s"],
                           "band": {"earliest_utc": x["earliest_utc"], "latest_utc": x["latest_utc"],
                                    "width_s": x["band_width_s"], "complete": x["band_complete"]}})
        g = b["geometric"]
        gm = g["metrics"]
        geo_events = [{"type": "becomes_visible" if t["to"] == "visible" else "becomes_not_visible",
                       "time_utc": t["time_utc"], "time_s": t["time_s"]} for t in g["transitions"]]
        terrain_total = m["total_visible_s"]
        return {
            "headline_state": b["headline_state"],
            "terrain_corrected": {
                "total_visible_s": {"nominal": terrain_total, "band": mb["total_visible_s"]},
                "visible_fraction": {"nominal": m["visible_fraction"], "band": mb["visible_fraction"]},
                "n_visible_intervals": {"nominal": m["n_visible_intervals"], "band": mb["n_visible_intervals"]},
                "longest_visible_s": longest("visible"),
                "longest_not_visible_s": longest("not_visible"),
                "events": events,
                "intervals": head["intervals"], "not_visible_intervals": head["not_visible_intervals"],
                "open_intervals": {
                    "visible": sum(1 for i in head["intervals"] if i["open_start"] or i["open_end"]),
                    "not_visible": sum(1 for i in head["not_visible_intervals"] if i["open_start"] or i["open_end"]),
                    "note": "intervals touching the window edge are cut off; their true length is at least the "
                            "value shown"},
                "events_only_in_displaced_runs": ps["events_only_in_displaced_runs"],
                "position_sensitivity": {
                    "directions_deg": ps["directions_deg"], "nominal_metrics": ps["nominal_metrics"],
                    "per_displacement_metrics": ps["per_displacement_metrics"]},
            },
            "geometric": {
                "definition": g["definition"],
                "total_visible_s": {"nominal": gm["total_visible_s"]},
                "visible_fraction": {"nominal": gm["visible_fraction"]},
                "n_visible_intervals": {"nominal": gm["n_visible_intervals"]},
                "longest_visible_s": {"closed_only": gm["longest_visible_s_closed_only"],
                                      "including_open": gm["longest_visible_s_including_open"],
                                      "includes_open_interval": gm["longest_visible_includes_open_interval"]},
                "longest_not_visible_s": {"closed_only": gm["longest_not_visible_s_closed_only"],
                                          "including_open": gm["longest_not_visible_s_including_open"],
                                          "includes_open_interval": gm["longest_not_visible_includes_open_interval"]},
                "events": geo_events, "intervals": g["intervals"], "not_visible_intervals": g["not_visible_intervals"],
                "position_sensitivity": g["position_sensitivity"],
            },
            "terrain_effect": {
                **b["terrain_effect"],
                "visible_s_terrain_minus_geometric": {
                    "nominal": terrain_total - gm["total_visible_s"],
                    "band": [mb["total_visible_s"][0] - gm["total_visible_s"],
                             mb["total_visible_s"][1] - gm["total_visible_s"]]},
                "note": "terrain-corrected minus geometric visible time; negative = terrain removes light the "
                        "geometry allows, positive = terrain horizon below the local horizontal adds visibility",
            },
            "completeness": b["completeness"],
        }

    # ---------------------------------------------------------------- deltas
    @staticmethod
    def _paired_ok(a: dict[str, Any], b: dict[str, Any]) -> bool:
        sa, sb = a["spec"], b["spec"]
        return all(sa[k] == sb[k] for k in ("lat_deg", "lon_deg_east", "observer_height_m",
                                            "position_uncertainty_m", "n_directions"))

    def _delta_terrain(self, a: dict[str, Any], b: dict[str, Any], body: str, key: str, flag_key: str | None,
                       paired: bool) -> dict[str, Any]:
        """Delta b - a for one terrain-corrected metric, with its position band."""
        ta, tb = a["bodies"][body]["terrain_corrected"], b["bodies"][body]["terrain_corrected"]
        if key in ("total_visible_s", "visible_fraction", "n_visible_intervals"):
            na, nb = ta[key]["nominal"], tb[key]["nominal"]
            band_a, band_b = ta[key]["band"], tb[key]["band"]
            mkey = key
            open_flag = False
        else:  # longest_*: use the value including open intervals, flagged
            kind = "visible" if "not" not in key else "not_visible"
            lt_a, lt_b = ta[key], tb[key]
            na, nb = lt_a["including_open"], lt_b["including_open"]
            band_a, band_b = lt_a["band_including_open"], lt_b["band_including_open"]
            mkey = f"longest_{kind}_s_including_open"
            open_flag = bool(lt_a["includes_open_interval"] or lt_b["includes_open_interval"])
        out: dict[str, Any] = {"baseline": na, "scenario": nb, "delta": None, "delta_band": None,
                               "distinguishable_from_zero": None, "involves_open_interval": open_flag}
        if na is None or nb is None:
            out["note"] = "metric undefined in one scenario (no such interval)"
            return out
        out["delta"] = nb - na
        if paired:
            pa, pb = ta["position_sensitivity"], tb["position_sensitivity"]
            diffs = [nb - na]
            for ma, mb_ in zip(pa["per_displacement_metrics"], pb["per_displacement_metrics"], strict=True):
                if ma[mkey] is not None and mb_[mkey] is not None:
                    diffs.append(mb_[mkey] - ma[mkey])
            out["delta_band"] = [min(diffs), max(diffs)]
            out["delta_band_method"] = ("paired: difference formed for the nominal position and each displaced "
                                        "position (one position error shared by both dates), then min/max")
        elif None not in band_a and None not in band_b:
            out["delta_band"] = [band_b[0] - band_a[1], band_b[1] - band_a[0]]
            out["delta_band_method"] = ("independent: interval arithmetic of the two metric bands (different "
                                        "sites have independent position errors); conservative")
        if out["delta_band"] is not None:
            lo, hi = out["delta_band"]
            out["distinguishable_from_zero"] = not (lo <= 0.0 <= hi)
        return out

    def _delta_scenario(self, a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
        paired = self._paired_ok(a, b)
        rows: dict[str, Any] = {}
        for body in BODIES:
            terrain = {
                "total_visible_s": self._delta_terrain(a, b, body, "total_visible_s", None, paired),
                "visible_fraction": self._delta_terrain(a, b, body, "visible_fraction", None, paired),
                "n_visible_intervals": self._delta_terrain(a, b, body, "n_visible_intervals", None, paired),
                "longest_visible_s": self._delta_terrain(a, b, body, "longest_visible_s", "x", paired),
                "longest_not_visible_s": self._delta_terrain(a, b, body, "longest_not_visible_s", "x", paired),
            }
            ga, gb = a["bodies"][body]["geometric"], b["bodies"][body]["geometric"]
            geometric = {}
            for key in ("total_visible_s", "visible_fraction", "n_visible_intervals"):
                geometric[key] = {"baseline": ga[key]["nominal"], "scenario": gb[key]["nominal"],
                                  "delta": gb[key]["nominal"] - ga[key]["nominal"], "delta_band": None,
                                  "position_sensitivity": "not_applicable (terrain-independent)"}
            for key in ("longest_visible_s", "longest_not_visible_s"):
                va, vb = ga[key]["including_open"], gb[key]["including_open"]
                geometric[key] = {"baseline": va, "scenario": vb, "delta": None if va is None or vb is None else vb - va,
                                  "delta_band": None, "involves_open_interval": bool(
                                      ga[key]["includes_open_interval"] or gb[key]["includes_open_interval"]),
                                  "position_sensitivity": "not_applicable (terrain-independent)"}
            ea, eb = a["bodies"][body]["terrain_effect"], b["bodies"][body]["terrain_effect"]
            rows[body] = {
                "terrain_corrected": terrain, "geometric": geometric,
                "terrain_effect_s": {
                    "baseline": ea["visible_s_terrain_minus_geometric"]["nominal"],
                    "scenario": eb["visible_s_terrain_minus_geometric"]["nominal"]},
                "summary": self._sentences(body, terrain, a, b),
            }
        return {"baseline_id": a["id"], "scenario_id": b["id"],
                "delta_band_method": "paired" if paired else "independent_interval_arithmetic", "bodies": rows}

    @staticmethod
    def _sentences(body: str, terrain: dict[str, Any], a: dict[str, Any], b: dict[str, Any]) -> list[str]:
        band = a["spec"]["position_uncertainty_m"]
        out = []
        for key, unit, scale, label in (("visible_fraction", "percentage points", 100.0, "visible fraction"),
                                        ("longest_not_visible_s", "hours", 1 / 3600.0, "longest not-visible interval")):
            d = terrain[key]
            if d["delta"] is None:
                out.append(f"{body} {label}: not comparable ({d.get('note', 'undefined')}).")
                continue
            lo, hi = (d["delta_band"] if d["delta_band"] else (None, None))
            txt = f"{body} {label}: {d['delta'] * scale:+.3g} {unit}"
            if lo is not None:
                if lo == 0.0 and hi == 0.0:
                    verdict = "no difference at the nominal or any sampled displaced position"
                elif d["distinguishable_from_zero"]:
                    verdict = "distinguishable from zero"
                else:
                    verdict = f"NOT distinguishable from zero given +/-{band:g} m position uncertainty"
                txt += f" (band {lo * scale:+.3g} to {hi * scale:+.3g}; {verdict})"
            if d["involves_open_interval"]:
                txt += "; involves an interval cut off by the window edge, so the value is a lower bound"
            out.append(txt + ".")
        return out

    # ---------------------------------------------------------------- rankings
    @staticmethod
    def _rankings(supported: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if len(supported) < 2:
            return []
        specs = [("sun_visible_fraction", "sun", "visible_fraction", True),
                 ("earth_visible_fraction", "earth", "visible_fraction", True),
                 ("sun_longest_darkness", "sun", "longest_not_visible_s", False),
                 ("earth_longest_blackout", "earth", "longest_not_visible_s", False)]
        out = []
        for name, body, key, higher_better in specs:
            rows = []
            for s in supported:
                t = s["bodies"][body]["terrain_corrected"][key]
                if key == "visible_fraction":
                    nom, band, open_flag = t["nominal"], t["band"], False
                else:
                    nom, band, open_flag = t["including_open"], t["band_including_open"], t["includes_open_interval"]
                rows.append({"scenario_id": s["id"], "label": s["spec"]["label"], "site_id": s["spec"]["site_id"],
                             "start_utc": s["spec"]["start_utc"], "nominal": nom, "band": band,
                             "includes_open_interval": open_flag})
            rows.sort(key=lambda r: (r["nominal"] is None, -(r["nominal"] or 0) if higher_better else (r["nominal"] or 0)))
            for i, r in enumerate(rows):
                r["rank"] = i + 1
                nxt = rows[i + 1] if i + 1 < len(rows) else None
                if nxt is None or r["band"] is None or nxt["band"] is None or None in r["band"] or None in nxt["band"]:
                    r["distinguishable_from_next"] = None
                else:
                    r["distinguishable_from_next"] = r["band"][0] > nxt["band"][1] or nxt["band"][0] > r["band"][1]
            out.append({"criterion": name, "better": "higher" if higher_better else "lower",
                        "method": "ordered by nominal value; `distinguishable_from_next` is true only if the "
                                  "position-uncertainty bands of adjacent ranks do not overlap",
                        "ranking": rows})
        return out

    # ---------------------------------------------------------------- comparison
    def compare(self, specs: list[ScenarioSpec], baseline_index: int = 0, use_cache: bool = True) -> dict[str, Any]:
        if not specs:
            raise InvalidInputError("give at least one scenario", field="scenarios")
        if len(specs) > MAX_SCENARIOS:
            raise InvalidInputError(f"at most {MAX_SCENARIOS} scenarios per comparison", field="scenarios")
        if not 0 <= baseline_index < len(specs):
            raise InvalidInputError("baseline_index out of range", field="baseline_index")
        results = [self.evaluate(s, use_cache) for s in specs]
        supported = [r for r in results if r["status"] == SUPPORTED]
        excluded = [{"scenario_id": r["id"], "label": r["spec"]["label"], "site_id": r["spec"]["site_id"],
                     "lat_deg": r["spec"]["lat_deg"], "lon_deg_east": r["spec"]["lon_deg_east"],
                     "start_utc": r["spec"]["start_utc"], "status": INSUFFICIENT, "reason": r["reason"]}
                    for r in results if r["status"] == INSUFFICIENT]
        base = results[baseline_index]
        deltas = []
        notes = []
        if base["status"] == SUPPORTED:
            deltas = [self._delta_scenario(base, r) for i, r in enumerate(results)
                      if i != baseline_index and r["status"] == SUPPORTED]
        else:
            notes.append("The baseline scenario is terrain_data_insufficient, so no deltas are formed.")
        if excluded:
            notes.append(f"{len(excluded)} scenario(s) excluded from deltas and rankings: terrain data insufficient.")
        if len(supported) < 2:
            notes.append("Fewer than two supported scenarios: nothing to rank.")
        return {
            "model_version": MODEL_VERSION, "baseline_id": base["id"], "scenarios": results,
            "excluded_terrain_data_insufficient": excluded, "deltas_vs_baseline": deltas,
            "rankings": self._rankings(supported), "notes": notes,
            "reading_guide": [
                "Totals and fractions are the robust headline (stable to a few percent under the position band).",
                "Event timestamps carry their position band; do not read the nominal time alone.",
                "Both geometric and terrain-corrected results are given for every scenario and delta.",
                "Intervals touching the window edge are flagged open; extrema/deltas involving them are lower bounds.",
                "Sites without terrain support are excluded, never ranked or estimated.",
            ],
        }

    # ---------------------------------------------------------------- delay simulator
    def delay(self, site: dict[str, Any], baseline_start_utc: Any, offsets_days: Any, *, use_cache: bool = True,
              **kw: Any) -> dict[str, Any]:
        if not isinstance(offsets_days, list) or not 1 <= len(offsets_days) <= MAX_OFFSETS \
                or not all(_is_num(o) and 0.0 < o <= MAX_DELAY_DAYS for o in offsets_days) \
                or len(set(offsets_days)) != len(offsets_days):
            raise InvalidInputError(
                f"offsets_days must be 1..{MAX_OFFSETS} distinct numbers in (0, {MAX_DELAY_DAYS:g}] days",
                field="offsets_days")
        kw.setdefault("duration_days", 14.0)  # assumption: about one lunar day of operations
        base_spec = self.make_spec(site, baseline_start_utc, label="baseline", **kw)
        offsets = sorted(float(o) for o in offsets_days)
        specs = [base_spec] + [
            self.make_spec(site, format_utc(base_spec.start_utc + timedelta(days=o)), label=f"delay +{o:g} d", **kw)
            for o in offsets]
        results = [self.evaluate(s, use_cache) for s in specs]
        base = results[0]
        if base["status"] != SUPPORTED:
            return {"model_version": MODEL_VERSION, "status": INSUFFICIENT, "reason": base["reason"],
                    "scenarios": results[:1], "delays": [], "rankings": [],
                    "note": "No delay comparison is produced for a site without supporting terrain data: no "
                            "numbers, no ranking, no estimate."}
        delays = [{"offset_days": o, "scenario": r, "delta_vs_baseline": self._delta_scenario(base, r)}
                  for o, r in zip(offsets, results[1:], strict=True)]
        table = []
        for o, r in zip([0.0, *offsets], results, strict=True):
            row: dict[str, Any] = {"offset_days": o, "scenario_id": r["id"], "start_utc": r["spec"]["start_utc"]}
            for body in BODIES:
                t, g = r["bodies"][body]["terrain_corrected"], r["bodies"][body]["geometric"]
                row[body] = {
                    "terrain_corrected_visible_fraction": t["visible_fraction"],
                    "geometric_visible_fraction": g["visible_fraction"]["nominal"],
                    "terrain_corrected_longest_not_visible_s": {
                        "nominal": t["longest_not_visible_s"]["including_open"],
                        "band": t["longest_not_visible_s"]["band_including_open"],
                        "includes_open_interval": t["longest_not_visible_s"]["includes_open_interval"]},
                    "geometric_longest_not_visible_s": {
                        "nominal": g["longest_not_visible_s"]["including_open"],
                        "includes_open_interval": g["longest_not_visible_s"]["includes_open_interval"]}}
            table.append(row)
        return {
            "model_version": MODEL_VERSION, "status": SUPPORTED, "site": base["spec"]["site_id"],
            "baseline": base, "delays": delays, "summary_table": table,
            "rankings": self._rankings(results),
            "notes": [("Each delay shifts the whole window by the stated number of days; the position-sensitivity "
                      "band of every delta is formed per displacement (one position error shared by both dates)."),
                      "Windows are identical in length; intervals cut off by a window edge are flagged open."],
        }
