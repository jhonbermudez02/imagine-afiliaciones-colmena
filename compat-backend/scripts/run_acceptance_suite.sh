#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND="$ROOT/backend"
DOCS="$ROOT/docs"
BASE_URL="${BASE_URL:-http://localhost:8000/api/v1}"
PYTHON_BIN="${PYTHON_BIN:-$BACKEND/.venv/bin/python3}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="${PYTHON_BIN_FALLBACK:-python3}"
fi

SAMPLE_SOLICITUD_ID="${SAMPLE_SOLICITUD_ID:-1}"
SAMPLE_TRAMITE="${SAMPLE_TRAMITE:-456}"
SAMPLE_USUARIO="${SAMPLE_USUARIO:-IMAGINE}"
SAMPLE_ID_PRESTACION="${SAMPLE_ID_PRESTACION:-1}"
SAMPLE_TIPO_SOLICITUD="${SAMPLE_TIPO_SOLICITUD:-INV}"
SAMPLE_PN="${SAMPLE_PN:-1}"
SAMPLE_AX="${SAMPLE_AX:-0}"
SAMPLE_ID_ESTADO_POST="${SAMPLE_ID_ESTADO_POST:-1}"
SAMPLE_TIPO_GESTION="${SAMPLE_TIPO_GESTION:-1}"
SAMPLE_CATEGORIA="${SAMPLE_CATEGORIA:-1}"

mkdir -p "$DOCS"

echo "[INFO] BASE_URL=$BASE_URL"
echo "[INFO] Ejecutando suite de aceptacion legacy"

"$PYTHON_BIN" "$BACKEND/scripts/smoke_legacy_opc.py" \
  --base-url "$BASE_URL" \
  --mode behavior \
  --sample-solicitud-id "$SAMPLE_SOLICITUD_ID" \
  --sample-tramite "$SAMPLE_TRAMITE" \
  --sample-usuario "$SAMPLE_USUARIO" \
  --sample-id-prestacion "$SAMPLE_ID_PRESTACION" \
  --sample-tipo-solicitud "$SAMPLE_TIPO_SOLICITUD" \
  --sample-pn "$SAMPLE_PN" \
  --sample-ax "$SAMPLE_AX" \
  --sample-id-estado-post "$SAMPLE_ID_ESTADO_POST" \
  --sample-tipo-gestion "$SAMPLE_TIPO_GESTION" \
  --sample-categoria "$SAMPLE_CATEGORIA" \
  --verbose \
  --report-json "$DOCS/smoke_behavior.json" \
  --report-junit "$DOCS/smoke_behavior.xml"

"$PYTHON_BIN" "$BACKEND/scripts/smoke_legacy_opc.py" \
  --base-url "$BASE_URL" \
  --mode real-ready \
  --sample-solicitud-id "$SAMPLE_SOLICITUD_ID" \
  --sample-tramite "$SAMPLE_TRAMITE" \
  --sample-usuario "$SAMPLE_USUARIO" \
  --sample-id-prestacion "$SAMPLE_ID_PRESTACION" \
  --sample-tipo-solicitud "$SAMPLE_TIPO_SOLICITUD" \
  --verbose \
  --report-json "$DOCS/smoke_real_ready.json" \
  --report-junit "$DOCS/smoke_real_ready.xml"

"$PYTHON_BIN" "$BACKEND/scripts/smoke_legacy_opc.py" \
  --base-url "$BASE_URL" \
  --mode workbench \
  --sample-solicitud-id "$SAMPLE_SOLICITUD_ID" \
  --sample-tramite "$SAMPLE_TRAMITE" \
  --sample-usuario "$SAMPLE_USUARIO" \
  --verbose \
  --report-json "$DOCS/smoke_workbench.json" \
  --report-junit "$DOCS/smoke_workbench.xml"

echo "[OK] Suite finalizada."
echo "[OK] Reportes:"
echo "  - $DOCS/smoke_behavior.json"
echo "  - $DOCS/smoke_behavior.xml"
echo "  - $DOCS/smoke_real_ready.json"
echo "  - $DOCS/smoke_real_ready.xml"
echo "  - $DOCS/smoke_workbench.json"
echo "  - $DOCS/smoke_workbench.xml"
