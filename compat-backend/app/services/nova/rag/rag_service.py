from __future__ import annotations

import json
import os
import re
import difflib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.db import execute_by_alias, fetch_all_by_alias
from app.core.observability import get_logger

logger = get_logger("app.ai.nova.rag")

WORD_RE = re.compile(r"[a-z0-9áéíóúñ]+", re.IGNORECASE)
STOPWORDS_RAG = {
    "de", "del", "la", "las", "el", "los", "y", "o", "en", "para", "por", "con", "sin",
    "que", "como", "cual", "cuanto", "donde", "cuando", "favor", "necesito", "quiero",
    "documento", "documental", "archivo", "archivos", "soporte", "soportes", "consulta",
}

DEFAULT_KB_DOCS: list[dict[str, Any]] = [
    {
        "doc_id": "kb-funerarios-cierre-reversion",
        "source": "system-kb",
        "text": (
            "Funerarios - Cierre y Reversión: ejecutar cierreMasivo/cierreMasivoAsulado "
            "con origen válido, verificar respuesta 200 y luego ejecutar reversionMasivo cuando aplique. "
            "Confirmar cambios de estado de reclamantes y trazabilidad."
        ),
        "metadata": {"topic": "funerarios", "intent": "cierre_reversion"},
    },
    {
        "doc_id": "kb-notificaciones-gestion",
        "source": "system-kb",
        "text": (
            "Notificaciones - Gestión operativa: consulta afiliado, carga reclamantes, "
            "trae imágenes a validar y guarda post estado/post gestión con campos obligatorios completos."
        ),
        "metadata": {"topic": "notificaciones", "intent": "gestion"},
    },
    {
        "doc_id": "kb-afiliaciones-926",
        "source": "system-kb",
        "text": (
            "Afiliaciones - Archivo 926: primero sincronizar lote y luego generar plano 926. "
            "Entrada recomendada: JSON de lote. Salida esperada: archivo TXT 926."
        ),
        "metadata": {"topic": "afiliaciones", "intent": "archivo_926"},
    },
    {
        "doc_id": "kb-afiliaciones-marco-normativo-core",
        "source": "system-kb",
        "text": (
            "Afiliaciones ARL Colombia - núcleo normativo: Ley 1562 de 2012 (modifica el Sistema de Riesgos Laborales), "
            "Decreto Ley 1295 de 1994 (organización y administración del sistema), y Decreto 1072 de 2015 "
            "(Decreto Único del Sector Trabajo, incluye lineamientos de SG-SST). "
            "NOVA debe priorizar trazabilidad de afiliación, consistencia de datos del empleador/trabajador y cumplimiento documental."
        ),
        "metadata": {"topic": "afiliaciones", "intent": "normativa_core"},
    },
    {
        "doc_id": "kb-afiliaciones-sst-estandares-minimos",
        "source": "system-kb",
        "text": (
            "SG-SST y afiliaciones: Resolución 0312 de 2019 establece estándares mínimos del SG-SST por tamaño/actividad. "
            "En operación de afiliaciones, controlar actividad económica, clase de riesgo, sede/centro de trabajo y cobertura."
        ),
        "metadata": {"topic": "afiliaciones", "intent": "sst_estandares"},
    },
    {
        "doc_id": "kb-afiliaciones-formulario-y-campos",
        "source": "system-kb",
        "text": (
            "Formulario de afiliación/novedades del empleador al SGRL: validar tipo y número de documento, razón social, "
            "representante legal, actividad económica, sede principal, responsables y trabajadores. "
            "Si hay inconsistencias entre OCR y XLSX, marcar revisión manual antes de generar 926."
        ),
        "metadata": {"topic": "afiliaciones", "intent": "formulario_validacion"},
    },
    {
        "doc_id": "kb-afiliaciones-control-calidad-datos",
        "source": "system-kb",
        "text": (
            "Control de calidad de afiliaciones: "
            "1) validar lote TXT y adjuntos, "
            "2) ejecutar OCR en vivo por lote, "
            "3) importar contrato/sede/trabajadores, "
            "4) comparar OCR vs BD vs 926 por campo crítico (empresa, NIT, dirección, ciudad, representante legal), "
            "5) bloquear generación final si hay errores críticos de validación."
        ),
        "metadata": {"topic": "afiliaciones", "intent": "quality_controls"},
    },
    {
        "doc_id": "kb-funerarios-validacion-jefe",
        "source": "system-kb",
        "text": (
            "Funerarios - Validación Jefe: usar la bandeja de validación jefe para revisar casos "
            "pendientes, aplicar decisión por trámite y dejar trazabilidad de usuario/fecha/resultado. "
            "Antes de aprobar, validar estado actual del reclamante, valor reconocido y soporte documental."
        ),
        "metadata": {"topic": "funerarios", "intent": "validacion_jefe"},
    },
    {
        "doc_id": "kb-funerarios-validacion-pagos",
        "source": "system-kb",
        "text": (
            "Funerarios - Validación Pagos: en la bandeja de pagos validar forma de pago, banco, cuenta, "
            "valor reconocido y consistencia con reclamante/trámite. Si hay inconsistencia, rechazar y registrar causal."
        ),
        "metadata": {"topic": "funerarios", "intent": "validacion_pagos"},
    },
    {
        "doc_id": "kb-notificaciones-bandejas",
        "source": "system-kb",
        "text": (
            "Notificaciones - Bandejas: Selección, Bandeja Entrada, Pendiente Validación, Pendiente Prestación, "
            "Prestaciones Generadas y Reporte. Flujo recomendado: cargar pendientes, seleccionar solicitud, "
            "validar imágenes/estado y guardar post estado o post gestión."
        ),
        "metadata": {"topic": "notificaciones", "intent": "bandejas"},
    },
    {
        "doc_id": "kb-admin-permisos-bloqueo",
        "source": "system-kb",
        "text": (
            "Administración - Permisos y Bloqueo Solicitudes: consultar estado actual, activar o desactivar "
            "bloqueo por solicitud/trámite y registrar usuario operador. Verificar resultado de operación y recargar bandeja."
        ),
        "metadata": {"topic": "administracion", "intent": "permisos_bloqueo"},
    },
    {
        "doc_id": "kb-documentos-clasificacion",
        "source": "system-kb",
        "text": (
            "Documentos - Clasificación: cargar por trámite/solicitud, seleccionar prestación/modalidad y clasificar "
            "imágenes antes de guardar. Validar campos obligatorios y evitar guardar con solicitud vacía."
        ),
        "metadata": {"topic": "documentos", "intent": "clasificacion"},
    },
    {
        "doc_id": "kb-auditoria-operativa",
        "source": "system-kb",
        "text": (
            "Auditoría operativa: consultar por trámite o solicitud con límite de registros, revisar usuario, "
            "fecha, estado anterior y estado nuevo para trazabilidad."
        ),
        "metadata": {"topic": "auditoria", "intent": "consulta"},
    },
]

