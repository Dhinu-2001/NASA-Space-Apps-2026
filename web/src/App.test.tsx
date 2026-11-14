import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const health = { status: "ok", service: "lunarnav-api", model_version: "0.1.0-stage1", env: "test", time_utc: "2026-11-14T00:00:00Z" };
const version = {
  model_version: "0.1.0-stage1",
  api_version: "0.1.0",
  stage: 1,
  notice: "Foundation skeleton only.",
  capabilities: [{ key: "ephemeris", title: "Sun and Earth azimuth/elevation (SPICE)", stage: 3, status: "not_implemented" }],
};

afterEach(() => vi.restoreAllMocks());

describe("App (Stage 1)", () => {
  it("shows backend status and labels unbuilt science as not implemented", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => ({ ok: true, json: async () => (url.endsWith("/health") ? health : version) })));
    render(<App />);
    expect(await screen.findByTestId("health-status")).toHaveTextContent("ok");
    expect(screen.getByText("not implemented")).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent(/No scientific results/);
  });

  it("shows an error state when the backend is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("network"); }));
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/Backend unavailable/);
  });
});
