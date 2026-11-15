import { readFileSync } from "node:fs";
import { fireEvent, render, screen, within } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import type { Site } from "./api/types";
import { SiteMap } from "./components/SiteMap";
import golden from "./polarGolden.json";
import { BASEMAP, polarXY, ringRadiusM, tilesFor } from "./polar";
import { baseRoutes, stubFetch } from "./testFixtures";

// Map geometry as drawn by SiteMap (kept in step with its constants; the assertions below derive expectations from the
// ENGINE-generated golden table, not from the component's own functions).
const C = 170;
const R = 158;
const E = 1_000_000;
const G = Object.fromEntries(golden.points.map((p) => [p.name, p]));
const svgX = (xm: number) => C + (xm / E) * R;
const svgY = (ym: number) => C - (ym / E) * R;

const site = (id: string, name: string, lat: number, lon: number, kind = "confirmed_landing"): Site => ({ id, name, kind, lat_deg: lat, lon_deg_east: lon, sources: [] });
const SITES: Site[] = [
  site("im2-athena", "IM-2 Athena landing site (Mons Mouton)", -84.79059, 29.19567),
  site("im1-odysseus", "IM-1 Odysseus landing site (Malapert A)", -80.12759, 1.44587),
  site("chandrayaan3-shiv-shakti", "Chandrayaan-3 Vikram landing site (Statio Shiv Shakti)", -69.3741, 32.32),
];
const marker = (id: string) => document.querySelector(`[data-marker="${id}"]`) as SVGCircleElement;

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

// ------------------------------------------------------------------ projection = the engine's

describe("polar projection (a mirror of the engine's lonlat_to_xy, pinned by a generated golden table)", () => {
  it("matches every golden point produced by the Python engine to well under a millimetre", () => {
    expect(golden.sphere_radius_m).toBe(1_737_400);
    for (const p of golden.points) {
      const xy = polarXY(p.lat_deg, p.lon_deg_east)!;
      expect(Math.abs(xy.x - p.x_m), p.name).toBeLessThan(1e-6);
      expect(Math.abs(xy.y - p.y_m), p.name).toBeLessThan(1e-6);
    }
  });

  it("refuses what the projection is not defined for instead of inventing a position", () => {
    expect(polarXY(0, 10)).toBeNull();
    expect(polarXY(12, 10)).toBeNull();
    expect(polarXY(Number.NaN, 10)).toBeNull();
    expect(polarXY(-91, 10)).toBeNull();
    expect(ringRadiusM(-90)).toBeCloseTo(0, 9);
  });
});

// ------------------------------------------------------------------ the tile grid

describe("basemap tile grid (NASA Moon Trek WMTS, from its WMTSCapabilities.xml)", () => {
  it("covers the disc with 16 level-2 tiles at the capabilities' URLs, origin and spans", () => {
    const t = tilesFor(2, 1_000_000);
    expect(t).toHaveLength(16);
    expect(new Set(t.map((x) => x.url)).size).toBe(16);
    expect(t[0].url).toBe("https://trek.nasa.gov/tiles/Moon/SP/LRO_WAC_Mosaic_SPole60_100m_v02/1.0.0//default/default028mm/2/0/0.png");
    expect(t[15].url).toMatch(/\/2\/3\/3\.png$/);
    for (const x of t) {
      expect(x.url.startsWith("https://trek.nasa.gov/")).toBe(true);
      expect(x.spanM).toBeCloseTo(2 * 1_095_930 / 4, 6);
      expect(x.leftM).toBeCloseTo(-1_095_930 + x.col * x.spanM, 6);
      expect(x.topM).toBeCloseTo(1_095_930 - x.row * x.spanM, 6);
    }
    expect(BASEMAP.level0SpanM).toBe(2 * BASEMAP.originM);
  });

  it("puts the pole exactly on the shared corner of the four central tiles (where the mosaic's own seams cross)", () => {
    const t = tilesFor(2, 1_000_000);
    const at = (r: number, c: number) => t.find((x) => x.row === r && x.col === c)!;
    expect(at(2, 2).leftM).toBeCloseTo(0, 6);
    expect(at(2, 2).topM).toBeCloseTo(0, 6);
    expect(at(1, 1).leftM + at(1, 1).spanM).toBeCloseTo(0, 6);
    expect(at(1, 1).topM - at(1, 1).spanM).toBeCloseTo(0, 6);
  });
});

