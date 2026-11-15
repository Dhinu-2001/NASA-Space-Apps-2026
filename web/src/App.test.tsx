import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import type { CompareResponse, DelayResponse, ScenarioBody, ScenarioResult, VisibilityBody } from "./api/types";
import { MetricsPanel } from "./components/MetricsPanel";
import { Timeline } from "./components/Timeline";
import { fmtDur, fmtPct, fmtUtc, localInputToUtc } from "./format";
import { CompareResult } from "./views/CompareTab";
import { DelayResult } from "./views/DelayTab";

const health = { status: "ok", service: "lunarnav-api", model_version: "0.6.0-stage6", env: "test", time_utc: "2026-11-15T00:00:00Z" };
const version = {
  model_version: "0.6.0-stage6",
  api_version: "0.1.0",
  stage: 6,
  notice: "Stage 6: scenario comparison ... Sites without supporting terrain data are reported as terrain_data_insufficient and never ranked.",
  capabilities: [
    { key: "ephemeris", title: "Sun and Earth azimuth/elevation (SPICE)", stage: 3, status: "validated" },
    { key: "visibility", title: "Terrain-corrected Sun/Earth visibility", stage: 5, status: "validated" },
    { key: "scenarios", title: "Scenario comparison and delay simulator", stage: 6, status: "validated" },
    { key: "engineering", title: "Solar energy availability (idealised direct-beam upper bound)", stage: 8, status: "validated" },
    { key: "pending-example", title: "Fixture-only capability that is built but not yet approved", stage: 11, status: "implemented_unvalidated" },
    { key: "antenna", title: "Antenna masks (fixture entry for a deferred capability)", stage: 8, status: "not_implemented" },
  ],
};
const sites = {
  catalogue_version: "x",
  policy: "Only sites with primary-source coordinates.",
  reference_sphere_radius_m: 1737400,
  sites: [
    { id: "im2-athena", name: "IM-2 Athena landing site (Mons Mouton)", kind: "confirmed_landing", lat_deg: -84.79, lon_deg_east: 29.2, sources: [] },
    { id: "im1-odysseus", name: "IM-1 Odysseus landing site (Malapert A)", kind: "confirmed_landing", lat_deg: -80.13, lon_deg_east: 1.45, sources: [] },
  ],
  pending_regions: [],
};

afterEach(() => {
  vi.restoreAllMocks();
  window.history.replaceState(null, "", "/");
});

function stubApi(extra: Record<string, unknown> = {}) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const path = url.replace(/^\/api/, "").split("?")[0];
      const table: Record<string, unknown> = { "/health": health, "/version": version, "/sites": sites, "/dem/windows": [], ...extra };
      if (path in table) return { ok: true, json: async () => table[path] };
      return { ok: false, status: 404, json: async () => ({ code: "NOT_FOUND", message: "no stub", field: null, details: {}, request_id: null }) };
    }),
  );
}

