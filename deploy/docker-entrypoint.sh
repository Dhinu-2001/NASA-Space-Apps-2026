#!/bin/sh
# Link the persistent /data volume into the application's data directory, make sure the data is there and verified, then start the server.
set -eu

for d in kernels dem_cache results; do
  mkdir -p "/data/$d"
  rm -rf "/app/data/$d"
  ln -s "/data/$d" "/app/data/$d"
done

data_complete() { python scripts/verify_data.py --require-all >/dev/null 2>&1; }

# 1. Fast path: install the prepared data bundle (a few minutes). Used only when /data is not complete.
#    LUNARNAV_DATA_BUNDLE_URL (https) AND LUNARNAV_DATA_BUNDLE_SHA256 must both be set: the archive is checked against that SHA-256
#    after the download, then every file against the bundle's SHA256SUMS, then against this repository's manifests
#    (scripts/verify_data.py). Nothing is used until all of that passes; a failure leaves /data untouched.
if ! data_complete && [ -n "${LUNARNAV_DATA_BUNDLE_URL:-}" ]; then
  if [ -z "${LUNARNAV_DATA_BUNDLE_SHA256:-}" ]; then
    echo "[entrypoint] LUNARNAV_DATA_BUNDLE_URL is set without LUNARNAV_DATA_BUNDLE_SHA256: refusing to install an unpinned bundle" >&2
  else
    echo "[entrypoint] /data is not complete: installing the data bundle from ${LUNARNAV_DATA_BUNDLE_URL}"
    python scripts/provision_data.py --from-bundle "$LUNARNAV_DATA_BUNDLE_URL" --sha256 "$LUNARNAV_DATA_BUNDLE_SHA256" \
      || echo "[entrypoint] bundle installation failed (see above); nothing unverified was used" >&2
  fi
fi

# 2. Fallback: if the bundle was not set, not reachable, or failed verification, rebuild the data directly from the official NASA
#    sources (NAIF kernels + LOLA terrain, each checksum-verified; about 40 minutes the first time, resumable). The bundle is a
#    convenience, never a single point of failure. Set LUNARNAV_NASA_FALLBACK=0 to disable (e.g. on a host without internet).
if ! data_complete && [ "${LUNARNAV_NASA_FALLBACK:-1}" = "1" ]; then
  echo "[entrypoint] /data is still not complete: downloading directly from NASA (python scripts/provision_data.py; about 40 min, resumable)"
  python scripts/provision_data.py \
    || { echo "[entrypoint] NASA download did not complete; exiting so that a restart resumes it (see docs/DEPLOYMENT.md)" >&2; exit 1; }
fi

# Fail fast with a clear message if the kernels or a DEM window are missing/corrupt. A missing DEM window is only a warning
# (the sites it covers are reported as "terrain data insufficient"); set LUNARNAV_REQUIRE_ALL_DATA=1 to make it fatal.
if [ "${LUNARNAV_REQUIRE_ALL_DATA:-0}" = "1" ]; then
  python scripts/verify_data.py --require-all
else
  python scripts/verify_data.py || { echo "Data not ready. Provision /data (docs/DEPLOYMENT.md): python scripts/provision_data.py, or unpack a bundle made with scripts/pack_data.py" >&2; exit 1; }
fi

exec "$@"
