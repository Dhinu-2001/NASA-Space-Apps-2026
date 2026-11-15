#!/bin/sh
# Link the persistent /data volume into the application's data directory, check the data, then start the server.
set -eu

for d in kernels dem_cache results; do
  mkdir -p "/data/$d"
  rm -rf "/app/data/$d"
  ln -s "/data/$d" "/app/data/$d"
done

# Fail fast with a clear message if the kernels or a DEM window are missing/corrupt. A missing DEM window is only a warning
# (the sites it covers are reported as "terrain data insufficient"); set LUNARNAV_REQUIRE_ALL_DATA=1 to make it fatal.
if [ "${LUNARNAV_REQUIRE_ALL_DATA:-0}" = "1" ]; then
  python scripts/verify_data.py --require-all
else
  python scripts/verify_data.py || { echo "Data not ready. Provision /data (docs/DEPLOYMENT.md): python scripts/provision_data.py, or unpack a bundle made with scripts/pack_data.py" >&2; exit 1; }
fi

exec "$@"
