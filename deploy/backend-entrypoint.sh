#!/bin/sh
set -eu

CORE_MARKER=/app/data/.core-bootstrap-complete
RAG_MARKER=/app/data/.rag-bootstrap-complete
BOOTSTRAP_SEED_DIR=/app/bootstrap-seed

# The scripts are idempotent. Markers prevent model loading and indexing on every restart,
# while keeping the first deployment reproducible from source-controlled seed data.
if [ "${BOOTSTRAP_ON_START:-true}" = "true" ] && [ ! -f "$CORE_MARKER" ]; then
  echo "[bootstrap] Creating tables and loading versioned core seed data..."
  # /app/data is a named volume in Docker Compose and therefore hides image
  # layers below it. Copy immutable seed inputs into the fresh volume before
  # scripts resolve their normal /app/data/seed path.
  mkdir -p /app/data/seed
  cp -R "$BOOTSTRAP_SEED_DIR"/. /app/data/seed/
  python /app/scripts/reset_db.py
  python /app/scripts/seed_skills.py
  python /app/scripts/seed_curriculum.py
  touch "$CORE_MARKER"
fi

if [ "${BUILD_RAG_INDEX_ON_START:-true}" = "true" ] && [ ! -f "$RAG_MARKER" ]; then
  echo "[bootstrap] Ingesting knowledge sources and building the RAG index..."
  python /app/scripts/ingest_knowledge.py
  python /app/scripts/build_index.py
  touch "$RAG_MARKER"
fi

exec "$@"
