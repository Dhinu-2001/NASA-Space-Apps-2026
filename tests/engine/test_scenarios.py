"""Stage 6 scenario / comparison / delay tests.

Kinds, labelled explicitly:
  * PURE tests - hand-built scenario dictionaries with analytic answers (delta bands, ranking, store, ids).
  * REAL-DATA tests - real SPICE ephemeris + LOLA windows (IM-2 supported; IM-1 / Chandrayaan-3 insufficient).
    Skipped with the rebuild command when kernels or DEM windows are absent.
"""

import json
from pathlib import Path

import pytest
from lunarnav import MODEL_VERSION
from lunarnav.ephemeris import EphemerisService
from lunarnav.errors import InvalidInputError
from lunarnav.horizon import HorizonService
from lunarnav.scenarios import (
    INSUFFICIENT,
    SUPPORTED,
    ScenarioService,
    ScenarioStore,
)
from lunarnav.visibility import BAND_METRIC_KEYS, VisibilityService

DATA = Path(__file__).resolve().parents[2] / "data"
HAVE_KERNELS = all((DATA / "kernels" / f).exists() for f in
                   ("naif0012.tls", "de440s.bsp", "moon_pa_de440_200625.bpc", "moon_de440_250416.tf"))
HAVE_DEM = all((DATA / "dem_cache" / f).exists() for f in
               ("im2_20m_r10km.tif", "im2_320m_r160km.tif", "im2_20m_r80km.tif", "im1_20m_r2km.tif"))
needs_data = pytest.mark.skipif(not (HAVE_KERNELS and HAVE_DEM), reason="kernels/DEM windows missing; see DEV_SETUP")
JAN = "2027-01-15T00:00:00Z"
MAR = "2027-03-15T00:00:00Z"


# ---------------------------------------------------------------- fake scenarios for pure tests

def _metrics(total, frac, n, lv_c, lv_o, lnv_c, lnv_o):
    return dict(zip(BAND_METRIC_KEYS, (total, frac, n, lv_c, lv_o, lnv_c, lnv_o), strict=True))


def fake(sid, *, site=(-85.0, 30.0), nominal, displaced, lnv_open=False, geo_total=500.0, label=None):
    """nominal / displaced: (total, longest_not_visible_including_open). Fractions use a 1000 s window."""
    def m(t, lnv):
        return _metrics(t, t / 1000.0, 2, 100.0, 100.0, lnv, lnv)
    nom = m(*nominal)
    per = [m(*d) for d in displaced]
    allm = [nom, *per]

    def band(key):
        vals = [x[key] for x in allm]
        return [min(vals), max(vals)]

    tc = {
        "total_visible_s": {"nominal": nom["total_visible_s"], "band": band("total_visible_s")},
        "visible_fraction": {"nominal": nom["visible_fraction"], "band": band("visible_fraction")},
        "n_visible_intervals": {"nominal": 2, "band": [2, 2]},
        "longest_visible_s": {"closed_only": 100.0, "including_open": 100.0, "includes_open_interval": False,
                              "band_closed_only": [100.0, 100.0], "band_including_open": [100.0, 100.0]},
        "longest_not_visible_s": {"closed_only": None if lnv_open else nom["longest_not_visible_s_including_open"],
                                  "including_open": nom["longest_not_visible_s_including_open"],
                                  "includes_open_interval": lnv_open,
                                  "band_closed_only": [None, None],
                                  "band_including_open": band("longest_not_visible_s_including_open")},
        "position_sensitivity": {"nominal_metrics": nom, "per_displacement_metrics": per},
    }
    gm = {"nominal": geo_total}
    geo = {"total_visible_s": gm, "visible_fraction": {"nominal": geo_total / 1000.0},
           "n_visible_intervals": {"nominal": 2},
           "longest_visible_s": {"including_open": 100.0, "includes_open_interval": False},
           "longest_not_visible_s": {"including_open": 200.0, "includes_open_interval": False}}
    body = {"terrain_corrected": tc, "geometric": geo,
            "terrain_effect": {"visible_s_terrain_minus_geometric": {"nominal": nom["total_visible_s"] - geo_total}}}
    return {"id": sid, "status": SUPPORTED,
            "spec": {"lat_deg": site[0], "lon_deg_east": site[1], "observer_height_m": 2.0,
                     "position_uncertainty_m": 100.0, "n_directions": len(per), "site_id": label or sid,
                     "label": label or sid, "start_utc": "2027-01-15T00:00:00Z"},
            "bodies": {"sun": body, "earth": body}}


