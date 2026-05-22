# syntax=docker/dockerfile:1.7
# custom-predictor — periodic Prometheus query → ai-gateway → JSON file + /metrics

FROM python:3.12-slim AS base
RUN groupadd -r app --gid 10101 \
 && useradd -r -u 10101 -g app -m -d /app -s /bin/bash app
WORKDIR /app
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && update-ca-certificates

FROM base AS builder
COPY pyproject.toml /app/pyproject.toml
RUN pip install --no-cache-dir --target=/app/site-packages \
      "fastapi==0.136.1" \
      "uvicorn[standard]==0.32.0" \
      "httpx[http2]==0.27.2" \
      "apscheduler==3.10.4" \
      "prometheus-client==0.21.0" \
      "structlog==24.4.0" \
      "pydantic==2.9.2" \
      "pydantic-settings==2.6.0"

FROM base AS final
COPY --from=builder /app/site-packages /app/site-packages
COPY app /app/app
ENV PYTHONPATH=/app:/app/site-packages \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
USER app
EXPOSE 8080
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
