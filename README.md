# Lunar Landing Site Navigator

NASA Space Apps Challenge 2026 — a scientifically grounded tool for comparing lunar south-pole landing sites and dates by terrain-corrected Sun and Earth visibility.

**Status: Stage 3 (geometric Sun/Earth ephemeris on top of the Stage 2 site/DEM foundation).** Sun/Earth azimuth/elevation are computed with local SPICE (DE440) and validated against JPL Horizons; **no terrain horizon or terrain-corrected visibility exists yet**, so elevations are geometric only. See `/version` (or the UI) for the honest capability table.

- Specifications: [docs/stage0/](docs/stage0/) · Decisions: [docs/DECISIONS.md](docs/DECISIONS.md)
- Architecture: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · API: [docs/API_CONTRACT.md](docs/API_CONTRACT.md)
- Stage 2 data docs: [docs/stage2/](docs/stage2/) · Stage 3 ephemeris method and validation: [docs/stage3/](docs/stage3/)
- Setup and run commands: [docs/DEV_SETUP.md](docs/DEV_SETUP.md)

Data sources: LOLA digital elevation models (NASA GSFC PGDA; in use since Stage 2), NAIF SPICE DE440 kernels (in use since Stage 3, checksum-verified at load), JPL Horizons (validation oracle only; reference values recorded in `data/validation/`). Site coordinates: NASA/JPL NAIF and LROC (NASA/GSFC/ASU).
