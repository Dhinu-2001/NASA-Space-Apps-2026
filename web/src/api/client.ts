// Typed API client. The frontend only fetches and displays backend results; it never computes astronomy,
// terrain or visibility (decision C4).
import type { components } from "./schema";
import type {
  CompareResponse,
  DelayResponse,
  DemWindowInfo,
  EphemerisPositionResponse,
  HorizonResponse,
  SitesResponse,
  VisibilityResponse,
} from "./types";

export type Health = components["schemas"]["HealthResponse"];
export type VersionInfo = components["schemas"]["VersionResponse"];
export type ApiErrorBody = components["schemas"]["ErrorBody"];

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: ApiErrorBody | null,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const BASE = import.meta.env.VITE_API_BASE ?? "/api";

async function request<T>(method: "GET" | "POST", path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      method,
      signal,
      headers: { accept: "application/json", ...(body !== undefined ? { "content-type": "application/json" } : {}) },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError(0, null, "Cannot reach the backend API.");
  }
  if (!res.ok) {
    let errBody: ApiErrorBody | null = null;
    try {
      errBody = (await res.json()) as ApiErrorBody;
    } catch {
      /* non-JSON error */
    }
    throw new ApiError(res.status, errBody, errBody?.message ?? `HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}

const qs = (p: Record<string, string | number | boolean | null | undefined>) => {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(p)) if (v !== null && v !== undefined && v !== "") u.set(k, String(v));
  return u.toString();
};

export interface SiteSel {
  site_id?: string | null;
  lat?: number | null;
  lon?: number | null;
}

export interface ScenarioCommon {
  duration_days?: number;
  step_seconds?: number;
  observer_height_m?: number | null;
  position_uncertainty_m?: number;
  az_step_deg?: number;
}

export const api = {
  health: (signal?: AbortSignal) => request<Health>("GET", "/health", undefined, signal),
  version: (signal?: AbortSignal) => request<VersionInfo>("GET", "/version", undefined, signal),
  sites: (signal?: AbortSignal) => request<SitesResponse>("GET", "/sites", undefined, signal),
  demWindows: (signal?: AbortSignal) => request<DemWindowInfo[]>("GET", "/dem/windows", undefined, signal),
  ephemerisProvenance: (signal?: AbortSignal) =>
    request<EphemerisPositionResponse>("GET", `/ephemeris/position?${qs({ site_id: "im2-athena", time_utc: "2027-01-15T00:00:00Z" })}`, undefined, signal),
  ephemerisPosition: (sel: SiteSel, timeUtc: string, signal?: AbortSignal) =>
    request<EphemerisPositionResponse>(
      "GET",
      `/ephemeris/position?${qs({ time_utc: timeUtc, site_id: sel.site_id, lat: sel.lat, lon: sel.lon })}`,
      undefined,
      signal,
    ),
  horizon: (sel: SiteSel, observerHeightM: number | null, signal?: AbortSignal) =>
    request<HorizonResponse>(
      "GET",
      `/horizon/profile?${qs({ site_id: sel.site_id, lat: sel.lat, lon: sel.lon, observer_height_m: observerHeightM })}`,
      undefined,
      signal,
    ),
  visibilityAt: (sel: SiteSel, timeUtc: string, observerHeightM: number | null, positionUncertaintyM: number, signal?: AbortSignal) =>
    request<VisibilityResponse>(
      "GET",
      `/visibility/at?${qs({
        time_utc: timeUtc,
        site_id: sel.site_id,
        lat: sel.lat,
        lon: sel.lon,
        observer_height_m: observerHeightM,
        position_uncertainty_m: positionUncertaintyM,
      })}`,
      undefined,
      signal,
    ),
  visibilitySeries: (
    sel: SiteSel,
    startUtc: string,
    endUtc: string,
    stepSeconds: number,
    observerHeightM: number | null,
    positionUncertaintyM: number,
    signal?: AbortSignal,
  ) =>
    request<VisibilityResponse>(
      "POST",
      "/visibility/series",
      {
        site: { site_id: sel.site_id ?? null, lat: sel.lat ?? null, lon: sel.lon ?? null },
        start_utc: startUtc,
        end_utc: endUtc,
        step_seconds: stepSeconds,
        observer_height_m: observerHeightM,
        position_uncertainty_m: positionUncertaintyM,
        include_series: true,
      },
      signal,
    ),
  compare: (
    sites: SiteSel[],
    startUtcList: string[],
    common: ScenarioCommon,
    baselineIndex: number,
    signal?: AbortSignal,
  ) =>
    request<CompareResponse>(
      "POST",
      "/scenarios/compare",
      {
        sites: sites.map((s) => ({ site_id: s.site_id ?? null, lat: s.lat ?? null, lon: s.lon ?? null })),
        start_utc_list: startUtcList,
        baseline_index: baselineIndex,
        ...common,
      },
      signal,
    ),
  delay: (site: SiteSel, baselineStartUtc: string, offsetsDays: number[], common: ScenarioCommon, signal?: AbortSignal) =>
    request<DelayResponse>(
      "POST",
      "/scenarios/delay",
      {
        site: { site_id: site.site_id ?? null, lat: site.lat ?? null, lon: site.lon ?? null },
        baseline_start_utc: baselineStartUtc,
        offsets_days: offsetsDays,
        ...common,
      },
      signal,
    ),
};