@pytest.fixture(scope="module")
def svc_pure(tmp_path_factory):
    d = tmp_path_factory.mktemp("d")
    (d / "catalogue").mkdir()
    (d / "catalogue" / "sites.json").write_bytes((DATA / "catalogue" / "sites.json").read_bytes())
    return ScenarioService(d, VisibilityService(EphemerisService(DATA), HorizonService(d)))


# ---------------------------------------------------------------- spec validation and identity

def test_spec_validation_names_the_field(svc_pure):
    mk = svc_pure.make_spec
    cases = [
        ({"site": {"site_id": "nope"}, "start_utc": JAN}, "site_id"),
        ({"site": {}, "start_utc": JAN}, "site"),
        ({"site": {"site_id": "im2-athena", "lat": -85, "lon": 0}, "start_utc": JAN}, "site"),
        ({"site": {"lat": "x", "lon": 1}, "start_utc": JAN}, "site"),
        ({"site": {"site_id": "im2-athena"}, "start_utc": "2027-01-15"}, "start_utc"),
        ({"site": {"site_id": "im2-athena"}, "start_utc": JAN, "duration_days": 0}, "duration_days"),
        ({"site": {"site_id": "im2-athena"}, "start_utc": JAN, "duration_days": 400}, "duration_days"),
        ({"site": {"site_id": "im2-athena"}, "start_utc": JAN, "step_seconds": 5}, "step_seconds"),
        ({"site": {"site_id": "im2-athena"}, "start_utc": JAN, "step_seconds": 60, "duration_days": 60}, "step_seconds"),
        ({"site": {"site_id": "im2-athena"}, "start_utc": JAN, "position_uncertainty_m": 0}, "position_uncertainty_m"),
        ({"site": {"site_id": "im2-athena"}, "start_utc": JAN, "position_uncertainty_m": -1}, "position_uncertainty_m"),
        ({"site": {"site_id": "im2-athena"}, "start_utc": JAN, "observer_height_m": "2"}, "observer_height_m"),
    ]
    for kw, field in cases:
        with pytest.raises(InvalidInputError) as e:
            mk(**kw)
        assert e.value.field == field, (kw, e.value.field)


def test_scenario_identity_is_deterministic_and_input_sensitive(svc_pure):
    mk = svc_pure.make_spec
    a = mk({"site_id": "im2-athena"}, JAN)
    assert svc_pure.scenario_id(a) == svc_pure.scenario_id(mk({"site_id": "im2-athena"}, JAN))
    assert len(svc_pure.scenario_id(a)) == 64
    assert svc_pure.scenario_id(a) == svc_pure.scenario_id(mk({"site_id": "im2-athena"}, JAN, label="other label"))
    for kw in ({"duration_days": 10}, {"observer_height_m": 3.0}, {"position_uncertainty_m": 50.0},
               {"step_seconds": 600}, {"n_directions": 12}, {"az_step_deg": 1.0}):
        assert svc_pure.scenario_id(mk({"site_id": "im2-athena"}, JAN, **kw)) != svc_pure.scenario_id(a), kw
    assert svc_pure.scenario_id(mk({"site_id": "im2-athena"}, MAR)) != svc_pure.scenario_id(a)
    assert svc_pure.scenario_id(mk({"site_id": "im2-intended"}, JAN)) != svc_pure.scenario_id(a)
    # default observer height is an assumption and is reported as such
    assert a.observer_height_is_default and a.public()["observer_height_is_default_assumption"]
    assert not mk({"site_id": "im2-athena"}, JAN, observer_height_m=2.0).observer_height_is_default


def test_store_roundtrip_and_refusals(tmp_path):
    st = ScenarioStore(tmp_path)
    sid = "a" * 64
    doc = {"id": sid, "model_version": MODEL_VERSION, "x": 1}
    st.save(sid, doc)
    assert st.load(sid) == doc
    assert st.load("b" * 64) is None and st.load("../../etc/passwd") is None and st.load("short") is None
    st.save(sid, {**doc, "model_version": "0.0.0-old"})
    assert st.load(sid) is None                      # a result from another model version is never served
    (st.dir / f"{sid}.json").write_text("{broken")
    assert st.load(sid) is None                      # unreadable entry is ignored


