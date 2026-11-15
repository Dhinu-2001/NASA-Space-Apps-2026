import { readFileSync } from "node:fs";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import type { CompareResponse, ScenarioResult } from "./api/types";
import { SWEEP_PARAMS, buildScenarios, checkCount, dateRange, linspace, parseDateList, parseNumberList, toCsv, valueLabel, type SweepBase } from "./sweep";
import { baseRoutes, scenarioSupported } from "./testFixtures";

// ------------------------------------------------------------------ pure request-construction helpers

const BASE: SweepBase = { site: { site_id: "im2-athena" }, siteLabel: "IM-2", startUtc: "2027-01-15T00:00:00Z", days: 30, bandM: 100, heightM: null, stepS: 900 };

describe("sweep request construction (no science, only turning typed values into ordinary scenario requests)", () => {
  it("varies exactly ONE parameter and leaves every other setting at the base value", () => {
    const cases: [typeof SWEEP_PARAMS[number]["id"], (string | number)[], keyof ReturnType<typeof buildScenarios>[number]][] = [
      ["band", [20, 200], "position_uncertainty_m"], ["length", [7, 14], "duration_days"], ["height", [0.5, 5], "observer_height_m"],
      ["step", [300, 3600], "step_seconds"], ["start", ["2027-02-01T00:00:00Z", "2027-03-01T00:00:00Z"], "start_utc"],
    ];
    for (const [param, values, field] of cases) {
      const reqs = buildScenarios(BASE, param, values);
      expect(reqs.map((r) => r[field])).toEqual(values);
      const fixed = { start_utc: BASE.startUtc, duration_days: 30, position_uncertainty_m: 100, observer_height_m: null, step_seconds: 900 };
      for (const r of reqs) for (const [k, v] of Object.entries(fixed)) if (k !== field) expect(r[k as keyof typeof r]).toEqual(v);
      expect(reqs.every((r) => r.site.site_id === "im2-athena" && r.label === valueLabel(param, values[reqs.indexOf(r)]))).toBe(true);
    }
  });

  it("builds evenly spaced values and dates, parses lists, and rejects what it cannot read with a message", () => {
    expect(linspace(20, 500, 5)).toEqual([20, 140, 260, 380, 500]);
    expect(linspace(5, 5, 1)).toEqual([5]);
    expect(dateRange("2027-01-15T00:00:00Z", "2027-01-17T00:00:00Z", 3)).toEqual(["2027-01-15T00:00:00Z", "2027-01-16T00:00:00Z", "2027-01-17T00:00:00Z"]);
    expect(parseNumberList("1, 2.5; 3")).toEqual({ ok: true, value: [1, 2.5, 3] });
    expect(parseNumberList("1, two")).toEqual({ ok: false, error: "“two” is not a number." });
    expect(parseNumberList("  ")).toMatchObject({ ok: false });
    expect(parseDateList("2027-01-15, 2027-02-03T12:30")).toEqual({ ok: true, value: ["2027-01-15T00:00:00Z", "2027-02-03T12:30:00Z"] });
    expect(parseDateList("15/01/2027")).toMatchObject({ ok: false });
    expect(parseDateList("2027-13-45")).toMatchObject({ ok: false });
    expect(checkCount(1)).toMatch(/at least 2/);
    expect(checkCount(13)).toMatch(/At most 12/);
    expect(checkCount(12)).toBeNull();
  });

  it("exports the table with the backend's numbers as received and no number for an insufficient scenario", () => {
    const ok = scenarioSupported(0.486, 0.808);
    const insufficient: ScenarioResult = { id: "x", status: "terrain_data_insufficient", served_from: "disk", spec: ok.spec, reason: 'no "terrain", really' };
    const csv = toCsv("band", [20, 50], [ok, insufficient]).trim().split("\n");
    expect(csv[0].split(",")).toHaveLength(15);
    expect(csv[1].split(",")).toHaveLength(15);
    expect(csv[1]).toContain("0.486");                           // nominal exactly as received
    expect(csv[1]).toContain("0.808");
    expect(csv[2]).toBe(["50 m", "terrain_data_insufficient", ...Array(12).fill(""), '"no ""terrain"", really"'].join(","));
  });
});

// ------------------------------------------------------------------ the tab, against a recording fetch stub

