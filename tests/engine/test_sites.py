import json
import math
import re
from pathlib import Path

import pytest
from lunarnav.errors import InvalidInputError
from lunarnav.sites import (
    SiteKind,
    custom_site,
    load_catalogue,
    normalise_longitude,
    validate_coordinates,
)

CATALOGUE = Path(__file__).resolve().parents[2] / "data" / "catalogue" / "sites.json"


# ---------------------------------------------------------------- coordinate conventions

@pytest.mark.parametrize(
    ("lon_in", "lon_out"),
    [(0, 0), (90, 90), (179.9, 179.9), (180, -180), (-180, -180), (270, -90), (360, 0),
     (-90, -90), (359.5, -0.5)],
)
def test_longitude_normalised_east_positive(lon_in, lon_out):
    assert validate_coordinates(-85.0, lon_in)[1] == pytest.approx(lon_out)


def test_normalise_longitude_range():
    for lon in (-180, -179.999, 0, 179.999, 180, 359.999, 360):
        assert -180.0 <= normalise_longitude(lon) < 180.0


@pytest.mark.parametrize("lat", [-90, -89.999999, 0, 89.999, 90])
def test_latitude_bounds_accepted(lat):
    assert validate_coordinates(lat, 10)[0] == lat


@pytest.mark.parametrize(
    ("lat", "lon", "field"),
    [(90.0001, 0, "lat"), (-90.0001, 0, "lat"), (0, 360.0001, "lon"), (0, -180.0001, "lon"),
     (0, 1000, "lon"), ("abc", 0, "lat"), (0, "10", "lon"), (None, 0, "lat"), (True, 0, "lat"),
     (0, False, "lon"), (math.nan, 0, "lat"), (0, math.inf, "lon"), (-math.inf, 0, "lat"),
     ([1], 0, "lat")],
)
def test_invalid_coordinates_report_the_offending_field(lat, lon, field):
    with pytest.raises(InvalidInputError) as e:
        validate_coordinates(lat, lon)
    assert e.value.field == field


def test_exact_pole_and_near_pole_are_valid_sites():
    for lat in (-90.0, -89.9999, -89.5):
        assert custom_site(lat, 0.0).kind is SiteKind.CUSTOM


def test_custom_site_has_no_source_and_stable_id():
    s = custom_site(-85, 270)
    assert s.kind is SiteKind.CUSTOM and not s.sources
    assert s.lon_deg_east == pytest.approx(-90)
    assert s.id == custom_site(-85, -90).id  # 270 and -90 are the same meridian


# ---------------------------------------------------------------- catalogue policy

def test_catalogue_loads_and_every_site_has_primary_source_urls():
    sites = load_catalogue(CATALOGUE)
    assert len(sites) >= 3
    for s in sites:
        assert s.kind is not SiteKind.CUSTOM
        assert s.sources, s.id
        assert all(src.url.startswith("https://") and src.quote for src in s.sources), s.id
        assert s.lon_convention == "east_positive" and s.lat_convention == "planetocentric"


def test_confirmed_vs_intended_are_distinguished():
    by_id = {s.id: s for s in load_catalogue(CATALOGUE)}
    assert by_id["im2-athena"].kind is SiteKind.CONFIRMED_LANDING
    assert by_id["im2-intended"].kind is SiteKind.INTENDED_TARGET
    # the intended target and the actual landing are different places
    a, b = by_id["im2-athena"], by_id["im2-intended"]
    assert (a.lat_deg, a.lon_deg_east) != (b.lat_deg, b.lon_deg_east)


def test_unsourced_regions_are_not_selectable_sites():
    doc = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    site_names = " ".join(s["name"] for s in doc["sites"]).lower()
    assert "artemis" not in site_names and "haworth" not in site_names
    assert all(p["status"].startswith("pending") for p in doc["pending_regions"])


def _numbers(text: str) -> list[float]:
    return [float(x) for x in re.findall(r"-?\d+\.\d+(?:E[+-]?\d+)?|-?\d+", text)]


def test_catalogue_coordinates_trace_to_the_quoted_source_text():
    """Every catalogue coordinate must appear (within the source's own rounding) in a quote."""
    for s in load_catalogue(CATALOGUE):
        for value, name in ((abs(s.lat_deg), "lat"), (s.lon_deg_east, "lon")):
            ok = False
            for src in s.sources:
                tol = 0.5 * 10 ** -(len(str(value).split(".")[-1]) if "." in str(value) else 0)
                for n in _numbers(src.quote):
                    # source may print fewer decimals (LROC: 80.13) than the catalogue (NAIF)
                    if abs(abs(n) - abs(value)) <= max(0.006, tol):
                        ok = True
            assert ok, f"{s.id}: {name}={value} not found in any quoted source text"


def test_naif_sourced_coordinates_match_the_kernel_text_exactly():
    for s in load_catalogue(CATALOGUE):
        for src in s.sources:
            if "naif.jpl.nasa.gov" in src.url:
                lon = float(re.search(r"Longitude \(deg\):\s*(-?[\d.]+)", src.quote).group(1))
                lat = float(re.search(r"Latitude \(deg\):\s*(-?[\d.]+)", src.quote).group(1))
                alt = float(re.search(r"Altitude \(km\):\s*([\d.E+-]+)", src.quote).group(1))
                assert (lat, lon) == (s.lat_deg, s.lon_deg_east)
                assert s.reference_height_m == pytest.approx(alt * 1000.0)


def _write(tmp_path, doc):
    p = tmp_path / "sites.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    return p


def _base(**over):
    site = {"id": "x", "name": "X", "kind": "confirmed_landing", "lat_deg": -85.0,
            "lon_deg_east": 10.0,
            "sources": [{"label": "l", "url": "https://example.org/a", "description": "d",
                         "quote": "q"}]}
    site.update(over)
    return {"lat_convention": "planetocentric", "lon_convention": "east_positive", "sites": [site]}


def test_catalogue_rejects_site_without_source(tmp_path):
    with pytest.raises(ValueError, match="no primary-source"):
        load_catalogue(_write(tmp_path, _base(sources=[])))


def test_catalogue_rejects_non_https_source(tmp_path):
    bad = _base()
    bad["sites"][0]["sources"][0]["url"] = "http://example.org"
    with pytest.raises(ValueError, match="https"):
        load_catalogue(_write(tmp_path, bad))


def test_catalogue_rejects_custom_kind_and_wrong_convention_and_duplicates(tmp_path):
    with pytest.raises(ValueError, match="custom"):
        load_catalogue(_write(tmp_path, _base(kind="custom")))
    wrong = _base()
    wrong["lon_convention"] = "west_positive"
    with pytest.raises(ValueError, match="convention"):
        load_catalogue(_write(tmp_path, wrong))
    dup = _base()
    dup["sites"].append(dict(dup["sites"][0]))
    with pytest.raises(ValueError, match="duplicate"):
        load_catalogue(_write(tmp_path, dup))


def test_catalogue_rejects_out_of_range_coordinates(tmp_path):
    with pytest.raises(InvalidInputError):
        load_catalogue(_write(tmp_path, _base(lat_deg=-95.0)))
