// Hand-written types for the endpoints whose OpenAPI response is an open dictionary
// (visibility and scenarios). They mirror docs/API_CONTRACT.md. The frontend only READS these numbers (decision C4).

export type CapabilityStatus = "not_implemented" | "implemented_unvalidated" | "validated";

export interface SourceRef {
  label: string;
  url: string;
  description: string;
  quote: string;
}

export interface Site {
  id: string;
  name: string;
  kind: string;
  lat_deg: number;
  lon_deg_east: number;
  reference_height_m?: number | null;
  reference_height_source?: string | null;
  notes?: string | null;
  sources: SourceRef[];
}

export interface PendingRegion {
  name: string;
  status: string;
  reason: string;
  reference_url?: string | null;
}

export interface SitesResponse {
  catalogue_version: string;
  policy: string;
  reference_sphere_radius_m: number;
  sites: Site[];
  pending_regions: PendingRegion[];
}

export interface DemWindowInfo {
  window_id: string;
  product_id: string;
  pixel_size_m: number;
  width: number;
  height: number;
  source_url: string;
  sha256: string;
  z_min_m: number;
  z_max_m: number;
  valid_fraction: number;
  overview_level: number | null;
}

export interface HorizonResponse {
  data_class: string;
  observer: {
    site_id: string | null;
    lat_deg: number;
    lon_deg_east: number;
    ground_height_m: number;
    observer_height_above_surface_m: number;
    observer_height_is_default_assumption: boolean;
    catalogue_reference_height_m: number | null;
  };
  n_azimuths: number;
  azimuth_deg: number[];
  horizon_elevation_deg: (number | null)[];
  horizon_distance_km: (number | null)[];
  truncated: boolean[];
  data_gap: boolean[];
  summary: Record<string, number | null>;
  notes: string[];
  provenance: { windows: { window_id: string; product_id: string; pixel_size_m: number; sha256: string; source_url: string }[] };
  served_from: string;
}

export interface Band {
  earliest_utc: string;
  latest_utc: string;
  width_s: number;
  complete: boolean;
}

export interface Interval {
  start_utc: string;
  end_utc: string;
  start_s: number;
  end_s: number;
  duration_s: number;
  open_start: boolean;
  open_end: boolean;
  start_band?: Band | null;
  end_band?: Band | null;
}

export interface IntervalMetrics {
  window_s: number;
  total_visible_s: number;
  visible_fraction: number | null;
  n_visible_intervals: number;
  longest_visible_s_closed_only: number | null;
  longest_visible_s_including_open: number | null;
  longest_visible_includes_open_interval: boolean;
  longest_not_visible_s_closed_only: number | null;
  longest_not_visible_s_including_open: number | null;
  longest_not_visible_includes_open_interval: boolean;
}

export interface Transition {
  time_utc: string;
  time_s: number;
  to: "visible" | "not_visible";
}

export interface BoundaryBand extends Band {
  nominal_time_s: number;
  band_width_s: number;
  displaced_runs_without_matching_event: number;
  band_complete: boolean;
}

export interface PositionSensitivityEntry {
  status: string;
  reason?: string;
  metric_bands?: Record<string, [number | null, number | null]>;
  boundary_bands?: BoundaryBand[];
  events_only_in_displaced_runs?: number;
  max_boundary_band_width_s?: number;
}

export interface StateEntry {
  intervals: Interval[];
  not_visible_intervals: Interval[];
  transitions: Transition[];
  metrics: IntervalMetrics;
  is_headline?: boolean;
  position_sensitivity?: PositionSensitivityEntry;
}

export interface GeometricEntry {
  definition: string;
  intervals: Interval[];
  not_visible_intervals: Interval[];
  transitions: Transition[];
  metrics: IntervalMetrics;
  position_sensitivity: { status: string; reason?: string };
}

export interface BodySeries {
  times_s: number[];
  azimuth_deg: number[];
  elevation_deg: number[];
  angular_radius_deg: number[];
  terrain_horizon_at_centre_deg: number[];
  geometric_headline_above_local_horizontal: boolean[];
  centre_visible: boolean[];
  any_part_visible: boolean[];
  fully_visible: boolean[];
  headline_visible: boolean[];
  horizon_complete: boolean[];
  unverified_visible: boolean[];
  position_sensitivity_deg: number[] | null;
  headline_state_robust_to_position: boolean[] | null;
}

export interface VisibilityBody {
  headline_state: string;
  series?: BodySeries;
  terrain_effect: {
    headline_visible_steps: number;
    geometric_headline_steps: number;
    steps_blocked_by_terrain_only: number;
    n_steps: number;
  };
  completeness: {
    steps_with_incomplete_horizon: number;
    unverified_visible_steps: number;
    visibility_is_upper_bound: boolean;
  };
  states?: { centre: StateEntry; any_part: StateEntry; fully: StateEntry };
  geometric?: GeometricEntry;
  headline?: { state: string; intervals: Interval[]; not_visible_intervals: Interval[]; metrics: IntervalMetrics; position_sensitivity: PositionSensitivityEntry };
}

export interface PositionSensitivityBlock {
  status: "computed" | "not_computed";
  reason?: string;
  data_class: string;
  kind: string;
  assumed_position_uncertainty_m: number | null;
  assumption: string | null;
  n_directions: number | null;
  method: string;
  limitations: string;
}

export interface VisibilityResponse {
  data_class: string;
  observer: {
    site_id: string | null;
    lat_deg: number;
    lon_deg_east: number;
    ground_height_m: number;
    observer_height_above_surface_m: number;
    observer_height_is_default_assumption: boolean;
  };
  window: { start_utc: string; end_utc: string; step_seconds: number; n_samples: number; note: string };
  definitions: { headline: { sun: string; earth: string }; states: string[]; disc_model: string; horizon_interpolation: string };
  horizon: { az_step_deg: number; windows: string[]; summary: Record<string, number | null>; served_from: string };
  bodies: Record<"sun" | "earth", VisibilityBody>;
  position_sensitivity: PositionSensitivityBlock;
  limitations: string[];
}

