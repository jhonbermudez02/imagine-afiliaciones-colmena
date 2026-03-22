from __future__ import annotations
from collections.abc import Sequence

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError


class NotificacionesRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def insert_notificacion(self, payload: dict) -> int | None:
        sql = text(
            """
            INSERT INTO auxilios.not_solicitudes
            (
                tramite, tipo_solicitud, fecha_solicitud, estado_solicitud, tipoid_afiliado,
                id_afiliado, nombre_afiliado, idoficina, oficina, idregional, regional,
                estado_flujo, usuario_insert, proceso
            )
            VALUES
            (
                :tramite, :tipo_solicitud, :fecha_solicitud, :estado_solicitud, :tipoid_afiliado,
                :id_afiliado, :nombre_afiliado, :idoficina, :oficina, :idregional, :regional,
                'Notificado', :usuario_insert, 'NOTIFICACIONES AUXILIOS'
            )
            RETURNING solicitud_id
            """
        )
        params = {
            "tramite": payload["tramite"],
            "tipo_solicitud": payload["tipo_solicitud"],
            "fecha_solicitud": payload["fecha_solicitud"],
            "estado_solicitud": payload["estado_solicitud"],
            "tipoid_afiliado": payload["tipoid_afiliado"],
            "id_afiliado": payload["id_afiliado"],
            "nombre_afiliado": payload["nombre_afiliado"],
            "idoficina": payload.get("idoficina"),
            "oficina": payload.get("oficina"),
            "idregional": payload.get("idregional"),
            "regional": payload.get("regional"),
            "usuario_insert": payload["usuario"],
        }
        with self.engine.begin() as conn:
            return conn.execute(sql, params).scalar_one()

    def insert_beneficiarios(self, tramite: str, usuario: str, beneficiarios: Sequence[dict]) -> int:
        sql = text(
            """
            INSERT INTO auxilios.not_reclamantes
            (
                tramite, tipoid_beneficiario, identificacion, nombre_beneficiario,
                direccion, telefono_beneficiario, usuario_insert, proceso
            )
            VALUES
            (
                :tramite, :tipoid_beneficiario, :identificacion, :nombre_beneficiario,
                :direccion, :telefono_beneficiario, :usuario_insert, 'NOTIFICACIONES AUXILIOS'
            )
            """
        )
        count = 0
        with self.engine.begin() as conn:
            for ben in beneficiarios:
                conn.execute(
                    sql,
                    {
                        "tramite": tramite,
                        "tipoid_beneficiario": ben["tipoid_beneficiario"],
                        "identificacion": ben["identificacion"],
                        "nombre_beneficiario": ben["nombre_beneficiario"],
                        "direccion": ben.get("direccion"),
                        "telefono_beneficiario": ben.get("telefono_beneficiario"),
                        "usuario_insert": usuario,
                    },
                )
                count += 1
        return count

    def change_estado_solicitud(self, solicitud_id: int, tramite: str, new_estado: str) -> int:
        sql = text(
            """
            UPDATE auxilios.not_solicitudes
            SET estado_flujo = :new_estado
            WHERE solicitud_id = :solicitud_id
              AND tramite = :tramite
              AND proceso = 'NOTIFICACIONES AUXILIOS'
            """
        )
        with self.engine.begin() as conn:
            result = conn.execute(
                sql,
                {"solicitud_id": solicitud_id, "tramite": tramite, "new_estado": new_estado},
            )
            return result.rowcount or 0

    def add_log_transition(
        self, solicitud_id: int, usuario: str, estado_proximo: str, observacion: str = ""
    ) -> bool:
        sql_estado = text(
            """
            SELECT estado_flujo
            FROM auxilios.not_solicitudes
            WHERE solicitud_id = :solicitud_id
            """
        )
        sql_log = text(
            """
            INSERT INTO auxilios.not_log(solicitud_id, usuario, estado_anterior, estado_actual, observacion)
            VALUES(:solicitud_id, :usuario, :estado_anterior, :estado_actual, :observacion)
            """
        )
        try:
            with self.engine.begin() as conn:
                estado_anterior = conn.execute(
                    sql_estado, {"solicitud_id": solicitud_id}
                ).scalar_one_or_none()
                conn.execute(
                    sql_log,
                    {
                        "solicitud_id": solicitud_id,
                        "usuario": usuario,
                        "estado_anterior": estado_anterior or "",
                        "estado_actual": estado_proximo,
                        "observacion": observacion,
                    },
                )
            return True
        except SQLAlchemyError:
            # El log no debe tumbar el flujo principal en esta fase de migracion.
            return False

    def finalize_tramite(self, solicitud_id: int, tramite: str) -> int:
        return self.change_estado_solicitud(solicitud_id, tramite, "FINALIZADO")

    def upsert_post_estado(
        self, solicitud_id: int, id_estado_post: int, marca: bool, usuario: str
    ) -> dict:
        sql_count = text(
            """
            SELECT count(id_estado_post_solicitud) as ct
            FROM auxilios.not_estados_post_solicitud
            WHERE solicitud_id = :solicitud_id
              AND id_estado_post = :id_estado_post
            """
        )
        sql_insert = text(
            """
            INSERT INTO auxilios.not_estados_post_solicitud
            (solicitud_id, user_insert, id_estado_post, marca)
            VALUES (:solicitud_id, :user_insert, :id_estado_post, :marca)
            """
        )
        sql_update = text(
            """
            UPDATE auxilios.not_estados_post_solicitud
            SET user_insert = :user_insert, marca = :marca
            WHERE solicitud_id = :solicitud_id
              AND id_estado_post = :id_estado_post
            """
        )
        params = {
            "solicitud_id": solicitud_id,
            "id_estado_post": id_estado_post,
            "user_insert": usuario,
            "marca": marca,
        }
        with self.engine.begin() as conn:
            ct = conn.execute(sql_count, params).scalar_one()
            if int(ct or 0) == 0:
                result = conn.execute(sql_insert, params)
                return {"inserted": result.rowcount or 0, "updated": 0}
            result = conn.execute(sql_update, params)
            return {"inserted": 0, "updated": result.rowcount or 0}

    def guardar_post_gestion(
        self, solicitud_id: int, tipo_gestion: int, usuario: str, observacion_g: str | None
    ) -> dict:
        if tipo_gestion == 4:
            sql = text(
                """
                INSERT INTO auxilios.not_estados_post_solicitud
                (
                    solicitud_id, fecha_insert, user_insert, fecha_solucion, usuario_solucion,
                    id_estado_post, marca, observacion
                )
                VALUES
                (
                    :solicitud_id, now(), :user_insert, now(), :usuario_solucion,
                    :id_estado_post, TRUE, :observacion
                )
                """
            )
            with self.engine.begin() as conn:
                result = conn.execute(
                    sql,
                    {
                        "solicitud_id": solicitud_id,
                        "user_insert": usuario,
                        "usuario_solucion": usuario,
                        "id_estado_post": tipo_gestion,
                        "observacion": observacion_g or "",
                    },
                )
            return {"inserted": result.rowcount or 0, "updated": 0}

        sql = text(
            """
            UPDATE auxilios.not_estados_post_solicitud
            SET fecha_solucion = now(),
                usuario_solucion = :usuario_solucion,
                observacion = :observacion
            WHERE id_estado_post = :id_estado_post
              AND solicitud_id = :solicitud_id
              AND marca = TRUE
            """
        )
        with self.engine.begin() as conn:
            result = conn.execute(
                sql,
                {
                    "usuario_solucion": usuario,
                    "observacion": observacion_g or "",
                    "id_estado_post": tipo_gestion,
                    "solicitud_id": solicitud_id,
                },
            )
        return {"inserted": 0, "updated": result.rowcount or 0}

    def list_reclamantes(self, solicitud_id: int, tramite: str | None = None) -> list[dict]:
        where_tramite = " AND r.tramite = :tramite " if tramite else ""
        sql = text(
            f"""
            SELECT
                r.id_ben,
                r.not_solicitud_id,
                r.tramite,
                r.tipoid_beneficiario,
                r.identificacion,
                r.nombre_beneficiario,
                r.direccion,
                r.telefono_beneficiario,
                r.estado_reclamante,
                p.apoderado,
                p.nom_apoderado,
                p.tel_apoderado,
                p.forma_pago,
                p.numero_cuenta,
                p.entidad_bancaria,
                p.tipo_cuenta
            FROM auxilios.not_reclamantes r
            LEFT JOIN auxilios.not_pagos_reclamantes p
              ON p.solicitud_id = r.not_solicitud_id
             AND p.id_reclamante = r.identificacion
            WHERE r.not_solicitud_id = :solicitud_id
              AND (r.estado_reclamante IS NULL OR r.estado_reclamante <> 'Eliminado')
              {where_tramite}
            ORDER BY r.id_ben
            """
        )
        params: dict[str, int | str] = {"solicitud_id": solicitud_id}
        if tramite:
            params["tramite"] = tramite
        with self.engine.begin() as conn:
            rows = conn.execute(sql, params).mappings().all()
        return [dict(r) for r in rows]

    def list_imagenes_validacion(
        self, solicitud_id: int, tramite: str, id_prestacion: int, tipo_solicitud: str
    ) -> list[dict]:
        sql_solicitud = text(
            """
            SELECT id_afiliado
            FROM auxilios.not_solicitudes
            WHERE tramite = :tramite AND solicitud_id = :solicitud_id
            """
        )
        sql = text(
            """
            SELECT
                t1.pi,
                t1.lo,
                t1.ax,
                t1.pn,
                t1.codoficina,
                tcp.descripcion,
                nmi.marca,
                ndp.obligatorio,
                nd.desc_documento
            FROM (
                SELECT tp.pi, tp.lo, '0' AS ax, tp.pn, tp.codoficina
                FROM tblpnpension tp
                WHERE tp.ce = :cedula
                  AND tp.pn IN (
                    SELECT pn
                    FROM auxilios.not_relacion_imagenes
                    WHERE tramite = :tramite
                      AND id_prestacion = :id_prestacion
                      AND solicitud_id = :solicitud_id
                  )
                UNION ALL
                SELECT ta.pi, ta.lo, ta.ax, ta.pn, ta.stiker AS codoficina
                FROM tblanpension ta
                WHERE ta.ce = :cedula
                  AND ta.pn IN (
                    SELECT pn
                    FROM auxilios.not_relacion_imagenes
                    WHERE tramite = :tramite
                      AND id_prestacion = :id_prestacion
                      AND solicitud_id = :solicitud_id
                  )
            ) AS t1
            INNER JOIN tblcodigospension tcp
              ON t1.lo = tcp.codigo
             AND (
                (:tipo_solicitud = 'INV' AND tcp.categoria = 'SOLICITUDES DE INVALIDEZ')
                OR (:tipo_solicitud = 'SBV' AND tcp.categoria = 'SOLICITUDES DE SOBREVIVENCIA')
                OR (:tipo_solicitud = 'VEJ' AND tcp.categoria = 'SOLICITUDES DE VEJEZ')
             )
            LEFT JOIN auxilios.not_marca_imagenes nmi
              ON nmi.ax = t1.ax
             AND nmi.pn = t1.pn
             AND nmi.tramite = :tramite
             AND nmi.solicitud_id = :solicitud_id
            INNER JOIN auxilios.not_relacion_imagenes nri
              ON nri.pn = t1.pn
             AND nri.tramite = :tramite
             AND nri.id_prestacion = :id_prestacion
             AND nri.solicitud_id = :solicitud_id
            INNER JOIN auxilios.not_documentos_prestaciones ndp
              ON ndp.id_documento = nri.id_documento
             AND ndp.id_prestacion = :id_prestacion
            INNER JOIN auxilios.not_documentos nd
              ON nd.id_documento = nri.id_documento
            ORDER BY t1.codoficina
            """
        )
        with self.engine.begin() as conn:
            cedula = conn.execute(
                sql_solicitud, {"tramite": tramite, "solicitud_id": solicitud_id}
            ).scalar_one_or_none()
            if not cedula:
                return []
            rows = conn.execute(
                sql,
                {
                    "cedula": cedula,
                    "tramite": tramite,
                    "id_prestacion": id_prestacion,
                    "solicitud_id": solicitud_id,
                    "tipo_solicitud": tipo_solicitud,
                },
            ).mappings().all()
        return [dict(r) for r in rows]

    def upsert_marca_imagen(
        self, solicitud_id: int, tramite: str, pn: int, ax: str, valor: int
    ) -> dict:
        sql_verif = text(
            """
            SELECT id_marca
            FROM auxilios.not_marca_imagenes
            WHERE ax = :ax AND pn = :pn AND tramite = :tramite AND solicitud_id = :solicitud_id
            """
        )
        sql_update = text(
            """
            UPDATE auxilios.not_marca_imagenes
            SET marca = :marca
            WHERE id_marca = :id_marca
            """
        )
        sql_insert = text(
            """
            INSERT INTO auxilios.not_marca_imagenes (ax, pn, tramite, marca, solicitud_id)
            VALUES (:ax, :pn, :tramite, :marca, :solicitud_id)
            """
        )
        with self.engine.begin() as conn:
            id_marca = conn.execute(
                sql_verif,
                {"ax": ax, "pn": pn, "tramite": tramite, "solicitud_id": solicitud_id},
            ).scalar_one_or_none()
            if id_marca:
                result = conn.execute(sql_update, {"id_marca": id_marca, "marca": valor})
                return {"updated": result.rowcount or 0, "inserted": 0}
            result = conn.execute(
                sql_insert,
                {
                    "ax": ax,
                    "pn": pn,
                    "tramite": tramite,
                    "marca": valor,
                    "solicitud_id": solicitud_id,
                },
            )
            return {"updated": 0, "inserted": result.rowcount or 0}

    def list_imagenes_consulta(
        self, solicitud_id: int, tramite: str, id_prestacion: int, tipo_solicitud: str
    ) -> list[dict]:
        sql = text(
            """
            SELECT
                t1.pi,
                t1.lo,
                t1.ax,
                t1.pn,
                t1.codoficina,
                tcp.descripcion,
                nmi.marca,
                ndp.obligatorio,
                nd.desc_documento
            FROM (
                SELECT tp.pi, tp.lo, '0' AS ax, tp.pn, tp.codoficina
                FROM tblpnpension tp
                WHERE tp.pn IN (
                    SELECT pn
                    FROM auxilios.not_relacion_imagenes
                    WHERE tramite = :tramite
                      AND id_prestacion = :id_prestacion
                      AND solicitud_id = :solicitud_id
                )
                UNION ALL
                SELECT ta.pi, ta.lo, ta.ax, ta.pn, ta.stiker AS codoficina
                FROM tblanpension ta
                WHERE ta.pn IN (
                    SELECT pn
                    FROM auxilios.not_relacion_imagenes
                    WHERE tramite = :tramite
                      AND id_prestacion = :id_prestacion
                      AND solicitud_id = :solicitud_id
                )
            ) AS t1
            INNER JOIN tblcodigospension tcp
              ON t1.lo = tcp.codigo
             AND (
                (:tipo_solicitud = 'INV' AND tcp.categoria = 'SOLICITUDES DE INVALIDEZ')
                OR (:tipo_solicitud = 'SBV' AND tcp.categoria = 'SOLICITUDES DE SOBREVIVENCIA')
                OR (:tipo_solicitud = 'VEJ' AND tcp.categoria = 'SOLICITUDES DE VEJEZ')
             )
            LEFT JOIN auxilios.not_marca_imagenes nmi
              ON nmi.ax = t1.ax
             AND nmi.pn = t1.pn
             AND nmi.tramite = :tramite
             AND nmi.solicitud_id = :solicitud_id
            INNER JOIN auxilios.not_relacion_imagenes nri
              ON nri.pn = t1.pn
             AND nri.tramite = :tramite
             AND nri.id_prestacion = :id_prestacion
             AND nri.solicitud_id = :solicitud_id
            INNER JOIN auxilios.not_documentos_prestaciones ndp
              ON ndp.id_documento = nri.id_documento
             AND ndp.id_prestacion = :id_prestacion
            INNER JOIN auxilios.not_documentos nd
              ON nd.id_documento = nri.id_documento
            ORDER BY t1.codoficina
            """
        )
        with self.engine.begin() as conn:
            rows = conn.execute(
                sql,
                {
                    "tramite": tramite,
                    "id_prestacion": id_prestacion,
                    "solicitud_id": solicitud_id,
                    "tipo_solicitud": tipo_solicitud,
                },
            ).mappings().all()
        return [dict(r) for r in rows]

    def eliminar_imagen_existente(self, pn: int) -> dict:
        sql_del_pension = text("DELETE FROM tblpnpension WHERE pn = :pn")
        sql_del_rel = text("DELETE FROM auxilios.not_relacion_imagenes WHERE pn = :pn")
        with self.engine.begin() as conn:
            del_pension = conn.execute(sql_del_pension, {"pn": pn}).rowcount or 0
            del_rel = conn.execute(sql_del_rel, {"pn": pn}).rowcount or 0
        return {"deleted_tblpnpension": del_pension, "deleted_not_relacion_imagenes": del_rel}

    def actualizar_categoria(self, pn: int, val: int) -> int:
        sql = text(
            """
            UPDATE auxilios.not_relacion_imagenes
            SET id_documento = :val
            WHERE pn = :pn
            """
        )
        with self.engine.begin() as conn:
            result = conn.execute(sql, {"pn": pn, "val": val})
        return result.rowcount or 0

    def actualizar_categoria_new(self, key: str, val: str, indexado: str) -> int:
        if indexado == "S":
            sql = text(
                """
                UPDATE auxilios.not_relacion_imagenes
                SET id_documento = :val
                WHERE pn = :key
                """
            )
        else:
            sql = text(
                """
                UPDATE auxilios.not_imagenes_temporal
                SET clasificacion = :val
                WHERE na = :key
                """
            )
        with self.engine.begin() as conn:
            result = conn.execute(sql, {"key": key, "val": val})
        return result.rowcount or 0

    def get_post_gestion_context(self, solicitud_id: int, tipo_gestion: int) -> dict:
        sql_tipo = text(
            """
            SELECT estado_post_id, estado_post
            FROM auxilios.not_estado_post
            WHERE estado_post_id = :tipo_gestion
              AND activo = TRUE
            """
        )
        sql_ultima = text(
            """
            SELECT
                id_estado_post_solicitud,
                solicitud_id,
                id_estado_post,
                marca,
                observacion,
                user_insert,
                usuario_solucion,
                fecha_insert,
                fecha_solucion
            FROM auxilios.not_estados_post_solicitud
            WHERE solicitud_id = :solicitud_id
              AND id_estado_post = :tipo_gestion
            ORDER BY id_estado_post_solicitud DESC
            LIMIT 1
            """
        )
        with self.engine.begin() as conn:
            tipo = conn.execute(sql_tipo, {"tipo_gestion": tipo_gestion}).mappings().first()
            ultima = conn.execute(
                sql_ultima, {"solicitud_id": solicitud_id, "tipo_gestion": tipo_gestion}
            ).mappings().first()
        return {
            "tipo_gestion_meta": dict(tipo) if tipo else None,
            "ultima_gestion": dict(ultima) if ultima else None,
        }

    def list_post_estados_activos(self) -> list[dict]:
        sql = text(
            """
            SELECT estado_post_id, estado_post
            FROM auxilios.not_estado_post
            WHERE activo = TRUE
            ORDER BY estado_post_id
            """
        )
        with self.engine.begin() as conn:
            rows = conn.execute(sql).mappings().all()
        return [dict(r) for r in rows]

    def insert_imagen_temporal(
        self,
        *,
        tramite: str,
        id_solicitud: int,
        id_prestacion: int,
        path: str,
        nombre_real: str,
    ) -> int:
        sql = text(
            """
            INSERT INTO auxilios.not_imagenes_temporal
            (tramite, id_solicitud, id_prestacion, path, nombre_real)
            VALUES
            (:tramite, :id_solicitud, :id_prestacion, :path, :nombre_real)
            RETURNING na
            """
        )
        with self.engine.begin() as conn:
            val = conn.execute(
                sql,
                {
                    "tramite": tramite,
                    "id_solicitud": id_solicitud,
                    "id_prestacion": id_prestacion,
                    "path": path,
                    "nombre_real": nombre_real,
                },
            ).scalar_one()
        return int(val)

    def list_auditoria(self, solicitud_id: int, limit: int) -> list[dict]:
        sql = text(
            """
            SELECT solicitud_id, usuario, estado_anterior, estado_actual, observacion
            FROM auxilios.not_log
            WHERE solicitud_id = :solicitud_id
            LIMIT :limit
            """
        )
        with self.engine.begin() as conn:
            rows = conn.execute(sql, {"solicitud_id": solicitud_id, "limit": limit}).mappings().all()
        return [dict(r) for r in rows]

    def get_bloqueo_ultimo_registro(self) -> dict | None:
        sql = text(
            """
            SELECT na, estado, usuario, fecha_bloqueo
            FROM auxilios.not_bloqueo
            ORDER BY na DESC
            LIMIT 1
            """
        )
        with self.engine.begin() as conn:
            row = conn.execute(sql).mappings().first()
        return dict(row) if row else None

    def create_bloqueo_registro(self, estado: int, usuario: str) -> dict:
        sql = text(
            """
            INSERT INTO auxilios.not_bloqueo (estado, usuario)
            VALUES (:estado, :usuario)
            RETURNING na, estado, usuario, fecha_bloqueo
            """
        )
        with self.engine.begin() as conn:
            row = conn.execute(sql, {"estado": estado, "usuario": usuario}).mappings().first()
        return dict(row) if row else {"na": None, "estado": estado, "usuario": usuario, "fecha_bloqueo": None}