DEPRECATED_DEFAULT_KB_DOC_IDS: set[str] = {
    "kb-ruta-actualizaestado",
    "kb-ruta-pendientes",
}


class RagService:
    def __init__(self, store_path: Path | None = None) -> None:
        default_path = Path(os.getenv("AI_RAG_STORE_PATH", "/tmp/ai_rag_store.json"))
        self.store_path = store_path or default_path
        self.backend = os.getenv("AI_RAG_BACKEND", "json").strip().lower()
        self.db_alias = os.getenv("AI_RAG_DB_ALIAS", "temporal").strip() or "temporal"
        self.db_table = os.getenv("AI_RAG_DB_TABLE", "nova_rag_chunks").strip() or "nova_rag_chunks"
        if self.backend == "postgres":
            self._ensure_db_schema()
        self.bootstrap_default_kb()

    def _ensure_parent(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)

    def _ensure_db_schema(self) -> None:
        execute_by_alias(
            self.db_alias,
            f"""
            CREATE TABLE IF NOT EXISTS {self.db_table} (
              chunk_id text PRIMARY KEY,
              doc_id text NOT NULL,
              source text NOT NULL,
              text_content text NOT NULL,
              metadata jsonb NOT NULL DEFAULT '{{}}'::jsonb,
              created_at timestamptz NOT NULL DEFAULT now()
            )
            """,
        )
        execute_by_alias(
            self.db_alias,
            f"CREATE INDEX IF NOT EXISTS {self.db_table}_doc_id_idx ON {self.db_table}(doc_id)",
        )
        execute_by_alias(
            self.db_alias,
            f"CREATE INDEX IF NOT EXISTS {self.db_table}_created_idx ON {self.db_table}(created_at DESC)",
        )

    def _load_store(self) -> list[dict[str, Any]]:
        if self.backend == "postgres":
            rows = fetch_all_by_alias(
                self.db_alias,
                f"""
                SELECT chunk_id, doc_id, source, text_content, metadata, created_at
                FROM {self.db_table}
                ORDER BY created_at DESC
                LIMIT 5000
                """,
            )
            out: list[dict[str, Any]] = []
            for r in rows:
                out.append(
                    {
                        "chunk_id": r.get("chunk_id"),
                        "doc_id": r.get("doc_id"),
                        "source": r.get("source"),
                        "text": r.get("text_content"),
                        "metadata": r.get("metadata") or {},
                        "created_at": str(r.get("created_at") or ""),
                    }
                )
            return out

        if not self.store_path.exists():
            return []
        try:
            data = json.loads(self.store_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [d for d in data if isinstance(d, dict)]
            return []
        except Exception:
            logger.warning(f'rag_store_read_failed path="{self.store_path}"')
            return []

    def _save_store(self, chunks: list[dict[str, Any]]) -> None:
        if self.backend == "postgres":
            execute_by_alias(self.db_alias, f"TRUNCATE TABLE {self.db_table}")
            for chunk in chunks:
                execute_by_alias(
                    self.db_alias,
                    f"""
                    INSERT INTO {self.db_table}(chunk_id, doc_id, source, text_content, metadata, created_at)
                    VALUES (:chunk_id, :doc_id, :source, :text_content, CAST(:metadata_json AS jsonb), CAST(:created_at AS timestamptz))
                    """,
                    {
                        "chunk_id": str(chunk.get("chunk_id", "")),
                        "doc_id": str(chunk.get("doc_id", "")),
                        "source": str(chunk.get("source", "")),
                        "text_content": str(chunk.get("text", "")),
                        "metadata_json": json.dumps(chunk.get("metadata") or {}),
                        "created_at": str(chunk.get("created_at") or datetime.now(timezone.utc).isoformat()),
                    },
                )
            return

        self._ensure_parent()
        self.store_path.write_text(json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _chunk_text(text: str, chunk_size: int = 900, overlap: int = 120) -> list[str]:
        clean = " ".join(text.split())
        if not clean:
            return []
        out: list[str] = []
        start = 0
        while start < len(clean):
            end = min(len(clean), start + chunk_size)
            out.append(clean[start:end])
            if end >= len(clean):
                break
            start = max(0, end - overlap)
        return out

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {m.group(0).lower() for m in WORD_RE.finditer(text)}

    @staticmethod
    def _content_tokens(text: str) -> set[str]:
        toks = RagService._tokens(text)
        return {t for t in toks if len(t) >= 3 and t not in STOPWORDS_RAG}

    @staticmethod
    def _normalize_query(text: str) -> str:
        t = str(text or "").strip().lower()
        repl = {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ñ": "n"}
        for a, b in repl.items():
            t = t.replace(a, b)
        t = re.sub(r"[^a-z0-9\\s]", " ", t)
        return " ".join(t.split())

    @staticmethod
    def _rewrite_query(question: str) -> str:
        """
        Reescritura ligera para mejorar recall sin depender de otro modelo.
        cRAG-lite: expande términos de negocio frecuentes en afiliaciones.
        """
        qn = RagService._normalize_query(question)
        if not qn:
            return ""
        expansions: dict[str, list[str]] = {
            "camara": ["camara de comercio", "certificado de existencia", "representacion legal"],
            "cedula": ["cedula", "cc", "documento identidad", "identificacion"],
            "representante": ["representante legal", "apoderado", "firmante"],
            "nomina": ["nomina", "salario", "ibc", "ingreso base"],
            "salario": ["salario", "nomina", "ibc"],
            "afiliados": ["afiliados", "trabajadores", "empleados", "cotizantes"],
            "trabajadores": ["trabajadores", "afiliados", "empleados"],
            "sede": ["sede", "centro de trabajo", "codigoct"],
            "centro": ["centro de trabajo", "codigoct", "sede"],
            "prevalidacion": ["prevalidacion", "precheck", "validacion documental"],
            "926": ["926", "bkcargue", "flatfile", "archivo de carga"],
            "nit": ["nit", "documento empleador", "numero documento empleador"],
        }
        out_terms: set[str] = set(RagService._tokens(qn))
        for k, vals in expansions.items():
            if k in qn:
                for v in vals:
                    out_terms.update(RagService._tokens(v))
        # Mantener orden determinístico.
        return " ".join(sorted(out_terms))

    @staticmethod
    def _score(query_tokens: set[str], text: str) -> float:
        if not query_tokens:
            return 0.0
        text_tokens = RagService._tokens(text)
        if not text_tokens:
            return 0.0
        # Fuzzy-aware overlap: exact match gives full weight, approximate token match gives partial weight.
        matched_weight = 0.0
        text_list = list(text_tokens)
        for q in query_tokens:
            if q in text_tokens:
                matched_weight += 1.0
                continue
            best = 0.0
            for t in text_list:
                if len(q) < 4 or len(t) < 4:
                    continue
                sim = difflib.SequenceMatcher(None, q, t).ratio()
                if sim > best:
                    best = sim
            if best >= 0.86:
                matched_weight += 0.85
            elif best >= 0.78:
                matched_weight += 0.55
        if matched_weight <= 0:
            return 0.0
        return matched_weight / float(len(query_tokens))

    @staticmethod
    def _phrase_boost(question: str, text: str) -> float:
        qn = RagService._normalize_query(question)
        tn = RagService._normalize_query(text)
        if not qn or not tn:
            return 0.0
        if len(qn) >= 8 and qn in tn:
            return 0.25
        # Boost por pares de palabras consecutivas.
        words = qn.split()
        if len(words) < 2:
            return 0.0
        hits = 0
        pairs = 0
        for i in range(len(words) - 1):
            p = f"{words[i]} {words[i + 1]}"
            if len(p) < 6:
                continue
            pairs += 1
            if p in tn:
                hits += 1
        if pairs <= 0:
            return 0.0
        return min(0.20, 0.20 * (hits / float(pairs)))

    @staticmethod
    def _metadata_boost(question: str, metadata: dict[str, Any]) -> float:
        if not isinstance(metadata, dict):
            return 0.0
        qn = RagService._normalize_query(question)
        if not qn:
            return 0.0
        topic = RagService._normalize_query(str(metadata.get("topic") or ""))
        intent = RagService._normalize_query(str(metadata.get("intent") or ""))
        b = 0.0
        if topic and topic in qn:
            b += 0.08
        if intent:
            for tk in intent.split("_"):
                if tk and tk in qn:
                    b += 0.04
                    break
        return min(0.15, b)

    @staticmethod
    def _exact_overlap_ratio(query_tokens: set[str], text: str) -> float:
        if not query_tokens:
            return 0.0
        tt = RagService._content_tokens(text)
        if not tt:
            return 0.0
        inter = len(query_tokens & tt)
        return inter / float(len(query_tokens))

    @staticmethod
    def _extract_digits(text: str) -> list[str]:
        out: list[str] = []
        for m in re.finditer(r"\d{5,15}", str(text or "")):
            v = str(m.group(0) or "").strip()
            if not v:
                continue
            out.append(v)
        # preserve order, unique
        uniq: list[str] = []
        seen: set[str] = set()
        for d in out:
            if d in seen:
                continue
            seen.add(d)
            uniq.append(d)
        return uniq

    @staticmethod
    def _digits_boost(question: str, text: str) -> float:
        qd = RagService._extract_digits(question)
        if not qd:
            return 0.0
        td = " ".join(RagService._extract_digits(text))
        if not td:
            return 0.0
        hits = 0
        for d in qd:
            if d in td:
                hits += 1
        if hits <= 0:
            return 0.0
        return min(0.45, 0.22 * float(hits))

    @staticmethod
    def _entity_query(question: str) -> str:
        """
        Query compacta con entidades fuertes:
        - números (NIT/cédula/lote)
        - tokens largos informativos
        """
        qn = RagService._normalize_query(question)
        toks = [t for t in qn.split() if len(t) >= 5 and t not in STOPWORDS_RAG]
        digits = RagService._extract_digits(question)
        merged = digits + toks[:12]
        # unique keep order
        seen: set[str] = set()
        out: list[str] = []
        for t in merged:
            if t in seen:
                continue
            seen.add(t)
            out.append(t)
        return " ".join(out).strip()

    @staticmethod
    def _score_with_variant(
        *,
        question: str,
        variant_query: str,
        text: str,
        metadata: dict[str, Any],
        weight: float,
    ) -> tuple[float, float]:
        v_tokens = RagService._content_tokens(variant_query) or RagService._tokens(variant_query)
        if not v_tokens:
            return 0.0, 0.0
        s = RagService._score(v_tokens, text)
        s += RagService._phrase_boost(variant_query, text)
        s += RagService._metadata_boost(variant_query, metadata)
        s += RagService._digits_boost(question, text)
        er = RagService._exact_overlap_ratio(v_tokens, text)
        return max(0.0, s * weight), er

    def bootstrap_default_kb(self) -> None:
        store = self._load_store()
        cleaned, removed = self._purge_deprecated_default_kb(store)
        if removed > 0:
            self._save_store(cleaned)
            store = cleaned
            logger.info(f"rag_default_kb_purged removed={removed}")
        existing_doc_ids = {str(c.get("doc_id", "")).strip() for c in store}
        needed = [d for d in DEFAULT_KB_DOCS if str(d.get("doc_id", "")).strip() not in existing_doc_ids]
        if not needed:
            return
        self.index(needed, replace_doc=False)
        logger.info(f"rag_default_kb_bootstrapped docs={len(needed)}")

    @staticmethod
    def _purge_deprecated_default_kb(store: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
        if not store:
            return store, 0
        out: list[dict[str, Any]] = []
        removed = 0
        for chunk in store:
            doc_id = str(chunk.get("doc_id", "")).strip()
            metadata = chunk.get("metadata") if isinstance(chunk.get("metadata"), dict) else {}
            topic = str(metadata.get("topic", "")).strip().lower()
            is_deprecated = doc_id in DEPRECATED_DEFAULT_KB_DOC_IDS or (doc_id.startswith("kb-ruta-") and topic == "ruta_inclusion")
            if is_deprecated:
                removed += 1
                continue
            out.append(chunk)
        return out, removed

    def index(
        self,
        documents: list[dict[str, Any]],
        *,
        replace_doc: bool = True,
        chunk_size: int = 900,
        overlap: int = 120,
    ) -> dict[str, Any]:
        if self.backend == "postgres":
            doc_ids = {str(d.get("doc_id", "")).strip() for d in documents}
            doc_ids.discard("")
            if replace_doc and doc_ids:
                for doc_id in doc_ids:
                    execute_by_alias(
                        self.db_alias,
                        f"DELETE FROM {self.db_table} WHERE doc_id = :doc_id",
                        {"doc_id": doc_id},
                    )

            now = datetime.now(timezone.utc).isoformat()
            added = 0
            for doc in documents:
                doc_id = str(doc.get("doc_id", "")).strip() or f"doc-{uuid4().hex[:10]}"
                source = str(doc.get("source", "")).strip() or "manual"
                text = str(doc.get("text", "")).strip()
                metadata = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
                if not text:
                    continue
                for chunk_text in self._chunk_text(text, chunk_size=chunk_size, overlap=overlap):
                    execute_by_alias(
                        self.db_alias,
                        f"""
                        INSERT INTO {self.db_table}(chunk_id, doc_id, source, text_content, metadata, created_at)
                        VALUES (:chunk_id, :doc_id, :source, :text_content, CAST(:metadata_json AS jsonb), CAST(:created_at AS timestamptz))
                        """,
                        {
                            "chunk_id": f"ch_{uuid4().hex}",
                            "doc_id": doc_id,
                            "source": source,
                            "text_content": chunk_text,
                            "metadata_json": json.dumps(metadata),
                            "created_at": now,
                        },
                    )
                    added += 1

            count_row = fetch_all_by_alias(self.db_alias, f"SELECT COUNT(*)::int AS n FROM {self.db_table}")
            store_size = int((count_row[0].get("n") if count_row else 0) or 0)
            return {"ok": True, "backend": "postgres", "docs": len(documents), "chunks_added": added, "store_size": store_size}

        store = self._load_store()
        doc_ids = {str(d.get("doc_id", "")).strip() for d in documents}
        doc_ids.discard("")
        if replace_doc and doc_ids:
            store = [c for c in store if str(c.get("doc_id", "")) not in doc_ids]

        now = datetime.now(timezone.utc).isoformat()
        added = 0
        for doc in documents:
            doc_id = str(doc.get("doc_id", "")).strip() or f"doc-{uuid4().hex[:10]}"
            source = str(doc.get("source", "")).strip() or "manual"
            text = str(doc.get("text", "")).strip()
            metadata = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
            if not text:
                continue
            for chunk_text in self._chunk_text(text, chunk_size=chunk_size, overlap=overlap):
                store.append(
                    {
                        "chunk_id": f"ch_{uuid4().hex}",
                        "doc_id": doc_id,
                        "source": source,
                        "text": chunk_text,
                        "metadata": metadata,
                        "created_at": now,
                    }
                )
                added += 1
        self._save_store(store)
        return {"ok": True, "backend": "json", "docs": len(documents), "chunks_added": added, "store_size": len(store)}

    def query(self, question: str, top_k: int = 5) -> dict[str, Any]:
        q = question.strip()
        if not q:
            return {"ok": True, "question": q, "count": 0, "items": []}
        q_rewritten = self._rewrite_query(q)
        q_entity = self._entity_query(q)
        if self.backend == "postgres":
            rows = fetch_all_by_alias(
                self.db_alias,
                f"""
                SELECT chunk_id, doc_id, source, text_content, metadata, created_at
                FROM {self.db_table}
                ORDER BY created_at DESC
                LIMIT 5000
                """,
            )
            store = [
                {
                    "chunk_id": r.get("chunk_id"),
                    "doc_id": r.get("doc_id"),
                    "source": r.get("source"),
                    "text": r.get("text_content"),
                    "metadata": r.get("metadata") or {},
                    "created_at": str(r.get("created_at") or ""),
                }
                for r in rows
            ]
        else:
            store = self._load_store()
        scored: list[tuple[float, dict[str, Any]]] = []
        exact_ratios: dict[str, float] = {}
        best_variant_by_chunk: dict[str, str] = {}
        variants: list[tuple[str, str, float]] = [
            ("original", q, 1.00),
            ("rewritten", q_rewritten if q_rewritten else q, 0.96),
        ]
        if q_entity:
            variants.append(("entities", q_entity, 1.08))
        for chunk in store:
            text_chunk = str(chunk.get("text", ""))
            md = chunk.get("metadata") if isinstance(chunk.get("metadata"), dict) else {}
            best_s = 0.0
            best_er = 0.0
            best_name = "original"
            for vname, vquery, vweight in variants:
                s_v, er_v = self._score_with_variant(
                    question=q,
                    variant_query=vquery,
                    text=text_chunk,
                    metadata=md,
                    weight=vweight,
                )
                if s_v > best_s:
                    best_s = s_v
                    best_er = er_v
                    best_name = vname
            s = best_s
            if s > 0:
                scored.append((s, chunk))
                key = str(chunk.get("chunk_id") or "")
                exact_ratios[key] = best_er
                best_variant_by_chunk[key] = best_name
        scored.sort(key=lambda x: x[0], reverse=True)
        # cRAG-lite correctivo: si no hay señal suficiente, reintento con union de términos.
        if len(scored) == 0:
            q_union = " ".join([x for x in [q, q_rewritten, q_entity] if str(x).strip()]).strip()
            if q_union:
                for chunk in store:
                    text_chunk = str(chunk.get("text", ""))
                    md = chunk.get("metadata") if isinstance(chunk.get("metadata"), dict) else {}
                    s_u, er_u = self._score_with_variant(
                        question=q,
                        variant_query=q_union,
                        text=text_chunk,
                        metadata=md,
                        weight=0.92,
                    )
                    if s_u > 0:
                        scored.append((s_u, chunk))
                        key = str(chunk.get("chunk_id") or "")
                        exact_ratios[key] = er_u
                        best_variant_by_chunk[key] = "corrective_union"
                scored.sort(key=lambda x: x[0], reverse=True)
        items = []
        max_score = 0.0
        top_exact_ratio = 0.0
        for score, chunk in scored[: max(1, min(top_k, 20))]:
            if score > max_score:
                max_score = score
            er = exact_ratios.get(str(chunk.get("chunk_id") or ""), 0.0)
            if er > top_exact_ratio:
                top_exact_ratio = er
            items.append(
                {
                    "score": round(score, 4),
                    "chunk_id": chunk.get("chunk_id"),
                    "doc_id": chunk.get("doc_id"),
                    "source": chunk.get("source"),
                    "text": chunk.get("text"),
                    "metadata": chunk.get("metadata") or {},
                    "match_variant": best_variant_by_chunk.get(str(chunk.get("chunk_id") or ""), "original"),
                }
            )
        # cRAG-lite gate: señaliza baja evidencia para evitar respuestas "inventadas".
        low_confidence = (len(items) == 0) or (max_score < 0.35) or (top_exact_ratio < 0.34)
        return {
            "ok": True,
            "question": q,
            "query_rewritten": q_rewritten,
            "query_entities": q_entity,
            "count": len(items),
            "max_score": round(max_score, 4),
            "top_exact_ratio": round(top_exact_ratio, 4),
            "low_confidence": low_confidence,
            "items": items,
        }
