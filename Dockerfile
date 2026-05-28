# ── Builder ──────────────────────────────────────────────────────
FROM python:3.12-slim AS builder
WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY hinge/ ./hinge/
RUN uv sync --frozen --no-dev

# ── Runtime ──────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime
WORKDIR /app

COPY --from=builder /app/.venv ./.venv
COPY --from=builder /app/hinge   ./hinge

ENV PATH="/app/.venv/bin:$PATH" \
    HINGE_STORE_PATH=/store/network.duckdb \
    HINGE_LOG_LEVEL=INFO

ENTRYPOINT ["hinge"]
