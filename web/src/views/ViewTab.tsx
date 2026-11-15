import { useEffect, useMemo, useState } from "react";
import { api, ApiError, type SiteSel } from "../api/client";
import type { Site, VisibilityResponse } from "../api/types";
import { AdvancedPlots } from "../components/AdvancedPlots";
import { ElevationChart } from "../components/ElevationChart";
import { HorizonPlot, type NowPoint } from "../components/HorizonPlot";
import { MetricsPanel } from "../components/MetricsPanel";
import { SiteMap } from "../components/SiteMap";
import { SolarPanel } from "../components/SolarPanel";
import { TimePlayer, sampleTimeUtc } from "../components/TimePlayer";
import { Timeline, type TimelineRow } from "../components/Timeline";
import { addSecondsIso, fmtDeg, fmtUtc, localInputToUtc } from "../format";
import { useAsync } from "../hooks";
import { Explain } from "../learn";
import { ProfilePicker } from "../profiles";
import { ErrorBox, Insufficient, Loading, Panel, StatusTag } from "../ui";

interface Applied {
  sel: SiteSel;
  siteLabel: string;
  height: number | null;
  startUtc: string;
  days: number;
  bandM: number;
}

const FIRST_CALL_HINT = "The first calculation for a site computes terrain profiles at several positions and can take about a minute; later requests are cached.";

