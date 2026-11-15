// "Time until sunset / Earthset": how long until a body's headline state next changes against the TERRAIN horizon.
//
// Display only (decision C4). Every input is a number the backend already returned for the visibility series: the headline
// intervals (visible / not visible) with their start and end times and the position-uncertainty bands of those events.
// The only arithmetic is presentation: remaining time = (event time) - (the time the card shows), for the nominal event and for
// the edges of its band. Nothing is searched for, predicted or extrapolated beyond the window the backend computed.

import type { Interval, VisibilityBody } from "./api/types";

export type CountdownKind = "sets" | "rises";

export interface Countdown {
  /** "sets": the body is visible now and will next be hidden by terrain; "rises": hidden now, will next clear the terrain */
  kind: CountdownKind;
  /** seconds from the shown time to the nominal event; null when no event happens inside the computed window */
  remainingS: number | null;
  /** the same for the earliest and latest event time over the sampled landing positions (null if the backend gave no band) */
  bandS: [number, number] | null;
  /** false when the event occurs only at some of the sampled positions (the band is then incomplete) */
  bandComplete: boolean;
  /** true when the state lasts to the end of the computed window: `atLeastS` is then a LOWER bound, not a prediction */
  noEventInWindow: boolean;
  atLeastS: number | null;
}

const TOL_S = 1; // the backend refines transitions to 1 s

const secondsFrom = (startMs: number, iso: string) => (Date.parse(iso) - startMs) / 1000;

function bandOf(iv: Interval | undefined, which: "start_band" | "end_band", startMs: number, tS: number): { band: [number, number] | null; complete: boolean } {
  const b = iv?.[which];
  if (!b) return { band: null, complete: true };
  return {
    band: [Math.max(0, secondsFrom(startMs, b.earliest_utc) - tS), Math.max(0, secondsFrom(startMs, b.latest_utc) - tS)],
    complete: b.complete,
  };
}

/**
 * Next change of the headline state after `tS` seconds from the window start.
 * `visibleNow` is the headline state the card itself shows at that time (from the backend series), so the two always agree.
 * Returns null when the backend gave no interval data (e.g. a site without terrain support) or the time is outside the window.
 */
export function nextChange(body: VisibilityBody, windowStartUtc: string, windowEndUtc: string, tS: number, visibleNow: boolean): Countdown | null {
  const h = body.headline;
  if (!h) return null;
  const startMs = Date.parse(windowStartUtc);
  const windowS = secondsFrom(startMs, windowEndUtc);
  if (!Number.isFinite(startMs) || !Number.isFinite(windowS) || tS < -TOL_S || tS > windowS + TOL_S) return null;

  if (visibleNow) {
    const cur = h.intervals.find((i) => i.start_s - TOL_S <= tS && tS < i.end_s + TOL_S);
    if (!cur) return null;
    if (cur.open_end) {
      return { kind: "sets", remainingS: null, bandS: null, bandComplete: true, noEventInWindow: true, atLeastS: Math.max(0, windowS - tS) };
    }
    const { band, complete } = bandOf(cur, "end_band", startMs, tS);
    return { kind: "sets", remainingS: Math.max(0, cur.end_s - tS), bandS: band, bandComplete: complete, noEventInWindow: false, atLeastS: null };
  }

  const next = [...h.intervals].filter((i) => i.start_s > tS + TOL_S).sort((a, b) => a.start_s - b.start_s)[0];
  if (!next) {
    return { kind: "rises", remainingS: null, bandS: null, bandComplete: true, noEventInWindow: true, atLeastS: Math.max(0, windowS - tS) };
  }
  const { band, complete } = bandOf(next, "start_band", startMs, tS);
  return { kind: "rises", remainingS: Math.max(0, next.start_s - tS), bandS: band, bandComplete: complete, noEventInWindow: false, atLeastS: null };
}

export const eventName = (body: "sun" | "earth", kind: CountdownKind) =>
  body === "sun" ? (kind === "sets" ? "Sunset" : "Sunrise") : kind === "sets" ? "Earthset" : "Earthrise";
