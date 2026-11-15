import { useState } from "react";
import type { BodySeries, HorizonResponse, VisibilityResponse } from "../api/types";
import { DASH, addSecondsIso, fmtDeg } from "../format";

// Advanced scientific plots (Stage 10 extras, Tier 1). DISPLAY ONLY (decision C4): every plotted value is an array the
// backend already returned (/horizon/profile and /visibility/series). Nothing here derives astronomy, terrain or
// visibility. The only arithmetic is screen layout: scaling values to pixels and projecting an (azimuth, elevation)
// pair that the backend returned onto the polar canvas (`polarXY`, the one place trigonometry is used, for drawing).

const SUN = "var(--sun)";
const EARTH = "var(--earth)";

// ------------------------------------------------------------------ shared layout helpers

function tickStep(span: number): number {
  for (const s of [1, 2, 5, 10, 15, 30, 45]) if (span / s <= 8) return s;
  return 60;
}

function ticks(lo: number, hi: number, step: number): number[] {
  const out: number[] = [];
  for (let t = Math.ceil(lo / step) * step; t <= hi + 1e-9; t += step) out.push(t);
  return out;
}

const finite = (v: number | null | undefined): v is number => typeof v === "number" && Number.isFinite(v);

// ------------------------------------------------------------------ 1. sky polar plot

const P = { size: 540, c: 270, r: 218 };

/** Screen position of a backend (azimuth, elevation) pair. Sky-chart orientation: looking up, north at the top, east at the left. */
function polarXY(azDeg: number, el: number, lo: number, hi: number): [number, number] {
  const rr = (P.r * (hi - el)) / (hi - lo);
  const a = (azDeg * Math.PI) / 180;
  return [P.c - rr * Math.sin(a), P.c - rr * Math.cos(a)];
}