const sweepResponse = (n: number, opts: { insufficientAt?: number[] } = {}): CompareResponse => {
  const scenarios: ScenarioResult[] = Array.from({ length: n }, (_, i) => {
    if (opts.insufficientAt?.includes(i)) {
      return { id: `i${i}`, status: "terrain_data_insufficient", served_from: "disk", spec: scenarioSupported().spec, reason: "terrain coverage is insufficient to certify the horizon (1440 truncated)", reason_code: "TERRAIN_NOT_CERTIFIED" } as ScenarioResult;
    }
    const s = scenarioSupported(0.486, 0.808);
    const w = 0.004 * (i + 1);                                   // a band that widens with the swept value
    s.bodies!.sun.terrain_corrected.visible_fraction = { nominal: 0.486, band: [0.486 - w, 0.486 + w / 4] };
    return { ...s, id: `s${i}`, served_from: i % 2 ? "disk" : "computed" };
  });
  return { baseline_id: scenarios[0].id, scenarios, excluded_terrain_data_insufficient: [], deltas_vs_baseline: [], rankings: [], notes: [], reading_guide: ["Sites without terrain support are excluded, never ranked or estimated."] };
};

type Call = { method: string; path: string; body: any };   // eslint-disable-line @typescript-eslint/no-explicit-any
const compareCalls = (calls: Call[]) => calls.filter((c) => c.path === "/scenarios/compare");

function renderApp(opts: { compare?: (body: any) => { ok: boolean; status?: number; body: unknown }; hash?: string } = {}) {   // eslint-disable-line @typescript-eslint/no-explicit-any
  const routes = baseRoutes() as Record<string, unknown>;
  const calls: Call[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const path = url.replace(/^\/api/, "").split("?")[0];
    const body = init?.body ? JSON.parse(init.body) : null;
    calls.push({ method: init?.method ?? "GET", path, body });
    if (path === "/scenarios/compare") {
      const dflt = (b: any): { ok: boolean; status?: number; body: unknown } => ({ ok: true, body: sweepResponse(b.scenarios.length) });   // eslint-disable-line @typescript-eslint/no-explicit-any
      const r = (opts.compare ?? dflt)(body);
      return { ok: r.ok, status: r.status ?? 200, json: async () => r.body };
    }
    return path in routes ? { ok: true, json: async () => routes[path] } : { ok: false, status: 404, json: async () => ({ code: "NOT_FOUND", message: path, field: null, details: {}, request_id: null }) };
  }));
  window.history.replaceState(null, "", `/${opts.hash ?? "#explore"}`);
  render(<App />);
  return calls;
}

const run = () => fireEvent.click(screen.getByRole("button", { name: "Run sweep" }));
const setParam = (v: string) => fireEvent.change(screen.getByLabelText("Parameter to vary"), { target: { value: v } });

beforeEach(() => window.localStorage.clear());
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
  window.localStorage.clear();
});

