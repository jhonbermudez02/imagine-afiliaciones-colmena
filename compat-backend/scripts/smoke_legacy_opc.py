#!/usr/bin/env python3
"""
Smoke test para adapters legacy OPC.

Modos:
1) routing:
   - valida discovery de `/legacy/opc/soportados`
   - verifica que cada OPC soportado no devuelva 500/501 con payload minimo
2) behavior:
   - ejecuta subset de OPC con payloads funcionales minimos (configurables)
   - valida codigos esperados por cada caso

Uso:
  python3 backend/scripts/smoke_legacy_opc.py --base-url http://localhost:8000/api/v1 --mode routing
  python3 backend/scripts/smoke_legacy_opc.py --base-url http://localhost:8000/api/v1 --mode behavior
"""

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
        classname = case.get("module", "legacy")
        name = case.get("name", "case")
        status = case.get("status", 0)
        lines.append(f'  <testcase classname="{classname}" name="{name}">')
        if not case["ok"]:
            message = case.get("message", f"HTTP {status}")
            detail = case.get("detail", "")
            lines.append(f'    <failure message="{message}">{detail}</failure>')
        lines.append("  </testcase>")
    lines.append("</testsuite>")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_module(
    module: str, base_url: str, timeout: float, verbose: bool, case_results: list[dict]
) -> tuple[int, int]:
    total = 0
    failed = 0
    support_url = f"{base_url}/{module}/legacy/opc/soportados"
    status, payload = http_json("GET", support_url, None, timeout)
    if status != 200:
        print(f"[FAIL] {module}: GET soportados -> {status} {payload}")
        case_results.append(
            {
                "module": module,
                "name": f"{module}.discovery",
                "ok": False,
                "status": status,
                "message": "discovery_failed",
                "detail": json.dumps(payload, ensure_ascii=False),
            }
        )
        return 1, 1

    opcs = payload.get("items", [])
    if not isinstance(opcs, list) or not opcs:
        print(f"[FAIL] {module}: lista de OPC vacia o invalida -> {payload}")
        case_results.append(
            {
                "module": module,
                "name": f"{module}.discovery_items",
                "ok": False,
                "status": status,
                "message": "discovery_items_invalid",
                "detail": json.dumps(payload, ensure_ascii=False),
            }
        )
        return 1, 1

    print(f"[INFO] {module}: {len(opcs)} opc soportados")
    for opc in opcs:
        total += 1
        status, response = http_json(
            "POST",
            f"{base_url}/{module}/legacy/opc",
            {"opc": str(opc)},
            timeout,
        )

        if status in (500, 501):
            failed += 1
            print(f"[FAIL] {module}:{opc} -> {status} {response}")
            case_results.append(
                {
                    "module": module,
                    "name": f"{module}.{opc}",
                    "ok": False,
                    "status": status,
                    "message": "unexpected_status",
                    "detail": json.dumps(response, ensure_ascii=False),
                }
            )
            continue

        case_results.append(
            {
                "module": module,
                "name": f"{module}.{opc}",
                "ok": True,
                "status": status,
                "message": "ok",
                "detail": "",
            }
        )
        if verbose:
            print(f"[OK] {module}:{opc} -> {status}")

    # Prueba de control: OPC inexistente debe devolver 501
    total += 1
    status, response = http_json(
        "POST",
        f"{base_url}/{module}/legacy/opc",
        {"opc": "__NO_EXISTE__"},
        timeout,
    )
    if status != 501:
        failed += 1
        print(f"[FAIL] {module}: control opc inexistente esperaba 501, obtuvo {status} {response}")
        case_results.append(
            {
                "module": module,
                "name": f"{module}.control_opc_inexistente",
                "ok": False,
                "status": status,
                "message": "expected_501_for_unknown_opc",
                "detail": json.dumps(response, ensure_ascii=False),
            }
        )
    elif verbose:
        print(f"[OK] {module}: control opc inexistente -> 501")
        case_results.append(
            {
                "module": module,
                "name": f"{module}.control_opc_inexistente",
                "ok": True,
                "status": status,
                "message": "ok",
                "detail": "",
            }
        )

    return total, failed


def _case(
    name: str,
    module: str,
    payload: dict,
    expected_statuses: set[int] | None = None,
) -> dict:
    return {
        "name": name,
        "module": module,
        "payload": payload,
        "expected_statuses": expected_statuses or {200},
    }


