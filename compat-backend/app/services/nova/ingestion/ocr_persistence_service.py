from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.core.db import execute_by_alias
from app.core.observability import get_logger

logger = get_logger("app.ai.nova.ocr_persistence")


class OcrPersistenceService:
    def __init__(self) -> None:
        self.db_alias = (
            os.getenv("AI_OCR_DB_ALIAS", "").strip()
            or os.getenv("AI_DB_ALIAS", "").strip()
            or "temporal"
        )
        self._schema_ready = False

    def _ensure_schema(self) -> None:
        if self._schema_ready:
            return
        execute_by_alias(
            self.db_alias,
            """
            CREATE TABLE IF NOT EXISTS documents (
              document_id text PRIMARY KEY,
              source_file jsonb NOT NULL DEFAULT '{}'::jsonb,
              document_classification jsonb NOT NULL DEFAULT '{}'::jsonb,
              processing jsonb NOT NULL DEFAULT '{}'::jsonb,
              retrieval_text text NOT NULL DEFAULT '',
              raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
              created_at timestamptz NOT NULL DEFAULT now()
            )
            """,
        )
        execute_by_alias(
            self.db_alias,
            "CREATE INDEX IF NOT EXISTS documents_created_at_idx ON documents(created_at DESC)",
        )
        execute_by_alias(
            self.db_alias,
            """
            CREATE TABLE IF NOT EXISTS document_pages (
              page_id text PRIMARY KEY,
              document_id text NOT NULL,
              page_number integer NOT NULL,
              source_mode text NOT NULL DEFAULT '',
              text_layer boolean NOT NULL DEFAULT false,
              chars integer NOT NULL DEFAULT 0,
              text_preview text NOT NULL DEFAULT '',
              details jsonb NOT NULL DEFAULT '{}'::jsonb,
              created_at timestamptz NOT NULL DEFAULT now()
            )
            """,
        )
        execute_by_alias(
            self.db_alias,
            "CREATE INDEX IF NOT EXISTS document_pages_document_id_idx ON document_pages(document_id)",
        )
        execute_by_alias(
            self.db_alias,
            """
            CREATE TABLE IF NOT EXISTS document_fields (
              field_id text PRIMARY KEY,
              document_id text NOT NULL,
              field_name text NOT NULL,
              value_text text,
              normalized_value text,
              confidence numeric(6,4) NOT NULL DEFAULT 0,
              status text NOT NULL DEFAULT 'UNRELIABLE',
              page integer,
              region_id text,
              payload jsonb NOT NULL DEFAULT '{}'::jsonb,
              created_at timestamptz NOT NULL DEFAULT now()
            )
            """,
        )
        execute_by_alias(
            self.db_alias,
            "CREATE INDEX IF NOT EXISTS document_fields_document_id_idx ON document_fields(document_id)",
        )
        execute_by_alias(
            self.db_alias,
            """
            CREATE TABLE IF NOT EXISTS document_quality_reports (
              quality_id text PRIMARY KEY,
              document_id text NOT NULL,
              report jsonb NOT NULL DEFAULT '{}'::jsonb,
              created_at timestamptz NOT NULL DEFAULT now()
            )
            """,
        )
        execute_by_alias(
            self.db_alias,
            "CREATE INDEX IF NOT EXISTS document_quality_reports_document_id_idx ON document_quality_reports(document_id)",
        )
        execute_by_alias(
            self.db_alias,
            """
            CREATE TABLE IF NOT EXISTS document_review_queue (
              review_id text PRIMARY KEY,
              document_id text NOT NULL,
              needs_human_review boolean NOT NULL DEFAULT false,
              priority text NOT NULL DEFAULT 'media',
              reasons jsonb NOT NULL DEFAULT '[]'::jsonb,
              suggested_review_fields jsonb NOT NULL DEFAULT '[]'::jsonb,
              status text NOT NULL DEFAULT 'pending',
              created_at timestamptz NOT NULL DEFAULT now()
            )
            """,
        )
        execute_by_alias(
            self.db_alias,
            "CREATE INDEX IF NOT EXISTS document_review_queue_document_id_idx ON document_review_queue(document_id)",
        )
        self._schema_ready = True

    @staticmethod
    def _j(data: Any) -> str:
        return json.dumps(data if data is not None else {}, ensure_ascii=False)

    @staticmethod
    def _txt(value: Any) -> str:
        if value is None:
            return ""
        return str(value)

    def save_incapacidad_payload(self, payload: dict[str, Any], ocr_output: dict[str, Any]) -> dict[str, Any]:
        rag = ocr_output.get("rag_ingest_template")
        if not isinstance(rag, dict):
            return {"ok": False, "message": "No hay rag_ingest_template para persistir."}
        if str(rag.get("document_type") or "").strip().lower() != "incapacidad_medica":
            return {"ok": False, "message": "El documento no es de tipo incapacidad_medica."}

        self._ensure_schema()

        document_id = str(payload.get("document_id") or "").strip() or str(uuid4())
        now_iso = datetime.now(timezone.utc).isoformat()

        filename = str((rag.get("meta") or {}).get("filename") or payload.get("filename") or "")
        mime_type = str((rag.get("meta") or {}).get("mime_type") or payload.get("mime_type") or "")
        source_file = {
            "filename": filename,
            "mime_type": mime_type,
            "uploaded_at": now_iso,
            "source_channel": "upload_manual",
        }
        classification = {
            "document_type": "incapacidad_medica",
            "source_type": str(rag.get("source_type") or ""),
            "has_text_layer": bool(rag.get("has_text_layer")),
            "requires_ocr": bool(rag.get("requires_ocr")),
            "page_count": int(rag.get("pages_total") or 0),
            "language": "es",
        }
        processing = {
            "pipeline_version": "1.0.0",
            "processed_at": now_iso,
            "ocr_engine": str(ocr_output.get("engine") or ""),
            "pages_total": int(ocr_output.get("pages_total") or rag.get("pages_total") or 0),
            "pages_processed": int(ocr_output.get("pages_processed") or rag.get("pages_processed") or 0),
        }
        retrieval_text = str(rag.get("retrieval_text") or "")
        raw_payload = {
            "ocr_output": ocr_output,
            "request_payload_meta": {
                "filename": str(payload.get("filename") or ""),
                "mime_type": str(payload.get("mime_type") or ""),
                "document_type": str(payload.get("document_type") or ""),
            },
        }

        execute_by_alias(
            self.db_alias,
            """
            INSERT INTO documents(document_id, source_file, document_classification, processing, retrieval_text, raw_payload)
            VALUES (:document_id, CAST(:source_file AS jsonb), CAST(:classification AS jsonb), CAST(:processing AS jsonb), :retrieval_text, CAST(:raw_payload AS jsonb))
            ON CONFLICT (document_id) DO UPDATE SET
              source_file = EXCLUDED.source_file,
              document_classification = EXCLUDED.document_classification,
              processing = EXCLUDED.processing,
              retrieval_text = EXCLUDED.retrieval_text,
              raw_payload = EXCLUDED.raw_payload
            """,
            {
                "document_id": document_id,
                "source_file": self._j(source_file),
                "classification": self._j(classification),
                "processing": self._j(processing),
                "retrieval_text": retrieval_text,
                "raw_payload": self._j(raw_payload),
            },
        )

        pages = ocr_output.get("pages", []) if isinstance(ocr_output.get("pages"), list) else []
        page_count = 0
        for p in pages:
            if not isinstance(p, dict):
                continue
            page_count += 1
            execute_by_alias(
                self.db_alias,
                """
                INSERT INTO document_pages(page_id, document_id, page_number, source_mode, text_layer, chars, text_preview, details)
                VALUES (:page_id, :document_id, :page_number, :source_mode, :text_layer, :chars, :text_preview, CAST(:details AS jsonb))
                """,
                {
                    "page_id": str(uuid4()),
                    "document_id": document_id,
                    "page_number": int(p.get("page") or page_count),
                    "source_mode": str(p.get("source_mode") or ""),
                    "text_layer": bool(p.get("text_layer")),
                    "chars": int(p.get("chars") or 0),
                    "text_preview": str(p.get("text_preview") or "")[:500],
                    "details": self._j(p),
                },
            )

        fields = rag.get("structured_fields", {}) if isinstance(rag.get("structured_fields"), dict) else {}
        field_count = 0
        for field_name, field_data in fields.items():
            if not isinstance(field_data, dict):
                continue
            field_count += 1
            execute_by_alias(
                self.db_alias,
                """
                INSERT INTO document_fields(field_id, document_id, field_name, value_text, normalized_value, confidence, status, page, region_id, payload)
                VALUES (:field_id, :document_id, :field_name, :value_text, :normalized_value, :confidence, :status, :page, :region_id, CAST(:payload AS jsonb))
                """,
                {
                    "field_id": str(uuid4()),
                    "document_id": document_id,
                    "field_name": str(field_name),
                    "value_text": self._txt(field_data.get("value")) or None,
                    "normalized_value": self._txt(field_data.get("normalized_value")) or None,
                    "confidence": float(field_data.get("confidence") or 0.0),
                    "status": str(field_data.get("status") or "UNRELIABLE"),
                    "page": int(field_data.get("page")) if field_data.get("page") is not None else None,
                    "region_id": self._txt(field_data.get("region_id")) or None,
                    "payload": self._j(field_data),
                },
            )

        quality_count = 0
        quality = rag.get("quality_report")
        if isinstance(quality, dict):
            quality_count = 1
            execute_by_alias(
                self.db_alias,
                """
                INSERT INTO document_quality_reports(quality_id, document_id, report)
                VALUES (:quality_id, :document_id, CAST(:report AS jsonb))
                """,
                {
                    "quality_id": str(uuid4()),
                    "document_id": document_id,
                    "report": self._j(quality),
                },
            )

        review_count = 0
        review_payload = {
            "needs_human_review": bool(rag.get("needs_human_review")),
            "priority": "media",
            "reasons": [],
            "suggested_review_fields": [],
            "status": "pending",
        }
        if bool(rag.get("needs_human_review")):
            review_payload["reasons"] = ["Campos con confianza media/baja detectados por OCR."]
            review_payload["suggested_review_fields"] = [
                str(k)
                for k, v in fields.items()
                if isinstance(v, dict) and str(v.get("status") or "") != "CONFIDENT"
            ]
        execute_by_alias(
            self.db_alias,
            """
            INSERT INTO document_review_queue(review_id, document_id, needs_human_review, priority, reasons, suggested_review_fields, status)
            VALUES (:review_id, :document_id, :needs_human_review, :priority, CAST(:reasons AS jsonb), CAST(:suggested_review_fields AS jsonb), :status)
            """,
            {
                "review_id": str(uuid4()),
                "document_id": document_id,
                "needs_human_review": bool(review_payload["needs_human_review"]),
                "priority": str(review_payload["priority"]),
                "reasons": self._j(review_payload["reasons"]),
                "suggested_review_fields": self._j(review_payload["suggested_review_fields"]),
                "status": str(review_payload["status"]),
            },
        )
        review_count = 1

        logger.info(
            'ocr_incapacidad_saved alias="%s" document_id="%s" pages=%s fields=%s',
            self.db_alias,
            document_id,
            page_count,
            field_count,
        )
        return {
            "ok": True,
            "db_alias": self.db_alias,
            "document_id": document_id,
            "saved": {
                "documents": 1,
                "document_pages": page_count,
                "document_fields": field_count,
                "document_quality_reports": quality_count,
                "document_review_queue": review_count,
            },
        }
