import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { baseRoutes, stubFetch } from "./testFixtures";

// Regression tests for "the Compute button sometimes sends no request" (reported 2026-11-15):
//   1. choosing a mission profile in the dropdown did not fill the form (only the separate Apply button did), so
//      Compute ran with the old values and, because results were keyed by the inputs, sent nothing;
//   2. pressing Compute/Run again with unchanged inputs sent nothing, silently.

type Call = { method: string; path: string; body: Record<string, unknown> | null };

function renderApp(hash: string) {
  const s = stubFetch(baseRoutes());
  const calls: Call[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    calls.push({ method: init?.method ?? "GET", path: url.replace(/^\/api/, "").split("?")[0], body: init?.body ? JSON.parse(init.body) : null });
    return s.fn(url, init);
  }));
  window.history.replaceState(null, "", `/${hash}`);
  render(<App />);
  return calls;
}
const count = (calls: Call[], path: string) => calls.filter((c) => c.path === path).length;
const profileSelect = (id: string) => screen.getByLabelText("Profile", { selector: `#${id}-select` }) as HTMLSelectElement;

beforeEach(() => window.localStorage.clear());
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
  window.localStorage.clear();
});

describe("Site & time: Compute always runs", () => {
  it("pressing Compute again with unchanged inputs sends the requests again", async () => {
    const calls = renderApp("#view");
    await screen.findByTestId("health-status");
    fireEvent.click(screen.getByRole("button", { name: "Compute" }));
    await screen.findByTestId("now-sun");
    const after1 = { horizon: count(calls, "/horizon/profile"), series: count(calls, "/visibility/series"), at: count(calls, "/visibility/at"), eph: count(calls, "/ephemeris/position") };
    expect(after1).toEqual({ horizon: 1, series: 1, at: 1, eph: 1 });
    fireEvent.click(screen.getByRole("button", { name: "Compute" }));
    await waitFor(() => expect(count(calls, "/visibility/series")).toBe(2));
    expect(count(calls, "/horizon/profile")).toBe(2);
    expect(count(calls, "/visibility/at")).toBe(2);
    expect(count(calls, "/ephemeris/position")).toBe(2);
  });

  it("choosing a profile in the dropdown fills the form at once, and Compute then uses it (no Apply press needed)", async () => {
    const calls = renderApp("#view");
    await screen.findByTestId("health-status");
    expect(screen.getByLabelText(/Window length/)).toHaveValue("30");
    fireEvent.change(profileSelect("view-profile"), { target: { value: "one-lunar-day" } });
    expect(screen.getByLabelText(/Window length/)).toHaveValue("14");                       // filled by the selection itself
    fireEvent.change(profileSelect("view-profile"), { target: { value: "tight-position" } });
    expect(screen.getByLabelText(/Window length/)).toHaveValue("30");
    expect(screen.getByLabelText(/Assumed landing-position uncertainty/)).toHaveValue("20");
    fireEvent.change(profileSelect("view-profile"), { target: { value: "one-lunar-day" } });
    fireEvent.click(screen.getByRole("button", { name: "Compute" }));
    await screen.findByTestId("now-sun");
    const series = calls.find((c) => c.path === "/visibility/series")!;
    expect(series.body).toMatchObject({ start_utc: "2027-01-15T00:00:00Z", end_utc: "2027-01-29T00:00:00Z", position_uncertainty_m: 100 });   // 14 days
  });

  it("the Apply profile button still re-applies the profile after the fields were edited", async () => {
    renderApp("#view");
    await screen.findByTestId("health-status");
    fireEvent.change(profileSelect("view-profile"), { target: { value: "one-lunar-day" } });
    fireEvent.change(screen.getByLabelText(/Window length/), { target: { value: "5" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply profile" }));
    expect(screen.getByLabelText(/Window length/)).toHaveValue("14");
  });
});

describe("the other computing tabs also run on every press", () => {
  const cases: [string, string, string, string][] = [
    ["Compare", "#compare", "Compare", "/scenarios/compare"],
    ["Landing sites", "#sites", "Compare sites", "/scenarios/compare"],
    ["Explore sweeps", "#explore", "Run sweep", "/scenarios/compare"],
    ["Delay simulator", "#delay", "Simulate delays", "/scenarios/delay"],
  ];
  for (const [name, hash, button, path] of cases) {
    it(`${name}: pressing "${button}" twice with unchanged inputs sends two requests`, async () => {
      const calls = renderApp(hash);
      await screen.findByTestId("health-status");
      fireEvent.click(screen.getByRole("button", { name: button }));
      await waitFor(() => expect(count(calls, path)).toBe(1));
      fireEvent.click(screen.getByRole("button", { name: button }));
      await waitFor(() => expect(count(calls, path)).toBe(2));
    });
  }

  it("Compare: choosing a profile fills the window length and band at once", async () => {
    renderApp("#compare");
    await screen.findByTestId("health-status");
    fireEvent.change(profileSelect("cmp-profile"), { target: { value: "loose-position" } });
    expect(screen.getByLabelText(/Window length/)).toHaveValue("30");
    expect(screen.getByLabelText(/Position uncertainty/)).toHaveValue("200");
  });
});