def build_behavior_cases(args: argparse.Namespace) -> list[dict]:
    solicitud_id = args.sample_solicitud_id
    tramite = args.sample_tramite
    usuario = args.sample_usuario
    id_prestacion = args.sample_id_prestacion
    tipo_solicitud = args.sample_tipo_solicitud
    pn = args.sample_pn
    ax = args.sample_ax
    id_estado_post = args.sample_id_estado_post
    tipo_gestion = args.sample_tipo_gestion
    categoria = args.sample_categoria

    cases: list[dict] = []

    # Notificaciones
    cases.append(
        _case(
            "notificaciones.consultaAfil",
            "notificaciones",
            {"opc": "consultaAfil", "ti": "CC", "cc": "123456789", "ts": tipo_solicitud},
        )
    )
    cases.append(
        _case(
            "notificaciones.modEstado",
            "notificaciones",
            {
                "opc": "modEstado",
                "solicitud_id": solicitud_id,
                "tramite": tramite,
                "user": usuario,
                "new_estado": "PENDIENTE LLAMADA",
            },
        )
    )
    cases.append(
        _case(
            "notificaciones.traerGestionPostPrestacion",
            "notificaciones",
            {
                "opc": "traerGestionPostPrestacion",
                "solicitud_id": solicitud_id,
                "tipo_gestion": tipo_gestion,
                "user": usuario,
            },
        )
    )
    cases.append(
        _case(
            "notificaciones.guardarPostEstado",
            "notificaciones",
            {
                "opc": "guardarPostEstado",
                "solicitud_id": solicitud_id,
                "id_estado_post": id_estado_post,
                "marca": "true",
                "user": usuario,
            },
        )
    )
    cases.append(
        _case(
            "notificaciones.guardarPostGestion",
            "notificaciones",
            {
                "opc": "guardarPostGestion",
                "solicitud_id": solicitud_id,
                "tipo_gestion": tipo_gestion,
                "observacion_g": "Smoke test gestion",
                "user": usuario,
            },
        )
    )
    cases.append(
        _case(
            "notificaciones.traerImagenesAValidar",
            "notificaciones",
            {
                "opc": "traerImagenesAValidar",
                "solicitud_id": solicitud_id,
                "tramite": tramite,
                "id_prestacion": id_prestacion,
                "tipo_solicitud": tipo_solicitud,
            },
        )
    )
    cases.append(
        _case(
            "notificaciones.validarImagen",
            "notificaciones",
            {
                "opc": "validarImagen",
                "solicitud_id": solicitud_id,
                "tramite": tramite,
                "pn": pn,
                "ax": ax,
                "valor": 1,
            },
        )
    )
    cases.append(
        _case(
            "notificaciones.consultarImagenes",
            "notificaciones",
            {
                "opc": "consultarImagenes",
                "solicitud_id": solicitud_id,
                "tramite": tramite,
                "id_prestacion": id_prestacion,
                "tipo_solicitud": tipo_solicitud,
            },
        )
    )
    cases.append(
        _case(
            "notificaciones.actualizarCategoria",
            "notificaciones",
            {"opc": "actualizarCategoria", "pn": pn, "val": categoria},
        )
    )
    cases.append(
        _case(
            "notificaciones.actualizarCategoriaNew",
            "notificaciones",
            {"opc": "actualizarCategoriaNew", "pn": str(pn), "val": str(categoria), "indexado": "S"},
        )
    )
    cases.append(
        _case(
            "notificaciones.verReclamantes",
            "notificaciones",
            {"opc": "verReclamantes", "solicitud_id": solicitud_id, "tramite": tramite},
        )
    )
    cases.append(
        _case(
            "notificaciones.cargaReclamantes",
            "notificaciones",
            {"opc": "cargaReclamantes", "solicitud_id": solicitud_id, "tramite": tramite},
        )
    )

    # Funerarios
    cases.append(
        _case(
            "funerarios.asignar",
            "funerarios",
            {"opc": "asignar", "tramite": tramite, "user": usuario},
        )
    )
    cases.append(
        _case(
            "funerarios.modEstado",
            "funerarios",
            {"opc": "modEstado", "tramite": tramite, "user": usuario, "new_estado": "Asignado"},
        )
    )
    cases.append(
        _case(
            "funerarios.buscaReclamantes",
            "funerarios",
            {"opc": "buscaReclamantes", "tramite": tramite},
        )
    )
    cases.append(
        _case(
            "funerarios.guardaBen",
            "funerarios",
            {
                "opc": "guardaBen",
                "tramite": tramite,
                "user": usuario,
                "items": [
                    {
                        "id_reclamante": "123456789",
                        "forma_pago": "Transferencia",
                        "banco": "001",
                        "tipo_cuenta": "Ahorros",
                        "numero_cuenta": "000111222",
                        "valor": 1000,
                    }
                ],
            },
        )
    )

    return cases


