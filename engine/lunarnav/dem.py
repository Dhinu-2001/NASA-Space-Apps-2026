"""LOLA DEM windows: projection, integrity-checked loading, and elevation lookup.

Grid convention (VERIFIED in Stage 2, see docs/stage2/DEM_VERIFICATION.md):
  * Moon sphere R = 1737.4 km, south polar stereographic, true scale at the pole (k0 = 1).
  * x = rho*sin(lon_east), y = rho*cos(lon_east), rho = 2R*tan((lat+90deg)/2).
    (lon 0 points toward +y, 90E toward +x.)
  * Heights are metres above the 1737.4 km reference sphere.
  * Raster values are pixel-centre samples; NoData is NaN.

Policy (decision S7): a request is never answered with flat terrain, a coarser window, or a
guessed value when data is missing. It raises a typed error instead.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import rasterio

from .errors import DataMissingError, InvalidInputError, OutOfDemCoverageError
from .sites import REFERENCE_RADIUS_M, validate_coordinates

R = REFERENCE_RADIUS_M


# ---------------------------------------------------------------- projection

def lonlat_to_xy(lat_deg, lon_deg_east):
    """(lat, lon_east) degrees -> south-polar-stereographic (x, y) metres. Array-friendly.

    Only defined for the southern hemisphere (lat < 0); the projection is singular at lat = +90.
    """
    lat = np.asarray(lat_deg, dtype=float)
    if np.any(lat >= 0.0):
        raise OutOfDemCoverageError(
            "South polar stereographic grid is only defined for southern latitudes (lat < 0).",
            field="lat",
        )
    colat = np.radians(lat + 90.0)
    rho = 2.0 * R * np.tan(colat / 2.0)
    lon = np.radians(np.asarray(lon_deg_east, dtype=float))
    x, y = rho * np.sin(lon), rho * np.cos(lon)
    return (float(x), float(y)) if x.ndim == 0 else (x, y)


def xy_to_lonlat(x_m, y_m):
    """Inverse of lonlat_to_xy. Returns (lat, lon_east) with lon in [-180, 180]."""
    x = np.asarray(x_m, dtype=float)
    y = np.asarray(y_m, dtype=float)
    rho = np.hypot(x, y)
    lat = np.degrees(2.0 * np.arctan(rho / (2.0 * R))) - 90.0
    lon = np.degrees(np.arctan2(x, y))
    return (float(lat), float(lon)) if lat.ndim == 0 else (lat, lon)


# ---------------------------------------------------------------- metadata

@dataclass(frozen=True)
class DemWindowMeta:
    window_id: str
    product_id: str
    file: str  # path relative to the data directory
    sha256: str  # SHA-256 of the reference file's bytes (provenance; platform-dependent, so NOT what is verified when content_sha256 exists)
    pixel_size_m: float
    left_m: float
    top_m: float
    width: int
    height: int
    valid_fraction: float
    z_min_m: float
    z_max_m: float
    source_url: str
    overview_level: int | None
    raw: dict[str, Any]
    content_sha256: str | None = None  # SHA-256 of the decoded elevations + georeferencing (platform-independent); verified on load

    @property
    def right_m(self) -> float:
        return self.left_m + self.width * self.pixel_size_m

    @property
    def bottom_m(self) -> float:
        return self.top_m - self.height * self.pixel_size_m

    @classmethod
    def from_dict(cls, window_id: str, d: dict[str, Any]) -> DemWindowMeta:
        return cls(
            window_id=window_id, product_id=d["product_id"], file=d["file"], sha256=d["sha256"],
            pixel_size_m=float(d["pixel_size_m"]), left_m=float(d["left_m"]),
            top_m=float(d["top_m"]), width=int(d["width"]), height=int(d["height"]),
            valid_fraction=float(d["valid_fraction"]), z_min_m=float(d["z_min_m"]),
            z_max_m=float(d["z_max_m"]), source_url=d["source_url"],
            overview_level=d.get("overview_level"), raw=d, content_sha256=d.get("content_sha256"),
        )


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def content_sha256(data: np.ndarray, transform: Any) -> str:
    """Platform-independent fingerprint of a DEM window: the decoded elevations and their georeferencing, not the file bytes.

    The same elevations written by a different GDAL/zlib build (e.g. Linux vs Windows) are different files but give the same
    value here. Covers: shape, float32 little-endian values (every NaN canonicalised), and the six affine transform terms.
    """
    a = np.ascontiguousarray(data, dtype="<f4")
    if np.isnan(a).any():
        a = np.where(np.isnan(a), np.float32("nan"), a).astype("<f4", copy=False)
    h = hashlib.sha256()
    h.update(b"lunarnav-dem-content-v1\n")
    h.update(f"{a.shape[0]}x{a.shape[1]} float32\n".encode())
    h.update(repr(tuple(float(v) for v in tuple(transform)[:6])).encode())
    h.update(b"\n")
    h.update(a.tobytes())
    return h.hexdigest()


@dataclass(frozen=True)
class ElevationResult:
    elevation_m: float
    lat_deg: float
    lon_deg_east: float
    x_m: float
    y_m: float
    window_id: str
    product_id: str
    pixel_size_m: float
    method: str
    source_url: str
    sha256: str
    data_class: str = "measured_interpolated"  # LOLA altimetry, gridded/interpolated

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


# ---------------------------------------------------------------- window

class DemWindow:
    """A raster window held in memory, verified against its recorded content SHA-256 (elevations + georeferencing)."""

    def __init__(self, meta: DemWindowMeta, data: np.ndarray) -> None:
        self.meta = meta
        self.data = data  # float32, shape (height, width), NaN = NoData

    @classmethod
    def load(cls, meta: DemWindowMeta, data_dir: Path) -> DemWindow:
        path = data_dir / meta.file
        if not path.exists():
            raise DataMissingError(
                f"DEM window file is not present: {meta.file}. "
                "Run scripts/extract_dem_window.py to create it.",
                field="dem", details={"window_id": meta.window_id, "file": meta.file},
            )
        if meta.content_sha256 is None:
            # legacy manifest entry without a content hash: fall back to the byte-level file hash
            actual = sha256_file(path)
            if actual != meta.sha256:
                raise DataMissingError(
                    "DEM window checksum does not match the recorded manifest; refusing to use it.",
                    field="dem",
                    details={"window_id": meta.window_id, "expected": meta.sha256, "actual": actual},
                )
        try:
            with rasterio.open(path) as ds:
                data = ds.read(1).astype(np.float32, copy=False)
                transform = ds.transform
        except Exception as e:
            raise DataMissingError(
                f"DEM window file cannot be read: {meta.file} ({type(e).__name__}); refusing to use it.",
                field="dem", details={"window_id": meta.window_id, "file": meta.file},
            ) from e
        if meta.content_sha256 is not None:
            actual = content_sha256(data, transform)
            if actual != meta.content_sha256:
                raise DataMissingError(
                    "DEM window content checksum (elevations and georeferencing) does not match the recorded manifest; refusing to use it.",
                    field="dem",
                    details={"window_id": meta.window_id, "expected": meta.content_sha256, "actual": actual},
                )
        if data.shape != (meta.height, meta.width):
            raise DataMissingError("DEM window shape disagrees with manifest.", field="dem",
                                   details={"window_id": meta.window_id})
        return cls(meta, data)

    def contains_xy(self, x: float, y: float, margin_px: float = 0.0) -> bool:
        m, pad = self.meta, margin_px * self.meta.pixel_size_m
        return (m.left_m + pad <= x <= m.right_m - pad) and (m.bottom_m + pad <= y <= m.top_m - pad)

    def elevation_xy(self, x: float, y: float) -> float:
        """Bilinear interpolation between the four surrounding pixel centres.

        Raises OutOfDemCoverageError if the point is closer than half a pixel to the window
        edge (four neighbours are required) and DataMissingError if any neighbour is NoData.
        """
        m = self.meta
        col = (x - m.left_m) / m.pixel_size_m - 0.5
        row = (m.top_m - y) / m.pixel_size_m - 0.5
        if not (0.0 <= col <= m.width - 1 and 0.0 <= row <= m.height - 1):
            raise OutOfDemCoverageError("Point is outside the DEM window.", field="lat/lon",
                                        details={"window_id": m.window_id})
        c0, r0 = min(math.floor(col), m.width - 2), min(math.floor(row), m.height - 2)
        fc, fr = col - c0, row - r0
        block = self.data[r0 : r0 + 2, c0 : c0 + 2]
        if np.isnan(block).any():
            raise DataMissingError(
                "DEM has NoData at this location; no value is substituted.", field="dem",
                details={"window_id": m.window_id, "x_m": x, "y_m": y},
            )
        top = block[0, 0] * (1 - fc) + block[0, 1] * fc
        bot = block[1, 0] * (1 - fc) + block[1, 1] * fc
        return float(top * (1 - fr) + bot * fr)


    def sample_xy_array(self, x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Vectorised bilinear lookup identical to `elevation_xy` (same pixel-centre convention).

        Returns (z, inside). `inside` is True where the point has four neighbouring pixel centres
        in this window. `z` is NaN where the point is outside OR any neighbour is NoData; the
        caller tells the two cases apart with `inside`. Nothing is ever filled in.
        """
        m = self.meta
        col = (np.asarray(x, dtype=float) - m.left_m) / m.pixel_size_m - 0.5
        row = (m.top_m - np.asarray(y, dtype=float)) / m.pixel_size_m - 0.5
        inside = (col >= 0.0) & (col <= m.width - 1) & (row >= 0.0) & (row <= m.height - 1)
        z = np.full(col.shape, np.nan, dtype=float)
        if not inside.any():
            return z, inside
        c = col[inside]
        r = row[inside]
        c0 = np.minimum(np.floor(c).astype(np.intp), m.width - 2)
        r0 = np.minimum(np.floor(r).astype(np.intp), m.height - 2)
        fc, fr = c - c0, r - r0
        d = self.data
        top = d[r0, c0] * (1 - fc) + d[r0, c0 + 1] * fc
        bot = d[r0 + 1, c0] * (1 - fc) + d[r0 + 1, c0 + 1] * fc
        z[inside] = top * (1 - fr) + bot * fr  # NaN propagates from any NaN neighbour
        return z, inside


