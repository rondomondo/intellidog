FROM python:3.12-slim

LABEL org.opencontainers.image.title="intellidog" \
      org.opencontainers.image.description="Intelligent Observability & Event Watchdog" \
      org.opencontainers.image.version="0.1.0"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY src/ ./src/
COPY rules/ ./rules/
COPY pyproject.toml .

RUN pip install -e . --no-deps

RUN useradd -m -u 1001 intellidog && \
    mkdir -p /app/data && \
    chown -R intellidog:intellidog /app

USER intellidog

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
