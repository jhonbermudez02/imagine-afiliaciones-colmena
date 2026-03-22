#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, text


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


def write_json_report(path: str, payload: dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def get_table_columns(engine, schema: str, table: str) -> set[str]:
    sql = text(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = :schema
          AND table_name = :table
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(sql, {"schema": schema, "table": table}).scalars().all()
    return {str(r) for r in rows}


def main() -> int:
    parser = argparse.ArgumentParser(description="Saneamiento de huérfanos en fun_pagos_reclamantes")
    parser.add_argument("--database-url", default="", help="Opcional: sobreescribe DATABASE_URL")
    parser.add_argument("--apply", action="store_true", help="Aplica backup + delete de huérfanos")
    parser.add_argument("--limit", type=int, default=20, help="Muestra N ejemplos de huérfanos")
    parser.add_argument("--report-json", default="")
    args = parser.parse_args()

    engine = create_engine(build_database_url(args.database_url), pool_pre_ping=True, future=True)
    pago_cols = get_table_columns(engine, schema="auxilios", table="fun_pagos_reclamantes")
    rec_cols = get_table_columns(engine, schema="auxilios", table="fun_reclamantes")

    required_pago = {"id", "tramite", "id_reclamante"}
    required_rec = {"tramite", "identificacion"}
    if not required_pago.issubset(pago_cols):
        missing = sorted(required_pago - pago_cols)
        print(f"[FAIL] columnas faltantes en auxilios.fun_pagos_reclamantes: {', '.join(missing)}")
        return 1
    if not required_rec.issubset(rec_cols):
        missing = sorted(required_rec - rec_cols)
        print(f"[FAIL] columnas faltantes en auxilios.fun_reclamantes: {', '.join(missing)}")
        return 1

    forma_pago_expr = "p.forma_pago" if "forma_pago" in pago_cols else "NULL::text AS forma_pago"
    entidad_bancaria_expr = (
        "p.entidad_bancaria" if "entidad_bancaria" in pago_cols else "NULL::text AS entidad_bancaria"
    )
    numero_cuenta_expr = "p.numero_cuenta" if "numero_cuenta" in pago_cols else "NULL::text AS numero_cuenta"
    valor_reconocido_expr = (
        "p.valor_reconocido" if "valor_reconocido" in pago_cols else "NULL::numeric AS valor_reconocido"
    )

    sql_count_orphans = text(
        """
        SELECT COUNT(*)
        FROM auxilios.fun_pagos_reclamantes p
        LEFT JOIN auxilios.fun_reclamantes r
          ON r.tramite = p.tramite
         AND r.identificacion = p.id_reclamante
        WHERE r.identificacion IS NULL
        """
    )
    sql_sample = text(
        f"""
        SELECT
            p.id,
            p.tramite,
            p.id_reclamante,
            {forma_pago_expr},
            {entidad_bancaria_expr},
            {numero_cuenta_expr},
            {valor_reconocido_expr}
        FROM auxilios.fun_pagos_reclamantes p
        LEFT JOIN auxilios.fun_reclamantes r
          ON r.tramite = p.tramite
         AND r.identificacion = p.id_reclamante
        WHERE r.identificacion IS NULL
        ORDER BY p.id
        LIMIT :limit
        """
    )

    with engine.connect() as conn:
        orphan_count = int(conn.execute(sql_count_orphans).scalar_one() or 0)
        samples = [dict(r) for r in conn.execute(sql_sample, {"limit": max(1, args.limit)}).mappings().all()]

    print(f"[INFO] orphan_pagos_detectados={orphan_count}")
    if samples:
        print("[INFO] muestra_orphans:")
        for row in samples:
            print(
                f"  id={row['id']} tramite={row['tramite']} id_reclamante={row['id_reclamante']} "
                f"forma_pago={row.get('forma_pago')}"
            )

    backed_up = 0
    deleted = 0
    if args.apply and orphan_count > 0:
        sql_create_backup = text(
            """
            CREATE TABLE IF NOT EXISTS auxilios.fun_pagos_reclamantes_orphans_backup AS
            SELECT p.*, now()::timestamp as backup_ts
            FROM auxilios.fun_pagos_reclamantes p
            WHERE 1 = 0
            """
        )
        sql_backup = text(
            """
            INSERT INTO auxilios.fun_pagos_reclamantes_orphans_backup
            SELECT p.*, now()::timestamp as backup_ts
            FROM auxilios.fun_pagos_reclamantes p
            LEFT JOIN auxilios.fun_reclamantes r
              ON r.tramite = p.tramite
             AND r.identificacion = p.id_reclamante
            WHERE r.identificacion IS NULL
              AND NOT EXISTS (
                SELECT 1
                FROM auxilios.fun_pagos_reclamantes_orphans_backup b
                WHERE b.id = p.id
              )
            """
        )
        sql_delete = text(
            """
            DELETE FROM auxilios.fun_pagos_reclamantes p
            USING (
                SELECT p2.id
                FROM auxilios.fun_pagos_reclamantes p2
                LEFT JOIN auxilios.fun_reclamantes r
                  ON r.tramite = p2.tramite
                 AND r.identificacion = p2.id_reclamante
                WHERE r.identificacion IS NULL
            ) z
            WHERE p.id = z.id
            """
        )
        with engine.begin() as conn:
            conn.execute(sql_create_backup)
            backed_up = conn.execute(sql_backup).rowcount or 0
            deleted = conn.execute(sql_delete).rowcount or 0
        print(f"[OK] backup_insertados={backed_up} eliminados={deleted}")
    elif args.apply:
        print("[OK] no_hay_orphans_para_aplicar")
    else:
        print("[INFO] dry_run=true (usa --apply para ejecutar backup+delete)")

    report = {
        "ok": True,
        "mode": "apply" if args.apply else "dry-run",
        "orphan_count_before": orphan_count,
        "sample": samples,
        "backed_up": backed_up,
        "deleted": deleted,
    }
    if args.report_json:
        write_json_report(args.report_json, report)
        print(f"[INFO] JSON report: {args.report_json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