// ------------------------------------------------------------------ what is drawn

describe("SiteMap on the imagery basemap", () => {
  it("draws 16 tile images, each at the SVG position of its grid square, and the catalogue sites at their golden positions", () => {
    render(<SiteMap sites={SITES} selectedId="im2-athena" custom={null} onSelect={() => undefined} />);
    const imgs = [...document.querySelectorAll("[data-testid='basemap'] image")];
    expect(imgs).toHaveLength(16);
    const centre = imgs.find((i) => (i.getAttribute("href") ?? "").endsWith("/2/2/2.png"))!;
    expect(Number(centre.getAttribute("x"))).toBeCloseTo(C, 3);                       // left edge of tile (2,2) is the pole
    expect(Number(centre.getAttribute("y"))).toBeCloseTo(C, 3);                       // top edge likewise
    for (const [id, g] of [["im2-athena", G["im2-athena"]], ["im1-odysseus", G["im1-odysseus"]], ["chandrayaan3-shiv-shakti", G["chandrayaan3-shiv-shakti"]]] as const) {
      expect(Number(marker(id).getAttribute("cx")), id).toBeCloseTo(svgX(g.x_m), 3);
      expect(Number(marker(id).getAttribute("cy")), id).toBeCloseTo(svgY(g.y_m), 3);
    }
  });

  it("draws the 85/80/70/60 °S rings at the radii the engine's projection gives", () => {
    render(<SiteMap sites={SITES} selectedId={null} custom={null} onSelect={() => undefined} />);
    const rho = (n: string) => Math.hypot(G[n].x_m, G[n].y_m);
    const expected: Record<string, number> = { "-85": rho("lat-85-lon-0"), "-80": rho("lat-80-lon-neg135"), "-70": rho("lat-70-lon-180"), "-60": rho("lat-60-lon-270") };
    for (const [lat, m] of Object.entries(expected)) {
      const c = document.querySelector(`[data-ring="${lat}"]`)!;
      expect(Number(c.getAttribute("r")), lat).toBeCloseTo((m / E) * R, 3);
    }
  });

  it("keeps the rings optional and the imagery optional, independently", () => {
    render(<SiteMap sites={SITES} selectedId={null} custom={null} onSelect={() => undefined} />);
    fireEvent.click(screen.getByLabelText("Lunar imagery"));
    expect(screen.queryByTestId("basemap")).toBeNull();
    expect(screen.getByTestId("map-rings")).toBeInTheDocument();
    expect(marker("im2-athena")).toBeTruthy();                                        // sites are still drawn on the plain schematic
    fireEvent.click(screen.getByLabelText("Lunar imagery"));
    fireEvent.click(screen.getByLabelText("Parallel rings"));
    expect(screen.queryByTestId("map-rings")).toBeNull();
    expect(screen.getByTestId("basemap")).toBeInTheDocument();
  });

  it("labels the source and resolution visibly, and says the imagery feeds no calculation", () => {
    render(<SiteMap sites={SITES} selectedId={null} custom={null} onSelect={() => undefined} />);
    const cap = document.querySelector("figcaption")!;
    expect(cap).toHaveTextContent("LRO LROC WAC mosaic, S Pole v2 (NASA/GSFC/Arizona State University), 100 m/pixel native");
    expect(cap).toHaveTextContent("about 2.1 km/pixel from NASA Moon Trek");
    expect(cap).toHaveTextContent("no calculation uses it");
    expect(within(cap as HTMLElement).getByRole("link")).toHaveAttribute("href", "https://trek.nasa.gov/moon/");
  });

  it("falls back to the ring schematic, and says so, when tiles cannot be loaded", () => {
    render(<SiteMap sites={SITES} selectedId={null} custom={null} onSelect={() => undefined} />);
    expect(screen.queryByTestId("basemap-failed")).toBeNull();
    for (const i of document.querySelectorAll("[data-testid='basemap'] image")) fireEvent.error(i);
    expect(screen.getByTestId("basemap-failed")).toHaveTextContent("16 map tile(s) could not be loaded");
    expect(screen.getByTestId("map-rings")).toBeInTheDocument();
    expect(Number(marker("chandrayaan3-shiv-shakti").getAttribute("cx"))).toBeCloseTo(svgX(G["chandrayaan3-shiv-shakti"].x_m), 3);
  });

  it("still renders for custom coordinates anywhere (no dependence on DEM coverage), pins far points to the edge and ignores invalid ones", () => {
    const { rerender } = render(<SiteMap sites={SITES} selectedId={null} custom={{ lat: -72, lon: 200 }} onSelect={() => undefined} />);
    const m = polarXY(-72, 200)!;                                                     // outside every DEM window: the imagery does not care
    const path = document.querySelector("[data-testid='custom-marker'] path")!.getAttribute("d")!;
    const [, px0, py0] = /^M(-?[\d.]+),(-?[\d.]+)/.exec(path)!.map(Number);               // the cross is drawn from (x - 6, y)
    expect(px0 + 6).toBeCloseTo(svgX(m.x), 3);
    expect(py0).toBeCloseTo(svgY(m.y), 3);
    expect(screen.getByTestId("custom-marker")).toHaveTextContent("custom");
    expect(screen.getByTestId("custom-marker")).not.toHaveTextContent("beyond");
    rerender(<SiteMap sites={SITES} selectedId={null} custom={{ lat: -55, lon: 10 }} onSelect={() => undefined} />);
    expect(screen.getByTestId("custom-marker")).toHaveTextContent("beyond map edge");
    rerender(<SiteMap sites={SITES} selectedId={null} custom={{ lat: 10, lon: 10 }} onSelect={() => undefined} />);
    expect(screen.queryByTestId("custom-marker")).toBeNull();                         // northern latitude: nothing invented
  });

  it("selects a site with the keyboard as before", () => {
    const onSelect = vi.fn();
    render(<SiteMap sites={SITES} selectedId={null} custom={null} onSelect={onSelect} />);
    fireEvent.keyDown(screen.getByRole("button", { name: /Select IM-1 Odysseus/ }), { key: "Enter" });
    expect(onSelect).toHaveBeenCalledWith("im1-odysseus");
  });
});

