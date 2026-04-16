#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend-nova"
DOCS="$ROOT/docs"
BASE_URL="${BASE_URL:-http://localhost:8010/api/v1}"
DATABASE_URL="${DATABASE_URL:-}"
FRONT_BASE="${FRONT_BASE:-http://localhost:8080}"
RUN_UI_RPA="${RUN_UI_RPA:-1}"
PYTHON_BIN="${PYTHON_BIN:-$BACKEND/.venv/bin/python3}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="${PYTHON_BIN_FALLBACK:-python3}"
fi

# Fuerza modo seguro para evitar consumo real de integraciones.
export SAP_CONTABILIDAD_MODE="${SAP_CONTABILIDAD_MODE:-stub_success}"
export SYNC_BENEFICIARIOS_MODE="${SYNC_BENEFICIARIOS_MODE:-stub_empty}"
export PENSION_ACTUALIZA_MODE="${PENSION_ACTUALIZA_MODE:-local}"
export TERCERO_EXISTE_MODE="${TERCERO_EXISTE_MODE:-local_all}"
export TERCERO_CREAR_MODE="${TERCERO_CREAR_MODE:-stub_success}"
export NOT_CONSULTA_AFIL_MODE="${NOT_CONSULTA_AFIL_MODE:-stub}"

mkdir -p "$DOCS"

echo "[INFO] BASE_URL=$BASE_URL"
echo "[INFO] Ejecutando validación pre-real (sin integraciones reales)"

"$PYTHON_BIN" "$BACKEND/scripts/smoke_legacy_opc.py" \
  --base-url "$BASE_URL" \
  --mode behavior \
  --sample-solicitud-id "${SAMPLE_SOLICITUD_ID:-1}" \
  --sample-tramite "${SAMPLE_TRAMITE:-456}" \
  --sample-usuario "${SAMPLE_USUARIO:-IMAGINE}" \
  --sample-id-prestacion "${SAMPLE_ID_PRESTACION:-1}" \
  --sample-tipo-solicitud "${SAMPLE_TIPO_SOLICITUD:-INV}" \
  --sample-pn "${SAMPLE_PN:-1}" \
  --sample-ax "${SAMPLE_AX:-0}" \
  --sample-id-estado-post "${SAMPLE_ID_ESTADO_POST:-1}" \
  --sample-tipo-gestion "${SAMPLE_TIPO_GESTION:-1}" \
  --sample-categoria "${SAMPLE_CATEGORIA:-1}" \
  --verbose \
  --report-json "$DOCS/smoke_behavior.json" \
  --report-junit "$DOCS/smoke_behavior.xml"

"$PYTHON_BIN" "$BACKEND/scripts/smoke_legacy_opc.py" \
  --base-url "$BASE_URL" \
  --mode workbench \
  --sample-solicitud-id "${SAMPLE_SOLICITUD_ID:-1}" \
  --sample-tramite "${SAMPLE_TRAMITE:-456}" \
  --sample-usuario "${SAMPLE_USUARIO:-IMAGINE}" \
  --verbose \
  --report-json "$DOCS/smoke_workbench.json" \
  --report-junit "$DOCS/smoke_workbench.xml"

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

"$PYTHON_BIN" "$BACKEND/scripts/stress_basic.py" \
  --base-url "$BASE_URL" \
  --total-requests "${STRESS_TOTAL_REQUESTS:-150}" \
  --concurrency "${STRESS_CONCURRENCY:-10}" \
  --verbose \
  --report-json "$DOCS/stress_basic.json"

if [[ -n "$DATABASE_URL" ]]; then
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

"$PYTHON_BIN" "$BACKEND/scripts/generate_form_parity_matrix.py" \
  --legacy-root "$ROOT/../_analysis/flujos/flujos" \
  --react-file "$ROOT/frontend/src/features/notificaciones/NotificacionesPage.tsx" \
  --react-file "$ROOT/frontend/src/features/funerarios/FunerariosPage.tsx"

"$PYTHON_BIN" "$BACKEND/scripts/consolidate_e2e_reports.py" \
  --docs-dir "$DOCS"

if [[ "$RUN_UI_RPA" == "1" ]]; then
  echo "[INFO] Ejecutando RPA UI (Playwright)"
  (
    cd "$FRONTEND"
    PLAYWRIGHT_BASE_URL="$FRONT_BASE" npm run e2e:rpa
  )

  TS="$(date +%Y%m%d_%H%M%S)"
  if [[ -d "$FRONTEND/playwright-report" ]]; then
    DEST="$DOCS/playwright_report_$TS"
    cp -R "$FRONTEND/playwright-report" "$DEST"
    echo "[INFO] Reporte Playwright: $DEST"
  fi
else
  echo "[WARN] RUN_UI_RPA=0, se omite Playwright UI RPA"
fi

echo "[OK] Validación pre-real completada."