export function SkyPolarPlot({
  profile, sun, earth, selected,
}: {
  profile: HorizonResponse;
  sun?: BodySeries;
  earth?: BodySeries;
  selected: number;
}) {
  const hs = profile.horizon_elevation_deg.filter(finite);
  const trackEl = [sun?.elevation_deg, earth?.elevation_deg].flatMap((a) => a ?? []);
  const all = [...hs, ...trackEl, 0];
  const hi = Math.ceil(Math.max(...all) + 1);
  const lo = Math.floor(Math.min(...all) - 1);
  const step = tickStep(hi - lo);
  const rings = ticks(lo, hi, step).filter((t) => t < hi);
  const R = (el: number) => (P.r * (hi - el)) / (hi - lo);

  // terrain: the sky BELOW the horizon elevation (outer annulus) is blocked; evenodd = outer circle minus the horizon curve
  const curve = profile.azimuth_deg
    .map((az, i) => ({ az, v: profile.horizon_elevation_deg[i] }))
    .filter((p): p is { az: number; v: number } => finite(p.v))
    .map((p) => polarXY(p.az, p.v, lo, hi).map((n) => n.toFixed(1)).join(","));
  const terrain = curve.length > 2
    ? `M${P.c - P.r},${P.c} a${P.r},${P.r} 0 1,0 ${2 * P.r},0 a${P.r},${P.r} 0 1,0 ${-2 * P.r},0 Z M${curve.join(" L")} Z`
    : null;

  const flagged = profile.azimuth_deg.filter((_, i) => profile.truncated[i] || profile.data_gap[i]);
  const stride = (n: number) => Math.max(1, Math.ceil(n / 900));
  const track = (s: BodySeries | undefined, color: string, label: string) => {
    if (!s) return null;
    const st = stride(s.azimuth_deg.length);
    const idx = s.azimuth_deg.map((_, i) => i).filter((i) => i % st === 0);
    const first = idx[0];
    const last = s.azimuth_deg.length - 1;
    return (
      <g>
        {idx.map((i) => {
          const [x, y] = polarXY(s.azimuth_deg[i], s.elevation_deg[i], lo, hi);
          return s.headline_visible[i]
            ? <circle key={i} cx={x} cy={y} r={2.2} fill={color} />
            : <circle key={i} cx={x} cy={y} r={1.8} fill="none" stroke={color} strokeWidth={0.8} opacity={0.55} />;
        })}
        {[[first, "start"], [last, "end"]].map(([i, w]) => {
          const [x, y] = polarXY(s.azimuth_deg[i as number], s.elevation_deg[i as number], lo, hi);
          return (
            <g key={w as string}>
              <circle cx={x} cy={y} r={6} fill="none" stroke={color} strokeWidth={2} />
              <text x={x + 8} y={y - 6} fontSize="10" fontWeight={700}>{label} {w as string}</text>
            </g>
          );
        })}
      </g>
    );
  };

  const selAz = profile.azimuth_deg[selected];
  const selEl = profile.horizon_elevation_deg[selected];
  const [sx, sy] = finite(selEl) ? polarXY(selAz, selEl, lo, hi) : polarXY(selAz, hi, lo, hi);
  const [ex, ey] = polarXY(selAz, lo, lo, hi);

  return (
    <figure style={{ margin: 0 }}>
      <svg className="plot" viewBox={`0 0 ${P.size} ${P.size}`} style={{ maxWidth: 560, margin: "0 auto" }} role="img"
        aria-label="Sky chart of the terrain horizon with the Sun and Earth tracks over the chosen window, looking up with north at the top and east at the left. Use the azimuth slider for exact values.">
        {terrain && <path d={terrain} fill="var(--terrain)" fillRule="evenodd" opacity={0.75} />}
        {rings.map((t) => (
          <g key={t}>
            <circle cx={P.c} cy={P.c} r={R(t)} fill="none" className="axis" strokeDasharray={t === 0 ? "5 4" : undefined} opacity={t === 0 ? 1 : 0.6} />
            <text x={P.c + 3} y={P.c - R(t) - 2} className="muted" fontSize="10">{t}°</text>
          </g>
        ))}
        {[0, 45, 90, 135, 180, 225, 270, 315].map((a) => {
          const [x1, y1] = polarXY(a, hi, lo, hi);
          const [x2, y2] = polarXY(a, lo, lo, hi);
          const [tx, ty] = polarXY(a, lo - (hi - lo) * 0.075, lo, hi);
          return (
            <g key={a}>
              <line x1={x1} y1={y1} x2={x2} y2={y2} className="axis" opacity={0.35} />
              <text x={tx} y={ty + 4} textAnchor="middle" className="muted">{a === 0 ? "N" : a === 90 ? "E" : a === 180 ? "S" : a === 270 ? "W" : `${a}°`}</text>
            </g>
          );
        })}
        {flagged.map((az) => {
          const [x1, y1] = polarXY(az, lo, lo, hi);
          const [x2, y2] = polarXY(az, lo + (hi - lo) * 0.04, lo, hi);
          return <line key={az} x1={x1} y1={y1} x2={x2} y2={y2} stroke="var(--bad)" strokeWidth={2} />;
        })}
        <line x1={P.c} y1={P.c} x2={ex} y2={ey} stroke="var(--text)" strokeDasharray="2 3" opacity={0.6} />
        {track(sun, SUN, "Sun")}
        {track(earth, EARTH, "Earth")}
        <circle cx={sx} cy={sy} r={4} fill="var(--text)" />
        <text x={P.c} y={P.size - 4} textAnchor="middle" className="muted">centre = highest elevation shown ({hi}°), rim = {lo}° · radial scale is zoomed, not true sky</text>
      </svg>
      <div className="legend">
        <span><i style={{ background: "var(--terrain)" }} />terrain blocks the sky below the horizon curve</span>
        <span><i style={{ background: SUN }} />Sun (filled = headline visible, hollow = not)</span>
        <span><i style={{ background: EARTH }} />Earth (filled = headline visible, hollow = not)</span>
        {flagged.length > 0 && <span><i style={{ background: "var(--bad)" }} />red marks: horizon is a lower bound (data truncated or missing)</span>}
      </div>
    </figure>
  );
}

// ------------------------------------------------------------------ 2. Sun and Earth elevation over time

const T = { w: 1000, h: 316, l: 46, r: 12, t: 10, b: 60 };

