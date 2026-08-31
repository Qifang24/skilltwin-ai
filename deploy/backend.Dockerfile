# Production image for the FastAPI + RAG service.
# Build context must be the project root: docker compose build backend
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/backend \
    HF_HOME=/app/data/cache/huggingface \
    SENTENCE_TRANSFORMERS_HOME=/app/data/cache/sentence-transformers

WORKDIR /app

# libgomp is required by common sentence-transformers / numpy builds.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/backend/requirements.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install -r /app/backend/requirements.txt

COPY backend /app/backend
COPY scripts /app/scripts
# Runtime data is mounted at /app/data. Keep versioned bootstrap inputs outside
# that mount so the first container start can reliably copy them into the volume.
COPY data/seed /app/bootstrap-seed
COPY knowledge /app/knowledge
COPY deploy/backend-entrypoint.sh /app/deploy/backend-entrypoint.sh

RUN useradd --create-home --uid 10001 skilltwin \
    && mkdir -p /app/data/chroma /app/data/cache \
    && chmod +x /app/deploy/backend-entrypoint.sh \
    && chown -R skilltwin:skilltwin /app

USER skilltwin
EXPOSE 8000

ENTRYPOINT ["/app/deploy/backend-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
