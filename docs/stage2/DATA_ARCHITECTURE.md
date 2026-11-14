# Stage 2 — Data Architecture

No database, no large files in Git (decisions C5, G1).

```
data/
  catalogue/sites.json        TRACKED  curated sites + per-record sources + pending regions
  manifests/
    dem_products.json         TRACKED  product-level facts, verification evidence, limitations
    dem_windows.json          TRACKED  one entry per extracted window (extent, pixel, CRS WKT, SHA-256, stats)
    kernels.json              TRACKED  kernel URL, size, MD5 (authoritative), SHA-256, coverage, version
  dem_cache/*.tif             IGNORED  extracted LOLA windows (regenerate: scripts/extract_dem_window.py)
  kernels/*                   IGNORED  NAIF kernels            (regenerate: scripts/fetch_kernels.py)
  results/                    IGNORED  reserved for cached scenario results (Stage 6)
```

## Conventions
| Topic | Rule |
|---|---|
| Window id | `<site>_<pixel>_r<half-width>` e.g. `im2_20m_r10km`; one GeoTIFF per window, name = id |
| Window file | float32, NaN NoData, deflate, product CRS and grid; tags carry source URL and product id |
| Grid alignment | window edges lie on the product's pixel grid (origin -304000 m) so overview and full-resolution pixels are comparable (tested) |
| Integrity | `DemWindow.load` re-hashes the file against the manifest SHA-256 on first use; mismatch or missing file raises `DATA_MISSING`, never a fallback |
| Provenance in results | `ElevationResult` carries `window_id`, `product_id`, `pixel_size_m`, `source_url`, `sha256`, `method`, `data_class` |
| Data class | DEM values are `measured_interpolated` (LOLA altimetry, gridded) |

## Lookup and failure behaviour
1. Validate (lat, lon) -> normalised east-positive longitude. Invalid -> `INVALID_INPUT` with the field.
2. Project to the south-polar grid. Northern latitudes -> `OUT_OF_DEM_COVERAGE` (the projection is undefined there).
3. Choose covering windows (>= 1 pixel inside the edge), **finest pixel first**. None -> `OUT_OF_DEM_COVERAGE` with the list of known windows.
4. Bilinear interpolation between four pixel centres. Within half a pixel of the edge -> `OUT_OF_DEM_COVERAGE`. Any NaN neighbour -> `DATA_MISSING`.
5. **No fallback:** if the finest window has NoData the error is raised; a coarser window is used only if the caller names it with `window_id`. Terrain is never replaced by 0 or flat ground.

## Reproducibility notes (decision S5)
- Manifest checksums are of the exact GeoTIFF bytes. A different GDAL version could write different bytes from identical pixel values; if a fresh extraction changes the SHA, the manifest is regenerated and the diff reviewed. A pixel-array hash (`data_sha256`) for platform-independent checks is a follow-up item, not yet implemented.
- Everything needed to rebuild `data/` from NASA/NAIF is scripted: `fetch_kernels.py`, `inspect_kernels.py`, `extract_dem_window.py`, `verify_dem_product.py`.

## API surface added in Stage 2
`GET /sites`, `POST /sites/validate`, `GET /dem/windows`, `GET /dem/elevation?lat&lon[&window_id]` (see [API_CONTRACT.md](../API_CONTRACT.md)).
