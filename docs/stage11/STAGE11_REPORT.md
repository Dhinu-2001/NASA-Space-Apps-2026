# Stage 11 evaluation report: final integration, documentation and deployment

Date: 2026-11-15. Owner approval: "APPROVED — PROCEED TO STAGE 11". Owner decisions taken at the start: deployment route **configuration plus a guided deploy** (the owner performs the final deploy); presentation format **.pptx**.

## 1. Stage objective
Prepare a complete, stable and demonstrable project: end-to-end testing, architecture/security/performance reviews, demonstration-data removal, NASA attribution, final documentation, deployment configuration, deployment, a demonstration scenario, a presentation, and documented limitations and future work.

## 2. Features implemented
* **Security hardening** (no science change): security headers, CSP on the UI, request body cap, bounded compute concurrency with typed `503 SERVER_BUSY`, LRU-capped result caches, list-size limits, build-commit stamp.
* **One-process production entry point** (`lunarnav_api.serve`): UI at `/`, API at `/api`.
* **Deployment configuration:** Dockerfile, compose file, entrypoint, runtime requirements, data provisioning/packing/verification scripts, production run scripts, CI workflow.
* **End-to-end browser test** (`scripts/e2e_browser.py`, 25 checks with console and network monitoring).
* **Attribution:** `docs/ATTRIBUTION.md` and a Credits panel in the About tab.
* **Release metadata:** API 1.0.0, stage 11; error contract completed (`NOT_FOUND`, `SERVER_BUSY`, 413).
* **Documentation set, demonstration script and a 14-slide .pptx presentation with speaker notes.**
* A small map hardening (reserved readout line) and an About-tab count update; two defects found and fixed during the stage (below).

## 3. Files created (37 incl. screenshots; non-image listed)
`Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.gitattributes`, `.github/workflows/ci.yml`, `deploy/docker-entrypoint.sh`, `requirements.runtime.txt`, `api/lunarnav_api/{hardening,serve}.py`, `engine/lunarnav/cachecap.py`, `scripts/{e2e_browser,verify_data,provision_data,pack_data}.py`, `scripts/run_production.{sh,ps1}`, `tests/api/test_hardening.py`, `tests/engine/test_cachecap.py`, `docs/{ATTRIBUTION,DEPLOYMENT,METHODOLOGY,TEST_AND_VALIDATION}.md`, `docs/stage11/{SECURITY_REVIEW,PERFORMANCE,CODE_REVIEW,E2E_REPORT,FUTURE_WORK,DEMO_SCRIPT,STAGE11_REPORT}.md`, `docs/stage11/e2e_results.json`, `docs/stage11/e2e/*.png`, `docs/stage11/presentation/Lunar_Landing_Site_Navigator.pptx`.

## 4. Files modified
`README.md` (rewritten), `docs/ARCHITECTURE.md` (rewritten), `docs/API_CONTRACT.md`, `docs/DECISIONS.md` (T1), `docs/openapi.json`, `docs/stage9/{KNOWN_LIMITATIONS,VALIDATION_REPORT,PROVENANCE,TEST_REPORT}.md` (limitations L-P10–L-P12, regenerated reports), `.env.example`, `.gitignore`, `api/lunarnav_api/{config,main,routes_scenarios,routes_visibility,schemas}.py`, `engine/lunarnav/{horizon,scenarios}.py` (cache housekeeping only), `web/src/views/AboutTab.tsx`, `web/src/components/SiteMap.tsx`, `web/src/api/schema.d.ts`, tests and fixtures for the version change.

## 5. Architecture changes
A serving layer (`serve.py`) and an HTTP hardening layer (`hardening.py`) added around the unchanged API app; cache housekeeping module in the engine. **No change to any scientific module, algorithm, tolerance or `MODEL_VERSION`.** See [../ARCHITECTURE.md](../ARCHITECTURE.md).

## 6. Dependencies added
None at runtime. Tooling used and not added to the project: `pip-audit`, `mypy` (one-off audits), `pptxgenjs` and Pillow/python-pptx (deck build and checks, in scratch folders).

## 7–8. Tests executed and results
| Check | Result |
|---|---|
| Backend pytest (with data) | **388 pass**, 0 fail, 0 skip (was 367: +21 hardening/cache tests) |
| Backend in a clean clone, no data | 273 pass, 115 skip, 0 fail |
| Frontend Vitest | **175 pass** (174 at the start of the stage; +1 map-hover regression test) |
| End-to-end real browser, production build from a clean virtualenv | **25 / 25 pass**, 0 exceptions, 0 console errors, 0 unexpected failed requests |
| ruff; TypeScript strict; production build | clean |
| `pip-audit` (38 packages) / `npm audit` | no known vulnerabilities / 0 |
| Deck: schema validator; text-fit check with real font metrics | pass / 0 problems (no renderer available; see 10) |

