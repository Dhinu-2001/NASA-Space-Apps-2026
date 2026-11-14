// Typed API client. Types come from the backend's OpenAPI document (npm run gen:api).
// The frontend only fetches and displays backend results; it never computes astronomy (decision C4).
import type { components } from "./schema";

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

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, { signal, headers: { accept: "application/json" } });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError(0, null, "Cannot reach the backend API.");
  }
  if (!res.ok) {
    let body: ApiErrorBody | null = null;
    try {
      body = (await res.json()) as ApiErrorBody;
    } catch {
      /* non-JSON error */
    }
    throw new ApiError(res.status, body, body?.message ?? `HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}

export const api = {
  health: (signal?: AbortSignal) => getJson<Health>("/health", signal),
  version: (signal?: AbortSignal) => getJson<VersionInfo>("/version", signal),
};
