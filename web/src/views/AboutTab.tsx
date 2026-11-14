import { useContext } from "react";
import { api } from "../api/client";
import type { Site, SitesResponse } from "../api/types";
import { useAsync } from "../hooks";
import { statusLabel } from "../format";
import { CapabilitiesContext, ErrorBox, Loading, Panel } from "../ui";

const Sha = ({ v }: { v: string | null | undefined }) =>
  v ? <code title={v} style={{ wordBreak: "break-all" }}>{v}</code> : <span className="muted-text">—</span>;

export function AboutTab({ sites }: { sites: SitesResponse | null }) {
  const caps = useContext(CapabilitiesContext);
  const prov = useAsync((s) => api.provenance(s), "prov");
  const list: Site[] = sites?.sites ?? [];

  return (
    <div className="stack">
      <Panel title="Capability status (what is actually built and approved)">
        <table>
          <thead><tr><th>Capability</th><th>Stage</th><th>Status</th></tr></thead>
          <tbody>
            {(caps ?? []).map((c) => (
              <tr key={c.key}><td>{c.title}</td><td>{c.stage}</td><td><span className={`tag tag-${c.status}`}>{statusLabel(c.status)}</span></td></tr>
            ))}
          </tbody>
        </table>
        <p className="help">“validated” = the project owner approved that stage’s evaluation gate after reviewing the evidence (implemented, tested, reviewed — <em>not</em> “proven against measurement”). “implemented unvalidated” = built but not yet approved: treat as provisional. “not implemented” = nothing on screen is computed for it.</p>
      </Panel>

      <Panel title="What the numbers mean">
        <ul className="plain">
          <li><strong>Terrain horizon</strong>: for each azimuth, the highest elevation of DEM terrain along a great-circle ray on the 1737.4 km Moon (curvature included). It is the terrain only; it says nothing about where the Sun or Earth is.</li>
          <li><strong>Sun / Earth direction</strong>: apparent azimuth (clockwise from local north) and elevation (above the local horizontal) from the JPL DE440 ephemeris with light-time and stellar-aberration corrections, in the Moon’s mean-Earth frame.</li>
          <li><strong>Visible (terrain-corrected)</strong>: the body’s disc is above the terrain horizon. Three states are computed: disc centre, any part of the disc, whole disc. <strong>Sun headline = any part</strong> (any direct illumination); <strong>Earth headline = disc centre</strong> (antenna pointing). This is geometric line of sight, <em>not</em> communication-link availability and not solar power.</li>
          <li><strong>Geometric</strong>: the same definition against the local horizontal with no terrain. Shown beside every terrain-corrected result so the effect of terrain is visible; it can be higher or lower (terrain can both block light and, on a high plateau, dip below the local horizontal).</li>
          <li><strong>Position band</strong>: how much a result could move if the landing position were wrong by the stated amount (default ±100 m). It is a <em>sensitivity to the input position</em>, computed by recomputing at displaced positions, not an error bar on the astronomy or terrain, which are exact for their inputs. It is a sample of displacements (8 directions), not a proven bound.</li>
          <li><strong>Cut off</strong>: an interval touching the edge of the window; its true length is at least what is shown.</li>
          <li><strong>Terrain data insufficient</strong>: the available terrain data cannot support a position-sensitivity result, so no figures, ranking or estimate are given.</li>
        </ul>
      </Panel>

      <Panel title="Assumptions and limitations">
        <ul className="plain">
          <li><span className="assump">Assumption:</span> observer height 2.0 m above the DEM surface unless you enter another value (decision C9).</li>
          <li><span className="assump">Assumption:</span> landing-position uncertainty ±100 m by default (configurable); positions are catalogue values from NASA/JPL NAIF and LROC sources.</li>
          <li><span className="assump">Assumption:</span> the mission-delay window defaults to 14 days (about one lunar day); change it to match the operation.</li>
          <li>Validated time range 2025-01-01 to 2035-12-31 (kernels are checksum-pinned; UTC after 2017 assumes no further leap seconds).</li>
          <li>The terrain is a LOLA DEM (about 90 % of 5 m pixels are interpolated between ground tracks); boulders, the lander body and regolith lofting are not modelled; no per-pixel DEM uncertainty is reported.</li>
          <li>Only IM-2 (landing and pre-landing target positions) has the 20 m terrain coverage needed for position-sensitivity figures. IM-1 has 2 km of 20 m data and Chandrayaan-3 has none, so they appear as “terrain data insufficient”. Extending coverage is future work. No real permanently shadowed region data are included.</li>
          <li>The ephemeris check against JPL Horizons shares JPL’s ephemerides, so it validates the implementation, not the ephemerides themselves; no physically independent horizon or visibility dataset was available.</li>
          <li>Events shorter than the sampling step that fall between samples are not detected (checked at IM-2: 15-minute and 5-minute runs agree).</li>
          <li>Not modelled: gravitational light bending (≤ 6×10⁻⁷°), Earth oblateness, refraction (none on the Moon).</li>
          <li>Engineering assessments (solar power, antenna masks, slope, temperature) are not built (deferred).</li>
        </ul>
        <p className="help">Full list with evidence: <code>docs/stage9/KNOWN_LIMITATIONS.md</code> (29 items) · validation evidence: <code>docs/stage9/VALIDATION_REPORT.md</code> · numerical tolerances: <code>docs/stage9/TOLERANCES.md</code>.</p>
      </Panel>

      <Panel title="Scientific data sources">
        <h3>Landing-site catalogue</h3>
        {sites && <p className="help">{sites.policy}</p>}
        <ul className="plain">
          {list.map((s) => (
            <li key={s.id}>
              <strong>{s.name}</strong> ({s.lat_deg}°, {s.lon_deg_east}°E)
              <ul className="plain">
                {s.sources.map((src) => (
                  <li key={src.url}><a href={src.url} target="_blank" rel="noreferrer">{src.label}</a> — {src.description}</li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
        {sites && sites.pending_regions.length > 0 && (
          <p className="help">Not selectable: {sites.pending_regions.map((p) => p.name).join("; ")} — {sites.pending_regions[0].reason}</p>
        )}
        {prov.phase === "loading" && <Loading startedAt={prov.startedAt} label="Loading provenance" />}
        {prov.phase === "error" && <ErrorBox error={prov.error} what="Provenance" />}
        {prov.phase === "ready" && (
          <>
            <p className="help">Catalogue version {prov.data.site_catalogue.catalogue_version} · SHA-256 <Sha v={prov.data.site_catalogue.sha256} /></p>

            <h3>Terrain (LOLA digital elevation models, NASA GSFC PGDA)</h3>
            <div className="scroll">
              <table>
                <thead><tr><th>Window</th><th>Product</th><th className="num">Pixel</th><th className="num">Size</th><th>SHA-256 (verified at load)</th></tr></thead>
                <tbody>
                  {prov.data.dem_windows.map((w) => (
                    <tr key={w.window_id}>
                      <td>{w.window_id}</td>
                      <td><a href={w.source_url} target="_blank" rel="noreferrer">{w.product_id}</a>{w.overview_level !== null ? ` (overview ${w.overview_level})` : ""}</td>
                      <td className="num">{w.pixel_size_m} m</td>
                      <td className="num">{w.width}×{w.height}</td>
                      <td><Sha v={w.sha256} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="help">Heights are metres above the 1737.4 km reference sphere (data class: measured, interpolated). Windows are real extracts of the cited LOLA product; nothing is resampled by this project.</p>

            <h3>Ephemeris (NAIF SPICE)</h3>
            {prov.data.spice_kernels ? (
              <div className="scroll">
                <table>
                  <thead><tr><th>Kernel</th><th>Role</th><th>SHA-256 (verified at load)</th></tr></thead>
                  <tbody>
                    {prov.data.spice_kernels.map((k) => (
                      <tr key={k.file}><td><a href={k.source_url} target="_blank" rel="noreferrer">{k.file}</a></td><td>{k.role.replaceAll("_", " ")}</td><td><Sha v={k.sha256} /></td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="error" role="alert">SPICE kernels are not installed on this server: {prov.data.spice_kernels_error}</p>
            )}
            <p className="help">
              Frame {prov.data.spice_frame ?? "MOON_ME"} · light-time + stellar aberration. The ephemeris engine was compared with JPL Horizons on a 220-row grid (Sun within 1.4×10⁻⁸°, Earth within 6×10⁻⁷°, against a pre-declared 0.01° criterion). Horizons shares JPL’s ephemerides, so this checks the implementation, not the ephemerides.
            </p>

            <h3>Reproducibility</h3>
            <p className="help">
              Model version <strong>{prov.data.model_version}</strong> · code commit <Sha v={prov.data.git_commit} /> · {Object.entries(prov.data.software).map(([k, v]) => `${k} ${v}`).join(" · ")}
            </p>
            <p className="help">
              Every visibility and scenario result carries a deterministic <code>provenance</code> block (kernel and DEM checksums, frame, algorithm version and every parameter, no timestamps): the same inputs and data give identical results. Validation fixture{" "}
              {Object.values(prov.data.validation_fixtures).map((f) => <span key={f.file}><code>{f.file}</code> <Sha v={f.sha256} /></span>)}.
              Data classes: {Object.entries(prov.data.data_classes).map(([k, v]) => `${k} (${v})`).join("; ")}.
            </p>
          </>
        )}
      </Panel>
    </div>
  );
}
