import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { CompareResponse, ScenarioResult, Site } from "../api/types";
import { SweepChart } from "../components/SweepChart";
import { fmtBand, fmtDur, fmtPct, localInputToUtc } from "../format";
import { useAsync } from "../hooks";
import {
  MAX_SWEEP_POINTS, SWEEP_PARAMS, buildScenarios, checkCount, dateRange, linspace, parseDateList, parseNumberList, toCsv,
  valueLabel, type SweepBase, type SweepParam, type SweepValue,
} from "../sweep";
import { ErrorBox, Loading, Panel, StatusTag } from "../ui";
import { CompareResult } from "./CompareTab";

// Parameter sweeps over the existing scenario endpoint. One parameter is varied; every scenario is evaluated by the
// backend (POST /scenarios/compare, explicit `scenarios` list, unchanged) and this page only lays the results out.
// A scenario the backend labels terrain_data_insufficient is a labelled gap: no number, no interpolation across it.

const HINT = "Each scenario that is not already cached computes terrain profiles and position-sensitivity runs (about half a minute for 30 days at 15-minute steps); a sweep of several can take a few minutes the first time.";

const DEFAULT_LIST: Record<SweepParam, string> = {
  start: "2027-01-15, 2027-02-15, 2027-03-15, 2027-04-15",
  length: "7, 14, 29.5, 45, 60",
  band: "20, 50, 100, 200, 500",
  height: "0.5, 2, 5, 10",
  step: "300, 900, 1800, 3600",
};
const DEFAULT_FILL: Record<SweepParam, { from: string; to: string; n: string }> = {
  start: { from: "2027-01-15T00:00", to: "2027-06-15T00:00", n: "6" },
  length: { from: "7", to: "56", n: "8" },
  band: { from: "20", to: "500", n: "6" },
  height: { from: "0", to: "10", n: "6" },
  step: { from: "300", to: "3600", n: "6" },
};

interface Applied {
  base: SweepBase;
  param: SweepParam;
  values: SweepValue[];
  baseline: number;
}