describe("Explore sweeps tab", () => {
  it("makes no request until Run, and previews exactly which scenarios will be requested", async () => {
    const calls = renderApp();
    await screen.findByTestId("health-status");
    expect(compareCalls(calls)).toHaveLength(0);
    expect(screen.getByTestId("sweep-preview")).toHaveTextContent("Will request 5 scenarios: 20 m · 50 m · 100 m · 200 m · 500 m");
    fireEvent.change(screen.getByLabelText(/^Values/), { target: { value: "10, 30" } });
    expect(screen.getByTestId("sweep-preview")).toHaveTextContent("Will request 2 scenarios: 10 m · 30 m");
    expect(compareCalls(calls)).toHaveLength(0);
  });

  it("sends ONE existing /scenarios/compare request with explicit scenarios that differ only in the swept parameter", async () => {
    const calls = renderApp();
    await screen.findByTestId("health-status");
    run();
    await screen.findByTestId("sweep-table");
    const sent = compareCalls(calls);
    expect(sent).toHaveLength(1);
    const b = sent[0].body;
    expect(Object.keys(b).sort()).toEqual(["baseline_index", "scenarios"]);                // the endpoint's explicit-list form, no sites/dates form
    expect(b.baseline_index).toBe(0);
    expect(b.scenarios.map((s: any) => s.position_uncertainty_m)).toEqual([20, 50, 100, 200, 500]);   // eslint-disable-line @typescript-eslint/no-explicit-any
    for (const s of b.scenarios) expect(s).toMatchObject({ site: { site_id: "im2-athena" }, start_utc: "2027-01-15T00:00:00Z", duration_days: 30, step_seconds: 900, observer_height_m: null });
    expect(calls.filter((c) => c.path.startsWith("/scenarios") || c.path.startsWith("/visibility") || c.path.startsWith("/horizon"))).toHaveLength(1);
  });

  it("sweeps start dates over a range filled in from two dates, with a custom baseline", async () => {
    const calls = renderApp();
    await screen.findByTestId("health-status");
    setParam("start");
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2027-01-15T00:00" } });
    fireEvent.change(screen.getByLabelText("To"), { target: { value: "2027-01-19T00:00" } });
    fireEvent.change(screen.getByLabelText(/^Points/), { target: { value: "3" } });
    fireEvent.click(screen.getByRole("button", { name: "Fill list" }));
    expect(screen.getByLabelText(/^Values/)).toHaveValue("2027-01-15T00:00, 2027-01-17T00:00, 2027-01-19T00:00");
    fireEvent.change(screen.getByLabelText("Baseline for the differences"), { target: { value: "2" } });
    run();
    await screen.findByTestId("sweep-table");
    const b = compareCalls(calls)[0].body;
    expect(b.scenarios.map((s: any) => s.start_utc)).toEqual(["2027-01-15T00:00:00Z", "2027-01-17T00:00:00Z", "2027-01-19T00:00:00Z"]);   // eslint-disable-line @typescript-eslint/no-explicit-any
    expect(b.baseline_index).toBe(2);
    expect(b.scenarios.every((s: any) => s.position_uncertainty_m === 100)).toBe(true);   // eslint-disable-line @typescript-eslint/no-explicit-any
  });

  it("accepts a window defined by start and end dates, and sweeps window length", async () => {
    const calls = renderApp();
    await screen.findByTestId("health-status");
    fireEvent.click(screen.getByLabelText(/Define the window by an end date/));
    fireEvent.change(screen.getByLabelText("Window end (UTC)"), { target: { value: "2027-01-25T00:00" } });
    run();
    await screen.findByTestId("sweep-table");
    expect(compareCalls(calls)[0].body.scenarios.every((s: any) => s.duration_days === 10)).toBe(true);   // eslint-disable-line @typescript-eslint/no-explicit-any
    setParam("length");
    run();
    await waitFor(() => expect(compareCalls(calls)).toHaveLength(2));
    expect(compareCalls(calls)[1].body.scenarios.map((s: any) => s.duration_days)).toEqual([7, 14, 29.5, 45, 60]);   // eslint-disable-line @typescript-eslint/no-explicit-any
  });

  it("blocks bad input before any request and says why", async () => {
    const calls = renderApp();
    await screen.findByTestId("health-status");
    fireEvent.change(screen.getByLabelText(/^Values/), { target: { value: "5" } });
    run();
    expect(screen.getByRole("alert")).toHaveTextContent(/at least 2/);
    fireEvent.change(screen.getByLabelText(/^Values/), { target: { value: "1,2,3,4,5,6,7,8,9,10,11,12,13" } });
    run();
    expect(screen.getByRole("alert")).toHaveTextContent(/At most 12/);
    fireEvent.change(screen.getByLabelText(/^Values/), { target: { value: "10, abc" } });
    expect(screen.getByTestId("sweep-preview")).toHaveTextContent("“abc” is not a number.");
    fireEvent.change(screen.getByLabelText(/^Values/), { target: { value: "10, 20" } });
    fireEvent.change(screen.getByLabelText("Position uncertainty (m)"), { target: { value: "0" } });
    run();
    expect(screen.getByRole("alert")).toHaveTextContent(/above 0 m/);
    expect(compareCalls(calls)).toHaveLength(0);
  });

  it("shows every number with its band beside the geometric value, and marks the baseline and cache state", async () => {
    renderApp();
    await screen.findByTestId("health-status");
    run();
    const table = await screen.findByTestId("sweep-table");
    const rows = within(table).getAllByTestId("sweep-row");
    expect(rows).toHaveLength(5);
    expect(rows[0]).toHaveTextContent("20 m");
    expect(rows[0]).toHaveTextContent("baseline");
    expect(rows[0]).toHaveTextContent("computed now");
    expect(rows[1]).toHaveTextContent("from cache");
    expect(rows[0]).toHaveTextContent("48.6 %");
    expect(rows[0]).toHaveTextContent(/band 48\.2 % to 48\.7 %/);          // 0.486 -0.004 .. +0.001
    expect(rows[4]).toHaveTextContent(/band 46\.6 % to 49\.1 %/);          // the band widens with the swept value
    expect(rows[0]).toHaveTextContent("53.3 %");                           // geometric beside it
    expect(screen.getAllByRole("img", { name: /terrain-corrected visible fraction with its position band/ })).toHaveLength(2);
  });

  it("spaces numeric sweeps evenly by default and dates to scale, switchable without any request", async () => {
    const calls = renderApp();
    await screen.findByTestId("health-status");
    run();
    await screen.findByTestId("sweep-table");
    const cx = () => [...document.querySelectorAll("svg[role='img'] circle")].slice(0, 5).map((c) => Number(c.getAttribute("cx")));
    const gaps = (a: number[]) => a.slice(1).map((v, i) => Number((v - a[i]).toFixed(1)));
    expect(new Set(gaps(cx())).size).toBe(1);                                    // 20, 50, 100, 200, 500 m: evenly spaced
    const before = calls.length;
    fireEvent.click(screen.getByLabelText(/Space the points evenly/));
    expect(new Set(gaps(cx())).size).toBeGreaterThan(1);                          // to scale: the gaps differ
    expect(calls.length).toBe(before);
  });

  it("leaves a labelled gap for a scenario with insufficient terrain: no figure, no interpolation across it", async () => {
    renderApp({ compare: (b) => ({ ok: true, body: sweepResponse(b.scenarios.length, { insufficientAt: [2] }) }) });
    await screen.findByTestId("health-status");
    run();
    const table = await screen.findByTestId("sweep-table");
    const row = within(table).getByTestId("sweep-row-insufficient");
    expect(row).toHaveTextContent("100 m");
    expect(row).toHaveTextContent("Terrain data insufficient");
    expect(row.textContent).not.toMatch(/\d\d\.\d %/);
    expect(row).toHaveTextContent(/1440 truncated/);
    expect(document.querySelector("svg")!.innerHTML).toContain("n/a");     // a gap marker in the chart, not a point
  });

  it("says so when no scenario has terrain support, and draws nothing", async () => {
    renderApp({ compare: (b) => ({ ok: true, body: sweepResponse(b.scenarios.length, { insufficientAt: [0, 1, 2, 3, 4] }) }) });
    await screen.findByTestId("health-status");
    run();
    expect(await screen.findByTestId("sweep-all-insufficient")).toHaveTextContent(/nothing to plot/);
    expect(screen.queryAllByRole("img", { name: /terrain-corrected visible fraction/ })).toHaveLength(0);
  });

  it("makes no further request for zoom, CSV, details or form edits; each explicit Run makes exactly one (C4 request-count test)", async () => {
    const calls = renderApp();
    await screen.findByTestId("health-status");
    run();
    await screen.findByTestId("sweep-table");
    const before = calls.length;
    const create = vi.fn(() => "blob:x");
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: create, revokeObjectURL: vi.fn() }));
    fireEvent.click(screen.getByLabelText(/Zoom the y-axis/));
    fireEvent.click(screen.getByRole("button", { name: "Download this table (CSV)" }));
    fireEvent.click(screen.getByText(/Differences from the baseline, and rankings/));
    fireEvent.change(screen.getByLabelText(/^Values/), { target: { value: "10, 20, 30" } });
    setParam("height");
    expect(create).toHaveBeenCalledTimes(1);
    expect(calls.length).toBe(before);
    run();
    await waitFor(() => expect(compareCalls(calls)).toHaveLength(2));
    expect(calls.length).toBe(before + 1);
  });

  it("shows a backend validation error with its field instead of a result", async () => {
    renderApp({ compare: () => ({ ok: false, status: 422, body: { code: "INVALID_INPUT", message: "duration_days must be in (0, 60]", field: "duration_days", details: {}, request_id: null } }) });
    await screen.findByTestId("health-status");
    run();
    await screen.findByText(/Sweep failed/);
    expect(screen.getByRole("alert")).toHaveTextContent(/duration_days/);
    expect(screen.queryByTestId("sweep-table")).toBeNull();
  });
});

