# Security review (Stage 11, task 3)

Scope: the HTTP API, the web UI, the build and deployment configuration and the data pipeline, reviewed against a **public, read-only, unauthenticated deployment**. Not a penetration test, and not a substitute for one before any wider public launch.

## 1. Threat model
| Asset | Notes |
|---|---|
| Availability | The one realistic threat: computing endpoints are CPU-heavy (a new point ≈ 70 s of one core) and results are cached on disk |
| Integrity of results | Scientific data and kernels are pinned by SHA-256; results are reproducible |
| Confidentiality | **There is nothing confidential**: no accounts, no stored user data, no secrets in the repository. Visitors' browsers contact NASA's tile server directly |
| Attackers | Anonymous internet clients: crafted input, oversized or abusive requests, request floods |

## 2. Findings and what was done
| # | Finding (severity) | Action | Evidence |
|---|---|---|---|
| S1 | **Unbounded result caches**: every unique request wrote a file to `data/results`; a client could fill the disk (medium) | LRU size caps (1000 scenarios, 3000 horizon profiles); a cache hit refreshes recency so warmed entries survive; in-progress temp files are never evicted | `engine/lunarnav/cachecap.py`, `tests/engine/test_cachecap.py` (5) |
| S2 | **No limit on concurrent heavy computations**: many cold requests could exhaust CPU/RAM (medium) | Bounded concurrency on the computing endpoints (`LUNARNAV_MAX_HEAVY_REQUESTS`); waiters queue for up to 90 s then receive a typed `503 SERVER_BUSY` with `Retry-After`; cheap endpoints are never queued | `api/lunarnav_api/hardening.py`, `tests/api/test_hardening.py` |
| S3 | **No security headers** (low) | `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy` (no geolocation/camera/microphone/payment/usb), `Cross-Origin-Opener-Policy` on every response, including errors | tests; E2E check 10a on the production build |
| S4 | **No Content-Security-Policy on the UI** (low) | UI responses carry `default-src 'self'; script-src 'self'; img-src 'self' data: https://trek.nasa.gov; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'` (`style-src` allows inline styles because React sets style attributes; scripts stay `'self'` only; no `unsafe-eval`) | `serve.py`; E2E loads every view under this CSP with no console errors |
| S5 | **Unbounded request size and list lengths** (low–medium): `sites × dates` lists were expanded before the 12-scenario check | Body cap 256 KB (declared or streamed) with a typed 413; pydantic length limits on `sites`, `start_utc_list`, `scenarios` (12), `offsets_days` (10), `bodies` (2), `label` (120) so oversize input is rejected before any work | tests: 5 request shapes rejected with typed 422, oversize and streamed bodies rejected with typed 413 |
| S6 | **CORS** (info) | Default allows only the local dev origins; production serves UI and API from one origin so none is needed; methods limited to GET/POST | `config.py`, `serve.py` |
| S7 | **Container and run hygiene** (info) | Non-root user, no secrets baked in, tracked data only, heavy data on a volume, fail-fast data verification, health check | `Dockerfile` (unbuilt here, see DEPLOYMENT.md) |
| S8 | **Build provenance** (info) | A deployment without `.git` showed an empty commit; `LUNARNAV_GIT_COMMIT` stamps it | test |

## 3. Reviewed and found sound (no change needed)
* **Path traversal:** `GET /scenarios/{id}` accepts only 64 lowercase hex characters before touching the filesystem; cache keys are hashes; no user-supplied path reaches `open()`.
* **Injection:** no database, no shell calls, no template rendering, no `eval`; numeric inputs are validated (finite, ranges); sites are resolved from a fixed catalogue or numeric coordinates.
* **Deserialisation:** disk caches are JSON and `numpy.load(..., allow_pickle=False)`; entries whose recorded key or version mismatch are ignored; a corrupt entry is recomputed, not trusted.
* **Error handling:** unknown exceptions return a generic 500 body (`Internal server error.`) with a request id; tracebacks go to the server log only; no absolute path or username appears in `/provenance` (checked).
* **XSS (UI):** React escapes all content; there is no `dangerouslySetInnerHTML`, `innerHTML` or `document.write` anywhere in the source; external links use `rel="noreferrer"`.
* **Data integrity:** kernels and DEM windows are SHA-256-verified at every load; mismatch ⇒ refused (`DATA_MISSING`).
* **Secrets:** none exist; `.env` is git-ignored; `.env.example` holds only non-secret settings.
* **Logging:** request path and status only; no query strings, no client addresses, no request bodies.
* **Dependencies:** `pip-audit` over the 38 pinned Python packages: *No known vulnerabilities found*; `npm audit` (production and development): *found 0 vulnerabilities* (2026-11-15). Versions are pinned by `requirements.lock.txt` and `package-lock.json`.

## 4. Residual risks (accepted, with the mitigation to apply when deploying)
| Risk | Why it remains | Mitigation |
|---|---|---|
| Request floods from one client | There is no per-IP rate limit; the limiter protects the host's CPU, not fairness between clients | Put a rate-limiting reverse proxy or CDN in front for a public launch |
| Availability under load | A slow request occupies a slot for up to about a minute; many cold new points queue and then receive 503 | Warm the caches; `LUNARNAV_MAX_HEAVY_REQUESTS=2`; scale vertically; future work: job queue ([FUTURE_WORK.md](FUTURE_WORK.md)) |
| No TLS in the application | By design | Terminate TLS at the platform or proxy (DEPLOYMENT.md) |
| API documentation exposed at `/api/docs` | It is a deliverable and read-only; the docs page loads Swagger assets from a CDN | Disable by deploying the plain `main` app behind the proxy if undesired |
| Map imagery from NASA's server | The visitor's IP and the page origin reach `trek.nasa.gov` (disclosed in the app and in ATTRIBUTION.md); live availability | Fallback to the ring map; could be self-hosted if terms allow |
| Not penetration tested; container image unbuilt | Out of scope/time and no Docker locally | Build and scan the image (`docker scout`/`trivy`) before public launch |

## 5. Verification
Hardening tests: 16 in `tests/api/test_hardening.py` (headers on success and error, oversize and streamed bodies, CORS headers on refusals, list/label limits for 5 request shapes, limiter admits N and returns typed 503 for the rest, waiting requests are served when a slot frees, cheap endpoints never queued, serving mode headers/CSP/caching, build stamp) and 5 in `tests/engine/test_cachecap.py`. Full backend suite 388 pass; browser test 25/25 under the production CSP.