function downloadCsv(name: string, text: string) {
  try {
    const url = URL.createObjectURL(new Blob([text], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    a.click();
    URL.revokeObjectURL(url);
  } catch {
    /* download unavailable in this environment: the table on screen is still complete */
  }
}

function Banded({ b }: { b: { nominal: number | null; band: [number | null, number | null] } }) {
  return (
    <>
      {fmtPct(b.nominal)}
      <span className="band">band {fmtBand(b.band, (v) => fmtPct(v))}</span>
    </>
  );
}

export function SweepResult({ applied, data }: { applied: Applied; data: CompareResponse }) {
  const [zoom, setZoom] = useState(false);
  const { param, values } = applied;
  const [even, setEven] = useState(param !== "start");   // layout only: dates are drawn to scale by default
  const labels = values.map((v) => valueLabel(param, v));
  const positions = values.map((v, i) => (even ? i : param === "start" ? Date.parse(v as string) : (v as number)));
  const scn: ScenarioResult[] = data.scenarios;
  const nInsufficient = scn.filter((s) => s.status !== "supported").length;
  return (
    <>
      <p className="help">
        {applied.base.siteLabel} · varying <strong>{SWEEP_PARAMS.find((p) => p.id === param)!.label.toLowerCase()}</strong> over {values.length} values; all other settings fixed
        ({applied.base.days} d from {applied.base.startUtc.slice(0, 16).replace("T", " ")} UTC, ±{applied.base.bandM} m, step {applied.base.stepS} s, observer height {applied.base.heightM ?? "2.0 (default assumption)"}).
      </p>
      <label style={{ color: "var(--text)", fontSize: "0.85rem" }}>
        <input type="checkbox" checked={zoom} onChange={(e) => setZoom(e.target.checked)} /> Zoom the y-axis to the data (default 0–100 %)
      </label>
      <label style={{ color: "var(--text)", fontSize: "0.85rem" }}>
        <input type="checkbox" checked={even} onChange={(e) => setEven(e.target.checked)} /> Space the points evenly (not to scale along the x-axis)
      </label>
      {nInsufficient === scn.length ? (
        <div className="insufficient" data-testid="sweep-all-insufficient">
          <strong>Terrain data insufficient</strong>
          <p>The backend has no supporting terrain data for any of these scenarios, so there is nothing to plot.</p>
          <p className="reason">{scn[0].reason}</p>
        </div>
      ) : (
        <div className="stack">
          <SweepChart body="sun" color="var(--sun)" title="Sun visible fraction" labels={labels} positions={positions} scenarios={scn} zoom={zoom} />
          <SweepChart body="earth" color="var(--earth)" title="Earth visible fraction" labels={labels} positions={positions} scenarios={scn} zoom={zoom} />
        </div>
      )}
      <div className="scroll">
        <table data-testid="sweep-table">
          <caption className="sr-only">Results for each swept value</caption>
          <thead>
            <tr>
              <th scope="col">{SWEEP_PARAMS.find((p) => p.id === param)!.label}</th>
              <th scope="col" className="num">Sun visible (terrain-corrected)</th>
              <th scope="col" className="num">Sun (geometric)</th>
              <th scope="col" className="num">Earth visible (terrain-corrected)</th>
              <th scope="col" className="num">Earth (geometric)</th>
              <th scope="col" className="num">Longest Sun darkness</th>
              <th scope="col" className="num">Longest Earth blackout</th>
            </tr>
          </thead>
          <tbody>
            {scn.map((s, i) => {
              if (s.status !== "supported" || !s.bodies) {
                return (
                  <tr key={s.id} data-testid="sweep-row-insufficient">
                    <th scope="row">{labels[i]}</th>
                    <td colSpan={6}><strong>Terrain data insufficient</strong> — no figures for this scenario.<span className="band" style={{ color: "var(--muted)" }}>{s.reason}</span></td>
                  </tr>
                );
              }
              const { sun, earth } = s.bodies;
              const longest = (b: typeof sun) => {
                const l = b.terrain_corrected.longest_not_visible_s;
                return l.including_open === null && b.terrain_corrected.visible_fraction.nominal === 1
                  ? <span>none: visible throughout</span>
                  : <>{fmtDur(l.including_open)}{l.includes_open_interval && <span className="flag">cut off</span>}<span className="band">band {fmtBand(l.band_including_open ?? null, fmtDur)}</span></>;
              };
              return (
                <tr key={s.id} data-testid="sweep-row">
                  <th scope="row">{labels[i]}{i === applied.baseline && <span className="flag good">baseline</span>}<span className="band" style={{ color: "var(--muted)" }}>{s.served_from === "disk" ? "from cache" : "computed now"}</span></th>
                  <td className="num"><Banded b={sun.terrain_corrected.visible_fraction} /></td>
                  <td className="num">{fmtPct(sun.geometric.visible_fraction.nominal)}</td>
                  <td className="num"><Banded b={earth.terrain_corrected.visible_fraction} /></td>
                  <td className="num">{fmtPct(earth.geometric.visible_fraction.nominal)}</td>
                  <td className="num">{longest(sun)}</td>
                  <td className="num">{longest(earth)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="help">
        “band” = how far the result could move for the assumed landing-position error (a sensitivity, not an error bar). “cut off” = the period touches the window edge, so the value is a lower bound. {nInsufficient > 0 ? `${nInsufficient} scenario(s) are terrain data insufficient and are neither plotted nor interpolated across.` : ""}
      </p>
      <button className="btn secondary" onClick={() => downloadCsv("lunar-navigator-sweep.csv", toCsv(param, values, scn))}>Download this table (CSV)</button>
      <details>
        <summary>Differences from the baseline, and rankings (the same backend calculation as the Compare tab)</summary>
        <CompareResult data={data} />
      </details>
    </>
  );
}

export function ExploreTab({ sites }: { sites: Site[] }) {
  const [siteId, setSiteId] = useState("im2-athena");
  const [useCustom, setUseCustom] = useState(false);
  const [lat, setLat] = useState("-84.79059");
  const [lon, setLon] = useState("29.19567");
  const [startLocal, setStartLocal] = useState("2027-01-15T00:00");
  const [days, setDays] = useState("30");
  const [byEnd, setByEnd] = useState(false);
  const [endLocal, setEndLocal] = useState("2027-02-14T00:00");
  const [band, setBand] = useState("100");
  const [height, setHeight] = useState("");
  const [step, setStep] = useState("900");
  const [param, setParam] = useState<SweepParam>("band");
  const [listText, setListText] = useState(DEFAULT_LIST.band);
  const [fill, setFill] = useState(DEFAULT_FILL.band);
  const [baseline, setBaseline] = useState(0);
  const [err, setErr] = useState<string | null>(null);
  const [applied, setApplied] = useState<Applied | null>(null);
  const [runId, setRunId] = useState(0); // every press of the run button is a new run, even with unchanged inputs (the backend caches, so a repeat is cheap)

  const parsed = useMemo(() => {
    if (param === "start") return parseDateList(listText);
    return parseNumberList(listText);
  }, [param, listText]);
  const values: SweepValue[] = parsed.ok ? parsed.value : [];
  const preview = parsed.ok ? checkCount(values.length) : parsed.error;

  const choose = (p: SweepParam) => {
    setParam(p);
    setListText(DEFAULT_LIST[p]);
    setFill(DEFAULT_FILL[p]);
    setBaseline(0);
  };

  const doFill = () => {
    const n = Number(fill.n);
    if (!Number.isInteger(n) || n < 2 || n > MAX_SWEEP_POINTS) return setErr(`Number of points must be a whole number from 2 to ${MAX_SWEEP_POINTS}.`);
    if (param === "start") {
      if (!fill.from || !fill.to) return setErr("Enter a first and last date.");
      setListText(dateRange(localInputToUtc(fill.from), localInputToUtc(fill.to), n).map((d) => d.slice(0, 16)).join(", "));
    } else {
      const a = Number(fill.from);
      const b = Number(fill.to);
      if (!Number.isFinite(a) || !Number.isFinite(b)) return setErr("Enter a first and last value (numbers).");
      setListText(linspace(a, b, n).join(", "));
    }
    setErr(null);
    setBaseline(0);
  };

  const run = () => {
    if (!parsed.ok) return setErr(parsed.error);
    const c = checkCount(parsed.value.length);
    if (c) return setErr(c);
    const startUtc = localInputToUtc(startLocal);
    const lengthDays = byEnd ? (Date.parse(localInputToUtc(endLocal)) - Date.parse(startUtc)) / 86400000 : Number(days);
    const b = Number(band);
    const st = Number(step);
    const h = height.trim() === "" ? null : Number(height);
    if (useCustom && (!Number.isFinite(Number(lat)) || !Number.isFinite(Number(lon)))) return setErr("Enter numeric latitude and longitude (degrees; south negative, east positive).");
    if (!startLocal) return setErr("Enter a window start (UTC).");
    if (!Number.isFinite(lengthDays) || lengthDays <= 0) return setErr(byEnd ? "The window end must be after its start." : "Window length must be a positive number of days.");
    if (!Number.isFinite(b) || b <= 0) return setErr("Position uncertainty must be above 0 m.");
    if (!Number.isFinite(st) || st <= 0) return setErr("Sampling step must be a positive number of seconds.");
    if (h !== null && !Number.isFinite(h)) return setErr("Observer height must be a number of metres (or empty for the 2.0 m default assumption).");
    setErr(null);
    const sel = useCustom ? { lat: Number(lat), lon: Number(lon) } : { site_id: siteId };
    setRunId((n) => n + 1);
    setApplied({
      base: { site: sel, siteLabel: useCustom ? `custom (${Number(lat).toFixed(4)}°, ${Number(lon).toFixed(4)}°E)` : (sites.find((s) => s.id === siteId)?.name ?? siteId), startUtc, days: lengthDays, bandM: b, heightM: h, stepS: st },
      param, values: parsed.value, baseline: Math.min(baseline, parsed.value.length - 1),
    });
  };

  // Deep link for demos: ?autorun=1 runs the default sweep on load (never in unit tests).
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (import.meta.env.MODE !== "test" && window.location.search.includes("autorun=1")) run(); }, []);

  const state = useAsync(
    applied ? (s) => api.compareScenarios(buildScenarios(applied.base, applied.param, applied.values), applied.baseline, s) : null,
    applied ? `${JSON.stringify(applied)}#${runId}` : null,
  );
  const meta = SWEEP_PARAMS.find((p) => p.id === param)!;

  return (
    <div className="layout">
      <div className="stack">
        <Panel title="1 · Base scenario">
          <label htmlFor="ex-site">Catalogue site</label>
          <select id="ex-site" value={siteId} disabled={useCustom} onChange={(e) => setSiteId(e.target.value)}>
            {sites.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
          <label><input type="checkbox" checked={useCustom} onChange={(e) => setUseCustom(e.target.checked)} /> Use custom coordinates</label>
          <div className="row">
            <div><label htmlFor="ex-lat">Latitude (°)</label><input id="ex-lat" value={lat} disabled={!useCustom} onChange={(e) => setLat(e.target.value)} /></div>
            <div><label htmlFor="ex-lon">Longitude (° east)</label><input id="ex-lon" value={lon} disabled={!useCustom} onChange={(e) => setLon(e.target.value)} /></div>
          </div>
          <label htmlFor="ex-start">Window start (UTC)</label>
          <input id="ex-start" type="datetime-local" value={startLocal} min="2025-01-01T00:00" max="2035-12-31T23:59" onChange={(e) => setStartLocal(e.target.value)} />
          <label><input type="checkbox" checked={byEnd} onChange={(e) => setByEnd(e.target.checked)} /> Define the window by an end date instead of a length</label>
          {byEnd ? (
            <>
              <label htmlFor="ex-end">Window end (UTC)</label>
              <input id="ex-end" type="datetime-local" value={endLocal} min="2025-01-01T00:00" max="2035-12-31T23:59" onChange={(e) => setEndLocal(e.target.value)} />
            </>
          ) : (
            <>
              <label htmlFor="ex-days">Window length (days, ≤ 60)</label>
              <input id="ex-days" value={days} onChange={(e) => setDays(e.target.value)} />
            </>
          )}
          <div className="row">
            <div><label htmlFor="ex-band">Position uncertainty (m)</label><input id="ex-band" value={band} onChange={(e) => setBand(e.target.value)} /></div>
            <div><label htmlFor="ex-step">Sampling step (s)</label><input id="ex-step" value={step} onChange={(e) => setStep(e.target.value)} /></div>
          </div>
          <label htmlFor="ex-height">Observer height (m)</label>
          <input id="ex-height" placeholder="2.0 (default assumption)" value={height} onChange={(e) => setHeight(e.target.value)} />
          <p className="help">{height.trim() === "" ? <span className="assump">Using the 2.0 m default: an assumption.</span> : "User-supplied height."} The swept parameter below overrides its own setting here.</p>
        </Panel>

        <Panel title="2 · Sweep">
          <label htmlFor="ex-param">Parameter to vary</label>
          <select id="ex-param" value={param} onChange={(e) => choose(e.target.value as SweepParam)}>
            {SWEEP_PARAMS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
          </select>
          <p className="help">{meta.help}</p>
          <label htmlFor="ex-list">Values ({meta.unit}; separated by commas{param === "start" ? "; dates like 2027-01-15 or 2027-01-15T12:00" : ""})</label>
          <input id="ex-list" value={listText} onChange={(e) => setListText(e.target.value)} />
          <p className="help" data-testid="sweep-preview" role="status">
            {preview ? <span className="error" style={{ display: "inline-block" }}>{preview}</span> : <>Will request {values.length} scenarios: {values.map((v) => valueLabel(param, v)).join(" · ")}. Already-cached scenarios return at once.</>}
          </p>
          <fieldset className="profiles">
            <legend>Fill the list evenly</legend>
            <div className="row">
              <div><label htmlFor="ex-from">From</label><input id="ex-from" type={param === "start" ? "datetime-local" : "text"} value={fill.from} onChange={(e) => setFill({ ...fill, from: e.target.value })} /></div>
              <div><label htmlFor="ex-to">To</label><input id="ex-to" type={param === "start" ? "datetime-local" : "text"} value={fill.to} onChange={(e) => setFill({ ...fill, to: e.target.value })} /></div>
              <div><label htmlFor="ex-n">Points (2–{MAX_SWEEP_POINTS})</label><input id="ex-n" value={fill.n} onChange={(e) => setFill({ ...fill, n: e.target.value })} /></div>
            </div>
            <button className="btn secondary" onClick={doFill}>Fill list</button>
          </fieldset>
          <label htmlFor="ex-baseline">Baseline for the differences</label>
          <select id="ex-baseline" value={Math.min(baseline, Math.max(values.length - 1, 0))} onChange={(e) => setBaseline(Number(e.target.value))}>
            {values.map((v, i) => <option key={i} value={i}>{valueLabel(param, v)}</option>)}
          </select>
          {err && <p className="error" role="alert">{err}</p>}
          <button className="btn" onClick={run}>Run sweep</button>
        </Panel>
      </div>

      <Panel title="Sweep results" tags={<><StatusTag cap="scenarios" /><StatusTag cap="visibility" /></>}>
        {!applied && <p>Choose a base scenario and a parameter to vary, then press <strong>Run sweep</strong>. The backend evaluates every scenario in one request; nothing is calculated in the browser.</p>}
        {state.phase === "loading" && <Loading startedAt={state.startedAt} label={`Evaluating ${applied?.values.length ?? ""} scenarios`} hint={HINT} />}
        {state.phase === "error" && <ErrorBox error={state.error} what="Sweep" />}
        {state.phase === "ready" && applied && <SweepResult applied={applied} data={state.data} />}
      </Panel>
    </div>
  );
}
