import { useState } from "react";
import { api } from "../api/client";
import type { DelayBodyRow, DelayResponse, Site } from "../api/types";
import { fmtBand, fmtDur, fmtPct, fmtUtc, localInputToUtc } from "../format";
import { useAsync } from "../hooks";
import { ErrorBox, Insufficient, Loading, Panel, StatusTag } from "../ui";

const HINT = "Each delay is a separate scenario; the first run for a site computes terrain profiles and can take a minute or more.";

/** Bars = terrain-corrected fraction with its position band; diamonds = geometric (no terrain). Backend numbers only. */
function DelayChart({ rows, body, color, label }: { rows: { offset: number; r: DelayBodyRow }[]; body: string; color: string; label: string }) {
  const W = 1000;
  const H = 220;
  const M = { l: 46, r: 12, t: 10, b: 30 };
  const slot = (W - M.l - M.r) / rows.length;
  const y = (f: number) => M.t + (1 - f) * (H - M.t - M.b);
  return (
    <figure style={{ margin: 0 }}>
      <svg className="plot" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${label} visible fraction versus delay`} data-testid={`delay-chart-${body}`}>
        {[0, 0.25, 0.5, 0.75, 1].map((t) => (
          <g key={t}>
            <line x1={M.l} x2={W - M.r} y1={y(t)} y2={y(t)} className="axis" opacity={0.5} />
            <text x={M.l - 6} y={y(t) + 4} textAnchor="end" className="muted">{Math.round(t * 100)}%</text>
          </g>
        ))}
        {rows.map((row, i) => {
          const f = row.r.terrain_corrected_visible_fraction;
          const cx = M.l + slot * (i + 0.5);
          const bw = Math.min(60, slot * 0.5);
          const g = row.r.geometric_visible_fraction;
          return (
            <g key={row.offset}>
              {f.nominal !== null && <rect x={cx - bw / 2} y={y(f.nominal)} width={bw} height={Math.max(1, y(0) - y(f.nominal))} fill={color} opacity={0.85} />}
              {f.band[0] !== null && f.band[1] !== null && (
                <g stroke="var(--text)" strokeWidth={2}>
                  <line x1={cx} x2={cx} y1={y(f.band[0])} y2={y(f.band[1])} />
                  <line x1={cx - 7} x2={cx + 7} y1={y(f.band[0])} y2={y(f.band[0])} />
                  <line x1={cx - 7} x2={cx + 7} y1={y(f.band[1])} y2={y(f.band[1])} />
                </g>
              )}
              {g !== null && <path d={`M${cx + bw / 2 + 8},${y(g) - 6} l6,6 l-6,6 l-6,-6 z`} fill="var(--text)" />}
              <text x={cx} y={H - 12} textAnchor="middle" className="muted">{row.offset === 0 ? "baseline" : `+${row.offset} d`}</text>
            </g>
          );
        })}
      </svg>
      <div className="legend">
        <span><i style={{ background: color }} />terrain-corrected visible fraction</span>
        <span><i style={{ background: "var(--text)", width: 2, height: 12 }} />position-uncertainty band</span>
        <span>◆ geometric (no terrain)</span>
      </div>
    </figure>
  );
}

export function DelayResult({ data }: { data: DelayResponse }) {
  if (data.status !== "supported" || !data.summary_table || !data.delays) {
    return (
      <>
        <Insufficient reason={data.reason} />
        <p className="help">{data.note}</p>
      </>
    );
  }
  const rows = data.summary_table.map((r) => ({ offset: r.offset_days, r }));
  return (
    <>
      {(["sun", "earth"] as const).map((b) => (
        <div key={b}>
          <h3 className={b === "sun" ? "sun-c" : "earth-c"}>{b === "sun" ? "Sun" : "Earth"} — visible fraction vs delay</h3>
          <DelayChart rows={rows.map((x) => ({ offset: x.offset, r: x.r[b] }))} body={b} color={b === "sun" ? "var(--sun)" : "var(--earth)"} label={b} />
        </div>
      ))}
      <div className="scroll">
        <table>
          <thead>
            <tr>
              <th>Delay</th>
              <th>Window starts (UTC)</th>
              <th className="num">Sun (terrain / geometric)</th>
              <th className="num">Earth (terrain / geometric)</th>
              <th className="num">Longest Sun darkness</th>
            </tr>
          </thead>
          <tbody>
            {data.summary_table.map((r) => (
              <tr key={r.offset_days}>
                <td>{r.offset_days === 0 ? "baseline" : `+${r.offset_days} d`}</td>
                <td>{fmtUtc(r.start_utc)}</td>
                {(["sun", "earth"] as const).map((b) => (
                  <td className="num" key={b}>
                    {fmtPct(r[b].terrain_corrected_visible_fraction.nominal)} / {fmtPct(r[b].geometric_visible_fraction)}
                    <span className="band">band {fmtBand(r[b].terrain_corrected_visible_fraction.band, (v) => fmtPct(v))}</span>
                  </td>
                ))}
                <td className="num">
                  {fmtDur(r.sun.terrain_corrected_longest_not_visible_s.nominal)}
                  {r.sun.terrain_corrected_longest_not_visible_s.includes_open_interval && <span className="flag">cut off</span>}
                  <span className="band">band {fmtBand(r.sun.terrain_corrected_longest_not_visible_s.band, fmtDur)}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h3>What each delay changes (with position uncertainty)</h3>
      {data.delays.map((d) => (
        <details key={d.offset_days} open={d.offset_days === data.delays![0].offset_days}>
          <summary>
            <strong>+{d.offset_days} d</strong> <span className="flag good">{d.delta_vs_baseline.delta_band_method === "paired" ? "paired band (same site)" : "independent bands"}</span>
          </summary>
          {(["sun", "earth"] as const).map((b) => (
            <ul className="sentences" key={b}>
              {d.delta_vs_baseline.bodies[b].summary.map((t) => (
                <li key={t}>{t}{t.includes("NOT distinguishable") ? <span className="flag">within position uncertainty</span> : null}</li>
              ))}
            </ul>
          ))}
        </details>
      ))}
      <p className="help">{(data.notes ?? []).join(" ")}</p>
    </>
  );
}

export function DelayTab({ sites }: { sites: Site[] }) {
  const [siteId, setSiteId] = useState("im2-athena");
  const [start, setStart] = useState("2027-01-15T00:00");
  const [offsets, setOffsets] = useState("1, 3, 7, 14");
  const [duration, setDuration] = useState("14");
  const [band, setBand] = useState("100");
  const [err, setErr] = useState<string | null>(null);
  const [applied, setApplied] = useState<{ site: string; start: string; offsets: number[]; duration: number; band: number } | null>(null);

  const run = () => {
    const o = offsets.split(/[ ,;]+/).filter(Boolean).map(Number);
    const d = Number(duration);
    const b = Number(band);
    if (o.length === 0 || o.length > 10 || o.some((x) => !Number.isFinite(x) || x <= 0 || x > 365)) return setErr("Delays: 1 to 10 numbers of days, each above 0 and at most 365.");
    if (new Set(o).size !== o.length) return setErr("Delays must be distinct.");
    if (!Number.isFinite(d) || d <= 0 || d > 60) return setErr("Window length must be between 0 and 60 days.");
    if (!Number.isFinite(b) || b <= 0) return setErr("Position uncertainty must be above 0 m.");
    if (!start) return setErr("Choose the baseline start (UTC).");
    setErr(null);
    setApplied({ site: siteId, start: localInputToUtc(start), offsets: o, duration: d, band: b });
  };

  const state = useAsync(
    applied ? (s) => api.delay({ site_id: applied.site }, applied.start, applied.offsets, { duration_days: applied.duration, position_uncertainty_m: applied.band }, s) : null,
    applied ? JSON.stringify(applied) : null,
  );

  return (
    <div className="layout">
      <Panel title="Mission delay simulator">
        <label htmlFor="dsite">Landing site</label>
        <select id="dsite" value={siteId} onChange={(e) => setSiteId(e.target.value)}>
          {sites.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
        <label htmlFor="dstart">Baseline window start (UTC)</label>
        <input id="dstart" type="datetime-local" value={start} min="2025-01-01T00:00" max="2035-12-31T23:59" onChange={(e) => setStart(e.target.value)} />
        <label htmlFor="doff">Delays to simulate (days, comma-separated)</label>
        <input id="doff" value={offsets} onChange={(e) => setOffsets(e.target.value)} />
        <div className="row">
          <div>
            <label htmlFor="ddur">Window length (days)</label>
            <input id="ddur" value={duration} onChange={(e) => setDuration(e.target.value)} />
          </div>
          <div>
            <label htmlFor="dband">Position uncertainty (m)</label>
            <input id="dband" value={band} onChange={(e) => setBand(e.target.value)} />
          </div>
        </div>
        <p className="help"><span className="assump">Default 14-day window is an assumption</span> (about one lunar day of operations), not a mission requirement; change it to match your operation. A window spanning a whole lunar month (29.5 d) hides short delays because the totals repeat.</p>
        {err && <p className="error" role="alert">{err}</p>}
        <button className="btn" onClick={run}>Simulate delays</button>
      </Panel>
      <Panel title="Effect of delay" tags={<><StatusTag cap="scenarios" /><StatusTag cap="visibility" /></>}>
        {!applied && <p>Choose a site and delays, then press <strong>Simulate delays</strong>.</p>}
        {state.phase === "loading" && <Loading startedAt={state.startedAt} label="Simulating delays" hint={HINT} />}
        {state.phase === "error" && <ErrorBox error={state.error} what="Delay simulation" />}
        {state.phase === "ready" && <DelayResult data={state.data} />}
      </Panel>
    </div>
  );
}
