// Shared test fixtures shaped exactly like the backend responses (see docs/API_CONTRACT.md). Test-only.
import type { BodySeries, GeometricEntry, IntervalMetrics, ScenarioBody, ScenarioResult, StateEntry, VisibilityBody, VisibilityResponse } from "./api/types";

export const N = 5; // samples
export const STEP = 900;

export const metrics = (f: number): IntervalMetrics => ({
  window_s: (N - 1) * STEP, total_visible_s: 1800, visible_fraction: f, n_visible_intervals: 1,
  longest_visible_s_closed_only: null, longest_visible_s_including_open: 1800, longest_visible_includes_open_interval: true,
  longest_not_visible_s_closed_only: 900, longest_not_visible_s_including_open: 900, longest_not_visible_includes_open_interval: false,
});

const state = (f: number): StateEntry => ({ intervals: [], not_visible_intervals: [], transitions: [], metrics: metrics(f) });

export function series(name: "sun" | "earth"): BodySeries {
  const base = name === "sun" ? 100 : 300;
  return {
    times_s: Array.from({ length: N }, (_, i) => i * STEP),
    azimuth_deg: Array.from({ length: N }, (_, i) => base + i * 10),
    elevation_deg: [1.0, 1.5, 2.0, 2.5, 3.0].map((v) => (name === "sun" ? v : v + 5)),
    angular_radius_deg: Array(N).fill(name === "sun" ? 0.27 : 0.95),
    terrain_horizon_at_centre_deg: [0.5, 1.8, 2.2, 1.0, 0.2],
    geometric_headline_above_local_horizontal: [true, true, true, true, true],
    centre_visible: [true, false, false, true, true],
    any_part_visible: [true, false, false, true, true],
    fully_visible: [true, false, false, true, true],
    headline_visible: [true, false, false, true, true],
    horizon_complete: [true, true, false, true, true],
    unverified_visible: Array(N).fill(false),
    position_sensitivity_deg: [0.1, 0.4, 0.9, 0.3, 0.05],
    headline_state_robust_to_position: [true, true, false, true, true],
  };
}

const geometric = (): GeometricEntry => ({
  definition: "against the local horizontal", intervals: [], not_visible_intervals: [], transitions: [], metrics: metrics(0.9),
  position_sensitivity: { status: "not_applicable" },
});

export function visBody(name: "sun" | "earth"): VisibilityBody {
  return {
    headline_state: name === "sun" ? "any_part_visible" : "centre_visible",
    series: series(name),
    terrain_effect: { headline_visible_steps: 3, geometric_headline_steps: 5, steps_blocked_by_terrain_only: 2, n_steps: N },
    completeness: { steps_with_incomplete_horizon: 1, unverified_visible_steps: 0, visibility_is_upper_bound: false },
    states: { centre: state(0.6), any_part: state(0.6), fully: state(0.6) },
    geometric: geometric(),
    headline: {
      state: name === "sun" ? "any_part_visible" : "centre_visible", intervals: [], not_visible_intervals: [], metrics: metrics(0.6),
      position_sensitivity: {
        status: "computed", events_only_in_displaced_runs: 0, boundary_bands: [],
        metric_bands: { visible_fraction: [0.55, 0.65], total_visible_s: [1500, 2100], n_visible_intervals: [1, 2], longest_visible_s_including_open: [1500, 2100], longest_not_visible_s_including_open: [600, 1200] },
      },
    },
  };
}

export const visResponse = (): VisibilityResponse => ({
  data_class: "calculated",
  observer: { site_id: "im2-athena", lat_deg: -84.79, lon_deg_east: 29.2, ground_height_m: 5321.9, observer_height_above_surface_m: 2, observer_height_is_default_assumption: true },
  window: { start_utc: "2027-01-15T00:00:00Z", end_utc: "2027-01-15T01:00:00Z", step_seconds: STEP, n_samples: N, note: "" },
  definitions: { headline: { sun: "any_part_visible", earth: "centre_visible" }, states: [], disc_model: "circle", horizon_interpolation: "max of bracketing samples" },
  horizon: { az_step_deg: 0.25, windows: ["w"], summary: { n_truncated: 0 }, served_from: "disk" },
  bodies: { sun: visBody("sun"), earth: visBody("earth") },
  position_sensitivity: { status: "computed", data_class: "calculated", kind: "sensitivity of the result to the INPUT observer position", assumed_position_uncertainty_m: 100, assumption: "observer position uncertain by +/-100 m", n_directions: 8, method: "m", limitations: "a sample, not a bound" },
  limitations: ["Geometric line of sight only."],
});

/** /visibility/at: the same shape with a single sample taken from the series at index `i`. */
export function atResponse(i = 1): VisibilityResponse {
  const v = visResponse();
  for (const b of ["sun", "earth"] as const) {
    const s = v.bodies[b].series!;
    const one = {} as Record<string, unknown>;
    for (const [k, val] of Object.entries(s)) one[k] = Array.isArray(val) ? [val[i]] : val;
    v.bodies[b].series = one as unknown as BodySeries;
  }
  return v;
}

export const horizonResponse = () => ({
  azimuth_deg: [0, 90, 180, 270], horizon_elevation_deg: [1, 2, 3, 1], truncated: [false, false, false, false], data_gap: [false, false, false, false],
  horizon_distance_km: [1, 1, 1, 1], observer: { ground_height_m: 5321.9, observer_height_above_surface_m: 2, observer_height_is_default_assumption: true },
  summary: { n_truncated: 0, n_data_gap: 0, horizon_min_deg: 1, horizon_max_deg: 3 }, provenance: { windows: [{ window_id: "w", pixel_size_m: 20 }] },
});

