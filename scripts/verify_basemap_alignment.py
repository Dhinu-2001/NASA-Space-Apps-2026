"""Alignment study for the south-pole imagery basemap (NASA Moon Trek WMTS, LRO LROC WAC S-Pole mosaic v2).

Measures how well the tiles, placed in the app's own south-polar stereographic grid (the engine's dem.lonlat_to_xy; sphere
radius 1737.4 km), line up with independent references, and writes docs/basemap/alignment_results.json:

  A. Mosaic seams: the product's meridian seams must cross exactly at the pole (grid origin / centring).
  B. WAC vs the project's own LOLA DEM (relief correlation, DEM hillshade lit with an azimuth that follows the polar angle):
     global registration shift around the pole, and its sensitivity to deliberate 230 m origin errors (does the method resolve them?).
  C. Shackleton crater: circle fit to the lit rim in the image vs the published centre (USGS Gazetteer 5450) and the DEM.
  D. Chandrayaan-3 (632 km from the pole): registration against the 60 m DEM plus a deliberate 0.1 % scale-error test (radial scale).
  E. IM-2 Athena vs the Mons Mouton massif outlined from the DEM.

Needs network (tiles from trek.nasa.gov, cached) and the local DEM windows in data/dem_cache. Usage:
    python scripts/verify_basemap_alignment.py [--cache DIR]
This is evidence tooling only; the web app does not use any of it.
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
import urllib.request
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import rasterio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
from lunarnav.dem import R, lonlat_to_xy

BASE = "https://trek.nasa.gov/tiles/Moon/SP/LRO_WAC_Mosaic_SPole60_100m_v02/1.0.0//default/default028mm"
TL = 1_095_930.0                       # TopLeftCorner (-TL, +TL) from WMTSCapabilities.xml
SPAN0 = 2 * TL
CACHE = Path(sys.argv[sys.argv.index("--cache") + 1]) if "--cache" in sys.argv else ROOT / "data" / "results" / "basemap_tiles"
CACHE.mkdir(parents=True, exist_ok=True)
SITES = {"im2-athena": (-84.79059, 29.19567), "im1-odysseus": (-80.12759, 1.44587), "chandrayaan3-shiv-shakti": (-69.3741, 32.32)}


def res(z: int) -> float:
    return SPAN0 / 2**z / 256


def tile(z: int, r: int, c: int) -> np.ndarray:
    f = CACHE / f"{z}_{r}_{c}.png"
    if not f.exists():
        req = urllib.request.Request(f"{BASE}/{z}/{r}/{c}.png", headers={"User-Agent": "python-urllib/3 (alignment study)"})
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    f.write_bytes(resp.read())
                break
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(2)
    with rasterio.open(f) as ds:
        return ds.read(1)


def mosaic(z: int, r0: int, r1: int, c0: int, c1: int):
    jobs = [(z, r, c) for r in range(r0, r1 + 1) for c in range(c0, c1 + 1)]
    with ThreadPoolExecutor(8) as ex:
        tiles = dict(zip(jobs, ex.map(lambda j: tile(*j), jobs)))
    img = np.concatenate([np.concatenate([tiles[(z, r, c)] for c in range(c0, c1 + 1)], axis=1) for r in range(r0, r1 + 1)], axis=0)
    return img.astype(float), -TL + c0 * 256 * res(z), TL - r0 * 256 * res(z), res(z)


def sample(arr, left, top, rs, X, Y):
    c = (X - left) / rs - 0.5
    r = (top - Y) / rs - 0.5
    c0 = np.clip(np.floor(c).astype(int), 0, arr.shape[1] - 2)
    r0 = np.clip(np.floor(r).astype(int), 0, arr.shape[0] - 2)
    fc, fr = c - c0, r - r0
    return arr[r0, c0] * (1 - fc) * (1 - fr) + arr[r0, c0 + 1] * fc * (1 - fr) + arr[r0 + 1, c0] * (1 - fc) * fr + arr[r0 + 1, c0 + 1] * fc * fr


def blur(z, s):
    k = int(3 * s) * 2 + 1
    g = np.exp(-0.5 * ((np.arange(k) - k // 2) / s) ** 2)
    g /= g.sum()
    z = np.apply_along_axis(lambda v: np.convolve(v, g, mode="same"), 0, z)
    return np.apply_along_axis(lambda v: np.convolve(v, g, mode="same"), 1, z)


def hp(z, s=6.0):
    return z - blur(z, s)


def hillshade(gx, gy, theta, phi, elev=3.0):
    a = np.radians(theta + phi)
    e = math.radians(elev)
    return (-gx * math.cos(e) * np.sin(a) - gy * math.cos(e) * np.cos(a) + math.sin(e)) / np.sqrt(1 + gx**2 + gy**2)


def xcorr(f, h, mask):
    f = (f - f[mask].mean()) * mask
    h = (h - h[mask].mean()) * mask
    f /= f[mask].std()
    h /= h[mask].std()
    cc = np.fft.fftshift(np.fft.ifft2(np.fft.fft2(f) * np.conj(np.fft.fft2(h))).real) / mask.sum()
    cy, cx = np.unravel_index(np.argmax(cc), cc.shape)
    n = cc.shape[0] // 2

    def sub(v0, vm, vp):
        d = vm - 2 * v0 + vp
        return 0.0 if d == 0 else 0.5 * (vm - vp) / d
    return (cx - n) + sub(cc[cy, cx], cc[cy, cx - 1], cc[cy, cx + 1]), (cy - n) + sub(cc[cy, cx], cc[cy - 1, cx], cc[cy + 1, cx]), float(cc.max())


def register(wac_img, x0, y0, rs, dem, dleft, dtop, dres, centre, half, g, mask_fn, phis):
    xs = centre[0] + np.arange(-half, half, g) + g / 2
    ys = centre[1] + np.arange(-half, half, g)[::-1] + g / 2
    X, Y = np.meshgrid(xs, ys)
    dem_s = sample(dem, dleft, dtop, dres, X, Y)
    gy, gx = np.gradient(blur(dem_s, 1.0), -g, g)
    theta = np.degrees(np.arctan2(X, Y))
    mask = mask_fn(X, Y)
    Wimg = hp(sample(wac_img, x0, y0, rs, X, Y))
    best = None
    for phi in phis:
        dx, dy, pk = xcorr(Wimg, hp(hillshade(gx, gy, theta, phi)), mask)
        if best is None or pk > best[0]:
            best = (pk, phi, dx * g, dy * g)
    H = hp(hillshade(gx, gy, theta, best[1]))
    return best, (X, Y, mask, H)


def main() -> None:
    out: dict = {"projection": "engine lunarnav.dem.lonlat_to_xy; sphere radius 1737400 m; tiles placed with TopLeftCorner (-1095930, 1095930) m"}
    z5 = 5
    img5, x0, y0, rs5 = mosaic(z5, 12, 19, 12, 19)            # 8x8 tiles centred on the pole, 267.56 m/px
    H, W = img5.shape

    # ---- A. seams
    d = np.abs(np.diff(img5[:, 150:700], axis=0)).mean(axis=1)
    rows = np.arange(len(d))
    sel = (rows > H / 2 - 40) & (rows < H / 2 + 40)
    r_seam = rows[sel][np.argmax(d[sel])] + 1.0
    d2 = np.abs(np.diff(img5[1150:1850, :], axis=1)).mean(axis=0)
    cols = np.arange(len(d2))
    sel2 = (cols > W / 2 - 40) & (cols < W / 2 + 40)
    c_seam = cols[sel2][np.argmax(d2[sel2])] + 1.0
    out["A_seams"] = {"horizontal_seam_y_m": y0 - r_seam * rs5, "vertical_seam_x_m": x0 + c_seam * rs5, "pixel_m": rs5,
                      "note": "seam boundaries sit on pixel edges; expected at exactly 0 m (the pole)"}

    # ---- B. pole-region registration against the local 320 m DEM window
    with rasterio.open(ROOT / "data" / "dem_cache" / "im2_320m_r160km.tif") as ds:
        dem = ds.read(1).astype(float)
        dres, dleft, dtop, dright, dbottom = ds.res[0], ds.bounds.left, ds.bounds.top, ds.bounds.right, ds.bounds.bottom
    g = 320.0

    def pole_mask(X, Y):
        rho = np.hypot(X, Y)
        return (rho > 20000) & (rho < 240000) & (X > dleft + 8 * dres) & (X < dright - 8 * dres) & (Y < dtop - 8 * dres) & (Y > dbottom + 8 * dres)
    best, (X, Y, mask, Hs) = register(img5, x0, y0, rs5, dem, dleft, dtop, dres, (0.0, 0.0), 250000.0, g, pole_mask, range(0, 360, 15))
    out["B_pole_vs_dem"] = {"correlation": best[0], "illumination_phi_deg": best[1], "shift_m": [best[2], best[3]], "grid_m": g,
                            "interpretation": "WAC minus DEM registration shift with the tiles placed at the WMTS origin"}
    tests = {}
    for tag, sx_, sy_ in (("origin_x_plus_230m", 230.0, 0.0), ("origin_x_minus_230m", -230.0, 0.0), ("origin_y_plus_230m", 0.0, 230.0), ("origin_y_minus_230m", 0.0, -230.0)):
        Ws = hp(sample(img5, x0 + sx_, y0 + sy_, rs5, X, Y))
        dx, dy, pk = xcorr(Ws, Hs, mask)
        tests[tag] = {"shift_m": [dx * g, dy * g], "correlation": pk}
    out["B_origin_error_sensitivity"] = tests

    # ---- C. Shackleton (USGS Gazetteer 5450: 89.67 S, 129.78 E, 20.92 km)
    px, py = lonlat_to_xy(-89.67, 129.78)
    ci, ri = int((px - x0) / rs5), int((y0 - py) / rs5)
    seen = np.zeros(img5.shape, bool)
    q = deque([(ri, ci)])
    seen[ri, ci] = True
    dark = img5 <= 12
    while q:
        r, c = q.popleft()
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            a, b = r + dr, c + dc
            if 0 <= a < H and 0 <= b < W and dark[a, b] and not seen[a, b] and math.hypot(b - ci, a - ri) * rs5 < 13500:
                seen[a, b] = True
                q.append((a, b))
    bright = img5 >= 45
    pts = np.array([(x0 + (c + 0.5) * rs5, y0 - (r + 0.5) * rs5) for r, c in zip(*np.nonzero(seen)) if bright[max(r - 2, 0):r + 3, max(c - 2, 0):c + 3].any()])
    n_before = len(pts)
    fits = []
    for _ in range(8):                                   # trim outliers (> 1.5 px from the circle) until the set stops changing
        A = np.c_[2 * pts[:, 0], 2 * pts[:, 1], np.ones(len(pts))]
        s, *_ = np.linalg.lstsq(A, (pts**2).sum(1), rcond=None)
        xc, yc = s[0], s[1]
        rad = math.sqrt(s[2] + xc**2 + yc**2)
        resid = np.hypot(pts[:, 0] - xc, pts[:, 1] - yc) - rad
        fits.append((len(pts), xc, yc, rad))
        keep = np.abs(resid) < 1.5 * rs5
        if keep.all():
            break
        pts = pts[keep]
    out["C_shackleton"] = {"published_centre_m": [px, py], "published_diameter_km": 20.92, "image_rim_centre_m": [xc, yc], "image_rim_radius_km": rad / 1000,
                           "offset_m": [xc - px, yc - py], "offset_px_267m": math.hypot(xc - px, yc - py) / rs5,
                           "published_coordinate_precision_m": math.radians(0.01) * R, "rim_points": len(pts), "rim_points_before_trimming": n_before,
                           "fit_history": [{"points": a_, "centre_m": [b_, c_], "radius_km": d_ / 1000} for a_, b_, c_, d_ in fits]}

    # ---- D. Chandrayaan-3: registration at 632 km radius and a deliberate 0.1 % scale error
    cx, cy = lonlat_to_xy(*SITES["chandrayaan3-shiv-shakti"])
    ct, rt = int((cx + TL) // (256 * res(5))), int((TL - cy) // (256 * res(5)))
    img3, x03, y03, rs3 = mosaic(5, rt - 2, rt + 2, ct - 2, ct + 2)
    with rasterio.open(ROOT / "data" / "dem_cache" / "ch3_60m_r200km.tif") as ds:
        d60 = ds.read(1).astype(float)
        r60, l60, t60, rt60, b60 = ds.res[0], ds.bounds.left, ds.bounds.top, ds.bounds.right, ds.bounds.bottom
    k = 4
    d240 = d60[: d60.shape[0] // k * k, : d60.shape[1] // k * k].reshape(d60.shape[0] // k, k, d60.shape[1] // k, k).mean((1, 3))

    def ch3_mask(X, Y):
        m = 6 * r60 * k
        return (X > l60 + m) & (X < rt60 - m) & (Y < t60 - m) & (Y > b60 + m)
    best3, (X3, Y3, mask3, H3) = register(img3, x03, y03, rs3, d240, l60, t60, r60 * k, (cx, cy), 130000.0, 240.0, ch3_mask, range(0, 360, 15))
    sc = {}
    for s in (0.999, 1.001):
        Ws = hp(sample(img3, x03, y03, rs3, X3 * s, Y3 * s))
        dx, dy, pk = xcorr(Ws, H3, mask3)
        sc[str(s)] = {"residual_m": [dx * 240.0, dy * 240.0], "correlation": pk}
    out["D_chandrayaan3"] = {"distance_from_pole_km": math.hypot(cx, cy) / 1000, "correlation": best3[0], "shift_m": [best3[2], best3[3]], "scale_error_test": sc,
                             "note": "a 0.1 % radial scale error would move this area by about 0.63 km"}

    # ---- E. IM-2 vs the Mons Mouton massif (DEM region above site height - 1500 m)
    sx, sy = lonlat_to_xy(*SITES["im2-athena"])
    ii, jj = int((sx - dleft) // dres), int((dtop - sy) // dres)
    zsite = dem[jj, ii]
    seen = np.zeros(dem.shape, bool)
    q = deque([(jj, ii)])
    seen[jj, ii] = True
    while q:
        r, c = q.popleft()
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            a, b = r + dr, c + dc
            if 0 <= a < dem.shape[0] and 0 <= b < dem.shape[1] and not seen[a, b] and dem[a, b] >= zsite - 1500:
                seen[a, b] = True
                q.append((a, b))
    edge = seen & ~(np.roll(seen, 1, 0) & np.roll(seen, -1, 0) & np.roll(seen, 1, 1) & np.roll(seen, -1, 1))
    ey, ex = np.nonzero(edge)
    dd = np.hypot(dleft + (ex + 0.5) * dres - sx, dtop - (ey + 0.5) * dres - sy)
    out["E_im2"] = {"marker_m": [sx, sy], "dem_height_m": float(zsite), "catalogue_height_m": 5321.0, "massif_area_km2": float(seen.sum() * dres**2 / 1e6),
                    "marker_to_massif_edge_km": float(dd.min() / 1000)}

    path = ROOT / "docs" / "basemap" / "alignment_results.json"
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2))
    print("wrote", path)


if __name__ == "__main__":
    os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
    main()
