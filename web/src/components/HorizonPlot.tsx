import type { BodySeries, HorizonResponse } from "../api/types";

// Terrain horizon (azimuth vs elevation) with the Sun and Earth paths over the chosen window and their positions
// at the selected time. Everything plotted is a number returned by the backend (decision C4).

const W = 1000;
const H = 300;
const M = { l: 46, r: 10, t: 12, b: 30 };

export interface NowPoint {
  az: number;
  el: number;
  rho: number;
}

function niceStep(span: number): number {
  for (const s of [0.5, 1, 2, 5, 10, 20]) if (span / s <= 8) return s;
  return 30;
}

export function HorizonPlot({
  profile,
  tracks,
  now,
}: {
  profile: HorizonResponse;
  tracks?: { sun?: BodySeries; earth?: BodySeries };
  now?: { sun?: NowPoint; earth?: NowPoint };
}) {
  const hs = profile.horizon_elevation_deg.filter((v): v is number => v !== null);
  const trackEls = [tracks?.sun?.elevation_deg, tracks?.earth?.elevation_deg].flatMap((a) => a ?? []);
  const nowEls = [now?.sun?.el, now?.earth?.el].filter((v): v is number => v !== undefined);
  const all = [...hs, ...trackEls, ...nowEls];
  let lo = Math.floor(Math.min(...all, 0) - 0.5);
  let hi = Math.ceil(Math.max(...all, 0) + 0.5);
  if (hi - lo < 3) hi = lo + 3;
  const step = niceStep(hi - lo);
  lo = Math.floor(lo / step) * step;
  hi = Math.ceil(hi / step) * step;
  const x = (az: number) => M.l + (az / 360) * (W - M.l - M.r);
  const y = (el: number) => M.t + (1 - (el - lo) / (hi - lo)) * (H - M.t - M.b);
  const xs = (W - M.l - M.r) / 360;
  const ys = (H - M.t - M.b) / (hi - lo);

  // terrain polygon (broken where the backend has no valid value)
  const segs: string[] = [];
  let cur: string[] = [];
  const flush = () => {
    if (cur.length > 1) {
      const first = cur[0].split(",")[0];
      const last = cur[cur.length - 1].split(",")[0];
      segs.push(`M${first},${y(lo)} L${cur.join(" L")} L${last},${y(lo)} Z`);
    }
    cur = [];
  };
  profile.azimuth_deg.forEach((az, i) => {
    const v = profile.horizon_elevation_deg[i];
    if (v === null) flush();
    else cur.push(`${x(az).toFixed(1)},${y(v).toFixed(1)}`);
  });
  flush();

  // runs of azimuths whose horizon is only a lower bound
  const flagged: [number, number][] = [];
  let start: number | null = null;
  profile.azimuth_deg.forEach((az, i) => {
    const f = profile.truncated[i] || profile.data_gap[i];
    if (f && start === null) start = az;
    if ((!f || i === profile.azimuth_deg.length - 1) && start !== null) {
      flagged.push([start, az]);
      start = null;
    }
  });

  const stride = (n: number) => Math.max(1, Math.ceil(n / 1200));
  const trackDots = (s: BodySeries | undefined, color: string) =>
    s
      ? s.azimuth_deg
          .filter((_, i) => i % stride(s.azimuth_deg.length) === 0)
          .map((az, k) => {
            const i = k * stride(s.azimuth_deg.length);
            return <circle key={i} cx={x(az)} cy={y(s.elevation_deg[i])} r={1.4} fill={color} opacity={0.45} />;
          })
      : null;

  const ticks: number[] = [];
  for (let t = lo; t <= hi + 1e-9; t += step) ticks.push(t);
  const dot = (p: NowPoint | undefined, color: string, label: string) =>
    p ? (
      <g>
        <ellipse cx={x(p.az)} cy={y(p.el)} rx={Math.max(4, p.rho * xs)} ry={Math.max(4, p.rho * ys)} fill={color} stroke="var(--text)" strokeWidth={1.5} opacity={0.95} />
        <text x={p.az > 300 ? x(p.az) - 8 : x(p.az) + 8} textAnchor={p.az > 300 ? "end" : "start"} y={y(p.el) - 7} fontSize="11" fontWeight={700}>{label}</text>
      </g>
    ) : null;

  return (
    <figure style={{ margin: 0 }}>
      <svg className="plot" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Terrain horizon profile with Sun and Earth paths">
        {ticks.map((t) => (
          <g key={t}>
            <line x1={M.l} x2={W - M.r} y1={y(t)} y2={y(t)} className="axis" strokeDasharray={t === 0 ? "5 4" : undefined} opacity={t === 0 ? 1 : 0.5} />
            <text x={M.l - 6} y={y(t) + 4} textAnchor="end" className="muted">{t}°</text>
          </g>
        ))}
        {[0, 45, 90, 135, 180, 225, 270, 315, 360].map((a) => (
          <g key={a}>
            <line x1={x(a)} x2={x(a)} y1={M.t} y2={H - M.b} className="axis" opacity={0.35} />
            <text x={x(a)} y={H - M.b + 14} textAnchor="middle" className="muted">
              {a === 0 || a === 360 ? "N" : a === 90 ? "E" : a === 180 ? "S" : a === 270 ? "W" : `${a}°`}
            </text>
          </g>
        ))}
        {segs.map((d, i) => <path key={i} d={d} fill="var(--terrain)" opacity={0.75} />)}
        {flagged.map(([a, b], i) => (
          <rect key={i} x={x(a)} y={H - M.b - 5} width={Math.max(2, x(b) - x(a))} height={5} fill="var(--bad)">
            <title>Horizon here is a lower bound (terrain data truncated or missing)</title>
          </rect>
        ))}
        {trackDots(tracks?.sun, "var(--sun)")}
        {trackDots(tracks?.earth, "var(--earth)")}
        {dot(now?.sun, "var(--sun)", "Sun")}
        {dot(now?.earth, "var(--earth)", "Earth")}
        <text x={M.l} y={H - 2} className="muted">azimuth, clockwise from local north</text>
        <text x={W - M.r} y={H - 2} textAnchor="end" className="muted">elevation above the local horizontal (dashed = 0°)</text>
      </svg>
      <div className="legend">
        <span><i style={{ background: "var(--terrain)" }} />terrain horizon (DEM)</span>
        <span><i style={{ background: "var(--sun)" }} />Sun path over the window</span>
        <span><i style={{ background: "var(--earth)" }} />Earth path over the window</span>
        {flagged.length > 0 && <span><i style={{ background: "var(--bad)" }} />horizon is only a lower bound here</span>}
      </div>
    </figure>
  );
}
