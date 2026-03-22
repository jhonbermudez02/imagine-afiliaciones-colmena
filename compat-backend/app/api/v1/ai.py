from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.services.nova import NovaOrchestrator

router = APIRouter()
nova = NovaOrchestrator()


def _assert_api_key_if_required(x_api_key: Optional[str]) -> None:
    ok, msg = nova.security.assert_api_key(x_api_key)
    if not ok:
        raise HTTPException(status_code=401, detail=msg)


class RagDocumentIn(BaseModel):
    doc_id: str = Field(default="")
    source: str = Field(default="manual")
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class RagIndexIn(BaseModel):
    documents: list[RagDocumentIn]
    replace_doc: bool = True
    chunk_size: int = 900
    overlap: int = 120


class RagQueryIn(BaseModel):
    question: str
    top_k: int = 5


class ChatIn(BaseModel):
    question: str
    template: str = "operacion"
    use_rag: bool = True
    top_k: int = 4


class OcrIn(BaseModel):
    text: str = ""
    file_base64: str = ""
    mime_type: str = ""
    filename: str = ""
    document_type: str = ""
    max_pages: int = 0


class OcrSyntheticIn(BaseModel):
    base: str = "temporal"
    limit: int = 3
    index_to_rag: bool = True


class CodeIngestionIn(BaseModel):
    repo_path: str
    source: str = "codebase"
    max_files: int = 200


class DbQueryIn(BaseModel):
    base: str = "temporal"
    sql: str
    params: dict[str, Any] = Field(default_factory=dict)


class EvalIn(BaseModel):
    cases: list[dict[str, Any]]


@router.get("/health")
def ai_health() -> dict[str, Any]:
    return nova.health()


@router.get("/prompts")
def ai_prompts() -> dict[str, Any]:
    return nova.prompts()

@router.post("/rag/init")
def ai_rag_init(x_api_key: Optional[str] = Header(default=None)) -> dict[str, Any]:
    _assert_api_key_if_required(x_api_key)
    return nova.rag_init()


@router.post("/rag/index")
def ai_rag_index(payload: RagIndexIn, x_api_key: Optional[str] = Header(default=None)) -> dict[str, Any]:
    _assert_api_key_if_required(x_api_key)
    docs = [d.model_dump() for d in payload.documents]
    out = nova.rag_index(
        docs,
        replace_doc=payload.replace_doc,
        chunk_size=max(200, min(payload.chunk_size, 4000)),
        overlap=max(0, min(payload.overlap, 1000)),
    )
    return out


@router.post("/rag/query")
def ai_rag_query(payload: RagQueryIn, x_api_key: Optional[str] = Header(default=None)) -> dict[str, Any]:
    _assert_api_key_if_required(x_api_key)
    return nova.rag_query(payload.question, top_k=max(1, min(payload.top_k, 20)))


@router.post("/chat")
def ai_chat(payload: ChatIn, x_api_key: Optional[str] = Header(default=None)) -> dict[str, Any]:
    _assert_api_key_if_required(x_api_key)
    return nova.chat(
        payload.question,
        template=payload.template,
        top_k=max(1, min(payload.top_k, 20)),
        use_rag=payload.use_rag,
    )


@router.post("/ocr/extract")
def ai_ocr_extract(payload: OcrIn, x_api_key: Optional[str] = Header(default=None)) -> dict[str, Any]:
    _assert_api_key_if_required(x_api_key)
    return nova.ocr_extract(payload.model_dump())


@router.post("/ocr/bootstrap-synthetic")
def ai_ocr_bootstrap_synthetic(payload: OcrSyntheticIn, x_api_key: Optional[str] = Header(default=None)) -> dict[str, Any]:
    _assert_api_key_if_required(x_api_key)
    return nova.ocr_bootstrap_synthetic(
        base=payload.base,
        limit=max(1, min(payload.limit, 20)),
        index_to_rag=payload.index_to_rag,
    )


@router.get("/ocr/synthetic/list")
def ai_ocr_synthetic_list(x_api_key: Optional[str] = Header(default=None)) -> dict[str, Any]:
    _assert_api_key_if_required(x_api_key)
    return nova.ocr_synthetic_list()


@router.get("/ocr/synthetic/image/{filename}")
def ai_ocr_synthetic_image(filename: str, x_api_key: Optional[str] = Header(default=None)) -> FileResponse:
    _assert_api_key_if_required(x_api_key)
    p = nova.ocr.resolve_synthetic_image_path(filename)
    if not p:
        raise HTTPException(status_code=404, detail="Imagen OCR no encontrada.")
    return FileResponse(path=str(p), media_type="image/png")


@router.post("/ingestion/code")
def ai_ingestion_code(payload: CodeIngestionIn, x_api_key: Optional[str] = Header(default=None)) -> dict[str, Any]:
    _assert_api_key_if_required(x_api_key)
    if not nova.security.can("admin", "ingestion"):
        raise HTTPException(status_code=403, detail="Operacion no permitida.")
    return nova.ingest_code(
        repo_path=payload.repo_path,
        source=payload.source,
        max_files=max(1, min(payload.max_files, 2000)),
    )


@router.post("/db/query")
def ai_db_query(payload: DbQueryIn, x_api_key: Optional[str] = Header(default=None)) -> dict[str, Any]:
    _assert_api_key_if_required(x_api_key)
    return nova.db_query(payload.base, payload.sql, payload.params)


@router.post("/eval/run")
def ai_eval_run(payload: EvalIn, x_api_key: Optional[str] = Header(default=None)) -> dict[str, Any]:
    _assert_api_key_if_required(x_api_key)
    return nova.evaluate(payload.cases)
