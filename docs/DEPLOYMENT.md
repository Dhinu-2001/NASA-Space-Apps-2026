# Deployment guide

The application is **one Python process** serving the built web UI and the API on one port (`/` UI, `/api` API), plus about **290 MB of scientific data** that is not in git. There is no database, no queue and no secret. Figures below are measured (see [stage11/PERFORMANCE.md](stage11/PERFORMANCE.md)).

| Resource | Need |
|---|---|
| CPU | 1–2 cores (a cold new point is about a minute of one core; cached answers take milliseconds) |
| Memory | about 85 MB idle, **about 350 MB** after real work; give it **1 GB** (a 512 MB instance is too tight) |
| Disk | 300 MB data + results cache (capped at about 1000 scenario files and 3000 horizon profiles, roughly 200 MB) |
| Network | one port (8000); outbound only to NASA for first-time data provisioning. Visitors' browsers load map tiles from `trek.nasa.gov` |

## What was and was not verified here
* **Verified (Windows, 2026-11-15):** a clean virtual environment built from `requirements.runtime.txt` plus `pip install --no-deps .`, started from an unrelated directory with environment variables only (`LUNARNAV_DATA_DIR`, `LUNARNAV_WEB_DIST`), serving UI + API; the 25-check browser test passes against it ([stage11/E2E_REPORT.md](stage11/E2E_REPORT.md)); `pip-audit` and `npm audit` clean.
* **Container verified (15 Nov 2026, Docker 29.9.3):** the image builds (507 MB), runs non-root, passes its health check and the full 26-check browser suite with data mounted at `/data` (see [stage11/DOCKER_VERIFICATION.md](stage11/DOCKER_VERIFICATION.md); the first run found a missing `libexpat1`, now fixed). **Still not done:** a vulnerability scan, `docker compose up`, and the in-container data download.
* **Not done:** a public deployment. It needs your hosting account; the steps below are written so that it takes minutes once the data are in place.

## 1. Get the data onto the host (once)
Pick one:

**A. Rebuild from NASA** (needs outbound internet; 30–60 minutes; resumable; the NASA PGDA server is slow and sometimes drops connections, just re-run):
```
python scripts/provision_data.py --warm        # kernels, DEM windows, then warm the caches
python scripts/provision_data.py --skip-large  # PARTIAL install (kernels + small windows, about 50 MB). IM-2 needs the 80 km window (141 MB), so with this option IM-2 reports 'terrain data insufficient (DATA_MISSING)'; it only gets the app running, e.g. for a smoke test
```
**B. Copy a bundle** (fast): on a machine that has the data, `python scripts/pack_data.py --with-cache` makes `lunarnav-data.tar.gz` (about 290 MB; it contains a `SHA256SUMS` file); unpack it into the data directory on the host. The application re-verifies every kernel and DEM window against `data/manifests` at load, so a damaged bundle is refused, never used.

Check the result: `python scripts/verify_data.py` prints `READY` and each window's checksum status (add `--require-all` to make a missing window fatal; without it the sites that window covers simply report "terrain data insufficient").

## 2. Run it

### Option 1: Docker (any host with Docker)
```
export GIT_COMMIT=$(git rev-parse --short HEAD)          # shown in /api/provenance and the About tab
docker compose up -d --build
# first run: put data into the volume (REQUIRED: the container does not download it itself and exits with "Data not ready" until you do)
docker compose run --rm --no-deps --entrypoint python lunarnav scripts/provision_data.py --warm   # NOTE: in Docker this currently yields files the app refuses (see stage11/DOCKER_VERIFICATION.md); prefer the bundle
#   or unpack a bundle:  docker run --rm -v <volume-name>:/data -v "$PWD":/in alpine tar xzf /in/lunarnav-data.tar.gz -C /data
#   (find <volume-name> with `docker volume ls`; compose names it <project>_lunarnav-data)
docker compose restart lunarnav
curl http://localhost:8000/api/health
```
The entrypoint links the `/data` volume into the app, runs `verify_data.py` and refuses to start on missing or corrupt kernels. Memory limit in the compose file is 1.5 GB.

### Option 2: a plain Linux VM or Windows machine (no Docker) — verified path
```
python -m venv .venv && .venv/bin/pip install -r requirements.runtime.txt && .venv/bin/pip install --no-deps .
cd web && npm ci && npm run build && cd ..                # or copy a prebuilt web/dist
export LUNARNAV_ENV=production LUNARNAV_DATA_DIR=$PWD/data LUNARNAV_WEB_DIST=$PWD/web/dist LUNARNAV_MAX_HEAVY_REQUESTS=2
sh scripts/run_production.sh 8000                        # PowerShell: .\scripts\run_production.ps1 -Port 8000
```
Run it under a service manager so it restarts: a minimal systemd unit is `ExecStart=/opt/lunarnav/.venv/bin/uvicorn lunarnav_api.serve:app --host 127.0.0.1 --port 8000 --proxy-headers` with the environment variables above in `Environment=` lines.

