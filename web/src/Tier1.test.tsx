import { readFileSync } from "node:fs";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import type { CompareResponse, ScenarioResult } from "./api/types";
import { baseRoutes, horizonResponse, scenarioSupported, sitesFixture } from "./testFixtures";

// ---- fixtures: three confirmed landing sites + one intended target; IM-1 insufficient, Chandrayaan-3 supported with the caveat ----

const NOT_APPROVED = "Terrain window ch3_60m_r200km (LDEM_60S_60MPP_ADJ, 60 m pixels) is implemented_unvalidated: the owner approved its integration, but it has NOT had the independent verification pass the IM-2 terrain had. Pixels this coarse do not resolve small ridges.";

const sites = {
  ...sitesFixture,
  sites: [
    ...sitesFixture.sites,
    { id: "im2-intended", name: "IM-2 intended target", kind: "intended_target", lat_deg: -84.78, lon_deg_east: 29.13, sources: [] },
    { id: "chandrayaan3-shiv-shakti", name: "Chandrayaan-3 Vikram landing site (Statio Shiv Shakti)", kind: "confirmed_landing", lat_deg: -69.3741, lon_deg_east: 32.32, sources: [] },
  ],
};

const supported = (siteId: string, sun: number, earth: number, extra: Partial<ScenarioResult> = {}): ScenarioResult => {
  const s = scenarioSupported(sun, earth);
  return {
    ...s, id: `id-${siteId}`, spec: { ...s.spec, site_id: siteId },
    observer: { ground_height_m: 529.3, observer_height_above_surface_m: 2 },
    horizon: { az_step_deg: 0.25, windows: [siteId === "im2-athena" ? "im2_20m_r80km" : "ch3_60m_r200km"], summary: { horizon_min_deg: 0.53, horizon_max_deg: 2.47, horizon_mean_deg: 1.36 } },
    limitations: ["Geometric line of sight / direct illumination only."],
    ...extra,
  };
};

const im1Insufficient: ScenarioResult = {
  id: "id-im1", status: "terrain_data_insufficient", served_from: "disk",
  spec: { ...scenarioSupported().spec, site_id: "im1-odysseus" },
  reason: "terrain coverage is insufficient to certify the horizon (360 truncated and 0 data-gap azimuths of 360); sensitivity is not extrapolated",
  reason_code: "TERRAIN_NOT_CERTIFIED",
};

const compareBody = (): CompareResponse => ({
  baseline_id: "id-im2-athena",
  scenarios: [
    supported("im2-athena", 0.486, 0.808),
    im1Insufficient,
    supported("chandrayaan3-shiv-shakti", 0.491, 1.0, { limitations: ["Geometric line of sight.", NOT_APPROVED] }),
  ],
  excluded_terrain_data_insufficient: [{ scenario_id: "id-im1", label: null, site_id: "im1-odysseus", reason: "x" }],
  deltas_vs_baseline: [], rankings: [], notes: [], reading_guide: [],
});

// ---- fetch stub that also records request bodies ----

function renderApp(opts: { compare?: () => { ok: boolean; status?: number; body: unknown }; hash?: string; horizon?: unknown } = {}) {
  const routes: Record<string, unknown> = { ...baseRoutes(), "/sites": sites, "/horizon/profile": opts.horizon ?? horizonResponse() };
  const calls: { method: string; path: string; body: unknown }[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const path = url.replace(/^\/api/, "").split("?")[0];
    calls.push({ method: init?.method ?? "GET", path, body: init?.body ? JSON.parse(init.body) : null });
    if (path === "/scenarios/compare") {
      const dflt = (): { ok: boolean; status?: number; body: unknown } => ({ ok: true, body: compareBody() });
      const r = (opts.compare ?? dflt)();
      return { ok: r.ok, status: r.status ?? 200, json: async () => r.body };
    }
    if (path in routes) return { ok: true, json: async () => routes[path] };
    return { ok: false, status: 404, json: async () => ({ code: "NOT_FOUND", message: `no stub for ${path}`, field: null, details: {}, request_id: null }) };
  }));
  window.history.replaceState(null, "", `/${opts.hash ?? "#sites"}`);
  render(<App />);
  return calls;
}

