import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { ScenarioResult, Site } from "../api/types";
import { DASH, fmtBand, fmtDeg, fmtDur, fmtPct, fmtUtc, localInputToUtc } from "../format";
import { useAsync } from "../hooks";
import { ErrorBox, Insufficient, Loading, Panel, StatusTag, UnvalidatedTerrainTag } from "../ui";

// Historical landing sites side by side over ONE common window, from a single POST /scenarios/compare.
// Display only (decision C4): every number is read from the backend response; a site the backend marks
// terrain_data_insufficient gets the label and its reason, never a figure, a rank or an estimate.

const HINT = "A site's first calculation computes terrain profiles and position-sensitivity runs; several sites can take a minute or more the first time.";

interface Applied {
  siteIds: string[];
  startUtc: string;
  days: number;
  bandM: number;
}

function Banded({ b, pct = true }: { b: { nominal: number | null; band: [number | null, number | null] }; pct?: boolean }) {
  return (
    <>
      {pct ? fmtPct(b.nominal) : fmtDur(b.nominal)}
      <span className="band">band {fmtBand(b.band, pct ? (v) => fmtPct(v) : fmtDur)}</span>
    </>
  );
}

const INSUFFICIENT_CELL = <em data-testid="cell-insufficient">terrain data insufficient</em>;

/** One column of the side-by-side table. `s` is undefined while the backend response does not contain the site. */
function cells(s: ScenarioResult | undefined) {
  if (!s || s.status !== "supported" || !s.bodies) return null;
  const { sun, earth } = s.bodies;
  const longest = (b: typeof sun) => b.terrain_corrected.longest_not_visible_s.including_open === null && b.terrain_corrected.visible_fraction.nominal === 1 ? (
    <span data-testid="no-gap">none: visible throughout the window</span>   // the backend reports no period without it
  ) : (
    <>
      {fmtDur(b.terrain_corrected.longest_not_visible_s.including_open)}
      {b.terrain_corrected.longest_not_visible_s.includes_open_interval && <span className="flag">cut off</span>}
      <span className="band">band {fmtBand(b.terrain_corrected.longest_not_visible_s.band_including_open ?? null, fmtDur)}</span>
    </>
  );
  const hz = s.horizon?.summary;
  return {
    terrain: (
      <>
        {s.horizon?.windows.length ? s.horizon.windows.join(" + ") : DASH}
        <UnvalidatedTerrainTag limitations={s.limitations} />
      </>
    ),
    horizon: hz ? `${fmtDeg(hz.horizon_min_deg as number | null)} to ${fmtDeg(hz.horizon_max_deg as number | null)}, mean ${fmtDeg(hz.horizon_mean_deg as number | null)}` : DASH,
    ground: s.observer ? `${s.observer.ground_height_m.toFixed(1)} m` : DASH,
    sunTc: <Banded b={sun.terrain_corrected.visible_fraction} />,
    sunGeo: fmtPct(sun.geometric.visible_fraction.nominal),
    earthTc: <Banded b={earth.terrain_corrected.visible_fraction} />,
    earthGeo: fmtPct(earth.geometric.visible_fraction.nominal),
    sunDark: longest(sun),
    earthBlackout: longest(earth),
  };
}