### Managed container platforms (Render, Fly.io, Railway, …)
Deploy the `Dockerfile`; attach a **persistent disk/volume of at least 1 GB at `/data`**; set the environment variables below; health check path `/api/health`; **at least 1 GB RAM**. Provision data once with the platform's shell (`python scripts/provision_data.py --warm`, or unpack a bundle). Free tiers with 512 MB or ephemeral disks will lose the data or run out of memory.

### HTTPS and timeouts (reverse proxy)
Terminate TLS in the platform or a reverse proxy (Caddy: `reverse_proxy 127.0.0.1:8000`). **Set the proxy read timeout to at least 180 seconds**: a first-time point takes about 70 s and most proxies default to 30–60 s. The UI and API share one origin, so **no CORS configuration is needed**; set `LUNARNAV_CORS_ORIGINS` only if the UI is hosted on a different origin.

## 3. Configuration (environment variables)
| Variable | Default | Meaning |
|---|---|---|
| `LUNARNAV_ENV` | `development` | `production` in deployments |
| `LUNARNAV_LOG_JSON` | `true` (code) | JSON log lines; set `false` for console logs |
| `LUNARNAV_LOG_LEVEL` | `INFO` | |
| `LUNARNAV_DATA_DIR` | `./data` | kernels, DEM windows, catalogue, manifests, results |
| `LUNARNAV_WEB_DIST` | `./web/dist` | built UI served at `/` |
| `LUNARNAV_MAX_HEAVY_REQUESTS` | `4` | concurrent computing requests; **use 2 on a small host**; others wait, then get `503 SERVER_BUSY` |
| `LUNARNAV_HEAVY_QUEUE_SECONDS` | `90` | how long a computing request may wait for a slot |
| `LUNARNAV_MAX_BODY_BYTES` | `262144` | request body cap |
| `LUNARNAV_CORS_ORIGINS` | localhost dev origins | JSON list of allowed browser origins |
| `LUNARNAV_GIT_COMMIT` | unset | build stamp for deployments without `.git` |

## 4. Operating it
* **Health:** `GET /api/health`. **What it is built from:** `GET /api/provenance` (commit, versions, kernel and DEM checksums). **API docs:** `/api/docs`.
* **Logs:** one JSON line per request with `request_id`, method, path, status, duration; no query strings, no client addresses. A busy server logs `server_busy`.
* **Warm caches** so the first visitor does not wait: `python scripts/warm_cache.py --base http://127.0.0.1:8000` (precomputes the default views and the comparison/delay examples).
* **Caches are disposable:** delete `data/results/*` at any time; they rebuild. They are LRU-capped so unique requests cannot fill the disk.
* **Update:** `git pull`, rebuild the image or the UI, restart. Scientific data are checksum-pinned, so an update never silently changes results; a changed model changes `MODEL_VERSION` and the cache keys.

## 5. Troubleshooting
| Symptom | Cause / fix |
|---|---|
| Container exits: "Data not ready" | Kernels missing or corrupt in `/data`: run `scripts/provision_data.py` or unpack a bundle; `verify_data.py` names the file |
| A site says "terrain data insufficient" that should work | Its DEM window file is missing (`verify_data.py` warns); Chandrayaan-3 needs `ch3_60m_r200km`, IM-2's finest terrain needs `im2_20m_r80km` |
| `503 SERVER_BUSY` | More computing requests than `LUNARNAV_MAX_HEAVY_REQUESTS` for longer than the queue time; retry (`Retry-After`) or raise the limit on a bigger host |
| Browser shows a gateway timeout on a new point | Proxy timeout below 180 s |
| Map shows no imagery | The visitor's network blocks `trek.nasa.gov`; the ring map and all results still work |
| `413` on a request | Body above `LUNARNAV_MAX_BODY_BYTES` (legitimate requests are well under 1 KB) |

## 6. Owner checklist for the public deployment
1. Choose a host and create the account (the authors cannot).
2. Provision data (section 1) and run `verify_data.py`.
3. Deploy (section 2), set the variables (section 3), set proxy timeouts, HTTPS.
4. Run the end-to-end test against the public URL: `python scripts/e2e_browser.py --base https://<your-host>` (needs Chrome and the warmed caches).
5. Put the URL in the README and the presentation.
