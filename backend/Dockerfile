ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.11.29
ARG PYTHON_IMAGE=python:3.12-slim

FROM ${UV_IMAGE} AS uv
FROM ${PYTHON_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY --from=uv /uv /uvx /bin/
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

RUN useradd --create-home --uid 10001 appuser
COPY --chown=appuser:appuser . .
USER appuser
ENV PATH="/app/.venv/bin:$PATH"

CMD ["uvicorn", "config.asgi:application", "--host", "0.0.0.0", "--port", "8000"]
