import { useState } from "react";
import type { Site } from "../api/types";
import { BASEMAP, levelPixelM, polarLonLat, polarXY, ringRadiusM, tilesFor } from "../polar";

// Map of the catalogue sites around the lunar south pole, drawn on real imagery.
//   * Basemap: NASA Moon Trek WMTS tiles of the LRO LROC WAC south-pole mosaic (ASU/NASA). Context only: no value is read
//     from the imagery and it feeds no calculation (decision C4). It needs no LOLA coverage, only latitude/longitude.
//   * Everything (tiles, rings, markers) is placed in ONE south-polar stereographic grid (see polar.ts, pinned to the engine's
//     own projection by a golden table); the imagery's alignment to that grid was measured, see docs/basemap/BASEMAP_ALIGNMENT.md.
//   * If the tiles cannot be loaded the map falls back to the plain ring schematic. Orientation: 0°E up, east to the right.

const SIZE = 340;
const C = SIZE / 2;
const R = 158; // pixels from the pole to the edge of the disc
const EXTENT_M = 1_000_000; // the disc shows 1000 km around the pole (the 60°S parallel is at 931 km)
const LEVEL = 2; // 2.1 km/pixel tiles: 16 requests cover the disc and are already finer than the screen
const RINGS = [-85, -80, -70, -60]; // southern latitudes, as polarXY and ringRadiusM expect

const px = (m: number) => (m / EXTENT_M) * R;
const KM_PER_PX = EXTENT_M / R / 1000; // map scale: how far one screen pixel is on the Moon
// A click is only good to about half a pixel; round the coordinates to 0.01 deg (about 300 m) so the form does not show false precision.
const round2 = (v: number) => Math.round(v * 100) / 100;
const short = (s: Site) => s.name.split(" (")[0].replace(" landing site", "").replace(" intended", " target");

const halo = { paintOrder: "stroke", stroke: "var(--surface)", strokeWidth: 3, strokeLinejoin: "round" } as const;

/** Screen position of a latitude/longitude (marker pinned to the rim, flagged, if it lies outside the disc). */
function place(lat: number, lon: number): { x: number; y: number; off: boolean } | null {
  const p = polarXY(lat, lon);
  if (!p) return null;
  const rho = Math.hypot(p.x, p.y);
  const k = rho > EXTENT_M * 0.96 ? (EXTENT_M * 0.96) / rho : 1;
  return { x: C + px(p.x * k), y: C - px(p.y * k), off: k < 1 };
}