export function SitesResult({ sites, scenarios, windowText }: { sites: Site[]; scenarios: ScenarioResult[]; windowText: string }) {
  const bySite = new Map(scenarios.map((s) => [s.spec.site_id, s]));
  const cols = sites.map((site) => ({ site, scn: bySite.get(site.id) }));
  const body = cols.map((c) => cells(c.scn));
  const rows: { label: string; key: keyof NonNullable<ReturnType<typeof cells>> }[] = [
    { label: "Terrain data used", key: "terrain" },
    { label: "Ground height (DEM)", key: "ground" },
    { label: "Terrain horizon (min to max elevation)", key: "horizon" },
    { label: "Sun visible, terrain-corrected", key: "sunTc" },
    { label: "Sun visible, geometric (no terrain)", key: "sunGeo" },
    { label: "Earth visible, terrain-corrected", key: "earthTc" },
    { label: "Earth visible, geometric (no terrain)", key: "earthGeo" },
    { label: "Longest period without Sun", key: "sunDark" },
    { label: "Longest Earth blackout", key: "earthBlackout" },
  ];
  const insufficient = cols.filter((c) => c.scn && c.scn.status !== "supported");
  return (
    <>
      <p className="help">{windowText}</p>
      <div className="scroll">
        <table data-testid="sites-table">
          <caption className="sr-only">Landing sites compared over the same window</caption>
          <thead>
            <tr>
              <th scope="col">Quantity</th>
              {cols.map(({ site }) => (
                <th scope="col" key={site.id} className="num">
                  {site.name}
                  <span className="band" style={{ color: "var(--muted)" }}>{site.lat_deg.toFixed(4)}°, {site.lon_deg_east.toFixed(4)}°E</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              <th scope="row">Result</th>
              {cols.map(({ site, scn }) => (
                <td key={site.id} className="num" data-testid={`status-${site.id}`}>
                  {!scn ? DASH : scn.status === "supported" ? <span className="flag good">supported</span> : <strong>terrain data insufficient</strong>}
                </td>
              ))}
            </tr>
            {rows.map((r) => (
              <tr key={r.key}>
                <th scope="row">{r.label}</th>
                {cols.map(({ site, scn }, i) => (
                  <td key={site.id} className="num">
                    {!scn ? DASH : body[i] ? body[i]![r.key] : INSUFFICIENT_CELL}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="help">
        “band” = how far the result could move for the assumed landing-position error (a sensitivity, not an error bar). “cut off” = the period touches the window edge, so the value is a lower bound. Every site is evaluated for the same window so the columns are comparable; this is not a replay of each mission’s actual date.
      </p>
      {insufficient.map(({ site, scn }) => (
        <div key={site.id}>
          <h3>{site.name}</h3>
          <Insufficient reason={scn!.reason} />
        </div>
      ))}
      <details>
        <summary>Limitations the backend attached to these results</summary>
        <ul className="plain">
          {[...new Set(scenarios.flatMap((s) => s.limitations ?? []))].map((l) => <li key={l}>{l}</li>)}
        </ul>
      </details>
    </>
  );
}

export function SitesTab({ sites }: { sites: Site[] }) {
  const landing = sites.filter((s) => s.kind === "confirmed_landing");
  const [chosen, setChosen] = useState<string[]>(landing.map((s) => s.id));
  const [startLocal, setStartLocal] = useState("2027-01-15T00:00");
  const [days, setDays] = useState("30");
  const [band, setBand] = useState("100");
  const [err, setErr] = useState<string | null>(null);
  const [applied, setApplied] = useState<Applied | null>(null);
  const [runId, setRunId] = useState(0); // every press of the run button is a new run, even with unchanged inputs (the backend caches, so a repeat is cheap)

  const run = () => {
    const d = Number(days);
    const b = Number(band);
    if (chosen.length === 0) return setErr("Select at least one site.");
    if (!startLocal) return setErr("Enter a start date (UTC).");
    if (!Number.isFinite(d) || d <= 0 || d > 60) return setErr("Duration must be between 0 and 60 days.");
    if (!Number.isFinite(b) || b <= 0) return setErr("Position uncertainty must be above 0 m.");
    setErr(null);
    setRunId((n) => n + 1);
    setApplied({ siteIds: landing.map((s) => s.id).filter((id) => chosen.includes(id)), startUtc: localInputToUtc(startLocal), days: d, bandM: b });
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (import.meta.env.MODE !== "test" && window.location.search.includes("autorun=1")) run(); }, []);

  const state = useAsync(
    applied ? (s) => api.compare(applied.siteIds.map((id) => ({ site_id: id })), [applied.startUtc], { duration_days: applied.days, position_uncertainty_m: applied.bandM }, 0, s) : null,
    applied ? `${JSON.stringify(applied)}#${runId}` : null,
  );

  return (
    <div className="layout">
      <Panel title="Landing sites to compare">
        <p className="help">
          The sites where a lander has touched down and the project holds coordinates for. One window is evaluated for all of them with the same backend scenario calculation used by the Compare tab; a site without sufficient terrain data is labelled, never estimated.
        </p>
        <fieldset style={{ border: "none", padding: 0, margin: 0 }}>
          <legend className="help">Sites</legend>
          {landing.map((s) => (
            <label key={s.id} style={{ color: "var(--text)", fontSize: "0.9rem" }}>
              <input type="checkbox" checked={chosen.includes(s.id)} onChange={(e) => setChosen(e.target.checked ? [...chosen, s.id] : chosen.filter((x) => x !== s.id))} /> {s.name}
            </label>
          ))}
        </fieldset>
        <label htmlFor="sites-start">Window start (UTC)</label>
        <input id="sites-start" type="datetime-local" value={startLocal} min="2025-01-01T00:00" max="2035-12-31T23:59" onChange={(e) => setStartLocal(e.target.value)} />
        <div className="row">
          <div>
            <label htmlFor="sites-days">Window length (days, ≤ 60)</label>
            <input id="sites-days" value={days} onChange={(e) => setDays(e.target.value)} />
          </div>
          <div>
            <label htmlFor="sites-band">Position uncertainty (m)</label>
            <input id="sites-band" value={band} onChange={(e) => setBand(e.target.value)} />
          </div>
        </div>
        <p className="help">Default observer height 2.0 m is an <span className="assump">assumption</span>. Validated range 2025–2035.</p>
        {err && <p className="error" role="alert">{err}</p>}
        <button className="btn" onClick={run}>Compare sites</button>
      </Panel>

      <Panel title="Sites side by side" tags={<><StatusTag cap="scenarios" /><StatusTag cap="visibility" /></>}>
        {!applied && <p>Choose sites and press <strong>Compare sites</strong>.</p>}
        {state.phase === "loading" && <Loading startedAt={state.startedAt} label="Comparing sites" hint={HINT} />}
        {state.phase === "error" && <ErrorBox error={state.error} what="Site comparison" />}
        {state.phase === "ready" && applied && (
          <SitesResult
            sites={landing.filter((s) => applied.siteIds.includes(s.id))}
            scenarios={state.data.scenarios}
            windowText={`${applied.days} days from ${fmtUtc(applied.startUtc)} · ±${applied.bandM} m position uncertainty`}
          />
        )}
      </Panel>
    </div>
  );
}
