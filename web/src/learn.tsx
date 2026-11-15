import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api } from "./api/client";
import { fmtBand, fmtPct, fmtUtc } from "./format";
import { useAsync } from "./hooks";
import { ErrorBox, Insufficient, Loading, Panel } from "./ui";

// Educational mode. Everything here is explanation of what the application shows, written from the project's own
// documented method and results. The only numbers are the live example, which is read from the backend (decision C4).

const STORAGE_KEY = "lunarnav.learn";

function readStored(): boolean {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === "1";
  } catch {
    return false; // storage can be unavailable (private window, blocked site data): the app works without it
  }
}

interface LearnState {
  learn: boolean;
  toggle: () => void;
}

const LearnContext = createContext<LearnState>({ learn: false, toggle: () => undefined });

export function LearnProvider({ children }: { children: ReactNode }) {
  const [learn, setLearn] = useState<boolean>(() => readStored() || (typeof window !== "undefined" && window.location.search.includes("learn=1")));
  const toggle = useCallback(() => setLearn((v) => !v), []);
  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, learn ? "1" : "0");
    } catch {
      /* ignore: per-viewer convenience only */
    }
  }, [learn]);
  return <LearnContext.Provider value={{ learn, toggle }}>{children}</LearnContext.Provider>;
}

export const useLearn = () => useContext(LearnContext);

export function LearnToggle() {
  const { learn, toggle } = useLearn();
  return (
    <button className="btn secondary learn-toggle" aria-pressed={learn} onClick={toggle} title="Show short plain-language explanations under each panel">
      Learn mode: {learn ? "on" : "off"}
    </button>
  );
}

export const EXPLAIN: Record<string, string> = {
  sunEarthNow:
    "These are the directions of the Sun and the Earth as seen from the landing site at the chosen time. Below each is the time until it sets (is hidden behind the terrain) or rises, with the band for the assumed position error. Azimuth is the compass direction (0° = north, increasing clockwise); elevation is the angle above the local flat horizontal. The terrain horizon is how high the surrounding ground reaches in that same direction: a body can only be seen if it is higher than the terrain there.",
  horizon:
    "The brown shape is the terrain skyline around the lander, built from laser-altimeter (LOLA) elevation data. The yellow and blue dots show where the Sun and the Earth travel across the sky during the whole window. Wherever a path dips below the brown shape, that body is hidden by terrain. Near the lunar poles the Sun stays very low in the sky, so even modest hills decide when there is sunlight.",
  player:
    "Drag the slider or press Play to step through the calculated samples. Each frame is a real sample computed by the backend; nothing is smoothed or guessed in between.",
  timelines:
    "Coloured bars show when each body is visible with the terrain taken into account. The thin bars underneath ignore terrain (geometric), so the gap between the two is the effect of the terrain. Short blue whiskers show how far an event time could move if the landing position were off by the stated distance. A dashed outline means the interval is cut off by the edge of the window, so it is at least that long.",
  bands:
    "A “band” shows how far a number could move if the assumed landing position is wrong by the stated distance (default 100 m). It is a sensitivity to the input position, not an error bar on the physics. Totals and fractions are fairly stable (a few percent). The exact time of an event close to the horizon can move by hours, because the Sun and the Earth change elevation very slowly there.",
  compare:
    "Compare puts scenarios side by side: the same site on different dates, or different sites. A difference is called clear only when its uncertainty band does not include zero. Sites without enough terrain data are shown as “terrain data insufficient” and never ranked or estimated.",
  delay:
    "The delay simulator shifts the whole window later by the number of days you list. Because the same position error applies to both dates, the difference between them is often more certain than either value on its own.",
  solar:
    "This estimate is an upper bound: it assumes a panel that always faces the Sun and counts a partly visible Sun as full light. It is not a power budget and not a battery state.",
  profiles:
    "Mission profiles only fill in the form (as soon as you choose one) with illustrative settings (window length, observer height, position uncertainty). They are examples for exploring the tool, not real mission requirements.",
};

export function Explain({ id }: { id: keyof typeof EXPLAIN | string }) {
  const { learn } = useLearn();
  const text = EXPLAIN[id];
  if (!learn || !text) return null;
  return (
    <div className="explain" data-testid={`explain-${id}`}>
      <strong>Learn:</strong> {text}
    </div>
  );
}

const STEPS = [
  "Pick a landing site on the map (or type your own coordinates) in the Site & time tab.",
  "Choose the start of a time window and the instant you want to look at (all times are UTC).",
  "Press Compute. The Sun and the Earth are placed in the sky of that site and compared with the terrain skyline.",
  "Look at the horizon plot: where a body's path dips below the brown skyline, it is hidden by terrain.",
  "Use the timelines and the time player to see when sunlight and Earth contact are available, and how long the dark and blackout periods last.",
  "Open Compare or the Delay simulator to put another site or date next to it, and read the differences together with their uncertainty.",
  "Check Data & assumptions to see where every number comes from and what it does not claim.",
];