describe("App shell", () => {
  it("shows every capability with its real status and the backend notice", async () => {
    stubApi();
    render(<App />);
    expect(await screen.findByTestId("health-status")).toHaveTextContent("ok");
    const strip = screen.getByLabelText("Capability status");
    expect(within(strip).getAllByText("validated").length).toBe(4);   // ephemeris, visibility, scenarios, engineering (fixture mirrors the backend)
    expect(within(strip).getAllByText("implemented unvalidated").length).toBe(1);   // the fixture-only entry: the status still renders honestly
    expect(within(strip).getByText("not implemented")).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent(/never ranked/);
  });

  it("tags panels with the status of the capability they depend on", async () => {
    stubApi();
    render(<App />);
    await screen.findByTestId("health-status");
    fireEvent.click(screen.getByRole("tab", { name: "Compare" }));
    expect(screen.getByTestId("status-scenarios")).toHaveTextContent("scenarios: validated");
    expect(screen.getByTestId("status-visibility")).toHaveTextContent("visibility: validated");
  });

  it("shows an error state when the backend is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("network"); }));
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/Backend unavailable/);
  });

  it("offers the full workflow controls: site, custom coordinates, time, band, observer height", async () => {
    stubApi();
    render(<App />);
    await screen.findByTestId("health-status");
    expect(screen.getByLabelText("Catalogue site")).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText(/Use custom coordinates/));
    expect(screen.getByLabelText(/Latitude/)).not.toBeDisabled();
    expect(screen.getByLabelText(/Show positions at/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Assumed landing-position uncertainty/)).toHaveValue("100");
    expect(screen.getByText(/2\.0 m default — an assumption/)).toBeInTheDocument();
    // client-side input validation (no request is made)
    fireEvent.change(screen.getByLabelText(/Latitude/), { target: { value: "abc" } });
    fireEvent.click(screen.getByRole("button", { name: "Compute" }));
    expect(screen.getByRole("alert")).toHaveTextContent(/numeric latitude/);
  });

  const provenance = {
    model_version: "0.9.0-stage9", git_commit: "abc123def456", software: { python: "3.12.10", spiceypy: "8.4.0" },
    spice_kernels: [{ file: "de440s.bsp", role: "planetary_spk", sha256: "a".repeat(64), source_url: "https://naif.example/de440s.bsp" }],
    spice_frame: "MOON_ME",
    dem_windows: [{ window_id: "im2_20m_r80km", product_id: "LDEM_80S_20MPP_ADJ", pixel_size_m: 20, width: 8000, height: 8000, source_url: "https://pgda.example/x.TIF", sha256: "b".repeat(64), z_min_m: 0, z_max_m: 1, valid_fraction: 1, overview_level: null }],
    site_catalogue: { catalogue_version: "2026-11-14.1", sha256: "c".repeat(64), sites: [] },
    validation_fixtures: { horizons: { file: "data/validation/horizons_stage3_reference.json", sha256: "d".repeat(64), note: "x" } },
    constants: {}, data_classes: { calculated: "derived by the engine" },
  };

  it("shows the data-sources, checksums, provenance and assumptions page with defaults labelled as assumptions", async () => {
    stubApi({ "/provenance": provenance });
    render(<App />);
    await screen.findByTestId("health-status");
    fireEvent.click(screen.getByRole("tab", { name: "Data & assumptions" }));
    expect(await screen.findByText(/de440s\.bsp/)).toBeInTheDocument();
    expect(screen.getByText("a".repeat(64))).toBeInTheDocument();           // full kernel checksum
    expect(screen.getByText("b".repeat(64))).toBeInTheDocument();           // full DEM checksum
    expect(screen.getByText("abc123def456")).toBeInTheDocument();           // code commit
    expect(screen.getByText(/0\.9\.0-stage9/)).toBeInTheDocument();
    expect(screen.getAllByText("Assumption:").length).toBeGreaterThanOrEqual(3);
    expect(screen.getByText(/IM-1 has 2 km of 20 m data/)).toBeInTheDocument();
    expect(screen.getByText(/“proven against measurement”/)).toBeInTheDocument();
    expect(screen.getAllByText(/shares JPL’s ephemerides/).length).toBe(2);   // limitations list and the ephemeris note
  });

  it("says so when the server has no SPICE kernels instead of showing an empty table", async () => {
    stubApi({ "/provenance": { ...provenance, spice_kernels: null, spice_kernels_error: "Required SPICE kernel missing: de440s.bsp" } });
    render(<App />);
    await screen.findByTestId("health-status");
    fireEvent.click(screen.getByRole("tab", { name: "Data & assumptions" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/SPICE kernels are not installed.*de440s\.bsp/);
  });
});

// ---------------------------------------------------------------- comparison: insufficient sites, bands, open flags

const body = (frac: number, band: [number, number], geo: number, open = false): ScenarioBody => ({
  headline_state: "any_part_visible",
  terrain_corrected: {
    total_visible_s: { nominal: 100, band: [90, 110] },
    visible_fraction: { nominal: frac, band },
    n_visible_intervals: { nominal: 2, band: [2, 3] },
    longest_visible_s: { closed_only: 10, including_open: 10, includes_open_interval: false },
    longest_not_visible_s: { closed_only: open ? null : 3600, including_open: 7200, includes_open_interval: open, band_including_open: [3600, 9000] },
    events: [],
    open_intervals: { visible: 0, not_visible: open ? 1 : 0, note: "" },
  },
  geometric: { definition: "", visible_fraction: { nominal: geo }, total_visible_s: { nominal: 1 }, longest_not_visible_s: { including_open: 100, includes_open_interval: false } },
  terrain_effect: { steps_blocked_by_terrain_only: 3, visible_s_terrain_minus_geometric: { nominal: -10, band: [-12, -8] }, note: "" },
  completeness: { visibility_is_upper_bound: false },
});

