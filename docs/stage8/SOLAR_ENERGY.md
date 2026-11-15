# Stage 8 — Idealised solar-energy availability (deliberately narrow)

Status: implemented; the Stage 8 gate was **approved by the project owner on 2026-11-15** after independent verification (357/357 backend tests run twice, live API output compared with the written reports), so `engineering` capability = `validated`. "Validated" means implemented, tested, evidence reviewed and approved - not proven against measurement - and it applies only to this narrow upper-bound estimate. Code: `engine/lunarnav/engineering.py`, `api/lunarnav_api/routes_engineering.py`, `web/src/components/SolarPanel.tsx`. Scope was set by the owner: *the minimum engineering assessment that is genuinely useful — a solar-energy estimate derived from the Sun visibility already computed, not a power-subsystem model.*

## 1. What it is, and what it is not
**It is** the electrical energy a panel of stated area and efficiency *could* collect from direct sunlight if it faced the Sun whenever any part of the Sun's disc is above the terrain horizon, at a constant irradiance, over a chosen window and landing position. It is therefore an **upper bound on direct-beam energy** (`data_class: calculated`; every non-measured input is a labelled assumption).
**It is not** a power budget, a battery state, an eclipse/thermal analysis, or a link analysis. Antenna masks, slope/aspect/roughness, temperature data, an incidence-angle power model and anything battery-related are **deferred, not built**.

## 2. Method — reuse, not recomputation
```
E[Wh] = efficiency × area[m²] × irradiance[W/m²] × illuminated time[h]
```
The illuminated time, its **position-sensitivity band**, the geometric (no-terrain) counterpart, the longest period without sunlight and its open-interval flag are **read from the cached Stage 6 scenario result** (`POST /engineering/solar` asks the scenario service for the scenario, which reuses the Stage 5 visibility engine). The engineering module imports no ephemeris, horizon, visibility, frame or DEM code (asserted by a static test) and recomputes nothing.
Because energy is linear in illuminated time, the energy band is the visible-time band multiplied by the same constant: **no new uncertainty is invented and none is dropped**.

## 2a. Inputs (all explicit)
| Input | Rule |
|---|---|
| `area_m2` | required, in (0, 10 000] m²; **no hidden default panel** (the UI offers a labelled example, 1 m² / 0.30, "illustrative, not a design") |
| `efficiency` | required, fraction in (0, 1] |
| `irradiance_w_m2` | optional, in [1000, 1500] W/m²; default **1361 W/m²** = nominal solar constant at 1 AU, an **assumption**, reported as `irradiance_is_default_assumption` |
| site, `start_utc`, `duration_days`, `observer_height_m` (default 2.0 m, C9), `position_uncertainty_m` (default 100 m, > 0), `az_step_deg` | as for scenarios |
Invalid input → `INVALID_INPUT` naming the field, **before** any calculation. A site without supporting terrain data returns `terrain_data_insufficient` with the reason and **no energy figure** (same rule as Stage 6).

## 3. Outputs
`terrain_corrected`: `energy_wh`, `mean_power_w`, `sunlit_hours` (each nominal + position band), `longest_without_direct_sunlight` (hours, band, `includes_open_interval`); `geometric` (same panel, no terrain); `terrain_effect.energy_wh_terrain_minus_geometric`; `partial_disc_bracket` (whole-disc energy as a lower bracket to the any-part headline, nominal positions only, no band); `panel` (incl. peak power and formula); `position_sensitivity` block; `assumptions`; `limitations`; `provenance` (deterministic calculation metadata). The scenario summary gained `terrain_corrected.state_fractions` (centre / any-part / whole-disc visible fractions) to supply the bracket; this changed the model version to 0.10.0-stage8 (scenario caches rebuild).

