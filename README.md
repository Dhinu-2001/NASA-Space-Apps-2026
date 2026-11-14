# Lunar Landing Site Navigator

NASA Space Apps Challenge 2026 — a scientifically grounded tool for comparing lunar south-pole landing sites and dates by terrain-corrected Sun and Earth visibility.

**Status: Stage 2 (site catalogue and LOLA DEM foundation).** No Sun/Earth, horizon or visibility results exist yet. See `/version` (or the UI) for the honest capability table.

- Specifications: [docs/stage0/](docs/stage0/) · Decisions: [docs/DECISIONS.md](docs/DECISIONS.md)
- Architecture: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · API: [docs/API_CONTRACT.md](docs/API_CONTRACT.md)
- Stage 2 data docs: [docs/stage2/](docs/stage2/)
- Setup and run commands: [docs/DEV_SETUP.md](docs/DEV_SETUP.md)

Data sources: LOLA digital elevation models (NASA GSFC PGDA; in use since Stage 2), NAIF SPICE DE440 kernels (downloaded and verified, not yet used), JPL Horizons (validation reference, Stage 3). Site coordinates: NASA/JPL NAIF and LROC (NASA/GSFC/ASU).
