import logging
from difflib import SequenceMatcher
import json
import re
from typing import Dict, List, Optional
from pathlib import Path
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
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
    rebuild_document_registry,
    run_case_workflow,
    save_manual_review,
    search_cases,
    search_document_registry,
    store_case_files,
)
from .config import settings
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
        display_name = profile.get('nombre') or 'n/d'
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
        if len(str(display_name).strip()) < 8 or len(name_tokens) < 2:
            candidate = _derive_full_representative_name(
                top.get("case_id") or "",
                profile.get("documento") or "",
                profile.get("nombre") or "",
            )
            if _looks_like_person_name(candidate):
                display_name = candidate
        precheck = top.get("precheck") or {}
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
            f"- Prevalidación: {'APROBADA' if precheck.get('approved') else 'NO APROBADA'}",
        ]
        if not precheck.get("approved"):
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
        key = (
            str(item.get("case_id") or ""),
            str(item.get("document_type") or ""),
            str(item.get("filename") or ""),
        )
        if key in seen_band:
            continue
        seen_band.add(key)
        unique_band.append(item)
    same_band = unique_band
    if len(same_band) > 1:
        options = [
            f"- {item.get('person_name') or item.get('company') or item.get('label')} · {item.get('document_type')} · {item.get('filename')}"
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
                f"- Persona: {top.get('person_name') or 'n/d'}",
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


@app.get("/")
async def root():
    return {"message": f"{settings.app_name} - Control Plane"}


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
        consulta_lower = request.consulta.lower()
        document_first = any(token in consulta_lower for token in ["cedula", "cédula", "rut", "camara", "cámara", "pdf", "documento", "soporte", "formulario"])
        case_results = search_cases(request.consulta, limit=5)
        case_response = build_case_consulta_response(request.consulta, case_results)
        document_results = search_document_registry(request.consulta, limit=8)
        focused_case_id = None
        if case_response is not None and "Coincidencias encontradas:" not in case_response.respuesta and case_results:
            focused_case_id = case_results[0].get("case_id")
        if focused_case_id:
            focused_documents = [item for item in document_results if item.get("case_id") == focused_case_id]
            if focused_documents:
                document_results = focused_documents
        document_response = build_document_consulta_response(request.consulta, document_results)
        if document_first and document_response is not None:
            return document_response
        if case_response is not None:
            return case_response
        if document_response is not None:
            return document_response
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
    for item in files or []:
        uploads.append((item.filename or "archivo.bin", await item.read()))
    if xlsx_file is not None:
        uploads.append((xlsx_file.filename or "case.xlsx", await xlsx_file.read()))
    for item in attachments or []:
        uploads.append((item.filename or "adjunto.bin", await item.read()))
    if not uploads:
        raise HTTPException(status_code=400, detail="Debes adjuntar al menos un XLSX o un soporte.")
    case_payload = store_case_files(label=label, uploads=uploads)
    return CaseCreateResponse(**case_payload)


@app.get("/api/cases/{case_id}", response_model=CaseCreateResponse)
async def case_detail(case_id: str):
    try:
        payload = load_case(case_id)
        return CaseCreateResponse(**payload)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Caso no encontrado.") from exc


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
        payload = run_case_workflow(case_id)
        return CaseCreateResponse(**payload)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Caso no encontrado.") from exc
    except Exception as exc:
        logger.error("Error ejecutando flujo del caso %s: %s", case_id, exc)
        raise HTTPException(status_code=500, detail=f"No pude ejecutar el flujo: {exc}") from exc


@app.post("/api/cases/{case_id}/manual-review")
async def case_manual_review(case_id: str, request: CaseManualReviewRequest):
    try:
        if normalize_haystack(request.verdict) not in {"si", "no"}:
            raise HTTPException(status_code=400, detail="La calificación debe ser 'si' o 'no'.")
        review_store = save_manual_review(
            case_id=case_id,
            kind=request.kind,
            filename=request.filename,
            verdict=request.verdict,
            expected_type=request.expected_type or "",
        )
        return {"case_id": case_id, "manual_review": review_store}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Caso no encontrado.") from exc


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
async def case_file(case_id: str, filename: str, download_name: str = Query(default="")):
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
    return FileResponse(path, media_type=media_type, filename=response_name)


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
