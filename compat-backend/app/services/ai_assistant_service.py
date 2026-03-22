from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.observability import get_logger

logger = get_logger("app.ai")

WORD_RE = re.compile(r"[a-z0-9áéíóúñ]+", re.IGNORECASE)


PROMPT_TEMPLATES: dict[str, str] = {
    "operacion": (
        "Eres un asistente operativo de procesos legacy clonados. "
        "Responde de forma accionable, breve y con foco en pasos ejecutables."
    ),
    "analitica": (
        "Eres un analista funcional. Resume hallazgos y riesgos, "
        "explica supuestos y propone validaciones concretas."
    ),
    "cumplimiento": (
        "Eres un asistente de cumplimiento. Prioriza privacidad, trazabilidad y controles "
        "de seguridad operativa."
    ),
}

DEFAULT_KB_DOCS: list[dict[str, Any]] = [
    {
        "doc_id": "kb-ruta-actualizaestado",
        "source": "system-kb",
        "text": (
            "Ruta Inclusion - Actualizar Estado: 1) Ir a pestaña Ruta Inclusion. "
            "2) Oprimir Cargar Pendientes para traer casos. "
            "3) Oprimir Cargar Opciones para poblar selector idtramite. "
            "4) Seleccionar idtramite. "
            "5) Oprimir Actualizar. "
            "Si selector queda vacio, revisar base temporal y estados Estudio/Devuelto/Afiliado."
        ),
        "metadata": {"topic": "ruta_inclusion", "intent": "actualiza_estado"},
    },
    {
        "doc_id": "kb-ruta-pendientes",
        "source": "system-kb",
        "text": (
            "Ruta Inclusion - Pendientes: usar accion Cargar Pendientes para consultar tramites "
            "desde proc_servicios_obtenertramites y detalles asociados. "
            "Luego usar subpestaña Pendientes/Consulta para visualizar casos."
        ),
        "metadata": {"topic": "ruta_inclusion", "intent": "pendientes"},
    },
    {
        "doc_id": "kb-926",
        "source": "system-kb",
        "text": (
            "Generacion 926: en Formulario Afiliaciones usar Sincronizar Lote y luego Generar Archivo 926. "
            "Para carga real usar JSON de lote, no el .txt de salida 926."
        ),
        "metadata": {"topic": "afiliaciones", "intent": "archivo_926"},
    },
]


@dataclass
class RagChunk:
    chunk_id: str
    doc_id: str
    source: str
    text: str
    metadata: dict[str, Any]
    created_at: str


