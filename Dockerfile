# MoniShield (v2, dashboard log & keamanan): image dua tahap (TRD §7.4, docs/06-docker.md).
# Tahap 1 (Node) membangun tampilan; tahap 2 (Python) hanya membawa paket Python, kode server, dan hasil build.
# Tidak ada Node, node_modules, alat build, .env, maupun log di image akhir.
# Di balik proxy pemeriksa TLS: sertifikat CA tambahan bisa diberikan sebagai build secret "ca_bundle"
# (docker-compose.yml: DOCKER_BUILD_CA). Hanya dipakai saat RUN mengunduh paket; tidak tersimpan di image.

# ---------------------------------------------------------------- tahap 1: tampilan (Svelte + Vite)
FROM node:22.22.0-bookworm-slim AS web
WORKDIR /src/web
COPY web/package.json web/package-lock.json ./
RUN --mount=type=secret,id=ca_bundle,required=false \
    if [ -s /run/secrets/ca_bundle ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/ca_bundle; fi; \
    npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# ---------------------------------------------------------------- tahap 2: server (FastAPI + DuckDB)
FROM python:3.13.9-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
# dependensi dulu (lapisan cache): daftar diambil dari pyproject.toml, termasuk boto3 (impor S3) dan kafka-python (log dari Kafka)
COPY pyproject.toml ./
RUN --mount=type=secret,id=ca_bundle,required=false \
    if [ -s /run/secrets/ca_bundle ]; then export PIP_CERT=/run/secrets/ca_bundle; fi; \
    python -c "import tomllib; p = tomllib.load(open('pyproject.toml', 'rb'))['project']; \
print('\n'.join(p['dependencies'] + p['optional-dependencies']['s3'] + p['optional-dependencies']['kafka']))" > /tmp/req.txt \
 && pip install -r /tmp/req.txt && rm /tmp/req.txt
COPY monishield/ monishield/
COPY --from=web /src/web/dist web/dist
# pengguna bukan root; folder volume dibuat di sini agar volume bernama mewarisi pemiliknya
RUN groupadd --system --gid 10001 monishield \
 && useradd --system --uid 10001 --gid monishield --home-dir /app --shell /usr/sbin/nologin monishield \
 && mkdir -p /data /cache /inbox /logs && chown monishield:monishield /data /cache /inbox
USER monishield
ENV S4_BIND=0.0.0.0:8000 S4_LOG_DIR=/logs S4_DATA_DIR=/data S4_CACHE_DIR=/cache S4_INBOX_DIR=/inbox S4_STATE_DIR=/data/state
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.build_opener(urllib.request.ProxyHandler({})).open('http://127.0.0.1:8000/api/health', timeout=4)"]
CMD ["python", "-m", "monishield", "serve"]
