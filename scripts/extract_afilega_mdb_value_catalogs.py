#!/usr/bin/env python3
from __future__ import annotations

import csv
import io
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MDB = Path(os.getenv("AFILEGA_SOURCE_MDB", "data/source_registry/Afiliaciones.mdb"))
JSON_OUT = ROOT / "data" / "evals" / "afilega_mdb_value_catalogs.json"
JS_OUT = ROOT / "frontend-nova" / "afilega-mdb-value-catalogs.js"

CATALOG_SOURCES: dict[str, list[tuple[str, str]]] = {
    "empresa_forma_pago": [
        ("afi_empresa_local", "emp_forma_pago"),
        ("afi_empresa_local__", "emp_forma_pago"),
        ("Plano_Emp_Tmp", "cod_forma_pago"),
        ("Plano_Emp_TmpN", "cod_forma_pago"),
    ],
    "empresa_tipo_aportante": [
        ("afi_empresa_local", "emp_aportante"),
        ("afi_empresa_local__", "emp_aportante"),
        ("afi_empresa_local", "cod_clase_aportante"),
        ("afi_empresa_local__", "cod_clase_aportante"),
        ("Plano_Emp_Tmp", "cod_tipo_aportante"),
        ("Plano_Emp_TmpN", "cod_tipo_aportante"),
    ],
    "empresa_vinculador_laboral": [
        ("afi_empresa_local", "emp_vinculador"),
        ("afi_empresa_local__", "emp_vinculador"),
    ],
    "empresa_regimen": [
        ("afi_empresa_local", "emp_regimen"),
        ("afi_empresa_local__", "emp_regimen"),
        ("Plano_Emp_Tmp", "cod_regimen"),
        ("Plano_Emp_TmpN", "cod_regimen"),
    ],
    "empresa_naturaleza": [
        ("afi_empresa_local", "emp_cod_naturaleza"),
        ("afi_empresa_local__", "emp_cod_naturaleza"),
        ("Plano_Emp_Tmp", "cod_naturaleza_empresa"),
        ("Plano_Emp_TmpN", "cod_naturaleza_empresa"),
    ],
    "empresa_clase_sociedad": [
        ("afi_empresa_local", "emp_cod_clase_soc"),
        ("afi_empresa_local__", "emp_cod_clase_soc"),
        ("Plano_Emp_Tmp", "cod_clase_sociedad"),
        ("Plano_Emp_TmpN", "cod_clase_sociedad"),
    ],
    "empresa_tamano": [
        ("afi_empresa_local", "emp_cod_tam_empresa"),
        ("afi_empresa_local__", "emp_cod_tam_empresa"),
        ("Plano_Emp_Tmp", "cod_tamano_empresa"),
        ("Plano_Emp_TmpN", "cod_tamano_empresa"),
    ],
    "empresa_grupo": [
        ("afi_empresa_local", "emp_cod_grupo_emp"),
        ("afi_empresa_local__", "emp_cod_grupo_emp"),
        ("Plano_Emp_Tmp", "cod_grupo_empresarial"),
        ("Plano_Emp_TmpN", "cod_grupo_empresarial"),
    ],
    "empresa_tipo_localizacion": [
        ("afi_empresa_local", "emp_cod_tipo_loc"),
        ("afi_empresa_local__", "emp_cod_tipo_loc"),
        ("afi_centros_local", "cen_cod_tipo_loc"),
        ("afi_centros_local__", "cen_cod_tipo_loc"),
        ("Plano_Emp_Tmp", "cod_tipo_localizacion"),
        ("Plano_Emp_TmpN", "cod_tipo_localizacion"),
    ],
    "empresa_zona_localizacion": [
        ("afi_empresa_local", "emp_cod_zona_loc"),
        ("afi_empresa_local__", "emp_cod_zona_loc"),
        ("afi_centros_local", "cen_cod_zona_loc"),
        ("afi_centros_local__", "cen_cod_zona_loc"),
        ("Plano_Emp_Tmp", "cod_zona_localizacion"),
        ("Plano_Emp_TmpN", "cod_zona_localizacion"),
    ],
    "sede_tipo_localizacion": [
        ("afi_centros_local", "cen_cod_tipo_loc"),
        ("afi_centros_local__", "cen_cod_tipo_loc"),
        ("afi_empresa_local", "emp_cod_tipo_loc"),
        ("afi_empresa_local__", "emp_cod_tipo_loc"),
    ],
    "sede_grado": [
        ("afi_centros_local", "cen_grado"),
        ("afi_centros_local__", "cen_grado"),
    ],
    "tipo_cotizante": [
        ("afi_medio_local", "afi_tipo_cotizante"),
        ("afi_medio_local__", "afi_tipo_cotizante"),
    ],
    "subtipo_cotizante": [
        ("afi_medio_local", "afi_subtipo_cotizante"),
        ("afi_medio_local__", "afi_subtipo_cotizante"),
    ],
    "tipo_novedad": [
        ("Plano_Nov_Tmp", "cod_tipo_novedad_trabajador"),
    ],
    "novedad_estado": [
        ("Plano_Nov_Tmp", "cod_estado_novedad"),
    ],
    "novedad_autoliquidacion": [
        ("Plano_Nov_Tmp", "bln_autoliquidacion"),
    ],
    "novedad_origen": [
        ("Plano_Nov_Tmp", "origen"),
    ],
}


