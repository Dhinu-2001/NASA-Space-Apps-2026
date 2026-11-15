import type { ScenarioResult } from "../api/types";

// Visible fraction of one body across the swept values: terrain-corrected nominal with its position band (whisker), and
// the geometric (no terrain) value beside it. Every plotted number is read from the backend response (decision C4).
// A scenario the backend marks terrain_data_insufficient gets a labelled gap, never a point.

const W = 1000;
const H = 240;
const M = { l: 52, r: 14, t: 12, b: 54 };

export function SweepChart({
  body, color, title, labels, positions, scenarios, zoom,
}: {
  body: "sun" | "earth";
  color: string;
  title: string;
  labels: string[];
  positions: number[]; // x position of each value (numeric value, or time for dates): layout only
  scenarios: ScenarioResult[];
  zoom: boolean;
}) {
  const pts = scenarios.map((s, i) => {
    if (s.status !== "supported" || !s.bodies) return { i, ok: false as const };
    const b = s.bodies[body];
    const f = b.terrain_corrected.visible_fraction;
    return { i, ok: true as const, nom: f.nominal, lo: f.band[0], hi: f.band[1], geo: b.geometric.visible_fraction.nominal };
  });
  const have = pts.filter((p): p is Extract<typeof p, { ok: true }> => p.ok);
  const vals = have.flatMap((p) => [p.nom, p.lo, p.hi, p.geo].filter((v): v is number => v !== null));
  let lo = 0;
  let hi = 1;
  if (zoom && vals.length > 0) {
    const mn = Math.min(...vals);
    const mx = Math.max(...vals);
    const pad = Math.max((mx - mn) * 0.15, 0.01);
    lo = Math.max(0, mn - pad);
    hi = Math.min(1, mx + pad);
  }
  const xmin = Math.min(...positions);
  const xmax = Math.max(...positions);
  const x = (v: number) => M.l + (xmax === xmin ? 0.5 : (v - xmin) / (xmax - xmin)) * (W - M.l - M.r);
  const y = (f: number) => M.t + (1 - (f - lo) / (hi - lo)) * (H - M.t - M.b);
  const step = zoom ? (hi - lo > 0.3 ? 0.1 : hi - lo > 0.1 ? 0.05 : 0.01) : 0.25;
  const grid: number[] = [];
  for (let g = Math.ceil(lo / step) * step; g <= hi + 1e-9; g += step) grid.push(Number(g.toFixed(4)));
  const line = have.map((p) => `${x(positions[p.i]).toFixed(1)},${y(p.nom!).toFixed(1)}`).join(" ");

  return (
    <figure style={{ margin: 0 }}>
      <h3 className={body === "sun" ? "sun-c" : "earth-c"} style={{ marginBottom: 2 }}>{title}</h3>
      <svg className="plot" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${title}: terrain-corrected visible fraction with its position band, and the geometric value, for each swept value. The same numbers are in the table below.`}>
        {grid.map((g) => (
          <g key={g}>
            <line x1={M.l} x2={W - M.r} y1={y(g)} y2={y(g)} className="axis" opacity={0.45} />
            <text x={M.l - 6} y={y(g) + 4} textAnchor="end" className="muted">{(g * 100).toFixed(step < 0.05 ? 1 : 0)} %</text>
          </g>
        ))}
        {line && <polyline points={line} fill="none" stroke={color} strokeWidth={1.4} opacity={0.6} />}
        {pts.map((p) => {
          const cx = x(positions[p.i]);
          return (
            <g key={p.i}>
              {p.ok ? (
                <>
                  {p.lo !== null && p.hi !== null && <line x1={cx} x2={cx} y1={y(p.lo)} y2={y(p.hi)} stroke={color} strokeWidth={4} opacity={0.35} />}
                  {p.geo !== null && <path d={`M${cx - 5},${y(p.geo)} l5,-5 l5,5 l-5,5 Z`} fill="none" stroke="var(--text)" strokeWidth={1.5} />}
                  {p.nom !== null && <circle cx={cx} cy={y(p.nom)} r={4.5} fill={color} />}
                </>
              ) : (
                <text x={cx} y={y(lo) - 6} textAnchor="middle" fontWeight={700} fill="var(--warn)">n/a</text>
              )}
              <text x={cx} y={H - M.b + 16} textAnchor="end" transform={`rotate(-28 ${cx} ${H - M.b + 16})`} className="muted">{labels[p.i]}</text>
            </g>
          );
        })}
        <text x={M.l} y={H - 4} className="muted">swept value · {zoom ? "y-axis zoomed to the data" : "y-axis 0–100 %"} · n/a = terrain data insufficient</text>
      </svg>
      <div className="legend">
        <span><i style={{ background: color }} />terrain-corrected (dot) with position band (bar)</span>
        <span><i style={{ background: "transparent", border: "1.5px solid var(--text)", transform: "rotate(45deg)", width: 8, height: 8 }} />geometric (no terrain)</span>
      </div>
    </figure>
  );
}
