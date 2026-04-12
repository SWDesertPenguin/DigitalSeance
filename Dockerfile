FROM python:3.11-alpine

WORKDIR /app

RUN apk add --no-cache gcc musl-dev libffi-dev

COPY pyproject.toml ./
RUN pip install --no-cache-dir .

COPY src/ src/
COPY alembic/ alembic/

EXPOSE 8750

CMD ["sh", "-c", "python -m alembic upgrade head && uvicorn src.mcp_server.app:create_app --host 0.0.0.0 --port 8750 --factory"]
