#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "frontend-nova" / "index.html"
MAIN = ROOT / "frontend-nova" / "main.js"
BACKEND = ROOT / "backend" / "app" / "cases.py"
CATALOGS = ROOT / "data" / "evals" / "afilega_mdb_value_catalogs.json"

LEGACY_REQUIRED = {
    "empleador_tipo_documento",
    "razon_social",
    "nit",
    "nit_dv",
    "codigo_actividad_economica",
    "clase_riesgo_empresa",
    "rep_legal_nombre_completo",
    "rep_legal_tipo_documento",
    "rep_legal_numero_documento",
    "tipo_documento_afiliado",
    "documento_afiliado",
    "primer_apellido",
    "primer_nombre",
    "fecha_nacimiento",
    "eps",
    "afp",
    "ibc",
    "tipo_cotizante",
    "subtipo_cotizante",
    "sede_nombre",
    "sede_codigo",
    "sede_direccion",
    "sede_departamento",
    "sede_municipio",
    "sede_codigo_actividad",
    "sede_clase_riesgo",
    "sedes_adicionales",
    "tipo_novedad",
    "novedad_estado",
    "novedad_autoliquidacion",
    "novedad_origen",
}


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def main() -> int:
    html = read(HTML)
    main_js = read(MAIN)
    backend = read(BACKEND)
    keys = set(re.findall(r'data-dig-key="([^"]+)"', html))
    report: dict[str, object] = {
        "digitacion_fields": len(keys),
        "missing_required_in_ui": sorted(LEGACY_REQUIRED - keys),
        "ui_keys_missing_backend_mentions": sorted(key for key in keys if f'"{key}"' not in backend and f"'{key}'" not in backend),
        "ui_keys_missing_frontend_validation_mentions": sorted(key for key in keys if f"'{key}'" not in main_js and f'"{key}"' not in main_js),
    }
    catalogs_payload = json.loads(CATALOGS.read_text(encoding="utf-8"))
    catalogs = catalogs_payload.get("catalogs") or {}
    report["mdb_catalog_non_empty"] = {key: len(value) for key, value in catalogs.items() if value}
    report["mdb_catalog_empty"] = sorted(key for key, value in catalogs.items() if not value)
    ok = not report["missing_required_in_ui"] and not report["ui_keys_missing_backend_mentions"]
    report["ok"] = ok
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
