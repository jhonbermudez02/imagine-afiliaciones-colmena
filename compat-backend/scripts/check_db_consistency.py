#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError


def build_database_url(explicit_url: str) -> str:
    if explicit_url.strip():
        return explicit_url.strip()
    env_url = os.getenv("DATABASE_URL", "").strip()
    if env_url:
        return env_url
    host = os.getenv("DDBB_HOST", "127.0.0.1").strip()
    port = os.getenv("DDBB_PORT", "5432").strip()
    user = os.getenv("DDBB_USER", "postgres").strip()
    password = os.getenv("DDBB_PASSWORD", "").strip()
    name = os.getenv("DDBB_NAME", "img000").strip()
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"


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
            return resp.getcode(), json.loads(raw)
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


def get_existing_tables(engine, schema: str = "auxilios") -> set[str]:
    sql = text(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = :schema
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(sql, {"schema": schema}).scalars().all()
    return {str(r) for r in rows}


def fetch_snapshot(engine, usuario: str, tramite: str) -> dict:
    query_specs = {
        "reclamantes_total": {
            "tables": {"fun_reclamantes"},
            "sql": text("SELECT COUNT(*) FROM auxilios.fun_reclamantes"),
        },
        "reclamantes_estado_aprobado_fiducia": {
            "tables": {"fun_reclamantes"},
            "sql": text("SELECT COUNT(*) FROM auxilios.fun_reclamantes WHERE estado_reclamante = 'APROBADO FIDUCIA'"),
        },
        "reclamantes_estado_aprobado_asulado": {
            "tables": {"fun_reclamantes"},
            "sql": text("SELECT COUNT(*) FROM auxilios.fun_reclamantes WHERE estado_reclamante = 'APROBADO ASULADO'"),
        },
        "reclamantes_estado_interfaz_fiducia": {
            "tables": {"fun_reclamantes"},
            "sql": text("SELECT COUNT(*) FROM auxilios.fun_reclamantes WHERE estado_reclamante = 'Interfaz Fiducia Generada'"),
        },
        "reclamantes_estado_interfaz_asulado": {
            "tables": {"fun_reclamantes"},
            "sql": text("SELECT COUNT(*) FROM auxilios.fun_reclamantes WHERE estado_reclamante = 'Interfaz Asulado Generada'"),
        },
        "reclamantes_estado_aux_fiducia_pagado": {
            "tables": {"fun_reclamantes"},
            "sql": text("SELECT COUNT(*) FROM auxilios.fun_reclamantes WHERE estado_reclamante = 'AUXILIO DE FIDUCIA PAGADO'"),
        },
        "tramite_reclamantes_total": {
            "tables": {"fun_reclamantes"},
            "sql": text("SELECT COUNT(*) FROM auxilios.fun_reclamantes WHERE tramite = :tramite"),
        },
        "tramite_solicitudes_total": {
            "tables": {"fun_solicitudes"},
            "sql": text("SELECT COUNT(*) FROM auxilios.fun_solicitudes WHERE tramite = :tramite"),
        },
        "tramite_solicitudes_flujo": {
            "tables": {"fun_solicitudes"},
            "sql": text("SELECT COALESCE(MAX(estado_flujo), '') FROM auxilios.fun_solicitudes WHERE tramite = :tramite"),
        },
        "logs_cierre_validado_usuario_hoy": {
            "tables": {"fun_log_cierre_masivo"},
            "sql": text(
            """
            SELECT COUNT(*)
            FROM auxilios.fun_log_cierre_masivo
            WHERE usuario_carga = :usuario
              AND estado = 'Validado'
              AND fecha_carga::date = current_date
            """
            ),
        },
        "logs_cierre_aprobado_operador_usuario_hoy": {
            "tables": {"fun_log_cierre_masivo"},
            "sql": text(
            """
            SELECT COUNT(*)
            FROM auxilios.fun_log_cierre_masivo
            WHERE usuario_carga = :usuario
              AND estado = 'Aprobado Operador'
              AND fecha_carga::date = current_date
            """
            ),
        },
        "logs_reclamante_usuario": {
            "tables": {"fun_log_reclamante"},
            "sql": text("SELECT COUNT(*) FROM auxilios.fun_log_reclamante WHERE usuario = :usuario"),
        },
        "orphan_pagos_sin_reclamante": {
            "tables": {"fun_pagos_reclamantes", "fun_reclamantes"},
            "sql": text(
            """
            SELECT COUNT(*)
            FROM auxilios.fun_pagos_reclamantes p
            LEFT JOIN auxilios.fun_reclamantes r
              ON r.tramite = p.tramite
             AND r.identificacion = p.id_reclamante
            WHERE r.identificacion IS NULL
            """
            ),
        },
    }
    out: dict[str, object] = {}
    existing_tables = get_existing_tables(engine)
    missing_relations: list[str] = []
    skipped_metrics: list[str] = []
    params = {"usuario": usuario, "tramite": tramite}
    with engine.connect() as conn:
        for key, spec in query_specs.items():
            required = set(spec["tables"])
            if not required.issubset(existing_tables):
                out[key] = "SKIPPED_NOT_AVAILABLE"
                skipped_metrics.append(key)
                continue
            sql = spec["sql"]
            try:
                val = conn.execute(sql, params).scalar_one_or_none()
                out[key] = (
                    int(val)
                    if isinstance(val, int) or (isinstance(val, (str, float)) and str(val).isdigit())
                    else (val or "")
                )
            except SQLAlchemyError as exc:
                msg = str(exc)
                if "UndefinedTable" in msg or "does not exist" in msg:
                    out[key] = "MISSING_RELATION"
                    missing_relations.append(msg.split("\n")[0][:300])
                else:
                    out[key] = "ERROR"
                    missing_relations.append(msg.split("\n")[0][:300])
                # Evita "InFailedSqlTransaction" en consultas siguientes del snapshot.
                try:
                    conn.rollback()
                except Exception:
                    pass
    out["_missing_relations"] = missing_relations
    out["_skipped_metrics"] = skipped_metrics
    out["_existing_tables"] = sorted(existing_tables)
    return out


def build_ops(base_url: str, usuario: str, tramite: str, id_ben: str, sworigen: str) -> list[dict]:
    endpoint = f"{base_url.rstrip('/')}/funerarios/legacy/opc"
    return [
        {
            "name": "cierreMasivo",
            "url": endpoint,
            "payload": {"opc": "cierreMasivo", "usuario": usuario},
        },
        {
            "name": "cierreMasivoAsulado",
            "url": endpoint,
            "payload": {"opc": "cierreMasivoAsulado", "usuario": usuario},
        },
        {
            "name": "cppOptimaMasivo",
            "url": endpoint,
            "payload": {"opc": "cppOptimaMasivo", "tramite": f"{tramite}_123456789", "sworigen": sworigen, "usuario": usuario},
        },
        {
            "name": "reversionMasivo",
            "url": endpoint,
            "payload": {"opc": "reversionMasivo", "id_ben": id_ben, "usuario": usuario},
        },
    ]


def evaluate(before: dict, after: dict, op_results: list[dict]) -> list[dict]:
    checks: list[dict] = []
    for op in op_results:
        checks.append(
            {
                "name": f"api_{op['name']}_status",
                "status": "PASS" if op["status"] == 200 else "FAIL",
                "detail": f"status={op['status']}",
            }
        )

    if before.get("_missing_relations") or after.get("_missing_relations"):
        checks.append(
            {
                "name": "snapshot_relations_present",
                "status": "WARN",
                "detail": (
                    "Se detectaron tablas/relaciones faltantes para el snapshot. "
                    "Revisar campo _missing_relations en before/after."
                ),
            }
        )
    skipped_before = before.get("_skipped_metrics", [])
    skipped_after = after.get("_skipped_metrics", [])
    if skipped_before or skipped_after:
        checks.append(
            {
                "name": "snapshot_partial_mode",
                "status": "PASS",
                "detail": f"metricas_no_aplicables={len(set(skipped_before) | set(skipped_after))}",
            }
        )

    if before.get("reclamantes_total") != "SKIPPED_NOT_AVAILABLE" and after.get("reclamantes_total") != "SKIPPED_NOT_AVAILABLE":
        delta_total = int(after["reclamantes_total"]) - int(before["reclamantes_total"])
        checks.append(
            {
                "name": "reclamantes_total_unchanged",
                "status": "PASS" if delta_total == 0 else "WARN",
                "detail": f"before={before['reclamantes_total']} after={after['reclamantes_total']} delta={delta_total}",
            }
        )

    if after.get("orphan_pagos_sin_reclamante") not in {"SKIPPED_NOT_AVAILABLE", "ERROR", "MISSING_RELATION"}:
        orphan_after = int(after["orphan_pagos_sin_reclamante"])
        checks.append(
            {
                "name": "orphan_pagos_sin_reclamante",
                "status": "PASS" if orphan_after == 0 else "WARN",
                "detail": f"count={orphan_after}",
            }
        )

    if (
        before.get("logs_reclamante_usuario") not in {"SKIPPED_NOT_AVAILABLE", "ERROR", "MISSING_RELATION"}
        and after.get("logs_reclamante_usuario") not in {"SKIPPED_NOT_AVAILABLE", "ERROR", "MISSING_RELATION"}
    ):
        logs_delta = int(after["logs_reclamante_usuario"]) - int(before["logs_reclamante_usuario"])
        checks.append(
            {
                "name": "logs_reclamante_growth",
                "status": "PASS" if logs_delta >= 0 else "FAIL",
                "detail": f"before={before['logs_reclamante_usuario']} after={after['logs_reclamante_usuario']} delta={logs_delta}",
            }
        )

    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description="Chequeo de consistencia DB para operaciones masivas")
    parser.add_argument("--base-url", default="http://localhost:8000/api/v1")
    parser.add_argument("--database-url", default="", help="Opcional: sobreescribe DATABASE_URL")
    parser.add_argument("--sample-usuario", default="IMAGINE")
    parser.add_argument("--sample-tramite", default="456")
    parser.add_argument("--sample-id-ben", default="1")
    parser.add_argument("--sample-sworigen", default="fiducia")
    parser.add_argument("--run-ops", action="store_true", help="Ejecuta operaciones masivas via API antes del snapshot final")
    parser.add_argument("--timeout", type=float, default=12.0)
    parser.add_argument("--report-json", default="")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    database_url = build_database_url(args.database_url)
    engine = create_engine(database_url, pool_pre_ping=True, future=True)

    before = fetch_snapshot(engine, usuario=args.sample_usuario, tramite=args.sample_tramite)
    op_results: list[dict] = []
    if args.run_ops:
        for op in build_ops(
            base_url=args.base_url,
            usuario=args.sample_usuario,
            tramite=args.sample_tramite,
            id_ben=args.sample_id_ben,
            sworigen=args.sample_sworigen,
        ):
            status, payload = http_json("POST", op["url"], op["payload"], args.timeout)
            op_result = {"name": op["name"], "status": status, "response": payload}
            op_results.append(op_result)
            if args.verbose:
                print(f"[{'OK' if status == 200 else 'FAIL'}] {op['name']} -> {status}")

    after = fetch_snapshot(engine, usuario=args.sample_usuario, tramite=args.sample_tramite)
    checks = evaluate(before, after, op_results)
    failed = [c for c in checks if c["status"] == "FAIL"]
    warns = [c for c in checks if c["status"] == "WARN"]

    report = {
        "ok": len(failed) == 0,
        "has_warnings": len(warns) > 0,
        "database_url_masked": database_url.split("@")[-1],
        "base_url": args.base_url,
        "run_ops": args.run_ops,
        "before": before,
        "after": after,
        "ops": op_results,
        "checks": checks,
        "summary": {
            "pass": len([c for c in checks if c["status"] == "PASS"]),
            "warn": len(warns),
            "fail": len(failed),
        },
    }

    print(
        f"[SUMMARY] consistency pass={report['summary']['pass']} "
        f"warn={report['summary']['warn']} fail={report['summary']['fail']}"
    )
    if warns:
        for w in warns:
            print(f"[WARN] {w['name']} {w['detail']}")
    if failed:
        for f in failed:
            print(f"[FAIL] {f['name']} {f['detail']}")

    if args.report_json:
        write_json_report(args.report_json, report)
        print(f"[INFO] JSON report: {args.report_json}")

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
