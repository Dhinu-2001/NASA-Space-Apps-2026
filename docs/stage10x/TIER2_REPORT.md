# Stage 10 extras — Tier 2 completion report (branch `feature/stage10-extras`, NOT merged)

Base: Tier 1 on this branch (itself based on `main` at `ab55edf`). Tier 2 is again **display layer only: no backend, engine, API, data or science change.** `scenarios.py` and every route are exactly as on main.

## 1. What was built — "Explore sweeps" tab
| Piece | File | Notes |
|---|---|---|
| Sweep tab | `web/src/views/ExploreTab.tsx` | Choose a base scenario (any catalogue site or custom lat/lon; start date; window length **or a start and end date**; position uncertainty; sampling step; observer height) and ONE parameter to vary: **start date, window length, position uncertainty, observer height, sampling step**. Values are typed as a list, or filled evenly from a first to a last value (2–12 points). A live preview lists the exact scenarios that will be requested. Baseline for the differences is selectable. |
| Request construction | `web/src/sweep.ts` | Pure helpers: build the scenario list (base scenario with exactly one parameter changed), even spacing, date/number list parsing, CSV export. No science. |
| Chart | `web/src/components/SweepChart.tsx` | Sun and Earth visible fraction across the swept values: terrain-corrected dot with its position-band bar, geometric value beside it; a labelled "n/a" marker for any scenario the backend calls terrain-data-insufficient (no point, no line across it); optional y-axis zoom; even or to-scale x spacing. |
| Table + export | in `ExploreTab.tsx` | One row per value: terrain-corrected with band, geometric, longest Sun darkness and Earth blackout with bands and "cut off", baseline marker, "from cache / computed now". CSV download of exactly the numbers shown. The existing `CompareResult` (deltas, paired/independent bands, rankings, reading guide) is reused in a collapsible section. |
| API client | `web/src/api/client.ts` | `compareScenarios(...)`: the existing `POST /scenarios/compare` in its existing explicit-`scenarios` form (each scenario overrides start, length, band, height, step). |

How a sweep reaches the backend: **one** `POST /scenarios/compare` with up to 12 explicit scenarios (the endpoint's own limit). The backend evaluates, caches and compares them as it always has.

## 2. Honesty rules
* A scenario labelled `terrain_data_insufficient` is a visible gap with the backend's reason and no figure; if all are insufficient the page says there is nothing to plot. Nothing is interpolated across a gap.
* Every terrain-corrected number carries its band; geometric is shown beside it; open (cut-off) intervals are flagged; "none: visible throughout" is shown only when the backend's longest-blackout is null and the fraction is exactly 100 %.
* Each swept parameter has an on-screen note of what the sweep does and does not mean (e.g. position uncertainty: "nominal results do not depend on it; the bands do"; window length: "changes what is averaged, not the model"; sampling step: "a numerical-sensitivity check").
* Backend validation errors (out-of-range dates, step limits, etc.) are shown verbatim with their field; the whole sweep fails as one request, as the endpoint does.
* The default observer height stays labelled as an assumption.

## 3. C4 — enforced three ways (`web/src/Tier2.test.tsx`)
1. **Request-count tests**: nothing is requested until Run; Run sends exactly one `/scenarios/compare` whose body has only `scenarios` + `baseline_index` and whose scenarios differ **only** in the swept parameter (asserted for all five parameters); zoom, spacing toggle, CSV download, opening the differences section, editing values and switching parameter make **zero** requests; each further explicit Run makes exactly one.
2. **Static tests**: no `fetch` in any of the three new files; the only API call is `compareScenarios`; no trigonometry/statistics anywhere; the chart imports only types.
3. **Numbers as received**: bands, geometric values, cache state and labelled gaps are asserted from stubbed backend responses; the CSV test asserts nominal values are written exactly as received and an insufficient row has no numbers.

## 4. Verification
* `npm run typecheck`, `npm run build` clean. **Frontend tests: 144 pass** (127 after Tier 1, + 17: helpers, tab behaviour, C4, axe). axe-core: no violations on the Explore tab before or after a sweep.
* One existing test edited: the tab-list expectation in `a11y.test.tsx` (extra tab).
* Real backend (via the dev proxy), real results:
  * IM-2 position-uncertainty sweep, 30 d from 2027-01-15, ±20/50/100/200/500 m: nominal Sun 48.65 % in all five (as it must be); band 48.4–48.8 %, 48.3–48.8 %, 45.4–48.9 %, 39.2–48.9 %, **0.0–50.2 %**; geometric 53.3 %. Four cold scenarios took 74 s; the ±100 m one came from cache.
  * Chandrayaan-3 start-date sweep (Jan/Feb/Mar/Apr 15): Sun 49.1, 48.1, 47.2, 46.9 % terrain-corrected (geometric 51.4, 50.3, 49.4, 49.1 %); every result carries the "NOT yet approved" terrain line.
  * IM-1 sweep: both scenarios `terrain_data_insufficient`, no `bodies` in either.
  * A start date of 2036-03-01: `EPHEMERIS_OUT_OF_RANGE`, field `start_utc`, shown as a typed error.
  * Screenshot: `tier2_explore.png`.
* Backend untouched, so the 364 backend tests are unaffected (not re-run on this branch).

## 5. Things you should know
* **The ±500 m band reaches 0.0 %.** That is the backend's own Stage 5/6 result (a displaced position among the eight sampled directions has the Sun fully blocked for the whole window), displayed unchanged. It is a sensitivity sample, not a bound, and not a UI artefact; the sweep simply makes it visible. Worth a glance before anyone quotes ±500 m figures.
* A sweep of 12 cold 30-day scenarios will take a few minutes (about 20 s each observed); the tab says so while loading. Already-cached scenarios return at once. The one-request design means a single invalid value fails the whole sweep (shown with its field).
* Sampling-step and window-length sweeps change what is being measured; the on-screen note says so. They are provided as sensitivity checks, not as alternative "answers".
* Only one parameter is varied at a time and only one site per sweep (multi-site/multi-date grids already exist in the Compare and Landing sites tabs). Two-parameter grids were not built.
* The tab-state is not saved in the URL (only `?autorun=1` for demos).
* Nothing here changes a capability status.

## 6. To view
`cd ../nasa-space-apps-stage10-extras/web && npm run dev -- --port 5174` (backend on :8000), tab **Explore sweeps** (or `http://localhost:5174/?autorun=1#explore`).
