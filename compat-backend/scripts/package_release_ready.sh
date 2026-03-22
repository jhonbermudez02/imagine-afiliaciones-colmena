#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/escobar/Downloads/sst/migracion_py_react"
DOCS="$ROOT/docs"
STAMP="${1:-20260225_143804}"
OUT="${2:-$DOCS/release_ready_${STAMP}.zip}"

files=(
  "$DOCS/acta_cierre_clone_100_2026-02-25.md"
  "$DOCS/handover_produccion_2026-02-25.md"
  "$DOCS/checklist_go_live_2026-02-25.md"
  "$DOCS/plan_rollback_2026-02-25.md"
  "$DOCS/plan_hypercare_2026-02-25.md"
  "$DOCS/runbook_e2e_react_2026-02-25.md"
  "$DOCS/real_mode_checklist_2026-02-24.md"
  "$DOCS/matriz_formularios_legacy_2026-02-25.md"
  "$DOCS/matriz_formularios_legacy_2026-02-25.json"
  "$DOCS/estado_formularios_final_2026-02-25.md"
  "$DOCS/estado_hacia_100_absoluto_2026-03-03.md"
  "$DOCS/plantilla_uat_formularios_2026-02-25.csv"
  "$DOCS/guia_uat_formularios_2026-02-25.md"
  "$DOCS/smoke_behavior.json"
  "$DOCS/smoke_behavior.xml"
  "$DOCS/smoke_real_ready.json"
  "$DOCS/smoke_real_ready.xml"
  "$DOCS/smoke_workbench.json"
  "$DOCS/smoke_workbench.xml"
  "$DOCS/smoke_negative.json"
  "$DOCS/smoke_negative.xml"
  "$DOCS/stress_basic.json"
  "$DOCS/db_consistency.json"
  "$DOCS/e2e_consolidado_${STAMP}.md"
  "$DOCS/e2e_consolidado_${STAMP}.json"
)

tmp_list="$(mktemp)"
for f in "${files[@]}"; do
  if [[ -f "$f" ]]; then
    echo "$f" >> "$tmp_list"
  fi
done

if [[ ! -s "$tmp_list" ]]; then
  echo "[ERROR] No se encontraron evidencias para release-ready."
  rm -f "$tmp_list"
  exit 1
fi

zip -j "$OUT" $(cat "$tmp_list") >/dev/null
rm -f "$tmp_list"
echo "[OK] Release-ready: $OUT"
