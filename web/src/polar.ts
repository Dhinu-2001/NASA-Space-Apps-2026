// Screen layout for the south-polar map: the SAME south-polar stereographic grid as the DEM and the basemap tiles.
//
// This is a mirror of engine/lunarnav/dem.py `lonlat_to_xy` (sphere radius 1,737,400 m, latitude_of_origin = -90,
// central meridian 0, x = rho*sin(lon_east), y = rho*cos(lon_east), rho = 2R*tan((lat+90)/2)). The frontend cannot call
// Python, and no API returns projected coordinates for an arbitrary point without DEM coverage, so the formula is
// repeated here. It is pinned to the engine by a golden table GENERATED from the engine (polarGolden.json) which a
// test on each side keeps equal: tests/engine/test_basemap_projection_golden.py (engine == file) and
// web/src/Basemap.test.tsx (this function == file). It only places things on screen; nothing scientific is derived (C4).

export const SPHERE_RADIUS_M = 1_737_400;

export interface XY {
  x: number; // metres, east-ish (x = rho*sin(lon_east))
  y: number; // metres, "up" on the map (y = rho*cos(lon_east))
}

/** South-polar stereographic metres for a planetocentric latitude (south negative) and east-positive longitude; null if undefined. */
export function polarXY(latDeg: number, lonDeg: number): XY | null {
  if (!Number.isFinite(latDeg) || !Number.isFinite(lonDeg) || latDeg >= 0 || latDeg < -90) return null;
  const rho = 2 * SPHERE_RADIUS_M * Math.tan(((latDeg + 90) * Math.PI) / 360);
  const lon = (lonDeg * Math.PI) / 180;
  return { x: rho * Math.sin(lon), y: rho * Math.cos(lon) };
}

/** Radius of a parallel in the same grid, metres. */
export function ringRadiusM(latDeg: number): number {
  return 2 * SPHERE_RADIUS_M * Math.tan(((latDeg + 90) * Math.PI) / 360);
}

// ---- NASA Moon Trek WMTS (REST) for the LRO LROC WAC south-pole mosaic, v2 ----
// Values from the service's own WMTSCapabilities.xml and ImageServer description (checked 2026-11-15, docs/basemap/):
// CRS = south polar stereographic on the 1,737,400 m sphere (identical to the DEM grid), TopLeftCorner = (-1095930, 1095930) m,
// 256-px tiles, level-0 tile spans 2 x 1095930 m, each further level halves it; tiles exist for levels 0..5.
export const BASEMAP = {
  template: "https://trek.nasa.gov/tiles/Moon/SP/LRO_WAC_Mosaic_SPole60_100m_v02/1.0.0//default/default028mm/{z}/{row}/{col}.png",
  originM: 1_095_930,
  level0SpanM: 2 * 1_095_930,
  maxLevel: 5,
  nativePixelM: 100,
  credit: "LRO LROC WAC mosaic, S Pole v2 (NASA/GSFC/Arizona State University), 100 m/pixel native",
  homepage: "https://trek.nasa.gov/moon/",
} as const;

export interface Tile {
  z: number;
  row: number;
  col: number;
  /** left edge and top edge in grid metres, and the side length */
  leftM: number;
  topM: number;
  spanM: number;
  url: string;
}

/** Every tile of a level that overlaps the square [-halfM, halfM]^2 around the pole (grid metres). */
export function tilesFor(level: number, halfM: number): Tile[] {
  const span = BASEMAP.level0SpanM / 2 ** level;
  const n = 2 ** level;
  const out: Tile[] = [];
  for (let row = 0; row < n; row++) {
    for (let col = 0; col < n; col++) {
      const leftM = -BASEMAP.originM + col * span;
      const topM = BASEMAP.originM - row * span;
      if (leftM + span < -halfM || leftM > halfM || topM - span > halfM || topM < -halfM) continue;
      out.push({ z: level, row, col, leftM, topM, spanM: span, url: BASEMAP.template.replace("{z}", String(level)).replace("{row}", String(row)).replace("{col}", String(col)) });
    }
  }
  return out;
}

/** Metres per pixel of a level (for the credit line only). */
export const levelPixelM = (level: number) => (BASEMAP.level0SpanM / 2 ** level / 256);
