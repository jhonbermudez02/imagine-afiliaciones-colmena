import logging
import threading
import io
import zipfile
from difflib import SequenceMatcher
import json
import re
from typing import Any, Dict, List, Optional
from pathlib import Path
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, Response
from pydantic import BaseModel

from .cases import (
    analyze_case,
    export_manual_review_dataset,
    format_reason_lines,
    get_document_reviews_export_path,
    get_case_file_path,
    list_cases,
    load_case,
    normalize_haystack,
    only_digits,
    rebuild_document_registry,
    run_case_workflow,
    save_case,
    save_document_workspace,
    save_manual_review,
    search_cases,
    search_document_registry,
    store_case_files,
)
from .config import settings
from .notifications import send_case_notification, send_tester_activity_summary
from .rag import generate_grounded_answer, infer_operational_decision, reindex_knowledge, search_knowledge
from .services import get_eval_summary, get_feed_summary, get_system_health, get_system_status

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name)

GENERIC_OPERATIONAL_TERMS = {
    "afiliacion",
    "afiliaciones",
    "pre",
    "validacion",
    "prevalidacion",
    "pre-validacion",
    "radicado",
    "radicacion",
    "radicación",
    "radicar",
    "documento",
    "documentos",
    "formulario",
    "independiente",
    "independientes",
    "empresa",
    "empresas",
    "contrato",
    "contratos",
    "tramite",
    "tramites",
    "tramites",
    "proceso",
    "procesos",
}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_repair_workflow_queue() -> None:
    try:
        state = _get_workflow_queue_status()
        if not (state.get("active") or {}) and (state.get("queue") or []):
            _start_next_queued_case_if_any()
    except Exception as exc:
        logger.error("No pude reparar la cola de ejecución al iniciar: %s", exc)
    # Auto-recuperar casos en disco que no tienen workflow completado
    try:
        import asyncio as _asyncio
        from pathlib import Path as _Path
        cases_dir = _Path(settings.cases_dir)
        recovered = 0
        for case_dir in cases_dir.iterdir():
            if not case_dir.name.startswith("case-"):
                continue
            try:
                payload = load_case(case_dir.name)
                wf = (payload.get("analysis") or {}).get("workflow_run") or {}
                wf_status = str(wf.get("status") or "").strip()
                if wf_status in ("", "none", "failed", "queued"):
                    enqueue_case_workflow(case_dir.name)
                    recovered += 1
            except Exception:
                pass
        if recovered:
            logger.info("Auto-recuperados %d casos huérfanos al iniciar", recovered)
    except Exception as exc:
        logger.error("Error en auto-recuperación de casos: %s", exc)


class ConsultaRequest(BaseModel):
    consulta: str
    contexto: Optional[Dict] = None


class ConsultaResponse(BaseModel):
    respuesta: str
    fuentes: Optional[List[Dict]] = None
    confianza: Optional[float] = None


class RetrievalResponse(BaseModel):
    fuentes: List[Dict]
    confianza: Optional[float] = None


class WorkflowResponse(BaseModel):
    flow: str
    classification: str
    recommended_status: str
    summary: str
    required_documents: List[str]
    critical_validations: List[str]
    blockers: List[str]
    next_step: str
    recommended_channel: str
    references: Optional[List[str]] = None


class Compare926Request(BaseModel):
    left_case_id: Optional[str] = None
    left_content: Optional[str] = None
    right_case_id: Optional[str] = None
    right_content: Optional[str] = None


class CaseManualReviewRequest(BaseModel):
    kind: str
    filename: str
    verdict: str
    expected_type: Optional[str] = None
    comisiones: Optional[List[Dict[str, Any]]] = None


class CaseDocumentWorkspaceRequest(BaseModel):
    action: str
    filename: Optional[str] = None
    order: Optional[List[str]] = None


class Consolidated926Request(BaseModel):
    case_ids: List[str]


class FeedbackNoteRequest(BaseModel):
    name: str
    text: str


class TesterActivityRequest(BaseModel):
    tester_email: str
    tester_name: str
    action: str
    metadata: Optional[Dict[str, Any]] = None


SEARCH_CALIBRATION_PATH = Path(settings.cases_dir).parent / "evals" / "learning" / "search_calibration.json"
_SEARCH_CALIBRATION_CACHE: Optional[Dict[str, Any]] = None
FEEDBACK_NOTES_PATH = Path(settings.cases_dir).parent / "evals" / "feedback_notes.jsonl"
WORKFLOW_QUEUE_PATH = Path(settings.cases_dir) / "workflow_queue.json"
TESTER_ACTIVITY_LOG_PATH = Path(settings.cases_dir).parent / "evals" / "tester_activity_log.jsonl"
WORKFLOW_QUEUE_LOCK = threading.RLock()
WORKFLOW_QUEUE_WORKER: Optional[threading.Thread] = None


def _load_tester_roster() -> List[Dict[str, str]]:
    path = Path(settings.notification_recipients_path)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    recipients = payload.get("recipients") if isinstance(payload, dict) else payload
    if not isinstance(recipients, list):
        return []
    out: List[Dict[str, str]] = []
    for item in recipients:
        if not isinstance(item, dict):
            continue
        email = str(item.get("email") or "").strip().lower()
        name = str(item.get("name") or "").strip()
        if not email:
            continue
        out.append({"email": email, "name": name})
    return out


def _append_tester_activity(entry: Dict[str, Any]) -> None:
    TESTER_ACTIVITY_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TESTER_ACTIVITY_LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _iter_tester_activity() -> List[Dict[str, Any]]:
    if not TESTER_ACTIVITY_LOG_PATH.exists():
        return []
    items: List[Dict[str, Any]] = []
    for line in TESTER_ACTIVITY_LOG_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        if isinstance(item, dict):
            items.append(item)
    return items


def _summarize_tester_activity(date_str: Optional[str] = None) -> Dict[str, Any]:
    roster = _load_tester_roster()
    target_date = date_str or datetime.now().strftime("%Y-%m-%d")
    rows = _iter_tester_activity()
    by_email: Dict[str, Dict[str, Any]] = {
        item["email"]: {
            "email": item["email"],
            "name": item.get("name") or item["email"],
            "total_actions": 0,
            "cases_created": 0,
            "workflow_started": 0,
            "searches": 0,
            "feedback_notes": 0,
            "reports_opened": 0,
            "documents_opened": 0,
            "last_activity": "",
        }
        for item in roster
    }
    for row in rows:
        created_at = str(row.get("created_at") or "")
        if not created_at.startswith(target_date):
            continue
        email = str(row.get("tester_email") or "").strip().lower()
        if not email:
            continue
        bucket = by_email.setdefault(email, {
            "email": email,
            "name": str(row.get("tester_name") or email),
            "total_actions": 0,
            "cases_created": 0,
            "workflow_started": 0,
            "searches": 0,
            "feedback_notes": 0,
            "reports_opened": 0,
            "documents_opened": 0,
            "last_activity": "",
        })
        action = str(row.get("action") or "").strip().lower()
        bucket["total_actions"] += 1
        if action == "case_created":
            bucket["cases_created"] += 1
        elif action == "workflow_started":
            bucket["workflow_started"] += 1
        elif action == "search_sent":
            bucket["searches"] += 1
        elif action == "feedback_saved":
            bucket["feedback_notes"] += 1
        elif action in {"open_executive_report", "open_precheck_report"}:
            bucket["reports_opened"] += 1
        elif action in {"open_classification", "open_documents", "open_926"}:
            bucket["documents_opened"] += 1
        if created_at > str(bucket.get("last_activity") or ""):
            bucket["last_activity"] = created_at
    items = list(by_email.values())
    items.sort(key=lambda item: (-int(item["total_actions"]), str(item["name"])))
    inactive = [item for item in items if int(item["total_actions"]) == 0]
    active = [item for item in items if int(item["total_actions"]) > 0]
    return {
        "date": target_date,
        "total_events": sum(int(item["total_actions"]) for item in items),
        "active_testers": len(active),
        "inactive_count": len(inactive),
        "items": items,
        "top_testers": active[:10],
        "inactive_testers": inactive,
    }


def _load_search_calibration() -> Dict[str, Any]:
    global _SEARCH_CALIBRATION_CACHE
    if _SEARCH_CALIBRATION_CACHE is not None:
        return _SEARCH_CALIBRATION_CACHE
    try:
        _SEARCH_CALIBRATION_CACHE = json.loads(SEARCH_CALIBRATION_PATH.read_text(encoding="utf-8"))
    except Exception:
        _SEARCH_CALIBRATION_CACHE = {}
    return _SEARCH_CALIBRATION_CACHE


