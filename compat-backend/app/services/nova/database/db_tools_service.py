from __future__ import annotations

import difflib
import re
from typing import Any

from app.core.db import fetch_all_by_alias

FORBIDDEN_SQL_RE = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke)\b",
    re.IGNORECASE,
)


class DbToolsService:
    STOPWORDS = {
        "de",
        "del",
        "la",
        "el",
        "los",
        "las",
        "y",
        "o",
        "en",
        "por",
        "para",
        "con",
        "sin",
        "estado",
        "afiliacion",
        "afiliación",
        "documento",
        "documentos",
        "tramite",
        "trámite",
        "ruta",
        "inclusion",
        "inclusión",
        "mostrar",
        "consultar",
        "que",
        "qué",
        "cuales",
        "cuales",
        "tengo",
        "hay",
        "listar",
        "dime",
        "ver",
        "por",
        "mas",
        "más",
        "con",
        "sin",
        "los",
        "las",
        "para",
    }
    def is_safe_readonly_sql(self, sql: str) -> tuple[bool, str]:
        s = sql.strip()
        if not s:
            return False, "SQL vacio."
        if ";" in s.strip(";"):
            return False, "Solo se permite una sentencia SQL."
        if not s.lower().startswith("select"):
            return False, "Solo consultas SELECT estan permitidas."
        if FORBIDDEN_SQL_RE.search(s):
            return False, "SQL contiene comandos no permitidos."
        return True, "ok"

    def query_readonly(self, base: str, sql: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        safe, msg = self.is_safe_readonly_sql(sql)
        if not safe:
            return {"ok": False, "message": msg}
        rows = fetch_all_by_alias(base, sql, params or {})
        return {"ok": True, "base": base, "count": len(rows), "rows": rows}

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return [t.lower() for t in re.findall(r"[a-z0-9áéíóúñ]+", text or "", flags=re.IGNORECASE)]

    @staticmethod
    def _fuzzy_contains(token: str, words: list[str], threshold: float = 0.74) -> bool:
        for w in words:
            if token == w:
                return True
            if len(token) >= 4 and len(w) >= 4:
                if token in w or w in token:
                    return True
            if len(token) >= 4 and len(w) >= 4:
                if difflib.SequenceMatcher(None, token, w).ratio() >= threshold:
                    return True
        return False

    def search_ruta_inclusion_context(self, base: str, question: str, limit: int = 5) -> dict[str, Any]:
        q = (question or "").strip()
        if not q:
            return {"ok": True, "base": base, "count": 0, "rows": []}

        clean = " ".join(q.split()).lower()
        raw_tokens = self._tokenize(clean)
        numeric = [t for t in raw_tokens if t.isdigit()]
        lexical = [t for t in raw_tokens if len(t) >= 3 and t not in self.STOPWORDS and not t.isdigit()]
        candidates = (numeric + lexical)[:6]
        if not candidates and clean not in {"trabajador", "trabajadores", "empleado", "empleados"}:
            return {"ok": True, "base": base, "count": 0, "rows": []}
        sql = """
        SELECT
          t.idtramite,
          t.estado,
          t.fecharegistro,
          w.numerodocumento,
          w.primerapellido,
          w.segundoapellido,
          w.primernombre,
          w.segundonombre,
          e.numerodocumentoempleador,
          e.razonsocialempleador,
          COALESCE(a.cantiadj, 0) AS cantiadj,
          a.ruta_primera
        FROM proc_servicios_obtenertramites t
        LEFT JOIN proc_servicios_obtenertrabajadortramite w ON w.idtramite = t.idtramite
        LEFT JOIN proc_servicios_obtenerempleadortramite e ON e.idtramite = t.idtramite
        LEFT JOIN (
          SELECT
            idtramite,
            COUNT(*) AS cantiadj,
            MIN(rutaadjunto) AS ruta_primera
          FROM proc_servicios_obtenerarchivosadjuntos
          GROUP BY idtramite
        ) a ON a.idtramite = t.idtramite
        ORDER BY t.fecharegistro DESC NULLS LAST, t.idtramite DESC
        LIMIT :hard_limit
        """
        params = {
            "hard_limit": 800,
        }
        rows = fetch_all_by_alias(base, sql, params)
        q_phrase = clean
        scored: list[tuple[float, bool, dict[str, Any]]] = []
        for row in rows:
            idt = str(row.get("idtramite") or "").strip()
            estado = str(row.get("estado") or "").strip()
            trabajador = " ".join(
                [
                    str(row.get("primerapellido") or "").strip(),
                    str(row.get("segundoapellido") or "").strip(),
                    str(row.get("primernombre") or "").strip(),
                    str(row.get("segundonombre") or "").strip(),
                ]
            ).strip()
            trabajador_doc = str(row.get("numerodocumento") or "").strip()
            empleador = str(row.get("razonsocialempleador") or "").strip()
            empleador_doc = str(row.get("numerodocumentoempleador") or "").strip()
            joined = " ".join([idt, estado, trabajador, trabajador_doc, empleador, empleador_doc]).lower()
            words = self._tokenize(joined)
            score = 0.0
            phrase_hit = bool(q_phrase and len(q_phrase) >= 5 and q_phrase in joined)
            if phrase_hit:
                score += 6.0
            for tok in candidates:
                if tok.isdigit():
                    if tok == idt or tok == trabajador_doc or tok == empleador_doc:
                        score += 4.0
                    elif tok in joined:
                        score += 1.5
                    continue
                if tok in joined:
                    score += 2.0
                elif self._fuzzy_contains(tok, words):
                    score += 1.3
            if score > 0:
                scored.append((score, phrase_hit, row))
        scored.sort(key=lambda x: x[0], reverse=True)

        # Si hay coincidencia exacta de frase y es unica, no mezclar con matches debiles.
        phrase_hits = [item for item in scored if item[1]]
        if len(phrase_hits) == 1 and len(q_phrase) >= 8:
            return {"ok": True, "base": base, "count": 1, "rows": [phrase_hits[0][2]]}

        out = [r for _, _, r in scored[: max(1, min(int(limit), 20))]]
        return {"ok": True, "base": base, "count": len(out), "rows": out}

    def list_recent_workers(self, base: str, limit: int = 8) -> dict[str, Any]:
        sql = """
        SELECT
          t.idtramite,
          t.estado,
          t.fecharegistro,
          w.numerodocumento,
          w.primerapellido,
          w.segundoapellido,
          w.primernombre,
          w.segundonombre,
          e.razonsocialempleador
        FROM proc_servicios_obtenertramites t
        LEFT JOIN proc_servicios_obtenertrabajadortramite w ON w.idtramite = t.idtramite
        LEFT JOIN proc_servicios_obtenerempleadortramite e ON e.idtramite = t.idtramite
        ORDER BY t.fecharegistro DESC NULLS LAST, t.idtramite DESC
        LIMIT :limit
        """
        rows = fetch_all_by_alias(base, sql, {"limit": max(1, min(int(limit), 30))})
        return {"ok": True, "base": base, "count": len(rows), "rows": rows}

    def get_pendientes_prestacion(self, base: str, limit: int = 10) -> dict[str, Any]:
        safe_limit = max(1, min(int(limit), 50))
        out = {
            "ok": True,
            "base": base,
            "total": 0,
            "sources": [],
            "rows": [],
        }

        # Notificaciones: estado_flujo contiene "PENDIENTE ... PRESTACION"
        try:
            rows_not = fetch_all_by_alias(
                base,
                """
                SELECT
                  solicitud_id::text AS id_ref,
                  tramite::text AS tramite,
                  COALESCE(estado_flujo, '') AS estado,
                  COALESCE(usuario_insert, '') AS usuario,
                  COALESCE(tipo_solicitud, '') AS modulo
                FROM auxilios.not_solicitudes
                WHERE UPPER(COALESCE(estado_flujo, '')) LIKE '%PENDIENTE%PRESTACION%'
                ORDER BY solicitud_id DESC
                LIMIT :limit
                """,
                {"limit": safe_limit},
            )
            total_not = fetch_all_by_alias(
                base,
                """
                SELECT COUNT(*)::int AS n
                FROM auxilios.not_solicitudes
                WHERE UPPER(COALESCE(estado_flujo, '')) LIKE '%PENDIENTE%PRESTACION%'
                """,
                {},
            )
            n_not = int((total_not[0].get("n") if total_not else 0) or 0)
            out["total"] += n_not
            out["sources"].append({"table": "auxilios.not_solicitudes", "count": n_not})
            for r in rows_not:
                rr = dict(r)
                rr["source_table"] = "auxilios.not_solicitudes"
                out["rows"].append(rr)
        except Exception:
            out["sources"].append({"table": "auxilios.not_solicitudes", "count": None, "error": "not_available"})

        # Funerarios: no siempre hay estado literal "pendiente prestación", pero se captura si existe.
        try:
            rows_fun = fetch_all_by_alias(
                base,
                """
                SELECT
                  COALESCE(tramite, '')::text AS id_ref,
                  COALESCE(tramite, '')::text AS tramite,
                  COALESCE(estado_flujo, '') AS estado,
                  COALESCE(usuario_asignado, '') AS usuario,
                  'funerarios'::text AS modulo
                FROM auxilios.fun_solicitudes
                WHERE UPPER(COALESCE(estado_flujo, '')) LIKE '%PENDIENTE%PRESTACION%'
                ORDER BY tramite DESC
                LIMIT :limit
                """,
                {"limit": safe_limit},
            )
            total_fun = fetch_all_by_alias(
                base,
                """
                SELECT COUNT(*)::int AS n
                FROM auxilios.fun_solicitudes
                WHERE UPPER(COALESCE(estado_flujo, '')) LIKE '%PENDIENTE%PRESTACION%'
                """,
                {},
            )
            n_fun = int((total_fun[0].get("n") if total_fun else 0) or 0)
            out["total"] += n_fun
            out["sources"].append({"table": "auxilios.fun_solicitudes", "count": n_fun})
            for r in rows_fun:
                rr = dict(r)
                rr["source_table"] = "auxilios.fun_solicitudes"
                out["rows"].append(rr)
        except Exception:
            out["sources"].append({"table": "auxilios.fun_solicitudes", "count": None, "error": "not_available"})

        out["rows"] = out["rows"][:safe_limit]
        return out

    def list_bancos(self, base: str, limit: int = 20) -> dict[str, Any]:
        safe_limit = max(1, min(int(limit), 100))
        out = {"ok": True, "base": base, "total": 0, "rows": []}
        try:
            rows = fetch_all_by_alias(
                base,
                """
                SELECT
                  COALESCE(cod_banco::text, '') AS codigo,
                  COALESCE(nom_banco, '') AS nombre
                FROM auxilios.fun_bancos
                ORDER BY cod_banco
                LIMIT :limit
                """,
                {"limit": safe_limit},
            )
            total = fetch_all_by_alias(base, "SELECT COUNT(*)::int AS n FROM auxilios.fun_bancos", {})
            out["total"] = int((total[0].get("n") if total else 0) or 0)
            out["rows"] = [dict(r) for r in rows]
        except Exception:
            out["rows"] = []
            out["total"] = 0
        return out

    def get_pending_summary(self, base: str, limit: int = 10) -> dict[str, Any]:
        safe_limit = max(1, min(int(limit), 50))
        out = {
            "ok": True,
            "base": base,
            "total": 0,
            "notificaciones_total": 0,
            "funerarios_total": 0,
            "rows": [],
        }
        try:
            total_not = fetch_all_by_alias(
                base,
                """
                SELECT COUNT(*)::int AS n
                FROM auxilios.not_solicitudes
                WHERE
                  UPPER(COALESCE(estado_flujo, '')) LIKE '%PENDIENTE%'
                  OR UPPER(COALESCE(estado_flujo, '')) NOT IN (
                    'FINALIZADO', 'PRESTACION GENERADA', 'RECHAZADA', 'CERRADO', 'PAGADO'
                  )
                """,
                {},
            )
            out["notificaciones_total"] = int((total_not[0].get("n") if total_not else 0) or 0)
            rows_not = fetch_all_by_alias(
                base,
                """
                SELECT
                  'notificaciones'::text AS modulo,
                  solicitud_id::text AS id_ref,
                  COALESCE(tramite, '')::text AS tramite,
                  COALESCE(estado_flujo, '') AS estado,
                  COALESCE(usuario_insert, '') AS usuario
                FROM auxilios.not_solicitudes
                WHERE
                  UPPER(COALESCE(estado_flujo, '')) LIKE '%PENDIENTE%'
                  OR UPPER(COALESCE(estado_flujo, '')) NOT IN (
                    'FINALIZADO', 'PRESTACION GENERADA', 'RECHAZADA', 'CERRADO', 'PAGADO'
                  )
                ORDER BY solicitud_id DESC
                LIMIT :limit
                """,
                {"limit": safe_limit},
            )
            out["rows"].extend([dict(r) for r in rows_not])
        except Exception:
            pass

        try:
            total_fun = fetch_all_by_alias(
                base,
                """
                SELECT COUNT(*)::int AS n
                FROM auxilios.fun_solicitudes
                WHERE
                  UPPER(COALESCE(estado_flujo, '')) LIKE '%PENDIENTE%'
                  OR UPPER(COALESCE(estado_flujo, '')) IN (
                    'ASIGNADO', 'SOLICITADO', 'APROBADO'
                  )
                """,
                {},
            )
            out["funerarios_total"] = int((total_fun[0].get("n") if total_fun else 0) or 0)
            rows_fun = fetch_all_by_alias(
                base,
                """
                SELECT
                  'funerarios'::text AS modulo,
                  COALESCE(tramite, '')::text AS id_ref,
                  COALESCE(tramite, '')::text AS tramite,
                  COALESCE(estado_flujo, '') AS estado,
                  ''::text AS usuario
                FROM auxilios.fun_solicitudes
                WHERE
                  UPPER(COALESCE(estado_flujo, '')) LIKE '%PENDIENTE%'
                  OR UPPER(COALESCE(estado_flujo, '')) IN (
                    'ASIGNADO', 'SOLICITADO', 'APROBADO'
                  )
                ORDER BY tramite DESC
                LIMIT :limit
                """,
                {"limit": safe_limit},
            )
            out["rows"].extend([dict(r) for r in rows_fun])
        except Exception:
            pass

        out["total"] = int(out["notificaciones_total"]) + int(out["funerarios_total"])
        out["rows"] = out["rows"][:safe_limit]
        return out

    def search_operational_context(self, base: str, question: str, limit: int = 8) -> dict[str, Any]:
        q = (question or "").strip()
        if not q:
            return {"ok": True, "base": base, "count": 0, "rows": []}

        raw_tokens = self._tokenize(q.lower())
        numeric = [t for t in raw_tokens if t.isdigit()]
        lexical = [t for t in raw_tokens if len(t) >= 3 and not t.isdigit() and t not in self.STOPWORDS]
        candidates = (numeric + lexical)[:8]
        if not candidates:
            return {"ok": True, "base": base, "count": 0, "rows": []}

        rows: list[dict[str, Any]] = []
        hard_limit = 400

        # Notificaciones
        try:
            rows_not = fetch_all_by_alias(
                base,
                """
                SELECT
                  'notificaciones'::text AS modulo,
                  solicitud_id::text AS id_ref,
                  COALESCE(tramite, '')::text AS tramite,
                  COALESCE(estado_flujo, '') AS estado,
                  COALESCE(usuario_insert, '') AS usuario,
                  COALESCE(tipo_solicitud, '') AS extra
                FROM auxilios.not_solicitudes
                ORDER BY solicitud_id DESC
                LIMIT :limit
                """,
                {"limit": hard_limit},
            )
            rows.extend(dict(r) for r in rows_not)
        except Exception:
            pass

        # Funerarios
        try:
            rows_fun = fetch_all_by_alias(
                base,
                """
                SELECT
                  'funerarios'::text AS modulo,
                  COALESCE(tramite, '')::text AS id_ref,
                  COALESCE(tramite, '')::text AS tramite,
                  COALESCE(estado_flujo, '') AS estado,
                  ''::text AS usuario,
                  ''::text AS extra
                FROM auxilios.fun_solicitudes
                ORDER BY tramite DESC
                LIMIT :limit
                """,
                {"limit": hard_limit},
            )
            rows.extend(dict(r) for r in rows_fun)
        except Exception:
            pass

        # Reclamantes funerarios
        try:
            rows_rec = fetch_all_by_alias(
                base,
                """
                SELECT
                  'funerarios_reclamantes'::text AS modulo,
                  COALESCE(id, 0)::text AS id_ref,
                  COALESCE(tramite, '')::text AS tramite,
                  COALESCE(estado_reclamante, '') AS estado,
                  COALESCE(identificacion, '') AS usuario,
                  COALESCE(nombres_reclamante, '') AS extra
                FROM auxilios.fun_reclamantes
                ORDER BY id DESC
                LIMIT :limit
                """,
                {"limit": hard_limit},
            )
            rows.extend(dict(r) for r in rows_rec)
        except Exception:
            pass

        # Pagos reclamantes
        try:
            rows_pay = fetch_all_by_alias(
                base,
                """
                SELECT
                  'funerarios_pagos'::text AS modulo,
                  COALESCE(id, 0)::text AS id_ref,
                  COALESCE(tramite, '')::text AS tramite,
                  COALESCE(estado, '') AS estado,
                  COALESCE(usuario_carga, '') AS usuario,
                  COALESCE(id_reclamante, '')::text AS extra
                FROM auxilios.fun_pagos_reclamantes
                ORDER BY id DESC
                LIMIT :limit
                """,
                {"limit": hard_limit},
            )
            rows.extend(dict(r) for r in rows_pay)
        except Exception:
            pass

        # Log notificaciones
        try:
            rows_not_log = fetch_all_by_alias(
                base,
                """
                SELECT
                  'notificaciones_log'::text AS modulo,
                  COALESCE(id, 0)::text AS id_ref,
                  COALESCE(solicitud_id, '')::text AS tramite,
                  COALESCE(estado_actual, '') AS estado,
                  COALESCE(usuario, '') AS usuario,
                  COALESCE(observacion, '') AS extra
                FROM auxilios.not_log
                ORDER BY id DESC
                LIMIT :limit
                """,
                {"limit": hard_limit},
            )
            rows.extend(dict(r) for r in rows_not_log)
        except Exception:
            pass

        # Bloqueo solicitudes (estado global)
        try:
            rows_blk = fetch_all_by_alias(
                base,
                """
                SELECT
                  'notificaciones_bloqueo'::text AS modulo,
                  COALESCE(na, 0)::text AS id_ref,
                  ''::text AS tramite,
                  CASE COALESCE(estado, -1)
                    WHEN 1 THEN 'Activo'
                    WHEN 0 THEN 'Inactivo'
                    ELSE ''
                  END AS estado,
                  COALESCE(usuario, '') AS usuario,
                  COALESCE(fecha_bloqueo::text, '') AS extra
                FROM auxilios.not_bloqueo
                ORDER BY na DESC
                LIMIT :limit
                """,
                {"limit": hard_limit},
            )
            rows.extend(dict(r) for r in rows_blk)
        except Exception:
            pass

        scored: list[tuple[float, dict[str, Any]]] = []
        for row in rows:
            joined = " ".join(
                [
                    str(row.get("modulo") or ""),
                    str(row.get("id_ref") or ""),
                    str(row.get("tramite") or ""),
                    str(row.get("estado") or ""),
                    str(row.get("usuario") or ""),
                    str(row.get("extra") or ""),
                ]
            ).lower()
            words = self._tokenize(joined)
            score = 0.0
            exact_hits = 0
            for tok in candidates:
                if tok.isdigit():
                    if tok == str(row.get("id_ref") or "") or tok == str(row.get("tramite") or ""):
                        score += 4.0
                        exact_hits += 1
                    elif tok in joined:
                        score += 1.5
                    continue
                if tok in joined:
                    score += 2.0
                    exact_hits += 1
                elif self._fuzzy_contains(tok, words):
                    score += 1.2
            if score >= 2.0 and exact_hits >= 1:
                scored.append((score, row))

        scored.sort(key=lambda x: x[0], reverse=True)
        out = [r for _, r in scored[: max(1, min(int(limit), 30))]]
        return {"ok": True, "base": base, "count": len(out), "rows": out}

    def search_afiliaciones_context(
        self,
        *,
        base: str,
        question: str,
        lote: str = "",
        idtramite: str = "",
        limit: int = 10,
    ) -> dict[str, Any]:
        q = " ".join((question or "").split()).strip()
        safe_limit = max(1, min(int(limit), 50))
        out_rows: list[dict[str, Any]] = []

        raw_tokens = self._tokenize(q.lower())
        numeric = [t for t in raw_tokens if t.isdigit()]
        lexical = [t for t in raw_tokens if len(t) >= 3 and not t.isdigit() and t not in self.STOPWORDS]
        candidates = (numeric + lexical)[:8]

        filters: dict[str, Any] = {"limit": 120}
        where_proc = "1=1"
        if idtramite.strip():
            where_proc += " AND t.idtramite::text = :idtramite"
            filters["idtramite"] = idtramite.strip()
        if lote.strip():
            where_proc += " AND COALESCE(t.lote::text, '') = :lote"
            filters["lote"] = lote.strip()

        try:
            rows_proc = fetch_all_by_alias(
                base,
                f"""
                SELECT
                  'proc_servicios'::text AS source_table,
                  t.idtramite::text AS idtramite,
                  COALESCE(t.lote::text, '') AS lote,
                  COALESCE(t.estado, '') AS estado,
                  COALESCE(e.numerodocumentoempleador, '') AS nit_empleador,
                  COALESCE(e.razonsocialempleador, '') AS empleador,
                  COALESCE(e.actividadeconomicaempleador, '') AS actividad,
                  COALESCE(e.tipoaportante, '') AS tipo_aportante,
                  COALESCE(w.numerodocumento, '') AS documento_trabajador,
                  COALESCE(w.tipodocumento, '') AS tipodoc_trabajador,
                  COALESCE(w.primerapellido, '') AS primerapellido,
                  COALESCE(w.segundoapellido, '') AS segundoapellido,
                  COALESCE(w.primernombre, '') AS primernombre,
                  COALESCE(w.segundonombre, '') AS segundonombre
                FROM proc_servicios_obtenertramites t
                LEFT JOIN proc_servicios_obtenerempleadortramite e ON e.idtramite = t.idtramite
                LEFT JOIN proc_servicios_obtenertrabajadortramite w ON w.idtramite = t.idtramite
                WHERE {where_proc}
                ORDER BY t.idtramite DESC
                LIMIT :limit
                """,
                filters,
            )
            out_rows.extend(dict(r) for r in rows_proc)
        except Exception:
            pass

        # Refuerzo global: cuando no hay lote/idtrámite, traer candidatos por texto normalizado
        # (sin tildes/ñ) para no depender solo de los últimos N registros.
        if (not lote.strip()) and (not idtramite.strip()) and candidates:
            primary = str(candidates[0] or "").strip().lower()
            if primary:
                # stem corto para tolerar variaciones leves y nombres con tildes.
                stem = re.sub(r"[^a-z0-9]", "", primary)[:4]
                token_norm = stem if len(stem) >= 3 else primary
                pattern_norm = f"%{token_norm}%"
                try:
                    rows_proc_global = fetch_all_by_alias(
                        base,
                        """
                        SELECT
                          'proc_servicios_global_search'::text AS source_table,
                          t.idtramite::text AS idtramite,
                          COALESCE(t.lote::text, '') AS lote,
                          COALESCE(t.estado, '') AS estado,
                          COALESCE(e.numerodocumentoempleador, '') AS nit_empleador,
                          COALESCE(e.razonsocialempleador, '') AS empleador,
                          COALESCE(e.actividadeconomicaempleador, '') AS actividad,
                          COALESCE(e.tipoaportante, '') AS tipo_aportante,
                          COALESCE(w.numerodocumento, '') AS documento_trabajador,
                          COALESCE(w.tipodocumento, '') AS tipodoc_trabajador,
                          COALESCE(w.primerapellido, '') AS primerapellido,
                          COALESCE(w.segundoapellido, '') AS segundoapellido,
                          COALESCE(w.primernombre, '') AS primernombre,
                          COALESCE(w.segundonombre, '') AS segundonombre
                        FROM proc_servicios_obtenertramites t
                        LEFT JOIN proc_servicios_obtenerempleadortramite e ON e.idtramite = t.idtramite
                        LEFT JOIN proc_servicios_obtenertrabajadortramite w ON w.idtramite = t.idtramite
                        WHERE
                          translate(lower(COALESCE(e.razonsocialempleador, '')), 'áéíóúñ', 'aeioun') LIKE :pattern
                          OR translate(lower(COALESCE(e.numerodocumentoempleador, '')), 'áéíóúñ', 'aeioun') LIKE :pattern
                          OR translate(lower(COALESCE(w.numerodocumento, '')), 'áéíóúñ', 'aeioun') LIKE :pattern
                          OR translate(
                                lower(
                                  CONCAT_WS(
                                    ' ',
                                    COALESCE(w.primerapellido, ''),
                                    COALESCE(w.segundoapellido, ''),
                                    COALESCE(w.primernombre, ''),
                                    COALESCE(w.segundonombre, '')
                                  )
                                ),
                                'áéíóúñ',
                                'aeioun'
                              ) LIKE :pattern
                        ORDER BY t.idtramite DESC
                        LIMIT :limit
                        """,
                        {"pattern": pattern_norm, "limit": 500},
                    )
                    out_rows.extend(dict(r) for r in rows_proc_global)
                except Exception:
                    pass
                try:
                    rows_wd_global = fetch_all_by_alias(
                        base,
                        """
                        SELECT
                          'brafiliadosarp_global_search'::text AS source_table,
                          ''::text AS idtramite,
                          COALESCE(lt::text, '') AS lote,
                          ''::text AS estado,
                          ''::text AS nit_empleador,
                          ''::text AS empleador,
                          COALESCE(f28, '') AS documento_trabajador,
                          COALESCE(f29::text, '') AS tipodoc_trabajador,
                          COALESCE(f31, '') AS primerapellido,
                          COALESCE(f32, '') AS segundoapellido,
                          COALESCE(f33, '') AS primernombre,
                          COALESCE(f34, '') AS segundonombre
                        FROM brafiliadosarp
                        WHERE
                          translate(
                            lower(
                              COALESCE(f31, '') || ' ' || COALESCE(f32, '') || ' ' || COALESCE(f33, '') || ' ' || COALESCE(f34, '')
                            ),
                            'áéíóúñ',
                            'aeioun'
                          ) LIKE :pattern
                          OR translate(lower(COALESCE(f28, '')), 'áéíóúñ', 'aeioun') LIKE :pattern
                        ORDER BY lt DESC, sr
                        LIMIT :limit
                        """,
                        {"pattern": pattern_norm, "limit": 500},
                    )
                    out_rows.extend(dict(r) for r in rows_wd_global)
                except Exception:
                    pass
                try:
                    rows_wh_global = fetch_all_by_alias(
                        base,
                        """
                        SELECT
                          'brempresasarp_global_search'::text AS source_table,
                          ''::text AS idtramite,
                          COALESCE(lt::text, '') AS lote,
                          ''::text AS estado,
                          COALESCE(f48::text, '') AS nit_empleador,
                          COALESCE(f51, '') AS empleador,
                          ''::text AS documento_trabajador,
                          ''::text AS tipodoc_trabajador,
                          ''::text AS primerapellido,
                          ''::text AS segundoapellido,
                          ''::text AS primernombre,
                          ''::text AS segundonombre
                        FROM brempresasarp
                        WHERE
                          translate(lower(COALESCE(f51, '')), 'áéíóúñ', 'aeioun') LIKE :pattern
                          OR translate(lower(COALESCE(f48::text, '')), 'áéíóúñ', 'aeioun') LIKE :pattern
                        ORDER BY lt DESC, sr
                        LIMIT :limit
                        """,
                        {"pattern": pattern_norm, "limit": 500},
                    )
                    out_rows.extend(dict(r) for r in rows_wh_global)
                except Exception:
                    pass

        lote_for_legacy = lote.strip() or (numeric[0] if numeric else "")
        if lote_for_legacy:
            try:
                rows_wh = fetch_all_by_alias(
                    base,
                    """
                    SELECT
                      'brempresasarp'::text AS source_table,
                      COALESCE(lt::text, '') AS lote,
                      COALESCE(sr::text, '') AS sr,
                      COALESCE(tp, '') AS tp,
                      COALESCE(f48::text, '') AS nit_empleador,
                      COALESCE(f51, '') AS empleador,
                      COALESCE(f15::text, '') AS ciudad,
                      COALESCE(f12, '') AS direccion,
                      COALESCE(f14::text, '') AS telefono,
                      COALESCE(clase, '') AS clase
                    FROM brempresasarp
                    WHERE lt::text = :lote
                    ORDER BY sr
                    LIMIT 20
                    """,
                    {"lote": lote_for_legacy},
                )
                out_rows.extend(dict(r) for r in rows_wh)
            except Exception:
                pass

            try:
                rows_wd = fetch_all_by_alias(
                    base,
                    """
                    SELECT
                      'brafiliadosarp'::text AS source_table,
                      COALESCE(lt::text, '') AS lote,
                      COALESCE(sr::text, '') AS sr,
                      COALESCE(f28, '') AS documento_trabajador,
                      COALESCE(f29::text, '') AS tipodoc_codigo,
                      COALESCE(f31, '') AS primerapellido,
                      COALESCE(f32, '') AS segundoapellido,
                      COALESCE(f33, '') AS primernombre,
                      COALESCE(f35::text, '') AS fechanacimiento,
                      COALESCE(f37, '') AS cargo,
                      COALESCE(f38::text, '') AS ingreso
                    FROM brafiliadosarp
                    WHERE lt::text = :lote
                    ORDER BY sr
                    LIMIT 80
                    """,
                    {"lote": lote_for_legacy},
                )
                out_rows.extend(dict(r) for r in rows_wd)
            except Exception:
                pass

        if not candidates and not idtramite.strip() and not lote.strip():
            return {"ok": True, "base": base, "count": 0, "rows": []}

        scored: list[tuple[float, dict[str, Any]]] = []
        for row in out_rows:
            joined = " ".join(str(v or "") for v in row.values()).lower()
            words = self._tokenize(joined)
            score = 0.0
            exact_hits = 0
            for tok in candidates:
                if tok.isdigit():
                    if tok in {str(row.get("idtramite") or ""), str(row.get("lote") or ""), str(row.get("documento_trabajador") or ""), str(row.get("nit_empleador") or "")}:
                        score += 4.0
                        exact_hits += 1
                    elif tok in joined:
                        score += 1.4
                    continue
                if tok in joined:
                    score += 2.0
                    exact_hits += 1
                elif self._fuzzy_contains(tok, words):
                    score += 1.1
            if score > 0 or (idtramite.strip() and str(row.get("idtramite") or "") == idtramite.strip()):
                scored.append((score, row))

        scored.sort(key=lambda x: x[0], reverse=True)
        # Importante: si hay términos de búsqueda y no hubo score, NO devolver
        # todo el lote/trámite porque genera falsos positivos contextuales.
        if not scored and (idtramite.strip() or lote.strip()):
            if candidates:
                return {"ok": True, "base": base, "count": 0, "rows": []}
            return {"ok": True, "base": base, "count": min(len(out_rows), safe_limit), "rows": out_rows[:safe_limit]}
        if not scored and candidates and (not idtramite.strip()) and (not lote.strip()):
            # Búsqueda global de respaldo por LIKE (empresa/trabajador/documentos),
            # para consultas fuera del lote actual.
            try:
                pattern = "%" + " ".join(candidates[:3]) + "%"
                rows_global = fetch_all_by_alias(
                    base,
                    """
                    SELECT
                      'proc_servicios_global'::text AS source_table,
                      t.idtramite::text AS idtramite,
                      COALESCE(t.lote::text, '') AS lote,
                      COALESCE(t.estado, '') AS estado,
                      COALESCE(e.numerodocumentoempleador, '') AS nit_empleador,
                      COALESCE(e.razonsocialempleador, '') AS empleador,
                      COALESCE(w.numerodocumento, '') AS documento_trabajador,
                      COALESCE(w.primerapellido, '') AS primerapellido,
                      COALESCE(w.segundoapellido, '') AS segundoapellido,
                      COALESCE(w.primernombre, '') AS primernombre,
                      COALESCE(w.segundonombre, '') AS segundonombre
                    FROM proc_servicios_obtenertramites t
                    LEFT JOIN proc_servicios_obtenerempleadortramite e ON e.idtramite = t.idtramite
                    LEFT JOIN proc_servicios_obtenertrabajadortramite w ON w.idtramite = t.idtramite
                    WHERE
                      LOWER(COALESCE(e.razonsocialempleador, '')) LIKE LOWER(:pattern)
                      OR COALESCE(e.numerodocumentoempleador, '') LIKE :pattern
                      OR COALESCE(w.numerodocumento, '') LIKE :pattern
                      OR LOWER(
                        CONCAT_WS(' ',
                          COALESCE(w.primerapellido, ''),
                          COALESCE(w.segundoapellido, ''),
                          COALESCE(w.primernombre, ''),
                          COALESCE(w.segundonombre, '')
                        )
                      ) LIKE LOWER(:pattern)
                    ORDER BY t.idtramite DESC
                    LIMIT :limit
                    """,
                    {"pattern": pattern, "limit": safe_limit},
                )
                if rows_global:
                    return {
                        "ok": True,
                        "base": base,
                        "count": min(len(rows_global), safe_limit),
                        "rows": [dict(r) for r in rows_global[:safe_limit]],
                    }
            except Exception:
                pass
        return {"ok": True, "base": base, "count": min(len(scored), safe_limit), "rows": [r for _, r in scored[:safe_limit]]}

    def afiliaciones_dimensional_snapshot(
        self,
        *,
        base: str,
        lote: str = "",
        idtramite: str = "",
        limit: int = 200,
    ) -> dict[str, Any]:
        safe_limit = max(1, min(int(limit), 1000))
        out: dict[str, Any] = {
            "ok": True,
            "base": base,
            "lote": lote,
            "idtramite": idtramite,
            "empleadores": [],
            "sedes": [],
            "trabajadores": [],
            "adjuntos": [],
            "salarios_total": 0,
        }

        params: dict[str, Any] = {"limit": safe_limit}
        where_proc = "1=1"
        if idtramite.strip():
            where_proc += " AND t.idtramite::text = :idtramite"
            params["idtramite"] = idtramite.strip()
        elif lote.strip():
            where_proc += " AND COALESCE(t.lote::text, '') = :lote"
            params["lote"] = lote.strip()

        try:
            empleadores = fetch_all_by_alias(
                base,
                f"""
                SELECT
                  t.idtramite::text AS idtramite,
                  COALESCE(t.lote::text, '') AS lote,
                  COALESCE(e.numerodocumentoempleador, '') AS nit_empleador,
                  COALESCE(e.razonsocialempleador, '') AS empleador,
                  COALESCE(e.actividadeconomicaempleador, '') AS actividad,
                  COALESCE(e.tipoaportante, '') AS tipo_aportante,
                  COALESCE(e.nombrerepresentantelegal, '') AS representante_legal,
                  COALESCE(e.tipodocumentorepresentantelegal, '') AS tipo_doc_representante,
                  COALESCE(e.numerodocumentorepresnetantelegal, '') AS doc_representante,
                  COALESCE(e.ciudadempleador, '') AS ciudad,
                  COALESCE(e.zonaempleador, '') AS zona,
                  COALESCE(e.localidadempleador, '') AS localidad,
                  COALESCE(e.direccionempleador, '') AS direccion,
                  COALESCE(e.telefonoprincipalempleador, '') AS telefono,
                  COALESCE(e.telefonocelularempleador, '') AS celular
                FROM proc_servicios_obtenertramites t
                LEFT JOIN proc_servicios_obtenerempleadortramite e ON e.idtramite = t.idtramite
                WHERE {where_proc}
                ORDER BY t.idtramite DESC
                LIMIT :limit
                """,
                params,
            )
            out["empleadores"] = [dict(r) for r in empleadores]
        except Exception:
            out["empleadores"] = []

        try:
            trab = fetch_all_by_alias(
                base,
                f"""
                SELECT
                  t.idtramite::text AS idtramite,
                  COALESCE(t.lote::text, '') AS lote,
                  COALESCE(w.tipodocumento, '') AS tipodoc,
                  COALESCE(w.numerodocumento, '') AS documento,
                  COALESCE(w.primerapellido, '') AS primerapellido,
                  COALESCE(w.segundoapellido, '') AS segundoapellido,
                  COALESCE(w.primernombre, '') AS primernombre,
                  COALESCE(w.segundonombre, '') AS segundonombre,
                  COALESCE(w.ciudad, '') AS ciudad,
                  COALESCE(w.actividadeconomica, '') AS actividad,
                  COALESCE(w.claseriesgo, '') AS riesgo,
                  COALESCE(w.fecha_nacimiento::text, '') AS fecha_nacimiento
                FROM proc_servicios_obtenertramites t
                LEFT JOIN proc_servicios_obtenertrabajadortramite w ON w.idtramite = t.idtramite
                WHERE {where_proc}
                ORDER BY t.idtramite DESC
                LIMIT :limit
                """,
                params,
            )
            out["trabajadores"] = [dict(r) for r in trab]
        except Exception:
            out["trabajadores"] = []

        # Priorizar sedes operativas de proc_servicios cuando hay idtramite/contexto.
        try:
            sedes_proc = fetch_all_by_alias(
                base,
                f"""
                SELECT
                  t.idtramite::text AS idtramite,
                  COALESCE(t.lote::text, '') AS lote,
                  'S'::text AS tp,
                  COALESCE(s.nombresede, '') AS nombre,
                  COALESCE(s.direccion, '') AS direccion,
                  COALESCE(s.ciudad, '') AS ciudad,
                  COALESCE(s.zona, '') AS zona,
                  COALESCE(s.localidad, '') AS localidad,
                  COALESCE(s.departamento, '') AS departamento,
                  COALESCE(s.telefono, '') AS telefono,
                  COALESCE(e.numerodocumentoempleador, '') AS nit_empleador,
                  ''::text AS riesgo
                FROM proc_servicios_obtenertramites t
                LEFT JOIN proc_servicios_obtenersedetramite s ON s.idtramite = t.idtramite
                LEFT JOIN proc_servicios_obtenerempleadortramite e ON e.idtramite = t.idtramite
                WHERE {where_proc}
                ORDER BY t.idtramite DESC, s.sr
                LIMIT :limit
                """,
                params,
            )
            sedes_proc_clean = [dict(r) for r in sedes_proc if str(r.get("nombre") or "").strip() or str(r.get("direccion") or "").strip()]
            if sedes_proc_clean:
                out["sedes"] = sedes_proc_clean
        except Exception:
            if "sedes" not in out:
                out["sedes"] = []

        lote_legacy = lote.strip()
        if lote_legacy:
            if not out.get("sedes"):
                try:
                    sedes = fetch_all_by_alias(
                        base,
                        """
                        SELECT
                          COALESCE(lt::text, '') AS lote,
                          COALESCE(sr::text, '') AS sr,
                          COALESCE(tp, '') AS tp,
                          COALESCE(f51, '') AS nombre,
                          COALESCE(f12, '') AS direccion,
                          COALESCE(f15::text, '') AS ciudad,
                          ''::text AS zona,
                          ''::text AS localidad,
                          ''::text AS departamento,
                          COALESCE(f14::text, '') AS telefono,
                          COALESCE(f48::text, '') AS nit_empleador,
                          COALESCE(clase, '') AS riesgo
                        FROM brempresasarp
                        WHERE lt::text = :lote
                        ORDER BY sr
                        LIMIT 100
                        """,
                        {"lote": lote_legacy},
                    )
                    out["sedes"] = [dict(r) for r in sedes]
                except Exception:
                    out["sedes"] = out.get("sedes", [])
            # Fallback empleador desde tabla legacy BR (tp=P) cuando proc_servicios no trae lote.
            if not out["empleadores"]:
                try:
                    br_emp = fetch_all_by_alias(
                        base,
                        """
                        SELECT
                          ''::text AS idtramite,
                          COALESCE(lt::text, '') AS lote,
                          COALESCE(f48::text, '') AS nit_empleador,
                          COALESCE(f51, '') AS empleador,
                          ''::text AS actividad,
                          ''::text AS tipo_aportante,
                          ''::text AS representante_legal,
                          ''::text AS tipo_doc_representante,
                          ''::text AS doc_representante,
                          COALESCE(f15::text, '') AS ciudad,
                          ''::text AS zona,
                          ''::text AS localidad,
                          COALESCE(f12, '') AS direccion,
                          COALESCE(f14::text, '') AS telefono,
                          ''::text AS celular
                        FROM brempresasarp
                        WHERE lt::text = :lote AND UPPER(COALESCE(tp,'')) = 'P'
                        ORDER BY sr
                        LIMIT 10
                        """,
                        {"lote": lote_legacy},
                    )
                    out["empleadores"] = [dict(r) for r in br_emp]
                except Exception:
                    out["empleadores"] = out["empleadores"]
            # Fallback trabajadores desde BR afiliados.
            if not out["trabajadores"]:
                try:
                    br_trab = fetch_all_by_alias(
                        base,
                        """
                        SELECT
                          ''::text AS idtramite,
                          COALESCE(lt::text, '') AS lote,
                          COALESCE(f29::text, '') AS tipodoc,
                          COALESCE(f28, '') AS documento,
                          COALESCE(f31, '') AS primerapellido,
                          COALESCE(f32, '') AS segundoapellido,
                          COALESCE(f33, '') AS primernombre,
                          ''::text AS segundonombre,
                          ''::text AS ciudad,
                          ''::text AS actividad,
                          ''::text AS riesgo,
                          COALESCE(f35::text, '') AS fecha_nacimiento
                        FROM brafiliadosarp
                        WHERE lt::text = :lote
                        ORDER BY sr
                        LIMIT 5000
                        """,
                        {"lote": lote_legacy},
                    )
                    out["trabajadores"] = [dict(r) for r in br_trab]
                except Exception:
                    out["trabajadores"] = out["trabajadores"]
            try:
                wd_rows = fetch_all_by_alias(
                    base,
                    """
                    SELECT COALESCE(f28, '') AS documento, COALESCE(f38::text, '') AS salario
                    FROM wd
                    WHERE lt::text = :lote
                    """,
                    {"lote": lote_legacy},
                )
                total = 0
                for r in wd_rows:
                    if not str(r.get("documento") or "").strip():
                        continue
                    s = str(r.get("salario") or "")
                    digits = "".join(ch for ch in s if ch.isdigit())
                    if digits:
                        total += int(digits)
                out["salarios_total"] = int(total)
            except Exception:
                out["salarios_total"] = int(out.get("salarios_total") or 0)

        try:
            where_adj = "1=1"
            adj_params: dict[str, Any] = {"limit": safe_limit}
            if idtramite.strip():
                where_adj += " AND a.idtramite::text = :idtramite"
                adj_params["idtramite"] = idtramite.strip()
            if lote.strip():
                where_adj += " AND COALESCE(t.lote::text, '') = :lote"
                adj_params["lote"] = lote.strip()
            adj = fetch_all_by_alias(
                base,
                f"""
                SELECT
                  a.idtramite::text AS idtramite,
                  COALESCE(t.lote::text, '') AS lote,
                  COALESCE(a.idadjuntostipotramite::text, '') AS tipo_adjunto,
                  COALESCE(a.rutaadjunto, '') AS rutaadjunto
                FROM proc_servicios_obtenerarchivosadjuntos a
                LEFT JOIN proc_servicios_obtenertramites t ON t.idtramite = a.idtramite
                WHERE {where_adj}
                ORDER BY a.idtramite DESC, a.idarchivosadjuntostramite ASC
                LIMIT :limit
                """,
                adj_params,
            )
            out["adjuntos"] = [dict(r) for r in adj]
        except Exception:
            out["adjuntos"] = []

        # Fallback adjuntos: si filtro por lote no retorna (porque proc_servicios no guarda lote), usar último trámite con más adjuntos.
        if not out["adjuntos"]:
            try:
                top = fetch_all_by_alias(
                    base,
                    """
                    SELECT idtramite::text AS idtramite, COUNT(*)::int AS n
                    FROM proc_servicios_obtenerarchivosadjuntos
                    GROUP BY idtramite
                    ORDER BY n DESC, idtramite DESC
                    LIMIT 1
                    """,
                    {},
                )
                top_id = str((top[0].get("idtramite") if top else "") or "").strip()
                if top_id:
                    adj2 = fetch_all_by_alias(
                        base,
                        """
                        SELECT
                          a.idtramite::text AS idtramite,
                          ''::text AS lote,
                          COALESCE(a.idadjuntostipotramite::text, '') AS tipo_adjunto,
                          COALESCE(a.rutaadjunto, '') AS rutaadjunto
                        FROM proc_servicios_obtenerarchivosadjuntos a
                        WHERE a.idtramite::text = :idtramite
                        ORDER BY a.idarchivosadjuntostramite ASC
                        LIMIT :limit
                        """,
                        {"idtramite": top_id, "limit": safe_limit},
                    )
                    out["adjuntos"] = [dict(r) for r in adj2]
            except Exception:
                out["adjuntos"] = out["adjuntos"]

        return out