export function SunEarthTimeChart({
  sun, earth, startUtc,
}: {
  sun?: BodySeries;
  earth?: BodySeries;
  startUtc: string;
}) {
  const ref = sun ?? earth;
  const n = ref ? ref.times_s.length : 0;
  const [range, setRange] = useState<[number, number] | null>(null);
  const [cursor, setCursor] = useState<number | null>(null);
  if (!ref || n < 2) return <p className="help">No time series available for this scenario.</p>;
  const i0 = range ? Math.min(range[0], n - 2) : 0;
  const i1 = range ? Math.max(range[1], i0 + 1) : n - 1;
  const cur = cursor === null ? Math.round((i0 + i1) / 2) : Math.min(Math.max(cursor, i0), i1);
  const t0 = ref.times_s[i0];
  const t1 = ref.times_s[i1];
  const bodies = [
    { key: "Sun", s: sun, color: SUN, textClass: "sun-c" },
    { key: "Earth", s: earth, color: EARTH, textClass: "earth-c" },
  ].filter((b): b is { key: string; s: BodySeries; color: string; textClass: string } => b.s !== undefined);

  const vals: number[] = [0];
  for (const b of bodies) for (let i = i0; i <= i1; i++) vals.push(b.s.elevation_deg[i], b.s.terrain_horizon_at_centre_deg[i]);
  const lo = Math.floor(Math.min(...vals) - 0.5);
  const hi = Math.ceil(Math.max(...vals) + 0.5);
  const x = (s: number) => T.l + ((s - t0) / (t1 - t0)) * (T.w - T.l - T.r);
  const y = (e: number) => T.t + (1 - (e - lo) / (hi - lo)) * (T.h - T.t - T.b);
  const line = (a: number[], s: BodySeries) =>
    s.times_s.slice(i0, i1 + 1).map((t, k) => `${x(t).toFixed(1)},${y(a[i0 + k]).toFixed(1)}`).join(" ");
  const dt = ref.times_s[1] - ref.times_s[0];

  // day grid: UTC dates at midnight offsets from the window start
  const dayS = 86400;
  const dayTicks: number[] = [];
  const spanDays = (t1 - t0) / dayS;
  const dayStep = spanDays > 40 ? 10 : spanDays > 18 ? 5 : spanDays > 8 ? 2 : 1;
  for (let d = Math.ceil(t0 / dayS / dayStep) * dayStep; d * dayS <= t1; d += dayStep) dayTicks.push(d * dayS);
  const showHours = spanDays <= 2;

  return (
    <figure style={{ margin: 0 }}>
      <svg className="plot" viewBox={`0 0 ${T.w} ${T.h}`} role="img" aria-label="Sun and Earth elevation over time, each against the terrain horizon at its own azimuth, with the visible periods marked. Use the sliders below for exact values.">
        {ticks(lo, hi, tickStep(hi - lo)).map((e) => (
          <g key={e}>
            <line x1={T.l} x2={T.w - T.r} y1={y(e)} y2={y(e)} className="axis" opacity={e === 0 ? 1 : 0.4} strokeDasharray={e === 0 ? "5 4" : undefined} />
            <text x={T.l - 6} y={y(e) + 4} textAnchor="end" className="muted">{e}°</text>
          </g>
        ))}
        {dayTicks.map((s) => (
          <g key={s}>
            <line x1={x(s)} x2={x(s)} y1={T.t} y2={T.h - T.b} className="axis" opacity={0.3} />
            <text x={x(s)} y={T.h - T.b + 14} textAnchor="middle" className="muted">{addSecondsIso(startUtc, s).slice(5, showHours ? 13 : 10).replace("T", " ")}</text>
          </g>
        ))}
        {bodies.map((b, row) => (
          <g key={b.key}>
            {b.s.headline_visible.slice(i0, i1 + 1).map((v, k) => v
              ? <rect key={k} x={x(b.s.times_s[i0 + k])} y={T.h - T.b + 24 + row * 10} width={Math.max(1, x(dt) - x(0))} height={6} fill={b.color} />
              : null)}
            <polyline points={line(b.s.terrain_horizon_at_centre_deg, b.s)} fill="none" stroke={b.color} strokeWidth={1.4} strokeDasharray="4 3" opacity={0.85} />
            <polyline points={line(b.s.elevation_deg, b.s)} fill="none" stroke={b.color} strokeWidth={2} />
          </g>
        ))}
        <line x1={x(ref.times_s[cur])} x2={x(ref.times_s[cur])} y1={T.t} y2={T.h - T.b} stroke="var(--text)" strokeDasharray="2 2" />
        <text x={T.l} y={T.h - 4} className="muted">UTC date (month-day) · bars under the axis: headline visible (Sun above, Earth below)</text>
      </svg>
      <div className="legend">
        {bodies.map((b) => (
          <span key={b.key}><i style={{ background: b.color }} />{b.key} elevation (solid) · terrain horizon at its azimuth (dashed)</span>
        ))}
      </div>
      <div className="row" style={{ marginTop: 8 }}>
        <div>
          <label htmlFor="adv-z0">Zoom: first sample ({addSecondsIso(startUtc, t0).replace("T", " ").replace("Z", " UTC")})</label>
          <input id="adv-z0" type="range" min={0} max={n - 2} value={i0} onChange={(e) => setRange([Number(e.target.value), Math.max(i1, Number(e.target.value) + 1)])} />
        </div>
        <div>
          <label htmlFor="adv-z1">Zoom: last sample ({addSecondsIso(startUtc, t1).replace("T", " ").replace("Z", " UTC")})</label>
          <input id="adv-z1" type="range" min={1} max={n - 1} value={i1} onChange={(e) => setRange([Math.min(i0, Number(e.target.value) - 1), Number(e.target.value)])} />
        </div>
        <button className="btn secondary" style={{ flex: "0 0 auto" }} onClick={() => { setRange(null); setCursor(null); }} disabled={range === null && cursor === null}>Reset zoom</button>
      </div>
      <label htmlFor="adv-cursor">Inspect sample (changes only this chart; the backend is not asked again)</label>
      <input id="adv-cursor" type="range" min={i0} max={i1} value={cur} onChange={(e) => setCursor(Number(e.target.value))} style={{ width: "100%" }} />
      <div className="cards" role="status" aria-live="polite" data-testid="time-readout" style={{ marginTop: 8 }}>
        {bodies.map((b) => (
          <div className="card" key={b.key}>
            <h3 className={b.textClass}>{b.key} · {addSecondsIso(startUtc, b.s.times_s[cur]).replace("T", " ").replace("Z", " UTC")}</h3>
            <div>az {fmtDeg(b.s.azimuth_deg[cur], 1)} · el {fmtDeg(b.s.elevation_deg[cur], 2, true)}</div>
            <div>terrain horizon there {fmtDeg(b.s.terrain_horizon_at_centre_deg[cur], 2, true)} · headline <strong>{b.s.headline_visible[cur] ? "VISIBLE" : "BLOCKED"}</strong>
              {!b.s.horizon_complete[cur] && <span className="flag bad">horizon incomplete: upper bound</span>}</div>
          </div>
        ))}
      </div>
    </figure>
  );
}