# ---------------------------------------------------------------- deltas (analytic)

def test_same_site_delta_is_paired_per_displacement(svc_pure):
    # Baseline and delayed totals both swing +-100 s with the displacement, in the SAME direction: the
    # position error cancels in the difference (paired band is tight), unlike interval arithmetic.
    a = fake("A", nominal=(500, 300), displaced=[(400, 300), (600, 300), (500, 300)])
    b = fake("B", nominal=(520, 300), displaced=[(420, 300), (620, 300), (520, 300)])
    d = svc_pure._delta_scenario(a, b)
    assert d["delta_band_method"] == "paired"
    t = d["bodies"]["sun"]["terrain_corrected"]["total_visible_s"]
    assert t["delta"] == 20 and t["delta_band"] == [20, 20] and t["distinguishable_from_zero"] is True
    # the independent method (different sites) is conservative: a +-100 s swing each way
    b2 = fake("B2", site=(-84.0, 30.0), nominal=(520, 300), displaced=[(420, 300), (620, 300), (520, 300)])
    d2 = svc_pure._delta_scenario(a, b2)
    assert d2["delta_band_method"] == "independent_interval_arithmetic"
    t2 = d2["bodies"]["sun"]["terrain_corrected"]["total_visible_s"]
    assert t2["delta_band"] == [420 - 600, 620 - 400] and t2["distinguishable_from_zero"] is False
    assert "independent" in t2["delta_band_method"]


def test_paired_band_can_flip_sign_and_is_reported_indistinguishable(svc_pure):
    a = fake("A", nominal=(500, 300), displaced=[(500, 300), (500, 300)])
    b = fake("B", nominal=(510, 300), displaced=[(490, 300), (530, 300)])
    t = svc_pure._delta_scenario(a, b)["bodies"]["earth"]["terrain_corrected"]["total_visible_s"]
    assert t["delta"] == 10 and t["delta_band"] == [-10, 30] and t["distinguishable_from_zero"] is False


def test_delta_carries_both_geometric_and_terrain_corrected_and_the_gap(svc_pure):
    a = fake("A", nominal=(500, 300), displaced=[(450, 300)], geo_total=600)
    b = fake("B", nominal=(520, 300), displaced=[(470, 300)], geo_total=560)
    row = svc_pure._delta_scenario(a, b)["bodies"]["sun"]
    assert set(row) >= {"terrain_corrected", "geometric", "terrain_effect_s", "summary"}
    g = row["geometric"]["total_visible_s"]
    assert g["delta"] == -40 and g["delta_band"] is None and "not_applicable" in g["position_sensitivity"]
    assert row["terrain_effect_s"] == {"baseline": -100, "scenario": -40}


def test_open_interval_involvement_is_flagged_in_the_delta(svc_pure):
    a = fake("A", nominal=(500, 800), displaced=[(500, 800)], lnv_open=True)
    b = fake("B", nominal=(500, 300), displaced=[(500, 300)], lnv_open=False)
    d = svc_pure._delta_scenario(a, b)["bodies"]["sun"]
    lnv = d["terrain_corrected"]["longest_not_visible_s"]
    assert lnv["involves_open_interval"] is True and lnv["delta"] == -500
    assert d["terrain_corrected"]["total_visible_s"]["involves_open_interval"] is False
    assert any("cut off by the window edge" in s for s in d["summary"])
    both_closed = svc_pure._delta_scenario(b, b)["bodies"]["sun"]["terrain_corrected"]["longest_not_visible_s"]
    assert both_closed["involves_open_interval"] is False


def test_zero_difference_is_described_as_no_difference(svc_pure):
    a = fake("A", nominal=(500, 300), displaced=[(450, 300)])
    sentences = svc_pure._delta_scenario(a, a)["bodies"]["sun"]["summary"]
    assert any("no difference" in s for s in sentences)


