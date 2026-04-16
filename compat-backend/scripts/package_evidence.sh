#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DOCS="$ROOT/docs"
OUT="${1:-$DOCS/evidencias_clone_100_2026-02-25.zip}"

files=(
  "$DOCS/acta_cierre_clone_100_2026-02-25.md"
  "$DOCS/e2e_consolidado_2026-02-25.md"
  "$DOCS/e2e_consolidado_2026-02-25.json"
  "$DOCS/matriz_formularios_legacy_2026-02-25.md"
  "$DOCS/matriz_formularios_legacy_2026-02-25.json"
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
  "$DOCS/runbook_e2e_react_2026-02-25.md"
)

tmp_list="$(mktemp)"
for f in "${files[@]}"; do
  if [[ -f "$f" ]]; then
    echo "$f" >> "$tmp_list"
  fi
done

if [[ ! -s "$tmp_list" ]]; then
  echo "[ERROR] No se encontraron archivos de evidencia para empaquetar."
  rm -f "$tmp_list"
  exit 1
fi

zip -j "$OUT" $(cat "$tmp_list") >/dev/null
rm -f "$tmp_list"

echo "[OK] Evidencias empaquetadas: $OUT"
