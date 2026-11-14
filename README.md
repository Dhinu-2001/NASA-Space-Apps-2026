# Lunar Landing Site Navigator

NASA Space Apps Challenge 2026 — a scientifically grounded tool for comparing lunar south-pole landing sites and dates by terrain-corrected Sun and Earth visibility.

**Status: Stage 7 (read-only web UI over the validated engine: site and time, Sun/Earth positions, terrain horizon, visibility timelines, comparison and delay simulator, with position-sensitivity bands).** Sun/Earth directions come from local SPICE (DE440), validated against JPL Horizons; the terrain horizon is ray-sampled from LOLA DEM windows; visibility, transitions and intervals combine the two. Geometric line of sight / direct illumination only, not link availability or irradiance. Sites without supporting terrain data are reported as terrain_data_insufficient and never ranked. See `/version` (or the UI) for the honest capability table.

- Specifications: [docs/stage0/](docs/stage0/) · Decisions: [docs/DECISIONS.md](docs/DECISIONS.md)
- Architecture: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · API: [docs/API_CONTRACT.md](docs/API_CONTRACT.md)
- Stage 2 data docs: [docs/stage2/](docs/stage2/) · Stage 3 ephemeris method and validation: [docs/stage3/](docs/stage3/) · Stage 4 horizon: [docs/stage4/](docs/stage4/) · Stage 5 visibility: [docs/stage5/](docs/stage5/) · Stage 6 scenarios: [docs/stage6/](docs/stage6/) · Stage 7 UI: [docs/stage7/](docs/stage7/)
- Setup and run commands: [docs/DEV_SETUP.md](docs/DEV_SETUP.md)

Data sources: LOLA digital elevation models (NASA GSFC PGDA; in use since Stage 2), NAIF SPICE DE440 kernels (in use since Stage 3, checksum-verified at load), JPL Horizons (validation oracle only; reference values recorded in `data/validation/`). Site coordinates: NASA/JPL NAIF and LROC (NASA/GSFC/ASU).