// ------------------------------------------------------------------ C4 enforced statically

describe("Display-layer rule (C4) for the Explore code", () => {
  const files = { tab: readFileSync("src/views/ExploreTab.tsx", "utf-8"), chart: readFileSync("src/components/SweepChart.tsx", "utf-8"), sweep: readFileSync("src/sweep.ts", "utf-8") };

  it("no fetch anywhere; the only API call is the existing compare with an explicit scenario list", () => {
    for (const src of Object.values(files)) expect(src).not.toMatch(/\bfetch\s*\(/);
    expect([...files.tab.matchAll(/api\.(\w+)/g)].map((m) => m[1])).toEqual(["compareScenarios"]);
    expect(files.chart).not.toMatch(/api\/client/);
  });

  it("no trigonometry or statistics; the chart and helpers import only types, React and the formatters", () => {
    for (const src of Object.values(files)) expect(src).not.toMatch(/Math\.(sin|cos|tan|atan|acos|asin|sqrt|pow|hypot|exp|log)/);
    const imp = (s: string) => [...s.matchAll(/^import .* from "([^"]+)"/gm)].map((m) => m[1]).sort();
    expect(imp(files.chart)).toEqual(["../api/types"]);
    expect(imp(files.sweep)).toEqual(["./api/client", "./api/types"]);
  });
});

// ------------------------------------------------------------------ accessibility

describe("Accessibility of the Explore tab (axe-core)", () => {
  it("has no violations before and after a sweep", async () => {
    renderApp();
    await screen.findByTestId("health-status");
    const audit = async (label: string) => {
      const res = await axe.run(document.body, { rules: { "color-contrast": { enabled: false } } });
      expect(res.violations.map((v) => `${v.id}: ${v.help} -> ${v.nodes.slice(0, 2).map((n) => n.target.join(" ")).join(" | ")}`), `axe on ${label}`).toEqual([]);
    };
    await audit("explore (empty)");
    run();
    await screen.findByTestId("sweep-table");
    await audit("explore (result)");
  });
});