export function ViewTab({ sites }: { sites: Site[] }) {
  const [siteId, setSiteId] = useState<string>("im2-athena");
  const [useCustom, setUseCustom] = useState(false);
  const [lat, setLat] = useState("-84.79059");
  const [lon, setLon] = useState("29.19567");
  const [heightStr, setHeightStr] = useState("");
  const [startLocal, setStartLocal] = useState("2027-01-15T00:00");
  const [days, setDays] = useState("30");
  const [timeLocal, setTimeLocal] = useState("2027-01-20T12:00");
  const [bandStr, setBandStr] = useState("100");
  const [formError, setFormError] = useState<string | null>(null);
  const [applied, setApplied] = useState<Applied | null>(null);
  const [timeUtc, setTimeUtc] = useState("2027-01-20T12:00:00Z");
  const [scrub, setScrub] = useState<number | null>(null);   // sample index chosen with the time player (null = the chosen time)

  const site = sites.find((s) => s.id === siteId) ?? null;
  const customPoint = useCustom && Number.isFinite(Number(lat)) && Number.isFinite(Number(lon)) ? { lat: Number(lat), lon: Number(lon) } : null;

  const compute = () => {
    const d = Number(days);
    const band = Number(bandStr);
    const h = heightStr.trim() === "" ? null : Number(heightStr);
    if (useCustom && (!Number.isFinite(Number(lat)) || !Number.isFinite(Number(lon)))) return setFormError("Enter numeric latitude and longitude (degrees; south negative, east positive).");
    if (!Number.isFinite(d) || d <= 0 || d > 60) return setFormError("Window length must be between 0 and 60 days.");
    if (!Number.isFinite(band) || band <= 0) return setFormError("Position uncertainty must be a number above 0 metres.");
    if (h !== null && !Number.isFinite(h)) return setFormError("Observer height must be a number of metres (or empty for the 2.0 m default assumption).");
    if (!startLocal || !timeLocal) return setFormError("Choose a window start and a time (UTC).");
    setFormError(null);
    setScrub(null);
    setTimeUtc(localInputToUtc(timeLocal));
    setApplied({
      sel: useCustom ? { lat: Number(lat), lon: Number(lon) } : { site_id: siteId },
      siteLabel: useCustom ? `custom (${Number(lat).toFixed(4)}°, ${Number(lon).toFixed(4)}°E)` : (site?.name ?? siteId),
      height: h,
      startUtc: localInputToUtc(startLocal),
      days: d,
      bandM: band,
    });
  };

  // Show the default scenario straight away (not in unit tests, which drive the form explicitly).
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (import.meta.env.MODE === "test") return;
    compute();
    const n = Number(new URLSearchParams(window.location.search).get("scrub"));
    if (Number.isInteger(n) && n >= 0) setScrub(n);   // demo deep link: ?scrub=<sample index>
  }, []);

  const key = applied ? JSON.stringify(applied) : null;
  const horizon = useAsync(applied ? (s) => api.horizon(applied.sel, applied.height, s) : null, key);
  const series = useAsync(
    applied
      ? (s) =>
          api.visibilitySeries(
            applied.sel,
            applied.startUtc,
            addSecondsIso(applied.startUtc, applied.days * 86400),
            applied.days > 30 ? 3600 : 900,
            applied.height,
            applied.bandM,
            s,
          )
      : null,
    key,
  );
  const eph = useAsync(applied ? (s) => api.ephemerisPosition(applied.sel, timeUtc, s) : null, key ? `${key}|${timeUtc}` : null);
  const at = useAsync(applied ? (s) => api.visibilityAt(applied.sel, timeUtc, applied.height, applied.bandM, s) : null, key ? `${key}|${timeUtc}` : null);

  const atData = at.phase === "ready" ? at.data : null;
  const vis: VisibilityResponse | null = series.phase === "ready" ? series.data : null;
  const insufficientFromError = (e: Error) => e instanceof ApiError && e.body?.code === "OUT_OF_DEM_COVERAGE";
  const insufficient =
    (vis && vis.position_sensitivity.status === "not_computed") ||
    (series.phase === "error" && insufficientFromError(series.error));
  const insufficientReason =
    vis?.position_sensitivity.reason ?? (series.phase === "error" ? series.error.message : undefined);

  const windowS = applied ? applied.days * 86400 : 0;
  const cursorS = applied ? (Date.parse(timeUtc) - Date.parse(applied.startUtc)) / 1000 : null;
  const cursorIn = cursorS !== null && cursorS >= 0 && cursorS <= windowS ? cursorS : null;

  const nowPoints = useMemo(() => {
    const out: { sun?: NowPoint; earth?: NowPoint } = {};
    if (at.phase === "ready") {
      for (const b of ["sun", "earth"] as const) {
        const s = at.data.bodies[b].series;
        if (s) out[b] = { az: s.azimuth_deg[0], el: s.elevation_deg[0], rho: s.angular_radius_deg[0] };
      }
    } else if (eph.phase === "ready") {
      for (const b of ["sun", "earth"] as const) {
        const e = eph.data.bodies[b];
        if (e) out[b] = { az: e.azimuth_deg[0], el: e.elevation_deg[0], rho: e.angular_diameter_deg[0] / 2 };
      }
    }
    return out;
  }, [at, eph]);

  // While the player is used, the markers/cursors show the scrubbed backend sample (no extra API call, no interpolation).
  const scrubNow = useMemo(() => {
    if (scrub === null || !vis) return null;
    const out: { sun?: NowPoint; earth?: NowPoint } = {};
    for (const b of ["sun", "earth"] as const) {
      const s = vis.bodies[b]?.series;
      if (s && scrub < s.times_s.length) out[b] = { az: s.azimuth_deg[scrub], el: s.elevation_deg[scrub], rho: s.angular_radius_deg[scrub] };
    }
    return out;
  }, [scrub, vis]);
  const nowForPlot = scrubNow ?? nowPoints;
  const scrubSeries = vis?.bodies?.sun?.series ?? vis?.bodies?.earth?.series;
  const scrubS = scrub !== null && scrubSeries && scrub < scrubSeries.times_s.length ? scrubSeries.times_s[scrub] : null;
  const cursorShown = scrubS ?? cursorIn;
  const cardSrc =
    scrub !== null && vis && !insufficient && scrubSeries && scrub < scrubSeries.times_s.length
      ? { data: vis, idx: scrub, t: sampleTimeUtc(vis, scrub) }
      : atData
        ? { data: atData, idx: 0, t: timeUtc }
        : null;

  const rows = (b: "sun" | "earth"): TimelineRow[] => {
    const body = vis!.bodies[b];
    const colour = b === "sun" ? "var(--sun)" : "var(--earth)";
    return [
      { label: `${b === "sun" ? "Sun" : "Earth"} terrain-corrected`, sub: body.headline_state.replaceAll("_", " "), visible: body.headline!.intervals, notVisible: body.headline!.not_visible_intervals, color: colour, withBands: true },
      { label: `${b === "sun" ? "Sun" : "Earth"} geometric`, sub: "no terrain", visible: body.geometric!.intervals, notVisible: body.geometric!.not_visible_intervals, color: colour, withBands: false },
    ];
  };

  const bandM = vis && vis.position_sensitivity.status === "computed" ? vis.position_sensitivity.assumed_position_uncertainty_m : null;

  return (
    <div className="layout">
      <div className="stack">
        <Panel title="1 · Landing location">
          <SiteMap sites={sites} selectedId={useCustom ? null : siteId} custom={customPoint} onSelect={(id) => { setSiteId(id); setUseCustom(false); }} />
          <label htmlFor="site-select">Catalogue site</label>
          <select id="site-select" value={siteId} disabled={useCustom} onChange={(e) => setSiteId(e.target.value)}>
            {sites.map((s) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
          {site && !useCustom && (
            <p className="help">
              {site.lat_deg.toFixed(5)}°, {site.lon_deg_east.toFixed(5)}°E · {site.kind.replaceAll("_", " ")}
              {site.reference_height_m !== undefined && site.reference_height_m !== null ? ` · catalogue height ${site.reference_height_m} m` : ""}
            </p>
          )}
          <label><input type="checkbox" checked={useCustom} onChange={(e) => setUseCustom(e.target.checked)} /> Use custom coordinates</label>
          <div className="row">
            <div>
              <label htmlFor="lat">Latitude (°, planetocentric, south negative)</label>
              <input id="lat" inputMode="decimal" value={lat} disabled={!useCustom} onChange={(e) => setLat(e.target.value)} />
            </div>
            <div>
              <label htmlFor="lon">Longitude (°, east positive)</label>
              <input id="lon" inputMode="decimal" value={lon} disabled={!useCustom} onChange={(e) => setLon(e.target.value)} />
            </div>
          </div>
          <p className="help">Custom points need LOLA terrain coverage; without it the result is labelled “terrain data insufficient”.</p>
        </Panel>

        <Panel title="2 · Date and time">
          <ProfilePicker idPrefix="view-profile" current={{ days, height: heightStr, band: bandStr }} onApply={(v) => { setDays(v.days); setHeightStr(v.height); setBandStr(v.band); }} />
          <label htmlFor="start">Window start (UTC)</label>
          <input id="start" type="datetime-local" value={startLocal} min="2025-01-01T00:00" max="2035-12-31T23:59" onChange={(e) => setStartLocal(e.target.value)} />
          <div className="row">
            <div>
              <label htmlFor="days">Window length (days, ≤ 60)</label>
              <input id="days" inputMode="decimal" value={days} onChange={(e) => setDays(e.target.value)} />
            </div>
            <div>
              <label htmlFor="time">Show positions at (UTC)</label>
              <input id="time" type="datetime-local" value={timeLocal} min="2025-01-01T00:00" max="2035-12-31T23:59" onChange={(e) => setTimeLocal(e.target.value)} />
            </div>
          </div>
          <p className="help">All times are UTC. Validated range 2025-01-01 to 2035-12-31.</p>
          <label htmlFor="height">Observer height above the surface (m)</label>
          <input id="height" inputMode="decimal" placeholder="2.0 (default assumption)" value={heightStr} onChange={(e) => setHeightStr(e.target.value)} />
          <p className="help">{heightStr.trim() === "" ? <span className="assump">Using the 2.0 m default — an assumption.</span> : "User-supplied height."}</p>
          <label htmlFor="band">Assumed landing-position uncertainty (m)</label>
          <input id="band" inputMode="decimal" value={bandStr} onChange={(e) => setBandStr(e.target.value)} />
          <p className="help">Default 100 m. Every result below shows how much it could move for this position error.</p>
          {formError && <p className="error" role="alert">{formError}</p>}
          <button className="btn" onClick={compute}>Compute</button>
        </Panel>
      </div>

      <div className="stack">
        {!applied && (
          <Panel title="Results">
            <p>Choose a site and time on the left, then press <strong>Compute</strong>. Everything shown is calculated by the backend (capability status is shown above and on each panel); this page only displays it.</p>
          </Panel>
        )}

        {applied && (
          <>
            <Panel title={`3 · Sun and Earth at ${fmtUtc(cardSrc ? cardSrc.t : timeUtc)}`} tags={<><StatusTag cap="ephemeris" /><StatusTag cap="visibility" /></>}>
              <p className="help">{applied.siteLabel}{scrub !== null ? " · showing the sample chosen with the time player" : ""}</p>
              <Explain id="sunEarthNow" />
              {at.phase === "loading" && eph.phase !== "ready" && !cardSrc && <Loading startedAt={at.startedAt} label="Calculating positions" hint={FIRST_CALL_HINT} />}
              {at.phase === "error" && eph.phase !== "ready" && !cardSrc && <ErrorBox error={at.error} what="Position calculation" />}
              {(cardSrc || eph.phase === "ready") && (
                <div className="cards">
                  {(["sun", "earth"] as const).map((b) => {
                    const p = nowForPlot[b];
                    const s = cardSrc ? cardSrc.data.bodies[b].series : undefined;
                    const k = cardSrc ? cardSrc.idx : 0;
                    return (
                      <div className="card" key={b} data-testid={`now-${b}`}>
                        <h3 className={b === "sun" ? "sun-c" : "earth-c"}>{b === "sun" ? "Sun" : "Earth"}</h3>
                        {p ? <div className="big">az {fmtDeg(p.az, 1)} · el {fmtDeg(p.el, 2, true)}</div> : null}
                        {s && cardSrc ? (
                          <ul className="plain">
                            <li>Terrain horizon at that azimuth: <strong>{fmtDeg(s.terrain_horizon_at_centre_deg[k], 2, true)}</strong>
                              {s.position_sensitivity_deg ? <span className="band">could change by up to {fmtDeg(s.position_sensitivity_deg[k], 2)} for a ±{cardSrc.data.position_sensitivity.assumed_position_uncertainty_m} m position error</span> : null}</li>
                            <li>Centre {s.centre_visible[k] ? "above" : "below"} the terrain · any part of disc {s.any_part_visible[k] ? "visible" : "blocked"} · whole disc {s.fully_visible[k] ? "visible" : "not fully visible"}</li>
                            <li>Headline ({cardSrc.data.bodies[b].headline_state.replaceAll("_", " ")}): <strong>{s.headline_visible[k] ? "VISIBLE" : "BLOCKED"}</strong>
                              {s.headline_state_robust_to_position && !s.headline_state_robust_to_position[k] ? <span className="flag">changes with position</span> : s.headline_state_robust_to_position ? <span className="flag good">same at all sampled positions</span> : null}
                              {!s.horizon_complete[k] && <span className="flag bad">horizon incomplete: upper bound</span>}
                            </li>
                            <li>Geometric (no terrain): {s.geometric_headline_above_local_horizontal[k] ? "above" : "below"} the local horizontal</li>
                          </ul>
                        ) : (
                          <p className="help">Terrain-corrected state unavailable for this location. The direction is astronomy only (observer on the reference sphere).</p>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </Panel>

            <Panel title="4 · Terrain horizon" tags={<StatusTag cap="horizon" />}>
              {horizon.phase === "loading" && <Loading startedAt={horizon.startedAt} label="Computing terrain horizon" hint={FIRST_CALL_HINT} />}
              {horizon.phase === "error" && (insufficientFromError(horizon.error) ? <Insufficient reason={horizon.error.message} /> : <ErrorBox error={horizon.error} what="Horizon" />)}
              <Explain id="horizon" />
              {vis && !insufficient && <TimePlayer vis={vis} index={scrub} onIndex={setScrub} />}
              {horizon.phase === "ready" && (
                <>
                  <HorizonPlot profile={horizon.data} tracks={vis?.bodies?.sun ? { sun: vis.bodies.sun.series, earth: vis.bodies.earth?.series } : undefined} now={nowForPlot} />
                  <p className="help">
                    Ground height {horizon.data.observer.ground_height_m.toFixed(1)} m (from the DEM) · observer {horizon.data.observer.observer_height_above_surface_m} m above it
                    {horizon.data.observer.observer_height_is_default_assumption ? <span className="assump"> (default assumption)</span> : ""} · {horizon.data.summary.n_truncated ?? 0} azimuths truncated, {horizon.data.summary.n_data_gap ?? 0} with data gaps · DEM: {horizon.data.provenance.windows.map((w) => `${w.pixel_size_m} m`).join(" + ")}
                  </p>
                </>
              )}
            </Panel>

            <Panel title="5 · Sunlight and Earth-visibility windows" tags={<StatusTag cap="visibility" />}>
              {series.phase === "loading" && <Loading startedAt={series.startedAt} label="Computing visibility windows and position sensitivity" hint={FIRST_CALL_HINT} />}
              {series.phase === "error" && (insufficientFromError(series.error) ? null : <ErrorBox error={series.error} what="Visibility" />)}
              {insufficient && <Insufficient reason={insufficientReason} />}
              {vis && !insufficient && (
                <>
                  <Explain id="timelines" />
                  <p className="help">
                    {fmtUtc(vis.window.start_utc)} → {fmtUtc(vis.window.end_utc)} · terrain-corrected bars with the boundary-uncertainty whiskers for a ±{bandM} m position error; geometric (no terrain) beneath. Click a timeline to move the time marker.
                  </p>
                  <Timeline
                    startUtc={vis.window.start_utc}
                    windowS={windowS}
                    rows={[...rows("sun"), ...rows("earth")]}
                    cursorS={cursorShown}
                    onPick={(sec) => {
                      const step = vis.window.step_seconds;
                      setScrub(Math.round(sec / step));
                      setTimeUtc(addSecondsIso(vis.window.start_utc, Math.round(sec / step) * step));
                      setTimeLocal(addSecondsIso(vis.window.start_utc, Math.round(sec / step) * step).replace("Z", "").slice(0, 16));
                    }}
                  />
                  {(["sun", "earth"] as const).map((b) => vis.bodies[b].series && (
                    <div key={b}>
                      <h3 className={b === "sun" ? "sun-c" : "earth-c"}>{b === "sun" ? "Sun" : "Earth"}: elevation vs terrain horizon</h3>
                      <ElevationChart series={vis.bodies[b].series!} windowS={windowS} color={b === "sun" ? "var(--sun)" : "var(--earth)"} label={b === "sun" ? "Sun" : "Earth"} cursorS={cursorShown} bandM={bandM} />
                    </div>
                  ))}
                  <Explain id="bands" />
                  <div className="cards" style={{ marginTop: 12 }}>
                    <MetricsPanel name="sun" body={vis.bodies.sun} bandM={bandM} sensStatus={vis.position_sensitivity.status} />
                    <MetricsPanel name="earth" body={vis.bodies.earth} bandM={bandM} sensStatus={vis.position_sensitivity.status} />
                  </div>
                  <details>
                    <summary>What do these numbers mean?</summary>
                    <ul className="plain">
                      <li><strong>Sun headline</strong>: {vis.definitions.headline.sun}</li>
                      <li><strong>Earth headline</strong>: {vis.definitions.headline.earth}</li>
                      <li>{vis.definitions.disc_model}; {vis.definitions.horizon_interpolation}.</li>
                      {vis.limitations.map((l) => <li key={l}>{l}</li>)}
                      <li>Position band: {vis.position_sensitivity.kind}. {vis.position_sensitivity.limitations}</li>
                    </ul>
                  </details>
                </>
              )}
            </Panel>
            {horizon.phase === "ready" && (
              <Panel title="Advanced plots (display only)" tags={<><StatusTag cap="horizon" /><StatusTag cap="visibility" /></>}>
                <p className="help">Sky chart, horizon detail and a zoomable Sun/Earth elevation chart, drawn from the horizon profile and visibility series already loaded above. Nothing is recalculated and no request is made when you use these controls.</p>
                <AdvancedPlots profile={horizon.data} vis={vis && !insufficient ? vis : null} />
              </Panel>
            )}
            <SolarPanel scenario={{ sel: applied.sel, startUtc: applied.startUtc, days: applied.days, height: applied.height, bandM: applied.bandM }} />
          </>
        )}
      </div>
    </div>
  );
}
