# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS base
RUN groupadd -r app --gid 10101 \
 && useradd -r -u 10101 -g app -m -d /app -s /bin/bash app
WORKDIR /app
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates \
 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir prometheus-client==0.21.0 httpx==0.27.2 structlog==24.4.0
COPY exporter.py /app/exporter.py
USER app
EXPOSE 9200
CMD ["python", "/app/exporter.py"]
