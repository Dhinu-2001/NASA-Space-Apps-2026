import { readFileSync } from "node:fs";
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import type { Band, Interval, VisibilityBody } from "./api/types";
import { eventName, nextChange } from "./countdown";
import { atResponse, baseRoutes, stubFetch, visBody, visResponse } from "./testFixtures";

const START = "2027-01-15T00:00:00Z";
const END = "2027-01-15T01:00:00Z"; // a 3600 s window

const at = (s: number) => new Date(Date.parse(START) + s * 1000).toISOString().replace(".000Z", "Z");
const band = (lo: number, hi: number, complete = true): Band => ({ earliest_utc: at(lo), latest_utc: at(hi), width_s: hi - lo, complete });
const iv = (a: number, b: number, extra: Partial<Interval> = {}): Interval => ({
  start_utc: at(a), end_utc: at(b), start_s: a, end_s: b, duration_s: b - a, open_start: false, open_end: false, ...extra,
});
const body = (intervals: Interval[]): VisibilityBody => {
  const b = visBody("sun");
  b.headline!.intervals = intervals;
  return b;
};

// ------------------------------------------------------------------ the helper: every number comes from the backend's intervals

describe("nextChange (time until the headline state next changes against the terrain)", () => {
  it("visible now: time to the end of the current interval, with the band of that event", () => {
    const c = nextChange(body([iv(0, 2400, { end_band: band(2000, 2900) })]), START, END, 600, true)!;
    expect(c).toMatchObject({ kind: "sets", remainingS: 1800, bandS: [1400, 2300], bandComplete: true, noEventInWindow: false });
    expect(eventName("sun", c.kind)).toBe("Sunset");
    expect(eventName("earth", c.kind)).toBe("Earthset");
  });

  it("hidden now: time to the START of the NEXT visible interval (not a later one), with its band", () => {
    const c = nextChange(body([iv(0, 300), iv(1500, 1800, { start_band: band(1400, 1600) }), iv(3000, 3500)]), START, END, 900, false)!;
    expect(c).toMatchObject({ kind: "rises", remainingS: 600, bandS: [500, 700], noEventInWindow: false });
    expect(eventName("sun", c.kind)).toBe("Sunrise");
    expect(eventName("earth", c.kind)).toBe("Earthrise");
  });

  it("never reports a negative band edge: an event band reaching back before the shown time is clamped to zero", () => {
    const c = nextChange(body([iv(0, 1000, { end_band: band(100, 1500) })]), START, END, 500, true)!;
    expect(c.bandS).toEqual([0, 1000]);
  });

  it("a state that lasts to the end of the window is a LOWER bound, never a predicted event", () => {
    const vis = nextChange(body([iv(1000, 3600, { open_end: true })]), START, END, 1200, true)!;
    expect(vis).toMatchObject({ kind: "sets", remainingS: null, bandS: null, noEventInWindow: true, atLeastS: 2400 });
    const hid = nextChange(body([iv(0, 600)]), START, END, 1000, false)!;      // hidden, no later visible interval
    expect(hid).toMatchObject({ kind: "rises", remainingS: null, noEventInWindow: true, atLeastS: 2600 });
  });

  it("flags a band that is only partly known (the event appears at some displaced positions only)", () => {
    const c = nextChange(body([iv(0, 2400, { end_band: band(2400, 2400, false) })]), START, END, 0, true)!;
    expect(c.bandComplete).toBe(false);
  });

  it("gives nothing it cannot back with backend data: no headline, outside the window, or no interval holding the shown time", () => {
    const empty = visBody("sun");
    delete (empty as { headline?: unknown }).headline;
    expect(nextChange(empty, START, END, 0, true)).toBeNull();
    expect(nextChange(body([iv(0, 600)]), START, END, -50, true)).toBeNull();
    expect(nextChange(body([iv(0, 600)]), START, END, 4000, true)).toBeNull();
    expect(nextChange(body([iv(2000, 3000)]), START, END, 100, true)).toBeNull();   // card says visible but no visible interval holds it
  });

  it("tolerates the 1 s event resolution at the boundary", () => {
    expect(nextChange(body([iv(0, 600, { end_band: band(600, 600) })]), START, END, 600.4, true)!.remainingS).toBe(0);
  });
});

// ------------------------------------------------------------------ in the Site & time view