const GLOSSARY: [string, string][] = [
  ["Azimuth", "Compass direction measured clockwise from local north (0° north, 90° east)."],
  ["Elevation", "Angle above the local flat horizontal (0° on the horizon, 90° overhead)."],
  ["Terrain horizon", "The highest angle reached by the ground in a given direction, seen from the site. Hills raise it, valleys lower it."],
  ["Geometric visibility", "Whether a body is above the local flat horizontal, ignoring terrain. Shown beside every terrain-corrected result."],
  ["Terrain-corrected visibility", "Whether a body is above the terrain horizon in its direction: the real line of sight."],
  ["Any part / centre / whole disc", "Three ways to count a body as visible: any part of its disc above the terrain (used for the Sun, any direct light), its centre (used for the Earth, antenna pointing), or its whole disc."],
  ["Position band", "How far a result could move if the landing position were wrong by the stated distance. A sensitivity to the input position, not an error bar on the physics."],
  ["Cut off", "An interval that touches the edge of the time window. Its true length is at least the value shown."],
  ["Upper bound", "A figure that cannot be exceeded under the stated assumptions, such as the idealised solar energy."],
  ["Terrain data insufficient", "The available terrain data cannot support a position-sensitivity result, so no figures are given for that site."],
  ["LOLA / DEM", "LOLA is the laser altimeter on NASA's Lunar Reconnaissance Orbiter; a DEM is the gridded elevation model made from its measurements."],
  ["Ephemeris (SPICE)", "The precise tables of where the Sun, Earth and Moon are at any time, from NASA/JPL, used through the NAIF SPICE toolkit."],
  ["UTC", "Coordinated Universal Time, used for every time shown, so there is no local-time ambiguity."],
  ["Validated", "In this project: implemented, tested, and approved by the project owner after reviewing the evidence. It does not mean proven against measurement."],
];

function LiveExample() {
  const s = useAsync((sig) => api.scenarioEvaluate({ site_id: "im2-athena" }, "2027-01-15T00:00:00Z", 30, 100, sig), "learn-example");
  return (
    <Panel title="A live example from the backend">
      {s.phase === "loading" && <Loading startedAt={s.startedAt} label="Loading the example" hint="The first calculation for a site can take about a minute; this one is normally cached." />}
      {s.phase === "error" && <ErrorBox error={s.error} what="Example" />}
      {s.phase === "ready" && s.data.status !== "supported" && <Insufficient reason={s.data.reason} />}
      {s.phase === "ready" && s.data.status === "supported" && s.data.bodies && (
        <>
          <p>
            IM-2 Athena landing site, 30 days from {fmtUtc(s.data.spec.start_utc)}, observer {s.data.spec.observer_height_m} m above the surface (an assumption), landing position uncertain by ±{s.data.spec.position_uncertainty_m} m:
          </p>
          <div className="scroll">
            <table>
              <thead><tr><th>Body</th><th className="num">Visible with terrain</th><th className="num">Visible ignoring terrain (geometric)</th></tr></thead>
              <tbody>
                {(["sun", "earth"] as const).map((b) => {
                  const body = s.data.bodies![b];
                  return (
                    <tr key={b}>
                      <td>{b === "sun" ? "Sun (any part)" : "Earth (centre)"}</td>
                      <td className="num">{fmtPct(body.terrain_corrected.visible_fraction.nominal)}<span className="band">band {fmtBand(body.terrain_corrected.visible_fraction.band, (v) => fmtPct(v))}</span></td>
                      <td className="num">{fmtPct(body.geometric.visible_fraction.nominal)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="help">The two columns differ because of the terrain: it can hide the Sun when the geometry says it is up, and on this high plateau it can also let the Earth be seen slightly below the local flat horizontal. Both columns are calculated by the backend; this page only displays them.</p>
        </>
      )}
    </Panel>
  );
}

export function LearnTab() {
  return (
    <div className="stack">
      <Panel title="How to use the app in seven steps">
        <ol className="plain">{STEPS.map((t) => <li key={t}>{t}</li>)}</ol>
      </Panel>

      <Panel title="Why lighting near the lunar poles is different">
        <ul className="plain">
          <li><strong>No atmosphere.</strong> There is no air to bend or scatter light, so shadows are sharp and a body is either above the terrain skyline or it is not.</li>
          <li><strong>A very low Sun.</strong> Close to the poles the Sun never climbs far above the horizon; it circles the sky staying low. A hill a few degrees high can therefore decide whether a site is lit.</li>
          <li><strong>Days last weeks.</strong> A full cycle of the Sun's motion takes about 29.5 Earth days, so sunlit and dark periods are measured in days, not hours (see the timelines).</li>
          <li><strong>The Earth hangs low in the sky</strong> for sites near the pole, rising and setting slowly over the month as the Moon's orientation librates, so Earth contact depends on terrain too.</li>
          <li><strong>Terrain decides.</strong> Ridges and crater rims control which directions are open to the Sun and the Earth, which is why this tool compares the sky with the real terrain skyline.</li>
        </ul>
      </Panel>

      <LiveExample />

      <Panel title="How sure can we be?">
        <ul className="plain">
          <li>The positions of the Sun and the Earth come from NASA/JPL ephemerides; the terrain comes from LOLA measurements. Both are used as published.</li>
          <li>The biggest uncertainty is <strong>where exactly the lander is</strong>. That is why every result shows a position band. A 100 m error moves the horizon at the example site by up to about 1.8°, comparable to several Sun diameters.</li>
          <li>Only some sites have enough terrain data. For the others the tool says “terrain data insufficient” rather than guessing.</li>
          <li>Results are geometric line of sight and direct illumination, not communication-link availability and not a power budget. The full list of limitations is in Data &amp; assumptions.</li>
        </ul>
      </Panel>

      <Panel title="Glossary">
        <dl className="glossary">
          {GLOSSARY.map(([term, def]) => (
            <div key={term}>
              <dt>{term}</dt>
              <dd>{def}</dd>
            </div>
          ))}
        </dl>
      </Panel>
    </div>
  );
}
