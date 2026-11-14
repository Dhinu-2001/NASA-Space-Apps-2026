"""Terrain horizon profile: for each azimuth, the highest elevation angle of terrain seen from an observer.

Method (docs/stage4/HORIZON_METHOD.md):
  * The Moon is a sphere of radius R = 1737.4 km; DEM heights are metres above that sphere (LOLA).
  * Observer at radius R + H_o, H_o = DEM height at the site + observer height above the surface.
  * For azimuth `az` (clockwise from local north; the Stage 3 ENU basis) a ray follows the great
    circle on the sphere:  p(theta) = u cos(theta) + t sin(theta),  u = local up, t = cos(az) N + sin(az) E.
  * Each sample is projected to the south-polar-stereographic grid and the DEM is read by bilinear
    interpolation. The elevation angle of a terrain point at height H_t and great-circle angle theta is
        e = atan2( (R+H_t) cos(theta) - (R+H_o) ,  (R+H_t) sin(theta) )
    which is exact on the sphere, so lunar curvature needs no separate correction term.
  * horizon(az) = max over samples of e. No floor, no smoothing and no fallback value is applied.

Honesty rules (decision S7):
  * NoData samples are skipped and counted; the azimuth is flagged `data_gap` (its horizon is a lower bound).
  * Where the ray leaves DEM coverage the azimuth is flagged `truncated` unless a stated bound proves that no
    terrain beyond the edge can exceed the horizon already found (`unseen_bound_deg`).
  * Windows are never silently substituted: the finest window containing a sample is used, and a NoData
    value there is NOT replaced by a coarser window's value.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from .dem import DemRegistry, DemWindow, lonlat_to_xy
from .errors import DataMissingError, InvalidInputError, OutOfDemCoverageError
from .frames import enu_basis
from .sites import REFERENCE_RADIUS_M, validate_coordinates

ALGORITHM_VERSION = "1"
R_M = REFERENCE_RADIUS_M
DEFAULT_AZ_STEP_DEG = 0.25
MAX_OBSERVER_HEIGHT_M = 1000.0
MAX_TOTAL_SAMPLES = 60_000_000  # n_azimuths * n_distance_steps; protects memory/time


def elevation_angle_rad(theta: np.ndarray | float, h_terrain_m: np.ndarray | float,
                        h_obs_m: float) -> np.ndarray:
    """Elevation (radians) above the observer's local horizontal of a terrain point.

    `theta` is the great-circle angle between observer and terrain point, `h_terrain_m` the terrain
    height and `h_obs_m` the observer height, both above the 1737.4 km sphere. Uses the identity
    (R+Ht)cos(theta) - (R+Ho) = (R+Ht)(cos(theta)-1) + (Ht-Ho) to avoid cancellation at small theta.
    """
    theta = np.asarray(theta, dtype=float)
    ht = np.asarray(h_terrain_m, dtype=float)
    vertical = (R_M + ht) * (-2.0 * np.sin(theta / 2.0) ** 2) + (ht - h_obs_m)
    horizontal = (R_M + ht) * np.sin(theta)
    return np.arctan2(vertical, horizontal)


def sphere_xy(p: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Unit vectors on the sphere (..., 3) in MOON_ME -> south-polar-stereographic (x, y) metres.

    x = 2R py/(1 - pz), y = 2R px/(1 - pz): algebraically equal to the Stage 2 grid
    (x = rho sin(lon), y = rho cos(lon), rho = 2R tan((lat+90)/2)) but valid at any point of the sphere
    except the north pole, and with no trigonometry in the hot loop.
    """
    denom = 1.0 - p[..., 2]
    return 2.0 * R_M * p[..., 1] / denom, 2.0 * R_M * p[..., 0] / denom


# ---------------------------------------------------------------- terrain sampler

