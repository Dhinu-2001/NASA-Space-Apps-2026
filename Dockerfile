# Lunar Landing Site Navigator: one image serving the built web UI and the API (lunarnav_api.serve).
# The heavy scientific data (SPICE kernels, DEM windows, ~290 MB) is NOT baked in: mount it at /data (see docs/DEPLOYMENT.md).
# Built and run on Docker 29.9.3 (15 Nov 2026); see docs/stage11/DOCKER_VERIFICATION.md.

# ---- 1. build the web UI
FROM node:24-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# ---- 2. runtime
FROM python:3.12-slim AS app
ARG GIT_COMMIT=unknown
ENV LUNARNAV_GIT_COMMIT=${GIT_COMMIT} \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    LUNARNAV_ENV=production \
    LUNARNAV_LOG_JSON=true \
    LUNARNAV_DATA_DIR=/app/data \
    LUNARNAV_WEB_DIST=/app/web/dist \
    LUNARNAV_MAX_HEAVY_REQUESTS=2
WORKDIR /app

# rasterio's wheel links libexpat, which the slim base image does not include (found by the first container run)
# zlib1g is upgraded to pick up Debian's fixed version (two HIGH CVEs flagged by docker scout in the base image's older build)
RUN apt-get update \
 && apt-get install -y --no-install-recommends libexpat1 \
 && apt-get install -y --only-upgrade zlib1g \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.runtime.txt ./
RUN pip install -r requirements.runtime.txt

COPY pyproject.toml README.md ./
COPY engine ./engine
COPY api ./api
RUN pip install --no-deps .

# tracked data (site catalogue, manifests, validation fixtures) ships in the image; heavy data comes from the /data volume
COPY data/catalogue ./data/catalogue
COPY data/manifests ./data/manifests
COPY data/validation ./data/validation
COPY scripts ./scripts
COPY docs/openapi.json ./docs/openapi.json
COPY --from=web /web/dist ./web/dist
COPY deploy/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

# The data folders are links into the /data volume, made here (not only in the entrypoint) so that ANY command run in the image,
# including `--entrypoint python scripts/provision_data.py`, writes into the volume and not into the container's throwaway layer.
RUN chmod +x /usr/local/bin/docker-entrypoint.sh \
 && useradd --system --uid 10001 --home /app lunarnav \
 && mkdir -p /data/kernels /data/dem_cache /data/results \
 && for d in kernels dem_cache results; do rm -rf "/app/data/$d"; ln -s "/data/$d" "/app/data/$d"; done \
 && chown -R lunarnav /app /data
USER lunarnav

EXPOSE 8000
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "lunarnav_api.serve:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
