# Final test report

Generated 2026-11-15 02:06 UTC by `scripts/build_test_report.py`. Commit tested: **81086821c347**. Machine: Windows 11, Python 3.12, Node 24.

**Overall: ALL CHECKS PASSED**

| Check | Result | Detail | Time |
|---|---|---|---|
| Backend tests (pytest) | PASS | 364 passed, 0 failed, 0 skipped | 103 s |
| Lint (ruff) | PASS | All checks passed! | 0 s |
| Frontend typecheck (tsc) | PASS | strict TypeScript, no errors | 6 s |
| Frontend tests (vitest) | PASS | 108 passed, 0 failed | 8 s |
| Production build (vite) | PASS | bundle builds | 7 s |

## Backend tests by file

| File | Passed | Failed | Skipped |
|---|---|---|---|
| `tests/api/test_api_chandrayaan3.py` | 5 | 0 | 0 |
| `tests/api/test_api_foundation.py` | 9 | 0 | 0 |
| `tests/api/test_api_stage2.py` | 15 | 0 | 0 |
| `tests/api/test_api_stage3.py` | 9 | 0 | 0 |
| `tests/api/test_api_stage4.py` | 7 | 0 | 0 |
| `tests/api/test_api_stage5.py` | 6 | 0 | 0 |
| `tests/api/test_api_stage6.py` | 5 | 0 | 0 |
| `tests/api/test_api_stage8.py` | 9 | 0 | 0 |
| `tests/api/test_api_stage9.py` | 5 | 0 | 0 |
| `tests/engine/test_dem.py` | 22 | 0 | 0 |
| `tests/engine/test_engineering.py` | 30 | 0 | 0 |
| `tests/engine/test_ephemeris.py` | 33 | 0 | 0 |
| `tests/engine/test_foundation.py` | 4 | 0 | 0 |
| `tests/engine/test_frames.py` | 21 | 0 | 0 |
| `tests/engine/test_horizon.py` | 53 | 0 | 0 |
| `tests/engine/test_scenarios.py` | 21 | 0 | 0 |
| `tests/engine/test_sites.py` | 40 | 0 | 0 |
| `tests/engine/test_visibility.py` | 20 | 0 | 0 |
| `tests/validation/test_edge_cases.py` | 42 | 0 | 0 |
| `tests/validation/test_regression_golden.py` | 8 | 0 | 0 |
| **Total** | **364** | **0** | **0** |

No test was skipped: all kernels and DEM windows were present, so every real-data test ran.

## What the suites cover

* **Unit/analytic**: frames, projection, time conversion, horizon geometry (flat, mesa, curvature, height), disc states, interval maths, delta and ranking logic.
* **Independent comparison**: JPL Horizons (220-row grid, recorded fixture) and the hand-written horizon implementation, re-asserted as regression evidence.
* **Real-data**: IM-2 LOLA windows + real SPICE ephemeris (golden scenarios, transitions vs brute-force scan, position sensitivity, IM-1 insufficient, Chandrayaan-3 on the 60 m window, uncovered point = no DEM).
* **Synthetic terrain with the real ephemeris**: terrain obstruction, permanently shadowed crater.
* **Fault injection**: missing or modified kernels and DEM, partial installation, out-of-range and malformed inputs.
* **API contract**: every endpoint's success shape and typed errors; calculation metadata; provenance.
* **UI**: capability status, bands always shown, insufficient sites shown with no numbers, cut-off flags, workflow.

## Not covered by automated tests

* Visual rendering beyond three headless-browser screenshots (`docs/stage7/`); no cross-browser testing.
* Load/performance testing (first calculation for a new site ≈ 1 min is measured, not tested).
* Any comparison with physical measurements (see `KNOWN_LIMITATIONS.md` L-M2).

## Reproduce

```powershell
.\.venv\Scripts\python.exe scripts\build_test_report.py        # runs everything below and rewrites this file
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
cd web; npm run typecheck; npm test; npm run build
```
