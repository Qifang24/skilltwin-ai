#!/bin/sh
set -eu

CORE_MARKER=/app/data/.core-bootstrap-complete
RAG_MARKER=/app/data/.rag-bootstrap-complete
BOOTSTRAP_SEED_DIR=/app/bootstrap-seed

# Schema upgrades must run on every release. The bootstrap marker only guards
# optional seed/index work; an existing persistent volume may already have the
# marker while still needing a newer additive migration.
echo "[bootstrap] Applying database migrations..."
python -m alembic upgrade head

# The scripts are idempotent. Markers prevent model loading and indexing on every restart,
# while keeping the first deployment reproducible from source-controlled seed data.
if [ "${BOOTSTRAP_ON_START:-true}" = "true" ] && [ ! -f "$CORE_MARKER" ]; then
  echo "[bootstrap] Loading versioned core seed data..."
  # /app/data is a named volume in Docker Compose and therefore hides image
  # layers below it. Copy immutable seed inputs into the fresh volume before
  # scripts resolve their normal /app/data/seed path.
  mkdir -p /app/data/seed
  cp -R "$BOOTSTRAP_SEED_DIR"/. /app/data/seed/
  python /app/scripts/seed_skills.py
  # Curriculum seeds require source knowledge chunks. Do not fail a clean
  # deployment when the optional knowledge volume is intentionally empty.
  if [ -n "$(find /app/knowledge -type f 2>/dev/null | head -n 1)" ]; then
    python /app/scripts/ingest_knowledge.py
    python /app/scripts/seed_curriculum.py
  else
    echo "[bootstrap] No knowledge documents found; skipping curriculum seed."
  fi
  touch "$CORE_MARKER"
fi

if [ "${BUILD_RAG_INDEX_ON_START:-true}" = "true" ] && [ ! -f "$RAG_MARKER" ]; then
  echo "[bootstrap] Ingesting knowledge sources and building the RAG index..."
  if [ -n "$(find /app/knowledge -type f 2>/dev/null | head -n 1)" ]; then
    python /app/scripts/ingest_knowledge.py
    python /app/scripts/build_index.py
  else
    echo "[bootstrap] No knowledge documents found; skipping RAG index."
  fi
  touch "$RAG_MARKER"
fi

exec "$@"