type Call = { method: string; path: string; body: unknown };
const compareCalls = (calls: Call[]) => calls.filter((c) => c.path === "/scenarios/compare");

beforeEach(() => window.localStorage.clear());
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
  window.localStorage.clear();
});

// =============================================================== Tier 1a: historical landing-site comparison

describe("Landing sites tab (side-by-side comparison of the existing scenarios API)", () => {
  it("offers only the confirmed landing sites and makes NO request until asked", async () => {
    const calls = renderApp();
    await screen.findByTestId("health-status");
    const boxes = screen.getAllByRole("checkbox").map((b) => (b.parentElement as HTMLElement).textContent?.trim());
    expect(boxes).toEqual(["IM-2 Athena landing site (Mons Mouton)", "IM-1 Odysseus landing site (Malapert A)", "Chandrayaan-3 Vikram landing site (Statio Shiv Shakti)"]);   // catalogue order
    expect(screen.queryByText(/IM-2 intended target/)).toBeNull();                 // an intended target is not a historical landing
    expect(compareCalls(calls)).toHaveLength(0);
  });

  it("sends exactly ONE existing /scenarios/compare request with the chosen sites, window and band", async () => {
    const calls = renderApp();
    await screen.findByTestId("health-status");
    fireEvent.click(screen.getByRole("button", { name: "Compare sites" }));
    await screen.findByTestId("sites-table");
    const sent = compareCalls(calls);
    expect(sent).toHaveLength(1);
    expect(sent[0].body).toMatchObject({
      sites: [{ site_id: "im2-athena" }, { site_id: "im1-odysseus" }, { site_id: "chandrayaan3-shiv-shakti" }],
      start_utc_list: ["2027-01-15T00:00:00Z"], duration_days: 30, position_uncertainty_m: 100, baseline_index: 0,
    });
    // ...and the page then makes no other kind of request for the comparison
    expect(calls.filter((c) => c.path.startsWith("/scenarios") || c.path.startsWith("/visibility") || c.path.startsWith("/horizon"))).toHaveLength(1);
  });

  it("shows supported sites side by side with bands and the geometric counterpart", async () => {
    renderApp();
    await screen.findByTestId("health-status");
    fireEvent.click(screen.getByRole("button", { name: "Compare sites" }));
    const table = await screen.findByTestId("sites-table");
    const rowOf = (label: RegExp) => within(table).getByText(label).closest("tr") as HTMLElement;
    const sunTc = rowOf(/Sun visible, terrain-corrected/);
    expect(within(sunTc).getAllByRole("cell")[0]).toHaveTextContent("48.6 %");           // IM-2
    expect(within(sunTc).getAllByRole("cell")[0]).toHaveTextContent(/band 45\.6 % to 48\.9 %/);   // band shown beside the number
    expect(within(sunTc).getAllByRole("cell")[2]).toHaveTextContent("49.1 %");           // Chandrayaan-3
    expect(within(rowOf(/Sun visible, geometric/)).getAllByRole("cell")[0]).toHaveTextContent("53.3 %");
    expect(within(rowOf(/Terrain horizon/)).getAllByRole("cell")[0]).toHaveTextContent("0.53° to 2.47°");
    expect(within(rowOf(/Terrain data used/)).getAllByRole("cell")[2]).toHaveTextContent("ch3_60m_r200km");
  });

  it("labels the insufficient site and gives it NO figure, rank or estimate in any row", async () => {
    renderApp();
    await screen.findByTestId("health-status");
    fireEvent.click(screen.getByRole("button", { name: "Compare sites" }));
    const table = await screen.findByTestId("sites-table");
    expect(screen.getByTestId("status-im1-odysseus")).toHaveTextContent("terrain data insufficient");
    const im1Cells = within(table).getAllByRole("row").slice(1).map((r) => within(r).getAllByRole("cell")[1].textContent ?? "");
    // the first body cell of every row of the IM-1 column: the label or a dash, never a number
    const metricRows = im1Cells.slice(1);
    expect(metricRows.length).toBeGreaterThanOrEqual(9);
    for (const t of metricRows) expect(t).toBe("terrain data insufficient");
    expect(within(table).getAllByTestId("cell-insufficient")).toHaveLength(9);
    expect(screen.getByTestId("terrain-insufficient")).toHaveTextContent(/360 truncated/);
    expect(within(table).queryByText(/rank/i)).toBeNull();                              // no rank cell for any site
    expect(screen.queryByRole("heading", { name: /Rankings/ })).toBeNull();                     // this view ranks nothing
  });

  it("says so, instead of showing a bare dash, when the backend reports a body is never blocked", async () => {
    const body = compareBody();
    const ch3 = body.scenarios[2];
    ch3.bodies!.earth.terrain_corrected.longest_not_visible_s = { closed_only: null, including_open: null, includes_open_interval: false };
    ch3.bodies!.earth.terrain_corrected.visible_fraction = { nominal: 1, band: [1, 1] };
    renderApp({ compare: () => ({ ok: true, body }) });
    await screen.findByTestId("health-status");
    fireEvent.click(screen.getByRole("button", { name: "Compare sites" }));
    await screen.findByTestId("sites-table");
    expect(screen.getByTestId("no-gap")).toHaveTextContent("none: visible throughout the window");
    expect(screen.getAllByTestId("no-gap")).toHaveLength(1);                              // only where the fraction is exactly 100 %
  });

  it("labels implemented_unvalidated terrain with the same pill as an implemented_unvalidated capability, from the backend's own limitation text", async () => {
    renderApp();
    await screen.findByTestId("health-status");
    fireEvent.click(screen.getByRole("button", { name: "Compare sites" }));
    await screen.findByTestId("sites-table");
    const flags = screen.getAllByTestId("terrain-unvalidated");
    expect(flags).toHaveLength(1);                                                           // Chandrayaan-3 only, not IM-2
    expect(flags[0]).toHaveAttribute("title", expect.stringContaining("implemented_unvalidated"));
    expect(within(screen.getByTestId("status-chandrayaan3-shiv-shakti")).getByText("supported")).toBeInTheDocument();
  });

  it("makes no further request when the user interacts with the result (C4)", async () => {
    const calls = renderApp();
    await screen.findByTestId("health-status");
    fireEvent.click(screen.getByRole("button", { name: "Compare sites" }));
    await screen.findByTestId("sites-table");
    const before = calls.length;
    fireEvent.click(screen.getByText("Limitations the backend attached to these results"));
    fireEvent.click(screen.getAllByRole("checkbox")[0]);                                      // changing the form is not running it
    fireEvent.change(screen.getByLabelText(/Window length/), { target: { value: "20" } });
    expect(calls.length).toBe(before);
    fireEvent.click(screen.getByRole("button", { name: "Compare sites" }));
    await waitFor(() => expect(compareCalls(calls)).toHaveLength(2));                         // one request per explicit Run
  });

  it("validates before asking the backend and shows backend errors instead of a result", async () => {
    const calls = renderApp({ compare: () => ({ ok: false, status: 422, body: { code: "INVALID_INPUT", message: "boom", field: "duration_days", details: {}, request_id: null } }) });
    await screen.findByTestId("health-status");
    fireEvent.change(screen.getByLabelText(/Window length/), { target: { value: "0" } });
    fireEvent.click(screen.getByRole("button", { name: "Compare sites" }));
    expect(screen.getByRole("alert")).toHaveTextContent(/between 0 and 60/);
    expect(compareCalls(calls)).toHaveLength(0);
    fireEvent.change(screen.getByLabelText(/Window length/), { target: { value: "30" } });
    fireEvent.click(screen.getByRole("button", { name: "Compare sites" }));
    await screen.findByText(/Site comparison failed/);
    expect(screen.queryByTestId("sites-table")).toBeNull();
  });
});

