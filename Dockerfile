# ==============================================================================
# OmniBrain - Backend Production Dockerfile (Module 7)
# Multi-stage build: a `builder` stage compiles/installs Python dependencies
# into an isolated venv; the final stage copies only that venv plus the
# application source, and runs as a non-root user. This keeps the shipped
# image free of build toolchains and keeps rebuilds fast (the dependency
# layer only invalidates when requirements.txt changes).
# ==============================================================================

FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

# build-essential is needed only to compile wheels for some backend deps
# (e.g. faiss-cpu, pymupdf); it is discarded once the final image is built.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt


FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/workspace

WORKDIR /workspace

# curl is required for the container HEALTHCHECK and docker-compose's
# service-level healthcheck probes.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 omnibrain

COPY --from=builder /opt/venv /opt/venv

COPY backend/ backend/

RUN mkdir -p logs storage/uploads storage/assets storage/faiss_index \
    && chown -R omnibrain:omnibrain /workspace

USER omnibrain

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