# ---------------------------------------------------------------- registry

class DemRegistry:
    """Looks up which verified window covers a site and returns elevations from it."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        manifest = self.data_dir / "manifests" / "dem_windows.json"
        self._cache: dict[str, DemWindow] = {}
        if not manifest.exists():
            self.windows: dict[str, DemWindowMeta] = {}
        else:
            doc = json.loads(manifest.read_text(encoding="utf-8"))
            self.windows = {k: DemWindowMeta.from_dict(k, v) for k, v in doc["windows"].items()}

    def window(self, window_id: str) -> DemWindow:
        """The checksum-verified window (loaded once, then cached in memory)."""
        if window_id not in self.windows:
            raise InvalidInputError(f"Unknown DEM window '{window_id}'.", field="window_id")
        return self._window(window_id)

    def _window(self, window_id: str) -> DemWindow:
        if window_id not in self._cache:
            self._cache[window_id] = DemWindow.load(self.windows[window_id], self.data_dir)
        return self._cache[window_id]

    def covering(self, lat_deg: float, lon_deg: float, margin_px: float = 1.0) -> list[DemWindowMeta]:
        """Windows that cover the point, finest pixel size first."""
        lat, lon = validate_coordinates(lat_deg, lon_deg)
        if lat >= 0.0:
            return []
        x, y = lonlat_to_xy(lat, lon)
        found = [
            m for m in self.windows.values()
            if m.left_m + margin_px * m.pixel_size_m <= x <= m.right_m - margin_px * m.pixel_size_m
            and m.bottom_m + margin_px * m.pixel_size_m <= y <= m.top_m - margin_px * m.pixel_size_m
        ]
        return sorted(found, key=lambda m: (m.pixel_size_m, m.window_id))

    def elevation(self, lat_deg: float, lon_deg: float, window_id: str | None = None
                  ) -> ElevationResult:
        lat, lon = validate_coordinates(lat_deg, lon_deg)
        if window_id is not None:
            if window_id not in self.windows:
                raise InvalidInputError(f"Unknown DEM window '{window_id}'.", field="window_id")
            chosen = self.windows[window_id]
        else:
            candidates = self.covering(lat, lon)
            if not candidates:
                raise OutOfDemCoverageError(
                    "No available DEM window covers this location. No flat-terrain or "
                    "synthetic fallback is used.",
                    field="lat/lon",
                    details={"lat_deg": lat, "lon_deg_east": lon,
                             "known_windows": sorted(self.windows)},
                )
            chosen = candidates[0]  # finest resolution; NoData here is an error, not a fallback
        x, y = lonlat_to_xy(lat, lon)
        z = self._window(chosen.window_id).elevation_xy(x, y)
        return ElevationResult(
            elevation_m=z, lat_deg=lat, lon_deg_east=lon, x_m=x, y_m=y,
            window_id=chosen.window_id, product_id=chosen.product_id,
            pixel_size_m=chosen.pixel_size_m, method="bilinear_pixel_centres",
            source_url=chosen.source_url, sha256=chosen.sha256,
        )
