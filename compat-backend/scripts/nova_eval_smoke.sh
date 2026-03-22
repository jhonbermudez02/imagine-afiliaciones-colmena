#!/usr/bin/env bash
set -euo pipefail

API_BASE="${API_BASE:-http://127.0.0.1:8011/api/v1}"
BASE="${BASE:-temporal}"
LOTE="${LOTE:-1001}"
IDTRAMITE="${IDTRAMITE:-24370}"
SOURCE_PREFIX="${SOURCE_PREFIX:-afiliaciones_lote_00616892}"
OUT="${OUT:-/tmp/nova_eval_report_$(date +%Y%m%d_%H%M%S).md}"

read -r -d '' QUESTIONS << 'QEOF' || true
resumen ejecutivo del lote 1001
faltantes de documentos criticos de la afiliacion
camara de comercio
que documentos tienes de rut
cedula representante legal
dame OCR de camara de comercio
QEOF

{
  echo "# NOVA Smoke Eval"
  echo
  echo "- Fecha: $(date '+%Y-%m-%d %H:%M:%S')"
  echo "- API: ${API_BASE}"
  echo "- Contexto: base=${BASE} lote=${LOTE} idtramite=${IDTRAMITE}"
  echo
} > "$OUT"

while IFS= read -r q; do
  [[ -z "$q" ]] && continue
  RESP="$(curl --max-time 60 -s -X POST "${API_BASE}/nova/chat" \
    -H 'Content-Type: application/json' \
    -d "{\"question\":\"${q}\",\"template\":\"afiliaciones_arl\",\"use_rag\":true,\"top_k\":6,\"base\":\"${BASE}\",\"lote\":\"${LOTE}\",\"idtramite\":\"${IDTRAMITE}\",\"source_prefix\":\"${SOURCE_PREFIX}\"}" || true)"
  ANSWER="$(printf '%s' "$RESP" | jq -r '.answer // "(sin answer)"' 2>/dev/null || echo '(json invalido)')"
  {
    echo "## Pregunta"
    echo
    echo "${q}"
    echo
    echo "## Respuesta"
    echo
    echo '```text'
    printf '%s\n' "$ANSWER"
    echo '```'
    echo
  } >> "$OUT"
done <<< "$QUESTIONS"

echo "$OUT"
