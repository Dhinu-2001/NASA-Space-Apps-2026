import { useState } from "react";
import { api } from "../api/client";
import type { CompareResponse, ScenarioResult } from "../api/types";
import { DASH, fmtBand, fmtDur, fmtPct, fmtUtc, localInputToUtc } from "../format";
import { useAsync } from "../hooks";
import { ErrorBox, Loading, Panel, StatusTag } from "../ui";
import type { Site } from "../api/types";

const HINT = "Each new site/date computes terrain profiles and position-sensitivity runs; a comparison of several scenarios can take a minute or more the first time.";

function BandedPct({ b }: { b: { nominal: number | null; band: [number | null, number | null] } }) {
  return (
    <>
      {fmtPct(b.nominal)}
      <span className="band">band {fmtBand(b.band, (v) => fmtPct(v))}</span>
    </>
  );
}

function ScenarioRow({ s }: { s: ScenarioResult }) {
  const label = s.spec.label ?? s.id.slice(0, 8);
  if (s.status !== "supported" || !s.bodies) {
    return (
      <tr data-testid="row-insufficient">
        <td>{label}</td>
        <td colSpan={7}>
          <strong>Terrain data insufficient</strong> — not compared, ranked or estimated.
          <span className="band" style={{ color: "var(--muted)" }}>{s.reason}</span>
        </td>
      </tr>
    );
  }
  const { sun, earth } = s.bodies;
  return (
    <tr data-testid="row-supported">
      <td>{label}<span className="band">{s.spec.duration_days} d from {fmtUtc(s.spec.start_utc)}</span></td>
      <td className="num"><BandedPct b={sun.terrain_corrected.visible_fraction} /></td>
      <td className="num">{fmtPct(sun.geometric.visible_fraction.nominal)}</td>
      <td className="num"><BandedPct b={earth.terrain_corrected.visible_fraction} /></td>
      <td className="num">{fmtPct(earth.geometric.visible_fraction.nominal)}</td>
      <td className="num">
        {fmtDur(sun.terrain_corrected.longest_not_visible_s.including_open)}
        {sun.terrain_corrected.longest_not_visible_s.includes_open_interval && <span className="flag">cut off</span>}
        <span className="band">band {fmtBand(sun.terrain_corrected.longest_not_visible_s.band_including_open ?? null, fmtDur)}</span>
      </td>
      <td className="num">
        {fmtDur(earth.terrain_corrected.longest_not_visible_s.including_open)}
        {earth.terrain_corrected.longest_not_visible_s.includes_open_interval && <span className="flag">cut off</span>}
        <span className="band">band {fmtBand(earth.terrain_corrected.longest_not_visible_s.band_including_open ?? null, fmtDur)}</span>
      </td>
    </tr>
  );
}