export function SiteMap({
  sites,
  selectedId,
  custom,
  onSelect,
  onPick,
}: {
  sites: Site[];
  selectedId: string | null;
  custom: { lat: number; lon: number } | null;
  onSelect: (id: string) => void;
  /** If given, clicking the map (not a site marker) reports the clicked latitude/longitude (planetocentric, east positive). */
  onPick?: (lat: number, lon: number) => void;
}) {
  const [showImagery, setShowImagery] = useState(true);
  const [showRings, setShowRings] = useState(true);
  const [failed, setFailed] = useState(0);
  const [hover, setHover] = useState<{ lat: number; lon: number } | null>(null);
  const [pickNote, setPickNote] = useState<string | null>(null);

  /** Pointer position -> grid metres -> latitude/longitude, or null outside the imagery disc. */
  const locate = (e: { clientX: number; clientY: number; currentTarget: SVGSVGElement }) => {
    const box = e.currentTarget.getBoundingClientRect();
    if (!box.width || !box.height) return null;
    const sx = ((e.clientX - box.left) / box.width) * SIZE;
    const sy = ((e.clientY - box.top) / box.height) * SIZE;
    const xM = ((sx - C) / R) * EXTENT_M;
    const yM = ((C - sy) / R) * EXTENT_M; // screen y grows downward; grid y grows "up" (0°E at the top)
    if (Math.hypot(xM, yM) > EXTENT_M) return null;
    return polarLonLat(xM, yM);
  };
  const tiles = tilesFor(LEVEL, EXTENT_M);
  const placed = new Map<string, number>();
  const cp = custom ? place(custom.lat, custom.lon) : null;
  return (
    <figure style={{ margin: 0 }}>
      <svg
        className="plot"
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        role="group"
        aria-label={`Map of catalogue sites around the lunar south pole on LRO imagery: select a site with Enter or Space, or use the Catalogue site list${onPick ? "; click the map to set custom coordinates, or type them in the fields" : ""}`}
        style={onPick ? { cursor: "crosshair" } : undefined}
        data-testid="site-map"
        onMouseMove={onPick ? (e) => setHover(locate(e)) : undefined}
        onMouseLeave={onPick ? () => setHover(null) : undefined}
        onClick={
          onPick
            ? (e) => {
                const p = locate(e);
                if (!p) {
                  setPickNote("That point is outside the map (north of about 58°S); click inside the map or type coordinates.");
                  return;
                }
                setPickNote(null);
                onPick(round2(p.lat), round2(p.lon));
              }
            : undefined
        }
      >
        <defs>
          <clipPath id="basemap-disc"><circle cx={C} cy={C} r={R} /></clipPath>
        </defs>
        <circle cx={C} cy={C} r={R} fill="var(--bg)" stroke="var(--border)" />
        {showImagery && (
          <g clipPath="url(#basemap-disc)" data-testid="basemap" aria-hidden="true">
            {tiles.map((t) => (
              <image
                key={`${t.z}/${t.row}/${t.col}`}
                href={t.url}
                x={C + px(t.leftM)}
                y={C - px(t.topM)}
                width={px(t.spanM) + 0.6}
                height={px(t.spanM) + 0.6}
                preserveAspectRatio="none"
                opacity={0.9}
                onError={() => setFailed((n) => n + 1)}
              />
            ))}
          </g>
        )}
        {showRings && (
          <g data-testid="map-rings">
            {RINGS.map((lat) => (
              <g key={lat}>
                <circle cx={C} cy={C} r={px(ringRadiusM(lat))} fill="none" stroke="#000" strokeOpacity={0.55} strokeWidth={2.2} />
                <circle cx={C} cy={C} r={px(ringRadiusM(lat))} fill="none" stroke="#fff" strokeOpacity={0.9} strokeWidth={0.9} strokeDasharray="3 2" data-ring={lat} />
                <text x={C - px(ringRadiusM(lat)) * 0.7071 - 2} y={C + px(ringRadiusM(lat)) * 0.7071 + 9} textAnchor="end" fontSize="9" fontWeight={600} style={halo}>{-lat}°S</text>
              </g>
            ))}
            <path d={`M${C},${C - R} V${C + R} M${C - R},${C} H${C + R}`} stroke="#000" strokeOpacity={0.45} strokeWidth={2} />
            <path d={`M${C},${C - R} V${C + R} M${C - R},${C} H${C + R}`} stroke="#fff" strokeOpacity={0.6} strokeWidth={0.7} />
          </g>
        )}
        <text x={C} y={C - R - 5} textAnchor="middle" className="muted" fontSize="9">0°E</text>
        <text x={C + R + 3} y={C + 3} textAnchor="start" className="muted" fontSize="9">90°E</text>
        <text x={C} y={C + R + 12} textAnchor="middle" className="muted" fontSize="9">180°</text>
        <text x={C - R - 3} y={C + 3} textAnchor="end" className="muted" fontSize="9">90°W</text>
        <circle cx={C} cy={C} r={2} fill="var(--text)" stroke="var(--surface)" />
        {sites.map((s) => {
          const p = place(s.lat_deg, s.lon_deg_east);
          if (!p) return null;
          const key = `${Math.round(p.x / 6)}:${Math.round(p.y / 6)}`;
          const n = placed.get(key) ?? 0;
          placed.set(key, n + 1);
          const sel = s.id === selectedId;
          return (
            <g
              key={s.id}
              role="button"
              tabIndex={0}
              aria-label={`Select ${s.name}`}
              aria-pressed={sel}
              data-site={s.id}
              style={{ cursor: "pointer" }}
              onClick={(e) => {
                e.stopPropagation(); // choosing a catalogue site is not a map pick
                setPickNote(null);
                onSelect(s.id);
              }}
              onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onSelect(s.id)}
            >
              <circle cx={p.x} cy={p.y} r={sel ? 6 : 4.5} fill={sel ? "var(--accent)" : "var(--surface)"} stroke={sel ? "var(--surface)" : "var(--accent)"} strokeWidth={2} data-marker={s.id} />
              <text x={p.x > C + 40 ? p.x - 9 : p.x + 9} y={p.y + 3 + n * 11} textAnchor={p.x > C + 40 ? "end" : "start"} fontSize="10" fontWeight={sel ? 700 : 500} style={halo}>
                {short(s)}
              </text>
            </g>
          );
        })}
        {custom && cp && (
          <g aria-label="Custom coordinates" data-testid="custom-marker">
            <path d={`M${cp.x - 6},${cp.y} h12 M${cp.x},${cp.y - 6} v12`} stroke="var(--bad)" strokeWidth={2.5} />
            <text x={cp.x + 8} y={cp.y - 6} fontSize="10" style={halo}>{cp.off ? "custom (beyond map edge)" : "custom"}</text>
          </g>
        )}
      </svg>
      <div className="row" style={{ marginTop: 4 }}>
        <label style={{ color: "var(--text)", fontSize: "0.8rem", margin: 0 }}>
          <input type="checkbox" checked={showImagery} onChange={(e) => setShowImagery(e.target.checked)} /> Lunar imagery
        </label>
        <label style={{ color: "var(--text)", fontSize: "0.8rem", margin: 0 }}>
          <input type="checkbox" checked={showRings} onChange={(e) => setShowRings(e.target.checked)} /> Parallel rings
        </label>
      </div>
      {onPick && (
        <p className="help" data-testid="pick-help">
          Click the map to set custom coordinates (the map resolves about ±{(KM_PER_PX / 2).toFixed(1)} km, far coarser than the ±100 m position uncertainty; type exact values for precision).
          Terrain data exist only around IM-1, IM-2 and Chandrayaan-3; elsewhere the backend normally reports “terrain data insufficient”.
        </p>
      )}
      {onPick && (
        // A line of fixed height: showing the pointer position must never change the page layout (a layout shift under the cursor
        // would move the map during a click).
        <p className="help" style={{ height: "1.3em", margin: "2px 0 0", overflow: "hidden", whiteSpace: "nowrap" }}>
          {hover ? <span data-testid="pointer-readout">Pointer: {hover.lat.toFixed(1)}°, {hover.lon.toFixed(1)}°E</span> : " "}
        </p>
      )}
      {pickNote && <p className="help" role="status" data-testid="pick-note"><span className="assump">Not picked:</span> {pickNote}</p>}
      {showImagery && failed > 0 && (
        <p className="help" role="status" data-testid="basemap-failed">
          <span className="assump">Imagery unavailable:</span> {failed} map tile(s) could not be loaded from NASA Moon Trek (offline or blocked?). The rings and sites are still correct.
        </p>
      )}
      <figcaption className="help">
        {showImagery && (
          <>
            Imagery: <a href={BASEMAP.homepage} target="_blank" rel="noreferrer">{BASEMAP.credit}</a>, shown at about {(levelPixelM(LEVEL) / 1000).toFixed(1)} km/pixel from NASA Moon Trek. It is context only; no calculation uses it.{" "}
          </>
        )}
        Imagery, rings and sites share one south-polar stereographic grid (0°E up, east to the right). Sites are the catalogue coordinates; Artemis III candidate regions are not shown because no primary-source coordinates exist yet.
      </figcaption>
    </figure>
  );
}
