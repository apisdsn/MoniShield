# MoniShield (v2, log & security dashboard): two-stage image (TRD §7.4, docs/06-docker.md).
# Stage 1 (Node) builds the UI; stage 2 (Python) only carries the Python packages, the server code and the build output.
# No Node, node_modules, build tools, .env or logs in the final image.
# Behind a TLS-inspecting proxy: an extra CA certificate can be given as the build secret "ca_bundle"
# (docker-compose.yml: DOCKER_BUILD_CA). Only used while RUN downloads packages; not stored in the image.

# ---------------------------------------------------------------- stage 1: UI (Svelte + Vite)
FROM node:22.22.0-bookworm-slim AS web
WORKDIR /src/web
COPY web/package.json web/package-lock.json ./
RUN --mount=type=secret,id=ca_bundle,required=false \
    if [ -s /run/secrets/ca_bundle ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/ca_bundle; fi; \
    npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# ---------------------------------------------------------------- stage 2: server (FastAPI + DuckDB)
FROM python:3.13.9-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
# dependencies first (cache layer): the list comes from pyproject.toml, including boto3 (S3 import) and kafka-python (logs from Kafka)
COPY pyproject.toml ./
RUN --mount=type=secret,id=ca_bundle,required=false \
    if [ -s /run/secrets/ca_bundle ]; then export PIP_CERT=/run/secrets/ca_bundle; fi; \
    python -c "import tomllib; p = tomllib.load(open('pyproject.toml', 'rb'))['project']; \
print('\n'.join(p['dependencies'] + p['optional-dependencies']['s3'] + p['optional-dependencies']['kafka']))" > /tmp/req.txt \
 && pip install -r /tmp/req.txt && rm /tmp/req.txt
COPY monishield/ monishield/
COPY --from=web /src/web/dist web/dist
# non-root user; volume folders are created here so named volumes inherit their owner
RUN groupadd --system --gid 10001 monishield \
 && useradd --system --uid 10001 --gid monishield --home-dir /app --shell /usr/sbin/nologin monishield \
 && mkdir -p /data /cache /inbox /logs && chown monishield:monishield /data /cache /inbox
USER monishield
ENV S4_BIND=0.0.0.0:8000 S4_LOG_DIR=/logs S4_DATA_DIR=/data S4_CACHE_DIR=/cache S4_INBOX_DIR=/inbox S4_STATE_DIR=/data/state
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.build_opener(urllib.request.ProxyHandler({})).open('http://127.0.0.1:8000/api/health', timeout=4)"]
CMD ["python", "-m", "monishield", "serve"]
