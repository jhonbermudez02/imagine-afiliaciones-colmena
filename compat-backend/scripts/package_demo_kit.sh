#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DOCS="$ROOT/docs"
CAPTURAS="$DOCS/demo_capturas_2026-02-25"
OUT="${1:-$DOCS/demo_kit_2026-02-25.zip}"

mkdir -p "$CAPTURAS"

files=(
  "$DOCS/demo_visual_runbook_2026-02-25.md"
  "$DOCS/e2e_consolidado_20260225_143804.md"
  "$DOCS/acta_cierre_clone_100_2026-02-25.md"
  "$DOCS/handover_produccion_2026-02-25.md"
  "$DOCS/mensaje_comite_salida_2026-02-25.md"
)

tmp_list="$(mktemp)"
for f in "${files[@]}"; do
  if [[ -f "$f" ]]; then
    echo "$f" >> "$tmp_list"
  fi
done

find "$CAPTURAS" -maxdepth 1 -type f \( -name "*.png" -o -name "*.jpg" -o -name "*.jpeg" \) -print >> "$tmp_list"

if [[ ! -s "$tmp_list" ]]; then
  echo "[ERROR] No hay artefactos para demo kit."
  rm -f "$tmp_list"
  exit 1
fi

zip -j "$OUT" $(cat "$tmp_list") >/dev/null
rm -f "$tmp_list"
echo "[OK] Demo kit: $OUT"
