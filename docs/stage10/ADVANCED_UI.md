# Stage 10 (core) — Interaction and education layer

Status: implemented for the core items the owner selected (1–4 below); **unvalidated until the Stage 10 gate is approved**. The UI has no engine capability of its own, so no capability status changes. Code: `web/src/components/TimePlayer.tsx`, `web/src/learn.tsx`, `web/src/profiles.tsx`, `web/src/App.tsx`, `web/src/styles.css`. Screenshots (real app, real backend): `view_player_learn.png`, `learn_tab.png`, `view_mobile_player.png`.

**Scope decision (owner):** items 1–4 now. Deferred and **not built**: detailed 3D lunar terrain, historical landing-site comparisons as a new feature, advanced scenario exploration, advanced scientific visualisation. See §6.

## 1. Interactive time scrubbing and animated Sun/Earth movement
A **time player** in the Terrain horizon panel (Site & time tab): slider over the whole window, play/pause, step back/forward, jump to start/end, three speeds, and "back to the chosen time".
* **Every frame is one sample the backend already computed** (azimuth, elevation, terrain horizon, visibility states, position-sensitivity). Nothing is interpolated or calculated: playback only changes *which* sample is shown. The panel says so, including that a brief event between two samples is not shown.
* While scrubbing, the Sun/Earth cards, the Sun and Earth markers on the horizon plot, the timeline cursor and both elevation-chart cursors all follow the sample. The cards read from the same series (the `/visibility/at` result and the series have the same shape), so **scrubbing makes zero API requests** (asserted by a test that counts requests).
* Every number shown while scrubbing keeps its flags: "changes with position", "horizon incomplete: upper bound", and the position-sensitivity band for that sample.
* Clicking a timeline also moves the player. Deep link for demos: `?scrub=<sample index>`.
* **Reduced motion:** if the system asks for reduced motion, autoplay is disabled (with an explanation); the slider and step buttons still work. The time readout announces politely only when not playing.
* Two defects found while testing and fixed: the playback timer was recreated on every render, and ticks computed from a stale index; both made playback depend on React's render timing.

## 2. Educational mode
* **Learn mode** toggle (header; remembered in the browser, default off; works if storage is blocked): short plain-language explanations under the panels (Sun/Earth now, horizon, player, timelines, bands, profiles, Compare, Delay, solar).
* **Learn tab:** the seven-step workflow, why lighting near the poles is different, a **live example read from the backend** (IM-2: terrain-corrected vs geometric fractions with the position band — shown to follow the API, not hard-coded), "how sure can we be?", and a glossary.
* Educational text is explanation only; the only numbers on the tab come from the backend. Claim check against the project's own evidence:

| Statement | Supported by |
|---|---|
| No atmosphere, so no refraction and sharp shadows | Stage 3 method (airless; refraction none on the Moon) |
| Near the poles the Sun stays low and circles the sky | Stage 3 tests (Sun elevation within ±1.6° at the pole, lunar axial tilt 1.54°); IM-2 chart (Sun within about ±6°) |
| A full cycle takes about 29.5 days | Methodology §4 (synodic month); the IM-2 timelines |
| The Earth stays low and rises/sets slowly (libration) | IM-2 Earth elevation range and events (set 27 Jan, rise 2 Feb) |
| A 100 m position error moves the horizon up to about 1.8° (several Sun diameters) | Stage 4 `RESOLUTION.md` (1.76°); Sun disc 0.53° |
| LOLA / DEM / SPICE descriptions | Stage 2 docs, provenance report |
| "Validated" ≠ proven against measurement | Stage 9 `VALIDATION_REPORT.md` §1 |
The text was written by the project from its documented results; it has **not** been reviewed by an educator or a planetary scientist (limitation L-P8).

