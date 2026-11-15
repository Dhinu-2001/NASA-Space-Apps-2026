# Architecture and code-quality review (Stage 11, task 2)

Reviewed 2026-11-15 by static analysis, structural checks and reading the code paths changed in Stages 9–11. Reviewer and author are the same agent: this is a self-review, which is a limitation; the independent evidence is the test suites, the browser test and the validation studies.

## 1. Size and shape
| Part | Lines | Files |
|---|---|---|
| Science engine `engine/lunarnav` | 2 820 (+ cache caps) | 14 |
| API `api/lunarnav_api` | 1 370 (+ hardening, serve) | 16 |
| Web UI (non-test, excluding generated types) | 4 420 | 26 |
| Scripts (data, validation, studies, reports, e2e) | 2 430 (+ new data/e2e scripts) | 25 |
| Tests: backend / frontend | 4 250 / 2 100 lines | 25 / 10 |

Largest modules: `visibility.py` 548, `scenarios.py` 524, `horizon.py` 444 lines: cohesive single-purpose modules, none unreasonable.

## 2. Architecture conformance
| Rule | Result |
|---|---|
| Engine has no web-framework import | **Pass** (enforced by a test; also `grep` finds no `fastapi`/`starlette`/`uvicorn` under `engine/`) |
| API is thin, no science | **Pass**: routes validate, call the engine, shape responses; the new hardening and serving modules contain no science |
| UI calculates nothing scientific (C4) | **Pass**: request-count suites in every view; static tests for no `fetch`/trigonometry in display components; layout arithmetic and the map's projection mirror are the only computation (the mirror is pinned to the engine by a generated golden table) |
| Reuse, not recomputation | **Pass**: engineering ← scenarios ← visibility ← horizon + ephemeris; the UI only displays |
| Typed errors, no silent fallbacks | **Pass**: no code path substitutes flat terrain or geometric results for missing terrain; limits return typed 413/503 |
| Determinism and reproducibility | **Pass**: cache keys hash inputs, model version and DEM checksums; golden regression suite; calculation-metadata block |

## 3. Static analysis
* `ruff check .` clean (rules in `pyproject.toml`); TypeScript strict (`tsc --noEmit`) clean; production build clean.
* **Complexity:** one function above McCabe 15: `build_visibility_router` (18), a router factory that nests its route handlers; acceptable.
* **mypy** (default settings, not part of the project tooling; run once for this review): 24 findings in 8 files, none a defect. 19 are one annotation pattern (`responses=` dictionaries typed `dict[int, …]` where FastAPI declares `dict[int | str, …]`); 4 are mypy not narrowing `height = DEFAULT if is_default else req.observer_height_m` and a `lo`/`hi` pair guarded by `if lo is not None`; 1 is the pydantic-plugin-less constructor call. Runtime behaviour was checked for each: correct. Tidy-up listed in future work.
* No `TODO`/`FIXME`/`HACK` markers; no `print` in engine or API; no committed secrets.
* Dependencies: pinned, audited, minimal (`pip-audit`, `npm audit` clean).

## 4. Findings from this review and the final stages
| # | Finding | Status |
|---|---|---|
| Q1 | **Compute / Run buttons silently did nothing** when inputs were unchanged, or when a profile was selected but not applied (found by the owner, reproduced with network capture) | Fixed in all five computing tabs; 8 regression tests, 7 of which fail on the old code |
| Q2 | Unbounded caches, no compute limits, no security headers, unbounded list sizes | Fixed (see [SECURITY_REVIEW.md](SECURITY_REVIEW.md)) |
| Q3 | The header and `/version` still said "stage 9" and API `0.1.0` | Now API `1.0.0`, stage 11; `MODEL_VERSION` deliberately unchanged because no science changed |
| Q4 | An end-to-end timing hazard in my own browser test (headless Chrome shows its scrollbar on first mouse activity, shifting the centred layout) was first misdiagnosed as an app defect; corrected after measuring | Test aims at the hovered target; recorded here for honesty. A reserved readout line was kept as a harmless layout-stability improvement |
| Q5 | Duplication: the five computing tabs repeat the same "applied inputs + run counter + `useAsync`" pattern, and the About tab is long | Accepted for the release; an extracted `useRun` hook and a split About tab are future work |
| Q6 | `docs/API_CONTRACT.md` listed `GET /metrics/registry` as "planned"; it was never built | Marked not built/deferred |
| Q7 | A TypeScript copy of the stereographic projection (and its inverse) exists for the map | Deliberate and pinned: the engine generates `polarGolden.json`; one test per side keeps both equal to it |
| Q8 | Historical stage documents contain statements that later stages superseded (for example "Chandrayaan-3 has no DEM") | Several superseded statements carry a dated note pointing to the current document; the decision log (DECISIONS.md) records every change of position. Not every historical sentence was rewritten: the stage documents are a dated record, and the final documents (README, ARCHITECTURE, METHODOLOGY, TEST_AND_VALIDATION) are authoritative |

## 5. Test quality
Backend 388 tests (unit, API contract, real-data integration with skips when data are absent, golden regression, 42 edge cases, hardening); frontend 175 (behaviour, accessibility with axe-core, request-count and static C4 suites); a 25-check real-browser test; validation studies with pre-declared criteria. No coverage percentage is reported because no coverage tool is configured; the claim is behavioural coverage of every endpoint and view plus the documented validation, not line coverage.

## 6. Verdict
Fit for the demonstration and for a supervised public deployment behind a rate-limiting proxy. Not asserted: independence from author bias (self-review), line coverage, cross-browser or screen-reader verification (see [KNOWN_LIMITATIONS](../stage9/KNOWN_LIMITATIONS.md) L-P4, L-P6).
