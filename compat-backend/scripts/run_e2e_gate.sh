#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND="$ROOT/backend"
DOCS="$ROOT/docs"
BASE_URL="${BASE_URL:-http://localhost:8000/api/v1}"
DATABASE_URL="${DATABASE_URL:-}"
PYTHON_BIN="${PYTHON_BIN:-$BACKEND/.venv/bin/python3}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="${PYTHON_BIN_FALLBACK:-python3}"
fi

mkdir -p "$DOCS"

echo "[INFO] Ejecutando suite de aceptación base"
"$BACKEND/scripts/run_acceptance_suite.sh"

echo "[INFO] Ejecutando smoke negativo"
"$PYTHON_BIN" "$BACKEND/scripts/smoke_negative.py" \
  --base-url "$BASE_URL" \
  --verbose \
  --report-json "$DOCS/smoke_negative.json" \
  --report-junit "$DOCS/smoke_negative.xml"

echo "[INFO] Ejecutando smoke NOVA regression"
"$PYTHON_BIN" "$BACKEND/scripts/smoke_nova_regression.py" \
  --base-url "$BASE_URL" \
  --verbose \
  --report-json "$DOCS/smoke_nova_regression.json" \
  --report-junit "$DOCS/smoke_nova_regression.xml" \
  --report-md "$DOCS/smoke_nova_regression.md"

echo "[INFO] Ejecutando stress básico"
"$PYTHON_BIN" "$BACKEND/scripts/stress_basic.py" \
  --base-url "$BASE_URL" \
  --total-requests 150 \
  --concurrency 10 \
  --verbose \
  --report-json "$DOCS/stress_basic.json"

if [[ -n "$DATABASE_URL" ]]; then
  echo "[INFO] Ejecutando consistencia DB"
  "$PYTHON_BIN" "$BACKEND/scripts/check_db_consistency.py" \
    --base-url "$BASE_URL" \
    --database-url "$DATABASE_URL" \
    --sample-usuario "${SAMPLE_USUARIO:-IMAGINE}" \
    --sample-tramite "${SAMPLE_TRAMITE:-456}" \
    --sample-id-ben "${SAMPLE_ID_BEN:-1}" \
    --sample-sworigen "${SAMPLE_SWORIGEN:-fiducia}" \
    --run-ops \
    --verbose \
    --report-json "$DOCS/db_consistency.json"
else
  echo "[WARN] DATABASE_URL no definido, se omite check_db_consistency.py"
fi

echo "[INFO] Regenerando matriz de paridad formularios"
"$PYTHON_BIN" "$BACKEND/scripts/generate_form_parity_matrix.py" \
  --legacy-root "$ROOT/../_analysis/flujos/flujos" \
  --react-file "$ROOT/frontend/src/features/notificaciones/NotificacionesPage.tsx" \
  --react-file "$ROOT/frontend/src/features/funerarios/FunerariosPage.tsx" \
  --out-json "$DOCS/matriz_formularios_legacy_2026-02-25.json" \
  --out-md "$DOCS/matriz_formularios_legacy_2026-02-25.md"

echo "[INFO] Consolidando reportes E2E"
"$PYTHON_BIN" "$BACKEND/scripts/consolidate_e2e_reports.py" \
  --docs-dir "$DOCS"

echo "[OK] E2E gate finalizado"