const supported = (id: string, label: string, open = false): ScenarioResult => ({
  id, status: "supported", served_from: "computed",
  spec: { site_id: "im2-athena", lat_deg: -84.79, lon_deg_east: 29.2, start_utc: "2027-01-15T00:00:00Z", duration_days: 30, step_seconds: 900, observer_height_m: 2, observer_height_is_default_assumption: true, position_uncertainty_m: 100, label },
  bodies: { sun: body(0.486, [0.454, 0.489], 0.533, open), earth: body(0.808, [0.8, 0.809], 0.735) },
});
const insufficient = (id: string): ScenarioResult => ({
  id, status: "terrain_data_insufficient", served_from: "computed", reason: "terrain coverage is insufficient to certify the horizon (360 truncated)",
  spec: { site_id: "im1-odysseus", lat_deg: -80.13, lon_deg_east: 1.45, start_utc: "2027-01-15T00:00:00Z", duration_days: 30, step_seconds: 900, observer_height_m: 2, observer_height_is_default_assumption: true, position_uncertainty_m: 100, label: "IM-1 @ Jan" },
});

const delta = (sentence: string) => ({
  baseline_id: "a", scenario_id: "b", delta_band_method: "independent_interval_arithmetic" as const,
  bodies: {
    sun: { terrain_corrected: {}, geometric: { visible_fraction: { baseline: 0.5, scenario: 0.45, delta: -0.05 } }, summary: [sentence] },
    earth: { terrain_corrected: {}, geometric: { visible_fraction: { baseline: 0.7, scenario: 0.7, delta: 0 } }, summary: ["earth visible fraction: +0.1 percentage points (band -0.3 to +0.8; NOT distinguishable from zero given +/-100 m position uncertainty)."] },
  },
});

const compare: CompareResponse = {
  baseline_id: "a",
  scenarios: [supported("a", "IM-2 @ Jan", true), supported("b", "IM-2 @ Mar"), insufficient("c")],
  excluded_terrain_data_insufficient: [{ scenario_id: "c", label: "IM-1 @ Jan", site_id: "im1-odysseus", reason: "terrain coverage is insufficient to certify the horizon (360 truncated)" }],
  deltas_vs_baseline: [delta("sun visible fraction: -6.12 percentage points (band -6.43 to -4.79; distinguishable from zero).")],
  rankings: [{ criterion: "sun_visible_fraction", better: "higher", method: "ordered by nominal value", ranking: [
    { rank: 1, scenario_id: "a", label: "IM-2 @ Jan", site_id: "im2-athena", start_utc: "x", nominal: 0.486, band: [0.454, 0.489], includes_open_interval: false, distinguishable_from_next: true },
    { rank: 2, scenario_id: "b", label: "IM-2 @ Mar", site_id: "im2-athena", start_utc: "x", nominal: 0.425, band: [0.396, 0.442], includes_open_interval: false, distinguishable_from_next: null },
  ] }],
  notes: [], reading_guide: ["Sites without terrain support are excluded, never ranked or estimated."],
};