def _load_workflow_queue_state() -> Dict[str, Any]:
    if not WORKFLOW_QUEUE_PATH.exists():
        return {"active": None, "queue": [], "updated_at": datetime.now(timezone.utc).isoformat()}
    try:
        data = json.loads(WORKFLOW_QUEUE_PATH.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    return {
        "active": data.get("active"),
        "queue": list(data.get("queue") or []),
        "updated_at": data.get("updated_at") or datetime.now(timezone.utc).isoformat(),
    }


def _repair_stale_workflow_queue_state() -> Dict[str, Any]:
    with WORKFLOW_QUEUE_LOCK:
        state = _load_workflow_queue_state()
        active = state.get("active") or {}
        case_id = str(active.get("case_id") or "")
        if not case_id:
            return state
        try:
            payload = load_case(case_id)
        except Exception:
            state["active"] = None
            _save_workflow_queue_state(state)
            return state
        analysis = payload.get("analysis") or {}
        queue_status = analysis.get("queue_status") or {}
        workflow = analysis.get("workflow_run") or {}
        payload_status = str(payload.get("status") or "").strip().lower()
        queue_state = str(queue_status.get("state") or "").strip().lower()
        workflow_state = str(workflow.get("status") or "").strip().lower()
        started_at_raw = str(active.get("started_at") or "")
        active_age_seconds = 0.0
        if started_at_raw:
            try:
                started_at = datetime.fromisoformat(started_at_raw.replace("Z", "+00:00"))
                active_age_seconds = max(0.0, (datetime.now(timezone.utc) - started_at).total_seconds())
            except Exception:
                active_age_seconds = 0.0
        if payload_status == "processing" or queue_state == "processing" or workflow_state == "processing":
            WORKFLOW_TIMEOUT_SECONDS = 900
            if active_age_seconds > WORKFLOW_TIMEOUT_SECONDS:
                logger.error("Timeout de workflow para contrato %s - lleva %.0f minutos. Cancelando.", case_id, active_age_seconds / 60)
                try:
                    payload = load_case(case_id)
                    analysis = payload.setdefault("analysis", {}) or {}
                    wf = analysis.setdefault("workflow_run", {}) or {}
                    wf["status"] = "failed"
                    wf["stop_reason"] = "Timeout automatico: el workflow excedio 15 minutos."
                    payload["status"] = "failed"
                    analysis["workflow_run"] = wf
                    payload["analysis"] = analysis
                    save_case(payload)
                except Exception as e:
                    logger.error("Error al marcar timeout del caso %s: %s", case_id, e)
                state["active"] = None
                _save_workflow_queue_state(state)
                return state
            return state
        if active_age_seconds < 30:
            return state
        logger.warning("Limpiando cola huérfana del contrato %s. active persistido sin ejecución real.", case_id)
        state["active"] = None
        _save_workflow_queue_state(state)
        return state


def _save_workflow_queue_state(state: Dict[str, Any]) -> Dict[str, Any]:
    WORKFLOW_QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    WORKFLOW_QUEUE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return state


def _queue_case_meta(payload: Dict[str, Any]) -> Dict[str, Any]:
    analysis = payload.get("analysis") or {}
    profile = ((analysis.get("xlsx_profile") or {}).get("profile") or {})
    empresa = profile.get("empresa") or payload.get("label") or payload.get("id")
    nit = profile.get("nit") or ""
    return {
        "case_id": payload.get("id"),
        "label": payload.get("label") or "",
        "empresa": empresa,
        "nit": nit,
        "updated_at": payload.get("updated_at") or datetime.now(timezone.utc).isoformat(),
    }


def _set_case_queue_status(case_id: str, queue_status: Dict[str, Any], status: Optional[str] = None) -> Dict[str, Any]:
    payload = load_case(case_id)
    analysis = payload.setdefault("analysis", {}) or {}
    analysis["queue_status"] = queue_status
    payload["analysis"] = analysis
    if status:
        payload["status"] = status
    return save_case(payload)


def _mark_case_workflow_processing(case_id: str, queue_status: Dict[str, Any], status: str = "processing") -> Dict[str, Any]:
    payload = load_case(case_id)
    analysis = payload.setdefault("analysis", {}) or {}
    analysis["queue_status"] = queue_status
    workflow = analysis.setdefault("workflow_run", {}) or {}
    workflow["status"] = "processing"
    workflow["current_step"] = "prevalidacion_documental"
    workflow["steps"] = []
    workflow["stop_reason"] = ""
    workflow["executive_report_precheck"] = None
    workflow["executive_report_final"] = None
    workflow["updated_at"] = datetime.now(timezone.utc).isoformat()
    analysis["workflow_run"] = workflow
    payload["analysis"] = analysis
    payload["status"] = status
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    return save_case(payload)


def _get_workflow_queue_status() -> Dict[str, Any]:
    return _repair_stale_workflow_queue_state()


def _send_case_notification_safe(payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        notification = send_case_notification(payload)
        analysis = payload.setdefault("analysis", {})
        workflow = analysis.setdefault("workflow_run", {})
        workflow["notification"] = notification
        save_case(payload)
        return notification
    except Exception as exc:
        logger.error("No pude procesar la notificación del caso %s: %s", payload.get("id"), exc)
        return {"ok": False, "delivery": "error", "error": str(exc)}


def _mark_case_workflow_failed(case_id: str, reason: str) -> None:
    try:
        payload = load_case(case_id)
    except Exception:
        return
    analysis = payload.setdefault("analysis", {}) or {}
    workflow = analysis.setdefault("workflow_run", {}) or {}
    workflow["status"] = "failed"
    workflow["stop_reason"] = reason
    workflow["updated_at"] = datetime.now(timezone.utc).isoformat()
    analysis["workflow_run"] = workflow
    analysis.pop("queue_status", None)
    payload["analysis"] = analysis
    payload["status"] = "failed"
    save_case(payload)


def _spawn_workflow_worker(case_id: str) -> None:
    global WORKFLOW_QUEUE_WORKER
    if not case_id:
        return
    if WORKFLOW_QUEUE_WORKER and WORKFLOW_QUEUE_WORKER.is_alive():
        return

    def _runner() -> None:
        global WORKFLOW_QUEUE_WORKER
        try:
            _mark_case_workflow_processing(
                case_id,
                {
                    "state": "processing",
                    "position": 0,
                    "active": _get_workflow_queue_status().get("active"),
                    "queue_length": len(_get_workflow_queue_status().get("queue") or []),
                },
                status="processing",
            )
            payload = run_case_workflow(case_id)
            _send_case_notification_safe(payload)
        except Exception as exc:
            logger.error("Error procesando contrato en cola %s: %s", case_id, exc)
            _mark_case_workflow_failed(case_id, f"No pude ejecutar el flujo automático: {exc}")
        finally:
            with WORKFLOW_QUEUE_LOCK:
                state = _load_workflow_queue_state()
                active = state.get("active") or {}
                if active.get("case_id") == case_id:
                    state["active"] = None
                    _save_workflow_queue_state(state)
            try:
                payload = load_case(case_id)
                analysis = payload.setdefault("analysis", {}) or {}
                analysis.pop("queue_status", None)
                payload["analysis"] = analysis
                save_case(payload)
            except Exception:
                pass
            WORKFLOW_QUEUE_WORKER = None
            _start_next_queued_case_if_any()

    WORKFLOW_QUEUE_WORKER = threading.Thread(target=_runner, daemon=True, name=f"queue-{case_id}")
    WORKFLOW_QUEUE_WORKER.start()


def _start_next_queued_case_if_any() -> None:
    global WORKFLOW_QUEUE_WORKER
    with WORKFLOW_QUEUE_LOCK:
        state = _load_workflow_queue_state()
        if state.get("active") or not state.get("queue"):
            return
        next_item = state["queue"].pop(0)
        state["active"] = {
            **next_item,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "status": "processing",
        }
        _save_workflow_queue_state(state)
    case_id = str(next_item.get("case_id") or "")
    _spawn_workflow_worker(case_id)


def _resolve_precheck_info(analysis: Dict[str, Any], case_item: Dict[str, Any]) -> Dict[str, Any]:
    raw = (analysis.get("validacion_resumen") or {}) if analysis else (case_item.get("precheck") or {})
    workflow = (analysis.get("workflow_run") or {}) if analysis else (case_item.get("workflow_run") or {})
    decision = (analysis.get("decision") or {}) if analysis else (case_item.get("decision") or {})
    nested = raw.get("precheck") if isinstance(raw, dict) else {}
    approved = None
    if isinstance(nested, dict) and nested.get("approved") is not None:
        approved = bool(nested.get("approved"))
    elif isinstance(raw, dict) and raw.get("approved") is not None:
        approved = bool(raw.get("approved"))
    elif str(workflow.get("status") or "").lower() == "stopped_prevalidacion":
        approved = False
    elif str(decision.get("recommended_status") or "").lower() == "aprobable":
        approved = True
    elif str(decision.get("recommended_status") or "").lower() in {"observado", "rechazado", "rechazado_prevalidacion"}:
        approved = False
    return {
        "approved": bool(approved),
        "raw": raw if isinstance(raw, dict) else {},
        "workflow": workflow if isinstance(workflow, dict) else {},
    }


def _unique_filenames(files: List[Any]) -> List[str]:
    seen: set[str] = set()
    ordered: List[str] = []
    for item in files or []:
        filename = str(item or "").strip()
        if not filename or filename in seen:
            continue
        seen.add(filename)
        ordered.append(filename)
    return ordered


def _compare_926_history_path() -> Path:
    path = Path(settings.compare_926_history_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _append_compare_926_history(entry: Dict[str, object]) -> None:
    path = _compare_926_history_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        if not isinstance(payload, list):
            payload = []
    except Exception:
        payload = []
    payload.append(entry)
    path.write_text(json.dumps(payload[-200:], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _resolve_926_content(case_id: Optional[str], content: Optional[str]) -> str:
    if content:
        return str(content)
    if not case_id:
        return ""
    payload = load_case(case_id)
    output_926 = (payload.get("analysis") or {}).get("output_926") or {}
    legacy = output_926.get("legacy") or {}
    draft = output_926.get("draft") or (payload.get("analysis") or {}).get("draft_926") or {}
    if legacy.get("ok") and legacy.get("content"):
        return str(legacy.get("content"))
    if draft.get("content"):
        return str(draft.get("content"))
    return ""


def _resolve_case_identity(case_id: Optional[str]) -> Dict[str, str]:
    if not case_id:
        return {"empresa": "", "nit": "", "documento": ""}
    try:
        payload = load_case(case_id)
    except FileNotFoundError:
        return {"empresa": "", "nit": "", "documento": ""}
    profile = (((payload.get("analysis") or {}).get("xlsx_profile") or {}).get("profile") or {})
    return {
        "empresa": str(profile.get("empresa") or ""),
        "nit": str(profile.get("nit") or ""),
        "documento": str(profile.get("documento") or ""),
    }


def _normalize_926_operational_line(line: str) -> str:
    pattern = re.compile(
        r"(20260401)(\d{8})(2000003\s+000000J)(\d{12})(000001600120260227)(\d{12})(\d{8})(9\s+3144437920)"
    )
    match = pattern.search(line)
    if not match:
        return line
    return (
        match.group(1)
        + "<FECHA_PROCESO>"
        + match.group(3)
        + "<NROENT>"
        + match.group(5)
        + "<WHLT>"
        + "<FECLOC>"
        + match.group(8)
    )


def _normalize_926_operational_content(content: str) -> str:
    lines = content.splitlines()
    if not lines:
        return content
    lines[0] = _normalize_926_operational_line(lines[0])
    return "\n".join(lines)


class ReindexResponse(BaseModel):
    documents: int
    chunks: int


class CaseCreateResponse(BaseModel):
    id: str
    label: str
    status: str
    created_at: str
    updated_at: str
    files: List[Dict]
    analysis: Optional[Dict] = None
    upload_summary: Optional[Dict[str, Any]] = None


class CaseListResponse(BaseModel):
    cases: List[Dict]


def _looks_like_person_name(value: str) -> bool:
    text = " ".join(str(value or "").strip().split())
    if len(text) < 8:
        return False
    lowered = text.lower()
    blocked = [
        "mora",
        "acuerdo",
        "urbana",
        "codigo",
        "formulario",
        "sede principal",
        "republica de colombia",
        "firma",
        "identificacion",
        "identificación",
        "representante legal",
        "documento consecutivo",
        "nit descentralizado",
        "nombres",
        "apellidos",
        "fecha de nacimiento",
        "fecha y lugar",
        "lugar de expedicion",
        "lugar de expedición",
        "fecha de expiracion",
        "fecha de expiración",
        "nacionalidad",
        "col nacionalidad",
        "cedula de ciudadania",
        "cédula de ciudadanía",
    ]
    if any(token in lowered for token in blocked):
        return False
    tokens = [token for token in text.split() if token]
    return len(tokens) >= 2


def _clean_person_name(candidate: str) -> str:
    text = normalize_haystack(candidate or "").upper()
    if not text:
        return ""
    text = re.sub(
        r"\b(REPUBLICA DE COLOMBIA|REPUBLICA|COLOMBIA|FIRMA|NOMBRES|APELLIDOS|COL|NACIONALIDAD|FECHA|DE NACIMIENTO|Y LUGAR|DE EXPEDICION|DE EXPEDICIÓN|EXPEDICION|EXPEDICIÓN|LUGAR|CIUDADANIA|CIUDADANÍA)\b",
        " ",
        text,
    )
    text = re.sub(r"\bPDA\b", " ", text)
    text = re.sub(r"\bJERK\b", " ", text)
    text = re.sub(r"\bC ECTOR\b", " HECTOR", text)
    text = re.sub(r"\bECTOR\b", "HECTOR", text)
    text = re.sub(r"\b(CC|C\.C\.)\b.*$", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _prefer_document_display_name(item: Dict[str, Any]) -> str:
    person_name = str(item.get("person_name") or "").strip()
    if _looks_like_person_name(person_name):
        return person_name
    person_document = only_digits(str(item.get("person_document") or item.get("document_number") or ""))
    if str(item.get("document_type") or "") == "cedula" and person_document:
        return f"documento {person_document}"
    company = str(item.get("company") or item.get("label") or "").strip()
    if company:
        return company
    return "n/d"


def _derive_full_representative_name(case_id: str, fallback_document: str = "", seed_name: str = "") -> str:
    try:
        payload = load_case(case_id)
    except Exception:
        return ""
    expected_doc = re.sub(r"\D+", "", str(fallback_document or ""))
    seed_tokens = [token.upper() for token in normalize_haystack(seed_name or "").split() if len(token) >= 4]
    candidates: List[str] = []
    blocked_tokens = {"NOMBRE", "IDENTIFICACION", "IDENTIFICACIÓN", "REPRESENTANTE", "LEGAL", "PRIMER", "SEGUNDO", "APELLIDO", "NOMBRES"}
    for doc in ((payload.get("analysis") or {}).get("documents") or []):
        text = str(doc.get("ocr_text") or doc.get("text_preview") or "")
        upper = text.upper()
        compact_digits = re.sub(r"\D+", "", upper)
        if expected_doc and expected_doc not in compact_digits:
            continue
        compact = re.sub(r"\s+", " ", upper)
        doc_type = str(doc.get("document_type") or "")
        if doc_type in {"carta", "pdf"} and expected_doc:
            explicit_letter_patterns = [
                r"ATENTAMENTE[, ]+([A-ZÁÉÍÓÚÑ ]{6,90})\s+CC\s+%s" % re.escape(expected_doc),
                r"([A-ZÁÉÍÓÚÑ ]{6,90})\s+CC\s+%s\s+REPRESENTANTE LEGAL" % re.escape(expected_doc),
                r"REPRESENTANTE LEGAL\s+([A-ZÁÉÍÓÚÑ ]{6,90})\s+CC\s+%s" % re.escape(expected_doc),
            ]
            for pattern in explicit_letter_patterns:
                match = re.search(pattern, compact)
                if not match:
                    continue
                candidate = _clean_person_name(match.group(1))
                if _looks_like_person_name(candidate) and not any(token in blocked_tokens for token in candidate.split()):
                    if not seed_tokens or any(token in candidate for token in seed_tokens):
                        return candidate
        if doc_type == "cedula":
            modern_match = re.search(
                r"([A-ZÁÉÍÓÚÑ ]{3,80})\s+NOMBRES\s+([A-ZÁÉÍÓÚÑ ]{3,80})\s+APELLIDOS",
                compact,
            )
            if modern_match:
                given_names = _clean_person_name(modern_match.group(1))
                surnames = _clean_person_name(modern_match.group(2))
                candidate = " ".join(part for part in [given_names, surnames] if part).strip()
                if _looks_like_person_name(candidate) and not any(token in blocked_tokens for token in candidate.split()):
                    if not seed_tokens or any(token in candidate for token in seed_tokens):
                        return candidate
            explicit_patterns = [
                r"NOMBRES\s+([A-ZÁÉÍÓÚÑ ]{3,60})\s+APELLIDOS\s+([A-ZÁÉÍÓÚÑ ]{3,60})",
                r"([A-ZÁÉÍÓÚÑ ]{3,60})\s+NOMBRES\s+([A-ZÁÉÍÓÚÑ ]{3,60})\s+APELLIDOS",
            ]
            for pattern in explicit_patterns:
                match = re.search(pattern, compact)
                if not match:
                    continue
                if pattern.startswith("NOMBRES"):
                    candidate = " ".join(
                        [
                            _clean_person_name(match.group(1)),
                            _clean_person_name(match.group(2)),
                        ]
                    ).strip()
                else:
                    candidate = " ".join(
                        [
                            _clean_person_name(match.group(1)),
                            _clean_person_name(match.group(2)),
                        ]
                    ).strip()
                if _looks_like_person_name(candidate) and not any(token in blocked_tokens for token in candidate.split()):
                    if not seed_tokens or any(token in candidate for token in seed_tokens):
                        return candidate
        if doc_type == "carta" and expected_doc:
            match = re.search(r"([A-ZÁÉÍÓÚÑ ]{6,80})\s+CC\s+%s" % re.escape(expected_doc), compact)
            if match:
                candidate = _clean_person_name(match.group(1))
                if _looks_like_person_name(candidate) and not any(token in blocked_tokens for token in candidate.split()):
                    if not seed_tokens or any(token in candidate for token in seed_tokens):
                        return candidate
        # Cedula moderna: "Nombres ... Apellidos ..."
        cedula_name = re.search(
            r"NOMBRES\s+([A-ZÁÉÍÓÚÑ ]{3,60})\s+APELLIDOS\s+([A-ZÁÉÍÓÚÑ ]{3,60})",
            compact,
        )
        if cedula_name:
            candidate = " ".join(
                [
                    _clean_person_name(cedula_name.group(1)),
                    _clean_person_name(cedula_name.group(2)),
                ]
            ).strip()
            if _looks_like_person_name(candidate) and not any(token in blocked_tokens for token in candidate.split()):
                if not seed_tokens or any(token in candidate for token in seed_tokens):
                    candidates.append(candidate)
                    continue
        # Cartas o certificaciones: nombre antes de CC/documento
        carta_name = re.search(
            r"([A-ZÁÉÍÓÚÑ]{3,}(?:\s+DE)?(?:\s+[A-ZÁÉÍÓÚÑ]{3,}){1,5})\s+CC\s+%s" % re.escape(expected_doc) if expected_doc else r"$^",
            compact,
        )
        if carta_name:
            candidate = _clean_person_name(carta_name.group(1))
            if _looks_like_person_name(candidate) and not any(token in blocked_tokens for token in candidate.split()):
                if not seed_tokens or any(token in candidate for token in seed_tokens):
                    candidates.append(candidate)
                    continue
        if "PRIMER APELLIDO" in compact and "PRIMER NOMBRE" in compact:
            surname_match = re.search(r"PRIMER APELLIDO[: ]+([A-ZÁÉÍÓÚÑ ]{3,40})\s+DEPARTAMENTO", compact)
            name_match = re.search(r"PRIMER NOMBRE[: ]+([A-ZÁÉÍÓÚÑ ]{3,40})\s+TIPO DE DOCUMENTO", compact)
            if surname_match and name_match:
                candidate = " ".join(
                    [
                        _clean_person_name(surname_match.group(1)),
                        _clean_person_name(name_match.group(1)),
                    ]
                ).strip()
                if _looks_like_person_name(candidate) and not any(token in blocked_tokens for token in candidate.split()):
                    if seed_tokens and not any(token in candidate for token in seed_tokens):
                        pass
                    else:
                        candidates.append(candidate)
                    continue
        for match in re.finditer(r"([A-ZÁÉÍÓÚÑ]{3,})\s+([A-ZÁÉÍÓÚÑ]{3,})\s+([A-ZÁÉÍÓÚÑ]{3,})\s+([A-ZÁÉÍÓÚÑ]{3,})", compact):
            candidate = _clean_person_name(" ".join(part.strip() for part in match.groups()))
            if any(token in {"URBANA", "BARRANQUILLA", "PRINCIPAL", "ATLANTICO", "CODIGO"} for token in candidate.split()):
                continue
            if _looks_like_person_name(candidate) and not any(token in blocked_tokens for token in candidate.split()):
                if seed_tokens and not any(token in candidate for token in seed_tokens):
                    continue
                candidates.append(candidate)
    if not candidates:
        return ""
    candidates.sort(key=lambda item: (-len(item.split()), -len(item)))
    return candidates[0]


def _build_formatted_report_text(report: Dict) -> str:
    if not report:
        return ""
    resumen = report.get("resumen_ejecutivo") or {}
    lines = [
        f"Reporte ejecutivo del caso {resumen.get('caso') or 'caso'}",
        f"Estado final: {resumen.get('estado') or report.get('estado_final') or 'n/d'}",
    ]
    fecha_proceso = resumen.get("fecha_proceso_human") or report.get("fecha_proceso_human") or resumen.get("fecha_proceso") or report.get("fecha_proceso")
    if fecha_proceso:
        lines.append(f"Fecha de proceso: {fecha_proceso}")
    lines.extend(
        [
            f"Afiliado: {resumen.get('empresa') or report.get('empresa') or 'n/d'}",
            f"NIT: {resumen.get('nit') or report.get('nit') or 'n/d'}",
            f"Trabajadores: {resumen.get('numero_trabajadores', 'n/d')}",
            f"Sedes: {resumen.get('numero_sedes', 'n/d')}",
        ]
    )
    errores = list(resumen.get("errores") or [])
    if errores:
        lines.append("Hallazgos:")
        for item in errores[:8]:
            reason_lines = format_reason_lines(item)
            if not reason_lines:
                continue
            lines.append(f"- {reason_lines[0]}")
            lines.extend(reason_lines[1:])
    observaciones = list(resumen.get("observaciones") or [])
    if observaciones:
        lines.append("Observaciones:")
        for item in observaciones[:8]:
            reason_lines = format_reason_lines(item)
            if not reason_lines:
                continue
            lines.append(f"- {reason_lines[0]}")
            lines.extend(reason_lines[1:])
    acciones = list(resumen.get("acciones_recomendadas") or [])
    if acciones:
        lines.append("Acciones recomendadas:")
        lines.extend(f"- {item}" for item in acciones[:6])
    return "\n".join(lines)


def build_case_consulta_response(query: str, results: List[Dict]) -> Optional[ConsultaResponse]:
    if not results:
        return None
    top = results[0]
    top_score = int(top.get("score") or 0)
    if top_score < 12:
        return None
    profile = top.get("profile") or {}
    matched = top.get("matched_documents") or []
    top_company = normalize_haystack((top.get("profile") or {}).get("empresa") or top.get("label") or "")
    top_representative = normalize_haystack((top.get("profile") or {}).get("nombre") or "")
    query_norm = normalize_haystack(query)
    query_tokens = [token for token in query_norm.split() if len(token) >= 4]
    generic_case_terms = {
        "pre",
        "validacion",
        "prevalidacion",
        "pre-validacion",
        "radicado",
        "radicacion",
        "radicación",
        "radicar",
        "afiliacion",
        "afiliaciones",
        "novedades",
        "riesgos",
        "laborales",
        "laboral",
        "independiente",
        "independientes",
        "empresa",
        "empresas",
        "trabajador",
        "trabajadores",
        "contrato",
        "contratos",
        "formulario",
        "documento",
        "documentos",
    }
    company_ratio = max(
        [SequenceMatcher(None, query_norm, token).ratio() for token in top_company.split() if len(token) >= 4] or [0.0]
    )
    representative_ratio = max(
        [SequenceMatcher(None, query_norm, token).ratio() for token in top_representative.split() if len(token) >= 4] or [0.0]
    )

    def case_query_signal(item: Dict) -> int:
        profile_item = item.get("profile") or {}
        company = normalize_haystack(profile_item.get("empresa") or item.get("label") or "")
        representative = normalize_haystack(profile_item.get("nombre") or "")
        score = 0
        for token in query_tokens:
            if token and token in company:
                score += 6
            if token and token in representative:
                score += 4
        return score

    top_signal = case_query_signal(top)
    has_numeric_signal = bool(re.search(r"\d{4,}", query_norm))
    meaningful_tokens = [token for token in query_tokens if token not in generic_case_terms]
    if not has_numeric_signal and top_signal == 0 and max(company_ratio, representative_ratio) < 0.8:
        if not meaningful_tokens:
            return None

    if len(results) > 1:
        near = [item for item in results[:5] if int(item.get("score") or 0) >= max(top_score - 6, 8)]
        if len(query_tokens) == 1:
            second_score = int(results[1].get("score") or 0) if len(results) > 1 else 0
            if top_score >= second_score + 25 or (second_score > 0 and top_score >= int(second_score * 1.8)):
                near = [top]
            strong_near = [
                item for item in results[:5]
                if case_query_signal(item) >= 4 and int(item.get("score") or 0) >= max(int(top_score * 0.3), 20)
            ]
            distinct_entities = {
                normalize_haystack((item.get("profile") or {}).get("empresa") or item.get("label") or "")
                for item in strong_near
            }
            if len(distinct_entities) > 1 and len(near) > 1:
                near = strong_near
        if max(company_ratio, representative_ratio) >= 0.8:
            near = [top]
    else:
        near = results[:1]
    if len(near) > 1:
        unique_near: List[Dict] = []
        seen_options = set()
        for item in near:
            profile_item = item.get("profile") or {}
            option_key = (
                normalize_haystack(profile_item.get("empresa") or item.get("label") or ""),
                normalize_haystack(profile_item.get("nombre") or ""),
                str(profile_item.get("documento") or ""),
            )
            if option_key in seen_options:
                continue
            seen_options.add(option_key)
            unique_near.append(item)
        options = [
            f"- {item.get('profile', {}).get('empresa') or item.get('label')} · representante {item.get('profile', {}).get('nombre') or 'n/d'} · documento {item.get('profile', {}).get('documento') or 'n/d'}"
            for item in unique_near[:5]
        ]
        text = "Respuesta ejecutiva:\n\nCoincidencias encontradas:\n" + "\n".join(options) + "\n\nSiguiente paso:\n- Indica cuál empresa o independiente quieres abrir o revisar."
        fuentes = []
    else:
        display_name = str(profile.get("nombre") or "").strip()
        if not _looks_like_person_name(display_name):
            display_name = ""
        name_tokens = [token for token in str(display_name).strip().split() if token]
        if (len(str(display_name).strip()) < 8 or len(name_tokens) < 2) and profile.get("documento"):
            doc_candidates = search_document_registry(str(profile.get("documento")), limit=5)
            for item in doc_candidates:
                if item.get("case_id") != top.get("case_id"):
                    continue
                candidate = item.get("person_name") or ""
                if _looks_like_person_name(candidate):
                    display_name = candidate
                    break
        name_tokens = [token for token in str(display_name).strip().split() if token]
        if len(str(display_name).strip()) < 8 or len(name_tokens) < 2:
            for item in matched:
                candidate = item.get("person_name") or ""
                if _looks_like_person_name(candidate):
                    display_name = candidate
                    break
        name_tokens = [token for token in str(display_name).strip().split() if token]
        if not _looks_like_person_name(display_name):
            display_name = f"documento {profile.get('documento')}" if profile.get("documento") else "n/d"
        precheck_info = _resolve_precheck_info({}, top)
        precheck = precheck_info["raw"]
        precheck_approved = precheck_info["approved"]
        executive_report = top.get("executive_report") or {}
        received_summary = top.get("received_summary") or []
        decision = top.get("decision") or {}
        workers = (
            executive_report.get("resumen_ejecutivo", {}).get("numero_trabajadores")
            or profile.get("numero_trabajadores")
            or "n/d"
        )
        sedes = (
            executive_report.get("resumen_ejecutivo", {}).get("numero_sedes")
            or profile.get("numero_sedes")
            or "n/d"
        )
        fecha_proceso = (
            executive_report.get("resumen_ejecutivo", {}).get("fecha_proceso_human")
            or executive_report.get("fecha_proceso_human")
            or executive_report.get("resumen_ejecutivo", {}).get("fecha_proceso")
            or executive_report.get("fecha_proceso")
            or profile.get("fecha_proceso")
            or "n/d"
        )
        if fecha_proceso == "n/d":
            updated_at = str(top.get("updated_at") or "")
            try:
                fecha_proceso = datetime.fromisoformat(updated_at.replace("Z", "+00:00")).strftime("%d/%m/%Y")
            except ValueError:
                pass
        fecha_digits = re.sub(r"\D+", "", str(fecha_proceso or ""))
        if fecha_proceso != "n/d" and len(fecha_digits) == 8:
            try:
                fecha_proceso = datetime.strptime(fecha_digits, "%Y%m%d").strftime("%d/%m/%Y")
            except ValueError:
                pass
        rejection_reasons = list((executive_report.get("resumen_ejecutivo", {}) or {}).get("errores") or [])
        lines = [
            "Respuesta ejecutiva:",
            "",
            "Empresa o independiente identificado:",
            f"- Empresa: {profile.get('empresa') or top.get('label') or 'n/d'}",
            f"- Representante: {display_name}",
            f"- Documento: {profile.get('documento') or 'n/d'}",
            f"- NIT: {profile.get('nit') or 'n/d'}",
            f"- Tipo de afiliación: {profile.get('tipo_afiliado') or 'n/d'}",
            f"- Trabajadores: {workers}",
            f"- Sedes: {sedes}",
            f"- Fecha del proceso: {fecha_proceso}",
            f"- Prevalidación: {'APROBADA' if precheck_approved else 'NO APROBADA'}",
        ]
        if not precheck_approved:
            if rejection_reasons:
                lines.extend(["", "Motivo del rechazo:"])
                for item in rejection_reasons[:8]:
                    reason_lines = format_reason_lines(item)
                    if not reason_lines:
                        continue
                    lines.append(f"- {reason_lines[0]}")
                    lines.extend(reason_lines[1:])
            lines.extend(
                [
                    "",
                    "Reporte ejecutivo de prevalidación:",
                    _build_formatted_report_text(executive_report) or "La prevalidación no fue aprobada.",
                ]
            )
        elif decision.get("summary"):
            lines.extend(["", f"Estado operativo: {decision.get('summary')}"])
        if received_summary:
            lines.extend(["", "Adjuntos clasificados:"])
            for item in received_summary[:12]:
                lines.append(
                    f"- {item.get('label') or item.get('document_type')}: {item.get('count', 0)} archivo(s) · códigos {', '.join(str(code) for code in (item.get('legacy_codes') or [])) or 'n/d'}"
                )
        document_options: List[Dict[str, Any]] = []
        for item in received_summary[:12]:
            for filename in (item.get("files") or [])[:4]:
                document_options.append(
                    {
                        "titulo": filename,
                        "contenido": f"{item.get('label') or item.get('document_type')} · código {', '.join(str(code) for code in (item.get('legacy_codes') or [])) or 'n/d'}",
                        "relevancia": 0.95,
                        "topic": "expediente",
                        "document_type": item.get("document_type"),
                        "source_url": f"/api/cases/{top.get('case_id')}/files/{filename}",
                    }
                )
        if document_options:
            lines.extend(["", "Documentos disponibles para abrir:"])
            for item in document_options[:8]:
                lines.append(
                    f"- {item.get('titulo')} · {item.get('contenido')}"
                )
        elif matched:
            lines.extend(["", "Documentos relacionados:"])
            for item in matched[:5]:
                lines.append(f"- {item.get('document_type')}: {item.get('filename')}")
        lines.extend(["", "Siguiente paso:", "- Revisa los documentos del expediente o solicita el detalle de la empresa o independiente."])
        text = "\n".join(lines)
        fuentes = document_options[:8] if document_options else []
    if 'fuentes' not in locals():
        fuentes = []
    if not fuentes and len(near) <= 1:
        for item in matched[:5]:
            fuentes.append(
                {
                    "titulo": item.get("filename"),
                    "contenido": item.get("snippet") or "",
                    "relevancia": min(float(item.get("score") or 0) / 20.0, 1.0),
                    "topic": "expediente",
                    "document_type": item.get("document_type"),
                    "source_url": f"/api/cases/{top.get('case_id')}/files/{item.get('filename')}",
                }
            )
    return ConsultaResponse(respuesta=text, fuentes=fuentes, confianza=min(top_score / 20.0, 1.0))


def build_document_consulta_response(query: str, results: List[Dict]) -> Optional[ConsultaResponse]:
    if not results:
        return None
    query_norm = normalize_haystack(query)
    generic_document_terms = {
        "pre",
        "validacion",
        "prevalidacion",
        "pre-validacion",
        "radicado",
        "radicacion",
        "radicación",
        "radicar",
        "afiliacion",
        "afiliaciones",
        "novedades",
        "riesgos",
        "laborales",
        "laboral",
        "independiente",
        "independientes",
        "empresa",
        "empresas",
        "trabajador",
        "trabajadores",
        "contrato",
        "contratos",
        "documento",
        "documentos",
        "formulario",
    }
    query_tokens = [token for token in query_norm.split() if len(token) >= 4]
    meaningful_tokens = [token for token in query_tokens if token not in generic_document_terms]
    if not meaningful_tokens and not re.search(r"\d{4,}", query_norm):
        return None
    preferred_types: List[str] = []
    if "cedula" in query_norm or "cédula" in query.lower():
        preferred_types.append("cedula")
    if "rut" in query_norm:
        preferred_types.append("rut")
    if "camara" in query_norm or "cámara" in query.lower():
        preferred_types.append("camara_comercio")
    if "formulario" in query_norm:
        preferred_types.append("formulario_afiliacion")
    if "entrega" in query_norm:
        preferred_types.append("entrega_documentos")
    if "soporte" in query_norm or "ingreso" in query_norm:
        preferred_types.append("soporte_ingresos")
    if "sede" in query_norm:
        preferred_types.append("anexo_sedes")
    if preferred_types:
        results = sorted(
            results,
            key=lambda item: (
                0 if str(item.get("document_type") or "") in preferred_types else 1,
                -int(item.get("score") or 0),
            ),
        )
    top = results[0]
    top_score = int(top.get("score") or 0)
    if top_score < 12:
        return None
    same_band = [item for item in results[:8] if int(item.get("score") or 0) >= max(top_score - 4, 10)]
    if preferred_types:
        preferred_band = [item for item in same_band if str(item.get("document_type") or "") in preferred_types]
        if preferred_band:
            same_band = preferred_band
            top = same_band[0]
    unique_band = []
    seen_band = set()
    for item in same_band:
        normalized_filename = normalize_haystack(Path(str(item.get("filename") or "")).name)
        key = (
            str(item.get("document_type") or ""),
            normalize_haystack(str(item.get("company") or "")),
            only_digits(str(item.get("person_document") or "")) or only_digits(str(item.get("document_number") or "")),
            normalized_filename,
        )
        if key in seen_band:
            continue
        seen_band.add(key)
        unique_band.append(item)
    same_band = unique_band

    def _document_result_label(item: Dict[str, Any]) -> str:
        document_type = str(item.get("document_type") or "")
        if document_type in {"camara_comercio", "rut", "formulario_afiliacion", "anexo_sedes"}:
            return str(item.get("company") or item.get("label") or item.get("person_name") or "n/d")
        return _prefer_document_display_name(item)

    if len(same_band) > 1:
        options = [
            f"- {_document_result_label(item)} · {item.get('document_type')} · {item.get('filename')}"
            for item in same_band[:6]
        ]
        text = "Respuesta ejecutiva:\n\nCoincidencias documentales:\n" + "\n".join(options) + "\n\nSiguiente paso:\n- Indica cuál documento quieres abrir o revisar."
    else:
        text = "\n".join(
            [
                "Respuesta ejecutiva:",
                "",
                "Documento identificado:",
                f"- Empresa: {top.get('company') or 'n/d'}",
                f"- Persona: {_prefer_document_display_name(top)}",
                f"- Documento: {top.get('person_document') or top.get('document_number') or 'n/d'}",
                f"- Tipo documental: {top.get('document_type') or 'n/d'}",
                f"- Archivo: {top.get('filename') or 'n/d'}",
                "",
                "Siguiente paso:",
                "- Revisa el documento en el visor o pide el detalle de la empresa o independiente.",
            ]
        )
    fuentes = [
        {
            "titulo": item.get("filename"),
            "contenido": item.get("text_preview") or "",
            "relevancia": min(float(item.get("score") or 0) / 20.0, 1.0),
            "topic": "documento",
            "document_type": item.get("document_type"),
            "source_url": f"/api/cases/{item.get('case_id')}/files/{item.get('filename')}",
        }
        for item in same_band[:6]
    ]
    return ConsultaResponse(respuesta=text, fuentes=fuentes, confianza=min(top_score / 20.0, 1.0))


def _is_generic_operational_query(query: str) -> bool:
    query_norm = normalize_haystack(query)
    if re.search(r"\d{4,}", query_norm):
        return False
    tokens = [token for token in query_norm.split() if len(token) >= 4]
    if not tokens:
        return True
    return all(token in GENERIC_OPERATIONAL_TERMS for token in tokens)


SUPPORTED_CASE_UPLOAD_EXTENSIONS = {
    ".xlsx",
    ".xlsm",
    ".xls",
    ".pdf",
    ".zip",
    ".png",
    ".jpg",
    ".jpeg",
    ".tif",
    ".tiff",
    ".bmp",
    ".webp",
}


def _is_broad_location_query(query: str) -> bool:
    query_norm = normalize_haystack(query)
    broad_patterns = [
        r"\bafiliad[oa]s?\s+en\s+\w+",
        r"\bempresas?\s+en\s+\w+",
        r"\bexpedientes?\s+en\s+\w+",
        r"\bcontratos?\s+en\s+\w+",
    ]
    return any(re.search(pattern, query_norm) for pattern in broad_patterns)


def _is_case_disambiguation_response(response: Optional[ConsultaResponse]) -> bool:
    if response is None:
        return False
    return "Coincidencias encontradas:" in str(response.respuesta or "")


def _extract_case_anchor_tokens(query: str) -> List[str]:
    query_norm = normalize_haystack(query)
    ignore_terms = {
        "estado", "expediente", "prevalidacion", "validacion", "pre", "radicacion", "radicar",
        "quien", "representante", "legal", "muestrame", "muéstrame", "cedula", "rut", "camara",
        "comercio", "documento", "documentos", "nomina", "nómina", "trabajadores", "trabajador",
        "sedes", "cuantas", "cuantos", "tiene", "del", "de", "la", "el", "por", "que", "fue",
        "cual", "cuales", "es", "son", "nit", "firma", "firmar", "formulario", "recibio",
        "recibidos", "recibio?", "mostrar", "abre", "abrir", "archivo", "reporte",
        "observaciones", "observacion", "prevalidacion", "bloqueantes", "siguiente", "paso",
    }
    return [token for token in query_norm.split() if len(token) >= 4 and token not in ignore_terms]


def _select_best_case_result(query: str, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if len(results) <= 1:
        return results

    def _updated_at_value(item: Dict[str, Any]) -> float:
        raw = str(item.get("updated_at") or "")
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
        except Exception:
            return 0.0

    latest_by_entity: Dict[tuple[str, str], Dict[str, Any]] = {}
    for item in results:
        profile = item.get("profile") or {}
        entity_key = (
            normalize_haystack(str(profile.get("empresa") or item.get("label") or "")),
            only_digits(str(profile.get("documento") or "")),
        )
        current = latest_by_entity.get(entity_key)
        if current is None:
            latest_by_entity[entity_key] = item
            continue
        current_key = (_updated_at_value(current), int(current.get("score") or 0))
        incoming_key = (_updated_at_value(item), int(item.get("score") or 0))
        if incoming_key >= current_key:
            latest_by_entity[entity_key] = item
    results = list(latest_by_entity.values())
    if len(results) <= 1:
        return results

    strong_tokens = _extract_case_anchor_tokens(query)
    if not strong_tokens:
        return results

    def _signal(item: Dict[str, Any]) -> tuple[int, int, float]:
        profile = item.get("profile") or {}
        company = normalize_haystack(str(profile.get("empresa") or item.get("label") or ""))
        label = normalize_haystack(str(item.get("label") or ""))
        representative = normalize_haystack(str(profile.get("nombre") or ""))
        signal = 0
        for token in strong_tokens:
            if token in company:
                signal += 12
            if token in label:
                signal += 8
            if token in representative:
                signal += 6
        return signal, int(item.get("score") or 0), _updated_at_value(item)

    ranked = sorted(results, key=_signal, reverse=True)
    top_signal = _signal(ranked[0])[0]
    if top_signal <= 0:
        return []
    return ranked


def _case_has_strong_anchor(query: str, case_item: Dict[str, Any]) -> bool:
    query_norm = normalize_haystack(query)
    ignore_terms = {
        "estado", "expediente", "prevalidacion", "validacion", "pre", "radicacion", "radicar",
        "quien", "representante", "legal", "muestrame", "cedula", "rut", "camara", "comercio",
        "documento", "documentos", "nomina", "trabajadores", "trabajador", "sedes", "cuantas",
        "cuantos", "tiene", "del", "de", "la", "el", "por", "que", "fue", "cual", "cuales",
        "es", "son", "nit", "firma", "firmar", "formulario", "recibio", "recibidos", "abre",
        "abrir", "archivo",
    }
    strong_tokens = [token for token in query_norm.split() if len(token) >= 4 and token not in ignore_terms]
    if not strong_tokens:
        return False
    profile = case_item.get("profile") or {}
    haystack = " ".join(
        [
            normalize_haystack(str(profile.get("empresa") or "")),
            normalize_haystack(str(case_item.get("label") or "")),
            normalize_haystack(str(profile.get("nombre") or "")),
        ]
    )
    hits = sum(1 for token in strong_tokens if token in haystack)
    return hits >= 1


def _build_case_result_from_payload(payload: Dict[str, Any], score: int = 100) -> Dict[str, Any]:
    analysis = payload.get("analysis") or {}
    profile = ((analysis.get("xlsx_profile") or {}).get("profile") or {})
    docs = analysis.get("documents") or []
    removed_files = set(((analysis.get("document_workspace") or {}).get("removed_files") or []))
    workflow = analysis.get("workflow_run") or {}
    return {
        "case_id": payload.get("id"),
        "label": payload.get("label"),
        "status": payload.get("status"),
        "score": score,
        "updated_at": payload.get("updated_at") or "",
        "profile": profile,
        "lote_usuario": payload.get("lote_usuario") or profile.get("lote_usuario") or "",
        "entity_document_hint": only_digits(profile.get("documento", "")),
        "doc_signature": tuple(
            sorted(
                f"{normalize_haystack(doc.get('filename', ''))}|{normalize_haystack(doc.get('document_type', ''))}"
                for doc in docs
            )
        ),
        "matched_documents": [],
        "received_summary": ((analysis.get("checklist") or {}).get("received_summary") or [])[:20],
        "decision": analysis.get("decision") or {},
        "precheck": ((analysis.get("validacion_resumen") or {}).get("precheck") or {}),
        "executive_report": analysis.get("reporte_ejecutivo") or {},
    }


def _resolve_context_case(request_context: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(request_context, dict):
        return None
    case_id = str(request_context.get("active_case_id") or request_context.get("last_case_id") or "").strip()
    if case_id:
        try:
            payload = load_case(case_id)
            return _build_case_result_from_payload(payload, score=120)
        except Exception:
            pass

    active_nit = only_digits(str(request_context.get("active_nit") or ""))
    active_company = normalize_haystack(str(request_context.get("active_company") or ""))
    best_payload: Optional[Dict[str, Any]] = None
    best_key: tuple[float, int] = (0.0, 0)
    for payload in list_cases(include_all=True):
        analysis = payload.get("analysis") or {}
        profile = ((analysis.get("xlsx_profile") or {}).get("profile") or {})
        payload_nit = only_digits(str(profile.get("nit") or profile.get("documento_empleador") or ""))
        payload_company = normalize_haystack(str(profile.get("empresa") or payload.get("label") or ""))
        nit_match = bool(active_nit and payload_nit and active_nit == payload_nit)
        company_match = bool(active_company and payload_company and active_company in payload_company)
        if not nit_match and not company_match:
            continue
        raw_updated_at = str(payload.get("updated_at") or "")
        try:
            updated_ts = datetime.fromisoformat(raw_updated_at.replace("Z", "+00:00")).timestamp()
        except Exception:
            updated_ts = 0.0
        score = 2 if nit_match else 1
        key = (updated_ts, score)
        if best_payload is None or key >= best_key:
            best_payload = payload
            best_key = key
    if not best_payload:
        return None
    return _build_case_result_from_payload(best_payload, score=120)


def _query_matches_context_case(query: str, case_item: Optional[Dict[str, Any]]) -> bool:
    if not case_item:
        return False
    query_norm = normalize_haystack(query)
    profile = case_item.get("profile") or {}
    haystack = " ".join(
        [
            normalize_haystack(str(profile.get("empresa") or case_item.get("label") or "")),
            normalize_haystack(str(profile.get("nombre") or "")),
            only_digits(str(profile.get("nit") or "")),
            only_digits(str(profile.get("documento") or "")),
        ]
    )
    anchors = _extract_case_anchor_tokens(query)
    if not anchors:
        return False
    return any(token in haystack for token in anchors)


def _should_prefer_context_case(query: str, request_context: Optional[Dict[str, Any]], case_item: Optional[Dict[str, Any]]) -> bool:
    if not case_item:
        return False
    query_norm = normalize_haystack(query)
    anchors = _extract_case_anchor_tokens(query)
    followup_terms = {
        "y", "tambien", "también", "ahora", "ese", "esa", "este", "esta", "muestrame", "muéstrame",
        "abre", "abrir", "ver", "rut", "cedula", "cédula", "camara", "cámara", "formulario", "926",
        "prevalidacion", "prevalidación", "reporte", "observaciones", "bloqueantes", "siguiente", "paso",
        "quien", "firma", "representante", "nomina", "nómina", "trabajadores", "sedes", "documentos",
    }
    query_tokens = [token for token in query_norm.split() if token]
    if _query_matches_context_case(query, case_item):
        return True
    if not anchors:
        return True
    if query_tokens and all(token in followup_terms or len(token) < 4 for token in query_tokens):
        return True
    if _is_generic_operational_query(query):
        return True
    return False


def _context_case_reference(request_context: Optional[Dict[str, Any]], case_item: Optional[Dict[str, Any]]) -> str:
    profile = (case_item or {}).get("profile") or {}
    company = str(
        (request_context or {}).get("active_company")
        or profile.get("empresa")
        or (case_item or {}).get("label")
        or ""
    ).strip()
    if company:
        return company
    nit = only_digits(
        str(
            (request_context or {}).get("active_nit")
            or profile.get("nit")
            or profile.get("documento_empleador")
            or ""
        )
    )
    if nit:
        return nit
    document = only_digits(
        str(
            (request_context or {}).get("active_document")
            or profile.get("documento")
            or ""
        )
    )
    return document


def _normalized_context_sources(request_context: Optional[Dict[str, Any]]) -> List[Dict[str, str]]:
    if not isinstance(request_context, dict):
        return []
    items = request_context.get("last_sources")
    if not isinstance(items, list):
        return []
    normalized: List[Dict[str, str]] = []
    for item in items[:8]:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "title": str(item.get("title") or "").strip(),
                "source_url": str(item.get("source_url") or "").strip(),
                "document_type": str(item.get("document_type") or "").strip(),
                "intent": str(item.get("intent") or "").strip(),
            }
        )
    return normalized


def _expand_contextual_query(query: str, request_context: Optional[Dict[str, Any]], case_item: Optional[Dict[str, Any]]) -> str:
    if not isinstance(request_context, dict):
        return query
    reference = _context_case_reference(request_context, case_item)
    if not reference:
        return query
    query_norm = normalize_haystack(query)
    raw_query = str(query or "").strip()
    anchors = _extract_case_anchor_tokens(query)
    if anchors and case_item and not _query_matches_context_case(query, case_item):
        return query
    if case_item and not _should_prefer_context_case(query, request_context, case_item):
        return query

    explicit_intent = _detect_consulta_intent(query)
    last_intent = str(request_context.get("last_intent") or "").strip()
    last_document_intent = str(request_context.get("last_document_intent") or "").strip()
    context_sources = _normalized_context_sources(request_context)
    source_index = int(request_context.get("last_source_index") or 0) if str(request_context.get("last_source_index") or "").strip() else 0
    vague_next_terms = {"muestrame el siguiente", "muéstrame el siguiente", "el siguiente", "siguiente", "abre el siguiente"}
    vague_doc_terms = {"abralo", "ábralo", "abrelo", "ábrelo", "ese documento", "esa fuente", "ese archivo", "abreme ese documento", "ábreme ese documento"}

    def _expand_from_source(source: Dict[str, str]) -> Optional[str]:
        source_intent = str(source.get("intent") or "").strip()
        source_title = str(source.get("title") or "").strip()
        if source_title:
            return f"abre el archivo {source_title} de {reference}"
        if source_intent:
            source_template = {
                "rut": "rut de {reference}",
                "camara": "camara de comercio de {reference}",
                "cedula": "cedula de {reference}",
                "formulario": "formulario de {reference}",
                "926": "926 de {reference}",
            }.get(source_intent)
            if source_template:
                return source_template.format(reference=reference)
        return None

    if query_norm in vague_next_terms and context_sources:
        next_index = min(source_index + 1, len(context_sources) - 1)
        next_source = context_sources[next_index]
        expanded = _expand_from_source(next_source) or query
        logger.info("Consulta contextual expandida: '%s' -> '%s'", query, expanded)
        return expanded

    if query_norm in vague_doc_terms:
        if context_sources:
            current_source = context_sources[min(source_index, len(context_sources) - 1)]
            expanded = _expand_from_source(current_source) or query
            logger.info("Consulta contextual expandida: '%s' -> '%s'", query, expanded)
            return expanded
        if last_document_intent:
            explicit_intent = last_document_intent

    if query_norm in {"y ahora", "y ahora?", "ahora que sigue", "ahora que hago", "¿y ahora?"}:
        expanded = f"siguiente paso de {reference}"
        logger.info("Consulta contextual expandida: '%s' -> '%s'", query, expanded)
        return expanded

    intent = explicit_intent if explicit_intent != "general" else (last_intent or last_document_intent)
    if not intent:
        return query

    templates = {
        "rut": "rut de {reference}",
        "camara": "camara de comercio de {reference}",
        "cedula": "cedula de {reference}",
        "representante": "quien es el representante de {reference}",
        "926": "926 de {reference}",
        "reporte_prevalidacion": "reporte de prevalidacion de {reference}",
        "estado": "estado del expediente {reference}",
        "observaciones": "que observaciones tiene {reference}",
        "bloqueantes": "bloqueantes de {reference}",
        "siguiente_paso": "siguiente paso de {reference}",
        "nomina": "nomina de {reference}",
        "trabajadores": "cuantos trabajadores tiene {reference}",
        "sedes": "cuantas sedes tiene {reference}",
        "formulario": "formulario de {reference}",
        "documentos_recibidos": "que documentos recibio {reference}",
        "rechazo": "por que fue rechazado {reference}",
    }
    template = templates.get(intent)
    if not template:
        if query_norm.startswith("y ") and raw_query:
            expanded = f"{raw_query[2:].strip()} de {reference}"
            logger.info("Consulta contextual expandida: '%s' -> '%s'", query, expanded)
            return expanded
        return query
    expanded = template.format(reference=reference)
    logger.info("Consulta contextual expandida: '%s' -> '%s'", query, expanded)
    return expanded


def _detect_consulta_intent(query: str) -> str:
    query_norm = normalize_haystack(query)
    calibration = _load_search_calibration()
    calibrated_intents = calibration.get("intents") or {}
    learned_matches: list[tuple[int, str]] = []
    for intent_name, meta in calibrated_intents.items():
        for phrase in meta.get("trigger_phrases") or []:
            phrase_norm = normalize_haystack(phrase)
            if phrase_norm and phrase_norm in query_norm:
                learned_matches.append((len(phrase_norm), str(intent_name)))
    if learned_matches:
        learned_matches.sort(reverse=True)
        return learned_matches[0][1]

    if "reporte de prevalidacion" in query_norm or "reporte prevalidacion" in query_norm:
        return "reporte_prevalidacion"
    if "observaciones" in query_norm or "observacion" in query_norm:
        return "observaciones"
    if "formulario" in query_norm:
        return "formulario"
    if any(token in query_norm for token in ["que documentos recibio", "documentos recibidos", "adjuntos recibidos", "soportes recibidos"]):
        return "documentos_recibidos"
    if any(token in query_norm for token in ["cual es el nit", "nit de", "nit del expediente"]):
        return "nit"
    if "siguiente paso" in query_norm or "que sigue" in query_norm or "que hago ahora" in query_norm or "proximo paso" in query_norm:
        return "siguiente_paso"
    if "926" in query_norm or "bkcargue" in query_norm or "archivo 926" in query_norm:
        return "926"
    if "bloqueantes" in query_norm or "bloqueante" in query_norm:
        return "bloqueantes"
    if any(token in query_norm for token in ["por que fue rechaz", "porque fue rechaz", "motivo del rechazo", "duplicados"]):
        return "rechazo"
    if any(token in query_norm for token in ["prevalidacion", "pre validacion", "estado del expediente", "estado operativo", "aprobado", "rechazado", "observado", "radicacion", "radicacion", "radicar"]):
        return "estado"
    if any(token in query_norm for token in ["quien es el representante", "representante de", "representante legal", "quien firma", "firma"]):
        return "representante"
    if "nomina" in query_norm or "nomina total" in query_norm or "nómina" in query.lower():
        return "nomina"
    if "trabajadores" in query_norm or "cuantos trabajadores" in query_norm:
        return "trabajadores"
    if "sedes" in query_norm or "cuantas sedes" in query_norm or "centros de trabajo" in query_norm:
        return "sedes"
    if "cedula" in query_norm or "cedula de" in query_norm or "muestrame la cedula" in query_norm:
        return "cedula"
    if "rut" in query_norm or "muestrame el rut" in query_norm:
        return "rut"
    if "camara" in query_norm or "camara de comercio" in query_norm:
        return "camara"
    return "general"


def _best_case_representative_name(case_item: Dict[str, Any]) -> str:
    profile = case_item.get("profile") or {}
    matched = case_item.get("matched_documents") or []
    display_name = str(profile.get("nombre") or "").strip()
    if _looks_like_person_name(display_name):
        return display_name
    if profile.get("documento"):
        doc_candidates = search_document_registry(str(profile.get("documento")), limit=5)
        for item in doc_candidates:
            if item.get("case_id") != case_item.get("case_id"):
                continue
            candidate = str(item.get("person_name") or "").strip()
            if _looks_like_person_name(candidate):
                return candidate
    for item in matched:
        candidate = str(item.get("person_name") or "").strip()
        if _looks_like_person_name(candidate):
            return candidate
    candidate = _derive_full_representative_name(
        case_item.get("case_id") or "",
        profile.get("documento") or "",
        profile.get("nombre") or "",
    )
    if _looks_like_person_name(candidate):
        return candidate
    return f"documento {profile.get('documento')}" if profile.get("documento") else "n/d"


def _case_anchor_sources(case_id: str, company: str, topic: str = "expediente") -> List[Dict[str, Any]]:
    if not case_id:
        return []
    return [
        {
            "titulo": company or case_id,
            "contenido": "Expediente relacionado",
            "relevancia": 0.9,
            "topic": topic,
            "document_type": "case",
            "source_url": f"/api/cases/{case_id}",
        }
    ]


def _build_specialized_case_response(intent: str, case_item: Dict[str, Any]) -> Optional[ConsultaResponse]:
    case_id = case_item.get("case_id") or ""
    fresh_payload: Dict[str, Any] = {}
    if case_id:
        try:
            fresh_payload = load_case(case_id)
        except Exception:
            fresh_payload = {}
    analysis = (fresh_payload.get("analysis") or {}) if fresh_payload else {}
    profile = (((analysis.get("xlsx_profile") or {}).get("profile") or {}) if analysis else {}) or (case_item.get("profile") or {})
    precheck_info = _resolve_precheck_info(analysis, case_item)
    precheck = precheck_info["raw"]
    precheck_approved = precheck_info["approved"]
    executive_report = (analysis.get("reporte_ejecutivo") or {}) if analysis else (case_item.get("executive_report") or {})
    resumen = executive_report.get("resumen_ejecutivo", {}) or {}
    decision = (analysis.get("decision") or {}) if analysis else (case_item.get("decision") or {})
    reasons = list((resumen or {}).get("errores") or [])
    next_step = decision.get("next_step") or "Revisa el expediente y decide la siguiente acción operativa."
    base_confidence = min(float(case_item.get("score") or 0) / 20.0, 1.0)

    if intent == "representante":
        name = _best_case_representative_name(case_item)
        document = profile.get("documento") or "n/d"
        company = profile.get("empresa") or case_item.get("label") or "n/d"
        text = "\n".join(
            [
                "Respuesta ejecutiva:",
                "",
                f"El representante del expediente es {name}.",
                f"- Empresa: {company}",
                f"- Documento: {document}",
                "",
                "Siguiente paso:",
                "- Si quieres, pide la cédula, el formulario o el detalle completo del expediente.",
            ]
        )
        return ConsultaResponse(
            respuesta=text,
            fuentes=_case_anchor_sources(case_id, company, topic="representante"),
            confianza=base_confidence,
        )

    if intent == "reporte_prevalidacion":
        company = profile.get("empresa") or case_item.get("label") or "n/d"
        estado = "APROBADA" if precheck_approved else "NO APROBADA"
        lines = [
            "Respuesta ejecutiva:",
            "",
            f"Reporte de prevalidación para {company}:",
            f"- Estado: {estado}",
            f"- Trabajadores: {resumen.get('numero_trabajadores') or profile.get('numero_trabajadores') or 'n/d'}",
            f"- Sedes: {resumen.get('numero_sedes') or profile.get('numero_sedes') or 'n/d'}",
        ]
        hallazgos = list((resumen or {}).get("errores") or [])
        observaciones = list((resumen or {}).get("observaciones") or [])
        if hallazgos:
            lines.extend(["", "Hallazgos:"])
            for item in hallazgos[:6]:
                reason_lines = format_reason_lines(item)
                if not reason_lines:
                    continue
                lines.append(f"- {reason_lines[0]}")
                lines.extend(reason_lines[1:])
        if observaciones:
            lines.extend(["", "Observaciones:"])
            for item in observaciones[:6]:
                reason_lines = format_reason_lines(item)
                if not reason_lines:
                    continue
                lines.append(f"- {reason_lines[0]}")
                lines.extend(reason_lines[1:])
        lines.extend(["", "Siguiente paso:", f"- {next_step}"])
        return ConsultaResponse(
            respuesta="\n".join(lines),
            fuentes=_case_anchor_sources(case_id, company, topic="prevalidacion"),
            confianza=base_confidence,
        )

    if intent == "observaciones":
        company = profile.get("empresa") or case_item.get("label") or "n/d"
        observaciones = list((resumen or {}).get("observaciones") or [])
        lines = [
            "Respuesta ejecutiva:",
            "",
            f"Observaciones del expediente {company}:",
        ]
        if observaciones:
            for item in observaciones[:8]:
                reason_lines = format_reason_lines(item)
                if not reason_lines:
                    continue
                lines.append(f"- {reason_lines[0]}")
                lines.extend(reason_lines[1:])
        else:
            lines.append("- Sin observaciones relevantes registradas.")
        lines.extend(["", "Siguiente paso:", f"- {next_step}"])
        return ConsultaResponse(
            respuesta="\n".join(lines),
            fuentes=_case_anchor_sources(case_id, company, topic="observaciones"),
            confianza=base_confidence,
        )

    if intent == "nit":
        company = profile.get("empresa") or case_item.get("label") or "n/d"
        nit = profile.get("nit") or profile.get("documento_empleador") or "n/d"
        text = "\n".join(
            [
                "Respuesta ejecutiva:",
                "",
                f"El NIT del expediente {company} es {nit}.",
                "",
                "Siguiente paso:",
                "- Si quieres, pide también el RUT o el detalle completo del expediente.",
            ]
        )
        return ConsultaResponse(
            respuesta=text,
            fuentes=_case_anchor_sources(case_id, company, topic="nit"),
            confianza=base_confidence,
        )

    if intent == "documentos_recibidos":
        summary = list(case_item.get("received_summary") or [])
        company = profile.get("empresa") or case_item.get("label") or "n/d"
        if not summary:
            return None
        lines = [
            "Respuesta ejecutiva:",
            "",
            f"Documentos recibidos para {company}:",
        ]
        source_items: List[Dict[str, Any]] = []
        for item in summary[:12]:
            label = item.get("label") or item.get("document_type") or "Documento"
            files = _unique_filenames(list(item.get("files") or []))
            count = len(files) or int(item.get("count") or 0)
            lines.append(f"- {label}: {count} archivo(s)")
            for filename in files[:1]:
                source_items.append(
                    {
                        "titulo": filename,
                        "contenido": f"{label} · código {', '.join(str(code) for code in (item.get('legacy_codes') or [])) or 'n/d'}",
                        "relevancia": 0.92,
                        "topic": "expediente",
                        "document_type": item.get("document_type"),
                        "source_url": f"/api/cases/{case_id}/files/{filename}",
                    }
                )
        lines.extend(["", "Siguiente paso:", "- Indica cuál documento quieres abrir o revisar."])
        return ConsultaResponse(respuesta="\n".join(lines), fuentes=source_items[:8], confianza=base_confidence)

    if intent == "formulario":
        summary_item = next(
            (item for item in (case_item.get("received_summary") or []) if item.get("document_type") == "formulario_afiliacion"),
            None,
        )
        if summary_item and (summary_item.get("files") or []):
            files = _unique_filenames(list(summary_item.get("files") or []))
            text = "\n".join(
                [
                    "Respuesta ejecutiva:",
                    "",
                    f"Encontré {len(files)} formulario(s) de afiliación para este expediente.",
                    f"- Empresa: {profile.get('empresa') or case_item.get('label') or 'n/d'}",
                    *[f"- {filename}" for filename in files[:6]],
                    "",
                    "Siguiente paso:",
                    "- Abre el formulario que quieres revisar.",
                ]
            )
            return ConsultaResponse(
                respuesta=text,
                fuentes=[
                    {
                        "titulo": filename,
                        "contenido": f"{summary_item.get('label') or 'Afiliación'} · código {', '.join(str(code) for code in (summary_item.get('legacy_codes') or [])) or '0'}",
                        "relevancia": 0.95,
                        "topic": "documento",
                        "document_type": "formulario_afiliacion",
                        "source_url": f"/api/cases/{case_id}/files/{filename}",
                    }
                    for filename in files[:6]
                ],
                confianza=base_confidence,
            )

    if intent == "estado":
        company = profile.get("empresa") or case_item.get("label") or "n/d"
        status_text = "APROBADA" if precheck_approved else "NO APROBADA"
        summary = decision.get("summary") or ("Expediente listo para radicación." if precheck_approved else "Expediente con bloqueos o inconsistencias.")
        lines = [
            "Respuesta ejecutiva:",
            "",
            f"Estado del expediente: {summary}",
            f"- Empresa: {company}",
            f"- Flujo: {str((precheck_info.get('workflow') or {}).get('status') or case_item.get('status') or 'n/d')}",
            f"- Prevalidación: {status_text}",
            f"- Trabajadores: {resumen.get('numero_trabajadores') or profile.get('numero_trabajadores') or 'n/d'}",
            f"- Sedes: {resumen.get('numero_sedes') or profile.get('numero_sedes') or 'n/d'}",
        ]
        if not precheck_approved:
            if reasons:
                lines.extend(["", "Bloqueantes:"])
                for item in reasons[:5]:
                    reason_lines = format_reason_lines(item)
                    if not reason_lines:
                        continue
                    lines.append(f"- {reason_lines[0]}")
                    lines.extend(reason_lines[1:])
        lines.extend(["", "Siguiente paso:", f"- {next_step}"])
        return ConsultaResponse(
            respuesta="\n".join(lines),
            fuentes=_case_anchor_sources(case_id, company, topic="estado"),
            confianza=base_confidence,
        )

    if intent == "rechazo" and not precheck_approved:
        lines = ["Respuesta ejecutiva:", ""]
        if reasons:
            lines.append("Motivo del rechazo:")
            for item in reasons[:8]:
                reason_lines = format_reason_lines(item)
                if not reason_lines:
                    continue
                lines.append(f"- {reason_lines[0]}")
                lines.extend(reason_lines[1:])
        else:
            lines.append("La prevalidación no fue aprobada, pero no encontré un motivo consolidado.")
        lines.extend(["", "Siguiente paso:", "- Corrige los hallazgos reportados y vuelve a ejecutar la prevalidación."])
        return ConsultaResponse(
            respuesta="\n".join(lines),
            fuentes=_case_anchor_sources(case_id, profile.get("empresa") or case_item.get("label") or "n/d", topic="rechazo"),
            confianza=base_confidence,
        )

    if intent == "bloqueantes":
        company = profile.get("empresa") or case_item.get("label") or "n/d"
        lines = [
            "Respuesta ejecutiva:",
            "",
            f"Bloqueantes del expediente {company}:",
        ]
        if reasons:
            for item in reasons[:8]:
                reason_lines = format_reason_lines(item)
                if not reason_lines:
                    continue
                lines.append(f"- {reason_lines[0]}")
                lines.extend(reason_lines[1:])
        else:
            lines.append("- Sin bloqueantes inmediatos detectados.")
        lines.extend(["", "Siguiente paso:", f"- {next_step}"])
        return ConsultaResponse(
            respuesta="\n".join(lines),
            fuentes=_case_anchor_sources(case_id, company, topic="bloqueantes"),
            confianza=base_confidence,
        )

    if intent == "siguiente_paso":
        company = profile.get("empresa") or case_item.get("label") or "n/d"
        summary = decision.get("summary") or ("Expediente listo para radicación." if precheck_approved else "Expediente con bloqueos o inconsistencias.")
        text = "\n".join(
            [
                "Respuesta ejecutiva:",
                "",
                f"Siguiente paso para {company}:",
                f"- {next_step}",
                f"- Estado operativo: {summary}",
                f"- Prevalidación: {'APROBADA' if precheck_approved else 'NO APROBADA'}",
            ]
        )
        return ConsultaResponse(
            respuesta=text,
            fuentes=_case_anchor_sources(case_id, company, topic="siguiente_paso"),
            confianza=base_confidence,
        )

    if intent == "926":
        output_926 = {}
        if case_id:
            try:
                payload = load_case(case_id)
                output_926 = ((payload.get("analysis") or {}).get("output_926") or {})
            except Exception:
                output_926 = {}
        if not output_926:
            output_926 = (case_item.get("workflow_run") or {}).get("output_926") or case_item.get("output_926") or {}
        if not output_926:
            output_926 = (case_item.get("analysis") or {}).get("output_926") or {}
        legacy = output_926.get("legacy") or {}
        draft = output_926.get("draft") or {}
        company = profile.get("empresa") or case_item.get("label") or "n/d"
        if legacy.get("ok") and legacy.get("filename"):
            text = "\n".join(
                [
                    "Respuesta ejecutiva:",
                    "",
                    f"El 926 del expediente {company} está disponible.",
                    f"- Archivo: {legacy.get('filename')}",
                    "- Estado: generado por la integración automática",
                    "",
                    "Siguiente paso:",
                    "- Si quieres, abre o descarga el archivo 926 del expediente.",
                ]
            )
            return ConsultaResponse(
                respuesta=text,
                fuentes=[
                    {
                        "titulo": str(legacy.get("filename") or "archivo_926.txt"),
                        "contenido": "Archivo 926 generado",
                        "relevancia": 0.98,
                        "topic": "926",
                        "document_type": "926",
                        "source_url": f"/api/cases/{case_id}/926",
                    }
                ],
                confianza=base_confidence,
            )
        if draft.get("filename"):
            text = "\n".join(
                [
                    "Respuesta ejecutiva:",
                    "",
                    f"El expediente {company} tiene un 926 borrador disponible.",
                    f"- Archivo: {draft.get('filename')}",
                    f"- Nota: {draft.get('note') or 'Borrador operativo disponible.'}",
                    "",
                    "Siguiente paso:",
                    "- Revisa el borrador o completa el flujo para obtener el 926 final.",
                ]
            )
            return ConsultaResponse(
                respuesta=text,
                fuentes=[
                    {
                        "titulo": str(draft.get("filename") or "archivo_926.txt"),
                        "contenido": "Archivo 926 borrador",
                        "relevancia": 0.9,
                        "topic": "926",
                        "document_type": "926",
                        "source_url": f"/api/cases/{case_id}/926",
                    }
                ],
                confianza=base_confidence,
            )
        text = "\n".join(
            [
                "Respuesta ejecutiva:",
                "",
                f"El expediente {company} no tiene 926 disponible todavía.",
                f"- Motivo: {output_926.get('reason') or 'Aún no está listo.'}",
                "",
                "Siguiente paso:",
                f"- {next_step}",
            ]
        )
        return ConsultaResponse(
            respuesta=text,
            fuentes=_case_anchor_sources(case_id, company, topic="926"),
            confianza=base_confidence,
        )

    if intent == "nomina":
        nomina = resumen.get("nomina_total")
        company = profile.get("empresa") or case_item.get("label") or "n/d"
        text = "\n".join(
            [
                "Respuesta ejecutiva:",
                "",
                f"La nómina total del expediente es {nomina if nomina is not None else 'n/d'}.",
                f"- Empresa: {company}",
                f"- Trabajadores: {resumen.get('numero_trabajadores') or profile.get('numero_trabajadores') or 'n/d'}",
                f"- Sedes: {resumen.get('numero_sedes') or profile.get('numero_sedes') or 'n/d'}",
                "",
                "Siguiente paso:",
                "- Si quieres, pide también el detalle de trabajadores o el estado de prevalidación.",
            ]
        )
        return ConsultaResponse(
            respuesta=text,
            fuentes=_case_anchor_sources(case_id, company, topic="trabajadores"),
            confianza=base_confidence,
        )

    if intent == "trabajadores":
        workers = resumen.get("numero_trabajadores") or profile.get("numero_trabajadores") or "n/d"
        company = profile.get("empresa") or case_item.get("label") or "n/d"
        text = "\n".join(
            [
                "Respuesta ejecutiva:",
                "",
                f"El expediente tiene {workers} trabajador(es).",
                f"- Empresa: {company}",
                f"- Nómina total: {resumen.get('nomina_total') if resumen.get('nomina_total') is not None else 'n/d'}",
                f"- Sedes: {resumen.get('numero_sedes') or profile.get('numero_sedes') or 'n/d'}",
                "",
                "Siguiente paso:",
                "- Si quieres, pide también el estado del expediente o la nómina total.",
            ]
        )
        return ConsultaResponse(
            respuesta=text,
            fuentes=_case_anchor_sources(case_id, company, topic="sedes"),
            confianza=base_confidence,
        )

    if intent == "sedes":
        sedes = resumen.get("numero_sedes") or profile.get("numero_sedes") or "n/d"
        company = profile.get("empresa") or case_item.get("label") or "n/d"
        text = "\n".join(
            [
                "Respuesta ejecutiva:",
                "",
                f"El expediente registra {sedes} sede(s).",
                f"- Empresa: {company}",
                f"- Trabajadores: {resumen.get('numero_trabajadores') or profile.get('numero_trabajadores') or 'n/d'}",
                "",
                "Siguiente paso:",
                "- Si quieres, pide también el anexo de sedes o el estado de prevalidación.",
            ]
        )
        return ConsultaResponse(
            respuesta=text,
            fuentes=[],
            confianza=base_confidence,
        )

    if intent in {"cedula", "rut", "camara"}:
        expected_type = {
            "cedula": "cedula",
            "rut": "rut",
            "camara": "camara_comercio",
        }[intent]
        summary_item = next(
            (item for item in (case_item.get("received_summary") or []) if item.get("document_type") == expected_type),
            None,
        )
        if summary_item and (summary_item.get("files") or []):
            files = _unique_filenames(list(summary_item.get("files") or []))
            source_items = [
                {
                    "titulo": filename,
                    "contenido": f"{summary_item.get('label') or expected_type} · código {', '.join(str(code) for code in (summary_item.get('legacy_codes') or [])) or 'n/d'}",
                    "relevancia": 0.95,
                    "topic": "documento",
                    "document_type": expected_type,
                    "source_url": f"/api/cases/{case_id}/files/{filename}",
                }
                for filename in files[:6]
            ]
            noun = {"cedula": "cédula", "rut": "RUT", "camara": "cámara de comercio"}[intent]
            text = "\n".join(
                [
                    "Respuesta ejecutiva:",
                    "",
                    f"Encontré {len(files)} archivo(s) de {noun} para este expediente.",
                    f"- Empresa: {profile.get('empresa') or case_item.get('label') or 'n/d'}",
                    *[f"- {filename}" for filename in files[:6]],
                    "",
                    "Siguiente paso:",
                    f"- Abre el archivo de {noun} que quieres revisar.",
                ]
            )
            return ConsultaResponse(
                respuesta=text,
                fuentes=source_items,
                confianza=base_confidence,
            )
    return None



# ── Admin Tables API ─────────────────────────────────────────
@app.get("/api/admin/tables/eps")
async def get_eps_catalog():
    from pathlib import Path
    import json
    p = Path("/data/evals/eps_catalog.json")
    return {"items": json.loads(p.read_text()) if p.exists() else []}

@app.post("/api/admin/tables/eps")
async def save_eps_catalog(payload: dict):
    from pathlib import Path
    import json
    p = Path("/data/evals/eps_catalog.json")
    p.write_text(json.dumps(payload.get("items", []), ensure_ascii=False, indent=2))
    return {"ok": True}

@app.get("/api/admin/tables/afp")
async def get_afp_catalog():
    from pathlib import Path
    import json
    p = Path("/data/evals/afp_catalog.json")
    return {"items": json.loads(p.read_text()) if p.exists() else []}

@app.post("/api/admin/tables/afp")
async def save_afp_catalog(payload: dict):
    from pathlib import Path
    import json
    p = Path("/data/evals/afp_catalog.json")
    p.write_text(json.dumps(payload.get("items", []), ensure_ascii=False, indent=2))
    return {"ok": True}

@app.get("/api/admin/tables/asesores")
async def get_asesores():
    from pathlib import Path
    import json
    p = Path("/data/evals/asesores_colmena.json")
    d = json.loads(p.read_text()) if p.exists() else {}
    return {"comerciales": d.get("comerciales", []), "intermediarios": d.get("intermediarios", [])}

@app.post("/api/admin/tables/asesores")
async def save_asesores(payload: dict):
    from pathlib import Path
    import json
    p = Path("/data/evals/asesores_colmena.json")
    comerciales = payload.get("comerciales", [])
    intermediarios = payload.get("intermediarios", [])
    d = {"comerciales": comerciales, "intermediarios": intermediarios, "total": len(comerciales) + len(intermediarios)}
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2))
    return {"ok": True}

@app.get("/api/admin/tables/smmlv")
async def get_smmlv():
    from pathlib import Path
    import json
    p = Path("/data/evals/smmlv_table.json")
    return json.loads(p.read_text()) if p.exists() else {}

@app.post("/api/admin/tables/smmlv")
async def save_smmlv(payload: dict):
    from pathlib import Path
    import json
    p = Path("/data/evals/smmlv_table.json")
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    return {"ok": True}

@app.get("/api/admin/tables/recipients")
async def get_recipients():
    from pathlib import Path
    import json
    p = Path(settings.notification_recipients_path)
    return json.loads(p.read_text()) if p.exists() else {}

@app.post("/api/admin/tables/recipients")
async def save_recipients(payload: dict):
    from pathlib import Path
    import json
    p = Path(settings.notification_recipients_path)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    return {"ok": True}

@app.get("/")
async def root():
    return {"message": f"{settings.app_name} - Control Plane"}



def build_runtime_resources() -> dict:
    """Lee metricas del contenedor desde cgroups y procfs."""
    import os, time
    result = {}
    try:
        mem_current = int(open("/sys/fs/cgroup/memory.current").read().strip())
        mem_max_raw = open("/sys/fs/cgroup/memory.max").read().strip()
        mem_max = int(mem_max_raw) if mem_max_raw != "max" else 0
        result["mem_used_mb"] = round(mem_current / 1024 / 1024, 1)
        result["mem_max_mb"] = round(mem_max / 1024 / 1024, 1) if mem_max else 0
        result["mem_pct"] = round(mem_current / mem_max * 100, 1) if mem_max else 0
    except Exception:
        result["mem_used_mb"] = 0
        result["mem_max_mb"] = 0
        result["mem_pct"] = 0
    try:
        cpu_lines = open("/sys/fs/cgroup/cpu.stat").read().strip().splitlines()
        cpu_data = {}
        for line in cpu_lines:
            parts = line.split()
            if len(parts) == 2:
                cpu_data[parts[0]] = int(parts[1])
        result["cpu_usage_usec"] = cpu_data.get("usage_usec", 0)
    except Exception:
        result["cpu_usage_usec"] = 0
    try:
        rss = 0
        for line in open("/proc/self/status").readlines():
            if line.startswith("VmRSS:"):
                rss = int(line.split()[1])
                break
        result["process_rss_mb"] = round(rss / 1024, 1)
    except Exception:
        result["process_rss_mb"] = 0
    result["timestamp"] = time.time()
    return result

@app.get("/health")
async def health():
    return await get_system_health()


@app.get("/api/system/status")
async def system_status():
    return await get_system_status()


@app.get("/api/system/feed-status")
async def feed_status():
    return get_feed_summary()


@app.get("/api/system/eval-status")
async def eval_status():
    return get_eval_summary()


@app.post("/api/system/reindex", response_model=ReindexResponse)
async def system_reindex():
    try:
        result = await reindex_knowledge()
        return ReindexResponse(**result)
    except Exception as exc:
        logger.error("Error reindexando corpus: %s", exc)
        raise HTTPException(status_code=500, detail=f"Error reindexando corpus: {exc}") from exc


@app.post("/api/afiliacion/consultar", response_model=ConsultaResponse)
async def consultar_afiliacion(request: ConsultaRequest):
    logger.info("Consulta recibida: %s", request.consulta)

    try:
        request_context = request.contexto or {}
        raw_query = request.consulta
        if _is_broad_location_query(raw_query):
            return ConsultaResponse(
                respuesta="\n".join(
                    [
                        "Respuesta ejecutiva:",
                        "",
                        "La consulta es demasiado amplia para devolver un documento o expediente único.",
                        "",
                        "Lo correcto es buscar con más precisión, por ejemplo:",
                        "- nombre de la empresa",
                        "- NIT",
                        "- representante legal",
                        "- tipo de documento + empresa",
                        "",
                        "Ejemplos:",
                        "- cámara puerto gaitan",
                        "- estado hvr",
                        "- nit monca",
                        "- cédula representante protegemos",
                    ]
                ),
                fuentes=[],
                confianza=0.25,
            )
        context_case = _resolve_context_case(request_context)
        effective_query = _expand_contextual_query(raw_query, request_context, context_case)
        intent = _detect_consulta_intent(effective_query)
        consulta_lower = effective_query.lower()
        document_first = any(token in consulta_lower for token in ["cedula", "cédula", "rut", "camara", "cámara", "pdf", "documento", "soporte", "formulario"])
        case_results = search_cases(effective_query, limit=10)
        if _should_prefer_context_case(effective_query, request_context, context_case):
            if context_case:
                case_results = [context_case] + [item for item in case_results if str(item.get("case_id") or "") != str(context_case.get("case_id") or "")]
        anchor_tokens = _extract_case_anchor_tokens(effective_query)
        if anchor_tokens:
            merged_by_case: Dict[str, Dict[str, Any]] = {}
            extra_results: List[Dict[str, Any]] = []
            for token in anchor_tokens[:3]:
                extra_results.extend(search_cases(token, limit=10))
            for item in case_results + extra_results:
                case_id = str(item.get("case_id") or "")
                if not case_id:
                    continue
                current = merged_by_case.get(case_id)
                if current is None or int(item.get("score") or 0) > int(current.get("score") or 0):
                    merged_by_case[case_id] = item
            case_results = list(merged_by_case.values())
        if context_case and _should_prefer_context_case(effective_query, request_context, context_case):
            case_results = [context_case] + [item for item in case_results if str(item.get("case_id") or "") != str(context_case.get("case_id") or "")]
        case_results = _select_best_case_result(effective_query, case_results)
        if anchor_tokens and case_results and not _case_has_strong_anchor(effective_query, case_results[0]) and not _query_matches_context_case(effective_query, context_case):
            case_results = []
        case_response = build_case_consulta_response(effective_query, case_results)
        if case_results and case_response is not None and not _is_case_disambiguation_response(case_response):
            specialized_case = _build_specialized_case_response(intent, case_results[0])
            if specialized_case is not None:
                return specialized_case
        if case_results and _case_has_strong_anchor(effective_query, case_results[0]):
            specialized_case = _build_specialized_case_response(intent, case_results[0])
            if specialized_case is not None:
                return specialized_case
        if not document_first and case_response is not None and not _is_case_disambiguation_response(case_response):
            return case_response
        document_results = search_document_registry(effective_query, limit=8)
        focused_case_id = None
        if case_results:
            focused_case_id = case_results[0].get("case_id")
        if focused_case_id:
            focused_documents = [item for item in document_results if item.get("case_id") == focused_case_id]
            if focused_documents:
                document_results = focused_documents
        document_response = build_document_consulta_response(effective_query, document_results)
        if anchor_tokens and not case_results and document_results:
            top_document = document_results[0]
            document_anchor_haystack = " ".join(
                [
                    normalize_haystack(str(top_document.get("company") or "")),
                    normalize_haystack(str(top_document.get("person_name") or "")),
                    normalize_haystack(str(top_document.get("label") or "")),
                    normalize_haystack(str(top_document.get("filename") or "")),
                ]
            )
            if not any(token in document_anchor_haystack for token in anchor_tokens):
                document_results = []
                document_response = None
        if document_first and document_response is not None:
            return document_response
        if case_response is not None:
            return case_response
        if document_response is not None:
            return document_response
        if anchor_tokens:
            return ConsultaResponse(
                respuesta="\n".join(
                    [
                        "Respuesta ejecutiva:",
                        "",
                        "No encontré un contrato o documento que coincida con esa empresa en la base actual.",
                        "",
                        "Siguiente paso:",
                        "- Verifica el nombre de la empresa o el NIT.",
                        "- Si el contrato existía antes, puede que ya no esté en la base actual.",
                    ]
                ),
                fuentes=[],
                confianza=0.2,
            )
        if _is_generic_operational_query(request.consulta):
            return ConsultaResponse(
                respuesta="\n".join(
                    [
                        "Respuesta ejecutiva:",
                        "",
                        "La consulta es muy general para abrir un expediente o documento específico.",
                        "",
                        "Prueba con una búsqueda más concreta:",
                        "- nombre de la empresa",
                        "- apellido o documento del representante",
                        "- tipo de documento y empresa",
                        "",
                        "Ejemplos:",
                        "- prevalidación protegemos",
                        "- radicado monca",
                        "- cédula representante londono",
                        "- cámara puerto gaitan",
                    ]
                ),
                fuentes=[],
                confianza=0.2,
            )
        selected_topics = None
        if request.contexto:
            selected_topics = request.contexto.get("topics")
            if not selected_topics and request.contexto.get("topic"):
                selected_topics = [request.contexto.get("topic")]
        sources = await search_knowledge(request.consulta, selected_topics=selected_topics)
        answer = await generate_grounded_answer(request.consulta, sources)
        confidence = round(min(max((source.get("relevancia", 0.0) for source in sources), default=0.0), 1.0), 2)
        return ConsultaResponse(
            respuesta=answer,
            fuentes=sources,
            confianza=confidence,
        )
    except Exception as exc:
        logger.error("Error procesando consulta: %s", exc)
        raise HTTPException(status_code=500, detail=f"Error interno: {exc}") from exc


@app.post("/api/afiliacion/retrieve", response_model=RetrievalResponse)
async def retrieve_afiliacion(request: ConsultaRequest):
    try:
        selected_topics = None
        if request.contexto:
            selected_topics = request.contexto.get("topics")
            if not selected_topics and request.contexto.get("topic"):
                selected_topics = [request.contexto.get("topic")]
        sources = await search_knowledge(request.consulta, selected_topics=selected_topics)
        confidence = round(min(max((source.get("relevancia", 0.0) for source in sources), default=0.0), 1.0), 2)
        return RetrievalResponse(fuentes=sources, confianza=confidence)
    except Exception as exc:
        logger.error("Error recuperando fuentes: %s", exc)
        raise HTTPException(status_code=500, detail=f"Error interno: {exc}") from exc


@app.post("/api/afiliacion/operar", response_model=WorkflowResponse)
async def operate_afiliacion(request: ConsultaRequest):
    try:
        selected_topics = None
        if request.contexto:
            selected_topics = request.contexto.get("topics")
            if not selected_topics and request.contexto.get("topic"):
                selected_topics = [request.contexto.get("topic")]
        sources = await search_knowledge(request.consulta, selected_topics=selected_topics)
        decision = infer_operational_decision(request.consulta, sources)
        return WorkflowResponse(**decision)
    except Exception as exc:
        logger.error("Error generando decision operativa: %s", exc)
        raise HTTPException(status_code=500, detail=f"Error interno: {exc}") from exc


@app.get("/api/cases", response_model=CaseListResponse)
async def cases_list():
    return CaseListResponse(cases=list_cases())


@app.get("/api/cases/production-summary")
async def cases_production_summary():
    deduped: Dict[str, Dict[str, Any]] = {}
    for payload in list_cases():
        analysis = payload.get("analysis") or {}
        workflow = analysis.get("workflow_run") or {}
        workflow_status = str(workflow.get("status") or "").strip().lower()
        payload_status = str(payload.get("status") or "").strip().lower()
        terminal_statuses = {"completed", "stopped_prevalidacion"}
        if workflow_status not in terminal_statuses and payload_status not in terminal_statuses:
            continue
        final_report = workflow.get("executive_report_final") or {}
        precheck_report = workflow.get("executive_report_precheck") or analysis.get("reporte_ejecutivo") or {}
        report = final_report or precheck_report
        resumen = report.get("resumen_ejecutivo") or {}
        profile = ((analysis.get("xlsx_profile") or {}).get("profile") or {})
        output_926 = workflow.get("output_926") or analysis.get("output_926") or {}
        legacy = output_926.get("legacy") or {}
        draft = output_926.get("draft") or {}
        status = str(workflow.get("status") or payload.get("status") or "n/d")
        item = {
            "id": payload.get("id"),
            "label": payload.get("label"),
            "updated_at": payload.get("updated_at"),
            "status": status,
            "empresa": resumen.get("empresa") or profile.get("empresa") or payload.get("label") or payload.get("id"),
            "nit": resumen.get("nit") or profile.get("nit") or "",
            "fecha": resumen.get("fecha_proceso_human") or report.get("fecha_proceso_human") or payload.get("updated_at"),
            "final_status": resumen.get("estado") or report.get("estado_final") or status,
            "summary": (analysis.get("decision") or {}).get("summary") or "",
            "filename": legacy.get("filename") or draft.get("filename") or "archivo_core.txt",
            "has_926": bool(legacy.get("ok") or legacy.get("available") or draft.get("content")),
        }
        nit_key = str(item.get("nit") or "").strip()
        empresa_key = str(item.get("empresa") or "").strip()
        if not nit_key and (not empresa_key or empresa_key.lower().startswith("case-")):
            continue
        entity_key = (str(item.get("nit") or "").strip() or str(item.get("empresa") or "").strip()).upper()
        if not entity_key:
            entity_key = str(item.get("id") or "")
        current = deduped.get(entity_key)
        if not current or str(item.get("updated_at") or "") > str(current.get("updated_at") or ""):
            deduped[entity_key] = item
    items = sorted(deduped.values(), key=lambda entry: str(entry.get("updated_at") or ""), reverse=True)
    return {"cases": items}


@app.get("/api/cases/precheck-failed")
async def cases_precheck_failed():
    deduped: Dict[str, Dict[str, Any]] = {}
    for payload in list_cases():
        analysis = payload.get("analysis") or {}
        decision = analysis.get("decision") or {}
        workflow = analysis.get("workflow_run") or {}
        if str(workflow.get("status") or "") != "stopped_prevalidacion" and str(decision.get("recommended_status") or "") == "aprobable":
            continue
        if str(workflow.get("status") or "") != "stopped_prevalidacion" and str(decision.get("recommended_status") or "") not in {"observado", "rechazado", "rechazado_prevalidacion"}:
            continue
        profile = ((analysis.get("xlsx_profile") or {}).get("profile") or {})
        report = workflow.get("executive_report_precheck") or analysis.get("reporte_ejecutivo") or {}
        resumen = report.get("resumen_ejecutivo") or {}
        item = {
            "id": payload.get("id"),
            "label": payload.get("label"),
            "empresa": resumen.get("empresa") or profile.get("empresa") or payload.get("label"),
            "company_name": resumen.get("empresa") or profile.get("empresa") or payload.get("label"),
            "nit": resumen.get("nit") or profile.get("nit") or "",
            "fecha": resumen.get("fecha_proceso_human") or report.get("fecha_proceso_human") or payload.get("updated_at"),
            "updated_at": payload.get("updated_at"),
            "estado": resumen.get("estado") or report.get("estado_final") or "RECHAZADO",
            "status": str(workflow.get("status") or decision.get("recommended_status") or "rechazado"),
            "summary": (decision.get("summary") or "").strip(),
            "next_step": decision.get("next_step") or "",
            "blockers": decision.get("blockers") or [],
            "report": report,
        }
        entity_key = (str(item.get("nit") or "").strip() or str(item.get("empresa") or "").strip()).upper()
        if not entity_key:
            entity_key = str(item.get("id") or "")
        current = deduped.get(entity_key)
        if not current or str(item.get("updated_at") or "") > str(current.get("updated_at") or ""):
            deduped[entity_key] = item
    items = sorted(deduped.values(), key=lambda entry: str(entry.get("updated_at") or ""), reverse=True)
    return {"cases": items}


@app.get("/api/workflow-queue")
async def workflow_queue_status():
    return _get_workflow_queue_status()


@app.get("/api/cases/search")
async def cases_search(q: str = Query(..., min_length=2), limit: int = Query(10, ge=1, le=30)):
    return {"query": q, "results": search_cases(q, limit=limit)}


@app.post("/api/926/compare")
async def compare_926(request: Compare926Request):
    left = _resolve_926_content(request.left_case_id, request.left_content)
    right = _resolve_926_content(request.right_case_id, request.right_content)
    if not left or not right:
        raise HTTPException(status_code=400, detail="Debes indicar ambos archivos 926 para comparar.")
    left_lines = left.splitlines()
    right_lines = right.splitlines()
    max_len = max(len(left_lines), len(right_lines))
    diffs: List[Dict[str, str]] = []
    for idx in range(max_len):
        left_line = left_lines[idx] if idx < len(left_lines) else ""
        right_line = right_lines[idx] if idx < len(right_lines) else ""
        if left_line == right_line:
            continue
        diffs.append(
            {
                "line": str(idx + 1),
                "left": left_line,
                "right": right_line,
            }
        )
    similarity = round(SequenceMatcher(None, left, right).ratio(), 4)
    left_normalized = _normalize_926_operational_content(left)
    right_normalized = _normalize_926_operational_content(right)
    business_match = left_normalized == right_normalized
    business_similarity = round(SequenceMatcher(None, left_normalized, right_normalized).ratio(), 4)
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "left_case_id": request.left_case_id or "",
        "right_case_id": request.right_case_id or "",
        **_resolve_case_identity(request.left_case_id),
        "left_lines": len(left_lines),
        "right_lines": len(right_lines),
        "different_lines": len(diffs),
        "similarity": similarity,
        "match": business_match,
        "exact_match_raw": len(diffs) == 0,
        "business_similarity": business_similarity,
        "operational_only": business_match and len(diffs) > 0,
        "diffs": diffs[:200],
    }
    _append_compare_926_history(result)
    return result


@app.post("/api/cases/rebuild-document-registry")
async def cases_rebuild_document_registry():
    return rebuild_document_registry()


@app.get("/api/documents/search")
async def documents_search(q: str = Query(..., min_length=2), limit: int = Query(12, ge=1, le=50)):
    return {"query": q, "results": search_document_registry(q, limit=limit)}


@app.post("/api/cases", response_model=CaseCreateResponse)
async def create_case(
    label: str = Form(default=""),
    files: Optional[List[UploadFile]] = File(default=None),
    xlsx_file: Optional[UploadFile] = File(default=None),
    attachments: Optional[List[UploadFile]] = File(default=None),
):
    uploads: List[tuple[str, bytes]] = []
    rejected_files: List[Dict[str, str]] = []
    for item in files or []:
        uploads.append((item.filename or "archivo.bin", await item.read()))
    if xlsx_file is not None:
        uploads.append((xlsx_file.filename or "case.xlsx", await xlsx_file.read()))
    for item in attachments or []:
        uploads.append((item.filename or "adjunto.bin", await item.read()))
    if not uploads:
        raise HTTPException(status_code=400, detail="Debes adjuntar al menos un XLSX o un soporte.")

    accepted_uploads: List[tuple[str, bytes]] = []
    for filename, content in uploads:
        lower_name = str(filename or "").lower()
        suffix = Path(lower_name).suffix
        if not str(filename or "").strip():
            rejected_files.append({"filename": "archivo_sin_nombre", "reason": "El archivo no tiene nombre y no se pudo identificar."})
            continue
        if not content:
            rejected_files.append({"filename": filename, "reason": "El archivo está vacío y no se pudo cargar."})
            continue
        if suffix not in SUPPORTED_CASE_UPLOAD_EXTENSIONS:
            rejected_files.append(
                {
                    "filename": filename,
                    "reason": "El archivo no tiene una extensión permitida. Usa XLSX, PDF o un formato de imagen soportado.",
                }
            )
            continue
        accepted_uploads.append((filename, content))

    if not accepted_uploads:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "No se pudo cargar ningún archivo válido del paquete.",
                "rejected_files": rejected_files,
            },
        )

    xlsx_count = sum(1 for filename, _ in accepted_uploads if str(filename).lower().endswith((".xlsx", ".xlsm", ".xls")))
    pdf_count = sum(1 for filename, _ in accepted_uploads if str(filename).lower().endswith(".pdf"))
    if len(accepted_uploads) < 2 or xlsx_count < 1 or pdf_count < 1:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Debes cargar mínimo 2 archivos válidos: un Excel en formato XLSX y al menos un PDF.",
                "accepted_files": [filename for filename, _ in accepted_uploads],
                "rejected_files": rejected_files,
            },
        )
    case_payload = store_case_files(label=label, uploads=accepted_uploads)
    case_payload["upload_summary"] = {
        "accepted_files": [filename for filename, _ in accepted_uploads],
        "rejected_files": rejected_files,
    }
    return CaseCreateResponse(**case_payload)


