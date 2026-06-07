# Bridge OS backend — production image for AWS App Runner
#
# Multi-stage build keeps the runtime image small. The wheel cache layer
# lets `pip install -e .` from pyproject.toml without re-downloading every
# dependency on every build.

FROM public.ecr.aws/docker/library/python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System deps needed at build time for psycopg, lightgbm, scikit-learn
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY app ./app

RUN pip install --upgrade pip setuptools wheel \
    && pip install .


# ---- Runtime stage --------------------------------------------------------

FROM public.ecr.aws/docker/library/python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BRIDGE_OS_USE_SECRETS_MANAGER=1 \
    APP_HOME=/app

WORKDIR ${APP_HOME}

# Runtime libs only (no compilers)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages + app code from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app/app ./app
COPY pyproject.toml ./

# Drop privileges
RUN useradd -m -u 1000 bridgeos && chown -R bridgeos:bridgeos /app
USER bridgeos

EXPOSE 8000

# App Runner sends GET / for health probes
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/system/health/full', timeout=5)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