export interface EphemerisProvenance {
  model_version?: string;
  kernels?: { file: string; sha256: string }[];
  frame?: string;
  aberration_correction?: string;
  bodies?: Record<string, unknown>;
  unmodelled?: string[];
}

export interface EphemerisBody {
  azimuth_deg: number[];
  elevation_deg: number[];
  range_km: number[];
  angular_diameter_deg: number[];
}

export interface EphemerisPositionResponse {
  provenance: EphemerisProvenance;
  notes: string[];
  bodies: Record<string, EphemerisBody>;
  observer: { lat_deg: number; lon_deg_east: number; height_m: number };
}

// ---- scenarios ----
export interface Banded {
  nominal: number | null;
  band: [number | null, number | null];
}

export interface LongestEntry {
  closed_only: number | null;
  including_open: number | null;
  includes_open_interval: boolean;
  band_closed_only?: [number | null, number | null];
  band_including_open?: [number | null, number | null];
}

export interface ScenarioEvent {
  type: "becomes_visible" | "becomes_not_visible";
  time_utc: string;
  time_s: number;
  band: { earliest_utc: string; latest_utc: string; width_s: number; complete: boolean };
}

export interface ScenarioBody {
  headline_state: string;
  terrain_corrected: {
    total_visible_s: Banded;
    visible_fraction: Banded;
    n_visible_intervals: Banded;
    longest_visible_s: LongestEntry;
    longest_not_visible_s: LongestEntry;
    events: ScenarioEvent[];
    open_intervals: { visible: number; not_visible: number; note: string };
  };
  geometric: {
    definition: string;
    visible_fraction: { nominal: number | null };
    total_visible_s: { nominal: number | null };
    longest_not_visible_s: { including_open: number | null; includes_open_interval: boolean };
  };
  terrain_effect: {
    steps_blocked_by_terrain_only: number;
    visible_s_terrain_minus_geometric: { nominal: number; band: [number, number] };
    note: string;
  };
  completeness: { visibility_is_upper_bound: boolean };
}

export interface ScenarioSpecOut {
  site_id: string | null;
  lat_deg: number;
  lon_deg_east: number;
  start_utc: string;
  duration_days: number;
  step_seconds: number;
  observer_height_m: number;
  observer_height_is_default_assumption: boolean;
  position_uncertainty_m: number;
  label: string | null;
}

export interface ScenarioResult {
  id: string;
  status: "supported" | "terrain_data_insufficient";
  spec: ScenarioSpecOut;
  reason?: string;
  note?: string;
  bodies?: Record<"sun" | "earth", ScenarioBody>;
  served_from: string;
}

export interface DeltaMetric {
  baseline: number | null;
  scenario: number | null;
  delta: number | null;
  delta_band: [number, number] | null;
  distinguishable_from_zero: boolean | null;
  involves_open_interval: boolean;
  delta_band_method?: string;
  note?: string;
}

export interface ScenarioDelta {
  baseline_id: string;
  scenario_id: string;
  delta_band_method: "paired" | "independent_interval_arithmetic";
  bodies: Record<
    "sun" | "earth",
    {
      terrain_corrected: Record<string, DeltaMetric>;
      geometric: Record<string, { baseline: number | null; scenario: number | null; delta: number | null }>;
      summary: string[];
    }
  >;
}

export interface RankingRow {
  rank: number;
  scenario_id: string;
  label: string | null;
  site_id: string | null;
  start_utc: string;
  nominal: number | null;
  band: [number | null, number | null] | null;
  includes_open_interval: boolean;
  distinguishable_from_next: boolean | null;
}

export interface CompareResponse {
  baseline_id: string;
  scenarios: ScenarioResult[];
  excluded_terrain_data_insufficient: { scenario_id: string; label: string | null; site_id: string | null; reason: string }[];
  deltas_vs_baseline: ScenarioDelta[];
  rankings: { criterion: string; better: string; method: string; ranking: RankingRow[] }[];
  notes: string[];
  reading_guide: string[];
}

export interface DelayRow {
  offset_days: number;
  scenario_id: string;
  start_utc: string;
  sun: DelayBodyRow;
  earth: DelayBodyRow;
}

export interface DelayBodyRow {
  terrain_corrected_visible_fraction: Banded;
  geometric_visible_fraction: number | null;
  terrain_corrected_longest_not_visible_s: { nominal: number | null; band: [number | null, number | null]; includes_open_interval: boolean };
  geometric_longest_not_visible_s: { nominal: number | null; includes_open_interval: boolean };
}

export interface DelayResponse {
  status: "supported" | "terrain_data_insufficient";
  reason?: string;
  note?: string;
  baseline?: ScenarioResult;
  delays?: { offset_days: number; scenario: ScenarioResult; delta_vs_baseline: ScenarioDelta }[];
  summary_table?: DelayRow[];
  notes?: string[];
}

export interface ProvenanceResponse {
  model_version: string;
  git_commit: string | null;
  software: Record<string, string>;
  spice_kernels: { file: string; role: string; sha256: string; source_url: string }[] | null;
  spice_kernels_error?: string;
  spice_frame?: string | null;
  dem_windows: DemWindowInfo[];
  site_catalogue: { catalogue_version: string; sha256: string | null; sites: { id: string; name: string; kind: string; sources: { label: string; url: string }[] }[] };
  validation_fixtures: Record<string, { file: string; sha256: string | null; note: string }>;
  constants: Record<string, number | string>;
  data_classes: Record<string, string>;
}
