// Presentation helpers only: unit formatting and axis arithmetic. No scientific computation lives here (decision C4).

export const DASH = "—";

/** "2027-01-28T08:58:55Z" -> "2027-01-28 08:58:55 UTC" */
export function fmtUtc(iso: string | null | undefined): string {
  if (!iso) return DASH;
  return iso.replace("T", " ").replace(/\.\d+Z$/, "Z").replace("Z", " UTC");
}

export function fmtDur(s: number | null | undefined): string {
  if (s === null || s === undefined) return DASH;
  const a = Math.abs(s);
  if (a >= 172800) return `${(s / 86400).toFixed(1)} d`;
  if (a >= 7200) return `${(s / 3600).toFixed(1)} h`;
  if (a >= 120) return `${(s / 60).toFixed(0)} min`;
  return `${s.toFixed(0)} s`;
}

export function fmtPct(f: number | null | undefined, digits = 1): string {
  return f === null || f === undefined ? DASH : `${(f * 100).toFixed(digits)} %`;
}

export function fmtDeg(v: number | null | undefined, digits = 2, signed = false): string {
  if (v === null || v === undefined) return DASH;
  return `${signed && v > 0 ? "+" : ""}${v.toFixed(digits)}°`;
}

export function fmtBand(band: [number | null, number | null] | null | undefined, f: (v: number) => string): string {
  if (!band || band[0] === null || band[1] === null) return DASH;
  return `${f(band[0])} to ${f(band[1])}`;
}

export const statusLabel = (s: string) => s.replaceAll("_", " ");

/** Convert a <input type="datetime-local"> value (read as UTC) to the API's ISO form. */
export function localInputToUtc(v: string): string {
  const base = v.length === 16 ? `${v}:00` : v;
  return `${base}Z`;
}

export function utcToLocalInput(iso: string): string {
  return iso.replace("Z", "").slice(0, 16);
}

/** Seconds between two ISO UTC strings (axis placement of a band edge). */
export function secondsBetween(fromIso: string, toIso: string): number {
  return (Date.parse(toIso) - Date.parse(fromIso)) / 1000;
}

export function addSecondsIso(iso: string, s: number): string {
  return new Date(Date.parse(iso) + s * 1000).toISOString().replace(".000Z", "Z");
}

/** Wh -> "143.0 kWh" / "820 Wh" (presentation only). */
export function fmtEnergy(wh: number | null | undefined): string {
  if (wh === null || wh === undefined) return DASH;
  return Math.abs(wh) >= 1000 ? `${(wh / 1000).toFixed(1)} kWh` : `${wh.toFixed(0)} Wh`;
}

export function fmtPower(w: number | null | undefined): string {
  return w === null || w === undefined ? DASH : `${w.toFixed(1)} W`;
}

export function fmtHours(h: number | null | undefined): string {
  if (h === null || h === undefined) return DASH;
  return Math.abs(h) >= 48 ? `${(h / 24).toFixed(1)} d` : `${h.toFixed(1)} h`;
}