@app.get("/api/cases/{case_id}", response_model=CaseCreateResponse)
async def case_detail(case_id: str):
    try:
        payload = load_case(case_id)
        return CaseCreateResponse(**payload)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Caso no encontrado.") from exc


@app.delete("/api/cases/{case_id}")
async def case_delete(case_id: str):
    """Elimina un caso y todos sus archivos adjuntos."""
    import shutil
    try:
        payload = load_case(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Caso no encontrado.")
    case_dir = Path(settings.cases_dir) / case_id
    if case_dir.exists():
        shutil.rmtree(str(case_dir))
        return {"ok": True, "deleted": case_id, "message": f"Caso {case_id} eliminado."}
    raise HTTPException(status_code=404, detail="Directorio del caso no encontrado.")


@app.post("/api/cases/{case_id}/analyze", response_model=CaseCreateResponse)
async def case_analyze(case_id: str):
    try:
        payload = analyze_case(case_id)
        return CaseCreateResponse(**payload)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Caso no encontrado.") from exc
    except Exception as exc:
        logger.error("Error analizando caso %s: %s", case_id, exc)
        raise HTTPException(status_code=500, detail=f"No pude analizar el caso: {exc}") from exc


@app.post("/api/cases/{case_id}/run-workflow", response_model=CaseCreateResponse)
async def case_run_workflow(case_id: str):
    try:
        with WORKFLOW_QUEUE_LOCK:
            state = _repair_stale_workflow_queue_state()
            active = state.get("active") or {}
            active_case_id = str(active.get("case_id") or "")
            if active_case_id == case_id:
                payload = load_case(case_id)
                queue_status = {
                    "state": "processing",
                    "position": 0,
                    "active": active,
                    "queue_length": len(state.get("queue") or []),
                }
                payload = _mark_case_workflow_processing(case_id, queue_status, status="processing")
                _spawn_workflow_worker(case_id)
                return CaseCreateResponse(**payload)
            if active_case_id and active_case_id != case_id:
                payload = load_case(case_id)
                already_queued = next((item for item in state.get("queue") or [] if str(item.get("case_id") or "") == case_id), None)
                if not already_queued:
                    meta = _queue_case_meta(payload)
                    state.setdefault("queue", []).append(meta)
                    _save_workflow_queue_state(state)
                    position = len(state.get("queue") or [])
                else:
                    position = next((index + 1 for index, item in enumerate(state.get("queue") or []) if str(item.get("case_id") or "") == case_id), 1)
                payload = _set_case_queue_status(
                    case_id,
                    {
                        "state": "queued",
                        "position": position,
                        "active": active,
                        "queue_length": len(state.get("queue") or []),
                    },
                    status="queued",
                )
                return CaseCreateResponse(**payload)
            payload = load_case(case_id)
            if state.get("queue"):
                state["queue"] = [
                    item
                    for item in (state.get("queue") or [])
                    if str(item.get("case_id") or "") != case_id
                ]
            meta = _queue_case_meta(payload)
            state["active"] = {
                **meta,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "status": "processing",
            }
            _save_workflow_queue_state(state)
        payload = _mark_case_workflow_processing(
            case_id,
            {
                "state": "processing",
                "position": 0,
                "active": _get_workflow_queue_status().get("active"),
                "queue_length": len(_get_workflow_queue_status().get("queue") or []),
            },
            status="processing",
        )
        _spawn_workflow_worker(case_id)
        return CaseCreateResponse(**payload)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Caso no encontrado.") from exc
    except Exception as exc:
        logger.error("Error ejecutando flujo del caso %s: %s", case_id, exc)
        _mark_case_workflow_failed(case_id, f"No pude ejecutar el flujo automático: {exc}")
        raise HTTPException(status_code=500, detail=f"No pude ejecutar el flujo: {exc}") from exc
    finally:
        _start_next_queued_case_if_any()


@app.post("/api/cases/{case_id}/manual-review")
async def case_manual_review(case_id: str, request: CaseManualReviewRequest):
    try:
        if normalize_haystack(request.kind) != "comisiones" and normalize_haystack(request.verdict) not in {"si", "no"}:
            raise HTTPException(status_code=400, detail="La calificación debe ser 'si' o 'no'.")
        review_store = save_manual_review(
            case_id=case_id,
            kind=request.kind,
            filename=request.filename,
            verdict=request.verdict,
            expected_type=request.expected_type or "",
            comisiones=request.comisiones,
        )
        return {"case_id": case_id, "manual_review": review_store}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Caso no encontrado.") from exc


@app.post("/api/cases/{case_id}/document-workspace")
async def case_document_workspace(case_id: str, request: CaseDocumentWorkspaceRequest):
    try:
        payload = save_document_workspace(
            case_id=case_id,
            action=request.action,
            filename=request.filename or "",
            order=request.order or [],
        )
        return {
            "case_id": case_id,
            "document_workspace": (payload.get("analysis") or {}).get("document_workspace") or {},
            "case": payload,
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Caso no encontrado.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/evals/document-reviews/export")
async def export_document_reviews():
    summary = export_manual_review_dataset()
    path = get_document_reviews_export_path()
    if not path.exists():
        raise HTTPException(status_code=404, detail="No hay dataset exportado.")
    return FileResponse(
        path,
        media_type="application/jsonl",
        filename=path.name,
        headers={
            "X-Export-Rows": str(summary.get("rows", 0)),
            "X-Export-Cases": str(summary.get("cases", 0)),
            "X-Export-Updated-At": str(summary.get("updated_at", "")),
        },
    )


@app.post("/api/926/consolidated")
async def consolidated_926(request: Consolidated926Request):
    case_ids: List[str] = []
    seen = set()
    for case_id in request.case_ids or []:
        normalized = str(case_id or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        case_ids.append(normalized)
    if not case_ids:
        raise HTTPException(status_code=400, detail="Debes seleccionar al menos un contrato.")

    chunks: List[str] = []
    selected_cases: List[str] = []
    for case_id in case_ids:
        payload = load_case(case_id)
        analysis = payload.get("analysis") or {}
        workflow = analysis.get("workflow_run") or {}
        output_926 = workflow.get("output_926") or analysis.get("output_926") or {}
        legacy = output_926.get("legacy") or {}
        draft = output_926.get("draft") or {}
        content = str(legacy.get("content") or draft.get("content") or "").strip()
        if not content:
            continue
        resumen = (workflow.get("executive_report_final") or workflow.get("executive_report_precheck") or {}).get("resumen_ejecutivo") or {}
        profile = ((analysis.get("xlsx_profile") or {}).get("profile") or {})
        company = str(resumen.get("empresa") or profile.get("empresa") or case_id)
        nit = str(resumen.get("nit") or profile.get("nit") or "")
        chunks.append(content)
        selected_cases.append(case_id)

    if not chunks:
        raise HTTPException(status_code=400, detail="Los contratos seleccionados no tienen un 926 disponible para consolidar.")

    filename = f"lote_colmena_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    return Response(
        content="\n\n".join(chunks),
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Consolidated-Cases": str(len(selected_cases)),
        },
    )


@app.get("/api/feedback-notes")
async def list_feedback_notes():
    if not FEEDBACK_NOTES_PATH.exists():
        return {"items": []}
    items: List[Dict[str, Any]] = []
    for line in FEEDBACK_NOTES_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except Exception:
            continue
    return {"items": items}


@app.get("/api/testers")
async def list_testers():
    return {"items": _load_tester_roster()}


@app.post("/api/test-activity")
async def create_tester_activity(request: TesterActivityRequest):
    tester_email = str(request.tester_email or "").strip().lower()
    tester_name = str(request.tester_name or "").strip()
    action = str(request.action or "").strip().lower()
    if not tester_email or not action:
        raise HTTPException(status_code=400, detail="tester_email y action son obligatorios.")
    entry = {
        "tester_email": tester_email,
        "tester_name": tester_name or tester_email,
        "action": action,
        "metadata": request.metadata or {},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _append_tester_activity(entry)
    return {"ok": True, "item": entry}


@app.get("/api/test-activity/summary")
async def tester_activity_summary(date: Optional[str] = Query(default=None)):
    return _summarize_tester_activity(date)


@app.post("/api/test-activity/send-summary")
async def send_tester_activity_summary_email(date: Optional[str] = Query(default=None)):
    summary = _summarize_tester_activity(date)
    result = send_tester_activity_summary(summary)
    return {"ok": bool(result.get("ok")), "delivery": result.get("delivery"), "summary": summary}


@app.post("/api/feedback-notes")
async def create_feedback_note(request: FeedbackNoteRequest):
    name = str(request.name or "").strip()
    text = str(request.text or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="El nombre no puede estar vacío.")
    if not text:
        raise HTTPException(status_code=400, detail="El comentario no puede estar vacío.")
    FEEDBACK_NOTES_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "name": name,
        "text": text,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    with FEEDBACK_NOTES_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return {"ok": True, "item": entry}


@app.get("/api/cases/{case_id}/report")
async def case_report(case_id: str):
    try:
        payload = load_case(case_id)
        report = (payload.get("analysis") or {}).get("reporte_ejecutivo")
        if not report:
            raise HTTPException(status_code=409, detail="El caso aun no tiene reporte ejecutivo.")
        return report
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Caso no encontrado.") from exc


@app.get("/api/cases/{case_id}/926", response_class=PlainTextResponse)
async def case_926(case_id: str):
    try:
        payload = load_case(case_id)
        output_926 = (payload.get("analysis") or {}).get("output_926") or {}
        legacy = output_926.get("legacy") or {}
        draft = output_926.get("draft") or (payload.get("analysis") or {}).get("draft_926")
        if legacy.get("ok") and legacy.get("content"):
            return PlainTextResponse(content=str(legacy.get("content", "")), media_type="text/plain")
        if not draft:
            raise HTTPException(status_code=409, detail="El caso aun no esta listo para borrador 926.")
        return PlainTextResponse(content=str(draft.get("content", "")), media_type="text/plain")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Caso no encontrado.") from exc


@app.get("/api/cases/{case_id}/files/{filename:path}")
async def case_file(case_id: str, filename: str, download_name: str = Query(default=""), inline: bool = Query(default=False)):
    try:
        path = get_case_file_path(case_id, filename)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Archivo no encontrado.") from exc
    response_name = path.name
    if download_name:
        response_name = Path(download_name).name
    else:
        try:
            payload = load_case(case_id)
            docs = payload.get("analysis", {}).get("documents", []) or []
            for doc in docs:
                if str(doc.get("filename") or "") == filename:
                    response_name = str(doc.get("download_filename") or doc.get("display_filename") or path.name)
                    break
        except Exception:
            response_name = path.name
    media_type = None
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        media_type = "application/pdf"
    elif suffix in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
        media_type = f"image/{'jpeg' if suffix in {'.jpg', '.jpeg'} else suffix.lstrip('.')}"
    elif suffix in {".tif", ".tiff"}:
        media_type = "image/tiff"
    if inline:
        return FileResponse(path, media_type=media_type, filename=response_name, content_disposition_type="inline")
    return FileResponse(path, media_type=media_type, filename=response_name, content_disposition_type="attachment")



@app.delete("/api/cases/{case_id}/files/{filename:path}")
async def delete_case_file(case_id: str, filename: str):
    try:
        path = get_case_file_path(case_id, filename)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Archivo no encontrado.")
    try:
        path.unlink()
        return {"ok": True, "deleted": filename}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/cases/{case_id}/files/{filename:path}/duplicate")
async def duplicate_case_file(case_id: str, filename: str):
    try:
        src = get_case_file_path(case_id, filename)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Archivo no encontrado.")
    import shutil as _shutil
    stem = src.stem
    suffix = src.suffix
    counter = 1
    while True:
        new_name = f"{stem}_copia{counter}{suffix}"
        dst = src.parent / new_name
        if not dst.exists():
            break
        counter += 1
    _shutil.copy2(src, dst)
    return {"ok": True, "filename": new_name}


@app.get("/api/cases/{case_id}/package")
async def case_package(case_id: str):
    try:
        payload = load_case(case_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Caso no encontrado.") from exc

    analysis = payload.get("analysis") or {}
    profile = ((analysis.get("xlsx_profile") or {}).get("profile") or {})
    workflow = analysis.get("workflow_run") or {}
    docs = analysis.get("documents") or []
    report = workflow.get("executive_report_final") or workflow.get("executive_report_precheck") or analysis.get("reporte_ejecutivo") or {}
    resumen = report.get("resumen_ejecutivo") or {}
    empresa = str(resumen.get("empresa") or profile.get("empresa") or payload.get("label") or case_id).strip() or case_id
    nit = str(resumen.get("nit") or profile.get("nit") or "").strip()

    package_buffer = io.BytesIO()
    with zipfile.ZipFile(package_buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "resumen_proceso.txt",
            "\n".join(
                [
                    f"Caso: {payload.get('id') or case_id}",
                    f"Empresa: {empresa}",
                    f"NIT: {nit or 'n/d'}",
                    f"Estado del flujo: {workflow.get('status') or payload.get('status') or 'n/d'}",
                    f"Estado final: {resumen.get('estado') or report.get('estado_final') or 'n/d'}",
                    f"Fecha: {resumen.get('fecha_proceso_human') or report.get('fecha_proceso_human') or payload.get('updated_at') or 'n/d'}",
                ]
            ),
        )
        if docs:
            lines = []
            for doc in docs:
                if str(doc.get("filename") or "").strip() in removed_files:
                    continue
                lines.append(
                    " | ".join(
                        [
                            str(doc.get("document_type") or "sin_tipo"),
                            str(doc.get("display_filename") or doc.get("download_filename") or doc.get("filename") or "sin_archivo"),
                        ]
                    )
                )
            archive.writestr("indice_documentos.txt", "\n".join(lines))

        output_926 = workflow.get("output_926") or analysis.get("output_926") or {}
        legacy = output_926.get("legacy") or {}
        draft = output_926.get("draft") or {}
        if legacy.get("content"):
            archive.writestr(str(legacy.get("filename") or "archivo_core.txt"), str(legacy.get("content") or ""))
        elif draft.get("content"):
            archive.writestr(str(draft.get("filename") or "borrador_926.txt"), str(draft.get("content") or ""))

        for item in payload.get("files") or []:
            filename = str(item.get("filename") or "").strip()
            if not filename or filename in removed_files:
                continue
            try:
                path = get_case_file_path(case_id, filename)
            except FileNotFoundError:
                continue
            archive.write(path, arcname=f"files/{path.name}")

    package_buffer.seek(0)
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", nit or empresa or case_id).strip("_") or case_id
    return Response(
        content=package_buffer.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="paquete_{safe_name}.zip"'
        },
    )


@app.get("/api/modelos")
async def listar_modelos():
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{settings.ollama_url}/api/tags", timeout=5.0)
            if response.status_code == 200:
                return response.json()
            return {"error": "No se pudo conectar con Ollama"}
    except Exception as exc:
        return {"error": str(exc)}