// =============================================================== Tier 1b: advanced plots (display layer only)

async function computeView(calls: Call[]) {
  await screen.findByTestId("health-status");
  fireEvent.click(screen.getByRole("button", { name: "Compute" }));
  await screen.findByTestId("advanced-plots");
  await screen.findByTestId("time-readout");
  expect(calls.length).toBeGreaterThan(0);
}

describe("Advanced plots panel (sky chart, horizon detail, Sun/Earth elevation over time)", () => {
  it("renders the three figures from the data the View tab already loaded", async () => {
    const calls = renderApp({ hash: "#view" });
    await computeView(calls);
    const panel = screen.getByRole("region", { name: /Advanced plots/ });
    expect(within(panel).getByRole("img", { name: /Sky chart of the terrain horizon/ })).toBeInTheDocument();
    expect(within(panel).getByRole("img", { name: /distance to the terrain that sets the horizon/ })).toBeInTheDocument();
    expect(within(panel).getByRole("img", { name: /Sun and Earth elevation over time/ })).toBeInTheDocument();
  });

  it("makes ZERO requests of its own: every control works on the arrays already received (C4 request-count test)", async () => {
    const calls = renderApp({ hash: "#view" });
    await computeView(calls);
    const before = calls.length;
    fireEvent.change(screen.getByLabelText(/Azimuth to inspect/), { target: { value: "2" } });
    fireEvent.change(screen.getByLabelText(/Inspect sample/), { target: { value: "3" } });
    fireEvent.change(screen.getByLabelText(/Zoom: first sample/), { target: { value: "1" } });
    fireEvent.change(screen.getByLabelText(/Zoom: last sample/), { target: { value: "3" } });
    fireEvent.click(screen.getByRole("button", { name: "Reset zoom" }));
    expect(calls.length).toBe(before);
  });

  it("reads the horizon at the chosen azimuth straight from the backend arrays", async () => {
    const calls = renderApp({ hash: "#view" });
    await computeView(calls);
    const r = screen.getByTestId("az-readout");
    expect(r).toHaveTextContent("Azimuth 0.00°");
    expect(r).toHaveTextContent("+1.000°");                                                  // horizon_elevation_deg[0]
    fireEvent.change(screen.getByLabelText(/Azimuth to inspect/), { target: { value: "2" } });
    expect(r).toHaveTextContent("Azimuth 180.00°");
    expect(r).toHaveTextContent("+3.000°");                                                  // horizon_elevation_deg[2]
    expect(r).toHaveTextContent("1.0 km away");                                              // horizon_distance_km[2]
    expect(r).toHaveTextContent("horizon certified at this azimuth");
  });

  it("marks an azimuth whose horizon is only a lower bound, never as certified", async () => {
    const h = { ...horizonResponse(), truncated: [false, true, false, false] };
    const calls = renderApp({ hash: "#view", horizon: h });
    await computeView(calls);
    fireEvent.change(screen.getByLabelText(/Azimuth to inspect/), { target: { value: "1" } });
    expect(screen.getByTestId("az-readout")).toHaveTextContent(/lower bound: terrain data truncated or missing/);
    expect(screen.getByTestId("az-readout")).not.toHaveTextContent(/certified/);
  });

  it("reads Sun and Earth at the inspected sample from the visibility series, and zooming only re-labels the window", async () => {
    const calls = renderApp({ hash: "#view" });
    await computeView(calls);
    fireEvent.change(screen.getByLabelText(/Inspect sample/), { target: { value: "3" } });
    const r = screen.getByTestId("time-readout");
    expect(r).toHaveTextContent("az 130.0°");                                                // sun azimuth_deg[3]
    expect(r).toHaveTextContent("el +2.50°");
    expect(r).toHaveTextContent("az 330.0°");                                                // earth azimuth_deg[3]
    expect(r).toHaveTextContent("2027-01-15 00:45:00 UTC");                                  // start + 3 x 900 s
    fireEvent.change(screen.getByLabelText(/Zoom: first sample/), { target: { value: "2" } });
    expect(screen.getByLabelText(/Zoom: first sample/).previousSibling ?? screen.getByLabelText(/Zoom: first sample/)).toBeTruthy();
    expect(screen.getByText(/Zoom: first sample \(2027-01-15 00:30:00 UTC\)/)).toBeInTheDocument();
    expect(calls.filter((c) => c.path === "/visibility/series")).toHaveLength(1);
  });

  it("is absent (no plots, no numbers) when the terrain horizon cannot be computed", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      const path = url.replace(/^\/api/, "").split("?")[0];
      const routes = baseRoutes() as Record<string, unknown>;
      if (path === "/horizon/profile" || path === "/visibility/series") {
        return { ok: false, status: 422, json: async () => ({ code: "OUT_OF_DEM_COVERAGE", message: "No DEM window covers this point; no terrain fallback is used.", field: "dem", details: {}, request_id: null }) };
      }
      return path in routes ? { ok: true, json: async () => routes[path] } : { ok: false, status: 404, json: async () => ({ code: "NOT_FOUND", message: path, field: null, details: {}, request_id: null }) };
    }));
    window.history.replaceState(null, "", "/#view");
    render(<App />);
    await screen.findByTestId("health-status");
    fireEvent.click(screen.getByRole("button", { name: "Compute" }));
    await screen.findAllByTestId("terrain-insufficient");
    expect(screen.queryByTestId("advanced-plots")).toBeNull();
  });
});

