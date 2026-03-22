from __future__ import annotations

import asyncio
import base64
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Optional
import re

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.core.observability import get_logger
from app.services.nova import NovaOrchestrator

router = APIRouter()
nova = NovaOrchestrator()
logger = get_logger("app.api.v1.nova")

try:
    import fitz  # PyMuPDF
except Exception:  # pragma: no cover
    fitz = None


def _explode_multipage_pdfs(doc_items: list[tuple[str, bytes]], max_pages: int = 300) -> list[tuple[str, bytes]]:
    out: list[tuple[str, bytes]] = []
    pages_used = 0
    for name, raw in doc_items:
        leaf = Path(str(name or "")).name
        if not leaf:
            continue
        if leaf.lower().startswith("._"):
            continue
        if not leaf.lower().endswith(".pdf") or fitz is None:
            out.append((leaf, raw))
            continue
        try:
            src = fitz.open(stream=raw, filetype="pdf")
        except Exception:
            out.append((leaf, raw))
            continue
        total = len(src)
        if total <= 1:
            out.append((leaf, raw))
            continue
        stem = Path(leaf).stem
        for idx in range(total):
            if pages_used >= max_pages:
                break
            one = fitz.open()
            one.insert_pdf(src, from_page=idx, to_page=idx)
            page_bytes = one.tobytes()
            one.close()
            out.append((f"{stem}__p{idx + 1:03d}.pdf", page_bytes))
            pages_used += 1
    return out


def _assert_api_key_if_required(x_api_key: Optional[str]) -> None:
    ok, msg = nova.security.assert_api_key(x_api_key)
    if not ok:
        raise HTTPException(status_code=401, detail=msg)


def _guess_mime(filename: str) -> str:
    low = (filename or "").lower()
    if low.endswith(".pdf"):
        return "application/pdf"
    if low.endswith(".png"):
        return "image/png"
    if low.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if low.endswith(".webp"):
        return "image/webp"
    if low.endswith(".bmp"):
        return "image/bmp"
    if low.endswith((".tif", ".tiff")):
        return "image/tiff"
    return "application/octet-stream"


class NovaChatIn(BaseModel):
    question: str
    template: str = "afiliaciones_arl"
    use_rag: bool = True
    top_k: int = 6
    base: str = "temporal"
    lote: str = ""
    idtramite: str = ""
    source_prefix: str = ""


class NovaRetrievalIn(BaseModel):
    question: str
    base: str = "temporal"
    lote: str = ""
    idtramite: str = ""
    source_prefix: str = ""
    top_k: int = 8


class NovaIndexFolderIn(BaseModel):
    folder_path: str
    source: str = "afiliaciones_docs"
    replace_doc: bool = False
    include_hidden: bool = False
    max_files: int = 500
    ocr_binary: bool = True


class NovaIndexZipIn(BaseModel):
    zip_path: str
    source: str = "afiliaciones_reglas_zip"
    replace_doc: bool = False
    include_hidden: bool = False
    max_files: int = 1500
    ocr_binary: bool = False


class NovaPdfCandidatesIn(BaseModel):
    question: str
    base: str = "temporal"
    lote: str = ""
    idtramite: str = ""
    max_files: int = Field(default=60, ge=1, le=200)


class NovaExplodedPdfItem(BaseModel):
    filename: str
    mime_type: str
    file_base64: str
    exploded: bool = False


@router.get("/health")
def nova_health() -> dict[str, Any]:
    data = nova.health()
    data["service"] = "nova"
    data["api_mode"] = "openai-compatible"
    return data