describe("Comparison view", () => {
  it("shows terrain-corrected next to geometric, with the position band on every fraction", () => {
    render(<CompareResult data={compare} />);
    const rows = screen.getAllByTestId("row-supported");
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText(fmtPct(0.486))).toBeInTheDocument();
    expect(within(rows[0]).getByText(fmtPct(0.533))).toBeInTheDocument();           // geometric alongside
    expect(within(rows[0]).getAllByText(/band 45\.4 % to 48\.9 %/).length).toBe(1);   // band visible, not just nominal
    expect(within(rows[0]).getAllByText(/band 80\.0 % to 80\.9 %/).length).toBe(1);
  });

  it("flags a cut-off interval instead of presenting it as complete", () => {
    render(<CompareResult data={compare} />);
    expect(within(screen.getAllByTestId("row-supported")[0]).getByText("cut off")).toBeInTheDocument();
    expect(within(screen.getAllByTestId("row-supported")[1]).queryByText("cut off")).toBeNull();
  });

  it("shows an insufficient site as a label with its reason and NO numbers, and keeps it out of rankings", () => {
    render(<CompareResult data={compare} />);
    const row = screen.getByTestId("row-insufficient");
    expect(row).toHaveTextContent("Terrain data insufficient");
    expect(row.textContent).not.toMatch(/\d+(\.\d+)? ?%/);
    const excluded = screen.getByTestId("excluded-list");
    expect(excluded).toHaveTextContent("im1-odysseus");
    expect(excluded.textContent).not.toMatch(/%/);
    const ranking = screen.getByText("sun visible fraction", { selector: "strong" }).closest(".card") as HTMLElement;
    expect(ranking.textContent).not.toMatch(/IM-1/);
  });

  it("carries the band into the differences and marks results inside position uncertainty", () => {
    render(<CompareResult data={compare} />);
    expect(screen.getByText(/band -6\.43 to -4\.79; distinguishable from zero/)).toBeInTheDocument();
    expect(screen.getByText(/NOT distinguishable from zero/)).toBeInTheDocument();
    expect(screen.getAllByText("within position uncertainty").length).toBe(1);
    expect(screen.getByText(/independent bands/)).toBeInTheDocument();
    expect(screen.getByText(/Geometric \(no terrain\), sun: visible fraction -5\.00 percentage points/)).toBeInTheDocument();
    expect(screen.getByText("clearly ahead of next")).toBeInTheDocument();
  });
});

