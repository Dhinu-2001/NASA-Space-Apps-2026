import type { BodySeries } from "../api/types";

// Body elevation vs the terrain horizon at the body's azimuth, over the window. The shaded band around the
// horizon is the backend's position sensitivity (max horizon change at that azimuth for the assumed position error).

const W = 1000;
const H = 190;
const M = { l: 46, r: 12, t: 10, b: 26 };

export function ElevationChart({
  series,
  windowS,
  color,
  label,
  cursorS,
  bandM,
}: {
  series: BodySeries;
  windowS: number;
  color: string;
  label: string;
  cursorS?: number | null;
  bandM: number | null;
}) {
  const sens = series.position_sensitivity_deg;
  const upper = series.terrain_horizon_at_centre_deg.map((h, i) => h + (sens ? sens[i] : 0));
  const lower = series.terrain_horizon_at_centre_deg.map((h, i) => h - (sens ? sens[i] : 0));
  const all = [...series.elevation_deg, ...upper, ...lower, 0];
  const lo = Math.floor(Math.min(...all) - 0.5);
  const hi = Math.ceil(Math.max(...all) + 0.5);
  const x = (s: number) => M.l + (s / windowS) * (W - M.l - M.r);
  const y = (e: number) => M.t + (1 - (e - lo) / (hi - lo)) * (H - M.t - M.b);
  const line = (vals: number[]) => vals.map((v, i) => `${x(series.times_s[i]).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const bandPoly = sens
    ? `${upper.map((v, i) => `${x(series.times_s[i]).toFixed(1)},${y(v).toFixed(1)}`).join(" ")} ${[...lower]
        .map((v, i) => `${x(series.times_s[i]).toFixed(1)},${y(v).toFixed(1)}`)
        .reverse()
        .join(" ")}`
    : null;
  const step = hi - lo > 16 ? 5 : hi - lo > 8 ? 2 : 1;
  const ticks: number[] = [];
  for (let t = Math.ceil(lo / step) * step; t <= hi; t += step) ticks.push(t);
  const dt = series.times_s.length > 1 ? series.times_s[1] - series.times_s[0] : windowS;

  return (
    <figure style={{ margin: 0 }}>
      <svg className="plot" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${label} elevation versus terrain horizon`}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={M.l} x2={W - M.r} y1={y(t)} y2={y(t)} className="axis" opacity={0.5} />
            <text x={M.l - 6} y={y(t) + 4} textAnchor="end" className="muted">{t}°</text>
          </g>
        ))}
        <line x1={M.l} x2={W - M.r} y1={y(0)} y2={y(0)} stroke="var(--muted)" strokeDasharray="5 4" />
        {series.headline_visible.map((v, i) =>
          v ? <rect key={i} x={x(series.times_s[i])} y={H - M.b - 5} width={Math.max(1, x(dt) - x(0))} height={5} fill={color} /> : null,
        )}
        {bandPoly && <polygon points={bandPoly} fill="var(--band)" />}
        <polyline points={line(series.terrain_horizon_at_centre_deg)} fill="none" stroke="var(--terrain)" strokeWidth={1.8} />
        <polyline points={line(series.elevation_deg)} fill="none" stroke={color} strokeWidth={1.8} />
        {cursorS !== null && cursorS !== undefined && (
          <line x1={x(cursorS)} x2={x(cursorS)} y1={M.t} y2={H - M.b} stroke="var(--text)" strokeDasharray="2 2" />
        )}
        <text x={M.l} y={H - 4} className="muted">time over the window</text>
        <text x={W - M.r} y={H - 4} textAnchor="end" className="muted">elevation (°) · dashed = local horizontal</text>
      </svg>
      <div className="legend">
        <span><i style={{ background: color }} />{label} centre elevation</span>
        <span><i style={{ background: "var(--terrain)" }} />terrain horizon at its azimuth</span>
        {bandM !== null && sens && <span><i style={{ background: "var(--band)" }} />horizon change under ±{bandM} m position error</span>}
        <span><i style={{ background: color, height: 4 }} />visible (headline state)</span>
      </div>
    </figure>
  );
}
