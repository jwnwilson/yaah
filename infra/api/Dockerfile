# Slim API image — serves the FastAPI app only (no node/claude-code, unlike the worker).
FROM python:3.12-slim

RUN pip install --no-cache-dir uv
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY src ./src

RUN useradd -m appuser && chown -R appuser /app
USER appuser

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "--app-dir", "src", \
     "interactors.api.app:create_app", "--factory", \
     "--host", "0.0.0.0", "--port", "8000"]
