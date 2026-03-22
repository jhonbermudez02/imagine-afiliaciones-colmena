#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/escobar/Downloads/sst/migracion_py_react"
DOCS="$ROOT/docs"
OUT="${1:-$DOCS/handover_produccion_2026-02-25.zip}"

files=(
  "$DOCS/acta_cierre_clone_100_2026-02-25.md"
  "$DOCS/handover_produccion_2026-02-25.md"
  "$DOCS/checklist_go_live_2026-02-25.md"
  "$DOCS/plan_rollback_2026-02-25.md"
  "$DOCS/plan_hypercare_2026-02-25.md"
  "$DOCS/e2e_consolidado_2026-02-25.md"
  "$DOCS/e2e_consolidado_2026-02-25.json"
  "$DOCS/matriz_formularios_legacy_2026-02-25.md"
  "$DOCS/matriz_formularios_legacy_2026-02-25.json"
  "$DOCS/runbook_e2e_react_2026-02-25.md"
  "$DOCS/real_mode_checklist_2026-02-24.md"
)

tmp_list="$(mktemp)"
for f in "${files[@]}"; do
  if [[ -f "$f" ]]; then
    echo "$f" >> "$tmp_list"
  fi
done

if [[ ! -s "$tmp_list" ]]; then
  echo "[ERROR] No se encontraron archivos para empaquetar handover."
  rm -f "$tmp_list"
  exit 1
fi

zip -j "$OUT" $(cat "$tmp_list") >/dev/null
rm -f "$tmp_list"

echo "[OK] Handover empaquetado: $OUT"