def build_real_ready_cases(args: argparse.Namespace) -> list[dict]:
    solicitud_id = args.sample_solicitud_id
    tramite = args.sample_tramite
    usuario = args.sample_usuario
    id_prestacion = args.sample_id_prestacion
    tipo_solicitud = args.sample_tipo_solicitud

    return [
        _case(
            "notificaciones.consultaAfil",
            "notificaciones",
            {"opc": "consultaAfil", "ti": "CC", "cc": "123456789", "ts": tipo_solicitud},
        ),
        _case(
            "funerarios.sincronizar",
            "funerarios",
            {"opc": "sincronizar", "tramite": tramite, "cedula": "123456789", "user": usuario},
        ),
        _case(
            "funerarios.enviaContabilizacion",
            "funerarios",
            {"opc": "enviaContabilizacion", "tramites": [f"{tramite}_123456789"], "user": usuario},
        ),
        _case(
            "funerarios.enviaContabilizacionOptima",
            "funerarios",
            {"opc": "enviaContabilizacionOptima", "tramite": tramite, "idrecla": "123456789", "user": usuario},
        ),
        _case(
            "funerarios.enviaContabilizacionAsulado",
            "funerarios",
            {"opc": "enviaContabilizacionAsulado", "tramite": tramite, "idrecla": "123456789", "user": usuario},
        ),
        _case(
            "funerarios.crearTerceros",
            "funerarios",
            {"opc": "crearTerceros", "user": usuario},
        ),
        _case(
            "notificaciones.cargaPlugInImages",
            "notificaciones",
            {
                "opc": "cargaPlugInImages",
                "solicitud_id": solicitud_id,
                "tramite": tramite,
                "prestacion": id_prestacion,
                "tiposol": tipo_solicitud,
            },
        ),
    ]


