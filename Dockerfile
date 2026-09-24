# The service image: MCP (/mcp) and REST (/api/v1) over a read-only index.
#
# The index is not baked in. The image picks the IndexSource from the environment
# (docs/local-run.md, "Index source"): mount a directory with index.duckdb and
# manifest.json and set BR_ELECTIONS_INDEX_DIR, or set BR_ELECTIONS_INDEX_BUCKET and
# BR_ELECTIONS_INDEX_CACHE_DIR for GcsIndexSource. Only the service dependencies are
# installed: no dev group, no pipeline group (curl_cffi, boto3), no network at request time.
# Telemetry stays off unless BR_ELECTIONS_POSTHOG_API_KEY is set.
#
# Build and run against a local index (compose.yaml does the same):
#   docker build -t br-elections-mcp .
#   docker run --rm -p 8080:8080 -v "$PWD/data/index:/data/index:ro" \
#     -e BR_ELECTIONS_INDEX_DIR=/data/index br-elections-mcp

# Base images pinned by the digest of their multi-arch index (python 3.12.14, uv 0.10.10).
ARG PYTHON_IMAGE=python:3.12-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.10.10@sha256:cbe0a44ba994e327b8fe7ed72beef1aaa7d2c4c795fd406d1dbf328bacb2f1c5

FROM ${UV_IMAGE} AS uv

FROM ${PYTHON_IMAGE} AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app
# Dependencies first, from the lockfile only, so a source change does not reinstall them.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-default-groups --no-install-project
COPY README.md LICENSE ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-default-groups --no-editable

FROM ${PYTHON_IMAGE} AS runtime
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app
WORKDIR /app
COPY --from=build --chown=root:root /app/.venv /app/.venv
COPY --chown=root:root data/elections.yaml /app/data/elections.yaml
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    BR_ELECTIONS_HOST=0.0.0.0 \
    BR_ELECTIONS_ELECTIONS_FILE=/app/data/elections.yaml
USER app
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/healthz', timeout=2)"]
# PORT is the port Cloud Run assigns; exec keeps uvicorn as PID 1 so it receives SIGTERM.
CMD ["sh", "-c", "exec uvicorn --factory br_elections_mcp.app:create_app --host 0.0.0.0 --port \"$PORT\""]