function seriesWithIntervals() {
  const v = visResponse();
  v.bodies.sun.headline!.intervals = [iv(0, 600, { open_start: true, end_band: band(300, 1200) }), iv(2700, 3600, { open_end: true, start_band: band(2600, 2800) })];
  v.bodies.earth.headline!.intervals = [iv(0, 3600, { open_start: true, open_end: true })];
  return v;
}

function renderApp() {
  const routes = { ...baseRoutes(), "/visibility/series": seriesWithIntervals(), "/visibility/at": atResponse(1) };
  const s = stubFetch(routes);
  vi.stubGlobal("fetch", vi.fn(s.fn));
  window.history.replaceState(null, "", "/#view");
  render(<App />);
  return s;
}

async function compute() {
  await screen.findByTestId("health-status");
  fireEvent.click(screen.getByRole("button", { name: "Compute" }));
  await screen.findByTestId("now-sun");
  await screen.findByLabelText(/Time within the window/);
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

describe("Sunset / Earthset countdown in the Sun and Earth cards", () => {
  it("shows no countdown while the chosen time is outside the computed window (nothing is extrapolated)", async () => {
    renderApp();
    await compute();                                        // the default 'positions at' time (20 Jan) is outside the 1-hour test window
    expect(screen.queryByTestId("countdown-sun")).toBeNull();
    expect(screen.queryByTestId("countdown-earth")).toBeNull();
  });

  it("follows the time player: Sunset in, then Sunrise in, then an 'at least' lower bound, each from the backend's intervals and bands", async () => {
    const s = renderApp();
    await compute();
    const before = s.calls.length;
    const slider = screen.getByLabelText(/Time within the window/);

    fireEvent.change(slider, { target: { value: "3" } });                   // t = 2700 s: Sun visible again, to the end of the window
    expect(screen.getByTestId("countdown-sun")).toHaveTextContent("stays visible for at least 15 min");
    expect(screen.getByTestId("countdown-sun")).toHaveTextContent("cut off");

    fireEvent.change(slider, { target: { value: "1" } });                   // t = 900 s: Sun blocked, next visible interval starts at 2700 s
    expect(screen.getByTestId("countdown-sun")).toHaveTextContent("Sunrise in 30 min");
    expect(screen.getByTestId("countdown-sun")).toHaveTextContent(/band 28 min to 32 min/);

    fireEvent.change(slider, { target: { value: "0" } });                   // t = 0: Sun visible, interval ends at 600 s
    const sun = screen.getByTestId("countdown-sun");
    expect(sun).toHaveTextContent("Sunset in 10 min");
    expect(sun).toHaveTextContent(/band 5 min to 20 min for a ±100 m position error/);
    expect(screen.getByTestId("countdown-earth")).toHaveTextContent("stays visible for at least 60 min");   // Earth visible to the window's end

    expect(s.calls.length).toBe(before);                                    // C4: not one request while scrubbing
    expect(screen.getByTestId("countdown-help")).toHaveTextContent(/terrain-corrected/);
  });

  it("is absent, with no number, when the site has no terrain support (no visibility series)", async () => {
    const s = stubFetch({ ...baseRoutes(), "/visibility/series": () => { throw new Error("unused"); } });
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: { method?: string }) => {
      if (url.includes("/visibility/series")) return { ok: false, status: 422, json: async () => ({ code: "OUT_OF_DEM_COVERAGE", message: "no terrain", field: "dem", details: {}, request_id: null }) };
      return s.fn(url, init);
    }));
    window.history.replaceState(null, "", "/#view");
    render(<App />);
    await screen.findByTestId("health-status");
    fireEvent.click(screen.getByRole("button", { name: "Compute" }));
    await screen.findAllByTestId("terrain-insufficient");
    expect(screen.queryByTestId("countdown-sun")).toBeNull();
    expect(screen.queryByTestId("countdown-help")).toBeNull();
  });
});

describe("display-only (C4)", () => {
  it("the helper contains no fetch, no trigonometry, and imports only types", () => {
    const src = readFileSync("src/countdown.ts", "utf-8");
    expect(src).not.toMatch(/\bfetch\s*\(/);
    expect(src).not.toMatch(/Math\.(sin|cos|tan|atan|acos|asin|sqrt|pow|exp|log)/);
    expect([...src.matchAll(/^import .* from "([^"]+)"/gm)].map((m) => m[1])).toEqual(["./api/types"]);
  });
});