def test_undefined_metric_is_not_silently_zero(svc_pure):
    a = fake("A", nominal=(500, 300), displaced=[(500, 300)])
    b = fake("B", nominal=(500, 300), displaced=[(500, 300)])
    for body in b["bodies"].values():
        tc = body["terrain_corrected"]
        tc["longest_not_visible_s"]["including_open"] = None
        tc["longest_not_visible_s"]["band_including_open"] = [None, None]
        tc["position_sensitivity"]["per_displacement_metrics"][0]["longest_not_visible_s_including_open"] = None
    d = svc_pure._delta_scenario(a, b)["bodies"]["sun"]["terrain_corrected"]["longest_not_visible_s"]
    assert d["delta"] is None and d["delta_band"] is None and "undefined" in d["note"]


# ---------------------------------------------------------------- ranking (analytic)

def test_rankings_use_bands_and_only_supported_scenarios(svc_pure):
    a = fake("A", nominal=(600, 300), displaced=[(590, 300), (610, 300)])
    b = fake("B", nominal=(500, 300), displaced=[(490, 300), (520, 300)])
    c = fake("C", nominal=(495, 300), displaced=[(480, 300), (505, 300)])
    rk = {r["criterion"]: r["ranking"] for r in svc_pure._rankings([b, a, c])}
    sun = rk["sun_visible_fraction"]
    assert [r["scenario_id"] for r in sun] == ["A", "B", "C"] and [r["rank"] for r in sun] == [1, 2, 3]
    assert sun[0]["distinguishable_from_next"] is True      # 590..610 vs 490..520: disjoint
    assert sun[1]["distinguishable_from_next"] is False     # 490..520 vs 480..505: overlap
    assert sun[2]["distinguishable_from_next"] is None      # last
    assert svc_pure._rankings([a]) == [] and svc_pure._rankings([]) == []
    low = {r["criterion"]: r["ranking"] for r in svc_pure._rankings([a, b])}["sun_longest_darkness"]
    assert all(r["includes_open_interval"] is False for r in low)


# ---------------------------------------------------------------- real data

@pytest.fixture(scope="module")
def svc():
    return ScenarioService(DATA, VisibilityService(EphemerisService(DATA), HorizonService(DATA)))


KW = {"az_step_deg": 1.0, "step_seconds": 1800.0, "duration_days": 10.0}


@needs_data
def test_supported_scenario_has_both_results_bands_and_open_flags(svc):
    s = svc.evaluate(svc.make_spec({"site_id": "im2-athena"}, "2027-01-29T00:00:00Z", **KW), use_cache=False)
    assert s["status"] == SUPPORTED and s["spec"]["observer_height_is_default_assumption"] is True
    assert s["position_sensitivity"]["status"] == "computed" and "+/-100 m" in s["position_sensitivity"]["assumption"]
    for body in ("sun", "earth"):
        b = s["bodies"][body]
        assert {"terrain_corrected", "geometric", "terrain_effect", "completeness"} <= set(b)
        tc, geo = b["terrain_corrected"], b["geometric"]
        assert tc["visible_fraction"]["band"][0] <= tc["visible_fraction"]["nominal"] <= tc["visible_fraction"]["band"][1]
        assert "band" not in geo["visible_fraction"]                      # geometric has no terrain band
        assert geo["position_sensitivity"]["status"] == "not_applicable"
        for e in tc["events"]:
            assert e["band"]["earliest_utc"] <= e["time_utc"] <= e["band"]["latest_utc"]
        assert b["completeness"]["visibility_is_upper_bound"] is False
    # Sun is dark for the whole 10 days after 2027-01-29: one open not-visible interval, flagged, not "closed"
    sun = s["bodies"]["sun"]["terrain_corrected"]
    assert sun["longest_not_visible_s"]["includes_open_interval"] is True
    assert sun["longest_not_visible_s"]["closed_only"] is None
    assert sun["open_intervals"]["not_visible"] >= 1
    json.dumps(s)  # fully serialisable


@needs_data
def test_cache_roundtrip_and_stable_id(svc):
    spec = svc.make_spec({"site_id": "im2-athena"}, "2027-01-29T00:00:00Z", **KW)
    first = svc.evaluate(spec)
    second = svc.evaluate(spec)
    assert first["id"] == second["id"] == svc.scenario_id(spec) and second["served_from"] == "disk"
    assert first["bodies"] == second["bodies"]
    relabelled = svc.evaluate(svc.make_spec({"site_id": "im2-athena"}, "2027-01-29T00:00:00Z", label="mine", **KW))
    assert relabelled["id"] == first["id"] and relabelled["spec"]["label"] == "mine"


