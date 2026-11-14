import type { Site } from "../api/types";

// 2D map of the catalogue sites around the lunar south pole.
// Display-only azimuthal layout (pole at the centre, 0° longitude up, east to the right). It is used for
// orientation and for picking a site; no scientific value is derived from these pixel positions (decision C4).

const SIZE = 320;
const C = SIZE / 2;
const MAX_COLAT = 38; // degrees from the pole shown at the edge
const R = 138;

function xy(lat: number, lon: number): [number, number] {
  const colat = Math.min(90 + lat, MAX_COLAT + 4);
  const r = (colat / MAX_COLAT) * R;
  const a = (lon * Math.PI) / 180;
  return [C + r * Math.sin(a), C - r * Math.cos(a)];
}

const short = (s: Site) => s.name.split(" (")[0].replace(" landing site", "").replace(" intended", " target");

export function SiteMap({
  sites,
  selectedId,
  custom,
  onSelect,
}: {
  sites: Site[];
  selectedId: string | null;
  custom: { lat: number; lon: number } | null;
  onSelect: (id: string) => void;
}) {
  const placed = new Map<string, number>();
  return (
    <figure style={{ margin: 0 }}>
      <svg className="plot" viewBox={`0 0 ${SIZE} ${SIZE}`} role="group" aria-label="Map of catalogue sites around the lunar south pole: select a site with Enter or Space, or use the Catalogue site list">
        {[10, 20, 30].map((d) => (
          <g key={d}>
            <circle cx={C} cy={C} r={(d / MAX_COLAT) * R} fill="none" className="axis" />
            <text x={C + 3} y={C - (d / MAX_COLAT) * R - 2} className="muted" fontSize="9">
              {90 - d}°S
            </text>
          </g>
        ))}
        <line x1={C} y1={C - R} x2={C} y2={C + R} className="axis" />
        <line x1={C - R} y1={C} x2={C + R} y2={C} className="axis" />
        <text x={C - 4} y={C - R - 4} className="muted" fontSize="9">0°E</text>
        <text x={SIZE - 2} y={C - 4} className="muted" fontSize="9" textAnchor="end">90°E</text>
        <text x={C - 12} y={C + R + 11} className="muted" fontSize="9">180°</text>
        <text x={C - R - 2} y={C - 4} className="muted" fontSize="9" textAnchor="start">90°W</text>
        <circle cx={C} cy={C} r={2} fill="currentColor" />
        {sites.map((s) => {
          const [x, y] = xy(s.lat_deg, s.lon_deg_east);
          const key = `${Math.round(x / 6)}:${Math.round(y / 6)}`;
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
              style={{ cursor: "pointer" }}
              onClick={() => onSelect(s.id)}
              onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onSelect(s.id)}
            >
              <circle cx={x} cy={y} r={sel ? 7 : 5} fill={sel ? "var(--accent)" : "var(--surface)"} stroke="var(--accent)" strokeWidth={2} />
              <text x={x + 9} y={y + 3 + n * 11} fontSize="10" fontWeight={sel ? 700 : 400}>
                {short(s)}
              </text>
            </g>
          );
        })}
        {custom && (
          <g aria-label="Custom coordinates">
            <path d={`M${xy(custom.lat, custom.lon)[0] - 6},${xy(custom.lat, custom.lon)[1]} h12 M${xy(custom.lat, custom.lon)[0]},${xy(custom.lat, custom.lon)[1] - 6} v12`} stroke="var(--bad)" strokeWidth={2} />
            <text x={xy(custom.lat, custom.lon)[0] + 8} y={xy(custom.lat, custom.lon)[1] - 6} fontSize="10">custom</text>
          </g>
        )}
      </svg>
      <figcaption className="help">
        Orientation map only (latitude rings from the pole; east to the right). Sites come from the cited catalogue; Artemis III candidate regions are not shown because no primary-source coordinates exist yet.
      </figcaption>
    </figure>
  );
}