// ------------------------------------------------------------------ C4: no new API calls

describe("the basemap adds no API calls (C4), consistent with the scrubbing test", () => {
  it("rendering, toggling the layers, selecting a site and tile errors cause no request of any kind", async () => {
    const s = stubFetch(baseRoutes());
    vi.stubGlobal("fetch", vi.fn(s.fn));
    window.history.replaceState(null, "", "/#view");
    render(<App />);
    await screen.findByTestId("health-status");
    const before = s.calls.length;
    expect(document.querySelectorAll("[data-testid='basemap'] image")).toHaveLength(16);
    fireEvent.click(screen.getByLabelText("Lunar imagery"));
    fireEvent.click(screen.getByLabelText("Lunar imagery"));
    fireEvent.click(screen.getByLabelText("Parallel rings"));
    fireEvent.click(screen.getByLabelText("Parallel rings"));
    fireEvent.click(screen.getByRole("button", { name: /Select IM-1 Odysseus/ }));
    for (const i of document.querySelectorAll("[data-testid='basemap'] image")) fireEvent.error(i);
    expect(s.calls.length).toBe(before);                                              // not one request (and no call outside /api: tiles are plain images)
    expect((fetch as unknown as { mock: { calls: [string][] } }).mock.calls.every(([u]) => u.startsWith("/api"))).toBe(true);
  });

  it("the new files contain no fetch/API client and only trig in the grid helper", () => {
    const map = readFileSync("src/components/SiteMap.tsx", "utf-8");
    const polar = readFileSync("src/polar.ts", "utf-8");
    for (const src of [map, polar]) expect(src).not.toMatch(/\bfetch\s*\(/);
    expect(map).not.toMatch(/api\/client/);
    expect(map).not.toMatch(/Math\.(sin|cos|tan|atan)/);
    const imp = [...map.matchAll(/^import .* from "([^"]+)"/gm)].map((m) => m[1]).sort();
    expect(imp).toEqual(["../api/types", "../polar", "react"]);
    expect(polar).not.toMatch(/^import /m);
  });
});

// ------------------------------------------------------------------ accessibility

describe("accessibility of the map", () => {
  it("has no axe violations with the imagery on", async () => {
    render(<main><SiteMap sites={SITES} selectedId="im2-athena" custom={{ lat: -75, lon: 100 }} onSelect={() => undefined} /></main>);
    const res = await axe.run(document.body, { rules: { "color-contrast": { enabled: false } } });
    expect(res.violations.map((v) => `${v.id}: ${v.help}`)).toEqual([]);
  });
});