@needs_data
@pytest.mark.parametrize(("site", "code"), [({"site_id": "im1-odysseus"}, "TERRAIN_NOT_CERTIFIED"),
                                            ({"site_id": "chandrayaan3-shiv-shakti"}, "OUT_OF_DEM_COVERAGE"),
                                            ({"lat": -69.3741, "lon": 32.32}, None)])
def test_insufficient_sites_get_a_label_and_reason_but_no_numbers(svc, site, code):
    r = svc.evaluate(svc.make_spec(site, JAN, **KW), use_cache=False)
    assert r["status"] == INSUFFICIENT and r["reason"]
    if code:
        assert r["reason_code"] == code
    for forbidden in ("bodies", "observer", "window", "horizon_summary_numbers"):
        assert forbidden not in r
    text = json.dumps(r)
    assert "visible_fraction" not in text and "total_visible_s" not in text and "geometric" not in text


@needs_data
def test_compare_excludes_insufficient_sites_and_never_ranks_them(svc):
    specs = [svc.make_spec({"site_id": s}, d, label=f"{s}@{d[:10]}", **KW)
             for s in ("im2-athena", "im2-intended", "im1-odysseus", "chandrayaan3-shiv-shakti")
             for d in ("2027-01-26T00:00:00Z", "2027-02-05T00:00:00Z")]
    r = svc.compare(specs, 0, use_cache=False)
    ids_excluded = {e["scenario_id"] for e in r["excluded_terrain_data_insufficient"]}
    assert len(ids_excluded) == 4 and all(e["status"] == INSUFFICIENT for e in r["excluded_terrain_data_insufficient"])
    assert {e["site_id"] for e in r["excluded_terrain_data_insufficient"]} == {"im1-odysseus", "chandrayaan3-shiv-shakti"}
    ranked = {row["scenario_id"] for rk in r["rankings"] for row in rk["ranking"]}
    assert ranked and not (ranked & ids_excluded)
    assert not ({d["scenario_id"] for d in r["deltas_vs_baseline"]} & ids_excluded)
    assert len(r["deltas_vs_baseline"]) == 3 and any("excluded" in n for n in r["notes"])
    text = json.dumps(r["excluded_terrain_data_insufficient"]).lower()
    assert "fraction" not in text and "total_visible" not in text and "estimated" not in text
    body = json.dumps([r["rankings"], r["deltas_vs_baseline"]]).lower()
    assert "estimated" not in body and "chandrayaan" not in body and "im1-odysseus" not in body
    # method per pair: same site (other date) is paired; the other IM-2 position is independent
    by = {d["scenario_id"]: d["delta_band_method"] for d in r["deltas_vs_baseline"]}
    assert sorted(by.values()) == ["independent_interval_arithmetic", "independent_interval_arithmetic", "paired"]
    # every delta carries geometric and terrain-corrected, and a band on the terrain side
    for d in r["deltas_vs_baseline"]:
        for body in ("sun", "earth"):
            assert d["bodies"][body]["geometric"]["total_visible_s"]["delta_band"] is None
            assert d["bodies"][body]["terrain_corrected"]["total_visible_s"]["delta_band"] is not None