// ------------------------------------------------------------------ 3. horizon profile detail

const D = { w: 1000, h: 330, l: 46, r: 12, t: 10, mid: 190, b: 26 };

export function HorizonDetailPlot({ profile, selected }: { profile: HorizonResponse; selected: number }) {
  const az = profile.azimuth_deg;
  const el = profile.horizon_elevation_deg;
  const dist = profile.horizon_distance_km;
  const ev = el.filter(finite);
  const elLo = Math.floor(Math.min(...ev, 0) - 0.5);
  const elHi = Math.ceil(Math.max(...ev, 0) + 0.5);
  const dv = dist.filter(finite);
  const dMax = Math.max(...dv, 1);
  const x = (a: number) => D.l + (a / 360) * (D.w - D.l - D.r);
  const yE = (v: number) => D.t + (1 - (v - elLo) / (elHi - elLo)) * (D.mid - D.t - 14);
  const yD = (v: number) => D.mid + 8 + (1 - v / dMax) * (D.h - D.b - D.mid - 8);
  const segs = (vals: (number | null)[], yf: (v: number) => number, floor: number) => {
    const out: string[] = [];
    let cur: string[] = [];
    const flush = () => {
      if (cur.length > 1) out.push(`M${cur[0].split(",")[0]},${floor} L${cur.join(" L")} L${cur[cur.length - 1].split(",")[0]},${floor} Z`);
      cur = [];
    };
    az.forEach((a, i) => { const v = vals[i]; if (v === null || v === undefined) flush(); else cur.push(`${x(a).toFixed(1)},${yf(v).toFixed(1)}`); });
    flush();
    return out;
  };
  const dStep = tickStep(dMax);
  return (
    <figure style={{ margin: 0 }}>
      <svg className="plot" viewBox={`0 0 ${D.w} ${D.h}`} role="img" aria-label="Terrain horizon elevation by azimuth, and below it the distance to the terrain that sets the horizon at each azimuth. Use the azimuth slider for exact values.">
        {ticks(elLo, elHi, tickStep(elHi - elLo)).map((e) => (
          <g key={e}>
            <line x1={D.l} x2={D.w - D.r} y1={yE(e)} y2={yE(e)} className="axis" opacity={e === 0 ? 1 : 0.4} strokeDasharray={e === 0 ? "5 4" : undefined} />
            <text x={D.l - 6} y={yE(e) + 4} textAnchor="end" className="muted">{e}°</text>
          </g>
        ))}
        {ticks(0, dMax, dStep).map((d) => (
          <g key={d}>
            <line x1={D.l} x2={D.w - D.r} y1={yD(d)} y2={yD(d)} className="axis" opacity={0.4} />
            <text x={D.l - 6} y={yD(d) + 4} textAnchor="end" className="muted">{d} km</text>
          </g>
        ))}
        {[0, 90, 180, 270, 360].map((a) => (
          <g key={a}>
            <line x1={x(a)} x2={x(a)} y1={D.t} y2={D.h - D.b} className="axis" opacity={0.3} />
            <text x={x(a)} y={D.h - D.b + 14} textAnchor="middle" className="muted">{a === 0 || a === 360 ? "N" : a === 90 ? "E" : a === 180 ? "S" : "W"}</text>
          </g>
        ))}
        {segs(el, yE, yE(elLo)).map((d, i) => <path key={`e${i}`} d={d} fill="var(--terrain)" opacity={0.75} />)}
        {segs(dist, yD, yD(0)).map((d, i) => <path key={`d${i}`} d={d} fill="var(--accent)" opacity={0.45} />)}
        {az.map((a, i) => (profile.truncated[i] || profile.data_gap[i])
          ? <rect key={i} x={x(a)} y={D.mid - 5} width={Math.max(2, x(az[1] - az[0]) - x(0))} height={5} fill="var(--bad)"><title>Horizon here is a lower bound (terrain data truncated or missing)</title></rect>
          : null)}
        <line x1={x(az[selected])} x2={x(az[selected])} y1={D.t} y2={D.h - D.b} stroke="var(--text)" strokeDasharray="2 2" />
        <text x={D.l} y={D.h - 2} className="muted">azimuth, clockwise from local north · top: horizon elevation · bottom: distance to the terrain that sets it</text>
      </svg>
      <div className="legend">
        <span><i style={{ background: "var(--terrain)" }} />horizon elevation</span>
        <span><i style={{ background: "var(--accent)" }} />distance to the limiting terrain (km)</span>
      </div>
    </figure>
  );
}

