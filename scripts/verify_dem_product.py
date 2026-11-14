"""Stage 2 measurements on the LOLA 20 m product using only cheap reads (overview 64 + windows).

Prints: overall valid fraction, latitude extent of valid data, and inference of the overview
resampling method (compares an overview pixel with its 16x16 full-resolution block).
"""
import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.env import Env

ROOT = Path(__file__).resolve().parents[1]
URL = "https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/LDEM_80S_20MPP_ADJ.TIF"
R = 1_737_400.0
env = Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".TIF",
          GDAL_HTTP_MAX_RETRY="6", GDAL_HTTP_TIMEOUT="180")
with env, rasterio.open(URL, overview_level=5) as ds:  # factor 64 -> 1280 m
    a = ds.read(1)
    res = ds.res[0]
    ny, nx = a.shape
    yy, xx = np.mgrid[0:ny, 0:nx]
    x = ds.bounds.left + (xx + 0.5) * res
    y = ds.bounds.top - (yy + 0.5) * res
    rho = np.hypot(x, y)
    lat = np.degrees(2 * np.arctan(rho / (2 * R))) - 90
    valid = np.isfinite(a)
    print("overview64 shape", a.shape, "res", res, "valid fraction", round(float(valid.mean()), 4))
    print("lat of valid pixels: max (northernmost)", round(float(lat[valid].max()), 3),
          "min", round(float(lat[valid].min()), 3))
    print("NaN pixels with lat < -80 (inside 80S circle):", int((~valid & (lat < -80)).sum()))
    print("NaN pixels with lat >= -80:", int((~valid & (lat >= -80)).sum()),
          "of", int((lat >= -80).sum()))
    print("z range", float(np.nanmin(a)), float(np.nanmax(a)))

# overview resampling inference using the already-extracted windows
man = json.loads((ROOT / "data/manifests/dem_windows.json").read_text())["windows"]
def load(w):
    with rasterio.open(ROOT / "data" / man[w]["file"]) as d:
        return d.read(1), d.transform
near, tn = load("im2_20m_r10km")
far, tf = load("im2_320m_r160km")
# find a far (320 m) pixel entirely inside the near window
res_f = 320.0
for fr in range(far.shape[0]):
    for fc in range(far.shape[1]):
        x0 = tf.c + fc * res_f; y0 = tf.f - fr * res_f
        c0 = (x0 - tn.c) / 20.0; r0 = (tn.f - y0) / 20.0
        if c0 >= 0 and r0 >= 0 and c0 + 16 <= near.shape[1] and r0 + 16 <= near.shape[0]:
            c0, r0 = round(c0), round(r0)
            blk = near[r0:r0 + 16, c0:c0 + 16]
            ov = far[fr, fc]
            print("overview px", float(ov), "| block mean", float(blk.mean()),
                  "| median", float(np.median(blk)), "| min", float(blk.min()), "max", float(blk.max()),
                  "| top-left", float(blk[0, 0]), "centre[8,8]", float(blk[8, 8]))
            raise SystemExit
print("no aligned pixel found fully inside near window")
