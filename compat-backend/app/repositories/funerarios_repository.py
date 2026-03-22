from __future__ import annotations
from collections.abc import Sequence

from sqlalchemy import text
from sqlalchemy.engine import Engine


class FunerariosRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def _table_exists(self, schema: str, table: str) -> bool:
        sql = text("SELECT to_regclass(:fqtn) IS NOT NULL")
        fqtn = f"{schema}.{table}"
        with self.engine.connect() as conn:
            val = conn.execute(sql, {"fqtn": fqtn}).scalar_one_or_none()
        return bool(val)
        self._report_cfg = {
            "FIDUCIA": {
                "db_name": "FIDUCIA",
                "statuses": ("AUXILIO DE FIDUCIA PAGADO",),
            },
            "COMPANIA DE SEGUROS BOLIVAR S A": {
                "db_name": "COMPANIA DE SEGUROS BOLIVAR S A",
                "statuses": (
                    "AUXILIO APROBADO CON SOPORTE OK ADMINISTRADORA",
                    "Cheque Informado",
                    "Transferencia Generada",
                ),
            },
            "SEGUROS DE VIDA SURAMERICANA S.A.": {
                "db_name": "SEGUROS DE VIDA SURAMERICANA S.A.",
                "statuses": (
                    "AUXILIO APROBADO CON SOPORTE OK",
                    "AUXILIO APROBADO CON SOPORTE OK ADMINISTRADORA",
                    "Cheque Informado",
                    "PAGO COBRADO Y PAGADO ASEGURADORA",
                    "Transferencia Generada",
                ),
            },
        }

    def assign_solicitud(self, tramite: str) -> int:
        sql = text(
            """
            UPDATE auxilios.fun_solicitudes
            SET estado_flujo = 'Asignado'
            WHERE tramite = :tramite
            """
        )
        with self.engine.begin() as conn:
            result = conn.execute(sql, {"tramite": tramite})
            return result.rowcount or 0

    def change_estado_solicitud(self, tramite: str, new_estado: str) -> int:
        sql = text(
            """
            UPDATE auxilios.fun_solicitudes
            SET estado_flujo = :new_estado
            WHERE tramite = :tramite
            """
        )
        with self.engine.begin() as conn:
            result = conn.execute(sql, {"tramite": tramite, "new_estado": new_estado})
            return result.rowcount or 0

    def list_reclamantes(self, tramite: str) -> Sequence[dict]:
        sql = text(
            """
            SELECT
                id_ben,
                tramite,
                tipoid_beneficiario,
                identificacion,
                nombre_beneficiario,
                estado_reclamante
            FROM auxilios.fun_reclamantes
            WHERE tramite = :tramite
            ORDER BY id_ben
            """
        )
        with self.engine.connect() as conn:
            rows = conn.execute(sql, {"tramite": tramite}).mappings().all()
            return [dict(r) for r in rows]

    def upsert_pagos_reclamantes(self, tramite: str, items: Sequence[dict]) -> dict:
        inserted = 0
        updated = 0
        with self.engine.begin() as conn:
            for item in items:
                exists_sql = text(
                    """
                    SELECT id
                    FROM auxilios.fun_pagos_reclamantes
                    WHERE tramite = :tramite AND id_reclamante = :id_reclamante
                    ORDER BY id DESC
                    LIMIT 1
                    """
                )
                existing = conn.execute(
                    exists_sql,
                    {"tramite": tramite, "id_reclamante": item["id_reclamante"]},
                ).scalar_one_or_none()

                params = {
                    "tramite": tramite,
                    "id_reclamante": item["id_reclamante"],
                    "forma_pago": item.get("forma_pago"),
                    "entidad_bancaria": item.get("banco"),
                    "tipo_cuenta": item.get("tipo_cuenta"),
                    "numero_cuenta": item.get("numero_cuenta"),
                    "valor_reconocido": item.get("valor"),
                }

                if existing:
                    upd_sql = text(
                        """
                        UPDATE auxilios.fun_pagos_reclamantes
                        SET
                            forma_pago = :forma_pago,
                            entidad_bancaria = :entidad_bancaria,
                            tipo_cuenta = :tipo_cuenta,
                            numero_cuenta = :numero_cuenta,
                            valor_reconocido = :valor_reconocido
                        WHERE id = :id
                        """
                    )
                    upd_params = dict(params)
                    upd_params["id"] = existing
                    conn.execute(upd_sql, upd_params)
                    updated += 1
                else:
                    ins_sql = text(
                        """
                        INSERT INTO auxilios.fun_pagos_reclamantes
                        (tramite, id_reclamante, forma_pago, entidad_bancaria, tipo_cuenta, numero_cuenta, valor_reconocido)
                        VALUES
                        (:tramite, :id_reclamante, :forma_pago, :entidad_bancaria, :tipo_cuenta, :numero_cuenta, :valor_reconocido)
                        """
                    )
                    conn.execute(ins_sql, params)
                    inserted += 1

        return {"inserted": inserted, "updated": updated}

    def list_auditoria(self, tramite: str, limit: int) -> Sequence[dict]:
        sql = text(
            """
            SELECT descripcion_actividad, usuario_ejecuta, proceso, tramite
            FROM auxilios.fun_actividades
            WHERE tramite = :tramite
            LIMIT :limit
            """
        )
        with self.engine.connect() as conn:
            rows = conn.execute(sql, {"tramite": tramite, "limit": limit}).mappings().all()
            return [dict(r) for r in rows]

    def list_bancos_catalog(self) -> Sequence[dict]:
        sql = text(
            """
            SELECT codigo, nombre
            FROM auxilios.fun_bancos
            ORDER BY nombre
            """
        )
        with self.engine.connect() as conn:
            rows = conn.execute(sql).mappings().all()
            return [dict(r) for r in rows]

    def list_bancos_grid(
        self,
        *,
        page: int,
        rp: int,
        sortname: str,
        sortorder: str,
        query: str | None,
        qtype: str | None,
    ) -> dict:
        safe_page = max(1, page)
        safe_rp = max(1, min(rp, 200))
        start = (safe_page - 1) * safe_rp

        allowed_sort = {"id", "codigo", "nombre"}
        safe_sortname = sortname if sortname in allowed_sort else "id"
        safe_sortorder = "DESC" if str(sortorder).upper() == "DESC" else "ASC"

        allowed_qtype = {"id", "codigo", "nombre"}
        where = ""
        params: dict[str, object] = {}
        if query and qtype in allowed_qtype:
            where = f" WHERE {qtype}::text ILIKE :query "
            params["query"] = f"%{query}%"

        total_sql = text(f"SELECT COUNT(*) FROM auxilios.fun_bancos {where}")
        rows_sql = text(
            f"""
            SELECT id, codigo, nombre
            FROM auxilios.fun_bancos
            {where}
            ORDER BY {safe_sortname} {safe_sortorder}
            LIMIT :limit OFFSET :offset
            """
        )
        params_rows = dict(params)
        params_rows["limit"] = safe_rp
        params_rows["offset"] = start

        with self.engine.connect() as conn:
            total = int(conn.execute(total_sql, params).scalar_one() or 0)
            rows = conn.execute(rows_sql, params_rows).mappings().all()
        return {"page": safe_page, "total": total, "rows": [dict(r) for r in rows]}

    def get_pago_reclamante(self, *, tramite: str | None, id_ben: str | None, identificacion: str | None) -> dict | None:
        where = []
        params: dict[str, object] = {}
        if tramite:
            where.append("r.tramite = :tramite")
            params["tramite"] = tramite
        if id_ben:
            where.append("r.id_ben = :id_ben")
            params["id_ben"] = id_ben
        if identificacion:
            where.append("r.identificacion = :identificacion")
            params["identificacion"] = identificacion
        if not where:
            return None

        sql = text(
            f"""
            SELECT
                r.id_ben,
                r.tramite,
                r.identificacion,
                r.nombre_beneficiario,
                p.id AS pago_id,
                p.nit_aseguradora,
                p.nombre_aseguradora,
                p.valor_reconocido,
                p.forma_pago,
                p.entidad_bancaria,
                p.tipo_cuenta,
                p.numero_cuenta
            FROM auxilios.fun_reclamantes r
            LEFT JOIN auxilios.fun_pagos_reclamantes p
              ON p.tramite = r.tramite
             AND p.id_reclamante = r.identificacion
            WHERE {" AND ".join(where)}
            ORDER BY p.id DESC NULLS LAST
            LIMIT 1
            """
        )
        with self.engine.connect() as conn:
            row = conn.execute(sql, params).mappings().first()
            return dict(row) if row else None

    def update_reclamante(
        self,
        *,
        id_ben: str,
        tipoid: str,
        cedula: str,
        nombre: str,
        telefono: str,
        direccion: str,
    ) -> int:
        sql = text(
            """
            UPDATE auxilios.fun_reclamantes
            SET
                tipoid_beneficiario = :tipoid,
                identificacion = :cedula,
                nombre_beneficiario = :nombre,
                direccion = :direccion,
                telefono_beneficiario = :telefono
            WHERE id_ben = :id_ben
            """
        )
        with self.engine.begin() as conn:
            result = conn.execute(
                sql,
                {
                    "id_ben": id_ben,
                    "tipoid": tipoid,
                    "cedula": cedula,
                    "nombre": nombre,
                    "direccion": direccion,
                    "telefono": telefono,
                },
            )
            return result.rowcount or 0

    def count_reclamante_exists(self, identificacion: str) -> int:
        sql = text(
            """
            SELECT COUNT(*)
            FROM auxilios.fun_reclamantes
            WHERE trim(identificacion) = trim(:identificacion)
            """
        )
        with self.engine.connect() as conn:
            return int(conn.execute(sql, {"identificacion": identificacion}).scalar_one() or 0)

    def count_reclamante_modificable(self, identificacion: str) -> int:
        sql = text(
            """
            SELECT COUNT(*)
            FROM auxilios.fun_reclamantes
            WHERE identificacion = :identificacion
              AND (
                estado_reclamante NOT IN (
                    'Transferencia Generada',
                    'Interfaz Generada',
                    'Cheque Informado',
                    'AUXILIO DE PENSIONADO APROBADO',
                    'AUXILIO APROBADO CON SOPORTE OK'
                )
                OR estado_reclamante IS NULL
              )
            """
        )
        with self.engine.connect() as conn:
            return int(conn.execute(sql, {"identificacion": identificacion}).scalar_one() or 0)

    def mark_reclamante_eliminado(self, *, id_ben: str) -> int:
        sql = text(
            """
            UPDATE auxilios.fun_reclamantes
            SET estado_reclamante = 'Eliminado'
            WHERE id_ben = :id_ben
            """
        )
        with self.engine.begin() as conn:
            result = conn.execute(sql, {"id_ben": id_ben})
            return result.rowcount or 0

    def get_tramite_estado(self, tramite: str) -> str | None:
        sql = text(
            """
            SELECT estado_flujo
            FROM auxilios.fun_solicitudes
            WHERE tramite = :tramite
            """
        )
        with self.engine.connect() as conn:
            return conn.execute(sql, {"tramite": tramite}).scalar_one_or_none()

    def count_reclamantes_tramitados(self, tramite: str) -> int:
        sql = text(
            """
            SELECT COUNT(*)
            FROM auxilios.not_reclamantes
            WHERE tramite = :tramite
              AND estado_reclamante IN (
                'Transferencia Generada',
                'Interfaz Generada',
                'Cheque Informado',
                'AUXILIO DE PENSIONADO APROBADO',
                'AUXILIO APROBADO CON SOPORTE OK'
              )
            """
        )
        with self.engine.connect() as conn:
            return int(conn.execute(sql, {"tramite": tramite}).scalar_one() or 0)

    def modificar_tramite(self, *, tramite: str, accion: int) -> int:
        with self.engine.begin() as conn:
            if accion == 1:
                conn.execute(
                    text(
                        """
                        UPDATE auxilios.fun_reclamantes
                        SET estado_reclamante = 'Eliminado'
                        WHERE tramite = :tramite
                        """
                    ),
                    {"tramite": tramite},
                )
                result = conn.execute(
                    text(
                        """
                        UPDATE auxilios.fun_solicitudes
                        SET estado_flujo = 'Eliminado'
                        WHERE tramite = :tramite
                        """
                    ),
                    {"tramite": tramite},
                )
                return result.rowcount or 0

            if accion == 2:
                for stmt in (
                    "DELETE FROM auxilios.fun_actividades WHERE tramite = :tramite",
                    "DELETE FROM auxilios.fun_pagos_reclamantes WHERE tramite = :tramite",
                    "DELETE FROM auxilios.fun_reclamante_datos_rechazo WHERE tramite = :tramite",
                    "DELETE FROM auxilios.fun_reclamante_llamada_cheque WHERE tramite = :tramite",
                    "DELETE FROM auxilios.fun_reclamantes_aprobados WHERE tramite = :tramite",
                    "DELETE FROM auxilios.fun_gestion_funeraria WHERE tramite = :tramite",
                    "DELETE FROM auxilios.fun_gestion_reclamante WHERE tramite = :tramite",
                ):
                    conn.execute(text(stmt), {"tramite": tramite})

                conn.execute(
                    text(
                        """
                        UPDATE auxilios.fun_reclamantes
                        SET estado_reclamante = NULL
                        WHERE tramite = :tramite
                        """
                    ),
                    {"tramite": tramite},
                )
                result = conn.execute(
                    text(
                        """
                        UPDATE auxilios.fun_solicitudes
                        SET estado_flujo = 'Solicitado'
                        WHERE tramite = :tramite
                        """
                    ),
                    {"tramite": tramite},
                )
                return result.rowcount or 0

        return 0

    def has_tramite_solicitud_relation(self, solicitud_as: str) -> bool:
        sql = text(
            """
            SELECT 1
            FROM auxilios.fun_tramite_solicitud
            WHERE solicitud_as = :solicitud_as
            ORDER BY fecha_insert DESC
            LIMIT 1
            """
        )
        with self.engine.connect() as conn:
            row = conn.execute(sql, {"solicitud_as": solicitud_as}).scalar_one_or_none()
            return row is not None

    def insert_devolucion_analisis(self, *, tramite: str, reclamante: str, observacion: str, usuario: str) -> int:
        sql = text(
            """
            INSERT INTO auxilios.fun_devoluciones_analisis
            (tramite, reclamante, observacion, proceso, usuario_devolucion)
            VALUES
            (:tramite, :reclamante, :observacion, 'AUXILIOS FUNERARIOS', :usuario)
            """
        )
        with self.engine.begin() as conn:
            result = conn.execute(
                sql,
                {
                    "tramite": tramite,
                    "reclamante": reclamante,
                    "observacion": observacion,
                    "usuario": usuario,
                },
            )
            return result.rowcount or 0

    def update_estado_reclamante_identificacion(self, *, tramite: str, identificacion: str, estado: str) -> int:
        sql = text(
            """
            UPDATE auxilios.fun_reclamantes
            SET estado_reclamante = :estado
            WHERE tramite = :tramite
              AND identificacion = :identificacion
            """
        )
        with self.engine.begin() as conn:
            result = conn.execute(
                sql,
                {"tramite": tramite, "identificacion": identificacion, "estado": estado},
            )
            return result.rowcount or 0

    def get_forma_pago_reclamante(self, *, tramite: str, identificacion: str) -> str | None:
        sql = text(
            """
            SELECT forma_pago
            FROM auxilios.fun_pagos_reclamantes
            WHERE tramite = :tramite
              AND id_reclamante = :identificacion
            ORDER BY id DESC
            LIMIT 1
            """
        )
        with self.engine.connect() as conn:
            return conn.execute(sql, {"tramite": tramite, "identificacion": identificacion}).scalar_one_or_none()

    def insert_rechazo_pago(self, *, tramite: str, beneficiario: str, usuario: str, observacion: str) -> int:
        sql = text(
            """
            INSERT INTO auxilios.fun_rechazospagos (tramite, beneficiario, usuario, observacion)
            VALUES (:tramite, :beneficiario, :usuario, :observacion)
            """
        )
        with self.engine.begin() as conn:
            result = conn.execute(
                sql,
                {
                    "tramite": tramite,
                    "beneficiario": beneficiario,
                    "usuario": usuario,
                    "observacion": observacion,
                },
            )
            return result.rowcount or 0

    def mark_aprueba_pago_jefe(self, tramites: Sequence[str]) -> int:
        if not tramites:
            return 0
        total = 0
        sql = text(
            """
            UPDATE auxilios.fun_reclamantes
            SET estado_reclamante = 'Aprueba Pago Jefe'
            WHERE estado_reclamante IN ('APROBADO', 'Respuesta Generica No Exitosa')
              AND tramite = :tramite
            """
        )
        with self.engine.begin() as conn:
            for tramite in tramites:
                total += conn.execute(sql, {"tramite": tramite}).rowcount or 0
        return total

    def update_estado_solicitud(self, *, tramite: str, estado_flujo: str) -> int:
        sql = text(
            """
            UPDATE auxilios.fun_solicitudes
            SET estado_flujo = :estado_flujo
            WHERE tramite = :tramite
              AND proceso = 'AUXILIOS FUNERARIOS'
            """
        )
        with self.engine.begin() as conn:
            result = conn.execute(sql, {"tramite": tramite, "estado_flujo": estado_flujo})
            return result.rowcount or 0

    def update_forma_pago_by_id_ben(self, *, tramite: str, id_ben: str, forma_pago: str) -> int:
        sql = text(
            """
            UPDATE auxilios.fun_pagos_reclamantes
            SET forma_pago = :forma_pago
            WHERE tramite = :tramite
              AND id_reclamante = (
                SELECT trim(identificacion)
                FROM auxilios.fun_reclamantes
                WHERE id_ben = :id_ben
                LIMIT 1
              )
            """
        )
        with self.engine.begin() as conn:
            result = conn.execute(
                sql,
                {"tramite": tramite, "id_ben": id_ben, "forma_pago": forma_pago},
            )
            return result.rowcount or 0

    def insert_gestion_funeraria(
        self,
        *,
        id_reclamante: str,
        tramite: str,
        estado: str,
        contacto_gestion: str,
        observacion: str,
        reclama_paga: str,
        poder: str,
        pagado_por: str,
        usuario_gestion: str,
        plan_exequial: str,
        numero_plan: str,
        titular_fallecido: str,
        nombre_funeraria: str,
    ) -> int:
        sql = text(
            """
            INSERT INTO auxilios.fun_gestion_funeraria
            (
                id_reclamante, tramite, estado, contacto_gestion, observacion, reclama_paga,
                poder, pagado_por, usuario_gestion, plan_exequial, numero_plan, titular_fallecido,
                nombre_funeraria, proceso
            )
            VALUES
            (
                :id_reclamante, :tramite, :estado, :contacto_gestion, :observacion, :reclama_paga,
                :poder, :pagado_por, :usuario_gestion, :plan_exequial, :numero_plan, :titular_fallecido,
                :nombre_funeraria, 'AUXILIOS FUNERARIOS'
            )
            """
        )
        with self.engine.begin() as conn:
            result = conn.execute(
                sql,
                {
                    "id_reclamante": id_reclamante,
                    "tramite": tramite,
                    "estado": estado,
                    "contacto_gestion": contacto_gestion,
                    "observacion": observacion,
                    "reclama_paga": reclama_paga,
                    "poder": poder,
                    "pagado_por": pagado_por,
                    "usuario_gestion": usuario_gestion,
                    "plan_exequial": plan_exequial,
                    "numero_plan": numero_plan,
                    "titular_fallecido": titular_fallecido,
                    "nombre_funeraria": nombre_funeraria,
                },
            )
            return result.rowcount or 0

    def insert_exequial_tramite(
        self, *, tramite: str, plan_exequial: str, numero_plan: str, titular_fallecido: str, nombre_funeraria: str
    ) -> int:
        sql = text(
            """
            INSERT INTO auxilios.exequial_tramite
            VALUES (:tramite, :plan_exequial, :numero_plan, :titular_fallecido, :nombre_funeraria)
            """
        )
        with self.engine.begin() as conn:
            result = conn.execute(
                sql,
                {
                    "tramite": tramite,
                    "plan_exequial": plan_exequial,
                    "numero_plan": numero_plan,
                    "titular_fallecido": titular_fallecido,
                    "nombre_funeraria": nombre_funeraria,
                },
            )
            return result.rowcount or 0

    def insert_gestion_reclamante(
        self,
        *,
        tramite: str,
        id_reclamante: str,
        estado: str,
        usuario: str,
        observacion: str,
        modificar_fpago: bool,
    ) -> int:
        if modificar_fpago:
            sql = text(
                """
                INSERT INTO auxilios.fun_gestion_reclamante
                (tramite, id_reclamante, confirmacta, modificapago, estado, user_gestion, proceso, observacion)
                VALUES
                (:tramite, :id_reclamante, 'NO', 'SI', 'Confirmado', :usuario, 'AUXILIOS FUNERARIOS', :observacion)
                """
            )
            params = {
                "tramite": tramite,
                "id_reclamante": id_reclamante,
                "usuario": usuario,
                "observacion": observacion,
            }
        else:
            sql = text(
                """
                INSERT INTO auxilios.fun_gestion_reclamante
                (tramite, id_reclamante, estado, user_gestion, proceso, observacion)
                VALUES
                (:tramite, :id_reclamante, :estado, :usuario, 'AUXILIOS FUNERARIOS', :observacion)
                """
            )
            params = {
                "tramite": tramite,
                "id_reclamante": id_reclamante,
                "estado": estado,
                "usuario": usuario,
                "observacion": observacion,
            }

        with self.engine.begin() as conn:
            result = conn.execute(sql, params)
            return result.rowcount or 0

    def insert_llamada_cheque(
        self, *, tramite: str, id_reclamante: str, id_respuesta: str, observacion: str, usuario: str
    ) -> int:
        sql = text(
            """
            INSERT INTO auxilios.fun_reclamante_llamada_cheque
            (tramite, id_reclamante, id_respuesta, observacion, usuario)
            VALUES
            (:tramite, :id_reclamante, :id_respuesta, :observacion, :usuario)
            """
        )
        with self.engine.begin() as conn:
            result = conn.execute(
                sql,
                {
                    "tramite": tramite,
                    "id_reclamante": id_reclamante,
                    "id_respuesta": id_respuesta,
                    "observacion": observacion,
                    "usuario": usuario,
                },
            )
            return result.rowcount or 0

    def insert_llamada_transferencia(
        self, *, tramite: str, id_reclamante: str, estado: str, observacion: str, usuario: str
    ) -> int:
        sql = text(
            """
            INSERT INTO auxilios.fun_reclamante_llamada_transferencia
            (tramite, id_reclamante, estado, observacion, usuario)
            VALUES
            (:tramite, :id_reclamante, :estado, :observacion, :usuario)
            """
        )
        with self.engine.begin() as conn:
            result = conn.execute(
                sql,
                {
                    "tramite": tramite,
                    "id_reclamante": id_reclamante,
                    "estado": estado,
                    "observacion": observacion,
                    "usuario": usuario,
                },
            )
            return result.rowcount or 0

    def list_reclamantes_origen_fondos(self, *, tramite: str) -> Sequence[dict]:
        sql = text(
            """
            SELECT
                fr.id_ben,
                fr.tramite,
                fr.nombre_beneficiario,
                fr.identificacion,
                fr.telefono_beneficiario,
                fpr.forma_pago
            FROM auxilios.fun_pagos_reclamantes AS fpr
            INNER JOIN auxilios.fun_reclamantes AS fr
                ON fr.identificacion = fpr.id_reclamante
               AND fr.estado_reclamante = 'Interfaz Generada'
               AND fr.tramite = :tramite
            WHERE fpr.tramite = :tramite
              AND fpr.forma_pago = 'Cheque'
              AND fpr.proceso = 'AUXILIOS FUNERARIOS'
            ORDER BY fr.id_ben
            """
        )
        with self.engine.connect() as conn:
            rows = conn.execute(sql, {"tramite": tramite}).mappings().all()
            return [dict(r) for r in rows]

    def list_respuestas_llamada(self) -> Sequence[dict]:
        sql = text(
            """
            SELECT id, respuesta
            FROM auxilios.fun_respuesta_llamada
            ORDER BY id
            """
        )
        with self.engine.connect() as conn:
            rows = conn.execute(sql).mappings().all()
            return [dict(r) for r in rows]

    def confirmar_pago_reclamante_origen_fondos(self, *, tramite: str, id_reclamante: str) -> int:
        sql = text(
            """
            UPDATE auxilios.fun_pagos_reclamantes
            SET estado = 'Confirmado'
            WHERE tramite = :tramite
              AND (
                    id_reclamante = :id_reclamante
                    OR id_reclamante = (
                        SELECT trim(identificacion)
                        FROM auxilios.fun_reclamantes
                        WHERE id_ben = :id_reclamante
                        LIMIT 1
                    )
              )
            """
        )
        with self.engine.begin() as conn:
            result = conn.execute(sql, {"tramite": tramite, "id_reclamante": id_reclamante})
            return result.rowcount or 0

    def update_estado_reclamante_by_id_ben(self, *, id_ben: str, estado: str) -> int:
        sql = text(
            """
            UPDATE auxilios.fun_reclamantes
            SET estado_reclamante = :estado
            WHERE id_ben = :id_ben
            """
        )
        with self.engine.begin() as conn:
            result = conn.execute(sql, {"id_ben": id_ben, "estado": estado})
            return result.rowcount or 0

    def exists_banco_codigo(self, codigo: str) -> bool:
        sql = text(
            """
            SELECT 1
            FROM auxilios.fun_bancos
            WHERE codigo = :codigo
            LIMIT 1
            """
        )
        with self.engine.connect() as conn:
            return conn.execute(sql, {"codigo": codigo}).scalar_one_or_none() is not None

    def insert_banco(self, *, codigo: str, banco: str) -> int:
        sql = text(
            """
            INSERT INTO auxilios.fun_bancos (id, codigo, nombre)
            VALUES (:id, :codigo, upper(:nombre))
            """
        )
        with self.engine.begin() as conn:
            result = conn.execute(sql, {"id": codigo, "codigo": codigo, "nombre": banco})
            return result.rowcount or 0

    def update_banco_nombre(self, *, codigo: str, banco: str) -> int:
        sql = text(
            """
            UPDATE auxilios.fun_bancos
            SET nombre = :nombre
            WHERE codigo = :codigo
            """
        )
        with self.engine.begin() as conn:
            result = conn.execute(sql, {"codigo": codigo, "nombre": banco})
            return result.rowcount or 0

    def update_pago_rechazo(self, *, id_pago: str, numero_cuenta: str, banco: str, tipo_cuenta: str) -> int:
        sql = text(
            """
            UPDATE auxilios.fun_pagos_reclamantes
            SET numero_cuenta = :numero_cuenta,
                entidad_bancaria = :banco,
                tipo_cuenta = :tipo_cuenta
            WHERE id = :id_pago
            """
        )
        with self.engine.begin() as conn:
            result = conn.execute(
                sql,
                {
                    "id_pago": id_pago,
                    "numero_cuenta": numero_cuenta,
                    "banco": banco,
                    "tipo_cuenta": tipo_cuenta,
                },
            )
            return result.rowcount or 0

    def insert_actualiza_rechazo_log(
        self,
        *,
        id_ben: str,
        id_pago: str,
        cuenta_old: str,
        cuenta_new: str,
        banco_old: str,
        banco_new: str,
        tipo_cta_old: str,
        tipo_cta_new: str,
        usuario: str,
    ) -> int:
        sql = text(
            """
            INSERT INTO auxilios.fun_actualiza_rechazo
            (id_ben, id_pago, cuenta_old, cuenta_new, banco_old, banco_new, tipo_cta_old, tipo_cta_new, usuario_actualiza)
            VALUES
            (:id_ben, :id_pago, :cuenta_old, :cuenta_new, :banco_old, :banco_new, :tipo_cta_old, :tipo_cta_new, :usuario)
            """
        )
        with self.engine.begin() as conn:
            result = conn.execute(
                sql,
                {
                    "id_ben": id_ben,
                    "id_pago": id_pago,
                    "cuenta_old": cuenta_old,
                    "cuenta_new": cuenta_new,
                    "banco_old": banco_old,
                    "banco_new": banco_new,
                    "tipo_cta_old": tipo_cta_old,
                    "tipo_cta_new": tipo_cta_new,
                    "usuario": usuario,
                },
            )
            return result.rowcount or 0

    def get_reclamante_by_id_ben(self, id_ben: str) -> dict | None:
        sql = text(
            """
            SELECT id_ben, tramite, tipoid_beneficiario, identificacion, nombre_beneficiario, direccion, telefono_beneficiario
            FROM auxilios.fun_reclamantes
            WHERE id_ben = :id_ben
            LIMIT 1
            """
        )
        with self.engine.connect() as conn:
            row = conn.execute(sql, {"id_ben": id_ben}).mappings().first()
            return dict(row) if row else None

    def exists_rechazo_datos(self, tramite: str) -> bool:
        sql = text(
            """
            SELECT 1
            FROM auxilios.fun_reclamante_datos_rechazo
            WHERE tramite = :tramite
            LIMIT 1
            """
        )
        with self.engine.connect() as conn:
            return conn.execute(sql, {"tramite": tramite}).scalar_one_or_none() is not None

    def insert_rechazo_datos(
        self, *, tramite: str, semanas: str, fidelidad: str, fecha_muerte: str, usuario: str
    ) -> int:
        sql = text(
            """
            INSERT INTO auxilios.fun_reclamante_datos_rechazo
            (tramite, semanas, fidelidad, fecha_muerte, usuario)
            VALUES
            (:tramite, :semanas, :fidelidad, :fecha_muerte, :usuario)
            """
        )
        with self.engine.begin() as conn:
            result = conn.execute(
                sql,
                {
                    "tramite": tramite,
                    "semanas": semanas,
                    "fidelidad": fidelidad,
                    "fecha_muerte": fecha_muerte,
                    "usuario": usuario,
                },
            )
            return result.rowcount or 0

    def get_banco_by_codigo(self, codigo: str) -> dict | None:
        sql = text(
            """
            SELECT id, codigo, nombre
            FROM auxilios.fun_bancos
            WHERE codigo = :codigo
            LIMIT 1
            """
        )
        with self.engine.connect() as conn:
            row = conn.execute(sql, {"codigo": codigo}).mappings().first()
            return dict(row) if row else None

    def _status_in_clause(self, statuses: Sequence[str]) -> tuple[str, dict[str, str]]:
        placeholders = []
        params: dict[str, str] = {}
        for idx, status in enumerate(statuses):
            key = f"st_{idx}"
            placeholders.append(f":{key}")
            params[key] = status
        return ", ".join(placeholders), params

    def get_reporte_mensual(self, year: int, entidad: str | None) -> list[dict]:
        entities = [entidad] if entidad and entidad in self._report_cfg else list(self._report_cfg.keys())
        items: list[dict] = []
        with self.engine.connect() as conn:
            for ent in entities:
                cfg = self._report_cfg[ent]
                in_clause, st_params = self._status_in_clause(cfg["statuses"])
                sql = text(
                    f"""
                    SELECT
                        extract(month from fpr.fecha_insert)::int AS month_num,
                        SUM(fpr.valor_reconocido) AS suma_de_valor,
                        COUNT(fpr.id) AS cuenta_id
                    FROM auxilios.fun_reclamantes fr
                    INNER JOIN auxilios.fun_pagos_reclamantes fpr
                      ON fr.tramite = fpr.tramite
                     AND fr.identificacion = fpr.id_reclamante
                    WHERE extract(year from fr.fecha_insert) = :year
                      AND fpr.nombre_aseguradora = :entidad
                      AND fr.estado_reclamante IN ({in_clause})
                    GROUP BY extract(month from fpr.fecha_insert)::int
                    ORDER BY month_num
                    """
                )
                rows = conn.execute(
                    sql,
                    {"year": year, "entidad": cfg["db_name"], **st_params},
                ).mappings().all()
                for row in rows:
                    items.append(
                        {
                            "entidad": ent,
                            "month_num": int(row["month_num"] or 0),
                            "suma_de_valor": float(row["suma_de_valor"] or 0),
                            "cuenta_id": int(row["cuenta_id"] or 0),
                        }
                    )
        return items

    def get_reporte_detalle_mes(self, year: int, month_num: int, entidad: str) -> list[dict]:
        if entidad not in self._report_cfg:
            return []
        cfg = self._report_cfg[entidad]
        in_clause, st_params = self._status_in_clause(cfg["statuses"])
        sql = text(
            f"""
            SELECT
                extract(day from fpr.fecha_insert)::int AS day_num,
                SUM(fpr.valor_reconocido) AS suma_de_valor,
                COUNT(fpr.id) AS cuenta_id
            FROM auxilios.fun_reclamantes fr
            INNER JOIN auxilios.fun_pagos_reclamantes fpr
              ON fr.tramite = fpr.tramite
             AND fr.identificacion = fpr.id_reclamante
            WHERE extract(year from fr.fecha_insert) = :year
              AND extract(month from fpr.fecha_insert) = :month_num
              AND fpr.nombre_aseguradora = :entidad
              AND fr.estado_reclamante IN ({in_clause})
            GROUP BY extract(day from fpr.fecha_insert)::int
            ORDER BY day_num
            """
        )
        with self.engine.connect() as conn:
            rows = conn.execute(
                sql,
                {"year": year, "month_num": month_num, "entidad": cfg["db_name"], **st_params},
            ).mappings().all()
        return [
            {
                "entidad": entidad,
                "day_num": int(r["day_num"] or 0),
                "suma_de_valor": float(r["suma_de_valor"] or 0),
                "cuenta_id": int(r["cuenta_id"] or 0),
            }
            for r in rows
        ]

    def get_id_ben_for_rechazo(self, *, tramite: str, identificacion: str, origen: str) -> str | None:
        sql = text(
            """
            SELECT recl.id_ben
            FROM auxilios.fun_reclamantes recl
            INNER JOIN auxilios.fun_pagos_reclamantes pag
              ON recl.tramite = pag.tramite
             AND recl.identificacion = pag.id_reclamante
            WHERE recl.tramite = :tramite
              AND recl.identificacion = :identificacion
              AND pag.origen = :origen
            LIMIT 1
            """
        )
        with self.engine.connect() as conn:
            return conn.execute(
                sql,
                {"tramite": tramite, "identificacion": identificacion, "origen": origen},
            ).scalar_one_or_none()

    def get_respuesta_banco_cargado(self, *, identificacion: str, causal: str) -> dict | None:
        sql = text(
            """
            SELECT na
            FROM auxilios.fun_respuesta_banco
            WHERE nit_reclamante ILIKE :ident_like
              AND codigo_respuesta = :causal
              AND estado = 'Cargado'
            ORDER BY na DESC
            LIMIT 1
            """
        )
        with self.engine.connect() as conn:
            row = conn.execute(
                sql,
                {"ident_like": f"{identificacion}%", "causal": causal},
            ).mappings().first()
            return dict(row) if row else None

    def exists_respuesta_banco_nombre_archivo(self, nombre_archivo: str) -> bool:
        sql = text(
            """
            SELECT 1
            FROM auxilios.fun_respuesta_banco
            WHERE nombre_archivo = :nombre_archivo
            LIMIT 1
            """
        )
        with self.engine.connect() as conn:
            return conn.execute(sql, {"nombre_archivo": nombre_archivo}).scalar_one_or_none() is not None

    def insert_respuesta_banco(self, *, row: dict) -> int:
        sql = text(
            """
            INSERT INTO auxilios.fun_respuesta_banco
            (
                nit_pagadora,
                fecha_transmision,
                secuencia_pago,
                tipo_registro,
                nit_reclamante,
                nombre_reclamante,
                codigo_banco,
                cuenta_reclamante,
                cuenta_local,
                tipo_transaccion,
                valor,
                concepto,
                codigo_respuesta,
                numero_cheque,
                fecha_aplicacion,
                nombre_archivo,
                usuario_carga,
                estado
            )
            VALUES
            (
                :nit_pagadora,
                :fecha_transmision,
                :secuencia_pago,
                :tipo_registro,
                :nit_reclamante,
                :nombre_reclamante,
                :codigo_banco,
                :cuenta_reclamante,
                :cuenta_local,
                :tipo_transaccion,
                :valor,
                :concepto,
                :codigo_respuesta,
                :numero_cheque,
                :fecha_aplicacion,
                :nombre_archivo,
                :usuario_carga,
                :estado
            )
            """
        )
        with self.engine.begin() as conn:
            result = conn.execute(sql, row)
            return result.rowcount or 0

    def list_respuesta_banco_pendientes_cruce(self) -> list[dict]:
        sql = text(
            """
            SELECT
                txt.na,
                txt.nit_reclamante,
                txt.codigo_respuesta,
                cod.descripcion,
                cod.estado_flujo
            FROM auxilios.fun_respuesta_banco AS txt
            LEFT JOIN auxilios.fun_codigos_respuestas AS cod
              ON txt.codigo_respuesta = cod.cod_respuesta
            WHERE txt.estado = 'Cargado'
            """
        )
        with self.engine.connect() as conn:
            rows = conn.execute(sql).mappings().all()
        return [dict(r) for r in rows]

    def list_reclamantes_by_identificacion_y_estado(self, *, identificacion: str, estados: list[str]) -> list[dict]:
        if not estados:
            return []
        in_clause, params = self._status_in_clause(estados)
        sql = text(
            f"""
            SELECT id_ben, tramite, identificacion
            FROM auxilios.fun_reclamantes
            WHERE identificacion = :identificacion
              AND estado_reclamante IN ({in_clause})
            """
        )
        bind = {"identificacion": identificacion, **params}
        with self.engine.connect() as conn:
            rows = conn.execute(sql, bind).mappings().all()
        return [dict(r) for r in rows]

    def update_respuesta_banco_estado(self, *, na: int, estado: str) -> int:
        sql = text(
            """
            UPDATE auxilios.fun_respuesta_banco
            SET estado = :estado
            WHERE na = :na
            """
        )
        with self.engine.begin() as conn:
            result = conn.execute(sql, {"na": na, "estado": estado})
            return result.rowcount or 0

    def insert_causal_rechazo(self, *, id_reclamante: str, cod_respuesta: str, id_archivo: int) -> int:
        sql = text(
            """
            INSERT INTO auxilios.fun_causal_rechazo (id_reclamante, cod_respuesta, id_archivo)
            VALUES (:id_reclamante, :cod_respuesta, :id_archivo)
            """
        )
        with self.engine.begin() as conn:
            result = conn.execute(
                sql,
                {
                    "id_reclamante": id_reclamante,
                    "cod_respuesta": cod_respuesta,
                    "id_archivo": id_archivo,
                },
            )
            return result.rowcount or 0

    def insert_log_activacion_rechazos(
        self, *, tramite: str, reclamante: str, causal: str, archivo: int, usuario: str
    ) -> int:
        sql = text(
            """
            INSERT INTO auxilios.fun_log_activacion_rechazos
            (tramite, reclamante, causal, archivo, usuario_activacion)
            VALUES
            (:tramite, :reclamante, :causal, :archivo, :usuario)
            """
        )
        with self.engine.begin() as conn:
            result = conn.execute(
                sql,
                {
                    "tramite": tramite,
                    "reclamante": reclamante,
                    "causal": causal,
                    "archivo": archivo,
                    "usuario": usuario,
                },
            )
            return result.rowcount or 0

    def get_afiliado_by_tramite(self, tramite: str) -> str | None:
        sql = text(
            """
            SELECT trim(id_afiliado) AS id_afiliado
            FROM auxilios.fun_solicitudes
            WHERE tramite = :tramite
            LIMIT 1
            """
        )
        with self.engine.connect() as conn:
            return conn.execute(sql, {"tramite": tramite}).scalar_one_or_none()

    def has_soporte_egreso_hoy(self, cedula: str) -> bool:
        sql = text(
            """
            SELECT 1
            FROM tblpnpension
            WHERE lt = '999999'
              AND lo = 'AUX-F'
              AND ce = :cedula
              AND fp = to_char(current_date, 'YYYYMMDD')
            LIMIT 1
            """
        )
        with self.engine.connect() as conn:
            return conn.execute(sql, {"cedula": cedula}).scalar_one_or_none() is not None

    def get_origen_pago(self, *, tramite: str, identificacion: str) -> str | None:
        sql = text(
            """
            SELECT origen
            FROM auxilios.fun_pagos_reclamantes
            WHERE tramite = :tramite
              AND id_reclamante = :identificacion
            ORDER BY id DESC
            LIMIT 1
            """
        )
        with self.engine.connect() as conn:
            return conn.execute(
                sql,
                {"tramite": tramite, "identificacion": identificacion},
            ).scalar_one_or_none()

    def ejecutar_cierre_masivo_operador(
        self,
        *,
        usuario: str,
        estado_origen: str,
        estado_destino: str,
        estado_log_actual: str,
    ) -> dict:
        if not self._table_exists("auxilios", "fun_log_cierre_masivo"):
            return {"procesados": 0, "actualizados": 0}
        sel = text(
            """
            SELECT na, tramite, id_reclamante
            FROM auxilios.fun_log_cierre_masivo
            WHERE estado = 'Validado'
              AND usuario_carga = :usuario
            ORDER BY na
            """
        )
        upd_recl = text(
            """
            UPDATE auxilios.fun_reclamantes
            SET estado_reclamante = :estado_destino
            WHERE tramite = :tramite
              AND identificacion = :id_reclamante
            """
        )
        upd_log = text(
            """
            UPDATE auxilios.fun_log_cierre_masivo
            SET estado = 'Aprobado Operador'
            WHERE na = :na
            """
        )
        ins_audit = text(
            """
            INSERT INTO auxilios.fun_log_reclamante
            (tramite, id_reclamante, usuario, estado_anterior, estado_actual)
            VALUES
            (:tramite, :id_reclamante, :usuario, :estado_anterior, :estado_actual)
            """
        )
        procesados = 0
        actualizados = 0
        with self.engine.begin() as conn:
            rows = conn.execute(sel, {"usuario": usuario}).mappings().all()
            for row in rows:
                procesados += 1
                params = {
                    "tramite": str(row["tramite"]),
                    "id_reclamante": str(row["id_reclamante"]),
                }
                result = conn.execute(
                    upd_recl,
                    {"estado_destino": estado_destino, **params},
                )
                actualizados += result.rowcount or 0
                conn.execute(
                    ins_audit,
                    {
                        "usuario": usuario,
                        "estado_anterior": estado_origen,
                        "estado_actual": estado_log_actual,
                        **params,
                    },
                )
                conn.execute(upd_log, {"na": int(row["na"])})
        return {"procesados": procesados, "actualizados": actualizados}

    def regresa_estados_masivo(self, *, usuario: str, estado_regreso: str) -> int:
        if not self._table_exists("auxilios", "fun_log_cierre_masivo"):
            return 0
        sql = text(
            """
            UPDATE auxilios.fun_reclamantes AS fr
            SET estado_reclamante = :estado_regreso
            FROM auxilios.fun_log_cierre_masivo AS l
            WHERE l.usuario_carga = :usuario
              AND l.fecha_carga::date = current_date
              AND fr.tramite = l.tramite
              AND fr.identificacion = l.id_reclamante
            """
        )
        with self.engine.begin() as conn:
            result = conn.execute(
                sql,
                {"usuario": usuario, "estado_regreso": estado_regreso},
            )
            return result.rowcount or 0

    def delete_log_cierre_masivo_en_validacion_usuario(self, usuario: str) -> int:
        if not self._table_exists("auxilios", "fun_log_cierre_masivo"):
            return 0
        sql = text(
            """
            DELETE FROM auxilios.fun_log_cierre_masivo
            WHERE usuario_carga = :usuario
              AND estado = 'En Validacion'
            """
        )
        with self.engine.begin() as conn:
            result = conn.execute(sql, {"usuario": usuario})
            return result.rowcount or 0

    def delete_log_cierre_masivo_en_validacion_anteriores(self) -> int:
        if not self._table_exists("auxilios", "fun_log_cierre_masivo"):
            return 0
        sql = text(
            """
            DELETE FROM auxilios.fun_log_cierre_masivo
            WHERE estado = 'En Validacion'
              AND fecha_carga::date < current_date
            """
        )
        with self.engine.begin() as conn:
            result = conn.execute(sql)
            return result.rowcount or 0

    def exists_log_cierre_masivo_duplicado(self, *, tramite: str, id_reclamante: str, usuario: str) -> bool:
        if not self._table_exists("auxilios", "fun_log_cierre_masivo"):
            return False
        sql = text(
            """
            SELECT 1
            FROM auxilios.fun_log_cierre_masivo
            WHERE tramite = :tramite
              AND id_reclamante = :id_reclamante
              AND estado = 'En Validacion'
              AND usuario_carga = :usuario
            LIMIT 1
            """
        )
        with self.engine.connect() as conn:
            return conn.execute(
                sql,
                {"tramite": tramite, "id_reclamante": id_reclamante, "usuario": usuario},
            ).scalar_one_or_none() is not None

    def insert_log_cierre_masivo_en_validacion(
        self,
        *,
        tramite: str,
        id_reclamante: str,
        valor: str,
        cod_banco: str,
        tipo_cta: str,
        cuenta: str,
        usuario: str,
    ) -> int:
        if not self._table_exists("auxilios", "fun_log_cierre_masivo"):
            return 0
        sql = text(
            """
            INSERT INTO auxilios.fun_log_cierre_masivo
            (tramite, id_reclamante, valor, cod_banco, tipo_cta, cuenta, usuario_carga, estado)
            VALUES
            (:tramite, :id_reclamante, :valor, :cod_banco, :tipo_cta, :cuenta, :usuario, 'En Validacion')
            """
        )
        with self.engine.begin() as conn:
            result = conn.execute(
                sql,
                {
                    "tramite": tramite,
                    "id_reclamante": id_reclamante,
                    "valor": valor,
                    "cod_banco": cod_banco,
                    "tipo_cta": tipo_cta,
                    "cuenta": cuenta,
                    "usuario": usuario,
                },
            )
            return result.rowcount or 0

    def mark_log_cierre_masivo_validado_hoy(self, usuario: str) -> int:
        if not self._table_exists("auxilios", "fun_log_cierre_masivo"):
            return 0
        sql = text(
            """
            UPDATE auxilios.fun_log_cierre_masivo
            SET estado = 'Validado'
            WHERE usuario_carga = :usuario
              AND estado = 'En Validacion'
              AND fecha_carga::date = current_date
            """
        )
        with self.engine.begin() as conn:
            result = conn.execute(sql, {"usuario": usuario})
            return result.rowcount or 0

    def validate_masivo_row(
        self,
        *,
        tramite: str,
        id_afiliado: str,
        id_reclamante: str,
        valor: str,
        banco: str,
        tipo_cta: str,
        cta: str,
        asulado: bool,
    ) -> str | None:
        estado_solicitud = "APROBADO ASULADO" if asulado else "APROBADO FIDUCIA"
        estado_reclamante = "APROBADO ASULADO" if asulado else "APROBADO FIDUCIA"
        bandeja = "asulado" if asulado else "fiducia"

        q1 = text(
            """
            SELECT 1
            FROM auxilios.fun_solicitudes
            WHERE tramite = :tramite
              AND estado_flujo = :estado_solicitud
            LIMIT 1
            """
        )
        q2 = text(
            """
            SELECT 1
            FROM auxilios.fun_solicitudes
            WHERE tramite = :tramite
              AND id_afiliado = :id_afiliado
            LIMIT 1
            """
        )
        q3 = text(
            """
            SELECT 1
            FROM auxilios.fun_reclamantes
            WHERE tramite = :tramite
              AND identificacion = :id_reclamante
              AND estado_reclamante = :estado_reclamante
            LIMIT 1
            """
        )
        q4 = text(
            """
            SELECT 1
            FROM auxilios.fun_bancos
            WHERE codigo = :banco
            LIMIT 1
            """
        )
        q5 = text(
            """
            SELECT 1
            FROM auxilios.fun_reclamantes AS rec
            INNER JOIN auxilios.fun_solicitudes AS sol
              ON rec.tramite = sol.tramite
            INNER JOIN auxilios.fun_pagos_reclamantes AS pago
              ON rec.identificacion = pago.id_reclamante
             AND rec.tramite = pago.tramite
            WHERE rec.tramite = :tramite
              AND sol.estado_flujo = :estado_solicitud
              AND sol.id_afiliado = :id_afiliado
              AND rec.identificacion = :id_reclamante
              AND pago.id_reclamante = :id_reclamante
              AND cast(pago.valor_reconocido as text) = :valor
              AND pago.tipo_cuenta = :tipo_cta
              AND cast(pago.numero_cuenta as text) = :cta
              AND cast(pago.entidad_bancaria as text) = :banco
              AND rec.estado_reclamante = :estado_reclamante
            LIMIT 1
            """
        )
        params = {
            "tramite": tramite,
            "id_afiliado": id_afiliado,
            "id_reclamante": id_reclamante,
            "valor": valor,
            "banco": banco,
            "tipo_cta": tipo_cta,
            "cta": cta,
            "estado_solicitud": estado_solicitud,
            "estado_reclamante": estado_reclamante,
        }
        with self.engine.connect() as conn:
            if conn.execute(q1, params).scalar_one_or_none() is None:
                return f"Tramite no se encuentra activo en la bandeja de aprobar {bandeja}"
            if conn.execute(q2, params).scalar_one_or_none() is None:
                return "Cedula del afiliado no corresponde al tramite enviado"
            if conn.execute(q3, params).scalar_one_or_none() is None:
                return f"Cedula del reclamante no se encuentra activa en la bandeja de {bandeja}"
            if tipo_cta not in {"Ahorros", "Corriente"}:
                return "Tipo de cuenta errado"
            if conn.execute(q4, params).scalar_one_or_none() is None:
                return "Codigo de banco errado"
            if conn.execute(q5, params).scalar_one_or_none() is None:
                return "No existen coincidencias con los valores de pago"
        return None

    def get_pago_para_cpp(self, *, tramite: str, identificacion: str) -> dict | None:
        sql = text(
            """
            SELECT
                rec.tramite,
                pago.forma_pago,
                pago.valor_reconocido,
                rec.identificacion,
                rec.nombre_beneficiario,
                pago.nit_aseguradora,
                pago.nombre_aseguradora,
                pago.id
            FROM auxilios.fun_reclamantes AS rec
            INNER JOIN auxilios.fun_solicitudes AS sol
              ON rec.tramite = sol.tramite
            INNER JOIN auxilios.fun_pagos_reclamantes AS pago
              ON rec.identificacion = pago.id_reclamante
             AND pago.tramite = sol.tramite
            WHERE sol.tramite = :tramite
              AND rec.identificacion = :identificacion
              AND pago.id_reclamante = :identificacion
            ORDER BY pago.id DESC
            LIMIT 1
            """
        )
        with self.engine.connect() as conn:
            row = conn.execute(sql, {"tramite": tramite, "identificacion": identificacion}).mappings().first()
            return dict(row) if row else None

    def update_estado_reclamante_by_tramite_identificacion(self, *, tramite: str, identificacion: str, estado: str) -> int:
        sql = text(
            """
            UPDATE auxilios.fun_reclamantes
            SET estado_reclamante = :estado
            WHERE tramite = :tramite
              AND identificacion = :identificacion
            """
        )
        with self.engine.begin() as conn:
            result = conn.execute(
                sql,
                {"estado": estado, "tramite": tramite, "identificacion": identificacion},
            )
            return result.rowcount or 0

    def count_reclamantes_by_tramite(self, tramite: str) -> int:
        sql = text(
            """
            SELECT COUNT(*)
            FROM auxilios.fun_reclamantes
            WHERE tramite = :tramite
            """
        )
        with self.engine.connect() as conn:
            return int(conn.execute(sql, {"tramite": tramite}).scalar_one() or 0)

    def count_reclamantes_by_tramite_estado(self, *, tramite: str, estado: str) -> int:
        sql = text(
            """
            SELECT COUNT(*)
            FROM auxilios.fun_reclamantes
            WHERE tramite = :tramite
              AND estado_reclamante = :estado
            """
        )
        with self.engine.connect() as conn:
            return int(conn.execute(sql, {"tramite": tramite, "estado": estado}).scalar_one() or 0)

    def get_pago_para_sap(self, *, tramite: str, identificacion: str) -> dict | None:
        sql = text(
            """
            SELECT
                rec.tramite,
                rec.identificacion,
                rec.nombre_beneficiario,
                pago.*
            FROM auxilios.fun_reclamantes AS rec
            INNER JOIN auxilios.fun_pagos_reclamantes AS pago
              ON rec.tramite = pago.tramite
            WHERE rec.tramite = :tramite
              AND rec.identificacion = :identificacion
              AND pago.id_reclamante = :identificacion
            ORDER BY pago.id DESC
            LIMIT 1
            """
        )
        with self.engine.connect() as conn:
            row = conn.execute(
                sql,
                {"tramite": tramite, "identificacion": identificacion},
            ).mappings().first()
            return dict(row) if row else None

    def insert_transaccion_sap(
        self,
        *,
        uuid: str,
        tramite: str,
        reclamante: str,
        tipo_proceso: str,
        estado: str,
        parametros_json: str,
    ) -> int:
        sql = text(
            """
            INSERT INTO auxilios.fun_transaccion_sap
            (uuid, tramite, reclamante, tipo_proceso, estado, parametros)
            VALUES
            (:uuid, :tramite, :reclamante, :tipo_proceso, :estado, :parametros)
            """
        )
        with self.engine.begin() as conn:
            result = conn.execute(
                sql,
                {
                    "uuid": uuid,
                    "tramite": tramite,
                    "reclamante": reclamante,
                    "tipo_proceso": tipo_proceso,
                    "estado": estado,
                    "parametros": parametros_json,
                },
            )
            return result.rowcount or 0

    def next_interfaz_sequence(self) -> int | None:
        sql = text("SELECT nextval('auxilios.interfaz_sequence') AS interfaz")
        with self.engine.connect() as conn:
            try:
                val = conn.execute(sql).scalar_one_or_none()
                return int(val) if val is not None else None
            except Exception:
                return None

    def exists_solicitud_sincronizable(self, cedula: str) -> bool:
        sql = text(
            """
            SELECT 1
            FROM auxilios.fun_solicitudes
            WHERE id_afiliado = :cedula
              AND estado_flujo IN ('Asignado', 'Solicitado', 'Aprobado')
            LIMIT 1
            """
        )
        with self.engine.connect() as conn:
            return conn.execute(sql, {"cedula": cedula}).scalar_one_or_none() is not None

    def exists_reclamante_tramite_ident(self, *, tramite: str, identificacion: str) -> bool:
        sql = text(
            """
            SELECT 1
            FROM auxilios.fun_reclamantes
            WHERE tramite = :tramite
              AND identificacion = :identificacion
            LIMIT 1
            """
        )
        with self.engine.connect() as conn:
            return conn.execute(
                sql,
                {"tramite": tramite, "identificacion": identificacion},
            ).scalar_one_or_none() is not None

    def insert_reclamante_basico(
        self,
        *,
        tramite: str,
        tipoid_beneficiario: str,
        identificacion: str,
        nombre_beneficiario: str,
        direccion: str,
        telefono_beneficiario: str,
        usuario: str,
    ) -> int:
        sql = text(
            """
            INSERT INTO auxilios.fun_reclamantes
            (
                tramite,
                tipoid_beneficiario,
                identificacion,
                nombre_beneficiario,
                direccion,
                telefono_beneficiario,
                usuario_insert,
                proceso
            )
            VALUES
            (
                :tramite,
                :tipoid_beneficiario,
                :identificacion,
                :nombre_beneficiario,
                :direccion,
                :telefono_beneficiario,
                :usuario,
                'AUXILIOS FUNERARIOS'
            )
            """
        )
        with self.engine.begin() as conn:
            result = conn.execute(
                sql,
                {
                    "tramite": tramite,
                    "tipoid_beneficiario": tipoid_beneficiario,
                    "identificacion": identificacion,
                    "nombre_beneficiario": nombre_beneficiario,
                    "direccion": direccion,
                    "telefono_beneficiario": telefono_beneficiario,
                    "usuario": usuario,
                },
            )
            return result.rowcount or 0

    def get_reclamante_core(self, *, tramite: str, identificacion: str) -> dict | None:
        sql = text(
            """
            SELECT tipoid_beneficiario, identificacion, nombre_beneficiario, direccion, telefono_beneficiario
            FROM auxilios.fun_reclamantes
            WHERE tramite = :tramite
              AND identificacion = :identificacion
            LIMIT 1
            """
        )
        with self.engine.connect() as conn:
            row = conn.execute(
                sql,
                {"tramite": tramite, "identificacion": identificacion},
            ).mappings().first()
            return dict(row) if row else None

    def get_tercero_id_by_identificacion(self, identificacion: str) -> int | None:
        sql = text(
            """
            SELECT tercero_id
            FROM auxilios.fun_terceros
            WHERE identificacion = :identificacion
            LIMIT 1
            """
        )
        with self.engine.connect() as conn:
            val = conn.execute(sql, {"identificacion": identificacion}).scalar_one_or_none()
            return int(val) if val is not None else None

    def next_tercero_id(self) -> int:
        sql = text("SELECT nextval('auxilios.fun_terceros_tercero_id_seq') AS tercero_id")
        with self.engine.connect() as conn:
            return int(conn.execute(sql).scalar_one())

    def upsert_avance_tercero(
        self,
        *,
        tercero_id: int,
        identificacion: str,
        tipo_id: str,
        nombres: list[str],
        direccion: str,
        telefono: str,
        data: dict,
    ) -> dict:
        nombres4 = (nombres + ["", "", "", ""])[:4]
        with self.engine.begin() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM auxilios.fun_terceros WHERE tercero_id = :tercero_id LIMIT 1"),
                {"tercero_id": tercero_id},
            ).scalar_one_or_none() is not None

            if exists:
                conn.execute(
                    text(
                        """
                        UPDATE auxilios.fun_terceros
                        SET grupo_cuenta = 'K004',
                            tipo_id = :tipo_id,
                            id_origen = :id_origen,
                            primer_nombre = :n1,
                            segundo_nombre = :n2,
                            tercer_nombre = :n3,
                            cuarto_nombre = :n4,
                            tratamiento = :tratamiento,
                            abreviatura = :abreviatura,
                            codigo_iso_pais = 'CO',
                            region = :region,
                            poblacion = :poblacion,
                            direccion = :direccion,
                            idioma = 'ES',
                            telefono = :telefono,
                            movil = :movil,
                            fax = :fax,
                            correo_electronico = :email,
                            numero_documento1 = :dc_documento1,
                            numero_documento2 = :dc_documento2,
                            numero_documento3 = :dc_documento3,
                            tipo_documento = :dc_tipo_doc,
                            clase_impuesto = :dc_clase_impuesto,
                            codigo_ciiu = :dc_ciiu,
                            codigo = :s_codigo,
                            cuenta_asociada = :s_cuenta_asociada,
                            grupo_tesoreria = :s_grupo_tesoreria,
                            condicion_pago = :ct_condicion_pago,
                            via_pago = :ct_via_pago,
                            bloqueado = :ct_bloqueado
                        WHERE tercero_id = :tercero_id
                        """
                    ),
                    {
                        "tercero_id": tercero_id,
                        "tipo_id": tipo_id,
                        "id_origen": f"{tipo_id}.{identificacion}",
                        "n1": nombres4[0],
                        "n2": nombres4[1],
                        "n3": nombres4[2],
                        "n4": nombres4[3],
                        "tratamiento": data.get("tratamiento", ""),
                        "abreviatura": data.get("abreviatura", ""),
                        "region": data.get("region", ""),
                        "poblacion": data.get("poblacion", ""),
                        "direccion": direccion,
                        "telefono": telefono,
                        "movil": data.get("movil", ""),
                        "fax": data.get("fax", ""),
                        "email": data.get("email", ""),
                        "dc_documento1": data.get("dc_documento1", ""),
                        "dc_documento2": data.get("dc_documento2", ""),
                        "dc_documento3": data.get("dc_documento3", ""),
                        "dc_tipo_doc": data.get("dc_tipo_doc", ""),
                        "dc_clase_impuesto": data.get("dc_clase_impuesto", ""),
                        "dc_ciiu": data.get("dc_ciiu", ""),
                        "s_codigo": data.get("s_codigo", ""),
                        "s_cuenta_asociada": data.get("s_cuenta_asociada", ""),
                        "s_grupo_tesoreria": data.get("s_grupo_tesoreria", ""),
                        "ct_condicion_pago": data.get("ct_condicion_pago", ""),
                        "ct_via_pago": data.get("ct_via_pago", ""),
                        "ct_bloqueado": data.get("ct_bloqueado", ""),
                    },
                )
            else:
                conn.execute(
                    text(
                        """
                        INSERT INTO auxilios.fun_terceros
                        (
                            tercero_id, grupo_cuenta, tipo_id, identificacion, id_origen,
                            primer_nombre, segundo_nombre, tercer_nombre, cuarto_nombre,
                            tratamiento, abreviatura, codigo_iso_pais, region, poblacion,
                            direccion, idioma, telefono, movil, fax, correo_electronico,
                            numero_documento1, numero_documento2, numero_documento3, tipo_documento,
                            clase_impuesto, codigo_ciiu, codigo, cuenta_asociada, grupo_tesoreria,
                            condicion_pago, via_pago, bloqueado
                        )
                        VALUES
                        (
                            :tercero_id, 'K004', :tipo_id, :identificacion, :id_origen,
                            :n1, :n2, :n3, :n4,
                            :tratamiento, :abreviatura, 'CO', :region, :poblacion,
                            :direccion, 'ES', :telefono, :movil, :fax, :email,
                            :dc_documento1, :dc_documento2, :dc_documento3, :dc_tipo_doc,
                            :dc_clase_impuesto, :dc_ciiu, :s_codigo, :s_cuenta_asociada, :s_grupo_tesoreria,
                            :ct_condicion_pago, :ct_via_pago, :ct_bloqueado
                        )
                        """
                    ),
                    {
                        "tercero_id": tercero_id,
                        "tipo_id": tipo_id,
                        "identificacion": identificacion,
                        "id_origen": f"{tipo_id}.{identificacion}",
                        "n1": nombres4[0],
                        "n2": nombres4[1],
                        "n3": nombres4[2],
                        "n4": nombres4[3],
                        "tratamiento": data.get("tratamiento", ""),
                        "abreviatura": data.get("abreviatura", ""),
                        "region": data.get("region", ""),
                        "poblacion": data.get("poblacion", ""),
                        "direccion": direccion,
                        "telefono": telefono,
                        "movil": data.get("movil", ""),
                        "fax": data.get("fax", ""),
                        "email": data.get("email", ""),
                        "dc_documento1": data.get("dc_documento1", ""),
                        "dc_documento2": data.get("dc_documento2", ""),
                        "dc_documento3": data.get("dc_documento3", ""),
                        "dc_tipo_doc": data.get("dc_tipo_doc", ""),
                        "dc_clase_impuesto": data.get("dc_clase_impuesto", ""),
                        "dc_ciiu": data.get("dc_ciiu", ""),
                        "s_codigo": data.get("s_codigo", ""),
                        "s_cuenta_asociada": data.get("s_cuenta_asociada", ""),
                        "s_grupo_tesoreria": data.get("s_grupo_tesoreria", ""),
                        "ct_condicion_pago": data.get("ct_condicion_pago", ""),
                        "ct_via_pago": data.get("ct_via_pago", ""),
                        "ct_bloqueado": data.get("ct_bloqueado", ""),
                    },
                )

            conn.execute(
                text("DELETE FROM auxilios.fun_terceros_cuenta_bancaria WHERE tercero_id = :tercero_id"),
                {"tercero_id": tercero_id},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO auxilios.fun_terceros_cuenta_bancaria
                    (
                        tercero_id, codigo_iso_pais, codigo_banco, cuenta_bancaria,
                        titular_cuenta, tipo_cuenta, referencia_banco_cuenta,
                        codigo_swift, codigo_iban, codigo_aba
                    )
                    VALUES
                    (
                        :tercero_id, 'CO', :ct_cod_banco, :ct_cuenta_bancaria,
                        :ct_titular, :ct_tipo_cuenta, :ct_referencia,
                        :ct_swift, :ct_iban, :ct_aba
                    )
                    """
                ),
                {
                    "tercero_id": tercero_id,
                    "ct_cod_banco": data.get("ct_cod_banco", ""),
                    "ct_cuenta_bancaria": data.get("ct_cuenta_bancaria", ""),
                    "ct_titular": data.get("ct_titular", ""),
                    "ct_tipo_cuenta": data.get("ct_tipo_cuenta", ""),
                    "ct_referencia": data.get("ct_referencia", ""),
                    "ct_swift": data.get("ct_swift", ""),
                    "ct_iban": data.get("ct_iban", ""),
                    "ct_aba": data.get("ct_aba", ""),
                },
            )
            conn.execute(
                text("DELETE FROM auxilios.fun_terceros_impuestos_retencion WHERE tercero_id = :tercero_id"),
                {"tercero_id": tercero_id},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO auxilios.fun_terceros_impuestos_retencion
                    (
                        tercero_id, codigo_iso_pais, tipo_retencion,
                        indicador_retencion, indicador_sujeto_retencion, categoria_retencion
                    )
                    VALUES
                    (
                        :tercero_id, 'CO', :ir_tipo_retencion,
                        :ir_indicador_retencion, :ir_indicador_sujeto, :ir_categoria_retencion
                    )
                    """
                ),
                {
                    "tercero_id": tercero_id,
                    "ir_tipo_retencion": data.get("ir_tipo_retencion", ""),
                    "ir_indicador_retencion": data.get("ir_indicador_retencion", ""),
                    "ir_indicador_sujeto": data.get("ir_indicador_sujeto", ""),
                    "ir_categoria_retencion": data.get("ir_categoria_retencion", ""),
                },
            )
        return {"ok": True, "tercero_id": tercero_id}

    def list_reclamantes_aprobados_para_terceros(self) -> list[dict]:
        sql = text(
            """
            SELECT
                rec.tramite,
                rec.identificacion,
                rec.tipoid_beneficiario,
                rec.nombre_beneficiario,
                rec.direccion,
                rec.telefono_beneficiario,
                sol.id_afiliado,
                sol.tipoid_afiliado
            FROM auxilios.fun_reclamantes AS rec
            INNER JOIN auxilios.fun_solicitudes AS sol
              ON rec.tramite = sol.tramite
            WHERE rec.estado_reclamante = 'APROBADO'
            """
        )
        with self.engine.connect() as conn:
            rows = conn.execute(sql).mappings().all()
        return [dict(r) for r in rows]

    def exists_solicitud_by_afiliado_tramite(self, *, afiliado: str, tramite: str) -> bool:
        sql = text(
            """
            SELECT 1
            FROM auxilios.fun_solicitudes
            WHERE id_afiliado = :afiliado
              AND tramite = :tramite
            LIMIT 1
            """
        )
        with self.engine.connect() as conn:
            return conn.execute(
                sql,
                {"afiliado": afiliado, "tramite": tramite},
            ).scalar_one_or_none() is not None

    def get_solicitud_funeraria(self, tramite: str) -> dict | None:
        sql = text(
            """
            SELECT
                tramite,
                tipoid_afiliado,
                id_afiliado,
                nombre_afiliado,
                tipo_solicitud,
                fecha_solicitud,
                regional,
                oficina
            FROM auxilios.fun_solicitudes
            WHERE tramite = :tramite
              AND proceso = 'AUXILIOS FUNERARIOS'
            LIMIT 1
            """
        )
        with self.engine.connect() as conn:
            row = conn.execute(sql, {"tramite": tramite}).mappings().first()
            return dict(row) if row else None

    def list_reclamantes_para_clasificacion(self, tramite: str) -> list[dict]:
        sql = text(
            """
            SELECT
                ben.id_ben,
                ben.tramite,
                ben.tipoid_beneficiario,
                ben.identificacion,
                ben.nombre_beneficiario,
                ben.direccion,
                ben.telefono_beneficiario,
                pag.forma_pago,
                pag.numero_cuenta,
                pag.entidad_bancaria,
                pag.tipo_cuenta
            FROM auxilios.fun_reclamantes AS ben
            INNER JOIN auxilios.fun_pagos_reclamantes AS pag
              ON trim(ben.identificacion) = pag.id_reclamante
            WHERE ben.tramite = :tramite
              AND pag.tramite = :tramite
              AND ben.proceso = 'AUXILIOS FUNERARIOS'
              AND ben.estado_reclamante IS NULL
            GROUP BY
                ben.id_ben,
                ben.tramite,
                ben.tipoid_beneficiario,
                ben.identificacion,
                ben.nombre_beneficiario,
                ben.direccion,
                ben.telefono_beneficiario,
                pag.forma_pago,
                pag.numero_cuenta,
                pag.entidad_bancaria,
                pag.tipo_cuenta
            ORDER BY ben.id_ben
            """
        )
        with self.engine.connect() as conn:
            rows = conn.execute(sql, {"tramite": tramite}).mappings().all()
        return [dict(r) for r in rows]

    def list_imagenes_afiliado(self, afiliado: str) -> list[str]:
        sql = text(
            """
            SELECT pi
            FROM tblpnpension
            WHERE ce = :afiliado
              AND cg = '51'
            UNION
            SELECT pi
            FROM tblanpension
            WHERE ce = :afiliado
              AND cg = '51'
            ORDER BY pi
            """
        )
        with self.engine.connect() as conn:
            rows = conn.execute(sql, {"afiliado": afiliado}).fetchall()
        items: list[str] = []
        for row in rows:
            path = str(row[0] or "").strip()
            if not path:
                continue
            if not path.startswith("https"):
                path = path.replace("http", "https", 1)
            items.append(path)
        return items

    def update_solicitud_rechazada(self, *, tramite: str, sub_estado: str) -> int:
        sql = text(
            """
            UPDATE auxilios.fun_solicitudes
            SET estado_flujo = 'Rechazado',
                sub_estado = :sub_estado
            WHERE tramite = :tramite
              AND proceso = 'AUXILIOS FUNERARIOS'
            """
        )
        with self.engine.begin() as conn:
            result = conn.execute(
                sql,
                {"tramite": tramite, "sub_estado": sub_estado},
            )
            return result.rowcount or 0

    def insert_actividad(self, *, tramite: str, usuario: str, descripcion: str) -> int:
        sql = text(
            """
            INSERT INTO auxilios.fun_actividades
            (descripcion_actividad, usuario_ejecuta, proceso, tramite)
            VALUES
            (:descripcion, :usuario, 'AUXILIOS FUNERARIOS', :tramite)
            """
        )
        with self.engine.begin() as conn:
            result = conn.execute(
                sql,
                {"descripcion": descripcion, "usuario": usuario, "tramite": tramite},
            )
            return result.rowcount or 0
