# Stage 10 extras — Tier 3 assessment: 3D lunar terrain rendering (assessment only, nothing built)

Written 2026-11-15 09:04 IST, about 15 hours before the 23:59 IST deadline. Branch `feature/stage10-extras`; main is untouched.

## Recommendation: do NOT start Tier 3 as scoped
It is technically possible, but not safely, and not within the rules this branch has worked under. Reasons in order of weight:

### 1. The data to draw it does not exist in the API (the blocking issue)
The only terrain endpoint that returns heights is `GET /dem/elevation`: **one point per call**. `/dem/windows` returns metadata only; `/horizon/profile` returns horizon angles, not terrain. A 3D surface needs a height grid.
* Without a backend change the only route is a grid of point calls: a modest 33 × 33 mesh is **1089 requests**, one per vertex. That breaks the one-request-per-action design and the C4 request-count tests, and would be slow and wasteful. Not acceptable.
* With a backend change: a new endpoint serving a down-sampled height patch (site, half-width, grid size) read through the existing `DemRegistry` bilinear sampler. That is a **new API surface**, not a display change. It needs its own decision (it was not authorised: Tiers 1–2 were explicitly "no new backend computation"), tests, OpenAPI regeneration, a data-class label (`measured_interpolated`), window/pixel-size provenance, typed errors for uncovered sites, and a merge into the backend on main, which is the submission.

### 2. Rendering rules that would need owner decisions
* **No browser-side shadows or sun-lit shading.** WebGL shadow mapping or Sun-direction hillshading would be a second, unvalidated visibility calculation in the browser (C4) that could visibly disagree with the validated horizon-ray engine and with the numbers on screen. The only safe lighting is a fixed, neutral one, which looks less impressive. Sun/Earth direction markers from the API's azimuth/elevation are acceptable.
* **Vertical exaggeration** is unavoidable at lunar-pole relief (a few km over tens of km) and misleads unless labelled and adjustable.
* **Resolution honesty:** IM-2 is 20 m, Chandrayaan-3 is 60 m and registered-but-unapproved (would need the same flag), and the 320 m overview is area-averaged and lowers peaks. A pretty mesh implies precision the data do not have.
* **IM-1:** it has terrain data (2 km of 20 m) but is "terrain data insufficient" for visibility. A 3D view of it would sit awkwardly beside the standing rule that it shows the label and no figures. Default would have to be the label only.

### 3. Engineering and verification risk
* No 3D library is installed. Adding one (three.js or similar) means a new dependency and a bundle-size increase; the worktree's `node_modules` is currently a junction to main's, so it would have to be replaced with a real install to avoid touching main's packages.
* **jsdom has no WebGL**, so the rendering cannot be unit-tested; it would be tested only through mocks plus manual or headless-browser screenshots. The project's evidence standard (tests for new logic, request-count test, axe) is hard to meet honestly for a canvas.
* **Accessibility:** a WebGL canvas needs a text alternative, keyboard operation for orbit/zoom, reduced-motion handling and a no-WebGL fallback. Each is real work, and Stage 10 core is built to WCAG-style checks.

### 4. Time and priority
Estimated effort if authorised with a backend endpoint: **about 6–8 hours** (backend endpoint, tests, docs ≈ 2–3 h; frontend integration, controls, fallback, accessibility, tests and verification ≈ 4–5 h), with real chance of overrun. **Stage 11 (final integration, deployment configuration, documentation, demo script, presentation) is mandatory, has not been authorised or started, and is what the submission actually depends on.** Spending ~half of the remaining time on an optional visual is the wrong trade.

## What already covers the intent
* The Site & time tab already shows the **terrain as seen from the lander**: the horizon profile and the new sky chart (Tier 1) give the full 360° skyline, with Sun and Earth tracks and the limiting terrain distance.
* If a 3D view is still wanted later, the smallest honest version is: one new read-only height-patch endpoint + a plain mesh with fixed lighting, labelled vertical exaggeration, a resolution/approval banner, a text alternative and a no-WebGL fallback. Treat it as post-submission work.

## Decision needed from the owner
Either (a) **skip Tier 3** (recommended; branch stays at Tier 2, main untouched), or (b) explicitly authorise a backend height-patch endpoint **and** the 3D dependency as a separate decision, accepting that it competes with Stage 11 for the remaining time.
