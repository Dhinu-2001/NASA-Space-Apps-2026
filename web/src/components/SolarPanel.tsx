import { useEffect, useState } from "react";
import { api, type SiteSel } from "../api/client";
import { fmtBand, fmtEnergy, fmtHours, fmtPower } from "../format";
import { useAsync } from "../hooks";
import { ErrorBox, Insufficient, Loading, Panel, StatusTag } from "../ui";

// Read-only display of the backend's idealised direct-beam solar-energy result for the scenario currently shown.
// The panel parameters are sent to the backend; nothing is multiplied or estimated here (decision C4).

export interface SolarScenario {
  sel: SiteSel;
  startUtc: string;
  days: number;
  height: number | null;
  bandM: number;
}

export function SolarPanel({ scenario }: { scenario: SolarScenario }) {
  const [area, setArea] = useState("");
  const [eff, setEff] = useState("");
  const [irr, setIrr] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [asked, setAsked] = useState<{ key: string; area: number; eff: number; irr: number | null } | null>(null);

  const ask = () => {
    const a = Number(area);
    const e = Number(eff);
    const i = irr.trim() === "" ? null : Number(irr);
    if (area.trim() === "" || !Number.isFinite(a) || a <= 0) return setErr("Enter a panel area above 0 m².");
    if (eff.trim() === "" || !Number.isFinite(e) || e <= 0 || e > 1) return setErr("Enter an efficiency as a fraction between 0 and 1 (e.g. 0.30).");
    if (i !== null && !Number.isFinite(i)) return setErr("Irradiance must be a number in W/m² (or empty for the default assumption).");
    setErr(null);
    setAsked({ key: JSON.stringify([scenario, a, e, i]), area: a, eff: e, irr: i });
  };

  // Demo deep link (?autorun=1): pre-fill the labelled example and ask once. Never in unit tests.
  useEffect(() => {
    if (import.meta.env.MODE !== "test" && window.location.search.includes("autorun=1")) {
      setArea("1");
      setEff("0.30");
      setAsked({ key: JSON.stringify([scenario, 1, 0.3, null]), area: 1, eff: 0.3, irr: null });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const state = useAsync(
    asked
      ? (s) => api.solarEnergy(scenario.sel, scenario.startUtc, scenario.days, scenario.height, scenario.bandM, { area_m2: asked.area, efficiency: asked.eff, irradiance_w_m2: asked.irr }, s)
      : null,
    asked ? asked.key : null,
  );

  return (
    <Panel title="6 · Idealised solar energy (upper bound)" tags={<><StatusTag cap="engineering" /><StatusTag cap="visibility" /></>}>
      <p className="help">
        Direct-beam energy a panel <em>could</em> collect if it faced the Sun whenever any part of the Sun is above the terrain, for the window and position above. It is an
        <strong> upper bound, not a power budget and not battery state</strong>. You must supply the panel: there is no hidden default.
      </p>
      <div className="row">
        <div>
          <label htmlFor="sol-area">Panel area (m²)</label>
          <input id="sol-area" inputMode="decimal" value={area} onChange={(e) => setArea(e.target.value)} />
        </div>
        <div>
          <label htmlFor="sol-eff">Efficiency (fraction, e.g. 0.30)</label>
          <input id="sol-eff" inputMode="decimal" value={eff} onChange={(e) => setEff(e.target.value)} />
        </div>
        <div>
          <label htmlFor="sol-irr">Irradiance (W/m², optional)</label>
          <input id="sol-irr" inputMode="decimal" placeholder="1361 (default assumption)" value={irr} onChange={(e) => setIrr(e.target.value)} />
        </div>
      </div>
      {err && <p className="error" role="alert">{err}</p>}
      <div className="row" style={{ marginTop: 8 }}>
        <button className="btn" onClick={ask} style={{ flex: "0 0 auto" }}>Estimate energy</button>
        <button className="btn secondary" onClick={() => { setArea("1"); setEff("0.30"); }} style={{ flex: "0 0 auto" }}>
          Use example: 1 m², 0.30 (illustrative, not a design)
        </button>
      </div>

      {state.phase === "loading" && <Loading startedAt={state.startedAt} label="Calculating energy" hint="Reuses the cached scenario; a new site/window may take a minute the first time." />}
      {state.phase === "error" && <ErrorBox error={state.error} what="Solar energy" />}
      {state.phase === "ready" && state.data.status !== "supported" && <Insufficient reason={state.data.reason} />}
      {state.phase === "ready" && state.data.status === "supported" && state.data.terrain_corrected && state.data.panel && (
        <SolarResult d={state.data} />
      )}
    </Panel>
  );
}

function SolarResult({ d }: { d: NonNullable<Awaited<ReturnType<typeof api.solarEnergy>>> }) {
  const tc = d.terrain_corrected!;
  const p = d.panel!;
  const dark = tc.longest_without_direct_sunlight;
  const bandM = d.position_sensitivity?.assumed_position_uncertainty_m;
  return (
    <div data-testid="solar-result">
      <p className="insufficient" style={{ borderStyle: "solid" }}>
        <strong>{d.kind}</strong>
      </p>
      <div className="scroll">
        <table>
          <thead>
            <tr><th>Quantity (whole window, {tc.headline_state.replaceAll("_", " ")})</th><th className="num">Terrain-corrected</th><th className="num">Geometric (no terrain)</th></tr>
          </thead>
          <tbody>
            <tr>
              <td>Energy</td>
              <td className="num">{fmtEnergy(tc.energy_wh.nominal)}<span className="band">band {fmtBand(tc.energy_wh.band, fmtEnergy)}</span></td>
              <td className="num">{fmtEnergy(d.geometric!.energy_wh)}</td>
            </tr>
            <tr>
              <td>Mean power over the window</td>
              <td className="num">{fmtPower(tc.mean_power_w.nominal)}<span className="band">band {fmtBand(tc.mean_power_w.band, fmtPower)}</span></td>
              <td className="num">{fmtPower(d.geometric!.mean_power_w)}</td>
            </tr>
            <tr>
              <td>Illuminated time</td>
              <td className="num">{fmtHours(tc.sunlit_hours.nominal)}<span className="band">band {fmtBand(tc.sunlit_hours.band, fmtHours)}</span></td>
              <td className="num">{fmtHours(d.geometric!.sunlit_hours)}</td>
            </tr>
            <tr>
              <td>Longest period without direct sunlight (no energy)</td>
              <td className="num">
                {fmtHours(dark.hours)}
                {dark.includes_open_interval && <span className="flag" title={dark.note}>cut off</span>}
                <span className="band">band {fmtBand(dark.band_hours, fmtHours)}</span>
              </td>
              <td className="num">—</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p className="help">
        Panel: {p.area_m2} m² × {p.efficiency} × {p.irradiance_w_m2} W/m²
        {p.irradiance_is_default_assumption ? <span className="assump"> (irradiance is the default assumption)</span> : ""} = {fmtPower(p.peak_electrical_power_w)} while illuminated.
        “band” = range if the landing position is wrong by ±{bandM} m (a sensitivity, not an error bar on the physics).
        Terrain effect on energy: {fmtEnergy(d.terrain_effect!.energy_wh_terrain_minus_geometric)} (terrain-corrected minus geometric).
      </p>
      {d.partial_disc_bracket && (
        <p className="help" data-testid="solar-bracket">
          Partial-Sun bracket: {fmtEnergy(d.partial_disc_bracket.whole_disc_energy_wh)} (whole Sun disc above the terrain) to {fmtEnergy(d.partial_disc_bracket.any_part_energy_wh)} (any part, the headline). {d.partial_disc_bracket.note}
        </p>
      )}
      <details>
        <summary>Assumptions and limitations of this estimate</summary>
        <ul className="plain">
          {(d.assumptions ?? []).map((a) => <li key={a}><span className="assump">Assumption:</span> {a}</li>)}
          {(d.limitations ?? []).map((l) => <li key={l}>{l}</li>)}
        </ul>
      </details>
    </div>
  );
}
