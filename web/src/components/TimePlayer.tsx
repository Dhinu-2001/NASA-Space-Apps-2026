import { useEffect, useRef, useState } from "react";
import type { BodySeries, VisibilityResponse } from "../api/types";
import { addSecondsIso, fmtDeg, fmtUtc } from "../format";

// Interactive time scrubber and animation. Every frame is ONE sample the backend already computed (az/el, terrain horizon,
// visibility states): nothing is interpolated or calculated here (decision C4). Playback only changes which sample is shown.

const SPEEDS = [
  { label: "slow (12 samples/s)", perSecond: 12 },
  { label: "normal (48 samples/s)", perSecond: 48 },
  { label: "fast (192 samples/s)", perSecond: 192 },
] as const;

export function prefersReducedMotion(): boolean {
  try {
    return typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch {
    return false;
  }
}

export function sampleTimeUtc(vis: VisibilityResponse, i: number): string {
  const s = vis.bodies.sun.series ?? vis.bodies.earth.series;
  return addSecondsIso(vis.window.start_utc, s ? s.times_s[i] : 0);
}

function Readout({ name, series, i, headline }: { name: "sun" | "earth"; series: BodySeries; i: number; headline: string }) {
  const robust = series.headline_state_robust_to_position;
  return (
    <div className="card" data-testid={`player-${name}`}>
      <h3 className={name === "sun" ? "sun-c" : "earth-c"}>{name === "sun" ? "Sun" : "Earth"}</h3>
      <div>
        az {fmtDeg(series.azimuth_deg[i], 1)} · el {fmtDeg(series.elevation_deg[i], 2, true)} · terrain horizon {fmtDeg(series.terrain_horizon_at_centre_deg[i], 2, true)}
      </div>
      <div>
        {headline.replaceAll("_", " ")}: <strong>{series.headline_visible[i] ? "VISIBLE" : "BLOCKED"}</strong>
        {robust && !robust[i] ? <span className="flag">changes with position</span> : null}
        {!series.horizon_complete[i] ? <span className="flag bad">horizon incomplete</span> : null}
      </div>
      {series.position_sensitivity_deg ? <div className="band">horizon could change by up to {fmtDeg(series.position_sensitivity_deg[i], 2)} for the assumed position error</div> : null}
    </div>
  );
}

export function TimePlayer({
  vis,
  index,
  onIndex,
}: {
  vis: VisibilityResponse;
  index: number | null;
  onIndex: (i: number | null) => void;
}) {
  const sun = vis.bodies.sun.series;
  const earth = vis.bodies.earth.series;
  const n = (sun ?? earth)?.times_s.length ?? 0;
  const reduced = prefersReducedMotion();
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const nSamples = (sun ?? earth)?.times_s.length ?? 0;
  const idx = Math.min(Math.max(index ?? 0, 0), Math.max(0, nSamples - 1));   // never leave the window
  const idxRef = useRef(idx);
  idxRef.current = idx;
  const onIndexRef = useRef(onIndex);
  onIndexRef.current = onIndex;   // keep the playback timer stable even if the parent passes a new callback each render

  useEffect(() => {
    if (!playing) return;
    const perSecond = SPEEDS[speed].perSecond;
    const tick = 100; // ms
    const id = setInterval(() => {
      const next = idxRef.current + Math.max(1, Math.round((perSecond * tick) / 1000));
      idxRef.current = Math.min(next, n - 1);   // advance immediately: playback must not depend on when React re-renders
      if (next >= n - 1) {
        onIndexRef.current(n - 1);
        setPlaying(false);
      } else {
        onIndexRef.current(next);
      }
    }, tick);
    return () => clearInterval(id);
  }, [playing, speed, n]);

  if (n < 2) return null;
  const step = vis.window.step_seconds;
  const t = sampleTimeUtc(vis, idx);
  const go = (i: number) => onIndex(Math.min(n - 1, Math.max(0, i)));
  const stepMin = Math.round(step / 60);

  return (
    <section className="player" aria-label="Time player">
      <div className="row" style={{ alignItems: "center" }}>
        <div className="player-buttons" role="group" aria-label="Playback controls" style={{ flex: "0 0 auto", display: "flex", gap: 6, flexWrap: "wrap" }}>
          <button className="btn secondary" aria-label="Go to the start of the window" onClick={() => { setPlaying(false); go(0); }}>⏮</button>
          <button className="btn secondary" aria-label="Previous sample" onClick={() => { setPlaying(false); go(idx - 1); }}>◀</button>
          <button
            className="btn"
            aria-pressed={playing}
            disabled={reduced}
            title={reduced ? "Autoplay is off because your system asks for reduced motion; use the slider or the step buttons" : undefined}
            onClick={() => { if (idx >= n - 1) go(0); setPlaying((p) => !p); }}
          >
            {playing ? "⏸ Pause" : "▶ Play"}
          </button>
          <button className="btn secondary" aria-label="Next sample" onClick={() => { setPlaying(false); go(idx + 1); }}>▶</button>
          <button className="btn secondary" aria-label="Go to the end of the window" onClick={() => { setPlaying(false); go(n - 1); }}>⏭</button>
        </div>
        <div style={{ flex: "0 1 210px" }}>
          <label htmlFor="player-speed">Speed</label>
          <select id="player-speed" value={speed} onChange={(e) => setSpeed(Number(e.target.value))}>
            {SPEEDS.map((s, k) => <option key={s.label} value={k}>{s.label}</option>)}
          </select>
        </div>
        <button className="btn secondary" style={{ flex: "0 0 auto" }} disabled={index === null} onClick={() => { setPlaying(false); onIndex(null); }}>
          Back to the chosen time
        </button>
      </div>

      <label htmlFor="player-slider">Time within the window (sample {idx + 1} of {n}, every {stepMin} min)</label>
      <input
        id="player-slider"
        type="range"
        min={0}
        max={n - 1}
        step={1}
        value={idx}
        aria-valuetext={fmtUtc(t)}
        onChange={(e) => { setPlaying(false); go(Number(e.target.value)); }}
        style={{ width: "100%" }}
      />
      <p className="big" data-testid="player-time" aria-live={playing ? "off" : "polite"}>{fmtUtc(t)}</p>
      {index !== null && (
        <div className="cards">
          {sun && <Readout name="sun" series={sun} i={idx} headline={vis.bodies.sun.headline_state} />}
          {earth && <Readout name="earth" series={earth} i={idx} headline={vis.bodies.earth.headline_state} />}
        </div>
      )}
      <p className="help">
        Each frame is one sample computed by the backend ({stepMin}-minute steps); nothing is interpolated between samples, so a brief event between two samples is not shown.
        {reduced ? " Autoplay is disabled because your system requests reduced motion." : ""}
      </p>
    </section>
  );
}
