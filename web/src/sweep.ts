// Request construction and table export for the Explore (parameter sweep) tab. NO science here (decision C4): these
// helpers only turn what the user typed into a list of ordinary scenario requests for the existing
// POST /scenarios/compare, and serialise numbers the backend already returned.

import type { ScenarioReq } from "./api/client";
import type { ScenarioResult } from "./api/types";

export const MAX_SWEEP_POINTS = 12; // the backend's own limit per comparison (MAX_SCENARIOS)

export type SweepParam = "start" | "length" | "band" | "height" | "step";

export const SWEEP_PARAMS: { id: SweepParam; label: string; unit: string; help: string }[] = [
  { id: "start", label: "Window start date", unit: "UTC", help: "Same site and window length, different start dates: how the answer moves through the year." },
  { id: "length", label: "Window length", unit: "days", help: "Fractions average over the window, so a different length changes what is being averaged, not the model. 29.5 d = one synodic month." },
  { id: "band", label: "Position uncertainty", unit: "m", help: "Nominal results do not depend on it; the BANDS do. Shows how much a better or worse landing-position knowledge matters." },
  { id: "height", label: "Observer height", unit: "m", help: "The 2.0 m default is an assumption; this shows how much the answer depends on it." },
  { id: "step", label: "Sampling step", unit: "s", help: "A numerical-sensitivity check: events shorter than the step can be missed, and totals change by about the event resolution." },
];

export interface SweepBase {
  site: { site_id?: string | null; lat?: number | null; lon?: number | null };
  siteLabel: string;
  startUtc: string; // ISO with Z
  days: number;
  bandM: number;
  heightM: number | null; // null = the backend's 2.0 m default assumption
  stepS: number;
}

export type ParseResult<T> = { ok: true; value: T } | { ok: false; error: string };

const round = (v: number, d = 3) => Number(v.toFixed(d));

/** n evenly spaced numbers from a to b inclusive (request construction only). */
export function linspace(a: number, b: number, n: number): number[] {
  if (n === 1) return [a];
  return Array.from({ length: n }, (_, i) => round(a + ((b - a) * i) / (n - 1)));
}

/** n evenly spaced instants from a to b inclusive, rounded to the minute, as ISO UTC strings. */
export function dateRange(aIso: string, bIso: string, n: number): string[] {
  const a = Date.parse(aIso);
  const b = Date.parse(bIso);
  return Array.from({ length: n }, (_, i) => {
    const t = n === 1 ? a : a + ((b - a) * i) / (n - 1);
    return new Date(Math.round(t / 60000) * 60000).toISOString().replace(".000Z", "Z");
  });
}

/** "2027-01-15, 2027-02-10T12:00" -> ISO UTC strings. */
export function parseDateList(text: string): ParseResult<string[]> {
  const parts = text.split(/[\s,;]+/).filter(Boolean);
  if (parts.length === 0) return { ok: false, error: "Enter at least one date." };
  const out: string[] = [];
  for (const p of parts) {
    if (!/^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2})?$/.test(p)) return { ok: false, error: `“${p}” is not a date like 2027-01-15 or 2027-01-15T12:00.` };
    const iso = `${p.length === 10 ? `${p}T00:00` : p}:00Z`;
    if (Number.isNaN(Date.parse(iso))) return { ok: false, error: `“${p}” is not a real date.` };
    out.push(iso);
  }
  return { ok: true, value: out };
}

export function parseNumberList(text: string): ParseResult<number[]> {
  const parts = text.split(/[\s,;]+/).filter(Boolean);
  if (parts.length === 0) return { ok: false, error: "Enter at least one value." };
  const out: number[] = [];
  for (const p of parts) {
    const v = Number(p);
    if (!Number.isFinite(v)) return { ok: false, error: `“${p}” is not a number.` };
    out.push(v);
  }
  return { ok: true, value: out };
}

/** Light checks only: the backend validates the real limits and its message is shown verbatim. */
export function checkCount(n: number): string | null {
  if (n < 2) return "A sweep needs at least 2 values.";
  if (n > MAX_SWEEP_POINTS) return `At most ${MAX_SWEEP_POINTS} values per sweep (the backend's limit per comparison).`;
  return null;
}

export type SweepValue = number | string;

/** Label for one sweep value (what the table and chart call it). */
export function valueLabel(param: SweepParam, v: SweepValue): string {
  if (param === "start") return String(v).slice(0, 16).replace("T", " ");
  const unit = SWEEP_PARAMS.find((p) => p.id === param)!.unit;
  return `${v} ${unit}`;
}

/** The explicit scenario list sent to /scenarios/compare: the base scenario with ONE parameter varied. */
export function buildScenarios(base: SweepBase, param: SweepParam, values: SweepValue[]): ScenarioReq[] {
  return values.map((v) => ({
    site: { site_id: base.site.site_id ?? null, lat: base.site.lat ?? null, lon: base.site.lon ?? null },
    start_utc: param === "start" ? (v as string) : base.startUtc,
    duration_days: param === "length" ? (v as number) : base.days,
    position_uncertainty_m: param === "band" ? (v as number) : base.bandM,
    observer_height_m: param === "height" ? (v as number) : base.heightM,
    step_seconds: param === "step" ? (v as number) : base.stepS,
    label: valueLabel(param, v),
  }));
}

/** Table export of what is on screen. Numbers are the backend's, written as received (no rounding, no derived columns). */
export function toCsv(param: SweepParam, values: SweepValue[], scenarios: ScenarioResult[]): string {
  const q = (s: string | number | null | undefined) => (s === null || s === undefined ? "" : /[",\n]/.test(String(s)) ? `"${String(s).replaceAll('"', '""')}"` : String(s));
  const head = [
    SWEEP_PARAMS.find((p) => p.id === param)!.label, "status",
    "sun_visible_fraction_terrain_corrected", "sun_band_low", "sun_band_high", "sun_visible_fraction_geometric",
    "earth_visible_fraction_terrain_corrected", "earth_band_low", "earth_band_high", "earth_visible_fraction_geometric",
    "sun_longest_not_visible_s", "sun_longest_not_visible_includes_open_interval",
    "earth_longest_not_visible_s", "earth_longest_not_visible_includes_open_interval", "reason",
  ];
  const rows = scenarios.map((s, i) => {
    if (s.status !== "supported" || !s.bodies) return [valueLabel(param, values[i]), "terrain_data_insufficient", ...Array(12).fill(""), s.reason ?? ""];
    const { sun, earth } = s.bodies;
    const f = (b: typeof sun) => [b.terrain_corrected.visible_fraction.nominal, b.terrain_corrected.visible_fraction.band[0], b.terrain_corrected.visible_fraction.band[1], b.geometric.visible_fraction.nominal];
    const l = (b: typeof sun) => [b.terrain_corrected.longest_not_visible_s.including_open, b.terrain_corrected.longest_not_visible_s.includes_open_interval];
    return [valueLabel(param, values[i]), "supported", ...f(sun), ...f(earth), ...l(sun), ...l(earth), ""];
  });
  return [head, ...rows].map((r) => r.map(q).join(",")).join("\n") + "\n";
}
