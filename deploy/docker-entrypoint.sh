#!/bin/sh
# Link the persistent /data volume into the application's data directory, check the data, then start the server.
set -eu

for d in kernels dem_cache results; do
  mkdir -p "/data/$d"
  rm -rf "/app/data/$d"
  ln -s "/data/$d" "/app/data/$d"
done

# Optional automatic provisioning from a prepared data bundle (a few minutes instead of 30-60 minutes of NASA downloads).
# Set LUNARNAV_DATA_BUNDLE_URL (https) and, to pin the archive, LUNARNAV_DATA_BUNDLE_SHA256. Used only when /data is not ready;
# the bundle is verified (archive digest, SHA256SUMS, manifests) before anything is used. Without the variable nothing is downloaded.
if [ -n "${LUNARNAV_DATA_BUNDLE_URL:-}" ] && ! python scripts/verify_data.py >/dev/null 2>&1; then
  echo "[entrypoint] /data is not ready: installing the data bundle from ${LUNARNAV_DATA_BUNDLE_URL}"
  python scripts/provision_data.py --from-bundle "$LUNARNAV_DATA_BUNDLE_URL" ${LUNARNAV_DATA_BUNDLE_SHA256:+--sha256 "$LUNARNAV_DATA_BUNDLE_SHA256"}     || { echo "[entrypoint] bundle installation failed (see above); nothing unverified was used" >&2; exit 1; }
fi

# Fail fast with a clear message if the kernels or a DEM window are missing/corrupt. A missing DEM window is only a warning
# (the sites it covers are reported as "terrain data insufficient"); set LUNARNAV_REQUIRE_ALL_DATA=1 to make it fatal.
if [ "${LUNARNAV_REQUIRE_ALL_DATA:-0}" = "1" ]; then
  python scripts/verify_data.py --require-all
else
  python scripts/verify_data.py || { echo "Data not ready. Provision /data (docs/DEPLOYMENT.md): python scripts/provision_data.py, or unpack a bundle made with scripts/pack_data.py" >&2; exit 1; }
fi

exec "$@"
