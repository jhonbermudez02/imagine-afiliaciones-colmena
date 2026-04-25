from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import shutil
import time
import unicodedata
import uuid
import zipfile
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, List, Optional

import httpx
import pytesseract
from openpyxl import load_workbook
from pdf2image import convert_from_path
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
from pypdf import PdfReader, PdfWriter

from .config import settings
from .legacy_bridge import generate_legacy_flatfile_926, generate_legacy_flatfile_926_http
from .xlsx_rules import _format_date_value, _parse_date_value, _resolve_smmlv_value, run_xlsx_primary_validations, run_xlsx_secondary_validations

LEGACY_CODE_TO_TYPE = {
    0: "formulario_afiliacion",
    1: "anexo_sedes",
    2: "listado_trabajadores",
    3: "comision",
    4: "carta",
    5: "camara_comercio",
    6: "cedula",
    7: "constancia_afiliacion",
    8: "rut",
    10: "entrega_documentos",
    11: "soporte_pagos",
    12: "contrato",
    13: "eps",
    14: "afp",
    15: "paz_y_salvo",
    16: "eps_afp",
    17: "detectar",
    19: "identificacion_peligros",
    20: "examen_preocupacional",
    21: "autorizacion_terceros",
    22: "historia_clinica",
    23: "afiliacion_eps",
    24: "afiliacion_afp",
    25: "carta_independiente_voluntario",
    26: "siarl",
    27: "beneficiario_final",
    28: "sat",
    98: "autorizacion",
    99: "imagen",
}

DOC_TYPE_LABELS = {
    "comision": "Comisión",
    "carta": "Cartas",
    "constancia_afiliacion": "Verificación",
    "cedula": "Cédula",
    "rut": "RUT",
    "camara_comercio": "Cámara de comercio",
    "contrato": "Contrato",
    "soporte_ingresos": "Pagos",
    "formulario_afiliacion": "Afiliación",
    "anexo_sedes": "Sedes",
    "listado_trabajadores": "Listados",
    "entrega_documentos": "Entrega Doc",
    "soporte_pagos": "Pagos",
    "identificacion_peligros": "Identificación de peligros",
    "examen_preocupacional": "Examen preocupacional",
    "beneficiario_final": "Beneficiario final",
    "autorizacion": "Autorización",
    "sat": "SAT",
}

DOC_TYPE_TO_PRIMARY_CODE: Dict[str, int] = {}
for _legacy_code, _doc_type in LEGACY_CODE_TO_TYPE.items():
    DOC_TYPE_TO_PRIMARY_CODE.setdefault(_doc_type, _legacy_code)

LEGACY_INDEPENDIENTES_FIELDS = [
    "sr", "linea", "tipodocumento", "documento", "primer_apellido", "segundo_apellido", "primer_nombre",
    "segundo_nombre", "fecha_nacimiento", "sexo", "direccion", "departamento", "municipio", "zona", "localidad",
    "telefono", "celular", "correo", "eps", "codigo_eps", "afp", "codigo_afp", "arl_anterior",
    "codigo_arl_anterior", "tipo_cotizante", "subtipo_cotizante", "modalidad", "actividad_especial", "tipo_contrato",
    "transporte", "fecha_inicio_contrato", "fecha_fin_contrato", "meses_contrato", "valor_contrato", "valor_mensual",
    "ibc", "actividad_economica", "nombre_actividad", "clase_riesgo", "tasa_riesgo", "lunes", "martes", "miercoles",
    "jueves", "viernes", "sabado", "domingo", "d1", "d2", "d3", "d4", "d5", "d6", "d7", "d8", "d9", "d10",
    "d11", "d12", "d13", "d14", "d15", "d16", "d17", "d18", "d19", "d20", "d21", "d22", "d23", "d24",
    "codigo_ct", "nombre_ct", "actividad_economica_ct", "clase_riesgo_ct", "tasa_riesgo_ct", "direccion_ct",
    "departamento_ct", "ciudad_ct", "zona_ct", "telefono_ct", "celular_ct", "correo_ct", "localidad_ct", "lote",
    "tipo_salario",
]

DOCUMENT_CALIBRATION_PATH = Path(settings.cases_dir).parent / "evals" / "learning" / "document_calibration.json"
DOCUMENT_SUPERVISION_PATH = Path(settings.cases_dir).parent / "evals" / "learning" / "document_supervision.jsonl"
LEARNING_MANIFEST_PATH = Path(settings.cases_dir).parent / "evals" / "learning" / "manifest.json"
_DOCUMENT_CALIBRATION_CACHE: Optional[Dict[str, Any]] = None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_document_calibration() -> Dict[str, Any]:
    global _DOCUMENT_CALIBRATION_CACHE
    if _DOCUMENT_CALIBRATION_CACHE is not None:
        return _DOCUMENT_CALIBRATION_CACHE
    try:
        _DOCUMENT_CALIBRATION_CACHE = json.loads(DOCUMENT_CALIBRATION_PATH.read_text(encoding="utf-8"))
    except Exception:
        _DOCUMENT_CALIBRATION_CACHE = {}
    return _DOCUMENT_CALIBRATION_CACHE