@needs_data
def test_changing_date_or_location_changes_the_outputs_and_deltas_are_consistent(svc):
    a = svc.evaluate(svc.make_spec({"site_id": "im2-athena"}, "2027-01-26T00:00:00Z", **KW))
    later = svc.evaluate(svc.make_spec({"site_id": "im2-athena"}, "2027-02-05T00:00:00Z", **KW))
    other = svc.evaluate(svc.make_spec({"site_id": "im2-intended"}, "2027-01-26T00:00:00Z", **KW))
    assert len({a["id"], later["id"], other["id"]}) == 3
    ev = lambda s: [e["time_utc"] for e in s["bodies"]["sun"]["terrain_corrected"]["events"]]
    assert ev(a) != ev(later)                                   # date changes the events
    tot = lambda s: s["bodies"]["sun"]["terrain_corrected"]["total_visible_s"]["nominal"]
    assert tot(a) != tot(later)
    assert a["bodies"]["sun"]["terrain_corrected"]["events"] != other["bodies"]["sun"]["terrain_corrected"]["events"]  # location
    # delta consistency: delta(a->b) = -delta(b->a); a->a is exactly zero
    ab = svc._delta_scenario(a, later)["bodies"]["sun"]["terrain_corrected"]["total_visible_s"]["delta"]
    ba = svc._delta_scenario(later, a)["bodies"]["sun"]["terrain_corrected"]["total_visible_s"]["delta"]
    aa = svc._delta_scenario(a, a)["bodies"]["sun"]["terrain_corrected"]["total_visible_s"]
    assert ab == pytest.approx(-ba) and ab == pytest.approx(tot(later) - tot(a))
    assert aa["delta"] == 0 and aa["delta_band"] == [0, 0]
    # the nominal delta always lies inside its own band
    for body in ("sun", "earth"):
        for k, v in svc._delta_scenario(a, later)["bodies"][body]["terrain_corrected"].items():
            if v["delta"] is not None and v["delta_band"] is not None:
                assert v["delta_band"][0] - 1e-9 <= v["delta"] <= v["delta_band"][1] + 1e-9, k


@needs_data
def test_baseline_that_is_insufficient_yields_no_deltas(svc):
    specs = [svc.make_spec({"site_id": "im1-odysseus"}, JAN, **KW), svc.make_spec({"site_id": "im2-athena"}, JAN, **KW)]
    r = svc.compare(specs, 0)
    assert r["deltas_vs_baseline"] == [] and any("baseline" in n for n in r["notes"])
    assert r["rankings"] == [] and any("Fewer than two" in n for n in r["notes"])
    with pytest.raises(InvalidInputError):
        svc.compare(specs, 5)
    with pytest.raises(InvalidInputError):
        svc.compare([], 0)


@needs_data
def test_delay_simulator_carries_bands_and_both_results_into_every_delta(svc):
    d = svc.delay({"site_id": "im2-athena"}, "2027-01-26T00:00:00Z", [3, 9], **{k: v for k, v in KW.items()})
    assert d["status"] == SUPPORTED and [x["offset_days"] for x in d["delays"]] == [3.0, 9.0]
    assert [r["offset_days"] for r in d["summary_table"]] == [0.0, 3.0, 9.0]
    for x in d["delays"]:
        dv = x["delta_vs_baseline"]
        assert dv["delta_band_method"] == "paired"           # same site: one shared position error
        for body in ("sun", "earth"):
            tc, geo = dv["bodies"][body]["terrain_corrected"], dv["bodies"][body]["geometric"]
            assert tc["visible_fraction"]["delta_band"] is not None and geo["visible_fraction"]["delta"] is not None
    for row in d["summary_table"]:
        for body in ("sun", "earth"):
            assert {"terrain_corrected_visible_fraction", "geometric_visible_fraction",
                    "terrain_corrected_longest_not_visible_s", "geometric_longest_not_visible_s"} <= set(row[body])
            assert "band" in row[body]["terrain_corrected_visible_fraction"]
    assert d["delays"][0]["scenario"]["spec"]["start_utc"] == "2027-01-29T00:00:00Z"
    assert d["rankings"] and "per displacement" in " ".join(d["notes"])


@needs_data
def test_delay_default_duration_is_the_labelled_14_day_assumption_and_inputs_are_validated(svc):
    d = svc.delay({"site_id": "im2-athena"}, "2027-01-26T00:00:00Z", [2], az_step_deg=1.0, step_seconds=3600.0)
    assert d["baseline"]["spec"]["duration_days"] == 14.0
    for bad in ([], [0], [-1], [400], [1, 1], ["x"], list(range(1, 12)), "3", None):
        with pytest.raises(InvalidInputError) as e:
            svc.delay({"site_id": "im2-athena"}, JAN, bad)
        assert e.value.field == "offsets_days"


@needs_data
def test_delay_for_a_data_insufficient_site_returns_no_numbers(svc):
    d = svc.delay({"site_id": "im1-odysseus"}, JAN, [2, 5], **KW)
    assert d["status"] == INSUFFICIENT and d["delays"] == [] and d["rankings"] == []
    assert "visible_fraction" not in json.dumps(d) and "no numbers" in d["note"]