## 4. Worked example (real result, IM-2 Athena, 2027-01-15 + 30 d, 15-min steps, observer 2.0 m, ±100 m, panel 1 m² × 0.30)
| | Terrain-corrected (nominal, [position band]) | Geometric (no terrain) |
|---|---|---|
| Peak electrical power while illuminated | 408.3 W (0.30 × 1 × 1361) | |
| Energy over 720 h | **143.0 kWh** [133.6, 143.9] | 156.8 kWh |
| Mean power | 198.6 W [185.5, 199.8] | 217.7 W |
| Illuminated time | 350.3 h [327.2, 352.4] | 383.95 h |
| Longest period without direct sunlight | 15.4 d [15.3, 16.4] (closed) | |
| Terrain effect | −13.8 kWh | |
| Partial-Sun bracket | 137.1 kWh (whole disc above terrain) to 143.0 kWh (any part) | |
Hand check: 0.30 × 1361 W × 1 260 929.0 s ÷ 3600 = 143 010.364 Wh; the API returns 143 010.365 Wh.

## 5. Evidence (`tests/engine/test_engineering.py`, `tests/api/test_api_stage8.py`, `web/src/SolarPanel.test.tsx`)
* **Analytic**: 1 m² perfect panel for 1 h = exactly the irradiance in Wh; E = η·A·I·t; mean power = peak × illuminated fraction; linear in area, efficiency and irradiance.
* **Bands**: energy band = visible-time band × factor; nominal always inside; a smaller position uncertainty gives a narrower energy band (API test).
* **Honesty**: labelled UPPER BOUND / "not battery state"; default irradiance flagged; assumptions and limitations returned with every result; zero-sun case gives 0 with band [0, 0], not a missing number; open-interval flag passed through; whole-disc ≤ any-part.
* **Typed errors**: 18 invalid-input cases (NaN, ±inf, bool, string, None, out of range, boundary values accepted) each name the field; an insufficient scenario is refused, never estimated; IM-1, Chandrayaan-3 and the exact pole return a label with no energy keys (API test).
* **Reuse rule**: a static test fails if the module imports ephemeris/horizon/visibility/frames/DEM/SPICE/rasterio code.
* **Cross-check against the reused service**: energy = factor × `total_visible_s` from `/scenarios/evaluate` for the same scenario id; geometric and band likewise.
* **UI** (`SolarPanel`): input validation before any request; the request actually sent; band, geometric, "cut off" flag, default-assumption label, bracket, assumptions; insufficient site shows no figure; backend errors show the field; the capability tag shows the real status.
* Real-browser check: panel rendered with real data, console clean (`docs/stage8/solar_panel.png`).

## 6. Assumptions and limitations (also returned by the API and shown in the UI)
1. **Sun-tracking panel** (no incidence-angle loss). A fixed panel would produce less; an incidence model would need per-displacement elevation series that have no band, so it was left out rather than given an invented band.
2. **Partly visible Sun counts as fully illuminating**; the whole-disc figure brackets the effect (≈ 4 % at IM-2) but has no position band.
3. **Constant irradiance** (1361 W/m² default). The ±3.4 % Earth–Sun distance variation (±6.9 % irradiance) over the year is **not modelled**; this can be tested only against the ephemeris range, which the engineering module deliberately does not touch.
4. Constant efficiency; no temperature, degradation, dust, wiring, power-conditioning or lander self-shadowing.
5. Terrain is the LOLA DEM horizon (boulders/lander not modelled); position band = a sensitivity to the input position (8 directions), not an error bar and not a bound (L-M8).
6. Idealised: **not** a power budget, battery state, eclipse/thermal or link analysis.
Everything in `docs/stage9/KNOWN_LIMITATIONS.md` still applies; new items L-M15 and L-M16 are recorded there.

## 7. Deferred (not built)
Antenna elevation mask and pointing constraints; terrain slope, aspect and roughness; temperature datasets; incidence-angle solar power; battery/thermal models; engineering dashboard beyond this one panel. `POST /engineering/antenna` returns `501 NOT_IMPLEMENTED` to make the boundary explicit.
