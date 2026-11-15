# End-to-end testing report (Stage 11, task 1)

Two independent end-to-end checks were run on 2026-11-15.

## A. Complete workflow in a real browser against the production build
`python scripts/e2e_browser.py --base http://127.0.0.1:8010` drives Chrome through the DevTools protocol against the **one-process production server started from a clean virtual environment** (runtime requirements only, package installed non-editable, started from an unrelated directory with environment variables only). It walks the workflow from site selection to scenario comparison, asserts figures that the validation reports document, and records every console error, uncaught exception and failed API request. Screenshots of each stage: [e2e/](e2e/); machine-readable results: [e2e_results.json](e2e_results.json).

**Result: 25 / 25 checks pass; 0 uncaught exceptions; 0 console errors (other than the browser's own note on the three expected 422 responses); 0 unexpected failed requests; 0 basemap tile failures.**

| # | Check | Result |
|---|---|---|
| 1a–1f | App loads and reaches the backend; 7 capabilities shown, all `validated`; default IM-2 view computes; **Sun 48.6 %, Earth 80.8 %, geometric 53.3 % / 73.5 % match the validated reports**; advanced plots present; 16 basemap tiles requested and the credit shown | pass |
| 2a | Solar estimate **143.0 kWh** with its band, labelled UPPER BOUND | pass |
| 3a–3b | Clicking the map fills latitude/longitude; a point without terrain data is **labelled "terrain data insufficient", never estimated** (the only expected 422 responses) | pass |
| 4a–4b | Choosing a mission profile fills the form at once (14 d); Compute after returning to IM-2 recomputes | pass |
| 5a–5b | Compare: 6 supported + 2 insufficient (IM-1) scenarios, no number in the insufficient rows | pass |
| 6a–6c | Landing sites: IM-1 labelled in all 9 metric rows; Chandrayaan-3 supported with the "terrain not yet approved" flag, IM-2 not flagged | pass |
| 7a | Sweep: 5 rows, Sun nominal 48.6 % in every row | pass |
| 8a | Delay simulator returns its table | pass |
| 9a–9c | Data page lists kernels, terrain windows with SHA-256, credits; 38 limitations stated; Learn tab renders | pass |
| 10a | Production page carries CSP, `nosniff` and no-framing headers | pass |
| 11a–11c | No uncaught exceptions; no console errors; no unexpected failed requests | pass |

**What the test found:** nothing wrong in the application. Two initial failures were in the test (an element checked before its request finished; a click aimed at a map position that moves 7.5 px when headless Chrome first shows its scrollbar). The scrollbar effect was first misdiagnosed as an application layout shift and "fixed" with a reserved readout line before measurement showed the cause; the test now hovers its target and re-measures. The reserved line stays as a harmless layout-stability improvement. (Earlier in the stage the same method found the real defect where Compute/Run sent no request; see [CODE_REVIEW.md](CODE_REVIEW.md) Q1.)

Limits of this test: Chrome only; the three demonstration sites; relies on warmed caches for speed; checks specific documented figures, not every number on screen.

## B. Clean-clone install test (does the README work?)
A fresh `git clone` of the committed repository, no scientific data present, following the README's commands:

| Step | Result |
|---|---|
| `python -m venv` + `pip install -e ".[dev]"` | installs |
| `ruff check .` | clean |
| `pytest -q` | **273 passed, 115 skipped, 0 failed** (every real-data test skips with the rebuild command in its message) |
| `scripts/verify_data.py` | reports `NOT READY` with the missing files named (a clear failure, not a crash) |
| `npm ci` → `typecheck` → `vitest run` → `build` | 125 packages, **175 tests pass**, build succeeds |
| `lunarnav_api.serve` without data or UI | `/api/health` 200, `/` 200 (explains how to build the UI), `/api/provenance` 200 (reports what is missing) |

The same commands are in `.github/workflows/ci.yml` (written without GitHub access; not yet run there).

## C. Full suites on the final tree
Backend 388 pass (with data); frontend 175 pass; typecheck and build clean; ruff clean. Details: [../TEST_AND_VALIDATION.md](../TEST_AND_VALIDATION.md).
