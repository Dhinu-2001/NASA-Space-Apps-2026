import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const health = { status: "ok", service: "lunarnav-api", model_version: "0.2.0-stage2", env: "test", time_utc: "2026-11-14T00:00:00Z" };
const version = {
  model_version: "0.2.0-stage2",
  api_version: "0.1.0",
  stage: 2,
  notice: "Stage 2: site catalogue and DEM elevation lookup only. No ephemeris, horizon or visibility results are produced yet.",
  capabilities: [{ key: "ephemeris", title: "Sun and Earth azimuth/elevation (SPICE)", stage: 3, status: "not_implemented" }],
};

afterEach(() => vi.restoreAllMocks());

describe("App", () => {
  it("shows backend status and labels unbuilt science as not implemented", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => ({ ok: true, json: async () => (url.endsWith("/health") ? health : version) })));
    render(<App />);
    expect(await screen.findByTestId("health-status")).toHaveTextContent("ok");
    expect(screen.getByText("not implemented")).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent(/No ephemeris, horizon or visibility results/);
  });

  it("shows an error state when the backend is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("network"); }));
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/Backend unavailable/);
  });
});