export const ephemerisResponse = () => ({
  provenance: {}, notes: [], observer: {},
  bodies: {
    sun: { azimuth_deg: [101], elevation_deg: [1.1], range_km: [1], angular_diameter_deg: [0.53] },
    earth: { azimuth_deg: [301], elevation_deg: [6.1], range_km: [1], angular_diameter_deg: [1.9] },
  },
});

const scnBody = (frac: number, band: [number, number], geo: number): ScenarioBody => ({
  headline_state: "any_part_visible",
  terrain_corrected: {
    total_visible_s: { nominal: 100, band: [90, 110] }, visible_fraction: { nominal: frac, band }, n_visible_intervals: { nominal: 2, band: [2, 3] },
    longest_visible_s: { closed_only: 10, including_open: 10, includes_open_interval: false },
    longest_not_visible_s: { closed_only: 3600, including_open: 3600, includes_open_interval: false },
    events: [], open_intervals: { visible: 0, not_visible: 0, note: "" },
  },
  geometric: { definition: "", visible_fraction: { nominal: geo }, total_visible_s: { nominal: 1 }, longest_not_visible_s: { including_open: 100, includes_open_interval: false } },
  terrain_effect: { steps_blocked_by_terrain_only: 3, visible_s_terrain_minus_geometric: { nominal: -10, band: [-12, -8] }, note: "" },
  completeness: { visibility_is_upper_bound: false },
});

export const scenarioSupported = (sunFrac = 0.486, earthFrac = 0.808): ScenarioResult => ({
  id: "abc", status: "supported", served_from: "disk",
  spec: { site_id: "im2-athena", lat_deg: -84.79, lon_deg_east: 29.2, start_utc: "2027-01-15T00:00:00Z", duration_days: 30, step_seconds: 900, observer_height_m: 2, observer_height_is_default_assumption: true, position_uncertainty_m: 100, label: null },
  bodies: { sun: scnBody(sunFrac, [sunFrac - 0.03, sunFrac + 0.003], 0.533), earth: scnBody(earthFrac, [earthFrac - 0.008, earthFrac + 0.001], 0.735) },
});

export const versionFixture = {
  model_version: "0.10.0-stage8", api_version: "1.0.0", stage: 11,
  notice: "Terrain-corrected visibility ... terrain_data_insufficient and never ranked.",
  capabilities: [
    { key: "ephemeris", title: "Sun and Earth azimuth/elevation (SPICE)", stage: 3, status: "validated" },
    { key: "horizon", title: "Terrain horizon profile", stage: 4, status: "validated" },
    { key: "visibility", title: "Terrain-corrected Sun/Earth visibility", stage: 5, status: "validated" },
    { key: "scenarios", title: "Scenario comparison and delay simulator", stage: 6, status: "validated" },
    { key: "engineering", title: "Solar energy availability (idealised direct-beam upper bound)", stage: 8, status: "validated" },
  ],
};

export const sitesFixture = {
  catalogue_version: "x", policy: "Only sites with primary-source coordinates.", reference_sphere_radius_m: 1737400,
  sites: [
    { id: "im2-athena", name: "IM-2 Athena landing site (Mons Mouton)", kind: "confirmed_landing", lat_deg: -84.79, lon_deg_east: 29.2, sources: [] },
    { id: "im1-odysseus", name: "IM-1 Odysseus landing site (Malapert A)", kind: "confirmed_landing", lat_deg: -80.13, lon_deg_east: 1.45, sources: [] },
  ],
  pending_regions: [],
};

export const healthFixture = { status: "ok", service: "lunarnav-api", model_version: "0.10.0-stage8", env: "test", time_utc: "2026-11-15T00:00:00Z" };

export const provenanceFixture = {
  model_version: "0.10.0-stage8", git_commit: "abc123def456", software: { python: "3.12.10" },
  spice_kernels: [{ file: "de440s.bsp", role: "planetary_spk", sha256: "a".repeat(64), source_url: "https://naif.example/de440s.bsp" }], spice_frame: "MOON_ME",
  dem_windows: [{ window_id: "im2_20m_r80km", product_id: "LDEM_80S_20MPP_ADJ", pixel_size_m: 20, width: 8000, height: 8000, source_url: "https://pgda.example/x.TIF", sha256: "b".repeat(64), z_min_m: 0, z_max_m: 1, valid_fraction: 1, overview_level: null }],
  site_catalogue: { catalogue_version: "2026-11-14.1", sha256: "c".repeat(64), sites: [] },
  validation_fixtures: { horizons: { file: "data/validation/horizons_stage3_reference.json", sha256: "d".repeat(64), note: "x" } },
  constants: {}, data_classes: { calculated: "derived by the engine" },
};

/** Route-table fetch stub. Keys are paths without the /api prefix and query; values are JSON bodies or functions. */
export function stubFetch(routes: Record<string, unknown>) {
  const calls: string[] = [];
  const fn = async (url: string, init?: { method?: string }) => {
    const path = url.replace(/^\/api/, "").split("?")[0];
    calls.push(`${init?.method ?? "GET"} ${path}`);
    if (path in routes) {
      const v = routes[path];
      const body = typeof v === "function" ? (v as () => unknown)() : v;
      return { ok: true, json: async () => body };
    }
    return { ok: false, status: 404, json: async () => ({ code: "NOT_FOUND", message: `no stub for ${path}`, field: null, details: {}, request_id: null }) };
  };
  return { fn, calls };
}

export const baseRoutes = () => ({
  "/health": healthFixture, "/version": versionFixture, "/sites": sitesFixture, "/provenance": provenanceFixture,
  "/horizon/profile": horizonResponse(), "/visibility/series": visResponse(), "/visibility/at": atResponse(1),
  "/ephemeris/position": ephemerisResponse(), "/scenarios/evaluate": scenarioSupported(),
});
