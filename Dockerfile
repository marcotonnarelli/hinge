# ── Builder ──────────────────────────────────────────────────────
FROM python:3.12-slim AS builder
WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev || uv sync --no-dev

COPY hinge/ ./hinge/

# ── Runtime ──────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime
WORKDIR /app

COPY --from=builder /app/.venv ./.venv
COPY --from=builder /app/hinge   ./hinge

ENV PATH="/app/.venv/bin:$PATH" \
    HINGE_STORE_PATH=/store/network.duckdb \
    HINGE_LOG_LEVEL=INFO

ENTRYPOINT ["hinge"]