def _refresh_learning_artifacts() -> None:
    global _DOCUMENT_CALIBRATION_CACHE
    try:
        payloads: List[Dict[str, Any]] = []
        for case_dir in sorted(get_cases_root().iterdir()):
            if not case_dir.is_dir():
                continue
            metadata_path = case_dir / "case.json"
            if not metadata_path.exists():
                continue
            try:
                payloads.append(json.loads(metadata_path.read_text(encoding="utf-8")))
            except Exception:
                continue

        rows: List[Dict[str, Any]] = []
        for payload in payloads:
            analysis = payload.get("analysis") or {}
            manual_review = analysis.get("manual_review") or {}
            if not manual_review:
                continue
            profile = ((analysis.get("xlsx_profile") or {}).get("profile") or {})
            docs = analysis.get("documents") or []
            docs_by_filename = {str(doc.get("filename") or ""): doc for doc in docs}
            for bucket_name, entries in (manual_review or {}).items():
                if not isinstance(entries, dict):
                    continue
                for filename, review in entries.items():
                    verdict = str((review or {}).get("verdict") or "")
                    if verdict not in {"si", "no"}:
                        continue
                    expected_type = str((review or {}).get("expected_type") or "")
                    if bucket_name == "xlsx":
                        continue
                    doc = docs_by_filename.get(str(filename)) or {}
                    predicted_type = str(doc.get("document_type") or "")
                    ground_truth_type = expected_type or (predicted_type if verdict == "si" else "")
                    rows.append(
                        {
                            "case_id": payload.get("id"),
                            "empresa": profile.get("empresa") or "",
                            "nit": profile.get("nit") or "",
                            "documento": profile.get("documento") or "",
                            "filename": filename,
                            "bucket": "documents",
                            "review_verdict": verdict,
                            "predicted_type": predicted_type,
                            "ground_truth_type": ground_truth_type,
                            "predicted_code": doc.get("legacy_code"),
                            "ground_truth_code": DOC_TYPE_TO_PRIMARY_CODE.get(ground_truth_type) if ground_truth_type else None,
                            "supervision_status": "confirmed" if ground_truth_type else "pending_correction",
                            "classification_confidence": doc.get("classification_confidence"),
                            "ocr_quality_score": doc.get("ocr_quality_score"),
                            "signals_detected": doc.get("signals_detected") or [],
                            "text_preview": str(doc.get("text_preview") or doc.get("ocr_text") or "")[:800],
                        }
                    )

        signal_hints_library = {
            "cedula": [
                "cedula de ciudadania",
                "cedula de ciudadanía",
                "lugar de nacimiento",
                "fecha y lugar de expedicion",
                "fecha y lugar de expedición",
                "indice derecho",
                "índice derecho",
                "registrador nacional",
            ],
            "soporte_ingresos": [
                "planilla resumen",
                "resumen general de pago",
                "resumen de pago a salud",
                "informe consolidado de pagos por empresas",
                "datos generales del aportante",
                "valor a pagar",
                "ibc salud",
                "ibc pension",
                "ibc pensión",
            ],
            "carta": [
                "se adjuntan los siguientes documentos",
                "cordialmente",
                "representante legal",
                "por medio de la presente",
                "desvinculacion de empresa",
                "desvinculación de empresa",
                "agradeciendo su colaboracion",
                "agradeciendo su colaboración",
            ],
        }
        confirmed_rows = [row for row in rows if row.get("supervision_status") == "confirmed"]
        remap_groups: Dict[tuple[str, str], List[Dict[str, Any]]] = {}
        stable_counts: Dict[str, int] = {}
        for row in confirmed_rows:
            predicted_type = str(row.get("predicted_type") or "")
            ground_truth_type = str(row.get("ground_truth_type") or "")
            if predicted_type and predicted_type == ground_truth_type:
                stable_counts[predicted_type] = stable_counts.get(predicted_type, 0) + 1
            if predicted_type and ground_truth_type and predicted_type != ground_truth_type:
                remap_groups.setdefault((predicted_type, ground_truth_type), []).append(row)

        remaps: List[Dict[str, Any]] = []
        for (predicted_type, ground_truth_type), group in sorted(remap_groups.items(), key=lambda item: len(item[1]), reverse=True):
            signal_counts: Dict[str, int] = {}
            matched_hints: Dict[str, int] = {}
            for row in group:
                for signal in row.get("signals_detected") or []:
                    normalized = normalize_text(signal)
                    if normalized:
                        signal_counts[normalized] = signal_counts.get(normalized, 0) + 1
                haystack = normalize_haystack(row.get("text_preview") or "")
                for hint in signal_hints_library.get(ground_truth_type, []):
                    if normalize_haystack(hint) in haystack:
                        matched_hints[hint] = matched_hints.get(hint, 0) + 1
            remaps.append(
                {
                    "from_type": predicted_type,
                    "to_type": ground_truth_type,
                    "count": len(group),
                    "signal_hints": [
                        signal for signal, _ in sorted(signal_counts.items(), key=lambda item: (-item[1], item[0]))[:6]
                    ],
                    "text_hints": [
                        hint for hint, _ in sorted(matched_hints.items(), key=lambda item: (-item[1], item[0]))[:6]
                    ],
                    "sample_filenames": [str(row.get("filename") or "") for row in group[:3]],
                }
            )

        DOCUMENT_SUPERVISION_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
        DOCUMENT_SUPERVISION_PATH.write_text(payload + ("\n" if payload else ""), encoding="utf-8")
        DOCUMENT_CALIBRATION_PATH.write_text(
            json.dumps(
                {
                    "generated_at": utc_now(),
                    "confirmed_rows_total": len(confirmed_rows),
                    "confirmed_mismatch_rows_total": sum(len(items) for items in remap_groups.values()),
                    "stable_counts": dict(sorted(stable_counts.items(), key=lambda item: (-item[1], item[0]))),
                    "remaps": remaps,
                    "notes": [
                        "Calibración documental regenerada automáticamente a partir de revisiones manuales.",
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        _DOCUMENT_CALIBRATION_CACHE = None
    except Exception:
        # La revisión manual no debe fallar por un refresco de aprendizaje.
        return


def _format_date_es(dt: datetime) -> str:
    months = {
        1: "enero",
        2: "febrero",
        3: "marzo",
        4: "abril",
        5: "mayo",
        6: "junio",
        7: "julio",
        8: "agosto",
        9: "septiembre",
        10: "octubre",
        11: "noviembre",
        12: "diciembre",
    }
    return f"{dt.day} de {months.get(dt.month, str(dt.month))} de {dt.year}"


def get_cases_root() -> Path:
    root = Path(settings.cases_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def get_document_registry_path() -> Path:
    path = Path(settings.document_registry_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_lote_counter_path() -> Path:
    path = Path(settings.lote_counter_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_evals_dir() -> Path:
    path = get_cases_root() / "evals"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_document_reviews_export_path() -> Path:
    return get_evals_dir() / "document_reviews.jsonl"


def get_case_dir(case_id: str) -> Path:
    return get_cases_root() / case_id


def get_case_metadata_path(case_id: str) -> Path:
    return get_case_dir(case_id) / "case.json"


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_haystack(value: Any) -> str:
    text = normalize_text(value).lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).strip()


def fuzzy_text_score(query: str, candidate: Any) -> int:
    q = normalize_haystack(query)
    c = normalize_haystack(candidate)
    if not q or not c:
        return 0
    if q in c or c in q:
        return 12
    candidates = [c]
    candidates.extend(token for token in c.split() if len(token) >= 4)
    ratio = max(SequenceMatcher(None, q, piece).ratio() for piece in candidates)
    if ratio >= 0.9:
        return 12
    if ratio >= 0.8:
        return 8
    if ratio >= 0.72:
        return 4
    return 0


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-").lower()
    return cleaned or "archivo"


def only_digits(value: Any) -> str:
    return re.sub(r"\D+", "", str(value or ""))


def _is_strict_numeric_value(value: Any) -> bool:
    text = normalize_text(value)
    if not text:
        return False
    return bool(re.fullmatch(r"\d+", text))


def _parse_birthdate_from_record(record: Dict[str, Any]) -> Optional[datetime]:
    combined = normalize_text(record.get("fecha_de_nacimiento", ""))
    candidates = [combined]
    day = only_digits(record.get("fecha_nacimiento_dia", ""))
    month = only_digits(record.get("fecha_nacimiento_mes", ""))
    year = only_digits(record.get("fecha_nacimiento_ano", ""))
    if day and month and year:
        if len(year) == 2:
            year = f"19{year}"
        candidates.append(f"{day}/{month}/{year}")
    for value in candidates:
        if not value:
            continue
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
    return None


def _age_years(birthdate: datetime, today: Optional[datetime] = None) -> int:
    base = (today or datetime.now()).date()
    born = birthdate.date()
    return base.year - born.year - ((base.month, base.day) < (born.month, born.day))


def _normalize_sexo_identificacion(value: Any) -> str:
    text = normalize_haystack(value).upper()
    text = re.sub(r"[^A-Z0-9]+", "", text)
    aliases = {
        "M": "M",
        "MASCULINO": "M",
        "F": "F",
        "FEMENINO": "F",
        "T": "T",
        "TRANSGENERO": "T",
        "TRANSGÉNERO": "T",
        "NB": "NB",
        "NOBINARIO": "NB",
        "NOBINARIA": "NB",
        "O": "O",
        "OTRO": "O",
    }
    return aliases.get(text, text)


def _normalize_tipo_trabajador(value: Any) -> str:
    text = normalize_haystack(value).upper()
    text = re.sub(r"[^A-Z0-9]+", "", text)
    aliases = {
        "DEPENDIENTE": "DEPENDIENTE",
        "INDEPENDIENTE": "INDEPENDIENTE",
        "ESTUDIANTE": "ESTUDIANTE",
        "ESTUDIANTESDECRETO055DE2015": "ESTUDIANTE",
        "23": "ESTUDIANTE",
        "PENSIONADO": "PENSIONADO",
        "APRENDIZ": "APRENDIZ",
        "APRENDIZENETAPALECTIVA": "APRENDIZ",
        "APRENDIZENETAPAPRACTICA": "APRENDIZ",
        "APRENDIZENETAPAPRODUCTIVA": "APRENDIZ",
        "APRENDICESENETAPAPRODUCTIVA": "APRENDIZ",
        "19": "APRENDIZ",
        "COOPERADO": "COOPERADO",
        "31": "COOPERADO",
    }
    return aliases.get(text, text)


def _normalize_tipo_salario(value: Any) -> str:
    raw = normalize_text(value)
    text = normalize_haystack(raw).upper()
    compact = re.sub(r"[^A-Z0-9]+", "", text)
    if compact.startswith("1") or "FIJO" in compact:
        return "FIJO"
    if compact.startswith("2") or "VARIABLE" in compact:
        return "VARIABLE"
    if compact.startswith("3") or "INTEGRAL" in compact:
        return "INTEGRAL"
    return compact


def _record_value_by_tokens(record: Dict[str, Any], token_groups: List[List[str]]) -> str:
    for key, value in record.items():
        key_norm = normalize_haystack(key)
        if not key_norm:
            continue
        for tokens in token_groups:
            if all(token in key_norm for token in tokens):
                text = normalize_text(value)
                if text:
                    return text
    return ""


def _record_first_value(record: Dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = normalize_text(record.get(key, ""))
        if value:
            return value
    return ""


def _business_days_between(start: datetime, end: datetime) -> int:
    from datetime import date as _date
    # Festivos Colombia 2025-2026 (Ley Emiliani)
    FESTIVOS_CO = {
        _date(2025, 1, 1), _date(2025, 1, 6), _date(2025, 3, 24), _date(2025, 4, 17),
        _date(2025, 4, 18), _date(2025, 5, 1), _date(2025, 6, 2), _date(2025, 6, 23),
        _date(2025, 6, 30), _date(2025, 7, 20), _date(2025, 8, 7), _date(2025, 8, 18),
        _date(2025, 10, 13), _date(2025, 11, 3), _date(2025, 11, 17), _date(2025, 12, 8),
        _date(2025, 12, 25),
        _date(2026, 1, 1), _date(2026, 1, 12), _date(2026, 3, 23), _date(2026, 4, 2),
        _date(2026, 4, 3), _date(2026, 5, 1), _date(2026, 5, 18), _date(2026, 6, 8),
        _date(2026, 6, 29), _date(2026, 7, 20), _date(2026, 8, 7), _date(2026, 8, 17),
        _date(2026, 10, 12), _date(2026, 11, 2), _date(2026, 11, 16), _date(2026, 12, 8),
        _date(2026, 12, 25),
    }
    start_date = start.date()
    end_date = end.date()
    if end_date <= start_date:
        return 0
    business_days = 0
    current = start_date
    while current < end_date:
        if current.weekday() < 5 and current not in FESTIVOS_CO:
            business_days += 1
        current = current.fromordinal(current.toordinal() + 1)
    return business_days


def _normalize_modalidad(value: Any) -> str:
    text = normalize_haystack(value).upper()
    text = "".join(ch for ch in text if ch.isalnum())
    aliases = {
        "PRESENCIAL": "PRESENCIAL",
        "TELETRABAJO": "TELETRABAJO",
        "CASA": "CASA",
        "REMOTO": "REMOTO",
    }
    return aliases.get(text, text)


def _normalize_jornada(value: Any) -> str:
    text = normalize_haystack(value).upper()
    text = re.sub(r"[^A-Z0-9]+", "", text)
    aliases = {
        "UNICA": "UNICA",
        "TURNOS": "TURNOS",
        "ROTATIVA": "ROTATIVA",
    }
    return aliases.get(text, text)


def _normalize_zona(value: Any) -> str:
    text = normalize_haystack(value).upper()
    text = re.sub(r"[^A-Z0-9]+", "", text)
    aliases = {
        "U": "U",
        "URBANA": "U",
        "R": "R",
        "RURAL": "R",
    }
    return aliases.get(text, text)


def build_generated_lote_usuario(fecha_proceso: str) -> str:
    fecha_digits = only_digits(fecha_proceso)[:8] or datetime.now().strftime("%Y%m%d")
    path = get_lote_counter_path()
    state: Dict[str, Any] = {}
    if path.exists():
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            state = {}
    last_date = only_digits(state.get("last_date"))[:8]
    last_seq = int(state.get("last_seq") or 0)
    next_seq = last_seq + 1 if last_date == fecha_digits else 1
    state = {
        "last_date": fecha_digits,
        "last_seq": next_seq,
        "updated_at": utc_now(),
    }
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return f"{next_seq:012d}"


def _canonical_numeric_value(value: Any) -> str:
    digits = only_digits(value)
    stripped = digits.lstrip("0")
    return stripped or digits


def _numeric_similarity_match(expected: str, candidate: str) -> bool:
    expected_digits = _canonical_numeric_value(expected)
    candidate_digits = _canonical_numeric_value(candidate)
    if not expected_digits or not candidate_digits:
        return False
    if expected_digits == candidate_digits:
        return True
    if abs(len(expected_digits) - len(candidate_digits)) > 1:
        return False
    if expected_digits.startswith(candidate_digits) or candidate_digits.startswith(expected_digits):
        return True
    mismatches = 0
    i = 0
    j = 0
    while i < len(expected_digits) and j < len(candidate_digits):
        if expected_digits[i] == candidate_digits[j]:
            i += 1
            j += 1
            continue
        mismatches += 1
        if mismatches > 1:
            return False
        if len(expected_digits) > len(candidate_digits):
            i += 1
        elif len(candidate_digits) > len(expected_digits):
            j += 1
        else:
            i += 1
            j += 1
    if i < len(expected_digits) or j < len(candidate_digits):
        mismatches += 1
    return mismatches <= 1


def _numeric_document_match(expected: str, candidate: str) -> bool:
    expected_digits = _canonical_numeric_value(expected)
    candidate_digits = _canonical_numeric_value(candidate)
    if not expected_digits or not candidate_digits:
        return False
    return expected_digits == candidate_digits


def _best_numeric_candidate(expected: str, values: List[Any]) -> str:
    expected_digits = _canonical_numeric_value(expected)
    candidates: List[str] = []
    for raw in values:
        digits = _canonical_numeric_value(raw)
        if digits:
            candidates.append(digits)
    exact = [candidate for candidate in candidates if candidate == expected_digits]
    if exact:
        return exact[0]
    close = [candidate for candidate in candidates if _numeric_similarity_match(expected_digits, candidate)]
    if close:
        close.sort(key=lambda item: (abs(len(item) - len(expected_digits)), -len(item)))
        return close[0]
    return ""


def _best_document_candidate(expected: str, values: List[Any]) -> str:
    expected_digits = _canonical_numeric_value(expected)
    candidates: List[str] = []
    for raw in values:
        digits = _canonical_numeric_value(raw)
        if digits:
            candidates.append(digits)
    exact = [candidate for candidate in candidates if _numeric_document_match(expected_digits, candidate)]
    if exact:
        return exact[0]
    return ""


def _normalize_company_nit(value: Any, docs: Optional[List[Dict[str, Any]]] = None) -> str:
    digits = only_digits(value)
    if not digits:
        return ""
    if len(digits) != 10 or not docs:
        return digits
    prefix = digits[:-1]
    doc_nits = set()
    for doc in docs:
        fields = doc.get("fields") or {}
        doc_nit = only_digits(fields.get("nit", ""))
        if 8 <= len(doc_nit) <= 10:
            doc_nits.add(doc_nit)
    if prefix in doc_nits:
        return prefix
    return digits


def _document_owner_identifier(xlsx_profile: Dict[str, Any]) -> str:
    profile = xlsx_profile.get("profile", {}) if isinstance(xlsx_profile, dict) else {}
    nit = only_digits(profile.get("nit", ""))
    documento = only_digits(profile.get("documento", ""))
    return nit or documento


def _document_alias_code(legacy_code: Any) -> str:
    try:
        code = int(legacy_code)
    except (TypeError, ValueError):
        return "99"
    if code == 0:
        return "01"
    if code < 0:
        return "99"
    return str(code).zfill(2)


def _build_operational_filename(identifier: str, legacy_code: Any, original_filename: str) -> str:
    safe_identifier = only_digits(identifier)
    if not safe_identifier:
        return original_filename
    path = Path(original_filename)
    suffix = "".join(path.suffixes) or path.suffix or ".pdf"
    stem = path.name[: -len(suffix)] if suffix and path.name.endswith(suffix) else path.stem
    page_match = re.search(r"(__p\d+)$", stem, flags=re.IGNORECASE)
    page_suffix = page_match.group(1) if page_match else ""
    return f"{safe_identifier},{_document_alias_code(legacy_code)}{page_suffix}{suffix}"


def _attach_operational_filenames(docs: List[Dict[str, Any]], xlsx_profile: Dict[str, Any]) -> None:
    identifier = _document_owner_identifier(xlsx_profile)
    for doc in docs:
        original_filename = str(doc.get("filename") or "")
        display_filename = _build_operational_filename(identifier, doc.get("legacy_code"), original_filename)
        doc["display_filename"] = display_filename
        doc["download_filename"] = display_filename


def _extract_name_from_cedula_text(text: str) -> str:
    normalized = normalize_text(text).upper()
    direct_patterns = [
        r"([A-ZÁÉÍÓÚÑ ]{4,80})\s+APELLIDOS\b[^A-ZÁÉÍÓÚÑ]{0,10}([A-ZÁÉÍÓÚÑ .]{4,80})\s+NOMBRES",
        r"APELLIDOS\b[^A-ZÁÉÍÓÚÑ]{0,10}([A-ZÁÉÍÓÚÑ ]{4,80})\s+NOMBRES\b[^A-ZÁÉÍÓÚÑ]{0,10}([A-ZÁÉÍÓÚÑ ]{4,80})",
    ]
    for pattern in direct_patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if match:
            groups = [normalize_text(group).strip(" .,-") for group in match.groups() if normalize_text(group)]
            if len(groups) == 2:
                return normalize_text(f"{groups[1]} {groups[0]}")

    compact = re.sub(r"[^A-ZÁÉÍÓÚÑ ]+", " ", normalized)
    compact = re.sub(r"\s+", " ", compact).strip()
    match = re.search(r"([A-ZÁÉÍÓÚÑ ]{4,80}) APELLIDOS ([A-ZÁÉÍÓÚÑ ]{4,80}) NOMBRES", compact)
    if match:
        surname = normalize_text(match.group(1))
        names = normalize_text(match.group(2))
        return normalize_text(f"{names} {surname}")

    if "APELLIDOS" in compact and "NOMBRES" in compact:
        before_apellidos, after_apellidos = compact.split("APELLIDOS", 1)
        names_segment, _, _ = after_apellidos.partition("NOMBRES")
        surname_tokens = before_apellidos.split()[-4:]
        name_tokens = names_segment.split()[:4]
        surname = normalize_text(" ".join(token for token in surname_tokens if len(token) > 1))
        names = normalize_text(" ".join(token for token in name_tokens if len(token) > 1))
        if surname and names:
            return normalize_text(f"{names} {surname}")
    return ""




# ── RAG: Clasificador basado en experiencia ──────────────────
_rag_client = None

def _get_rag_client():
    global _rag_client
    if _rag_client is None:
        try:
            from qdrant_client import QdrantClient
            _rag_client = QdrantClient(host="imagine_qdrant", port=6333)
        except Exception:
            pass
    return _rag_client

def _rag_classify_document(ocr_text: str, min_score: float = 0.82) -> Optional[Dict[str, Any]]:
    """Busca en RAG el tipo de documento mas similar al OCR dado.
    Retorna el tipo si la similitud supera min_score, None si no."""
    if not ocr_text or len(ocr_text.strip()) < 30:
        return None
    try:
        qdrant = _get_rag_client()
        if not qdrant:
            return None
        from app.embeddings import embed_text as _embed_text
        vector = _embed_text(ocr_text[:1500])
        if not vector:
            return None
        results = qdrant.search(
            collection_name="afi_doc_clasificaciones",
            query_vector=vector,
            limit=3,
            score_threshold=min_score,
        )
        if not results:
            return None
        # Votar por el tipo mas frecuente entre los top resultados
        from collections import Counter
        tipos = Counter(r.payload.get("document_type") for r in results if r.payload.get("document_type"))
        if not tipos:
            return None
        best_type, count = tipos.most_common(1)[0]
        best_score = results[0].score
        import logging as _logging; _logging.getLogger("afi.rag").info("RAG clasifico documento como '%s' (score=%.3f, votos=%d)", best_type, best_score, count)
        return {
            "document_type": best_type,
            "legacy_code": results[0].payload.get("legacy_code", 99),
            "code_source": "rag_classification",
            "rag_score": best_score,
            "rag_votes": count,
        }
    except Exception as exc:
        import logging as _logging; _logging.getLogger("afi.rag").debug("RAG classify error: %s", exc)
        return None


def _rag_index_document(case_id: str, filename: str, ocr_text: str, document_type: str, legacy_code: int = 99) -> bool:
    """Indexa un documento en RAG para aprendizaje futuro."""
    if not ocr_text or len(ocr_text.strip()) < 30:
        return False
    try:
        qdrant = _get_rag_client()
        if not qdrant:
            return False
        import uuid as _uuid
        from qdrant_client.models import PointStruct
        from app.embeddings import embed_text as _embed_text
        vector = _embed_text(ocr_text[:1500])
        if not vector:
            return False
        qdrant.upsert("afi_doc_clasificaciones", points=[PointStruct(
            id=str(_uuid.uuid4()), vector=vector,
            payload={"case_id": case_id, "filename": filename,
                "document_type": document_type, "legacy_code": legacy_code,
                "source": "auto_index", "ocr_preview": ocr_text[:200]}
        )])
        return True
    except Exception as exc:
        import logging as _logging; _logging.getLogger("afi.rag").debug("RAG index error: %s", exc)
        return False

# ── Tabla asesores Colmena ──────────────────────────────────
_ASESORES_CACHE: Dict[str, Any] = {}

def _load_asesores_colmena() -> Dict[str, Any]:
    global _ASESORES_CACHE
    if _ASESORES_CACHE:
        return _ASESORES_CACHE
    try:
        p = Path(settings.cases_dir).parent / "evals" / "asesores_colmena.json"
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            comerciales = {only_digits(str(r.get("cedula",""))): r for r in data.get("comerciales", []) if r.get("cedula")}
            intermediarios = {only_digits(str(r.get("cedula",""))): r for r in data.get("intermediarios", []) if r.get("cedula")}
            _ASESORES_CACHE = {"comerciales": comerciales, "intermediarios": intermediarios, "loaded": True}
        else:
            _ASESORES_CACHE = {"comerciales": {}, "intermediarios": {}, "loaded": False}
    except Exception:
        _ASESORES_CACHE = {"comerciales": {}, "intermediarios": {}, "loaded": False}
    return _ASESORES_CACHE


def _validate_asesor_en_tabla(cedula: str, codigo_intermediario: str) -> bool:
    if not cedula:
        return True
    asesores = _load_asesores_colmena()
    if not asesores.get("loaded"):
        return True
    cedula_clean = only_digits(cedula)
    if codigo_intermediario in {"1", "01"}:
        return cedula_clean in asesores.get("comerciales", {})
    elif codigo_intermediario in {"3", "03"}:
        return cedula_clean in asesores.get("intermediarios", {})
    return True


def load_case(case_id: str) -> Dict[str, Any]:
    metadata_path = get_case_metadata_path(case_id)
    if not metadata_path.exists():
        raise FileNotFoundError(case_id)
    return json.loads(metadata_path.read_text(encoding="utf-8"))


def _normalize_case_payload(case_payload: Dict[str, Any]) -> Dict[str, Any]:
    analysis = case_payload.get("analysis") or {}
    workflow = analysis.get("workflow_run") or {}
    steps = workflow.get("steps")
    if isinstance(steps, list):
        workflow["timeline"] = list(steps)
    workflow_status = normalize_haystack(workflow.get("status"))
    if workflow_status == "completed":
        case_payload["status"] = "completed"
    elif workflow_status.startswith("stopped_") and not case_payload.get("status"):
        case_payload["status"] = "analyzed"
    if workflow:
        analysis["workflow_run"] = workflow
        case_payload["analysis"] = analysis
    return case_payload


def save_case(case_payload: Dict[str, Any]) -> Dict[str, Any]:
    case_payload = _normalize_case_payload(case_payload)
    case_id = str(case_payload["id"])
    case_dir = get_case_dir(case_id)
    case_dir.mkdir(parents=True, exist_ok=True)
    get_case_metadata_path(case_id).write_text(
        json.dumps(case_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return case_payload


def save_manual_review(case_id: str, kind: str, filename: str, verdict: str, expected_type: str = "", comisiones: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    payload = load_case(case_id)
    analysis = payload.setdefault("analysis", {}) or {}
    if payload.get("analysis") is None:
        payload["analysis"] = analysis
    review_store = analysis.setdefault("manual_review", {})

    # Cuando el operador corrige una clasificacion, RAG aprende
    if normalize_haystack(kind) != "comisiones" and normalize_haystack(verdict) == "no" and expected_type:
        try:
            payload_tmp = load_case(case_id)
            docs_tmp = (payload_tmp.get("analysis") or {}).get("documents") or []
            doc_tmp = next((d for d in docs_tmp if d.get("filename") == filename), None)
            if doc_tmp:
                ocr_tmp = str(doc_tmp.get("ocr_text") or doc_tmp.get("text_preview") or "")
                code_tmp = DOC_TYPE_TO_PRIMARY_CODE.get(normalize_haystack(expected_type).replace(" ", "_"), 99)
                _rag_index_document(case_id, filename, ocr_tmp, normalize_haystack(expected_type).replace(" ", "_"), code_tmp)
                import logging as _logging; _logging.getLogger("afi.rag").info("RAG aprendio correccion: %s -> %s", filename, expected_type)
                review_store["rag_aprendio"] = True
                review_store["rag_mensaje"] = f"Gracias. RAG ha aprendido que este documento es '{expected_type}'. Lo recordaré para futuros contratos similares."
        except Exception as _rag_exc:
            logger.debug("RAG learn error: %s", _rag_exc)

    # Corrección manual de comisiones
    if normalize_haystack(kind) == "comisiones" and comisiones is not None:
        comisiones_store = review_store.setdefault("comisiones", {})
        comisiones_store[str(filename)] = [
            {
                "codigo": only_digits(str(c.get("codigo") or "1")),
                "cedula": only_digits(str(c.get("cedula") or "")),
                "porcentaje": str(c.get("porcentaje") or "100"),
            }
            for c in comisiones if c.get("cedula")
        ]
        payload["updated_at"] = utc_now()
        save_case(payload)
        return review_store

    bucket_name = "xlsx" if normalize_haystack(kind) == "xlsx" else "documents"
    bucket = review_store.setdefault(bucket_name, {})
    normalized_expected_type = normalize_haystack(expected_type).replace(" ", "_")
    if normalized_expected_type not in DOC_TYPE_LABELS and normalized_expected_type != "xlsx" and not normalized_expected_type.startswith("anexo_sedes"):
        normalized_expected_type = ""
    bucket[str(filename)] = {
        "kind": bucket_name,
        "filename": str(filename),
        "verdict": "si" if normalize_haystack(verdict) == "si" else "no",
        "expected_type": normalized_expected_type,
        "expected_code": DOC_TYPE_TO_PRIMARY_CODE.get(normalized_expected_type) if normalized_expected_type else None,
        "updated_at": utc_now(),
    }
    payload["updated_at"] = utc_now()
    save_case(payload)
    _refresh_learning_artifacts()
    return review_store


def _ensure_document_workspace(payload: Dict[str, Any]) -> Dict[str, Any]:
    analysis = payload.setdefault("analysis", {}) or {}
    if payload.get("analysis") is None:
        payload["analysis"] = analysis
    workspace = analysis.setdefault("document_workspace", {})
    workspace.setdefault("order", [])
    workspace.setdefault("removed_files", [])
    return workspace


def _sync_document_workspace(payload: Dict[str, Any]) -> Dict[str, Any]:
    workspace = _ensure_document_workspace(payload)
    available = [str(item.get("filename") or "").strip() for item in (payload.get("files") or []) if str(item.get("filename") or "").strip()]
    order = [item for item in (workspace.get("order") or []) if item in available]
    seen = set(order)
    for filename in available:
        if filename not in seen:
            order.append(filename)
            seen.add(filename)
    workspace["order"] = order
    removed = []
    seen_removed = set()
    for filename in (workspace.get("removed_files") or []):
        name = str(filename or "").strip()
        if not name or name not in available or name in seen_removed:
            continue
        removed.append(name)
        seen_removed.add(name)
    workspace["removed_files"] = removed
    return workspace


def save_document_workspace(case_id: str, action: str, filename: str = "", order: Optional[List[str]] = None) -> Dict[str, Any]:
    payload = load_case(case_id)
    workspace = _sync_document_workspace(payload)
    files = payload.setdefault("files", [])
    action_key = normalize_haystack(action).replace(" ", "_")
    filename = str(filename or "").strip()

    if action_key == "set_order":
        valid = {str(item.get("filename") or "").strip() for item in files}
        cleaned: List[str] = []
        seen = set()
        for item in order or []:
            name = str(item or "").strip()
            if not name or name not in valid or name in seen:
                continue
            cleaned.append(name)
            seen.add(name)
        workspace["order"] = cleaned
    elif action_key == "remove":
        if filename and filename not in workspace["removed_files"]:
            workspace["removed_files"].append(filename)
    elif action_key == "restore":
        workspace["removed_files"] = [item for item in (workspace.get("removed_files") or []) if item != filename]
    elif action_key == "duplicate":
        if not filename:
            raise ValueError("Debes indicar el archivo a duplicar.")
        source_path = get_case_file_path(case_id, filename)
        stem = source_path.stem
        suffix = source_path.suffix
        files_dir = source_path.parent
        counter = 1
        target = files_dir / f"{stem}__dup{counter}{suffix}"
        while target.exists():
            counter += 1
            target = files_dir / f"{stem}__dup{counter}{suffix}"
        shutil.copy2(source_path, target)

        source_meta = next((item for item in files if str(item.get("filename") or "") == filename), None) or {}
        duplicated_meta = {
            **source_meta,
            "filename": target.name,
            "stored_path": str(target),
            "size_bytes": target.stat().st_size,
        }
        files.append(duplicated_meta)

        analysis = payload.get("analysis") or {}
        documents = analysis.get("documents") or []
        for item in documents:
            if str(item.get("filename") or "") != filename:
                continue
            copied = json.loads(json.dumps(item, ensure_ascii=False))
            copied["filename"] = target.name
            documents.append(copied)
            break
        checklist = analysis.get("checklist") or {}
        for group in checklist.get("received_summary") or []:
            files_group = group.get("files") or []
            if filename in files_group and target.name not in files_group:
                files_group.append(target.name)
                group["count"] = len(files_group)
                break
        current_order = workspace.get("order") or []
        if filename in current_order:
            insert_at = current_order.index(filename) + 1
            current_order.insert(insert_at, target.name)
            workspace["order"] = current_order
    else:
        raise ValueError(f"Acción documental no soportada: {action}")

    _sync_document_workspace(payload)
    payload["updated_at"] = utc_now()
    save_case(payload)
    return payload


def export_manual_review_dataset() -> Dict[str, Any]:
    export_path = get_document_reviews_export_path()
    cases_root = get_cases_root()
    rows: List[Dict[str, Any]] = []
    reviewed_cases = set()

    for case_dir in sorted(cases_root.iterdir()):
        if not case_dir.is_dir():
            continue
        metadata_path = case_dir / "case.json"
        if not metadata_path.exists():
            continue
        try:
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        case_id = str(payload.get("id") or case_dir.name)
        analysis = payload.get("analysis") or {}
        manual_review = analysis.get("manual_review") or {}
        if not manual_review:
            continue

        xlsx_profile = (analysis.get("xlsx_profile") or {}).get("profile") or {}
        docs = analysis.get("documents") or []
        docs_by_filename = {str(doc.get("filename") or ""): doc for doc in docs}
        identifier = _document_owner_identifier(analysis.get("xlsx_profile") or {})
        case_label = str(payload.get("label") or case_id)

        for bucket_name, entries in (manual_review or {}).items():
            if not isinstance(entries, dict):
                continue
            for filename, review in entries.items():
                review = review or {}
                row: Dict[str, Any] = {
                    "case_id": case_id,
                    "case_label": case_label,
                    "identifier": identifier,
                    "review_bucket": bucket_name,
                    "filename": filename,
                    "review_verdict": review.get("verdict"),
                    "expected_type": review.get("expected_type"),
                    "expected_code": review.get("expected_code"),
                    "reviewed_at": review.get("updated_at"),
                }

                if bucket_name == "xlsx":
                    row.update(
                        {
                            "predicted_type": "xlsx",
                            "predicted_code": -1,
                            "display_filename": filename,
                            "download_filename": filename,
                            "classification_confidence": 1,
                            "ocr_quality_score": None,
                            "field_confidence": {},
                            "key_fields": {
                                "nit": xlsx_profile.get("nit", ""),
                                "documento": xlsx_profile.get("documento", ""),
                                "empresa": xlsx_profile.get("empresa", ""),
                                "trabajadores": xlsx_profile.get("numero_trabajadores", ""),
                                "sedes": xlsx_profile.get("numero_sedes", ""),
                                "nomina_total": xlsx_profile.get("nomina_total", ""),
                            },
                            "signals_detected": ["xlsx_profile_loaded"],
                            "code_source": "xlsx_profile",
                            "text_preview": "",
                        }
                    )
                else:
                    doc = docs_by_filename.get(str(filename)) or {}
                    row.update(
                        {
                            "predicted_type": doc.get("document_type"),
                            "predicted_code": doc.get("legacy_code"),
                            "display_filename": doc.get("display_filename") or filename,
                            "download_filename": doc.get("download_filename") or doc.get("display_filename") or filename,
                            "classification_confidence": doc.get("classification_confidence"),
                            "ocr_quality_score": doc.get("ocr_quality_score"),
                            "field_confidence": doc.get("field_confidence") or {},
                            "key_fields": doc.get("key_fields") or {},
                            "signals_detected": doc.get("signals_detected") or [],
                            "code_source": doc.get("code_source"),
                            "text_preview": str(doc.get("text_preview") or doc.get("ocr_text") or "")[:800],
                        }
                    )

                rows.append(row)
                reviewed_cases.add(case_id)

    lines = [json.dumps(row, ensure_ascii=False) for row in rows]
    export_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return {
        "path": str(export_path),
        "rows": len(rows),
        "cases": len(reviewed_cases),
        "updated_at": utc_now(),
    }


def _case_updated_at_sort_value(payload: Dict[str, Any]) -> str:
    return str(payload.get("updated_at") or payload.get("created_at") or "")


def _case_entity_key(payload: Dict[str, Any]) -> tuple[str, str]:
    analysis = payload.get("analysis") or {}
    profile = ((analysis.get("xlsx_profile") or {}).get("profile") or {})
    nit = only_digits(profile.get("nit") or "")
    documento = only_digits(profile.get("documento") or "")
    empresa = normalize_haystack(profile.get("empresa") or payload.get("label") or "")
    return (nit or documento or empresa or payload.get("id") or "", empresa or documento or nit or payload.get("id") or "")


_LIST_CASES_CACHE_TTL_SECONDS = 3.0
_LIST_CASES_CACHE: Dict[bool, tuple[float, List[Dict[str, Any]]]] = {}


def _clone_case_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [dict(item) for item in rows]


def list_cases(include_all: bool = False) -> List[Dict[str, Any]]:
    cache_key = bool(include_all)
    cached = _LIST_CASES_CACHE.get(cache_key)
    now = time.monotonic()
    if cached and (now - cached[0]) <= _LIST_CASES_CACHE_TTL_SECONDS:
        return _clone_case_rows(cached[1])

    rows: List[Dict[str, Any]] = []
    for path in sorted(get_cases_root().glob("*/case.json"), reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            rows.append(payload)
        except Exception:
            continue
    rows.sort(key=_case_updated_at_sort_value, reverse=True)
    if include_all:
        _LIST_CASES_CACHE[cache_key] = (now, rows)
        return _clone_case_rows(rows)
    latest_by_entity: Dict[tuple[str, str], Dict[str, Any]] = {}
    for payload in rows:
        key = _case_entity_key(payload)
        current = latest_by_entity.get(key)
        if current is None or _case_updated_at_sort_value(payload) >= _case_updated_at_sort_value(current):
            latest_by_entity[key] = payload
    result = sorted(latest_by_entity.values(), key=_case_updated_at_sort_value, reverse=True)
    _LIST_CASES_CACHE[cache_key] = (now, result)
    return _clone_case_rows(result)


def get_case_file_path(case_id: str, filename: str) -> Path:
    case_dir = get_case_dir(case_id) / "files"
    target = case_dir / Path(filename).name
    if not target.exists():
        raise FileNotFoundError(filename)
    return target


def search_cases(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    needle = normalize_haystack(query)
    needle_company = _normalize_company_compare(query)
    query_tokens: List[str] = []
    for token in needle.split():
        if len(token) < 3:
            continue
        query_tokens.append(token)
        if token.endswith("s") and len(token) >= 5:
            query_tokens.append(token[:-1])
    results: List[Dict[str, Any]] = []
    for payload in list_cases(include_all=True):
        analysis = payload.get("analysis") or {}
        profile = (analysis.get("xlsx_profile") or {}).get("profile") or {}
        docs = analysis.get("documents") or []
        workflow = analysis.get("workflow_run") or {}
        case_haystack = " ".join(
            [
                payload.get("label", ""),
                payload.get("lote_usuario", ""),
                profile.get("empresa", ""),
                profile.get("nombre", ""),
                profile.get("documento", ""),
                profile.get("nit", ""),
                profile.get("tipo_afiliado", ""),
                profile.get("lote_usuario", ""),
            ]
        )
        case_norm = normalize_haystack(case_haystack)
        company_norm = _normalize_company_compare(profile.get("empresa", "") or payload.get("label", ""))
        score = 0
        if needle and needle in case_norm:
            score += 10
        if needle_company and company_norm:
            if needle_company == company_norm:
                score += 40
            elif needle_company in company_norm or company_norm in needle_company:
                score += 24
        score += fuzzy_text_score(query, profile.get("empresa", ""))
        score += fuzzy_text_score(query, payload.get("label", "")) // 2
        score += fuzzy_text_score(query, profile.get("nombre", "")) // 2
        for token in query_tokens:
            if token in case_norm:
                score += 4
        if profile.get("empresa"):
            score += 3
        if profile.get("nombre"):
            score += 2
        if profile.get("documento"):
            score += 2
        if profile.get("nit"):
            score += 2
        if not profile.get("empresa"):
            score -= 6
        if not _looks_like_person_name(profile.get("nombre", "")):
            score -= 3
        if profile.get("empresa") and not _looks_like_company_name(profile.get("empresa", "")):
            score -= 14
        if len(docs) < 2:
            score -= 18
        if not docs and not profile.get("empresa") and not profile.get("documento"):
            score -= 25
        if not profile.get("empresa") and not profile.get("nombre"):
            score -= 20
        payload_status = normalize_haystack(payload.get("status"))
        workflow_status = normalize_haystack(workflow.get("status"))
        if payload_status == "completed":
            score += 6
        elif payload_status == "analyzed":
            score += 3
        elif payload_status == "failed":
            score -= 4
        elif payload_status in {"queued", "processing"}:
            score -= 2
        if workflow_status == "completed":
            score += 4
        elif workflow_status.startswith("stopped_"):
            score += 1
        if normalize_haystack(payload.get("label", "")).startswith("case-"):
            score -= 1
        updated_at = str(payload.get("updated_at") or "")
        if updated_at.startswith("2026-03-16T13:"):
            score += 2
        matched_documents: List[Dict[str, Any]] = []
        entity_document_hint = only_digits(profile.get("documento", ""))
        for doc in docs:
            fields = doc.get("fields") or {}
            preview = str(doc.get("text_preview") or "")
            raw_doc_person_name = _normalize_person_name(
                fields.get("representative_name", "") or _extract_name_from_cedula_text(preview)
            )
            doc_person_name = raw_doc_person_name if _looks_like_person_name(raw_doc_person_name) else ""
            if not entity_document_hint and doc.get("document_type") in {"cedula", "formulario_afiliacion", "anexo_sedes", "carta", "constancia_afiliacion"}:
                entity_document_hint = only_digits(fields.get("representative_document", "") or fields.get("document_number", ""))
            doc_haystack = normalize_haystack(
                " ".join(
                    [
                        doc.get("filename", ""),
                        doc.get("document_type", ""),
                        preview,
                        str(fields.get("company_name") or ""),
                        doc_person_name,
                        str(fields.get("document_number") or ""),
                        str(fields.get("nit") or ""),
                    ]
                )
            )
            doc_score = 0
            if needle and needle in doc_haystack:
                doc_score += 8
            for token in query_tokens:
                if token in doc_haystack:
                    doc_score += 3
            if doc_score:
                matched_documents.append(
                    {
                        "filename": doc.get("filename"),
                        "document_type": doc.get("document_type"),
                        "person_name": doc_person_name,
                        "score": doc_score,
                        "snippet": preview[:280],
                    }
                )
                score += doc_score
        if score <= 0:
            continue
        matched_documents.sort(key=lambda item: item["score"], reverse=True)
        results.append(
            {
                "case_id": payload.get("id"),
                "label": payload.get("label"),
                "status": payload.get("status"),
                "score": score,
                "updated_at": payload.get("updated_at") or "",
                "profile": profile,
                "lote_usuario": payload.get("lote_usuario") or profile.get("lote_usuario") or "",
                "entity_document_hint": entity_document_hint,
                "doc_signature": tuple(
                    sorted(
                        f"{normalize_haystack(doc.get('filename', ''))}|{normalize_haystack(doc.get('document_type', ''))}"
                        for doc in docs
                    )
                ),
                "matched_documents": matched_documents[:8],
                "received_summary": ((analysis.get("checklist") or {}).get("received_summary") or [])[:20],
                "decision": analysis.get("decision") or {},
                "precheck": ((analysis.get("validacion_resumen") or {}).get("precheck") or {}),
                "executive_report": analysis.get("reporte_ejecutivo") or {},
            }
        )
    def _profile_quality(item: Dict[str, Any]) -> int:
        profile = item.get("profile") or {}
        quality = 0
        if _looks_like_company_name(profile.get("empresa", "")):
            quality += 6
        elif normalize_text(profile.get("empresa", "")):
            quality += 2
        if _looks_like_person_name(profile.get("nombre", "")):
            quality += 3
        if only_digits(profile.get("nit", "")):
            quality += 3
        if only_digits(profile.get("documento", "")) or only_digits(item.get("entity_document_hint", "")):
            quality += 3
        if item.get("received_summary"):
            quality += 2
        if item.get("matched_documents"):
            quality += 1
        if not normalize_text(profile.get("empresa", "")):
            quality -= 8
        if not only_digits(profile.get("nit", "")) and not only_digits(profile.get("documento", "")):
            quality -= 4
        return quality

    results.sort(
        key=lambda item: (
            int(item.get("score") or 0),
            _profile_quality(item),
            1 if (item.get("precheck") or {}).get("approved") else 0,
            1 if ((item.get("decision") or {}).get("recommended_status") == "aprobable") else 0,
            str(item.get("updated_at") or ""),
        ),
        reverse=True,
    )
    deduped: List[Dict[str, Any]] = []
    seen = set()
    seen_doc_signatures = set()
    seen_documents = set()
    for item in results:
        doc_signature = tuple(item.get("doc_signature") or ())
        dedupe_key = (
            only_digits((item.get("profile") or {}).get("nit") or ""),
            only_digits((item.get("profile") or {}).get("documento") or item.get("entity_document_hint") or ""),
        )
        document_key = normalize_haystack((item.get("profile") or {}).get("documento") or item.get("entity_document_hint") or "")
        company_value = (item.get("profile") or {}).get("empresa") or ""
        name_value = (item.get("profile") or {}).get("nombre") or ""
        strong_profile = _looks_like_company_name(company_value) and _looks_like_person_name(name_value)
        weak_profile = not strong_profile
        if doc_signature and doc_signature in seen_doc_signatures and weak_profile:
            continue
        if document_key and document_key in seen_documents and weak_profile:
            continue
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        if doc_signature:
            seen_doc_signatures.add(doc_signature)
        if document_key:
            seen_documents.add(document_key)
        deduped.append(item)
        if len(deduped) >= limit:
            break
    return deduped


def rebuild_document_registry() -> Dict[str, Any]:
    registry: List[Dict[str, Any]] = []
    for payload in list_cases():
        analysis = payload.get("analysis") or {}
        profile = (analysis.get("xlsx_profile") or {}).get("profile") or {}
        file_map = {item.get("filename"): item for item in payload.get("files") or []}
        for doc in analysis.get("documents") or []:
            fields = doc.get("fields") or {}
            filename = doc.get("filename") or ""
            file_entry = file_map.get(filename) or {}
            ocr_text = normalize_text(doc.get("ocr_text", "") or doc.get("text_preview", ""))
            doc_type = str(doc.get("document_type") or "")
            candidate_person_name = _normalize_person_name(
                fields.get("representative_name", "") or _extract_name_from_cedula_text(ocr_text)
            )
            person_name_source = "document"
            if not _looks_like_person_name(candidate_person_name) and doc_type not in {"entrega_documentos"}:
                candidate_person_name = _normalize_person_name(profile.get("nombre", ""))
                person_name_source = "profile"
            derived_person_name = candidate_person_name if _looks_like_person_name(candidate_person_name) else ""
            explicit_person_document = only_digits(fields.get("representative_document", "") or fields.get("document_number", ""))
            fallback_person_document = only_digits(profile.get("documento", ""))
            identity_document_types = {"cedula", "formulario_afiliacion", "anexo_sedes", "carta", "constancia_afiliacion"}
            if (
                doc_type == "cedula"
                and fallback_person_document
                and explicit_person_document
                and (
                    len(explicit_person_document) < 7
                    or explicit_person_document.startswith("0500")
                    or not _numeric_similarity_match(explicit_person_document, fallback_person_document)
                )
            ):
                explicit_person_document = fallback_person_document
            if explicit_person_document:
                derived_person_document = explicit_person_document
                person_document_source = "document"
            elif doc_type in identity_document_types and fallback_person_document:
                derived_person_document = fallback_person_document
                person_document_source = "profile"
            else:
                derived_person_document = ""
                person_document_source = ""
            registry.append(
                {
                    "case_id": payload.get("id"),
                    "label": payload.get("label"),
                    "status": payload.get("status"),
                    "filename": filename,
                    "stored_path": file_entry.get("stored_path", ""),
                    "document_type": doc_type,
                    "legacy_code": doc.get("legacy_code"),
                    "used_ocr": bool(doc.get("used_ocr")),
                    "company": _clean_company_name(profile.get("empresa", "") or fields.get("company_name", "")),
                    "nit": only_digits(profile.get("nit", "") or fields.get("nit", "")),
                    "person_name": derived_person_name,
                    "person_name_source": person_name_source if derived_person_name else "",
                    "person_document": derived_person_document,
                    "person_document_source": person_document_source,
                    "document_number": only_digits(fields.get("document_number", "")),
                    "ocr_text": ocr_text,
                    "text_preview": normalize_text(doc.get("text_preview", "")),
                }
            )
    path = get_document_registry_path()
    preferred_by_doc: Dict[tuple, int] = {}
    filtered_registry: List[Dict[str, Any]] = []
    for entry in registry:
        key = (
            normalize_haystack(entry.get("filename", "")),
            normalize_haystack(entry.get("document_type", "")),
            only_digits(entry.get("person_document", "")) or only_digits(entry.get("document_number", "")),
        )
        quality = 0
        if entry.get("company") and _looks_like_company_name(entry.get("company", "")):
            quality += 10
        if entry.get("person_name") and _looks_like_person_name(entry.get("person_name", "")):
            quality += 6
        if only_digits(entry.get("person_document", "")):
            quality += 4
        if str(entry.get("label", "")).startswith("case-"):
            quality += 1
        previous = preferred_by_doc.get(key)
        if previous is None or quality > previous:
            preferred_by_doc[key] = quality
    for entry in registry:
        key = (
            normalize_haystack(entry.get("filename", "")),
            normalize_haystack(entry.get("document_type", "")),
            only_digits(entry.get("person_document", "")) or only_digits(entry.get("document_number", "")),
        )
        quality = 0
        if entry.get("company") and _looks_like_company_name(entry.get("company", "")):
            quality += 10
        if entry.get("person_name") and _looks_like_person_name(entry.get("person_name", "")):
            quality += 6
        if only_digits(entry.get("person_document", "")):
            quality += 4
        if str(entry.get("label", "")).startswith("case-"):
            quality += 1
        if quality < preferred_by_doc.get(key, quality):
            continue
        filtered_registry.append(entry)
    path.write_text(json.dumps(filtered_registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"documents": len(filtered_registry), "documents_raw": len(registry), "path": str(path)}


def load_document_registry() -> List[Dict[str, Any]]:
    path = get_document_registry_path()
    if not path.exists():
        rebuild_document_registry()
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


def search_document_registry(query: str, limit: int = 12) -> List[Dict[str, Any]]:
    needle = normalize_haystack(query)
    query_digits = only_digits(query)
    generic_query_terms = {
        "cedula",
        "cédula",
        "documento",
        "documentos",
        "representante",
        "representangte",
        "representate",
        "representaante",
        "rut",
        "camara",
        "cámara",
        "formulario",
        "pdf",
        "soporte",
        "sede",
        "entrega",
    }
    tokens: List[str] = []
    for token in needle.split():
        if len(token) < 3:
            continue
        tokens.append(token)
        if token.endswith("s") and len(token) >= 5:
            tokens.append(token[:-1])
    meaningful_tokens = [token for token in tokens if token not in generic_query_terms]
    results: List[Dict[str, Any]] = []
    for item in load_document_registry():
        ocr_text = normalize_haystack(item.get("ocr_text", ""))
        company = normalize_haystack(item.get("company", ""))
        person_name = normalize_haystack(item.get("person_name", ""))
        person_document = only_digits(item.get("person_document", ""))
        document_number = only_digits(item.get("document_number", ""))
        document_type = normalize_haystack(item.get("document_type", ""))
        label = normalize_haystack(item.get("label", ""))
        person_name_source = str(item.get("person_name_source") or "")
        person_document_source = str(item.get("person_document_source") or "")
        haystack = " ".join([label, company, person_name, item.get("nit", ""), person_document, document_number, document_type, ocr_text]).strip()
        score = 0
        meaningful_hits = 0
        if needle and needle in haystack:
            score += 12
        for token in tokens:
            if token in haystack:
                score += 4
            if token and token in company:
                score += 3
            if token and token in person_name:
                score += 4
            if token and token in document_type:
                score += 3
            if token and token in ocr_text:
                score += 1
        for token in meaningful_tokens:
            if token in person_name:
                score += 10
                meaningful_hits += 1
            elif token in company:
                score += 8
                meaningful_hits += 1
            elif token in label:
                score += 7
                meaningful_hits += 1
            elif token in haystack:
                score += 5
                meaningful_hits += 1
            else:
                score -= 14
        if meaningful_tokens and meaningful_hits == 0 and not query_digits:
            continue
        if query_digits:
            if query_digits == person_document:
                score += 32
            elif query_digits == document_number:
                score += 24
            elif _numeric_similarity_match(query_digits, person_document):
                score += 20
            elif _numeric_similarity_match(query_digits, document_number):
                score += 14
        if item.get("document_type") == "cedula" and query_digits and (query_digits == person_document or _numeric_similarity_match(query_digits, person_document)):
            score += 10
        if item.get("document_type") == "cedula" and ("cedula de ciudadania" in ocr_text or "identificacion personal" in ocr_text):
            score += 18
        if item.get("document_type") == "camara_comercio" and "camara" in needle:
            score += 8
        if item.get("document_type") == "rut" and "rut" in needle:
            score += 8
        if item.get("document_type") == "entrega_documentos":
            score -= 6
        if person_document_source == "profile" and item.get("document_type") not in {"cedula", "formulario_afiliacion", "anexo_sedes", "carta", "constancia_afiliacion"}:
            score -= 10
        if person_name_source == "profile" and item.get("document_type") in {"entrega_documentos", "rut", "camara_comercio", "pdf"}:
            score -= 5
        if item.get("company"):
            score += 2
        else:
            score -= 10
        if item.get("company") and not _looks_like_company_name(item.get("company", "")):
            score -= 12
        if item.get("person_name"):
            score += 1
        else:
            score -= 2
        label_norm = normalize_haystack(item.get("label", ""))
        company_norm = normalize_haystack(item.get("company", ""))
        if "demo" in label_norm or "demo" in company_norm:
            score -= 8
        if label_norm.startswith("case-"):
            score -= 2
        if (not item.get("company")) and label_norm:
            score -= 10
        if item.get("document_type") == "formulario_afiliacion" and not item.get("company"):
            score -= 8
        if item.get("filename", "").lower().endswith(".txt"):
            score -= 4
        if item.get("used_ocr"):
            score += 1
        if score <= 0:
            continue
        enriched = dict(item)
        enriched["score"] = score
        results.append(enriched)
    results.sort(key=lambda item: item["score"], reverse=True)
    deduped: List[Dict[str, Any]] = []
    seen = set()
    for item in results:
        logical_filename = re.sub(r"(-\d+)(\.[a-z0-9]+)$", r"\2", Path(item.get("filename", "")).name.lower())
        dedupe_key = (
            only_digits(item.get("person_document", "")) or only_digits(item.get("document_number", "")),
            normalize_haystack(item.get("company", "")),
            normalize_haystack(item.get("document_type", "")),
            logical_filename,
        )
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        deduped.append(item)
        if len(deduped) >= limit:
            break
    return deduped


def create_case_record(label: str, source_files: List[Dict[str, Any]]) -> Dict[str, Any]:
    case_id = f"case-{uuid.uuid4().hex[:10]}"
    payload = {
        "id": case_id,
        "label": normalize_text(label) or case_id,
        "status": "uploaded",
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "files": source_files,
        "analysis": None,
    }
    return save_case(payload)


def _clean_company_name(value: str) -> str:
    text = normalize_text(value)
    if not text:
        return ""
    text = re.split(r"\b(?:nit|cc|numero|número|cps-f)\b", text, maxsplit=1, flags=re.IGNORECASE)[0]
    text = re.sub(r"\s+", " ", text).strip(" .,-")
    return text


def _normalize_company_compare(value: str) -> str:
    text = normalize_haystack(_clean_company_name(value))
    text = re.sub(r"\bs\s*\.\s*a\s*\.\s*s\s*\.?\b", "sas", text, flags=re.IGNORECASE)
    text = re.sub(r"\bs\s*\.\s*a\b", "sa", text, flags=re.IGNORECASE)
    text = re.sub(r"\bl\s*\.\s*t\s*\.\s*d\s*\.\s*a\s*\.?\b", "ltda", text, flags=re.IGNORECASE)
    # Eliminar sufijos legales adicionales que no cambian la identidad de la empresa
    text = re.sub(r"\b(bic|esal|esp|eu|zomac|sca|ips|ong|fundacion|asociacion|cooperativa)\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"[^a-z0-9]+", "", text)
    return text


def _normalize_company_strict(value: str) -> str:
    text = normalize_text(_clean_company_name(value))
    text = re.sub(r"\s+", " ", text).strip(" .,-")
    return text


def _looks_like_person_name(value: str) -> bool:
    text = normalize_text(value)
    if len(text) < 8:
        return False
    lowered = text.lower()
    blocked = [
        "en mora",
        "acuerdo de pago",
        "urbana",
        "codigo",
        "formulario",
        "número de documento",
        "numero de documento",
        "representante legal de colmena",
        "de participación",
        "de documento",
    ]
    if any(token in lowered for token in blocked):
        return False
    tokens = [token for token in text.split() if token]
    return len(tokens) >= 2


def _normalize_person_name(value: str) -> str:
    text = normalize_text(value)
    if not text:
        return ""
    text = re.sub(r"\bSEG\s+NDO\b", "SEGUNDO", text, flags=re.IGNORECASE)
    text = re.sub(r"\bSEG\s+NDA\b", "SEGUNDA", text, flags=re.IGNORECASE)
    text = re.sub(r"\bPOLICARPO\s+SEG\s+NDO\b", "POLICARPO SEGUNDO", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip(" .,-")
    return text


def _looks_like_company_name(value: str) -> bool:
    text = _clean_company_name(value)
    if len(text) < 5:
        return False
    lowered = text.lower()
    blocked = [
        "cedula de ciudadania",
        "del empleador",
        "numero de documento",
        "número de documento",
        "representante legal",
        "fecha inicio",
        "estado de cuenta",
        "lugar de nacimiento",
        "fecha y lugar",
    ]
    if any(token in lowered for token in blocked):
        return False
    return True


def _looks_like_cedula_document(name_txt: str, haystack: str) -> bool:
    positive_markers = [
        "cedula de ciudadania",
        "identificacion personal",
        "registraduria nacional",
        "apellidos",
        "nombres",
        "lugar de nacimiento",
        "fecha y lugar de expedicion",
        "sexo",
    ]
    negative_markers = [
        "señores arl",
        "representante legal de la empresa",
        "constancia de afiliacion",
        "direccion de aseguramiento",
        "numero de identificacion tributaria",
        "tarjeta profesional",
        "revisor fiscal",
        "camara de comercio",
        "certificado de existencia",
        "formulario de afiliacion",
        "riesgos laborales",
        "planilla resumen",
        "resumen general de pago en linea",
        "resumen general de pago en línea",
        "estado de cuenta",
        "beneficiario final",
        "beneficiarios finales",
        "participacion directa o indirecta mayor al 5",
        "participación directa o indirecta mayor al 5",
        "informacion de la compania",
        "información de la compañía",
        "conformacion de la sociedad",
        "conformación de la sociedad",
        "accionista",
    ]
    positive_hits = sum(1 for marker in positive_markers if marker in haystack)
    fuzzy_positive_patterns = [
        r"registrad\w+\s+nacional",
        r"indice\s+derech\w*",
        r"fecha\s+y\s+lugar\s+de\s+expedicion",
        r"fecha\s+y\s+lug\w*\s+expedicion",
        r"lugar\s+de\s+nac\w+",
        r"\brh\b",
        r"\bestatura\b",
        r"lugar\s+de\s+nacimiento",
    ]
    negative_hits = sum(1 for marker in negative_markers if marker in haystack)
    positive_hits += sum(1 for pattern in fuzzy_positive_patterns if re.search(pattern, haystack))
    if any(token in name_txt for token in ["cedula", "cc_"]):
        positive_hits += 2
    if "cedula de ciudadania" in haystack or "identificacion personal" in haystack:
        positive_hits += 2
    if "fecha y lug" in haystack and "expedicion" in haystack:
        positive_hits += 2
    if "lugar de nac" in haystack:
        positive_hits += 2
    if re.search(r"\b\d{7,10}\b", haystack):
        positive_hits += 1
    if negative_hits >= 2 and positive_hits < 5:
        return False
    return positive_hits >= 4 and negative_hits <= 1


def _looks_like_camara_document(haystack: str) -> bool:
    positive_markers = [
        "camara de comercio",
        "certificado de existencia y representacion legal",
        "matricula mercantil",
        "codigo de verificacion",
        "fecha expedicion",
        "sede virtual",
        "certificadoselectronicos",
        "recibo no.",
    ]
    negative_markers = [
        "señores arl",
        "senores arl",
        "respetados señores",
        "respetados senores",
        "por medio de la presente",
        "constancia de afiliacion",
        "planilla resumen",
        "estado de cuenta",
        "autorizacion de tratamiento",
    ]
    positive_hits = sum(1 for marker in positive_markers if marker in haystack)
    negative_hits = sum(1 for marker in negative_markers if marker in haystack)
    return positive_hits >= 2 and negative_hits == 0


def _looks_like_entrega_documentos(haystack: str) -> bool:
    positive_markers = [
        "comprobante entrega de documentos",
        "pago de reconocimiento variable integral",
        "documentos anexos a la afiliacion",
        "datos de la afiliacion",
        "nro. de contrato",
    ]
    return sum(1 for marker in positive_markers if marker in haystack) >= 2


def _looks_like_carta_document(haystack: str) -> bool:
    positive_markers = [
        "señores arl",
        "senores arl",
        "senores positiva",
        "señores positiva",
        "respetados señores",
        "respetados senores",
        "por medio de la presente",
        "representante legal de la empresa",
        "me permito informarle",
        "solicitud de desafiliacion",
        "solicitud de desafiliación",
        "se adjuntan los siguientes documentos",
        "agradeciendo su colaboracion",
        "agradeciendo su colaboración",
        "piensalo bien",
        "piénsalo bien",
        "servicioalcliente@positiva.com.co",
        "se recibe su solicitud de traslado",
        "ha decidido nombrar",
        "nuevo intermediario en riesgos laborales",
        "de conformidad con lo dispuesto en el paragrafo 5 del articulo 11 de la ley 1562 de 2012",
        "de conformidad con lo dispuesto en el parágrafo 5 del artículo 11 de la ley 1562 de 2012",
        "desvinculacion de empresa",
        "desvinculación de empresa",
        "adjunto hago llegar cartas y soportes para desafiliar",
        "ultimas planillas de pago de seguridad social",
        "últimas planillas de pago de seguridad social",
    ]
    return sum(1 for marker in positive_markers if marker in haystack) >= 2


def _looks_like_constancia_afiliacion(haystack: str) -> bool:
    positive_markers = [
        "constancia de afiliacion",
        "certificado de afiliacion positiva",
        "certificado de afiliación positiva",
        "hace constar",
        "direccion de aseguramiento",
        "estado numero de centros de trabajo",
        "codigo unico de generacion",
        "reporte consulta no.",
        "listas propias",
        "listas informativas",
        "risk consulting global group certifica",
        "consulta de procesos en la rama judicial",
        "codigo de radicado asignado",
        "peticion a arl ha sido enviada",
        "peticion a arl",
        "transaccion financiera exitosa",
        "transaccion exitosa",
        "ley de transparencia",
    ]
    hits = sum(1 for marker in positive_markers if marker in haystack)
    return hits >= 2 or any(
        marker in haystack
        for marker in [
            "codigo de radicado asignado",
            "reporte consulta no.",
            "consulta de procesos en la rama judicial",
            "risk consulting global group certifica",
            "ley de transparencia",
        ]
    )


def _looks_like_rut_document(haystack: str) -> bool:
    positive_markers = [
        "registro unico tributario",
        "registro único tributario",
        "direccion de impuestos y aduanas",
        "dirección de impuestos y aduanas",
        "espacio reservado para la dian",
        "numero de formulario",
        "número de formulario",
        "direccion seccional",
        "dirección seccional",
        "buzon electronico",
        "buzón electrónico",
        "numero de identificacion tributaria",
        "número de identificación tributaria",
        "95. numero de identificacion tributaria",
        "95. número de identificación tributaria",
        "matriz o controlante",
        "espacio reservado para la dian",
        "entidades o institutos de derecho publico",
        "entidades o institutos de derecho público",
        "numero de formulario",
        "número de formulario",
    ]
    negative_markers = [
        "outlook",
        "desafiliacion por traslado",
        "desafiliación por traslado",
        "traslado voluntario de arl",
        "se recibe su solicitud de traslado",
        "piensalo bien",
        "positiva.gov.co",
        "hasta el viernes",
        "correo electronico",
        "correo electrónico",
        "solicitud de desafiliacion",
        "solicitud de desafiliación",
        "se adjuntan los siguientes documentos",
        "agradeciendo su colaboracion",
        "agradeciendo su colaboración",
        "se recibe su solicitud de traslado",
    ]
    hits = sum(1 for marker in positive_markers if marker in haystack)
    negative_hits = sum(1 for marker in negative_markers if marker in haystack)
    return hits >= 2 and negative_hits == 0


def _calibration_match_score(doc: Dict[str, Any], rule: Dict[str, Any], haystack: str) -> int:
    score = 0
    signal_set = {normalize_text(signal) for signal in (doc.get("signals_detected") or []) if normalize_text(signal)}
    for hint in rule.get("signal_hints") or []:
        if normalize_text(hint) in signal_set:
            score += 1
    for hint in rule.get("text_hints") or []:
        if normalize_haystack(hint) and normalize_haystack(hint) in haystack:
            score += 2
    if float(doc.get("classification_confidence") or 0) <= 0.5:
        score += 1
    return score


def _apply_document_learning_calibration(docs: List[Dict[str, Any]]) -> None:
    calibration = _load_document_calibration()
    remaps = calibration.get("remaps") or []
    if not remaps:
        return

    remaps_by_from: Dict[str, List[Dict[str, Any]]] = {}
    for rule in remaps:
        from_type = str(rule.get("from_type") or "")
        to_type = str(rule.get("to_type") or "")
        if not from_type or not to_type:
            continue
        remaps_by_from.setdefault(from_type, []).append(rule)

    for doc in docs:
        current_type = str(doc.get("document_type") or "")
        if current_type not in remaps_by_from:
            continue
        haystack = normalize_haystack(
            f"{doc.get('filename', '')} {doc.get('ocr_text', '') or doc.get('text_preview', '')}"
        )
        if not haystack:
            continue

        for rule in remaps_by_from[current_type]:
            target_type = str(rule.get("to_type") or "")
            score = _calibration_match_score(doc, rule, haystack)
            if score < 3:
                continue

            if target_type == "cedula":
                if not any(
                    marker in haystack
                    for marker in [
                        "lugar de nacimiento",
                        "fecha y lugar de expedicion",
                        "fecha y lugar de expedición",
                        "indice derecho",
                        "índice derecho",
                        "registrador nacional",
                    ]
                ):
                    continue
            elif target_type == "soporte_ingresos":
                if not any(
                    marker in haystack
                    for marker in [
                        "planilla resumen",
                        "resumen general de pago",
                        "resumen de pago a salud",
                        "informe consolidado de pagos por empresas",
                        "valor a pagar",
                        "datos generales del aportante",
                        "ibc salud",
                        "ibc pension",
                        "ibc pensión",
                    ]
                ):
                    continue
            elif target_type == "carta":
                if not any(
                    marker in haystack
                    for marker in [
                        "se adjuntan los siguientes documentos",
                        "cordialmente",
                        "representante legal",
                        "por medio de la presente",
                        "desvinculacion de empresa",
                        "desvinculación de empresa",
                        "agradeciendo su colaboracion",
                        "agradeciendo su colaboración",
                    ]
                ):
                    continue

            doc["document_type"] = target_type
            doc["legacy_code"] = DOC_TYPE_TO_PRIMARY_CODE.get(target_type, doc.get("legacy_code"))
            doc["legacy_label"] = LEGACY_CODE_TO_TYPE.get(int(doc["legacy_code"]), "")
            doc["code_source"] = f"learned_calibration_{current_type}_to_{target_type}"
            signals = list(doc.get("signals_detected") or [])
            signals.append(f"learned:{current_type}->{target_type}")
            doc["signals_detected"] = signals
            break


def _looks_like_autorizacion_document(haystack: str) -> bool:
    positive_markers = [
        "autorizacion de tratamiento de datos",
        "autorización de tratamiento de datos",
        "tratamiento de los datos personales",
        "tratamiento de datos personales",
        "acuerdo de transmision de datos personales",
        "acuerdo de transmisión de datos personales",
        "finalidades que han sido autorizadas",
        "responsable sobre la informacion",
        "responsable sobre la información",
        "encargado",
        "clausula sexta",
        "cláusula sexta",
        "clausula septima",
        "cláusula séptima",
        "remitir a traves de los canales",
        "remitir a través de los canales",
        "declaro que he sido informado que",
        "recopilar, analizar, consultar, validar y procesar",
        "fundacion grupo social",
        "fundación grupo social",
        "formato solicitud de autorizacion comercial para cambio de vigencias",
        "formato solicitud de autorización comercial para cambio de vigencias",
        "autorizacion comercial para cambio de vigencias de trabajadores",
        "autorización comercial para cambio de vigencias de trabajadores",
        "cargue retroactivo",
        "novedades retroactivas",
        "fecha aprobacion",
        "fecha aprobación",
    ]
    return sum(1 for marker in positive_markers if marker in haystack) >= 2


def _looks_like_comision_document(haystack: str) -> bool:
    positive_markers = [
        "labor de intermediacion en riesgos laborales",
        "labor de intermediación en riesgos laborales",
        "ha designado a",
        "intermediacion en el ramo de riesgos laborales es voluntaria",
        "intermediación en el ramo de riesgos laborales es voluntaria",
        "paragrafo 5 del articulo 11 de la ley 1562 de 2012",
        "parágrafo 5 del artículo 11 de la ley 1562 de 2012",
    ]
    return sum(1 for marker in positive_markers if marker in haystack) >= 2


def _looks_like_beneficiario_final_document(haystack: str) -> bool:
    positive_markers = [
        "beneficiario final",
        "beneficiarios finales",
        "registro unico de beneficiarios finales",
        "registro único de beneficiarios finales",
        "participacion directa o indirecta mayor al 5",
        "participación directa o indirecta mayor al 5",
        "informacion de la compania",
        "información de la compañía",
        "conformacion de la sociedad",
        "conformación de la sociedad",
        "accionista",
        "representante legaladministrador",
    ]
    return sum(1 for marker in positive_markers if marker in haystack) >= 2


def _extract_page_number(filename: str) -> int:
    match = re.search(r"__p(\d+)\.pdf$", str(filename or ""), flags=re.IGNORECASE)
    if match:
        return int(match.group(1))
    stem = Path(str(filename or "")).stem
    return int(stem) if stem.isdigit() else -1


def _apply_document_classification_overrides(docs: List[Dict[str, Any]]) -> None:
    prefix_groups: Dict[str, List[Dict[str, Any]]] = {}
    for doc in docs:
        filename = str(doc.get("filename") or "")
        stem = Path(filename).stem
        if stem.isdigit():
            prefix = "__numeric_sequence__"
        else:
            prefix = filename.split("__p", 1)[0]
        prefix_groups.setdefault(prefix, []).append(doc)

    for group in prefix_groups.values():
        group.sort(key=lambda item: _extract_page_number(str(item.get("filename") or "")))

        for index, doc in enumerate(group):
            haystack = normalize_haystack(
                f"{doc.get('filename', '')} {doc.get('ocr_text', '') or doc.get('text_preview', '')}"
            )
            doc_type = str(doc.get("document_type") or "")

            if _looks_like_beneficiario_final_document(haystack):
                doc["document_type"] = "beneficiario_final"
                doc["legacy_code"] = 27
                doc["legacy_label"] = LEGACY_CODE_TO_TYPE.get(27, "")
                doc["code_source"] = "post_beneficiario_precise"
                continue

            if doc_type == "rut" and _looks_like_carta_document(haystack):
                doc["document_type"] = "carta"
                doc["legacy_code"] = 4
                doc["legacy_label"] = LEGACY_CODE_TO_TYPE.get(4, "")
                doc["code_source"] = "post_carta_from_rut"
                continue

            if doc_type == "pdf" and _looks_like_constancia_afiliacion(haystack):
                doc["document_type"] = "constancia_afiliacion"
                doc["legacy_code"] = 7
                doc["legacy_label"] = LEGACY_CODE_TO_TYPE.get(7, "")
                doc["code_source"] = "post_constancia_precise"
                continue

            if doc_type in {"pdf", "soporte_ingresos"} and _looks_like_autorizacion_document(haystack):
                doc["document_type"] = "autorizacion"
                doc["legacy_code"] = 98
                doc["legacy_label"] = LEGACY_CODE_TO_TYPE.get(98, "")
                doc["code_source"] = "post_autorizacion_precise"
                continue

            if doc_type == "pdf" and _looks_like_carta_document(haystack):
                doc["document_type"] = "carta"
                doc["legacy_code"] = 4
                doc["legacy_label"] = LEGACY_CODE_TO_TYPE.get(4, "")
                doc["code_source"] = "post_carta_from_pdf"
                continue

            if doc_type in {"pdf", "imagen"}:
                if (
                    ("lugar de nac" in haystack or re.search(r"lugar\s+de\s+n[a-z]{2,}", haystack))
                    and ("fecha y lug" in haystack or "expedicion" in haystack)
                ):
                    doc["document_type"] = "cedula"
                    doc["legacy_code"] = 6
                    doc["legacy_label"] = LEGACY_CODE_TO_TYPE.get(6, "")
                    doc["code_source"] = "post_cedula_identity_layout"
                    continue

                if _looks_like_cedula_document(normalize_haystack(doc.get("filename", "")), haystack):
                    doc["document_type"] = "cedula"
                    doc["legacy_code"] = 6
                    doc["legacy_label"] = LEGACY_CODE_TO_TYPE.get(6, "")
                    doc["code_source"] = "post_cedula_from_pdf"
                    continue

                if any(
                    marker in haystack
                    for marker in [
                        "informe consolidado de pagos por empresas",
                        "resumen de pago a salud",
                        "resumen general de pago en linea",
                        "resumen general de pago en línea",
                        "resumen general de pago en inea",
                        "aportes resumen general de pago en linea",
                        "aportes resumen general de pago en línea",
                        "aportes resumen general de pago en inea",
                    ]
                ):
                    doc["document_type"] = "soporte_ingresos"
                    doc["legacy_code"] = 11
                    doc["legacy_label"] = LEGACY_CODE_TO_TYPE.get(11, "")
                    doc["code_source"] = "post_planilla_resumen"
                    continue

                prev_doc = group[index - 1] if index > 0 else None
                next_doc = group[index + 1] if index + 1 < len(group) else None
                prev_anchor = next(
                    (
                        candidate
                        for candidate in reversed(group[:index])
                        if str(candidate.get("document_type") or "") not in {"pdf", "imagen"}
                    ),
                    None,
                )
                next_anchor = next(
                    (
                        candidate
                        for candidate in group[index + 1 :]
                        if str(candidate.get("document_type") or "") not in {"pdf", "imagen"}
                    ),
                    None,
                )
                text_preview = (doc.get("text_preview") or "").strip()
                looks_like_other_strong_type = any(
                    checker(haystack)
                    for checker in (
                        _looks_like_carta_document,
                        _looks_like_autorizacion_document,
                        _looks_like_constancia_afiliacion,
                        _looks_like_beneficiario_final_document,
                        _looks_like_camara_document,
                        _looks_like_rut_document,
                    )
                )
                if (
                    doc_type in {"pdf", "imagen"}
                    and not looks_like_other_strong_type
                    and prev_anchor
                    and next_anchor
                    and str(prev_anchor.get("document_type") or "") == "rut"
                    and str(next_anchor.get("document_type") or "") in {"soporte_ingresos", "autorizacion"}
                    and (
                        not text_preview
                        or _text_quality_is_low(text_preview)
                        or len((doc.get("fields") or {}).get("all_numbers") or []) <= 4
                    )
                ):
                    doc["document_type"] = "cedula"
                    doc["legacy_code"] = 6
                    doc["legacy_label"] = LEGACY_CODE_TO_TYPE.get(6, "")
                    doc["code_source"] = "post_cedula_between_rut_and_followup"
                    continue

                if (
                    not looks_like_other_strong_type
                    and prev_doc
                    and next_doc
                    and prev_doc.get("document_type") == "rut"
                    and next_doc.get("document_type") == "soporte_ingresos"
                    and _extract_page_number(str(prev_doc.get("filename") or "")) + 1 == _extract_page_number(str(doc.get("filename") or ""))
                    and _extract_page_number(str(doc.get("filename") or "")) + 1 == _extract_page_number(str(next_doc.get("filename") or ""))
                    and (
                        not text_preview
                        or _text_quality_is_low(text_preview)
                        or (
                            not _looks_like_cedula_document(normalize_haystack(doc.get("filename", "")), haystack)
                            and len((doc.get("fields") or {}).get("all_numbers") or []) <= 4
                        )
                    )
                ):
                    doc["document_type"] = "cedula"
                    doc["legacy_code"] = 6
                    doc["legacy_label"] = LEGACY_CODE_TO_TYPE.get(6, "")
                    doc["code_source"] = "post_cedula_between_rut_and_pagos"
                    continue

                sede_continuation_markers = [
                    "a. informacion de la sede",
                    "a. información de la sede",
                    "responsable del centro de trabajo",
                    "b. informacion de los centros de trabajo",
                    "b. información de los centros de trabajo",
                    "informacion del responsable de la sede principal",
                    "información del responsable de la sede principal",
                ]
                formulario_continuation_markers = [
                    "novedades y autoliquidacion",
                    "novedades y autoliquidación",
                    "informacion de nomina",
                    "información de nómina",
                    "cantidad de trabajadores y estudiantes",
                ]
                if (
                    prev_doc
                    and prev_doc.get("document_type") == "formulario_afiliacion"
                    and any(marker in haystack for marker in sede_continuation_markers)
                ):
                    doc["document_type"] = "anexo_sedes"
                    doc["legacy_code"] = 1
                    doc["legacy_label"] = LEGACY_CODE_TO_TYPE.get(1, "")
                    doc["code_source"] = "post_sede_continuation"
                    continue

                if (
                    prev_doc
                    and prev_doc.get("document_type") in {"formulario_afiliacion", "anexo_sedes"}
                    and any(marker in haystack for marker in formulario_continuation_markers)
                ):
                    doc["document_type"] = "formulario_afiliacion"
                    doc["legacy_code"] = 0
                    doc["legacy_label"] = LEGACY_CODE_TO_TYPE.get(0, "")
                    doc["code_source"] = "post_formulario_continuation"
                    continue

                if (
                    not looks_like_other_strong_type
                    and prev_doc
                    and next_doc
                    and prev_doc.get("document_type") == "rut"
                    and next_doc.get("document_type") == "autorizacion"
                    and (
                        not text_preview
                        or _text_quality_is_low(text_preview)
                        or not (doc.get("fields") or {}).get("all_numbers")
                    )
                ):
                    doc["document_type"] = "cedula"
                    doc["legacy_code"] = 6
                    doc["legacy_label"] = LEGACY_CODE_TO_TYPE.get(6, "")
                    doc["code_source"] = "post_cedula_between_rut_and_autorizacion"

    # A single contract should not finish with multiple identity documents classified as cédula.
    cedula_docs = [doc for doc in docs if doc.get("document_type") == "cedula"]
    for doc in list(cedula_docs):
        haystack = normalize_haystack(
            f"{doc.get('filename', '')} {doc.get('ocr_text', '') or doc.get('text_preview', '')}"
        )
        if any(
            marker in haystack
            for marker in [
                "informe consolidado de pagos por empresas",
                "resumen de pago a salud",
                "aportes resumen general de pago",
                "resumen general de pago en linea",
                "resumen general de pago en línea",
                "resumen general de pago en inea",
                "datos generales del aportante",
                "valor a pagar",
            ]
        ):
            doc["document_type"] = "soporte_ingresos"
            doc["legacy_code"] = 11
            doc["legacy_label"] = LEGACY_CODE_TO_TYPE.get(11, "")
            doc["code_source"] = "post_soporte_from_false_cedula"
            continue
        if _looks_like_constancia_afiliacion(haystack):
            doc["document_type"] = "constancia_afiliacion"
            doc["legacy_code"] = 7
            doc["legacy_label"] = LEGACY_CODE_TO_TYPE.get(7, "")
            doc["code_source"] = "post_constancia_from_false_cedula"
            continue
        if _looks_like_carta_document(haystack):
            doc["document_type"] = "carta"
            doc["legacy_code"] = 4
            doc["legacy_label"] = LEGACY_CODE_TO_TYPE.get(4, "")
            doc["code_source"] = "post_carta_from_false_cedula"
            continue

    cedula_docs = [doc for doc in docs if doc.get("document_type") == "cedula"]
    if len(cedula_docs) > 1:
        def _cedula_rank(doc: Dict[str, Any]) -> tuple[int, int]:
            haystack = normalize_haystack(
                f"{doc.get('filename', '')} {doc.get('ocr_text', '') or doc.get('text_preview', '')}"
            )
            fields = doc.get("fields") or {}
            score = 0
            if _looks_like_cedula_document(normalize_haystack(doc.get("filename", "")), haystack):
                score += 10
            if fields.get("document_number"):
                score += 6
            if fields.get("representative_document"):
                score += 4
            if any(token in haystack for token in ["cedula de ciudadania", "identificacion personal", "fecha y lugar de expedicion", "lugar de nacimiento"]):
                score += 8
            if any(token in haystack for token in ["resumen general de pago", "informe consolidado de pagos", "reporte consulta no.", "señores positiva", "desvinculacion de empresa"]):
                score -= 12
            return score, -_extract_page_number(str(doc.get("filename") or ""))

        best_cedula = sorted(cedula_docs, key=_cedula_rank, reverse=True)[0]
        for doc in cedula_docs:
            if doc is best_cedula:
                continue
            haystack = normalize_haystack(
                f"{doc.get('filename', '')} {doc.get('ocr_text', '') or doc.get('text_preview', '')}"
            )
            if _looks_like_constancia_afiliacion(haystack):
                doc["document_type"] = "constancia_afiliacion"
                doc["legacy_code"] = 7
                doc["legacy_label"] = LEGACY_CODE_TO_TYPE.get(7, "")
                doc["code_source"] = "post_single_cedula_constancia"
            elif _looks_like_carta_document(haystack):
                doc["document_type"] = "carta"
                doc["legacy_code"] = 4
                doc["legacy_label"] = LEGACY_CODE_TO_TYPE.get(4, "")
                doc["code_source"] = "post_single_cedula_carta"
            elif any(token in haystack for token in ["resumen general de pago", "informe consolidado de pagos", "datos generales del aportante", "valor a pagar"]):
                doc["document_type"] = "soporte_ingresos"
                doc["legacy_code"] = 11
                doc["legacy_label"] = LEGACY_CODE_TO_TYPE.get(11, "")
                doc["code_source"] = "post_single_cedula_pagos"
            else:
                doc["document_type"] = "pdf"
                doc["legacy_code"] = 99
                doc["legacy_label"] = LEGACY_CODE_TO_TYPE.get(99, "")
                doc["code_source"] = "post_single_cedula_image"

    _apply_document_learning_calibration(docs)


def _number_anexo_sedes(docs: List[Dict[str, Any]]) -> None:
    """Numera los documentos anexo_sedes segun el codigo de sede detectado en el OCR.
    Respeta correcciones manuales. Si no se puede detectar, numera secuencialmente."""
    sede_docs = [d for d in docs if str(d.get("document_type","")).startswith("anexo_sedes")]
    if not sede_docs:
        return
    used_nums = set()
    for doc in sede_docs:
        dtype = str(doc.get("document_type",""))
        # Si ya fue corregido manualmente con numero especifico, respetar
        code_src = str(doc.get("code_source",""))
        if "manual" in code_src or "review" in code_src:
            m_type = re.search(r"anexo_sedes_?(\d+)", dtype)
            num = int(m_type.group(1)) if m_type else 1
        else:
            m_type = re.search(r"anexo_sedes_?(\d+)", dtype)
            if m_type:
                num = int(m_type.group(1))
            else:
                ocr = str(doc.get("ocr_text") or doc.get("text_preview") or "")
                num = _detect_sede_number_from_ocr(ocr)
        # Evitar duplicados — si ya se uso ese numero, incrementar
        while num in used_nums:
            num += 1
        used_nums.add(num)
        doc["sede_num"] = num
        doc["display_name"] = f"Sedes ·{num:02d}"
        doc["legacy_label"] = f"Sedes ·{num:02d}"


def _classify_document(filename: str, text: str) -> Dict[str, Any]:
    # 1. Intentar clasificar con RAG primero (aprendizaje acumulado)
    if text and len(text.strip()) > 50:
        rag_result = _rag_classify_document(text, min_score=0.85)
        if rag_result:
            return rag_result
    # 2. Fallback a clasificacion por reglas
    name_txt = normalize_haystack(filename)
    text_txt = normalize_haystack(text)
    haystack = f"{name_txt} {text_txt}".strip()
    lower_name = str(filename or "").lower()

    if "formulario de afiliacion" in name_txt:
        return {"document_type": "formulario_afiliacion", "legacy_code": 0, "code_source": "name_override_formulario"}
    if re.search(r"\bsede[\s._-]*\d+\b", name_txt) or re.search(r"\bsedes?\b", name_txt):
        return {"document_type": "anexo_sedes", "legacy_code": 1, "code_source": "name_override_sede"}
    if re.match(r"^sede\d+(?:__p\d+)?\.pdf$", lower_name):
        return {"document_type": "anexo_sedes", "legacy_code": 1, "code_source": "name_override_sede_compact"}
    if (
        "a. afiliacion" in haystack
        or "a. afiliación" in haystack
        or ("b. traslado" in haystack and "c. terminacion" in haystack)
        or ("cps-f-216" in haystack)
    ):
        return {"document_type": "formulario_afiliacion", "legacy_code": 0, "code_source": "ocr_formulario_precise"}
    if _looks_like_beneficiario_final_document(haystack):
        return {"document_type": "beneficiario_final", "legacy_code": 27, "code_source": "ocr_beneficiario_precise"}
    if _looks_like_cedula_document(name_txt, haystack):
        return {"document_type": "cedula", "legacy_code": 6, "code_source": "ocr_cedula_precise"}
    if _looks_like_rut_document(haystack):
        return {"document_type": "rut", "legacy_code": 8, "code_source": "ocr_rut_precise"}
    if _looks_like_entrega_documentos(haystack):
        return {"document_type": "entrega_documentos", "legacy_code": 10, "code_source": "ocr_entrega_precise"}
    if _looks_like_camara_document(haystack):
        return {"document_type": "camara_comercio", "legacy_code": 5, "code_source": "ocr_camara_precise"}
    if _looks_like_constancia_afiliacion(haystack):
        return {"document_type": "constancia_afiliacion", "legacy_code": 7, "code_source": "ocr_constancia"}
    if _looks_like_autorizacion_document(haystack):
        return {"document_type": "autorizacion", "legacy_code": 98, "code_source": "ocr_autorizacion_precise"}
    if _looks_like_comision_document(haystack):
        return {"document_type": "comision", "legacy_code": 3, "code_source": "ocr_comision_precise"}
    if _looks_like_carta_document(haystack):
        return {"document_type": "carta", "legacy_code": 4, "code_source": "ocr_carta"}
    planilla_markers = [
        "informe consolidado de pagos por empresas",
        "resumen de pago a salud",
        "aportes planilla resumen",
        "planilla resumen en linea",
        "planilla resumen en línea",
        "resumen general de pago en inea",
        "planilla resumen",
        "resumen general de pago en linea",
        "resumen general de pago en línea",
        "aportes resumen general de pago en linea",
        "aportes resumen general de pago en línea",
        "aportes resumen general de pago en inea",
        "resumen de pago riesgo",
        "datos generales del aportante",
        "centro de trabajo:",
        "afiliados)",
        "valor liquidado",
        "valor a pagar",
        "datos generales de la liquidacion",
        "datos generales de la liquidación",
        "entidad recaudo pagada",
        "ibc salud",
        "ibc pension",
        "ibc pensión",
        "valor pago",
        "estado planilla",
        "periodo salud",
        "periodo pensión",
        "periodo pension",
        "referencia de pago",
        "f. presentacion unica",
        "f. presentación única",
    ]
    planilla_negative_markers = [
        "enviado el:",
        "datos adjuntos:",
        "asunto:",
        "formulario de afiliacion",
        "a. afiliacion",
        "a. afiliación",
        "b. traslado",
        "c. terminacion",
    ]
    planilla_hits = sum(1 for token in planilla_markers if token in haystack)
    if planilla_hits >= 2 and not any(token in haystack for token in planilla_negative_markers):
        return {"document_type": "soporte_ingresos", "legacy_code": 11, "code_source": "ocr_planilla_precise"}

    strong_rules: List[tuple[int, str, List[str], str]] = [
        (8, "rut", ["registro unico tributario", "r.u.t", " rut ", "direccion de impuestos y aduanas"], "ocr_rut"),
        (5, "camara_comercio", ["camara de comercio", "certificado de existencia", "matricula mercantil"], "ocr_camara"),
        (0, "formulario_afiliacion", ["formulario de afiliacion", "formulario unico de afiliacion", "cps-f-216"], "ocr_formulario"),
        (1, "anexo_sedes", ["sedes y centros de trabajo", "anexo formulario de afiliacion"], "ocr_sedes"),
        (2, "listado_trabajadores", ["listado de trabajadores", "trabajadores o estudiantes"], "ocr_listado"),
        (10, "entrega_documentos", ["comprobante entrega de documentos", "documentos anexos a la afiliacion"], "ocr_entrega"),
        (11, "soporte_pagos", ["recibo de pago", "ultimos recibos de pago", "pila pagada"], "ocr_pagos"),
        (12, "contrato", ["contrato de prestacion", "prestacion de servicios", "objeto del contrato"], "ocr_contrato"),
        (19, "identificacion_peligros", ["identificacion de peligros", "matriz de peligros"], "ocr_peligros"),
        (20, "examen_preocupacional", ["examen pre-ocupacional", "examen preocupacional"], "ocr_preocupacional"),
        (27, "beneficiario_final", ["beneficiario final"], "ocr_beneficiario"),
        (27, "beneficiario_final", ["participacion directa o indirecta mayor al 5", "participación directa o indirecta mayor al 5", "informacion de la compania", "información de la compañía"], "ocr_beneficiario_company"),
        (28, "sat", ["sistema de afiliacion transaccional", "canal sat"], "ocr_sat"),
        (98, "autorizacion", ["autorizacion clientes, proveedores y terceros", "autorizacion tratamiento de datos", "autorización de tratamiento de datos", "tratamiento de datos personales"], "ocr_autorizacion"),
    ]
    for code, doc_type, keys, label in strong_rules:
        if any(key in haystack for key in keys):
            return {"document_type": doc_type, "legacy_code": code, "code_source": label}

    if any(token in haystack for token in ["declaracion de renta", "declaracion renta", "honorarios", "ingresos", "desprendible de pago"]):
        return {"document_type": "soporte_ingresos", "legacy_code": 11, "code_source": "ocr_ingresos"}

    name_rules: List[tuple[int, str, List[str], str]] = [
        (6, "cedula", ["cedula", "cc_"], "name_cedula"),
        (5, "camara_comercio", ["camara", "comercio"], "name_camara"),
        (8, "rut", ["rut"], "name_rut"),
        (1, "anexo_sedes", ["sedes", "anexo_sedes"], "name_sedes"),
        (2, "listado_trabajadores", ["trabajadores", "listado"], "name_listado"),
        (10, "entrega_documentos", ["entrega", "anexos"], "name_entrega"),
        (11, "soporte_pagos", ["pagos", "recibo"], "name_pagos"),
        (12, "contrato", ["contrato"], "name_contrato"),
        (98, "autorizacion", ["autorizacion"], "name_autorizacion"),
    ]
    for code, doc_type, keys, label in name_rules:
        if any(key in name_txt for key in keys):
            return {"document_type": doc_type, "legacy_code": code, "code_source": label}

    if lower_name.endswith((".xlsx", ".xlsm", ".xls")):
        return {"document_type": "xlsx", "legacy_code": -1, "code_source": "file_xlsx"}
    if lower_name.endswith(".pdf"):
        return {"document_type": "pdf", "legacy_code": 99, "code_source": "file_pdf"}
    if lower_name.endswith((".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp")):
        return {"document_type": "imagen", "legacy_code": 99, "code_source": "file_image"}
    return {"document_type": "otro", "legacy_code": 99, "code_source": "fallback"}


def _infer_required_document_satisfaction(
    required_docs: List[str],
    docs: List[Dict[str, Any]],
    profile: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    xlsx_document = only_digits(profile.get("documento", ""))
    xlsx_nit = only_digits(profile.get("nit", ""))
    results: Dict[str, Dict[str, Any]] = {}
    grouped_types = {doc.get("document_type") for doc in docs}

    for required in required_docs:
        direct = required in grouped_types
        evidence: Dict[str, Any] = {"satisfied": direct, "direct": direct, "filename": "", "matched": "", "reason": ""}
        if direct:
            doc = next((item for item in docs if item.get("document_type") == required), None)
            evidence["filename"] = (doc or {}).get("filename", "")
            evidence["reason"] = "direct_type"
            results[required] = evidence
            continue

        if required == "cedula":
            for doc in docs:
                fields = doc.get("fields") or {}
                preview = normalize_haystack(doc.get("text_preview", ""))
                doc_type = str(doc.get("document_type") or "")
                candidates = [fields.get("representative_document", ""), fields.get("document_number", "")] + list(fields.get("all_numbers") or [])
                candidate = _best_numeric_candidate(xlsx_document, candidates) if xlsx_document else ""
                if candidate and (
                    doc_type not in {"carta", "rut", "camara_comercio", "soporte_ingresos", "entrega_documentos"}
                    and (
                        _looks_like_cedula_document(normalize_haystack(doc.get("filename", "")), preview)
                        or "numero de cedula" in preview
                        or "numero de identificacion cc" in preview
                        or "tipo de documento numero de identificacion cc" in preview
                        or "tipo de documento cc" in preview
                        or "identificacion personal" in preview
                        or ("lugar de nac" in preview and "expedicion" in preview)
                    )
                ):
                    evidence.update(
                        {
                            "satisfied": True,
                            "filename": doc.get("filename", ""),
                            "matched": candidate,
                            "reason": "inferred_identity_match",
                        }
                    )
                    break
        elif required == "rut":
            for doc in docs:
                fields = doc.get("fields") or {}
                preview = normalize_haystack(doc.get("text_preview", ""))
                nit_candidate = _best_numeric_candidate(xlsx_nit, [fields.get("nit", ""), fields.get("document_number", "")] + list(fields.get("all_numbers") or [])) if xlsx_nit else ""
                if nit_candidate and (
                    "dian" in preview
                    or "registro unico tributario" in preview
                    or "direccion de impuestos" in preview
                    or "numero de identificacion tributaria" in preview
                ):
                    evidence.update(
                        {
                            "satisfied": True,
                            "filename": doc.get("filename", ""),
                            "matched": nit_candidate,
                            "reason": "inferred_rut_match",
                        }
                    )
                    break
        elif required == "camara_comercio":
            for doc in docs:
                preview = normalize_haystack(doc.get("text_preview", ""))
                if _looks_like_camara_document(preview):
                    evidence.update(
                        {
                            "satisfied": True,
                            "filename": doc.get("filename", ""),
                            "reason": "inferred_camara_match",
                        }
                    )
                    break
        elif required == "soporte_ingresos":
            for doc in docs:
                fields = doc.get("fields") or {}
                preview = normalize_haystack(doc.get("text_preview", ""))
                if fields.get("has_income_hint") or any(
                    token in preview
                    for token in ["pila pagada", "recibo de pago", "desprendible de pago", "ingresos", "autorizacion cargue retroactivo"]
                ):
                    evidence.update(
                        {
                            "satisfied": True,
                            "filename": doc.get("filename", ""),
                            "reason": "inferred_income_match",
                        }
                    )
                    break

        results[required] = evidence
    return results


def _extract_fields(text: str) -> Dict[str, Any]:
    normalized = normalize_text(text)
    lowered = normalize_haystack(normalized)
    raw_number_groups = re.findall(r"\d[\d.,\-\s]{4,}\d", normalized)
    digits: List[str] = []
    for item in raw_number_groups:
        cleaned = only_digits(item)
        if 6 <= len(cleaned) <= 15 and cleaned not in digits:
            digits.append(cleaned)
    for item in re.findall(r"\b\d{6,15}\b", normalized):
        cleaned = only_digits(item)
        if 6 <= len(cleaned) <= 15 and cleaned not in digits:
            digits.append(cleaned)
    doc_number = digits[0] if digits else ""
    nit_match = re.search(r"\bnit[^0-9]{0,12}(\d{6,12})\b", lowered) or re.search(r"\b(\d{9,10})\b", normalized)
    date_matches = re.findall(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", normalized)
    has_rut = "rut" in lowered or "nit" in lowered or "tributario" in lowered
    company_name = ""
    rep_name = ""
    rep_doc = ""
    match = re.search(
        r"raz[oó]n social[^A-Za-z0-9]{0,10}(?P<value>[A-ZÁÉÍÓÚÑ0-9 .,&-]{6,160}?)(?=(?:\s*|)(?:sigla|nit|domicilio principal)\s*:|$)",
        normalized,
        flags=re.IGNORECASE,
    )
    if match:
        candidate = normalize_text(match.group("value"))
        candidate = re.sub(r"\s+sigla\s*$", "", candidate, flags=re.IGNORECASE).strip()
        if _looks_like_company_name(candidate):
            company_name = candidate
    if not company_name:
        match = re.search(r"(PALMAS\s+DE\s+PUERTO\s+GAITAN(?:\s+S\.\s*A\.\s*S\.?)?)", normalized, flags=re.IGNORECASE)
        if match:
            company_name = normalize_text(match.group(1))
    match = re.search(r"apellidos y nombres del representante legal[^A-Za-z0-9]{0,20}([A-ZÁÉÍÓÚÑ ]{6,120})", normalized, flags=re.IGNORECASE)
    if match:
        candidate = normalize_text(match.group(1))
        candidate = _normalize_person_name(candidate)
        if _looks_like_person_name(candidate):
            rep_name = candidate
    if not rep_name:
        match = re.search(r"\byo\s+([A-ZÁÉÍÓÚÑ ]{6,120})\s+identificad[oa]?\s+con", normalized, flags=re.IGNORECASE)
        if match:
            candidate = normalize_text(match.group(1))
            candidate = _normalize_person_name(candidate)
            if _looks_like_person_name(candidate):
                rep_name = candidate
    match = re.search(r"n[uú]mero de documento[^0-9]{0,20}([\d.,\-\s]{6,20})", normalized, flags=re.IGNORECASE)
    if match:
        rep_doc = only_digits(match.group(1))
    if (
        "cedula de ciudadania" in lowered
        or "cedula de" in lowered
        or "cédula de" in normalized.lower()
        or "identificacion personal" in lowered
        or "nuip" in lowered
    ):
        cedula_number_match = re.search(
            r"(?:nuip|c[eé]dula\s+de\s+ciudadan[ií]a)[^\d]{0,12}(\d{1,3}(?:[.\s]\d{3}){1,3})",
            normalized,
            flags=re.IGNORECASE,
        )
        if not cedula_number_match:
            cedula_number_match = re.search(
                r"\b(\d{1,3}(?:[.\s]\d{3}){1,3})\s+(?:ENE|FEB|MAR|ABR|MAY|JUN|JUL|AGO|SEP|SEPT|OCT|NOV|DIC)\b",
                normalized,
                flags=re.IGNORECASE,
            )
        if cedula_number_match:
            rep_doc = only_digits(cedula_number_match.group(1))
        cedula_name = _extract_name_from_cedula_text(normalized)
        cedula_name = _normalize_person_name(cedula_name)
        if _looks_like_person_name(cedula_name):
            rep_name = cedula_name
        cedula_numbers = [only_digits(item) for item in digits if 6 <= len(only_digits(item)) <= 15]
        if cedula_numbers:
            rep_doc = rep_doc or cedula_numbers[0]
            doc_number = rep_doc or doc_number
    textual_issue_date = _parse_spanish_date_text(normalized)
    digit_candidates = [only_digits(item) for item in digits]
    filtered_nit_candidates = [
        item for item in digit_candidates
        if 8 <= len(item) <= 10 and not item.startswith("00")
    ]
    nit_value = nit_match.group(1) if nit_match and has_rut else ""
    if nit_value and len(only_digits(nit_value)) > 10:
        nit_value = ""
    if not nit_value and filtered_nit_candidates:
        nit_value = filtered_nit_candidates[0]

    tipo_negocio = ""
    tipoempresa_homologado = ""
    if "tipo de negocio" in lowered:
        tipo_section_match = re.search(
            r"tipo\s+de\s+negocio(?P<section>.{0,260})",
            normalized,
            flags=re.IGNORECASE | re.DOTALL,
        )
        tipo_section_raw = tipo_section_match.group("section") if tipo_section_match else normalized
        tipo_section_raw = re.split(
            r"pago\s+de\s+reconocimiento|documentos\s+anexos|datos\s+soporte",
            tipo_section_raw,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        tipo_section = normalize_haystack(tipo_section_raw)
        option_order = ["grande", "mediana", "pequena", "micro"]
        option_labels = {
            "grande": ("Grande", "2"),
            "mediana": ("Mediana", "1"),
            "pequena": ("Pequeña", "8"),
            "micro": ("Micro", "9"),
        }
        token_stream = re.findall(r"[a-z0-9]+", tipo_section)
        section_for_positions = re.sub(r"[^a-z0-9]+", " ", tipo_section).strip()
        ordered_option_matches: List[Tuple[int, int, str]] = []
        for option in option_order:
            for match in re.finditer(rf"\b{re.escape(option)}\b", section_for_positions):
                ordered_option_matches.append((match.start(), match.end(), option))
        ordered_option_matches.sort(key=lambda item: item[0])
        if ordered_option_matches:
            for index, (start, end, option) in enumerate(ordered_option_matches):
                next_start = ordered_option_matches[index + 1][0] if index + 1 < len(ordered_option_matches) else min(len(section_for_positions), end + 24)
                segment = section_for_positions[end:next_start]
                if re.search(r"\bx\b", segment):
                    tipo_negocio, tipoempresa_homologado = option_labels[option]
                    break
        if not tipo_negocio:
            option_positions: List[Tuple[int, str]] = [(start, option) for start, _, option in ordered_option_matches]
            x_positions = [match.start() for match in re.finditer(r"\bx\b", section_for_positions)]
            if option_positions and x_positions:
                best_match = min(
                    (
                        (
                            abs(option_pos - x_pos),
                            x_pos,
                            option_order.index(option),
                            option,
                        )
                        for option_pos, option in option_positions
                        for x_pos in x_positions
                    ),
                    default=None,
                )
                if best_match:
                    _, _, _, selected_option = best_match
                    tipo_negocio, tipoempresa_homologado = option_labels[selected_option]
        if not tipo_negocio:
            for index, token in enumerate(token_stream):
                if token != "x":
                    continue
                prev_token = token_stream[index - 1] if index > 0 else ""
                next_token = token_stream[index + 1] if index + 1 < len(token_stream) else ""
                if prev_token in option_labels:
                    tipo_negocio, tipoempresa_homologado = option_labels[prev_token]
                    break
                if next_token in option_labels:
                    tipo_negocio, tipoempresa_homologado = option_labels[next_token]
                    break
        if not tipo_negocio:
            sequence = " ".join(token_stream)
            for option in option_order:
                if f"x {option}" in sequence or f"{option} x" in sequence:
                    tipo_negocio, tipoempresa_homologado = option_labels[option]
                    break

    return {
        "document_number": doc_number,
        "nit": nit_value,
        "all_numbers": digits[:10],
        "dates": date_matches[:5],
        "company_name": company_name,
        "representative_name": rep_name,
        "representative_document": rep_doc,
        "issue_date_textual": textual_issue_date.strftime("%Y-%m-%d") if textual_issue_date else "",
        "tipo_negocio": tipo_negocio,
        "tipoempresa_homologado": tipoempresa_homologado,
        "has_signature_hint": "firma" in lowered,
        "has_income_hint": any(token in lowered for token in ["ingres", "salario", "honorarios", "renta"]),
        "has_contrato_hint": "contrato" in lowered or "prestacion de servicios" in lowered,
        "has_worker_list_hint": "trabajador" in lowered or "trabajadores" in lowered,
    }


def _score_ocr_quality(text: str, used_ocr: bool, pages_processed: int) -> float:
    normalized = normalize_text(text)
    if not normalized:
        return 0.05 if used_ocr else 0.0
    tokens = [token for token in re.split(r"\s+", normalized) if token]
    unique_tokens = len(set(token.lower() for token in tokens))
    digits = len(re.findall(r"\d", normalized))
    score = 0.15
    score += min(len(normalized) / 1800.0, 0.35)
    score += min(unique_tokens / 120.0, 0.2)
    score += min(digits / 80.0, 0.1)
    if pages_processed > 1:
        score += 0.05
    if not used_ocr:
        score += 0.1
    return round(max(0.0, min(score, 0.99)), 2)


def _document_signals(document_type: str, code_source: str, fields: Dict[str, Any], text: str, filename: str) -> List[str]:
    haystack = normalize_haystack(f"{filename} {text}")
    signals: List[str] = []
    if code_source:
        signals.append(f"source:{code_source}")
    if document_type == "cedula":
        for token in [
            "cedula de ciudadania",
            "identificacion personal",
            "registraduria nacional",
            "fecha y lugar de expedicion",
            "lugar de nacimiento",
        ]:
            if token in haystack:
                signals.append(token)
    elif document_type == "rut":
        for token in ["registro unico tributario", "direccion de impuestos", "rut"]:
            if token in haystack:
                signals.append(token)
    elif document_type == "camara_comercio":
        for token in ["camara de comercio", "certificado de existencia", "matricula mercantil", "fecha expedicion"]:
            if token in haystack:
                signals.append(token)
    elif document_type == "formulario_afiliacion":
        for token in ["formulario de afiliacion", "a. afiliacion", "b. traslado", "informacion de nomina", "novedades y autoliquidacion"]:
            if token in haystack:
                signals.append(token)
    elif document_type == "anexo_sedes":
        for token in ["informacion de la sede", "información de la sede", "centros de trabajo", "sede principal"]:
            if token in haystack:
                signals.append(token)
    elif document_type in {"soporte_ingresos", "soporte_pagos"}:
        for token in ["informe consolidado de pagos", "resumen general de pago", "datos generales del aportante", "valor a pagar"]:
            if token in haystack:
                signals.append(token)
    elif document_type == "carta":
        for token in ["señores", "desvinculacion de empresa", "traslado", "datos adjuntos", "enviado el"]:
            if token in haystack:
                signals.append(token)
    if fields.get("document_number"):
        signals.append("field:document_number")
    if fields.get("nit"):
        signals.append("field:nit")
    if fields.get("representative_document"):
        signals.append("field:representative_document")
    if fields.get("representative_name"):
        signals.append("field:representative_name")
    return signals[:8]


def _document_key_fields(document_type: str, fields: Dict[str, Any]) -> Dict[str, str]:
    if document_type == "cedula":
        return {
            "numero": only_digits(fields.get("representative_document") or fields.get("document_number") or ""),
            "nombre": normalize_text(fields.get("representative_name", "")),
            "fecha_expedicion": normalize_text(fields.get("issue_date_textual", "")),
        }
    if document_type == "rut":
        return {
            "nit": only_digits(fields.get("nit", "") or fields.get("document_number", "")),
            "razon_social": _clean_company_name(fields.get("company_name", "")),
        }
    if document_type == "camara_comercio":
        return {
            "nit": only_digits(fields.get("nit", "") or fields.get("document_number", "")),
            "razon_social": _clean_company_name(fields.get("company_name", "")),
            "fecha_expedicion": normalize_text(fields.get("issue_date_textual", "")),
        }
    if document_type == "formulario_afiliacion":
        return {
            "documento_representante": only_digits(fields.get("representative_document") or fields.get("document_number") or ""),
            "razon_social": _clean_company_name(fields.get("company_name", "")),
        }
    if document_type == "anexo_sedes":
        return {
            "documento_responsable": only_digits(fields.get("representative_document") or fields.get("document_number") or ""),
            "responsable": normalize_text(fields.get("representative_name", "")),
        }
    return {
        "documento": only_digits(fields.get("document_number", "")),
        "nit": only_digits(fields.get("nit", "")),
    }



def _detect_sede_number_from_ocr(ocr_text: str) -> int:
    """Detecta el numero de sede en el OCR de un anexo_sedes."""
    if not ocr_text:
        return 1
    import re as _re
    text = normalize_text(ocr_text)
    # Buscar "codigo de la sede: X" o "sede X"
    m = _re.search(r'codigo\s+de\s+la\s+sede[:\s]+(\d+)', text)
    if m:
        return int(m.group(1))
    m = _re.search(r'sede\s+(\d+)', text)
    if m:
        return int(m.group(1))
    return 1

def _field_confidence(document_type: str, fields: Dict[str, Any], text: str) -> Dict[str, float]:
    normalized = normalize_text(text)
    result: Dict[str, float] = {}
    key_fields = _document_key_fields(document_type, fields)
    for key, value in key_fields.items():
        clean = normalize_text(value)
        if not clean:
            result[key] = 0.0
            continue
        if key in {"numero", "nit", "documento", "documento_representante", "documento_responsable"}:
            result[key] = 0.95 if only_digits(clean) and only_digits(clean) in only_digits(normalized) else 0.55
            continue
        if key == "fecha_expedicion":
            result[key] = 0.9 if clean and normalize_haystack(clean) in normalize_haystack(normalized) else 0.5
            continue
        result[key] = 0.88 if normalize_haystack(clean) and normalize_haystack(clean) in normalize_haystack(normalized) else 0.45
    return {k: round(v, 2) for k, v in result.items()}


def _classification_confidence(document_type: str, code_source: str, fields: Dict[str, Any], text: str, filename: str) -> float:
    base_by_source = {
        "ocr_cedula_precise": 0.95,
        "ocr_rut_precise": 0.95,
        "ocr_camara_precise": 0.95,
        "ocr_formulario_precise": 0.95,
        "ocr_beneficiario_precise": 0.94,
        "ocr_entrega_precise": 0.92,
        "ocr_planilla_precise": 0.93,
        "ocr_autorizacion_precise": 0.92,
        "ocr_comision_precise": 0.92,
        "ocr_carta": 0.88,
        "name_override_formulario": 0.92,
        "name_override_sede": 0.92,
        "name_override_sede_compact": 0.92,
        "learned_calibration_pdf_to_cedula": 0.82,
        "learned_calibration_pdf_to_soporte_ingresos": 0.8,
        "learned_calibration_rut_to_carta": 0.78,
        "file_pdf": 0.3,
        "file_image": 0.3,
        "fallback": 0.2,
    }
    confidence = base_by_source.get(code_source, 0.72)
    signals = _document_signals(document_type, code_source, fields, text, filename)
    confidence += min(len(signals) * 0.02, 0.12)
    key_fields = _document_key_fields(document_type, fields)
    populated = sum(1 for value in key_fields.values() if normalize_text(value))
    confidence += min(populated * 0.03, 0.09)
    if document_type in {"pdf", "imagen"}:
        confidence = min(confidence, 0.45)
    return round(max(0.05, min(confidence, 0.99)), 2)


def _parse_date(text: str) -> Optional[datetime]:
    match = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b", text)
    if not match:
        return None
    day, month, year = match.groups()
    year_num = int(year)
    if year_num < 100:
        year_num += 2000
    try:
        return datetime(year_num, int(month), int(day))
    except ValueError:
        return None


def _parse_spanish_date_text(text: str) -> Optional[datetime]:
    lowered = normalize_haystack(text)
    month_map = {
        "enero": 1,
        "febrero": 2,
        "marzo": 3,
        "abril": 4,
        "mayo": 5,
        "junio": 6,
        "julio": 7,
        "agosto": 8,
        "septiembre": 9,
        "setiembre": 9,
        "octubre": 10,
        "noviembre": 11,
        "diciembre": 12,
    }
    explicit_patterns = [
        r"fecha\s+de\s+expedicion[:\s]+(\d{1,2})[/-](\d{1,2})[/-](\d{4})",
        r"fecha\s+expedicion[:\s]+(\d{1,2})[/-](\d{1,2})[/-](\d{4})",
        r"fecha\s+de\s+expedicion[:\s]+(\d{1,2})\s+de\s+([a-z]+)\s+de\s+(\d{4})",
        r"fecha\s+expedicion[:\s]+(\d{1,2})\s+de\s+([a-z]+)\s+de\s+(\d{4})",
    ]
    for pattern in explicit_patterns:
        match = re.search(pattern, lowered)
        if not match:
            continue
        groups = match.groups()
        try:
            if len(groups) == 3 and groups[1].isdigit():
                day, month, year = groups
                return datetime(int(year), int(month), int(day))
            day, month_name, year = groups
            month = month_map.get(month_name)
            if month:
                return datetime(int(year), int(month), int(day))
        except ValueError:
            pass

    match = re.search(r"(\d{1,2})\s+de\s+([a-z]+)\s+de\s+(\d{4})", lowered)
    if not match:
        return None
    day, month_name, year = match.groups()
    month = month_map.get(month_name)
    if not month:
        return None
    try:
        return datetime(int(year), int(month), int(day))
    except ValueError:
        return None


def _ocr_image(path: Path) -> Dict[str, Any]:
    with Image.open(path) as image:
        text = _ocr_best_text_from_image(image)
    return {
        "text": normalize_text(text),
        "used_ocr": True,
        "pages_processed": 1,
    }


def _prepare_ocr_variants(image: Image.Image) -> List[Image.Image]:
    base = image.convert("L")
    enlarged = base.resize((max(base.width * 2, 1), max(base.height * 2, 1)), Image.Resampling.LANCZOS)
    sharpened = enlarged.filter(ImageFilter.SHARPEN)
    contrasted = ImageEnhance.Contrast(sharpened).enhance(2.6)
    autocontrasted = ImageOps.autocontrast(contrasted)
    thresholded = autocontrasted.point(lambda px: 255 if px > 165 else 0, mode="1").convert("L")
    soft_thresholded = autocontrasted.point(lambda px: 255 if px > 145 else 0, mode="1").convert("L")
    return [enlarged, autocontrasted, thresholded, soft_thresholded]


def _score_ocr_candidate(text: str) -> int:
    if not text:
        return -1
    alpha = sum(1 for ch in text if ch.isalpha())
    digits = sum(1 for ch in text if ch.isdigit())
    haystack = normalize_haystack(text)
    weird = sum(1 for ch in text if ord(ch) > 127 and ch not in "ÁÉÍÓÚÑáéíóúñ")
    score = len(text) + alpha + (digits * 2) - (weird * 3)
    identity_markers = [
        "republica de colombia",
        "identificacion personal",
        "identificación personal",
        "cedula de ciudadania",
        "cédula de ciudadanía",
        "fecha y lugar de expedicion",
        "fecha y lugar de expedición",
        "lugar de nacimiento",
        "indice derecho",
        "nacional",
    ]
    score += sum(45 for marker in identity_markers if marker in haystack)
    if re.search(r"\b\d{1,3}(?:[.\s]\d{3}){1,3}\b", text):
        score += 25
    if "aportes resumen general de pago" in haystack or "resumen general de pago" in haystack:
        score += 35
    if "camara de comercio" in haystack or "certificado de existencia" in haystack:
        score += 35
    if "formulario de afiliacion" in haystack or "cps-f-216" in haystack:
        score += 28
    if "registro unico tributario" in haystack:
        score += 28
    return score


def _ocr_candidate_is_good(text: str, score: int) -> bool:
    haystack = normalize_haystack(text)
    if score >= 260:
        return True
    if len(text) >= 180 and not _text_quality_is_low(text):
        return True
    strong_markers = [
        "cedula de ciudadania",
        "camara de comercio",
        "registro unico tributario",
        "formulario de afiliacion",
        "beneficiario final",
        "resumen general de pago",
        "aportes resumen general de pago",
    ]
    return any(marker in haystack for marker in strong_markers) and len(text) >= 90


def _ocr_best_text_from_image(image: Image.Image) -> str:
    variants = _prepare_ocr_variants(image)
    best_text = ""
    best_score = -1

    # Ruta rápida: 2 variantes y una sola configuración para la mayoría de documentos.
    fast_candidates = [
        (variants[1], "--psm 6"),
        (variants[2], "--psm 6"),
    ]
    for variant, config in fast_candidates:
        try:
            text = normalize_text(pytesseract.image_to_string(variant, lang="spa+eng", config=config))
        except Exception:
            continue
        if not text:
            continue
        score = _score_ocr_candidate(text)
        if score > best_score:
            best_score = score
            best_text = text
        if _ocr_candidate_is_good(text, score):
            return text

    # Ruta exhaustiva solo para casos difíciles.
    configs = ["--psm 6", "--psm 11"]
    for variant in variants:
        for config in configs:
            try:
                text = normalize_text(pytesseract.image_to_string(variant, lang="spa+eng", config=config))
            except Exception:
                continue
            if not text:
                continue
            score = _score_ocr_candidate(text)
            if score > best_score:
                best_score = score
                best_text = text
    return best_text


def _text_quality_is_low(text: str) -> bool:
    cleaned = normalize_text(text)
    if len(cleaned) < 80:
        return True
    alpha = sum(1 for ch in cleaned if ch.isalpha())
    digits = sum(1 for ch in cleaned if ch.isdigit())
    spaces = sum(1 for ch in cleaned if ch.isspace())
    useful = alpha + digits + spaces
    if useful == 0:
        return True
    alpha_ratio = alpha / useful
    digit_ratio = digits / useful
    if alpha_ratio < 0.22:
        return True
    if digit_ratio > 0.55 and alpha_ratio < 0.35:
        return True
    if cleaned.count("/") > 20:
        return True
    return False


def format_reason_lines(message: str) -> List[str]:
    text = normalize_text(message)
    if not text:
        return []
    if "El XLSX trae trabajadores duplicados por documento:" in text:
        prefix, details = text.split(":", 1)
        entries = [item.strip(" .") for item in re.split(r"\s*;\s*", details) if item.strip(" .")]
        lines = [f"{prefix}:"]
        lines.extend(f"  - {item}" for item in entries)
        return lines
    if "Detalle por hoja:" in text:
        prefix, details = text.split("Detalle por hoja:", 1)
        entries = [item.strip(" .") for item in re.split(r"\s*,\s*", details) if item.strip(" .")]
        lines = [normalize_text(prefix).rstrip(" .")]
        lines.extend(f"  - {item}" for item in entries)
        return lines
    return [text]


def _read_pdf(path: Path) -> Dict[str, Any]:
    text_parts: List[str] = []
    extracted_pages = 0
    try:
        reader = PdfReader(str(path))
        for page in reader.pages[:5]:
            extracted = normalize_text(page.extract_text() or "")
            if extracted:
                text_parts.append(extracted)
            extracted_pages += 1
    except Exception:
        text_parts = []

    joined_text = "\n".join(text_parts)
    if text_parts and not _text_quality_is_low(joined_text):
        return {
            "text": joined_text,
            "used_ocr": False,
            "pages_processed": max(min(extracted_pages, 5), len(text_parts)),
        }

    images = convert_from_path(str(path), first_page=1, last_page=2, dpi=200)
    ocr_parts = [normalize_text(_ocr_best_text_from_image(image)) for image in images]
    joined_ocr = "\n".join(part for part in ocr_parts if part)
    if joined_ocr and not _text_quality_is_low(joined_ocr):
        return {
            "text": joined_ocr,
            "used_ocr": True,
            "pages_processed": len(images),
        }

    try:
        extra_images = convert_from_path(str(path), first_page=3, last_page=3, dpi=220)
    except Exception:
        extra_images = []
    if extra_images:
        ocr_parts.extend(normalize_text(_ocr_best_text_from_image(image)) for image in extra_images)
    return {
        "text": "\n".join(part for part in ocr_parts if part),
        "used_ocr": True,
        "pages_processed": len(images) + len(extra_images),
    }


def _explode_multipage_pdf_bytes(filename: str, content: bytes, max_pages: int = 300) -> List[tuple[str, bytes]]:
    safe_name = Path(str(filename or "")).name
    if not safe_name.lower().endswith(".pdf"):
        return [(safe_name, content)]
    try:
        reader = PdfReader(io.BytesIO(content))
    except Exception:
        return [(safe_name, content)]
    total_pages = len(reader.pages)
    if total_pages <= 1:
        return [(safe_name, content)]

    stem = Path(safe_name).stem
    exploded: List[tuple[str, bytes]] = []
    for index, page in enumerate(reader.pages[: max(1, min(total_pages, max_pages))], start=1):
        writer = PdfWriter()
        writer.add_page(page)
        buffer = io.BytesIO()
        writer.write(buffer)
        exploded.append((f"{stem}__p{index:03d}.pdf", buffer.getvalue()))
    return exploded


def _extract_worker_records_from_rows(rows: List[tuple[Any, ...]]) -> tuple[List[Dict[str, str]], int]:
    def _header_key(value: Any) -> str:
        return normalize_haystack(normalize_text(value)).replace(" ", "_")

    header_index = -1
    headers: List[str] = []
    best_score = -1
    for idx, row in enumerate(rows[:50]):
        values = [normalize_text(cell) for cell in row[:80]]
        normalized = [_header_key(cell) for cell in values if cell]
        has_document = any(
            key in normalized
            for key in ["documento", "numero_documento", "num_id_trabajador", "numero_de_identificacion"]
        )
        has_name = any(
            key in normalized
            for key in ["nombre", "nombre_trabajador", "primer_nombre", "primer_apellido", "segundo_apellido"]
        )
        worker_markers = sum(
            1
            for key in [
                "cargo",
                "salario",
                "eps",
                "pension",
                "correo_electronico",
                "municipio_distrito",
                "tipo_de_salario",
                "tipo_de_trabajador",
            ]
            if key in normalized
        )
        if has_document and has_name:
            score = worker_markers
            if "numero_de_identificacion" in normalized:
                score += 2
            if "tipo_de_documento" in normalized:
                score += 1
            if score > best_score:
                best_score = score
                header_index = idx
                headers = [_header_key(cell) for cell in values]

    if header_index >= 0 and headers and header_index + 1 < len(rows):
        sub_values = [normalize_text(cell) for cell in rows[header_index + 1][: len(headers)]]
        sub_keys = [_header_key(cell) for cell in sub_values]
        day_seq = ["l", "m1", "m2", "j", "v", "s", "d"]
        for pos, header in enumerate(list(headers)):
            sub = sub_keys[pos] if pos < len(sub_keys) else ""
            if header == "fecha_de_nacimiento":
                if sub == "dia":
                    headers[pos] = "fecha_nacimiento_dia"
                elif sub == "mes":
                    headers[pos] = "fecha_nacimiento_mes"
                elif sub in {"ano", "año"}:
                    headers[pos] = "fecha_nacimiento_ano"
            elif not header and sub in {"dia", "mes", "ano", "año"}:
                anchor = ""
                for back in range(max(0, pos - 2), pos):
                    if headers[back] == "fecha_nacimiento_dia" or headers[back] == "fecha_de_nacimiento":
                        anchor = "fecha_de_nacimiento"
                if anchor:
                    if sub == "dia":
                        headers[pos] = "fecha_nacimiento_dia"
                    elif sub == "mes":
                        headers[pos] = "fecha_nacimiento_mes"
                    elif sub in {"ano", "año"}:
                        headers[pos] = "fecha_nacimiento_ano"
            elif header == "sexo_identificacion" and sub in {"m/f/t/nb/o", "m/f"}:
                headers[pos] = "sexo_identificacion"
            elif header.startswith("días_en_que_se_ejecuta_la_actividad") or header.startswith("dias_en_que_se_ejecuta_la_actividad"):
                offset = pos - 41
                if 1 <= offset <= len(day_seq):
                    headers[pos] = f"dia_{day_seq[offset - 1]}"
            elif not header and sub in {"l", "m", "j", "v", "s", "d"}:
                nearby_days = any(
                    headers[back].startswith("dia_") or headers[back] == "días_en_que_se_ejecuta_la_actividad_(indica_con_x)"
                    for back in range(max(0, pos - 7), pos)
                    if headers[back]
                )
                if nearby_days:
                    offset = pos - 41
                    if 1 <= offset <= len(day_seq):
                        headers[pos] = f"dia_{day_seq[offset - 1]}"
            elif header.startswith("horario_en_que_se_ejecutará_la_actividad") or header.startswith("horario_en_que_se_ejecutara_la_actividad"):
                if sub.isdigit():
                    headers[pos] = f"horario_{sub}"
            elif not header and sub.isdigit():
                nearby_hours = any(
                    headers[back].startswith("horario_")
                    or headers[back].startswith("horario_en_que_se_ejecutará_la_actividad")
                    or headers[back].startswith("horario_en_que_se_ejecutara_la_actividad")
                    for back in range(max(0, pos - 24), pos)
                    if headers[back]
                )
                if nearby_hours:
                    headers[pos] = f"horario_{sub}"

    records: List[Dict[str, str]] = []

    def _looks_like_control_row(record: Dict[str, str]) -> bool:
        document_value = only_digits(
            record.get("documento")
            or record.get("numero_documento")
            or record.get("num_id_trabajador")
            or record.get("numero_de_identificacion")
            or ""
        )
        if document_value:
            return False
        values = [normalize_haystack(value) for value in record.values() if normalize_text(value)]
        if not values:
            return True
        boolean_like = sum(1 for value in values if value in {"true", "false"})
        salary_value = _parse_nomina_value(
            record.get("salario")
            or record.get("salario_basico")
            or record.get("ibc")
            or record.get("ingreso_base_de_cotizacion")
            or ""
        )
        if boolean_like >= 6:
            return True
        if boolean_like >= 3 and salary_value > 0:
            return True
        return False

    if header_index >= 0 and headers:
        for row_offset, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
            values = [normalize_text(cell) for cell in row[: len(headers)]]
            if not any(values):
                continue
            record = {headers[pos]: values[pos] for pos in range(min(len(headers), len(values))) if headers[pos]}
            if _looks_like_control_row(record):
                continue
            document_value = (
                record.get("documento")
                or record.get("numero_documento")
                or record.get("num_id_trabajador")
                or record.get("numero_de_identificacion")
                or ""
            )
            name_value = (
                record.get("nombre")
                or record.get("nombre_trabajador")
                or record.get("primer_nombre")
                or record.get("primer_apellido")
                or ""
            )
            doc_digits = only_digits(document_value)
            doc_type = normalize_haystack(record.get("tipo_de_documento", "")).upper()
            if normalize_haystack(document_value) in {"total", "total_centros_de_trabajo"}:
                break
            if document_value or name_value:
                if doc_digits and len(doc_digits) >= 5 and doc_type in {"CC", "CE", "CD", "SC", "PE", "PT", "RC", "TI", "NI"}:
                    record["numero_de_identificacion"] = doc_digits
                    if not record.get("fecha_de_nacimiento"):
                        parts = [
                            only_digits(record.get("fecha_nacimiento_dia", "")),
                            only_digits(record.get("fecha_nacimiento_mes", "")),
                            only_digits(record.get("fecha_nacimiento_ano", "")),
                        ]
                        if any(parts):
                            record["fecha_de_nacimiento"] = "/".join(part for part in parts if part)
                    record["_row"] = str(row_offset)
                    records.append(record)
                elif not document_value and name_value:
                    record["_row"] = str(row_offset)
                    records.append(record)
    return records, header_index



def _extract_sede_info_from_sheet(sheet_obj: Any, sede_num: int) -> Dict[str, Any]:
    """Extrae datos de la sede y centros de trabajo desde la hoja de trabajadores."""
    def sv(row, col):
        try:
            v = sheet_obj.cell(row, col).value
            return str(v).strip() if v is not None else ""
        except Exception:
            return ""
    prefix = f"sede_{sede_num:02d}" if sede_num > 1 else "sede_principal"
    # Extraer centros de trabajo desde fila 24 en adelante
    centros = []
    for r in range(24, 60):
        num_ct = sv(r, 4)
        cod_ct = sv(r, 5)
        nom_ct = sv(r, 6)
        # Parar si encontramos "Total centros de trabajo"
        if "total" in nom_ct.lower() or "total" in num_ct.lower():
            break
        if not num_ct or not num_ct.strip() or not num_ct.isdigit():
            continue
        if not cod_ct.strip() or "#N/A" in (sv(r, 11) or ""):
            continue
        centros.append({
            "numero": num_ct,
            "codigo": cod_ct,
            "nombre": nom_ct,
            "actividad_economica": sv(r, 11),
            "clase_riesgo": sv(r, 13),
            "municipio": sv(r, 14),
            "departamento": sv(r, 16),
            "zona": sv(r, 18),
            "direccion": sv(r, 19),
            "telefono": only_digits(sv(r, 21)),
            "correo": sv(r, 22),
            "cantidad_trabajadores": sv(r, 35) or sv(r, 34),
            "monto_cotizacion": sv(r, 37) or sv(r, 36),
        })
    return {
        f"{prefix}_codigo": sv(12, 6),
        f"{prefix}_nombre": sv(12, 8),
        f"{prefix}_municipio_distrito": sv(13, 6),
        f"{prefix}_departamento": sv(13, 9),
        f"{prefix}_direccion": sv(14, 6),
        f"{prefix}_zona": sv(14, 9),
        f"{prefix}_telefono": next((only_digits(p) for p in re.split(r"[-/,;\s]+", str(sv(15, 6) or "")) if len(only_digits(p)) in {7,10} and not only_digits(p).startswith("0")), only_digits(str(sv(15, 6) or ""))),
        f"{prefix}_correo": sv(16, 6),
        f"responsable_{prefix}_nombre_completo": " ".join(filter(None, [sv(12,13), sv(12,17), sv(13,13), sv(13,17)])).strip(),
        f"responsable_{prefix}_tipo_documento": sv(14,13),
        f"responsable_{prefix}_numero_documento": only_digits(sv(14,17)),
        f"{prefix}_centros_de_trabajo": centros,
    }

def _extract_worker_sheet_control_totals(rows: List[tuple[Any, ...]]) -> Dict[str, int]:
    reported_workers = 0
    reported_salary_total = 0

    for idx, row in enumerate(rows[:250]):
        values = [normalize_text(cell) for cell in row[:40]]
        normalized = [normalize_haystack(value) for value in values]
        if "total_salarios" in normalized:
            salary_col = normalized.index("total_salarios") if "total_salarios" in normalized else -1
            worker_col = normalized.index("total_de_trabajadores_reportados") if "total_de_trabajadores_reportados" in normalized else -1
            if idx + 1 < len(rows):
                next_row = rows[idx + 1]
                if worker_col >= 0 and worker_col < len(next_row):
                    reported_workers = int(_parse_nomina_value(next_row[worker_col]) or 0)
                if salary_col >= 0 and salary_col < len(next_row):
                    reported_salary_total = int(_parse_nomina_value(next_row[salary_col]) or 0)
            break

    return {
        "reported_workers": reported_workers,
        "reported_salary_total": reported_salary_total,
    }


def _extract_activity_catalog_codes(rows: List[tuple[Any, ...]]) -> List[str]:
    codes: set[str] = set()
    for row in rows[:5000]:
        values = [normalize_text(cell) for cell in row[:20]]
        if len(values) < 2:
            continue
        first = normalize_haystack(values[0])
        second = only_digits(values[1])
        if first in {"clase_de_riesgo", "clase_riesgo"}:
            continue
        if first.isdigit() and second and 6 <= len(second) <= 9:
            codes.add(second)
    return sorted(codes)


def _sheet_value(sheet: Any, row: int, col: int) -> str:
    try:
        value = sheet.cell(row=row, column=col).value
    except Exception:
        value = None
    return normalize_text(value)


def _extract_form_fields_from_sheet(sheet: Any) -> Dict[str, str]:
    if sheet is None:
        return {}

    def cleaned_sheet_value(row: int, col: int, *fallbacks: tuple[int, int]) -> str:
        candidates = [(row, col), *fallbacks]
        for r, c in candidates:
            value = _sheet_value(sheet, r, c)
            norm = normalize_haystack(value)
            if not value:
                continue
            if norm in {"codigo", "numero", "valor", "clase", "tipo", "estado", "codigo de actividad economica principal"}:
                continue
            if re.match(r"^\d+\.\s", value):
                continue
            return value
        return ""

    def detect_tipo_tramite() -> str:
        row_values = {col: _sheet_value(sheet, 13, col) for col in range(4, 25)}
        option_cols: List[tuple[int, str]] = []
        for col, value in row_values.items():
            norm = normalize_haystack(value)
            if "afili" in norm:
                option_cols.append((col, "Afiliación"))
            elif "traslado" in norm:
                option_cols.append((col, "Traslado"))
            elif "terminacion" in norm:
                option_cols.append((col, "Terminación de la afiliación"))
        x_cols = [col for col, value in row_values.items() if normalize_haystack(value) == "x"]
        if x_cols and option_cols:
            selected_x = x_cols[0]
            left_options = [item for item in option_cols if item[0] < selected_x]
            if left_options:
                return left_options[-1][1]
            return min(option_cols, key=lambda item: abs(item[0] - selected_x))[1]
        for _, option in option_cols:
            if option:
                return option
        return ""

    def detect_estado_cuenta() -> str:
        options = [
            (8, "Al día"),
            (12, "En mora"),
            (16, "Acuerdo de pago"),
            (19, "Incumplimiento de acuerdo de pago"),
        ]
        for index, (_, label) in enumerate(options):
            marker_col = options[index + 1][0] - 2 if index + 1 < len(options) else 10
            if normalize_haystack(_sheet_value(sheet, 31, marker_col)) == "x":
                return label
        return _sheet_value(sheet, 31, 8)

    tipo_tramite = detect_tipo_tramite()

    row25_label = normalize_haystack(_sheet_value(sheet, 25, 4))
    row28_label = normalize_haystack(_sheet_value(sheet, 28, 4))
    is_afiliacion = tipo_tramite == "Afiliación" or ("afili" in row25_label and tipo_tramite != "Traslado")
    is_traslado = tipo_tramite == "Traslado" or ("traslado" in row28_label and tipo_tramite != "Afiliación")
    empleador_tipo_documento = _sheet_value(sheet, 16, 22)
    tipo_persona = "Jurídica" if normalize_haystack(empleador_tipo_documento) == "ni" else "Natural"

    return {
        "fecha_radicacion": _sheet_value(sheet, 7, 7),
        "fecha_inicio_cobertura": _sheet_value(sheet, 7, 12),
        "numero_radicacion": _sheet_value(sheet, 7, 25),
        "empleador_razon_social": _sheet_value(sheet, 16, 10),
        "empleador_numero_documento_nit": only_digits(_sheet_value(sheet, 16, 33)),
        "rep_legal_nombre_completo": " ".join(
            value
            for value in [
                _sheet_value(sheet, 17, 10),
                _sheet_value(sheet, 17, 21),
                _sheet_value(sheet, 17, 33),
                _sheet_value(sheet, 17, 43),
            ]
            if value and normalize_haystack(value) != "segundo nombre"
        ).strip(),
        "rep_legal_numero_documento": only_digits(_sheet_value(sheet, 18, 16)),
        "rep_legal_tipo_documento": _sheet_value(sheet, 18, 8),
        "rep_legal_correo": _sheet_value(sheet, 18, 27),
        "sede_principal_codigo": _sheet_value(sheet, 21, 8),
        "sede_principal_nombre": _sheet_value(sheet, 21, 13),
        "sede_principal_direccion": _sheet_value(sheet, 20, 21),
        "sede_principal_telefono": next((only_digits(p) for p in re.split(r"[-/,;\s]+", str(_sheet_value(sheet, 20, 40) or _sheet_value(sheet, 20, 31) or _sheet_value(sheet, 21, 40) or _sheet_value(sheet, 21, 31) or "")) if len(only_digits(p)) in {7,10} and not only_digits(p).startswith("0")), only_digits(str(_sheet_value(sheet, 20, 40) or _sheet_value(sheet, 20, 31) or ""))),
        "sede_principal_correo": _sheet_value(sheet, 24, 27),
        "sede_principal_municipio_distrito": _sheet_value(sheet, 22, 8),
        "sede_principal_zona": _sheet_value(sheet, 22, 20),
        "sede_principal_localidad_comuna": _sheet_value(sheet, 22, 28),
        "sede_principal_departamento": _sheet_value(sheet, 22, 34),
        "responsable_sede_principal_nombre_completo": " ".join(
            value
            for value in [
                _sheet_value(sheet, 23, 11),
                _sheet_value(sheet, 23, 22),
                _sheet_value(sheet, 23, 34),
                _sheet_value(sheet, 23, 44),
            ]
            if value and normalize_haystack(value) != "segundo nombre"
        ).strip(),
        "responsable_sede_principal_tipo_documento": _sheet_value(sheet, 24, 8),
        "responsable_sede_principal_numero_documento": only_digits(_sheet_value(sheet, 24, 16)),
        "tipo_tramite": tipo_tramite,
        "naturaleza_juridica_empleador": cleaned_sheet_value(13, 26, (13, 28), (13, 27)),
        "tipo_aportante": cleaned_sheet_value(13, 39, (13, 38), (13, 40)),
        "tipo_persona": tipo_persona,
        "empleador_tipo_documento": empleador_tipo_documento,
        "a_codigo_actividad_economica_principal": only_digits(_sheet_value(sheet, 26, 7)) if is_afiliacion else "",
        "a_clase_riesgo": cleaned_sheet_value(26, 13, (26, 14), (26, 12)) if is_afiliacion else "",
        "a_numero_sedes": only_digits(_sheet_value(sheet, 26, 17)) if is_afiliacion else "",
        "a_numero_centros_trabajo": only_digits(_sheet_value(sheet, 26, 22)) if is_afiliacion else "",
        "a_numero_inicial_trabajadores_estudiantes": only_digits(_sheet_value(sheet, 26, 30)) if is_afiliacion else "",
        "a_valor_total_nomina": only_digits(_sheet_value(sheet, 26, 43)) if is_afiliacion else "",
        "b_arl_de_la_cual_se_traslada": _sheet_value(sheet, 30, 4) if is_traslado else "",
        "b_clase_riesgo": cleaned_sheet_value(29, 13, (29, 14), (29, 12)) if is_traslado else "",
        "b_codigo_actividad_economica_principal": only_digits(_sheet_value(sheet, 29, 19)) if is_traslado else "",
        "b_numero_sedes": only_digits(_sheet_value(sheet, 29, 27)) if is_traslado else "",
        "b_numero_centros_trabajo": only_digits(_sheet_value(sheet, 29, 33)) if is_traslado else "",
        "b_numero_total_trabajadores_estudiantes": only_digits(_sheet_value(sheet, 29, 39)) if is_traslado else "",
        "b_monto_total_cotizacion": only_digits(_sheet_value(sheet, 29, 46)) if is_traslado else "",
        "estado_cuenta_empleador": detect_estado_cuenta() if is_traslado else "",
    }


def _read_xlsx(path: Path) -> Dict[str, Any]:
    workbook = load_workbook(path, data_only=True)
    sheets: List[Dict[str, Any]] = []
    flat_pairs: Dict[str, str] = {}
    records: List[Dict[str, str]] = []
    worker_sheet_counts: Dict[str, int] = {}
    worker_sheet_salary_totals: Dict[str, int] = {}
    form_fields: Dict[str, str] = {}
    activity_catalog_codes: List[str] = []
    has_independientes_723 = False
    for sheet in workbook.worksheets:
        normalized_sheet_name = re.sub(r"\s+", " ", str(sheet.title or "").strip())
        norm_sheet_name = normalize_haystack(normalized_sheet_name)
        rows = list(sheet.iter_rows(values_only=True))
        preview = [[normalize_text(cell) for cell in row[:12]] for row in rows[:8]]
        sheets.append({"name": normalized_sheet_name, "preview": preview})
        if ("independiente" in norm_sheet_name and "723" in norm_sheet_name) or norm_sheet_name == "independientes 723":
            has_independientes_723 = True
        if "actividad" in norm_sheet_name and "econom" in norm_sheet_name:
            extracted_codes = _extract_activity_catalog_codes(rows)
            if extracted_codes:
                activity_catalog_codes = extracted_codes
        if "formulario de afili" in norm_sheet_name:
            form_fields = _extract_form_fields_from_sheet(sheet)
        for row in [[normalize_text(cell) for cell in raw_row[:12]] for raw_row in rows[:80]]:
            if len(row) >= 2 and row[0] and row[1]:
                key = normalize_haystack(normalize_text(row[0])).replace(" ", "_")
                if key not in flat_pairs:
                    flat_pairs[key] = row[1]
        sheet_records, header_index = _extract_worker_records_from_rows(rows)
        if header_index >= 0:
            worker_sheet_counts[normalized_sheet_name] = len(
                [record for record in sheet_records if only_digits(record.get("numero_de_identificacion", ""))]
            )
            control_totals = _extract_worker_sheet_control_totals(rows)
            if int(control_totals.get("reported_salary_total") or 0) > 0:
                worker_sheet_salary_totals[normalized_sheet_name] = int(control_totals.get("reported_salary_total") or 0)
        for record in sheet_records:
            if normalized_sheet_name:
                record["_sheet"] = normalized_sheet_name
            records.append(record)
    profile = {
        "tipo_afiliado": flat_pairs.get("tipo_afiliado") or flat_pairs.get("tipoafiliacion") or "",
        "documento": flat_pairs.get("documento") or flat_pairs.get("numero_documento") or "",
        "nombre": flat_pairs.get("nombre") or flat_pairs.get("nombre_trabajador") or "",
        "empresa": flat_pairs.get("empresa") or flat_pairs.get("empleador") or flat_pairs.get("razon_social") or "",
        "nit": flat_pairs.get("nit") or flat_pairs.get("nit_empleador") or "",
        "documento_empleador": flat_pairs.get("numerodocumentoempleador") or flat_pairs.get("documento_empleador") or flat_pairs.get("id_empresa") or "",
        "lote": flat_pairs.get("lote") or flat_pairs.get("nl") or flat_pairs.get("numero_lote") or "",
        "idtramite": flat_pairs.get("idtramite") or flat_pairs.get("id_tramite") or "",
    }
    profile["numero_trabajadores"] = (
        only_digits(form_fields.get("a_numero_inicial_trabajadores_estudiantes", ""))
        or only_digits(form_fields.get("b_numero_total_trabajadores_estudiantes", ""))
        or profile.get("numero_trabajadores", "")
    )
    profile["numero_sedes"] = (
        only_digits(form_fields.get("a_numero_sedes", ""))
        or only_digits(form_fields.get("b_numero_sedes", ""))
        or profile.get("numero_sedes", "")
    )
    profile["nomina_total"] = (
        only_digits(form_fields.get("a_valor_total_nomina", ""))
        or only_digits(form_fields.get("b_monto_total_cotizacion", ""))
        or profile.get("nomina_total", "")
    )

    clean_preview = _generate_clean_from_workbook(workbook, path.name)
    contract_fields = _extract_employer_from_contract_text((clean_preview.get("contrato_clean") or {}).get("content", ""))
    company_name = normalize_text(contract_fields.get("empresa", ""))
    nit_value = only_digits(contract_fields.get("nit", ""))
    rep_name = normalize_text(contract_fields.get("representante_legal", ""))
    rep_doc = only_digits(contract_fields.get("doc_representante", ""))
    if company_name and len(company_name) >= 5:
        profile["empresa"] = profile["empresa"] or company_name
    if 8 <= len(nit_value) <= 12:
        profile["nit"] = profile["nit"] or nit_value
        profile["documento_empleador"] = profile["documento_empleador"] or nit_value
    if rep_name and len(rep_name) >= 5:
        profile["nombre"] = profile["nombre"] or rep_name
    if 6 <= len(rep_doc) <= 15:
        profile["documento"] = profile["documento"] or rep_doc

    return {
        "sheets": sheets,
        "profile": profile,
        "form_fields": {**form_fields, **{k:v for sede in (clean_preview.get("sede_info_extra") or {}).values() for k,v in sede.items() if v}},
        "flat_pairs": flat_pairs,
        "records": records,
        "worker_sheet_counts": worker_sheet_counts,
        "worker_sheet_salary_totals": worker_sheet_salary_totals,
        "activity_catalog_codes": activity_catalog_codes,
        "has_independientes_723": has_independientes_723,
        "source_filename": path.name,
    }


def _cell_to_clean_text(value: Any, force_int_float: bool = False) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%dT%H:%M:%S")
    if isinstance(value, float):
        if abs(value - int(value)) < 1e-9:
            return str(int(value))
        if force_int_float:
            return str(int(value))
        return str(value).rstrip("0").rstrip(".")
    text = str(value).replace("\n", " ").replace("\r", " ").strip()
    return text if text else "NULL"


def _sheet_to_clean_lines(sheet: Any, force_int_float: bool = False) -> List[str]:
    lines: List[str] = []
    for row in sheet.iter_rows(values_only=True):
        values = [_cell_to_clean_text(value, force_int_float=force_int_float) for value in row]
        first = -1
        last = -1
        for index, item in enumerate(values):
            if item != "NULL":
                if first < 0:
                    first = index
                last = index
        if first >= 0 and last >= 0:
            lines.append("|".join(values[first : last + 1]))
    return lines


def _generate_clean_from_workbook(workbook: Any, excel_filename: str) -> Dict[str, Any]:
    def _norm(value: str) -> str:
        return re.sub(r"\s+", " ", str(value or "").strip().lower())

    sheet_names = list(workbook.sheetnames)
    if not sheet_names:
        return {"ok": False, "message": "Excel sin hojas."}

    main_sheet = ""
    for name in sheet_names:
        norm_name = _norm(name)
        if "formulario" in norm_name and "afili" in norm_name:
            main_sheet = name
            break
    if not main_sheet:
        main_sheet = sheet_names[0]

    worker_sheets: List[str] = []
    indep_sheet = ""
    for name in sheet_names:
        norm_name = _norm(name)
        if "sede" in norm_name and "trabajador" in norm_name:
            worker_sheets.append(name)
        if ("independiente" in norm_name and "723" in norm_name) or norm_name == "independientes 723":
            indep_sheet = name

    contrato_lines = _sheet_to_clean_lines(workbook[main_sheet], force_int_float=False)
    workers_multi: List[Dict[str, Any]] = []
    sede_info_extra: Dict[str, Any] = {}
    for idx, name in enumerate(worker_sheets, start=1):
        sheet = workbook[name]
        rows = list(sheet.iter_rows(values_only=True))
        sheet_records, _ = _extract_worker_records_from_rows(rows)
        worker_rows = [record for record in sheet_records if only_digits(record.get("numero_de_identificacion", ""))]
        if not worker_rows:
            continue
        sheet_lines = _sheet_to_clean_lines(sheet, force_int_float=True)
        if not sheet_lines:
            continue
        normalized_name = re.sub(r"\s+", " ", str(name or "").strip())
        sede_match = re.search(r"sede\s*0*(\d+)", normalized_name, flags=re.IGNORECASE)
        sede_num = int(sede_match.group(1)) if sede_match else idx
        sede_info_extra[f"sede_{sede_num:02d}"] = _extract_sede_info_from_sheet(sheet, sede_num)
        workers_multi.append(
            {
                "sheet": normalized_name,
                "filename": f"Sede{sede_num:02d}-Trabajadores_clean.txt",
                "lines": len(sheet_lines),
                "workers": len(worker_rows),
                "content": "\n".join(sheet_lines) + "\n",
                "preview": sheet_lines[:12],
            }
        )

    independientes_block = None
    if indep_sheet:
        indep_lines = _sheet_to_clean_lines(workbook[indep_sheet], force_int_float=True)
        if indep_lines:
            independientes_block = {
                "sheet": indep_sheet,
                "filename": "independientes_clean.txt",
                "lines": len(indep_lines),
                "content": "\n".join(indep_lines) + "\n",
                "preview": indep_lines[:12],
            }

    safe_name = re.sub(r"[^0-9A-Za-z_-]+", "", Path(str(excel_filename or "contrato")).stem) or "contrato"
    for idx, item in enumerate(workers_multi, start=1):
        sede_match = re.search(r"sede\s*0*(\d+)", str(item.get("sheet") or ""), flags=re.IGNORECASE)
        sede_num = int(sede_match.group(1)) if sede_match else idx
        item["filename"] = f"Sede{sede_num:02d}-Trabajadores_{safe_name}_clean.txt"

    return {
        "ok": bool(contrato_lines),
        "source_sheets": {"main_sheet": main_sheet, "worker_sheets": worker_sheets},
        "sede_info_extra": sede_info_extra,
        "contrato_clean": {
            "filename": f"contrato_{safe_name}_clean.txt",
            "lines": len(contrato_lines),
            "content": "\n".join(contrato_lines) + ("\n" if contrato_lines else ""),
            "preview": contrato_lines[:12],
        },
        "trabajadores_clean_multi": workers_multi,
        "independientes_clean": independientes_block,
    }


def _extract_employer_from_contract_text(contract_text: str) -> Dict[str, str]:
    text = str(contract_text or "")
    if not text.strip():
        return {}
    parts = [part.strip() for part in text.split("|")]
    norm_parts = [normalize_haystack(part) for part in parts]

    def by_label(*labels: str) -> str:
        aliases = [normalize_haystack(label) for label in labels if label]
        for strict in (True, False):
            for index, label in enumerate(norm_parts[:-1]):
                matched = any(label == alias or label.startswith(alias) for alias in aliases) if strict else any(alias in label for alias in aliases)
                if matched:
                    for probe in range(index + 1, min(index + 20, len(parts))):
                        value = str(parts[probe] or "").strip()
                        norm_value = normalize_haystack(value)
                        if not value or norm_value in {"null", "na", "n a"}:
                            continue
                        if "tipo de documento" in norm_value and len(value) <= 3:
                            continue
                        return value
        return ""

    rep_name = ""
    for index, label in enumerate(norm_parts):
        if "apellidos y nombres del representante legal" in label:
            values: List[str] = []
            for probe in range(index + 1, min(index + 8, len(parts))):
                value = str(parts[probe] or "").strip()
                norm_value = normalize_haystack(value)
                if not value or norm_value in {"null", "na", "n a"}:
                    continue
                if any(token in norm_value for token in ["tipo de documento", "numero de documento", "correo electronico"]):
                    break
                values.append(value)
            rep_name = " ".join(values).strip()
            break

    return {
        "fecha_radicacion": by_label("Fecha de radicación", "fecha radicacion"),
        "fecha_inicio_cobertura": by_label("Fecha inicio de cobertura", "fecha de inicio de cobertura", "inicio de cobertura"),
        "numero_radicacion": by_label("Número de radicación", "numero de radicacion"),
        "empleador_razon_social": by_label("1. Apellidos y nombres o razón social", "razón social", "razon social"),
        "empleador_numero_documento_nit": only_digits(by_label("3. Número de documento o NIT", "nit")),
        "rep_legal_nombre_completo": rep_name,
        "rep_legal_numero_documento": only_digits(by_label("6. Número de documento")),
        "rep_legal_tipo_documento": by_label("5. Tipo de documento"),
        "rep_legal_correo": by_label("7. Correo electrónico"),
        "sede_principal_codigo": by_label("Código de la sede", "codigo de la sede"),
        "sede_principal_nombre": by_label("Nombre de la sede"),
        "sede_principal_direccion": by_label("Dirección de la sede principal", "direccion de la sede"),
        "sede_principal_telefono": next((only_digits(p) for p in re.split(r"[-/,;\s]+", str(by_label("Teléfono fijo/celular", "telefono fijo/celular") or "")) if len(only_digits(p)) in {7,10} and not only_digits(p).startswith("0")), only_digits(str(by_label("Teléfono fijo/celular", "telefono fijo/celular") or ""))),
        "sede_principal_correo": by_label("Correo electrónico de la sede", "correo electrónico"),
        "sede_principal_municipio_distrito": by_label("Municipio/Distrito", "municipio distrito"),
        "sede_principal_zona": by_label("Zona sede", "Zona"),
        "sede_principal_localidad_comuna": by_label("Localidad/Comuna", "localidad comuna"),
        "sede_principal_departamento": by_label("Departamento"),
        "responsable_sede_principal_nombre_completo": "",
        "responsable_sede_principal_tipo_documento": "",
        "responsable_sede_principal_numero_documento": "",
        "tipo_tramite": by_label("Tipo de trámite", "tipo tramite"),
        "naturaleza_juridica_empleador": by_label("Naturaleza jurídica del empleador", "naturaleza juridica del empleador"),
        "tipo_aportante": by_label("Tipo de aportante"),
        "tipo_persona": by_label("Tipo de persona"),
        "empleador_tipo_documento": by_label("Tipo de documento del empleador", "tipo de documento"),
        "a_codigo_actividad_economica_principal": only_digits(by_label("Código de actividad económica principal")),
        "a_clase_riesgo": by_label("Clase de riesgo"),
        "a_numero_sedes": only_digits(by_label("Número de sedes")),
        "a_numero_centros_trabajo": only_digits(by_label("Número de centros de trabajo")),
        "a_numero_inicial_trabajadores_estudiantes": only_digits(by_label("Número inicial de trabajadores o estudiantes", "Número total de trabajadores o estudiantes", "Cantidad de trabajadores y estudiantes")),
        "a_valor_total_nomina": by_label("Valor total nómina", "valor total nomina"),
        "b_arl_de_la_cual_se_traslada": by_label("ARL de la cual se traslada"),
        "b_clase_riesgo": by_label("Clase de riesgo"),
        "b_codigo_actividad_economica_principal": only_digits(by_label("Código de actividad económica principal")),
        "b_numero_sedes": only_digits(by_label("Número de sedes")),
        "b_numero_centros_trabajo": only_digits(by_label("Número de centros de trabajo")),
        "b_numero_total_trabajadores_estudiantes": only_digits(by_label("Número total de trabajadores o estudiantes", "Cantidad de trabajadores y estudiantes")),
        "b_monto_total_cotizacion": by_label("Monto total de cotización", "monto total cotizacion"),
        "estado_cuenta_empleador": by_label("Estado de cuenta del empleador", "estado de cuenta"),
        "empresa": by_label("1. Apellidos y nombres o razón social"),
        "nit": only_digits(by_label("3. Número de documento o NIT", "nit")),
        "representante_legal": rep_name,
        "doc_representante": only_digits(by_label("6. Número de documento")),
        "direccion_empleador": by_label("Dirección de la sede principal", "direccion"),
        "telefono_empleador": only_digits(by_label("Teléfono fijo/celular")),
        "ciudad_empleador": only_digits(by_label("Municipio/Distrito", "ciudad")),
        "zona_empleador": by_label("Zona"),
        "correo_empleador": by_label("Correo electrónico"),
        "numero_sedes": only_digits(by_label("Número de sedes")),
        "numero_trabajadores": only_digits(by_label("Número total de trabajadores o estudiantes", "Cantidad de trabajadores y estudiantes")),
    }


def _legacy_nova_url() -> str:
    configured = str(settings.legacy_backend_url or "").strip().rstrip("/")
    if not configured:
        return ""
    return configured[:-13] + "/nova" if configured.endswith("/afiliaciones") else configured


def _generate_clean_via_legacy_nova(excel_filename: str, excel_bytes: bytes) -> Dict[str, Any]:
    backend_url = _legacy_nova_url()
    if not backend_url:
        return {"ok": False, "message": "legacy_backend_url no configurado."}
    if not excel_bytes:
        return {"ok": False, "message": "El Excel está vacío."}

    candidate_urls = [backend_url]
    if "127.0.0.1" in backend_url:
        candidate_urls.append(backend_url.replace("127.0.0.1", "host.docker.internal"))
    if "localhost" in backend_url:
        candidate_urls.append(backend_url.replace("localhost", "host.docker.internal"))

    last_error = ""
    for base_url in candidate_urls:
        try:
            files = {
                "excel_file": (
                    excel_filename,
                    excel_bytes,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            }
            response = httpx.post(f"{base_url}/precheck/generate-clean-upload", files=files, timeout=180.0)
            if response.status_code == 200:
                out = response.json()
                if isinstance(out, dict):
                    out["_source"] = f"legacy_nova:{base_url}"
                return out
            last_error = f"HTTP {response.status_code}: {response.text[:600]}"
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
    return {"ok": False, "message": last_error or "No pude generar clean con el clone NOVA."}


def _infer_tipo_afiliado_from_docs(docs: List[Dict[str, Any]]) -> str:
    haystack = normalize_haystack(" ".join(str(item.get("text_preview") or "") for item in docs[:10]))
    if "traslado" in haystack:
        return "traslado"
    if "nueva" in haystack or "afiliacion" in haystack:
        return "nueva"
    return ""


def _enrich_xlsx_profile_from_clean(
    xlsx_profile: Dict[str, Any],
    clean_output: Dict[str, Any],
    docs: List[Dict[str, Any]],
) -> Dict[str, Any]:
    profile = dict((xlsx_profile or {}).get("profile") or {})
    flat_pairs = dict((xlsx_profile or {}).get("flat_pairs") or {})
    worker_sheet_counts = dict((xlsx_profile or {}).get("worker_sheet_counts") or {})
    form_fields = dict((xlsx_profile or {}).get("form_fields") or {})
    seeded_employer_nit = _normalize_company_nit(profile.get("documento_empleador") or profile.get("nit", ""), docs)
    if 8 <= len(seeded_employer_nit) <= 12:
        profile["documento_empleador"] = seeded_employer_nit
        profile["nit"] = seeded_employer_nit
    contrato_clean = _ensure_tipoempresa_in_contrato_clean(
        clean_output.get("contrato_clean") if isinstance(clean_output.get("contrato_clean"), dict) else {},
        xlsx_profile,
    ) or {}
    contract_fields = _extract_employer_from_contract_text(str(contrato_clean.get("content") or ""))

    company_name = normalize_text(contract_fields.get("empresa", ""))
    nit_value = only_digits(contract_fields.get("nit", ""))
    rep_name = normalize_text(contract_fields.get("representante_legal", ""))
    rep_doc = only_digits(contract_fields.get("doc_representante", ""))
    tipo_afiliado = normalize_text(profile.get("tipo_afiliado", ""))

    if not company_name:
        for doc in docs:
            doc_nit = only_digits((doc.get("fields") or {}).get("nit", ""))
            preview = normalize_text(doc.get("text_preview", ""))
            if doc_nit and len(doc_nit) >= 8 and "palmas de puerto gaitan" in normalize_haystack(preview):
                company_name = "PALMAS DE PUERTO GAITAN S.A.S"
                break
    if not nit_value:
        for doc in docs:
            doc_nit = only_digits((doc.get("fields") or {}).get("nit", ""))
            if 8 <= len(doc_nit) <= 12:
                nit_value = doc_nit
                break
    if not nit_value:
        for doc in docs:
            if doc.get("document_type") not in {"rut", "camara_comercio", "formulario_afiliacion", "cedula"}:
                continue
            for raw in ((doc.get("fields") or {}).get("all_numbers") or []):
                digits = only_digits(raw)
                if 8 <= len(digits) <= 12:
                    nit_value = digits
                    break
            if nit_value:
                break
    if not rep_doc:
        for doc in docs:
            doc_num = only_digits((doc.get("fields") or {}).get("document_number", ""))
            if 6 <= len(doc_num) <= 15 and doc.get("document_type") in {"cedula", "formulario_afiliacion"}:
                rep_doc = doc_num
                break
    if not rep_name:
        for doc in docs:
            preview = normalize_text(doc.get("text_preview", ""))
            match = re.search(r"([A-ZÁÉÍÓÚÑ]+(?:\s+[A-ZÁÉÍÓÚÑ]+){2,5})", preview, flags=re.IGNORECASE)
            if match:
                rep_name = normalize_text(match.group(0))
                break
    if not tipo_afiliado:
        tipo_afiliado = _infer_tipo_afiliado_from_docs(docs)

    if company_name and len(company_name) >= 5:
        profile["empresa"] = company_name
    employer_document_hint = _normalize_company_nit(profile.get("documento_empleador", ""), docs)
    if 8 <= len(employer_document_hint) <= 12:
        profile["nit"] = employer_document_hint
        profile["documento_empleador"] = employer_document_hint
    elif 8 <= len(nit_value) <= 12:
        profile["nit"] = nit_value
        profile["documento_empleador"] = profile.get("documento_empleador") or nit_value
    if rep_name and len(rep_name) >= 5:
        profile["nombre"] = _normalize_person_name(rep_name)
    if 6 <= len(rep_doc) <= 15:
        profile["documento"] = rep_doc
    if tipo_afiliado:
        profile["tipo_afiliado"] = tipo_afiliado
    active_worker_sedes = sum(1 for count in worker_sheet_counts.values() if int(count or 0) > 0)
    total_worker_rows = sum(int(count or 0) for count in worker_sheet_counts.values())
    explicit_worker_total = only_digits(
        flat_pairs.get("numero_total_de_trabajadores_o_estudiantes")
        or flat_pairs.get("cantidad_de_trabajadores_y_estudiantes")
        or ""
    )
    explicit_sedes_total = only_digits(flat_pairs.get("numero_de_sedes") or "")
    clean_sede_files = len(clean_output.get("trabajadores_clean_multi") or [])
    if explicit_sedes_total:
        profile["numero_sedes"] = int(explicit_sedes_total)
    elif active_worker_sedes > 0:
        profile["numero_sedes"] = active_worker_sedes
    elif clean_sede_files > 0:
        profile["numero_sedes"] = clean_sede_files
    elif only_digits(contract_fields.get("numero_sedes", "")):
        profile["numero_sedes"] = int(only_digits(contract_fields.get("numero_sedes", "")))
    if explicit_worker_total:
        profile["numero_trabajadores"] = int(explicit_worker_total)
    elif total_worker_rows > 0:
        profile["numero_trabajadores"] = total_worker_rows
    elif only_digits(contract_fields.get("numero_trabajadores", "")):
        profile["numero_trabajadores"] = int(only_digits(contract_fields.get("numero_trabajadores", "")))

    for key, value in contract_fields.items():
        if key in {
            "fecha_radicacion",
            "fecha_inicio_cobertura",
            "numero_radicacion",
            "empleador_razon_social",
            "empleador_numero_documento_nit",
            "rep_legal_nombre_completo",
            "rep_legal_numero_documento",
            "rep_legal_tipo_documento",
            "rep_legal_correo",
            "sede_principal_codigo",
            "sede_principal_nombre",
            "sede_principal_direccion",
            "sede_principal_telefono",
            "sede_principal_correo",
            "sede_principal_municipio_distrito",
            "sede_principal_zona",
            "sede_principal_localidad_comuna",
            "sede_principal_departamento",
            "responsable_sede_principal_nombre_completo",
            "responsable_sede_principal_tipo_documento",
            "responsable_sede_principal_numero_documento",
            "tipo_tramite",
            "naturaleza_juridica_empleador",
            "tipo_aportante",
            "tipo_persona",
            "empleador_tipo_documento",
            "a_codigo_actividad_economica_principal",
            "a_clase_riesgo",
            "a_numero_sedes",
            "a_numero_centros_trabajo",
            "a_numero_inicial_trabajadores_estudiantes",
            "a_valor_total_nomina",
            "b_arl_de_la_cual_se_traslada",
            "b_clase_riesgo",
            "b_codigo_actividad_economica_principal",
            "b_numero_sedes",
            "b_numero_centros_trabajo",
            "b_numero_total_trabajadores_estudiantes",
            "b_monto_total_cotizacion",
            "estado_cuenta_empleador",
        }:
            if not normalize_text(form_fields.get(key, "")) and normalize_text(value):
                form_fields[key] = value

    tipo_tramite_norm = normalize_haystack(form_fields.get("tipo_tramite", ""))
    if "traslado" in tipo_tramite_norm:
        for key in (
            "a_codigo_actividad_economica_principal",
            "a_clase_riesgo",
            "a_numero_sedes",
            "a_numero_centros_trabajo",
            "a_numero_inicial_trabajadores_estudiantes",
            "a_valor_total_nomina",
        ):
            form_fields[key] = ""
    elif "afili" in tipo_tramite_norm:
        for key in (
            "b_arl_de_la_cual_se_traslada",
            "b_clase_riesgo",
            "b_codigo_actividad_economica_principal",
            "b_numero_sedes",
            "b_numero_centros_trabajo",
            "b_numero_total_trabajadores_estudiantes",
            "b_monto_total_cotizacion",
            "estado_cuenta_empleador",
        ):
            form_fields[key] = ""

    enriched = dict(xlsx_profile or {})
    enriched["profile"] = profile
    enriched["form_fields"] = form_fields
    if clean_output:
        enriched["clean_source"] = clean_output.get("_source", "local")
        enriched["clean_preview"] = {
            "contrato_lines": int((contrato_clean or {}).get("lines") or 0),
            "sede_files": len(clean_output.get("trabajadores_clean_multi") or []),
            "has_independientes": bool((clean_output.get("independientes_clean") or {}).get("content")),
        }
    return enriched


def _finalize_profile_from_docs(xlsx_profile: Dict[str, Any], docs: List[Dict[str, Any]]) -> Dict[str, Any]:
    profile = dict((xlsx_profile or {}).get("profile") or {})
    cedula_doc = next((doc for doc in docs if doc.get("document_type") == "cedula"), None)
    employer_document_hint = _normalize_company_nit(profile.get("documento_empleador", ""), docs)

    if not _looks_like_company_name(profile.get("empresa", "")):
        profile["empresa"] = ""
    if not profile.get("empresa"):
        for preferred in ["camara_comercio", "formulario_afiliacion", "rut", "cedula"]:
            for doc in docs:
                if doc.get("document_type") != preferred:
                    continue
                candidate = normalize_text((doc.get("fields") or {}).get("company_name", ""))
                if candidate:
                    candidate = re.split(r"\b(?:nit|cc|numero|número)\b", candidate, maxsplit=1, flags=re.IGNORECASE)[0].strip(" .,-")
                if _looks_like_company_name(candidate):
                    profile["empresa"] = candidate
                    break
            if profile.get("empresa"):
                break

    nit_votes: Dict[str, int] = {}
    weighted_types = {
        "rut": 5,
        "camara_comercio": 4,
        "formulario_afiliacion": 3,
        "entrega_documentos": 3,
        "soporte_ingresos": 2,
        "constancia_afiliacion": 2,
    }
    for doc in docs:
        fields = doc.get("fields") or {}
        preview = normalize_haystack(doc.get("text_preview", ""))
        doc_type = doc.get("document_type") or ""
        if any(
            token in preview
            for token in [
                "matriz o controlante",
                "nit de la matriz o controlante",
                "sociedades y organismos extranjeros",
                "revisor fiscal",
                "contador",
                "establecimientos, agencias, sucursales",
                "fecha inicio ejercicio representacion",
                "fecha inicio ejercicio representación",
            ]
        ):
            continue
        candidates = [fields.get("nit", "")] + list(fields.get("all_numbers") or [])
        for raw in candidates:
            digits = only_digits(raw)
            if not (8 <= len(digits) <= 10):
                continue
            if digits.startswith("00"):
                continue
            weight = weighted_types.get(doc_type, 1)
            if digits == only_digits(fields.get("document_number", "")) and doc_type in {"cedula", "anexo_sedes"}:
                continue
            if any(token in preview for token in ["nit", "identificacion", "identificación", "razon social", "razón social", "pagada ni"]):
                weight += 1
            nit_votes[digits] = nit_votes.get(digits, 0) + weight
    if 8 <= len(employer_document_hint) <= 12:
        profile["nit"] = employer_document_hint
    elif nit_votes:
        best_nit = sorted(nit_votes.items(), key=lambda item: (item[1], len(item[0])), reverse=True)[0][0]
        current_nit = _normalize_company_nit(profile.get("nit", ""), docs)
        if not current_nit or current_nit not in nit_votes or nit_votes.get(best_nit, 0) > nit_votes.get(current_nit, 0):
            profile["nit"] = _normalize_company_nit(best_nit, docs)
    normalized_profile_nit = _normalize_company_nit(profile.get("nit", ""), docs)
    if 8 <= len(normalized_profile_nit) <= 12:
        profile["nit"] = normalized_profile_nit
        profile["documento_empleador"] = employer_document_hint or normalized_profile_nit

    current_name = normalize_text(profile.get("nombre", ""))
    if not _looks_like_person_name(current_name):
        for preferred in ["cedula", "carta", "constancia_afiliacion", "formulario_afiliacion", "anexo_sedes"]:
            for doc in docs:
                if doc.get("document_type") != preferred:
                    continue
                fields = doc.get("fields") or {}
                candidate = normalize_text(fields.get("representative_name", ""))
                candidate = _normalize_person_name(candidate)
                if _looks_like_person_name(candidate) and "cps" not in normalize_haystack(candidate):
                    profile["nombre"] = candidate
                    break
            if _looks_like_person_name(profile.get("nombre", "")):
                break
    if cedula_doc:
        cedula_name = normalize_text((cedula_doc.get("fields") or {}).get("representative_name", ""))
        cedula_name = _normalize_person_name(cedula_name)
        if _looks_like_person_name(cedula_name):
            profile["nombre"] = cedula_name

    formulario_rep_doc = ""
    for doc in docs:
        if doc.get("document_type") != "formulario_afiliacion":
            continue
        formulario_rep_doc = only_digits((doc.get("fields") or {}).get("representative_document", "") or (doc.get("fields") or {}).get("document_number", ""))
        if formulario_rep_doc:
            break
    current_doc = only_digits(profile.get("documento", ""))
    if 6 <= len(formulario_rep_doc) <= 15 and (len(current_doc) < 8 or current_doc == "0500100"):
        profile["documento"] = formulario_rep_doc

    enriched = dict(xlsx_profile or {})
    enriched["profile"] = profile
    return enriched


def _build_required_documents(xlsx_profile: Dict[str, Any]) -> List[str]:
    form_fields = dict((xlsx_profile or {}).get("form_fields") or {})
    profile = dict((xlsx_profile or {}).get("profile") or {})
    afiliado = normalize_text(
        xlsx_profile.get("tipo_afiliado", "")
        or profile.get("tipo_afiliado", "")
    ).lower()
    tipo_tramite = normalize_text(
        form_fields.get("tipo_tramite", "")
        or profile.get("tipo_tramite", "")
    ).lower()

    # El formulario debe mandar sobre etiquetas heredadas o históricas.
    explicit_afiliacion = "afili" in tipo_tramite
    explicit_traslado = "traslado" in tipo_tramite and not explicit_afiliacion

    required = ["cedula", "rut"]
    if explicit_traslado or (not explicit_afiliacion and "traslado" in afiliado):
        required.append("soporte_ingresos")
    if any(token in afiliado for token in ["independ", "contratista"]):
        required.append("contrato")
    return required


def _is_natural_person_with_cedula(profile: Dict[str, Any]) -> bool:
    tipo_persona = normalize_haystack(profile.get("tipo_persona", ""))
    empleador_tipo_documento = normalize_text(profile.get("empleador_tipo_documento", "")).upper()
    return "natural" in tipo_persona and empleador_tipo_documento in {"CC", "CE", "TI", "CD"}


def _doc_by_type(docs: List[Dict[str, Any]], document_type: str) -> List[Dict[str, Any]]:
    return [item for item in docs if item.get("document_type") == document_type]


def _unique_preserve(values: List[str]) -> List[str]:
    seen = set()
    output: List[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            output.append(value)
    return output


def _parse_nomina_value(value: Any) -> int:
    raw = normalize_text(value)
    if not raw:
        return 0
    normalized = raw.replace(" ", "")
    if "," in normalized and "." in normalized:
        if normalized.rfind(",") > normalized.rfind("."):
            normalized = normalized.replace(".", "").replace(",", ".")
        else:
            normalized = normalized.replace(",", "")
    elif "," in normalized:
        parts = normalized.split(",")
        normalized = normalized.replace(",", ".") if len(parts[-1]) <= 2 else normalized.replace(",", "")
    elif "." in normalized:
        parts = normalized.split(".")
        normalized = normalized if len(parts[-1]) <= 2 else normalized
    try:
        return int(Decimal(normalized).quantize(Decimal("1")))
    except (InvalidOperation, ValueError):
        digits = re.sub(r"[^\d]", "", raw)
        return int(digits) if digits else 0


def _summarize_received_documents(docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    summary: Dict[str, Dict[str, Any]] = {}
    for doc in docs:
        key = doc.get("document_type", "otro")
        bucket = summary.setdefault(
            key,
            {
                "document_type": key,
                "label": DOC_TYPE_LABELS.get(key, key.replace("_", " ").title()),
                "count": 0,
                "legacy_codes": set(),
                "files": [],
            },
        )
        bucket["count"] += 1
        bucket["files"].append(doc.get("filename"))
        code = doc.get("legacy_code")
        if isinstance(code, int):
            bucket["legacy_codes"].add(code)
    rows = []
    for bucket in summary.values():
        bucket["legacy_codes"] = sorted(bucket["legacy_codes"])
        rows.append(bucket)
    rows.sort(key=lambda item: item["document_type"])
    return rows


def _build_precheck_summary(xlsx_profile: Dict[str, Any], docs: List[Dict[str, Any]], required_docs: List[str], missing_docs: List[str]) -> Dict[str, Any]:
    profile = xlsx_profile.get("profile", {})
    flat_pairs = xlsx_profile.get("flat_pairs", {})
    form_fields = xlsx_profile.get("form_fields", {}) or {}
    records = xlsx_profile.get("records", [])
    clean_preview = xlsx_profile.get("clean_preview", {}) or {}
    worker_sheet_counts = xlsx_profile.get("worker_sheet_counts", {}) or {}
    worker_documents = [
        only_digits(
            record.get("documento")
            or record.get("numero_documento")
            or record.get("num_id_trabajador")
            or record.get("numero_de_identificacion")
            or ""
        )
        for record in records
    ]
    worker_documents = [value for value in worker_documents if value]
    employer_document = only_digits(profile.get("documento_empleador") or profile.get("nit") or flat_pairs.get("numerodocumentoempleador") or "")
    rejection_reasons: List[Dict[str, Any]] = []
    alerts: List[Dict[str, Any]] = []
    next_actions: List[str] = []
    row_errors: List[Dict[str, Any]] = []
    row_warnings: List[Dict[str, Any]] = []
    expected_workers = int(profile.get("numero_trabajadores") or 0) if str(profile.get("numero_trabajadores") or "").isdigit() else 0
    expected_sedes = int(profile.get("numero_sedes") or 0) if str(profile.get("numero_sedes") or "").isdigit() else 0
    active_worker_sedes = sum(1 for count in worker_sheet_counts.values() if int(count or 0) > 0)
    parsed_sede_files = active_worker_sedes if active_worker_sedes > 0 else int(clean_preview.get("sede_files") or 0)
    workers_count_matches = expected_workers > 0 and len(records) == expected_workers
    primary_validation = run_xlsx_primary_validations(xlsx_profile)
    secondary_validation = run_xlsx_secondary_validations(xlsx_profile)

    missing_profile_fields: List[str] = []
    if not normalize_text(profile.get("empresa", "")):
        missing_profile_fields.append("empresa")
    if not only_digits(profile.get("nit", "")):
        missing_profile_fields.append("nit")
    if not only_digits(profile.get("documento", "")):
        missing_profile_fields.append("documento_representante")
    if not normalize_text(profile.get("tipo_afiliado", "")):
        missing_profile_fields.append("tipo_afiliado")
    if expected_workers <= 0:
        missing_profile_fields.append("numero_trabajadores")
    if expected_sedes <= 0:
        missing_profile_fields.append("numero_sedes")
    if missing_profile_fields:
        rejection_reasons.append(
            {
                "code": "XLSX_REQUIRED_FIELDS_MISSING",
                "severity": "blocker",
                "message": f"El XLSX no trae completos estos campos obligatorios: {', '.join(missing_profile_fields)}.",
            }
        )
        next_actions.append("Completar o corregir la cabecera del XLSX antes de continuar con la radicación.")

    responsable_sede_documento = only_digits(form_fields.get("responsable_sede_principal_numero_documento", ""))
    if not responsable_sede_documento:
        rejection_reasons.append(
            {
                "code": "RESPONSABLE_SEDE_DOCUMENTO_VACIO",
                "severity": "blocker",
                "message": "La cédula del responsable del centro de trabajo es obligatoria.",
            }
        )

    _tel_raw = form_fields.get("sede_principal_telefono", "") or ""
    # Si hay multiples numeros separados por guiones/espacios, tomar el primero valido
    _tel_parts = re.split(r"[-/,;\s]+", _tel_raw.strip())
    _tel_valid = next((only_digits(p) for p in _tel_parts if len(only_digits(p)) in {7, 10} and not only_digits(p).startswith("0")), None)
    sede_principal_telefono = _tel_valid or only_digits(_tel_raw)
    if sede_principal_telefono:
        if sede_principal_telefono.startswith("0"):
            rejection_reasons.append(
                {
                    "code": "SEDE_PRINCIPAL_TELEFONO_INVALIDO",
                    "severity": "blocker",
                    "message": f"El teléfono de la sede principal no puede iniciar en 0 ({sede_principal_telefono}).",
                }
            )
        elif len(sede_principal_telefono) not in {7, 10}:
            rejection_reasons.append(
                {
                    "code": "SEDE_PRINCIPAL_TELEFONO_INVALIDO",
                    "severity": "blocker",
                    "message": f"El teléfono fijo/celular de la sede principal debe tener 7 o 10 dígitos ({sede_principal_telefono}).",
                }
            )

    for email_key, email_label in (
        ("rep_legal_correo", "El correo del representante legal"),
        ("sede_principal_correo", "El correo de la sede principal"),
    ):
        email_value = normalize_text(form_fields.get(email_key, ""))
        if email_value and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email_value):
            rejection_reasons.append(
                {
                    "code": "FORMULARIO_CORREO_INVALIDO",
                    "severity": "blocker",
                    "message": f"{email_label} no tiene un formato válido ({email_value}).",
                }
            )

    for blocker in primary_validation.get("blockers", []):
        rejection_reasons.append({**blocker, "severity": "blocker"})
    for blocker in secondary_validation.get("blockers", []):
        rejection_reasons.append({**blocker, "severity": "blocker"})
    for action in primary_validation.get("next_actions", []):
        if action not in next_actions:
            next_actions.append(action)
    for item in secondary_validation.get("alerts", []):
        alerts.append(item)

    suspicious_required_docs: List[str] = []
    for doc in docs:
        doc_type = str(doc.get("document_type") or "")
        if doc_type not in required_docs:
            continue
        text_size = len(normalize_text(doc.get("ocr_text") or doc.get("text_preview") or ""))
        key_fields = doc.get("key_fields") or {}
        classification_confidence = float(doc.get("classification_confidence") or 0)
        ocr_quality_score = float(doc.get("ocr_quality_score") or 0)
        if text_size < 20 and not key_fields:
            suspicious_required_docs.append(f"{doc.get('filename')} ({doc_type})")
            continue
        if classification_confidence < 0.45 and ocr_quality_score < 0.18:
            suspicious_required_docs.append(f"{doc.get('filename')} ({doc_type})")
    if suspicious_required_docs:
        rejection_reasons.append(
            {
                "code": "DOCUMENTS_MINIMUM_QUALITY_FAILED",
                "severity": "blocker",
                "message": "Estos soportes no cumplen características mínimas de lectura o clasificación: " + ", ".join(sorted(set(suspicious_required_docs))) + ".",
            }
        )
        next_actions.append("Reemplazar los soportes borrosos, vacíos o sin contenido útil antes de volver a ejecutar la prevalidación.")

    if missing_docs:
        missing_doc_labels = [DOC_TYPE_LABELS.get(item, item.replace("_", " ")) for item in missing_docs]
        rejection_reasons.append(
            {
                "code": "MISSING_REQUIRED_DOCUMENTS",
                "severity": "blocker",
                "message": f"Faltan soportes obligatorios: {', '.join(missing_doc_labels)}.",
            }
        )
        next_actions.append("Solicitar al cliente los soportes faltantes antes de continuar el trámite.")

    duplicates = sorted({doc for doc in worker_documents if worker_documents.count(doc) > 1})
    if duplicates:
        duplicate_details: List[str] = []
        for duplicate_doc in duplicates[:5]:
            appearances: List[str] = []
            for record in records:
                row_document = only_digits(
                    record.get("documento")
                    or record.get("numero_documento")
                    or record.get("num_id_trabajador")
                    or record.get("numero_de_identificacion")
                    or ""
                )
                if row_document != duplicate_doc:
                    continue
                full_name = normalize_text(
                    record.get("nombre")
                    or record.get("nombre_trabajador")
                    or " ".join(
                        value
                        for value in [
                            record.get("primer_nombre", ""),
                            record.get("segundo_nombre", ""),
                            record.get("primer_apellido", ""),
                            record.get("segundo_apellido", ""),
                        ]
                        if normalize_text(value)
                    )
                )
                sheet_name = normalize_text(record.get("_sheet", ""))
                row_number = normalize_text(record.get("_row", ""))
                parts = [duplicate_doc]
                if full_name:
                    parts.append(full_name)
                location = " · ".join(item for item in [sheet_name, f"fila {row_number}" if row_number else ""] if item)
                if location:
                    parts.append(location)
                appearances.append(" | ".join(parts))
            if appearances:
                duplicate_details.append("; ".join(appearances[:3]))
        rejection_reasons.append(
            {
                "code": "DUPLICATE_WORKER_DOCUMENTS",
                "severity": "blocker",
                "message": (
                    "El XLSX trae trabajadores duplicados por documento: "
                    + " ; ".join(duplicate_details)
                    + "."
                ),
            }
        )
        next_actions.append("Corregir en el XLSX los documentos repetidos indicados con hoja y fila antes de radicar.")

    if employer_document and employer_document in worker_documents:
        rejection_reasons.append(
            {
                "code": "WORKER_DOCUMENT_EQUALS_EMPLOYER",
                "severity": "blocker",
                "message": "El documento del trabajador no puede coincidir con el documento del empleador.",
            }
        )

    if expected_workers > 0 and not records:
        rows_message = (
            f"El XLSX declara {expected_workers} trabajador(es), pero no se pudieron leer filas individuales "
            "para validar cédulas repetidas, campos vacíos y consistencia fila a fila."
        )
        alerts.append(
            {
                "code": "XLSX_ROWS_NOT_PARSED",
                "severity": "alert",
                "message": rows_message,
            }
        )
        next_actions.append(
            f"Revisar la estructura interna de la hoja de trabajadores del XLSX; el archivo declara {expected_workers} trabajador(es) pero Imagine leyó 0 filas individuales."
        )

    worker_sheet_counts_active = {
        sheet: int(count or 0)
        for sheet, count in worker_sheet_counts.items()
        if int(count or 0) > 0
    }
    # Tener una hoja de sede sin trabajadores no debe reportarse ni contarse como inconsistencia.

    if expected_workers > 0 and records and len(records) != expected_workers:
        sheet_breakdown = ", ".join(
            f"{sheet}: {count}"
            for sheet, count in worker_sheet_counts_active.items()
        )
        rejection_reasons.append(
            {
                "code": "WORKER_COUNT_MISMATCH",
                "severity": "blocker",
                "message": (
                    f"El XLSX reporta {expected_workers} trabajadores, pero se leyeron {len(records)} filas de trabajadores."
                    + (f" Detalle por hoja: {sheet_breakdown}." if sheet_breakdown else "")
                ),
            }
        )
        next_actions.append("Revisar la hoja o sede donde el total de trabajadores no coincide con el consolidado del formulario.")

    if expected_sedes > 0 and parsed_sede_files > 0 and expected_sedes != parsed_sede_files:
        sheet_breakdown = ", ".join(
            f"{sheet}: {count}"
            for sheet, count in worker_sheet_counts_active.items()
        )
        message = (
            f"El contrato tiene {parsed_sede_files} sede(s) detectadas en el paquete, "
            f"pero solo {expected_sedes} sede(s) tienen trabajadores válidos en el XLSX."
            + (f" Detalle por hoja: {sheet_breakdown}." if sheet_breakdown else "")
        )
        if workers_count_matches:
            alerts.append(
                {
                    "code": "SEDES_COUNT_MISMATCH",
                    "severity": "alert",
                    "message": message,
                }
            )
        else:
            rejection_reasons.append(
                {
                    "code": "SEDES_COUNT_MISMATCH",
                    "severity": "blocker",
                    "message": message,
                }
            )

    valid_modalidades = {"PRESENCIAL", "TELETRABAJO", "CASA", "REMOTO"}
    valid_jornadas = {"UNICA", "TURNOS", "ROTATIVA"}
    valid_zonas = {"U", "R"}
    valid_sexos = {"M", "F", "T", "NB", "O"}
    valid_tipo_documento = {"CC", "CE", "CD", "SC", "PE", "PT", "RC", "TI", "NI"}
    valid_tipo_trabajador = {"DEPENDIENTE", "INDEPENDIENTE", "ESTUDIANTE", "PENSIONADO", "APRENDIZ", "COOPERADO"}
    valid_tipo_salario = {"FIJO", "VARIABLE", "INTEGRAL"}
    today = datetime.now()
    afiliacion_inicio_cobertura = _parse_date_value(form_fields.get("fecha_inicio_cobertura", ""))
    _, smmlv_value = _resolve_smmlv_value(form_fields)
    activity_catalog_codes = {
        only_digits(value)
        for value in (xlsx_profile.get("activity_catalog_codes") or [])
        if only_digits(value)
    }
    if activity_catalog_codes:
        form_activity_code = only_digits(
            form_fields.get("a_codigo_actividad_economica_principal")
            or form_fields.get("b_codigo_actividad_economica_principal")
            or ""
        )
        if form_activity_code and form_activity_code not in activity_catalog_codes:
            rejection_reasons.append(
                {
                    "code": "FORMULARIO_ACTIVIDAD_ECONOMICA_INVALIDA",
                    "severity": "blocker",
                    "message": (
                        "El código de actividad económica del formulario no existe en el listado de actividades económicas "
                        f"del XLSX ({form_activity_code})."
                    ),
                }
            )
    for index, record in enumerate(records[:200], start=1):
        row_excel = int(record.get("_row") or index + 1)  # fila real en el Excel
        row_excel = int(record.get("_row") or index + 1)  # fila real en el Excel
        raw_document = normalize_text(
            record.get("documento")
            or record.get("numero_documento")
            or record.get("num_id_trabajador")
            or record.get("numero_de_identificacion")
            or ""
        )
        row_document = only_digits(
            raw_document
        )
        full_name = normalize_text(
            record.get("nombre")
            or record.get("nombre_trabajador")
            or " ".join(
                value
                for value in [
                    record.get("primer_nombre", ""),
                    record.get("segundo_nombre", ""),
                    record.get("primer_apellido", ""),
                    record.get("segundo_apellido", ""),
                ]
                if normalize_text(value)
            )
        )
        if not row_document:
            row_errors.append({"row": row_excel, "code": "DOCUMENTO_VACIO", "message": f"Documento vacío en fila {row_excel}.", "documento": ""})
        elif not _is_strict_numeric_value(raw_document):
            row_errors.append({
                "row": row_excel,
                "code": "DOCUMENTO_NO_NUMERICO",
                "message": f"El número de identificación debe ser numérico en fila {row_excel} ({raw_document}).",
                "documento": row_document,
            })
        if not full_name:
            row_errors.append({"row": row_excel, "code": "NOMBRE_VACIO", "message": f"Nombre vacío en fila {row_excel}.", "documento": row_document})

        doc_type_raw = record.get("tipo_de_documento", "")
        doc_type = normalize_haystack(doc_type_raw).upper()
        if not doc_type:
            row_errors.append({"row": row_excel, "code": "TIPO_DOCUMENTO_VACIO", "message": f"Tipo de documento vacío en fila {row_excel}.", "documento": row_document})
        elif doc_type not in valid_tipo_documento:
            row_errors.append({"row": row_excel, "code": "TIPO_DOCUMENTO_INVALIDO", "message": f"Tipo de documento inválido en fila {row_excel} ({doc_type_raw}).", "documento": row_document})
        elif row_document:
            doc_max_lengths = {
                "CC": 10,
                "TI": 10,
                "CD": 10,
                "RC": 10,
                "CE": 7,
                "PT": 15,
            }
            doc_exact_lengths = {
                "SC": 9,
                "PE": 15,
            }
            if doc_type in doc_max_lengths and len(row_document) > doc_max_lengths[doc_type]:
                row_errors.append({
                    "row": row_excel,
                    "code": "DOCUMENTO_LONGITUD_INVALIDA",
                    "message": f"El documento tipo {doc_type} no puede tener más de {doc_max_lengths[doc_type]} dígitos en fila {row_excel} ({row_document}).",
                    "documento": row_document,
                })
            elif doc_type in doc_exact_lengths and len(row_document) != doc_exact_lengths[doc_type]:
                row_errors.append({
                    "row": row_excel,
                    "code": "DOCUMENTO_LONGITUD_INVALIDA",
                    "message": f"El documento tipo {doc_type} debe tener exactamente {doc_exact_lengths[doc_type]} dígitos en fila {row_excel} ({row_document}).",
                    "documento": row_document,
                })

        birthdate = _parse_birthdate_from_record(record)
        birth_year_raw = only_digits(record.get("fecha_nacimiento_ano", ""))
        if birth_year_raw and len(birth_year_raw) == 4 and int(birth_year_raw) < 1905:
            row_errors.append({
                "row": row_excel,
                "code": "FECHA_NACIMIENTO_ANTIGUA_INVALIDA",
                "message": f"El año de nacimiento no puede ser inferior a 1905 en fila {row_excel} ({birth_year_raw}).",
                "documento": row_document,
            })
        if birthdate:
            age = _age_years(birthdate, today)
            if age < 17:
                row_errors.append({
                    "row": row_excel,
                    "code": "EDAD_MINIMA_INVALIDA",
                    "message": f"La fecha de nacimiento en fila {row_excel} deja una edad menor a 17 años ({birthdate.strftime('%d/%m/%Y')}).",
                    "documento": row_document,
                })

        sexo_raw = record.get("sexo", "") or record.get("sexo_identificacion", "")
        sexo = _normalize_sexo_identificacion(sexo_raw)
        if not sexo:
            row_errors.append({"row": row_excel, "code": "SEXO_VACIO", "message": f"Sexo identificación vacío en fila {row_excel}.", "documento": row_document})
        elif sexo not in valid_sexos:
            row_errors.append({"row": row_excel, "code": "SEXO_INVALIDO", "message": f"Sexo identificación inválido en fila {row_excel} ({sexo_raw}). Usa solo M, F, T, NB u O.", "documento": row_document})

        zona_raw = record.get("zona", "") or record.get("zona_rural_urbana", "") or record.get("zona_(rural/urbana)", "")
        zona = _normalize_zona(zona_raw)
        if not zona:
            row_errors.append({"row": row_excel, "code": "ZONA_VACIA", "message": f"Zona vacía en fila {row_excel}.", "documento": row_document})
        elif zona not in valid_zonas:
            row_errors.append({"row": row_excel, "code": "ZONA_INVALIDA", "message": f"Zona inválida en fila {row_excel} ({zona_raw}).", "documento": row_document})

        modalidad_raw = record.get("modalidad", "")
        modalidad = _normalize_modalidad(modalidad_raw)
        if not modalidad:
            row_errors.append({"row": row_excel, "code": "MODALIDAD_VACIA", "message": f"Modalidad vacía en fila {row_excel}.", "documento": row_document})
        elif modalidad not in valid_modalidades:
            row_errors.append({"row": row_excel, "code": "MODALIDAD_INVALIDA", "message": f"Modalidad inválida en fila {row_excel} ({record.get('modalidad')}).", "documento": row_document})

        jornada_raw = record.get("jornada", "")
        jornada = _normalize_jornada(jornada_raw)
        if not jornada:
            row_errors.append({"row": row_excel, "code": "JORNADA_VACIA", "message": f"Jornada vacía en fila {row_excel}.", "documento": row_document})
        elif jornada not in valid_jornadas:
            row_errors.append({"row": row_excel, "code": "JORNADA_INVALIDA", "message": f"Jornada inválida en fila {row_excel} ({record.get('jornada')}).", "documento": row_document})

        tipo_trabajador_raw = record.get("tipo_de_trabajador", "")
        tipo_trabajador = _normalize_tipo_trabajador(tipo_trabajador_raw)
        if not tipo_trabajador:
            row_errors.append({"row": row_excel, "code": "TIPO_TRABAJADOR_VACIO", "message": f"Tipo de trabajador vacío en fila {row_excel}.", "documento": row_document})
        elif tipo_trabajador not in valid_tipo_trabajador:
            row_errors.append({"row": row_excel, "code": "TIPO_TRABAJADOR_INVALIDO", "message": f"Tipo de trabajador inválido en fila {row_excel} ({tipo_trabajador_raw}).", "documento": row_document})
        elif tipo_trabajador == "ESTUDIANTE":
            actividad_economica_estudiante_raw = (
                record.get("codigo_actividad_economica")
                or record.get("codigo_de_actividad_economica")
                or record.get("codigo_actividad_economica_principal")
                or record.get("actividad_economica")
                or record.get("actividad_economica_ct")
                or _record_value_by_tokens(
                    record,
                    [
                        ["codigo", "actividad", "economica"],
                        ["actividad", "economica"],
                    ],
                )
            )
            actividad_economica_estudiante = only_digits(actividad_economica_estudiante_raw)
            if not actividad_economica_estudiante:
                row_errors.append(
                    {
                        "row": row_excel,
                        "code": "ESTUDIANTE_ACTIVIDAD_ECONOMICA_VACIA",
                        "message": f"Para tipo de trabajador estudiante, el código de actividad económica es obligatorio en fila {row_excel}.",
                        "documento": row_document,
                    }
                )
            elif activity_catalog_codes and actividad_economica_estudiante not in activity_catalog_codes:
                row_errors.append(
                    {
                        "row": row_excel,
                        "code": "ESTUDIANTE_ACTIVIDAD_ECONOMICA_INVALIDA",
                        "message": f"Para tipo de trabajador estudiante, el código de actividad económica no existe en el catálogo del XLSX en fila {row_excel} ({actividad_economica_estudiante}).",
                        "documento": row_document,
                    }
                )

            fecha_inicio_cobertura_estudiante_raw = (
                record.get("fecha_inicio_cobertura")
                or record.get("fecha_de_inicio_de_cobertura")
                or record.get("inicio_cobertura")
                or record.get("contrato_en_practica")
                or record.get("fecha_inicio_contrato")
                or record.get("fecha_inicio")
                or record.get("fecha_inicio_estudiante")
                or _record_value_by_tokens(
                    record,
                    [
                        ["fecha", "inicio"],
                        ["inicio", "contrato"],
                    ],
                )
                or ""
            )
            fecha_inicio_cobertura_estudiante = _parse_date_value(fecha_inicio_cobertura_estudiante_raw)
            if not fecha_inicio_cobertura_estudiante:
                row_errors.append(
                    {
                        "row": row_excel,
                        "code": "ESTUDIANTE_COBERTURA_VACIA",
                        "message": f"Para tipo de trabajador estudiante, la fecha de inicio de cobertura es obligatoria en fila {row_excel}.",
                        "documento": row_document,
                    }
                )
            elif afiliacion_inicio_cobertura and fecha_inicio_cobertura_estudiante.date() < afiliacion_inicio_cobertura.date():
                row_errors.append(
                    {
                        "row": row_excel,
                        "code": "ESTUDIANTE_COBERTURA_INVALIDA",
                        "message": (
                            "La fecha de inicio de cobertura del estudiante no puede ser inferior a la fecha de inicio de cobertura "
                            f"de la afiliación en fila {row_excel}. Estudiante: {_format_date_value(fecha_inicio_cobertura_estudiante_raw)} "
                            f"· Afiliación: {_format_date_value(form_fields.get('fecha_inicio_cobertura'))}."
                        ),
                        "documento": row_document,
                    }
                )

        tipo_salario_raw = record.get("tipo_de_salario", "")
        tipo_salario = _normalize_tipo_salario(tipo_salario_raw)
        if not tipo_salario:
            row_errors.append({"row": row_excel, "code": "TIPO_SALARIO_VACIO", "message": f"Tipo de salario vacío en fila {row_excel}.", "documento": row_document})
        elif tipo_salario not in valid_tipo_salario:
            row_errors.append({"row": row_excel, "code": "TIPO_SALARIO_INVALIDO", "message": f"Tipo de salario inválido en fila {row_excel} ({tipo_salario_raw}).", "documento": row_document})

        codigo_ct = only_digits(
            _record_first_value(
                record,
                "codigo_del_centro_de_trabajo",
                "codigo_centro_trabajo",
                "codigo_ct",
            )
        )
        if not codigo_ct:
            row_errors.append(
                {
                    "row": row_excel,
                    "code": "CENTRO_TRABAJO_CODIGO_VACIO",
                    "message": f"El código del centro de trabajo es obligatorio en fila {row_excel}.",
                    "documento": row_document,
                }
            )

        if tipo_trabajador == "INDEPENDIENTE":
            tipo_contrato = _record_first_value(record, "tipo_de_contrato", "tipo_contrato")
            tipo_cotizante = _record_first_value(record, "tipo_de_cotizante", "tipo_cotizante")
            fecha_inicio_contrato_raw = (
                _record_first_value(record, "fecha_inicio_contrato", "fecha_de_inicio_del_contrato")
                or _record_value_by_tokens(record, [["fecha", "inicio", "contrato"]])
            )
            fecha_fin_contrato_raw = (
                _record_first_value(record, "fecha_fin_contrato", "fecha_de_fin_del_contrato")
                or _record_value_by_tokens(record, [["fecha", "fin", "contrato"]])
            )
            fecha_fin_contrato = _parse_date_value(fecha_fin_contrato_raw)
            actividad_economica_raw = (
                _record_first_value(record, "actividad_economica", "codigo_actividad_economica", "codigo_de_actividad_economica")
                or _record_value_by_tokens(record, [["actividad", "economica"]])
            )
            actividad_economica = only_digits(actividad_economica_raw)
            actividad_economica_ct = only_digits(
                _record_first_value(record, "actividad_economica_ct", "codigo_actividad_economica_ct")
            )
            zona_ct_raw = _record_first_value(record, "zona_ct", "zona_centro_trabajo")
            zona_ct = _normalize_zona(zona_ct_raw)
            valor_contrato = _parse_nomina_value(
                _record_first_value(record, "valor_contrato", "monto_total_del_contrato_en_practica")
            )
            valor_mensual = _parse_nomina_value(_record_first_value(record, "valor_mensual"))
            ibc = _parse_nomina_value(_record_first_value(record, "ibc", "ingreso_base_de_cotizacion"))

            if not tipo_cotizante:
                row_errors.append({
                    "row": row_excel,
                    "code": "INDEPENDIENTE_TIPO_COTIZANTE_VACIO",
                    "message": f"Para independientes, el tipo de cotizante es obligatorio en fila {row_excel}.",
                    "documento": row_document,
                })
            if not tipo_contrato:
                row_errors.append({
                    "row": row_excel,
                    "code": "INDEPENDIENTE_TIPO_CONTRATO_VACIO",
                    "message": f"Para independientes, el tipo de contrato es obligatorio en fila {row_excel}.",
                    "documento": row_document,
                })
            if not fecha_inicio_contrato_raw:
                row_errors.append({
                    "row": row_excel,
                    "code": "INDEPENDIENTE_FECHA_INICIO_CONTRATO_VACIA",
                    "message": f"Para independientes, la fecha de inicio del contrato es obligatoria en fila {row_excel}.",
                    "documento": row_document,
                })
            if not fecha_fin_contrato_raw:
                row_errors.append({
                    "row": row_excel,
                    "code": "INDEPENDIENTE_FECHA_FIN_CONTRATO_VACIA",
                    "message": f"Para independientes, la fecha de fin del contrato es obligatoria en fila {row_excel}.",
                    "documento": row_document,
                })
            elif afiliacion_inicio_cobertura and fecha_fin_contrato and fecha_fin_contrato.date() < afiliacion_inicio_cobertura.date():
                row_errors.append({
                    "row": row_excel,
                    "code": "INDEPENDIENTE_FECHA_FIN_CONTRATO_INVALIDA",
                    "message": (
                        "Para independientes, la fecha de fin del contrato no puede ser inferior a la fecha de inicio de cobertura "
                        f"de la afiliación en fila {row_excel}. Fin contrato: {_format_date_value(fecha_fin_contrato_raw)} "
                        f"· Afiliación: {_format_date_value(form_fields.get('fecha_inicio_cobertura'))}."
                    ),
                    "documento": row_document,
                })
            if not actividad_economica:
                row_errors.append({
                    "row": row_excel,
                    "code": "INDEPENDIENTE_ACTIVIDAD_ECONOMICA_VACIA",
                    "message": f"Para independientes, la actividad económica es obligatoria en fila {row_excel}.",
                    "documento": row_document,
                })
            elif activity_catalog_codes and actividad_economica not in activity_catalog_codes:
                row_errors.append({
                    "row": row_excel,
                    "code": "INDEPENDIENTE_ACTIVIDAD_ECONOMICA_INVALIDA",
                    "message": f"Para independientes, la actividad económica no existe en el catálogo del XLSX en fila {row_excel} ({actividad_economica}).",
                    "documento": row_document,
                })
            if not actividad_economica_ct:
                row_errors.append({
                    "row": row_excel,
                    "code": "INDEPENDIENTE_ACTIVIDAD_ECONOMICA_CT_VACIA",
                    "message": f"Para independientes, la actividad económica del centro de trabajo es obligatoria en fila {row_excel}.",
                    "documento": row_document,
                })
            elif activity_catalog_codes and actividad_economica_ct not in activity_catalog_codes:
                row_errors.append({
                    "row": row_excel,
                    "code": "INDEPENDIENTE_ACTIVIDAD_ECONOMICA_CT_INVALIDA",
                    "message": f"Para independientes, la actividad económica del centro de trabajo no existe en el catálogo del XLSX en fila {row_excel} ({actividad_economica_ct}).",
                    "documento": row_document,
                })
            if not zona_ct:
                row_errors.append({
                    "row": row_excel,
                    "code": "INDEPENDIENTE_ZONA_CT_VACIA",
                    "message": f"Para independientes, la zona del centro de trabajo es obligatoria en fila {row_excel}.",
                    "documento": row_document,
                })
            elif zona_ct not in valid_zonas:
                row_errors.append({
                    "row": row_excel,
                    "code": "INDEPENDIENTE_ZONA_CT_INVALIDA",
                    "message": f"Para independientes, la zona del centro de trabajo es inválida en fila {row_excel} ({zona_ct_raw}).",
                    "documento": row_document,
                })
            if not valor_contrato:
                row_errors.append({
                    "row": row_excel,
                    "code": "INDEPENDIENTE_VALOR_CONTRATO_VACIO",
                    "message": f"Para independientes, el valor del contrato es obligatorio en fila {row_excel}.",
                    "documento": row_document,
                })
            elif valor_contrato < smmlv_value:
                row_errors.append({
                    "row": row_excel,
                    "code": "INDEPENDIENTE_VALOR_CONTRATO_INVALIDO",
                    "message": f"Para independientes, el valor del contrato no puede ser inferior al mínimo configurado ({smmlv_value}) en fila {row_excel}.",
                    "documento": row_document,
                })
            if not valor_mensual:
                row_errors.append({
                    "row": row_excel,
                    "code": "INDEPENDIENTE_VALOR_MENSUAL_VACIO",
                    "message": f"Para independientes, el valor mensual es obligatorio en fila {row_excel}.",
                    "documento": row_document,
                })
            elif valor_mensual < smmlv_value:
                row_errors.append({
                    "row": row_excel,
                    "code": "INDEPENDIENTE_VALOR_MENSUAL_INVALIDO",
                    "message": f"Para independientes, el valor mensual no puede ser inferior al mínimo configurado ({smmlv_value}) en fila {row_excel}.",
                    "documento": row_document,
                })
            if not ibc:
                row_errors.append({
                    "row": row_excel,
                    "code": "INDEPENDIENTE_IBC_VACIO",
                    "message": f"Para independientes, el IBC es obligatorio en fila {row_excel}.",
                    "documento": row_document,
                })
            elif ibc < smmlv_value:
                row_errors.append({
                    "row": row_excel,
                    "code": "INDEPENDIENTE_IBC_INVALIDO",
                    "message": f"Para independientes, el IBC no puede ser inferior al mínimo configurado ({smmlv_value}) en fila {row_excel}.",
                    "documento": row_document,
                })

        phone = only_digits(record.get("telefono") or "")
        mobile = only_digits(record.get("celular") or "")
        phone_looks_like_mobile = len(phone) == 10 and not phone.startswith("0")
        phone_as_mobile = not mobile and phone_looks_like_mobile
        effective_mobile = phone if phone_as_mobile else mobile
        phone_can_be_zero = bool(mobile) and phone in {"", "0"}
        if phone_as_mobile:
            phone_can_be_zero = True

        if phone and not phone_can_be_zero:
            if phone == "0":
                row_errors.append({
                    "row": row_excel,
                    "code": "TELEFONO_FORMATO_INVALIDO",
                    "message": f"El teléfono debe ir en 0 solo cuando el celular esté diligenciado en fila {row_excel}.",
                    "documento": row_document,
                })
            elif phone.startswith("0"):
                row_errors.append({
                    "row": row_excel,
                    "code": "TELEFONO_FORMATO_INVALIDO",
                    "message": f"El teléfono no puede iniciar en 0 en fila {row_excel} ({phone}).",
                    "documento": row_document,
                })
            elif len(phone) not in {7, 10}:
                row_errors.append({
                    "row": row_excel,
                    "code": "TELEFONO_FORMATO_INVALIDO",
                    "message": f"El teléfono debe tener 7 dígitos o 10 si fue reportado como celular en fila {row_excel} ({phone}).",
                    "documento": row_document,
                })

        if effective_mobile:
            if effective_mobile.startswith("0"):
                row_errors.append({
                    "row": row_excel,
                    "code": "CELULAR_FORMATO_INVALIDO",
                    "message": f"El celular no puede iniciar en 0 en fila {row_excel} ({effective_mobile}).",
                    "documento": row_document,
                })
            elif len(effective_mobile) != 10:
                row_errors.append({
                    "row": row_excel,
                    "code": "CELULAR_FORMATO_INVALIDO",
                    "message": f"El celular debe tener 10 dígitos en fila {row_excel} ({effective_mobile}).",
                    "documento": row_document,
                })

        email = normalize_text(record.get("mail") or record.get("correo") or record.get("correo_electronico") or "")
        if email:
            simple_email_ok = bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email))
            if not simple_email_ok:
                row_errors.append({
                    "row": row_excel,
                    "code": "CORREO_FORMATO_INVALIDO",
                    "message": f"Correo con formato no válido en fila {row_excel} ({email}).",
                    "documento": row_document,
                })

    if row_errors:
        rejection_reasons.extend(
            {"code": item["code"], "severity": "blocker", "message": item["message"]}
            for item in row_errors[:20]
        )
        next_actions.append("Corregir las filas inválidas del XLSX antes de continuar con la radicación.")

    listed_workers = _doc_by_type(docs, "listado_trabajadores")
    listed_workers_present = bool(listed_workers) or parsed_sede_files > 0 or any(doc.get("document_type") == "anexo_sedes" for doc in docs)
    if records and not listed_workers_present:
        alerts.append(
            {
                "code": "WORKER_LIST_NOT_FOUND",
                "severity": "alert",
                "message": "El XLSX contiene trabajadores, pero no se detectó un listado de trabajadores entre los adjuntos.",
            }
        )
        next_actions.append("Validar si el flujo exige listado de trabajadores o si la carga vino embebida solo en el XLSX.")

    if any(required in {"formulario_afiliacion", "anexo_sedes"} for required in required_docs):
        existing_types = {doc.get("document_type") for doc in docs}
        for expected_type in ["formulario_afiliacion", "anexo_sedes"]:
            if expected_type in required_docs and expected_type not in existing_types:
                alerts.append(
                    {
                        "code": f"OPTIONAL_{expected_type.upper()}_NOT_FOUND",
                        "severity": "alert",
                        "message": f"No se detectó {DOC_TYPE_LABELS.get(expected_type, expected_type)} en los adjuntos cargados.",
                    }
                )

    return {
        "approved": not rejection_reasons,
        "xlsx_primary_validation": primary_validation,
        "xlsx_secondary_validation": secondary_validation,
        "motivos_de_rechazo": rejection_reasons,
        "alerts": alerts,
        "row_errors": row_errors[:50],
        "row_warnings": row_warnings[:50],
        "next_actions": _unique_preserve(next_actions),
    }


def _build_validation_summary(xlsx_profile: Dict[str, Any], docs: List[Dict[str, Any]], missing_docs: List[str]) -> Dict[str, Any]:
    profile = xlsx_profile.get("profile", {})
    flat_pairs = xlsx_profile.get("flat_pairs", {}) or {}
    form_fields = dict((xlsx_profile or {}).get("form_fields") or {})
    xlsx_document = only_digits(profile.get("documento", ""))
    xlsx_nit = _normalize_company_nit(profile.get("documento_empleador") or profile.get("nit", ""), docs)
    validations: List[Dict[str, Any]] = []
    alerts: List[Dict[str, Any]] = []
    matches: Dict[str, Any] = {}
    required_evidence = _infer_required_document_satisfaction(_build_required_documents(profile), docs, profile)
    natural_person_with_cedula = _is_natural_person_with_cedula({
        "tipo_persona": form_fields.get("tipo_persona") or profile.get("tipo_persona", ""),
        "empleador_tipo_documento": form_fields.get("empleador_tipo_documento") or profile.get("empleador_tipo_documento", ""),
    })

    cedula_docs = _doc_by_type(docs, "cedula")
    matched_cedula = None
    matched_cedula_candidate = ""
    cedula_inferred = False
    if xlsx_document:
        for doc in cedula_docs:
            fields = doc.get("fields") or {}
            candidate = _best_document_candidate(xlsx_document, [fields.get("document_number", "")] + list(fields.get("all_numbers") or []))
            if candidate:
                matched_cedula = doc
                matched_cedula_candidate = candidate
                break
        if not matched_cedula and len(cedula_docs) == 1:
            matched_cedula = cedula_docs[0]
            matched_cedula_candidate = xlsx_document
            cedula_inferred = True
    inferred_cedula = required_evidence.get("cedula") or {}
    if not matched_cedula and inferred_cedula.get("satisfied") and inferred_cedula.get("filename"):
        matched_cedula = next((doc for doc in docs if doc.get("filename") == inferred_cedula.get("filename")), None)
        matched_cedula_candidate = inferred_cedula.get("matched", "")
    cedula_ok = bool(matched_cedula_candidate) if xlsx_document else bool(cedula_docs or inferred_cedula.get("satisfied"))
    validations.append(
        {
            "code": "CEDULA_MATCH_XLSX",
            "status": "OK" if cedula_ok else "ALERTA",
            "message": "La cedula coincide con el documento del XLSX." if cedula_ok else "La cedula OCR no coincide con el documento del XLSX.",
        }
    )
    if not cedula_ok:
        alerts.append(validations[-1])
    if xlsx_document:
        matches["cedula_principal"] = {
            "expected": xlsx_document,
            "matched": matched_cedula_candidate,
            "filename": (matched_cedula or {}).get("filename", ""),
            "inferred": cedula_inferred,
            "ok": bool(matched_cedula_candidate),
        }

    rut_docs = _doc_by_type(docs, "rut")
    matched_rut = None
    rut_ok = False
    if xlsx_nit:
        matched_rut = next((doc for doc in rut_docs if _canonical_numeric_value(doc["fields"].get("nit", "")) == _canonical_numeric_value(xlsx_nit)), None)
        if not matched_rut:
            for doc in docs:
                fields = doc.get("fields") or {}
                preview = normalize_haystack(doc.get("text_preview", ""))
                candidates = [fields.get("nit", ""), fields.get("document_number", "")] + list(fields.get("all_numbers") or [])
                candidate = _best_numeric_candidate(xlsx_nit, candidates)
                if candidate and (
                    doc.get("document_type") in {"rut", "entrega_documentos", "camara_comercio", "soporte_ingresos"}
                    or "rut" in preview
                    or "dian" in preview
                    or "numero de identificacion tributaria" in preview
                ):
                    matched_rut = doc
                    break
        rut_ok = bool(matched_rut)
    else:
        rut_ok = bool(rut_docs)
    validations.append(
        {
            "code": "RUT_MATCH_XLSX",
            "status": "OK" if rut_ok else "ALERTA",
            "message": "El RUT coincide con el NIT del XLSX." if rut_ok else "El RUT no entrega un NIT consistente con el XLSX.",
        }
    )
    if not rut_ok:
        alerts.append(validations[-1])
    if xlsx_nit:
        matches["rut_nit"] = {
            "expected": xlsx_nit,
            "matched": _best_numeric_candidate(
                xlsx_nit,
                [
                    ((matched_rut or {}).get("fields", {}) or {}).get("nit", ""),
                    ((matched_rut or {}).get("fields", {}) or {}).get("document_number", ""),
                    *list((((matched_rut or {}).get("fields", {}) or {}).get("all_numbers") or [])),
                ],
            ),
            "filename": (matched_rut or {}).get("filename", ""),
            "ok": bool(matched_rut),
        }

    formulario_docs = _doc_by_type(docs, "formulario_afiliacion")
    representative_form = next((doc for doc in formulario_docs if only_digits((doc.get("fields") or {}).get("representative_document", "") or (doc.get("fields") or {}).get("document_number", ""))), None)
    form_doc = only_digits((representative_form or {}).get("fields", {}).get("representative_document", "") or (representative_form or {}).get("fields", {}).get("document_number", ""))
    profile_doc = only_digits(profile.get("documento", ""))
    if form_doc and profile_doc and not _numeric_document_match(form_doc, profile_doc):
        form_doc_candidates = [form_doc] + list(((representative_form or {}).get("fields", {}) or {}).get("all_numbers") or [])
        best_form_doc = _best_document_candidate(profile_doc, form_doc_candidates)
        if best_form_doc:
            form_doc = best_form_doc
        else:
            form_doc = profile_doc
    representative_cedula = None
    ced_doc = ""
    rep_doc_inferred = False
    if form_doc:
        for doc in cedula_docs:
            fields = doc.get("fields") or {}
            candidate = _best_document_candidate(form_doc, [fields.get("document_number", "")] + list(fields.get("all_numbers") or []))
            if candidate:
                representative_cedula = doc
                ced_doc = candidate
                break
    if not representative_cedula and inferred_cedula.get("satisfied") and form_doc and _numeric_document_match(form_doc, inferred_cedula.get("matched", "")):
        representative_cedula = next((doc for doc in docs if doc.get("filename") == inferred_cedula.get("filename")), None)
        ced_doc = inferred_cedula.get("matched", "")
        rep_doc_inferred = True
    if (
        not representative_cedula
        and form_doc
        and len(cedula_docs) == 1
        and not ced_doc
    ):
        representative_cedula = cedula_docs[0]
        ced_doc = form_doc
        rep_doc_inferred = True
    rep_doc_ok = bool(form_doc and ced_doc and _numeric_document_match(form_doc, ced_doc))
    if representative_form or representative_cedula:
        if rep_doc_ok and rep_doc_inferred:
            rep_message = (
                f"La cédula del representante coincide por inferencia documental: formulario={form_doc or 'n/d'} "
                f"· cédula referenciada={ced_doc or 'n/d'}."
            )
        elif rep_doc_ok:
            rep_message = "La cédula del representante en el formulario coincide con la cédula adjunta."
        else:
            rep_message = f"La cédula del representante no coincide: formulario={form_doc or 'n/d'} · cédula adjunta={ced_doc or 'n/d'}."
        validations.append(
            {
                "code": "REPRESENTANTE_DOC_MATCH",
                "status": "OK" if rep_doc_ok else "ALERTA",
                "message": rep_message,
            }
        )
        matches["representante_documento"] = {
            "expected": form_doc,
            "matched": ced_doc,
            "formulario": (representative_form or {}).get("filename", ""),
            "cedula": (representative_cedula or {}).get("filename", ""),
            "inferred": rep_doc_inferred,
            "ok": rep_doc_ok,
        }
        if not rep_doc_ok:
            alerts.append(validations[-1])

    profile_company = normalize_haystack(profile.get("empresa", ""))
    profile_company_cmp = _normalize_company_compare(profile.get("empresa", ""))
    profile_company_strict = _normalize_company_strict(profile.get("empresa", ""))
    camara_docs = _doc_by_type(docs, "camara_comercio")
    camara_primary = next((d for d in camara_docs if d.get("fields", {}).get("company_name", "").strip()), camara_docs[0] if camara_docs else None)
    formulario_primary = formulario_docs[0] if formulario_docs else None
    camara_company_source = normalize_text((camara_primary or {}).get("fields", {}).get("company_name", ""))
    form_company_source = normalize_text((formulario_primary or {}).get("fields", {}).get("company_name", "")) or normalize_text(profile.get("empresa", ""))
    camara_company = normalize_haystack(camara_company_source)
    form_company = normalize_haystack(form_company_source)
    camara_company_cmp = _normalize_company_compare(camara_company_source)
    form_company_cmp = _normalize_company_compare(form_company_source)
    camara_company_strict = _normalize_company_strict(camara_company_source)
    form_company_strict = _normalize_company_strict(form_company_source)
    company_ok = False
    if not natural_person_with_cedula and camara_primary and (formulario_primary or profile.get("empresa")):
        form_or_xlsx_company = normalize_haystack(form_company_source)
        form_or_xlsx_company_cmp = _normalize_company_compare(form_company_source)
        form_or_xlsx_company_strict = _normalize_company_strict(form_company_source)
        form_has_company = bool(form_or_xlsx_company)
        company_ok = bool(
            camara_company_cmp
            and (
                (form_has_company and form_or_xlsx_company_cmp and camara_company_cmp == form_or_xlsx_company_cmp)
                or (not form_has_company and profile_company_cmp and camara_company_cmp == profile_company_cmp)
            )
        )
        validations.append(
            {
                "code": "EMPRESA_MATCH_CAMARA_FORMULARIO",
                "status": "OK" if company_ok else "ALERTA",
                "message": "La razón social coincide entre cámara de comercio y formulario/XLSX."
                if company_ok
                else "La razón social no coincide entre cámara de comercio y formulario/XLSX.",
            }
        )
        matches["empresa_nombre"] = {
            "profile": profile.get("empresa", ""),
            "camara": (camara_primary or {}).get("fields", {}).get("company_name", ""),
            "formulario": (formulario_primary or {}).get("fields", {}).get("company_name", "") or profile.get("empresa", ""),
            "camara_compare": camara_company_cmp,
            "formulario_compare": form_or_xlsx_company_cmp,
            "camara_strict": camara_company_strict,
            "formulario_strict": form_or_xlsx_company_strict,
            "camara_file": (camara_primary or {}).get("filename", ""),
            "formulario_file": (formulario_primary or {}).get("filename", "") or (xlsx_profile.get("source_filename") or ""),
            "ok": company_ok,
        }
        if not company_ok:
            alerts.append(validations[-1])

    if "contrato" not in missing_docs:
        contrato_docs = _doc_by_type(docs, "contrato")
        contrato_ok = any(bool(doc["fields"].get("has_contrato_hint")) for doc in contrato_docs) or bool(contrato_docs)
        validations.append(
            {
                "code": "CONTRATO_PRESENTE",
                "status": "OK" if contrato_ok else "REVISAR",
                "message": "Se detecta soporte contractual." if contrato_ok else "El contrato existe pero requiere verificacion manual.",
            }
        )

    if "soporte_ingresos" not in missing_docs:
        ingresos_docs = _doc_by_type(docs, "soporte_ingresos")
        ingresos_ok = any(bool(doc["fields"].get("has_income_hint")) for doc in ingresos_docs) or bool(ingresos_docs)
        validations.append(
            {
                "code": "INGRESOS_PRESENTES",
                "status": "OK" if ingresos_ok else "REVISAR",
                "message": "Se detecta soporte de ingresos." if ingresos_ok else "El soporte de ingresos requiere confirmacion manual.",
            }
        )

    if camara_docs and not natural_person_with_cedula:
        recent_date = None
        recent_source = None
        for doc in camara_docs:
            fields = doc.get("fields") or {}
            parsed = None
            issue_date_textual = normalize_text(fields.get("issue_date_textual", ""))
            if issue_date_textual:
                try:
                    parsed = datetime.strptime(issue_date_textual, "%Y-%m-%d")
                except ValueError:
                    parsed = None
            if not parsed:
                parsed = _parse_spanish_date_text(doc.get("text_preview", "")) or _parse_date(doc.get("text_preview", ""))
            if parsed and (recent_date is None or parsed > recent_date):
                recent_date = parsed
                recent_source = doc.get("filename")
        if recent_date:
            age_days = (datetime.now() - recent_date).days
            age_business_days = _business_days_between(recent_date, datetime.now())
            ok = age_business_days <= 60
            issue_date_human = _format_date_es(recent_date)
            validations.append(
                {
                    "code": "CAMARA_VIGENTE",
                    "status": "OK" if ok else "ALERTA",
                    "message": (
                        f"Camara de comercio vigente. Fecha de expedicion: {issue_date_human}. Antigüedad: {age_business_days} dias hábiles."
                        if ok
                        else f"Camara de comercio vencida. Fecha de expedicion: {issue_date_human}. Antigüedad: {age_business_days} dias hábiles."
                    ),
                    "severity": "blocker" if not ok else "ok",
                }
            )
            matches["camara_vigencia"] = {
                "issued_at": recent_date.strftime("%Y-%m-%d"),
                "issued_at_human": issue_date_human,
                "age_days": age_days,
                "age_business_days": age_business_days,
                "filename": recent_source or "",
                "ok": ok,
            }
            if not ok:
                alerts.append(validations[-1])

    tipo_negocio_detectado = normalize_text(profile.get("tipo_negocio_detectado") or "")
    tipoempresa_detectado = normalize_text(profile.get("tipoempresa_homologado") or "")
    naturaleza_empleador = normalize_text(
        profile.get("naturaleza_juridica_empleador")
        or flat_pairs.get("naturalezajuridica")
        or ""
    )
    tipoempresa_compat = _map_naturaleza_to_tipoempresa_compat(naturaleza_empleador)
    if tipoempresa_detectado:
        tipoempresa_ok = not tipoempresa_compat or tipoempresa_detectado == tipoempresa_compat
        message = (
            f"tipoempresa detectado desde 'TIPO DE NEGOCIO' = {tipoempresa_detectado} ({tipo_negocio_detectado or 'n/d'}) y coincide con el valor que hoy usaría el CORE."
            if tipoempresa_ok
            else f"tipoempresa detectado desde 'TIPO DE NEGOCIO' = {tipoempresa_detectado} ({tipo_negocio_detectado or 'n/d'}), pero el CORE hoy usaría {tipoempresa_compat} según naturaleza jurídica '{naturaleza_empleador or 'n/d'}'."
        )
        validations.append(
            {
                "code": "TIPOEMPRESA_CORE_COMPARE",
                "status": "OK" if tipoempresa_ok else "ALERTA",
                "message": message,
            }
        )
        matches["tipoempresa_core"] = {
            "tipo_negocio_detectado": tipo_negocio_detectado,
            "expected_from_pdf": tipoempresa_detectado,
            "core_current_from_naturaleza": tipoempresa_compat,
            "naturaleza_juridica_empleador": naturaleza_empleador,
            "source_document": profile.get("tipoempresa_source_document", ""),
            "source": profile.get("tipoempresa_source", ""),
            "ok": tipoempresa_ok,
            "inference": "core_current_from_naturaleza" if tipoempresa_compat else "",
        }
        if not tipoempresa_ok:
            alerts.append(validations[-1])

    entrega_porcentaje_issue = None
    for doc in docs:
        if str(doc.get("document_type") or "") != "entrega_documentos":
            continue
        # Extraer todos los intermediarios y validar suma por tipo
        todos_intermediarios = _extract_todos_intermediarios(doc)
        errores_participacion = _validate_participacion_por_tipo(todos_intermediarios)
        for err in errores_participacion:
            validations.append({"code": "COMISION_PARTICIPACION_SUMA", "status": "ALERTA", "severity": "blocker", "message": err})
            alerts.append(validations[-1])
        entrega_data = _extract_intermediario_codigo_y_porcentaje(doc)
        codigo_intermediario = entrega_data.get("codigo_intermediario") or ""
        porcentaje_venta = entrega_data.get("porcentaje_venta") or ""
        if codigo_intermediario not in {"1", "01", "3", "03"}:
            continue
        # Solo validar porcentaje si hay tabla legible (todos_intermediarios) o porcentaje explícito
        # Si no hay tabla y el porcentaje es ambiguo (1 dígito), no bloquear
        porcentaje_legible = bool(todos_intermediarios) or (len(only_digits(porcentaje_venta)) >= 2)
        if not porcentaje_legible:
            continue
        ok = _is_percentage_100(porcentaje_venta)
        validations.append(
            {
                "code": "ENTREGA_DOCUMENTOS_PORCENTAJE_INTERMEDIARIO",
                "status": "OK" if ok else "ALERTA",
                "severity": "ok" if ok else "blocker",
                "message": (
                    f"En el soporte entrega de documentos, para intermediario código {codigo_intermediario.zfill(2)} el porcentaje de la venta fue leído como '{porcentaje_venta}' y cumple con el 100% requerido."
                    if ok
                    else f"En el soporte entrega de documentos, para intermediario código {codigo_intermediario.zfill(2)} el porcentaje de la venta debe venir diligenciado al 100%. Valor leído: '{porcentaje_venta or 'vacío'}'."
                ),
            }
        )
        todos_intermediarios_full = _extract_todos_intermediarios(doc)
        matches["entrega_documentos_intermediario"] = {
            "codigo_intermediario": codigo_intermediario.zfill(2),
            "porcentaje_venta": porcentaje_venta,
            "filename": str(doc.get("filename") or ""),
            "ok": ok,
            "todos_intermediarios": todos_intermediarios_full,
        }
        if not ok:
            entrega_porcentaje_issue = validations[-1]
            alerts.append(validations[-1])
        # Validar que el asesor esté en la tabla de comerciales/intermediarios
        todos_intermediarios = _extract_todos_intermediarios(doc)
        for interm in todos_intermediarios:
            cedula_interm = interm.get("vendedor_documento", "")
            codigo_interm = interm.get("codigo_intermediario", "")
            if cedula_interm and codigo_interm:
                en_tabla = _validate_asesor_en_tabla(cedula_interm, codigo_interm)
                if not en_tabla:
                    tipo_nombre = {"1": "Consultor", "3": "Corredor/Agencia"}.get(codigo_interm, "Intermediario")
                    msg = f"El {tipo_nombre} con documento {cedula_interm} no se encuentra en la base de comerciales e intermediarios de Colmena."
                    v = {"code": "ASESOR_NO_EN_TABLA", "status": "ALERTA", "severity": "blocker", "message": msg}
                    validations.append(v)
                    alerts.append(v)
        break

    precheck = _build_precheck_summary(xlsx_profile, docs, _build_required_documents(profile), missing_docs)
    alerts.extend(item for item in precheck.get("alerts", []) if item not in alerts)
    precheck_reasons = list(precheck.get("motivos_de_rechazo", []))
    existing_reason_keys = {
        (item.get("code", ""), item.get("message", ""))
        for item in precheck_reasons
        if isinstance(item, dict)
    }
    for alert in alerts:
        if not isinstance(alert, dict):
            continue
        if normalize_haystack(alert.get("severity", "")).lower() == "alert":
            continue
        reason_key = (alert.get("code", ""), alert.get("message", ""))
        if reason_key in existing_reason_keys:
            continue
        precheck_reasons.append(
            {
                "code": alert.get("code", "VALIDATION_ALERT"),
                "severity": "blocker",
                "message": alert.get("message", ""),
            }
        )
        existing_reason_keys.add(reason_key)
    precheck["motivos_de_rechazo"] = precheck_reasons
    precheck["approved"] = not precheck_reasons
    return {
        "ok": precheck["approved"] and not missing_docs,
        "items": validations,
        "alerts": alerts,
        "matches": matches,
        "precheck": precheck,
    }


def _build_executive_report(label: str, xlsx_profile: Dict[str, Any], checklist: Dict[str, Any], decision: Dict[str, Any], validation_summary: Dict[str, Any]) -> Dict[str, Any]:
    profile = xlsx_profile.get("profile", {})
    employer_nit = _normalize_company_nit(profile.get("documento_empleador") or profile.get("nit", ""))
    records = xlsx_profile.get("records", []) or []
    worker_sheet_counts = xlsx_profile.get("worker_sheet_counts", {}) or {}
    worker_sheet_salary_totals = xlsx_profile.get("worker_sheet_salary_totals", {}) or {}
    raw_fecha_proceso = only_digits(profile.get("fecha_proceso") or "")[:8]
    if len(raw_fecha_proceso) != 8:
        raw_fecha_proceso = datetime.now().strftime("%Y%m%d")
    try:
        fecha_proceso_dt = datetime.strptime(raw_fecha_proceso, "%Y%m%d")
        fecha_proceso_human = _format_date_es(fecha_proceso_dt)
    except ValueError:
        fecha_proceso_human = raw_fecha_proceso
    derived_workers = profile.get("numero_trabajadores")
    derived_sedes = profile.get("numero_sedes")
    worker_count = int(derived_workers) if str(derived_workers).isdigit() else len(records)
    nomina_total_from_records = sum(
        _parse_nomina_value(
            record.get("salario")
            or record.get("salario_basico")
            or record.get("ibc")
            or record.get("ingreso_base_de_cotizacion")
            or ""
        )
        for record in records
    )
    nomina_total = sum(int(value or 0) for value in worker_sheet_salary_totals.values()) or nomina_total_from_records
    active_worker_sedes = sum(1 for count in worker_sheet_counts.values() if int(count or 0) > 0)
    sedes_count = (
        active_worker_sedes
        if active_worker_sedes > 0
        else int(derived_sedes)
        if str(derived_sedes).isdigit()
        else sum(1 for item in (checklist.get("received_summary") or []) if item.get("document_type") == "anexo_sedes")
    )
    estado = "APROBADO" if decision.get("recommended_status") == "aprobable" else "RECHAZADO"
    errores: List[str] = []
    observaciones: List[str] = []
    for item in decision.get("blockers", []):
        message = item["message"] if isinstance(item, dict) else str(item)
        if message and message not in errores:
            errores.append(message)
    for item in validation_summary.get("alerts", []):
        message = item["message"] if isinstance(item, dict) else str(item)
        if message and message not in observaciones:
            observaciones.append(message)
    precheck = validation_summary.get("precheck", {})
    report_lines = [
        f"Reporte ejecutivo del caso {label}",
        f"Estado final: {estado}",
        f"Fecha de proceso: {fecha_proceso_human}",
        f"Afiliado: {profile.get('empresa', 'n/d')}",
        f"NIT: {employer_nit or 'n/d'}",
        f"Nómina total: {nomina_total}",
        f"Trabajadores: {worker_count}",
        f"Sedes: {sedes_count}",
    ]
    if checklist.get("missing"):
        report_lines.append(f"Faltantes: {', '.join(checklist.get('missing', []))}")
    if errores:
        report_lines.append("Hallazgos:")
        for item in errores[:8]:
            lines = format_reason_lines(item)
            if not lines:
                continue
            report_lines.append(f"- {lines[0]}")
            report_lines.extend(lines[1:])
    if observaciones:
        report_lines.append("Observaciones:")
        for item in observaciones[:8]:
            lines = format_reason_lines(item)
            if not lines:
                continue
            report_lines.append(f"- {lines[0]}")
            report_lines.extend(lines[1:])
    if precheck.get("next_actions"):
        report_lines.append("Acciones recomendadas:")
        report_lines.extend(f"- {item}" for item in precheck.get("next_actions", [])[:6])
    return {
        "estado_final": estado,
        "resumen_ejecutivo": {
            "caso": label,
            "empresa": profile.get("empresa", ""),
            "nit": employer_nit,
            "documento": profile.get("documento", ""),
            "fecha_proceso": raw_fecha_proceso,
            "fecha_proceso_human": fecha_proceso_human,
            "nomina_total": nomina_total,
            "numero_trabajadores": worker_count,
            "numero_sedes": sedes_count,
            "estado": estado,
            "faltantes": checklist.get("missing", []),
            "errores": errores,
            "observaciones": observaciones,
            "matches": validation_summary.get("matches", {}),
            "siguiente_paso": decision.get("next_step", ""),
            "acciones_recomendadas": precheck.get("next_actions", []),
        },
        "texto": "\n".join(report_lines),
    }


def _build_926_draft(profile: Dict[str, Any], checklist: Dict[str, Any], decision: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if decision.get("recommended_status") != "aprobable":
        return None
    documento = only_digits(profile.get("documento", ""))
    nit = only_digits(profile.get("nit", ""))
    empresa = normalize_text(profile.get("empresa", ""))
    afiliado = normalize_text(profile.get("tipo_afiliado", ""))
    lines = [
        f"1|{nit}|{empresa[:60]}",
        f"2|{documento}|{afiliado[:30]}|OK",
        f"9|{','.join(checklist.get('received', []))}|READY",
    ]
    return {
        "filename": f"borrador_926_{slugify(empresa or 'caso')}.txt",
        "content": "\n".join(lines) + "\n",
        "note": "Borrador operativo inicial. Aun no reemplaza el generador 926 legacy completo.",
    }



def _push_comisiones_to_legacy(lote: str, docs: List[Dict[str, Any]], base: str = "temporal") -> bool:
    if not lote:
        return False
    base_url = str(settings.legacy_backend_url or "").strip().rstrip("/")
    if not base_url:
        return False
    entrega_docs = [d for d in docs if str(d.get("document_type") or "") == "entrega_documentos"]
    if not entrega_docs:
        return False
    # Buscar correcciones manuales de comisiones en el payload
    manual_comisiones: Dict[str, List[Dict[str, str]]] = {}
    for doc in entrega_docs:
        fname = str(doc.get("filename") or "")
        mc = doc.get("_manual_comisiones") or []
        if mc:
            manual_comisiones[fname] = mc
    comision_rows = []
    linea = 0
    for doc in entrega_docs:
        fname = str(doc.get("filename") or "")
        # Preferir correcciones manuales del operador sobre OCR
        if fname in manual_comisiones:
            for mc in manual_comisiones[fname]:
                codigo_raw = only_digits(str(mc.get("codigo") or "1"))
                if codigo_raw == "2":
                    continue
                codigo_plano = {"1": "2", "3": "3", "4": "4"}.get(codigo_raw, "2")
                linea += 1
                comision_rows.append({
                    "lote": lote, "linea": str(linea), "sr": "1",
                    "vendedor": only_digits(str(mc.get("cedula") or codigo_raw)),
                    "codigo_vendedor": codigo_plano, "venta": "1",
                    "porcentaje": str(mc.get("porcentaje") or "100"),
                })
            continue
        intermediarios = _extract_todos_intermediarios(doc)
        if not intermediarios:
            data = _extract_intermediario_codigo_y_porcentaje(doc)
            codigo = only_digits(data.get("codigo_intermediario") or "")
            if codigo and codigo != "2":
                codigo_plano = {"1": "2", "3": "3", "4": "4"}.get(codigo, "2")
                linea += 1
                comision_rows.append({
                    "lote": lote, "linea": str(linea), "sr": "1",
                    "vendedor": only_digits(data.get("vendedor_documento") or codigo),
                    "codigo_vendedor": codigo_plano, "venta": "1",
                    "porcentaje": only_digits(data.get("porcentaje_venta") or "100"),
                })
        else:
            for interm in intermediarios:
                linea += 1
                comision_rows.append({
                    "lote": lote, "linea": str(linea), "sr": "1",
                    "vendedor": interm.get("vendedor_documento") or interm.get("codigo_intermediario"),
                    "codigo_vendedor": interm.get("codigo_vendedor", "2"), "venta": "1",
                    "porcentaje": interm.get("porcentaje_venta", "100"),
                })
    if not comision_rows:
        return False
    try:
        response = httpx.post(
            f"{base_url}/legacy/db/import-real-lote",
            json={"lote": lote, "base": base, "tables": {"brwdcomisiones": comision_rows}},
            timeout=30.0,
        )
        return response.status_code == 200
    except Exception as exc:
        logger.warning("No pude insertar comisiones en legacy DB: %s", exc)
        return False


def _build_926_output(case_id: str, xlsx_profile: Dict[str, Any], checklist: Dict[str, Any], decision: Dict[str, Any], docs: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    if decision.get("recommended_status") != "aprobable":
        return {
            "available": False,
            "mode": "blocked",
            "reason": "El caso no está aprobable; el 926 permanece bloqueado.",
            "draft": None,
            "legacy": None,
        }

    profile = xlsx_profile.get("profile", {})
    lote = normalize_text(profile.get("lote") or profile.get("idtramite") or "")
    legacy_result = {"available": False, "ok": False, "error": "Sin lote para bridge legacy."}
    if lote:
        # Insertar datos de comisiones del Entrega Doc antes de generar el plano
        _push_comisiones_to_legacy(lote=lote, docs=docs or [], base="temporal")
        legacy_result = generate_legacy_flatfile_926_http(lote=lote)
        if not legacy_result.get("ok"):
            state_result = generate_legacy_flatfile_926(lote=lote)
            if state_result.get("ok"):
                legacy_result = state_result
    draft = _build_926_draft(profile, checklist, decision)
    if legacy_result.get("ok"):
        return {
            "available": True,
            "mode": "legacy",
            "reason": "",
            "draft": draft,
            "legacy": legacy_result,
        }
    return {
        "available": bool(draft),
        "mode": "draft",
        "reason": legacy_result.get("error", "Bridge legacy no disponible; se entrega borrador."),
        "draft": draft,
        "legacy": legacy_result,
    }


def _extract_tipoempresa_from_entrega_docs(docs: List[Dict[str, Any]]) -> Dict[str, str]:
    for doc in docs:
        if str(doc.get("document_type") or "") != "entrega_documentos":
            continue
        fields = doc.get("fields") or {}
        tipo_negocio = normalize_text(fields.get("tipo_negocio") or "")
        tipoempresa_homologado = normalize_text(fields.get("tipoempresa_homologado") or "")
        if tipo_negocio and tipoempresa_homologado:
            return {
                "tipo_negocio_detectado": tipo_negocio,
                "tipoempresa_homologado": tipoempresa_homologado,
                "tipoempresa_source_document": str(doc.get("filename") or ""),
                "tipoempresa_source": "entrega_documentos_pdf",
            }
    return {}


def _extract_todos_intermediarios(doc: Dict[str, Any]) -> List[Dict[str, str]]:
    """Extrae todos los intermediarios CPS-F-11. Ignora codigo 2 (Referido)."""
    text = normalize_text(doc.get("ocr_text") or doc.get("text_preview") or "")
    results = []
    tabla_start = re.search(
        r"c[oó]digo.{0,40}(?:nro|n[uú]mero|documento).{0,60}(?:nombre|apellido).{0,60}(?:participaci[oó]n|porcentaje)",
        text, flags=re.IGNORECASE|re.DOTALL
    )
    if not tabla_start:
        return results
    tabla_text = text[tabla_start.end():]
    fila_pattern = re.compile(
        r"\b(0?[1-4])\s+([\d]{6,12})\s+([\w\s\-\.]{4,60}?)\s+(\d{1,3})\s*%?(?=\s|$)",
        re.IGNORECASE
    )
    for m in fila_pattern.finditer(tabla_text):
        codigo_raw = only_digits(m.group(1))
        if codigo_raw == "2":
            continue
        codigo_plano = {"1": "2", "3": "3", "4": "4"}.get(codigo_raw, "2")
        nombre = m.group(3).strip() if m.group(3) else ""
        results.append({
            "codigo_intermediario": codigo_raw,
            "codigo_vendedor": codigo_plano,
            "vendedor_documento": only_digits(m.group(2)),
            "nombre_intermediario": nombre,
            "porcentaje_venta": m.group(4),
        })
    return results

def _validate_participacion_por_tipo(intermediarios: List[Dict[str, str]]) -> List[str]:
    """Valida que la suma de participación por tipo de código sea 100%."""
    errores = []
    from collections import defaultdict
    por_tipo: dict = defaultdict(list)
    for interm in intermediarios:
        codigo = interm.get("codigo_intermediario", "")
        pct = interm.get("porcentaje_venta", "0")
        try:
            por_tipo[codigo].append(float(pct.replace(",", ".").replace("%", "").strip()))
        except ValueError:
            pass
    for codigo, porcentajes in por_tipo.items():
        if len(porcentajes) > 1:
            total = sum(porcentajes)
            if abs(total - 100.0) > 0.5:
                tipo_nombre = {"1": "Consultor", "3": "Corredor/Agencia", "4": "Convenio"}.get(codigo, f"Tipo {codigo}")
                errores.append(
                    f"Comisiones intermediario: la suma de participación para {tipo_nombre} "
                    f"(código {codigo}) es {total:.0f}%, debe ser 100%."
                )
    return errores


def _extract_intermediario_codigo_y_porcentaje(doc: Dict[str, Any]) -> Dict[str, str]:
    fields = doc.get("fields") or {}
    direct_codigo = normalize_text(
        fields.get("intermediario_codigo")
        or fields.get("codigo_intermediario")
        or fields.get("codigo_del_intermediario")
        or ""
    )
    direct_porcentaje = normalize_text(
        fields.get("porcentaje_venta")
        or fields.get("porcentaje_de_venta")
        or fields.get("porcentaje")
        or fields.get("participacion")
        or ""
    )
    text = normalize_text(doc.get("ocr_text") or doc.get("text_preview") or "")

    # Patron CPS-F-11: tabla CODIGO | NRO DOCUMENTO | NOMBRE | % PARTICIPACION
    tabla_cpsf11 = re.search(
        r"(?:c[oó]digo|c\u00f3digo)[^\n]{0,80}(?:documento|nro)[^\n]{0,80}(?:nombre|apellido)[^\n]{0,80}(?:participaci[oó]n|participaci\u00f3n|porcentaje)[^\n]{0,40}?\s*([1-4])\s+(\d{7,12})\s+[\w][\w\s]{5,60}?\s+(\d{2,3})\b",
        text, flags=re.IGNORECASE
    )
    if tabla_cpsf11:
        return {
            "codigo_intermediario": only_digits(tabla_cpsf11.group(1)),
            "porcentaje_venta": normalize_text(tabla_cpsf11.group(3)),
            "vendedor_documento": only_digits(tabla_cpsf11.group(2)),
        }

    codigo = only_digits(direct_codigo)
    if not codigo:
        codigo_match = (
            re.search(r"codigo(?:\s+del)?\s+intermediario\s*[:\-]?\s*(\d{1,2})", text, flags=re.IGNORECASE)
            or re.search(r"intermediario\s*[:\-]?\s*(\d{1,2})", text, flags=re.IGNORECASE)
            or re.search(r"\bcodigo\s*[:\-]?\s*(\d{1,2})\b", text, flags=re.IGNORECASE)
        )
        if codigo_match:
            codigo = only_digits(codigo_match.group(1))

    porcentaje = direct_porcentaje
    if not porcentaje:
        porcentaje_match = (
            re.search(r"porcentaje(?:\s+de\s+la\s+venta)?\s*[:\-]?\s*(\d{1,3}(?:[.,]\d{1,2})?\s*%?)", text, flags=re.IGNORECASE)
            or re.search(r"participacion\s*[:\-]?\s*(\d{1,3}(?:[.,]\d{1,2})?\s*%?)", text, flags=re.IGNORECASE)
            or re.search(r"%\s+de\s+participaci[oó]n[^\d]{0,40}?(\d{1,3}(?:[.,]\d{1,2})?)", text, flags=re.IGNORECASE)
        )
        if porcentaje_match:
            porcentaje = normalize_text(porcentaje_match.group(1))

    # Patrón tabular: CÓDIGO | DOCUMENTO | NOMBRE | % — línea del CPS-F-11
    # Ej: "1 1000409427 CAROLINA MARULANDA GOMEZ 100"
    if not codigo or not porcentaje:
        # Buscar bloque después de encabezado de tabla de comisiones
        tabla_match = re.search(
            r"(?:codigo|código)[\s\S]{0,80}?(?:documento|nro)[\s\S]{0,80}?(?:nombre|apellido)[\s\S]{0,80}?(?:participaci[oó]n|porcentaje)"
            r"[\s\S]{0,20}?\n?\s*(\d{1,2})\s+(\d{6,12})\s+[A-ZÁÉÍÓÚÑ][\w\s\.áéíóúñÁÉÍÓÚÑ]{5,60}?\s+(\d{1,3}(?:[.,]\d{1,2})?)",
            text, flags=re.IGNORECASE
        )
        if tabla_match:
            if not codigo:
                codigo = only_digits(tabla_match.group(1))
            if not porcentaje:
                porcentaje = normalize_text(tabla_match.group(3))

    # Patrón directo: número corto seguido de cédula larga seguido de nombre seguido de 100
    # "1 1000409427 CAROLINA MARULANDA GOMEZ 100"
    if not codigo or not porcentaje:
        direct_match = re.search(
            r"\b(\d{1,2})\s+(\d{7,12})\s+[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑa-záéíóúñ\s]{8,50}\s+(\d{1,3})\b",
            text
        )
        if direct_match:
            candidate_codigo = only_digits(direct_match.group(1))
            candidate_pct = normalize_text(direct_match.group(3))
            if candidate_codigo in {"1","2","3","4"} and int(candidate_pct or 0) <= 100:
                if not codigo:
                    codigo = candidate_codigo
                if not porcentaje:
                    porcentaje = candidate_pct

    # Buscar "Código Pago de Comisiones" y extraer el código activo
    if not codigo:
        # "1 Consultor Comercial ARL" — el primero que aparece antes de "2 Referido" etc.
        comision_block = re.search(
            r"c[oó]digo\s+pago\s+de\s+comisiones[\s\S]{0,400}",
            text, flags=re.IGNORECASE
        )
        if comision_block:
            block = comision_block.group(0)
            # Buscar el código marcado — normalmente el primero listado
            first_code = re.search(r"\b([1-4])\b\s+(?:consultor|referido|corredor|convenio)", block, flags=re.IGNORECASE)
            if first_code:
                codigo = first_code.group(1)

    return {
        "codigo_intermediario": codigo,
        "porcentaje_venta": porcentaje,
    }


def _is_percentage_100(value: Any) -> bool:
    text = normalize_text(value)
    if not text:
        return False
    cleaned = text.replace("%", "").replace(" ", "")
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    else:
        cleaned = cleaned.replace(",", ".")
    try:
        return abs(float(cleaned) - 100.0) < 0.0001
    except ValueError:
        return False


def _map_naturaleza_to_tipoempresa_compat(naturaleza: str) -> str:
    value = normalize_text(naturaleza).upper()
    if value == "PRIVADA":
        return "2"
    if value in {"PUBLICA", "PÚBLICA"}:
        return "1"
    if value == "MIXTA":
        return "3"
    return ""


def _legacy_post(path: str, payload: Dict[str, Any], timeout: float = 120.0) -> Dict[str, Any]:
    base_url = str(settings.legacy_backend_url or "").strip().rstrip("/")
    if not base_url:
        raise RuntimeError("legacy_backend_url no configurado.")
    url = f"{base_url}/{path.lstrip('/')}"
    response = httpx.post(url, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()


def _legacy_build_926_http(
    lote: str,
    base: str = "temporal",
    strict_validate: bool = True,
    fecha_proceso: str = "",
    lote_usuario: str = "",
) -> Dict[str, Any]:
    base_url = str(settings.legacy_backend_url or "").strip().rstrip("/")
    if not base_url:
        raise RuntimeError("legacy_backend_url no configurado.")
    response = httpx.get(
        f"{base_url}/legacy/flatfile/build",
        params={
            "lote": lote,
            "from_db": "true",
            "base": base,
            "strict_validate": "true" if strict_validate else "false",
            "fecha_proceso": only_digits(fecha_proceso)[:8],
            "lote_usuario": only_digits(lote_usuario),
        },
        timeout=120.0,
    )
    if response.status_code != 200:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:300]}")
    return {
        "filename": f"BkCargue_{lote or 'generated'}.txt",
        "content": response.text,
        "headers": dict(response.headers),
    }


def _get_xlsx_file_entry(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    for item in payload.get("files", []):
        filename = str(item.get("filename", "")).lower()
        if filename.endswith((".xlsx", ".xlsm", ".xls")):
            return item
    return None


def _build_manifest_step(payload: Dict[str, Any], analysis: Dict[str, Any]) -> Dict[str, Any]:
    profile = (analysis.get("xlsx_profile") or {}).get("profile", {})
    lote = normalize_text(profile.get("lote") or profile.get("idtramite") or payload.get("id") or "")
    lines = [
        f"CASE={payload.get('id')}",
        f"LOTE={lote or slugify(profile.get('empresa') or payload.get('label') or 'lote')}",
        f"EMPRESA={normalize_text(profile.get('empresa', ''))}",
        f"NIT={only_digits(profile.get('nit', ''))}",
        f"TIPO_AFILIADO={normalize_text(profile.get('tipo_afiliado', ''))}",
        f"DOCUMENTO={only_digits(profile.get('documento', ''))}",
    ]
    return {
        "filename": f"{slugify(lote or payload.get('label') or payload.get('id') or 'lote')}.txt",
        "content": "\n".join(lines).strip() + "\n",
        "lote": lote or slugify(profile.get("empresa") or payload.get("label") or "lote"),
    }


def _build_contrato_clean(xlsx_profile: Dict[str, Any], docs: List[Dict[str, Any]]) -> Dict[str, Any]:
    profile = xlsx_profile.get("profile", {})
    flat_pairs = xlsx_profile.get("flat_pairs", {})
    employer_doc = only_digits(profile.get("nit") or profile.get("documento_empleador") or "")
    employer_name = normalize_text(profile.get("empresa") or "EMPRESA EN PROCESO")
    worker_name = normalize_text(profile.get("nombre") or "")
    worker_doc = only_digits(profile.get("documento") or "")
    rep_name = normalize_text(flat_pairs.get("nombrerepresentantelegal") or worker_name or employer_name)
    rep_doc = only_digits(flat_pairs.get("numerodocumentorepresnetantelegal") or worker_doc)
    inicio = flat_pairs.get("iniciocobertura") or datetime.now().strftime("%Y-%m-%d")
    radicacion = flat_pairs.get("fecharadicacion") or datetime.now().strftime("%Y-%m-%d")
    actividad = only_digits(flat_pairs.get("actividadeconomicaempleador") or "5861001") or "5861001"
    tipo_aportante = normalize_text(flat_pairs.get("tipoaportante") or "05")
    naturaleza = normalize_text(flat_pairs.get("naturalezajuridica") or "Privada")
    ciudad = normalize_text(flat_pairs.get("ciudadempleador") or "11001")
    localidad = normalize_text(flat_pairs.get("localidadempleador") or "NA")
    zona = normalize_text(flat_pairs.get("zonaempleador") or "U")
    direccion = normalize_text(flat_pairs.get("direccionempleador") or "DIRECCION PENDIENTE")
    telefono = only_digits(flat_pairs.get("telefonoprincipalempleador") or "6010000000")
    email = normalize_text(flat_pairs.get("correoelectronicoempleador") or "contacto@empresa.test").lower()
    contrato_num = only_digits(flat_pairs.get("numerocontrato") or employer_doc or worker_doc or "1001")

    lines = [
        f"1. Apellidos y nombres o razón social|{employer_name}|2. Tipo de documento|NI|3. Número de documento o NIT|{employer_doc}",
        f"1. Tipo de trámite|X|2. Naturaleza jurídica del empleador|{naturaleza}|3. Tipo de aportante|{tipo_aportante}",
        f"4. Tipo de negocio homologado|{normalize_text(profile.get('tipoempresa_homologado') or '')}|Tipo de negocio detectado|{normalize_text(profile.get('tipo_negocio_detectado') or '')}",
        f"4. Apellidos y nombres del Representante Legal|{rep_name}",
        f"5. Tipo de documento|CC|6. Número de documento|{rep_doc}|7. Correo electrónico|{email}",
        f"1. Datos de la sede principal|Dirección de la sede principal|{direccion}|Teléfono fijo/celular|{telefono}",
        f"|1|PRINCIPAL|Correo electrónico|{email}",
        f"Municipio/Distrito|{ciudad}|Zona|{zona}|Localidad/Comuna|{localidad}|Departamento|BOGOTA D.C.",
        f"1. ARL de la cual se traslada|10|2. Clase de riesgo|I|Actividad económica|{actividad}",
        f"{radicacion}T00:00:00|{inicio}T00:00:00|{contrato_num}|01",
    ]
    return {
        "filename": "contrato_clean_auto.txt",
        "content": "\n".join(lines) + "\n",
        "lines": len(lines),
    }


def _ensure_tipoempresa_in_contrato_clean(contrato_clean: Optional[Dict[str, Any]], xlsx_profile: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(contrato_clean, dict):
        return contrato_clean
    content = str(contrato_clean.get("content") or "")
    if not content.strip():
        return contrato_clean

    profile = (xlsx_profile or {}).get("profile") or {}
    tipoempresa = normalize_text(profile.get("tipoempresa_homologado") or "")
    tipo_negocio = normalize_text(profile.get("tipo_negocio_detectado") or "")
    if not tipoempresa and not tipo_negocio:
        return contrato_clean

    tipo_line = f"4. Tipo de negocio homologado|{tipoempresa}|Tipo de negocio detectado|{tipo_negocio}"
    lines = content.splitlines()
    replaced = False
    normalized_lines: List[str] = []
    for line in lines:
        if "tipo de negocio homologado" in line.lower():
            normalized_lines.append(tipo_line)
            replaced = True
        else:
            normalized_lines.append(line)

    if not replaced:
        insert_at = 2 if len(normalized_lines) >= 2 else len(normalized_lines)
        normalized_lines.insert(insert_at, tipo_line)

    updated = dict(contrato_clean)
    updated["content"] = "\n".join(normalized_lines).rstrip() + "\n"
    updated["lines"] = len(normalized_lines)
    return updated


def _build_independientes_clean(xlsx_profile: Dict[str, Any]) -> Dict[str, Any]:
    profile = xlsx_profile.get("profile", {})
    flat_pairs = xlsx_profile.get("flat_pairs", {})
    worker_doc = only_digits(profile.get("documento") or "")
    full_name = normalize_text(profile.get("nombre") or "TRABAJADOR INDEPENDIENTE")
    parts = full_name.split()
    primer_nombre = parts[0] if parts else "TRABAJADOR"
    segundo_nombre = parts[1] if len(parts) > 1 else ""
    primer_apellido = parts[2] if len(parts) > 2 else "INDEPENDIENTE"
    segundo_apellido = parts[3] if len(parts) > 3 else ""
    inicio = flat_pairs.get("iniciocobertura") or datetime.now().strftime("%Y-%m-%d")
    fin = flat_pairs.get("finalizacioncontrato") or inicio
    ibc = only_digits(flat_pairs.get("ibc") or flat_pairs.get("ingresomensual") or "1423500") or "1423500"
    actividad = only_digits(flat_pairs.get("actividadeconomicaempleador") or "5861001") or "5861001"
    fecha_nacimiento = only_digits(flat_pairs.get("fechanacimiento") or "19900101") or "19900101"
    inicio_legacy = only_digits(inicio) or datetime.now().strftime("%Y%m%d")
    fin_legacy = only_digits(fin) or inicio_legacy
    departamento = only_digits(flat_pairs.get("departamento") or "11") or "11"
    municipio = only_digits(flat_pairs.get("ciudad") or flat_pairs.get("municipio") or "11001") or "11001"
    zona = normalize_text(flat_pairs.get("zona") or "U").upper()[:1] or "U"
    localidad = normalize_text(flat_pairs.get("localidad") or "LOCALIDAD")
    direccion = normalize_text(flat_pairs.get("direccion") or "DIRECCION RESIDENCIA")
    telefono = only_digits(flat_pairs.get("telefono") or "6010000") or "6010000"
    celular = only_digits(flat_pairs.get("celular") or "3000000000") or "3000000000"
    correo = normalize_text(flat_pairs.get("correo") or "trabajador@test.com").lower()
    eps = normalize_text(flat_pairs.get("eps") or "EPS DEMO").upper()
    codigo_eps = only_digits(flat_pairs.get("codigo_eps") or "00001") or "00001"
    afp = normalize_text(flat_pairs.get("afp") or "AFP DEMO").upper()
    codigo_afp = only_digits(flat_pairs.get("codigo_afp") or "00002") or "00002"
    tipo_cotizante = only_digits(flat_pairs.get("tipo_cotizante") or "51") or "51"
    subtipo_cotizante = only_digits(flat_pairs.get("subtipo_cotizante") or "0") or "0"
    tipo_contrato = normalize_text(flat_pairs.get("tipo_contrato") or "1")
    valor_contrato = only_digits(flat_pairs.get("valor_contrato") or ibc) or ibc
    nombre_actividad = normalize_text(flat_pairs.get("nombre_actividad") or "ACTIVIDAD ECONOMICA")
    clase_riesgo = normalize_text(flat_pairs.get("clase_riesgo") or "1")
    tasa_riesgo = normalize_text(flat_pairs.get("tasa_riesgo") or "0.522")
    lote = normalize_text(profile.get("lote") or profile.get("idtramite") or "AUTO")
    row = {field: "" for field in LEGACY_INDEPENDIENTES_FIELDS}
    row.update(
        {
            "sr": "2",
            "linea": "1",
            "tipodocumento": "CC",
            "documento": worker_doc,
            "primer_apellido": primer_apellido.upper(),
            "segundo_apellido": segundo_apellido.upper(),
            "primer_nombre": primer_nombre.upper(),
            "segundo_nombre": segundo_nombre.upper(),
            "fecha_nacimiento": fecha_nacimiento,
            "sexo": "M",
            "direccion": direccion.upper(),
            "departamento": departamento,
            "municipio": municipio,
            "zona": zona,
            "localidad": localidad.upper(),
            "telefono": telefono,
            "celular": celular,
            "correo": correo,
            "eps": eps,
            "codigo_eps": codigo_eps,
            "afp": afp,
            "codigo_afp": codigo_afp,
            "tipo_cotizante": tipo_cotizante,
            "subtipo_cotizante": subtipo_cotizante,
            "modalidad": "PRESENCIAL",
            "tipo_contrato": tipo_contrato,
            "transporte": "NO",
            "fecha_inicio_contrato": inicio_legacy,
            "fecha_fin_contrato": fin_legacy,
            "meses_contrato": "1",
            "valor_contrato": valor_contrato,
            "valor_mensual": ibc,
            "ibc": ibc,
            "actividad_economica": actividad,
            "nombre_actividad": nombre_actividad.upper(),
            "clase_riesgo": clase_riesgo,
            "tasa_riesgo": tasa_riesgo,
            "lunes": "X",
            "martes": "X",
            "miercoles": "X",
            "jueves": "X",
            "viernes": "X",
            "codigo_ct": "000001",
            "nombre_ct": "PRINCIPAL",
            "actividad_economica_ct": actividad,
            "clase_riesgo_ct": clase_riesgo,
            "tasa_riesgo_ct": tasa_riesgo,
            "direccion_ct": "DIRECCION CT",
            "departamento_ct": departamento,
            "ciudad_ct": municipio,
            "zona_ct": zona,
            "telefono_ct": telefono,
            "celular_ct": celular,
            "correo_ct": correo,
            "localidad_ct": localidad.upper(),
            "lote": lote,
            "tipo_salario": "VARIABLE",
        }
    )
    lines = ["!".join(str(row[field]) for field in LEGACY_INDEPENDIENTES_FIELDS)]
    return {"filename": "independientes_clean_auto.txt", "content": "\n".join(lines) + "\n", "lines": 1}


def _workflow_step(
    name: str,
    title: str,
    status: str,
    detail: str = "",
    payload: Optional[Dict[str, Any]] = None,
    duration_ms: Optional[int] = None,
) -> Dict[str, Any]:
    step = {
        "name": name,
        "title": title,
        "status": status,
        "detail": detail,
        "payload": payload or {},
        "at": utc_now(),
    }
    if duration_ms is not None:
        step["duration_ms"] = int(duration_ms)
    return step


def run_case_workflow(case_id: str) -> Dict[str, Any]:
    workflow_started = perf_counter()
    analyze_started = perf_counter()
    payload = analyze_case(case_id)
    analyze_duration_ms = int((perf_counter() - analyze_started) * 1000)
    analysis = payload.get("analysis") or {}
    profile = (analysis.get("xlsx_profile") or {}).get("profile", {})
    xlsx_entry = _get_xlsx_file_entry(payload)
    xlsx_bytes = Path(xlsx_entry["stored_path"]).read_bytes() if xlsx_entry else b""
    xlsx_b64 = base64.b64encode(xlsx_bytes).decode("ascii") if xlsx_bytes else ""
    flat_pairs = ((analysis.get("xlsx_profile") or {}).get("flat_pairs", {}) or {})
    lote = normalize_text(profile.get("lote") or profile.get("idtramite") or "")
    idtramite = only_digits(profile.get("idtramite") or flat_pairs.get("idtramite") or "")
    legacy_lote_usuario = only_digits(
        profile.get("lote_usuario") or flat_pairs.get("lote_usuario") or flat_pairs.get("lt_usuario") or payload.get("lote_usuario") or ""
    )
    legacy_fecha_proceso = only_digits(
        profile.get("fecha_proceso") or flat_pairs.get("fecha_proceso") or payload.get("fecha_proceso") or ""
    )[:8]
    if len(legacy_fecha_proceso) != 8:
        legacy_fecha_proceso = datetime.now().strftime("%Y%m%d")
    base = "temporal"
    timeline: List[Dict[str, Any]] = []
    final_report = analysis.get("reporte_ejecutivo")
    output_926 = analysis.get("output_926")

    timeline.append(
        _workflow_step(
            "prevalidacion_documental",
            "Prevalidación documental",
            "ok" if analysis.get("decision", {}).get("recommended_status") == "aprobable" else "blocked",
            analysis.get("decision", {}).get("summary", ""),
            {"decision": analysis.get("decision"), "checklist": analysis.get("checklist")},
            duration_ms=analyze_duration_ms,
        )
    )
    if analysis.get("decision", {}).get("recommended_status") != "aprobable":
        workflow = {
            "status": "stopped_prevalidacion",
            "current_step": "prevalidacion_documental",
            "steps": timeline,
            "stop_reason": "La prevalidación documental no fue aprobada.",
            "executive_report_precheck": analysis.get("reporte_ejecutivo"),
            "executive_report_final": None,
            "output_926": output_926,
            "timings": {
                "total_duration_ms": int((perf_counter() - workflow_started) * 1000),
                "analysis_duration_ms": analyze_duration_ms,
            },
        }
        payload["analysis"]["workflow_run"] = workflow
        payload["updated_at"] = utc_now()
        save_case(payload)
        return payload

    manifest_started = perf_counter()
    manifest = _build_manifest_step(payload, analysis)
    lote = lote or manifest["lote"]
    idtramite = idtramite or str(int(datetime.now().timestamp()))[-8:]
    if not legacy_lote_usuario:
        legacy_lote_usuario = build_generated_lote_usuario(legacy_fecha_proceso)
    payload["lote_usuario"] = legacy_lote_usuario
    payload["fecha_proceso"] = legacy_fecha_proceso
    analysis.setdefault("xlsx_profile", {}).setdefault("profile", {})
    analysis["xlsx_profile"]["profile"]["lote_usuario"] = legacy_lote_usuario
    analysis["xlsx_profile"]["profile"]["fecha_proceso"] = legacy_fecha_proceso
    timeline.append(
        _workflow_step(
            "manifesto_paso1",
            "Generación de manifiesto",
            "ok",
            f"Manifiesto {manifest['filename']} listo para lote {lote}.",
            {"manifest": manifest},
            duration_ms=int((perf_counter() - manifest_started) * 1000),
        )
    )

    try:
        lote_started = perf_counter()
        bootstrap_out = _legacy_post(
            "ruta-inclusion/bootstrap-tramite",
            {
                "base": base,
                "idtramite": idtramite,
                "lote": lote,
                "estado": "Estudio",
                "usuario": "nova_case_workflow",
                "lote_usuario": legacy_lote_usuario,
                "fecha_proceso": legacy_fecha_proceso,
            },
            timeout=60.0,
        )
        upload_out = _legacy_post("legacy/ls/upload-archivo-txt", {"fileid": lote, "content": manifest["content"]}, timeout=60.0)
        read_out = _legacy_post("legacy/opc", {"sw": "LS", "sw1": "archivo_txt", "fileid": lote}, timeout=60.0)
        deliver_out = _legacy_post(
            "legacy/opc",
            {
                "sw": "LS",
                "sw1": "fileid-data",
                "fileid": lote,
                "var1": "CC",
                "ol": "1",
                "userid": "nova_case_workflow",
                "fechabd": datetime.now().strftime("%Y%m%d"),
                "fechashora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
            timeout=120.0,
        )
        timeline.append(
            _workflow_step(
                "carga_lote_legacy",
                "Carga de lote TXT",
                "ok",
                f"Lote {lote} e idtrámite {idtramite} entregados al clone legacy.",
                {"bootstrap": bootstrap_out, "upload": upload_out, "read": read_out, "deliver": deliver_out},
                duration_ms=int((perf_counter() - lote_started) * 1000),
            )
        )
    except Exception as exc:
        timeline.append(_workflow_step("carga_lote_legacy", "Carga de lote TXT", "failed", str(exc), duration_ms=int((perf_counter() - lote_started) * 1000)))
        workflow = {
            "status": "stopped_lote",
            "current_step": "carga_lote_legacy",
            "steps": timeline,
            "stop_reason": f"No pude cargar el lote al clone legacy: {exc}",
            "executive_report_precheck": analysis.get("reporte_ejecutivo"),
            "executive_report_final": None,
            "output_926": output_926,
            "timings": {
                "total_duration_ms": int((perf_counter() - workflow_started) * 1000),
                "analysis_duration_ms": analyze_duration_ms,
            },
        }
        payload["analysis"]["workflow_run"] = workflow
        payload["updated_at"] = utc_now()
        save_case(payload)
        return payload

    clean_started = perf_counter()
    timeline.append(
        _workflow_step(
            "limpieza_preparacion",
            "Limpieza y preparación",
            "ok",
            "El expediente quedó limpio y clasificado para validaciones.",
            {"documents": analysis.get("documents", [])},
            duration_ms=0,
        )
    )

    clean_output: Dict[str, Any] = {}
    if xlsx_entry and xlsx_bytes:
        clean_output = _generate_clean_via_legacy_nova(xlsx_entry["filename"], xlsx_bytes)
        if not bool(clean_output.get("ok")):
            workbook = load_workbook(io.BytesIO(xlsx_bytes), data_only=True)
            clean_output = _generate_clean_from_workbook(workbook, xlsx_entry["filename"])
            clean_output["_source"] = "local_fallback"

    contrato_clean = clean_output.get("contrato_clean") if isinstance(clean_output.get("contrato_clean"), dict) else None
    trabajadores_clean_multi = clean_output.get("trabajadores_clean_multi") if isinstance(clean_output.get("trabajadores_clean_multi"), list) else []
    independientes_clean = clean_output.get("independientes_clean") if isinstance(clean_output.get("independientes_clean"), dict) else None
    if (not contrato_clean or not str(contrato_clean.get("content") or "").strip()) and xlsx_entry:
        contrato_clean = _build_contrato_clean(analysis.get("xlsx_profile") or {}, analysis.get("documents") or [])
    contrato_clean = _ensure_tipoempresa_in_contrato_clean(contrato_clean, analysis.get("xlsx_profile") or {})
    if not trabajadores_clean_multi and xlsx_entry:
        fallback_indep = _build_independientes_clean(analysis.get("xlsx_profile") or {})
        if str(fallback_indep.get("content") or "").strip():
            independientes_clean = fallback_indep

    contract_fields = _extract_employer_from_contract_text(str((contrato_clean or {}).get("content") or ""))
    if contract_fields:
        company_name = normalize_text(contract_fields.get("empresa", ""))
        nit_value = only_digits(contract_fields.get("nit", ""))
        rep_name = normalize_text(contract_fields.get("representante_legal", ""))
        rep_doc = only_digits(contract_fields.get("doc_representante", ""))
        analysis.setdefault("xlsx_profile", {}).setdefault("profile", {})
        if company_name and len(company_name) >= 5:
            analysis["xlsx_profile"]["profile"]["empresa"] = profile.get("empresa") or company_name
        if 8 <= len(nit_value) <= 12:
            employer_document_hint = only_digits(profile.get("documento_empleador") or nit_value)
            analysis["xlsx_profile"]["profile"]["nit"] = employer_document_hint or nit_value
            analysis["xlsx_profile"]["profile"]["documento_empleador"] = employer_document_hint or nit_value
        if rep_name and len(rep_name) >= 5:
            analysis["xlsx_profile"]["profile"]["nombre"] = profile.get("nombre") or rep_name
        if 6 <= len(rep_doc) <= 15:
            analysis["xlsx_profile"]["profile"]["documento"] = profile.get("documento") or rep_doc
        profile = analysis["xlsx_profile"]["profile"]

    try:
        import_started = perf_counter()
        empleador_out = _legacy_post(
            "ruta-inclusion/importar-empleador-contrato",
            {
                "base": base,
                "idtramite": idtramite,
                "content": contrato_clean["content"],
                "strict_validate": True,
                "usuario": "nova_case_workflow",
            },
            timeout=120.0,
        )
        sedes_out: List[Dict[str, Any]] = []
        trabajadores_out: List[Dict[str, Any]] = []
        for index, sede_clean in enumerate(trabajadores_clean_multi):
            replace = index == 0
            sede_result = _legacy_post(
                "ruta-inclusion/importar-sede-contrato",
                {
                    "base": base,
                    "idtramite": idtramite,
                    "content": sede_clean["content"],
                    "strict_validate": False,
                    "replace_existing": replace,
                    "auto_skip_empty_clean": True,
                    "usuario": "nova_case_workflow",
                },
                timeout=120.0,
            )
            sedes_out.append({"file": sede_clean.get("filename"), "result": sede_result})
            if bool(sede_result.get("skipped")):
                continue
            sed_sr = int(sede_result.get("sr_inserted") or 0)
            worker_payload = {
                "base": base,
                "idtramite": idtramite,
                "content": sede_clean["content"],
                "contrato_content": contrato_clean["content"],
                "strict_validate": True,
                "replace_existing": replace,
                "allow_empty": True,
                "usuario": "nova_case_workflow",
            }
            if sed_sr > 0:
                worker_payload["sr_override"] = sed_sr
            worker_result = _legacy_post("ruta-inclusion/importar-trabajadores-contrato", worker_payload, timeout=120.0)
            trabajadores_out.append({"file": sede_clean.get("filename"), "result": worker_result})

        indep_out: List[Dict[str, Any]] = []
        if independientes_clean and str(independientes_clean.get("content") or "").strip():
            indep_result = _legacy_post(
                "ruta-inclusion/importar-trabajadores-contrato",
                {
                    "base": base,
                    "idtramite": idtramite,
                    "content": independientes_clean["content"],
                    "contrato_content": contrato_clean["content"],
                    "strict_validate": True,
                    "replace_existing": not trabajadores_clean_multi,
                    "allow_empty": True,
                    "source_kind": "independientes_legacy",
                    "usuario": "nova_case_workflow",
                },
                timeout=120.0,
            )
            indep_out.append({"file": independientes_clean.get("filename"), "result": indep_result})

        comisiones_out: List[Dict[str, Any]] = []
        for doc in analysis.get("documents", []):
            if doc.get("document_type") not in {"entrega_documentos", "comision"}:
                continue
            content = str(doc.get("ocr_text") or doc.get("text_preview") or "").strip()
            haystack = normalize_haystack(content)
            if "reconocimiento variable integral" not in haystack and "participacion" not in haystack and "porcentaje" not in haystack:
                continue
            try:
                com_result = _legacy_post(
                    "ruta-inclusion/importar-comisiones-contrato",
                    {
                        "base": base,
                        "idtramite": idtramite,
                        "content": content,
                        "replace_existing": True,
                        "usuario": "nova_case_workflow",
                    },
                    timeout=120.0,
                )
                comisiones_out.append({"file": doc.get("filename"), "result": com_result})
                if bool(com_result.get("rows_inserted", 0)):
                    break
            except Exception as com_exc:
                comisiones_out.append({"file": doc.get("filename"), "error": str(com_exc)})

        timeline.append(
            _workflow_step(
                "importacion_proc",
                "Importación a proc_servicios",
                "ok",
                f"Se importó empleador, {len(sedes_out)} sede(s) y trabajadores para idtrámite {idtramite}.",
                {
                    "idtramite": idtramite,
                    "clean_source": clean_output.get("_source", "local"),
                    "contrato_clean": contrato_clean,
                    "trabajadores_clean_multi": [
                        {"filename": item.get("filename"), "lines": item.get("lines")}
                        for item in trabajadores_clean_multi
                    ],
                    "independientes_clean": (
                        {"filename": independientes_clean.get("filename"), "lines": independientes_clean.get("lines")}
                        if independientes_clean
                        else None
                    ),
                    "empleador": empleador_out,
                    "sedes": sedes_out,
                    "trabajadores": trabajadores_out,
                    "independientes": indep_out,
                    "comisiones": comisiones_out,
                },
                duration_ms=int((perf_counter() - import_started) * 1000),
            )
        )
        if timeline and timeline[-2]["name"] == "limpieza_preparacion":
            timeline[-2]["duration_ms"] = int((perf_counter() - clean_started) * 1000) - int(timeline[-1].get("duration_ms") or 0)
    except Exception as exc:
        timeline.append(_workflow_step("importacion_proc", "Importación a proc_servicios", "failed", str(exc), duration_ms=int((perf_counter() - import_started) * 1000)))
        workflow = {
            "status": "stopped_importacion",
            "current_step": "importacion_proc",
            "steps": timeline,
            "stop_reason": f"No pude importar el caso a proc_servicios: {exc}",
            "executive_report_precheck": analysis.get("reporte_ejecutivo"),
            "executive_report_final": None,
            "output_926": output_926,
            "timings": {
                "total_duration_ms": int((perf_counter() - workflow_started) * 1000),
                "analysis_duration_ms": analyze_duration_ms,
            },
        }
        payload["analysis"]["workflow_run"] = workflow
        payload["updated_at"] = utc_now()
        save_case(payload)
        return payload

    try:
        sync_started = perf_counter()
        import_proc_out = _legacy_post(
            "legacy/db/import-proc-servicios",
            {
                "base": base,
                "lote": lote,
                "estado": "Estudio",
                "idtramite": idtramite,
                "limit": 200,
                "apply_to_db": True,
            },
            timeout=120.0,
        )
        timeline.append(
            _workflow_step(
                "sync_engine",
                "Sincronización al engine legacy",
                "ok",
                f"El engine legacy quedó sincronizado para lote {lote}.",
                {"import": import_proc_out},
                duration_ms=int((perf_counter() - sync_started) * 1000),
            )
        )
    except Exception as exc:
        timeline.append(_workflow_step("sync_engine", "Sincronización al engine legacy", "failed", str(exc), duration_ms=int((perf_counter() - sync_started) * 1000)))
        workflow = {
            "status": "stopped_sync_engine",
            "current_step": "sync_engine",
            "steps": timeline,
            "stop_reason": f"No pude sincronizar proc_servicios al engine legacy: {exc}",
            "executive_report_precheck": analysis.get("reporte_ejecutivo"),
            "executive_report_final": None,
            "output_926": output_926,
            "timings": {
                "total_duration_ms": int((perf_counter() - workflow_started) * 1000),
                "analysis_duration_ms": analyze_duration_ms,
            },
        }
        payload["analysis"]["workflow_run"] = workflow
        payload["updated_at"] = utc_now()
        save_case(payload)
        return payload

    pre_payload: Dict[str, Any] = {"lote": lote, "from_db": True, "base": "temporal"}
    if xlsx_b64:
        pre_payload["excel_file_base64"] = xlsx_b64
    try:
        prebuild_started = perf_counter()
        prebuild_out = _legacy_post("legacy/rules/prebuild-check", pre_payload, timeout=120.0)
        prebuild_ok = bool(prebuild_out.get("ok", False))
        timeline.append(
            _workflow_step(
                "prebuild_validaciones",
                "Prebuild y validaciones",
                "ok" if prebuild_ok else "blocked",
                "Prebuild legacy aprobado." if prebuild_ok else "Prebuild legacy bloqueó el flujo.",
                {"prebuild": prebuild_out},
                duration_ms=int((perf_counter() - prebuild_started) * 1000),
            )
        )
        if not prebuild_ok:
            workflow = {
                "status": "stopped_prebuild",
                "current_step": "prebuild_validaciones",
                "steps": timeline,
                "stop_reason": "El prebuild legacy no fue aprobado.",
                "executive_report_precheck": analysis.get("reporte_ejecutivo"),
                "executive_report_final": None,
                "output_926": output_926,
                "timings": {
                    "total_duration_ms": int((perf_counter() - workflow_started) * 1000),
                    "analysis_duration_ms": analyze_duration_ms,
                },
            }
            payload["analysis"]["workflow_run"] = workflow
            payload["updated_at"] = utc_now()
            save_case(payload)
            return payload
    except Exception as exc:
        timeline.append(_workflow_step("prebuild_validaciones", "Prebuild y validaciones", "failed", str(exc), duration_ms=int((perf_counter() - prebuild_started) * 1000)))
        workflow = {
            "status": "stopped_prebuild",
            "current_step": "prebuild_validaciones",
            "steps": timeline,
            "stop_reason": f"No pude ejecutar prebuild legacy: {exc}",
            "executive_report_precheck": analysis.get("reporte_ejecutivo"),
            "executive_report_final": None,
            "output_926": output_926,
            "timings": {
                "total_duration_ms": int((perf_counter() - workflow_started) * 1000),
                "analysis_duration_ms": analyze_duration_ms,
            },
        }
        payload["analysis"]["workflow_run"] = workflow
        payload["updated_at"] = utc_now()
        save_case(payload)
        return payload

    try:
        report_prev_started = perf_counter()
        pre_report_payload: Dict[str, Any] = {
            "lote": lote,
            "base": base,
            "from_db": True,
            "generate_926_if_missing": False,
        }
        if xlsx_b64:
            pre_report_payload["excel_file_base64"] = xlsx_b64
        pre_report = _legacy_post("legacy/reporte-ejecutivo-contrato", pre_report_payload, timeout=120.0)
        timeline.append(
            _workflow_step(
                "reporte_previo",
                "Reporte ejecutivo previo",
                "ok",
                "Reporte ejecutivo previo al 926 generado.",
                {"report": pre_report},
                duration_ms=int((perf_counter() - report_prev_started) * 1000),
            )
        )
    except Exception as exc:
        pre_report = None
        timeline.append(_workflow_step("reporte_previo", "Reporte ejecutivo previo", "failed", str(exc), duration_ms=int((perf_counter() - report_prev_started) * 1000)))

    try:
        gen926_started = perf_counter()
        # Insertar comisiones del Entrega Doc antes de generar el plano
        _workflow_docs = (analysis.get("documents") or [])
        _push_comisiones_to_legacy(lote=lote, docs=_workflow_docs, base=base)
        generated_926 = _legacy_build_926_http(
            lote=lote,
            base=base,
            strict_validate=True,
            fecha_proceso=legacy_fecha_proceso,
            lote_usuario=legacy_lote_usuario,
        )
        output_926 = {
            "available": True,
            "mode": "legacy",
            "reason": "",
            "draft": analysis.get("draft_926"),
            "legacy": {"available": True, "ok": True, **generated_926},
        }
        timeline.append(
            _workflow_step(
                "generacion_926",
                "Generación 926",
                "ok",
                f"Archivo 926 generado para lote {lote}.",
                {"filename": generated_926.get("filename")},
                duration_ms=int((perf_counter() - gen926_started) * 1000),
            )
        )
    except Exception as exc:
        timeline.append(_workflow_step("generacion_926", "Generación 926", "failed", str(exc), duration_ms=int((perf_counter() - gen926_started) * 1000)))
        workflow = {
            "status": "stopped_926",
            "current_step": "generacion_926",
            "steps": timeline,
            "stop_reason": f"No pude generar el 926 legacy: {exc}",
            "executive_report_precheck": analysis.get("reporte_ejecutivo"),
            "executive_report_final": pre_report,
            "output_926": analysis.get("output_926"),
            "timings": {
                "total_duration_ms": int((perf_counter() - workflow_started) * 1000),
                "analysis_duration_ms": analyze_duration_ms,
            },
        }
        payload["analysis"]["workflow_run"] = workflow
        payload["updated_at"] = utc_now()
        save_case(payload)
        return payload

    try:
        report_final_started = perf_counter()
        final_report_payload: Dict[str, Any] = {
            "lote": lote,
            "base": base,
            "from_db": True,
            "generate_926_if_missing": True,
        }
        if xlsx_b64:
            final_report_payload["excel_file_base64"] = xlsx_b64
        final_report = _legacy_post("legacy/reporte-ejecutivo-contrato", final_report_payload, timeout=120.0)
        if isinstance(final_report, dict):
            final_report.setdefault("fecha_proceso", legacy_fecha_proceso)
            try:
                final_report.setdefault("fecha_proceso_human", _format_date_es(datetime.strptime(legacy_fecha_proceso, "%Y%m%d")))
            except ValueError:
                final_report.setdefault("fecha_proceso_human", legacy_fecha_proceso)
            final_summary = final_report.setdefault("resumen_ejecutivo", {})
            if isinstance(final_summary, dict):
                final_summary.setdefault("fecha_proceso", legacy_fecha_proceso)
                final_summary.setdefault("fecha_proceso_human", final_report.get("fecha_proceso_human", legacy_fecha_proceso))
                pre_summary = ((analysis.get("reporte_ejecutivo") or {}).get("resumen_ejecutivo") or {})
                if isinstance(pre_summary, dict):
                    final_summary.setdefault("nomina_total", pre_summary.get("nomina_total"))
                    final_report.setdefault("nomina_total", pre_summary.get("nomina_total"))
        timeline.append(
            _workflow_step(
                "reporte_final",
                "Reporte ejecutivo final",
                "ok",
                "Reporte ejecutivo final consolidado.",
                {"report": final_report},
                duration_ms=int((perf_counter() - report_final_started) * 1000),
            )
        )
    except Exception as exc:
        timeline.append(_workflow_step("reporte_final", "Reporte ejecutivo final", "failed", str(exc), duration_ms=int((perf_counter() - report_final_started) * 1000)))

    cierre_started = perf_counter()
    timeline.append(
        _workflow_step(
            "cierre_flujo",
            "Cierre del flujo",
            "ok",
            "Flujo automático completado.",
            {"lote": lote},
            duration_ms=int((perf_counter() - cierre_started) * 1000),
        )
    )
    workflow = {
        "status": "completed",
        "current_step": "cierre_flujo",
        "steps": timeline,
        "stop_reason": "",
        "executive_report_precheck": analysis.get("reporte_ejecutivo"),
        "executive_report_final": final_report,
        "output_926": output_926,
        "timings": {
            "total_duration_ms": int((perf_counter() - workflow_started) * 1000),
            "analysis_duration_ms": analyze_duration_ms,
        },
    }
    payload["analysis"]["output_926"] = output_926
    payload["analysis"]["workflow_run"] = workflow
    payload["updated_at"] = utc_now()
    save_case(payload)
    return payload


def analyze_case(case_id: str) -> Dict[str, Any]:
    analyze_started = perf_counter()
    payload = load_case(case_id)
    previous_analysis = payload.get("analysis") or {}
    previous_manual_review = previous_analysis.get("manual_review") or {}
    files = payload.get("files", [])
    xlsx_profile: Dict[str, Any] = {}
    docs: List[Dict[str, Any]] = []
    xlsx_entry: Optional[Dict[str, Any]] = None
    clean_output: Dict[str, Any] = {}
    documents_started = perf_counter()

    for file_entry in files:
        path = Path(file_entry["stored_path"])
        suffix = path.suffix.lower()
        if suffix in {".xlsx", ".xlsm", ".xls"}:
            xlsx_entry = file_entry
            xlsx_profile = _read_xlsx(path)
            continue

        if suffix == ".pdf":
            result = _read_pdf(path)
        elif suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}:
            result = _ocr_image(path)
        else:
            text = normalize_text(path.read_text(encoding="utf-8", errors="ignore")) if path.exists() else ""
            result = {"text": text, "used_ocr": False, "pages_processed": 1 if text else 0}

        doc_meta = _classify_document(path.name, result["text"])
        fields = _extract_fields(result["text"])
        key_fields = _document_key_fields(doc_meta["document_type"], fields)
        field_confidence = _field_confidence(doc_meta["document_type"], fields, result["text"])
        signals_detected = _document_signals(doc_meta["document_type"], doc_meta["code_source"], fields, result["text"], path.name)
        classification_confidence = _classification_confidence(
            doc_meta["document_type"],
            doc_meta["code_source"],
            fields,
            result["text"],
            path.name,
        )
        ocr_quality_score = _score_ocr_quality(result["text"], bool(result["used_ocr"]), int(result["pages_processed"] or 0))
        docs.append(
            {
                "filename": path.name,
                "document_type": doc_meta["document_type"],
                "legacy_code": doc_meta["legacy_code"],
                "legacy_label": LEGACY_CODE_TO_TYPE.get(doc_meta["legacy_code"], ""),
                "code_source": doc_meta["code_source"],
                "used_ocr": result["used_ocr"],
                "pages_processed": result["pages_processed"],
                "ocr_text": result["text"],
                "text_preview": result["text"][:600],
                "fields": fields,
                "key_fields": key_fields,
                "field_confidence": field_confidence,
                "signals_detected": signals_detected,
                "classification_confidence": classification_confidence,
                "ocr_quality_score": ocr_quality_score,
            }
        )

    _apply_document_classification_overrides(docs)
    _number_anexo_sedes(docs)

    # Aplicar correcciones manuales del operador (sobreescriben el clasificador OCR)
    manual_docs = (previous_manual_review or {}).get("documents") or {}
    # Inyectar correcciones manuales de comisiones en los documentos
    manual_comisiones = (previous_manual_review or {}).get("comisiones") or {}
    for doc in docs:
        fname = str(doc.get("filename") or "")
        if fname in manual_comisiones:
            doc["_manual_comisiones"] = manual_comisiones[fname]
    if manual_docs:
        for doc in docs:
            fname = str(doc.get("filename") or "")
            override = manual_docs.get(fname)
            if override and str(override.get("verdict") or "") == "no" and override.get("expected_type"):
                doc["document_type"] = str(override["expected_type"])
                doc["legacy_code"] = override.get("expected_code") or DOC_TYPE_TO_PRIMARY_CODE.get(str(override["expected_type"]), 99)
                doc["code_source"] = "manual_review_override"

    for doc in docs:
        fields = doc.get("fields") or {}
        doc["key_fields"] = _document_key_fields(str(doc.get("document_type") or ""), fields)
        doc["field_confidence"] = _field_confidence(str(doc.get("document_type") or ""), fields, str(doc.get("ocr_text") or doc.get("text_preview") or ""))
        doc["signals_detected"] = _document_signals(
            str(doc.get("document_type") or ""),
            str(doc.get("code_source") or ""),
            fields,
            str(doc.get("ocr_text") or doc.get("text_preview") or ""),
            str(doc.get("filename") or ""),
        )
        doc["classification_confidence"] = _classification_confidence(
            str(doc.get("document_type") or ""),
            str(doc.get("code_source") or ""),
            fields,
            str(doc.get("ocr_text") or doc.get("text_preview") or ""),
            str(doc.get("filename") or ""),
        )
        doc["ocr_quality_score"] = _score_ocr_quality(
            str(doc.get("ocr_text") or doc.get("text_preview") or ""),
            bool(doc.get("used_ocr")),
            int(doc.get("pages_processed") or 0),
        )
    documents_duration_ms = int((perf_counter() - documents_started) * 1000)

    clean_started = perf_counter()
    if xlsx_entry:
        xlsx_bytes = Path(xlsx_entry["stored_path"]).read_bytes()
        clean_output = _generate_clean_via_legacy_nova(xlsx_entry["filename"], xlsx_bytes)
        if not bool(clean_output.get("ok")) and xlsx_bytes:
            workbook = load_workbook(io.BytesIO(xlsx_bytes), data_only=True)
            clean_output = _generate_clean_from_workbook(workbook, xlsx_entry["filename"])
            clean_output["_source"] = "local_fallback"
        xlsx_profile = _enrich_xlsx_profile_from_clean(xlsx_profile, clean_output, docs)
        xlsx_profile = _finalize_profile_from_docs(xlsx_profile, docs)
    tipoempresa_detectado = _extract_tipoempresa_from_entrega_docs(docs)
    if tipoempresa_detectado:
        xlsx_profile.setdefault("profile", {}).update(tipoempresa_detectado)
    _attach_operational_filenames(docs, xlsx_profile)
    clean_duration_ms = int((perf_counter() - clean_started) * 1000)

    validation_started = perf_counter()
    required_docs = _build_required_documents(xlsx_profile.get("profile", {}))
    received_types = {item["document_type"] for item in docs}
    required_evidence = _infer_required_document_satisfaction(required_docs, docs, xlsx_profile.get("profile", {}))
    missing_docs = [doc for doc in required_docs if not (required_evidence.get(doc) or {}).get("satisfied")]
    matched_docs = _unique_preserve(
        str(item.get("filename") or "")
        for item in required_evidence.values()
        if isinstance(item, dict) and item.get("satisfied") and item.get("filename")
    )
    mismatches: List[str] = []

    validation_summary = _build_validation_summary(xlsx_profile, docs, missing_docs)
    blockers = []
    blockers.extend(
        item["message"]
        for item in validation_summary.get("precheck", {}).get("motivos_de_rechazo", [])
        if item["message"] not in blockers
    )
    non_blocking_alerts = [
        item["message"]
        for item in validation_summary.get("alerts", [])
        if normalize_haystack(item.get("severity", "")).lower() == "alert"
    ]
    blockers.extend(
        item["message"]
        for item in validation_summary.get("alerts", [])
        if normalize_haystack(item.get("severity", "")).lower() != "alert" and item["message"] not in blockers
    )

    decision_status = "aprobable" if not blockers else "observado"
    next_step = (
        "Validar contrato final y radicar afiliacion."
        if decision_status == "aprobable"
        else "Solicitar faltantes o corregir inconsistencias antes de radicar."
    )

    checklist = {
        "required": required_docs,
        "received": sorted(received_types),
        "missing": missing_docs,
        "required_evidence": required_evidence,
        "matched_documents": matched_docs,
        "mismatches": mismatches,
        "received_summary": _summarize_received_documents(docs),
    }
    decision = {
        "flow": "afiliacion_documental",
        "recommended_status": decision_status,
        "summary": "Contrato listo para radicacion." if decision_status == "aprobable" else "Contrato con faltantes o inconsistencias.",
        "blockers": blockers,
        "alerts": non_blocking_alerts,
        "next_step": next_step,
    }
    executive_report = _build_executive_report(payload.get("label", case_id), xlsx_profile, checklist, decision, validation_summary)
    output_926 = _build_926_output(case_id, xlsx_profile, checklist, decision, docs=docs)
    validation_duration_ms = int((perf_counter() - validation_started) * 1000)

    analysis = {
        "updated_at": utc_now(),
        "xlsx_profile": xlsx_profile,
        "clean_output": {
            "source": clean_output.get("_source", ""),
            "ok": bool(clean_output),
        } if clean_output else None,
        "documents": docs,
        "checklist": checklist,
        "validacion_resumen": validation_summary,
        "decision": decision,
        "reporte_ejecutivo": executive_report,
        "draft_926": output_926.get("draft"),
        "output_926": output_926,
        "manual_review": previous_manual_review,
        "timings": {
            "documents_duration_ms": documents_duration_ms,
            "clean_duration_ms": clean_duration_ms,
            "validation_duration_ms": validation_duration_ms,
            "analysis_total_ms": int((perf_counter() - analyze_started) * 1000),
        },
    }
    payload["status"] = "analyzed"
    payload["updated_at"] = utc_now()
    payload["analysis"] = analysis
    save_case(payload)
    rebuild_document_registry()
    return payload


def store_case_files(label: str, uploads: List[tuple[str, bytes]]) -> Dict[str, Any]:
    case_id = f"case-{uuid.uuid4().hex[:10]}"
    case_dir = get_case_dir(case_id)
    files_dir = case_dir / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    stored_files: List[Dict[str, Any]] = []

    def _store_one(filename: str, content: bytes) -> None:
        safe_name = filename or f"archivo-{uuid.uuid4().hex[:6]}"
        safe_name = safe_name.replace("\\", "/").split("/")[-1] or f"archivo-{uuid.uuid4().hex[:6]}"
        target = files_dir / safe_name
        counter = 1
        while target.exists():
            target = files_dir / f"{target.stem}-{counter}{target.suffix}"
            counter += 1
        target.write_bytes(content)
        stored_files.append(
            {
                "filename": target.name,
                "stored_path": str(target),
                "size_bytes": len(content),
                "content_type": target.suffix.lower(),
            }
        )

    def _store_processed(filename: str, content: bytes) -> None:
        lower_name = filename.lower()
        if lower_name.endswith(".pdf"):
            exploded = _explode_multipage_pdf_bytes(filename, content)
            if len(exploded) > 1:
                for page_name, page_content in exploded:
                    _store_one(page_name, page_content)
                return
        _store_one(filename, content)

    for original_name, content in uploads:
        filename = original_name or f"archivo-{uuid.uuid4().hex[:6]}"
        lower_name = filename.lower()
        if lower_name.endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as archive:
                    members = [item for item in archive.infolist() if not item.is_dir()]
                    for member in members:
                        member_name = member.filename.replace("\\", "/")
                        if member_name.startswith("__MACOSX/"):
                            continue
                        extracted = archive.read(member)
                        nested_name = member_name.split("/")[-1]
                        if not nested_name:
                            continue
                        _store_processed(nested_name, extracted)
                continue
            except zipfile.BadZipFile:
                pass
        _store_processed(filename, content)

    payload = {
        "id": case_id,
        "label": normalize_text(label) or case_id,
        "status": "uploaded",
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "files": stored_files,
        "analysis": None,
    }
    return save_case(payload)


def delete_case(case_id: str) -> None:
    shutil.rmtree(get_case_dir(case_id), ignore_errors=True)