def export_table(mdb_path: Path, table: str) -> list[dict[str, str]]:
    result = subprocess.run(["mdb-export", str(mdb_path), table], text=True, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"mdb-export failed for {table}")
    return list(csv.DictReader(io.StringIO(result.stdout)))


def clean_value(value: Any) -> str:
    text = str(value or "").strip()
    if not text or text.upper() == "NULL":
        return ""
    return text


def build_catalogs(mdb_path: Path) -> dict[str, Any]:
    table_cache: dict[str, list[dict[str, str]]] = {}
    tables: dict[str, Any] = {}
    catalogs: dict[str, list[str]] = {}
    source_map: dict[str, list[dict[str, Any]]] = {}
    warnings: list[str] = []

    for key, sources in CATALOG_SOURCES.items():
        values: set[str] = set()
        source_map[key] = []
        for table, field in sources:
            try:
                if table not in table_cache:
                    table_cache[table] = export_table(mdb_path, table)
                    tables[table] = {"rows": len(table_cache[table])}
                extracted = sorted({clean_value(row.get(field)) for row in table_cache[table] if clean_value(row.get(field))})
                values.update(extracted)
                source_map[key].append({"table": table, "field": field, "values_found": len(extracted)})
            except Exception as exc:
                warnings.append(f"{table}.{field}: {exc}")
                source_map[key].append({"table": table, "field": field, "error": str(exc)})
        catalogs[key] = sorted(values, key=lambda item: (len(item), item))

    return {
        "source_mdb": str(mdb_path),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "catalogs": catalogs,
        "source_map": source_map,
        "tables": tables,
        "warnings": warnings,
        "note": "Los catálogos vacíos provienen de tablas MDB sin registros; el sistema no inventa valores para esos campos.",
    }


def write_js(payload: dict[str, Any]) -> None:
    catalogs = payload.get("catalogs") or {}
    body = json.dumps(catalogs, ensure_ascii=False, indent=2)
    generated_at = payload.get("generated_at") or ""
    source_mdb = payload.get("source_mdb") or ""
    JS_OUT.write_text(
        "// Generado por scripts/extract_afilega_mdb_value_catalogs.py\n"
        f"export const AFILEGA_MDB_VALUE_CATALOG_SOURCE = {json.dumps(source_mdb, ensure_ascii=False)};\n"
        f"export const AFILEGA_MDB_VALUE_CATALOG_GENERATED_AT = {json.dumps(generated_at)};\n"
        f"export const AFILEGA_MDB_VALUE_CATALOGS = {body};\n",
        encoding="utf-8",
    )


def main() -> int:
    mdb_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_MDB
    if not mdb_path.exists():
        print(f"No existe MDB: {mdb_path}", file=sys.stderr)
        return 2
    payload = build_catalogs(mdb_path)
    JSON_OUT.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_js(payload)
    non_empty = {key: len(value) for key, value in (payload.get("catalogs") or {}).items() if value}
    print(json.dumps({"json": str(JSON_OUT), "js": str(JS_OUT), "non_empty": non_empty}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
