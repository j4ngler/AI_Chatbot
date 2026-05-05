#!/usr/bin/env bash
# VPS / Linux: chạy API không Docker. Build frontend: (cd enterprise_web && npm ci && npm run build)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p "$ROOT/data"
export DATABASE_URL="${DATABASE_URL:-sqlite:///${ROOT}/data/erp_demo_local.db}"
export JWT_SECRET="${JWT_SECRET:-change-me-on-vps}"
HOST_BIND="${HOST_BIND:-0.0.0.0}"
PORT="${PORT:-8000}"
echo "DATABASE_URL=$DATABASE_URL"
exec python -m uvicorn api.main:app --host "$HOST_BIND" --port "$PORT"
