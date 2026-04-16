#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.cases import _build_precheck_summary

CASES_PATH = ROOT / "data" / "evals" / "prevalidation_battery_cases.json"
REPORT_PATH = ROOT / "data" / "evals" / "latest_prevalidation_battery_report.json"


BASE_CASE: dict[str, Any] = {
    "profile": {
        "empresa": "EMPRESA DEMO S.A.S.",
        "nit": "900123456",
        "documento": "70301576",
        "tipo_afiliado": "Afiliación",
        "numero_trabajadores": "1",
        "numero_sedes": "1",
        "nomina_total": "1750905",
        "documento_empleador": "900123456",
    },
    "flat_pairs": {
        "numerodocumentoempleador": "900123456",
    },
    "form_fields": {
        "fecha_radicacion": "10/04/2026",
        "fecha_inicio_cobertura": "11/04/2026",
        "numero_radicacion": "123456",
        "empleador_razon_social": "EMPRESA DEMO S.A.S.",
        "empleador_numero_documento_nit": "900123456",
        "rep_legal_nombre_completo": "CIRO HERNANDO GARNICA SALGADO",
        "rep_legal_numero_documento": "70301576",
        "rep_legal_tipo_documento": "CC",
        "rep_legal_correo": "demo@empresa.com",
        "sede_principal_codigo": "01",
        "sede_principal_nombre": "PRINCIPAL",
        "sede_principal_direccion": "CR 10 20 30",
        "sede_principal_telefono": "6041234",
        "sede_principal_correo": "sede@empresa.com",
        "sede_principal_municipio_distrito": "MEDELLIN",
        "sede_principal_zona": "U",
        "sede_principal_localidad_comuna": "10",
        "sede_principal_departamento": "ANTIOQUIA",
        "responsable_sede_principal_nombre_completo": "ANA LOPEZ",
        "responsable_sede_principal_tipo_documento": "CC",
        "responsable_sede_principal_numero_documento": "11032446",
        "tipo_tramite": "Afiliación",
        "naturaleza_juridica_empleador": "2",
        "tipo_aportante": "01",
        "tipo_persona": "Jurídica",
        "empleador_tipo_documento": "NI",
        "a_codigo_actividad_economica_principal": "4466301",
        "a_clase_riesgo": "V",
        "a_numero_sedes": "1",
        "a_numero_centros_trabajo": "1",
        "a_numero_inicial_trabajadores_estudiantes": "1",
        "a_valor_total_nomina": "1750905",
    },
    "records": [
        {
            "numero_de_identificacion": "11032446",
            "tipo_de_documento": "CC",
            "primer_nombre": "ANA",
            "primer_apellido": "LOPEZ",
            "salario": "1750905",
            "eps": "SALUD TOTAL",
            "pension": "PORVENIR",
            "sexo_identificacion": "F",
            "tipo_de_trabajador": "Dependiente",
            "tipo_de_salario": "1-Fijo",
            "jornada": "Única",
            "modalidad": "Presencial",
            "codigo_del_centro_de_trabajo": "1",
            "zona_(rural/urbana)": "Urbana",
            "fecha_nacimiento_dia": "22",
            "fecha_nacimiento_mes": "11",
            "fecha_nacimiento_ano": "1988",
            "_sheet": "Sede 01 - Trabajadores",
            "_row": "2",
        }
    ],
    "worker_sheet_counts": {
        "Sede 01 - Trabajadores": 1,
    },
    "worker_sheet_salary_totals": {
        "Sede 01 - Trabajadores": 1750905,
    },
    "clean_preview": {
        "sede_files": 1,
    },
}


def deep_merge(base: Any, override: Any) -> Any:
    if isinstance(override, dict) and override.get("__replace__") is True:
        return copy.deepcopy(override.get("value"))
    if isinstance(base, dict) and isinstance(override, dict):
        merged = {**base}
        for key, value in override.items():
            merged[key] = deep_merge(merged.get(key), value)
        return merged
    return copy.deepcopy(override)


def load_cases() -> list[dict[str, Any]]:
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))


def grade_case(case_def: dict[str, Any]) -> dict[str, Any]:
    payload = deep_merge(copy.deepcopy(BASE_CASE), case_def.get("overrides") or {})
    result = _build_precheck_summary(payload, docs=[], required_docs=[], missing_docs=[])
    actual_codes = [item.get("code") for item in result.get("motivos_de_rechazo", [])]
    expected_codes = case_def.get("expected_blocker_codes") or []
    approved = bool(result.get("approved"))
    expected_approved = bool(case_def.get("expected_approved"))
    missing_expected = [code for code in expected_codes if code not in actual_codes]
    unexpected_approval = approved != expected_approved
    passed = not missing_expected and not unexpected_approval
    return {
        "id": case_def["id"],
        "description": case_def.get("description", ""),
        "passed": passed,
        "expected_approved": expected_approved,
        "actual_approved": approved,
        "expected_blocker_codes": expected_codes,
        "actual_blocker_codes": actual_codes,
        "missing_expected_codes": missing_expected,
        "messages": [item.get("message") for item in result.get("motivos_de_rechazo", [])],
    }


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for item in results if item["passed"])
    failed = total - passed
    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": round((passed / total), 4) if total else 0.0,
        "failed_cases": [
            {
                "id": item["id"],
                "missing_expected_codes": item["missing_expected_codes"],
                "actual_approved": item["actual_approved"],
                "expected_approved": item["expected_approved"],
            }
            for item in results
            if not item["passed"]
        ],
    }


def main() -> None:
    cases = load_cases()
    results = [grade_case(case_def) for case_def in cases]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cases_total": len(results),
        "summary": summarize(results),
        "results": results,
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = report["summary"]
    print(
        "[ok] prevalidation-battery completada "
        f"casos={report['cases_total']} "
        f"passed={summary['passed']} "
        f"failed={summary['failed']} "
        f"pass_rate={summary['pass_rate']}"
    )
    print(f"[ok] reporte={REPORT_PATH}")


if __name__ == "__main__":
    main()
