import type { Interval } from "../api/types";
import { addSecondsIso, secondsBetween } from "../format";

// Visibility timeline. Bars are the backend's intervals; whiskers are the backend's position-sensitivity band
// for each boundary; dashed outlines mark intervals cut off by the window edge (decision C4: display only).

const W = 1000;
const LABEL = 170;
const RIGHT = 12;

export interface TimelineRow {
  label: string;
  sub?: string;
  visible: Interval[];
  notVisible: Interval[];
  color: string;
  withBands: boolean;
}

function tickStepDays(windowS: number): number {
  const days = windowS / 86400;
  for (const s of [1, 2, 5, 7, 10, 14, 30, 60, 90]) if (days / s <= 10) return s;
  return 120;
}

export function Timeline({
  startUtc,
  windowS,
  rows,
  cursorS,
  onPick,
}: {
  startUtc: string;
  windowS: number;
  rows: TimelineRow[];
  cursorS?: number | null;
  onPick?: (seconds: number) => void;
}) {
  const rowH = 34;
  const top = 8;
  const H = top + rows.length * rowH + 30;
  const x = (s: number) => LABEL + (Math.min(Math.max(s, 0), windowS) / windowS) * (W - LABEL - RIGHT);
  const step = tickStepDays(windowS);
  const ticks: number[] = [];
  for (let d = 0; d * 86400 <= windowS + 1; d += step) ticks.push(d * 86400);

  const bar = (iv: Interval, ry: number, h: number, color: string, key: string, opacity = 1) => {
    const open = iv.open_start || iv.open_end;
    return (
      <rect
        key={key}
        x={x(iv.start_s)}
        y={ry}
        width={Math.max(1, x(iv.end_s) - x(iv.start_s))}
        height={h}
        fill={color}
        opacity={opacity}
        stroke={open ? "var(--warn)" : "none"}
        strokeWidth={open ? 1.5 : 0}
        strokeDasharray={open ? "4 2" : undefined}
      >
        <title>{`${iv.start_utc} → ${iv.end_utc}${open ? " (cut off by the window edge: true length is at least this)" : ""}`}</title>
      </rect>
    );
  };

  const whisker = (band: Interval["start_band"], nominalS: number, cy: number, key: string) => {
    if (!band) return null;
    const a = secondsBetween(startUtc, band.earliest_utc);
    const b = secondsBetween(startUtc, band.latest_utc);
    const wide = Math.abs(x(b) - x(a)) < 1.5;
    return (
      <g key={key} stroke="var(--accent)" strokeWidth={1.5} opacity={band.complete ? 1 : 0.7}>
        <line x1={x(a)} x2={x(b)} y1={cy} y2={cy} strokeDasharray={band.complete ? undefined : "3 2"} />
        <line x1={x(a)} x2={x(a)} y1={cy - 4} y2={cy + 4} />
        <line x1={x(b)} x2={x(b)} y1={cy - 4} y2={cy + 4} />
        <circle cx={x(nominalS)} cy={cy} r={2.2} fill="var(--surface)" />
        <title>{`position band ${band.earliest_utc} to ${band.latest_utc}${band.complete ? "" : " (incomplete: some displaced runs lack this event)"}${wide ? "" : ""}`}</title>
      </g>
    );
  };

  return (
    <figure style={{ margin: 0 }}>
      <svg
        className="plot"
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label="Visibility timeline"
        onClick={(e) => {
          if (!onPick) return;
          const r = e.currentTarget.getBoundingClientRect();
          const vx = ((e.clientX - r.left) / r.width) * W;
          if (vx < LABEL || vx > W - RIGHT) return;
          onPick(((vx - LABEL) / (W - LABEL - RIGHT)) * windowS);
        }}
        style={{ cursor: onPick ? "crosshair" : "default" }}
      >
        {ticks.map((t) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={top} y2={H - 26} className="axis" opacity={0.5} />
            <text x={x(t)} y={H - 12} textAnchor="middle" className="muted">{addSecondsIso(startUtc, t).slice(5, 10)}</text>
          </g>
        ))}
        {rows.map((r, i) => {
          const ry = top + i * rowH;
          const h = r.withBands ? 16 : 9;
          const by = ry + (r.withBands ? 8 : 12);
          return (
            <g key={r.label}>
              <text x={4} y={ry + 14} fontWeight={600}>{r.label}</text>
              {r.sub && <text x={4} y={ry + 26} className="muted" fontSize="9">{r.sub}</text>}
              {r.notVisible.map((iv, k) => bar(iv, by, h, "var(--dark)", `n${k}`, 0.35))}
              {r.visible.map((iv, k) => bar(iv, by, h, r.color, `v${k}`))}
              {r.withBands &&
                [...r.visible, ...r.notVisible].flatMap((iv, k) => [
                  iv.open_start ? null : whisker(iv.start_band, iv.start_s, by + h + 5, `s${k}`),
                  iv.open_end ? null : whisker(iv.end_band, iv.end_s, by + h + 5, `e${k}`),
                ])}
            </g>
          );
        })}
        {cursorS !== null && cursorS !== undefined && (
          <line x1={x(cursorS)} x2={x(cursorS)} y1={top} y2={H - 26} stroke="var(--text)" strokeWidth={1.5} strokeDasharray="2 2" />
        )}
      </svg>
      <div className="legend">
        <span><i style={{ background: "var(--sun)" }} />visible (coloured bar)</span>
        <span><i style={{ background: "var(--dark)", opacity: 0.5 }} />not visible</span>
        <span><i style={{ border: "1.5px dashed var(--warn)" }} />cut off by the window edge</span>
        <span><i style={{ background: "var(--accent)", height: 2, verticalAlign: 3 }} />position-uncertainty band of the boundary (dashed = incomplete)</span>
      </div>
    </figure>
  );
}
