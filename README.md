# Lunar Landing Site Navigator

NASA Space Apps Challenge 2026 — a scientifically grounded tool for comparing lunar south-pole landing sites and dates by terrain-corrected Sun and Earth visibility.

**Status: Stage 4 (terrain horizon profiles on top of the Stage 3 ephemeris and Stage 2 site/DEM foundation).** Sun/Earth azimuth/elevation come from local SPICE (DE440), validated against JPL Horizons; the terrain horizon is ray-sampled from LOLA DEM windows. **Terrain-corrected Sun/Earth visibility does not exist yet (Stage 5)**; the two are not combined. See `/version` (or the UI) for the honest capability table.

- Specifications: [docs/stage0/](docs/stage0/) · Decisions: [docs/DECISIONS.md](docs/DECISIONS.md)
- Architecture: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · API: [docs/API_CONTRACT.md](docs/API_CONTRACT.md)
- Stage 2 data docs: [docs/stage2/](docs/stage2/) · Stage 3 ephemeris method and validation: [docs/stage3/](docs/stage3/) · Stage 4 horizon method, validation and resolution limits: [docs/stage4/](docs/stage4/)
- Setup and run commands: [docs/DEV_SETUP.md](docs/DEV_SETUP.md)

Data sources: LOLA digital elevation models (NASA GSFC PGDA; in use since Stage 2), NAIF SPICE DE440 kernels (in use since Stage 3, checksum-verified at load), JPL Horizons (validation oracle only; reference values recorded in `data/validation/`). Site coordinates: NASA/JPL NAIF and LROC (NASA/GSFC/ASU).