## 9. Scientific validation results
Unchanged and re-confirmed by the golden-regression suites and the browser test (IM-2 Sun 48.6 % [45.4, 48.9], Earth 80.8 %, solar 143.0 kWh, Chandrayaan-3 49.1 %, IM-1 insufficient). Ephemeris vs Horizons 1.4×10⁻⁸° / 6×10⁻⁷°; horizon vs independent implementation 1.1×10⁻⁹°. No new science was introduced in this stage.

## 10. Known issues
1. **No public deployment exists** and **the container image has never been built** (no Docker on the development machine); only the equivalent clean-virtualenv production run is verified.
2. **Presentation not visually rendered:** LibreOffice is not installed here, so the deck was checked by schema validation, a font-metric text-fit check and a wireframe drawn from the file; the two native charts (slides 5 and 6) have not been seen rendered. Open it in PowerPoint and check them.
3. **Attribution terms unconfirmed:** no Moon Trek-, PGDA- or LROC-specific licence text was found (NASA general guidance applies; credits shown). Not legal advice.
4. **No licence declared** for the project's own code.
5. A point nobody has computed takes about 70 s (L-P10); no per-IP rate limiting (L-P12); the security and code reviews are self-reviews.
6. ~~Countdown to sunset/Earthset not shown~~ — added 15 November 2026 (see addendum).
7. The development backend on :8000 still runs the pre-Stage 11 code (header shows API 0.1.0, stage 9) until restarted; no functional difference for the UI.
8. Commits made after the last push are local until pushed (this agent does not push).

## 11. Outstanding tasks (all owner-side or optional)
Choose hosting and deploy (guide: [../DEPLOYMENT.md](../DEPLOYMENT.md)); build and scan the container image; choose a licence; approve or reject Chandrayaan-3 terrain as a gate; confirm provider terms; open and check the deck, add the deployed URL; push to GitHub and confirm the repository is public.

## 12. Acceptance criteria status
| # | Task / deliverable | Status |
|---|---|---|
| 1 | End-to-end testing | **PASS** |
| 2 | Architecture and code-quality review | **PASS** (self-review; stated) |
| 3 | Security review | **PASS** (hardened; not a penetration test; residual risks listed) |
| 4 | Performance review | **PASS** (measured; limits documented) |
| 5 | Remove demonstration data from production views | **PASS** (audit found no mock or fixture data in the bundle; built-in profiles and the solar example are labelled illustrative; `?autorun`/`?scrub` demo links retained deliberately and produce only real computed results) |
| 6 | Verify NASA data attribution | **PARTIAL** (attribution complete and shown in the app; provider-specific terms not located) |
| 7 | Finalise application documentation | **PASS** |
| 8 | Prepare deployment configuration | **PARTIAL** (written; image unbuilt; clean-venv production run verified) |
| 9 | Deploy the application | **BLOCKED** (needs the owner's hosting account; guided steps ready) |
| 10 | Demonstration scenario | **PASS** (every quoted number checked against the live app; browser rehearsal 25/25) |
| 11 | Project presentation | **PARTIAL** (built, validated, notes written; not visually rendered here) |
| 12 | Known limitations and future work | **PASS** |
| D | Deliverables: working deployed application | **NOT MET** (see 9); source repository: **PASS** (push pending); README, architecture, methodology, API documentation, test and validation report, demonstration script, presentation: **PASS / PARTIAL** as above |
| A | Final acceptance: complete workflow from site selection to comparing scenarios; measured, calculated, estimated and illustrative content distinguished | **PASS** (browser test; data classes and labels on every result) |

**Overall Stage 11: PARTIAL**, because the public deployment is blocked on an external decision and three items carry stated caveats.

## 13. Recommended next action
1. **Deploy** using [../DEPLOYMENT.md](../DEPLOYMENT.md) (the fastest verified path is the one-process production run; Docker if your host needs it), then run `scripts/e2e_browser.py --base <url>` against it.
2. Open the deck in PowerPoint, check the two charts, add the live URL.
3. ~~Sunset/Earthset countdown~~ — done (see addendum).
4. Decide licence and Chandrayaan-3 approval; push to GitHub.

## Addendum (15 November 2026): sunset/Earthset countdown added
Item 6 of the open issues and item 3 above are closed. The Sun and Earth cards in **Site & time** now show **"Sunset in X" / "Sunrise in X" / "Earthset in X" / "Earthrise in X"**: the time from the shown instant to the next change of the terrain-corrected state, with the position-uncertainty band of that event. Display-only (C4): remaining time = the backend's interval event time minus the shown time; no new request, no trigonometry (tests enforce both). If the state lasts to the end of the computed window the card says "stays visible/blocked for at least X (cut off)", never a prediction; an event seen at only some sampled positions is flagged "incomplete band"; nothing is shown outside the window or for sites without terrain.
Evidence: 11 new frontend tests (frontend 186 pass); real-data check against the API's own intervals (IM-2 default: Sunset in 13.4 d, band 13.0–13.5 d, incomplete band; Earthset in 12.5 d, band 12.4–12.5 d); end-to-end check 1g, now **26/26** on the production build; screenshot `countdown_view.png`. Still the same terrain-corrected geometry: not a power, thermal or link claim.
