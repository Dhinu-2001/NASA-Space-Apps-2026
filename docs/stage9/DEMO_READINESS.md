# Demo readiness (final polish) — what was checked, measured and fixed

Rehearsed on the real stack (backend on :8000, frontend dev server on :5173, headless Edge) at Stage 9 completion. Screenshots in `docs/stage7/final_*.png` are of the live app with real data.

## 1. Start-up checklist (about 2 minutes)
```powershell
# terminal 1 — backend
.\.venv\Scripts\python.exe -m uvicorn lunarnav_api.main:app --port 8000
# terminal 2 — frontend (Node is not on PATH on this machine)
$env:Path = "$env:LOCALAPPDATA\Programs\nodejs;$env:Path"; cd web; npm run dev
# terminal 3 — warm the caches through the running server (once; ~15 s the first time, instant afterwards)
.\.venv\Scripts\python.exe -I scripts\warm_cache.py --base http://127.0.0.1:8000
```
Open http://localhost:5173/ . Deep links for the demo (run the tab's defaults on load): `/?autorun=1#compare`, `/?autorun=1#delay`, `#about`.
Pre-flight: `curl http://127.0.0.1:8000/health` and `GET /provenance` (must list 4 kernels and 4 DEM windows; if `spice_kernels_error` appears the kernels are missing: `scripts/fetch_kernels.py`).

## 2. Measured waits (first visitor, caches warmed by `warm_cache.py`)
| View | Before warming | After warming |
|---|---|---|
| Site & time (default IM-2, 30 days, ±100 m: horizon + series + positions) | ≈ 60 s (terrain profiles at 9 positions) | **≈ 7 s** first time, **instant** on repeat (in-memory cache of identical requests) |
| Compare (4 sites × 2 dates, 30 d) | ≈ 80 s | ≈ 19 s on a cold scenario cache, **0.0 s** once cached |
| Delay (IM-2, 14-day window, 4 delays) | ≈ 25 s | ≈ 10 s cold scenario cache, **0.0 s** once cached |
Every slow path shows a spinner with elapsed seconds and, after 4 s, an explanation. Horizon profiles are cached on disk (`data/results/horizon`) and survive restarts; scenario results likewise (`data/results/scenarios`); neither is committed (decision G1).

## 3. The four tabs, verified in a real browser with real data
| Tab | Verified | Evidence |
|---|---|---|
| Site & time | map, catalogue + custom coordinates, UTC time, Sun/Earth az/el with horizon comparison and position-error note, horizon plot with Sun/Earth paths, timelines with boundary whiskers, elevation-vs-horizon charts with position band, metrics with bands and "cut off" flags, event table with "incomplete" band flags | `final_view.png` |
| Compare | 4 supported scenarios with terrain-corrected beside geometric and bands; 4 insufficient scenarios (IM-1, Chandrayaan-3) as labelled non-results with reasons and no figures; paired vs independent delta methods; rankings with "clearly ahead / not distinguishable" | `final_compare.png`, `final_mobile.png` (500 px) |
| Delay simulator | bars with uncertainty whiskers, geometric markers, table with bands and "cut off" flags, paired deltas ("−7.14 pp, band −7.14 to −7.14") | `final_delay.png` |
| Data & assumptions | all 7 capabilities with status; definitions; assumptions labelled; catalogue sources as links with SHA-256; all four DEM windows and four kernels with **full SHA-256**; frame; Horizons comparison with its independence caveat; model version, code commit, software versions; data classes | `final_about.png` |

**Browser console:** captured with `--enable-logging` on all four tabs plus the 500 px view. The only messages are INFO (Vite connecting, a React DevTools hint, an unrelated browser extension). **No errors, no warnings.**
**Capability status:** every status shown comes from `GET /version` (all of sites, dem, ephemeris, horizon, visibility, scenarios `validated`; engineering `implemented unvalidated`: the narrow solar-energy upper bound, added after this rehearsal; see `docs/stage8/`).

## 4. Fixed during polish
| Item | Fix |
|---|---|
| Header said "stage 6" and the notice described Stage 6 | backend stage/notice updated to Stage 9; mentions that engineering assessments are not built |
| Scenario labels were long ISO timestamps | labels use the date only |
| Ranking cards were cramped in three narrow columns | wider responsive grid |
| About tab showed 12-character checksums and no code version | now served by `GET /provenance`: full SHA-256s, model version, commit, software; reports clearly if SPICE kernels are missing (tested) |
| Repeat loads recomputed the same series (≈ 7 s each) | identical visibility requests served from an in-memory cache (deep-copied; regression-tested against the `/visibility/at` in-place edit) |
| No way to land directly on a result for a demo | `?autorun=1` deep links for Compare and Delay |
| Earlier overclaims ("validated backend") | softened in Stage 9 audit |

## 5. Suggested 5-minute walkthrough (the evaluation workflow)
1. **Site & time** — IM-2 is preselected: point at the horizon plot (real LOLA terrain, Sun and Earth paths), then the Sun card: elevation vs horizon, "could change by up to 0.05° for a ±100 m position error".
2. Timelines: terrain-corrected vs geometric (155 Sun steps blocked by terrain); the wide whisker on the sunset = how uncertain a grazing event is.
3. **Compare** — IM-2 landing vs intended target: not distinguishable at ±100 m; Jan vs Mar: −6.1 points, distinguishable. IM-1 and Chandrayaan-3 shown honestly as "terrain data insufficient".
4. **Delay simulator** — each day of delay costs exactly 1/14 of the sunlit window (paired band collapses to zero) while the absolute value stays uncertain.
5. **Data & assumptions** — status table, checksums, assumptions, limitations; "validated" means owner-approved evidence, not proof against measurement.

## 6. Known demo risks
* First request after a **cold** start (no `data/results`) takes up to a minute: run `warm_cache.py` first.
* If the machine lacks the kernels/DEM files the UI says so (503 / "terrain data insufficient" / About tab banner) rather than showing numbers.
* The dev server shows Vite messages in the console (INFO only); a production bundle is built with `npm run build`.