def build_workbench_cases(args: argparse.Namespace) -> list[dict]:
    solicitud_id = args.sample_solicitud_id
    tramite = args.sample_tramite
    usuario = args.sample_usuario
    year = dt.date.today().year
    return [
        _case(
            "notificaciones.workbench.consultaAfil",
            "notificaciones",
            {"opc": "consultaAfil", "ti": "CC", "cc": "123456789", "ts": "INV"},
        ),
        _case(
            "notificaciones.workbench.cargaReclamantes",
            "notificaciones",
            {"opc": "cargaReclamantes", "solicitud_id": solicitud_id, "tramite": tramite},
        ),
        _case(
            "notificaciones.workbench.traerImagenesAValidar",
            "notificaciones",
            {
                "opc": "traerImagenesAValidar",
                "solicitud_id": solicitud_id,
                "tramite": tramite,
                "id_prestacion": args.sample_id_prestacion,
                "tipo_solicitud": args.sample_tipo_solicitud,
            },
        ),
        _case(
            "notificaciones.workbench.guardarPostEstado",
            "notificaciones",
            {
                "opc": "guardarPostEstado",
                "solicitud_id": solicitud_id,
                "id_estado_post": args.sample_id_estado_post,
                "marca": "true",
                "user": usuario,
            },
        ),
        _case(
            "notificaciones.workbench.guardarPostGestion",
            "notificaciones",
            {
                "opc": "guardarPostGestion",
                "solicitud_id": solicitud_id,
                "tipo_gestion": args.sample_tipo_gestion,
                "observacion_g": "Prueba workbench automatizada",
                "user": usuario,
            },
        ),
        _case(
            "funerarios.bandejas.listarBancos",
            "funerarios",
            {"opc": "listarBancos", "page": 1, "rp": 25, "sortname": "id", "sortorder": "asc"},
        ),
        _case(
            "funerarios.bandejas.reporte",
            "funerarios",
            {"opc": "reporte", "date": year, "entidad": "FIDUCIA", "usuario": usuario},
        ),
        _case(
            "funerarios.bandejas.estadistico",
            "funerarios",
            {"opc": "estadistico", "date": year, "entidad": "FIDUCIA", "usuario": usuario},
        ),
        _case(
            "funerarios.detalle.asignar",
            "funerarios",
            {"opc": "asignar", "tramite": tramite, "user": usuario},
        ),
        _case(
            "funerarios.detalle.modEstado",
            "funerarios",
            {"opc": "modEstado", "tramite": tramite, "user": usuario, "new_estado": "Asignado"},
        ),
        _case(
            "funerarios.detalle.buscaReclamantes",
            "funerarios",
            {"opc": "buscaReclamantes", "tramite": tramite},
        ),
        _case(
            "funerarios.gestion.gestionar",
            "funerarios",
            {"opc": "gestionar", "tramite": tramite, "usuario": usuario},
        ),
        _case(
            "funerarios.gestion.guardarRespuesta",
            "funerarios",
            {
                "opc": "guardarRespuesta",
                "tramite": tramite,
                "usuario": usuario,
                "id_reclamante": "123456789",
                "id_respuesta": "1",
                "observacion_respuesta": "Prueba workbench automatizada",
            },
        ),
        _case(
            "funerarios.gestion.gestionaRec",
            "funerarios",
            {
                "opc": "gestionaRec",
                "tramite": tramite,
                "idben": "1",
                "estado": "Modificar Fpago",
                "obs": "Prueba workbench automatizada",
                "usuario": usuario,
            },
        ),
        _case(
            "funerarios.documentos.cargarRes",
            "funerarios",
            {"opc": "cargarRes", "tramite": tramite, "usuario": usuario},
        ),
        _case(
            "funerarios.documentos.clasificaImg",
            "funerarios",
            {"opc": "clasificaImg", "tramite": tramite, "usuario": usuario},
        ),
        _case(
            "funerarios.cargues.cierreMasivo",
            "funerarios",
            {"opc": "cierreMasivo", "usuario": usuario},
        ),
        _case(
            "funerarios.cargues.cierreMasivoAsulado",
            "funerarios",
            {"opc": "cierreMasivoAsulado", "usuario": usuario},
        ),
        _case(
            "funerarios.cargues.cppOptimaMasivo",
            "funerarios",
            {"opc": "cppOptimaMasivo", "tramite": f"{tramite}_123456789", "sworigen": "fiducia", "usuario": usuario},
        ),
        _case(
            "funerarios.cargues.reversionMasivo",
            "funerarios",
            {"opc": "reversionMasivo", "id_ben": "1", "usuario": usuario},
        ),
        _case(
            "funerarios.legacy.roundtrip",
            "funerarios",
            {"opc": "listarValores", "tipo": "bancos"},
        ),
    ]


def run_behavior(args: argparse.Namespace, case_results: list[dict]) -> tuple[int, int]:
    total = 0
    failed = 0
    for case in build_behavior_cases(args):
        total += 1
        module = case["module"]
        name = case["name"]
        payload = case["payload"]
        expected_statuses = case["expected_statuses"]
        status, response = http_json(
            "POST",
            f"{args.base_url.rstrip('/')}/{module}/legacy/opc",
            payload,
            args.timeout,
        )

        if status in expected_statuses:
            case_results.append(
                {
                    "module": module,
                    "name": name,
                    "ok": True,
                    "status": status,
                    "message": "ok",
                    "detail": "",
                }
            )
            if args.verbose:
                print(f"[OK] {name} -> {status}")
            continue

        failed += 1
        print(f"[FAIL] {name} -> {status} {response}")
        case_results.append(
            {
                "module": module,
                "name": name,
                "ok": False,
                "status": status,
                "message": "unexpected_status",
                "detail": json.dumps(response, ensure_ascii=False),
            }
        )
    return total, failed


def run_real_ready(args: argparse.Namespace, case_results: list[dict]) -> tuple[int, int]:
    total = 0
    failed = 0
    for case in build_real_ready_cases(args):
        total += 1
        module = case["module"]
        name = case["name"]
        payload = case["payload"]
        status, response = http_json(
            "POST",
            f"{args.base_url.rstrip('/')}/{module}/legacy/opc",
            payload,
            args.timeout,
        )
        ok = status == 200
        detail = ""
        if ok:
            markers = []
            if isinstance(response, dict):
                for k in ("source", "mode", "ws_ok", "ws_detail", "nota"):
                    if k in response:
                        markers.append(f"{k}={response.get(k)}")
            detail = ", ".join(markers)
        else:
            failed += 1
            detail = json.dumps(response, ensure_ascii=False)
        case_results.append(
            {
                "module": module,
                "name": name,
                "ok": ok,
                "status": status,
                "message": "ok" if ok else "unexpected_status",
                "detail": detail,
            }
        )
        if args.verbose:
            print(f"[{'OK' if ok else 'FAIL'}] {name} -> {status} {detail}")
    return total, failed


