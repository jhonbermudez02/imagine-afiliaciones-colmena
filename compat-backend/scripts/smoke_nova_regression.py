#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path


def http_json(method: str, url: str, body: dict | None, timeout: float) -> tuple[int, dict]:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url=url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8") or "{}"
            payload = json.loads(raw)
            return resp.getcode(), payload
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8") or "{}"
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"raw": raw}
        return exc.code, payload
    except urllib.error.URLError as exc:
        return 599, {"error": "network_unreachable", "detail": str(exc)}


def write_json_report(path: str, payload: dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_junit_report(path: str, suite_name: str, cases: list[dict]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    failures = sum(1 for c in cases if not c["ok"])
    ts = dt.datetime.utcnow().isoformat() + "Z"
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<testsuite name="{suite_name}" tests="{len(cases)}" failures="{failures}" timestamp="{ts}">',
    ]
    for case in cases:
        lines.append(f'  <testcase classname="{case["module"]}" name="{case["name"]}">')
        if not case["ok"]:
            lines.append(
                f'    <failure message="{case["message"]}">{case.get("detail", "")}</failure>'
            )
        lines.append("  </testcase>")
    lines.append("</testsuite>")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_md_report(path: str, summary: dict, checks: list[dict]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Smoke NOVA Regression",
        "",
        f"- Fecha: `{dt.datetime.utcnow().isoformat()}Z`",
        f"- Base URL: `{summary.get('base_url', '')}`",
        f"- Resultado: `{'PASS' if summary.get('ok') else 'FAIL'}`",
        f"- Total: `{summary.get('total', 0)}`",
        f"- Passed: `{summary.get('passed', 0)}`",
        f"- Failed: `{summary.get('failed', 0)}`",
        "",
        "## Detalle",
        "",
        "| Caso | Pregunta | Estado | Provider | Hallazgo |",
        "|---|---|---|---|---|",
    ]
    for c in checks:
        name = c.get("name", "")
        q = str(c.get("question", "")).replace("|", "/")
        ok = "OK" if c.get("ok") else "FAIL"
        provider = c.get("provider", "")
        finding = (c.get("finding", "") or "").replace("|", "/")
        lines.append(f"| {name} | `{q}` | `{ok}` | `{provider}` | {finding} |")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_cases() -> list[dict]:
    return [
        {
            "name": "nova.validacion_jefe",
            "module": "nova",
            "question": "validacion jefe",
            "must_include_any": [
                "validación jefe",
                "validacion jefe",
                "aprueba/rechaza",
                "menú de validación jefe",
                "menu de validacion jefe",
            ],
        },
        {
            "name": "nova.bloqueo_typo_fuzzy",
            "module": "nova",
            "question": "bloqeo solcutusd",
            "must_include_any": [
                "bloqueo solicitudes",
                "administración/permisos",
                "activar/desactivar",
                "activar desactivar",
            ],
        },
        {
            "name": "nova.auditoria_operativa",
            "module": "nova",
            "question": "auditoria",
            "must_include_any": [
                "auditoría",
                "auditoria",
                "cargar auditoría",
                "cargar auditoria",
                "solicitud_id",
            ],
        },
        {
            "name": "nova.buscar_reclamante_documento",
            "module": "nova",
            "question": "buscar reclamante por documento",
            "must_include_any": [
                "necesito el número de documento",
                "necesito el numero de documento",
                "buscar reclamante 12345678",
            ],
        },
        {
            "name": "nova.validacion_pagos",
            "module": "nova",
            "question": "validacion pagos",
            "must_include_any": [
                "validación pagos",
                "validacion pagos",
                "forma de pago",
                "entidad bancaria",
                "cuenta",
            ],
        },
        {
            "name": "nova.bandejas_notificaciones",
            "module": "nova",
            "question": "bandeja notificaciones",
            "must_include_any": [
                "notificaciones",
                "pendientes de validación",
                "pendientes prestación",
                "prestaciones generadas",
                "reporte",
            ],
        },
        {
            "name": "nova.documentos_clasificacion",
            "module": "nova",
            "question": "clasificacion documentos",
            "must_include_any": [
                "documentos",
                "clasificación",
                "clasificacion",
                "trámite",
                "id solicitud",
            ],
        },
        {
            "name": "nova.administracion_permisos",
            "module": "nova",
            "question": "administracion permisos",
            "must_include_any": [
                "administración/permisos",
                "administracion/permisos",
                "bloqueo solicitudes",
                "activar/desactivar",
            ],
        },
        {
            "name": "nova.typo_auditoria",
            "module": "nova",
            "question": "audotoria",
            "must_include_any": [
                "auditoría",
                "auditoria",
                "cargar auditoría",
                "cargar auditoria",
            ],
        },
        {
            "name": "nova.cierre_masivo",
            "module": "nova",
            "question": "como ejecutar cierre masivo",
            "must_include_any": [
                "cierre masivo",
                "cierremasivo",
                "reversion",
                "reversión",
                "trazabilidad",
            ],
        },
        {
            "name": "nova.notificaciones_guardar",
            "module": "nova",
            "question": "que valida notificaciones antes de guardar",
            "must_include_any": [
                "notificaciones",
                "campos obligatorios",
                "post estado",
                "post gestión",
                "post gestion",
            ],
        },
        {
            "name": "nova.pendientes_de_pago",
            "module": "nova",
            "question": "que pendientes de pago hay",
            "must_include_any": [
                "pendientes de pago",
                "validación pagos",
                "validacion pagos",
                "forma de pago",
                "banco",
            ],
        },
        {
            "name": "nova.usuarios_con_mas_trabajo",
            "module": "nova",
            "question": "usuairos con mas trabajo",
            "must_include_any": [
                "usuarios con más carga operativa",
                "usuarios con mas carga operativa",
                "estadístico",
                "estadistico",
                "auditoría",
                "auditoria",
            ],
        },
        {
            "name": "nova.solicitudes_bloqueadas",
            "module": "nova",
            "question": "que solicitudes tengo bloqueadas",
            "must_include_any": [
                "estado global",
                "activo/inactivo",
                "bloqueoestado",
                "bloqueocreate",
                "bloqueo solicitudes",
            ],
        },
        {
            "name": "nova.tramites_funerarios_pendientes",
            "module": "nova",
            "question": "Listar trámites funerarios pendientes",
            "must_include_any": [
                "trámites funerarios pendientes",
                "tramites funerarios pendientes",
                "reporte operativo",
                "estadístico",
                "detalle trámite",
            ],
        },
        {
            "name": "nova.bancos_data",
            "module": "nova",
            "question": "bancos",
            "must_include_any": [
                "bancos (dato real)",
                "total=",
            ],
        },
        {
            "name": "nova.notificaciones_pendientes_data",
            "module": "nova",
            "question": "notificaciones pendientes",
            "must_include_any": [
                "pendientes (dato real)",
                "notificaciones=",
                "funerarios=",
            ],
        },
        {
            "name": "nova.tramites_pendientes_data",
            "module": "nova",
            "question": "tramites pendientes",
            "must_include_any": [
                "pendientes (dato real)",
                "total=",
            ],
        },
        {
            "name": "nova.solicitudes_pendientes_typo_data",
            "module": "nova",
            "question": "spliciotudes pendientes",
            "must_include_any": [
                "pendientes (dato real)",
                "total=",
            ],
        },
        {
            "name": "nova.pendientes_prestacion_data_first",
            "module": "nova",
            "question": "pendientes de prestacion",
            "must_include_any": [
                "dato real",
                "total=",
                "pendientes de prestación",
                "pendientes de prestacion",
            ],
        },
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke de regresión NOVA (chat operativo).")
    parser.add_argument("--base-url", default="http://localhost:8000/api/v1")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--report-json", default="")
    parser.add_argument("--report-junit", default="")
    parser.add_argument("--report-md", default="")
    args = parser.parse_args()

    total = 0
    failed = 0
    cases_out: list[dict] = []
    md_checks: list[dict] = []
    base_url = args.base_url.rstrip("/")
    chat_url = f"{base_url}/ai/chat"
    global_forbidden = [
        "ruta inclusion",
    ]

    for case in build_cases():
        total += 1
        status, response = http_json(
            method="POST",
            url=chat_url,
            body={"question": case["question"], "template": "operacion", "use_rag": True},
            timeout=args.timeout,
        )
        answer = str(response.get("answer", ""))
        answer_low = answer.lower()
        citations = response.get("citations")
        has_data_first = ("dato real" in answer_low) or ("datos reales" in answer_low)
        has_no_real_data = "no encontré datos reales" in answer_low or "no encontre datos reales" in answer_low
        has_must = any(
            needle.lower() in answer_low for needle in case["must_include_any"]
        )
        has_forbidden = any(bad in answer_low for bad in global_forbidden)
        has_visible_citations = isinstance(citations, list) and len(citations) > 0
        ok = (
            status == 200
            and bool(response.get("ok"))
            and (has_must or has_data_first or has_no_real_data)
            and not has_forbidden
            and not has_visible_citations
        )
        if not ok:
            failed += 1
            finding_parts = []
            if status != 200 or not bool(response.get("ok")):
                finding_parts.append("status/ok inválido")
            if not has_must:
                finding_parts.append("no cumple contenido esperado")
            if has_forbidden:
                finding_parts.append("contiene frase prohibida")
            if has_visible_citations:
                finding_parts.append("expone fuentes/citations")
            finding = ", ".join(finding_parts) or "respuesta inválida"
            detail = {
                "status": status,
                "response": response,
                "must_include_any": case["must_include_any"],
                "forbidden": global_forbidden,
                "finding": finding,
            }
            print(f"[FAIL] {case['name']} -> {status} {json.dumps(detail, ensure_ascii=False)}")
            msg = "unexpected_nova_answer"
            case_detail = json.dumps(detail, ensure_ascii=False)
        else:
            if args.verbose:
                provider = response.get("provider", "")
                print(f"[OK] {case['name']} -> {status} provider={provider}")
            msg = "ok"
            case_detail = ""
            finding = ""
        cases_out.append(
            {
                "module": case["module"],
                "name": case["name"],
                "ok": ok,
                "status": status,
                "message": msg,
                "detail": case_detail,
            }
        )
        md_checks.append(
            {
                "name": case["name"],
                "question": case["question"],
                "ok": ok,
                "provider": str(response.get("provider", "")),
                "finding": finding,
            }
        )

    summary = {
        "mode": "nova-regression",
        "base_url": base_url,
        "total": total,
        "passed": total - failed,
        "failed": failed,
        "ok": failed == 0,
        "cases": cases_out,
    }
    print(f"[SUMMARY] mode=nova-regression total={total} passed={total - failed} failed={failed}")

    if args.report_json:
        write_json_report(args.report_json, summary)
        print(f"[INFO] JSON report: {args.report_json}")
    if args.report_junit:
        write_junit_report(args.report_junit, "smoke_nova_regression", cases_out)
        print(f"[INFO] JUnit report: {args.report_junit}")
    if args.report_md:
        write_md_report(args.report_md, summary, md_checks)
        print(f"[INFO] MD report: {args.report_md}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