// =============================================================== C4 enforced statically too

describe("Display-layer rule (C4) for the new code", () => {
  const advanced = readFileSync("src/components/AdvancedPlots.tsx", "utf-8");
  const sitesTab = readFileSync("src/views/SitesTab.tsx", "utf-8");

  it("the advanced plots cannot make a request: no fetch, no api client, only types, React and the formatters", () => {
    expect(advanced).not.toMatch(/\bfetch\s*\(/);
    expect(advanced).not.toMatch(/from "\.\.\/api\/client"/);
    const imports = [...advanced.matchAll(/^import .* from "([^"]+)"/gm)].map((m) => m[1]);
    expect(imports.sort()).toEqual(["../api/types", "../format", "react"]);
  });

  it("trigonometry appears only in the screen projection of backend azimuth/elevation (polarXY), nowhere in the sites view", () => {
    const uses = advanced.split("\n").filter((l) => /Math\.(sin|cos|tan|atan|acos|asin)/.test(l));
    expect(uses.length).toBeGreaterThanOrEqual(1);
    const fn = advanced.slice(advanced.indexOf("function polarXY"), advanced.indexOf("export function SkyPolarPlot"));
    for (const l of uses) expect(fn).toContain(l);
    expect(sitesTab).not.toMatch(/Math\.(sin|cos|tan|atan|acos|asin|sqrt|pow|hypot)/);
  });

  it("the sites view reads results only through the existing compare call", () => {
    expect([...sitesTab.matchAll(/api\.(\w+)/g)].map((m) => m[1])).toEqual(["compare"]);
  });
});

// =============================================================== accessibility

async function audit(label: string) {
  const res = await axe.run(document.body, { rules: { "color-contrast": { enabled: false } } });
  const summary = res.violations.map((v) => `${v.id} (${v.impact}): ${v.help} -> ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ")}`);
  expect(summary, `axe violations on ${label}`).toEqual([]);
}

describe("Accessibility of the new views (axe-core)", () => {
  it("Landing sites tab, before and after a comparison", async () => {
    renderApp();
    await screen.findByTestId("health-status");
    await audit("landing sites (empty)");
    fireEvent.click(screen.getByRole("button", { name: "Compare sites" }));
    await screen.findByTestId("sites-table");
    await audit("landing sites (result)");
  });

  it("Site & time tab with the advanced plots", async () => {
    const calls = renderApp({ hash: "#view" });
    await computeView(calls);
    await audit("view with advanced plots");
  });
});
