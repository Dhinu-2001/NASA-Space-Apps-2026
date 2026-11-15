# Scientific validation report (Stage 9)

Covers Stages 0–7 and Stage 9. Stage 8 (engineering) was built afterwards in a deliberately narrow form; the owner approved its gate on 2026-11-15, so it is now `validated` in the same sense (`docs/stage8/SOLAR_ENERGY.md`). Written so that a reviewer can see, for each important output, what was checked, against what, how independent that check is, and what it does *not* show. Companion documents: [TOLERANCES.md](TOLERANCES.md), [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md), [TRACEABILITY.md](TRACEABILITY.md), [PROVENANCE.md](PROVENANCE.md), [TEST_REPORT.md](TEST_REPORT.md).

## 1. What "validated" means in this project
A capability is marked `validated` when **(a)** it is implemented and tested, **(b)** its acceptance criteria were declared before the checks were run, **(c)** the evidence is recorded in `docs/stageN/VALIDATION.md`, and **(d)** the project owner reviewed it and approved the stage gate. It does **not** mean "proven against measurement". The independence of each check is stated below; the two largest gaps are L-M1 (the ephemeris check shares JPL's ephemerides) and L-M2 (no physically independent horizon or visibility dataset).

Statuses today (`GET /version`, shown in the UI): `sites`, `dem`, `ephemeris`, `horizon`, `visibility`, `scenarios` = validated; `engineering` = validated (Stage 8, narrow: an idealised solar-energy upper bound; evidence in `docs/stage8/SOLAR_ENERGY.md`; owner-approved 2026-11-15, after this report's original scope, and it carries the same meaning of "validated" as above).

## 2. Independence of the evidence

| Component | Strongest evidence | Independent of the code under test? | Independent of the data/ephemerides? | What it cannot show |
|---|---|---|---|---|
| Ephemeris | 220-row comparison with **JPL Horizons** | yes (different software, different ephemeris realisation DE441 vs DE440, different frame realisation MEAN_ME vs ME) | **no** — both are JPL ephemerides and NAIF frames | an error in the ephemerides themselves (L-M1) |
| Horizon | hand-written implementation using **pyproj geodesics, PROJ's stereographic, the GeoTIFF's own affine transform, 3-D vector elevation** (no shared code) + analytic flat/mesa/curvature/height cases | yes | **no** — reads the same DEM values | an error in the DEM (L-D1, L-M2) |
| Visibility | analytic disc-vs-wall tests; **real ephemeris over synthetic terrain** with analytic expectations; 2 s brute-force scan of transitions; step-size convergence | partly (same predicate, evaluated differently) | n/a | agreement with any physical measurement (L-M2) |
| Position sensitivity | monotonic/consistency properties; nominal inside its band; band grows with uncertainty | partly | n/a | that 8 directions bound the true worst case (L-M8) |
| Scenarios | analytic delta/ranking cases; consistency (antisymmetry, zero self-delta); insufficient sites carry no numbers | yes (hand-built dictionaries) | n/a | — |
| DEM/sites | projection vs PROJ (0.1 mm); lander height vs two published values (criterion 25 m, pre-declared) | yes | partly (NAIF/LROC heights are independent of the DEM) | true site position (L-D5) |

## 3. Results by component

### 3.1 Sites and DEM (Stage 2) — `docs/stage2/`
* Catalogue: every site cites a primary source (NAIF CLPS kernels, LROC image pages); none estimated; Artemis III regions listed as pending, not selectable.
* Grid convention verified, not assumed: formula reproduces PROJ on the product's own CRS to 0.1 mm; four candidate orientations compared against independently published heights. DEM at the lander: IM-2 5321.89 m (+0.89 m vs NAIF), IM-1 2591.03 m (+8.03 m vs NAIF, +12.03 m vs LROC) against a **pre-declared** 25 m criterion.
* Overviews are area-averaged (overview 5190.37 m vs block mean 5189.91 m; nearest-neighbour alternatives 5163/5194 m) — so coarse windows under-state ridges (measured, L-D2).
* Kernels: four required SPICE kernels downloaded and matched to NAIF's published MD5; SHA-256 pinned and verified at every load.

### 3.2 Ephemeris (Stage 3) — `docs/stage3/VALIDATION.md`
* Method: SPICE `spkcpo`, `LT+S`, surface point fixed in `MOON_ME`; pole azimuth convention E4.
* **Pre-declared criterion 0.01° per row; 220 rows (11 observers incl. both exact poles at non-zero longitude, 10 epochs 2025–2035 incl. a leap day, × Sun/Earth): worst separation Sun 1.35×10⁻⁸°, Earth 6.0×10⁻⁷°** (margins 7×10⁵ and 1.7×10⁴). The residual does not depend on location, height, hemisphere or epoch.
* The check would catch the mistakes that matter: a wrong lunar frame costs 0.029° (3× the criterion), neglecting the observer offset 0.27° for Earth, omitting aberration 5.8×10⁻³° for the Sun.
* 33 + 21 engine tests (time conversion J2000 = 64.18392728 s; leap-second handling; poles; physical bounds derived from orbital geometry — two initial bounds of mine were wrong and were *re-derived*, not loosened).
* Not shown: L-M1, L-D4, L-M4.

### 3.3 Terrain horizon (Stage 4) — `docs/stage4/`
* Method: great-circle rays on the 1737.4 km sphere, exact elevation formula, bilinear DEM, finest window wins, NoData never filled, explicit truncation bound.
* **Pre-declared criterion 10⁻³° vs the independent implementation on real IM-2 data (63 azimuths × heights 0/2/30 m): worst 1.1×10⁻⁹°.** Analytic: flat terrain at any height gives −arccos(R/(R+h)) (also corrected an error in my own Stage 0 document: 0.087°, not 0.05°, for 2 m); a mesa is found at the independently computed bearing, elevation (±0.02°) and angular width; curvature matches d/2R and 3-D vectors; observer height matches independent geometry.
* Measured limits: the horizon at IM-2 is set within 30 km (80 → 160 km changes nothing); 320 m data under-estimates by up to 0.44°; azimuth step 0.25° misses ≤ 0.053°; a 100 m position error moves the horizon by up to 1.76° (the dominant uncertainty, L-D5).
* Not shown: L-D1, L-M2, L-M11.

### 3.4 Visibility (Stage 5) — `docs/stage5/VALIDATION.md`
* Three states per body (centre / any part / whole disc); Sun headline any-part, Earth headline centre (decision E2); geometric counterpart beside every result; incomplete horizons flagged `unverified_visible`.
* Transitions by bisection on the predicate: all refined transitions agree with a 2 s brute-force scan within 4 s; 15-min vs 5-min runs give identical transitions.
* **Real ephemeris over synthetic terrain** shows visibility responds to terrain (mesa on a body's azimuth blocks it at every step in the shadow; outside its span results equal flat terrain).
* Position-sensitivity bands on every boundary, metric and step; IM-2 (30 d): Sun visible 48.6 % [45.4, 48.9], Earth 80.8 % [80.0, 80.9]; largest boundary band 11.1 h (grazing Sun events).

### 3.5 Scenarios (Stage 6) — `docs/stage6/VALIDATION.md`
* Delta/ranking logic verified on hand-built cases (paired vs independent bands); only supported sites compared; insufficient sites carry no figures (asserted, including against real IM-1 / Chandrayaan-3 results).
* Finding that shaped the design: a 30-day window hides short delays (totals repeat), so the delay default is 14 days (an assumption, labelled).

### 3.6 UI (Stage 7) — `docs/stage7/UI.md`
* 16 component tests; grep audit that the frontend computes nothing scientific (C4); real backend JSON rendered through the components; headless-browser screenshots of three views.

## 4. New in Stage 9 (this report's own evidence)

| Stage 9 task | Evidence added | Where |
|---|---|---|
| 1 Scientific test scenarios, regression | Golden IM-2 horizon + 30-day visibility scenarios (Sun and Earth totals, transitions, band widths) with tolerances declared before pinning; recorded Stage 3/4 evidence re-asserted; modelling sensitivities re-asserted | `tests/validation/test_regression_golden.py` (8) |
| 5 Coordinate edge cases | invalid lat/lon (NaN, inf, bool, string, out of range) → `INVALID_INPUT` with the field; northern/equatorial sites → `OUT_OF_DEM_COVERAGE`; antimeridian equivalence on the grid and in the ephemeris | `tests/validation/test_edge_cases.py` |
| 6 Time boundaries | 2025-01-01, 2035-12-31 23:59:59 and a leap day work; 2024-12-31 23:59:59, 2036-01-01 and a window running past the end are **refused**, not truncated; non-UTC strings rejected | same |
| 7 Polar locations | exact poles: elevation independent of longitude, azimuth shifts by exactly the longitude (E4) on both poles. **Finding:** the exact south pole lies inside the 320 m IM-2 window only → 46/72 azimuths truncated → *not certified* → scenarios "terrain data insufficient" (L-D7) | same |
| 8 Permanently shadowed terrain | synthetic crater (rim ≈ 26°, floor 1.5 km below): Sun and Earth never visible for 30 days, band [0, 0], longest not-visible = whole window flagged open, while geometry says the Sun is up ~half the month (terrain removes 100 %). **No real PSR data** (L-D6) | same |
| 9 Missing datasets | missing kernels → `DATA_MISSING` with rebuild hint; modified kernel/DEM refused by checksum; missing DEM → scenario labelled insufficient (`DATA_MISSING`), API 503 with `field: dem`; `/provenance` degrades gracefully on a partial install | `test_edge_cases.py`, `test_api_stage9.py` |
| 10 Numerical tolerances | every criterion, achieved value, margin and rationale in one table | [TOLERANCES.md](TOLERANCES.md) |
| 11 Known limitations | 33 limitations with effect and evidence | [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) |
| 12 Data provenance | generated report: kernels, DEM windows, catalogue, Horizons fixture, software, git history | [PROVENANCE.md](PROVENANCE.md), `GET /provenance` |
| 13 Reproducible calculation metadata | deterministic `provenance` block (model version, kernel + DEM SHA-256, frame, aberration, algorithm version, every parameter, no timestamps) in every visibility/scenario result; identical inputs ⇒ identical metadata (asserted) | `engine/lunarnav/provenance.py` |

### Defect found and fixed by Stage 9
`ScenarioService.evaluate` converted **any** `DataMissingError` into `terrain_data_insufficient`. A missing or modified SPICE kernel would therefore have been reported to the user as a *terrain* problem. It now re-raises unless the error's field is `dem`; regression test `test_missing_kernels_are_never_mislabelled_as_terrain_data_insufficient`.

## 5. Methodology traceability
Every important output has a method document, evidence and limitations: see the matrix in [TRACEABILITY.md](TRACEABILITY.md) (15 outputs).

## 6. Claims audit (gate: "no unverified scientific claim presented as validated")
Searched code, API descriptions, UI strings, README and all documents for "validated", "verified", "accurate", "exact", "proven", "guarantee", "certif*".

| Where | Claim | Verdict | Action |
|---|---|---|---|
| `README.md` | "read-only web UI over the **validated** engine" | Over-broad (read as "proven") | **Rewritten**: `validated` = implemented, tested, reviewed and approved, not proven against measurement; links here |
| UI, View tab (empty state) | "Everything shown is calculated by the **validated** backend" | Over-broad | **Rewritten**: "calculated by the backend (capability status is shown above and on each panel)" |
| Stage 3/4/5 method and validation docs | "stays `implemented_unvalidated` until the gate is approved" | **Stale** (the gates are approved; the capability table says `validated`) | **Updated** with the approval and the meaning of "validated" |
| Stage 7 UI doc | "unvalidated until the Stage 7 gate is approved" | Stale | Updated |
| UI capability strip / About tab | status taken from the backend; "validated = the project owner approved that stage's evaluation gate" | Supported and qualified | none |
| UI About tab | "ephemeris engine was validated against JPL Horizons … that check shares JPL's ephemerides, so it validates the implementation, not the ephemerides" | Supported and qualified | none |
| `ephemeris.py` range error | "results outside this range have not been validated" | Supported | none |
| API notes (horizon) | "curvature (exact sphere)" | Supported (mathematical statement; tested against independent geometry) | none |
| Stage 0 Methodology | limb dip "≈ 0.05° for 2 m" | **Wrong** (0.087°) | already corrected in Stage 4 (decision H7) |
| Stage 5/6 | "Sun headline any-part = any direct illumination" | Qualified as geometric; not irradiance | stated in UI and L-M9/L-M10 |
| Any document | "accurate", "proven", "guarantee", "independently validated" | **none found** except "not a proven bound" (a negation) | — |

Claims the project does **not** make: agreement with measurement; a link budget, power or thermal figure; a bound on position error; any statement about a real permanently shadowed region; any result outside 2025–2035; any figure for IM-1 or Chandrayaan-3.

### Addendum: Stage 10 text claims
The Learn tab and Learn-mode explanations were checked claim by claim against the project's own evidence (table in `docs/stage10/ADVANCED_UI.md` §2); none states more than the documented results support, and the content is explicitly marked as not independently reviewed (L-P8). Stage 10 adds no engine capability and no number that is computed in the browser.

## 7. Verdict against the Stage 9 gate
* Every important output has a traceable methodology, evidence, tests and documented limitations (§5).
* No claim is presented as validated beyond what its evidence supports (§6), with the independence gaps stated in §2 and in the UI's About tab.
* Status: **PASS**, with the open items in [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) (chiefly L-M1, L-M2, L-D5, L-D3, L-P3).
