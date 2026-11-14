# Development Setup (Windows 11)

## Tool versions installed in Stage 1

| Tool | Version | Source / location |
|---|---|---|
| Git | 2.56.1.windows.1 | pre-installed |
| Python | 3.12.10 | python.org installer via `winget install Python.Python.3.12 --scope user` → `%LOCALAPPDATA%\Programs\Python\Python312` |
| Node.js | 24.22.3 (LTS "Krypton", released 2026-11-10) | Official portable zip from nodejs.org, SHA-256 verified against `SHASUMS256.txt` (`e612af99…7d9f`) → `%LOCALAPPDATA%\Programs\nodejs` |
| npm | 11.19.1 | bundled with Node |

Why a portable Node zip: the winget MSI needs an interactive admin (UAC) prompt, which an unattended session cannot answer. A first download attempt was corrupted by a connection reset; it failed checksum verification and was discarded.
If you prefer a system install: `winget install OpenJS.NodeJS.LTS` from an elevated terminal.

## First-time setup

PowerShell, from the repo root:

```powershell
# Backend
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item .env.example .env

# Frontend (Node must be on PATH for this shell)
$env:Path = "$env:LOCALAPPDATA\Programs\nodejs;$env:Path"
cd web; npm install; cd ..
```

## Run

```powershell
# Terminal 1 — backend (http://127.0.0.1:8000, docs at /docs)
.\.venv\Scripts\python.exe -m uvicorn lunarnav_api.main:app --reload --port 8000

# Terminal 2 — frontend (http://localhost:5173, proxies /api -> backend)
$env:Path = "$env:LOCALAPPDATA\Programs\nodejs;$env:Path"
cd web; npm run dev
```

## Test / lint / contract

```powershell
.\.venv\Scripts\python.exe -m pytest                         # engine + API tests
.\.venv\Scripts\python.exe -m ruff check .                   # lint
cd web; npm test; npm run typecheck                           # frontend tests + types
# After changing API schemas:
.\.venv\Scripts\python.exe scripts\export_openapi.py          # writes docs/openapi.json
cd web; npm run gen:api                                       # regenerates src/api/schema.d.ts
```

## Rebuild the (git-ignored) scientific data
```powershell
.\.venv\Scripts\python.exe scripts\fetch_kernels.py          # NAIF kernels, MD5-verified (~45 MB)
.\.venv\Scripts\python.exe -I scripts\inspect_kernels.py      # coverage/version metadata into the manifest
.\.venv\Scripts\python.exe -I scripts\extract_dem_window.py    # LOLA windows; the default set includes the 80 km / 20 m IM-2 window (~190 MB download)
.\.venv\Scripts\python.exe -I scripts\extract_dem_window.py im2_20m_r10km im2_320m_r160km im1_20m_r2km   # only the 3 small windows (~5 MB)
```
Tests that need the windows (or the kernels) skip with the rebuild command in their message when the files are absent.

## Stage 3 ephemeris validation
```powershell
.\.venv\Scripts\python.exe -I scripts\fetch_horizons_reference.py   # (network) re-record the JPL Horizons oracle -> data/validation/
$env:PYTHONPATH="scripts"; .\.venv\Scripts\python.exe scripts\validate_ephemeris.py     # offline engine-vs-Horizons residuals (exit 1 on failure)
$env:PYTHONPATH="scripts"; .\.venv\Scripts\python.exe scripts\ephemeris_sensitivity.py  # size of each modelling choice
```
The Horizons fixture is tracked (small); re-fetching is only needed to extend the grid.

## Stage 4 terrain horizon
```powershell
.\.venv\Scripts\python.exe -I scripts\extract_dem_window.py im2_20m_r80km     # 80 km @ 20 m, ~190 MB, checkpointed: re-run resumes after a dropped connection
.\.venv\Scripts\python.exe -I scripts\validate_horizon.py --json docs\stage4\validation_summary.json   # engine vs independent implementation (exit 1 on failure)
.\.venv\Scripts\python.exe -I scripts\horizon_resolution_study.py --json docs\stage4\resolution_study.json  # resolution / sampling / position limits (a few minutes)
```
Horizon profiles are cached in `data/results/horizon` (git-ignored, regenerable). Real-DEM tests skip with the rebuild command when the windows are absent.

## Stage 5 visibility
```powershell
.\.venv\Scripts\python.exe -I scripts\visibility_study.py --json docs\stage5\im2_study.json   # IM-2 30-day result, position-band sweep, step convergence
```
The first `/visibility/*` call for a site computes the nominal + 8 displaced horizon profiles (about 60 s for IM-2 at 0.25 degrees); they are cached in `data/results/horizon`.

## Dependencies
- Python: declared in `pyproject.toml`; exact resolved versions pinned in `requirements.lock.txt` (`pip freeze`). Science libraries are added in the stage that first needs them (numpy, rasterio, pyproj: Stage 2; spiceypy 8.4.0 / CSPICE N0067: Stage 3).
- Frontend: `web/package.json` + `web/package-lock.json`.

## Not committed (decision G1)
`.venv/`, `node_modules/`, `.env`, and everything in `data/kernels`, `data/dem_cache`, `data/results`.
