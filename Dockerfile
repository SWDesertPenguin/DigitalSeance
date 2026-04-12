FROM python:3.11-alpine

WORKDIR /app

# Install build dependencies for asyncpg and bcrypt
RUN apk add --no-cache gcc musl-dev libffi-dev

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files first (cache layer)
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --no-dev --frozen

# Copy application code
COPY src/ src/
COPY alembic/ alembic/

# Expose MCP port
EXPOSE 8750

# Run migrations then start server
CMD ["sh", "-c", "uv run alembic upgrade head && uv run uvicorn src.mcp_server.app:create_app --host 0.0.0.0 --port 8750 --factory"]
