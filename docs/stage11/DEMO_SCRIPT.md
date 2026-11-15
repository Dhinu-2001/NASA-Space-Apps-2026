# Demonstration script (about 7 minutes) and Q&A crib

Every number below was read from the running application on 2026-11-15 (production build, warmed caches) and is checked by `scripts/e2e_browser.py` where marked ✔. If a number on screen differs, trust the screen and tell the judges; do not quote this page over the app.

## Before you go on stage (10 minutes)
1. **Start the app** in production mode: `.\scripts\run_production.ps1 -Port 8000` (or open the deployed URL). Wait for `READY` and the first log line.
2. **Warm the caches** if you changed machines or cleared `data/results`: `python scripts/warm_cache.py --base http://127.0.0.1:8000` (about a minute; it computes the default views so nothing waits on stage).
3. Open `http://127.0.0.1:8000/#view` in a clean browser window (1400 px wide or more), reload once so the first view is cached.
4. Run the safety net once: `python scripts/e2e_browser.py --base http://127.0.0.1:8000` should end with **26/26 checks passed**.
5. **Network:** the map imagery comes live from NASA. If the Wi-Fi is poor the map falls back to rings and an "Imagery unavailable" note; everything else works offline.
6. Avoid clicking an uncached map point on stage: a new point takes about a minute (use the one rehearsed below only if you want to show the labelled "insufficient" case, which is instant).

## The story in one sentence
*A mission planner can compare landing sites and dates in seconds, sees the Sun and Earth against the real terrain horizon, and is told, in the interface, how far each number can be trusted.*

## Beat 1: the problem and the honest framing (45 s)
**Show:** the page header and the capability strip (7 capabilities, all "validated").
**Say:** "South-pole landings live or die on lighting and Earth contact. Tools like Quickmap and Horizons give the data, but not a quick answer. This tool gives the answer, and it says what it is: geometric line of sight and direct illumination only, from NASA's ephemerides and laser-altimeter terrain. 'Validated' here means reviewed and approved by the project owner, not proven against measurement; the About tab says so."

## Beat 2: Site & time, IM-2 Athena (90 s)
**Show:** the **Site & time** tab (IM-2 Athena, 2027-01-15, 30 days, ±100 m). Point at the map, then the Sun and Earth cards, the horizon plot with the Sun and Earth tracks, and the timelines.
**Expect ✔:** Sun and Earth at the shown time, e.g. "az 63.6° · el +3.07°" (Sun), Earth about 9° up; terrain horizon from −1.47° to +4.07° around the compass.
**Countdown ✔:** under each card, *Sunset in 13.4 d (band 13.0 to 13.5 d, flagged "incomplete band")* and *Earthset in 12.5 d (band 12.4 to 12.5 d)*: the time to the next moment the body is hidden behind the terrain, from the computed intervals; drag the time player and it follows (for example *Earthrise in 12.6 h* on 1 Feb 17:00).
**Say:** "This is IM-2's landing site. The Sun stays within a few degrees of the horizon, so the terrain decides everything. The grey shape is the real horizon from the 20 m laser-altimeter terrain; the gold and blue paths are the Sun and Earth over the month."
**Then the numbers (Section 5):** "Terrain-corrected, the Sun is visible **48.6 %** of the month, band **45.4–48.9 %**. The geometric answer, ignoring terrain, would be 53.3 %: terrain costs about five points. Earth is visible **80.8 %** (band 80.0–80.9 %) against 73.5 % geometric: here terrain actually *helps*, because the local horizontal is a poor reference on a plateau."
**Say about the band:** "The band is how far the answer moves if the landing position is wrong by 100 m. It is a sensitivity, not an error bar. Longest period without Sun: **15.4 days** (band 15.3–16.4)."
**Optional (15 s):** drag the time player, or click the timeline: the cards and plots move with no new request, because the browser calculates nothing.

## Beat 3: the honest "no" (45 s)
**Show:** click on the map somewhere away from the three sites (for example near 75°S, 100°E), press **Compute**.
**Expect ✔:** the coordinates fill in, then the **"Terrain data insufficient"** box, with no figures.
**Say:** "Where we have no terrain data, the tool does not guess. IM-1 is the same: too little terrain around it, so it is labelled, never ranked."

## Beat 4: compare sites (60 s)
**Show:** **Landing sites** tab → **Compare sites**.
**Expect ✔:** IM-2 Sun **48.6 %**; Chandrayaan-3 Sun **49.1 %** (band 48.5–49.4 %) with the amber **"terrain: implemented unvalidated"** pill, Earth **100 %** ("none: visible throughout the window"); IM-1 column reads "terrain data insufficient" in every row.
**Say:** "Chandrayaan-3's terrain is a coarser 60 m product. We integrated it with the owner's approval, but it has not had the independent verification pass IM-2's terrain had, so it is labelled implemented_unvalidated on every result."