## 3. Accessibility pass
Evidence: automated `axe-core` audit on every tab (including the View tab computed, scrubbing, with Learn mode on), keyboard tests, contrast computed from the real stylesheet, and browser rehearsal with a clean console.
* **Defects axe found and fixed:** the site map was `role="img"` but contained focusable site markers (nested interactive controls, *serious*) → now a labelled `group`; every Learn explanation was a duplicate-named landmark → plain notes.
* **Contrast defects found and fixed** (computed WCAG ratios, light theme): Sun text colour 2.77:1 → new `--sun-text` 5.56:1; Sun graphics 2.77:1 → 3.27:1; warning text on its pale background 4.34:1 → 4.92:1; dark-theme buttons (white on light blue, about 2.3:1) → dark text 7.84:1. All text pairs now ≥ 4.5:1 and all graphic pairs ≥ 3:1 in both themes (tested, 48 contrast cases).
* **Keyboard:** WAI-ARIA tabs pattern (arrow keys, Home/End, roving tab index, tabpanel linked to its tab), skip link to the current panel, visible 3 px focus outline, tab targets ≥ 44 px and controls ≥ 40 px, slider and buttons fully operable by keyboard.
* **Other:** `prefers-reduced-motion` honoured, `forced-colors` outlines, charts keep text alternatives and the same data is in the tables, the horizon chart's accessible label now states the elevation range from the backend summary.
* **Not done:** no screen-reader walkthrough with real assistive technology; axe cannot check colour contrast without layout, hence the separate token test (which checks tokens, not every rendered combination).

## 4. Configurable mission profiles
Named bundles of **existing** form parameters (window length, observer height, position uncertainty) in Site & time, Compare and Delay: five built-in profiles (14 / 30 / 60-day windows; ±20 m and ±200 m position knowledge) and **user-saved profiles** (browser-local; corrupt or blocked storage tolerated; invalid entries dropped).
* They only fill in the form. The built-in ones are labelled **illustrative assumptions, not real mission requirements**; an empty observer height means the 2.0 m default assumption.
* The ±200 m profile is deliberately included because Stage 5 showed that results change qualitatively at that level.

## 5. Rules from the decision log
* **C2/C4:** the new code uses `Math` only for index clamping and playback stepping; no trigonometry, no astronomy, terrain or visibility logic was added (grep audit). The only trig in the UI remains the orientation map's layout.
* **Bands and flags** remain visible while scrubbing; **insufficient sites** still get a label and no player (tested); **capability status** tags are unchanged.
* **Performance:** scrubbing makes no requests; the bundle grew from 281 KB to 314 KB (94.7 KB gzipped); browser console clean on all tabs and on a 500 px view.

## 6. Deferred (not built) and why
| Item | Reason |
|---|---|
| Detailed 3D lunar terrain | Needs a new backend endpoint for a decimated heightmap (labelled `measured_interpolated`, decimated), a 3D library over a slow network, and covers IM-2 only; highest risk to the gate "must not compromise scientific accuracy or performance". Recommended only if time remains after Stage 11. |
| Historical landing-site comparisons | Compare already does site comparison honestly; IM-1 correctly stays "terrain data insufficient"; Chandrayaan-3 (60 m terrain, 2026-11-15) is supported with a not-yet-approved caveat. |
| Advanced scenario exploration; advanced scientific visualisation | Not selected for the core scope. |

## 7. Tests (`web/src`: 108 frontend tests in 5 files; backend unchanged at 357)
`TimePlayer.test.tsx` (10): slider semantics, readouts straight from the series with flags and band, stepping and clamping, playback and stop at the end, pause/hand-back, no network use, reduced motion, polite announcements. `Stage10.test.tsx` (17): scrubbing in the real View tab with a request count, markers and cursor move, no player for an insufficient site, Learn mode (default off, persistence, broken storage, per-panel explanations, Learn tab content, live example follows the API, insufficient and error cases), profiles (apply, keep height, labels, save/persist/delete, validation, corrupt/unavailable storage, real form, Compare and Delay). `a11y.test.tsx` (58): tabs pattern, skip link, landmarks, axe on every tab, contrast tokens, reduced-motion/forced-colours/focus CSS. A mutation check (breaking the scrub wiring) was confirmed to fail the integration test.

## 8. Limitations
* The player replays samples at the step the scenario was computed with (15 minutes for windows up to 30 days); it is not a continuous simulation.
* No 3D view; the map is an orientation aid.
* Educational content is static, written by the project, and not independently reviewed (L-P8).
* Saved profiles and the Learn setting live in one browser only.
