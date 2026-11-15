# Known limitations and future work (Stage 11, task 12)

The authoritative list of limitations, each with its effect and evidence, is [stage9/KNOWN_LIMITATIONS.md](../stage9/KNOWN_LIMITATIONS.md) (38 items). This page groups what to do about them, in priority order for a team continuing the project.

## What the project does not claim (summary)
Geometric line of sight and direct illumination only; no link budget, irradiance, thermal, power or battery results; "validated" means owner-approved after review, not proven against measurement; the position band is a sensitivity sample, not a proven bound; Horizons validates the implementation, not the ephemerides; terrain is interpolated LOLA data with no propagated height uncertainty; only IM-2 has 20 m terrain, Chandrayaan-3 has 60 m terrain that is registered but not owner-approved, IM-1 has too little terrain.

## 1. Science (highest value first)
1. **Independent validation against illumination products.** Compare the computed Sun-visible fraction at IM-2 and nearby points with LRO-derived polar illumination maps (NASA PGDA / LROC WAC percentage- and time-weighted illumination, 100 m, which Moon Trek also serves). This is the strongest available check that is *physically independent* of the ephemeris and of our horizon code. Expected effort: 1–2 days.
2. **Terrain for IM-1** (extend the 20 m window beyond its 4 km edge by fetching more of `LDEM_80S_20MPP_ADJ` or the 75S 30 m product) and a proper terrain-approval review of the Chandrayaan-3 60 m window (resolution study, frame check, EFFRES/ERR layers).
3. **Propagate DEM height error** (the provider's `_ERR` layers) into the horizon, and report effective resolution (`_EFFRES`) per site.
4. **More sites** once primary-source coordinates exist (Artemis III candidate regions are listed as pending, never invented).
5. **Beyond geometry:** antenna elevation masks and pointing constraints, terrain slope/aspect/roughness, temperature data, an incidence-angle power model, permanently shadowed region mapping. Each needs its own method document, validation and owner gate.
6. A proper bound on position sensitivity (denser or adaptive displacement sampling) instead of an 8-direction sample.

## 2. Product and interface
* Sunset/Earthset countdown: **done** (15 November 2026), display-only from the backend intervals.
* **3D terrain** was assessed and deliberately not built ([stage10x/TIER3_ASSESSMENT.md](../stage10x/TIER3_ASSESSMENT.md)): it needs a new height-patch endpoint, a rendering dependency and care with exaggeration, shading and resolution honesty.
* Permalinks to a computed view, PDF/report export, saved scenarios, multi-site sweeps, mobile layout polish.
* **Accessibility:** a manual screen-reader walkthrough and a formal audit (automated checks and keyboard tests exist); cross-browser testing (verified in Chrome/Chromium only).
* Self-host the map imagery if the providers' terms allow, to remove the live dependency on `trek.nasa.gov` and the IP disclosure.

## 3. Engineering
* **Job queue with progress** for new points (about a minute today), and a precomputed or parallel terrain-profile grid; shared cache and limiter for multi-worker deployments.
* **Verify the container image** (build, scan, run) and add a CI workflow run on GitHub; add per-IP rate limiting at the proxy.
* Extract the repeated "run" logic of the five computing tabs into one hook; split the About tab; tidy the `responses=` type annotations (mypy findings); add a coverage report.
* Regenerate `MODEL_VERSION` semantics if any science changes (cache keys and provenance depend on it).

## 4. Decisions waiting for the project owner
| Decision | Why it matters |
|---|---|
| **Choose a licence** for the source repository | None is declared; required before others may reuse the code |
| **Approve (or not) Chandrayaan-3 terrain as a gate** | It stays labelled "not yet approved" until then |
| **Provide hosting** for the public deployment | The authors cannot create accounts ([DEPLOYMENT.md](../DEPLOYMENT.md)) |
| Confirm provider terms for NASA imagery and data before use beyond a demonstration | No product-specific licence text was found ([ATTRIBUTION.md](../ATTRIBUTION.md)) |