def run_workbench(args: argparse.Namespace, case_results: list[dict]) -> tuple[int, int]:
    total = 0
    failed = 0
    for case in build_workbench_cases(args):
        total += 1
        module = case["module"]
        name = case["name"]
        payload = case["payload"]
        status, response = http_json(
            "POST",
            f"{args.base_url.rstrip('/')}/{module}/legacy/opc",
            payload,
            args.timeout,
        )

        ok = status == 200
        if ok:
            case_results.append(
                {
                    "module": module,
                    "name": name,
                    "ok": True,
                    "status": status,
                    "message": "ok",
                    "detail": "",
                }
            )
            if args.verbose:
                print(f"[OK] {name} -> {status}")
            continue

        failed += 1
        print(f"[FAIL] {name} -> {status} {response}")
        case_results.append(
            {
                "module": module,
                "name": name,
                "ok": False,
                "status": status,
                "message": "unexpected_status",
                "detail": json.dumps(response, ensure_ascii=False),
            }
        )
    return total, failed


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test de adapters legacy opc")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000/api/v1",
        help="Base URL de la API (default: %(default)s)",
    )
    parser.add_argument("--timeout", type=float, default=10.0, help="Timeout HTTP en segundos")
    parser.add_argument("--verbose", action="store_true", help="Imprime detalle por OPC")
    parser.add_argument(
        "--mode",
        choices=["routing", "behavior", "real-ready", "workbench"],
        default="routing",
        help="Tipo de smoke test a ejecutar",
    )
    parser.add_argument("--sample-solicitud-id", type=int, default=1, help="solicitud_id para modo behavior")
    parser.add_argument("--sample-tramite", default="1", help="tramite para modo behavior")
    parser.add_argument("--sample-usuario", default="SMOKE", help="usuario para modo behavior")
    parser.add_argument("--sample-id-prestacion", type=int, default=1, help="id_prestacion para modo behavior")
    parser.add_argument("--sample-tipo-solicitud", default="INV", help="tipo_solicitud para modo behavior")
    parser.add_argument("--sample-pn", type=int, default=1, help="pn para modo behavior")
    parser.add_argument("--sample-ax", default="0", help="ax para modo behavior")
    parser.add_argument("--sample-id-estado-post", type=int, default=1, help="id_estado_post para modo behavior")
    parser.add_argument("--sample-tipo-gestion", type=int, default=1, help="tipo_gestion para modo behavior")
    parser.add_argument("--sample-categoria", type=int, default=1, help="categoria id_documento para modo behavior")
    parser.add_argument("--report-json", default="", help="Ruta de salida reporte JSON")
    parser.add_argument("--report-junit", default="", help="Ruta de salida reporte JUnit XML")
    args = parser.parse_args()

    grand_total = 0
    grand_failed = 0
    case_results: list[dict] = []
    if args.mode == "routing":
        for module in ("funerarios", "notificaciones"):
            total, failed = run_module(
                module, args.base_url.rstrip("/"), args.timeout, args.verbose, case_results
            )
            grand_total += total
            grand_failed += failed
    elif args.mode == "behavior":
        grand_total, grand_failed = run_behavior(args, case_results)
    elif args.mode == "real-ready":
        grand_total, grand_failed = run_real_ready(args, case_results)
    else:
        grand_total, grand_failed = run_workbench(args, case_results)

    passed = grand_total - grand_failed
    print(f"[SUMMARY] mode={args.mode} total={grand_total} passed={passed} failed={grand_failed}")
    summary = {
        "mode": args.mode,
        "base_url": args.base_url.rstrip("/"),
        "total": grand_total,
        "passed": passed,
        "failed": grand_failed,
        "ok": grand_failed == 0,
        "cases": case_results,
    }
    if args.report_json:
        write_json_report(args.report_json, summary)
        print(f"[INFO] JSON report: {args.report_json}")
    if args.report_junit:
        write_junit_report(args.report_junit, f"legacy-opc-{args.mode}", case_results)
        print(f"[INFO] JUnit report: {args.report_junit}")
    return 1 if grand_failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
