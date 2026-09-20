# Stage 1: Build virtual environment with uv
FROM python:3.11-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Copy uv binary from official image
COPY --from=ghcr.io/astral-sh/uv:0.6.14 /uv /uvx /bin/

WORKDIR /app

# Copy dependency files for layer caching
COPY pyproject.toml uv.lock ./

# Install dependencies into /app/.venv without dev dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Stage 2: Minimal runtime image
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Create non-root system user for security
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

# Copy installed python virtualenv from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application code and migrations
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY scripts/ ./scripts/

# Create data directory and assign ownership
RUN mkdir -p /app/data && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