@router.post("/pdf/explode-upload")
async def nova_pdf_explode_upload(
    file: UploadFile = File(...),
    max_pages: int = Form(300),
    x_api_key: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    _assert_api_key_if_required(x_api_key)
    filename = Path(str(file.filename or "")).name
    if not filename:
        raise HTTPException(status_code=400, detail="Archivo inválido.")
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Archivo vacío.")
    exploded = _explode_multipage_pdfs([(filename, raw)], max_pages=max(1, min(int(max_pages), 1200)))
    items: list[NovaExplodedPdfItem] = []
    for out_name, out_raw in exploded:
        items.append(
            NovaExplodedPdfItem(
                filename=out_name,
                mime_type=_guess_mime(out_name),
                file_base64=base64.b64encode(out_raw).decode("ascii"),
                exploded=(out_name != filename),
            )
        )
    return {
        "ok": True,
        "count_in": 1,
        "count_out": len(items),
        "files": [x.model_dump() for x in items],
    }


@router.get("/prompts")
def nova_prompts() -> dict[str, Any]:
    return nova.prompts()


def _build_answer_structured(answer: str, intent_route: str = "") -> dict[str, Any]:
    txt = str(answer or "").strip()
    lines = [ln.strip() for ln in txt.splitlines() if ln.strip()]
    txt_norm = (
        txt.lower()
        .replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
        .replace("ñ", "n")
    )
    out: dict[str, Any] = {
        "kind": "text",
        "intent_route": str(intent_route or "").strip(),
        "raw": txt,
    }
    if not lines:
        return out

    if txt_norm.startswith("ficha rapida nova"):
        out["kind"] = "ficha_rapida"
        fields: dict[str, str] = {}
        items: list[str] = []
        for ln in lines[1:]:
            if ln == "Traza NOVA:":
                break
            if not ln.startswith("- "):
                continue
            body = ln[2:].strip()
            if ":" in body:
                k, v = body.split(":", 1)
                fields[k.strip()] = v.strip()
            else:
                items.append(body)
        out["title"] = "Ficha rápida NOVA"
        out["fields"] = fields
        out["items"] = items
        return out

    section_names = ("Resumen:", "Cómo lo sé:", "Siguiente paso:")
    if any(ln in section_names for ln in lines):
        out["kind"] = "sectioned"
        sec: dict[str, list[str]] = {"resumen": [], "como_lo_se": [], "siguiente_paso": []}
        current = "resumen"
        for ln in lines:
            if ln == "Traza NOVA:":
                break
            if ln == "Resumen:":
                current = "resumen"
                continue
            if ln == "Cómo lo sé:":
                current = "como_lo_se"
                continue
            if ln == "Siguiente paso:":
                current = "siguiente_paso"
                continue
            sec[current].append(ln)
        out["sections"] = sec
        return out
    return out


@router.post("/chat")
def nova_chat(payload: NovaChatIn, x_api_key: Optional[str] = Header(default=None)) -> dict[str, Any]:
    _assert_api_key_if_required(x_api_key)
    out = nova.chat(
        payload.question,
        template=payload.template,
        use_rag=payload.use_rag,
        top_k=max(1, min(payload.top_k, 20)),
        base=payload.base,
        lote=payload.lote,
        idtramite=payload.idtramite,
        source_prefix=payload.source_prefix,
    )
    answer = str(out.get("answer") or "")
    out["answer_structured"] = _build_answer_structured(answer, str(out.get("intent_route") or ""))
    if "Traza NOVA:" in answer:
        trace: list[dict[str, str]] = []
        after = answer.split("Traza NOVA:", 1)[1]
        for raw in after.splitlines():
            ln = str(raw or "").strip()
            if not ln.startswith("- "):
                continue
            body = ln[2:].strip()
            # expected: step [tool]: detail
            step = body
            tool = ""
            detail = ""
            m = re.match(r"^(.*?)\s*\[([^\]]+)\]\s*:\s*(.*)$", body)
            if m:
                step = str(m.group(1) or "").strip()
                tool = str(m.group(2) or "").strip()
                detail = str(m.group(3) or "").strip()
            else:
                m2 = re.match(r"^(.*?)\s*:\s*(.*)$", body)
                if m2:
                    step = str(m2.group(1) or "").strip()
                    detail = str(m2.group(2) or "").strip()
            if step:
                trace.append({"step": step, "tool": tool, "detail": detail})
        if trace:
            out["decision_trace"] = trace[:12]
            if not str(out.get("intent_route") or "").strip():
                for t in trace:
                    if str(t.get("step") or "") == "route_selected":
                        det = str(t.get("detail") or "")
                        m = re.search(r"route=([a-zA-Z0-9_\\-]+)", det)
                        if m:
                            out["intent_route"] = str(m.group(1) or "").strip()
                        break
            out["answer_structured"] = _build_answer_structured(answer, str(out.get("intent_route") or ""))
    return out


@router.post("/retrieval/search")
def nova_retrieval_search(payload: NovaRetrievalIn, x_api_key: Optional[str] = Header(default=None)) -> dict[str, Any]:
    _assert_api_key_if_required(x_api_key)
    return nova.retrieval_search(
        question=payload.question,
        base=payload.base,
        lote=payload.lote,
        idtramite=payload.idtramite,
        source_prefix=payload.source_prefix,
        top_k=payload.top_k,
    )


@router.post("/rag/index-folder")
def nova_rag_index_folder(payload: NovaIndexFolderIn, x_api_key: Optional[str] = Header(default=None)) -> dict[str, Any]:
    _assert_api_key_if_required(x_api_key)
    return nova.rag_index_folder(
        folder_path=payload.folder_path,
        source=payload.source,
        replace_doc=payload.replace_doc,
        include_hidden=payload.include_hidden,
        max_files=max(1, min(payload.max_files, 5000)),
        ocr_binary=payload.ocr_binary,
    )


@router.post("/rag/index-zip")
def nova_rag_index_zip(payload: NovaIndexZipIn, x_api_key: Optional[str] = Header(default=None)) -> dict[str, Any]:
    _assert_api_key_if_required(x_api_key)
    return nova.rag_index_zip(
        zip_path=payload.zip_path,
        source=payload.source,
        replace_doc=payload.replace_doc,
        include_hidden=payload.include_hidden,
        max_files=max(1, min(payload.max_files, 5000)),
        ocr_binary=payload.ocr_binary,
    )


@router.post("/rag/index-zip-upload")
async def nova_rag_index_zip_upload(
    file: UploadFile = File(...),
    source: str = Form("afiliaciones_reglas_zip"),
    replace_doc: bool = Form(False),
    include_hidden: bool = Form(False),
    max_files: int = Form(1500),
    ocr_binary: bool = Form(False),
    x_api_key: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    _assert_api_key_if_required(x_api_key)
    filename = Path(str(file.filename or "")).name
    if not filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Debes subir un archivo .zip")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Archivo ZIP vacío.")
    with tempfile.NamedTemporaryFile(prefix="nova_rules_", suffix=".zip", delete=True) as tmp:
        tmp.write(content)
        tmp.flush()
        return nova.rag_index_zip(
            zip_path=tmp.name,
            source=source,
            replace_doc=replace_doc,
            include_hidden=include_hidden,
            max_files=max(1, min(max_files, 5000)),
            ocr_binary=ocr_binary,
        )


@router.post("/pdf/candidates")
async def nova_pdf_candidates(payload: NovaPdfCandidatesIn, x_api_key: Optional[str] = Header(default=None)) -> dict[str, Any]:
    _assert_api_key_if_required(x_api_key)
    try:
        rows = await asyncio.wait_for(
            asyncio.to_thread(
                nova.find_pdf_candidates,
                question=payload.question,
                base=payload.base,
                lote=payload.lote,
                idtramite=payload.idtramite,
                max_files=payload.max_files,
            ),
            timeout=8.0,
        )
        return {"ok": True, "count": len(rows), "rows": rows}
    except asyncio.TimeoutError:
        logger.warning(
            f'nova_pdf_candidates_timeout lote="{payload.lote}" idtramite="{payload.idtramite}" max_files="{payload.max_files}"'
        )
        return {
            "ok": True,
            "count": 0,
            "rows": [],
            "degraded": True,
            "message": "Búsqueda OCR superó tiempo límite; reintenta con consulta más específica.",
        }
    except Exception as exc:
        logger.warning(f'nova_pdf_candidates_failed error="{type(exc).__name__}: {exc}"')
        return {
            "ok": True,
            "count": 0,
            "rows": [],
            "degraded": True,
            "message": f"Búsqueda documental no disponible temporalmente ({type(exc).__name__}).",
        }


@router.get("/pdf/view")
def nova_pdf_view(
    filename: str,
    base: str = "temporal",
    lote: str = "",
    idtramite: str = "",
    x_api_key: Optional[str] = Header(default=None),
) -> FileResponse:
    _assert_api_key_if_required(x_api_key)
    p = nova.resolve_pdf_for_view(base=base, lote=lote, idtramite=idtramite, filename=filename)
    if not p:
        raise HTTPException(status_code=404, detail="PDF no encontrado para el lote/trámite indicado.")
    return FileResponse(
        path=str(p),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{p.name}"'},
    )


@router.get("/report/auditoria-xlsx")
def nova_report_auditoria_xlsx(
    base: str = "temporal",
    lote: str = "",
    idtramite: str = "",
    source_prefix: str = "",
    x_api_key: Optional[str] = Header(default=None),
) -> FileResponse:
    _assert_api_key_if_required(x_api_key)
    out = nova.build_auditoria_xlsx_report(
        base=base,
        lote=lote,
        idtramite=idtramite,
        source_prefix=source_prefix,
    )
    if not bool(out.get("ok")):
        raise HTTPException(status_code=400, detail=str(out.get("message") or "No se pudo generar auditoría XLSX."))
    file_path = Path(str(out.get("path") or ""))
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Archivo de auditoría XLSX no encontrado.")
    return FileResponse(
        path=str(file_path),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=str(out.get("filename") or "NOVA_Auditoria.xlsx"),
    )


@router.post("/precheck/ingesta-upload")
async def nova_precheck_ingesta_upload(
    excel_file: UploadFile = File(...),
    docs: list[UploadFile] | None = File(default=None),
    docs_zip: UploadFile | None = File(default=None),
    base: str = Form("temporal"),
    lote: str = Form(""),
    idtramite: str = Form(""),
    ls_root: str = Form(r"\\10.17.0.125\imagenes4\img11"),
    ls_fecha: str = Form(""),
    ls_familia: str = Form("Afa"),
    ls_lote_folder: str = Form(""),
    ocr_preview_binary: bool = Form(False),
    ocr_preview_limit: int = Form(40),
    include_clean: bool = Form(False),
    include_clean_strict: bool = Form(True),
    x_api_key: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    _assert_api_key_if_required(x_api_key)
    excel_name = Path(str(excel_file.filename or "")).name
    if not excel_name.lower().endswith((".xlsx", ".xlsm", ".xls")):
        raise HTTPException(status_code=400, detail="El archivo de contrato debe ser Excel (.xlsx/.xlsm/.xls).")
    excel_bytes = await excel_file.read()
    if not excel_bytes:
        raise HTTPException(status_code=400, detail="El Excel de contrato está vacío.")

    doc_items: list[tuple[str, bytes]] = []
    for f in (docs or [])[:200]:
        name = Path(str(f.filename or "")).name
        if not name:
            continue
        raw = await f.read()
        if raw:
            doc_items.append((name, raw))

    if docs_zip is not None:
        zip_name = Path(str(docs_zip.filename or "")).name
        if zip_name and not zip_name.lower().endswith(".zip"):
            raise HTTPException(status_code=400, detail="docs_zip debe ser .zip")
        zip_raw = await docs_zip.read()
        if zip_raw:
            try:
                with tempfile.NamedTemporaryFile(prefix="nova_docs_", suffix=".zip", delete=True) as tmp:
                    tmp.write(zip_raw)
                    tmp.flush()
                    with zipfile.ZipFile(tmp.name, "r") as zf:
                        for info in zf.infolist():
                            if info.is_dir():
                                continue
                            leaf = Path(info.filename).name
                            if not leaf:
                                continue
                            if not leaf.lower().endswith((".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp")):
                                continue
                            try:
                                raw = zf.read(info.filename)
                            except Exception:
                                continue
                            if raw:
                                doc_items.append((leaf, raw))
            except zipfile.BadZipFile:
                raise HTTPException(status_code=400, detail="ZIP de documentos inválido.")

    doc_items = _explode_multipage_pdfs(doc_items)

    if not doc_items:
        raise HTTPException(status_code=400, detail="Debes adjuntar al menos un soporte (PDF/imagen o ZIP).")

    out = nova.precheck_ingesta_documental(
        excel_filename=excel_name,
        excel_bytes=excel_bytes,
        docs=doc_items[:200],
        base=base,
        lote=lote,
        idtramite=idtramite,
        ls_root=ls_root,
        ls_fecha=ls_fecha,
        ls_familia=ls_familia,
        ls_lote_folder=ls_lote_folder,
        return_ocr_binary=bool(ocr_preview_binary),
        ocr_binary_limit=max(0, min(int(ocr_preview_limit), 120)),
        include_clean=bool(include_clean),
        include_clean_strict=bool(include_clean_strict),
    )
    if not bool(out.get("ok")):
        raise HTTPException(status_code=400, detail=str(out.get("message") or "No se pudo ejecutar precheck de ingesta."))
    return out


@router.post("/knowledge/test-upload")
async def nova_knowledge_test_upload(
    excel_file: UploadFile = File(...),
    x_api_key: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    _assert_api_key_if_required(x_api_key)
    excel_name = Path(str(excel_file.filename or "")).name
    if not excel_name.lower().endswith((".xlsx", ".xlsm", ".xls")):
        raise HTTPException(status_code=400, detail="El archivo debe ser Excel (.xlsx/.xlsm/.xls).")
    excel_bytes = await excel_file.read()
    if not excel_bytes:
        raise HTTPException(status_code=400, detail="El archivo Excel está vacío.")
    out = nova.knowledge_test_from_excel(
        excel_filename=excel_name,
        excel_bytes=excel_bytes,
    )
    if not bool(out.get("ok")):
        raise HTTPException(status_code=400, detail=str(out.get("message") or "No se pudo ejecutar test de conocimiento."))
    return out


@router.post("/precheck/generate-clean-upload")
async def nova_precheck_generate_clean_upload(
    excel_file: UploadFile = File(...),
    x_api_key: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    _assert_api_key_if_required(x_api_key)
    excel_name = Path(str(excel_file.filename or "")).name
    if not excel_name.lower().endswith((".xlsx", ".xlsm", ".xls")):
        raise HTTPException(status_code=400, detail="El archivo debe ser Excel (.xlsx/.xlsm/.xls).")
    excel_bytes = await excel_file.read()
    if not excel_bytes:
        raise HTTPException(status_code=400, detail="El archivo Excel está vacío.")
    out = nova.generate_clean_from_excel(
        excel_filename=excel_name,
        excel_bytes=excel_bytes,
    )
    if not bool(out.get("ok")):
        raise HTTPException(status_code=400, detail=str(out.get("message") or "No se pudo generar archivos clean."))
    qc = out.get("quality_controls") if isinstance(out, dict) else None
    if isinstance(qc, dict) and not bool(qc.get("ok")):
        dup = qc.get("duplicates") if isinstance(qc.get("duplicates"), dict) else {}
        dup_count = int(dup.get("count") or 0)
        dup_items = dup.get("items") if isinstance(dup.get("items"), list) else []
        by_sede = qc.get("by_sede") if isinstance(qc.get("by_sede"), list) else []
        sede_mismatch = [r for r in by_sede if isinstance(r, dict) and str(r.get("status") or "").upper() != "OK"]
        line_items: list[str] = []
        reason_parts: list[str] = []
        if dup_count > 0:
            samples = []
            for it in dup_items[:3]:
                td = str(it.get("tipodocumento") or "").strip()
                nd = str(it.get("numerodocumento") or "").strip()
                if nd:
                    samples.append(f"{td}-{nd}" if td else nd)
                occs = it.get("occurrences") if isinstance(it.get("occurrences"), list) else []
                for occ in occs[:8]:
                    sh = str(occ.get("sheet") or "").strip()
                    rw = str(occ.get("row") or "").strip()
                    if sh and rw:
                        line_items.append(f"Hoja '{sh}', fila {rw}: cédula duplicada ({td}-{nd}).")
            sample_txt = f" Ejemplos: {', '.join(samples)}." if samples else ""
            reason_parts.append(f"Se detectaron {dup_count} cédula(s) duplicada(s).{sample_txt}")
        if sede_mismatch:
            reason_parts.append(f"Hay {len(sede_mismatch)} sede(s) con descuadre de afiliados o salarios vs Excel.")
            for sm in sede_mismatch[:10]:
                sh = str(sm.get("sheet") or "").strip()
                sd = str(sm.get("sede") or "").strip()
                ea = int(sm.get("expected_afiliados") or 0)
                ga = int(sm.get("generated_afiliados") or 0)
                es = int(sm.get("expected_salarios") or 0)
                gs = int(sm.get("generated_salarios") or 0)
                line_items.append(
                    f"Hoja '{sh or ('Sede ' + sd)}': afiliados Excel={ea} vs generado={ga}, salarios Excel={es} vs generado={gs}."
                )
        if not reason_parts:
            reason_parts.append("Los TXT generados no cuadran contra el Excel.")
        human_msg = " ".join(reason_parts).strip()
        user_msg = (
            "Estimado usuario: su archivo de reporte Excel tiene inconsistencias. "
            "Por favor revise, corrija y radique nuevamente cuando esté correcto."
        )
        raise HTTPException(
            status_code=400,
            detail={
                "message": f"{user_msg} {human_msg}",
                "user_message": user_msg,
                "linea_a_linea": line_items[:80],
                "quality_controls": qc,
            },
        )
    return out


@router.get("/doc-code/examples")
def nova_doc_code_examples(x_api_key: Optional[str] = Header(default=None)) -> dict[str, Any]:
    _assert_api_key_if_required(x_api_key)
    return nova.doc_code_examples_list()


@router.post("/doc-code/train-upload")
async def nova_doc_code_train_upload(
    file: UploadFile = File(...),
    code: int = Form(...),
    name: str = Form(""),
    x_api_key: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    _assert_api_key_if_required(x_api_key)
    filename = Path(str(file.filename or "")).name
    if not filename:
        raise HTTPException(status_code=400, detail="Archivo inválido.")
    raw = await file.read()
    out = nova.doc_code_train_example(
        filename=filename,
        mime_type=str(file.content_type or ""),
        file_bytes=raw,
        code=int(code),
        name=name,
    )
    if not bool(out.get("ok")):
        raise HTTPException(status_code=400, detail=str(out.get("message") or "No se pudo guardar ejemplo."))
    return out


@router.post("/doc-code/predict-upload")
async def nova_doc_code_predict_upload(
    file: UploadFile = File(...),
    x_api_key: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    _assert_api_key_if_required(x_api_key)
    filename = Path(str(file.filename or "")).name
    if not filename:
        raise HTTPException(status_code=400, detail="Archivo inválido.")
    raw = await file.read()
    out = nova.doc_code_predict_file(
        filename=filename,
        mime_type=str(file.content_type or ""),
        file_bytes=raw,
    )
    if not bool(out.get("ok")):
        raise HTTPException(status_code=400, detail=str(out.get("message") or "No se pudo clasificar archivo."))
    return out