describe("Delay view", () => {
  const dr = (offset: number, frac: number): DelayResponse["summary_table"] extends (infer R)[] | undefined ? R : never => ({
    offset_days: offset, scenario_id: `s${offset}`, start_utc: "2027-01-15T00:00:00Z",
    sun: { terrain_corrected_visible_fraction: { nominal: frac, band: [frac - 0.05, frac + 0.02] }, geometric_visible_fraction: frac + 0.03, terrain_corrected_longest_not_visible_s: { nominal: 7200, band: [3600, 9000], includes_open_interval: true }, geometric_longest_not_visible_s: { nominal: 100, includes_open_interval: false } },
    earth: { terrain_corrected_visible_fraction: { nominal: 0.8, band: [0.79, 0.81] }, geometric_visible_fraction: 0.7, terrain_corrected_longest_not_visible_s: { nominal: 100, band: [90, 110], includes_open_interval: false }, geometric_longest_not_visible_s: { nominal: 100, includes_open_interval: false } },
  });
  const supportedDelay: DelayResponse = {
    status: "supported",
    summary_table: [dr(0, 0.95), dr(1, 0.88)],
    delays: [{ offset_days: 1, scenario: supported("d1", "delay +1 d"), delta_vs_baseline: { ...delta("sun visible fraction: -7.14 percentage points (band -7.14 to -7.14; distinguishable from zero)."), delta_band_method: "paired" } }],
    notes: ["Each delay shifts the whole window."],
  };

  it("draws the band and the geometric value for every delay and flags cut-off intervals", () => {
    render(<DelayResult data={supportedDelay} />);
    expect(screen.getByTestId("delay-chart-sun")).toBeInTheDocument();
    expect(screen.getAllByText(/band 90\.0 % to 97\.0 %/).length).toBe(1);
    expect(screen.getAllByText("cut off").length).toBe(2);
    expect(screen.getByText(/paired band \(same site\)/)).toBeInTheDocument();
    expect(screen.getAllByText(/\//).length).toBeGreaterThan(0);
  });

  it("shows an insufficient site as a label with no numbers or charts", () => {
    render(<DelayResult data={{ status: "terrain_data_insufficient", reason: "no DEM covers this location", note: "No delay comparison is produced for a site without supporting terrain data." }} />);
    expect(screen.getByTestId("terrain-insufficient")).toBeInTheDocument();
    expect(screen.queryByTestId("delay-chart-sun")).toBeNull();
    expect(document.body.textContent).not.toMatch(/\d %/);
  });
});

// ---------------------------------------------------------------- single-site metrics + timeline

const iv = (s: number, e: number, os = false, oe = false, band = true) => ({
  start_utc: "2027-01-15T00:00:00Z", end_utc: "2027-01-16T00:00:00Z", start_s: s, end_s: e, duration_s: e - s, open_start: os, open_end: oe,
  start_band: band ? { earliest_utc: "2027-01-15T00:00:00Z", latest_utc: "2027-01-15T06:00:00Z", width_s: 21600, complete: true } : null,
  end_band: band ? { earliest_utc: "2027-01-15T18:00:00Z", latest_utc: "2027-01-16T02:00:00Z", width_s: 28800, complete: false } : null,
});
const metrics = (f: number) => ({ window_s: 86400, total_visible_s: 43200, visible_fraction: f, n_visible_intervals: 1, longest_visible_s_closed_only: null, longest_visible_s_including_open: 43200, longest_visible_includes_open_interval: true, longest_not_visible_s_closed_only: 20000, longest_not_visible_s_including_open: 20000, longest_not_visible_includes_open_interval: false });
const visBody = (sens: "computed" | "not_computed"): VisibilityBody => ({
  headline_state: "any_part_visible",
  terrain_effect: { headline_visible_steps: 5, geometric_headline_steps: 8, steps_blocked_by_terrain_only: 3, n_steps: 10 },
  completeness: { steps_with_incomplete_horizon: 0, unverified_visible_steps: 0, visibility_is_upper_bound: false },
  states: {
    centre: { intervals: [], not_visible_intervals: [], transitions: [], metrics: metrics(0.4) },
    any_part: { intervals: [], not_visible_intervals: [], transitions: [{ time_utc: "2027-01-15T12:00:00Z", time_s: 43200, to: "not_visible" }], metrics: metrics(0.5), is_headline: true },
    fully: { intervals: [], not_visible_intervals: [], transitions: [], metrics: metrics(0.3) },
  },
  geometric: { definition: "", intervals: [], not_visible_intervals: [], transitions: [], metrics: metrics(0.6), position_sensitivity: { status: "not_applicable" } },
  headline: {
    state: "any_part_visible", intervals: [], not_visible_intervals: [], metrics: metrics(0.5),
    position_sensitivity: sens === "computed"
      ? { status: "computed", metric_bands: { visible_fraction: [0.45, 0.52], total_visible_s: [40000, 46000], n_visible_intervals: [1, 2], longest_visible_s_including_open: [40000, 46000], longest_not_visible_s_including_open: [19000, 21000] },
          boundary_bands: [{ nominal_time_s: 43200, earliest_utc: "2027-01-15T10:00:00Z", latest_utc: "2027-01-15T20:00:00Z", width_s: 36000, complete: false, band_width_s: 36000, band_complete: false, displaced_runs_without_matching_event: 2 }], events_only_in_displaced_runs: 1 }
      : { status: "not_computed", reason: "terrain coverage is insufficient" },
  },
});

describe("Metrics and timeline", () => {
  it("shows every metric with its band, flags the cut-off interval and the incomplete event band", () => {
    render(<MetricsPanel name="sun" body={visBody("computed")} bandM={100} sensStatus="computed" />);
    expect(screen.getByText(/band 45\.0 % to 52\.0 %/)).toBeInTheDocument();
    expect(screen.getAllByText("cut off").length).toBe(2); // terrain-corrected and geometric cells of "longest visible"
    expect(screen.getByText("incomplete")).toBeInTheDocument();
    expect(screen.getByText(/width 10\.0 h/)).toBeInTheDocument();
    expect(screen.getByText(/1 further event\(s\) appear only at displaced positions/)).toBeInTheDocument();
    expect(screen.getByText(/±100 m \(a sensitivity, not an error bar/)).toBeInTheDocument();
    expect(screen.getByText("headline")).toBeInTheDocument();
  });

  it("says 'not computed' rather than showing a confident single number when sensitivity is unavailable", () => {
    render(<MetricsPanel name="earth" body={visBody("not_computed")} bandM={null} sensStatus="not_computed" />);
    expect(screen.getAllByText(/band not computed/).length).toBeGreaterThan(0);
    expect(screen.getByText("not computed")).toBeInTheDocument();
  });

  it("draws interval bars, dashed outlines for cut-off intervals and a whisker for each closed boundary band", () => {
    const { container } = render(
      <Timeline startUtc="2027-01-15T00:00:00Z" windowS={172800} cursorS={3600}
        rows={[{ label: "Sun", visible: [iv(0, 43200, true, false)], notVisible: [iv(43200, 172800, false, true)], color: "var(--sun)", withBands: true }]} />,
    );
    expect(container.querySelectorAll("rect[stroke-dasharray]").length).toBe(2);   // both intervals touch an edge
    expect(container.querySelectorAll("g[stroke='var(--accent)']").length).toBe(2); // closed boundary at 43200 seen from both intervals
    expect(screen.getByText(/position-uncertainty band of the boundary/)).toBeInTheDocument();
  });
});

describe("formatting (presentation only)", () => {
  it("formats durations, percentages and times", () => {
    expect(fmtDur(90)).toBe("90 s");
    expect(fmtDur(7200)).toBe("2.0 h");
    expect(fmtDur(2 * 86400)).toBe("2.0 d");
    expect(fmtPct(0.4861)).toBe("48.6 %");
    expect(fmtUtc("2027-01-28T08:58:55Z")).toBe("2027-01-28 08:58:55 UTC");
    expect(localInputToUtc("2027-01-15T00:00")).toBe("2027-01-15T00:00:00Z");
  });
});

describe("View workflow", () => {
  it("computes a site and shows Sun/Earth positions, horizon and an honest insufficient-terrain label", async () => {
    const at = (bodies = true) => ({
      observer: {}, position_sensitivity: { status: "computed", assumed_position_uncertainty_m: 100 }, limitations: [],
      bodies: Object.fromEntries(["sun", "earth"].map((b) => [b, { headline_state: b === "sun" ? "any_part_visible" : "centre_visible", series: bodies ? {
        azimuth_deg: [120.5], elevation_deg: [1.25], angular_radius_deg: [0.27], terrain_horizon_at_centre_deg: [0.8], position_sensitivity_deg: [0.9],
        centre_visible: [true], any_part_visible: [true], fully_visible: [false], headline_visible: [true], headline_state_robust_to_position: [false],
        horizon_complete: [true], geometric_headline_above_local_horizontal: [true], times_s: [0], unverified_visible: [false] } : undefined }])),
    });
    const horizon = { azimuth_deg: [0, 90, 180, 270], horizon_elevation_deg: [1, 2, 3, null], truncated: [false, false, false, true], data_gap: [false, false, false, false], horizon_distance_km: [1, 1, 1, null],
      observer: { ground_height_m: 5321.9, observer_height_above_surface_m: 2, observer_height_is_default_assumption: true }, summary: { n_truncated: 1, n_data_gap: 0 }, provenance: { windows: [{ window_id: "w", pixel_size_m: 20 }] } };
    const insufficientSeries = { ok: true, json: async () => ({ position_sensitivity: { status: "not_computed", reason: "terrain coverage is insufficient to certify the horizon (360 truncated)" }, bodies: {}, window: {}, definitions: { headline: {} }, limitations: [] }) };
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: { method?: string }) => {
      const path = url.replace(/^\/api/, "").split("?")[0];
      const json = (o: unknown) => ({ ok: true, json: async () => o });
      if (path === "/health") return json(health);
      if (path === "/version") return json(version);
      if (path === "/sites") return json(sites);
      if (path === "/horizon/profile") return json(horizon);
      if (path === "/visibility/at") return json(at());
      if (path === "/ephemeris/position") return json({ provenance: {}, notes: [], observer: {}, bodies: {} });
      if (path === "/visibility/series" && init?.method === "POST") return insufficientSeries;
      return { ok: false, status: 404, json: async () => ({ code: "NOT_FOUND", message: "x", field: null, details: {}, request_id: null }) };
    }));
    render(<App />);
    await screen.findByTestId("health-status");
    fireEvent.click(screen.getByRole("button", { name: "Compute" }));
    const sun = await screen.findByTestId("now-sun");
    expect(sun).toHaveTextContent("az 120.5°");
    expect(sun).toHaveTextContent("el +1.25°");
    expect(sun).toHaveTextContent("could change by up to 0.90° for a ±100 m position error");
    expect(sun).toHaveTextContent("changes with position");
    expect(await screen.findByLabelText(/Terrain horizon profile/)).toBeInTheDocument();
    expect(await screen.findByText(/horizon is only a lower bound here/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("terrain-insufficient")).toBeInTheDocument());
    expect(screen.queryByLabelText("Visibility timeline")).toBeNull();               // no timeline for an insufficient site
    expect(screen.getByTestId("terrain-insufficient")).toHaveTextContent(/360 truncated/);
  });
});
