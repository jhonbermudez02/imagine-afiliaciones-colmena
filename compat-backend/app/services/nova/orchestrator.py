from __future__ import annotations

import base64
import csv
import io
import json
import mimetypes
import os
import re
import difflib
import hashlib
import tempfile
from collections import Counter
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.core.documentos import TIPOS_DOCUMENTO_TRABAJADOR
from app.core.db import execute_by_alias, fetch_all_by_alias
from app.core.observability import get_logger
from app.services.nova.database.db_tools_service import DbToolsService
from app.services.nova.evaluation.eval_service import EvalService
from app.services.nova.ingestion.code_ingest_service import CodeIngestService
from app.services.nova.ingestion.ocr_persistence_service import OcrPersistenceService
from app.services.nova.ingestion.ocr_service import OcrService
from app.services.nova.llm.llm_service import LlmService, PROMPT_TEMPLATES
from app.services.nova.rag.rag_service import RagService
from app.services.nova.security.security_service import SecurityService

logger = get_logger("app.ai.nova")

try:
    from openpyxl import load_workbook
    from openpyxl import Workbook
except Exception:  # pragma: no cover
    load_workbook = None
    Workbook = None


class NovaOrchestrator:
    def __init__(self) -> None:
        self.security = SecurityService()
        self.llm = LlmService()
        self.rag = RagService()
        self.ingestion = CodeIngestService()
        self.ocr = OcrService()
        self.ocr_persistence = OcrPersistenceService()
        self.db_tools = DbToolsService()
        self.eval = EvalService()
        self._doc_code_table_ready = False
        self._legacy_adjunto_map_cache: list[dict[str, Any]] | None = None
        self._entity_memory: dict[str, dict[str, str]] = {}

    @staticmethod
    def _memory_key(base: str, lote: str, idtramite: str) -> str:
        return f"{str(base or '').strip()}|{str(lote or '').strip()}|{str(idtramite or '').strip()}"

    def _save_entity_memory(self, *, base: str, lote: str, idtramite: str, row: dict[str, Any] | None) -> None:
        if not isinstance(row, dict):
            return
        empresa = str(row.get("empleador") or row.get("razonsocialempleador") or "").strip()
        nit = str(row.get("nit_empleador") or row.get("numerodocumentoempleador") or "").strip()
        doc = str(row.get("documento_trabajador") or row.get("numerodocumento") or "").strip()
        nombre = " ".join(
            [
                str(row.get("primerapellido") or "").strip(),
                str(row.get("segundoapellido") or "").strip(),
                str(row.get("primernombre") or "").strip(),
                str(row.get("segundonombre") or "").strip(),
            ]
        ).strip()
        if not any([empresa, nit, doc, nombre]):
            return
        key = self._memory_key(base, lote, idtramite)
        self._entity_memory[key] = {
            "empresa": empresa,
            "nit": nit,
            "documento": doc,
            "nombre": nombre,
        }

    def _load_entity_memory(self, *, base: str, lote: str, idtramite: str) -> dict[str, str]:
        key = self._memory_key(base, lote, idtramite)
        return dict(self._entity_memory.get(key) or {})

    @staticmethod
    def _precheck_cache_path(*, base: str, lote: str, idtramite: str) -> Path:
        key = f"{str(base or '').strip()}|{str(lote or '').strip()}|{str(idtramite or '').strip()}"
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
        return Path("/tmp") / f"nova_precheck_cache_{digest}.json"

    def _save_precheck_cache(self, *, base: str, lote: str, idtramite: str, payload: dict[str, Any]) -> None:
        try:
            p = self._precheck_cache_path(base=base, lote=lote, idtramite=idtramite)
            data = dict(payload or {})
            data["_saved_at"] = datetime.now().isoformat()
            p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except Exception:
            return

    def _load_precheck_cache(self, *, base: str, lote: str, idtramite: str) -> dict[str, Any] | None:
        try:
            candidates = [
                self._precheck_cache_path(base=base, lote=lote, idtramite=idtramite),
                self._precheck_cache_path(base=base, lote=lote, idtramite=""),
            ]
            for p in candidates:
                if not p.exists():
                    continue
                raw = p.read_text(encoding="utf-8")
                data = json.loads(raw)
                if isinstance(data, dict):
                    return data
        except Exception:
            return None
        return None

    @staticmethod
    def _safe_token(value: str, fallback: str = "") -> str:
        token = re.sub(r"[^0-9A-Za-z_-]+", "", str(value or "")).strip()
        if token:
            return token
        return re.sub(r"[^0-9A-Za-z_-]+", "", str(fallback or "")).strip()

    @staticmethod
    def _doc_id_with_hash(prefix: str, kind: str, key: str) -> str:
        digest = hashlib.sha1(f"{kind}|{key}".encode("utf-8")).hexdigest()[:16]
        return f"{prefix}:{kind}:{digest}"

    @staticmethod
    def _sanitize_rag_text(value: str) -> str:
        txt = str(value or "")
        if not txt:
            return ""
        return txt.replace("\x00", " ").strip()

    def _build_precheck_rag_documents(
        self,
        *,
        source: str,
        doc_id_prefix: str,
        excel_filename: str,
        xlsx_text: str,
        manifest_content: str,
        docs_ocr: list[dict[str, Any]],
        clean_payload: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        docs: list[dict[str, Any]] = []
        clean_payload = clean_payload or {}

        xlsx_body = self._sanitize_rag_text(xlsx_text)
        if xlsx_body:
            docs.append(
                {
                    "doc_id": self._doc_id_with_hash(doc_id_prefix, "xlsx", excel_filename),
                    "source": source,
                    "text": xlsx_body,
                    "metadata": {"kind": "xlsx_snapshot", "filename": str(excel_filename or "")},
                }
            )

        manifest_body = self._sanitize_rag_text(manifest_content)
        if manifest_body:
            docs.append(
                {
                    "doc_id": self._doc_id_with_hash(doc_id_prefix, "manifest", manifest_body[:1200]),
                    "source": source,
                    "text": manifest_body,
                    "metadata": {"kind": "manifest_paso1"},
                }
            )

        for d in docs_ocr:
            filename = str(d.get("filename") or "").strip()
            text = self._sanitize_rag_text(str(d.get("text") or ""))
            if not filename or not text:
                continue
            docs.append(
                {
                    "doc_id": self._doc_id_with_hash(doc_id_prefix, "ocr", filename),
                    "source": source,
                    "text": text,
                    "metadata": {
                        "kind": "ocr_doc",
                        "filename": filename,
                        "doc_type": str(d.get("doc_type") or ""),
                        "tipo": int(d.get("tipo") or 99),
                        "chars": int(d.get("chars") or 0),
                    },
                }
            )

        contrato_clean = clean_payload.get("contrato_clean") if isinstance(clean_payload.get("contrato_clean"), dict) else None
        if contrato_clean and self._sanitize_rag_text(str(contrato_clean.get("content") or "")):
            docs.append(
                {
                    "doc_id": self._doc_id_with_hash(
                        doc_id_prefix,
                        "clean_contrato",
                        str(contrato_clean.get("filename") or "contrato_clean"),
                    ),
                    "source": source,
                    "text": self._sanitize_rag_text(str(contrato_clean.get("content") or "")),
                    "metadata": {
                        "kind": "clean_contrato",
                        "filename": str(contrato_clean.get("filename") or ""),
                    },
                }
            )

        multi_clean = clean_payload.get("trabajadores_clean_multi")
        if isinstance(multi_clean, list):
            for item in multi_clean:
                if not isinstance(item, dict):
                    continue
                fn = str(item.get("filename") or "").strip()
                content = self._sanitize_rag_text(str(item.get("content") or ""))
                if not fn or not content:
                    continue
                docs.append(
                    {
                        "doc_id": self._doc_id_with_hash(doc_id_prefix, "clean_sede", fn),
                        "source": source,
                        "text": content,
                        "metadata": {"kind": "clean_sede", "filename": fn},
                    }
                )

        indep_clean = clean_payload.get("independientes_clean") if isinstance(clean_payload.get("independientes_clean"), dict) else None
        if indep_clean and self._sanitize_rag_text(str(indep_clean.get("content") or "")):
            docs.append(
                {
                    "doc_id": self._doc_id_with_hash(
                        doc_id_prefix,
                        "clean_independientes",
                        str(indep_clean.get("filename") or "independientes_clean"),
                    ),
                    "source": source,
                    "text": self._sanitize_rag_text(str(indep_clean.get("content") or "")),
                    "metadata": {
                        "kind": "clean_independientes",
                        "filename": str(indep_clean.get("filename") or ""),
                    },
                }
            )

        return docs

    def _refresh_rag_source(self, *, source: str, documents: list[dict[str, Any]]) -> dict[str, Any]:
        if not source:
            return {"ok": False, "message": "source vacío para refresh RAG"}
        if not documents:
            return {"ok": False, "message": "sin documentos para indexar en RAG", "source": source}
        if self.rag.backend == "postgres":
            execute_by_alias(
                self.rag.db_alias,
                f"DELETE FROM {self.rag.db_table} WHERE source = :source",
                {"source": source},
            )
        out = self.rag.index(documents, replace_doc=False)
        if isinstance(out, dict):
            out["source"] = source
            out["documents"] = len(documents)
            return out
        return {"ok": False, "source": source, "documents": len(documents)}

    def health(self) -> dict[str, Any]:
        return {
            "ok": True,
            "service": "ai",
            "architecture": "NOVA",
            "provider_mode": self.llm.provider,
            "templates": sorted(PROMPT_TEMPLATES.keys()),
            "modules": ["llm", "rag", "ingestion", "database", "security", "evaluation"],
        }

    def prompts(self) -> dict[str, Any]:
        return {"ok": True, "count": len(PROMPT_TEMPLATES), "items": PROMPT_TEMPLATES}

    def rag_index(
        self,
        documents: list[dict[str, Any]],
        *,
        replace_doc: bool = True,
        chunk_size: int = 900,
        overlap: int = 120,
    ) -> dict[str, Any]:
        return self.rag.index(documents, replace_doc=replace_doc, chunk_size=chunk_size, overlap=overlap)

    def rag_query(self, question: str, top_k: int = 5) -> dict[str, Any]:
        return self.rag.query(question, top_k=top_k)

    def chat(
        self,
        question: str,
        template: str = "operacion",
        use_rag: bool = True,
        top_k: int = 4,
        base: str | None = None,
        lote: str = "",
        idtramite: str = "",
        source_prefix: str = "",
    ) -> dict[str, Any]:
        q = question.strip()
        if not q:
            return {"ok": False, "message": "La pregunta no puede estar vacia."}
        decision_trace: list[dict[str, Any]] = []

        def trace(step: str, *, tool: str = "", detail: str = "") -> None:
            decision_trace.append(
                {
                    "step": str(step or "").strip(),
                    "tool": str(tool or "").strip(),
                    "detail": str(detail or "").strip(),
                }
            )

        def finalize(raw_answer: str) -> str:
            out = self._finalize_chat_answer(answer=raw_answer, template=template, question=q)
            if template == "afiliaciones_arl" and decision_trace:
                lines: list[str] = []
                for tr in decision_trace[:8]:
                    st = str(tr.get("step") or "").strip()
                    tl = str(tr.get("tool") or "").strip()
                    dt = str(tr.get("detail") or "").strip()
                    bit = f"- {st}"
                    if tl:
                        bit += f" [{tl}]"
                    if dt:
                        bit += f": {dt}"
                    lines.append(bit)
                trace_block = "Traza NOVA:\n" + "\n".join(lines)
                if "Traza NOVA:" not in out:
                    out = f"{out}\n\n{trace_block}".strip()
            return out
        db_base = (base or os.getenv("AI_DB_ALIAS", "temporal")).strip() or "temporal"
        qn = self._normalize(q)
        q_tokens = qn.split()
        qn_raw = NovaOrchestrator._norm_text(q)

        # Guardia temprana de dominio para evitar cruces entre proyectos.
        if template == "afiliaciones_arl":
            is_cross_raw = any(k in qn_raw for k in ("funerario", "funerarios", "notificacion", "notificaciones"))
            has_aff_raw = any(k in qn_raw for k in ("afiliacion", "afiliaciones", "lote", "926", "empleador", "trabajador", "sede", "contrato"))
            if is_cross_raw and not has_aff_raw:
                return {
                    "ok": True,
                    "template": template,
                    "system_prompt": PROMPT_TEMPLATES.get(template, PROMPT_TEMPLATES["operacion"]),
                    "question": q,
                    "answer": finalize(
                        "Esta instancia NOVA está dedicada a Afiliaciones ARL y no consulta módulos de Funerarios/Notificaciones.\n"
                        "Para esa consulta usa el NOVA del proyecto Funerarios."
                    ),
                    "citations": self._maybe_citations(
                        [{"doc_id": "guard:domain-afiliaciones", "source": "router.guard", "score": 1.0}]
                    ),
                    "rag_hits": 0,
                    "db_hits": 0,
                    "db_base": db_base,
                    "db_rows_preview": [],
                    "provider": "local-deterministic",
                }

        def has_like_q(target: str, threshold: float = 0.72) -> bool:
            for tk in q_tokens:
                if tk == target:
                    return True
                if len(tk) >= 4 and len(target) >= 4:
                    if difflib.SequenceMatcher(None, tk, target).ratio() >= threshold:
                        return True
            return False

        # Memoria de entidad (empresa/persona) para preguntas de seguimiento.
        followup_markers = {"y", "tambien", "también", "ese", "esa", "mismo", "misma", "cual", "cuál", "dime", "muéstrame", "muestrame"}
        is_followup_like = (len(q_tokens) <= 4) and any(t in followup_markers for t in q_tokens)
        has_direct_identifier = any(t.isdigit() and len(t) >= 5 for t in q_tokens)
        if (template == "afiliaciones_arl") and is_followup_like and not has_direct_identifier:
            mem = self._load_entity_memory(base=db_base, lote=lote, idtramite=idtramite)
            mem_probe = " ".join([mem.get("empresa", ""), mem.get("nit", ""), mem.get("documento", ""), mem.get("nombre", "")]).strip()
            if mem_probe:
                q = f"{q} {mem_probe}".strip()
                qn = self._normalize(q)
                q_tokens = qn.split()
                trace("memory_expand", tool="memory.entity", detail=f"expanded_with={mem_probe[:80]}")

        procedural_hint = (
            has_like_q("como")
            or has_like_q("que")
            or has_like_q("valida")
            or has_like_q("validar")
            or has_like_q("ejecutar")
            or has_like_q("pasos")
            or has_like_q("proceso")
            or has_like_q("cierre")
            or has_like_q("reversion")
            or has_like_q("reversion")
        )

        is_cross_domain_ops_intent = (
            has_like_q("funerario")
            or has_like_q("funerarios")
            or has_like_q("notificacion")
            or has_like_q("notificaciones")
            or has_like_q("reclamante")
            or has_like_q("prestacion")
            or has_like_q("prestaciones")
            or has_like_q("bloqueo")
        )
        is_doc_keyword_intent = (
            has_like_q("camara", 0.62)
            or has_like_q("cámara", 0.62)
            or has_like_q("comercio", 0.62)
            or has_like_q("cedula", 0.55)
            or has_like_q("cédula", 0.55)
            or has_like_q("identificacion", 0.55)
            or has_like_q("identificación", 0.55)
            or has_like_q("rut", 0.62)
            or has_like_q("formulario", 0.62)
            or has_like_q("adjunto", 0.62)
            or has_like_q("soporte", 0.62)
            or has_like_q("documento", 0.62)
        )
        has_afiliaciones_keyword = (
            has_like_q("afiliacion")
            or has_like_q("afiliaciones")
            or has_like_q("lote")
            or has_like_q("926")
            or has_like_q("empleador")
            or has_like_q("trabajador")
            or has_like_q("sede")
            or has_like_q("ocr")
            or has_like_q("contrato")
            or has_like_q("cedula")
            or has_like_q("cédula")
            or has_like_q("representante")
            or has_like_q("camara")
            or has_like_q("cámara")
            or has_like_q("rut")
            or has_like_q("imagen")
            or has_like_q("pdf")
            or is_doc_keyword_intent
        )
        is_afiliaciones_intent = (
            template == "afiliaciones_arl"
            or has_afiliaciones_keyword
        ) and (not is_cross_domain_ops_intent or template == "afiliaciones_arl")
        is_compare_ocr_intent = is_afiliaciones_intent and (
            has_like_q("compara")
            or has_like_q("comparar")
            or has_like_q("contrastar")
            or has_like_q("contra")
        ) and (has_like_q("ocr") or has_like_q("documento") or has_like_q("pdf"))
        afiliaciones_only_mode = template == "afiliaciones_arl"
        is_live_ocr_intent = is_afiliaciones_intent and (
            has_like_q("ocr")
            and (
                has_like_q("vivo")
                or has_like_q("nuevo")
                or has_like_q("nueva")
                or has_like_q("releer")
                or has_like_q("reprocesa")
                or has_like_q("reprocesar")
                or has_like_q("ejecuta")
                or has_like_q("ejecutar")
            )
        )
        is_pdf_doc_lookup_intent = is_afiliaciones_intent and (
            (
                has_like_q("pdf", 0.7)
                or has_like_q("adjunto", 0.62)
                or has_like_q("archivo", 0.62)
                or has_like_q("imagen", 0.55)
                or has_like_q("foto", 0.62)
            )
            and (
                has_like_q("cedula", 0.55)
                or has_like_q("cédula", 0.55)
                or has_like_q("cc", 0.62)
                or has_like_q("identificacion", 0.55)
                or has_like_q("identificación", 0.55)
                or has_like_q("documento", 0.58)
            )
            or (
                (has_like_q("representante", 0.58) or has_like_q("legal", 0.58))
                and (
                    has_like_q("cedula", 0.55)
                    or has_like_q("cédula", 0.55)
                    or has_like_q("identificacion", 0.55)
                    or has_like_q("identificación", 0.55)
                    or has_like_q("documento", 0.58)
                )
            )
        )
        is_doc_type_lookup_intent = is_afiliaciones_intent and (
            has_like_q("camara", 0.62)
            or has_like_q("cámara", 0.62)
            or has_like_q("comercio", 0.62)
            or has_like_q("rut", 0.62)
            or has_like_q("formulario", 0.62)
            or has_like_q("cedula", 0.55)
            or has_like_q("cédula", 0.55)
            or has_like_q("anexo", 0.62)
            or has_like_q("listado", 0.62)
            or (
                (has_like_q("faltante", 0.58) or has_like_q("faltantes", 0.58) or has_like_q("requisito", 0.58))
                and (has_like_q("documento", 0.58) or has_like_q("adjunto", 0.58) or has_like_q("soporte", 0.58))
            )
        )
        has_revalidator_word = any(
            k in qn_raw
            for k in ("revalidador", "prevalid", "revalid", "validacion", "validación", "validar")
        )
        is_revalidator_intent = is_afiliaciones_intent and (
            has_revalidator_word
            and (
                has_like_q("documento", 0.58)
                or has_like_q("regla", 0.58)
                or has_like_q("afiliacion", 0.58)
                or has_like_q("afiliaciones", 0.58)
            )
            or (
                (has_like_q("cedula", 0.55) or has_like_q("cédula", 0.55))
                and (has_like_q("duplicada", 0.58) or has_like_q("duplicado", 0.58) or has_like_q("repetida", 0.58))
            )
            or (
                (has_like_q("camara", 0.62) or has_like_q("cámara", 0.62))
                and (has_like_q("vigencia", 0.58) or has_like_q("meses", 0.58) or has_like_q("expedicion", 0.58) or has_like_q("expedición", 0.58))
            )
        )
        is_xlsx_pdf_compare_intent = is_afiliaciones_intent and (
            (has_like_q("compara") or has_like_q("comparar") or has_like_q("contrastar") or has_like_q("contra"))
            and (has_like_q("xlsx") or has_like_q("hoja") or has_like_q("hojas") or has_like_q("excel"))
            and (has_like_q("pdf") or has_like_q("ocr"))
        )
        is_dimensional_intent = is_afiliaciones_intent and (
            (has_like_q("datos", 0.58) and (has_like_q("empleador", 0.58) or has_like_q("sede", 0.58) or has_like_q("asesor", 0.58)))
            or has_like_q("datos", 0.50)
            or has_like_q("resumen", 0.58)
            or has_like_q("ejecutivo", 0.58)
            or has_like_q("nomina", 0.58)
            or has_like_q("nómina", 0.58)
            or has_like_q("salario", 0.58)
            or has_like_q("salarios", 0.58)
            or has_like_q("cuantos", 0.58)
            or has_like_q("cuantas", 0.58)
            or (has_like_q("ciudad", 0.58))
            or (has_like_q("actividad", 0.58))
            or (has_like_q("riesgo", 0.58))
            or (has_like_q("representante", 0.58))
            or (has_like_q("faltante", 0.58) or has_like_q("faltantes", 0.58))
            or has_like_q("asesor", 0.58)
            or has_like_q("telefono", 0.58)
            or has_like_q("afiliado", 0.58)
            or has_like_q("afiliados", 0.58)
            or has_like_q("empleado", 0.58)
            or has_like_q("empleados", 0.58)
            or has_like_q("barranquilla", 0.9)
            or has_like_q("bogota", 0.9)
            or has_like_q("medellin", 0.9)
            or has_like_q("cali", 0.9)
        )
        is_excel_cps_intent = is_afiliaciones_intent and (
            has_like_q("excel")
            or has_like_q("xlsx")
            or has_like_q("cps")
            or has_like_q("f-216", 0.66)
            or has_like_q("hoja")
            or has_like_q("hojas")
            or has_like_q("false")
            or has_like_q("orp")
            or has_like_q("subtipo")
        )
        is_rules_lookup_intent = (
            has_like_q("codigo")
            or has_like_q("código")
            or has_like_q("cotizante")
            or has_like_q("subtipo")
            or has_like_q("tipo")
        ) and (
            has_like_q("trabajador")
            or has_like_q("estudiante")
            or has_like_q("dependiente")
            or has_like_q("independiente")
            or has_like_q("postgrado")
        )
        is_metrics_query = is_afiliaciones_intent and (
            has_like_q("nomina", 0.58)
            or has_like_q("nómina", 0.58)
            or has_like_q("salario", 0.58)
            or has_like_q("salarios", 0.58)
            or has_like_q("trabajadores", 0.58)
            or has_like_q("empleados", 0.58)
            or has_like_q("sedes", 0.58)
            or has_like_q("cuantos", 0.58)
            or has_like_q("cuantas", 0.58)
        )
        is_entity_lookup_intent = is_afiliaciones_intent and (
            (
                len(q_tokens) <= 5
                and any((t.isdigit() and len(t) >= 6) or (len(t) >= 4 and not t.isdigit()) for t in q_tokens)
            )
            or has_like_q("nit", 0.62)
            or has_like_q("cedula", 0.55)
            or has_like_q("cédula", 0.55)
            or has_like_q("empresa", 0.58)
            or has_like_q("empleador", 0.58)
            or has_like_q("afiliado", 0.58)
        )
        if is_metrics_query:
            is_pdf_doc_lookup_intent = False
            is_doc_type_lookup_intent = False
            is_dimensional_intent = True
        intent_route = "general"
        if is_revalidator_intent:
            intent_route = "prevalidacion"
        elif is_xlsx_pdf_compare_intent:
            intent_route = "xlsx_pdf_compare"
        elif is_pdf_doc_lookup_intent or is_doc_type_lookup_intent:
            intent_route = "documental_lookup"
        elif is_live_ocr_intent:
            intent_route = "ocr_live"
        elif is_entity_lookup_intent:
            intent_route = "entity_lookup"
        elif is_dimensional_intent:
            intent_route = "resumen_operativo"
        elif is_excel_cps_intent:
            intent_route = "excel_cps"
        elif is_afiliaciones_intent:
            intent_route = "afiliaciones_general"
        elif is_cross_domain_ops_intent:
            intent_route = "cross_domain_operacion"
        elif procedural_hint:
            intent_route = "procedural"
        logger.info(f'nova_intent_route route="{intent_route}" template="{template}"')
        trace("route_selected", tool="router", detail=f"route={intent_route} template={template}")

        # Guardia de dominio: en el NOVA de Afiliaciones no mezclar flujos de Funerarios/Notificaciones
        # cuando la pregunta no tiene señal de afiliaciones.
        if template == "afiliaciones_arl" and is_cross_domain_ops_intent and not has_afiliaciones_keyword:
            trace("domain_guard", tool="router.guard", detail="consulta fuera de dominio afiliaciones")
            return {
                "ok": True,
                "template": template,
                "system_prompt": PROMPT_TEMPLATES.get(template, PROMPT_TEMPLATES["operacion"]),
                "question": q,
                "answer": finalize(
                    "Esta instancia NOVA está en modo Afiliaciones ARL y no consulta módulos de Funerarios/Notificaciones.\n"
                    "Para esa consulta usa el NOVA del proyecto Funerarios o cambia el template a 'operacion'."
                ),
                "citations": self._maybe_citations(
                    [{"doc_id": "guard:domain-afiliaciones", "source": "router.guard", "score": 1.0}]
                ),
                "rag_hits": 0,
                "db_hits": 0,
                "db_base": db_base,
                "db_rows_preview": [],
                "provider": "local-deterministic",
            }
        if use_rag and is_rules_lookup_intent and self._is_rules_source_prefix(source_prefix):
            trace("rules_lookup", tool="rag.query", detail=f"source_prefix={source_prefix} top_k={max(40, min(top_k * 8, 120))}")
            rag_rules = self.rag.query(q, top_k=max(40, min(top_k * 8, 120)))
            rule_items = self._filter_rag_items_by_source_prefix(
                rag_rules.get("items", []) if isinstance(rag_rules, dict) else [],
                source_prefix,
            )
            rule_answer = self._build_rules_lookup_answer(question=q, items=rule_items)
            if rule_answer:
                return {
                    "ok": True,
                    "template": template,
                    "system_prompt": PROMPT_TEMPLATES.get(template, PROMPT_TEMPLATES["operacion"]),
                    "question": q,
                    "answer": finalize(rule_answer),
                    "citations": self._maybe_citations(
                        [{"doc_id": "rag:rules-lookup", "source": source_prefix or "rules", "score": 1.0}]
                    ),
                    "rag_hits": len(rule_items),
                    "db_hits": 0,
                    "db_base": db_base,
                    "db_rows_preview": [],
                    "provider": "local-deterministic",
                }

        if is_afiliaciones_intent:
            try:
                trace("afiliaciones_context", tool="db.search_afiliaciones_context", detail=f"base={db_base} lote={lote} idtramite={idtramite}")
                af_ctx = self.db_tools.search_afiliaciones_context(
                    base=db_base,
                    question=q,
                    lote=lote,
                    idtramite=idtramite,
                    limit=12,
                )
                af_rows = af_ctx.get("rows", []) if isinstance(af_ctx, dict) else []
                # cRAG correctivo (2da pasada): si no hay evidencia en el scope actual y la intención
                # es de entidad, reintentar búsqueda global para no perder matches válidos fuera del lote.
                if (not af_rows) and (intent_route == "entity_lookup" or is_entity_lookup_intent):
                    trace("entity_lookup_retry_global", tool="db.search_afiliaciones_context", detail="retry_with_global_scope")
                    af_ctx_global = self.db_tools.search_afiliaciones_context(
                        base=db_base,
                        question=q,
                        lote="",
                        idtramite="",
                        limit=20,
                    )
                    af_rows = af_ctx_global.get("rows", []) if isinstance(af_ctx_global, dict) else []
                q_entity_terms = []
                for tk in q_tokens:
                    if tk.isdigit() and len(tk) >= 6:
                        q_entity_terms.append(tk)
                    elif len(tk) >= 4 and tk not in {"lote", "tramite", "trámite", "afiliacion", "afiliaciones", "empresa", "empleador", "trabajador", "trabajadores"}:
                        q_entity_terms.append(tk)
                if q_entity_terms and (not af_rows):
                    rag_items_fb: list[dict[str, Any]] = []
                    if use_rag:
                        trace("entity_lookup_rag_fallback", tool="rag.query", detail=f"top_k={max(20, min(top_k * 4, 80))}")
                        rag_fb = self.rag.query(q, top_k=max(20, min(top_k * 4, 80)))
                        rag_items_fb = rag_fb.get("items", []) if isinstance(rag_fb, dict) else []
                        sp = str(source_prefix or "").strip()
                        if not sp and str(lote or "").strip():
                            sp = f"afiliaciones_lote_{str(lote).strip()}"
                        rag_items_fb = self._filter_rag_items_by_source_prefix(rag_items_fb, sp)
                        # Evitar falsos positivos: exigir coincidencia de término ancla de entidad
                        # (empresa/ciudad/nit/nombre objetivo) en texto o metadata.
                        generic_terms = {
                            "empresa", "empresas", "afiliado", "afiliados", "afiliada", "afiliadas",
                            "sede", "sedes", "representante", "legal", "trabajador", "trabajadores",
                            "nit", "cedula", "cédula", "documento", "datos", "dame", "consulta",
                            "nomina", "nómina", "salario", "salarios", "valor", "bogota", "bogotá",
                            "barranquilla", "medellin", "medellín", "cali", "palma", "palmas",
                        }
                        anchor_terms = [t for t in q_entity_terms if (len(t) >= 4 and t not in generic_terms and not t.isdigit())]
                        if not anchor_terms:
                            anchor_terms = [t for t in q_entity_terms if (t.isdigit() and len(t) >= 6)]

                        def _rag_hit_has_anchor(it: dict[str, Any]) -> bool:
                            if not anchor_terms:
                                return True
                            md = it.get("metadata") if isinstance(it.get("metadata"), dict) else {}
                            text_norm = self._norm_text(str(it.get("text") or ""))
                            fn_norm = self._norm_text(str(md.get("filename") or md.get("path") or it.get("doc_id") or ""))
                            hay = False
                            for term in anchor_terms:
                                tn = self._norm_text(term)
                                if not tn:
                                    continue
                                if tn in text_norm or tn in fn_norm:
                                    hay = True
                                    break
                            return hay

                        rag_items_fb = [it for it in rag_items_fb if _rag_hit_has_anchor(it)]
                    if rag_items_fb:
                        asks_nomina_value = any(k in qn_raw for k in ("nomina", "nómina", "salario", "cotizacion", "cotización"))
                        nomina_detectada: int | None = None
                        if asks_nomina_value:
                            candidates: list[int] = []
                            for it in rag_items_fb[:20]:
                                t_raw = str(it.get("text") or "")
                                if not t_raw:
                                    continue
                                t_norm = self._norm_text(t_raw)
                                if not any(k in t_norm for k in ("nomina", "nómina", "salario", "cotizacion", "cotizacion", "monto total")):
                                    continue
                                for m in re.finditer(r"\b\d{6,15}\b", re.sub(r"[.,]", "", t_raw)):
                                    try:
                                        v = int(str(m.group(0) or "0"))
                                    except Exception:
                                        continue
                                    if 100000 <= v <= 999999999999:
                                        candidates.append(v)
                            if candidates:
                                nomina_detectada = max(candidates)
                        top_rows = []
                        for it in rag_items_fb[:6]:
                            md = it.get("metadata") if isinstance(it.get("metadata"), dict) else {}
                            filename = str(md.get("filename") or md.get("path") or it.get("doc_id") or "")
                            kind = str(md.get("kind") or "")
                            score = float(it.get("score") or 0.0)
                            top_rows.append(f"- {filename} ({kind or 'doc'}) · score {score:.2f}")
                        answer_fb_lines = [
                            "Coincidencias encontradas en RAG del lote actual.",
                            f"- Consulta: {question}",
                            f"- Contexto actual: lote={lote or '-'} | idtrámite={idtramite or '-'}",
                        ]
                        if nomina_detectada is not None:
                            answer_fb_lines.append(f"- Nómina total detectada (RAG): {nomina_detectada:,}".replace(",", "."))
                        answer_fb_lines.append("- Evidencia principal:")
                        answer_fb_lines.extend(top_rows)
                        answer_fb = "\n".join(answer_fb_lines)
                        return {
                            "ok": True,
                            "template": template,
                            "system_prompt": PROMPT_TEMPLATES.get(template, PROMPT_TEMPLATES["operacion"]),
                            "question": q,
                            "answer": finalize(answer_fb),
                            "citations": self._maybe_citations(
                                [
                                    {"doc_id": str(it.get("doc_id") or ""), "source": str(it.get("source") or ""), "score": float(it.get("score") or 0.0)}
                                    for it in rag_items_fb[:6]
                                ]
                            ),
                            "rag_hits": len(rag_items_fb),
                            "db_hits": 0,
                            "db_base": db_base,
                            "db_rows_preview": [],
                            "provider": "local-deterministic",
                        }
                    trace("entity_lookup_no_match", tool="db.search_afiliaciones_context", detail=f"terms={','.join(q_entity_terms[:4])}")
                    return {
                        "ok": True,
                        "template": template,
                        "system_prompt": PROMPT_TEMPLATES.get(template, PROMPT_TEMPLATES["operacion"]),
                        "question": q,
                        "answer": finalize(
                            "Sin coincidencias documentales para esa búsqueda.\n"
                            f"- Consulta: {question}\n"
                            f"- Contexto actual: lote={lote or '-'} | idtrámite={idtramite or '-'}\n"
                            "- Sugerencia: intenta con NIT/cédula exacta o ejecuta sin filtro de lote para búsqueda global."
                        ),
                        "citations": [],
                        "rag_hits": 0,
                        "db_hits": 0,
                        "db_base": db_base,
                        "db_rows_preview": [],
                        "provider": "local-deterministic",
                    }
                # Ruta explícita: comparar nombre representante en Cámara vs Formulario de afiliación.
                wants_camara_vs_afiliacion = (
                    ("camara" in qn_raw or "cámara" in qn_raw)
                    and ("afiliacion" in qn_raw or "afiliación" in qn_raw or "formulario" in qn_raw)
                    and ("representante" in qn_raw or "legal" in qn_raw)
                    and ("igual" in qn_raw or "iguales" in qn_raw or "coincid" in qn_raw or "certific" in qn_raw)
                )
                if wants_camara_vs_afiliacion:
                    trace("rep_name_camara_vs_form", tool="cache.precheck", detail="comparacion OCR camara vs formulario")
                    pre = self._load_precheck_cache(base=db_base, lote=lote, idtramite=idtramite)
                    docs_pre = pre.get("docs_ocr", []) if isinstance(pre, dict) else []
                    excel_fields = pre.get("excel_fields", {}) if isinstance(pre, dict) else {}
                    rep_ref = str((excel_fields or {}).get("representante_legal") or "").strip()
                    if not rep_ref:
                        dim_now = self.db_tools.afiliaciones_dimensional_snapshot(base=db_base, lote=lote, idtramite=idtramite, limit=60)
                        emps_now = dim_now.get("empleadores", []) if isinstance(dim_now, dict) else []
                        if isinstance(emps_now, list) and emps_now:
                            rep_ref = str((emps_now[0] or {}).get("representante_legal") or "").strip()
                    docs_eval: list[dict[str, Any]] = docs_pre if isinstance(docs_pre, list) else []
                    rag_citations: list[dict[str, Any]] = []
                    if not docs_eval:
                        trace("rep_name_camara_vs_form_rag_fallback", tool="rag.query", detail="sin cache, uso RAG lote")
                        sp = str(source_prefix or "").strip()
                        if not sp and str(lote or "").strip():
                            sp = f"afiliaciones_lote_{str(lote).strip()}"
                        q_cmp = " ".join(
                            [
                                "camara comercio formulario afiliacion representante legal",
                                str(rep_ref or "").strip(),
                                str(question or "").strip(),
                            ]
                        ).strip()
                        rag_cmp = self.rag.query(q_cmp, top_k=max(18, min(top_k * 4, 45)))
                        rag_items_cmp = rag_cmp.get("items", []) if isinstance(rag_cmp, dict) else []
                        rag_items_cmp = self._filter_rag_items_by_source_prefix(rag_items_cmp, sp)
                        docs_eval = []
                        for it in rag_items_cmp[:80]:
                            md = it.get("metadata") if isinstance(it.get("metadata"), dict) else {}
                            txt = str(it.get("text") or "").strip()
                            if not txt:
                                continue
                            fn = str(md.get("filename") or "").strip()
                            path = str(md.get("path") or "").strip()
                            if not fn and path:
                                fn = Path(path.replace("\\", "/")).name
                            if not fn:
                                continue
                            docs_eval.append(
                                {
                                    "filename": fn,
                                    "doc_type": str(md.get("doc_type") or ""),
                                    "tipo": str(md.get("tipo") or md.get("tipo_adjunto") or ""),
                                    "text": txt,
                                    "ocr_text": txt,
                                }
                            )
                            if len(rag_citations) < 6:
                                rag_citations.append(
                                    {
                                        "doc_id": str(it.get("doc_id") or fn),
                                        "source": str(it.get("source") or sp or "rag"),
                                        "score": float(it.get("score") or 0.0),
                                    }
                                )
                    if not docs_eval:
                        answer_no_cache = (
                            "No pude reunir evidencia OCR para certificar Cámara vs Afiliación en este momento.\n"
                            "- Ejecuta Paso 0 (Prevalidación documental) para refrescar OCR del lote.\n"
                            "- Luego repite esta consulta y NOVA mostrará COINCIDE/NO COINCIDE con enlaces de imagen."
                        )
                        return {
                            "ok": True,
                            "template": template,
                            "system_prompt": PROMPT_TEMPLATES.get(template, PROMPT_TEMPLATES["operacion"]),
                            "question": q,
                            "answer": finalize(answer_no_cache),
                            "citations": [],
                            "rag_hits": 0,
                            "db_hits": len(af_rows),
                            "db_base": db_base,
                            "db_rows_preview": af_rows[:8],
                            "provider": "local-deterministic",
                        }
                    rep_ref_norm = self._norm_text(rep_ref)
                    rep_tokens = [t for t in rep_ref_norm.split() if len(t) >= 4 and t not in {"de", "del", "la", "las", "los", "y"}][:6]

                    def _best_doc(items: list[dict[str, Any]], kind: str) -> dict[str, Any]:
                        best: dict[str, Any] = {}
                        best_score = -1
                        for d in items:
                            dt = str(d.get("doc_type") or "").strip()
                            tipo = str(d.get("tipo") or d.get("tipo_adjunto") or "").strip()
                            fn = str(d.get("filename") or "").strip()
                            if kind == "camara":
                                if not (dt == "camara_comercio" or tipo == "5"):
                                    continue
                            else:
                                fnn = self._norm_text(fn)
                                if not (dt == "formulario_afiliacion" or tipo == "0" or "formulario" in fnn):
                                    continue
                            text_norm = self._norm_text(str(d.get("text") or d.get("ocr_text") or ""))
                            score = 0
                            for tk in rep_tokens:
                                if tk in text_norm:
                                    score += 1
                            if score > best_score:
                                best_score = score
                                best = d
                        return best

                    cam = _best_doc(docs_eval, "camara")
                    frm = _best_doc(docs_eval, "form")
                    cam_txt = self._norm_text(str(cam.get("text") or cam.get("ocr_text") or ""))
                    frm_txt = self._norm_text(str(frm.get("text") or frm.get("ocr_text") or ""))
                    cam_hits = sum(1 for tk in rep_tokens if tk in cam_txt)
                    frm_hits = sum(1 for tk in rep_tokens if tk in frm_txt)
                    min_hits = max(2, min(3, len(rep_tokens))) if rep_tokens else 2
                    cam_ok = cam_hits >= min_hits
                    frm_ok = frm_hits >= min_hits
                    equal_ok = cam_ok and frm_ok
                    cam_name = self._extract_rep_name_from_text(str(cam.get("text") or cam.get("ocr_text") or ""))
                    frm_name = self._extract_rep_name_from_text(str(frm.get("text") or frm.get("ocr_text") or ""))
                    if not rep_ref.strip() and (cam_name or frm_name):
                        rep_ref = cam_name or frm_name
                    if not rep_tokens and cam_name and frm_name:
                        cam_n = self._norm_text(cam_name)
                        frm_n = self._norm_text(frm_name)
                        cam_t = [t for t in cam_n.split() if len(t) >= 4]
                        frm_t = [t for t in frm_n.split() if len(t) >= 4]
                        overlap = len(set(cam_t) & set(frm_t))
                        ratio = difflib.SequenceMatcher(None, cam_n, frm_n).ratio()
                        equal_ok = (overlap >= 2) or (ratio >= 0.74)

                    lines = [
                        "Validación OCR: representante legal en Cámara vs Afiliación",
                        f"- Referencia (Excel): {rep_ref or 'N/D'}",
                        f"- Cámara: {str(cam.get('filename') or 'N/D')} | coincidencia tokens={cam_hits}/{len(rep_tokens)}",
                        f"- Afiliación: {str(frm.get('filename') or 'N/D')} | coincidencia tokens={frm_hits}/{len(rep_tokens)}",
                        f"- Resultado: {'IGUALES' if equal_ok else 'REVISAR (no coincide completamente)'}",
                    ]
                    if cam_name:
                        lines.append(f"- Nombre detectado en Cámara: {cam_name}")
                    if frm_name:
                        lines.append(f"- Nombre detectado en Afiliación: {frm_name}")
                    cam_fn = str(cam.get("filename") or "").strip()
                    frm_fn = str(frm.get("filename") or "").strip()
                    if cam_fn:
                        lines.append(
                            f"- Ver Cámara: /api/v1/nova/pdf/view?base={base}&lote={lote}&idtramite={idtramite}&filename={cam_fn}"
                        )
                    if frm_fn:
                        lines.append(
                            f"- Ver Afiliación: /api/v1/nova/pdf/view?base={base}&lote={lote}&idtramite={idtramite}&filename={frm_fn}"
                        )
                    return {
                        "ok": True,
                        "template": template,
                        "system_prompt": PROMPT_TEMPLATES.get(template, PROMPT_TEMPLATES["operacion"]),
                        "question": q,
                        "answer": finalize("\n".join(lines)),
                        "citations": self._maybe_citations(
                            rag_citations
                            if rag_citations
                            else [{"doc_id": "precheck:rep-name-compare", "source": "nova.precheck_ingesta_documental", "score": 1.0}]
                        ),
                        "rag_hits": 0,
                        "db_hits": len(af_rows),
                        "db_base": db_base,
                        "db_rows_preview": af_rows[:8],
                        "provider": "local-deterministic",
                    }
                # Ruta explícita: cédula de representante + imagen/visor.
                wants_rep_cedula_image = (
                    (("cedula" in qn_raw) or ("cédula" in qn_raw))
                    and (("representante" in qn_raw) or ("legal" in qn_raw))
                    and (("imagen" in qn_raw) or ("pdf" in qn_raw) or ("ver" in qn_raw) or ("muestra" in qn_raw) or ("muestrame" in qn_raw))
                )
                if wants_rep_cedula_image:
                    trace("rep_cedula_image", tool="pdf.candidates", detail="consulta directa de cédula representante")
                    pre = self._load_precheck_cache(base=db_base, lote=lote, idtramite=idtramite)
                    excel_fields = pre.get("excel_fields", {}) if isinstance(pre, dict) else {}
                    rep_ref = str((excel_fields or {}).get("representante_legal") or "").strip()
                    rep_ref_norm = self._norm_text(rep_ref)
                    rep_tokens = [t for t in rep_ref_norm.split() if len(t) >= 4 and t not in {"de", "del", "la", "las", "los", "y"}][:6]
                    cand_rows = self.find_pdf_candidates(
                        question="cedula representante legal",
                        base=db_base,
                        lote=lote,
                        idtramite=idtramite,
                        max_files=16,
                        allow_live_fallback=False,
                    )
                    if not cand_rows:
                        snapshot_docs = self.db_tools.afiliaciones_dimensional_snapshot(
                            base=db_base,
                            lote=lote,
                            idtramite=idtramite,
                            limit=500,
                        )
                        adj_rows = (snapshot_docs.get("adjuntos", []) if isinstance(snapshot_docs, dict) else [])
                        pseudo_rows: list[dict[str, Any]] = []
                        seen_files: set[str] = set()
                        for a in adj_rows:
                            tipo = str(a.get("tipo_adjunto") or "").strip()
                            if tipo != "6":
                                continue
                            ruta = str(a.get("rutaadjunto") or "").strip()
                            fn = Path(ruta.replace("\\", "/")).name if ruta else ""
                            if not fn:
                                continue
                            fk = fn.lower()
                            if fk in seen_files:
                                continue
                            seen_files.add(fk)
                            pseudo_rows.append(
                                {
                                    "filename": fn,
                                    "tipo_adjunto": "6",
                                    "score": 1,
                                    "chars": 0,
                                    "evidence": "Coincidencia por tipo documental (cédula representante).",
                                }
                            )
                            if len(pseudo_rows) >= 8:
                                break
                        answer_docs = self._format_pdf_candidates_answer(
                            question="cedula representante legal",
                            base=db_base,
                            lote=lote,
                            idtramite=idtramite,
                            rows=pseudo_rows,
                        )
                        return {
                            "ok": True,
                            "template": template,
                            "system_prompt": PROMPT_TEMPLATES.get(template, PROMPT_TEMPLATES["operacion"]),
                            "question": q,
                            "answer": finalize(answer_docs),
                            "citations": self._maybe_citations(
                                [{"doc_id": "db:adjuntos-fallback", "source": f"{db_base}.proc_servicios_obtenerarchivosadjuntos", "score": 1.0}]
                            ),
                            "rag_hits": 0,
                            "db_hits": len(af_rows),
                            "db_base": db_base,
                            "db_rows_preview": af_rows[:8],
                            "provider": "local-deterministic",
                        }
                    answer_pdf = self._format_pdf_candidates_answer(
                        question="cedula representante legal",
                        base=db_base,
                        lote=lote,
                        idtramite=idtramite,
                        rows=cand_rows,
                    )
                    # Certificación OCR de consistencia nombre esperado vs evidencia de cédula.
                    cert_lines: list[str] = []
                    if rep_tokens:
                        joined_ev = self._norm_text(" ".join(str(r.get("evidence") or "") for r in cand_rows[:6]))
                        hits = sum(1 for tk in rep_tokens if tk in joined_ev)
                        min_hits = max(2, min(3, len(rep_tokens)))
                        cert_lines.append("Verificación OCR cédula representante:")
                        cert_lines.append(f"- Referencia esperada: {rep_ref}")
                        cert_lines.append(f"- Coincidencia en evidencia OCR: {hits}/{len(rep_tokens)}")
                        cert_lines.append(f"- Resultado: {'COINCIDE' if hits >= min_hits else 'REVISAR'}")
                    answer_out = answer_pdf if not cert_lines else f"{answer_pdf}\n" + "\n".join(cert_lines)
                    return {
                        "ok": True,
                        "template": template,
                        "system_prompt": PROMPT_TEMPLATES.get(template, PROMPT_TEMPLATES["operacion"]),
                        "question": q,
                        "answer": finalize(answer_out),
                        "citations": self._maybe_citations(
                            [{"doc_id": "db:adjuntos+pdf-candidates", "source": f"{db_base}.proc_servicios_obtenerarchivosadjuntos", "score": 1.0}]
                        ),
                        "rag_hits": 0,
                        "db_hits": len(af_rows),
                        "db_base": db_base,
                        "db_rows_preview": af_rows[:8],
                        "provider": "local-deterministic",
                    }
                # Ruta explícita: total nómina por ciudad para todos.
                city_target = ""
                for c in ("barranquilla", "bogota", "medellin", "cali", "cartagena"):
                    if c in qn_raw:
                        city_target = c
                        break
                asks_nomina_total_city = (
                    bool(city_target)
                    and any(k in qn_raw for k in ("nomina", "nómina", "nomna", "nomnas", "salario", "salarios"))
                    and any(k in qn_raw for k in ("total", "todos", "todas"))
                )
                if asks_nomina_total_city:
                    trace("city_nomina_total", tool="db.wd+brempresasarp", detail=f"city={city_target}")
                    total_city = self._get_city_nomina_total(base=db_base, city_target=city_target)
                    answer_city = (
                        "Resultado de nómina por ciudad:\n"
                        f"- Ciudad: {city_target.upper()}\n"
                        f"- Nómina total afiliados: {int(total_city)}\n"
                        "- Fuente: consolidado operativo (wd + brempresasarp).\n"
                        f"- Contexto de consulta: lote={lote or '-'} | idtrámite={idtramite or '-'}"
                    )
                    return {
                        "ok": True,
                        "template": template,
                        "system_prompt": PROMPT_TEMPLATES.get(template, PROMPT_TEMPLATES["operacion"]),
                        "question": q,
                        "answer": finalize(answer_city),
                        "citations": self._maybe_citations(
                            [{"doc_id": "db:city-nomina-total", "source": f"{db_base}.wd+brempresasarp", "score": 1.0}]
                        ),
                        "rag_hits": 0,
                        "db_hits": len(af_rows),
                        "db_base": db_base,
                        "db_rows_preview": af_rows[:8],
                        "provider": "local-deterministic",
                    }
                if is_revalidator_intent:
                    trace("precheck_cache_read", tool="cache.precheck", detail=f"base={db_base} lote={lote} idtramite={idtramite}")
                    pre = self._load_precheck_cache(base=db_base, lote=lote, idtramite=idtramite)
                    if isinstance(pre, dict):
                        answer_pre = self._format_revalidator_answer(question=q, precheck=pre)
                        return {
                            "ok": True,
                            "template": template,
                            "system_prompt": PROMPT_TEMPLATES.get(template, PROMPT_TEMPLATES["operacion"]),
                            "question": q,
                            "answer": finalize(answer_pre),
                            "citations": self._maybe_citations(
                                [{"doc_id": "precheck:cache", "source": "nova.precheck_ingesta_documental", "score": 1.0}]
                            ),
                            "rag_hits": 0,
                            "db_hits": len(af_rows),
                            "db_base": db_base,
                            "db_rows_preview": af_rows[:8],
                            "provider": "local-deterministic",
                        }
                    answer_pre_missing = (
                        "No tengo prevalidación documental reciente para actuar como revalidador.\n"
                        "- Ejecuta Paso 0 (ingesta + precheck) para cargar reglas, OCR y checklist.\n"
                        "- Luego vuelve a preguntar y te doy el diagnóstico por regla (OK/FALLA) con evidencia."
                    )
                    return {
                        "ok": True,
                        "template": template,
                        "system_prompt": PROMPT_TEMPLATES.get(template, PROMPT_TEMPLATES["operacion"]),
                        "question": q,
                        "answer": finalize(answer_pre_missing),
                        "citations": [],
                        "rag_hits": 0,
                        "db_hits": len(af_rows),
                        "db_base": db_base,
                        "db_rows_preview": af_rows[:8],
                        "provider": "local-deterministic",
                    }
                if is_xlsx_pdf_compare_intent:
                    trace("xlsx_vs_ocr", tool="ocr.live+excel", detail="comparacion xlsx contra OCR en vivo")
                    # Modo chat: comparación rápida por cache para evitar latencia alta por OCR/filesystem.
                    cache_pre = self._load_precheck_cache(base=db_base, lote=lote, idtramite=idtramite)
                    if not isinstance(cache_pre, dict) or not cache_pre:
                        trace("xlsx_vs_ocr_cache_miss", tool="cache.precheck", detail="sin snapshot de precheck")
                        answer = (
                            "Comparación XLSX vs OCR (rápida): no hay snapshot reciente en caché para este lote.\n"
                            "- Ejecuta Paso 0 (prevalidación documental) para cargar Excel + OCR en caché.\n"
                            "- Luego repite esta consulta y NOVA comparará en caliente con evidencia."
                        )
                    else:
                        excel_fields = cache_pre.get("excel_fields") if isinstance(cache_pre.get("excel_fields"), dict) else {}
                        summary = cache_pre.get("summary") if isinstance(cache_pre.get("summary"), dict) else {}
                        alerts = cache_pre.get("alerts") if isinstance(cache_pre.get("alerts"), list) else []
                        docs_ocr = cache_pre.get("docs_ocr") if isinstance(cache_pre.get("docs_ocr"), list) else []
                        docs_ok = sum(1 for d in docs_ocr if bool(d.get("ok")))
                        trace("xlsx_vs_ocr_cache_hit", tool="cache.precheck", detail=f"docs_ocr={len(docs_ocr)}")
                        crit_alerts = [a for a in alerts if str(a.get("severity") or "").lower() in {"critical", "high"}]
                        lines = [
                            "Comparación XLSX vs OCR (rápida, desde cache precheck):",
                            f"- Empresa (Excel): {str(excel_fields.get('empresa') or 'N/D')}",
                            f"- NIT (Excel): {str(excel_fields.get('nit') or 'N/D')}",
                            f"- OCR procesado: {docs_ok}/{len(docs_ocr)} documento(s) en cache.",
                            f"- Sedes Excel: {int(summary.get('worker_sheets_detected') or 0)} | Tipo1 detectado: {int(summary.get('docs_tipo_1_detected') or 0)}",
                        ]
                        if crit_alerts:
                            lines.append("- Alertas críticas detectadas:")
                            for a in crit_alerts[:5]:
                                lines.append(f"- {str(a.get('code') or '')}: {str(a.get('message') or '')}")
                        else:
                            lines.append("- Estado: sin alertas críticas en la última prevalidación cacheada.")
                        answer = "\n".join(lines)
                    return {
                        "ok": True,
                        "template": template,
                        "system_prompt": PROMPT_TEMPLATES.get(template, PROMPT_TEMPLATES["operacion"]),
                        "question": q,
                        "answer": finalize(answer),
                        "citations": self._maybe_citations(
                            [{"doc_id": "xlsx-vs-live-ocr", "source": "contrato_clean+adjuntos_live_ocr", "score": 1.0}]
                        ),
                        "rag_hits": 0,
                        "db_hits": len(af_rows),
                        "db_base": db_base,
                        "db_rows_preview": af_rows[:8],
                        "provider": "local-deterministic",
                    }
                if is_pdf_doc_lookup_intent:
                    trace("pdf_doc_lookup", tool="pdf.candidates", detail="busqueda documental rapida (cache+ocr acotado)")
                    cand_rows = self.find_pdf_candidates(
                        question=q,
                        base=db_base,
                        lote=lote,
                        idtramite=idtramite,
                        max_files=12,
                        allow_live_fallback=False,
                    )
                    if not cand_rows:
                        trace("pdf_doc_lookup_fallback", tool="db.adjuntos", detail="sin hits OCR; fallback por tipo documental")
                        snapshot_docs = self.db_tools.afiliaciones_dimensional_snapshot(
                            base=db_base,
                            lote=lote,
                            idtramite=idtramite,
                            limit=500,
                        )
                        adj_rows = (snapshot_docs.get("adjuntos", []) if isinstance(snapshot_docs, dict) else [])
                        answer_docs = self._format_adjuntos_by_type_answer(
                            question=q,
                            base=db_base,
                            lote=lote,
                            idtramite=idtramite,
                            adjuntos=adj_rows,
                            ocr_rows=[],
                        )
                        return {
                            "ok": True,
                            "template": template,
                            "system_prompt": PROMPT_TEMPLATES.get(template, PROMPT_TEMPLATES["operacion"]),
                            "question": q,
                            "answer": finalize(answer_docs),
                            "citations": self._maybe_citations(
                                [{"doc_id": "db:adjuntos-fallback", "source": f"{db_base}.proc_servicios_obtenerarchivosadjuntos", "score": 1.0}]
                            ),
                            "rag_hits": 0,
                            "db_hits": len(af_rows),
                            "db_base": db_base,
                            "db_rows_preview": af_rows[:8],
                            "provider": "local-deterministic",
                        }
                    answer_pdf = self._format_pdf_candidates_answer(
                        question=q,
                        base=db_base,
                        lote=lote,
                        idtramite=idtramite,
                        rows=cand_rows,
                    )
                    return {
                        "ok": True,
                        "template": template,
                        "system_prompt": PROMPT_TEMPLATES.get(template, PROMPT_TEMPLATES["operacion"]),
                        "question": q,
                        "answer": finalize(answer_pdf),
                        "citations": self._maybe_citations(
                            [{"doc_id": "db:adjuntos+pdf-candidates", "source": f"{db_base}.proc_servicios_obtenerarchivosadjuntos", "score": 1.0}]
                        ),
                        "rag_hits": 0,
                        "db_hits": len(af_rows),
                        "db_base": db_base,
                        "db_rows_preview": af_rows[:8],
                        "provider": "local-deterministic",
                    }
                if is_doc_type_lookup_intent:
                    trace("doc_type_lookup", tool="db.adjuntos", detail="consulta adjuntos por tipo documental")
                    snapshot_docs = self.db_tools.afiliaciones_dimensional_snapshot(
                        base=db_base,
                        lote=lote,
                        idtramite=idtramite,
                        limit=500,
                    )
                    adj_rows = (snapshot_docs.get("adjuntos", []) if isinstance(snapshot_docs, dict) else [])
                    target_types = self._doc_type_targets_from_question(q)
                    filtered_adj = [
                        a
                        for a in adj_rows
                        if str(a.get("tipo_adjunto") or "").strip() in set(target_types)
                    ]
                    wants_ocr_excerpt = (
                        has_like_q("ocr", 0.58)
                        or has_like_q("evidencia", 0.58)
                        or has_like_q("extracto", 0.58)
                        or has_like_q("texto", 0.58)
                    )
                    ocr_excerpt_rows: list[dict[str, Any]] = []
                    if wants_ocr_excerpt and filtered_adj:
                        ocr_out = self._run_live_ocr_for_adjuntos(
                            adjuntos=filtered_adj,
                            max_files=3,
                        )
                        ocr_excerpt_rows = ocr_out.get("rows", []) if isinstance(ocr_out, dict) else []
                    answer_docs = self._format_adjuntos_by_type_answer(
                        question=q,
                        base=db_base,
                        lote=lote,
                        idtramite=idtramite,
                        adjuntos=adj_rows,
                        ocr_rows=ocr_excerpt_rows,
                    )
                    return {
                        "ok": True,
                        "template": template,
                        "system_prompt": PROMPT_TEMPLATES.get(template, PROMPT_TEMPLATES["operacion"]),
                        "question": q,
                        "answer": finalize(answer_docs),
                        "citations": self._maybe_citations(
                            [{"doc_id": "db:adjuntos+live-ocr-doc-type-lookup", "source": f"{db_base}.proc_servicios_obtenerarchivosadjuntos", "score": 1.0}]
                        ),
                        "rag_hits": 0,
                        "db_hits": len(af_rows),
                        "db_base": db_base,
                        "db_rows_preview": af_rows[:8],
                        "provider": "local-deterministic",
                    }
                if is_live_ocr_intent:
                    trace("ocr_live", tool="ocr.live", detail=f"max_files={30}")
                    live_ocr = self._run_live_ocr_for_lote(base=db_base, lote=lote, idtramite=idtramite, max_files=30)
                    if is_compare_ocr_intent:
                        live_items = [
                            {
                                "text": str(r.get("ocr_text") or ""),
                                "metadata": {"path": str(r.get("filename") or r.get("source_path") or "")},
                                "source": "live-ocr",
                            }
                            for r in live_ocr.get("rows", [])
                            if bool(r.get("ok")) and str(r.get("ocr_text") or "").strip()
                        ]
                        answer_cmp_live = self._format_afiliaciones_ocr_comparison(
                            question=q,
                            af_rows=af_rows,
                            rag_items=live_items,
                            lote=lote,
                            idtramite=idtramite,
                        )
                        answer_live = self._format_live_ocr_result(live_ocr)
                        answer = f"{answer_live}\n\n{answer_cmp_live}".strip()
                    else:
                        answer = self._format_live_ocr_result(live_ocr)
                    return {
                        "ok": True,
                        "template": template,
                        "system_prompt": PROMPT_TEMPLATES.get(template, PROMPT_TEMPLATES["operacion"]),
                        "question": q,
                        "answer": finalize(answer),
                        "citations": self._maybe_citations(
                            [{"doc_id": "db:adjuntos+live-ocr", "source": f"{db_base}.proc_servicios_obtenerarchivosadjuntos", "score": 1.0}]
                        ),
                        "rag_hits": 0,
                        "db_hits": len(af_rows),
                        "db_base": db_base,
                        "db_rows_preview": af_rows[:8],
                        "provider": "local-deterministic",
                    }
                if is_compare_ocr_intent:
                    trace("ocr_compare", tool="rag.query+db.dim", detail="comparacion OCR vs BD")
                    employer_seed = self._pick_employer_row(af_rows)
                    seed_terms = []
                    for k in ("empleador", "nit_empleador", "direccion", "telefono", "ciudad", "actividad", "tipo_aportante"):
                        val = str((employer_seed or {}).get(k) or "").strip()
                        if val:
                            seed_terms.append(val)
                    enriched_query = " ".join(
                        [
                            q,
                            "empleador nit direccion telefono ciudad representante legal actividad economica tipo aportante",
                            " ".join(seed_terms),
                        ]
                    ).strip()
                    rag_cmp = self.rag.query(
                        enriched_query,
                        top_k=max(20, min(top_k * 6, 80)),
                    )
                    rag_items_cmp = rag_cmp.get("items", []) if isinstance(rag_cmp, dict) else []
                    rag_items_cmp = self._filter_rag_items_by_source_prefix(rag_items_cmp, source_prefix)
                    rag_items_cmp = self._select_rag_items_for_ocr_compare(rag_items_cmp, max_items=40)
                    rag_items_cmp = self._rank_rag_items_for_employer_compare(
                        rag_items_cmp,
                        employer_seed=employer_seed,
                        lote=lote,
                        idtramite=idtramite,
                        max_items=40,
                    )
                    answer_cmp = self._format_afiliaciones_ocr_comparison(
                        question=q,
                        af_rows=af_rows,
                        rag_items=rag_items_cmp,
                        lote=lote,
                        idtramite=idtramite,
                    )
                    return {
                        "ok": True,
                        "template": template,
                        "system_prompt": PROMPT_TEMPLATES.get(template, PROMPT_TEMPLATES["operacion"]),
                        "question": q,
                        "answer": finalize(answer_cmp),
                        "citations": self._maybe_citations(
                            [{"doc_id": "db+rag:afiliaciones-ocr-compare", "source": f"{db_base}.afiliaciones+rag", "score": 1.0}]
                        ),
                        "rag_hits": len(rag_items_cmp),
                        "db_hits": len(af_rows),
                        "db_base": db_base,
                        "db_rows_preview": af_rows[:8],
                        "provider": "local-deterministic",
                    }
                if is_dimensional_intent and not is_excel_cps_intent:
                    trace("dimension_snapshot", tool="db.afiliaciones_dimensional_snapshot", detail="resumen operativo del lote")
                    contrato_fields: dict[str, str] = {}
                    normative_catalog: list[dict[str, Any]] = []
                    xlsx_sheet_names: list[str] = []
                    contrato_src_dim = ""
                    nomina_total_override: int | None = None
                    dim = self.db_tools.afiliaciones_dimensional_snapshot(
                        base=db_base,
                        lote=lote,
                        idtramite=idtramite,
                        limit=250,
                    )
                    needs_nomina = any(k in qn for k in ("nomina", "nómina", "salario", "salarios"))
                    if needs_nomina:
                        nomina_total_override = self._get_authoritative_nomina_total(base=db_base, lote=lote)
                        trace(
                            "nomina_authoritative",
                            tool="legacy.reporte_ejecutivo",
                            detail=f"nomina_total={int(nomina_total_override or 0)}",
                        )
                    if needs_nomina and source_prefix.strip() and self._as_int_count(dim.get("salarios_total")) <= 0:
                        contrato_txt_dim, contrato_src_dim = self._pick_contrato_primary_source_text(
                            question=q,
                            lote=lote,
                            source_prefix=source_prefix,
                            top_k=max(20, min(top_k * 6, 80)),
                        )
                        contrato_fields = self._extract_xlsx_empleador_sede(contrato_txt_dim) if contrato_txt_dim else {}
                    answer_dim = self._format_afiliaciones_dimension_answer(
                        question=q,
                        qn=qn,
                        snapshot=dim,
                        contrato_fields=contrato_fields,
                        normative_catalog=normative_catalog,
                        xlsx_sheet_names=xlsx_sheet_names,
                        contrato_source=contrato_src_dim,
                        nomina_total_override=nomina_total_override,
                    )
                    answer_dim, verify = self._verify_afiliaciones_answer(
                        question=q,
                        answer=answer_dim,
                        snapshot=dim,
                    )
                    trace(
                        "answer_verify",
                        tool="verifier.afiliaciones",
                        detail=f"ok={verify.get('ok')} repaired={verify.get('repaired')}",
                    )
                    return {
                        "ok": True,
                        "template": template,
                        "system_prompt": PROMPT_TEMPLATES.get(template, PROMPT_TEMPLATES["operacion"]),
                        "question": q,
                        "answer": finalize(answer_dim),
                        "citations": self._maybe_citations(
                            [{"doc_id": "db:afiliaciones-dimension", "source": f"{db_base}.proc_servicios+br*", "score": 1.0}]
                        ),
                        "rag_hits": 0,
                        "db_hits": len(af_rows),
                        "db_base": db_base,
                        "db_rows_preview": af_rows[:8],
                        "provider": "local-deterministic",
                    }
                if is_excel_cps_intent:
                    trace("excel_audit", tool="excel.audit", detail="auditoria de excel CPS-F-216")
                    contrato_txt_x, contrato_src_x = self._pick_contrato_primary_source_text(
                        question=q,
                        lote=lote,
                        source_prefix=source_prefix,
                        top_k=max(20, min(top_k * 6, 80)),
                    )
                    contrato_fields = self._extract_xlsx_empleador_sede(contrato_txt_x) if contrato_txt_x else {}
                    xlsx_sheet_names = self._extract_xlsx_sheet_names(contrato_txt_x) if contrato_txt_x else []
                    dim = self.db_tools.afiliaciones_dimensional_snapshot(
                        base=db_base,
                        lote=lote,
                        idtramite=idtramite,
                        limit=500,
                    )
                    answer_excel = self._format_afiliaciones_excel_audit_answer(
                        question=q,
                        qn=qn,
                        contrato_text=contrato_txt_x,
                        contrato_fields=contrato_fields,
                        xlsx_sheet_names=xlsx_sheet_names,
                        contrato_source=contrato_src_x,
                        snapshot=dim,
                    )
                    return {
                        "ok": True,
                        "template": template,
                        "system_prompt": PROMPT_TEMPLATES.get(template, PROMPT_TEMPLATES["operacion"]),
                        "question": q,
                        "answer": finalize(answer_excel),
                        "citations": self._maybe_citations(
                            [{"doc_id": "xlsx:cps-f216-audit", "source": contrato_src_x or "xlsx", "score": 1.0}]
                        ),
                        "rag_hits": 0,
                        "db_hits": len(af_rows),
                        "db_base": db_base,
                        "db_rows_preview": af_rows[:8],
                        "provider": "local-deterministic",
                    }
                if af_rows:
                    self._save_entity_memory(
                        base=db_base,
                        lote=lote,
                        idtramite=idtramite,
                        row=(af_rows[0] if af_rows else None),
                    )
                    answer = self._format_afiliaciones_card(
                        question=q,
                        rows=af_rows,
                        base=db_base,
                        lote=lote,
                        idtramite=idtramite,
                    )
                    dim = self.db_tools.afiliaciones_dimensional_snapshot(
                        base=db_base,
                        lote=lote,
                        idtramite=idtramite,
                        limit=250,
                    )
                    answer, verify = self._verify_afiliaciones_answer(
                        question=q,
                        answer=answer,
                        snapshot=dim,
                    )
                    trace(
                        "answer_verify",
                        tool="verifier.afiliaciones",
                        detail=f"ok={verify.get('ok')} repaired={verify.get('repaired')}",
                    )
                    return {
                        "ok": True,
                        "template": template,
                        "system_prompt": PROMPT_TEMPLATES.get(template, PROMPT_TEMPLATES["operacion"]),
                        "question": q,
                        "answer": finalize(answer),
                        "citations": self._maybe_citations(
                            [{"doc_id": "db:afiliaciones-context", "source": f"{db_base}.afiliaciones", "score": 1.0}]
                        ),
                        "rag_hits": 0,
                        "db_hits": len(af_rows),
                        "db_base": db_base,
                        "db_rows_preview": af_rows[:8],
                        "provider": "local-deterministic",
                    }
            except Exception as exc:
                logger.warning(f'afiliaciones_context_search_failed base="{db_base}" error="{exc}"')

        # Data-first intent: pendientes de prestación.
        if (not afiliaciones_only_mode) and (has_like_q("pendiente") or has_like_q("pendientes")) and (
            has_like_q("prestacion") or has_like_q("prestaciones")
        ):
            try:
                pending = self.db_tools.get_pendientes_prestacion(base=db_base, limit=10)
                total = int(pending.get("total", 0) or 0)
                rows = pending.get("rows", []) if isinstance(pending.get("rows"), list) else []
                if total <= 0:
                    answer = (
                        "Pendientes de prestación (dato real): no se encontraron registros con estado "
                        "'PENDIENTE ... PRESTACION' en las tablas operativas consultadas."
                    )
                else:
                    lines = [f"Pendientes de prestación (dato real): total={total}."]
                    lines.append("Muestra de trámites:")
                    for r in rows[:5]:
                        lines.append(
                            f"- source={r.get('source_table','')} id_ref={r.get('id_ref','')} tramite={r.get('tramite','')} "
                            f"estado={r.get('estado','')} usuario={r.get('usuario','')}"
                        )
                    answer = "\n".join(lines)
                return {
                    "ok": True,
                    "template": template,
                    "system_prompt": PROMPT_TEMPLATES.get(template, PROMPT_TEMPLATES["operacion"]),
                    "question": q,
                    "answer": finalize(answer),
                    "citations": self._maybe_citations(
                        [{"doc_id": "db:pendientes-prestacion", "source": f"{db_base}.auxilios", "score": 1.0}]
                    ),
                    "rag_hits": 0,
                    "db_hits": len(rows),
                    "db_base": db_base,
                    "db_rows_preview": rows[:5],
                    "provider": "local-deterministic",
                }
            except Exception as exc:
                logger.warning(f'pendientes_prestacion_query_failed base="{db_base}" error="{exc}"')

        # Data-first intent: bancos.
        if (not afiliaciones_only_mode) and (has_like_q("banco") or has_like_q("bancos")):
            try:
                banks = self.db_tools.list_bancos(base=db_base, limit=20)
                total = int(banks.get("total", 0) or 0)
                rows = banks.get("rows", []) if isinstance(banks.get("rows"), list) else []
                lines = [f"Bancos (dato real): total={total}."]
                if rows:
                    lines.append("Muestra:")
                    for r in rows[:10]:
                        lines.append(f"- codigo={r.get('codigo','')} nombre={r.get('nombre','')}")
                else:
                    lines.append("No hay bancos disponibles en la tabla consultada.")
                return {
                    "ok": True,
                    "template": template,
                    "system_prompt": PROMPT_TEMPLATES.get(template, PROMPT_TEMPLATES["operacion"]),
                    "question": q,
                    "answer": self.security.mask_sensitive("\n".join(lines)),
                    "citations": self._maybe_citations(
                        [{"doc_id": "db:fun-bancos", "source": f"{db_base}.auxilios.fun_bancos", "score": 1.0}]
                    ),
                    "rag_hits": 0,
                    "db_hits": len(rows),
                    "db_base": db_base,
                    "db_rows_preview": rows[:10],
                    "provider": "local-deterministic",
                }
            except Exception as exc:
                logger.warning(f'bancos_query_failed base="{db_base}" error="{exc}"')

        # Data-first intent: pendientes de notificaciones/trámites/solicitudes.
        if (not afiliaciones_only_mode) and (has_like_q("pendiente") or has_like_q("pendientes")) and (
            has_like_q("notificacion")
            or has_like_q("notificaciones")
            or has_like_q("tramite")
            or has_like_q("tramites")
            or has_like_q("solicitud")
            or has_like_q("solicitudes")
        ):
            try:
                pending = self.db_tools.get_pending_summary(base=db_base, limit=12)
                total = int(pending.get("total", 0) or 0)
                n_not = int(pending.get("notificaciones_total", 0) or 0)
                n_fun = int(pending.get("funerarios_total", 0) or 0)
                rows = pending.get("rows", []) if isinstance(pending.get("rows"), list) else []
                lines = [f"Pendientes (dato real): total={total} (notificaciones={n_not}, funerarios={n_fun})."]
                if rows:
                    lines.append("Muestra:")
                    for r in rows[:8]:
                        lines.append(
                            f"- modulo={r.get('modulo','')} id_ref={r.get('id_ref','')} tramite={r.get('tramite','')} "
                            f"estado={r.get('estado','')} usuario={r.get('usuario','')}"
                        )
                else:
                    lines.append("No hay trámites/solicitudes pendientes en las tablas consultadas.")
                return {
                    "ok": True,
                    "template": template,
                    "system_prompt": PROMPT_TEMPLATES.get(template, PROMPT_TEMPLATES["operacion"]),
                    "question": q,
                    "answer": self.security.mask_sensitive("\n".join(lines)),
                    "citations": self._maybe_citations(
                        [{"doc_id": "db:pending-summary", "source": f"{db_base}.auxilios", "score": 1.0}]
                    ),
                    "rag_hits": 0,
                    "db_hits": len(rows),
                    "db_base": db_base,
                    "db_rows_preview": rows[:8],
                    "provider": "local-deterministic",
                }
            except Exception as exc:
                logger.warning(f'pending_summary_query_failed base="{db_base}" error="{exc}"')

        # Data-first intent: buscar reclamante por documento (requires numeric id).
        if (not afiliaciones_only_mode) and ((has_like_q("reclamante") and has_like_q("documento")) or (has_like_q("buscar") and has_like_q("reclamante"))):
            digits = "".join(ch for ch in q if ch.isdigit())
            if not digits:
                answer = (
                    "Para buscar reclamante con datos reales necesito el número de documento. "
                    "Ejemplo: 'buscar reclamante 12345678'."
                )
                return {
                    "ok": True,
                    "template": template,
                    "system_prompt": PROMPT_TEMPLATES.get(template, PROMPT_TEMPLATES["operacion"]),
                    "question": q,
                    "answer": finalize(answer),
                    "citations": [],
                    "rag_hits": 0,
                    "db_hits": 0,
                    "db_base": db_base,
                    "db_rows_preview": [],
                    "provider": "local-deterministic",
                }

        # Data-first global: for any question, try operational search in auxilios tables.
        try:
            op_ctx = self.db_tools.search_operational_context(base=db_base, question=q, limit=10)
            op_rows = op_ctx.get("rows", []) if isinstance(op_ctx, dict) else []
            if op_rows and not afiliaciones_only_mode:
                lines = [f"Resultado con datos reales: coincidencias={len(op_rows)}."]
                lines.append("Muestra de registros:")
                for r in op_rows[:6]:
                    lines.append(
                        f"- modulo={r.get('modulo','')} id_ref={r.get('id_ref','')} tramite={r.get('tramite','')} "
                        f"estado={r.get('estado','')} usuario={r.get('usuario','')}"
                    )
                answer = "\n".join(lines)
                return {
                    "ok": True,
                    "template": template,
                    "system_prompt": PROMPT_TEMPLATES.get(template, PROMPT_TEMPLATES["operacion"]),
                    "question": q,
                    "answer": finalize(answer),
                    "citations": self._maybe_citations(
                        [{"doc_id": "db:operational-search", "source": f"{db_base}.auxilios", "score": 1.0}]
                    ),
                    "rag_hits": 0,
                    "db_hits": len(op_rows),
                    "db_base": db_base,
                    "db_rows_preview": op_rows[:6],
                    "provider": "local-deterministic",
                }
            require_real = os.getenv("AI_REQUIRE_REAL_DATA", "true").strip().lower() in {"1", "true", "yes", "y"}
            if require_real and not procedural_hint:
                answer = (
                    "No encontré datos reales para esa consulta en las tablas operativas disponibles. "
                    "Intenta con identificadores concretos (trámite, solicitud, estado o usuario) para buscar nuevamente."
                )
                return {
                    "ok": True,
                    "template": template,
                    "system_prompt": PROMPT_TEMPLATES.get(template, PROMPT_TEMPLATES["operacion"]),
                    "question": q,
                    "answer": finalize(answer),
                    "citations": [],
                    "rag_hits": 0,
                    "db_hits": 0,
                    "db_base": db_base,
                    "db_rows_preview": [],
                    "provider": "local-deterministic",
                }
        except Exception as exc:
            logger.warning(f'operational_context_search_failed base="{db_base}" error="{exc}"')

        rag = self.rag.query(q, top_k=max(20, top_k) if source_prefix.strip() else top_k) if use_rag else {"ok": True, "count": 0, "items": []}
        if use_rag:
            trace("rag_query", tool="rag.query", detail=f"top_k={max(20, top_k) if source_prefix.strip() else top_k}")
        items = rag.get("items", []) if isinstance(rag, dict) else []
        rag_low_confidence = bool(rag.get("low_confidence", False)) if isinstance(rag, dict) else False
        rag_max_score = float(rag.get("max_score", 0.0) or 0.0) if isinstance(rag, dict) else 0.0
        items = self._filter_rag_items_by_source_prefix(items, source_prefix)
        context_blocks = [str(it.get("text", "")) for it in items if str(it.get("text", "")).strip()]
        db_rows: list[dict[str, Any]] = []
        try:
            db_ctx = self.db_tools.search_ruta_inclusion_context(base=db_base, question=q, limit=5)
            db_rows = db_ctx.get("rows", []) if isinstance(db_ctx, dict) else []
        except Exception as exc:
            logger.warning(f'db_context_search_failed base="{db_base}" error="{exc}"')

        # Hard guardrail: for afiliaciones template keep deterministic operational response,
        # avoid drifting into generic long-form LLM narratives.
        if afiliaciones_only_mode:
            contrato_fields: dict[str, str] = {}
            nomina_total_override: int | None = None
            dim = self.db_tools.afiliaciones_dimensional_snapshot(
                base=db_base,
                lote=lote,
                idtramite=idtramite,
                limit=250,
            )
            needs_nomina = any(k in qn for k in ("nomina", "nómina", "salario", "salarios"))
            if needs_nomina:
                nomina_total_override = self._get_authoritative_nomina_total(base=db_base, lote=lote)
                trace(
                    "nomina_authoritative",
                    tool="legacy.reporte_ejecutivo",
                    detail=f"nomina_total={int(nomina_total_override or 0)}",
                )
            if needs_nomina and source_prefix.strip() and self._as_int_count(dim.get("salarios_total")) <= 0:
                contrato_txt_dim, _ = self._pick_contrato_primary_source_text(
                    question=q,
                    lote=lote,
                    source_prefix=source_prefix,
                    top_k=max(20, min(top_k * 6, 80)),
                )
                contrato_fields = self._extract_xlsx_empleador_sede(contrato_txt_dim) if contrato_txt_dim else {}
            answer_dim = self._format_afiliaciones_dimension_answer(
                question=q,
                qn=qn,
                snapshot=dim,
                contrato_fields=contrato_fields,
                nomina_total_override=nomina_total_override,
            )
            answer_dim, verify = self._verify_afiliaciones_answer(
                question=q,
                answer=answer_dim,
                snapshot=dim,
            )
            trace(
                "answer_verify",
                tool="verifier.afiliaciones",
                detail=f"ok={verify.get('ok')} repaired={verify.get('repaired')}",
            )
            return {
                "ok": True,
                "template": template,
                "system_prompt": PROMPT_TEMPLATES.get(template, PROMPT_TEMPLATES["operacion"]),
                "question": q,
                "answer": finalize(answer_dim),
                "citations": self._maybe_citations(
                    [{"doc_id": "db:afiliaciones-guardrail", "source": f"{db_base}.proc_servicios+br*", "score": 1.0}]
                ),
                "rag_hits": 0,
                "db_hits": int(dim.get("empleadores") is not None) + int(dim.get("trabajadores") is not None),
                "db_base": db_base,
                "db_rows_preview": [],
                "provider": "local-deterministic",
            }

        if db_rows:
            db_context_blocks = []
            for r in db_rows[:3]:
                nombre = " ".join(
                    [
                        str(r.get("primerapellido") or "").strip(),
                        str(r.get("segundoapellido") or "").strip(),
                        str(r.get("primernombre") or "").strip(),
                        str(r.get("segundonombre") or "").strip(),
                    ]
                ).strip()
                db_context_blocks.append(
                    " | ".join(
                        [
                            f"idtramite={r.get('idtramite')}",
                            f"estado={r.get('estado') or ''}",
                            f"trabajador={nombre or 'N/A'}",
                            f"doc={r.get('numerodocumento') or ''}",
                            f"empleador={r.get('razonsocialempleador') or ''}",
                            f"nit={r.get('numerodocumentoempleador') or ''}",
                            f"adjuntos={r.get('cantiadj') or 0}",
                            f"ruta={r.get('ruta_primera') or ''}",
                        ]
                    )
                )
            context_blocks = db_context_blocks + context_blocks
        else:
            ql = q.lower().strip()
            if use_rag and rag_low_confidence and not items:
                answer_low = (
                    "No tengo evidencia suficiente en RAG para responder con confianza.\n"
                    "- Ajusta la consulta con un dato concreto (NIT, cédula, lote, idtrámite o tipo documental).\n"
                    "- Si aplica, vuelve a indexar adjuntos/OCR para enriquecer contexto."
                )
                return {
                    "ok": True,
                    "template": template,
                    "system_prompt": PROMPT_TEMPLATES.get(template, PROMPT_TEMPLATES["operacion"]),
                    "question": q,
                    "answer": finalize(answer_low),
                    "citations": self._maybe_citations(
                        [{"doc_id": "rag:low-confidence", "source": "nova.rag", "score": rag_max_score}]
                    ),
                    "rag_hits": 0,
                    "db_hits": 0,
                    "db_base": db_base,
                    "db_rows_preview": [],
                    "provider": "local-deterministic",
                }
            if ql in {"trabajador", "trabajadores", "empleado", "empleados"}:
                try:
                    recent = self.db_tools.list_recent_workers(base=db_base, limit=8)
                    recent_rows = recent.get("rows", []) if isinstance(recent, dict) else []
                    if recent_rows:
                        answer = finalize(self._format_workers_prompt(recent_rows))
                        return {
                            "ok": True,
                            "template": template,
                            "system_prompt": PROMPT_TEMPLATES.get(template, PROMPT_TEMPLATES["operacion"]),
                            "question": q,
                            "answer": answer,
                            "citations": self._maybe_citations(
                                [{"doc_id": "db:proc_servicios", "source": f"{db_base}.proc_servicios_*", "score": 1.0}]
                            ),
                            "rag_hits": 0,
                            "db_hits": len(recent_rows),
                            "db_base": db_base,
                            "db_rows_preview": [],
                            "provider": "local-deterministic",
                        }
                except Exception as exc:
                    logger.warning(f'workers_prompt_failed base="{db_base}" error="{exc}"')
            fallback = self._domain_fallback_answer(q)
            if fallback:
                return {
                    "ok": True,
                    "template": template,
                    "system_prompt": PROMPT_TEMPLATES.get(template, PROMPT_TEMPLATES["operacion"]),
                    "question": q,
                    "answer": finalize(fallback),
                    "citations": self._maybe_citations(
                        [{"doc_id": "kb:domain-fallback", "source": "local-rules", "score": 1.0}]
                    ),
                    "rag_hits": 0,
                    "db_hits": 0,
                    "db_base": db_base,
                    "db_rows_preview": [],
                    "provider": "local-deterministic",
                }
        llm_out = self.llm.generate(question=q, template=template, context_blocks=context_blocks)
        cites = [
            {"doc_id": it.get("doc_id"), "source": it.get("source"), "score": it.get("score")}
            for it in items
        ]
        if db_rows:
            cites.insert(
                0,
                {
                    "doc_id": "db:proc_servicios",
                    "source": f"{db_base}.proc_servicios_*",
                    "score": 1.0,
                },
            )
        answer = finalize(str(llm_out.get("answer", "")))
        if db_rows and str(llm_out.get("template", template)) == "operacion" and self._should_use_afiliaciones_card(question=q):
            if len(db_rows) > 1 and not any(ch.isdigit() for ch in q):
                answer = finalize(self._format_ambiguous_results(question=q, rows=db_rows))
            else:
                answer = finalize(self._format_operational_card(question=q, rows=db_rows))
        ocr_section = self._format_ocr_section(items)
        if ocr_section:
            answer = f"{answer}\n\n{ocr_section}".strip()
        return {
            "ok": True,
            "template": llm_out.get("template"),
            "system_prompt": llm_out.get("system_prompt"),
            "question": q,
            "answer": answer,
            "citations": self._maybe_citations(cites),
            "rag_hits": len(items),
            "rag_low_confidence": rag_low_confidence,
            "rag_max_score": rag_max_score,
            "db_hits": len(db_rows),
            "db_base": db_base,
            "db_rows_preview": [
                {
                    "idtramite": r.get("idtramite"),
                    "estado": r.get("estado"),
                    "trabajador": " ".join(
                        [
                            str(r.get("primerapellido") or "").strip(),
                            str(r.get("segundoapellido") or "").strip(),
                            str(r.get("primernombre") or "").strip(),
                            str(r.get("segundonombre") or "").strip(),
                        ]
                    ).strip(),
                    "documento": r.get("numerodocumento"),
                    "empleador": r.get("razonsocialempleador"),
                    "nit_empleador": r.get("numerodocumentoempleador"),
                    "adjuntos": r.get("cantiadj"),
                    "ruta_adjunto": r.get("ruta_primera"),
                }
                for r in db_rows[:3]
            ],
            "provider": llm_out.get("provider", "local-deterministic"),
        }

    @staticmethod
    def _digits_only(value: Any) -> str:
        return "".join(ch for ch in str(value or "") if ch.isdigit())

    @staticmethod
    def _as_int_count(value: Any) -> int:
        if isinstance(value, list):
            return len(value)
        if isinstance(value, tuple):
            return len(value)
        if isinstance(value, dict):
            return len(value)
        try:
            return int(value or 0)
        except Exception:
            return 0

    def _verify_afiliaciones_answer(
        self,
        *,
        question: str,
        answer: str,
        snapshot: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        qn = self._norm_text(question)
        answer_text = str(answer or "")
        answer_norm = self._norm_text(answer_text)
        employ = (snapshot.get("employers", [{}]) or [{}])[0] if isinstance(snapshot, dict) else {}
        expected_empresa = str(employ.get("razonsocialempleador") or "").strip()
        expected_nit = self._digits_only(employ.get("numerodocumentoempleador"))
        expected_sedes = self._as_int_count(snapshot.get("sedes")) if isinstance(snapshot, dict) else 0
        expected_workers = self._as_int_count(snapshot.get("trabajadores")) if isinstance(snapshot, dict) else 0
        expected_salarios = self._as_int_count(snapshot.get("salarios_total")) if isinstance(snapshot, dict) else 0
        ans_digits = self._digits_only(answer_text)

        asks_empresa = any(k in qn for k in ("empresa", "empleador", "razon social", "razón social", "nit"))
        asks_sedes = any(k in qn for k in ("sede", "sedes"))
        asks_workers = any(k in qn for k in ("trabajador", "trabajadores", "afiliado", "afiliados", "empleado", "empleados"))
        asks_nomina = any(k in qn for k in ("nomina", "nómina", "salario", "salarios", "cotizacion", "cotización"))

        failures: list[str] = []
        if asks_empresa and expected_empresa:
            if self._norm_text(expected_empresa) not in answer_norm:
                failures.append("empresa_mismatch")
        if asks_empresa and expected_nit:
            if expected_nit not in ans_digits:
                failures.append("nit_mismatch")
        if asks_sedes and expected_sedes > 0:
            if str(expected_sedes) not in answer_text:
                failures.append("sedes_mismatch")
        if asks_workers and expected_workers > 0:
            if str(expected_workers) not in answer_text:
                failures.append("trabajadores_mismatch")
        if asks_nomina and expected_salarios > 0:
            if str(expected_salarios) not in ans_digits:
                failures.append("nomina_mismatch")

        if not failures:
            return answer_text, {"ok": True, "repaired": False, "failures": []}

        repaired = self._format_afiliaciones_dimension_answer(
            question=question,
            qn=qn,
            snapshot=snapshot,
            contrato_fields={},
            normative_catalog=[],
            xlsx_sheet_names=[],
            contrato_source="",
        )
        return repaired, {"ok": False, "repaired": True, "failures": failures}

    def _get_authoritative_nomina_total(self, *, base: str, lote: str) -> int:
        lote_s = str(lote or "").strip()
        if not lote_s:
            return 0
        try:
            # Fuente de verdad: mismo cálculo que usa el reporte ejecutivo legacy.
            from app.api.v1.afiliaciones import _contract_executive_report  # type: ignore

            out = _contract_executive_report(
                lote=lote_s,
                from_db=True,
                base=str(base or "temporal").strip() or "temporal",
                excel_bytes=None,
                flatfile_926_content="",
                generate_926_if_missing=False,
            )
            engine = out.get("engine_totals") if isinstance(out, dict) else {}
            if isinstance(engine, dict):
                return self._as_int_count(engine.get("salarios"))
        except Exception:
            return 0
        return 0

    def _get_city_nomina_total(self, *, base: str, city_target: str) -> int:
        city = self._norm_text(city_target or "")
        if not city:
            return 0
        aliases_map = {
            "barranquilla": {"barranquilla", "08001", "8 001", "atlantico"},
            "bogota": {"bogota", "bogota d c", "11001", "11 001", "cundinamarca"},
            "medellin": {"medellin", "05001", "5 001", "antioquia"},
            "cali": {"cali", "76001", "76 001", "valle"},
            "cartagena": {"cartagena", "13001", "13 001", "bolivar"},
        }
        aliases = list(aliases_map.get(city, {city}))
        patterns = [f"%{a}%" for a in aliases if a]
        if not patterns:
            return 0
        try:
            rows = fetch_all_by_alias(
                base,
                """
                SELECT
                  SUM(
                    CASE
                      WHEN regexp_replace(COALESCE(w.f38::text, ''), '[^0-9]', '', 'g') <> ''
                        THEN CAST(regexp_replace(COALESCE(w.f38::text, ''), '[^0-9]', '', 'g') AS bigint)
                      ELSE 0
                    END
                  )::bigint AS total_nomina
                FROM wd w
                JOIN brempresasarp e ON e.lt = w.lt
                WHERE UPPER(COALESCE(e.tp, '')) = 'P'
                  AND EXISTS (
                    SELECT 1
                    FROM unnest(:patterns::text[]) AS p(pattern)
                    WHERE translate(lower(COALESCE(e.f15::text, '')), 'áéíóúñ', 'aeioun') LIKE p.pattern
                  )
                """,
                {"patterns": patterns},
            )
            total = int(((rows[0].get("total_nomina") if rows else 0) or 0))
            return max(0, total)
        except Exception:
            return 0

    def _finalize_chat_answer(self, *, answer: str, template: str, question: str) -> str:
        masked = self.security.mask_sensitive(str(answer or "")).strip()
        if template != "afiliaciones_arl":
            out = masked
        else:
            out = self._compact_closed_domain_answer(question=question, answer=masked)
        if self._wants_presentation_critique(question):
            block = self._presentation_critique_block()
            if block not in out:
                out = f"{out}\n\n{block}".strip()
        return out

    @staticmethod
    def _compact_closed_domain_answer(*, question: str, answer: str, max_lines: int = 24) -> str:
        text = str(answer or "").strip()
        text_norm = NovaOrchestrator._norm_text(text)
        # Para consultas documentales, no forzar bloques genéricos.
        if (
            "consulta documental nova" in text_norm
            or "documentos candidatos por busqueda ocr en vivo" in text_norm
            or "pdfs candidatos a cedula" in text_norm
        ):
            doc_lines = [ln.strip() for ln in text.splitlines() if ln and ln.strip()]
            cleaned_doc: list[str] = []
            for ln in doc_lines:
                lnn = NovaOrchestrator._norm_text(ln)
                if "abrir documento:" in lnn and "/api/v1/nova/pdf/view" in lnn:
                    continue
                if "ruta=" in lnn:
                    continue
                cleaned_doc.append(ln)
                if len(cleaned_doc) >= max(1, int(max_lines)):
                    break
            return "\n".join(cleaned_doc) if cleaned_doc else text
        if not text:
            return (
                "Resumen:\n"
                "- Sin evidencia en contexto operativo para confirmar ese dato.\n"
                "Cómo lo sé:\n"
                "- Contexto operativo (sin coincidencias).\n"
                "Siguiente paso:\n"
                "- Ejecutar OCR página 1 de adjuntos del lote y reintentar consulta puntual."
            )
        raw_lines = [ln.strip() for ln in text.splitlines() if ln and ln.strip()]
        # Preserve structured audit responses as-is.
        if re.search(r"^\s*1\)\s*resumen ejecutivo", text, flags=re.IGNORECASE | re.MULTILINE):
            return text
        if re.search(r"^\s*ficha rapida nova", text_norm, flags=re.IGNORECASE | re.MULTILINE):
            return text
        if not raw_lines:
            return (
                "Resumen:\n"
                "- Sin evidencia en contexto operativo para confirmar ese dato.\n"
                "Cómo lo sé:\n"
                "- Contexto operativo (sin coincidencias).\n"
                "Siguiente paso:\n"
                "- Ejecutar OCR página 1 de adjuntos del lote y reintentar consulta puntual."
            )

        drop_prefixes = (
            "sugerencias:",
            "puedo ayudarte",
            "consulta de afiliaciones recibida.",
            "este ocr es nuevo:",
        )
        cleaned: list[str] = []
        for ln in raw_lines:
            lnn = NovaOrchestrator._norm_text(ln)
            if any(lnn.startswith(p) for p in drop_prefixes):
                continue
            cleaned.append(ln)
            if len(cleaned) >= max(1, int(max_lines)):
                break

        if not cleaned:
            return (
                "Resumen:\n"
                "- Sin evidencia en contexto operativo para confirmar ese dato.\n"
                "Cómo lo sé:\n"
                "- Contexto operativo (sin coincidencias).\n"
                "Siguiente paso:\n"
                "- Ejecutar OCR página 1 de adjuntos del lote y reintentar consulta puntual."
            )

        qn = NovaOrchestrator._norm_text(question)
        src_lines: list[str] = []
        data_lines: list[str] = []
        action_lines: list[str] = []
        for ln in cleaned:
            lnn = NovaOrchestrator._norm_text(ln)
            if "fuente" in lnn or "source" in lnn:
                src_lines.append(f"- {ln.lstrip('- ').strip()}")
            elif "abrir documento" in lnn or "api/v1/nova/pdf/view" in lnn:
                action_lines.append(f"- {ln.lstrip('- ').strip()}")
            elif "no se encontraron" in lnn or "sin evidencia" in lnn:
                data_lines.append("- Sin evidencia en contexto operativo para confirmar ese dato.")
            elif ln.startswith("-"):
                data_lines.append(ln)
            else:
                data_lines.append(f"- {ln}")

        if not data_lines:
            data_lines = ["- Sin evidencia en contexto operativo para confirmar ese dato."]
        if not src_lines:
            src_lines = ["- Contexto operativo NOVA (BD + OCR + contrato_clean cuando aplica)."]
        if not action_lines:
            if "representante" in qn or "cedula" in qn or "identificacion" in qn:
                action_lines = ["- Validar PDF de cédula (tipo adjunto 6) y confirmar número de documento contra contrato."]
            elif "926" in qn:
                action_lines = ["- Ejecutar validaciones del lote y regenerar 926 para verificación estructural."]
            else:
                action_lines = ["- Si aplica, especificar lote/idtrámite para validar con evidencia puntual."]

        return "\n".join(
            ["Resumen:"] + data_lines[:18] + ["Cómo lo sé:"] + src_lines[:4] + ["Siguiente paso:"] + action_lines[:4]
        )

    @staticmethod
    def _wants_presentation_critique(question: str) -> bool:
        qn = NovaOrchestrator._norm_text(question)
        keys = {"presentacion", "presentación", "redaccion", "redacción", "humana", "humano", "contexto"}
        return any(k in qn for k in keys)

    @staticmethod
    def _presentation_critique_block() -> str:
        return "\n".join(
            [
                "Crítica de presentación:",
                "- Qué está bien: la respuesta prioriza datos operativos y trazabilidad.",
                "- Qué confunde: mezcla datos y acciones en un solo bloque, y dificulta escaneo rápido.",
                "- Cómo mejorarlo: separar siempre en 'Resumen', 'Cómo lo sé' y 'Siguiente paso', con máximo 3-5 bullets por sección.",
            ]
        )

    def retrieval_search(
        self,
        *,
        question: str,
        base: str = "temporal",
        lote: str = "",
        idtramite: str = "",
        source_prefix: str = "",
        top_k: int = 8,
    ) -> dict[str, Any]:
        db = self.db_tools.search_afiliaciones_context(
            base=base,
            question=question,
            lote=lote,
            idtramite=idtramite,
            limit=max(1, min(top_k, 30)),
        )
        rag = self.rag.query(question, top_k=max(20, min(top_k * 4, 80)) if source_prefix.strip() else max(1, min(top_k, 20)))
        rag_items = rag.get("items", []) if isinstance(rag, dict) else []
        rag_items = self._filter_rag_items_by_source_prefix(rag_items, source_prefix)
        rule_answer = self._build_rules_lookup_answer(question=question, items=rag_items) if self._is_rules_source_prefix(source_prefix) else ""
        return {
            "ok": True,
            "question": question,
            "base": base,
            "lote": lote,
            "idtramite": idtramite,
            "source_prefix": source_prefix,
            "db_count": int(db.get("count", 0) if isinstance(db, dict) else 0),
            "db_rows": db.get("rows", []) if isinstance(db, dict) else [],
            "rag_count": len(rag_items),
            "rag_query_rewritten": rag.get("query_rewritten", "") if isinstance(rag, dict) else "",
            "rag_max_score": float(rag.get("max_score", 0.0) or 0.0) if isinstance(rag, dict) else 0.0,
            "rag_top_exact_ratio": float(rag.get("top_exact_ratio", 0.0) or 0.0) if isinstance(rag, dict) else 0.0,
            "rag_low_confidence": bool(rag.get("low_confidence", False)) if isinstance(rag, dict) else False,
            "rag_items": rag_items,
            "rule_answer": rule_answer,
        }

    def rag_index_folder(
        self,
        *,
        folder_path: str,
        source: str = "afiliaciones_docs",
        replace_doc: bool = False,
        include_hidden: bool = False,
        max_files: int = 500,
        ocr_binary: bool = True,
    ) -> dict[str, Any]:
        root = Path(folder_path).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            return {"ok": False, "message": f"Ruta inválida: {root}"}

        text_ext = {
            ".txt",
            ".json",
            ".md",
            ".sql",
            ".log",
            ".yml",
            ".yaml",
            ".xml",
            ".html",
            ".htm",
        }
        csv_ext = {".csv"}
        xlsx_ext = {".xlsx", ".xlsm"}
        ocr_ext = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}

        docs: list[dict[str, Any]] = []
        scanned = 0
        skipped = 0
        ocr_docs = 0

        for p in sorted(root.rglob("*")):
            if scanned >= max(1, min(int(max_files), 5000)):
                break
            if not p.is_file():
                continue
            rel = p.relative_to(root).as_posix()
            if not include_hidden and any(part.startswith(".") for part in rel.split("/")):
                continue

            ext = p.suffix.lower()
            scanned += 1
            doc_id = f"{source}:{rel}"
            metadata = {"path": rel, "ext": ext, "size": p.stat().st_size}

            if ext in csv_ext:
                csv_docs = self._csv_to_semantic_docs(p, rel=rel)
                if not csv_docs:
                    skipped += 1
                    continue
                for idx, (doc_text, doc_meta) in enumerate(csv_docs, start=1):
                    md = dict(metadata)
                    md.update(doc_meta)
                    csv_doc_id = doc_id if idx == 1 else f"{doc_id}#csv={idx}"
                    docs.append(
                        {
                            "doc_id": csv_doc_id,
                            "source": f"{source}:csv",
                            "text": doc_text,
                            "metadata": md,
                        }
                    )
                continue

            if ext in text_ext:
                txt = ""
                try:
                    txt = p.read_text(encoding="utf-8", errors="ignore").strip()
                except Exception:
                    try:
                        txt = p.read_text(encoding="latin-1", errors="ignore").strip()
                    except Exception:
                        txt = ""
                if not txt:
                    skipped += 1
                    continue
                docs.append({"doc_id": doc_id, "source": source, "text": txt, "metadata": metadata})
                continue

            if ext in xlsx_ext:
                sheet_docs = self._xlsx_to_sheet_docs(p)
                if not sheet_docs:
                    skipped += 1
                    continue
                for sheet_name, sheet_text, tags in sheet_docs:
                    metadata_xlsx = dict(metadata)
                    metadata_xlsx["sheet_name"] = sheet_name
                    metadata_xlsx["sheet_tags"] = tags
                    docs.append(
                        {
                            "doc_id": f"{doc_id}#sheet={self._slug_sheet(sheet_name)}",
                            "source": f"{source}:xlsx",
                            "text": sheet_text,
                            "metadata": metadata_xlsx,
                        }
                    )
                continue

            if ocr_binary and ext in ocr_ext:
                try:
                    raw = p.read_bytes()
                except Exception:
                    skipped += 1
                    continue
                payload = {
                    "filename": p.name,
                    "mime_type": "application/pdf" if ext == ".pdf" else "image/*",
                    "file_base64": base64.b64encode(raw).decode("ascii"),
                }
                ocr = self.ocr.extract(payload)
                ocr_text = str(ocr.get("text") or "").strip()
                if not ocr_text:
                    skipped += 1
                    continue
                rag_tmpl = ocr.get("rag_ingest_template") if isinstance(ocr.get("rag_ingest_template"), dict) else {}
                doc_type = str(rag_tmpl.get("document_type") or "").strip().lower()
                struct_fields = rag_tmpl.get("structured_fields") if isinstance(rag_tmpl.get("structured_fields"), dict) else {}
                if struct_fields:
                    extra_lines: list[str] = []
                    for key, info in struct_fields.items():
                        if not isinstance(info, dict):
                            continue
                        value = info.get("value")
                        if value in (None, ""):
                            continue
                        extra_lines.append(f"{key}: {value}")
                    if extra_lines:
                        ocr_text = f"{ocr_text}\n\nCampos estructurados OCR:\n" + "\n".join(extra_lines)
                metadata_ocr = dict(metadata)
                metadata_ocr.update(
                    {
                        "ocr_engine": str(ocr.get("engine") or ""),
                        "ocr_chars": int(ocr.get("chars") or 0),
                        "ocr_pages": int(ocr.get("pages_processed") or 0),
                        "ocr_document_type": doc_type,
                    }
                )
                docs.append(
                    {
                        "doc_id": doc_id,
                        "source": f"{source}:ocr",
                        "text": ocr_text,
                        "metadata": metadata_ocr,
                    }
                )
                ocr_docs += 1
                continue

            skipped += 1

        if not docs:
            return {
                "ok": False,
                "message": "No se encontraron documentos indexables en la carpeta.",
                "folder": str(root),
                "files_scanned": scanned,
                "skipped": skipped,
            }

        rag_out = self.rag.index(docs, replace_doc=replace_doc)
        return {
            "ok": bool(rag_out.get("ok")),
            "folder": str(root),
            "files_scanned": scanned,
            "skipped": skipped,
            "documents_indexed": len(docs),
            "ocr_documents": ocr_docs,
            "rag": rag_out,
        }

    def rag_index_zip(
        self,
        *,
        zip_path: str,
        source: str = "afiliaciones_reglas_zip",
        replace_doc: bool = False,
        include_hidden: bool = False,
        max_files: int = 1500,
        ocr_binary: bool = False,
    ) -> dict[str, Any]:
        zp = Path(zip_path).expanduser().resolve()
        if not zp.exists() or not zp.is_file():
            return {"ok": False, "message": f"ZIP inválido: {zp}"}
        if zp.suffix.lower() != ".zip":
            return {"ok": False, "message": "El archivo debe ser .zip"}
        try:
            with tempfile.TemporaryDirectory(prefix="nova_rag_zip_") as td:
                target = Path(td) / "unzipped"
                target.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(zp) as zf:
                    zf.extractall(target)
                out = self.rag_index_folder(
                    folder_path=str(target),
                    source=source,
                    replace_doc=replace_doc,
                    include_hidden=include_hidden,
                    max_files=max_files,
                    ocr_binary=ocr_binary,
                )
                out["zip_path"] = str(zp)
                return out
        except Exception as exc:
            return {"ok": False, "message": f"No se pudo indexar zip: {type(exc).__name__}: {exc}"}

    @staticmethod
    def _xlsx_to_sheet_docs(path: Path) -> list[tuple[str, str, list[str]]]:
        if load_workbook is None:
            return []
        try:
            wb = load_workbook(filename=str(path), data_only=True, read_only=True)
        except Exception:
            return []
        docs: list[tuple[str, str, list[str]]] = []
        try:
            for ws in wb.worksheets:
                rows_out: list[str] = [f"# Hoja: {ws.title}"]
                for row in ws.iter_rows(values_only=True):
                    vals = [str(v).strip() for v in row if v is not None and str(v).strip()]
                    if vals:
                        rows_out.append(" | ".join(vals))
                if len(rows_out) > 1:
                    txt = "\n".join(rows_out).strip()
                    docs.append((ws.title, txt, NovaOrchestrator._classify_sheet_tags(ws.title)))
        finally:
            wb.close()
        return docs

    @staticmethod
    def _slug_sheet(name: str) -> str:
        t = (name or "").strip().lower()
        t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
        return t or "sheet"

    @staticmethod
    def _csv_to_semantic_docs(path: Path, *, rel: str, max_rows: int = 400) -> list[tuple[str, dict[str, Any]]]:
        raw = ""
        for enc in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                raw = path.read_text(encoding=enc, errors="ignore")
                if raw.strip():
                    break
            except Exception:
                continue
        if not raw.strip():
            return []

        reader = csv.reader(io.StringIO(raw))
        rows = [[str(c or "").strip() for c in row] for row in reader]
        if not rows:
            return []

        def non_empty(vals: list[str]) -> list[str]:
            return [v for v in vals if v]

        header_idx = -1
        best_score = -1.0
        for i, row in enumerate(rows[:60]):
            ne = non_empty(row)
            if len(ne) < 2:
                continue
            alpha = sum(1 for v in ne if re.search(r"[a-zA-ZáéíóúÁÉÍÓÚñÑ]", v))
            score = float(len(ne)) + (0.3 * float(alpha))
            if score > best_score:
                best_score = score
                header_idx = i

        docs: list[tuple[str, dict[str, Any]]] = []
        headers = rows[header_idx] if 0 <= header_idx < len(rows) else []
        clean_headers = [h if h else f"col_{i+1}" for i, h in enumerate(headers)]

        table_title = Path(rel).name
        summary_lines = [f"Archivo CSV: {table_title}"]
        used = 0
        for r_i, row in enumerate(rows[header_idx + 1 if header_idx >= 0 else 0 :], start=(header_idx + 2 if header_idx >= 0 else 1)):
            vals = non_empty(row)
            if len(vals) < 2:
                continue
            pairs: list[str] = []
            for i, v in enumerate(row):
                vv = str(v or "").strip()
                if not vv:
                    continue
                key = clean_headers[i] if i < len(clean_headers) else f"col_{i+1}"
                if key.strip().lower() == vv.strip().lower():
                    continue
                pairs.append(f"{key}: {vv}")
            if len(pairs) < 2:
                continue
            row_text = f"Tabla: {table_title}\nFila: {r_i}\n" + " | ".join(pairs[:28])
            docs.append(
                (
                    row_text,
                    {
                        "path": rel,
                        "row_number": r_i,
                        "record_kind": "csv_row_semantic",
                    },
                )
            )
            summary_lines.append(" - " + " | ".join(pairs[:8]))
            used += 1
            if used >= max_rows:
                break

        # Add one compact summary chunk for broad retrieval.
        if len(summary_lines) > 1:
            docs.insert(
                0,
                (
                    "\n".join(summary_lines[:160]),
                    {
                        "path": rel,
                        "record_kind": "csv_summary_semantic",
                    },
                ),
            )

        if docs:
            return docs

        flat = " ".join(str(raw).split())
        if not flat:
            return []
        return [(flat[:12000], {"path": rel, "record_kind": "csv_fallback_raw"})]

    @staticmethod
    def _classify_sheet_tags(name: str) -> list[str]:
        n = NovaOrchestrator._norm_text(name)
        tags: list[str] = []
        if any(k in n for k in ["norma", "decreto", "resolucion", "ley"]):
            tags.append("normativa")
        if any(k in n for k in ["actividad", "riesgo", "clase"]):
            tags.append("actividades")
        if any(k in n for k in ["empleador", "empresa", "contrato"]):
            tags.append("empleador")
        if any(k in n for k in ["sede", "centro"]):
            tags.append("sede")
        if any(k in n for k in ["trabajador", "dependiente", "independiente", "estudiante"]):
            tags.append("trabajadores")
        return tags

    @staticmethod
    def _filter_rag_items_by_source_prefix(items: list[dict[str, Any]], source_prefix: str) -> list[dict[str, Any]]:
        prefix = (source_prefix or "").strip().lower()
        if not prefix:
            return items
        out: list[dict[str, Any]] = []
        for it in items:
            doc_id = str(it.get("doc_id") or "").lower()
            source = str(it.get("source") or "").lower()
            md = it.get("metadata") if isinstance(it.get("metadata"), dict) else {}
            path = str(md.get("path") or "").lower()
            if prefix in doc_id or prefix in source or prefix in path:
                out.append(it)
        return out

    @staticmethod
    def _is_rules_source_prefix(source_prefix: str) -> bool:
        p = str(source_prefix or "").strip().lower()
        return "normas" in p or "reglas" in p or "afiliaciones_normas_contrato" in p

    @staticmethod
    def _extract_rules_target_terms(question: str) -> list[str]:
        q = NovaOrchestrator._norm_text(question)
        # Prefer phrase after "para ...", fallback to whole normalized question.
        m = re.search(r"\bpara\s+(.+)$", q)
        phrase = m.group(1).strip() if m else q
        stop = {
            "cual", "cuál", "es", "el", "la", "los", "las", "de", "del", "tipo", "codigo", "codigo",
            "código", "trabajador", "cotizante", "subtipo", "que", "qué", "por", "favor",
        }
        terms = [t for t in re.split(r"[^a-z0-9áéíóúñ]+", phrase) if t and len(t) >= 3 and t not in stop]
        return terms[:8]

    @staticmethod
    def _extract_code_desc_candidates(text: str) -> list[tuple[str, str]]:
        s = str(text or "").replace("\n", " ")
        out: list[tuple[str, str]] = []
        seen: set[str] = set()
        # Common CSV fragments: "21,Estudiantes de postgrado en salud"
        for m in re.finditer(r"\b(\d{1,3})\s*,\s*([A-Za-zÁÉÍÓÚÑñ][^,\n]{4,140})", s):
            code = m.group(1).strip()
            desc = m.group(2).strip(" .;:|")
            key = f"{code}|{desc.lower()}"
            if key in seen:
                continue
            seen.add(key)
            out.append((code, desc))
        return out

    @staticmethod
    def _score_rule_candidate(desc: str, target_terms: list[str]) -> float:
        if not desc:
            return 0.0
        dn = NovaOrchestrator._norm_text(desc)
        if not target_terms:
            return 0.1
        hits = sum(1 for t in target_terms if t and t in dn)
        return float(hits) / float(max(1, len(target_terms)))

    def _build_rules_lookup_answer(self, *, question: str, items: list[dict[str, Any]]) -> str:
        if not items:
            return ""
        qn = self._norm_text(question)
        if not any(k in qn for k in ["codigo", "código", "cotizante", "subtipo", "trabajador", "estudiante"]):
            return ""
        target_terms = self._extract_rules_target_terms(question)
        best: tuple[float, str, str, str] | None = None  # score, code, desc, source
        for it in items[:80]:
            txt = str(it.get("text") or "")
            md = it.get("metadata") if isinstance(it.get("metadata"), dict) else {}
            src = str(md.get("path") or it.get("doc_id") or "")
            norm_txt = self._norm_text(txt)
            # High-priority exact semantic match for common query.
            if "postgrado" in target_terms and "salud" in target_terms and "estudiantes" in target_terms:
                m_exact = re.search(r"\b(\d{1,3})\D{0,25}estudiantes\D{0,25}postgrado\D{0,25}salud\b", norm_txt)
                if m_exact:
                    c = m_exact.group(1).lstrip("0") or m_exact.group(1)
                    try:
                        nc = int(c)
                    except Exception:
                        nc = 0
                    if 1 <= nc <= 99:
                        best = (1.0, str(nc), "estudiantes de postgrado en salud", src)
                        break
            if target_terms:
                present = [t for t in target_terms if t in norm_txt]
                if present:
                    anchor = present[0]
                    idx = norm_txt.find(anchor)
                    win_l = max(0, idx - 120)
                    win_r = min(len(norm_txt), idx + 120)
                    window = norm_txt[win_l:win_r]
                    code_guess = ""
                    matches = list(re.finditer(r"(\d{1,3})\b", window))
                    for m_code in reversed(matches):
                        cand = m_code.group(1)
                        try:
                            n_cand = int(cand)
                        except Exception:
                            continue
                        if len(cand) > 2 or n_cand <= 0 or n_cand > 99:
                            continue
                        code_guess = cand
                        break
                    if code_guess and len(present) >= min(2, len(target_terms)):
                        desc_guess = " ".join(target_terms)
                        score_guess = float(len(present)) / float(max(1, len(target_terms)))
                        if best is None or score_guess > best[0]:
                            best = (score_guess, code_guess, desc_guess, src)
            for code, desc in self._extract_code_desc_candidates(txt):
                score = self._score_rule_candidate(desc, target_terms)
                if best is None or score > best[0]:
                    best = (score, code, desc, src)
        if not best or best[0] < 0.2:
            return ""
        _, code, desc, src = best
        return (
            "Resultado norma (RAG):\n"
            f"- Código: {code}\n"
            f"- Descripción: {desc}\n"
            f"- Fuente: {src}"
        )

    @staticmethod
    def _maybe_citations(citations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        # Default is hidden to avoid exposing internal KB/source labels in end-user chat UI.
        show = os.getenv("AI_SHOW_CITATIONS", "false").strip().lower() in {"1", "true", "yes", "y"}
        return citations if show else []

    @staticmethod
    def _normalize(text: str) -> str:
        t = (text or "").lower()
        repl = {
            "á": "a",
            "é": "e",
            "í": "i",
            "ó": "o",
            "ú": "u",
            "ñ": "n",
        }
        for a, b in repl.items():
            t = t.replace(a, b)
        t = re.sub(r"[^a-z0-9\s]", " ", t)
        return " ".join(t.split())

    @staticmethod
    def _should_use_afiliaciones_card(question: str) -> bool:
        q = NovaOrchestrator._normalize(question)
        if not q:
            return True
        cross_domain = (
            "funerario",
            "notificacion",
            "notificaciones",
            "reclamante",
            "prestacion",
            "prestaciones",
            "bloqueo",
            "validacion jefe",
            "validacion pagos",
            "pago",
            "pagos",
            "auditoria",
        )
        if any(k in q for k in cross_domain):
            return False
        return True

    def _domain_fallback_answer(self, question: str) -> str:
        q = self._normalize(question)
        if not q:
            return ""
        tokens = q.split()

        def has_like(target: str, threshold: float = 0.72) -> bool:
            for tk in tokens:
                if tk == target:
                    return True
                if len(tk) >= 4 and len(target) >= 4:
                    if difflib.SequenceMatcher(None, tk, target).ratio() >= threshold:
                        return True
            return False

        if (has_like("solicitud") or has_like("solicitudes")) and (
            has_like("bloqueada") or has_like("bloqueadas") or has_like("bloqueado") or has_like("bloqueados")
        ):
            return (
                "En este módulo, Bloqueo Solicitudes se maneja por estado global (Activo/Inactivo), "
                "no por un listado individual de solicitudes bloqueadas.\n"
                "Para verificarlo:\n"
                "1) Ve a Notificaciones -> Bloqueo Solicitudes.\n"
                "2) Consulta estado actual (bloqueoEstado).\n"
                "3) Si corresponde, cambia estado con usuario (bloqueoCreate) y vuelve a consultar."
            )

        if ("administracion" in q and ("permiso" in q or has_like("permisos"))) or (
            has_like("bloqueo") and (has_like("solicitud") or has_like("solicitudes"))
        ):
            return (
                "Administración/Permisos en este sistema se atiende desde Notificaciones -> pestaña Bloqueo Solicitudes. "
                "Ahí puedes consultar estado actual (activar/desactivar) y enviar el cambio con usuario."
            )

        if ((has_like("validacion") or has_like("validar")) and has_like("jefe")) or (
            has_like("jefe") and (has_like("pago") or has_like("pagos") or has_like("aprobacion"))
        ):
            return (
                "Para Validación Jefe:\n"
                "1) Abre Auxilio Funerario -> menú de validación jefe.\n"
                "2) Carga pendientes y filtra por trámite/documento.\n"
                "3) Revisa valor reconocido, estado del reclamante y soportes.\n"
                "4) Aprueba/Rechaza y confirma la operación.\n"
                "5) Recarga bandeja para validar que el caso salió de pendientes."
            )

        if (has_like("validacion") or has_like("validar")) and (has_like("pago") or has_like("pagos")):
            return (
                "Para Validación Pagos:\n"
                "1) Abre Auxilio Funerario -> menú de validación pagos.\n"
                "2) Verifica forma de pago, entidad bancaria, cuenta y valor.\n"
                "3) Confirma consistencia trámite/reclamante.\n"
                "4) Aprueba o rechaza con causal y guarda."
            )

        if "auditoria" in q or has_like("auditoria"):
            return (
                "Para auditoría: \n"
                "1) Funerarios -> pestaña Detalle Trámite -> Cargar auditoría (con trámite y límite).\n"
                "2) Notificaciones -> pestaña Auditoría -> Cargar auditoría (con solicitud_id y límite)."
            )

        if ((has_like("reclamante") and has_like("documento")) or (has_like("buscar") and has_like("reclamante"))):
            return (
                "Para buscar reclamante por documento:\n"
                "1) Ve a Funerarios -> Gestión Reclamante.\n"
                "2) Usa 'Verificar / Modificar reclamante' y completa 'Identificación para verificar'.\n"
                "3) Ejecuta 'verificaReclamante'.\n"
                "Si prefieres, también puedes cargar reclamantes por trámite desde Detalle Trámite."
            )

        if (has_like("pendiente") or has_like("pendientes")) and (has_like("pago") or has_like("pagos")):
            return (
                "Para consultar pendientes de pago:\n"
                "1) Abre Auxilio Funerario -> menú de validación pagos.\n"
                "2) Carga pendientes y filtra por trámite/documento si aplica.\n"
                "3) Revisa valor reconocido, forma de pago, banco y cuenta.\n"
                "4) Si necesitas totales, usa reporte/estadístico de bandejas con el mismo filtro."
            )

        if (has_like("tramite") or has_like("tramites")) and has_like("funerario") and (
            has_like("pendiente") or has_like("pendientes") or has_like("listar")
        ):
            return (
                "Para listar trámites funerarios pendientes:\n"
                "1) Abre Auxilio Funerario -> Bandejas.\n"
                "2) Usa Reporte Operativo y/o Estadístico para filtrar por estado pendiente.\n"
                "3) Si necesitas detalle por caso, entra a Detalle Trámite y carga por trámite.\n"
                "4) Ordena por estado/fecha para priorizar gestión."
            )

        if (has_like("usuario") or has_like("usuarios")) and (
            has_like("trabajo") or has_like("carga") or has_like("pendiente") or has_like("pendientes")
        ):
            return (
                "Para identificar usuarios con más carga operativa:\n"
                "1) Abre Auxilio Funerario -> Bandejas -> Estadístico.\n"
                "2) Ejecuta el reporte por rango de fecha y revisa volumen por analista/usuario.\n"
                "3) Complementa en Auditoría para confirmar cantidad de gestiones por usuario.\n"
                "4) Ordena de mayor a menor y usa ese top como 'usuarios con más trabajo'."
            )

        if has_like("bandeja") or has_like("pendiente"):
            return (
                "Bandejas operativas:\n"
                "- Funerarios -> pestaña Bandejas (listar bancos, reporte, estadístico).\n"
                "- Notificaciones -> pestaña Bandeja (selección, entrada, pendientes de validación, pendientes prestación, prestaciones generadas, reporte).\n"
                "Si no ves datos, valida primero trámite/solicitud y vuelve a cargar."
            )

        if has_like("documento") or has_like("documentos") or has_like("clasificacion"):
            return (
                "Para Documentos/Clasificación:\n"
                "1) Abre la pestaña Documentos.\n"
                "2) Completa trámite, id solicitud, prestación y modalidad.\n"
                "3) Carga imágenes y ejecuta guardar clasificación.\n"
                "4) Si no aparecen datos, recarga con los identificadores válidos."
            )

        return ""

    @staticmethod
    def _format_ocr_section(items: list[dict[str, Any]]) -> str:
        if not items:
            return ""
        ocr_items = [
            it for it in items
            if str(it.get("source") or "").lower().startswith("ocr")
            or str(it.get("doc_id") or "").lower().startswith("ocr")
        ]
        if not ocr_items:
            return ""
        lines = ["Hallazgos OCR relevantes:"]
        for it in ocr_items[:2]:
            txt = " ".join(str(it.get("text") or "").split()).strip()
            if len(txt) > 200:
                txt = f"{txt[:200]}..."
            lines.append(f"- {txt or 'Sin texto OCR útil.'}")
        return "\n".join(lines)

    def _format_workers_prompt(self, rows: list[dict[str, Any]]) -> str:
        lines = [
            "Tengo estos trabajadores en el lote reciente. Indícame cuál quieres abrir por nombre, documento o idtramite:",
        ]
        for r in rows[:8]:
            trabajador = " ".join(
                [
                    str(r.get("primerapellido") or "").strip(),
                    str(r.get("segundoapellido") or "").strip(),
                    str(r.get("primernombre") or "").strip(),
                    str(r.get("segundonombre") or "").strip(),
                ]
            ).strip()
            lines.append(
                f"- {trabajador or 'N/A'} | doc {r.get('numerodocumento') or ''} | trámite {r.get('idtramite') or ''} | empresa {r.get('razonsocialempleador') or ''} | estado {r.get('estado') or ''}"
            )
        lines.append("Si quieres, te muestro detalle completo de uno (estado, adjuntos y ruta documento).")
        return "\n".join(lines)

    def _format_ambiguous_results(self, *, question: str, rows: list[dict[str, Any]]) -> str:
        lines = [f"Encontré varias coincidencias para '{question}'. Elige una para ver detalle completo:"]
        for r in rows[:5]:
            trabajador = " ".join(
                [
                    str(r.get("primerapellido") or "").strip(),
                    str(r.get("segundoapellido") or "").strip(),
                    str(r.get("primernombre") or "").strip(),
                    str(r.get("segundonombre") or "").strip(),
                ]
            ).strip()
            lines.append(
                f"- idtramite {r.get('idtramite') or ''} | empresa {r.get('razonsocialempleador') or ''} | trabajador {trabajador or 'N/A'} | doc {r.get('numerodocumento') or ''} | estado {r.get('estado') or ''}"
            )
        lines.append("Puedes responder con el idtramite o el documento del trabajador.")
        return "\n".join(lines)

    def _format_operational_card(self, *, question: str, rows: list[dict[str, Any]]) -> str:
        if not rows:
            return "No encontré resultados en base para esa consulta."
        first = rows[0]
        trabajador = " ".join(
            [
                str(first.get("primerapellido") or "").strip(),
                str(first.get("segundoapellido") or "").strip(),
                str(first.get("primernombre") or "").strip(),
                str(first.get("segundonombre") or "").strip(),
            ]
        ).strip()
        lines = [
            "Resumen del caso encontrado:",
            f"- Consulta: {question}",
            f"- Id trámite: {first.get('idtramite') or ''}",
            f"- Estado: {first.get('estado') or ''}",
            f"- Fecha registro: {first.get('fecharegistro') or ''}",
            f"- Trabajador: {trabajador or 'N/A'}",
            f"- Documento trabajador: {first.get('numerodocumento') or ''}",
            f"- Empleador: {first.get('razonsocialempleador') or ''}",
            f"- NIT empleador: {first.get('numerodocumentoempleador') or ''}",
            f"- Adjuntos: {first.get('cantiadj') or 0}",
            f"- Ruta documento (referencia): {first.get('ruta_primera') or ''}",
        ]
        estado = str(first.get("estado") or "").strip().lower()
        if estado == "estudio":
            lines.append("- Siguiente paso sugerido: gestionar caso o actualizar estado desde Ruta Inclusión.")
        elif estado == "devuelto":
            lines.append("- Siguiente paso sugerido: revisar causal/subcausal y reingresar trámite.")
        elif estado == "afiliado":
            lines.append("- Siguiente paso sugerido: validar plano generado y trazabilidad final.")
        else:
            lines.append("- Siguiente paso sugerido: abrir detalle del trámite y validar trazabilidad.")
        if self._wants_presentation_critique(question):
            lines.extend(["", self._presentation_critique_block()])
        return "\n".join(lines)

    def _format_afiliaciones_card(
        self,
        *,
        question: str,
        rows: list[dict[str, Any]],
        base: str = "temporal",
        lote: str = "",
        idtramite: str = "",
    ) -> str:
        if not rows:
            return "No encontré resultados de Afiliaciones para esa consulta."
        qn = self._normalize(question)
        asks_workers = any(k in qn for k in ["trabajador", "trabajadores", "afiliado", "afiliados", "empleado", "empleados"])

        def _entity_terms(qtxt: str) -> list[str]:
            toks = [t.lower() for t in re.findall(r"[a-z0-9áéíóúñ]+", qtxt or "", flags=re.IGNORECASE)]
            toks = [t for t in toks if len(t) >= 3 and not t.isdigit()]
            drop = {
                "consulta", "buscar", "busca", "muestra", "dime", "resumen", "datos",
                "afiliacion", "afiliaciones", "empresa", "empleador", "trabajador",
                "trabajadores", "afiliado", "afiliados", "documento", "documentos",
                "cedula", "camara", "comercio", "lote", "tramite", "trámite",
            }
            return [t for t in toks if t not in drop][:4]

        def _text_match_terms(text: str, terms: list[str]) -> bool:
            if not terms:
                return True
            norm = self._norm_text(text or "")
            words = norm.split()
            for term in terms:
                if term in norm:
                    return True
                for w in words:
                    if len(w) >= 4 and len(term) >= 4 and difflib.SequenceMatcher(None, term, w).ratio() >= 0.72:
                        return True
            return False

        entity_terms = _entity_terms(qn)
        matched_rows = []
        for r in rows:
            joined = " ".join(str(v or "") for v in r.values())
            if _text_match_terms(joined, entity_terms):
                matched_rows.append(r)
        if entity_terms and not matched_rows and not lote.strip() and not idtramite.strip():
            return (
                "Sin coincidencias documentales para esa búsqueda.\n"
                f"- Consulta: {question}\n"
                "- Sugerencia: usa NIT, cédula o nombre completo (empresa o afiliado)."
            )
        rows_used = matched_rows if matched_rows else rows

        target_idtramites = {
            str(r.get("idtramite") or "").strip()
            for r in rows_used
            if str(r.get("idtramite") or "").strip()
        }
        target_lotes = {
            str(r.get("lote") or "").strip()
            for r in rows_used
            if str(r.get("lote") or "").strip()
        }

        snapshot: dict[str, Any] = {}
        try:
            snapshot = self.db_tools.afiliaciones_dimensional_snapshot(
                base=base,
                lote=lote,
                idtramite=idtramite,
                limit=5000,
            )
        except Exception:
            snapshot = {}

        empleadores_all = snapshot.get("empleadores", []) if isinstance(snapshot, dict) else []
        sedes_all = snapshot.get("sedes", []) if isinstance(snapshot, dict) else []
        trabajadores_all = snapshot.get("trabajadores", []) if isinstance(snapshot, dict) else []
        adjuntos_all = snapshot.get("adjuntos", []) if isinstance(snapshot, dict) else []

        def _scope_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
            if not items:
                return []
            scoped = items
            if target_idtramites:
                scoped = [x for x in scoped if str(x.get("idtramite") or "").strip() in target_idtramites]
            elif target_lotes:
                scoped = [x for x in scoped if str(x.get("lote") or "").strip() in target_lotes]
            if entity_terms:
                scoped_terms = []
                for x in scoped:
                    joined = " ".join(str(v or "") for v in x.values())
                    if _text_match_terms(joined, entity_terms):
                        scoped_terms.append(x)
                if scoped_terms:
                    return scoped_terms
            return scoped

        empleadores = _scope_rows(empleadores_all)
        sedes = _scope_rows(sedes_all)
        trabajadores = _scope_rows(trabajadores_all)
        adjuntos = _scope_rows(adjuntos_all)
        if not empleadores and not sedes and not trabajadores:
            # Fallback defensivo a las filas de búsqueda cuando snapshot no responde.
            empleadores = [r for r in rows_used if str(r.get("source_table") or "") == "brempresasarp" and str(r.get("tp") or "").upper() == "P"]
            sedes = [r for r in rows_used if str(r.get("source_table") or "") == "brempresasarp" and str(r.get("tp") or "").upper() == "S"]
            trabajadores = [r for r in rows_used if str(r.get("source_table") or "") in {"brafiliadosarp", "proc_servicios"}]

        lines = ["Ficha rápida NOVA", "Resultado de validación de radicación"]
        if lote.strip():
            lines.append(f"- Lote: {lote.strip()}")
        if idtramite.strip():
            lines.append(f"- Trámite: {idtramite.strip()}")
        lines.append(f"- Consulta: {question}")
        lines.append(f"- Coincidencias base: {len(rows_used)}")
        lines.append(f"- Empleadores: {len(empleadores)}")
        sedes_view = [s for s in sedes if str(s.get("tp") or "S").upper() == "S"] or sedes
        lines.append(f"- Sedes: {len(sedes_view)}")
        lines.append(f"- Trabajadores: {len(trabajadores)}")
        lines.append(f"- Adjuntos: {len(adjuntos)}")

        if empleadores:
            e = empleadores[0]
            lines.append(
                f"- Empleador: {e.get('empleador','')} | NIT: {e.get('nit_empleador','')}"
            )
        for s in sedes_view[:8]:
            lines.append(f"- Sede: {s.get('nombre','')} | Ciudad: {s.get('ciudad','')} | Tel: {s.get('telefono','')}")

        if asks_workers:
            for t in trabajadores[:8]:
                ap = " ".join([str(t.get("primerapellido") or "").strip(), str(t.get("segundoapellido") or "").strip()]).strip()
                no = " ".join([str(t.get("primernombre") or "").strip(), str(t.get("segundonombre") or "").strip()]).strip()
                lines.append(f"- Afiliado: {t.get('documento','') or t.get('documento_trabajador','')} | {(ap + ' ' + no).strip()}")
        # De-duplicate consecutive repeated lines.
        compact: list[str] = []
        for ln in lines:
            if not compact or compact[-1] != ln:
                compact.append(ln)
        return "\n".join(compact)

    @staticmethod
    def _norm_text(v: str) -> str:
        t = (v or "").strip().lower()
        repl = {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ñ": "n"}
        for a, b in repl.items():
            t = t.replace(a, b)
        t = re.sub(r"[^a-z0-9\s@.\-/#]", " ", t)
        return " ".join(t.split())

    @staticmethod
    def _norm_company_name(v: str) -> str:
        t = NovaOrchestrator._norm_text(v)
        if not t:
            return ""
        # Normaliza variantes OCR frecuentes: "S. A. S", "S A S", "S.A.S".
        t = re.sub(r"\bs[\s\.\-]*a[\s\.\-]*s\b", "sas", t)
        t = re.sub(r"\bs[\s\.\-]*a\b", "sa", t)
        t = re.sub(r"[^a-z0-9\s]", " ", t)
        return " ".join(t.split())

    @staticmethod
    def _company_equivalent(a: str, b: str) -> bool:
        na = NovaOrchestrator._norm_company_name(a)
        nb = NovaOrchestrator._norm_company_name(b)
        if not na or not nb:
            return False
        if na == nb or na in nb or nb in na:
            return True
        ignore = {"sas", "sa", "ltda", "s", "a"}
        ta = [x for x in na.split() if x not in ignore]
        tb = [x for x in nb.split() if x not in ignore]
        if not ta or not tb:
            return False
        sa = set(ta)
        sb = set(tb)
        inter = len(sa & sb)
        union = len(sa | sb)
        if inter >= 2 and union > 0 and (inter / union) >= 0.7:
            return True
        return False

    @staticmethod
    def _digits(v: str) -> str:
        return "".join(ch for ch in str(v or "") if ch.isdigit())

    @staticmethod
    def _extract_sede_slot_from_name(v: str) -> str:
        n = NovaOrchestrator._norm_text(v)
        m = re.search(r"\bsede[\s._-]*0*([1-9][0-9]*)\b", n)
        if m:
            try:
                slot = int(m.group(1))
                # Evita capturar números de contrato/lote como si fueran número de sede.
                if 1 <= slot <= 99:
                    return str(slot)
                return ""
            except Exception:
                return ""
        return ""

    @staticmethod
    def _pick_employer_row(rows: list[dict[str, Any]]) -> dict[str, Any]:
        for r in rows:
            if str(r.get("source_table") or "") == "brempresasarp" and str(r.get("tp") or "").upper() == "P":
                return r
        for r in rows:
            if str(r.get("source_table") or "") == "proc_servicios":
                return r
        return {}

    @staticmethod
    def _normalize_address(v: str) -> str:
        t = NovaOrchestrator._norm_text(v)
        if not t:
            return ""
        repl = {
            "calle": "cl",
            "carrera": "cra",
            "avenida": "av",
            "transversal": "tv",
            "diagonal": "dg",
            "numero": "num",
            " no ": " num ",
        }
        for a, b in repl.items():
            t = t.replace(a, b)
        t = t.replace("#", " ")
        t = re.sub(r"\bnum\b", "", t)
        t = re.sub(r"\s+", " ", t).strip()
        return t

    def _score_field_match(self, label: str, target_raw: str, candidate_norm: str) -> tuple[float, str]:
        target = self._norm_text(target_raw)
        if not target or not candidate_norm:
            return 0.0, "none"
        l = self._norm_text(label)

        if "nit" in l or "telefono" in l:
            td = self._digits(target_raw)
            cd = self._digits(candidate_norm)
            if not td or not cd:
                return 0.0, "none"
            if td in cd:
                return 1.0, "exact"
            if len(td) >= 7 and (td[-7:] in cd or td[-6:] in cd):
                return 0.88, "normalized"
            return difflib.SequenceMatcher(None, td, cd).ratio(), "fuzzy"

        if "ciudad" in l:
            city_aliases = {
                "barranquilla": {"barranquilla", "08001", "8 001", "atlantico"},
                "bogota": {"bogota", "bogota d c", "11001", "11 001", "cundinamarca"},
                "medellin": {"medellin", "05001", "5 001", "antioquia"},
                "cali": {"cali", "76001", "76 001", "valle"},
                "cartagena": {"cartagena", "13001", "13 001", "bolivar"},
            }
            aliases = city_aliases.get(target, {target})
            if any(a in candidate_norm for a in aliases):
                return 1.0, "normalized"
            if f" {target} " in f" {candidate_norm} ":
                return 1.0, "exact"
            return difflib.SequenceMatcher(None, target, candidate_norm).ratio(), "fuzzy"

        if "direccion" in l:
            ta = self._normalize_address(target_raw)
            ca = self._normalize_address(candidate_norm)
            if ta and ca:
                if ta in ca:
                    return 1.0, "normalized"
                toks = [t for t in ta.split() if len(t) >= 2]
                if toks:
                    hits = sum(1 for t in toks if t in ca)
                    ratio = hits / max(1, len(toks))
                    if ratio >= 0.8:
                        return 0.9, "normalized"
                    return max(ratio, difflib.SequenceMatcher(None, ta, ca).ratio()), "fuzzy"

        if target in candidate_norm:
            return 1.0, "exact"
        tokens = [t for t in target.split() if len(t) >= 3]
        if not tokens:
            return 0.0, "none"
        hits = sum(1 for t in tokens if t in candidate_norm)
        token_score = hits / max(1, len(tokens))
        fuzzy_score = difflib.SequenceMatcher(None, target, candidate_norm).ratio()
        return max(token_score, fuzzy_score), "fuzzy"

    @staticmethod
    def _extract_value_by_labels(raw_text: str, label: str) -> str:
        txt = str(raw_text or "").strip()
        if not txt:
            return ""
        parts = [p.strip() for p in txt.split("|")]
        if len(parts) < 2:
            return ""
        label_norm = NovaOrchestrator._norm_text(label)
        aliases: list[str] = []
        if "direccion" in label_norm:
            aliases = [
                "direccion de la sede principal",
                "direccion de la sede",
                "direccion",
                "direccion empleador",
            ]
        elif "ciudad" in label_norm:
            aliases = [
                "municipio distrito",
                "municipio",
                "ciudad",
                "lugar de afiliacion ciudad departamento",
            ]
        else:
            return ""

        norm_parts = [NovaOrchestrator._norm_text(p) for p in parts]
        for i, p in enumerate(norm_parts[:-1]):
            if any(a in p for a in aliases):
                for nxt in parts[i + 1 : min(i + 4, len(parts))]:
                    val = str(nxt).strip()
                    if not val:
                        continue
                    if NovaOrchestrator._norm_text(val) in {"null", "na", "n a"}:
                        continue
                    return val
        return ""

    @staticmethod
    def _source_bonus(label: str, src: str, source_tag: str) -> float:
        s = (src or "").lower()
        tag = (source_tag or "").lower()
        is_pdf_ocr = (".pdf" in s) or (":ocr" in tag) or ("ocr" in tag)
        is_flatfile = ("bkcargue" in s) or s.endswith(".txt")
        # For semantic fields we prefer OCR/PDF, for numeric fields keep neutral.
        if label in {"Ciudad", "Dirección", "Empresa"}:
            if is_pdf_ocr:
                return 0.10
            if is_flatfile:
                return -0.05
        return 0.0

    def _format_afiliaciones_ocr_comparison(
        self,
        *,
        question: str,
        af_rows: list[dict[str, Any]],
        rag_items: list[dict[str, Any]],
        lote: str = "",
        idtramite: str = "",
    ) -> str:
        lines: list[str] = []

        employer_row = self._pick_employer_row(af_rows)
        if not employer_row:
            return "Sin coincidencias de empleador: no hay registro BD para comparar."

        fields: list[tuple[str, str]] = [
            ("Empresa", str(employer_row.get("empleador") or "")),
            ("NIT", str(employer_row.get("nit_empleador") or "")),
            ("Dirección", str(employer_row.get("direccion") or "")),
            ("Teléfono", str(employer_row.get("telefono") or "")),
            ("Ciudad", str(employer_row.get("ciudad") or "")),
            ("Actividad económica", str(employer_row.get("actividad") or "")),
            ("Tipo aportante", str(employer_row.get("tipo_aportante") or "")),
        ]
        fields = [(k, v.strip()) for k, v in fields if v and v.strip()]

        rag_text_rows: list[tuple[str, str, str, str]] = []
        consulted_sources: list[str] = []
        for it in rag_items:
            text = str(it.get("text") or "")
            if not text.strip():
                continue
            md = it.get("metadata") if isinstance(it.get("metadata"), dict) else {}
            src = str(md.get("path") or it.get("doc_id") or "")
            source_tag = str(it.get("source") or "")
            rag_text_rows.append((self._norm_text(text), text, src, source_tag))
            if src and src not in consulted_sources:
                consulted_sources.append(src)

        if not rag_text_rows:
            return "\n".join(lines + ["- No hay texto OCR/documental disponible para comparar."])
        matched_lines: list[str] = []
        for label, value in fields:
            match_src = ""
            match_snippet = ""
            best_score = 0.0
            best_mode = "none"
            matched = False
            preferred_rows: list[tuple[str, str, str, str]] = []
            fallback_rows: list[tuple[str, str, str, str]] = []
            for row in rag_text_rows:
                _norm, _raw, _src, _tag = row
                s = (_src or "").lower()
                t = (_tag or "").lower()
                is_ocr_pdf = (".pdf" in s) or (":ocr" in t) or ("ocr" in t)
                if is_ocr_pdf:
                    preferred_rows.append(row)
                else:
                    fallback_rows.append(row)
            ordered_rows = preferred_rows + fallback_rows

            for norm_text, raw_text, src, source_tag in ordered_rows:
                score, mode = self._score_field_match(label, value, norm_text)
                score = max(0.0, min(1.0, score + self._source_bonus(label, src, source_tag)))
                if score > best_score:
                    best_score = score
                    best_mode = mode
                    match_src = src
                    needle = self._norm_text(value)[:20]
                    idx = norm_text.find(needle) if needle else -1
                    if idx >= 0:
                        match_snippet = raw_text[max(0, idx - 60): idx + 180]
                    else:
                        match_snippet = raw_text[:160]
                # Structured label extraction from contrato clean/txt sources.
                src_low = src.lower()
                if label in {"Dirección", "Ciudad"} and "contrato_" in src_low and src_low.endswith(".txt"):
                    extracted = self._extract_value_by_labels(raw_text, label)
                    if extracted:
                        score_tag, _ = self._score_field_match(label, value, self._norm_text(extracted))
                        score_tag = max(score_tag, 0.85)
                        if score_tag > best_score:
                            best_score = min(1.0, score_tag)
                            best_mode = "tag"
                            match_src = src
                            match_snippet = extracted
            threshold = 0.72
            if label in {"NIT", "Teléfono", "Ciudad"}:
                threshold = 0.84
            # For semantic fields require stronger OCR/PDF evidence before accepting fallback TXT.
            src_low = match_src.lower()
            if label in {"Empresa", "Dirección", "Ciudad"} and ".pdf" not in src_low and "ocr" not in src_low:
                if best_score < 0.98:
                    best_score = min(best_score, 0.69)
            matched = best_score >= threshold
            if matched:
                tag = "MATCH"
                if best_mode == "normalized":
                    tag = "MATCH_NORMALIZADO"
                elif best_mode == "tag":
                    tag = "MATCH_ETIQUETA"
                matched_lines.append(f"- {label}: {tag}({round(best_score,2)}) | {value}")

        if matched_lines:
            human_lines: list[str] = []
            for ln in matched_lines:
                # Input format: "- Campo: TAG(score) | valor"
                try:
                    left, value = ln.split("|", 1)
                    field = left.split(":", 1)[0].replace("-", "").strip()
                    human_lines.append(f"- {field}: {value.strip()}")
                except Exception:
                    human_lines.append(ln)
            lines.append("Coincidencias encontradas para el empleador:")
            lines.extend(human_lines)
        else:
            lines.append("No encontré coincidencias confiables del empleador entre BD/XLSX y OCR.")
        return "\n".join(lines)

    @staticmethod
    def _select_rag_items_for_ocr_compare(items: list[dict[str, Any]], max_items: int = 40) -> list[dict[str, Any]]:
        if not items:
            return []
        preferred: list[dict[str, Any]] = []
        secondary: list[dict[str, Any]] = []
        fallback: list[dict[str, Any]] = []
        for it in items:
            md = it.get("metadata") if isinstance(it.get("metadata"), dict) else {}
            src = str(md.get("path") or it.get("doc_id") or "").lower()
            source_tag = str(it.get("source") or "").lower()
            ext = str(md.get("ext") or "").lower()
            # Drop known noisy sources for employer OCR comparison.
            if "express_arl/" in src or src.endswith(".csv") or "casos " in src:
                continue
            is_pdf_ocr = (ext == ".pdf") or (":ocr" in source_tag) or ("ocr" in source_tag)
            is_flatfile = "bkcargue" in src
            is_contract_txt = ("contrato_" in src and src.endswith("_clean.txt")) or ("sede01-trabajadores_" in src and src.endswith("_clean.txt"))
            if is_pdf_ocr:
                preferred.append(it)
            elif is_contract_txt:
                secondary.append(it)
            elif is_flatfile:
                fallback.append(it)
            else:
                secondary.append(it)
        # Strict mode for OCR comparison:
        # 1) prefer PDF/OCR and contract-clean sources
        # 2) only fallback to flatfile (BkCargue) if nothing else is available
        if preferred or secondary:
            ordered = preferred + secondary
        else:
            ordered = fallback
        return ordered[: max(1, min(max_items, 120))]

    @staticmethod
    def _resolve_local_pdf_path(raw_path: str) -> Path | None:
        raw = str(raw_path or "").strip()
        if not raw:
            return None
        normalized = raw.replace("\\", "/")
        candidates: list[Path] = []
        direct = Path(normalized)
        if direct.exists() and direct.is_file():
            return direct

        # UNC style: //10.17.../imagenes4/img11/YYYYMMDD/Afa/00616892/12881223.pdf
        m = re.search(r"/Afa/([^/]+)/([^/]+\.pdf)$", normalized, flags=re.IGNORECASE)
        if m:
            lote_folder = m.group(1)
            filename = m.group(2)
            candidates.append(Path("/host_downloads") / lote_folder / filename)
            candidates.append(Path("/host_downloads") / "00616892" / filename)
            candidates.append(Path("/host_downloads") / filename)
        else:
            filename = Path(normalized).name
            if filename:
                candidates.append(Path("/host_downloads") / filename)

        for c in candidates:
            if c.exists() and c.is_file():
                return c

        # Fallback: expensive search by filename under mounted downloads.
        filename = Path(normalized).name
        if filename:
            try:
                root = Path("/host_downloads")
                if root.exists():
                    for p in root.rglob(filename):
                        if p.is_file():
                            return p
            except Exception:
                return None
        return None

    def _run_live_ocr_for_lote(
        self,
        *,
        base: str,
        lote: str = "",
        idtramite: str = "",
        max_files: int = 30,
    ) -> dict[str, Any]:
        snap = self.db_tools.afiliaciones_dimensional_snapshot(base=base, lote=lote, idtramite=idtramite, limit=500)
        adj = snap.get("adjuntos", []) if isinstance(snap, dict) else []
        rows: list[dict[str, Any]] = []
        ok_count = 0
        processed = 0
        for item in adj:
            if processed >= max(1, min(int(max_files), 120)):
                break
            ruta = str(item.get("rutaadjunto") or "").strip()
            if not ruta:
                continue
            local = self._resolve_local_pdf_path(ruta)
            if not local:
                rows.append(
                    {
                        "idtramite": str(item.get("idtramite") or ""),
                        "tipo_adjunto": str(item.get("tipo_adjunto") or ""),
                        "source_path": ruta,
                        "ok": False,
                        "error": "no_local_path",
                    }
                )
                continue
            processed += 1
            try:
                raw = local.read_bytes()
                payload = {
                    "filename": local.name,
                    "mime_type": "application/pdf",
                    "file_base64": base64.b64encode(raw).decode("ascii"),
                }
                ocr_out = self.ocr.extract(payload)
                text = str(ocr_out.get("text") or "").strip()
                ok = bool(ocr_out.get("ok")) and bool(text)
                if ok:
                    ok_count += 1
                pages = ocr_out.get("pages", []) if isinstance(ocr_out, dict) else []
                source_modes = {
                    str(p.get("source_mode") or "").strip()
                    for p in pages
                    if isinstance(p, dict) and str(p.get("source_mode") or "").strip()
                }
                if "ocr_image_page" in source_modes:
                    ocr_mode = "pdf_scanned_image"
                elif "pdf_text_layer" in source_modes:
                    ocr_mode = "pdf_text_layer"
                else:
                    ocr_mode = "unknown"
                rows.append(
                    {
                        "idtramite": str(item.get("idtramite") or ""),
                        "tipo_adjunto": str(item.get("tipo_adjunto") or ""),
                        "source_path": ruta,
                        "local_path": str(local),
                        "filename": local.name,
                        "ok": ok,
                        "chars": int(ocr_out.get("chars") or 0),
                        "ocr_text": text,
                        "preview": text[:220],
                        "engine": str(ocr_out.get("engine") or ""),
                        "ocr_mode": ocr_mode,
                        "error": "" if ok else str(ocr_out.get("message") or "ocr_failed"),
                    }
                )
            except Exception as exc:
                rows.append(
                    {
                        "idtramite": str(item.get("idtramite") or ""),
                        "tipo_adjunto": str(item.get("tipo_adjunto") or ""),
                        "source_path": ruta,
                        "local_path": str(local),
                        "filename": local.name,
                        "ok": False,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
        return {
            "ok": True,
            "base": base,
            "lote": lote,
            "idtramite": idtramite,
            "adjuntos_total": len(adj),
            "processed": processed,
            "ok_count": ok_count,
            "rows": rows,
        }

    def _run_live_ocr_for_adjuntos(
        self,
        *,
        adjuntos: list[dict[str, Any]],
        max_files: int = 3,
    ) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        ok_count = 0
        processed = 0
        for item in (adjuntos or [])[: max(1, min(int(max_files), 12))]:
            ruta = str(item.get("rutaadjunto") or "").strip()
            if not ruta:
                continue
            local = self._resolve_local_pdf_path(ruta)
            if not local:
                rows.append(
                    {
                        "filename": "",
                        "tipo_adjunto": str(item.get("tipo_adjunto") or ""),
                        "ok": False,
                        "error": "no_local_path",
                    }
                )
                continue
            processed += 1
            try:
                raw = local.read_bytes()
                payload = {
                    "filename": local.name,
                    "mime_type": "application/pdf",
                    "file_base64": base64.b64encode(raw).decode("ascii"),
                    "max_pages": 1,
                }
                ocr_out = self.ocr.extract(payload)
                text = str(ocr_out.get("text") or "").strip()
                ok = bool(ocr_out.get("ok")) and bool(text)
                if ok:
                    ok_count += 1
                rows.append(
                    {
                        "filename": local.name,
                        "tipo_adjunto": str(item.get("tipo_adjunto") or ""),
                        "ok": ok,
                        "chars": int(ocr_out.get("chars") or 0),
                        "ocr_text": text,
                        "error": "" if ok else str(ocr_out.get("message") or "ocr_failed"),
                    }
                )
            except Exception as exc:
                rows.append(
                    {
                        "filename": local.name,
                        "tipo_adjunto": str(item.get("tipo_adjunto") or ""),
                        "ok": False,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
        return {"ok": True, "processed": processed, "ok_count": ok_count, "rows": rows}

    def find_pdf_candidates(
        self,
        *,
        question: str,
        base: str,
        lote: str = "",
        idtramite: str = "",
        max_files: int = 60,
        allow_live_fallback: bool = False,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        cache = self._load_precheck_cache(base=base, lote=lote, idtramite=idtramite)
        cached_docs = cache.get("docs_ocr", []) if isinstance(cache, dict) else []
        if isinstance(cached_docs, list) and cached_docs:
            for d in cached_docs[: max(1, min(int(max_files), 80))]:
                rows.append(
                    {
                        "filename": str(d.get("filename") or ""),
                        "tipo_adjunto": str(d.get("tipo") if d.get("tipo") is not None else d.get("tipo_adjunto") or ""),
                        "ok": bool(d.get("ok")),
                        "chars": int(d.get("chars") or 0),
                        "ocr_text": str(d.get("text") or d.get("ocr_text") or ""),
                    }
                )
        else:
            # Fallback en vivo con tope bajo para no bloquear UI.
            if allow_live_fallback:
                live_limit = max(1, min(int(max_files), 10))
                live = self._run_live_ocr_for_lote(base=base, lote=lote, idtramite=idtramite, max_files=live_limit)
                rows = live.get("rows", []) if isinstance(live, dict) else []
            else:
                rows = []
        qn = self._norm_text(question)
        q_tokens = [t for t in qn.split() if len(t) >= 4 and t not in {"pdf", "lote", "tramite", "trámite", "archivo", "adjunto", "documento"}]
        if not q_tokens:
            q_tokens = ["cedula", "identificacion", "identificacion personal", "cedula de ciudadania"]
        out: list[dict[str, Any]] = []
        for r in rows:
            if not bool(r.get("ok")):
                continue
            text = str(r.get("ocr_text") or "")
            nt = self._norm_text(text)
            score = 0
            for tk in q_tokens:
                if tk in nt:
                    score += 2
                else:
                    # small fuzzy fallback for typos in query
                    for w in nt.split():
                        if len(w) >= 4 and difflib.SequenceMatcher(None, tk, w).ratio() >= 0.84:
                            score += 1
                            break
            if str(r.get("tipo_adjunto") or "").strip() == "6":
                score += 1
            if score <= 0:
                continue
            snippet = text[:180]
            for tk in q_tokens:
                idx = nt.find(tk)
                if idx >= 0:
                    snippet = text[max(0, idx - 40): idx + 160]
                    break
            out.append(
                {
                    "filename": str(r.get("filename") or ""),
                    "tipo_adjunto": str(r.get("tipo_adjunto") or ""),
                    "chars": int(r.get("chars") or 0),
                    "score": int(score),
                    "evidence": " ".join(snippet.split()),
                }
            )
        out.sort(key=lambda x: (x.get("score", 0), x.get("chars", 0)), reverse=True)
        if out:
            return out[:12]

        # Fallback sin OCR: si no hubo texto OCR util, intentar cruce por BD operativa
        # y proponer documentos del mismo lote para que el usuario no quede sin salida.
        try:
            snap = self.db_tools.afiliaciones_dimensional_snapshot(base=base, lote=lote, idtramite=idtramite, limit=500)
            trabajadores = snap.get("trabajadores", []) if isinstance(snap, dict) else []
            empleadores = snap.get("empleadores", []) if isinstance(snap, dict) else []
            adjuntos = snap.get("adjuntos", []) if isinstance(snap, dict) else []
            af_ctx = self.db_tools.search_afiliaciones_context(
                base=base,
                question=question,
                lote=lote,
                idtramite=idtramite,
                limit=5,
            )
            af_rows = af_ctx.get("rows", []) if isinstance(af_ctx, dict) else []

            q_words = [w for w in self._norm_text(question).split() if len(w) >= 4]
            # Nombre candidato (afiliado/empresa) detectado en BD con tolerancia a typo leve.
            matched_label = ""
            for t in trabajadores[:800]:
                parts = [
                    str(t.get("primerapellido") or "").strip(),
                    str(t.get("segundoapellido") or "").strip(),
                    str(t.get("primernombre") or "").strip(),
                    str(t.get("segundonombre") or "").strip(),
                    str(t.get("nombre") or "").strip(),
                    str(t.get("documento") or t.get("documento_trabajador") or "").strip(),
                ]
                full = " ".join([p for p in parts if p]).strip()
                nf = self._norm_text(full)
                if not nf:
                    continue
                for qw in q_words:
                    if qw in nf:
                        matched_label = full
                        break
                    for ww in nf.split():
                        if len(ww) >= 4 and difflib.SequenceMatcher(None, qw, ww).ratio() >= 0.78:
                            matched_label = full
                            break
                    if matched_label:
                        break
                if matched_label:
                    break

            if not matched_label:
                for rr in af_rows[:3]:
                    full_ctx = " ".join(
                        [
                            str(rr.get("primerapellido") or "").strip(),
                            str(rr.get("segundoapellido") or "").strip(),
                            str(rr.get("primernombre") or "").strip(),
                            str(rr.get("segundonombre") or "").strip(),
                            str(rr.get("documento_trabajador") or rr.get("numerodocumento") or "").strip(),
                        ]
                    ).strip()
                    if not full_ctx:
                        continue
                    nctx = self._norm_text(full_ctx)
                    if not nctx:
                        continue
                    ok_match = False
                    for qw in q_words:
                        if qw in nctx:
                            ok_match = True
                            break
                        for ww in nctx.split():
                            if len(ww) >= 4 and difflib.SequenceMatcher(None, qw, ww).ratio() >= 0.78:
                                ok_match = True
                                break
                        if ok_match:
                            break
                    if ok_match:
                        matched_label = full_ctx
                        break

            if not matched_label:
                for e in empleadores[:20]:
                    efull = " ".join(
                        [
                            str(e.get("empleador") or "").strip(),
                            str(e.get("nit_empleador") or "").strip(),
                        ]
                    ).strip()
                    nef = self._norm_text(efull)
                    if not nef:
                        continue
                    for qw in q_words:
                        if qw in nef:
                            matched_label = efull
                            break
                        for ww in nef.split():
                            if len(ww) >= 4 and difflib.SequenceMatcher(None, qw, ww).ratio() >= 0.78:
                                matched_label = efull
                                break
                        if matched_label:
                            break
                    if matched_label:
                        break

            if matched_label and isinstance(adjuntos, list) and adjuntos:
                prefer_types = {"6", "5", "0", "1", "8"}
                built: list[dict[str, Any]] = []
                seen_files: set[str] = set()
                for a in adjuntos:
                    ruta = str(a.get("rutaadjunto") or "").strip()
                    if not ruta:
                        continue
                    fname = Path(ruta.replace("\\", "/")).name
                    if not fname:
                        continue
                    fkey = fname.lower()
                    if fkey in seen_files:
                        continue
                    seen_files.add(fkey)
                    tipo = str(a.get("tipo_adjunto") or "").strip()
                    score = 2 if tipo in prefer_types else 1
                    built.append(
                        {
                            "filename": fname,
                            "tipo_adjunto": tipo,
                            "chars": 0,
                            "score": score,
                            "evidence": (
                                f"Coincidencia en base operativa: {matched_label}"
                                if matched_label
                                else "Coincidencia detectada en contexto BD del lote/trámite"
                            ),
                        }
                    )
                    if len(built) >= 12:
                        break
                built.sort(key=lambda x: (x.get("score", 0), x.get("filename", "")), reverse=True)
                if built:
                    return built[:12]

            # Si no hay contexto lote/trámite activo, intentar resolverlo por nombre/doc
            # y repetir snapshot para devolver documentos útiles.
            if not matched_label and (not str(lote or "").strip() and not str(idtramite or "").strip()):
                inferred_idt = ""
                inferred_lote = ""
                if isinstance(af_rows, list) and af_rows:
                    rr0 = af_rows[0] if isinstance(af_rows[0], dict) else {}
                    inferred_idt = str(rr0.get("idtramite") or "").strip()
                    inferred_lote = str(rr0.get("lote") or "").strip()
                if not inferred_idt and q_words:
                    kw = str(q_words[0] or "").strip()
                    if kw:
                        try:
                            q_emp = self.db_tools.query_readonly(
                                base=base,
                                sql=(
                                    "SELECT t.idtramite::text AS idtramite, COALESCE(t.lote::text,'') AS lote, "
                                    "COALESCE(e.razonsocialempleador,'') AS empleador "
                                    "FROM proc_servicios_obtenertramites t "
                                    "JOIN proc_servicios_obtenerempleadortramite e ON e.idtramite = t.idtramite "
                                    "WHERE LOWER(COALESCE(e.razonsocialempleador,'')) LIKE LOWER(:kw) "
                                    "ORDER BY t.idtramite DESC LIMIT 1"
                                ),
                                params={"kw": f"%{kw}%"},
                            )
                            r_emp = q_emp.get("rows", []) if isinstance(q_emp, dict) else []
                            if r_emp:
                                r0 = r_emp[0] if isinstance(r_emp[0], dict) else {}
                                inferred_idt = str(r0.get("idtramite") or "").strip()
                                inferred_lote = str(r0.get("lote") or "").strip()
                                if not matched_label:
                                    matched_label = str(r0.get("empleador") or "").strip()
                        except Exception:
                            pass
                if inferred_idt or inferred_lote:
                    snap2 = self.db_tools.afiliaciones_dimensional_snapshot(
                        base=base,
                        lote=inferred_lote,
                        idtramite=inferred_idt,
                        limit=500,
                    )
                    empleadores2 = snap2.get("empleadores", []) if isinstance(snap2, dict) else []
                    adjuntos2 = snap2.get("adjuntos", []) if isinstance(snap2, dict) else []
                    for e in empleadores2[:20]:
                        efull2 = " ".join(
                            [
                                str(e.get("empleador") or "").strip(),
                                str(e.get("nit_empleador") or "").strip(),
                            ]
                        ).strip()
                        nef2 = self._norm_text(efull2)
                        if not nef2:
                            continue
                        for qw in q_words:
                            if qw in nef2:
                                matched_label = efull2
                                break
                            for ww in nef2.split():
                                if len(ww) >= 4 and difflib.SequenceMatcher(None, qw, ww).ratio() >= 0.78:
                                    matched_label = efull2
                                    break
                            if matched_label:
                                break
                        if matched_label:
                            break
                    if matched_label and isinstance(adjuntos2, list) and adjuntos2:
                        prefer_types = {"6", "5", "0", "1", "8"}
                        built2: list[dict[str, Any]] = []
                        seen2: set[str] = set()
                        for a in adjuntos2:
                            ruta = str(a.get("rutaadjunto") or "").strip()
                            if not ruta:
                                continue
                            fname = Path(ruta.replace("\\", "/")).name
                            if not fname:
                                continue
                            fk = fname.lower()
                            if fk in seen2:
                                continue
                            seen2.add(fk)
                            tipo = str(a.get("tipo_adjunto") or "").strip()
                            built2.append(
                                {
                                    "filename": fname,
                                    "tipo_adjunto": tipo,
                                    "chars": 0,
                                    "score": 2 if tipo in prefer_types else 1,
                                    "evidence": f"Coincidencia en base operativa: {matched_label}",
                                }
                            )
                            if len(built2) >= 12:
                                break
                        built2.sort(key=lambda x: (x.get("score", 0), x.get("filename", "")), reverse=True)
                        if built2:
                            return built2[:12]
        except Exception:
            pass
        return []

    def resolve_pdf_for_view(
        self,
        *,
        base: str,
        lote: str = "",
        idtramite: str = "",
        filename: str,
    ) -> Path | None:
        target = Path(str(filename or "")).name
        if not target.lower().endswith(".pdf"):
            return None
        target_page: int | None = None
        candidate_names: list[str] = [target]
        m_page = re.match(r"^(.+?)__p\d+\.pdf$", target, flags=re.IGNORECASE)
        if m_page:
            try:
                target_page = int(target.rsplit("__p", 1)[1].split(".", 1)[0])
            except Exception:
                target_page = None
            parent_name = f"{m_page.group(1)}.pdf"
            if parent_name.lower() != target.lower():
                candidate_names.append(parent_name)
        candidate_names_lc = {n.lower() for n in candidate_names}
        snap = self.db_tools.afiliaciones_dimensional_snapshot(base=base, lote=lote, idtramite=idtramite, limit=500)
        adj = snap.get("adjuntos", []) if isinstance(snap, dict) else []
        for item in adj:
            raw = str(item.get("rutaadjunto") or "").strip()
            if not raw:
                continue
            raw_name = Path(raw.replace("\\", "/")).name
            if raw_name.lower() not in candidate_names_lc:
                continue
            local = self._resolve_local_pdf_path(raw)
            if local and local.exists() and local.is_file():
                try:
                    resolved = local.resolve()
                    root = Path("/host_downloads").resolve()
                    if str(resolved).startswith(str(root)):
                        if target_page and str(resolved.name).lower() != target.lower():
                            page_pdf = self._extract_single_pdf_page_cached(resolved, target_page)
                            if page_pdf and page_pdf.exists():
                                return page_pdf
                        return resolved
                except Exception:
                    continue
        # fallback: search by filename under mounted downloads
        try:
            root = Path("/host_downloads")
            for cname in candidate_names:
                for p in root.rglob(cname):
                    if p.is_file():
                        resolved = p.resolve()
                        if str(resolved).startswith(str(root.resolve())):
                            if target_page and str(resolved.name).lower() != target.lower():
                                page_pdf = self._extract_single_pdf_page_cached(resolved, target_page)
                                if page_pdf and page_pdf.exists():
                                    return page_pdf
                            return resolved
        except Exception:
            return None
        return None

    @staticmethod
    def _extract_single_pdf_page_cached(pdf_path: Path, page_number_1_based: int) -> Path | None:
        if page_number_1_based <= 0:
            return None
        try:
            import fitz  # type: ignore
        except Exception:
            return None
        try:
            stat = pdf_path.stat()
            key = hashlib.sha1(
                f"{str(pdf_path)}|{int(stat.st_mtime)}|{int(stat.st_size)}|{int(page_number_1_based)}".encode("utf-8")
            ).hexdigest()[:20]
            out_dir = Path("/tmp/nova_pdf_view_pages")
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"{pdf_path.stem}__p{page_number_1_based:03d}_{key}.pdf"
            if out_path.exists() and out_path.is_file():
                return out_path

            src = fitz.open(str(pdf_path))
            total = len(src)
            idx = page_number_1_based - 1
            if idx < 0 or idx >= total:
                src.close()
                return None
            one = fitz.open()
            one.insert_pdf(src, from_page=idx, to_page=idx)
            src.close()
            one.save(str(out_path))
            one.close()
            if out_path.exists() and out_path.is_file():
                return out_path
        except Exception:
            return None
        return None

    def _pick_contrato_primary_source_text(
        self,
        *,
        question: str,
        lote: str = "",
        source_prefix: str = "",
        top_k: int = 40,
    ) -> tuple[str, str]:
        strict_scope = bool(str(lote or "").strip() or str(source_prefix or "").strip())
        # 1) Primary source: original XLSX file (contrato*.xlsx) from mounted downloads.
        xlsx_text, xlsx_src = self._read_primary_contract_xlsx(lote=lote, source_prefix=source_prefix)
        if xlsx_text:
            return xlsx_text, xlsx_src
        if not strict_scope:
            return "", ""
        # 2) Fallback: RAG contrato_* documents.
        q = f"{question} contrato clean empleador sede xlsx"
        rag = self.rag.query(q, top_k=max(10, min(int(top_k), 120)))
        items = rag.get("items", []) if isinstance(rag, dict) else []
        items = self._filter_rag_items_by_source_prefix(items, source_prefix)
        best_txt = ""
        best_rank = -1
        best_src = ""
        for it in items:
            txt = str(it.get("text") or "").strip()
            if not txt:
                continue
            md = it.get("metadata") if isinstance(it.get("metadata"), dict) else {}
            src = str(md.get("path") or it.get("doc_id") or "").lower()
            rank = 0
            if "contrato_" in src and "_clean.txt" in src:
                rank = 4
            elif "contrato_" in src and src.endswith(".txt"):
                rank = 3
            elif "contrato_" in src and src.endswith(".json"):
                rank = 2
            else:
                continue
            if rank > best_rank:
                best_rank = rank
                best_txt = txt
                best_src = src
        if best_txt:
            return best_txt, f"rag:{best_src}"
        # Fallback: read latest contrato_*_clean.txt from mounted downloads pipeline.
        try:
            root = Path("/host_downloads/afa_pipeline")
            if root.exists() and root.is_dir():
                candidates = sorted(root.glob("contrato_*_clean.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
                for p in candidates[:5]:
                    txt = p.read_text(encoding="utf-8", errors="ignore").strip()
                    if txt:
                        return txt, str(p)
        except Exception:
            return "", ""
        return best_txt, best_src

    def _read_primary_contract_xlsx(self, *, lote: str = "", source_prefix: str = "") -> tuple[str, str]:
        root = Path("/host_downloads")
        if not root.exists() or not root.is_dir():
            return "", ""
        lote_s = str(lote or "").strip()
        prefix = (source_prefix or "").strip().lower()
        strict_scope = bool(lote_s or prefix)
        candidates: list[Path] = []
        if not strict_scope:
            exact = root / "contrato.xlsx"
            if exact.exists() and exact.is_file():
                candidates.append(exact)
        # Prefer XLSX within source_prefix path if available.
        if prefix:
            for p in root.rglob("*.xlsx"):
                pp = str(p).lower()
                if prefix in pp and "contrato" in p.name.lower():
                    candidates.append(p)
        if lote_s:
            for p in root.rglob("*.xlsx"):
                pp = str(p).lower()
                if lote_s in pp and "contrato" in p.name.lower():
                    candidates.append(p)
        # Generic fallback for contrato*.xlsx in downloads.
        if not strict_scope:
            for p in root.rglob("*contrato*.xlsx"):
                candidates.append(p)
        # De-duplicate and prioritize latest.
        uniq: dict[str, Path] = {}
        for c in candidates:
            uniq[str(c)] = c
        ordered = sorted(uniq.values(), key=lambda p: p.stat().st_mtime, reverse=True)
        if strict_scope and not ordered:
            return "", ""
        for p in ordered[:10]:
            sheet_docs = self._xlsx_to_sheet_docs(p)
            if not sheet_docs:
                continue
            # Include all sheets to preserve employer/representative sections even if the sheet
            # title does not map cleanly to tags.
            pieces: list[str] = [t for _, t, _ in sheet_docs]
            text = "\n\n".join(pieces).strip()
            if text:
                return text, str(p)
        return "", ""

    def _extract_xlsx_empleador_sede(self, contrato_text: str) -> dict[str, str]:
        text = str(contrato_text or "")
        if not text.strip():
            return {}
        parts = [p.strip() for p in text.split("|")]
        norm_parts = [self._norm_text(p) for p in parts]

        def by_label(*labels: str) -> str:
            aliases = [self._norm_text(l) for l in labels if l]
            for i, lbl in enumerate(norm_parts[:-1]):
                if any(a in lbl for a in aliases):
                    for j in range(i + 1, min(i + 6, len(parts))):
                        val = str(parts[j] or "").strip()
                        if not val:
                            continue
                        nv = self._norm_text(val)
                        if nv in {"null", "na", "n a"}:
                            continue
                        if "tipo de documento" in nv and len(val) <= 3:
                            continue
                        return val
            return ""

        rep_name = ""
        for i, lbl in enumerate(norm_parts):
            if "apellidos y nombres del representante legal" in lbl:
                vals: list[str] = []
                for j in range(i + 1, min(i + 8, len(parts))):
                    v = str(parts[j] or "").strip()
                    if not v:
                        continue
                    nv = self._norm_text(v)
                    if nv in {"null", "na", "n a"}:
                        continue
                    if any(k in nv for k in ["tipo de documento", "numero de documento", "correo electronico"]):
                        break
                    vals.append(v)
                rep_name = " ".join(vals).strip()
                break
        if not rep_name:
            m_rep = re.search(
                r"representante legal[^\n|]*[|\n]\s*([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ\s]{5,80})",
                text,
                flags=re.IGNORECASE,
            )
            if m_rep:
                rep_name = " ".join(str(m_rep.group(1) or "").split()).strip()

        tdoc_rep = by_label("5. Tipo de documento")
        doc_rep = by_label("6. Número de documento")
        if not tdoc_rep:
            m_tdoc = re.search(r"5\.\s*Tipo de documento[^\n|]*[|\n]\s*([A-Z]{2,3})", text, flags=re.IGNORECASE)
            if m_tdoc:
                tdoc_rep = str(m_tdoc.group(1) or "").strip().upper()
        if not doc_rep:
            m_doc = re.search(r"6\.\s*Número de documento[^\n|]*[|\n]\s*([0-9]{5,15})", text, flags=re.IGNORECASE)
            if m_doc:
                doc_rep = str(m_doc.group(1) or "").strip()
        nomina_total = ""
        m_nom = re.search(
            r"(?:monto\s+total\s+de\s+la\s+cotizaci[oó]n|valor\s+total\s+de\s+n[oó]mina)[^\n|]*[|\n]\s*([0-9][0-9\.\,\s]{3,})",
            text,
            flags=re.IGNORECASE,
        )
        if m_nom:
            nomina_total = "".join(ch for ch in str(m_nom.group(1) or "") if ch.isdigit())

        sede_name = ""
        for i in range(0, max(0, len(parts) - 3)):
            a = self._norm_text(parts[i])
            b = str(parts[i + 1] or "").strip()
            c = str(parts[i + 2] or "").strip()
            if a == "null" and b.isdigit() and c:
                nc = self._norm_text(c)
                if nc not in {"null", "na", "n a"} and "correo" not in nc:
                    sede_name = c
                    break

        return {
            "empresa": by_label("1. Apellidos y nombres o razón social"),
            "nit": by_label("3. Número de documento o NIT"),
            "direccion_empleador": by_label("Dirección de la sede principal", "direccion empleador", "direccion"),
            "telefono_empleador": by_label("Teléfono fijo/celular", "telefono fijo celular"),
            "ciudad_empleador": by_label("Municipio/Distrito", "ciudad"),
            "zona_empleador": by_label("Zona"),
            "correo_empleador": by_label("Correo electrónico de la sede", "Correo electrónico"),
            "representante_legal": rep_name,
            "tipo_doc_representante": tdoc_rep,
            "doc_representante": doc_rep,
            "sede_codigo": by_label("Código de la sede:"),
            "sede_nombre": sede_name or by_label("Nombre  de la sede:", "Nombre de la sede principal"),
            "sede_direccion": by_label("Dirección de la sede:", "Dirección de la sede principal"),
            "sede_ciudad": by_label("Municipio:", "Municipio/Distrito"),
            "sede_departamento": by_label("Departamento:"),
            "sede_telefono": by_label("Teléfono fijo/celular:", "Teléfono fijo/celular"),
            "sede_correo": by_label("Correo electrónico de la sede:", "Correo electrónico de la sede"),
            "sede_responsable": by_label("2. Apellidos y nombres del responsable de la sede principal"),
            "nomina_total": nomina_total,
        }

    def _format_xlsx_vs_live_ocr_comparison(
        self,
        *,
        question: str,
        lote: str = "",
        idtramite: str = "",
        contrato_text: str,
        contrato_source: str = "",
        live_ocr_result: dict[str, Any],
    ) -> str:
        lines = ["Comparación XLSX (hojas contrato/sede) vs OCR en vivo (PDFs):", f"- Consulta: {question}"]
        if lote.strip():
            lines.append(f"- Lote: {lote.strip()}")
        if idtramite.strip():
            lines.append(f"- Trámite: {idtramite.strip()}")
        if contrato_source:
            lines.append(f"- Fuente contrato: {contrato_source}")

        parsed = self._extract_xlsx_empleador_sede(contrato_text)
        if not parsed:
            lines.append("- No pude leer campos del contrato_clean (fuente XLSX) para comparar.")
            return "\n".join(lines)

        ocr_rows = live_ocr_result.get("rows", []) if isinstance(live_ocr_result, dict) else []
        ocr_joined = "\n".join(str(r.get("ocr_text") or "") for r in ocr_rows if bool(r.get("ok")))
        ocr_norm = self._norm_text(ocr_joined)
        lines.append(
            f"- OCR en vivo: adjuntos={int(live_ocr_result.get('adjuntos_total') or 0)} "
            f"procesados={int(live_ocr_result.get('processed') or 0)} ok={int(live_ocr_result.get('ok_count') or 0)}"
        )

        field_map = [
            ("Empresa", "empresa"),
            ("NIT", "nit"),
            ("Dirección empleador", "direccion_empleador"),
            ("Teléfono empleador", "telefono_empleador"),
            ("Ciudad empleador", "ciudad_empleador"),
            ("Zona empleador", "zona_empleador"),
            ("Correo empleador", "correo_empleador"),
            ("Representante legal", "representante_legal"),
            ("Tipo doc representante", "tipo_doc_representante"),
            ("Doc representante", "doc_representante"),
            ("Código sede", "sede_codigo"),
            ("Nombre sede", "sede_nombre"),
            ("Dirección sede", "sede_direccion"),
            ("Ciudad sede", "sede_ciudad"),
            ("Departamento sede", "sede_departamento"),
            ("Teléfono sede", "sede_telefono"),
            ("Correo sede", "sede_correo"),
            ("Responsable sede", "sede_responsable"),
        ]

        matched_lines: list[str] = []
        for label, key in field_map:
            val = str(parsed.get(key) or "").strip()
            if not val:
                continue
            score, mode = self._score_field_match(label, val, ocr_norm)
            threshold = 0.80 if label in {"NIT", "Teléfono empleador", "Teléfono sede", "Doc representante"} else 0.72
            if score >= threshold:
                tag = "MATCH" if mode == "exact" else ("MATCH_NORMALIZADO" if mode == "normalized" else "MATCH_FUZZY")
                matched_lines.append(f"  - {label}: {tag}({round(score,2)}) | XLSX='{val}'")
        lines.append(f"- Coincidencias: {len(matched_lines)} campo(s).")
        if matched_lines:
            lines.append("- Campos con coincidencia:")
            lines.extend(matched_lines)
        else:
            lines.append("- No se detectaron coincidencias confiables XLSX vs OCR para este lote.")
        lines.append("- Solo se muestran coincidencias; los NO MATCH se omiten por diseño.")
        lines.append("Nota: esta comparación usa XLSX original cuando está disponible y OCR recién ejecutado de los PDFs del lote.")
        return "\n".join(lines)

    @staticmethod
    def _format_live_ocr_result(result: dict[str, Any]) -> str:
        lines = ["OCR en vivo por lote/trámite (nueva lectura):"]
        lines.append(
            f"- Lote: {str(result.get('lote') or '')} | Trámite: {str(result.get('idtramite') or '')} | "
            f"Adjuntos BD: {int(result.get('adjuntos_total') or 0)} | Procesados: {int(result.get('processed') or 0)} | "
            f"OK: {int(result.get('ok_count') or 0)}"
        )
        rows = result.get("rows", []) if isinstance(result, dict) else []
        mode_counts: dict[str, int] = {}
        for r in rows:
            mode = str(r.get("ocr_mode") or "").strip()
            if mode:
                mode_counts[mode] = mode_counts.get(mode, 0) + 1
        if mode_counts:
            lines.append(f"- Modo OCR detectado: {mode_counts}")
        for r in rows[:20]:
            if bool(r.get("ok")):
                lines.append(
                    f"- {r.get('filename','')} tipo={r.get('tipo_adjunto','')} modo={r.get('ocr_mode','unknown')} chars={r.get('chars',0)} ok"
                )
            else:
                lines.append(
                    f"- {r.get('filename') or r.get('source_path') or 'adjunto'} tipo={r.get('tipo_adjunto','')} "
                    f"ERROR={r.get('error','ocr_failed')}"
                )
        lines.append("Este OCR es nuevo: no reutiliza texto guardado en RAG.")
        return "\n".join(lines)

    @staticmethod
    def _format_live_ocr_pdf_lookup(
        *,
        question: str,
        base: str = "temporal",
        lote: str = "",
        idtramite: str = "",
        live_ocr_result: dict[str, Any],
        representante_nombre: str = "",
        representante_doc: str = "",
        contrato_source: str = "",
    ) -> str:
        rows = live_ocr_result.get("rows", []) if isinstance(live_ocr_result, dict) else []
        tokens = [
            "cedula de ciudadania",
            "cedula ciudadania",
            "identificacion personal",
            "republica de colombia",
            "numero",
            "cc",
        ]
        qn = NovaOrchestrator._norm_text(question)
        rep_doc_digits = NovaOrchestrator._digits(representante_doc)
        rep_name_tokens = [t for t in NovaOrchestrator._norm_text(representante_nombre).split() if len(t) >= 4][:4]
        asks_rep_legal = ("representante legal" in qn) or ("rep legal" in qn)

        matches: list[dict[str, Any]] = []
        for r in rows:
            if not bool(r.get("ok")):
                continue
            text = str(r.get("ocr_text") or "")
            nt = NovaOrchestrator._norm_text(text)
            nt_digits = NovaOrchestrator._digits(nt)
            score = 0
            for tk in tokens:
                if tk in nt:
                    score += 1
            # type 6 suele ser documento de identidad en este flujo.
            if str(r.get("tipo_adjunto") or "").strip() == "6":
                score += 2
            rep_name_hits = 0
            if asks_rep_legal and rep_name_tokens:
                for tk in rep_name_tokens:
                    if tk in nt:
                        rep_name_hits += 1
                        score += 2
            rep_doc_match = bool(asks_rep_legal and rep_doc_digits and rep_doc_digits in nt_digits)
            if rep_doc_match:
                score += 5
            # En consultas de representante legal, evitar falsos positivos:
            # si no coincide el documento, exigir al menos 2 tokens fuertes del nombre.
            if asks_rep_legal and not rep_doc_match and rep_name_hits < 2:
                continue
            strong_phrase = ("cedula de ciudadania" in nt) or ("identificacion personal" in nt)
            strong_country_id = ("republica de colombia" in nt and "cedula" in nt)
            is_tipo6 = str(r.get("tipo_adjunto") or "").strip() == "6"
            if not (is_tipo6 or strong_phrase or strong_country_id or (asks_rep_legal and score >= 3)):
                continue
            if score < 4:
                continue
            snippet = ""
            for tk in tokens[:4]:
                idx = nt.find(tk)
                if idx >= 0:
                    snippet = text[max(0, idx - 40): idx + 140]
                    break
            if not snippet:
                snippet = text[:160]
            matches.append(
                {
                    "filename": str(r.get("filename") or ""),
                    "tipo_adjunto": str(r.get("tipo_adjunto") or ""),
                    "chars": int(r.get("chars") or 0),
                    "score": score,
                    "snippet": " ".join(snippet.split()),
                }
            )
        matches.sort(key=lambda x: (x["score"], x["chars"]), reverse=True)

        lines = ["PDFs candidatos a cédula (OCR en vivo):"]
        if lote.strip():
            lines.append(f"- Lote: {lote.strip()}")
        if idtramite.strip():
            lines.append(f"- Trámite: {idtramite.strip()}")
        lines.append(f"- Consulta: {question}")
        if not matches:
            lines.append("- No se encontraron PDFs con señales OCR de cédula/identificación.")
            if asks_rep_legal and (representante_nombre.strip() or representante_doc.strip()):
                lines.append(
                    f"- Dato contrato (fallback): {representante_nombre.strip() or 'N/D'} | "
                    f"Doc: {representante_doc.strip() or 'N/D'}"
                )
                if contrato_source.strip():
                    lines.append(f"- Fuente contrato: {contrato_source}")
            return "\n".join(lines)
        if asks_rep_legal and (representante_nombre.strip() or representante_doc.strip()):
            lines.append(
                f"- Referencia representante legal: {representante_nombre.strip() or 'N/D'} | "
                f"Doc: {representante_doc.strip() or 'N/D'}"
            )
        lines.append(f"- Documento sugerido para abrir: {matches[0]['filename']}")
        lines.append(
            f"- Abrir documento: /api/v1/nova/pdf/view?base={base}&lote={lote}&idtramite={idtramite}&filename={matches[0]['filename']}"
        )
        for m in matches[:8]:
            lines.append(
                f"- {m['filename']} | tipo={m['tipo_adjunto']} | score={m['score']} | chars={m['chars']} | evidencia='{m['snippet']}'"
            )
        return "\n".join(lines)

    @staticmethod
    def _format_pdf_candidates_answer(
        *,
        question: str,
        base: str,
        lote: str = "",
        idtramite: str = "",
        rows: list[dict[str, Any]] | None = None,
    ) -> str:
        docs = rows or []
        lines = ["Documentos candidatos por búsqueda OCR en vivo:"]
        if lote.strip():
            lines.append(f"- Lote: {lote.strip()}")
        if idtramite.strip():
            lines.append(f"- Trámite: {idtramite.strip()}")
        lines.append(f"- Consulta: {question}")
        lines.append(f"- Coincidencias: {len(docs)}")
        if not docs:
            lines.append("- No encontré documentos que coincidan con ese criterio.")
            lines.append("- Sugerencia: intenta con términos más específicos (ej. 'camara de comercio nit 901234660').")
            return "\n".join(lines)
        top = docs[0]
        top_name = str(top.get("filename") or "").strip()
        if top_name:
            lines.append(f"- Documento sugerido para abrir: {top_name}")
            lines.append(
                f"- Abrir documento: /api/v1/nova/pdf/view?base={base}&lote={lote}&idtramite={idtramite}&filename={top_name}"
            )
        for d in docs[:10]:
            lines.append(
                f"- {str(d.get('filename') or '')} | tipo={str(d.get('tipo_adjunto') or '')} | "
                f"score={int(d.get('score') or 0)} | chars={int(d.get('chars') or 0)} | "
                f"evidencia='{str(d.get('evidence') or '').strip()}'"
            )
        return "\n".join(lines)

    @staticmethod
    def _doc_type_targets_from_question(question: str) -> list[str]:
        qn = NovaOrchestrator._norm_text(question)
        targets: list[str] = []
        if ("camara" in qn and "comercio" in qn) or ("camara y comercio" in qn):
            targets.append("5")
        if "cedula" in qn or "cédula" in qn or "identificacion" in qn or "identificación" in qn:
            targets.append("6")
        if "rut" in qn or "dian" in qn:
            targets.append("8")
        if "formulario" in qn or "afiliacion" in qn or "afiliación" in qn:
            targets.append("0")
        if "sede" in qn or "anexo" in qn:
            targets.append("1")
        if "listado" in qn or "trabajadores" in qn:
            targets.append("2")
        if "historia clinica" in qn or "historia clínica" in qn:
            targets.append("22")
        if not targets:
            # Búsqueda documental genérica: priorizar tipos operativos frecuentes.
            targets = ["5", "6", "8", "0", "1", "2"]
        # Mantener orden y unicidad.
        seen: set[str] = set()
        out: list[str] = []
        for t in targets:
            if t in seen:
                continue
            seen.add(t)
            out.append(t)
        return out

    @staticmethod
    def _extract_rep_name_from_text(text: str) -> str:
        raw = str(text or "")
        if not raw.strip():
            return ""
        cleaned = " ".join(raw.replace("|", " ").split())
        patterns = [
            r"apellidos\s+y\s+nombres\s+del\s+representante\s+legal\s*[:\-]?\s*([A-Za-zÁÉÍÓÚÑáéíóúñ\s]{8,160})",
            r"nombre\s+del\s+representante\s+legal\s*[:\-]?\s*([A-Za-zÁÉÍÓÚÑáéíóúñ\s]{8,160})",
            r"representante\s+legal\s*[:\-]?\s*([A-Za-zÁÉÍÓÚÑáéíóúñ\s]{8,160})",
        ]
        stop_words = (
            "tipo de documento",
            "numero de documento",
            "número de documento",
            "correo",
            "actividad economica",
            "actividad económica",
            "direccion",
            "dirección",
            "nit",
        )
        for pat in patterns:
            m = re.search(pat, cleaned, flags=re.IGNORECASE)
            if not m:
                continue
            cand = " ".join(str(m.group(1) or "").split()).strip()
            if not cand:
                continue
            low = cand.lower()
            cut = len(cand)
            for w in stop_words:
                idx = low.find(w)
                if idx >= 0:
                    cut = min(cut, idx)
            cand = cand[:cut].strip(" -:;,")
            tokens = [t for t in cand.split() if len(NovaOrchestrator._norm_text(t)) >= 2]
            if len(tokens) >= 2:
                return " ".join(tokens[:8]).strip()
        return ""

    @staticmethod
    def _doc_code_label(code: str) -> str:
        labels = {
            "0": "Formulario afiliación",
            "1": "Anexo sedes",
            "2": "Listado trabajadores",
            "3": "Comisión",
            "5": "Cámara de comercio",
            "6": "Cédula representante",
            "8": "RUT",
            "11": "Pagos ARL anterior",
            "22": "Historia clínica",
            "98": "Autorización",
            "99": "Imagen/Otro",
        }
        return labels.get(str(code or "").strip(), f"Tipo {str(code or '').strip() or 'N/D'}")

    @staticmethod
    def _critical_requirements_matrix() -> list[dict[str, Any]]:
        return [
            {"key": "formulario_afiliacion", "label": "Formulario afiliación", "types": ["0"], "critical": True},
            {"key": "anexo_sedes", "label": "Anexo sedes", "types": ["1"], "critical": True},
            {"key": "listado_trabajadores", "label": "Listado trabajadores", "types": ["2"], "critical": True},
            {"key": "camara_comercio", "label": "Cámara de comercio", "types": ["5"], "critical": True},
            {"key": "cedula_representante", "label": "Cédula representante legal", "types": ["6"], "critical": True},
            {"key": "rut", "label": "RUT", "types": ["8"], "critical": True},
        ]

    @staticmethod
    def _format_adjuntos_by_type_answer(
        *,
        question: str,
        base: str,
        lote: str = "",
        idtramite: str = "",
        adjuntos: list[dict[str, Any]] | None = None,
        ocr_rows: list[dict[str, Any]] | None = None,
    ) -> str:
        rows = adjuntos or []
        ocr_rows = ocr_rows or []
        targets = NovaOrchestrator._doc_type_targets_from_question(question)
        qn = NovaOrchestrator._norm_text(question)
        asks_missing = ("faltante" in qn) or ("faltantes" in qn) or ("prevalid" in qn) or ("requisito" in qn)
        req_rows = NovaOrchestrator._critical_requirements_matrix()
        critical_types = [str(t) for r in req_rows for t in list(r.get("types") or [])]
        if asks_missing:
            targets = critical_types
        filtered: list[dict[str, Any]] = []
        for a in rows:
            tipo = str(a.get("tipo_adjunto") or "").strip()
            if tipo in targets:
                filtered.append(a)

        # Fallback: si no hay match por tipo, mostrar muestra general.
        if not filtered:
            filtered = rows[:12]

        def filename_from_path(v: str) -> str:
            p = str(v or "").replace("\\", "/")
            return p.split("/")[-1] if p else ""

        lines = ["Consulta documental NOVA (BD adjuntos):"]
        if lote.strip():
            lines.append(f"- Lote: {lote.strip()}")
        if idtramite.strip():
            lines.append(f"- Trámite: {idtramite.strip()}")
        lines.append(f"- Consulta: {question}")
        lines.append(f"- Tipos objetivo: {', '.join(targets)}")
        lines.append(f"- Coincidencias: {len(filtered)}")

        present_types: set[str] = set()
        for a in rows:
            t = str(a.get("tipo_adjunto") or "").strip()
            if t:
                present_types.add(t)
        req_status: list[dict[str, Any]] = []
        for req in req_rows:
            req_types = [str(t) for t in req.get("types", [])]
            found = any(t in present_types for t in req_types)
            req_status.append(
                {
                    "label": str(req.get("label") or ""),
                    "types": req_types,
                    "found": found,
                    "critical": bool(req.get("critical")),
                }
            )
        missing_critical = [r for r in req_status if bool(r.get("critical")) and (not bool(r.get("found")))]

        if asks_missing:
            lines.append("- Estado requisitos críticos (por tipo adjunto):")
            if missing_critical:
                for r in missing_critical:
                    lines.append(
                        f"- FALTANTE: {r['label']} (tipo {','.join(r['types'])})"
                    )
            else:
                lines.append("- OK: no veo faltantes críticos en los tipos adjuntos del lote.")
        else:
            # Consulta documental puntual: responder directo sin ruido de checklist completo.
            lines.append("- Estado: consulta puntual resuelta con adjuntos encontrados.")

        if not filtered:
            lines.append("- No hay adjuntos para ese criterio.")
            return "\n".join(lines)

        if ocr_rows:
            lines.append("- OCR rápido (muestra):")
            for r in ocr_rows[:2]:
                fn = str(r.get("filename") or "sin_nombre")
                if bool(r.get("ok")):
                    txt = " ".join(str(r.get("ocr_text") or "").split())[:140]
                    lines.append(f"- {fn}: {txt or 'OCR vacío'}")
                else:
                    lines.append(f"- {fn}: OCR no disponible")

        lines.append("- Documentos encontrados (ábrelo en el visor NOVA):")
        max_list = 8 if not ocr_rows else 5
        for idx, a in enumerate(filtered[:max_list], start=1):
            tipo = str(a.get("tipo_adjunto") or "").strip()
            ruta = str(a.get("rutaadjunto") or "")
            fn = filename_from_path(ruta)
            lines.append(f"- {idx}) {NovaOrchestrator._doc_code_label(tipo)} (tipo {tipo or 'N/D'}) - {fn or 'sin_nombre'}")
        return "\n".join(lines)

    @staticmethod
    def _extract_dates_ddmmyyyy(text: str) -> list[datetime]:
        out: list[datetime] = []
        src = str(text or "")
        for m in re.finditer(r"\b([0-3]?\d)[/\-]([0-1]?\d)[/\-]((?:19|20)\d{2})\b", src):
            try:
                dd = int(m.group(1))
                mm = int(m.group(2))
                yy = int(m.group(3))
                out.append(datetime(yy, mm, dd))
            except Exception:
                continue
        return out

    @staticmethod
    def _format_revalidator_answer(*, question: str, precheck: dict[str, Any]) -> str:
        summary = precheck.get("summary", {}) if isinstance(precheck, dict) else {}
        excel_fields = precheck.get("excel_fields", {}) if isinstance(precheck, dict) else {}
        checklist = precheck.get("checklist", []) if isinstance(precheck, dict) else []
        alerts = precheck.get("alerts", []) if isinstance(precheck, dict) else []
        motivos = precheck.get("motivos_de_rechazo", []) if isinstance(precheck, dict) else []
        docs_ocr = precheck.get("docs_ocr", []) if isinstance(precheck, dict) else []
        dup_docs = (((precheck.get("clean_generated") or {}).get("quality_controls") or {}).get("duplicates") or {}) if isinstance(precheck, dict) else {}

        empresa = str(excel_fields.get("empresa") or "").strip()
        nit = str(excel_fields.get("nit") or "").strip()
        rep = str(excel_fields.get("representante_legal") or "").strip()
        rep_doc = str(excel_fields.get("doc_representante") or "").strip()

        camara_docs = [d for d in (docs_ocr or []) if str(d.get("doc_type") or "") == "camara_comercio"]
        camara_dates: list[datetime] = []
        for d in camara_docs:
            camara_dates.extend(NovaOrchestrator._extract_dates_ddmmyyyy(str(d.get("text") or "")))
        camara_recent = max(camara_dates) if camara_dates else None
        camara_days = (datetime.now() - camara_recent).days if camara_recent else None
        camara_vigente = (camara_days is not None) and (camara_days <= 90)

        critical_missing = [x for x in checklist if bool(x.get("critical")) and not bool(x.get("found"))]

        lines: list[str] = []
        lines.append("Revalidador NOVA (reglas operativas):")
        lines.append(f"- Empresa: {empresa or 'N/D'} | NIT: {nit or 'N/D'}")
        lines.append(f"- Representante legal (Excel): {rep or 'N/D'} | Doc: {rep_doc or 'N/D'}")
        lines.append(
            f"- Estado precheck: {'APROBADO' if bool(precheck.get('approved')) else 'RECHAZADO'} | "
            f"bloqueantes={int(summary.get('blocking_issues') or 0)}"
        )

        lines.append("- Validación documental crítica:")
        if critical_missing:
            for m in critical_missing[:8]:
                lines.append(f"- FALLA: {str(m.get('requirement') or m.get('requirement_key') or 'Requisito')} (faltante)")
        else:
            lines.append("- OK: no veo faltantes críticos en checklist.")

        lines.append("- Consistencia Cámara de Comercio:")
        if camara_recent:
            lines.append(
                f"- Fecha detectada en OCR: {camara_recent.strftime('%Y-%m-%d')} "
                f"({camara_days} días) -> {'OK' if camara_vigente else 'FALLA (>90 días)'}"
            )
        else:
            lines.append("- REVISAR: no pude extraer fecha de expedición en OCR de cámara.")

        rep_name_alert = any(str(a.get("code") or "") == "ALERTA_REPRESENTANTE_LEGAL_NO_COINCIDE" for a in alerts)
        rep_doc_alert = any(str(a.get("code") or "") == "ALERTA_DOC_REPRESENTANTE_NO_COINCIDE" for a in alerts)
        lines.append(
            f"- Nombre representante vs cámara: {'FALLA' if rep_name_alert else 'OK'} | "
            f"Documento representante vs cámara: {'FALLA' if rep_doc_alert else 'OK'}"
        )

        lines.append("- Duplicados de cédula en Excel/TXT generado:")
        dup_ok = bool(dup_docs.get("ok", True))
        dup_items = list(dup_docs.get("items") or [])
        if dup_ok or not dup_items:
            lines.append("- OK: no se detectan duplicados en el set generado.")
        else:
            for d in dup_items[:8]:
                occ = list(d.get("occurrences") or [])
                where = ", ".join([f"{str(x.get('sheet') or '')}:fila {str(x.get('row') or '')}" for x in occ[:4]])
                lines.append(
                    f"- FALLA: {str(d.get('tipodocumento') or '')}-{str(d.get('numerodocumento') or '')} "
                    f"(repetido {int(d.get('count') or 0)} veces) | {where}"
                )

        if motivos:
            lines.append("- Motivos bloqueantes actuales:")
            for m in motivos[:8]:
                lines.append(f"- {str(m.get('code') or '')}: {str(m.get('title') or '')}")

        lines.append("- Siguiente paso:")
        lines.append("- Corrige FALLAS y re-ejecuta Paso 0; NOVA volverá a validar contra las mismas reglas.")
        return "\n".join(lines)

    def _format_afiliaciones_dimension_answer(
        self,
        *,
        question: str,
        qn: str,
        snapshot: dict[str, Any],
        contrato_fields: dict[str, str] | None = None,
        normative_catalog: list[str] | None = None,
        xlsx_sheet_names: list[str] | None = None,
        contrato_source: str = "",
        nomina_total_override: int | None = None,
    ) -> str:
        empleadores = snapshot.get("empleadores", []) if isinstance(snapshot, dict) else []
        sedes = snapshot.get("sedes", []) if isinstance(snapshot, dict) else []
        trabajadores = snapshot.get("trabajadores", []) if isinstance(snapshot, dict) else []
        adjuntos = snapshot.get("adjuntos", []) if isinstance(snapshot, dict) else []
        contrato_fields = contrato_fields or {}
        normative_catalog = normative_catalog or []
        xlsx_sheet_names = xlsx_sheet_names or []

        tokens = (qn or "").split()
        token_set = set(tokens)

        def has_like(target: str, threshold: float = 0.62) -> bool:
            for tk in tokens:
                if tk == target:
                    return True
                if len(tk) >= 4 and len(target) >= 4:
                    if difflib.SequenceMatcher(None, tk, target).ratio() >= threshold:
                        return True
            return False

        lines = ["Resumen del lote:"]
        if str(snapshot.get("lote") or "").strip() or str(snapshot.get("idtramite") or "").strip():
            lines.append(
                f"- Contexto: lote={str(snapshot.get('lote') or 'N/D')} | idtrámite={str(snapshot.get('idtramite') or 'N/D')}"
            )
        lines.append(f"- Empleadores: {len(empleadores)}")
        sedes_operativas = [s for s in sedes if str(s.get("tp") or "").upper() == "S"] or sedes
        lines.append(f"- Sedes: {len(sedes_operativas)}")
        lines.append(f"- Trabajadores: {len(trabajadores)}")
        lines.append(f"- Adjuntos: {len(adjuntos)}")
        salarios_total = NovaOrchestrator._as_int_count(snapshot.get("salarios_total") if isinstance(snapshot, dict) else 0)
        if isinstance(nomina_total_override, int) and nomina_total_override > 0:
            salarios_total = int(nomina_total_override)
        if salarios_total <= 0:
            salarios_total = NovaOrchestrator._as_int_count((contrato_fields or {}).get("nomina_total"))
        if salarios_total > 0:
            lines.append(f"- Nómina total: {salarios_total}")

        wants_datos = has_like("datos")
        if has_like("empleador") or has_like("empresa") or wants_datos:
            lines.append("")
            lines.append("Empleador:")
            for e in empleadores[:5]:
                actividad = str(e.get("actividad") or "").strip() or str(contrato_fields.get("actividad_economica") or "").strip()
                tipo_aportante = str(e.get("tipo_aportante") or "").strip() or str(contrato_fields.get("tipo_aportante") or "").strip()
                ciudad_emp = str(e.get("ciudad") or "").strip()
                if re.fullmatch(r"\d{4,6}", ciudad_emp):
                    ciudad_sede = str((sedes_operativas[0].get("ciudad") if sedes_operativas else "") or "").strip()
                    if ciudad_sede:
                        ciudad_emp = f"{ciudad_sede} ({ciudad_emp})"
                lines.append(
                    f"- Razón social: {e.get('empleador','')}"
                )
                lines.append(f"- NIT: {e.get('nit_empleador','')}")
                if actividad:
                    lines.append(f"- Actividad económica: {actividad}")
                if tipo_aportante:
                    lines.append(f"- Tipo aportante: {tipo_aportante}")
                lines.append(f"- Dirección: {e.get('direccion','')}")
                lines.append(f"- Ciudad: {ciudad_emp}")
                break
        if has_like("sede") or wants_datos:
            lines.append("")
            lines.append("Sede:")
            for s in sedes_operativas[:8]:
                lines.append(f"- Nombre: {s.get('nombre','')}")
                lines.append(f"- Ciudad: {s.get('ciudad','')}")
                if str(s.get("zona") or "").strip():
                    lines.append(f"- Zona: {s.get('zona','')}")
                if str(s.get("riesgo") or "").strip():
                    lines.append(f"- Clase/Riesgo: {s.get('riesgo','')}")
                if str(s.get("telefono") or "").strip():
                    lines.append(f"- Teléfono: {s.get('telefono','')}")
                break
        if has_like("representante"):
            lines.append("")
            lines.append("Representante legal:")
            for e in empleadores[:5]:
                rep = str(e.get("representante_legal") or "").strip()
                tdoc = str(e.get("tipo_doc_representante") or "").strip()
                ndoc = str(e.get("doc_representante") or "").strip()
                if not rep:
                    rep = str(contrato_fields.get("representante_legal") or "").strip()
                if not tdoc:
                    tdoc = str(contrato_fields.get("tipo_doc_representante") or "").strip()
                if not ndoc:
                    ndoc = str(contrato_fields.get("doc_representante") or "").strip()
                lines.append(f"- Nombre: {rep or 'No disponible'}")
                lines.append(f"- Tipo y número de documento: {(tdoc + ' ' + ndoc).strip() or 'No disponible'}")
                if contrato_source.strip():
                    lines.append(f"- Fuente del dato: {contrato_source}")
                else:
                    lines.append("- Fuente del dato: snapshot BD")
                break
        if has_like("ciudad"):
            agg: dict[str, int] = {}
            for t in trabajadores:
                c = str(t.get("ciudad") or "").strip()
                if c:
                    agg[c] = agg.get(c, 0) + 1
            if not agg:
                for e in empleadores:
                    c = str(e.get("ciudad") or "").strip() or str(contrato_fields.get("ciudad_empleador") or "").strip()
                    if c:
                        agg[c] = max(agg.get(c, 0), len(trabajadores) or 1)
                for s in sedes:
                    c = str(s.get("ciudad") or "").strip()
                    if c:
                        agg[c] = max(agg.get(c, 0), len(trabajadores) or 1)
            lines.append("")
            lines.append("Ciudad:")
            if agg:
                for c, n in sorted(agg.items(), key=lambda x: x[1], reverse=True)[:10]:
                    lines.append(f"- {c} ({n} trabajador(es))")
            else:
                lines.append("- No disponible")
        if has_like("actividad"):
            agg: dict[str, int] = {}
            for t in trabajadores:
                a = str(t.get("actividad") or "").strip()
                if a:
                    agg[a] = agg.get(a, 0) + 1
            if not agg:
                for e in empleadores:
                    a = str(e.get("actividad") or "").strip() or str(contrato_fields.get("actividad_economica") or "").strip()
                    if a:
                        agg[a] = max(agg.get(a, 0), len(trabajadores) or 1)
            lines.append("")
            lines.append("Actividad económica:")
            if agg:
                for a, n in sorted(agg.items(), key=lambda x: x[1], reverse=True)[:10]:
                    lines.append(f"- {a} ({n} trabajador(es))")
            else:
                lines.append("- No disponible")
        if has_like("nomina") or has_like("nómina") or has_like("salario") or has_like("salarios"):
            lines.append("")
            lines.append("Nómina:")
            lines.append(f"- Valor total nómina: {salarios_total if salarios_total > 0 else 'No disponible'}")
        if has_like("hoja") or has_like("sheet") or has_like("orp") or (has_like("codigo") and has_like("actividad")):
            lines.append("")
            lines.append("Hojas XLSX relevantes:")
            if xlsx_sheet_names:
                if has_like("orp"):
                    orp_hits = [h for h in xlsx_sheet_names if "orp" in NovaOrchestrator._norm_text(h)]
                    if orp_hits:
                        for h in orp_hits[:5]:
                            lines.append(f"- {h}")
                    else:
                        lines.append("- No encontré hoja con ORP en el XLSX indexado.")
                if has_like("actividad"):
                    act_hits = [h for h in xlsx_sheet_names if "actividad" in NovaOrchestrator._norm_text(h)]
                    if act_hits:
                        for h in act_hits[:5]:
                            lines.append(f"- {h}")
                    elif not has_like("orp"):
                        lines.append("- No encontré hoja de actividades en el XLSX indexado.")
                if not has_like("orp") and not has_like("actividad"):
                    for h in xlsx_sheet_names[:8]:
                        lines.append(f"- {h}")
            else:
                lines.append("- No disponible")
        if has_like("riesgo"):
            agg: dict[str, int] = {}
            for t in trabajadores:
                r = str(t.get("riesgo") or "").strip()
                if r:
                    agg[r] = agg.get(r, 0) + 1
            if not agg:
                for s in sedes:
                    r = str(s.get("riesgo") or "").strip()
                    if r:
                        agg[r] = max(agg.get(r, 0), len(trabajadores) or 1)
            lines.append("")
            lines.append("Riesgo:")
            if agg:
                for r, n in sorted(agg.items(), key=lambda x: x[1], reverse=True)[:10]:
                    lines.append(f"- {r} ({n} registro(s))")
            else:
                lines.append("- No disponible")
        asks_adjuntos = has_like("adjunto") or has_like("adjuntos") or has_like("documento") or has_like("documentos")
        asks_normativa = has_like("normativo") or has_like("normativa") or has_like("instructivo") or has_like("regla")
        if asks_adjuntos:
            by_tipo: dict[str, int] = {}
            for a in adjuntos:
                t = str(a.get("tipo_adjunto") or "").strip() or "SIN_TIPO"
                by_tipo[t] = by_tipo.get(t, 0) + 1
            missing = [a for a in adjuntos if not str(a.get("rutaadjunto") or "").strip()]
            lines.append(f"- Adjuntos por tipo: {by_tipo}")
            lines.append(f"- Adjuntos sin ruta: {len(missing)}")
            if asks_normativa and normative_catalog:
                lines.append(f"- Catálogo normativo XLSX detectado: {len(normative_catalog)} ítem(s).")
                adj_evidence = " ".join(
                    [
                        str(a.get("tipo_adjunto") or "")
                        + " "
                        + str(a.get("rutaadjunto") or "")
                        + " "
                        + str(a.get("nombrearchivo") or "")
                        for a in adjuntos
                    ]
                )
                adj_norm = NovaOrchestrator._norm_text(adj_evidence)
                present: list[str] = []
                missing_norm: list[str] = []
                for it in normative_catalog:
                    key_tokens = [tok for tok in NovaOrchestrator._norm_text(it).split() if len(tok) >= 4]
                    hit = False
                    if key_tokens:
                        for tk in key_tokens[:4]:
                            if tk in adj_norm:
                                hit = True
                                break
                    if hit:
                        present.append(it)
                    else:
                        missing_norm.append(it)
                lines.append(f"- Normativos presentes (aprox): {len(present)}")
                lines.append(f"- Normativos faltantes (aprox): {len(missing_norm)}")
                for it in missing_norm[:8]:
                    lines.append(f"  - FALTANTE_NORMATIVO: {it}")
            elif asks_normativa:
                lines.append("- No encontré catálogo normativo en el XLSX; verifica hojas de instructivos/normas.")
        if has_like("asesor"):
            lines.append("- Asesor: no está expuesto de forma consistente en las tablas leídas por NOVA en este snapshot.")
            lines.append("- Recomendación: mapear campo usuario_asignado en proc_servicios_obtenertramites para habilitarlo.")

        if has_like("telefono"):
            lines.append("")
            lines.append("Contacto empleador:")
            for e in empleadores[:3]:
                tel = str(e.get("telefono") or "").strip() or str(contrato_fields.get("telefono_empleador") or "").strip()
                cel = str(e.get("celular") or "").strip() or str(contrato_fields.get("telefono_empleador") or "").strip()
                lines.append(f"- Teléfono empleador: {tel or 'NO_DISPONIBLE'} | Celular: {cel or 'NO_DISPONIBLE'}")

        asks_trabajadores = bool(
            {"trabajador", "trabajadores", "afiliado", "afiliados", "empleado", "empleados"} & token_set
        )
        if asks_trabajadores:
            lines.append("")
            docs = {
                str(t.get("documento") or "").strip()
                for t in trabajadores
                if str(t.get("documento") or "").strip()
            }
            lines.append(f"Trabajadores del lote ({len(docs)}):")
            for t in trabajadores[:12]:
                ap = " ".join([str(t.get("primerapellido") or "").strip(), str(t.get("segundoapellido") or "").strip()]).strip()
                no = " ".join([str(t.get("primernombre") or "").strip(), str(t.get("segundonombre") or "").strip()]).strip()
                lines.append(f"- {t.get('documento','')} | {ap} {no}".strip())

        if any(k in qn for k in ["barranquilla", "bogota", "medellin", "cali"]):
            city_target = ""
            for c in ["barranquilla", "bogota", "medellin", "cali"]:
                if c in qn:
                    city_target = c
                    break
            city_aliases = {
                "barranquilla": {"barranquilla", "08001", "8 001", "atlantico"},
                "bogota": {"bogota", "bogota d c", "11001", "11 001", "cundinamarca"},
                "medellin": {"medellin", "05001", "5 001", "antioquia"},
                "cali": {"cali", "76001", "76 001", "valle"},
            }
            hits = []
            for e in empleadores:
                ec = NovaOrchestrator._norm_text(str(e.get("ciudad") or ""))
                aliases = city_aliases.get(city_target, {city_target} if city_target else set())
                if city_target and any(a in ec for a in aliases):
                    hits.append(e)
            lines.append(f"- Coincidencias por ciudad '{city_target.upper()}': {len(hits)} empleador(es).")
            for e in hits[:5]:
                lines.append(f"- {e.get('empleador','')} | NIT={e.get('nit_empleador','')} | Ciudad={e.get('ciudad','')}")
            asks_global = any(k in token_set for k in {"todos", "todas", "total"})
            asks_nomina = has_like("nomina") or has_like("nómina") or has_like("salario") or has_like("salarios")
            if asks_global and asks_nomina and city_target:
                city_total = self._get_city_nomina_total(base=str(snapshot.get("base") or "temporal"), city_target=city_target)
                if city_total > 0:
                    lines.append(f"- Nómina total afiliados en {city_target.upper()}: {city_total}")

        if len(lines) <= 2:
            lines.append("")
            lines.append("Sugerencias:")
            lines.append("- datos empleador")
            lines.append("- datos sede")
            lines.append("- afiliados del lote")
            lines.append("- documentos faltantes")
        return "\n".join(lines)

    @staticmethod
    def _extract_xlsx_normative_catalog(contrato_text: str) -> list[str]:
        text = str(contrato_text or "")
        if not text.strip():
            return []
        norm = NovaOrchestrator._norm_text(text)
        lines_raw = [ln.strip() for ln in text.splitlines() if ln and ln.strip()]
        candidates: list[str] = []

        strong_keys = [
            "obligatorio",
            "debe adjuntar",
            "debera adjuntar",
            "documentos requeridos",
            "documentos soporte",
            "anexos requeridos",
            "anexos",
            "soportes",
        ]
        doc_words = [
            "cedula",
            "nit",
            "rut",
            "camara",
            "comercio",
            "representante legal",
            "contrato",
            "afiliacion",
            "sede",
            "trabajador",
            "pago",
            "planilla",
            "soporte",
            "certificado",
            "formulario",
            "examen preocupacional",
            "identificacion de peligros",
        ]
        legal_words = ["ley", "decreto", "resolucion", "circular", "reglamentario", "norma"]

        for ln in lines_raw:
            lnn = NovaOrchestrator._norm_text(ln)
            if not lnn or lnn == "# hoja":
                continue
            has_strong = any(k in lnn for k in strong_keys)
            has_doc = any(d in lnn for d in doc_words)
            # Keep concise doc/support items, avoid long legal prose.
            if has_strong and has_doc:
                if len(lnn) > 180:
                    continue
                if any(w in lnn for w in legal_words) and len(lnn) > 100:
                    continue
                cleaned = re.sub(r"\s+", " ", ln.replace("|", " ")).strip(" -\t:;,.")
                if len(cleaned) >= 8 and len(cleaned) <= 180:
                    candidates.append(cleaned)

        # Fallback: pick short "documento ..." bullets if strong signal exists globally.
        if not candidates and ("obligatorio" in norm or "documentos" in norm):
            for ln in lines_raw:
                lnn = NovaOrchestrator._norm_text(ln)
                if "documento" in lnn and any(d in lnn for d in doc_words):
                    if len(lnn) > 140:
                        continue
                    cleaned = re.sub(r"\s+", " ", ln.replace("|", " ")).strip(" -\t:;,.")
                    if len(cleaned) >= 8 and len(cleaned) <= 140:
                        candidates.append(cleaned)

        # Deduplicate preserving order.
        out: list[str] = []
        seen: set[str] = set()
        for c in candidates:
            key = NovaOrchestrator._norm_text(c)
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(c)
            if len(out) >= 40:
                break
        return out

    @staticmethod
    def _extract_xlsx_sheet_names(contrato_text: str) -> list[str]:
        text = str(contrato_text or "")
        if not text.strip():
            return []
        out: list[str] = []
        seen: set[str] = set()
        for ln in text.splitlines():
            m = re.match(r"^\s*#\s*Hoja:\s*(.+?)\s*$", ln, flags=re.IGNORECASE)
            if not m:
                continue
            sheet = m.group(1).strip()
            if not sheet:
                continue
            key = NovaOrchestrator._norm_text(sheet)
            if key in seen:
                continue
            seen.add(key)
            out.append(sheet)
        return out

    @staticmethod
    def _is_allowed_contract_sheet(sheet_name: str) -> bool:
        n = NovaOrchestrator._norm_text(sheet_name)
        if not n:
            return False
        if ("formulario" in n and "afili" in n) or ("sede" in n and "trabajador" in n):
            return True
        markers = (
            "independientes 723",
            "instructivo",
            "listado actividades economicas",
            "codigos orp",
            "cod tipo de trabajador",
            "subtipos",
            "formulario afil ind voluntario",
            "indice",
            "hoja1",
        )
        return any(m in n for m in markers)

    @staticmethod
    def _split_xlsx_sheets(contrato_text: str) -> dict[str, list[str]]:
        text = str(contrato_text or "")
        if not text.strip():
            return {}
        out: dict[str, list[str]] = {}
        current = ""
        for raw in text.splitlines():
            ln = str(raw or "").strip()
            m = re.match(r"^\s*#\s*Hoja:\s*(.+?)\s*$", ln, flags=re.IGNORECASE)
            if m:
                current = m.group(1).strip()
                out.setdefault(current, [])
                continue
            if current and ln:
                out[current].append(ln)
        return out

    @staticmethod
    def _guess_tramite_tipo(contrato_text: str) -> str:
        nt = NovaOrchestrator._norm_text(contrato_text)
        if "b. traslado" in nt and " x" in nt[nt.find("b. traslado"): nt.find("b. traslado") + 40]:
            return "Traslado"
        if "c. terminacion" in nt and " x" in nt[nt.find("c. terminacion"): nt.find("c. terminacion") + 40]:
            return "Novedad/Terminación"
        return "Afiliación"

    @staticmethod
    def _extract_critical_dates(contrato_text: str) -> tuple[str, str]:
        t = str(contrato_text or "")
        rad = ""
        ini = ""
        m_rad = re.search(r"fecha de radicaci[oó]n[^\n]*\n([^\n]+)", t, flags=re.IGNORECASE)
        if m_rad:
            m_d = re.search(r"(\d{4}-\d{2}-\d{2})", m_rad.group(1))
            if m_d:
                rad = m_d.group(1)
        m_ini = re.search(r"fecha inicio de cobertura[^\n]*\n([^\n]+)", t, flags=re.IGNORECASE)
        if m_ini:
            m_d = re.search(r"(\d{4}-\d{2}-\d{2})", m_ini.group(1))
            if m_d:
                ini = m_d.group(1)
        if not rad:
            m_any = re.findall(r"\b(\d{4}-\d{2}-\d{2})\b", t)
            if m_any:
                rad = m_any[0]
                if len(m_any) > 1:
                    ini = ini or m_any[1]
        return rad, ini

    @staticmethod
    def _extract_false_evidence(sheets: dict[str, list[str]], max_items: int = 12) -> list[str]:
        out: list[str] = []
        for sh, rows in sheets.items():
            for i, ln in enumerate(rows, start=1):
                if "false" in NovaOrchestrator._norm_text(ln):
                    compact = " ".join(str(ln).split())
                    out.append(f"{sh}#L{i}: {compact[:180]}")
                    if len(out) >= max_items:
                        return out
        return out

    @staticmethod
    def _extract_false_evidence_from_excel(content: bytes, max_items: int = 40) -> list[str]:
        if load_workbook is None or not content:
            return []
        try:
            wb = load_workbook(io.BytesIO(content), data_only=True, read_only=False)
        except Exception:
            return []

        out: list[str] = []
        doc_types = set(TIPOS_DOCUMENTO_TRABAJADOR)
        for sh in wb.sheetnames:
            ws = wb[sh]
            max_row = int(ws.max_row or 0)
            max_col = int(ws.max_column or 0)
            if max_row <= 0 or max_col <= 0:
                continue
            for rr in range(1, max_row + 1):
                false_pos: list[int] = []
                bool_count = 0
                for cc in range(1, max_col + 1):
                    v = ws.cell(rr, cc).value
                    if isinstance(v, bool):
                        bool_count += 1
                    if isinstance(v, bool) and v is False:
                        false_pos.append(cc)
                if not false_pos:
                    continue
                # Evita falsos positivos de filas resumen/validación (no son filas de trabajador).
                # Ejemplo observado: fila con contador en col D y múltiples checks TRUE/FALSE.
                doc_type_cell = str(ws.cell(rr, 6).value or "").strip().upper()
                doc_num_cell = re.sub(r"\D+", "", str(ws.cell(rr, 7).value or ""))
                is_worker_row = doc_type_cell in doc_types and bool(re.fullmatch(r"\d{6,15}", doc_num_cell))
                d_counter = ws.cell(rr, 4).value
                has_counter = isinstance(d_counter, (int, float)) and float(d_counter) >= 0
                summary_like = (not is_worker_row) and has_counter and bool_count >= 5
                if summary_like:
                    continue
                hints: list[str] = []
                for cc in false_pos:
                    hint = ""
                    for hr in range(rr - 1, max(0, rr - 20), -1):
                        hv = ws.cell(hr, cc).value
                        if hv is None:
                            continue
                        hs = str(hv).strip()
                        if not hs:
                            continue
                        nh = NovaOrchestrator._norm_text(hs)
                        if nh in {"true", "false"}:
                            continue
                        if re.fullmatch(r"\d+", nh or ""):
                            continue
                        hint = hs
                        break
                    if hint:
                        hints.append(hint)
                hint_txt = ", ".join(hints[:4]).strip()
                out.append(
                    f"{sh}#L{rr}#P{','.join(str(x) for x in false_pos)}: "
                    f"{hint_txt if hint_txt else 'validaciones en incorrecto'}"
                )
                if len(out) >= max_items:
                    return out
        return out

    @staticmethod
    def _extract_activity_catalog(sheets: dict[str, list[str]]) -> dict[str, tuple[str, str]]:
        out: dict[str, tuple[str, str]] = {}
        target = ""
        for sh in sheets.keys():
            n = NovaOrchestrator._norm_text(sh)
            if "actividad" in n and "econom" in n:
                target = sh
                break
        if not target:
            return out
        for ln in sheets.get(target, []):
            parts = [p.strip() for p in str(ln).split("|")]
            if len(parts) < 3:
                continue
            risk = re.sub(r"\D", "", parts[0])
            code = re.sub(r"\D", "", parts[1])
            if not risk or not code:
                continue
            if len(code) < 6 or len(code) > 9:
                continue
            desc = parts[-1].strip()
            if desc:
                out[code] = (risk, desc)
        return out

    @staticmethod
    def _extract_orp_catalog(sheets: dict[str, list[str]]) -> dict[str, tuple[str, str]]:
        out: dict[str, tuple[str, str]] = {}
        target = ""
        for sh in sheets.keys():
            n = NovaOrchestrator._norm_text(sh)
            if "orp" in n:
                target = sh
                break
        if not target:
            return out
        for ln in sheets.get(target, []):
            parts = [p.strip() for p in str(ln).split("|")]
            if len(parts) < 3:
                continue
            risk = re.sub(r"\D", "", parts[0])
            code = re.sub(r"\D", "", parts[1])
            if not risk or not code:
                continue
            if len(code) < 3 or len(code) > 6:
                continue
            name = parts[2].strip()
            out[code] = (risk, name)
        return out

    @staticmethod
    def _format_afiliaciones_excel_audit_answer(
        *,
        question: str,
        qn: str,
        contrato_text: str,
        contrato_fields: dict[str, str],
        xlsx_sheet_names: list[str],
        contrato_source: str,
        snapshot: dict[str, Any],
    ) -> str:
        sheets = NovaOrchestrator._split_xlsx_sheets(contrato_text)
        tramite = NovaOrchestrator._guess_tramite_tipo(contrato_text)
        fecha_rad, fecha_ini = NovaOrchestrator._extract_critical_dates(contrato_text)
        false_hits = NovaOrchestrator._extract_false_evidence(sheets, max_items=12)

        empleador = str(contrato_fields.get("empresa") or "").strip()
        nit = str(contrato_fields.get("nit") or "").strip()
        actividad_emp = str(contrato_fields.get("actividad_economica") or "").strip()
        rep = str(contrato_fields.get("representante_legal") or "").strip()
        rep_doc = " ".join(
            [
                str(contrato_fields.get("tipo_doc_representante") or "").strip(),
                str(contrato_fields.get("doc_representante") or "").strip(),
            ]
        ).strip()

        sedes = snapshot.get("sedes", []) if isinstance(snapshot, dict) else []
        trabajadores = snapshot.get("trabajadores", []) if isinstance(snapshot, dict) else []
        sedes_count = len(sedes)
        trab_count = len(trabajadores)

        act_catalog = NovaOrchestrator._extract_activity_catalog(sheets)
        orp_catalog = NovaOrchestrator._extract_orp_catalog(sheets)
        act_norm = re.sub(r"\D", "", actividad_emp)
        act_match = act_catalog.get(act_norm) if act_norm else None

        lines: list[str] = []
        lines.append("1) Resumen ejecutivo")
        lines.append(f"- Documento: CPS-F-216 | Trámite inferido: {tramite}")
        lines.append(f"- Sedes detectadas: {sedes_count} | Trabajadores totales: {trab_count}")
        lines.append(f"- Validaciones FALSE detectadas: {len(false_hits)}")

        lines.append("")
        lines.append("2) Datos del empleador")
        lines.append(f"- Aportante: {empleador or 'REVISAR'}")
        lines.append(f"- NIT: {nit or 'REVISAR'}")
        lines.append(f"- Representante legal: {rep or 'REVISAR'}")
        lines.append(f"- Documento representante: {rep_doc or 'REVISAR'}")
        lines.append(f"- Actividad económica reportada: {actividad_emp or 'REVISAR'}")

        lines.append("")
        lines.append("3) Fechas críticas")
        lines.append(f"- Fecha de radicación: {fecha_rad or 'REVISAR'}")
        lines.append(f"- Fecha inicio de cobertura: {fecha_ini or 'REVISAR'}")

        lines.append("")
        lines.append("4) Conteo por sedes y trabajadores")
        lines.append(f"- Total sedes: {sedes_count}")
        lines.append(f"- Total trabajadores: {trab_count}")
        if not sedes_count or not trab_count:
            lines.append("- REVISAR: faltan datos en BD; validar carga de contrato/sedes/trabajadores.")

        lines.append("")
        lines.append("5) Validaciones (OK/REVISAR/ALERTA)")
        lines.append(f"- FALSE en validaciones: {'ALERTA' if false_hits else 'OK'}")
        lines.append(f"- Cruce actividad económica: {'OK' if act_match else 'REVISAR'}")
        lines.append(f"- Catálogo ORP cargado: {'OK' if orp_catalog else 'REVISAR'}")
        lines.append("- Subtipos: REVISAR (no se detectó evidencia suficiente de tipo/subtipo en esta lectura).")

        lines.append("")
        lines.append("6) Inconsistencias detectadas")
        if act_norm and act_match:
            lines.append(f"- Actividad {act_norm}: clase riesgo {act_match[0]} | {act_match[1][:120]}")
        elif act_norm and not act_match:
            lines.append(f"- ALERTA: código de actividad {act_norm} no encontrado en 'Listado Actividades Economicas'.")
        else:
            lines.append("- REVISAR: no se identificó código de actividad económica en hoja principal.")
        if false_hits:
            lines.append(f"- ALERTA: {len(false_hits)} fila(s) con FALSE en hojas de sede.")
        else:
            lines.append("- No se encontraron FALSE en la lectura textual del Excel.")

        lines.append("")
        lines.append("7) Evidencia")
        if contrato_source.strip():
            lines.append(f"- Fuente XLSX: {contrato_source}")
        if xlsx_sheet_names:
            lines.append(f"- Hojas detectadas: {', '.join(xlsx_sheet_names[:10])}")
        for it in false_hits[:8]:
            lines.append(f"- {it}")

        lines.append("")
        lines.append("8) Recomendación operativa final")
        lines.append("- Si hay FALSE, corregir filas en Sede y revalidar antes de generar 926.")
        lines.append("- Confirmar actividad económica y clase de riesgo contra la hoja de actividades.")
        lines.append("- Para ORP/subtipos, cargar valores de trabajadores y ejecutar cruce normativo completo.")
        return "\n".join(lines)

    def build_auditoria_xlsx_report(
        self,
        *,
        base: str = "temporal",
        lote: str = "",
        idtramite: str = "",
        source_prefix: str = "",
    ) -> dict[str, Any]:
        if Workbook is None:
            return {"ok": False, "message": "openpyxl no está disponible en backend."}
        contrato_text, contrato_source = self._pick_contrato_primary_source_text(
            question="auditoria xlsx cps f-216",
            lote=lote,
            source_prefix=source_prefix,
            top_k=60,
        )
        if not str(contrato_text or "").strip():
            return {"ok": False, "message": "No encontré contrato XLSX indexado para generar auditoría."}

        snapshot = self.db_tools.afiliaciones_dimensional_snapshot(
            base=base,
            lote=lote,
            idtramite=idtramite,
            limit=1000,
        )
        trabajadores = snapshot.get("trabajadores", []) if isinstance(snapshot, dict) else []

        sheets = self._split_xlsx_sheets(contrato_text)
        contrato_fields = self._extract_xlsx_empleador_sede(contrato_text)
        false_hits = self._extract_false_evidence(sheets, max_items=200)
        actividad_catalog = self._extract_activity_catalog(sheets)
        orp_catalog = self._extract_orp_catalog(sheets)

        wb = Workbook()
        ws_consolidado = wb.active
        ws_consolidado.title = "Consolidado_Sedes"
        ws_consolidado.append(
            [
                "sede_sr",
                "documento",
                "apellidos",
                "nombres",
                "fecha_nacimiento",
                "cargo",
                "ingreso",
                "actividad",
                "riesgo",
                "ciudad",
            ]
        )
        for t in trabajadores:
            ws_consolidado.append(
                [
                    str(t.get("sr") or ""),
                    str(t.get("documento") or ""),
                    " ".join([str(t.get("primerapellido") or "").strip(), str(t.get("segundoapellido") or "").strip()]).strip(),
                    " ".join([str(t.get("primernombre") or "").strip(), str(t.get("segundonombre") or "").strip()]).strip(),
                    str(t.get("fechanacimiento") or ""),
                    str(t.get("cargo") or ""),
                    str(t.get("ingreso") or ""),
                    str(t.get("actividad") or ""),
                    str(t.get("riesgo") or ""),
                    str(t.get("ciudad") or ""),
                ]
            )

        ws_activ = wb.create_sheet("Diccionario_Actividades")
        ws_activ.append(["codigo_actividad", "clase_riesgo", "descripcion"])
        for code, (risk, desc) in sorted(actividad_catalog.items(), key=lambda x: x[0]):
            ws_activ.append([code, risk, desc])

        ws_orp = wb.create_sheet("Maestro_Cargos")
        ws_orp.append(["codigo_orp", "clase_riesgo", "cargo"])
        for code, (risk, name) in sorted(orp_catalog.items(), key=lambda x: x[0]):
            ws_orp.append([code, risk, name])

        ws_audit = wb.create_sheet("Auditoria_Riesgos")
        ws_audit.append(
            [
                "documento",
                "trabajador",
                "cargo_trabajador",
                "riesgo_orp",
                "actividad_principal",
                "riesgo_actividad",
                "estado",
                "detalle",
            ]
        )
        act_code = re.sub(r"\D", "", str(contrato_fields.get("actividad_economica") or ""))
        act_match = actividad_catalog.get(act_code) if act_code else None
        riesgo_actividad = str(act_match[0]) if act_match else ""
        desc_actividad = str(act_match[1]) if act_match else ""

        orp_by_name = {
            self._norm_text(v[1]): str(v[0])
            for v in orp_catalog.values()
            if str(v[1]).strip()
        }
        for t in trabajadores:
            doc = str(t.get("documento") or "")
            nombre = " ".join(
                [
                    str(t.get("primerapellido") or "").strip(),
                    str(t.get("segundoapellido") or "").strip(),
                    str(t.get("primernombre") or "").strip(),
                    str(t.get("segundonombre") or "").strip(),
                ]
            ).strip()
            cargo = str(t.get("cargo") or "")
            cargo_key = self._norm_text(cargo)
            riesgo_orp = orp_by_name.get(cargo_key, "")
            estado = "REVISAR"
            detalle = "Sin coincidencia exacta de cargo en catálogo ORP."
            if riesgo_orp:
                estado = "OK"
                detalle = "Cargo validado contra ORP."
                if riesgo_actividad and riesgo_orp.isdigit() and riesgo_actividad.isdigit() and int(riesgo_orp) > int(riesgo_actividad):
                    estado = "ALERTA"
                    detalle = "Riesgo ORP superior al riesgo de la actividad principal."
            ws_audit.append(
                [
                    doc,
                    nombre,
                    cargo,
                    riesgo_orp,
                    act_code,
                    riesgo_actividad,
                    estado,
                    detalle,
                ]
            )

        ws_meta = wb.create_sheet("Informe_Validaciones")
        ws_meta.append(["clave", "valor"])
        ws_meta.append(["lote", lote])
        ws_meta.append(["idtramite", idtramite])
        ws_meta.append(["empleador", str(contrato_fields.get("empresa") or "")])
        ws_meta.append(["nit", str(contrato_fields.get("nit") or "")])
        ws_meta.append(["actividad_principal_codigo", act_code])
        ws_meta.append(["actividad_principal_descripcion", desc_actividad])
        ws_meta.append(["false_detectados", str(len(false_hits))])
        ws_meta.append(["fuente_xlsx", contrato_source or "N/D"])
        for idx, item in enumerate(false_hits[:120], start=1):
            ws_meta.append([f"false_evidencia_{idx}", item])

        safe_lote = re.sub(r"[^0-9A-Za-z_-]+", "", str(lote or "")) or "lote"
        safe_tr = re.sub(r"[^0-9A-Za-z_-]+", "", str(idtramite or "")) or "tr"
        filename = f"NOVA_Auditoria_{safe_lote}_{safe_tr}.xlsx"
        out_dir = Path(tempfile.gettempdir()) / "nova_exports"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / filename
        wb.save(str(out_path))
        return {
            "ok": True,
            "path": str(out_path),
            "filename": filename,
            "meta": {
                "trabajadores": len(trabajadores),
                "actividades": len(actividad_catalog),
                "orp": len(orp_catalog),
                "false_hits": len(false_hits),
            },
        }

    @staticmethod
    def _find_sheet_by_keywords(sheets: dict[str, list[str]], keys: list[str]) -> str:
        if not sheets:
            return ""
        for sh in sheets.keys():
            n = NovaOrchestrator._norm_text(sh)
            if all(k in n for k in keys):
                return sh
        return ""

    @staticmethod
    def _topic_score(passes: list[bool]) -> int:
        if not passes:
            return 0
        ok = sum(1 for p in passes if p)
        return int(round((ok * 100.0) / float(len(passes))))

    def knowledge_test_from_excel(self, *, excel_filename: str, excel_bytes: bytes) -> dict[str, Any]:
        xlsx_text = self._xlsx_bytes_to_text_snapshot(excel_bytes)
        if not xlsx_text:
            return {"ok": False, "message": "No se pudo leer el Excel."}

        sheets = self._split_xlsx_sheets(xlsx_text)
        sheet_names = list(sheets.keys())
        fields = self._extract_xlsx_empleador_sede(xlsx_text)
        false_hits = self._extract_false_evidence_from_excel(excel_bytes, max_items=40)
        if not false_hits:
            false_hits = self._extract_false_evidence(sheets, max_items=40)
        false_hits_relevant: list[str] = []
        false_hits_ignored: list[str] = []
        for hit in false_hits:
            parsed = self._parse_false_evidence_item(hit)
            sheet = str(parsed.get("sheet") or "")
            row = str(parsed.get("row") or "")
            pos = list(parsed.get("false_positions") or [])
            raw_values = str(parsed.get("raw_values") or "")
            n_sheet = self._norm_text(sheet)
            is_sede_sheet = ("sede" in n_sheet) and ("trabajador" in n_sheet)
            if not is_sede_sheet:
                false_hits_relevant.append(hit)
                continue
            rows_in_sheet = sheets.get(sheet, [])
            has_workers = any(self._is_worker_data_line(r) for r in rows_in_sheet)
            is_placeholder = self._is_placeholder_false_row(raw_values)
            is_summary_validation = self._is_summary_validation_false_row(raw_values)
            starts_with_zero_counter = bool(re.match(r"^\s*0\s*\|", raw_values))
            has_doc_like = bool(re.search(r"\b\d{6,12}\b", raw_values))
            n_raw = self._norm_text(raw_values)
            has_optional_subtipo = "subtipo de afiliado" in n_raw or "subtipo afiliado" in n_raw
            field_hints: list[str] = []
            try:
                row_idx = int(row or "0")
            except Exception:
                row_idx = 0
            if row_idx > 0 and pos:
                field_hints = self._infer_false_field_hints(rows_in_sheet, row_idx, pos)
            has_optional_hints_only = bool(field_hints) and all(self._is_optional_false_hint(h) for h in field_hints)
            if (
                ((not has_workers) and is_placeholder)
                or (is_placeholder and starts_with_zero_counter and (not has_doc_like))
                or is_summary_validation
                or has_optional_subtipo
                or has_optional_hints_only
            ):
                false_hits_ignored.append(hit)
            else:
                false_hits_relevant.append(hit)
        activity_catalog = self._extract_activity_catalog(sheets)
        orp_catalog = self._extract_orp_catalog(sheets)

        sh_act = self._find_sheet_by_keywords(sheets, ["actividad", "econom"])
        sh_orp = self._find_sheet_by_keywords(sheets, ["orp"])
        sh_cot = self._find_sheet_by_keywords(sheets, ["cotizante"])
        if not sh_cot:
            for sh in sheets.keys():
                n = self._norm_text(sh)
                if ("tipo" in n and "trabajador" in n and ("cotiz" in n or "cotz" in n)):
                    sh_cot = sh
                    break
        sh_sedes_inst = self._find_sheet_by_keywords(sheets, ["instructivo", "sede"])
        sh_form_inst = self._find_sheet_by_keywords(sheets, ["instructivo", "formulario", "afili"])
        sh_ind_723 = self._find_sheet_by_keywords(sheets, ["independ", "723"])

        cot_rows = len(sheets.get(sh_cot, [])) if sh_cot else 0
        sedes_inst_rows = len(sheets.get(sh_sedes_inst, [])) if sh_sedes_inst else 0
        form_inst_rows = len(sheets.get(sh_form_inst, [])) if sh_form_inst else 0
        ind_723_rows = len(sheets.get(sh_ind_723, [])) if sh_ind_723 else 0

        act_risks = {str(v[0]) for v in activity_catalog.values() if str(v[0]).isdigit()}
        orp_risks = {str(v[0]) for v in orp_catalog.values() if str(v[0]).isdigit()}
        has_risk_scale = any(x in act_risks for x in {"1", "2", "3", "4", "5"})
        has_orp_scale = any(x in orp_risks for x in {"1", "2", "3", "4", "5"})

        topic_actividades_checks = [
            bool(sh_act),
            len(activity_catalog) >= 100,
            has_risk_scale,
        ]
        topic_orp_checks = [
            bool(sh_orp),
            len(orp_catalog) >= 100,
            has_orp_scale,
        ]
        topic_cotizantes_checks = [
            bool(sh_cot),
            cot_rows >= 20,
            ("cotizante" in self._norm_text("\n".join(sheets.get(sh_cot, [])[:60])) if sh_cot else False),
        ]
        topic_sedes_checks = [
            bool(sh_sedes_inst),
            sedes_inst_rows >= 40,
            ("centros de trabajo" in self._norm_text("\n".join(sheets.get(sh_sedes_inst, [])[:120])) if sh_sedes_inst else False),
        ]
        topic_ind_checks = [
            bool(sh_ind_723),
            ind_723_rows >= 15,
            ("independiente" in self._norm_text("\n".join(sheets.get(sh_ind_723, [])[:120])) if sh_ind_723 else False),
        ]
        topic_form_checks = [
            bool(sh_form_inst),
            form_inst_rows >= 60,
            ("datos del tramite" in self._norm_text("\n".join(sheets.get(sh_form_inst, [])[:120])) if sh_form_inst else False),
        ]

        by_topic = {
            "actividades_economicas": {
                "score": self._topic_score(topic_actividades_checks),
                "sheet": sh_act,
                "catalog_size": len(activity_catalog),
            },
            "codigos_orp": {
                "score": self._topic_score(topic_orp_checks),
                "sheet": sh_orp,
                "catalog_size": len(orp_catalog),
            },
            "tipos_cotizante": {
                "score": self._topic_score(topic_cotizantes_checks),
                "sheet": sh_cot,
                "rows": cot_rows,
            },
            "instructivo_sedes": {
                "score": self._topic_score(topic_sedes_checks),
                "sheet": sh_sedes_inst,
                "rows": sedes_inst_rows,
            },
            "independientes_723": {
                "score": self._topic_score(topic_ind_checks),
                "sheet": sh_ind_723,
                "rows": ind_723_rows,
            },
            "instructivo_formulario": {
                "score": self._topic_score(topic_form_checks),
                "sheet": sh_form_inst,
                "rows": form_inst_rows,
            },
        }

        topic_scores = [int(v.get("score") or 0) for v in by_topic.values()]
        score_global = int(round(sum(topic_scores) / max(1, len(topic_scores))))

        faltantes: list[str] = []
        if not sh_act or len(activity_catalog) < 100:
            faltantes.append("Revisar/ingestar hoja de 'Listado de Actividades Económicas'.")
        if not sh_orp or len(orp_catalog) < 100:
            faltantes.append("Revisar/ingestar hoja de 'Codigos ORP'.")
        if not sh_cot:
            faltantes.append("Falta hoja de 'Códigos de tipo de trabajador (cotizantes)'.")
        if not sh_sedes_inst:
            faltantes.append("Falta hoja de 'Instructivo Sedes'.")
        if not sh_ind_723:
            faltantes.append("Falta hoja 'INDEPENDIENTES 723'.")
        if not sh_form_inst:
            faltantes.append("Falta hoja 'Instructivo Formulario Afiliación y novedades'.")

        actividad_emp = re.sub(r"\D", "", str(fields.get("actividad_economica") or ""))
        act_match = activity_catalog.get(actividad_emp) if actividad_emp else None
        riesgo_max_act = max([int(v[0]) for v in activity_catalog.values() if str(v[0]).isdigit()], default=0)
        riesgo_max_orp = max([int(v[0]) for v in orp_catalog.values() if str(v[0]).isdigit()], default=0)
        target_false = false_hits_relevant[0] if false_hits_relevant else (false_hits[0] if false_hits else "")
        false_primary = self._parse_false_evidence_item(target_false) if target_false else {}
        false_sheet = str(false_primary.get("sheet") or "")
        false_row = str(false_primary.get("row") or "")
        false_pos = list(false_primary.get("false_positions") or [])
        if len(false_hits_relevant) > 0:
            false_gate_message = (
                f"Se detectaron {len(false_hits_relevant)} FALSE bloqueante(s). "
                "Debes corregirlos antes de continuar."
            )
        elif len(false_hits_ignored) > 0:
            false_gate_message = (
                f"Se detectaron {len(false_hits_ignored)} FALSE informativo(s) en plantilla/sede sin datos; "
                "no bloquean este lote."
            )
        else:
            false_gate_message = "No se detectaron FALSE en el Excel."

        preguntas_control = [
            {
                "tema": "actividades_economicas",
                "pregunta": "¿Cuál es la clase de riesgo de la actividad económica del empleador?",
                "respuesta_nova": (
                    f"Encontré el código {actividad_emp} y en catálogo corresponde a riesgo {act_match[0]} ({act_match[1][:80]})."
                    if actividad_emp and act_match
                    else "No pude validar la actividad económica del empleador contra el catálogo."
                ),
                "interpretacion": (
                    "OK: la actividad económica quedó validada con tabla oficial."
                    if actividad_emp and act_match
                    else "REVISAR: confirma y corrige el código de actividad en el formulario principal antes de continuar."
                ),
            },
            {
                "tema": "actividades_economicas",
                "pregunta": "¿Cuál es el riesgo máximo en el listado de actividades económicas?",
                "respuesta_nova": f"En este archivo, el riesgo más alto encontrado en el catálogo de actividades es {str(riesgo_max_act or 'N/D')}.",
                "interpretacion": "Dato de referencia del catálogo cargado para este lote; no implica por sí solo un error.",
            },
            {
                "tema": "codigos_orp",
                "pregunta": "¿Cuántos códigos ORP detectó NOVA en la hoja?",
                "respuesta_nova": f"Se detectaron {len(orp_catalog)} códigos ORP en la hoja.",
                "interpretacion": "OK: ya se puede cruzar cargo del trabajador vs nivel de riesgo ORP.",
            },
            {
                "tema": "codigos_orp",
                "pregunta": "¿Cuál es el riesgo máximo detectado en ORP?",
                "respuesta_nova": f"El riesgo máximo encontrado en ORP es {str(riesgo_max_orp or 'N/D')}.",
                "interpretacion": "Se usa para alertar cargos con riesgo alto frente a la actividad económica declarada.",
            },
            {
                "tema": "tipos_cotizante",
                "pregunta": "¿Existe hoja de cotizantes y cuántas filas útiles tiene?",
                "respuesta_nova": f"{'Sí' if bool(sh_cot) else 'No'}, con {cot_rows} filas útiles.",
                "interpretacion": (
                    "OK: base disponible para validar tipo/subtipo de cotizante."
                    if bool(sh_cot) and cot_rows > 0
                    else "REVISAR: falta base de cotizantes para validar tipos/subtipos."
                ),
            },
            {
                "tema": "instructivo_sedes",
                "pregunta": "¿Existe Instructivo Sedes y menciona centros de trabajo?",
                "respuesta_nova": (
                    "Sí, el instructivo de sedes está presente y sí menciona centros de trabajo."
                    if topic_sedes_checks[0] and topic_sedes_checks[2]
                    else "No completo: no encontré evidencia suficiente del instructivo de sedes."
                ),
                "interpretacion": (
                    "OK: se pueden validar campos obligatorios de sede, centro y trabajador."
                    if topic_sedes_checks[0] and topic_sedes_checks[2]
                    else "REVISAR: sin instructivo completo de sedes, la validación queda incompleta."
                ),
            },
            {
                "tema": "independientes_723",
                "pregunta": "¿Existe hoja INDEPENDIENTES 723 y contiene datos?",
                "respuesta_nova": f"{'Sí' if bool(sh_ind_723) else 'No'}, con {ind_723_rows} filas.",
                "interpretacion": (
                    "OK: se pueden aplicar reglas de independientes voluntarios (723)."
                    if bool(sh_ind_723) and ind_723_rows > 0
                    else "Si el lote no maneja independientes, no bloquea; si sí maneja, debe corregirse."
                ),
            },
            {
                "tema": "calidad_datos",
                "pregunta": "¿Cuántas validaciones FALSE detectó en el Excel?",
                "respuesta_nova": f"Detecté {len(false_hits)} validación(es) en FALSE.",
                "interpretacion": (
                    f"REVISAR: {len(false_hits_relevant)} bloqueante(s) y {len(false_hits_ignored)} informativa(s). Corrige los bloqueantes y repite Precheck."
                    if len(false_hits_relevant) > 0
                    else (
                        f"Sin bloqueos por FALSE. Se detectaron {len(false_hits_ignored)} caso(s) informativo(s) (p. ej. sede vacía)."
                        if len(false_hits_ignored) > 0
                        else "Sin bloqueos por FALSE en la revisión actual."
                    )
                ),
            },
            {
                "tema": "calidad_datos",
                "pregunta": "¿Cuántas validaciones FALSE son bloqueantes vs informativas?",
                "respuesta_nova": f"Bloqueantes: {len(false_hits_relevant)} | Informativas: {len(false_hits_ignored)}.",
                "interpretacion": (
                    "Si bloqueantes = 0, el lote puede continuar por este criterio."
                    if len(false_hits_relevant) == 0
                    else "Hay bloqueos por FALSE: corrige esas filas antes de pasar al flujo operativo."
                ),
            },
            {
                "tema": "calidad_datos",
                "pregunta": "¿Dónde está la primera validación en FALSE detectada?",
                "respuesta_nova": (
                    f"Hoja '{false_sheet}', fila {false_row}, columnas de validación {', '.join(str(x) for x in false_pos)}."
                    if target_false and false_sheet and false_row
                    else "No se detectaron filas con FALSE."
                ),
                "interpretacion": (
                    "Ataca primero esa fila para desbloquear el lote más rápido."
                    if len(false_hits_relevant) > 0
                    else (
                        "Es una alerta informativa (no bloqueante) por regla de sede vacía."
                        if len(false_hits_ignored) > 0
                        else "No requiere corrección por FALSE."
                    )
                ),
            },
            {
                "tema": "calidad_datos",
                "pregunta": "¿Cuál es la primera evidencia FALSE bloqueante?",
                "respuesta_nova": (
                    str(false_hits_relevant[0])
                    if false_hits_relevant
                    else "No hay evidencia FALSE bloqueante."
                ),
                "interpretacion": (
                    "Corrige esta fila primero."
                    if false_hits_relevant
                    else "No requiere corrección por FALSE."
                ),
            },
            {
                "tema": "calidad_datos",
                "pregunta": "¿El lote puede pasar a ejecución operativa con el estado actual?",
                "respuesta_nova": (
                    "No. Hay inconsistencias de calidad de datos que deben corregirse antes de ejecutar el flujo."
                    if false_hits_relevant
                    else "Sí. No hay bloqueos de calidad de datos en esta revisión (las alertas, si existen, son informativas)."
                ),
                "interpretacion": (
                    "Mantener el lote en corrección hasta dejar validaciones en TRUE."
                    if false_hits_relevant
                    else "Puede continuar a Paso 1."
                ),
            },
            {
                "tema": "instructivo_formulario",
                "pregunta": "¿Está presente el instructivo del formulario de afiliación y novedades?",
                "respuesta_nova": (
                    f"Sí, hoja detectada: {sh_form_inst}."
                    if sh_form_inst
                    else "No, no encontré la hoja de instructivo del formulario."
                ),
                "interpretacion": (
                    "OK para validar reglas del formulario principal."
                    if sh_form_inst
                    else "REVISAR: falta base normativa del formulario."
                ),
            },
            {
                "tema": "instructivo_sedes",
                "pregunta": "¿Está presente el instructivo de sedes para validar centro y trabajadores?",
                "respuesta_nova": (
                    f"Sí, hoja detectada: {sh_sedes_inst}."
                    if sh_sedes_inst
                    else "No, no encontré la hoja de instructivo de sedes."
                ),
                "interpretacion": (
                    "OK para validar estructura sede/centro/trabajador."
                    if sh_sedes_inst
                    else "REVISAR: falta base normativa de sedes."
                ),
            },
        ]

        return {
            "ok": True,
            "excel": excel_filename,
            "score_global": score_global,
            "decision": "OK" if score_global >= 80 else ("REVISAR" if score_global >= 60 else "CRITICO"),
            "by_topic": by_topic,
            "hallazgos": {
                "sheet_count": len(sheet_names),
                "false_hits": len(false_hits),
                "false_hits_relevant": len(false_hits_relevant),
                "false_hits_ignored": len(false_hits_ignored),
                "false_gate_message": false_gate_message,
                "sheet_names": sheet_names[:40],
            },
            "empresa": {
                "razon_social": str(fields.get("empresa") or ""),
                "nit": str(fields.get("nit") or ""),
                "actividad_economica": str(fields.get("actividad_economica") or ""),
            },
            "faltantes_recomendados": faltantes,
            "preguntas_control": preguntas_control,
            "false_evidence": false_hits_relevant[:20],
            "false_evidence_ignored": false_hits_ignored[:20],
        }

    @staticmethod
    def _xlsx_bytes_to_text_snapshot(content: bytes) -> str:
        if load_workbook is None:
            return ""
        if not content:
            return ""
        try:
            wb = load_workbook(io.BytesIO(content), data_only=True, read_only=True)
        except Exception:
            return ""
        chunks: list[str] = []
        for sh in wb.sheetnames:
            chunks.append(f"# Hoja: {sh}")
            ws = wb[sh]
            row_count = 0
            for row in ws.iter_rows(values_only=True):
                vals = [str(v).strip() for v in row if v is not None and str(v).strip()]
                if not vals:
                    continue
                chunks.append(" | ".join(vals))
                row_count += 1
                if row_count >= 600:
                    break
            chunks.append("")
        return "\n".join(chunks).strip()

    def generate_clean_from_excel(self, *, excel_filename: str, excel_bytes: bytes) -> dict[str, Any]:
        if load_workbook is None:
            return {"ok": False, "message": "openpyxl no está disponible en backend."}
        if not excel_bytes:
            return {"ok": False, "message": "El Excel está vacío."}
        try:
            wb = load_workbook(io.BytesIO(excel_bytes), data_only=True, read_only=True)
        except Exception:
            return {"ok": False, "message": "No se pudo leer el Excel."}

        def _norm(s: str) -> str:
            return re.sub(r"\s+", " ", str(s or "").strip().lower())

        def _cell_to_txt(v: Any, *, force_int_float: bool = False) -> str:
            if v is None:
                return "NULL"
            if isinstance(v, bool):
                return "TRUE" if v else "FALSE"
            if isinstance(v, datetime):
                return v.strftime("%Y-%m-%dT%H:%M:%S")
            if isinstance(v, float):
                if abs(v - int(v)) < 1e-9:
                    return str(int(v))
                if force_int_float:
                    # En hojas de sedes/independientes se esperan enteros en campos
                    # operativos (salario, IBC, etc). Si vienen decimales "largos"
                    # por ruido de origen, conservamos solo parte entera.
                    return str(int(v))
                return str(v).rstrip("0").rstrip(".")
            txt = str(v).replace("\n", " ").replace("\r", " ").strip()
            return txt if txt else "NULL"

        def _sheet_to_lines(ws: Any, *, force_int_float: bool = False) -> list[str]:
            out: list[str] = []
            for row in ws.iter_rows(values_only=True):
                vals = [_cell_to_txt(v, force_int_float=force_int_float) for v in row]
                first = -1
                last = -1
                for i, x in enumerate(vals):
                    if x != "NULL":
                        if first < 0:
                            first = i
                        last = i
                if first < 0 or last < 0:
                    continue
                out.append("|".join(vals[first : last + 1]))
            return out

        def _parse_money_int(v: Any) -> int:
            if v is None:
                return 0
            if isinstance(v, (int, float)):
                return int(float(v))
            txt = str(v).strip()
            if not txt or txt.upper() == "NULL":
                return 0
            if "." in txt or "," in txt:
                txt = re.split(r"[.,]", txt)[0]
            digits = "".join(ch for ch in txt if ch.isdigit())
            if not digits:
                return 0
            try:
                return int(digits)
            except Exception:
                return 0

        def _expected_stats_from_sheet(ws: Any) -> dict[str, int]:
            # Fuente de verdad por hoja: filas de trabajadores (doc/id) y salario.
            # En los XLSX de contrato actuales: doc=col 6, id=col 7, salario=col 19.
            docs = set(TIPOS_DOCUMENTO_TRABAJADOR)
            afiliados = 0
            salarios = 0
            max_scan = int(ws.max_row or 0)
            for rr in range(1, max_scan + 1):
                doc_type = str(ws.cell(rr, 6).value or "").strip().upper()
                if doc_type not in docs:
                    continue
                doc_raw = re.sub(r"\D+", "", str(ws.cell(rr, 7).value or ""))
                if not re.fullmatch(r"\d{6,15}", doc_raw):
                    continue
                afiliados += 1
                salarios += _parse_money_int(ws.cell(rr, 19).value)
            return {"afiliados": afiliados, "salarios": salarios}

        def _analyze_worker_sheet(ws: Any, sheet_name: str) -> dict[str, Any]:
            docs = set(TIPOS_DOCUMENTO_TRABAJADOR)
            lines: list[str] = []
            expected_afiliados = 0
            expected_salarios = 0
            seen_hits: list[dict[str, Any]] = []
            for rr, row in enumerate(ws.iter_rows(values_only=True), start=1):
                vals = [_cell_to_txt(v, force_int_float=True) for v in row]
                first = -1
                last = -1
                for i, x in enumerate(vals):
                    if x != "NULL":
                        if first < 0:
                            first = i
                        last = i
                if first >= 0 and last >= 0:
                    lines.append("|".join(vals[first : last + 1]))

                doc_type = str(row[5] if len(row) > 5 and row[5] is not None else "").strip().upper()
                if doc_type not in docs:
                    continue
                doc_num = _norm_doc(row[6] if len(row) > 6 else "")
                if not re.fullmatch(r"\d{6,15}", doc_num):
                    continue
                expected_afiliados += 1
                expected_salarios += _parse_money_int(row[18] if len(row) > 18 else "")
                seen_hits.append(
                    {
                        "sheet": sheet_name,
                        "row": rr,
                        "tipodocumento": doc_type,
                        "numerodocumento": doc_num,
                    }
                )
            return {
                "lines": lines,
                "expected": {"afiliados": expected_afiliados, "salarios": expected_salarios},
                "seen_hits": seen_hits,
            }

        def _generated_stats_from_lines(lines: list[str]) -> dict[str, int]:
            docs = set(TIPOS_DOCUMENTO_TRABAJADOR)
            afiliados = 0
            salarios = 0
            for ln in lines:
                parts = [str(x).strip() for x in str(ln or "").split("|")]
                if len(parts) < 31:
                    continue
                if parts[2].upper() not in docs:
                    continue
                if not re.fullmatch(r"\d{6,15}", re.sub(r"\D+", "", parts[3] or "")):
                    continue
                afiliados += 1
                salarios += _parse_money_int(parts[15] if len(parts) > 15 else "")
            return {"afiliados": afiliados, "salarios": salarios}

        sheet_names = list(wb.sheetnames)
        if not sheet_names:
            return {"ok": False, "message": "Excel sin hojas."}

        # La hoja principal se busca en TRES pasadas, y el orden importa. La plantilla
        # real trae una hoja "Instructivo Formulario Afili." ANTES del formulario, y esa
        # tambien contiene "formulario" y "afili": con una sola pasada laxa ganaba el
        # instructivo, el clean salia de ahi -con contenido, pero sin ninguna de las
        # etiquetas que busca el parser- y la importacion del empleador fallaba con los
        # doce campos vacios a la vez.
        main_sheet = ""
        for sh in sheet_names:                                  # 1) nombre exacto
            if _norm(sh) == "formulario de afiliacion":
                main_sheet = sh
                break
        if not main_sheet:
            for sh in sheet_names:                              # 2) "formulario de afili..."
                if "formulario de afili" in _norm(sh):
                    main_sheet = sh
                    break
        if not main_sheet:
            for sh in sheet_names:                              # 3) laxa, sin instructivo/indice
                n = _norm(sh)
                if "instructivo" in n or "indice" in n:
                    continue
                if "formulario" in n and "afili" in n:
                    main_sheet = sh
                    break
        if not main_sheet:
            main_sheet = sheet_names[0]

        worker_sheets: list[str] = []
        indep_sheet = ""
        for sh in sheet_names:
            n = _norm(sh)
            if "sede" in n and "trabajador" in n:
                worker_sheets.append(sh)
            if ("independiente" in n and "723" in n) or n == "independientes 723":
                indep_sheet = sh
        if not worker_sheets:
            worker_sheets = [main_sheet]

        contrato_lines = _sheet_to_lines(wb[main_sheet], force_int_float=False)
        trabajadores_lines: list[str] = []
        trabajadores_multi: list[dict[str, Any]] = []
        quality_rows: list[dict[str, Any]] = []
        total_expected_afiliados = 0
        total_expected_salarios = 0
        total_generated_afiliados = 0
        total_generated_salarios = 0
        seen_docs_global: dict[str, list[dict[str, Any]]] = {}

        def _norm_doc(v: Any) -> str:
            return re.sub(r"\D+", "", str(v or ""))

        for sh in worker_sheets:
            analyzed = _analyze_worker_sheet(wb[sh], sh)
            sheet_lines = list(analyzed.get("lines") or [])
            trabajadores_lines.extend(sheet_lines)
            expected = analyzed.get("expected") or {"afiliados": 0, "salarios": 0}
            generated = _generated_stats_from_lines(sheet_lines)
            total_expected_afiliados += int(expected["afiliados"])
            total_expected_salarios += int(expected["salarios"])
            total_generated_afiliados += int(generated["afiliados"])
            total_generated_salarios += int(generated["salarios"])
            for hit in list(analyzed.get("seen_hits") or []):
                key = f"{hit.get('tipodocumento')}|{hit.get('numerodocumento')}"
                prev = seen_docs_global.get(key) or []
                prev.append(hit)
                seen_docs_global[key] = prev
            sede_match = re.search(r"sede\s*0*(\d+)", sh, flags=re.IGNORECASE)
            sede_num = int(sede_match.group(1)) if sede_match else (len(trabajadores_multi) + 1)
            afiliados_ok = int(expected["afiliados"]) == int(generated["afiliados"])
            salarios_ok = int(expected["salarios"]) == int(generated["salarios"])
            quality_rows.append(
                {
                    "sede": str(sede_num),
                    "sheet": sh,
                    "expected_afiliados": int(expected["afiliados"]),
                    "generated_afiliados": int(generated["afiliados"]),
                    "expected_salarios": int(expected["salarios"]),
                    "generated_salarios": int(generated["salarios"]),
                    "afiliados_ok": afiliados_ok,
                    "salarios_ok": salarios_ok,
                    "status": "OK" if (afiliados_ok and salarios_ok) else "ERROR",
                }
            )
            trabajadores_multi.append(
                {
                    "sheet": sh,
                    "filename": f"Sede{sede_num:02d}-Trabajadores_{safe_name if 'safe_name' in locals() else 'contrato'}_clean.txt",
                    "lines": len(sheet_lines),
                    "content": "\n".join(sheet_lines),
                    "preview": sheet_lines[:12],
                }
            )

        independientes_block: dict[str, Any] | None = None
        if indep_sheet:
            indep_lines = _sheet_to_lines(wb[indep_sheet], force_int_float=True)
            if indep_lines:
                independientes_block = {
                    "sheet": indep_sheet,
                    "filename": f"independientes_{safe_name if 'safe_name' in locals() else 'contrato'}_clean.txt",
                    "lines": len(indep_lines),
                    "content": "\n".join(indep_lines),
                    "preview": indep_lines[:12],
                }

        if not contrato_lines:
            return {"ok": False, "message": f"No se pudo generar contrato clean desde hoja '{main_sheet}'."}
        if not trabajadores_lines:
            return {"ok": False, "message": "No se pudo generar archivo de trabajadores clean desde hojas de sede."}

        safe_name = re.sub(r"[^0-9A-Za-z_-]+", "", Path(str(excel_filename or "contrato")).stem) or "contrato"
        contrato_name = f"contrato_{safe_name}_clean.txt"
        trabajadores_name = f"Sede01-Trabajadores_{safe_name}_clean.txt"
        contrato_content = "\n".join(contrato_lines)
        trabajadores_content = "\n".join(trabajadores_lines)
        # Recalcular nombres con safe_name definitivo.
        for i, item in enumerate(trabajadores_multi, start=1):
            sede_match = re.search(r"sede\s*0*(\d+)", str(item.get("sheet") or ""), flags=re.IGNORECASE)
            sede_num = int(sede_match.group(1)) if sede_match else i
            item["filename"] = f"Sede{sede_num:02d}-Trabajadores_{safe_name}_clean.txt"
        if independientes_block is not None:
            independientes_block["filename"] = f"independientes_{safe_name}_clean.txt"
        duplicate_groups: list[dict[str, Any]] = []
        for key, hits in seen_docs_global.items():
            if len(hits) <= 1:
                continue
            tdoc, ndoc = key.split("|", 1)
            duplicate_groups.append(
                {
                    "tipodocumento": tdoc,
                    "numerodocumento": ndoc,
                    "count": len(hits),
                    "occurrences": hits,
                }
            )
        totals_ok = (total_expected_afiliados == total_generated_afiliados) and (total_expected_salarios == total_generated_salarios)
        quality_ok = totals_ok and all(str(x.get("status")) == "OK" for x in quality_rows) and (len(duplicate_groups) == 0)
        return {
            "ok": True,
            "excel": excel_filename,
            "source_sheets": {"main_sheet": main_sheet, "worker_sheets": worker_sheets},
            "contrato_clean": {
                "filename": contrato_name,
                "lines": len(contrato_lines),
                "content": contrato_content,
                "preview": contrato_lines[:12],
            },
            "trabajadores_clean": {
                "filename": trabajadores_name,
                "lines": len(trabajadores_lines),
                "content": trabajadores_content,
                "preview": trabajadores_lines[:12],
            },
            "trabajadores_clean_multi": trabajadores_multi,
            "independientes_clean": independientes_block,
            "quality_controls": {
                "ok": quality_ok,
                "by_sede": quality_rows,
                "duplicates": {
                    "ok": len(duplicate_groups) == 0,
                    "count": len(duplicate_groups),
                    "items": duplicate_groups[:50],
                },
                "totals": {
                    "expected_afiliados": total_expected_afiliados,
                    "generated_afiliados": total_generated_afiliados,
                    "expected_salarios": total_expected_salarios,
                    "generated_salarios": total_generated_salarios,
                    "afiliados_ok": total_expected_afiliados == total_generated_afiliados,
                    "salarios_ok": total_expected_salarios == total_generated_salarios,
                },
            },
        }

    @staticmethod
    def _extract_required_document_rules(sheets: dict[str, list[str]]) -> list[dict[str, Any]]:
        categories = [
            ("formulario_afiliacion", "Formulario de afiliación", ["formulario", "afiliacion"], True),
            ("anexo_sedes", "Anexo de sedes y centros", ["anexo", "sedes", "centros de trabajo"], True),
            ("listado_trabajadores", "Listado de trabajadores", ["listado", "trabajadores"], True),
            ("camara_comercio", "Cámara y comercio", ["camara", "comercio"], True),
            ("rut", "RUT", ["rut"], True),
            ("cedula_representante", "Cédula representante legal", ["cedula", "representante legal"], True),
            ("cert_arl_anterior", "Certificación ARL anterior", ["arl anterior", "certificacion de afiliacion"], False),
            ("carta_desafiliacion", "Carta desafiliación ARL anterior", ["carta de desafiliacion"], False),
            ("intermediacion", "Carta de intermediación", ["intermediacion"], False),
            ("sarlaft", "Consulta listas SARLAFT", ["sarlaft"], False),
        ]
        selected: dict[str, dict[str, Any]] = {}
        for sh, rows in sheets.items():
            nsh = NovaOrchestrator._norm_text(sh)
            if ("instructivo" not in nsh) and ("anexo" not in nsh) and ("formulario" not in nsh):
                continue
            for ln in rows:
                nln = NovaOrchestrator._norm_text(ln)
                if len(nln) < 8:
                    continue
                for key, label, kws, critical in categories:
                    if any(kw in nln for kw in kws):
                        # "si aplica" no bloquea.
                        is_critical = critical and ("si aplica" not in nln)
                        selected[key] = {
                            "key": key,
                            "label": label,
                            "keywords": kws,
                            "critical": is_critical,
                            "source_line": ln[:240],
                        }
        if selected:
            return list(selected.values())
        # Fallback mínimo si no se detectan reglas en instructivos.
        return [
            {"key": "formulario_afiliacion", "label": "Formulario de afiliación", "keywords": ["formulario", "afiliacion"], "critical": True, "source_line": "fallback"},
            {"key": "listado_trabajadores", "label": "Listado de trabajadores", "keywords": ["listado", "trabajadores"], "critical": True, "source_line": "fallback"},
            {"key": "rut", "label": "RUT", "keywords": ["rut"], "critical": True, "source_line": "fallback"},
            {"key": "cedula_representante", "label": "Cédula representante legal", "keywords": ["cedula", "representante legal"], "critical": True, "source_line": "fallback"},
        ]

    @staticmethod
    def _first_keyword_evidence(text: str, keywords: list[str]) -> str:
        lines = [str(x).strip() for x in str(text or "").splitlines() if str(x).strip()]
        for ln in lines:
            nln = NovaOrchestrator._norm_text(ln)
            if any(kw in nln for kw in keywords):
                return ln[:240]
        compact = " ".join(str(text or "").split())
        return compact[:240]

    @staticmethod
    def _parse_false_evidence_item(item: str) -> dict[str, Any]:
        src = str(item or "").strip()
        m = re.match(r"^(.*?)#L(\d+)(?:#P([0-9,]+))?:\s*(.*)$", src)
        if not m:
            return {
                "sheet": "",
                "row": "",
                "false_positions": [],
                "false_count": 0,
                "raw_values": "",
            }
        sheet = str(m.group(1) or "").strip()
        row = str(m.group(2) or "").strip()
        raw_pos = str(m.group(3) or "").strip()
        raw_values = str(m.group(4) or "").strip()
        false_positions: list[int] = []
        if raw_pos:
            for tok in raw_pos.split(","):
                tok = tok.strip()
                if tok.isdigit():
                    false_positions.append(int(tok))
        if not false_positions:
            parts = [p.strip() for p in raw_values.split("|")] if raw_values else []
            for idx, p in enumerate(parts, start=1):
                pn = NovaOrchestrator._norm_text(p)
                # Soporta celdas truncadas por extracción (ej: "Fal", "Fals")
                # para ubicar mejor el campo inválido real.
                if pn in {"false", "falso"} or pn.startswith("fal"):
                    false_positions.append(idx)
        return {
            "sheet": sheet,
            "row": row,
            "false_positions": false_positions,
            "false_count": len(false_positions),
            "raw_values": raw_values[:260],
        }

    @staticmethod
    def _infer_false_field_hints(sheet_rows: list[str], row_index: int, false_positions: list[int]) -> list[str]:
        if not sheet_rows or row_index <= 1 or not false_positions:
            return []
        max_pos = max(false_positions)
        start = max(1, row_index - 12)
        header_parts: list[str] = []
        for idx in range(row_index - 1, start - 1, -1):
            ln = str(sheet_rows[idx - 1] or "")
            parts = [p.strip() for p in ln.split("|")]
            if len(parts) < max_pos:
                continue
            nln = NovaOrchestrator._norm_text(ln)
            if "true" in nln or "false" in nln:
                continue
            alpha_count = len(re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{3,}", ln))
            if alpha_count < 3:
                continue
            header_parts = parts
            break
        if not header_parts:
            return []
        hints: list[str] = []
        for pos in false_positions:
            try:
                raw = str(header_parts[pos - 1] or "").strip()
            except Exception:
                raw = ""
            if not raw:
                continue
            if re.fullmatch(r"\d+", raw):
                continue
            normalized = re.sub(r"\s+", " ", raw).strip()
            if len(normalized) > 80:
                normalized = normalized[:80].rstrip() + "..."
            hints.append(normalized)
        # Deduplicar preservando orden.
        dedup: list[str] = []
        seen: set[str] = set()
        for h in hints:
            key = NovaOrchestrator._norm_text(h)
            if key in seen:
                continue
            seen.add(key)
            dedup.append(h)
        return dedup

    @staticmethod
    def _is_optional_false_hint(hint: str) -> bool:
        h = NovaOrchestrator._norm_text(str(hint or ""))
        if not h:
            return False
        optional_markers = [
            "telefono",
            "teléfono",
            "localidad",
            "subtipo de afiliado",
            "subtipo afiliado",
        ]
        return any(m in h for m in optional_markers)

    @staticmethod
    def _is_worker_data_line(line: str) -> bool:
        ln = str(line or "").strip()
        if not ln:
            return False
        nln = NovaOrchestrator._norm_text(ln)
        if not nln:
            return False
        if "sum(" in nln or "count(" in nln or "counta(" in nln:
            return False
        parts = [p.strip() for p in ln.split("|")]
        # Las filas reales de afiliados en plantillas de sedes tienen muchas columnas.
        if len(parts) < 8:
            return False
        # Estructura esperada en sedes: col 6 = tipo doc, col 7 = documento.
        if len(parts) >= 7:
            td = (parts[5] or "").strip().upper()
            doc = re.sub(r"\D+", "", parts[6] or "")
            valid_td = set(TIPOS_DOCUMENTO_TRABAJADOR)
            if td in valid_td and bool(re.fullmatch(r"\d{6,15}", doc)):
                return True
        if "true" in nln or "false" in nln:
            # Plantilla de validaciones suele tener casi solo booleanos.
            pass
        has_doc = bool(re.search(r"\b\d{6,12}\b", ln))
        alpha_tokens = re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{3,}", ln)
        has_name_like = len(alpha_tokens) >= 2
        has_date = bool(re.search(r"\b\d{4}[-/]\d{2}[-/]\d{2}\b", ln))
        return bool(has_doc and (has_name_like or has_date))

    @staticmethod
    def _is_placeholder_false_row(raw_values: str) -> bool:
        parts = [p.strip() for p in str(raw_values or "").split("|") if str(p).strip()]
        if not parts:
            return True
        allowed = {"true", "false", "0", "1", "si", "no", "x", "n/a", "na"}
        non_allowed = 0
        for p in parts:
            pn = NovaOrchestrator._norm_text(p)
            if pn in allowed:
                continue
            if re.fullmatch(r"[0-9]{1,3}", pn or ""):
                continue
            non_allowed += 1
        return non_allowed == 0

    @staticmethod
    def _is_summary_validation_false_row(raw_values: str) -> bool:
        """
        Detecta filas de control/resumen (no filas de trabajador) que suelen verse como:
        30|True|True|...|60000000|True|...
        """
        parts = [p.strip() for p in str(raw_values or "").split("|") if str(p).strip()]
        if len(parts) < 10:
            return False
        bool_hits = 0
        for p in parts:
            pn = NovaOrchestrator._norm_text(p)
            if pn in {"true", "false", "verdadero", "falso"} or pn.startswith("fal"):
                bool_hits += 1
        # Alta densidad de booleanos en la fila => patrón típico de validación de totales.
        if bool_hits >= max(6, int(len(parts) * 0.45)):
            return True
        # Marcadores textuales de resumen.
        nraw = NovaOrchestrator._norm_text(str(raw_values or ""))
        if "total de trabajadores reportados" in nraw or "total salarios" in nraw:
            return True
        return False

    @staticmethod
    def _doc_page_marker(filename: str) -> tuple[str, int] | None:
        m = re.match(r"^(.*)__p(\d{3,})\.pdf$", str(filename or "").strip(), flags=re.IGNORECASE)
        if not m:
            return None
        base = m.group(1).strip()
        try:
            page = int(m.group(2))
        except Exception:
            return None
        return base, page

    @staticmethod
    def _classify_doc_type(norm_name: str, norm_text: str) -> str:
        hay = f"{norm_name} {norm_text}".strip()
        rules = [
            ("cedula_representante", ["cedula de ciudadania", "identificacion personal", "registraduria", "tarjeta de identidad"]),
            ("camara_comercio", ["camara y comercio", "certificado de existencia", "matricula mercantil"]),
            ("rut", ["registro unico tributario", "rut ", "r.u.t"]),
            ("formulario_afiliacion", ["formulario de afiliacion", "cps-f-216", "datos del tramite"]),
            ("listado_trabajadores", ["listado de trabajadores", "sede 01", "trabajadores o estudiantes"]),
            ("intermediacion", ["carta de intermediacion"]),
            ("cert_arl_anterior", ["certificacion de afiliacion", "arl anterior"]),
            ("carta_desafiliacion", ["carta de desafiliacion"]),
            ("sarlaft", ["sarlaft", "consulta listas"]),
        ]
        for label, keys in rules:
            if any(k in hay for k in keys):
                return label
        return "otro"

    def _group_documental_units(self, docs_ocr: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not docs_ocr:
            return []
        docs = []
        for d in docs_ocr:
            marker = self._doc_page_marker(str(d.get("filename") or ""))
            base_name = marker[0] if marker else str(d.get("filename") or "")
            page_no = marker[1] if marker else 0
            doc_type = self._classify_doc_type(str(d.get("norm_name") or ""), str(d.get("norm_text") or ""))
            item = dict(d)
            item["base_name"] = base_name
            item["page_no"] = page_no
            item["doc_type"] = doc_type
            docs.append(item)

        ordered = sorted(docs, key=lambda x: (str(x.get("base_name") or ""), int(x.get("page_no") or 0), str(x.get("filename") or "")))
        groups: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None

        def close_current() -> None:
            nonlocal current
            if not current:
                return
            pages = current.get("pages", [])
            current["page_count"] = len(pages)
            current["chars"] = int(sum(int(p.get("chars") or 0) for p in pages))
            texts = [str(p.get("text") or "") for p in pages if str(p.get("text") or "").strip()]
            current["text"] = "\n".join(texts)
            current["norm_text"] = self._norm_text(current["text"])
            current["norm_name"] = self._norm_text(str(current.get("filename") or ""))
            groups.append(current)
            current = None

        for d in ordered:
            base_name = str(d.get("base_name") or "")
            page_no = int(d.get("page_no") or 0)
            doc_type = str(d.get("doc_type") or "otro")
            if current is None:
                current = {"filename": base_name, "doc_type": doc_type, "pages": [d], "start_page": page_no, "end_page": page_no}
                continue
            same_base = str(current.get("filename") or "") == base_name
            same_type = str(current.get("doc_type") or "") == doc_type
            prev_end = int(current.get("end_page") or 0)
            contiguous = bool(page_no) and bool(prev_end) and page_no == prev_end + 1
            if same_base and same_type and (contiguous or page_no == 0):
                current["pages"].append(d)
                current["end_page"] = page_no or prev_end
            else:
                close_current()
                current = {"filename": base_name, "doc_type": doc_type, "pages": [d], "start_page": page_no, "end_page": page_no}
        close_current()
        return groups

    @staticmethod
    def _suggest_adjunto_code(doc_type: str) -> int:
        # Mapeo base por tipo documental (fallback).
        dt = str(doc_type or "otro").strip().lower()
        mapping = {
            "formulario_afiliacion": 0,
            "anexo_sedes": 1,
            "listado_trabajadores": 2,
            "cedula_representante": 6,
            "rut": 8,
            "camara_comercio": 5,
            "intermediacion": 4,
            "carta_desafiliacion": 4,
            "cert_arl_anterior": 11,
            "sarlaft": 28,
        }
        return int(mapping.get(dt, 99))

    @staticmethod
    def _doc_code_store_path() -> Path:
        configured = os.getenv("NOVA_DOC_CODE_STORE_PATH", "/tmp/nova_doc_code_examples.json").strip() or "/tmp/nova_doc_code_examples.json"
        return Path(configured)

    @staticmethod
    def _doc_code_db_alias() -> str:
        return os.getenv("NOVA_DOC_CODE_DB_ALIAS", "temporal").strip() or "temporal"

    @staticmethod
    def _doc_code_db_table() -> str:
        return "nova_doc_code_examples"

    @staticmethod
    def _legacy_adjunto_map_path() -> Path:
        default_path = (
            Path(__file__).resolve().parents[2]
            / "data"
            / "nova_legacy_adjunto_map.json"
        )
        configured = (
            os.getenv("NOVA_LEGACY_ADJUNTO_MAP_PATH", str(default_path)).strip()
            or str(default_path)
        )
        return Path(configured)

    def _load_legacy_adjunto_map(self) -> list[dict[str, Any]]:
        if self._legacy_adjunto_map_cache is not None:
            return self._legacy_adjunto_map_cache
        p = self._legacy_adjunto_map_path()
        if not p.exists():
            self._legacy_adjunto_map_cache = []
            return self._legacy_adjunto_map_cache
        try:
            raw = p.read_text(encoding="utf-8")
            data = json.loads(raw)
            if not isinstance(data, list):
                self._legacy_adjunto_map_cache = []
                return self._legacy_adjunto_map_cache
            out: list[dict[str, Any]] = []
            for i, e in enumerate(data):
                if not isinstance(e, dict):
                    continue
                try:
                    code = int(e.get("code"))
                except Exception:
                    continue
                norm_name = str(e.get("norm_name") or "").strip()
                keys_raw = (
                    e.get("keys")
                    if isinstance(e.get("keys"), list)
                    else (e.get("tokens") if isinstance(e.get("tokens"), list) else [])
                )
                keys = [
                    self._norm_text(str(k))
                    for k in keys_raw
                    if str(k).strip()
                ]
                contains_raw = e.get("name_contains") if isinstance(e.get("name_contains"), list) else []
                name_contains = [
                    self._norm_text(str(k))
                    for k in contains_raw
                    if str(k).strip()
                ]
                out.append(
                    {
                        "id": str(e.get("id") or f"legacy_{i + 1}"),
                        "code": code,
                        "norm_name": self._norm_text(norm_name),
                        "keys": keys,
                        "name_contains": name_contains,
                    }
                )
            self._legacy_adjunto_map_cache = out
            return self._legacy_adjunto_map_cache
        except Exception:
            self._legacy_adjunto_map_cache = []
            return self._legacy_adjunto_map_cache

    def _ensure_doc_code_examples_table(self) -> bool:
        if self._doc_code_table_ready:
            return True
        try:
            alias = self._doc_code_db_alias()
            table = self._doc_code_db_table()
            execute_by_alias(
                alias,
                f"""
                CREATE TABLE IF NOT EXISTS public.{table} (
                  id TEXT PRIMARY KEY,
                  code INTEGER NOT NULL,
                  name TEXT NOT NULL DEFAULT '',
                  filename TEXT NOT NULL DEFAULT '',
                  norm_name TEXT NOT NULL DEFAULT '',
                  tokens_json TEXT NOT NULL DEFAULT '[]',
                  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """,
                {},
            )
            self._doc_code_table_ready = True
            return True
        except Exception:
            return False

    @staticmethod
    def _doc_tokens(norm_name: str, norm_text: str, limit: int = 80) -> list[str]:
        src = f"{str(norm_name or '')} {str(norm_text or '')}"
        raw = re.findall(r"[a-z0-9]{3,}", src.lower())
        stop = {
            "de", "del", "para", "con", "por", "una", "uno", "los", "las", "que", "com", "seg", "arl",
            "formulario", "documento", "doc", "datos", "tipo", "numero", "codigo", "codigo", "pdf",
        }
        out: list[str] = []
        seen: set[str] = set()
        for t in raw:
            if t in stop:
                continue
            if t in seen:
                continue
            seen.add(t)
            out.append(t)
            if len(out) >= limit:
                break
        return out

    def _load_doc_code_examples(self) -> list[dict[str, Any]]:
        if self._ensure_doc_code_examples_table():
            try:
                alias = self._doc_code_db_alias()
                table = self._doc_code_db_table()
                rows = fetch_all_by_alias(
                    alias,
                    f"""
                    SELECT
                      id,
                      code,
                      name,
                      filename,
                      norm_name,
                      tokens_json,
                      COALESCE(created_at::text, '') AS created_at
                    FROM public.{table}
                    ORDER BY created_at DESC, id DESC
                    LIMIT 5000
                    """,
                    {},
                )
                out: list[dict[str, Any]] = []
                for e in rows:
                    tokens_raw = str(e.get("tokens_json") or "[]")
                    try:
                        tokens_any = json.loads(tokens_raw)
                    except Exception:
                        tokens_any = []
                    tokens = [str(t) for t in tokens_any if str(t).strip()] if isinstance(tokens_any, list) else []
                    out.append(
                        {
                            "id": str(e.get("id") or ""),
                            "code": int(e.get("code") or 99),
                            "name": str(e.get("name") or ""),
                            "filename": str(e.get("filename") or ""),
                            "norm_name": str(e.get("norm_name") or ""),
                            "tokens": tokens,
                            "created_at": str(e.get("created_at") or ""),
                        }
                    )
                return out
            except Exception:
                pass

        p = self._doc_code_store_path()
        if not p.exists():
            return []
        try:
            raw = p.read_text(encoding="utf-8")
            data = json.loads(raw)
            if not isinstance(data, list):
                return []
            out: list[dict[str, Any]] = []
            for e in data:
                if not isinstance(e, dict):
                    continue
                code = int(e.get("code") or 99)
                tokens = e.get("tokens") if isinstance(e.get("tokens"), list) else []
                out.append(
                    {
                        "id": str(e.get("id") or ""),
                        "code": code,
                        "name": str(e.get("name") or ""),
                        "filename": str(e.get("filename") or ""),
                        "norm_name": str(e.get("norm_name") or ""),
                        "tokens": [str(t) for t in tokens if str(t).strip()],
                        "created_at": str(e.get("created_at") or ""),
                    }
                )
            return out
        except Exception:
            return []

    def _save_doc_code_examples(self, rows: list[dict[str, Any]]) -> None:
        if self._ensure_doc_code_examples_table():
            try:
                alias = self._doc_code_db_alias()
                table = self._doc_code_db_table()
                for r in rows:
                    execute_by_alias(
                        alias,
                        f"""
                        INSERT INTO public.{table} (id, code, name, filename, norm_name, tokens_json, created_at)
                        VALUES (:id, :code, :name, :filename, :norm_name, :tokens_json, CAST(:created_at AS timestamptz))
                        ON CONFLICT (id)
                        DO UPDATE SET
                          code = EXCLUDED.code,
                          name = EXCLUDED.name,
                          filename = EXCLUDED.filename,
                          norm_name = EXCLUDED.norm_name,
                          tokens_json = EXCLUDED.tokens_json,
                          created_at = EXCLUDED.created_at
                        """,
                        {
                            "id": str(r.get("id") or ""),
                            "code": int(r.get("code") or 99),
                            "name": str(r.get("name") or ""),
                            "filename": str(r.get("filename") or ""),
                            "norm_name": str(r.get("norm_name") or ""),
                            "tokens_json": json.dumps(list(r.get("tokens") or []), ensure_ascii=False),
                            "created_at": str(r.get("created_at") or datetime.now().isoformat()),
                        },
                    )
                execute_by_alias(
                    alias,
                    f"""
                    DELETE FROM public.{table}
                    WHERE id IN (
                      SELECT id FROM public.{table}
                      ORDER BY created_at DESC, id DESC
                      OFFSET 2000
                    )
                    """,
                    {},
                )
                return
            except Exception:
                pass

        p = self._doc_code_store_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    def doc_code_examples_list(self) -> dict[str, Any]:
        rows = self._load_doc_code_examples()
        return {"ok": True, "count": len(rows), "items": rows[:300]}

    def doc_code_train_example(
        self,
        *,
        filename: str,
        mime_type: str,
        file_bytes: bytes,
        code: int,
        name: str = "",
    ) -> dict[str, Any]:
        if not file_bytes:
            return {"ok": False, "message": "Archivo vacío."}
        mime = str(mime_type or "").strip() or (mimetypes.guess_type(filename)[0] or "application/octet-stream")
        payload = {
            "filename": filename,
            "mime_type": mime,
            "file_base64": base64.b64encode(file_bytes).decode("ascii"),
            "max_pages": 1,
        }
        ocr_out = self.ocr.extract(payload)
        text = str(ocr_out.get("text") or "")
        norm_name = self._norm_text(filename)
        norm_text = self._norm_text(text)
        tokens = self._doc_tokens(norm_name, norm_text)
        sha = hashlib.sha1(file_bytes).hexdigest()[:16]
        rows = self._load_doc_code_examples()
        rid = f"ex_{datetime.now().strftime('%Y%m%d%H%M%S')}_{sha}"
        item = {
            "id": rid,
            "code": int(code),
            "name": str(name or ""),
            "filename": str(filename or ""),
            "norm_name": norm_name,
            "tokens": tokens,
            "created_at": datetime.now().isoformat(),
        }
        rows = [r for r in rows if str(r.get("id") or "") != rid]
        rows.append(item)
        if len(rows) > 2000:
            rows = rows[-2000:]
        self._save_doc_code_examples(rows)
        return {
            "ok": True,
            "item": item,
            "ocr": {"ok": bool(ocr_out.get("ok")), "chars": int(ocr_out.get("chars") or 0), "engine": str(ocr_out.get("engine") or "")},
            "count": len(rows),
        }

    def doc_code_predict_file(self, *, filename: str, mime_type: str, file_bytes: bytes) -> dict[str, Any]:
        if not file_bytes:
            return {"ok": False, "message": "Archivo vacío."}
        mime = str(mime_type or "").strip() or (mimetypes.guess_type(filename)[0] or "application/octet-stream")
        payload = {
            "filename": filename,
            "mime_type": mime,
            "file_base64": base64.b64encode(file_bytes).decode("ascii"),
            "max_pages": 1,
        }
        ocr_out = self.ocr.extract(payload)
        text = str(ocr_out.get("text") or "")
        norm_name = self._norm_text(filename)
        norm_text = self._norm_text(text)
        doc_type = self._classify_doc_type(norm_name, norm_text)
        code, source = self._infer_adjunto_code(norm_name, norm_text, doc_type, mime)
        return {
            "ok": True,
            "filename": filename,
            "predicted_code": int(code),
            "doc_type": doc_type,
            "code_source": source,
            "ocr": {"ok": bool(ocr_out.get("ok")), "chars": int(ocr_out.get("chars") or 0), "engine": str(ocr_out.get("engine") or "")},
            "catalog": self._adjunto_code_catalog(),
        }

    def _infer_adjunto_code(self, norm_name: str, norm_text: str, doc_type: str, mime_type: str = "") -> tuple[int, str]:
        hay = f"{str(norm_name or '')} {str(norm_text or '')}".strip()
        mt = str(mime_type or "").lower()
        name_txt = str(norm_name or "")
        # Reglas explícitas por nombre de archivo (requerimiento operativo actual del flujo).
        if "formulario de afiliacion" in name_txt:
            return 0, "name_override_formulario_afiliacion"
        # Soporta variantes: SEDE1.pdf, SEDE_1.pdf, SEDE-1.pdf, SEDE 1.pdf, sedes.pdf
        if (
            re.search(r"\bsede\d+\b", name_txt, flags=re.IGNORECASE)
            or re.search(r"\bsede[\s._-]*\d+\b", name_txt, flags=re.IGNORECASE)
            or re.search(r"\bsedes?\b", name_txt, flags=re.IGNORECASE)
        ):
            return 1, "name_override_sede"
        if mt.startswith("image/"):
            return 99, "imagen"
        legacy_map = self._load_legacy_adjunto_map()
        if legacy_map:
            q_tokens = self._doc_tokens(norm_name, norm_text)
            qset = set(q_tokens)
            best_code: int | None = None
            best_score = 0.0
            best_id = ""
            for ex in legacy_map:
                ex_norm_name = str(ex.get("norm_name") or "")
                if ex_norm_name and ex_norm_name == str(norm_name or ""):
                    return int(ex.get("code") or 99), f"legacy_map:name_match:{str(ex.get('id') or '')}"
                contains = [str(x) for x in (ex.get("name_contains") or []) if str(x)]
                if contains and any(k in str(norm_name or "") for k in contains):
                    return int(ex.get("code") or 99), f"legacy_map:name_contains:{str(ex.get('id') or '')}"
                keys = [str(t) for t in (ex.get("keys") or []) if str(t)]
                if not keys:
                    continue
                key_hits = sum(1 for k in keys if k in hay)
                eset = set(keys)
                common = len(qset.intersection(eset))
                denom = max(1, min(len(qset), len(eset)))
                score = (float(common) / float(denom)) + (0.25 if key_hits > 0 else 0.0)
                if score > best_score:
                    best_score = score
                    best_code = int(ex.get("code") or 99)
                    best_id = str(ex.get("id") or "")
            if best_code is not None and best_score >= 0.35:
                return int(best_code), f"legacy_map:{best_id}:{best_score:.2f}"
        examples = self._load_doc_code_examples()
        if examples:
            q_tokens = self._doc_tokens(norm_name, norm_text)
            qset = set(q_tokens)
            best_code = None
            best_score = 0.0
            best_id = ""
            for ex in examples:
                ex_norm_name = str(ex.get("norm_name") or "")
                if ex_norm_name and ex_norm_name == str(norm_name or ""):
                    return int(ex.get("code") or 99), f"trained_example:name_match:{str(ex.get('id') or '')}"
                ex_tokens = [str(t) for t in (ex.get("tokens") or []) if str(t)]
                if not ex_tokens:
                    continue
                eset = set(ex_tokens)
                common = len(qset.intersection(eset))
                denom = max(1, min(len(qset), len(eset)))
                score = float(common) / float(denom)
                if score > best_score:
                    best_score = score
                    best_code = int(ex.get("code") or 99)
                    best_id = str(ex.get("id") or "")
            if best_code is not None and best_score >= 0.18:
                return int(best_code), f"trained_example:{best_id}:{best_score:.2f}"
        # Reglas por evidencia directa OCR (prioridad alta).
        strong_rules: list[tuple[int, list[str], str]] = [
            (3, ["reconocimiento variable integral", "pago de comisiones", "cps-f-11"], "comision"),
            (10, ["comprobante entrega de documentos", "entrega doc", "documentos anexos a la afiliacion"], "entrega_doc"),
            (27, ["beneficiario final"], "beneficiario_final"),
            (28, ["sistema de afiliacion transaccional", "sistema de afiliación transaccional", "canal sat", "canal de venta sat"], "sat"),
            (6, ["cedula de ciudadania", "identificacion personal", "registraduria nacional"], "cedula"),
            (8, ["registro unico tributario", "registro único tributario", "r.u.t", " rut "], "rut"),
            (5, ["camara de comercio", "certificado de existencia", "matricula mercantil"], "camara_comercio"),
            (0, ["formulario de afiliacion", "formulario único de afiliación", "cps-f-216"], "formulario_afiliacion"),
            (1, ["sedes y centros de trabajo", "anexo formulario de afiliacion"], "sedes"),
            (2, ["listado de trabajadores", "trabajadores o estudiantes"], "listados"),
            (11, ["pagos", "recibo de pago", "ultimos recibos de pago"], "pagos"),
            (12, ["contrato de prestacion", "contrato prestación", "objeto del contrato"], "contrato"),
            (15, ["paz y salvo"], "paz_y_salvo"),
            (16, ["eps - afp", "eps y afp"], "eps_afp"),
            (17, ["detectar"], "detectar"),
            (18, ["retroactivas", "retroactiva"], "retroactivas"),
            (19, ["identificacion de peligros", "identificación de peligros"], "identificacion_peligros"),
            (20, ["examen pre-ocupacional", "examen preocupacional"], "examen_preocupacional"),
            (21, ["autorizacion clientes, proveedores y terceros", "autorización clientes, proveedores y terceros"], "autorizacion_terceros"),
            (22, ["historia clinica", "historia clínica"], "historia_clinica"),
            (23, ["afiliacion a eps", "afiliación a eps"], "afiliacion_eps"),
            (24, ["afiliacion a afp", "afiliación a afp"], "afiliacion_afp"),
            (25, ["carta informativa independiente voluntario"], "carta_ind_vol"),
            (26, ["siarl"], "siarl"),
            (98, ["autorizacion", "autorización"], "autorizacion"),
            (4, ["carta", "carta de"], "cartas"),
        ]
        for code, keys, label in strong_rules:
            if any(k in hay for k in keys):
                return int(code), label
        # Reglas por nombre cuando el OCR no aporta suficiente.
        name_rules: list[tuple[int, list[str], str]] = [
            (6, ["cedula", "cc_"], "name_cedula"),
            (5, ["camara", "comercio"], "name_camara"),
            (8, ["rut"], "name_rut"),
            (1, ["sedes", "anexo_sedes"], "name_sedes"),
            (2, ["trabajadores", "sede01-trabajadores", "sede_"], "name_listado"),
            (3, ["comision", "rvi"], "name_comision"),
            (10, ["entrega", "anexos"], "name_entrega_doc"),
            (11, ["pagos", "recibo"], "name_pagos"),
            (12, ["contrato"], "name_contrato"),
            (19, ["peligros"], "name_peligros"),
            (20, ["preocupacional", "pre-ocupacional"], "name_preocupacional"),
            (27, ["beneficiario"], "name_beneficiario"),
            (28, ["sarlaft", "sat"], "name_sat"),
            (98, ["autorizacion"], "name_autorizacion"),
            (4, ["carta", "intermediacion", "desafiliacion"], "name_cartas"),
        ]
        for code, keys, label in name_rules:
            if any(k in str(norm_name or "") for k in keys):
                return int(code), label
        # Fallback por tipo.
        return NovaOrchestrator._suggest_adjunto_code(doc_type), "fallback_doc_type"

    @staticmethod
    def _adjunto_code_catalog() -> list[dict[str, Any]]:
        return [
            {"code": 0, "name": "Afiliación"},
            {"code": 1, "name": "Sedes"},
            {"code": 2, "name": "Listados"},
            {"code": 3, "name": "Comisión"},
            {"code": 4, "name": "Cartas"},
            {"code": 5, "name": "Cámara Comercio"},
            {"code": 6, "name": "Cédula"},
            {"code": 7, "name": "Verificación"},
            {"code": 8, "name": "DIAN"},
            {"code": 10, "name": "Entrega Doc"},
            {"code": 11, "name": "Pagos"},
            {"code": 12, "name": "Contrato"},
            {"code": 13, "name": "EPS"},
            {"code": 14, "name": "AFP"},
            {"code": 15, "name": "Paz y Salvo"},
            {"code": 16, "name": "EPS - AFP"},
            {"code": 17, "name": "Detectar"},
            {"code": 18, "name": "Retroactivas"},
            {"code": 19, "name": "Identificación de Peligros"},
            {"code": 20, "name": "Examen Pre-ocupacional"},
            {"code": 21, "name": "Autorización clientes/proveedores/terceros"},
            {"code": 22, "name": "Historia Clínica"},
            {"code": 23, "name": "Afiliación a EPS"},
            {"code": 24, "name": "Afiliación a AFP"},
            {"code": 25, "name": "Carta informativa Independiente Voluntario"},
            {"code": 26, "name": "SIARL"},
            {"code": 27, "name": "Beneficiario Final"},
            {"code": 28, "name": "SAT"},
            {"code": 98, "name": "Autorización"},
            {"code": 99, "name": "Imagen"},
        ]

    @staticmethod
    def _extract_nit_mentions(text: str) -> list[str]:
        src = str(text or "")
        out: list[str] = []
        for m in re.finditer(r"\bnit[^0-9]{0,12}([0-9][0-9\.\- ]{5,15})", src, flags=re.IGNORECASE):
            digits = re.sub(r"\D", "", m.group(1))
            if 6 <= len(digits) <= 12:
                out.append(digits)
        return out

    @staticmethod
    def _extract_company_mentions(text: str) -> list[str]:
        src = str(text or "").upper()
        out: list[str] = []
        legal_suffix = r"(?:\bS\.?\s*A\.?\s*S\.?\b|\bLTDA\b|\bS\.?\s*A\.?\b)"
        for m in re.finditer(rf"\b([A-Z0-9][A-Z0-9\s\.\-&]{{6,120}}{legal_suffix})\b", src):
            v = re.sub(r"\s+", " ", m.group(1)).strip(" -.")
            if len(v) >= 8:
                out.append(v)
        return out

    @staticmethod
    def _extract_identity_company_lines(text: str) -> list[str]:
        anchors = [
            "razon social",
            "razón social",
            "empresa",
            "nombre o razon social",
            "nombre o razón social",
            "nit",
        ]
        lines = [str(x).strip() for x in str(text or "").splitlines() if str(x).strip()]
        out: list[str] = []
        for ln in lines:
            nln = NovaOrchestrator._norm_text(ln)
            if any(a in nln for a in anchors):
                out.append(ln)
        return out[:60]

    @staticmethod
    def _extract_nit_mentions_strong(text: str) -> list[str]:
        out: list[str] = []
        for ln in NovaOrchestrator._extract_identity_company_lines(text):
            for m in re.finditer(r"\bnit[^0-9]{0,12}([0-9][0-9\.\- ]{5,15})", ln, flags=re.IGNORECASE):
                digits = re.sub(r"\D", "", m.group(1))
                if 6 <= len(digits) <= 12:
                    out.append(digits)
        return out

    @staticmethod
    def _extract_company_mentions_strong(text: str) -> list[str]:
        out: list[str] = []
        legal_suffix = r"(?:\bS\.?\s*A\.?\s*S\.?\b|\bLTDA\b|\bS\.?\s*A\.?\b)"
        for ln in NovaOrchestrator._extract_identity_company_lines(text):
            for m in re.finditer(rf"\b([A-Z0-9][A-Z0-9\s\.\-&]{{6,120}}{legal_suffix})\b", ln.upper()):
                v = re.sub(r"\s+", " ", m.group(1)).strip(" -.")
                if len(v) >= 8:
                    out.append(v)
        return out

    @staticmethod
    def _has_real_evidence(requirement_key: str, unit: dict[str, Any]) -> bool:
        txt = str(unit.get("norm_text") or "")
        if not txt:
            return False
        if requirement_key == "cedula_representante":
            has_digits = bool(re.search(r"\b\d{6,12}\b", txt))
            has_core = (
                "cedula de ciudadania" in txt
                or "identificacion personal" in txt
                or "numero de cedula" in txt
                or "nro de cedula" in txt
                or "no de cedula" in txt
                or "identificada con el numero de cedula" in txt
                or "identificado con el numero de cedula" in txt
            )
            has_rep_context = ("representante legal" in txt) or ("gerente" in txt)
            return has_digits and (has_core or has_rep_context)
        if requirement_key == "camara_comercio":
            if "documentos anexos" in txt and "certificado de camara y comercio" in txt:
                return False
            has_camara = ("camara de comercio" in txt) or ("matricula mercantil" in txt) or ("sede virtual" in txt and "camara" in txt)
            has_cert = ("certificado" in txt) or ("existencia y representacion legal" in txt)
            has_nit = "nit" in txt
            return has_camara and (has_cert or has_nit)
        if requirement_key == "rut":
            return ("registro unico tributario" in txt or "r u t" in txt or "rut" in txt) and ("nit" in txt)
        if requirement_key == "formulario_afiliacion":
            has_form = ("formulario de afiliacion" in txt or "cps-f-216" in txt)
            has_body = ("datos del tramite" in txt) or ("tipo de tramite" in txt) or ("numero de contrato" in txt) or ("nro. de contrato" in txt)
            return has_form and has_body
        if requirement_key == "listado_trabajadores":
            return ("trabajador" in txt or "trabajadores" in txt) and bool(re.search(r"\b\d{6,12}\b", txt))
        if requirement_key == "anexo_sedes":
            return ("sedes y centros de trabajo" in txt) or ("centros de trabajo" in txt and "sede" in txt)
        return True

    @staticmethod
    def _preferred_types_for_requirement(requirement_key: str) -> list[str]:
        mapping = {
            "cedula_representante": ["cedula_representante", "otro"],
            "camara_comercio": ["camara_comercio"],
            "rut": ["rut"],
            "formulario_afiliacion": ["formulario_afiliacion"],
            "listado_trabajadores": ["listado_trabajadores", "otro"],
            "anexo_sedes": ["formulario_afiliacion", "otro"],
        }
        return mapping.get(requirement_key, ["otro", "formulario_afiliacion", "camara_comercio", "rut", "cedula_representante"])

    @staticmethod
    def _detect_tramite_inconsistency(xlsx_text: str) -> bool:
        t = NovaOrchestrator._norm_text(xlsx_text)
        # Señal simple: cuando aparecen ambos marcados.
        if re.search(r"traslado\s*x", t) and re.search(r"nueva\s*x", t):
            return True
        if re.search(r"\btraslado\b", t) and re.search(r"\bnueva\b", t) and "tipo de afiliacion" in t:
            return True
        return False

    @staticmethod
    def _nit_equivalent(a: str, b: str) -> bool:
        aa = re.sub(r"\D", "", str(a or ""))
        bb = re.sub(r"\D", "", str(b or ""))
        if not aa or not bb:
            return False
        if aa == bb:
            return True
        # Tolerancia para NIT con dígito de verificación anexado.
        if len(aa) == len(bb) + 1 and aa.startswith(bb):
            return True
        if len(bb) == len(aa) + 1 and bb.startswith(aa):
            return True
        return False

    @staticmethod
    def _is_historical_identity_context(text: str) -> bool:
        n = NovaOrchestrator._norm_text(text)
        markers = [
            "cambio de razon social",
            "cambio de razón social",
            "reforma",
            "transformacion",
            "transformación",
            "fusion",
            "fusión",
            "escision",
            "escisión",
            "antes",
            "anteriormente",
            "historia",
            "historico",
            "histórico",
        ]
        return any(m in n for m in markers)

    def precheck_ingesta_documental(
        self,
        *,
        excel_filename: str,
        excel_bytes: bytes,
        docs: list[tuple[str, bytes]],
        base: str = "temporal",
        lote: str = "",
        idtramite: str = "",
        ls_root: str = r"\\10.17.0.125\imagenes4\img11",
        ls_fecha: str = "",
        ls_familia: str = "Afa",
        ls_lote_folder: str = "",
        return_ocr_binary: bool = False,
        ocr_binary_limit: int = 40,
        include_clean: bool = False,
        include_clean_strict: bool = True,
    ) -> dict[str, Any]:
        xlsx_text = self._xlsx_bytes_to_text_snapshot(excel_bytes)
        if not xlsx_text:
            return {"ok": False, "approved": False, "message": "No se pudo leer el Excel de contrato."}

        sheets_all = self._split_xlsx_sheets(xlsx_text)
        ignored_non_template_sheets = [sh for sh in list(sheets_all.keys()) if not self._is_allowed_contract_sheet(sh)]
        sheets = {sh: rows for sh, rows in sheets_all.items() if self._is_allowed_contract_sheet(sh)}
        fields = self._extract_xlsx_empleador_sede(xlsx_text)
        false_hits = self._extract_false_evidence_from_excel(excel_bytes, max_items=40)
        if not false_hits:
            false_hits = self._extract_false_evidence(sheets, max_items=40)
        rules = self._extract_required_document_rules(sheets)
        false_hits_relevant: list[str] = []
        false_hits_ignored: list[str] = []
        for hit in false_hits:
            parsed = self._parse_false_evidence_item(hit)
            sheet = str(parsed.get("sheet") or "")
            row = str(parsed.get("row") or "")
            pos = list(parsed.get("false_positions") or [])
            raw_values = str(parsed.get("raw_values") or "")
            if sheet and (not self._is_allowed_contract_sheet(sheet)):
                false_hits_ignored.append(hit)
                continue
            n_sheet = self._norm_text(sheet)
            is_sede_sheet = ("sede" in n_sheet) and ("trabajador" in n_sheet)
            if not is_sede_sheet:
                false_hits_relevant.append(hit)
                continue
            rows_in_sheet = sheets.get(sheet, [])
            has_workers = any(self._is_worker_data_line(r) for r in rows_in_sheet)
            is_placeholder = self._is_placeholder_false_row(raw_values)
            is_summary_validation = self._is_summary_validation_false_row(raw_values)
            starts_with_zero_counter = bool(re.match(r"^\s*0\s*\|", raw_values))
            has_doc_like = bool(re.search(r"\b\d{6,12}\b", raw_values))
            n_raw = self._norm_text(raw_values)
            has_optional_subtipo = "subtipo de afiliado" in n_raw or "subtipo afiliado" in n_raw
            field_hints: list[str] = []
            try:
                row_idx = int(row or "0")
            except Exception:
                row_idx = 0
            if row_idx > 0 and pos:
                field_hints = self._infer_false_field_hints(rows_in_sheet, row_idx, pos)
            has_optional_hints_only = bool(field_hints) and all(self._is_optional_false_hint(h) for h in field_hints)
            # Regla negocio: sede vacía (sin trabajadores) + fila de plantilla => no bloquea.
            if (
                ((not has_workers) and is_placeholder)
                or (is_placeholder and starts_with_zero_counter and (not has_doc_like))
                or is_summary_validation
                or has_optional_subtipo
                or has_optional_hints_only
            ):
                false_hits_ignored.append(hit)
            else:
                false_hits_relevant.append(hit)

        docs_ocr: list[dict[str, Any]] = []
        visual_preview: list[dict[str, Any]] = []
        safe_preview_limit = max(0, min(int(ocr_binary_limit or 0), 120))
        worker_sheets: list[str] = []
        for sh in list(sheets.keys()):
            n_sh = self._norm_text(sh)
            if ("sede" not in n_sh) or ("trabajador" not in n_sh):
                continue
            rows_in_sheet = sheets.get(sh, [])
            if any(self._is_worker_data_line(r) for r in rows_in_sheet):
                worker_sheets.append(sh)
        unexpected_worker_like_sheets: list[str] = []
        known_non_worker_markers = (
            "formulario",
            "instructivo",
            "actividad",
            "orp",
            "subtipo",
            "indice",
            "hoja1",
            "independ",
        )
        for sh in list(sheets.keys()):
            if sh in worker_sheets:
                continue
            n_sh = self._norm_text(sh)
            if any(m in n_sh for m in known_non_worker_markers):
                continue
            rows_in_sheet = sheets.get(sh, [])
            if any(self._is_worker_data_line(r) for r in rows_in_sheet):
                unexpected_worker_like_sheets.append(sh)
        for idx_doc, (filename, raw) in enumerate(docs[:120]):
            if not raw:
                continue
            mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
            payload = {
                "filename": filename,
                "mime_type": mime,
                "file_base64": base64.b64encode(raw).decode("ascii"),
                "max_pages": 1,
            }
            ocr_out = self.ocr.extract(payload)
            text = str(ocr_out.get("text") or "")
            norm_name = self._norm_text(filename)
            norm_text = self._norm_text(text)
            doc_type = self._classify_doc_type(norm_name, norm_text)
            doc_code, code_source = self._infer_adjunto_code(norm_name, norm_text, doc_type, mime)
            docs_ocr.append(
                {
                    "filename": filename,
                    "ok": bool(ocr_out.get("ok")),
                    "mime_type": mime,
                    "chars": int(ocr_out.get("chars") or 0),
                    "text": text,
                    "norm_name": norm_name,
                    "norm_text": norm_text,
                    "doc_type": doc_type,
                    "tipo": int(doc_code),
                    "code_source": str(code_source or ""),
                }
            )
            if return_ocr_binary and idx_doc < safe_preview_limit:
                visual_preview.append(
                    {
                        "filename": filename,
                        "mime_type": mime,
                        "file_base64": base64.b64encode(raw).decode("ascii"),
                        "ok": bool(ocr_out.get("ok")),
                        "chars": int(ocr_out.get("chars") or 0),
                        "doc_type": doc_type,
                        "tipo": int(doc_code),
                    }
                )
        doc_units = self._group_documental_units(docs_ocr)

        checklist: list[dict[str, Any]] = []
        for rule in rules:
            req_key = str(rule.get("key") or "")
            kws = [self._norm_text(x) for x in list(rule.get("keywords") or []) if str(x).strip()]
            preferred_types = self._preferred_types_for_requirement(req_key)
            best_doc: dict[str, Any] | None = None
            for d in doc_units:
                if not d.get("pages"):
                    continue
                d_type = str(d.get("doc_type") or "otro")
                inferred_code = int(
                    self._infer_adjunto_code(
                        self._norm_text(str(d.get("filename") or "")),
                        self._norm_text(str(d.get("text") or "")),
                        d_type,
                        "application/pdf",
                    )[0]
                )
                allow_by_code = (req_key == "camara_comercio" and inferred_code == 5)
                if d_type not in preferred_types and not allow_by_code:
                    continue
                evidence_ok = self._has_real_evidence(req_key, d)
                hay_kw = any(kw in str(d.get("norm_name") or "") or kw in str(d.get("norm_text") or "") for kw in kws)
                # Para cámara, aceptar también match por evidencia fuerte o por código documental inferido.
                hay = hay_kw or (req_key == "camara_comercio" and (evidence_ok or allow_by_code))
                if hay and evidence_ok:
                    best_doc = d
                    break
            if best_doc is None:
                # fallback más laxo si no hubo match por tipo
                for d in doc_units:
                    if not d.get("pages"):
                        continue
                    inferred_code = int(
                        self._infer_adjunto_code(
                            self._norm_text(str(d.get("filename") or "")),
                            self._norm_text(str(d.get("text") or "")),
                            str(d.get("doc_type") or "otro"),
                            "application/pdf",
                        )[0]
                    )
                    evidence_ok = self._has_real_evidence(req_key, d)
                    hay_kw = any(kw in str(d.get("norm_name") or "") or kw in str(d.get("norm_text") or "") for kw in kws)
                    hay = hay_kw or (req_key == "camara_comercio" and (evidence_ok or inferred_code == 5))
                    if hay and evidence_ok:
                        best_doc = d
                        break
            found = best_doc is not None
            checklist.append(
                {
                    "requirement_key": rule.get("key"),
                    "requirement": rule.get("label"),
                    "critical": bool(rule.get("critical")),
                    "found": found,
                    "file": str((best_doc or {}).get("filename") or ""),
                    "pages": (
                        f"{int((best_doc or {}).get('start_page') or 0)}-{int((best_doc or {}).get('end_page') or 0)}"
                        if bool((best_doc or {}).get("start_page")) and bool((best_doc or {}).get("end_page"))
                        else ""
                    ),
                    "evidence": self._first_keyword_evidence(str((best_doc or {}).get("text") or ""), kws) if found else "",
                    "source_rule": str(rule.get("source_line") or ""),
                    "status": "OK" if found else ("FALTANTE_CRITICO" if bool(rule.get("critical")) else "FALTANTE_OPCIONAL"),
                }
            )

        missing_critical = [x for x in checklist if bool(x.get("critical")) and not bool(x.get("found"))]
        data_issues: list[str] = []
        alerts: list[dict[str, Any]] = []
        if not str(fields.get("empresa") or "").strip():
            data_issues.append("Falta razón social en Excel.")
        if not str(fields.get("nit") or "").strip():
            data_issues.append("Falta NIT en Excel.")
        if not str(fields.get("representante_legal") or "").strip():
            data_issues.append("Falta representante legal en Excel.")
        if false_hits_relevant:
            data_issues.append(f"Se detectaron {len(false_hits_relevant)} validaciones en FALSE en hojas del Excel.")

        # Alertas de consistencia de trámite en formulario.
        if self._detect_tramite_inconsistency(xlsx_text):
            alerts.append(
                {
                    "code": "ALERTA_TIPO_TRAMITE_INCONSISTENTE",
                    "severity": "medium",
                    "message": "El formulario presenta señales simultáneas de TRASLADO y NUEVA afiliación (revisión recomendada).",
                }
            )

        # Alertas de identidad de empresa (NIT/razón social cruzada en soportes).
        main_nit = re.sub(r"\D", "", str(fields.get("nit") or ""))
        main_empresa = self._norm_company_name(str(fields.get("empresa") or ""))
        strong_identity_types = {"formulario_afiliacion", "camara_comercio", "rut"}
        for u in doc_units:
            txt = str(u.get("text") or "")
            utype = str(u.get("doc_type") or "")
            if utype not in strong_identity_types:
                continue
            nits = self._extract_nit_mentions_strong(txt)
            companies = [self._norm_company_name(x) for x in self._extract_company_mentions_strong(txt)]
            has_equiv_company = any(self._company_equivalent(c, main_empresa) for c in companies) if main_empresa else False
            page_ref = (
                f"{int(u.get('start_page') or 0)}-{int(u.get('end_page') or 0)}"
                if bool(u.get("start_page")) and bool(u.get("end_page"))
                else ""
            )
            nit_freq = Counter([n for n in nits if n])
            for nit in nits:
                if main_nit and nit and (not self._nit_equivalent(nit, main_nit)):
                    # Filtra ruido OCR: un único NIT distinto aislado no bloquea.
                    if int(nit_freq.get(nit, 0)) < 2:
                        continue
                    # Si el mismo documento identifica de forma consistente la empresa principal,
                    # no bloquear por un NIT espurio detectado por OCR.
                    if has_equiv_company:
                        continue
                    is_historical = self._is_historical_identity_context(txt)
                    alerts.append(
                        {
                            "code": "ALERTA_IDENTIDAD_HISTORICA" if is_historical else "ERROR_IDENTIDAD_EMPRESA",
                            "severity": "medium" if is_historical else "critical",
                            "message": (
                                f"Se detectó NIT distinto en contexto histórico ({nit} != {main_nit})."
                                if is_historical
                                else f"Soporte con NIT distinto al principal ({nit} != {main_nit})."
                            ),
                            "file": str(u.get("filename") or ""),
                            "pages": page_ref,
                        }
                    )
                    break
            if main_empresa and companies:
                mismatch = [c for c in companies if not self._company_equivalent(c, main_empresa)]
                if mismatch:
                    is_historical = self._is_historical_identity_context(txt)
                    alerts.append(
                        {
                            "code": "ALERTA_IDENTIDAD_HISTORICA" if is_historical else "ERROR_IDENTIDAD_EMPRESA",
                            "severity": "medium" if is_historical else "critical",
                            "message": (
                                "Se detectó razón social distinta en contexto histórico del documento."
                                if is_historical
                                else "Se detectó razón social distinta en soportes."
                            ),
                            "file": str(u.get("filename") or ""),
                            "pages": page_ref,
                            "evidence": mismatch[0][:120],
                        }
                    )
                    break

        # Match representante legal: Excel (hoja afiliación) vs Cámara de Comercio.
        rep_excel = self._norm_text(str(fields.get("representante_legal") or ""))
        rep_tokens = [
            t
            for t in rep_excel.split()
            if len(t) >= 3 and t not in {"de", "del", "la", "las", "los", "y"}
        ]
        camara_units = [u for u in doc_units if str(u.get("doc_type") or "") == "camara_comercio"]
        if rep_tokens and camara_units:
            best_hits = 0
            best_file = ""
            best_pages = ""
            for u in camara_units:
                txt_n = self._norm_text(str(u.get("text") or ""))
                hits = sum(1 for tk in rep_tokens if tk in txt_n)
                if hits > best_hits:
                    best_hits = hits
                    best_file = str(u.get("filename") or "")
                    if bool(u.get("start_page")) and bool(u.get("end_page")):
                        best_pages = f"{int(u.get('start_page') or 0)}-{int(u.get('end_page') or 0)}"
            min_hits = min(2, len(rep_tokens))
            if best_hits < min_hits:
                alerts.append(
                    {
                        "code": "ALERTA_REPRESENTANTE_LEGAL_NO_COINCIDE",
                        "severity": "medium",
                        "message": "El representante legal del Excel no coincide claramente con Cámara de Comercio.",
                        "file": best_file,
                        "pages": best_pages,
                        "evidence": f"Tokens coincidentes: {best_hits}/{len(rep_tokens)}",
                    }
                )
        # Match documento representante legal: Excel (hoja afiliación) vs Cámara de Comercio.
        rep_doc_digits = re.sub(r"\D+", "", str(fields.get("doc_representante") or ""))
        if rep_doc_digits and camara_units:
            doc_found = False
            doc_file = ""
            doc_pages = ""
            for u in camara_units:
                txt_digits = re.sub(r"\D+", "", str(u.get("text") or ""))
                if rep_doc_digits and rep_doc_digits in txt_digits:
                    doc_found = True
                    break
                if not doc_file:
                    doc_file = str(u.get("filename") or "")
                    if bool(u.get("start_page")) and bool(u.get("end_page")):
                        doc_pages = f"{int(u.get('start_page') or 0)}-{int(u.get('end_page') or 0)}"
            if not doc_found:
                alerts.append(
                    {
                        "code": "ALERTA_DOC_REPRESENTANTE_NO_COINCIDE",
                        "severity": "medium",
                        "message": "El documento del representante legal del Excel no coincide claramente con Cámara de Comercio.",
                        "file": doc_file,
                        "pages": doc_pages,
                        "evidence": f"Documento esperado: {rep_doc_digits}",
                    }
                )
        # Vigencia de cámara de comercio: máximo 90 días.
        camara_dates: list[datetime] = []
        for u in camara_units:
            txt = str(u.get("text") or "")
            camara_dates.extend(self._extract_dates_ddmmyyyy(txt))
        camara_recent = max(camara_dates) if camara_dates else None
        camara_days = (datetime.now() - camara_recent).days if camara_recent else None
        camara_vigencia_ok = (camara_days is not None) and (camara_days <= 90)
        if camara_recent and (not camara_vigencia_ok):
            alerts.append(
                {
                    "code": "ALERTA_CAMARA_COMERCIO_VENCIDA",
                    "severity": "critical",
                    "message": "Certificado de cámara de comercio con vigencia mayor a 90 días.",
                    "evidence": f"Última fecha detectada: {camara_recent.strftime('%Y-%m-%d')} ({camara_days} días).",
                }
            )

        # Deduplicar alertas por código/mensaje.
        if unexpected_worker_like_sheets:
            alerts.append(
                {
                    "code": "ALERTA_HOJA_NO_ESTANDAR",
                    "severity": "medium",
                    "message": (
                        "Se detectaron hojas no estándar con datos de trabajadores; NOVA las ignora en el flujo base."
                    ),
                    "evidence": ", ".join(unexpected_worker_like_sheets[:8]),
                }
            )
        if ignored_non_template_sheets:
            alerts.append(
                {
                    "code": "ALERTA_HOJAS_FUERA_DE_FORMATO",
                    "severity": "medium",
                    "message": "Se detectaron hojas fuera del formato oficial; NOVA las ignoró en prevalidación.",
                    "evidence": ", ".join(ignored_non_template_sheets[:12]),
                }
            )
        dedup_alerts: list[dict[str, Any]] = []
        seen_alerts: set[str] = set()
        for a in alerts:
            key = f"{a.get('code')}|{a.get('message')}|{a.get('file')}|{a.get('pages')}"
            if key in seen_alerts:
                continue
            seen_alerts.add(key)
            dedup_alerts.append(a)
        alerts = dedup_alerts

        sedes_detectadas = len(worker_sheets)
        tipo1_raw_count = sum(1 for d in docs_ocr if int(d.get("tipo") or -1) == 1)
        sede_slots_tipo1: set[str] = set()
        for d in docs_ocr:
            if int(d.get("tipo") or -1) != 1:
                continue
            slot = self._extract_sede_slot_from_name(str(d.get("filename") or ""))
            if slot:
                sede_slots_tipo1.add(slot)
        # Fallback: si no hubo numeración explícita en nombre, usar documentos tipo 1 únicos por base.
        if not sede_slots_tipo1:
            unique_tipo1_base = {
                str(d.get("filename") or "").strip()
                for d in doc_units
                if int(self._infer_adjunto_code(
                    self._norm_text(str(d.get("filename") or "")),
                    self._norm_text(str(d.get("text") or "")),
                    str(d.get("doc_type") or "otro"),
                    "application/pdf",
                )[0]) == 1
            }
            tipo1_count = len(unique_tipo1_base)
            tipo1_detected_detail = sorted(unique_tipo1_base)[:20]
        else:
            tipo1_count = len(sede_slots_tipo1)
            tipo1_detected_detail = sorted(sede_slots_tipo1, key=lambda x: int(x))
        # Regla operativa: prevalece Excel como maestro.
        # Solo bloquea cuando faltan soportes tipo 1 frente a sedes detectadas en Excel.
        sedes_tipo1_ok = (sedes_detectadas == 0) or (tipo1_count >= sedes_detectadas)
        has_blocking_alert = any(str(a.get("severity") or "").lower() in {"critical", "high"} for a in alerts)
        approved = (len(missing_critical) == 0) and (len(data_issues) == 0) and (not has_blocking_alert) and sedes_tipo1_ok
        blocking_issues: list[dict[str, Any]] = []
        for item in missing_critical:
            req = str(item.get("requirement") or item.get("requirement_key") or "Requisito")
            blocking_issues.append(
                {
                    "code": "DOCUMENTO_FALTANTE_CRITICO",
                    "severity": "critical",
                    "title": f"Falta soporte crítico: {req}",
                    "where": str(item.get("source_rule") or ""),
                    "evidence": str(item.get("evidence") or ""),
                    "action": f"Adjuntar documento válido para '{req}' y volver a ejecutar Paso 0.",
                }
            )
        for issue in data_issues:
            txt = str(issue or "")
            where = ""
            ev = ""
            human_title = txt
            human_action = "Corregir el Excel en la fila/campo indicado (OK/INCORRECTO y obligatorios), guardar y reenviar."
            parsed_false: dict[str, Any] = {}
            sheet = ""
            row = ""
            pos: list[int] = []
            field_hints: list[str] = []
            if "FALSE" in txt.upper() and false_hits_relevant:
                parsed_false = self._parse_false_evidence_item(false_hits_relevant[0])
                sheet = str(parsed_false.get("sheet") or "")
                row = str(parsed_false.get("row") or "")
                pos = list(parsed_false.get("false_positions") or [])
                try:
                    row_idx = int(row or "0")
                except Exception:
                    row_idx = 0
                field_hints = self._infer_false_field_hints(sheets.get(sheet, []), row_idx, pos)
                where = f"{sheet}, fila {row}".strip(", ")
                ev = str(false_hits_relevant[0] or "")
                if sheet and row:
                    human_title = f"En la hoja '{sheet}', fila {row}, hay validaciones en INCORRECTO."
                if field_hints:
                    # Mensaje humano y directo para el asesor.
                    human_title = (
                        f"En la hoja '{sheet}', fila {row}, faltan o están incorrectos: "
                        f"{', '.join(field_hints)}."
                    )
                if pos:
                    field_hint_txt = f" Campos probables: {', '.join(field_hints)}." if field_hints else ""
                    human_action = (
                        f"Abre el Excel y ve a '{sheet}' fila {row}. "
                        f"Revisa las celdas de validación de esa fila (posiciones aprox: {', '.join(str(x) for x in pos)}), "
                        f"corrige los campos obligatorios, deja las validaciones en OK y vuelve a ejecutar Paso 0.{field_hint_txt}"
                    )
                else:
                    human_action = (
                        f"Abre el Excel y ve a '{sheet}' fila {row}. "
                        "Corrige los campos obligatorios que estén inválidos y vuelve a ejecutar Paso 0."
                    )
            blocking_issues.append(
                {
                    "code": "EXCEL_DATA_ISSUE",
                    "severity": "critical",
                    "title": human_title,
                    "where": where,
                    "sheet": sheet,
                    "row": row,
                    "false_positions": pos,
                    "field_hints": field_hints,
                    "evidence": ev,
                    "action": human_action,
                }
            )
        for a in alerts:
            sev = str(a.get("severity") or "").lower()
            if sev not in {"critical", "high"}:
                continue
            blocking_issues.append(
                {
                    "code": str(a.get("code") or "ALERTA_BLOQUEANTE"),
                    "severity": sev,
                    "title": str(a.get("message") or "Alerta bloqueante"),
                    "where": (
                        f"{str(a.get('file') or '')} {str(a.get('pages') or '')}".strip()
                    ),
                    "evidence": str(a.get("evidence") or ""),
                    "action": "Revisar la inconsistencia documental y reenviar soportes/Excel corregidos.",
                }
            )
        if not sedes_tipo1_ok:
            blocking_issues.append(
                {
                    "code": "SEDES_DOC_TIPO1_MISMATCH",
                    "severity": "critical",
                    "title": "Faltan documentos tipo 1 para las sedes reportadas en Excel.",
                    "where": (
                        f"Sedes en Excel: {sedes_detectadas} | "
                        f"Documentos tipo 1 (únicos por sede): {tipo1_count} | "
                        f"Tipo 1 detectados (raw): {tipo1_raw_count}"
                    ),
                    "evidence": "El Excel define el número de sedes; se requiere al menos un tipo 1 por sede.",
                    "action": (
                        "Verifica adjuntos de sede y su clasificación; "
                        f"sede(s) detectadas tipo 1: {', '.join(tipo1_detected_detail) if tipo1_detected_detail else 'N/D'}."
                    ),
                }
            )
        next_actions = [
            "Corregir todos los motivos críticos listados en 'motivos_de_rechazo'.",
            "Volver a cargar Excel + soportes en Paso 0.",
            "Solo continuar a Paso 1 cuando 'decision' sea APROBADO.",
        ]
        summary = {
            "excel": excel_filename,
            "docs_received": len(docs),
            "docs_ocr_ok": sum(1 for d in docs_ocr if bool(d.get("ok"))),
            "doc_units": len(doc_units),
            "ignored_non_template_sheets": ignored_non_template_sheets,
            "worker_sheets_detected": sedes_detectadas,
            "unexpected_worker_like_sheets": unexpected_worker_like_sheets,
            "docs_tipo_1_detected": tipo1_count,
            "docs_tipo_1_detected_raw": tipo1_raw_count,
            "docs_tipo_1_detected_detail": tipo1_detected_detail,
            "sedes_vs_tipo1_ok": sedes_tipo1_ok,
            "rules_total": len(checklist),
            "missing_critical": len(missing_critical),
            "false_hits": len(false_hits),
            "false_hits_relevant": len(false_hits_relevant),
            "false_hits_ignored": len(false_hits_ignored),
            "data_issues": len(data_issues),
            "alerts": len(alerts),
            "blocking_issues": len(blocking_issues),
        }
        rep_name_vs_camara_ok = not any(str(a.get("code") or "") == "ALERTA_REPRESENTANTE_LEGAL_NO_COINCIDE" for a in alerts)
        rep_doc_vs_camara_ok = (
            None
            if not rep_doc_digits or not camara_units
            else (not any(str(a.get("code") or "") == "ALERTA_DOC_REPRESENTANTE_NO_COINCIDE" for a in alerts))
        )

        fecha_segment = re.sub(r"\D", "", str(ls_fecha or ""))[:8] or datetime.now().strftime("%Y%m%d")
        lote_segment = re.sub(r"[^0-9A-Za-z_-]+", "", str(ls_lote_folder or lote or "")) or "LOTE"
        root_clean = str(ls_root or r"\\10.17.0.125\imagenes4\img11").rstrip("\\/")
        fam_clean = str(ls_familia or "Afa").strip() or "Afa"
        manifest_rows: list[dict[str, Any]] = []
        manifest_lines: list[str] = []
        for d in docs_ocr:
            fn = str(d.get("filename") or "").strip()
            if not fn:
                continue
            t = str(d.get("doc_type") or "otro")
            code = int(d.get("tipo") or 99)
            code_source = str(d.get("code_source") or "precomputed")
            ruta = f"{root_clean}\\{fecha_segment}\\{fam_clean}\\{lote_segment}\\{fn}"
            manifest_rows.append({"ruta": ruta, "tipo": code, "filename": fn, "doc_type": t, "code_source": code_source})
            manifest_lines.append(f"{ruta},{code}")
        manifest_content = "\n".join(manifest_lines)
        manifest_filename = f"{lote_segment}.txt"
        lote_token = self._safe_token(lote, fallback=lote_segment) or self._safe_token(idtramite, fallback="general")
        nit_token = self._safe_token(str(fields.get("nit") or ""), fallback="na")
        rag_source_lote = f"afiliaciones_lote_{lote_token}_nit_{nit_token}"
        rag_doc_prefix = (
            f"{rag_source_lote}:{self._safe_token(idtramite, fallback='na')}:{self._safe_token(excel_filename, fallback='xlsx')}"
        )
        rag_clean_payload: dict[str, Any] = {}

        out: dict[str, Any] = {
            "ok": True,
            "approved": approved,
            "decision": "APROBADO" if approved else "RECHAZADO",
            "summary": summary,
            "excel_fields": {
                "empresa": str(fields.get("empresa") or ""),
                "nit": str(fields.get("nit") or ""),
                "representante_legal": str(fields.get("representante_legal") or ""),
                "doc_representante": str(fields.get("doc_representante") or ""),
                "actividad_economica": str(fields.get("actividad_economica") or ""),
            },
            "validacion_resumen": {
                "empresa": str(fields.get("empresa") or ""),
                "nit": str(fields.get("nit") or ""),
                "representante_nombre_vs_camara_ok": rep_name_vs_camara_ok,
                "representante_doc_vs_camara_ok": rep_doc_vs_camara_ok,
                "camara_vigencia_ok": camara_vigencia_ok if camara_recent is not None else None,
                "camara_fecha_detectada": camara_recent.strftime("%Y-%m-%d") if camara_recent else "",
                "camara_antiguedad_dias": int(camara_days) if camara_days is not None else None,
                "afiliados_formulario_vs_total_ok": None,
                "nomina_formulario_vs_total_ok": None,
            },
            "data_issues": data_issues,
            "alerts": alerts[:30],
            "motivos_de_rechazo": blocking_issues[:40],
            "next_actions": next_actions,
            "false_evidence": false_hits_relevant[:20],
            "false_evidence_ignored": false_hits_ignored[:20],
            "checklist": checklist,
            "docs_preview": [
                {
                    "filename": str(d.get("filename") or ""),
                    "ok": bool(d.get("ok")),
                    "chars": int(d.get("chars") or 0),
                    "doc_type": str(d.get("doc_type") or ""),
                    "tipo": int(d.get("tipo") or 99),
                }
                for d in docs_ocr[:80]
            ],
            "docs_ocr": [
                {
                    "filename": str(d.get("filename") or ""),
                    "ok": bool(d.get("ok")),
                    "chars": int(d.get("chars") or 0),
                    "mime_type": str(d.get("mime_type") or ""),
                    "doc_type": str(d.get("doc_type") or ""),
                    "tipo": int(d.get("tipo") or 99),
                    "text": str(d.get("text") or "")[:2400],
                }
                for d in docs_ocr[:120]
            ],
            "docs_preview_visual": visual_preview,
            "doc_units_preview": [
                {
                    "filename": str(d.get("filename") or ""),
                    "doc_type": str(d.get("doc_type") or ""),
                    "pages": (
                        f"{int(d.get('start_page') or 0)}-{int(d.get('end_page') or 0)}"
                        if bool(d.get("start_page")) and bool(d.get("end_page"))
                        else ""
                    ),
                    "page_count": int(d.get("page_count") or 0),
                    "chars": int(d.get("chars") or 0),
                }
                for d in doc_units[:80]
            ],
            "manifest_paso1": {
                "filename": manifest_filename,
                "root": root_clean,
                "fecha": fecha_segment,
                "familia": fam_clean,
                "lote_folder": lote_segment,
                "total_lines": len(manifest_lines),
                "code_catalog": self._adjunto_code_catalog(),
                "preview": manifest_rows[:40],
                "content": manifest_content,
            },
            "context": {"base": base, "lote": lote, "idtramite": idtramite},
        }
        if include_clean:
            clean_out = self.generate_clean_from_excel(
                excel_filename=excel_filename,
                excel_bytes=excel_bytes,
            )
            out["clean_generation"] = {
                "ok": bool(clean_out.get("ok")),
                "message": str(clean_out.get("message") or ""),
            }
            if bool(clean_out.get("ok")):
                out["source_sheets"] = clean_out.get("source_sheets")
                out["contrato_clean"] = clean_out.get("contrato_clean")
                out["trabajadores_clean"] = clean_out.get("trabajadores_clean")
                out["trabajadores_clean_multi"] = clean_out.get("trabajadores_clean_multi")
                out["independientes_clean"] = clean_out.get("independientes_clean")
                out["quality_controls"] = clean_out.get("quality_controls")
                out["clean_generated"] = {
                    "quality_controls": clean_out.get("quality_controls"),
                }
                qc = clean_out.get("quality_controls") if isinstance(clean_out, dict) else None
                if isinstance(qc, dict):
                    totals = qc.get("totals") if isinstance(qc.get("totals"), dict) else {}
                    out["validacion_resumen"]["afiliados_formulario_vs_total_ok"] = bool(totals.get("afiliados_ok", False))
                    out["validacion_resumen"]["nomina_formulario_vs_total_ok"] = bool(totals.get("salarios_ok", False))
                if include_clean_strict and isinstance(qc, dict) and not bool(qc.get("ok")):
                    dup = qc.get("duplicates") if isinstance(qc.get("duplicates"), dict) else {}
                    dup_count = int(dup.get("count") or 0)
                    dup_items = dup.get("items") if isinstance(dup.get("items"), list) else []
                    by_sede = qc.get("by_sede") if isinstance(qc.get("by_sede"), list) else []
                    bad_sedes = [r for r in by_sede if isinstance(r, dict) and str(r.get("status") or "").upper() != "OK"]
                    evidence_lines: list[str] = []
                    if dup_count > 0:
                        for it in dup_items[:5]:
                            td = str(it.get("tipodocumento") or "").strip()
                            nd = str(it.get("numerodocumento") or "").strip()
                            occs = it.get("occurrences") if isinstance(it.get("occurrences"), list) else []
                            for occ in occs[:6]:
                                sh = str(occ.get("sheet") or "").strip()
                                rw = str(occ.get("row") or "").strip()
                                if sh and rw:
                                    evidence_lines.append(f"{sh} fila {rw}: cédula duplicada ({td}-{nd}).")
                    for sm in bad_sedes[:5]:
                        sh = str(sm.get("sheet") or "").strip()
                        ea = int(sm.get("expected_afiliados") or 0)
                        ga = int(sm.get("generated_afiliados") or 0)
                        es = int(sm.get("expected_salarios") or 0)
                        gs = int(sm.get("generated_salarios") or 0)
                        evidence_lines.append(
                            f"{sh}: afiliados Excel={ea} vs generado={ga}, salarios Excel={es} vs generado={gs}."
                        )
                    evidence_txt = " | ".join(evidence_lines[:15]) if evidence_lines else "Sin detalle específico."
                    out["approved"] = False
                    out["decision"] = "RECHAZADO"
                    out["motivos_de_rechazo"] = list(out.get("motivos_de_rechazo") or []) + [
                        {
                            "code": "CLEAN_CONCILIATION_ISSUE",
                            "severity": "critical",
                            "title": "El Excel tiene inconsistencias (duplicados/descuadres) y no puede continuar.",
                            "where": "quality_controls.by_sede / totals",
                            "evidence": evidence_txt,
                            "action": "Estimado usuario: revise y corrija el Excel (hoja/fila indicada), luego radique nuevamente.",
                        }
                    ]
            elif include_clean_strict:
                out["approved"] = False
                out["decision"] = "RECHAZADO"
                out["motivos_de_rechazo"] = list(out.get("motivos_de_rechazo") or []) + [
                    {
                        "code": "CLEAN_GENERATION_FAILED",
                        "severity": "critical",
                        "title": "No se pudo generar archivos clean desde Excel.",
                        "where": "precheck_ingesta_documental",
                        "evidence": str(clean_out.get("message") or ""),
                        "action": "Revisar formato del Excel y volver a ejecutar Paso 0.",
                    }
                ]
            rag_clean_payload = {
                "contrato_clean": clean_out.get("contrato_clean") if isinstance(clean_out, dict) else None,
                "trabajadores_clean_multi": clean_out.get("trabajadores_clean_multi") if isinstance(clean_out, dict) else None,
                "independientes_clean": clean_out.get("independientes_clean") if isinstance(clean_out, dict) else None,
            }

        # RAG full del lote actual: refresca la fuente del lote para evitar respuestas parciales.
        try:
            rag_docs = self._build_precheck_rag_documents(
                source=rag_source_lote,
                doc_id_prefix=rag_doc_prefix,
                excel_filename=excel_filename,
                xlsx_text=xlsx_text,
                manifest_content=manifest_content,
                docs_ocr=docs_ocr,
                clean_payload=rag_clean_payload,
            )
            rag_ingesta = self._refresh_rag_source(source=rag_source_lote, documents=rag_docs)
            out["rag_ingesta"] = rag_ingesta
        except Exception as exc:
            out["rag_ingesta"] = {
                "ok": False,
                "source": rag_source_lote,
                "message": f"fallo_rag_ingesta: {type(exc).__name__}: {exc}",
            }
        # Persistir snapshot para que NOVA opere como revalidador en chat.
        self._save_precheck_cache(
            base=base,
            lote=lote,
            idtramite=idtramite,
            payload={
                "approved": out.get("approved"),
                "decision": out.get("decision"),
                "summary": out.get("summary"),
                "excel_fields": out.get("excel_fields"),
                "validacion_resumen": out.get("validacion_resumen"),
                "alerts": out.get("alerts"),
                "motivos_de_rechazo": out.get("motivos_de_rechazo"),
                "checklist": out.get("checklist"),
                "docs_ocr": out.get("docs_ocr"),
                "clean_generated": out.get("clean_generated"),
                "context": out.get("context"),
            },
        )
        return out

    @staticmethod
    def _rank_rag_items_for_employer_compare(
        items: list[dict[str, Any]],
        *,
        employer_seed: dict[str, Any],
        lote: str = "",
        idtramite: str = "",
        max_items: int = 40,
    ) -> list[dict[str, Any]]:
        if not items:
            return []
        seeds = [
            str(employer_seed.get("empleador") or ""),
            str(employer_seed.get("nit_empleador") or ""),
            str(employer_seed.get("direccion") or ""),
            str(employer_seed.get("telefono") or ""),
            str(employer_seed.get("ciudad") or ""),
            str(lote or ""),
            str(idtramite or ""),
        ]
        seed_norm = [NovaOrchestrator._norm_text(s) for s in seeds if str(s).strip()]
        seed_digits = [NovaOrchestrator._digits(s) for s in seeds if NovaOrchestrator._digits(s)]

        def rank(it: dict[str, Any]) -> tuple[int, int, float]:
            md = it.get("metadata") if isinstance(it.get("metadata"), dict) else {}
            src = str(md.get("path") or it.get("doc_id") or "").lower()
            source_tag = str(it.get("source") or "").lower()
            text = str(it.get("text") or "")
            text_norm = NovaOrchestrator._norm_text(text)
            text_digits = NovaOrchestrator._digits(text)

            structural = 0
            if "contrato_" in src and ("_clean.txt" in src or src.endswith(".json") or src.endswith(".txt")):
                structural += 4
            if ".pdf" in src or ":ocr" in source_tag or "ocr" in source_tag:
                structural += 3
            if "bkcargue" in src:
                structural += 1

            token_hits = 0
            for sn in seed_norm:
                if sn and sn in text_norm:
                    token_hits += 1
            digit_hits = 0
            for sd in seed_digits:
                if sd and sd in text_digits:
                    digit_hits += 1
            score = float(it.get("score") or 0.0)
            return (token_hits + digit_hits, structural, score)

        ordered = sorted(items, key=rank, reverse=True)
        return ordered[: max(1, min(max_items, 120))]

    def ocr_extract(self, payload: dict[str, Any]) -> dict[str, Any]:
        out = self.ocr.extract(payload)
        if not bool(out.get("ok")):
            return out

        rag_payload = out.get("rag_ingest_template")
        is_incapacidad = isinstance(rag_payload, dict) and str(rag_payload.get("document_type") or "").strip().lower() == "incapacidad_medica"
        if not is_incapacidad:
            return out

        try:
            persist = self.ocr_persistence.save_incapacidad_payload(payload=payload, ocr_output=out)
            out["persistence"] = persist
        except Exception as exc:
            logger.warning("ocr_incapacidad_persistence_failed error=%s: %s", type(exc).__name__, exc)
            out["persistence"] = {
                "ok": False,
                "message": f"No se pudo persistir OCR incapacidad: {type(exc).__name__}: {exc}",
            }
        return out

    def ocr_synthetic_list(self) -> dict[str, Any]:
        return self.ocr.list_synthetic_images()

    def ocr_bootstrap_synthetic(self, base: str = "temporal", limit: int = 3, index_to_rag: bool = True) -> dict[str, Any]:
        safe_limit = max(1, min(int(limit), 20))
        sql = """
        SELECT
          t.idtramite,
          t.estado,
          w.numerodocumento,
          w.primerapellido,
          w.segundoapellido,
          w.primernombre,
          w.segundonombre,
          e.numerodocumentoempleador,
          e.razonsocialempleador
        FROM proc_servicios_obtenertramites t
        LEFT JOIN proc_servicios_obtenertrabajadortramite w ON w.idtramite = t.idtramite
        LEFT JOIN proc_servicios_obtenerempleadortramite e ON e.idtramite = t.idtramite
        ORDER BY t.fecharegistro DESC NULLS LAST, t.idtramite DESC
        LIMIT :limit
        """
        rows_out = self.db_tools.query_readonly(base=base, sql=sql, params={"limit": safe_limit})
        rows = rows_out.get("rows", []) if isinstance(rows_out, dict) and rows_out.get("ok") else []
        if not rows:
            return {"ok": False, "message": f"No hay datos base en {base} para generar imágenes OCR sintéticas."}
        normalized = []
        for r in rows:
            trabajador = " ".join(
                [
                    str(r.get("primerapellido") or "").strip(),
                    str(r.get("segundoapellido") or "").strip(),
                    str(r.get("primernombre") or "").strip(),
                    str(r.get("segundonombre") or "").strip(),
                ]
            ).strip()
            normalized.append(
                {
                    "idtramite": str(r.get("idtramite") or ""),
                    "estado": str(r.get("estado") or ""),
                    "trabajador": trabajador,
                    "numerodocumento": str(r.get("numerodocumento") or ""),
                    "numerodocumentoempleador": str(r.get("numerodocumentoempleador") or ""),
                    "razonsocialempleador": str(r.get("razonsocialempleador") or ""),
                }
            )
        synth = self.ocr.build_synthetic_ocr_docs(normalized)
        if not synth.get("ok"):
            return synth
        rag_result: dict[str, Any] | None = None
        docs = synth.get("documents", [])
        if index_to_rag and isinstance(docs, list) and docs:
            rag_result = self.rag.index(docs, replace_doc=True)
        return {
            "ok": True,
            "base": base,
            "rows_source": len(rows),
            "ocr": {
                "engine": synth.get("engine"),
                "output_dir": synth.get("output_dir"),
                "images_generated": synth.get("images_generated"),
                "images": synth.get("images"),
            },
            "rag_indexed": bool(rag_result and rag_result.get("ok")),
            "rag": rag_result,
        }

    def rag_init(self) -> dict[str, Any]:
        # La inicialización ocurre en constructor del servicio; esta operación fuerza bootstrap.
        self.rag.bootstrap_default_kb()
        return {"ok": True, "backend": self.rag.backend, "message": "RAG inicializado."}

    def ingest_code(self, repo_path: str, source: str = "codebase", max_files: int = 200) -> dict[str, Any]:
        ing = self.ingestion.ingest_path(repo_path, source=source, max_files=max_files)
        if not ing.get("ok"):
            return ing
        docs = ing.get("documents", [])
        if not isinstance(docs, list):
            return {"ok": False, "message": "Error de ingesta: documentos invalidos."}
        idx = self.rag.index(docs, replace_doc=False)
        return {
            "ok": True,
            "repo_path": ing.get("repo_path"),
            "files_scanned": ing.get("files_scanned"),
            "documents_indexed": len(docs),
            "rag": idx,
        }

    def db_query(self, base: str, sql: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.db_tools.query_readonly(base=base, sql=sql, params=params)

    def evaluate(self, cases: list[dict[str, Any]]) -> dict[str, Any]:
        return self.eval.run(cases, lambda q, t, ur, k: self.chat(q, template=t, use_rag=ur, top_k=k))
