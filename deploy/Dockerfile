# Hawiya AI — service image.
# Phase 1 production-shape: API + PassportEye + Tesseract.
#
# Tesseract is a system binary (~50 MB with English language data). It's
# installed in the runtime stage. PassportEye and its scientific deps
# (numpy, scikit-image, scipy, Pillow) are built as wheels in the builder
# stage so the runtime install is fully offline and air-gap friendly.

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        ca-certificates \
        libpq5 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# --- builder --------------------------------------------------------------
FROM base AS builder

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        # SciPy / scikit-image build deps
        gfortran \
        libopenblas-dev \
        liblapack-dev \
 && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --upgrade pip \
 && pip wheel --wheel-dir /wheels ".[ocr]"

# --- runtime --------------------------------------------------------------
FROM base AS runtime

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        # Tesseract + English language data for PassportEye.
        tesseract-ocr \
        tesseract-ocr-eng \
        libtesseract5 \
        # Runtime libs for SciPy / scikit-image wheels.
        libgomp1 \
        libopenblas0 \
 && rm -rf /var/lib/apt/lists/*

RUN groupadd --system hawiya && useradd --system --gid hawiya --home /app hawiya

COPY --from=builder /wheels /wheels
RUN pip install --no-index --find-links=/wheels "hawiya-ai[ocr]" \
 && rm -rf /wheels

COPY alembic.ini ./
COPY src ./src
COPY scripts ./scripts

USER hawiya

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://localhost:8000/v1/health', timeout=2).status == 200 else 1)"

CMD ["uvicorn", "hawiya.main:app", "--host", "0.0.0.0", "--port", "8000"]
