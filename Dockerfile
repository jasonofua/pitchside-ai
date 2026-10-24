# One image for every Python role (gateway, sim, ingestor, stats, agents, or all of them
# in local mode), with the static web app built in and served by the gateway.

# ---- web: Next.js static export --------------------------------------------------------
FROM node:22-alpine AS web
WORKDIR /web
RUN corepack enable
COPY web/package.json web/pnpm-lock.yaml web/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY web/ ./
ARG NEXT_PUBLIC_API_URL=""
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL} NEXT_TELEMETRY_DISABLED=1
RUN pnpm build

# ---- runtime: Python services ----------------------------------------------------------
FROM python:3.12-slim AS runtime
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /uvx /bin/
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PITCHSIDE_ROOT=/app \
    PITCHSIDE_DATA_DIR=/data
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --all-extras --no-install-project
COPY schemas ./schemas
COPY data/world.json ./data/world.json
COPY data/crests ./data/crests
COPY services ./services
# COPY keeps the build context's file modes; make the app readable by the non-root user
# whatever they were on the machine that ran the build (azd's remote build uploads them as is).
RUN chmod -R a+rX schemas data services
RUN uv sync --frozen --no-dev --all-extras
COPY --from=web /web/out ./web/out
RUN useradd --create-home --uid 10001 pitchside && mkdir -p /data && chown pitchside /data
USER pitchside
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"
CMD ["python", "-m", "runtime.main"]
