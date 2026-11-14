import type { IntervalMetrics, VisibilityBody } from "../api/types";
import { DASH, fmtBand, fmtDur, fmtPct, fmtUtc } from "../format";

// Metrics for one body: terrain-corrected (with the position band) beside geometric. Numbers come from the backend.

const BODY_NAME = { sun: "Sun", earth: "Earth" } as const;

function Cell({ nominal, band, flag }: { nominal: string; band?: string | null; flag?: string | null }) {
  return (
    <td className="num">
      {nominal}
      {flag ? <span className="flag" title="The interval touches the edge of the window, so its true length is at least this value">{flag}</span> : null}
      {band ? <span className="band">band {band}</span> : null}
    </td>
  );
}

export function MetricsPanel({
  name,
  body,
  bandM,
  sensStatus,
}: {
  name: "sun" | "earth";
  body: VisibilityBody;
  bandM: number | null;
  sensStatus: string;
}) {
  const head = body.headline!;
  const geo = body.geometric!;
  const m = head.metrics;
  const g: IntervalMetrics = geo.metrics;
  const ps = head.position_sensitivity;
  const mb = ps.status === "computed" ? ps.metric_bands : undefined;
  const notComputed = ps.status !== "computed";
  const b = (key: string, f: (v: number) => string) => (mb && mb[key] ? fmtBand(mb[key], f) : notComputed ? "not computed" : null);
  const headState = body.headline_state.replace("_visible", "");
  const events = body.states![headState as "centre" | "any_part"].transitions;
  const bands = ps.status === "computed" ? (ps.boundary_bands ?? []) : [];
  const colour = name === "sun" ? "sun-c" : "earth-c";

  return (
    <div className="card" data-testid={`metrics-${name}`}>
      <h3 className={colour}>
        {BODY_NAME[name]} — headline: {body.headline_state.replaceAll("_", " ")}
      </h3>
      {body.completeness.visibility_is_upper_bound && (
        <p className="error" role="alert">Some “visible” steps have an incomplete horizon: those results are upper bounds.</p>
      )}
      <div className="scroll">
        <table>
          <thead>
            <tr>
              <th>Metric</th>
              <th className="num">Terrain-corrected</th>
              <th className="num">Geometric (no terrain)</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Visible fraction</td>
              <Cell nominal={fmtPct(m.visible_fraction)} band={b("visible_fraction", (v) => fmtPct(v))} />
              <Cell nominal={fmtPct(g.visible_fraction)} />
            </tr>
            <tr>
              <td>Total visible time</td>
              <Cell nominal={fmtDur(m.total_visible_s)} band={b("total_visible_s", fmtDur)} />
              <Cell nominal={fmtDur(g.total_visible_s)} />
            </tr>
            <tr>
              <td>Visible intervals</td>
              <Cell nominal={String(m.n_visible_intervals)} band={b("n_visible_intervals", (v) => String(v))} />
              <Cell nominal={String(g.n_visible_intervals)} />
            </tr>
            <tr>
              <td>Longest visible</td>
              <Cell nominal={fmtDur(m.longest_visible_s_including_open)} flag={m.longest_visible_includes_open_interval ? "cut off" : null} band={b("longest_visible_s_including_open", fmtDur)} />
              <Cell nominal={fmtDur(g.longest_visible_s_including_open)} flag={g.longest_visible_includes_open_interval ? "cut off" : null} />
            </tr>
            <tr>
              <td>Longest not visible</td>
              <Cell nominal={fmtDur(m.longest_not_visible_s_including_open)} flag={m.longest_not_visible_includes_open_interval ? "cut off" : null} band={b("longest_not_visible_s_including_open", fmtDur)} />
              <Cell nominal={fmtDur(g.longest_not_visible_s_including_open)} flag={g.longest_not_visible_includes_open_interval ? "cut off" : null} />
            </tr>
          </tbody>
        </table>
      </div>
      <p className="help">
        Terrain removed {body.terrain_effect.steps_blocked_by_terrain_only} of {body.terrain_effect.geometric_headline_steps} geometrically-visible steps.
        {bandM !== null && sensStatus === "computed" ? ` “band” = range if the landing position is wrong by ±${bandM} m (a sensitivity, not an error bar on the physics).` : ""}
        {" "}“cut off” = the interval touches the window edge: its true length is at least the value shown.
      </p>

      <h3>Events (boundaries)</h3>
      {events.length === 0 ? (
        <p className="help">No visibility change inside this window.</p>
      ) : (
        <div className="scroll">
          <table>
            <thead>
              <tr>
                <th>Event</th>
                <th>Nominal time</th>
                <th>Position band (earliest – latest)</th>
              </tr>
            </thead>
            <tbody>
              {events.map((e, i) => {
                const bd = bands[i];
                return (
                  <tr key={e.time_s}>
                    <td>{e.to === "visible" ? "becomes visible" : "becomes not visible"}</td>
                    <td>{fmtUtc(e.time_utc)}</td>
                    <td>
                      {bd ? (
                        <>
                          {fmtUtc(bd.earliest_utc)} – {fmtUtc(bd.latest_utc)} <span className="band">width {fmtDur(bd.band_width_s)}</span>
                          {!bd.band_complete && <span className="flag" title="In some displaced runs this event does not exist">incomplete</span>}
                        </>
                      ) : (
                        <span className="muted-text">{notComputed ? "not computed" : DASH}</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {ps.status === "computed" && (ps.events_only_in_displaced_runs ?? 0) > 0 && (
        <p className="help assump">{ps.events_only_in_displaced_runs} further event(s) appear only at displaced positions.</p>
      )}

      <h3>Three disc states</h3>
      <table>
        <thead><tr><th>State</th><th className="num">Visible fraction</th></tr></thead>
        <tbody>
          {(["centre", "any_part", "fully"] as const).map((s) => (
            <tr key={s}>
              <td>{s.replace("_", " ")} visible{s === headState ? <span className="flag good">headline</span> : null}</td>
              <td className="num">{fmtPct(body.states![s].metrics.visible_fraction)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
