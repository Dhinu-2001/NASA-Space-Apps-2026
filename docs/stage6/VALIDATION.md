# Stage 6 — Validation evidence and IM-2 example results

Status: `scenarios` stays `implemented_unvalidated` until the user approves the gate.

## 1. Gate items → tests (`tests/engine/test_scenarios.py`, `tests/api/test_api_stage6.py`)
| Gate item | Evidence |
|---|---|
| Changing the landing date changes the outputs | real IM-2: a scenario 10 days later has a different id, different events and a different Sun total; the 15 Jan → 15 Mar comparison differs by −6.1 pp (Sun) with a band that excludes zero |
| Changing the location changes the outputs | IM-2 landing position vs intended target: different id, different event times; nominal Sun fraction 48.6 % vs 49.0 % |
| Multiple scenarios can be compared | grid of 4 sites × 2 dates (8 scenarios), explicit lists, `baseline_index`; 12-scenario cap |
| Differences are calculated consistently | delta(a→b) = −delta(b→a); delta(a→a) is exactly 0 with band [0, 0]; the nominal delta always lies inside its band; paired band hand-checked on analytic dictionaries (same-direction swings cancel; opposite swings give [−10, +30]); independent band equals interval arithmetic |
| Missing data does not silently produce misleading comparisons | IM-1 and Chandrayaan-3 → `terrain_data_insufficient`, reason, **no numbers** (test asserts no `bodies`, no `visible_fraction`, no `geometric` in the result); they are absent from every delta and ranking; an insufficient baseline gives no deltas; a delay for such a site returns no numbers |

User-instruction checks: both geometric and terrain-corrected in every delta and delay-table row (test); band carried into deltas, paired for the same site and independent across sites (test); open intervals flagged and any delta involving one marked (test); identical inputs → identical id, changed inputs/model → different id or no cache hit (test); cache refuses a different model version and corrupt files (test).

## 2. IM-2 example (30-day windows, 15-min steps, observer 2.0 m default, ±100 m, 8 directions)
Source: `scripts/scenario_study.py` → `scenario_study.json`. Sun = any part of the disc, Earth = disc centre. Terrain-corrected fraction with its position band, and the geometric fraction beside it.

| Scenario | Sun terrain-corrected | Sun geometric | Earth terrain-corrected | Earth geometric |
|---|---|---|---|---|
| IM-2 landing, 15 Jan 2027 | 48.6 % [45.4, 48.9] | 53.3 % | 80.8 % [80.0, 80.9] | 73.5 % |
| IM-2 landing, 15 Mar 2027 | 42.5 % [39.6, 44.2] | 44.8 % | 83.0 % [82.3, 83.1] | 74.8 % |
| IM-2 intended target, 15 Jan 2027 | 49.0 % [48.8, 49.1] | 53.3 % | 80.7 % [80.6, 80.8] | 73.5 % |
| IM-2 intended target, 15 Mar 2027 | 41.5 % [41.2, 41.6] | 44.8 % | 82.9 % [82.8, 83.2] | 74.9 % |
| IM-1, Chandrayaan-3 (both dates) | **terrain data insufficient** | — | **terrain data insufficient** | — |

* The terrain effect has opposite signs for the two bodies: terrain removes 4.7 pp of Sun the geometry allows (15 Jan), while Earth gains 7.3 pp because the plateau's terrain horizon dips below the local horizontal.
* **Deltas vs landing/15 Jan** — same site, 15 Mar (paired): Sun −6.1 pp (band −6.4 to −4.8, distinguishable), Earth +2.2 pp (+2.0 to +2.3, distinguishable). Intended target, 15 Jan (independent): Sun +0.4 pp (band −0.1 to +3.7, **not distinguishable**), Earth −0.04 pp (−0.3 to +0.8, **not distinguishable**) — the landing position and the pre-landing target are not separable at ±100 m.
* **Rankings** (supported only): Sun fraction — intended/Jan 49.0 %, landing/Jan 48.6 % (adjacent bands overlap: not distinguishable), landing/Mar 42.5 %, intended/Mar 41.5 %. The date effect is distinguishable; the position effect is not.

## 3. Delay simulator — IM-2 landing, baseline 15 Jan 2027, 14-day window (assumed), terrain-corrected fraction [band] / geometric
| Delay | Sun | Earth | Sun Δ vs baseline (paired) |
|---|---|---|---|
| 0 | 95.6 % [88.8, 96.2] / 94.1 % | 89.0 % [88.9, 89.1] / 83.2 % | — |
| 1 d | 88.5 % [81.7, 89.1] / 86.9 % | 81.8 % / 76.1 % | −7.14 pp, band [−7.14, −7.14] |
| 3 d | 74.2 % [67.4, 74.8] / 72.7 % | 67.6 % / 61.8 % | −21.4 pp, band [−21.4, −21.4] |
| 7 d | 45.6 % [38.8, 46.2] / 44.1 % | 58.8 % [57.2, 59.1] / 43.2 % | −50 pp, band [−50, −50] |
| 14 d | **0.0 %** [0, 0] / 5.9 % | 69.8 % [68.3, 70.0] / 59.9 % | −95.6 pp, band [−96.2, −88.8] |
| 21 d | 44.4 % [44.3, 44.4] / 55.9 % | 100 % / 100 % | −51.2 pp, band [−51.8, −44.5] |

Reading: every day of delay in the first week costs the Sun exactly 1/14 of the window (the sunset moves with the position error, but the loss between two windows does not) while the absolute fraction stays uncertain by ±3 – 7 pp. At 14 d the terrain-corrected Sun is 0 % although the geometry allows 5.9 % — the terrain removes all of it, an example of the gap the tool exists to show. Every Sun row is flagged `includes_open_interval` (the dark/lit interval is cut by the window edge). With a **30-day** window, delays of 1, 3 and 7 days give identical totals (Sun 48.65 %, Earth 80.76 %): the window spans a whole synodic month, so only event times move.

## 4. What this does NOT show
* Only IM-2 can be compared; the landing/target comparison is ≈ 0.37 km apart. No other site has terrain support, by design excluded rather than estimated.
* Validation is analytic/synthetic plus internal consistency; there is no physically independent scenario dataset.
* The position band is an 8-direction sample, not a bound, and assumes the DEM is correct.
* The 14-day delay window is an assumption; choose the window that matches the operation.
