# Stage 10 extras — Tier 1 completion report (branch `feature/stage10-extras`, NOT merged)

Base: `main` at `ab55edf`. This branch contains display-layer changes only: **no backend, engine, API, data or science change** (`git diff main --stat` touches `web/` and `docs/stage10x/` only). Main is untouched; the submission does not depend on this branch.

## 1. What was built
| Item | Where | What it does |
|---|---|---|
| **Landing sites** tab (historical landing-site comparison) | `web/src/views/SitesTab.tsx`, tab added in `App.tsx` | Side-by-side table, one column per confirmed landing site (IM-1, IM-2, Chandrayaan-3; the IM-2 *intended target* is excluded as it is not a landing). One window, one POST to the existing `/scenarios/compare`. Rows: terrain windows used, ground height, horizon range, Sun and Earth visible (terrain-corrected with its position band, and geometric beside it), longest period without Sun, longest Earth blackout. |
| Advanced plots panel | `web/src/components/AdvancedPlots.tsx`, wired into `ViewTab.tsx` | (a) **Sky chart**: polar plot of the terrain horizon with the Sun and Earth tracks (filled = headline visible, hollow = not), start/end markers, lower-bound azimuths marked; (b) **horizon profile detail**: horizon elevation by azimuth with the distance to the limiting terrain beneath; (c) **Sun and Earth elevation over time** on one axis with each body's horizon at its own azimuth, date grid, visible bars, zoom sliders and an inspect cursor with a numeric readout. One azimuth slider drives the sky chart and horizon detail readout. |
| Types | `web/src/api/types.ts` | Optional fields the API **already returns** (`limiting_pixel_size_m`; scenario `observer`, `horizon`, `limitations`). Types only. |

## 2. Honesty rules, as implemented and tested
* **Insufficient sites**: IM-1's column shows the words "terrain data insufficient" in *every* row (test: all nine metric cells are exactly that text, no digit anywhere), no rank, and the existing `Insufficient` box with the backend's reason. Chandrayaan-3 is shown as the backend returns it: supported, and flagged **"terrain not yet approved"** — the flag is read from the backend's own limitation text ("registered but NOT yet approved"), not hard-coded to a site. IM-2 carries no flag.
* **Bands and geometric** are shown beside every terrain-corrected number, as in Compare; "cut off" is shown for open intervals.
* A body the backend reports as never blocked shows "none: visible throughout the window" (only when the backend's longest-period is null **and** its fraction is exactly 100 %), instead of a bare dash.
* Lower-bound horizons (truncated / data gap) are marked red in every plot and the azimuth readout says "lower bound", never "certified".
* The sky chart's radial scale is zoomed (and says so on the figure); it is not true sky geometry.

## 3. C4 (display only) — enforced three ways
1. **Request-count tests** (`web/src/Tier1.test.tsx`): the Landing sites tab makes zero requests until Run, then exactly one `POST /scenarios/compare` (body asserted) and nothing else; interacting with the result and editing the form makes none; a second Run makes exactly one more. In the View tab, moving the azimuth slider, the inspect slider, both zoom sliders and Reset zoom makes **zero** requests.
2. **Values come from the backend arrays**: tests set the sliders and assert the readouts equal the stubbed arrays (horizon elevation, distance, Sun/Earth azimuth/elevation at the chosen sample, UTC time of the sample).
3. **Static tests**: `AdvancedPlots.tsx` has no `fetch`, no API-client import, and imports only React, the types and the formatters; trigonometry appears only inside `polarXY` (projecting a backend azimuth/elevation to screen pixels — the same drawing-only use as `SiteMap.tsx`); `SitesTab.tsx` has no math functions and only calls `api.compare`.

## 4. Verification
* `npm run typecheck` clean; `npm run build` clean.
* Frontend tests: **127 pass** (108 existing — one edited, the tab-list expectation in `a11y.test.tsx` — plus 19 new). axe-core: no violations on the Landing sites tab (empty and with results) or on the View tab with the advanced panel.
* Real browser against the live backend (Chrome headless, real IM-1/IM-2/Chandrayaan-3 results): `tier1_sites.png`, `tier1_advanced_plots.png`. Observed: IM-1 label in every row; IM-2 Sun 48.6 % [45.4, 48.9] vs 53.3 % geometric (same as the validated reports); Chandrayaan-3 49.1 % [48.5, 49.4] with the not-approved flag; horizon ranges −1.47…4.07° (IM-2) and 0.53…2.47° (Chandrayaan-3).
* Backend untouched, so the 364 backend tests are unaffected (not re-run on this branch for that reason).

## 5. Limitations / decisions for you
* The comparison uses one common window for all sites (default 2027-01-15, 30 d); it is **not** a replay of each mission's real date, and says so on screen.
* The "terrain used" row lists window ids as returned (e.g. `im2_20m_r80km`); pixel size is not shown there because the scenario response carries ids, not sizes. Showing sizes would need an extra existing call (`/dem/windows`) — not done, to keep one request.
* Plot data are decimated for drawing only when there are more than ~900 samples (every n-th dot); the readouts always use the full arrays.
* Nothing here changes a capability status.

## 6. Ready for your review
Nothing from this branch is merged. To look: `cd ../nasa-space-apps-stage10-extras/web && npm run dev -- --port 5174` (backend on :8000).