## Beat 5: how a schedule change matters (75 s)
**Show:** **Compare** tab (defaults: sites × two dates) or keep to **Delay simulator** → **Simulate delays**.
**Expect ✔ (Compare, IM-2 Jan 15 vs Mar 15, paired):** Sun fraction **−6.12 percentage points** (band −6.43 to −4.79), "distinguishable from zero"; Earth +2.22 points. **IM-2 landing vs intended target** (different position): Sun +0.40 points, band −0.14 to +3.67, **"NOT distinguishable from zero given ±100 m"**.
**Expect ✔ (Delay, 14-day window from 15 Jan):** Sun **95.6 %** baseline; delay 1 day 88.5 %, 3 days 74.2 %, 7 days 45.6 %, **14 days 0.0 %**; Earth 89.0 % → 81.8 → 67.6 → 58.8 → 69.8 %.
**Say:** "A two-month slip costs six points of Sun, and the tool can tell that is real. The difference between the landing point and the intended target, about 370 m apart, gives results whose position bands overlap, so the tool says they are not distinguishable. A 14-day delay moves the whole window into the dark half of the lunar month."

## Beat 6: power and engineering (45 s)
**Show:** back in **Site & time**, scroll to **Idealised solar energy**, press **Use example**, **Estimate energy**.
**Expect ✔:** **143.0 kWh** (band 133.6–143.9), geometric 156.8 kWh, partial-Sun bracket 137.1–143.0 kWh, labelled **UPPER BOUND, not a power budget and not battery state**.
**Say:** "One square metre at 30 % efficiency, an illustrative example. It is an upper bound, and the tool refuses to call it more."

## Beat 7: sweeps and plots (45 s)
**Show:** **Explore sweeps** → **Run sweep** (position uncertainty 20–500 m).
**Expect ✔:** the Sun nominal stays **48.6 %** in every row while the band widens, to **0 %–50.2 %** at ±500 m.
**Say:** "This is the whole point of the band: the best estimate does not change, but how much you can lean on it does."
**Optional:** scroll the Site & time tab to the **Advanced plots** (sky chart) and the **Learn** tab for non-specialists.

## Beat 8: trust and sources (30 s)
**Show:** **Data & assumptions**: capability table, kernel and terrain checksums, the credits panel.
**Say:** "Every dataset is a NASA source with its checksum verified at load; the ephemeris matches JPL Horizons to 10⁻⁸ degrees, the horizon matches an independent implementation to 10⁻⁹. The limits are listed, 38 of them, with their effects."

## Backup plan
| If | Then |
|---|---|
| Backend not responding | The page shows "Backend unavailable"; restart `run_production.ps1`; or show `docs/stage11/e2e/*.png` (real screenshots of every step) |
| A view is slow (uncached) | The loading text says a first calculation takes about a minute; fill with Beat 8, or switch tab and come back |
| No internet | The map loses imagery only; say so; everything else is unaffected |
| `503 SERVER_BUSY` | Someone else is computing; retry in a few seconds |
| A number differs from this page | Trust the screen; mention the model version in the header |

## Q&A crib (honest answers)
* **Is it validated?** "Implemented, tested and approved by the project owner after review. Against JPL Horizons the ephemeris agrees to 1.4×10⁻⁸° (Sun) and 6×10⁻⁷° (Earth). But Horizons shares JPL's ephemerides, so it validates our implementation, not the ephemerides. There is no independent illumination dataset checked yet: that is our first piece of future work."
* **Why not a power budget or comms link budget?** "Out of scope by design: we give geometry, which is the part that decides feasibility first. Anything beyond is listed as not built."
* **What does the band mean?** "We recompute the result with the position displaced to eight points around the nominal position. It is a sensitivity sample, not a proven bound."
* **Why is IM-1 missing numbers?** "Only 2 km of 20 m terrain surround it, so the horizon is incomplete in every direction. We label it instead of guessing."
* **Is the Earth always visible at Chandrayaan-3?** "In this window, yes: Earth stays 11–22° up while the terrain horizon never exceeds 2.5°."
* **What about libration and orbital variations?** "The ephemeris includes the Moon's actual orientation (libration) through NASA's SPICE lunar kernels."
* **What about shadows from boulders, slopes, craters?** "Craters and slopes are in the LOLA terrain at 20–60 m; boulders and the lander body are not modelled."
* **Where do the data come from?** "NASA: LOLA terrain from PGDA, SPICE kernels from NAIF, landing coordinates from NAIF/LROC, map imagery from LROC via Moon Trek. All credited in the app."