class TerrainSampler:
    """Reads heights from an ordered set of verified DEM windows, finest pixel size first."""

    def __init__(self, windows: list[DemWindow]) -> None:
        if not windows:
            raise OutOfDemCoverageError("No DEM window available; no terrain fallback is used.",
                                        field="dem")
        self.windows = sorted(windows, key=lambda w: (w.meta.pixel_size_m, w.meta.window_id))
        self._max_height_m: float | None = None

    @property
    def max_height_m(self) -> float:
        """Highest valid height in any loaded window (a data-derived value, not a global guarantee)."""
        if self._max_height_m is None:
            self._max_height_m = float(max(np.nanmax(w.data) for w in self.windows))
        return self._max_height_m

    def sample(self, x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Returns (z, cover): z in metres (NaN if NoData), cover = index of the window used, -1 if none."""
        shape = x.shape
        xf, yf = x.ravel(), y.ravel()
        z = np.full(xf.shape, np.nan)
        cover = np.full(xf.shape, -1, dtype=np.int16)
        for i, w in enumerate(self.windows):
            todo = np.flatnonzero(cover < 0)
            if todo.size == 0:
                break
            zi, inside = w.sample_xy_array(xf[todo], yf[todo])
            hit = todo[inside]
            cover[hit] = i
            z[hit] = zi[inside]  # may be NaN: NoData stays NoData, it is not filled from a coarser window
        return z.reshape(shape), cover.reshape(shape)

    def height_at(self, x: float, y: float) -> tuple[float, DemWindow]:
        z, cover = self.sample(np.array([x]), np.array([y]))
        if cover[0] < 0:
            raise OutOfDemCoverageError("The observer is outside every loaded DEM window.", field="lat/lon")
        if np.isnan(z[0]):
            raise DataMissingError("DEM has NoData at the observer location; no value is substituted.",
                                   field="dem")
        return float(z[0]), self.windows[int(cover[0])]


# ---------------------------------------------------------------- profile

@dataclass
class HorizonProfile:
    azimuth_deg: np.ndarray            # clockwise from local north, [0, 360)
    horizon_elevation_deg: np.ndarray  # NaN where no valid sample exists
    horizon_distance_km: np.ndarray    # great-circle distance to the limiting terrain sample
    limiting_pixel_size_m: np.ndarray  # pixel size of the DEM window supplying that sample
    range_covered_km: np.ndarray       # distance along the ray over which DEM data exist
    n_missing_samples: np.ndarray      # NoData samples skipped on the ray
    unseen_bound_deg: np.ndarray       # max elevation terrain beyond coverage could reach (see module doc)
    truncated: np.ndarray              # bool: terrain beyond coverage could still raise the horizon
    data_gap: np.ndarray               # bool: NoData encountered; horizon is a lower bound
    meta: dict[str, Any] = field(default_factory=dict)
    served_from: str = "computed"      # computed | memory | disk (not part of the scientific result)

    @property
    def n_azimuths(self) -> int:
        return int(self.azimuth_deg.size)

    def horizon_at(self, az_deg: float) -> float:
        """Horizon elevation at an arbitrary azimuth by linear interpolation between samples.

        Approximation: a narrow peak between two samples is under-represented. Use
        `max_between` when obstruction must not be under-estimated (e.g. across a Sun disc).
        """
        step = 360.0 / self.n_azimuths
        a = (az_deg % 360.0) / step
        i0 = math.floor(a) % self.n_azimuths
        i1 = (i0 + 1) % self.n_azimuths
        f = a - math.floor(a)
        v0, v1 = self.horizon_elevation_deg[i0], self.horizon_elevation_deg[i1]
        return float(v0 * (1 - f) + v1 * f)

    def max_between(self, az_from_deg: float, az_to_deg: float) -> float:
        """Highest sampled horizon over an azimuth span (clockwise from `az_from` to `az_to`, wraps 360).

        Includes the two samples that bracket each end, so the result never under-estimates the
        sampled obstruction across the span.
        """
        step = 360.0 / self.n_azimuths
        start = (az_from_deg % 360.0) / step
        span = (az_to_deg - az_from_deg) % 360.0 / step
        first = math.floor(start + 1e-9)
        last = math.ceil(start + span - 1e-9)
        idx = np.arange(first, last + 1) % self.n_azimuths
        return float(np.nanmax(self.horizon_elevation_deg[idx]))

    def summary(self) -> dict[str, Any]:
        h = self.horizon_elevation_deg
        ok = np.isfinite(h)
        return {
            "n_azimuths": self.n_azimuths,
            "horizon_min_deg": float(np.nanmin(h)) if ok.any() else None,
            "horizon_max_deg": float(np.nanmax(h)) if ok.any() else None,
            "horizon_mean_deg": float(np.nanmean(h)) if ok.any() else None,
            "n_truncated": int(self.truncated.sum()),
            "n_data_gap": int(self.data_gap.sum()),
            "n_complete": int((~self.truncated & ~self.data_gap).sum()),
        }


def compute_horizon(
    sampler: TerrainSampler,
    lat_deg: float,
    lon_deg_east: float,
    observer_height_m: float,
    *,
    az_step_deg: float = DEFAULT_AZ_STEP_DEG,
    step_m: float | None = None,
    max_range_km: float | None = None,
    unseen_terrain_max_height_m: float | None = None,
) -> HorizonProfile:
    """Compute the terrain horizon at a site. All heights are metres above the 1737.4 km sphere.

    `observer_height_m` is above the DEM surface at the site (so H_o = ground + this).
    `step_m` defaults to the finest pixel size of the loaded windows; `max_range_km` defaults to the
    farthest DEM coverage (rays stop where coverage ends).
    `unseen_terrain_max_height_m` is the height assumed for unseen terrain when bounding truncation
    (default: highest value in the loaded windows).
    """
    lat, lon = validate_coordinates(lat_deg, lon_deg_east)
    if not _finite(observer_height_m) or not 0.0 <= observer_height_m <= MAX_OBSERVER_HEIGHT_M:
        raise InvalidInputError(
            f"observer_height_m must be a finite number in [0, {MAX_OBSERVER_HEIGHT_M:g}] metres above the surface",
            field="observer_height_m")
    if not _finite(az_step_deg) or not 0.01 <= az_step_deg <= 10.0:
        raise InvalidInputError("az_step_deg must be in [0.01, 10]", field="az_step_deg")
    n_az_f = 360.0 / az_step_deg
    if abs(n_az_f - round(n_az_f)) > 1e-6:
        raise InvalidInputError("az_step_deg must divide 360 exactly", field="az_step_deg")
    n_az = round(n_az_f)

    x0, y0 = lonlat_to_xy(lat, lon)  # raises for lat >= 0
    ground_m, ground_window = sampler.height_at(x0, y0)
    h_obs = ground_m + observer_height_m

    finest = sampler.windows[0].meta.pixel_size_m
    step = float(step_m) if step_m is not None else finest
    if not _finite(step) or step <= 0.0:
        raise InvalidInputError("step_m must be a positive number", field="step_m")
    if max_range_km is None:
        far = max(_farthest_corner_m(w, x0, y0) for w in sampler.windows)
        max_range_m = far
    else:
        if not _finite(max_range_km) or max_range_km <= 0.0:
            raise InvalidInputError("max_range_km must be positive", field="max_range_km")
        max_range_m = max_range_km * 1000.0
    n_d = math.floor(max_range_m / step)
    if n_d < 1:
        raise InvalidInputError("max range is smaller than one sampling step", field="max_range_km")
    if n_az * n_d > MAX_TOTAL_SAMPLES:
        raise InvalidInputError(
            f"{n_az} azimuths x {n_d} steps exceeds the {MAX_TOTAL_SAMPLES:,}-sample limit; "
            "increase az_step_deg or step_m, or lower max_range_km", field="az_step_deg")

    h_unseen = sampler.max_height_m if unseen_terrain_max_height_m is None else float(unseen_terrain_max_height_m)
    basis = enu_basis(lat, lon)
    dist = step * np.arange(1, n_d + 1)          # great-circle distance along the ray, m
    theta = dist / R_M
    cos_t, sin_t = np.cos(theta), np.sin(theta)

    azimuth = np.arange(n_az) * az_step_deg
    horizon = np.full(n_az, np.nan)
    h_dist = np.full(n_az, np.nan)
    h_pix = np.full(n_az, np.nan)
    covered = np.zeros(n_az)
    n_missing = np.zeros(n_az, dtype=np.int64)
    bound = np.full(n_az, np.nan)

    chunk = max(1, int(2_000_000 // n_d))
    for a0 in range(0, n_az, chunk):
        az_r = np.radians(azimuth[a0 : a0 + chunk])
        tdir = np.cos(az_r)[:, None] * basis.north[None, :] + np.sin(az_r)[:, None] * basis.east[None, :]
        pts = basis.up[None, None, :] * cos_t[None, :, None] + tdir[:, None, :] * sin_t[None, :, None]
        x, y = sphere_xy(pts)
        z, cover = sampler.sample(x, y)

        outside = cover < 0
        any_out = outside.any(axis=1)
        n_cov = np.where(any_out, outside.argmax(axis=1), n_d)  # samples [0, n_cov) are inside coverage
        valid_pos = np.arange(n_d)[None, :] < n_cov[:, None]
        missing = valid_pos & np.isnan(z)
        usable = valid_pos & ~np.isnan(z)

        e = elevation_angle_rad(theta[None, :], np.where(usable, z, 0.0), h_obs)
        e = np.where(usable, e, -np.inf)
        k = e.argmax(axis=1)
        rows = np.arange(e.shape[0])
        best = e[rows, k]
        has = np.isfinite(best)
        sl = slice(a0, a0 + e.shape[0])
        horizon[sl] = np.where(has, np.degrees(best), np.nan)
        h_dist[sl] = np.where(has, dist[k] / 1000.0, np.nan)
        pix = np.array([w.meta.pixel_size_m for w in sampler.windows])
        h_pix[sl] = np.where(has, pix[np.clip(cover[rows, k], 0, None)], np.nan)
        covered[sl] = n_cov * step / 1000.0
        n_missing[sl] = missing.sum(axis=1)
        # Highest elevation any terrain beyond the first uncovered sample could have, assuming it is no
        # higher than h_unseen. For H >= H_o the elevation of a point at height H falls monotonically with
        # distance, so the bound is its value at the edge. For H < H_o it first rises to the tangent
        # (elevation -arccos((R+H)/(R+H_o))) and then falls; the bound is that tangent value if the edge
        # lies before the tangent distance.
        theta_edge = (n_cov + 1) * step / R_M
        theta_star = math.acos(min(1.0, (R_M + h_unseen) / (R_M + h_obs))) if h_unseen < h_obs else 0.0
        bound[sl] = np.degrees(np.where(theta_edge >= theta_star,
                                        elevation_angle_rad(theta_edge, h_unseen, h_obs), -theta_star))

    truncated = ~(bound <= horizon)  # NaN horizon => truncated
    data_gap = n_missing > 0
    meta = {
        "algorithm_version": ALGORITHM_VERSION,
        "observer": {"lat_deg": lat, "lon_deg_east": lon, "ground_height_m": ground_m,
                     "observer_height_above_surface_m": float(observer_height_m),
                     "observer_radius_height_m": h_obs,
                     "ground_height_window": ground_window.meta.window_id},
        "parameters": {"az_step_deg": az_step_deg, "step_m": step, "max_range_km": max_range_m / 1000.0,
                       "unseen_terrain_max_height_m": h_unseen, "reference_radius_m": R_M,
                       "interpolation": "bilinear_pixel_centres"},
        "windows": [{"window_id": w.meta.window_id, "product_id": w.meta.product_id,
                     "pixel_size_m": w.meta.pixel_size_m, "sha256": w.meta.sha256,
                     "overview_level": w.meta.overview_level, "source_url": w.meta.source_url}
                    for w in sampler.windows],
    }
    return HorizonProfile(azimuth, horizon, h_dist, h_pix, covered, n_missing, bound, truncated, data_gap, meta)


def _finite(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _farthest_corner_m(w: DemWindow, x0: float, y0: float) -> float:
    m = w.meta
    return max(math.hypot(cx - x0, cy - y0) for cx in (m.left_m, m.right_m) for cy in (m.bottom_m, m.top_m))


# ---------------------------------------------------------------- window selection and caching

def _contains(a: Any, b: Any) -> bool:
    """True if window meta `a` fully contains window meta `b` (axis-aligned in the same grid)."""
    return a.left_m <= b.left_m and a.right_m >= b.right_m and a.bottom_m <= b.bottom_m and a.top_m >= b.top_m


def select_windows(registry: DemRegistry, lat: float, lon: float,
                   window_ids: list[str] | None = None) -> list[DemWindow]:
    """Windows to sample for a site. Drops a window wholly contained in another of equal or finer
    resolution (it adds nothing). With `window_ids` the caller chooses explicitly."""
    if window_ids is not None:
        for wid in window_ids:
            if wid not in registry.windows:
                raise InvalidInputError(f"Unknown DEM window '{wid}'.", field="window_ids")
        metas = [registry.windows[w] for w in window_ids]
    else:
        metas = registry.covering(lat, lon)
        if not metas:
            raise OutOfDemCoverageError(
                "No available DEM window covers this location, so no terrain horizon can be computed. "
                "No flat-terrain or synthetic fallback is used.", field="lat/lon",
                details={"lat_deg": lat, "lon_deg_east": lon, "known_windows": sorted(registry.windows)})
    keep: list[Any] = []
    # Finest first; among equal pixel sizes the larger window first, so a nested duplicate is dropped.
    for m in sorted(metas, key=lambda q: (q.pixel_size_m, -(q.right_m - q.left_m) * (q.top_m - q.bottom_m),
                                          q.window_id)):
        if not any(k.pixel_size_m <= m.pixel_size_m and _contains(k, m) for k in keep):
            keep.append(m)
    return [registry.window(m.window_id) for m in keep]


class HorizonService:
    """Computes horizon profiles for catalogue/custom sites with an in-memory + on-disk cache.

    Cache key = SHA-256 of (algorithm version, the SHA-256 of every window used, observer, parameters).
    Changing any input, any DEM byte or the algorithm therefore changes the key; a stale entry can never
    be served. Disk entries live in data/results/horizon (git-ignored, regenerable).
    """

    def __init__(self, data_dir: Path, memory_items: int = 16) -> None:
        self.data_dir = Path(data_dir)
        self.registry = DemRegistry(self.data_dir)
        self.cache_dir = self.data_dir / "results" / "horizon"
        self._memory: OrderedDict[str, HorizonProfile] = OrderedDict()
        self._memory_items = memory_items
        self._lock = threading.RLock()  # cache dicts and lazy window loads are shared across API threads

    def profile(self, lat_deg: float, lon_deg_east: float, observer_height_m: float, *,
                az_step_deg: float = DEFAULT_AZ_STEP_DEG, step_m: float | None = None,
                max_range_km: float | None = None, window_ids: list[str] | None = None,
                use_cache: bool = True) -> HorizonProfile:
        with self._lock:
            return self._profile(lat_deg, lon_deg_east, observer_height_m, az_step_deg, step_m,
                                 max_range_km, window_ids, use_cache)

    def _profile(self, lat_deg: float, lon_deg_east: float, observer_height_m: float, az_step_deg: float,
                 step_m: float | None, max_range_km: float | None, window_ids: list[str] | None,
                 use_cache: bool) -> HorizonProfile:
        lat, lon = validate_coordinates(lat_deg, lon_deg_east)
        windows = select_windows(self.registry, lat, lon, window_ids)
        # Ceiling for unseen terrain (used only to decide `truncated`): the highest value in ANY window the
        # project holds, not just the ones sampled here, so a tiny window cannot certify itself complete.
        h_unseen = max(m.z_max_m for m in self.registry.windows.values())
        key = self._key(lat, lon, observer_height_m, az_step_deg, step_m, max_range_km, windows, h_unseen)
        if use_cache:
            hit = self._memory.get(key)
            if hit is not None:
                self._memory.move_to_end(key)
                hit.served_from = "memory"
                return hit
            disk = self._read_disk(key)
            if disk is not None:
                self._remember(key, disk)
                disk.served_from = "disk"
                return disk
        prof = compute_horizon(TerrainSampler(windows), lat, lon, observer_height_m,
                               az_step_deg=az_step_deg, step_m=step_m, max_range_km=max_range_km,
                               unseen_terrain_max_height_m=h_unseen)
        prof.meta["cache_key"] = key
        if use_cache:
            self._remember(key, prof)
            self._write_disk(key, prof)
        return prof

    @staticmethod
    def _key(lat: float, lon: float, h: Any, az_step: Any, step_m: Any, max_range_km: Any,
             windows: list[DemWindow], h_unseen: float) -> str:
        blob = json.dumps({"algo": ALGORITHM_VERSION, "lat": lat, "lon": lon, "h": h, "az": az_step,
                           "step": step_m, "range": max_range_km, "unseen": h_unseen,
                           "windows": [(w.meta.window_id, w.meta.sha256) for w in windows]}, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()

    def _remember(self, key: str, prof: HorizonProfile) -> None:
        self._memory[key] = prof
        self._memory.move_to_end(key)
        while len(self._memory) > self._memory_items:
            self._memory.popitem(last=False)

    _ARRAYS = ("azimuth_deg", "horizon_elevation_deg", "horizon_distance_km", "limiting_pixel_size_m",
               "range_covered_km", "n_missing_samples", "unseen_bound_deg", "truncated", "data_gap")

    def _write_disk(self, key: str, prof: HorizonProfile) -> None:
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            tmp = self.cache_dir / f"{key}.tmp.npz"
            np.savez_compressed(tmp, meta_json=np.array(json.dumps(prof.meta)),
                                **{n: getattr(prof, n) for n in self._ARRAYS})
            os.replace(tmp, self.cache_dir / f"{key}.npz")
        except OSError:
            pass  # the cache is an optimisation only; the computed result is still returned

    def _read_disk(self, key: str) -> HorizonProfile | None:
        path = self.cache_dir / f"{key}.npz"
        if not path.exists():
            return None
        try:
            with np.load(path, allow_pickle=False) as z:
                meta = json.loads(str(z["meta_json"]))
                if meta.get("cache_key") != key or meta.get("algorithm_version") != ALGORITHM_VERSION:
                    return None
                return HorizonProfile(**{n: z[n] for n in self._ARRAYS}, meta=meta)
        except (OSError, ValueError, KeyError):
            return None  # unreadable/corrupt entry: recompute rather than trust it
