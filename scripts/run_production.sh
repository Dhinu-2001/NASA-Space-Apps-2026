#!/bin/sh
# Production-mode run WITHOUT Docker: builds the web UI if needed, verifies the data, serves UI + API on one port.
# Usage: LUNARNAV_ENV=production sh scripts/run_production.sh [port]
set -eu
cd "$(dirname "$0")/.."
PORT="${1:-8000}"
if [ ! -f web/dist/index.html ]; then
  (cd web && npm ci && npm run build)
fi
python scripts/verify_data.py || { echo "Data not ready: see docs/DEPLOYMENT.md" >&2; exit 1; }
export LUNARNAV_ENV="${LUNARNAV_ENV:-production}" LUNARNAV_LOG_JSON="${LUNARNAV_LOG_JSON:-true}" LUNARNAV_MAX_HEAVY_REQUESTS="${LUNARNAV_MAX_HEAVY_REQUESTS:-2}"
exec python -m uvicorn lunarnav_api.serve:app --host 0.0.0.0 --port "$PORT" --proxy-headers