export function CompareResult({ data }: { data: CompareResponse }) {
  const label = (id: string) => data.scenarios.find((s) => s.id === id)?.spec.label ?? id.slice(0, 8);
  return (
    <>
      <div className="scroll">
        <table>
          <thead>
            <tr>
              <th>Scenario</th>
              <th className="num">Sun visible (terrain-corrected)</th>
              <th className="num">Sun (geometric)</th>
              <th className="num">Earth visible (terrain-corrected)</th>
              <th className="num">Earth (geometric)</th>
              <th className="num">Longest Sun darkness</th>
              <th className="num">Longest Earth blackout</th>
            </tr>
          </thead>
          <tbody>
            {data.scenarios.map((s) => <ScenarioRow key={s.id} s={s} />)}
          </tbody>
        </table>
      </div>
      <p className="help">
        “band” = how far the result could move for the assumed landing-position error. Fractions are the robust headline; event times and longest intervals carry their band. “cut off” = the interval touches the window edge, so the value is a lower bound.
      </p>

      {data.excluded_terrain_data_insufficient.length > 0 && (
        <div className="insufficient" data-testid="excluded-list">
          <strong>Not compared: terrain data insufficient</strong>
          <ul className="plain">
            {[...new Map(data.excluded_terrain_data_insufficient.map((e) => [e.site_id ?? e.label, e])).values()].map((e) => (
              <li key={e.scenario_id}>{e.site_id ?? e.label}: {e.reason}</li>
            ))}
          </ul>
          <p>These sites have no figures, no rank and no estimate in this comparison.</p>
        </div>
      )}

      <h3>Differences from the baseline ({label(data.baseline_id)})</h3>
      {data.deltas_vs_baseline.length === 0 ? (
        <p className="help">{data.notes.join(" ") || "No other supported scenario to compare."}</p>
      ) : (
        data.deltas_vs_baseline.map((d) => (
          <details key={d.scenario_id} open>
            <summary>
              <strong>{label(d.scenario_id)}</strong>{" "}
              <span className="flag good">{d.delta_band_method === "paired" ? "same site: paired band" : "different site: independent bands"}</span>
            </summary>
            {(["sun", "earth"] as const).map((b) => (
              <div key={b}>
                <ul className="sentences">
                  {d.bodies[b].summary.map((t) => (
                    <li key={t}>{t}{t.includes("NOT distinguishable") ? <span className="flag">within position uncertainty</span> : null}</li>
                  ))}
                </ul>
                <p className="help">
                  Geometric (no terrain), {b}: visible fraction {d.bodies[b].geometric.visible_fraction.delta === null ? DASH : `${(d.bodies[b].geometric.visible_fraction.delta! * 100).toFixed(2)} percentage points`}.
                </p>
              </div>
            ))}
          </details>
        ))
      )}

      {data.rankings.length > 0 && (
        <>
          <h3>Rankings (supported scenarios only)</h3>
          <div className="cards">
            {data.rankings.map((r) => (
              <div className="card" key={r.criterion}>
                <strong>{r.criterion.replaceAll("_", " ")}</strong> <span className="muted-text">({r.better} is better)</span>
                <table>
                  <tbody>
                    {r.ranking.map((x) => (
                      <tr key={x.scenario_id}>
                        <td>{x.rank}</td>
                        <td>{x.label ?? x.site_id}</td>
                        <td className="num">
                          {r.criterion.includes("fraction") ? fmtPct(x.nominal) : fmtDur(x.nominal)}
                          {x.includes_open_interval && <span className="flag">cut off</span>}
                          <span className="band">band {fmtBand(x.band, r.criterion.includes("fraction") ? (v) => fmtPct(v) : fmtDur)}</span>
                        </td>
                        <td>{x.distinguishable_from_next === null ? "" : x.distinguishable_from_next ? <span className="flag good">clearly ahead of next</span> : <span className="flag">not distinguishable from next</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </div>
          <p className="help">{data.rankings[0].method}</p>
        </>
      )}
      <details>
        <summary>How to read this comparison</summary>
        <ul className="plain">{data.reading_guide.map((g) => <li key={g}>{g}</li>)}{data.notes.map((n) => <li key={n}>{n}</li>)}</ul>
      </details>
    </>
  );
}

export function CompareTab({ sites }: { sites: Site[] }) {
  const [chosen, setChosen] = useState<string[]>(["im2-athena", "im2-intended", "im1-odysseus", "chandrayaan3-shiv-shakti"]);
  const [dates, setDates] = useState<string[]>(["2027-01-15T00:00", "2027-03-15T00:00"]);
  const [duration, setDuration] = useState("30");
  const [band, setBand] = useState("100");
  const [baseSite, setBaseSite] = useState(0);
  const [baseDate, setBaseDate] = useState(0);
  const [err, setErr] = useState<string | null>(null);
  const [applied, setApplied] = useState<{ sites: string[]; dates: string[]; duration: number; band: number; baseline: number } | null>(null);

  const run = () => {
    const d = Number(duration);
    const b = Number(band);
    if (chosen.length === 0) return setErr("Select at least one site.");
    if (dates.length === 0 || dates.some((x) => !x)) return setErr("Enter at least one start date (UTC).");
    if (chosen.length * dates.length > 12) return setErr("At most 12 scenarios (sites × dates) per comparison.");
    if (!Number.isFinite(d) || d <= 0 || d > 60) return setErr("Duration must be between 0 and 60 days.");
    if (!Number.isFinite(b) || b <= 0) return setErr("Position uncertainty must be above 0 m.");
    setErr(null);
    setApplied({ sites: chosen, dates: dates.map(localInputToUtc), duration: d, band: b, baseline: Math.min(baseSite, chosen.length - 1) * dates.length + Math.min(baseDate, dates.length - 1) });
  };

  const state = useAsync(
    applied ? (s) => api.compare(applied.sites.map((id) => ({ site_id: id })), applied.dates, { duration_days: applied.duration, position_uncertainty_m: applied.band }, applied.baseline, s) : null,
    applied ? JSON.stringify(applied) : null,
  );

  return (
    <div className="layout">
      <Panel title="Scenarios to compare">
        <p className="help">Sites × start dates. Only sites whose terrain data support a position-sensitivity figure are compared; others are shown as “terrain data insufficient”.</p>
        <fieldset style={{ border: "none", padding: 0, margin: 0 }}>
          <legend className="help">Sites</legend>
          {sites.map((s) => (
            <label key={s.id} style={{ color: "var(--text)", fontSize: "0.9rem" }}>
              <input type="checkbox" checked={chosen.includes(s.id)} onChange={(e) => setChosen(e.target.checked ? [...chosen, s.id] : chosen.filter((x) => x !== s.id))} /> {s.name}
            </label>
          ))}
        </fieldset>
        <label>Start dates (UTC)</label>
        {dates.map((d, i) => (
          <div className="row" key={i}>
            <input type="datetime-local" aria-label={`Start date ${i + 1}`} value={d} min="2025-01-01T00:00" max="2035-12-31T23:59" onChange={(e) => setDates(dates.map((x, j) => (j === i ? e.target.value : x)))} />
            <button className="btn secondary" style={{ flex: "0 0 auto" }} onClick={() => setDates(dates.filter((_, j) => j !== i))} disabled={dates.length === 1} aria-label={`Remove date ${i + 1}`}>Remove</button>
          </div>
        ))}
        <button className="btn secondary" onClick={() => setDates([...dates, "2027-02-15T00:00"])} disabled={dates.length >= 6}>Add date</button>
        <div className="row">
          <div>
            <label htmlFor="cdur">Window length (days)</label>
            <input id="cdur" value={duration} onChange={(e) => setDuration(e.target.value)} />
          </div>
          <div>
            <label htmlFor="cband">Position uncertainty (m)</label>
            <input id="cband" value={band} onChange={(e) => setBand(e.target.value)} />
          </div>
        </div>
        <div className="row">
          <div>
            <label htmlFor="bsite">Baseline site</label>
            <select id="bsite" value={baseSite} onChange={(e) => setBaseSite(Number(e.target.value))}>
              {chosen.map((id, i) => <option key={id} value={i}>{sites.find((s) => s.id === id)?.name ?? id}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="bdate">Baseline date</label>
            <select id="bdate" value={baseDate} onChange={(e) => setBaseDate(Number(e.target.value))}>
              {dates.map((d, i) => <option key={i} value={i}>{d.replace("T", " ")} UTC</option>)}
            </select>
          </div>
        </div>
        <p className="help">Default observer height 2.0 m is an <span className="assump">assumption</span>.</p>
        {err && <p className="error" role="alert">{err}</p>}
        <button className="btn" onClick={run}>Compare</button>
      </Panel>

      <Panel title="Comparison" tags={<><StatusTag cap="scenarios" /><StatusTag cap="visibility" /></>}>
        {!applied && <p>Choose scenarios and press <strong>Compare</strong>.</p>}
        {state.phase === "loading" && <Loading startedAt={state.startedAt} label="Comparing scenarios" hint={HINT} />}
        {state.phase === "error" && <ErrorBox error={state.error} what="Comparison" />}
        {state.phase === "ready" && <CompareResult data={state.data} />}
      </Panel>
    </div>
  );
}