// ------------------------------------------------------------------ wrapper: one azimuth control for the two horizon plots

export function AdvancedPlots({ profile, vis }: { profile: HorizonResponse; vis: VisibilityResponse | null }) {
  const [sel, setSel] = useState(0);
  const i = Math.min(sel, profile.azimuth_deg.length - 1);
  const sun = vis?.bodies?.sun?.series;
  const earth = vis?.bodies?.earth?.series;
  const pix = profile.limiting_pixel_size_m?.[i];
  return (
    <div data-testid="advanced-plots">
      <h3>Sky chart: terrain horizon and body tracks</h3>
      <SkyPolarPlot profile={profile} sun={sun} earth={earth} selected={i} />
      <label htmlFor="adv-az">Azimuth to inspect (°)</label>
      <input id="adv-az" type="range" min={0} max={profile.azimuth_deg.length - 1} value={i} onChange={(e) => setSel(Number(e.target.value))} style={{ width: "100%" }} />
      <p role="status" aria-live="polite" data-testid="az-readout" className="help" style={{ fontSize: "0.85rem", color: "var(--text)" }}>
        Azimuth <strong>{fmtDeg(profile.azimuth_deg[i], 2)}</strong> · horizon elevation <strong>{fmtDeg(profile.horizon_elevation_deg[i], 3, true)}</strong>
        {" "}· limiting terrain {finite(profile.horizon_distance_km[i]) ? `${profile.horizon_distance_km[i]!.toFixed(1)} km away` : DASH}
        {finite(pix) ? ` (${pix} m pixels)` : ""}
        {(profile.truncated[i] || profile.data_gap[i]) ? <span className="flag bad">lower bound: terrain data truncated or missing</span> : <span className="flag good">horizon certified at this azimuth</span>}
      </p>
      <h3>Horizon profile detail</h3>
      <HorizonDetailPlot profile={profile} selected={i} />
      {vis && (sun !== undefined || earth !== undefined) ? (
        <>
          <h3>Sun and Earth elevation over time</h3>
          <SunEarthTimeChart sun={sun} earth={earth} startUtc={vis.window.start_utc} />
        </>
      ) : <p className="help">The time chart needs the visibility series, which is unavailable for this location.</p>}
    </div>
  );
}
