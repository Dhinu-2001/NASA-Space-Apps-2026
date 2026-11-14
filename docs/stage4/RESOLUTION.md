# Stage 4 — Resolution and sampling limits (IM-2 Athena, observer 2 m)

Source: `scripts/horizon_resolution_study.py` → `resolution_study.json`. Reference profile = 20 m DEM to 80 km, 0.25° azimuth step (horizon −1.47…4.07°, mean 1.17°; ground 5321.9 m).

| Question | Result |
|---|---|
| Where is the horizon set? | median 12.9 km, 90th pct 21.7 km, max 29.7 km; 46 % of azimuths within 10 km; **none beyond 40 km** |
| Is 10 km of 20 m data enough? | **No.** Truncating at 10 km under-estimates by mean 0.80°, rms 1.28°, max 3.33°; 46 % of azimuths by > 0.5° |
| Does extending 80 → 160 km (320 m far field) change anything? | **No: 0.0000° difference**, all 1440 azimuths `complete` (unseen bound −3.3…−2.0° ≪ horizon) |
| 20 m vs 320 m pixels (same 80 km extent)? | 320 m under-estimates: mean −0.06°, rms 0.12°, p95 0.33°, **max 0.44°**; 25 % of azimuths by > 0.05°, none by > 0.5° |
| Is the 320 m overview an area average? | Yes. vs 16×16 mean of the 20 m data: rms 1.0 m (max 10.5 m); vs centre-pixel decimation rms 3.4 m; within-block terrain rms 23 m |
| Azimuth step | missed obstruction vs 0.05° reference (conservative max-of-neighbours): 1° → max 0.22°, 0.5° → 0.11°, **0.25° → max 0.053°, p95 0.023°** |
| Radial step 10 m vs 20 m | rms 0.003°, max 0.042° |
| Observer height (vs 2 m) | 0 m: +0.13° mean (max 0.85°); 5 m: −0.09° (max 0.34°); 10 m: −0.21° (max 0.81°); 30 m: −0.55° (max 2.5°) |
| **Observer position error** | 20 m shift → max 0.11°, rms 0.02°; **100 m shift → max 1.76°, rms 0.65°, p95 1.6°** |

## Conclusions
1. For IM-2, **20 m data within ~30 km is what matters**; the 80 km / 160 km extents are not needed for the horizon (they let the engine *prove* completeness). The user-requested 80 km fetch confirms this with data rather than assumption.
2. The 320 m overview alone is a usable but biased-low approximation (≤ 0.44° here). It must not be used silently where 20 m exists; the engine picks the finest window automatically.
3. The default 0.25° azimuth step loses at most ~0.05° (conservative reconstruction). Stage 5 should use `max_between` across a disc's azimuth span.
4. **The dominant uncertainty is the site position, not the grid.** Catalogue coordinates are not known to better than tens of metres in general; a 100 m error moves the horizon by up to 1.8°, comparable to the Sun's 0.53° diameter. Stage 5 results near the horizon must carry this caveat; this is quantified for IM-2 only.
5. Observer height matters at the 0.1–1° level and is a first-class input (default 2.0 m is an assumption, C9).
6. These numbers are for IM-2 (a high plateau). IM-1 has only 2 km of 20 m data (all azimuths `truncated`); Chandrayaan-3 has none (explicit error).
