#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/escobar/Downloads/sst/migracion_py_react"
BACKEND="$ROOT/backend"
REPORT="$ROOT/docs/real_ready_report_2026-02-24.json"
BASE_URL="${BASE_URL:-http://localhost:8000/api/v1}"

if [[ -f "$BACKEND/.env.real" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$BACKEND/.env.real"
  set +a
else
  echo "[WARN] No existe $BACKEND/.env.real (usa .env.real.template)."
fi

echo "[INFO] Ejecutando smoke real-ready en $BASE_URL"
python3 "$BACKEND/scripts/smoke_legacy_opc.py" \
  --mode real-ready \
  --base-url "$BASE_URL" \
  --timeout 12 \
  --verbose \
  --report-json "$REPORT"

echo "[INFO] Reporte generado en: $REPORT"
