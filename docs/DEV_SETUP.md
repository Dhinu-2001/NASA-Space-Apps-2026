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

## Dependencies
- Python: declared in `pyproject.toml`; exact resolved versions pinned in `requirements.lock.txt` (`pip freeze`). Science libraries (spiceypy, numpy, rasterio, pyproj) are added in the stage that first needs them.
- Frontend: `web/package.json` + `web/package-lock.json`.

## Not committed (decision G1)
`.venv/`, `node_modules/`, `.env`, and everything in `data/kernels`, `data/dem_cache`, `data/results`.