class AiAssistantService:
    def __init__(self, store_path: Path | None = None) -> None:
        default_path = Path(os.getenv("AI_RAG_STORE_PATH", "/tmp/ai_rag_store.json"))
        self.store_path = store_path or default_path
        self._bootstrap_default_kb()

    def _ensure_parent(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)

    def _load_store(self) -> list[dict[str, Any]]:
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
        self._ensure_parent()
        self.store_path.write_text(json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8")

    def _bootstrap_default_kb(self) -> None:
        store = self._load_store()
        existing_doc_ids = {str(c.get("doc_id", "")).strip() for c in store}
        needed = [d for d in DEFAULT_KB_DOCS if str(d.get("doc_id", "")).strip() not in existing_doc_ids]
        if not needed:
            return
        self.rag_index(needed, replace_doc=False)
        logger.info(f"ai_default_kb_bootstrapped docs={len(needed)}")

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
    def _score(query_tokens: set[str], text: str) -> float:
        if not query_tokens:
            return 0.0
        text_tokens = AiAssistantService._tokens(text)
        if not text_tokens:
            return 0.0
        inter = query_tokens.intersection(text_tokens)
        if not inter:
            return 0.0
        return float(len(inter)) / float(len(query_tokens))

    def rag_index(
        self,
        documents: list[dict[str, Any]],
        *,
        replace_doc: bool = True,
        chunk_size: int = 900,
        overlap: int = 120,
    ) -> dict[str, Any]:
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
                chunk = RagChunk(
                    chunk_id=f"ch_{uuid4().hex}",
                    doc_id=doc_id,
                    source=source,
                    text=chunk_text,
                    metadata=metadata,
                    created_at=now,
                )
                store.append(chunk.__dict__)
                added += 1

        self._save_store(store)
        return {"ok": True, "docs": len(documents), "chunks_added": added, "store_size": len(store)}

    def rag_query(self, question: str, top_k: int = 5) -> dict[str, Any]:
        q = question.strip()
        if not q:
            return {"ok": True, "question": q, "count": 0, "items": []}
        store = self._load_store()
        q_tokens = self._tokens(q)
        scored: list[tuple[float, dict[str, Any]]] = []
        for chunk in store:
            s = self._score(q_tokens, str(chunk.get("text", "")))
            if s > 0:
                scored.append((s, chunk))
        scored.sort(key=lambda x: x[0], reverse=True)
        items = []
        for score, chunk in scored[: max(1, min(top_k, 20))]:
            items.append(
                {
                    "score": round(score, 4),
                    "chunk_id": chunk.get("chunk_id"),
                    "doc_id": chunk.get("doc_id"),
                    "source": chunk.get("source"),
                    "text": chunk.get("text"),
                    "metadata": chunk.get("metadata") or {},
                }
            )
        return {"ok": True, "question": q, "count": len(items), "items": items}

    def chat(
        self,
        question: str,
        *,
        template: str = "operacion",
        top_k: int = 4,
        use_rag: bool = True,
    ) -> dict[str, Any]:
        q = question.strip()
        if not q:
            return {"ok": False, "message": "La pregunta no puede estar vacia."}

        selected_template = template if template in PROMPT_TEMPLATES else "operacion"
        rag = self.rag_query(q, top_k=top_k) if use_rag else {"ok": True, "count": 0, "items": []}
        items = rag.get("items", []) if isinstance(rag, dict) else []
        cites = []
        for item in items:
            cites.append(
                {
                    "doc_id": item.get("doc_id"),
                    "source": item.get("source"),
                    "score": item.get("score"),
                }
            )

        if items:
            lead = "Respuesta basada en documentos indexados:"
            bullets = []
            for idx, item in enumerate(items[:3], start=1):
                snippet = str(item.get("text", "")).strip().replace("\n", " ")
                snippet = snippet[:220] + ("..." if len(snippet) > 220 else "")
                bullets.append(f"{idx}. {snippet}")
            answer = f"{lead}\n" + "\n".join(bullets)
        else:
            q_low = q.lower()
            if "actualizar estado" in q_low and "ruta" in q_low:
                answer = (
                    "Para actualizar estado en Ruta Inclusion: "
                    "1) Cargar Pendientes, 2) Cargar Opciones, 3) seleccionar idtramite, 4) Actualizar. "
                    "Si el selector no muestra items, valida base/estados y vuelve a cargar pendientes."
                )
            elif "pendiente" in q_low and "ruta" in q_low:
                answer = (
                    "Para listar pendientes de Ruta Inclusion usa el boton Cargar Pendientes en la pestaña Ruta Inclusion. "
                    "Luego revisa subvista Pendientes."
                )
            else:
                answer = (
                    "No encontré contexto en RAG para esa pregunta. "
                    "Puedes indexar documentos y volver a consultar."
                )

        logger.info(
            f'ai_chat template="{selected_template}" use_rag={use_rag} rag_hits={len(items)} qlen={len(q)}'
        )
        return {
            "ok": True,
            "template": selected_template,
            "system_prompt": PROMPT_TEMPLATES[selected_template],
            "question": q,
            "answer": answer,
            "citations": cites,
            "rag_hits": len(items),
            "provider": "local-deterministic",
        }

    def ocr_extract(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        OCR inicial: modo fallback para flujo de pruebas sin dependencias extras.
        - Si llega `text`, lo normaliza y retorna.
        - Si llega `file_base64`, devuelve mensaje de integración pendiente para engine OCR real.
        """
        raw_text = str(payload.get("text", "")).strip()
        if raw_text:
            normalized = "\n".join(line.strip() for line in raw_text.splitlines() if line.strip())
            return {
                "ok": True,
                "engine": "fallback-text",
                "text": normalized,
                "chars": len(normalized),
                "lines": len(normalized.splitlines()) if normalized else 0,
            }

        if payload.get("file_base64"):
            return {
                "ok": False,
                "engine": "fallback-text",
                "message": "OCR binario no configurado. Integra Tesseract/Azure/AWS Textract en servidor.",
            }

        return {"ok": False, "message": "Debes enviar `text` o `file_base64`."}
