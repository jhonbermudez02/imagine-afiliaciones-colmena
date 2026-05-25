from __future__ import annotations

import json
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List


WORKER_DATA_START_REMINDER = "Recuerda que la información de los trabajadores debe comenzar en la línea 39."


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_haystack(value: Any) -> str:
    return normalize_text(value).lower()


def only_digits(value: Any) -> str:
    return re.sub(r"\D+", "", str(value or ""))


def _compact_contact_text(value: Any) -> str:
    return re.sub(r"\s+", "", normalize_text(value))


def _is_strict_numeric_value(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float, Decimal)):
        try:
            return Decimal(str(value)) >= 0
        except (InvalidOperation, ValueError):
            return False
    text = normalize_text(value)
    if not text:
        return False
    if re.fullmatch(r"[\d\s]+", text):
        return bool(only_digits(text))
    return bool(re.fullmatch(r"\d+", text))


def _is_blank_value(value: Any) -> bool:
    return not normalize_text(value)


def _is_x_marker(value: Any) -> bool:
    return normalize_haystack(value) == "x"


def _is_email_value(value: Any) -> bool:
    text = _compact_contact_text(value)
    if not text:
        return False
    if ".." in text:
        return False
    match = re.fullmatch(
        r"[A-Za-z0-9.!$%&'*+/=?^_`{|}~-]+@"
        r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
        r"[A-Za-z]{2,}",
        text,
    )
    if not match:
        return False
    local, domain = text.rsplit("@", 1)
    return not (local.startswith(".") or local.endswith(".") or "#" in local or "#" in domain)


def _ascii_lower(value: Any) -> str:
    text = unicodedata.normalize("NFKD", normalize_text(value))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return text.lower()


def _address_quality_issue(value: Any) -> str | None:
    text = normalize_text(value)
    if not text:
        return None
    normalized = _ascii_lower(text)
    alnum = re.sub(r"[^0-9a-z]+", "", normalized)
    letters = re.sub(r"[^a-z]+", "", normalized)
    if not letters:
        return "no puede estar formada solo por números o caracteres especiales"
    if len(alnum) < 5:
        return "es demasiado corta para identificar una dirección"
    generic_values = {
        "bogota",
        "bogota dc",
        "bogota d c",
        "casa",
        "oficina",
        "sede",
        "principal",
        "direccion",
        "no aplica",
        "n/a",
        "na",
    }
    if normalized in generic_values:
        return "es demasiado genérica para identificar una dirección"
    if re.fullmatch(r"(?:manzana|mz|mza)\s+[0-9a-z]{1,2}", normalized):
        return "está incompleta; agrega la dirección completa de la manzana"
    return None


def _is_valid_roman_risk(value: Any) -> bool:
    return normalize_text(value).upper() in {"I", "II", "III", "IV", "V"}


def _has_letter_and_number_value(value: Any) -> bool:
    text = normalize_text(value)
    if not text:
        return True
    has_letter = any(unicodedata.category(char).startswith("L") for char in text)
    has_number = any(unicodedata.category(char).startswith("N") for char in text)
    return has_letter and has_number


def _is_letters_only_value(value: Any) -> bool:
    text = normalize_text(value)
    if not text:
        return True
    compact = re.sub(r"\s+", "", text)
    return bool(compact) and all(unicodedata.category(char).startswith("L") for char in compact)


def _append_letters_only_validation(
    blockers: List[Dict[str, Any]],
    cell_info: Dict[str, Any],
    *,
    code: str,
    field: str,
    message_prefix: str | None = None,
    sheet: str | None = None,
) -> None:
    raw_value = cell_info.get("value")
    if _is_blank_value(raw_value) or _is_letters_only_value(raw_value):
        return
    label = cell_info.get("label") or field
    cell = cell_info.get("cell") or "celda requerida"
    row_number = cell_info.get("row")
    prefix = message_prefix or f"El campo '{label}' ({cell})"
    payload: Dict[str, Any] = {
        "code": code,
        "severity": "blocker",
        "field": field,
        "cell": cell,
        "message": f"{prefix} solo debe contener letras. Valor recibido: {raw_value}.",
    }
    if sheet:
        payload["sheet"] = sheet
    if row_number is not None:
        payload["row"] = row_number
    blockers.append(payload)


def _append_letter_and_number_validation(
    blockers: List[Dict[str, Any]],
    cell_info: Dict[str, Any],
    *,
    code: str,
    field: str,
    message_prefix: str | None = None,
    sheet: str | None = None,
) -> None:
    raw_value = cell_info.get("value")
    if _is_blank_value(raw_value) or _has_letter_and_number_value(raw_value):
        return
    label = cell_info.get("label") or field
    cell = cell_info.get("cell") or "celda requerida"
    row_number = cell_info.get("row")
    prefix = message_prefix or f"El campo '{label}' ({cell})"
    payload: Dict[str, Any] = {
        "code": code,
        "severity": "blocker",
        "field": field,
        "cell": cell,
        "message": f"{prefix} debe contener al menos una letra y al menos un número. Valor recibido: {raw_value}.",
    }
    if sheet:
        payload["sheet"] = sheet
    if row_number is not None:
        payload["row"] = row_number
    blockers.append(payload)


def _append_required_cell_validation(
    blockers: List[Dict[str, Any]],
    form_cell_values: Dict[str, Any],
    field: str,
    *,
    require_numeric: bool,
    require_email: bool = False,
    code_prefix: str,
) -> None:
    cell_info = form_cell_values.get(field) or {}
    raw_value = cell_info.get("value")
    label = cell_info.get("label") or field
    cell = cell_info.get("cell") or "celda requerida"
    if _is_blank_value(raw_value):
        blockers.append(
            {
                "code": f"{code_prefix}_EMPTY",
                "severity": "blocker",
                "field": field,
                "cell": cell,
                "message": f"El campo '{label}' ({cell}) no puede estar vacío.",
            }
        )
    elif require_numeric and not _is_strict_numeric_value(raw_value):
        blockers.append(
            {
                "code": f"{code_prefix}_NOT_NUMERIC",
                "severity": "blocker",
                "field": field,
                "cell": cell,
                "message": f"El campo '{label}' ({cell}) debe ser numérico. Valor recibido: {raw_value}.",
            }
        )
    elif require_email and not _is_email_value(raw_value):
        blockers.append(
            {
                "code": f"{code_prefix}_INVALID_EMAIL",
                "severity": "blocker",
                "field": field,
                "cell": cell,
                "message": f"El campo '{label}' ({cell}) debe tener formato de correo electrónico válido.",
            }
        )


def _append_cell_length_validation(
    blockers: List[Dict[str, Any]],
    form_cell_values: Dict[str, Any],
    field: str,
    *,
    min_length: int,
    max_length: int,
    code_prefix: str,
) -> None:
    cell_info = form_cell_values.get(field) or {}
    raw_value = cell_info.get("value")
    if _is_blank_value(raw_value):
        return
    label = cell_info.get("label") or field
    cell = cell_info.get("cell") or "celda requerida"
    text = normalize_text(raw_value)
    if not (min_length <= len(text) <= max_length):
        blockers.append(
            {
                "code": f"{code_prefix}_INVALID_LENGTH",
                "severity": "blocker",
                "field": field,
                "cell": cell,
                "message": f"El campo '{label}' ({cell}) debe tener entre {min_length} y {max_length} caracteres. Valor recibido: {raw_value}.",
            }
        )


def _append_min_length_validation(
    blockers: List[Dict[str, Any]],
    form_cell_values: Dict[str, Any],
    field: str,
    *,
    min_length: int,
    code_prefix: str,
) -> None:
    cell_info = form_cell_values.get(field) or {}
    raw_value = cell_info.get("value")
    if _is_blank_value(raw_value):
        return
    label = cell_info.get("label") or field
    cell = cell_info.get("cell") or "celda requerida"
    text = normalize_text(raw_value)
    if len(text) < min_length:
        blockers.append(
            {
                "code": f"{code_prefix}_MIN_LENGTH",
                "severity": "blocker",
                "field": field,
                "cell": cell,
                "message": f"El campo '{label}' ({cell}) debe tener al menos {min_length} caracteres. Valor recibido: {raw_value}.",
            }
        )


def _append_address_quality_validation(
    blockers: List[Dict[str, Any]],
    cell_info: Dict[str, Any],
    *,
    code: str,
    field: str,
    message_prefix: str | None = None,
    sheet: str | None = None,
) -> None:
    raw_value = cell_info.get("value")
    issue = _address_quality_issue(raw_value)
    if not issue:
        return
    label = cell_info.get("label") or field
    cell = cell_info.get("cell") or "celda requerida"
    row_number = cell_info.get("row")
    prefix = message_prefix or f"El campo '{label}' ({cell})"
    payload: Dict[str, Any] = {
        "code": code,
        "severity": "blocker",
        "field": field,
        "cell": cell,
        "message": f"{prefix} {issue}. Valor recibido: {raw_value}.",
    }
    if sheet:
        payload["sheet"] = sheet
    if row_number is not None:
        payload["row"] = row_number
    blockers.append(payload)


def _append_digits_length_validation(
    blockers: List[Dict[str, Any]],
    form_cell_values: Dict[str, Any],
    field: str,
    *,
    min_length: int,
    max_length: int,
    code_prefix: str,
) -> None:
    cell_info = form_cell_values.get(field) or {}
    raw_value = cell_info.get("value")
    if _is_blank_value(raw_value):
        return
    label = cell_info.get("label") or field
    cell = cell_info.get("cell") or "celda requerida"
    text = normalize_text(raw_value)
    if not re.fullmatch(r"\d+", text) or not (min_length <= len(text) <= max_length):
        blockers.append(
            {
                "code": f"{code_prefix}_INVALID_DIGITS_LENGTH",
                "severity": "blocker",
                "field": field,
                "cell": cell,
                "message": (
                    f"El campo '{label}' ({cell}) solo debe contener números y tener entre "
                    f"{min_length} y {max_length} caracteres. Valor recibido: {raw_value}."
                ),
            }
        )


def _sheet_cell_info(sheet_values: Dict[str, Any], field: str) -> Dict[str, Any]:
    return dict((sheet_values or {}).get(field) or {})


def _append_sede_cell_validation(
    blockers: List[Dict[str, Any]],
    sheet_name: str,
    sheet_values: Dict[str, Any],
    field: str,
    *,
    require_numeric: bool = False,
    require_email: bool = False,
    require_date: bool = False,
) -> None:
    cell_info = _sheet_cell_info(sheet_values, field)
    raw_value = cell_info.get("value")
    label = cell_info.get("label") or field
    cell = cell_info.get("cell") or "celda requerida"
    message_prefix = f"{sheet_name}: el campo '{label}' ({cell})"
    if _is_blank_value(raw_value):
        blockers.append(
            {
                "code": "XLSX_SEDE_REQUIRED_CELL_EMPTY",
                "severity": "blocker",
                "field": field,
                "sheet": sheet_name,
                "cell": cell,
                "message": f"{message_prefix} no puede estar vacío.",
            }
        )
    elif require_numeric and not _is_strict_numeric_value(raw_value):
        blockers.append(
            {
                "code": "XLSX_SEDE_REQUIRED_CELL_NOT_NUMERIC",
                "severity": "blocker",
                "field": field,
                "sheet": sheet_name,
                "cell": cell,
                "message": f"{message_prefix} debe ser numérico. Valor recibido: {raw_value}.",
            }
        )
    elif require_email and not _is_email_value(raw_value):
        blockers.append(
            {
                "code": "XLSX_SEDE_REQUIRED_CELL_INVALID_EMAIL",
                "severity": "blocker",
                "field": field,
                "sheet": sheet_name,
                "cell": cell,
                "message": f"{message_prefix} debe tener formato de correo electrónico válido.",
            }
        )
    elif require_date and not _parse_date_value(raw_value):
        blockers.append(
            {
                "code": "XLSX_SEDE_REQUIRED_CELL_INVALID_DATE",
                "severity": "blocker",
                "field": field,
                "sheet": sheet_name,
                "cell": cell,
                "message": f"{message_prefix} debe tener una fecha válida. Valor recibido: {raw_value}.",
            }
        )


def _center_cell_info(row_values: Dict[str, Any], field: str) -> Dict[str, Any]:
    return dict((row_values or {}).get(field) or {})


def _append_center_cell_validation(
    blockers: List[Dict[str, Any]],
    sheet_name: str,
    row_values: Dict[str, Any],
    field: str,
    *,
    require_numeric: bool = False,
    require_email: bool = False,
    min_length: int | None = None,
    max_length: int | None = None,
) -> None:
    cell_info = _center_cell_info(row_values, field)
    raw_value = cell_info.get("value")
    label = cell_info.get("label") or field
    cell = cell_info.get("cell") or "celda requerida"
    row_number = cell_info.get("row")
    message_prefix = f"{sheet_name}, fila {row_number}: el campo '{label}' ({cell})"
    if _is_blank_value(raw_value):
        blockers.append(
            {
                "code": "XLSX_CENTRO_REQUIRED_CELL_EMPTY",
                "severity": "blocker",
                "field": field,
                "sheet": sheet_name,
                "cell": cell,
                "row": row_number,
                "message": f"{message_prefix} no puede estar vacío.",
            }
        )
        return
    if require_numeric and not _is_strict_numeric_value(raw_value):
        blockers.append(
            {
                "code": "XLSX_CENTRO_REQUIRED_CELL_NOT_NUMERIC",
                "severity": "blocker",
                "field": field,
                "sheet": sheet_name,
                "cell": cell,
                "row": row_number,
                "message": f"{message_prefix} debe ser numérico. Valor recibido: {raw_value}.",
            }
        )
    if require_email and not _is_email_value(raw_value):
        blockers.append(
            {
                "code": "XLSX_CENTRO_REQUIRED_CELL_INVALID_EMAIL",
                "severity": "blocker",
                "field": field,
                "sheet": sheet_name,
                "cell": cell,
                "row": row_number,
                "message": f"{message_prefix} debe tener formato de correo electrónico válido.",
            }
        )
    if min_length is not None and max_length is not None:
        text = normalize_text(raw_value)
        if not (min_length <= len(text) <= max_length):
            blockers.append(
                {
                    "code": "XLSX_CENTRO_REQUIRED_CELL_INVALID_LENGTH",
                    "severity": "blocker",
                    "field": field,
                    "sheet": sheet_name,
                    "cell": cell,
                    "row": row_number,
                    "message": (
                        f"{message_prefix} debe tener entre {min_length} y {max_length} caracteres. "
                        f"Valor recibido: {raw_value}."
                    ),
                }
            )


def _is_allowed_centralization_value(value: Any) -> bool:
    normalized = normalize_haystack(value)
    if not normalized:
        return False
    normalized = unicodedata.normalize("NFKD", normalized).encode("ascii", "ignore").decode("ascii")
    return normalized in {"centralizada", "descentralizada"}


def _worker_cell_info(row_values: Dict[str, Any], field: str) -> Dict[str, Any]:
    return dict((row_values or {}).get(field) or {})


def _append_worker_cell_validation(
    blockers: List[Dict[str, Any]],
    sheet_name: str,
    row_values: Dict[str, Any],
    field: str,
    *,
    require_numeric: bool = False,
    require_email: bool = False,
    min_length: int | None = None,
    max_length: int | None = None,
    allow_zero_length: bool = False,
) -> None:
    cell_info = _worker_cell_info(row_values, field)
    raw_value = cell_info.get("value")
    label = cell_info.get("label") or field
    cell = cell_info.get("cell") or "celda requerida"
    row_number = cell_info.get("row")
    message_prefix = f"{sheet_name}, fila {row_number}: el campo '{label}' ({cell})"
    if _is_blank_value(raw_value):
        blockers.append(
            {
                "code": "XLSX_TRABAJADOR_REQUIRED_CELL_EMPTY",
                "severity": "blocker",
                "field": field,
                "sheet": sheet_name,
                "cell": cell,
                "row": row_number,
                "message": f"{message_prefix} no puede estar vacío.",
            }
        )
        return
    if require_numeric and not _is_strict_numeric_value(raw_value):
        blockers.append(
            {
                "code": "XLSX_TRABAJADOR_REQUIRED_CELL_NOT_NUMERIC",
                "severity": "blocker",
                "field": field,
                "sheet": sheet_name,
                "cell": cell,
                "row": row_number,
                "message": f"{message_prefix} debe ser numérico. Valor recibido: {raw_value}.",
            }
        )
    if require_email and not _is_email_value(raw_value):
        blockers.append(
            {
                "code": "XLSX_TRABAJADOR_REQUIRED_CELL_INVALID_EMAIL",
                "severity": "blocker",
                "field": field,
                "sheet": sheet_name,
                "cell": cell,
                "row": row_number,
                "message": f"{message_prefix} debe tener formato de correo electrónico válido.",
            }
        )
    if min_length is not None and max_length is not None:
        text = normalize_text(raw_value)
        if allow_zero_length and text == "0":
            return
        if not (min_length <= len(text) <= max_length):
            blockers.append(
                {
                    "code": "XLSX_TRABAJADOR_REQUIRED_CELL_INVALID_LENGTH",
                    "severity": "blocker",
                    "field": field,
                    "sheet": sheet_name,
                    "cell": cell,
                    "row": row_number,
                    "message": (
                        f"{message_prefix} debe tener entre {min_length} y {max_length} caracteres. "
                        f"Valor recibido: {raw_value}."
                    ),
                }
            )


def _is_allowed_worker_sex_value(value: Any) -> bool:
    normalized = normalize_haystack(value)
    if not normalized:
        return False
    normalized = unicodedata.normalize("NFKD", normalized).encode("ascii", "ignore").decode("ascii")
    return normalized in {"masculino", "maculino", "femenino", "otro", "no binario", "transexual", "m", "f", "o", "nb", "t"}


def _is_allowed_salary_type_value(value: Any) -> bool:
    normalized = normalize_haystack(value)
    if not normalized:
        return False
    normalized = unicodedata.normalize("NFKD", normalized).encode("ascii", "ignore").decode("ascii")
    return normalized in {"1", "1-fijo", "fijo", "2", "2-variable", "variable"}


def _valid_date_parts(day_value: Any, month_value: Any, year_value: Any) -> bool:
    if not (_is_strict_numeric_value(day_value) and _is_strict_numeric_value(month_value) and _is_strict_numeric_value(year_value)):
        return False
    try:
        day = int(Decimal(str(day_value)))
        month = int(Decimal(str(month_value)))
        year = int(Decimal(str(year_value)))
        datetime(year, month, day)
        return True
    except (InvalidOperation, TypeError, ValueError):
        return False


def _same_date_value(left: Any, right: Any) -> bool:
    left_date = _parse_date_value(left)
    right_date = _parse_date_value(right)
    if not left_date or not right_date:
        return False
    return left_date.date() == right_date.date()


def _sede_sheet_number(sheet_name: str) -> int | None:
    match = re.search(r"sede\s+0*(\d+)", normalize_haystack(sheet_name))
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _worker_document_raw(record: Dict[str, Any]) -> str:
    return normalize_text(
        record.get("_raw_numero_de_identificacion")
        or record.get("_raw_documento")
        or record.get("documento")
        or record.get("numero_documento")
        or record.get("num_id_trabajador")
        or record.get("numero_de_identificacion")
        or ""
    )


def _valid_date(value: Any) -> bool:
    text = normalize_text(value)
    if not text:
        return False
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            datetime.strptime(text, fmt)
            return True
        except ValueError:
            continue
    digits = only_digits(text)
    if len(digits) == 8:
        for fmt in ("%d%m%Y", "%Y%m%d"):
            try:
                datetime.strptime(digits, fmt)
                return True
            except ValueError:
                continue
    return False


def _parse_date_value(value: Any) -> datetime | None:
    text = normalize_text(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    digits = only_digits(text)
    if len(digits) == 8:
        for fmt in ("%d%m%Y", "%Y%m%d"):
            try:
                return datetime.strptime(digits, fmt)
            except ValueError:
                continue
    return None


def _format_date_value(value: Any) -> str:
    parsed = _parse_date_value(value)
    if parsed:
        return parsed.strftime("%d/%m/%Y")
    return normalize_text(value) or "n/d"


def _is_next_month(base_date: datetime, candidate_date: datetime) -> bool:
    expected_year = base_date.year
    expected_month = base_date.month + 1
    if expected_month == 13:
        expected_month = 1
        expected_year += 1
    return candidate_date.year == expected_year and candidate_date.month == expected_month


def _is_two_months_before(base_date: datetime, candidate_date: datetime) -> bool:
    expected_year = base_date.year
    expected_month = base_date.month - 2
    while expected_month <= 0:
        expected_month += 12
        expected_year -= 1
    return candidate_date.year == expected_year and candidate_date.month == expected_month


PRIMARY_REQUIRED_FIELDS = {
    "fecha_radicacion": "fecha",
    "fecha_inicio_cobertura": "fecha",
    "numero_radicacion": "texto",
    "empleador_razon_social": "texto",
    "empleador_numero_documento_nit": "numero",
    "rep_legal_nombre_completo": "texto",
    "rep_legal_numero_documento": "numero",
    "rep_legal_tipo_documento": "texto",
    "rep_legal_correo": "texto",
    "sede_principal_codigo": "texto",
    "sede_principal_nombre": "texto",
    "sede_principal_direccion": "texto",
    "sede_principal_telefono": "numero",
    "sede_principal_correo": "texto",
    "sede_principal_municipio_distrito": "texto",
    "sede_principal_zona": "texto",
    "sede_principal_localidad_comuna": "texto",
    "sede_principal_departamento": "texto",
    "responsable_sede_principal_nombre_completo": "texto",
    "responsable_sede_principal_tipo_documento": "texto",
    "responsable_sede_principal_numero_documento": "numero",
    "tipo_tramite": "texto",
    "naturaleza_juridica_empleador": "texto",
    "tipo_aportante": "texto",
    "tipo_persona": "texto",
    "empleador_tipo_documento": "texto",
}

PRIMARY_REQUIRED_AFILIACION = [
    "a_codigo_actividad_economica_principal",
    "a_clase_riesgo",
    "a_numero_sedes",
    "a_numero_centros_trabajo",
    "a_numero_inicial_trabajadores_estudiantes",
    "a_valor_total_nomina",
]

PRIMARY_REQUIRED_TRASLADO = [
    "b_arl_de_la_cual_se_traslada",
    "b_clase_riesgo",
    "b_codigo_actividad_economica_principal",
    "b_numero_sedes",
    "b_numero_centros_trabajo",
    "b_numero_total_trabajadores_estudiantes",
    "b_monto_total_cotizacion",
    "estado_cuenta_empleador",
]

ALLOWED_TIPO_TRAMITE = {"afiliacion", "afiliación", "traslado", "terminacion de la afiliacion", "terminación de la afiliación"}
ALLOWED_DOCUMENT_TYPES = {"CC", "CD", "CE", "PE", "PT", "RC", "SC", "TI", "NI"}
ALLOWED_ESTADO_CUENTA = {"al día", "al dia", "en mora", "acuerdo de pago", "incumplimiento de acuerdo de pago"}
SMMLV_TABLE_PATH = Path(__file__).resolve().parents[2] / "data" / "evals" / "smmlv_table.json"
EPS_CATALOG_PATH = Path(__file__).resolve().parents[2] / "data" / "evals" / "eps_catalog.json"
AFP_CATALOG_PATH = Path(__file__).resolve().parents[2] / "data" / "evals" / "afp_catalog.json"
PILA_CATALOG_PATH = Path(__file__).resolve().parents[2] / "data" / "evals" / "pila_catalog.json"
DEFAULT_SMMLV_TABLE = {
    "2025": 1423500,
    "2026": 1750905,
}

CATALOG_EQUIVALENTS = {
    "EMSSANAR": "EMSANAR",
    "MUTUALSER": "ASOCIACIONMUTUALSER",
    "SURAMERICANA": "SURA",
    "ALIANSALUDEPSANTESCOLMEDICA": "ALIANSALUD",
    "ALIANSALUDANTESCOLMEDICA": "ALIANSALUD",
    "ALIANZAMEDELLINANTIOQUIASAVIASALUD": "SAVIASALUD",
    "FONDODESOLIDARIDADYGARANTIAFOSYGA": "FIDUFOSYGA",
    "ASMETSALUDCM": "ASMETSALUD",
    "SOSSERVICIOOCCIDENTALDESALUD": "SOS",
    "SOSSERVICIOOCCIDENTALDESALUDSA": "SOS",
    "PROTECCI0N": "PROTECCION",
    "NOTIENEPENSION": "SINAFP",
    "NOTIENEENSION": "SINAFP",
    "SINPENSION": "SINAFP",
    "SIN": "SINAFP",
}


def _load_smmlv_table() -> Dict[str, int]:
    try:
        payload = json.loads(SMMLV_TABLE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        payload = DEFAULT_SMMLV_TABLE
    table: Dict[str, int] = {}
    for year, value in (payload or {}).items():
        digits = only_digits(year)
        amount = _parse_amount(value)
        if len(digits) == 4 and amount > 0:
            table[digits] = amount
    return table or dict(DEFAULT_SMMLV_TABLE)


def _resolve_smmlv_year(form_fields: Dict[str, Any]) -> str:
    for candidate in [
        form_fields.get("fecha_radicacion", ""),
        form_fields.get("fecha_inicio_cobertura", ""),
    ]:
        parsed = _parse_date_value(candidate)
        if parsed:
            return str(parsed.year)
    return str(datetime.now().year)


def _resolve_smmlv_value(form_fields: Dict[str, Any]) -> tuple[str, int]:
    table = _load_smmlv_table()
    year = _resolve_smmlv_year(form_fields)
    if year in table:
        return year, table[year]
    latest_year = max(table.keys())
    return latest_year, table[latest_year]



def _rag_validate_eps_afp(value: str, tipo: str) -> bool:
    """Valida EPS o AFP usando RAG con el motor de embeddings configurado.
    Retorna True si es válido, False si no."""
    if not value or len(value.strip()) < 3:
        return True  # Sin valor, no validar
    try:
        from qdrant_client import QdrantClient
        from app.embeddings import embed_text
        from app.qdrant_guard import collection_matches_current_embeddings
        qdrant = QdrantClient(host="imagine_qdrant", port=6333)
        col = "afi_eps_catalog" if tipo == "eps" else "afi_afp_catalog"
        if not collection_matches_current_embeddings(qdrant, col):
            return True
        vector = embed_text(f"{'EPS entidad de salud' if tipo=='eps' else 'AFP fondo de pensiones'}: {value}")
        if not vector:
            return True  # Si falla RAG, no bloquear
        results = qdrant.search(collection_name=col, query_vector=vector, limit=1, score_threshold=0.82)
        return bool(results)
    except Exception:
        return True  # Si falla RAG, no bloquear


# Palabras válidas en nombres de EPS/AFP del dominio colombiano
_EPS_AFP_DOMAIN_WORDS = {
    "FONDO","PENSIONES","INSTITUTO","SEGUROS","SOCIALES","PROMOTORA",
    "ENTIDAD","MOVILIDAD","NUEVA","SALUD","TOTAL","ALIANZA","NACIONAL",
    "COLOMBIA","COLOMBIANA","INTEGRAL","VIDA","MEDICA","COMPANEROS",
    "COMPENSAR","COLPENSIONES","COLPATRIA","COLFONDOS","SKANDIA","PORVENIR",
    "PROTECCION","HORIZONTE","SURA","CAFAM","SANITAS","COOSALUD",
    "COOEMSSANAR","MALLAMAS","MUTUAL","COOPERATIVA","FAMILIAR","REGIONAL",
    "OCCIDENTAL","NORTE","SUROCCIDENTE","LITORAL","CAPITAL","MEDIMAS",
    "COOSALUD","NUEVA","COMFENALCO","SAVIA","ALIANSALUD","GOLDEN","GROUP",
    "EMSSANAR","ASMET","ANAS","PIJAOS","DUSAKAWI","CAPRESOCA","ECOOPSOS",
    "MUTUAL","AMBUQ","BARRIOS","UNIDOS","COOSALUD","CONVIDA","COMFACOR",
    "COMFABOY","COMFAMILIAR","COMFACUNDI","COMFENALCO","COMFLORIDA",
    "COOMEVA","EPS","SAS","LTDA","IPS","ESE","SERVISALUD","SALUD",
    "CESANTIAS","PENSIONES","DE","Y","LA","EL","LOS","LAS","DEL",
    "CM","ARL","EPS","AFP","SAS","SA","LTDA","IPS","ESE","BIC",
    "NINGUNA","FONDO","PASIVO","SOCIAL","FERROCARRILES","NACIONALES","COLOMBIA",
    "ECOPETROL","REGIMEN","ESPECIAL","MAGISTERIO","FFMM","POLICIA","ECOS",
    "ASOCIACION","MUTUA","ALTERNATIVO","SSS","FONDO","ALTERNATIVO","PENSION","SALUD"
}
_EPS_AFP_VALID_TOKENS: set = set()  # se llena al cargar catalogos

def _get_entity_tokens(value: str) -> set:
    import unicodedata as _ud
    text = str(value).strip().upper()
    text = "".join(ch for ch in _ud.normalize("NFKD", text) if not _ud.combining(ch))
    stop = {"S","A","SA","SAS","LTDA","EPS","AFP","DE","DEL","LA","LOS","Y","E","EL","EN","CON","AL"}
    return set(t for t in re.split(r"[^A-Z0-9]+", text) if t and t not in stop and len(t) >= 3)

def _build_valid_tokens(eps_catalog_path: Path, afp_catalog_path: Path) -> set:
    global _EPS_AFP_VALID_TOKENS
    if _EPS_AFP_VALID_TOKENS:
        return _EPS_AFP_VALID_TOKENS
    valid = set(_EPS_AFP_DOMAIN_WORDS)
    for path_c in [eps_catalog_path, afp_catalog_path]:
        try:
            for item in json.loads(path_c.read_text(encoding="utf-8")):
                if isinstance(item, dict) and item.get("nombre"):
                    valid.update(_get_entity_tokens(item["nombre"]))
        except Exception:
            pass
    try:
        for item in json.loads(PILA_CATALOG_PATH.read_text(encoding="utf-8")):
            if not isinstance(item, dict):
                continue
            for value in _pila_alias_values(item):
                if value:
                    valid.update(_get_entity_tokens(str(value)))
    except Exception:
        pass
    _EPS_AFP_VALID_TOKENS = valid
    return valid

def _check_entity_valid(value: str, catalog_token_sets: list, valid_tokens: set) -> bool:
    val_tokens = _get_entity_tokens(value)
    if not val_tokens:
        return True
    unknown = val_tokens - valid_tokens
    if unknown:
        return False
    # Si todos los tokens son conocidos del dominio, es valido aunque no este en catalog_token_sets
    return True

def _normalize_catalog_name(value: Any) -> str:
    text = normalize_text(value).upper()
    text = "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))
    tokens = [token for token in re.split(r"[^A-Z0-9]+", text) if token]
    stop_tokens = {"S", "A", "SA", "SAS", "LTDA", "EPS", "AFP"}
    compact = "".join(token for token in tokens if token not in stop_tokens)
    normalized = compact or re.sub(r"[^A-Z0-9]+", "", text)
    normalized = CATALOG_EQUIVALENTS.get(normalized, normalized)
    if "0" in normalized and re.search(r"[A-Z]", normalized):
        alpha_variant = normalized.replace("0", "O")
        normalized = CATALOG_EQUIVALENTS.get(alpha_variant, alpha_variant)
    return normalized


def _load_name_catalog(path: Path) -> set[str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        payload = []
    names: set[str] = set()
    for item in payload or []:
        if not isinstance(item, dict):
            continue
        normalized = _normalize_catalog_name(item.get("nombre"))
        if normalized:
            names.add(normalized)
    return names


def _pila_alias_values(item: Dict[str, Any]) -> List[Any]:
    aliases = item.get("alias") or []
    if not isinstance(aliases, list):
        aliases = re.split(r"[,;\n]+", str(aliases))
    return [item.get("nombre_oficial"), *aliases]


def _load_pila_name_catalog(subsystem: str) -> set[str]:
    try:
        payload = json.loads(PILA_CATALOG_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        payload = []
    names: set[str] = set()
    subsystem = subsystem.upper()
    for item in payload or []:
        if not isinstance(item, dict) or str(item.get("subsistema") or "").upper() != subsystem:
            continue
        for value in _pila_alias_values(item):
            normalized = _normalize_catalog_name(value)
            if normalized:
                names.add(normalized)
    return names


def run_xlsx_primary_validations(xlsx_profile: Dict[str, Any]) -> Dict[str, Any]:
    form_fields = dict((xlsx_profile or {}).get("form_fields") or {})
    form_cell_values = dict((xlsx_profile or {}).get("form_cell_values") or {})
    profile = dict((xlsx_profile or {}).get("profile") or {})
    worker_sheet_counts = dict((xlsx_profile or {}).get("worker_sheet_counts") or {})
    sede_sheet_values = dict((xlsx_profile or {}).get("sede_sheet_values") or {})
    sede_center_rows = dict((xlsx_profile or {}).get("sede_center_rows") or {})
    sede_worker_rows = dict((xlsx_profile or {}).get("sede_worker_rows") or {})
    has_independientes_723 = bool((xlsx_profile or {}).get("has_independientes_723"))

    blockers: List[Dict[str, Any]] = []
    next_actions: List[str] = []
    missing_fields: List[str] = []

    # Backfill mínimos desde profile si el lector del formulario no los trajo aún.
    form_fields.setdefault("empleador_razon_social", profile.get("empresa", ""))
    form_fields.setdefault("empleador_numero_documento_nit", profile.get("documento_empleador") or profile.get("nit", ""))
    form_fields.setdefault("rep_legal_nombre_completo", profile.get("nombre", ""))
    form_fields.setdefault("rep_legal_numero_documento", profile.get("documento", ""))
    form_fields.setdefault("a_numero_sedes", profile.get("numero_sedes", ""))
    form_fields.setdefault("b_numero_sedes", profile.get("numero_sedes", ""))
    form_fields.setdefault("a_numero_inicial_trabajadores_estudiantes", profile.get("numero_trabajadores", ""))
    form_fields.setdefault("b_numero_total_trabajadores_estudiantes", profile.get("numero_trabajadores", ""))
    form_fields.setdefault("a_valor_total_nomina", profile.get("nomina_total", ""))
    form_fields.setdefault("b_monto_total_cotizacion", profile.get("nomina_total", ""))

    for field, field_type in PRIMARY_REQUIRED_FIELDS.items():
        value = form_fields.get(field, "")
        if not normalize_text(value):
            missing_fields.append(field)
            continue
        if field_type == "numero" and not only_digits(value):
            blockers.append(
                {
                    "code": "XLSX_PRIMARY_INVALID_TYPE",
                    "severity": "blocker",
                    "message": f"El campo '{field}' del formulario del XLSX debe ser numérico.",
                }
            )
        if field_type == "fecha" and not _valid_date(value):
            blockers.append(
                {
                    "code": "XLSX_PRIMARY_INVALID_DATE",
                    "severity": "blocker",
                    "message": f"El campo '{field}' del formulario del XLSX no trae una fecha válida.",
                }
            )

    tipo_tramite = normalize_haystack(form_fields.get("tipo_tramite", "") or profile.get("tipo_afiliado", ""))
    afiliacion_marker = (form_cell_values.get("tipo_tramite_afiliacion_marker") or {}).get("value")
    traslado_marker = (form_cell_values.get("tipo_tramite_traslado_marker") or {}).get("value")
    afiliacion_marked = _is_x_marker(afiliacion_marker)
    traslado_marked = _is_x_marker(traslado_marker)
    if not afiliacion_marked and not traslado_marked:
        blockers.append(
            {
                "code": "XLSX_TRAMITE_MARKER_MISSING",
                "severity": "blocker",
                "field": "tipo_tramite",
                "cell": "I13/N13",
                "message": "El formulario debe marcar con X el tipo de trámite en I13 (Afiliación) o N13 (Traslado).",
            }
        )
    elif afiliacion_marked and traslado_marked:
        blockers.append(
            {
                "code": "XLSX_TRAMITE_MARKER_DUPLICATE",
                "severity": "blocker",
                "field": "tipo_tramite",
                "cell": "I13/N13",
                "message": "El formulario no puede tener marcadas con X simultáneamente I13 (Afiliación) y N13 (Traslado).",
            }
        )
    elif afiliacion_marked and "afili" not in tipo_tramite:
        tipo_tramite = "afiliacion"
    elif traslado_marked and "traslado" not in tipo_tramite:
        tipo_tramite = "traslado"
    if tipo_tramite and tipo_tramite not in ALLOWED_TIPO_TRAMITE:
        blockers.append(
            {
                "code": "XLSX_PRIMARY_INVALID_TRAMITE",
                "severity": "blocker",
                "message": "El campo 'tipo_tramite' del XLSX no tiene un valor permitido.",
            }
        )

    empleador_tipo_documento = normalize_text(form_fields.get("empleador_tipo_documento", "")).upper()
    if empleador_tipo_documento and empleador_tipo_documento not in ALLOWED_DOCUMENT_TYPES:
        blockers.append(
            {
                "code": "XLSX_PRIMARY_INVALID_DOC_TYPE",
                "severity": "blocker",
                "message": "El campo 'empleador_tipo_documento' del XLSX no tiene un valor permitido.",
            }
        )

    traslado_payload = any(
        normalize_text(form_fields.get(field, ""))
        for field in ["b_arl_de_la_cual_se_traslada", "b_clase_riesgo", "b_codigo_actividad_economica_principal", "b_monto_total_cotizacion"]
    )
    afiliacion_payload = any(
        normalize_text(form_fields.get(field, ""))
        for field in ["a_codigo_actividad_economica_principal", "a_clase_riesgo", "a_numero_sedes", "a_valor_total_nomina"]
    )

    if "traslado" in tipo_tramite:
        direct_cell_fields = [
            ("b_arl_de_la_cual_se_traslada", False),
            ("b_clase_riesgo", False),
            ("b_codigo_actividad_economica_principal", True),
            ("b_numero_sedes", True),
            ("b_numero_centros_trabajo", True),
            ("b_numero_total_trabajadores_estudiantes", True),
            ("b_monto_total_cotizacion", True),
        ]
        for field, require_numeric in direct_cell_fields:
            _append_required_cell_validation(
                blockers,
                form_cell_values,
                field,
                require_numeric=require_numeric,
                code_prefix="XLSX_TRASLADO_REQUIRED_CELL",
            )
        b_clase_riesgo_info = form_cell_values.get("b_clase_riesgo") or {}
        b_clase_riesgo_value = b_clase_riesgo_info.get("value")
        if not _is_blank_value(b_clase_riesgo_value) and not _is_valid_roman_risk(b_clase_riesgo_value):
            blockers.append(
                {
                    "code": "XLSX_TRASLADO_REQUIRED_CELL_INVALID_ROMAN_RISK",
                    "severity": "blocker",
                    "field": "b_clase_riesgo",
                    "cell": b_clase_riesgo_info.get("cell") or "M29",
                    "message": (
                        "Para afiliaciones de traslado, el campo 'Clase de riesgo' (M29) debe ser un número romano "
                        f"entre I y V. Valor recibido: {b_clase_riesgo_value}."
                    ),
                }
            )
        for field in PRIMARY_REQUIRED_TRASLADO:
            if not normalize_text(form_fields.get(field, "")):
                missing_fields.append(field)
        missing_fields = [field for field in missing_fields if field not in {field for field, _ in direct_cell_fields}]
        estado = normalize_haystack(form_fields.get("estado_cuenta_empleador", ""))
        if estado and estado not in ALLOWED_ESTADO_CUENTA:
            blockers.append(
                {
                    "code": "XLSX_PRIMARY_INVALID_ESTADO_CUENTA",
                    "severity": "blocker",
                    "message": "El campo 'estado_cuenta_empleador' del XLSX no tiene un valor permitido.",
                }
            )
        radicacion_date = _parse_date_value(form_fields.get("fecha_radicacion", ""))
        inicio_cobertura_date = _parse_date_value(form_fields.get("fecha_inicio_cobertura", ""))
        if radicacion_date and inicio_cobertura_date and not _is_two_months_before(inicio_cobertura_date, radicacion_date):
            blockers.append(
                {
                    "code": "XLSX_PRIMARY_FECHA_TRASLADO_INVALIDA",
                    "severity": "blocker",
                    "message": (
                        "Para afiliaciones de traslado, la fecha de radicación debe quedar dos meses antes "
                        f"a la fecha de inicio de cobertura. Inicio de cobertura: {_format_date_value(form_fields.get('fecha_inicio_cobertura'))} "
                        f"· Radicación: {_format_date_value(form_fields.get('fecha_radicacion'))}."
                    ),
                }
            )
    elif "afili" in tipo_tramite:
        direct_cell_fields = [
            "a_clase_riesgo",
            "a_numero_sedes",
            "a_numero_centros_trabajo",
            "a_numero_inicial_trabajadores_estudiantes",
            "a_valor_total_nomina",
        ]
        for field in direct_cell_fields:
            _append_required_cell_validation(
                blockers,
                form_cell_values,
                field,
                require_numeric=True,
                code_prefix="XLSX_AFILIACION_REQUIRED_CELL",
            )
        if not (traslado_payload and not afiliacion_payload):
            for field in PRIMARY_REQUIRED_AFILIACION:
                if not normalize_text(form_fields.get(field, "")):
                    missing_fields.append(field)
        if has_independientes_723:
            tolerated_independientes = {
                "a_numero_inicial_trabajadores_estudiantes",
                "a_valor_total_nomina",
            }
            missing_fields = [field for field in missing_fields if field not in tolerated_independientes]
        if traslado_payload:
            tolerated = {"a_codigo_actividad_economica_principal", "a_valor_total_nomina"}
            if set(missing_fields).issubset(tolerated):
                missing_fields = [field for field in missing_fields if field not in tolerated]
        missing_fields = [field for field in missing_fields if field not in direct_cell_fields]

        radicacion_date = _parse_date_value(form_fields.get("fecha_radicacion", ""))
        inicio_cobertura_date = _parse_date_value(form_fields.get("fecha_inicio_cobertura", ""))
        if radicacion_date and inicio_cobertura_date:
            expected_start = radicacion_date + timedelta(days=1)
            if inicio_cobertura_date.date() != expected_start.date():
                diff_days = (inicio_cobertura_date.date() - radicacion_date.date()).days
                blockers.append(
                    {
                        "code": "XLSX_PRIMARY_FECHA_COBERTURA_INVALIDA",
                        "severity": "blocker",
                        "message": (
                            "Para afiliaciones de primera vez, la fecha inicio de cobertura debe ser exactamente un día "
                            f"posterior a la fecha de radicación. Radicación: {_format_date_value(form_fields.get('fecha_radicacion'))} "
                            f"· Inicio de cobertura: {_format_date_value(form_fields.get('fecha_inicio_cobertura'))} "
                            f"· Diferencia detectada: {diff_days} día(s)."
                        ),
                    }
                )

    common_cell_fields = [
        ("numero_radicacion", True, False),
        ("lugar_afiliacion", False, False),
        ("codigo_lugar", True, False),
        ("nombre_lugar", False, False),
        ("naturaleza_juridica_codigo_tramite", True, False),
        ("naturaleza_juridica_nombre", False, False),
        ("tipo_aportante_codigo", True, False),
        ("tipo_aportante_nombre", False, False),
        ("tipo_persona", False, False),
        ("empleador_razon_social", False, False),
        ("empleador_tipo_documento", False, False),
        ("empleador_numero_documento_nit", True, False),
        ("rep_legal_primer_apellido", False, False),
        ("rep_legal_primer_nombre", False, False),
        ("rep_legal_tipo_documento", False, False),
        ("rep_legal_numero_documento", False, False),
        ("rep_legal_correo_electronico", False, True),
        ("sede_principal_codigo", True, False),
        ("sede_principal_nombre", False, False),
        ("sede_principal_direccion", False, False),
        ("sede_principal_telefono", True, False),
        ("sede_principal_correo", False, True),
        ("sede_principal_municipio_distrito", False, False),
        ("sede_principal_zona", False, False),
        ("sede_principal_as22", False, False),
        ("responsable_sede_primer_apellido", False, False),
        ("responsable_sede_primer_nombre", False, False),
        ("responsable_sede_tipo_documento", False, False),
        ("responsable_sede_numero_documento", True, False),
        ("responsable_sede_correo", False, True),
    ]
    for field, require_numeric, require_email in common_cell_fields:
        _append_required_cell_validation(
            blockers,
            form_cell_values,
            field,
            require_numeric=require_numeric,
            require_email=require_email,
            code_prefix="XLSX_COMMON_REQUIRED_CELL",
        )
    _append_cell_length_validation(
        blockers,
        form_cell_values,
        "numero_radicacion",
        min_length=6,
        max_length=40,
        code_prefix="XLSX_COMMON_REQUIRED_CELL",
    )
    _append_cell_length_validation(
        blockers,
        form_cell_values,
        "empleador_numero_documento_nit",
        min_length=6,
        max_length=12,
        code_prefix="XLSX_COMMON_REQUIRED_CELL",
    )
    _append_digits_length_validation(
        blockers,
        form_cell_values,
        "rep_legal_numero_documento",
        min_length=6,
        max_length=10,
        code_prefix="XLSX_COMMON_REQUIRED_CELL",
    )
    for field in [
        "rep_legal_primer_apellido",
        "rep_legal_primer_nombre",
        "responsable_sede_primer_apellido",
        "responsable_sede_primer_nombre",
    ]:
        _append_letters_only_validation(
            blockers,
            form_cell_values.get(field) or {},
            code="XLSX_FORM_LETTERS_ONLY",
            field=field,
        )

    _append_min_length_validation(
        blockers,
        form_cell_values,
        "sede_principal_direccion",
        min_length=5,
        code_prefix="XLSX_COMMON_REQUIRED_CELL",
    )
    _append_address_quality_validation(
        blockers,
        form_cell_values.get("sede_principal_direccion") or {},
        code="XLSX_COMMON_REQUIRED_CELL_INVALID_ADDRESS",
        field="sede_principal_direccion",
    )

    for field in ["autorizacion_1", "autorizacion_2", "autorizacion_3"]:
        _append_required_cell_validation(
            blockers,
            form_cell_values,
            field,
            require_numeric=False,
            code_prefix="XLSX_AUTHORIZATION_REQUIRED_CELL",
        )

    def form_raw(field: str) -> Any:
        return (form_cell_values.get(field) or {}).get("value") or form_fields.get(field, "")

    expected_sedes_value = form_raw("b_numero_sedes") if "traslado" in tipo_tramite else form_raw("a_numero_sedes")
    expected_sedes = _parse_amount(expected_sedes_value)
    sede_sheet_names = sorted(
        sede_sheet_values.keys(),
        key=lambda name: (_sede_sheet_number(name) is None, _sede_sheet_number(name) or 0, name),
    )
    if expected_sedes > 0:
        numbered_sheet_names = [
            name
            for name in sede_sheet_names
            if (_sede_sheet_number(name) or 0) <= expected_sedes
        ]
        if len(numbered_sheet_names) < expected_sedes:
            blockers.append(
                {
                    "code": "XLSX_SEDE_SHEET_COUNT_MISSING",
                    "severity": "blocker",
                    "message": (
                        f"El formulario declara {expected_sedes} sede(s), pero el XLSX trae "
                        f"{len(numbered_sheet_names)} hoja(s) de sede dentro de esa cantidad: {', '.join(numbered_sheet_names) or 'ninguna'}."
                    ),
                }
            )
        actual_numbers = {number for number in (_sede_sheet_number(name) for name in sede_sheet_names) if number is not None}
        expected_numbers = set(range(1, expected_sedes + 1))
        missing_numbers = sorted(expected_numbers - actual_numbers)
        if missing_numbers:
            blockers.append(
                {
                    "code": "XLSX_SEDE_SHEET_SEQUENCE_MISSING",
                    "severity": "blocker",
                    "message": "Faltan hojas de sede esperadas por el formulario: "
                    + ", ".join(f"Sede {number:02d} - Trabajadores" for number in missing_numbers)
                    + ".",
                }
            )
        sede_sheet_names = numbered_sheet_names

    sede_required_fields = [
        ("numero_radicacion", False, False, False),
        ("fecha_radicacion", False, False, True),
        ("fecha_inicio_cobertura", False, False, True),
        ("codigo_sede", True, False, False),
        ("nombre_sede", False, False, False),
        ("municipio", False, False, False),
        ("direccion_sede", False, False, False),
        ("telefono_sede", True, False, False),
        ("departamento", False, False, False),
        ("zona_sede", False, False, False),
        ("correo_sede", False, True, False),
        ("responsable_primer_apellido", False, False, False),
        ("responsable_primer_nombre", False, False, False),
        ("responsable_tipo_documento", False, False, False),
        ("responsable_numero_documento", False, False, False),
    ]
    expected_numero_radicacion = form_raw("numero_radicacion")
    expected_fecha_radicacion = form_raw("fecha_radicacion")
    expected_fecha_inicio = form_raw("fecha_inicio_cobertura")
    for sheet_name in sede_sheet_names:
        sheet_values = sede_sheet_values.get(sheet_name) or {}
        for field, require_numeric, require_email, require_date in sede_required_fields:
            _append_sede_cell_validation(
                blockers,
                sheet_name,
                sheet_values,
                field,
                require_numeric=require_numeric,
                require_email=require_email,
                require_date=require_date,
            )
        for field in ["responsable_primer_apellido", "responsable_primer_nombre"]:
            cell_info = _sheet_cell_info(sheet_values, field)
            _append_letters_only_validation(
                blockers,
                cell_info,
                code="XLSX_SEDE_LETTERS_ONLY",
                field=field,
                sheet=sheet_name,
                message_prefix=f"{sheet_name}: el campo '{cell_info.get('label') or field}' ({cell_info.get('cell') or 'celda requerida'})",
            )
        radicacion_value = _sheet_cell_info(sheet_values, "numero_radicacion").get("value")
        if normalize_text(expected_numero_radicacion) and normalize_text(radicacion_value) and normalize_text(radicacion_value) != normalize_text(expected_numero_radicacion):
            blockers.append(
                {
                    "code": "XLSX_SEDE_RADICACION_MISMATCH",
                    "severity": "blocker",
                    "sheet": sheet_name,
                    "field": "numero_radicacion",
                    "cell": "G7",
                    "message": (
                        f"{sheet_name}: el número de radicación (G7) debe coincidir con el formulario "
                        f"(Y7). Sede='{radicacion_value}' · Formulario='{expected_numero_radicacion}'."
                    ),
                }
            )
        sede_fecha_radicacion = _sheet_cell_info(sheet_values, "fecha_radicacion").get("value")
        if normalize_text(expected_fecha_radicacion) and normalize_text(sede_fecha_radicacion) and not _same_date_value(sede_fecha_radicacion, expected_fecha_radicacion):
            blockers.append(
                {
                    "code": "XLSX_SEDE_FECHA_RADICACION_MISMATCH",
                    "severity": "blocker",
                    "sheet": sheet_name,
                    "field": "fecha_radicacion",
                    "cell": "I7",
                    "message": (
                        f"{sheet_name}: la fecha de radicación (I7) debe coincidir con el formulario "
                        f"(G7). Sede='{_format_date_value(sede_fecha_radicacion)}' · Formulario='{_format_date_value(expected_fecha_radicacion)}'."
                    ),
                }
            )
        sede_fecha_inicio = _sheet_cell_info(sheet_values, "fecha_inicio_cobertura").get("value")
        if normalize_text(expected_fecha_inicio) and normalize_text(sede_fecha_inicio) and not _same_date_value(sede_fecha_inicio, expected_fecha_inicio):
            blockers.append(
                {
                    "code": "XLSX_SEDE_FECHA_INICIO_MISMATCH",
                    "severity": "blocker",
                    "sheet": sheet_name,
                    "field": "fecha_inicio_cobertura",
                    "cell": "K7",
                    "message": (
                        f"{sheet_name}: la fecha inicio de cobertura (K7) debe coincidir con el formulario "
                        f"(L7). Sede='{_format_date_value(sede_fecha_inicio)}' · Formulario='{_format_date_value(expected_fecha_inicio)}'."
                    ),
                }
            )

    validated_sede_codes = {
        normalize_text(_sheet_cell_info(sede_sheet_values.get(sheet_name) or {}, "codigo_sede").get("value"))
        for sheet_name in sede_sheet_names
        if normalize_text(_sheet_cell_info(sede_sheet_values.get(sheet_name) or {}, "codigo_sede").get("value"))
    }
    expected_activity = form_raw("b_codigo_actividad_economica_principal") if "traslado" in tipo_tramite else form_raw("a_codigo_actividad_economica_principal")
    expected_centros_value = form_raw("b_numero_centros_trabajo") if "traslado" in tipo_tramite else form_raw("a_numero_centros_trabajo")
    expected_workers_value = form_raw("b_numero_total_trabajadores_estudiantes") if "traslado" in tipo_tramite else form_raw("a_numero_inicial_trabajadores_estudiantes")
    expected_amount_value = form_raw("b_monto_total_cotizacion") if "traslado" in tipo_tramite else form_raw("a_valor_total_nomina")
    center_required_fields = [
        ("codigo_centro_trabajo", True, False, None, None),
        ("nombre_centro_trabajo", False, False, None, None),
        ("codigo_actividad_economica", True, False, None, None),
        ("descripcion_actividad_economica", False, False, None, None),
        ("clase_riesgo", True, False, None, None),
        ("municipio_sede", False, False, None, None),
        ("departamento_sede", False, False, None, None),
        ("zona_sede", False, False, None, None),
        ("direccion_sede", False, False, None, None),
        ("telefono_sede", True, False, 6, 12),
        ("correo_sede", False, True, None, None),
        ("responsable_primer_apellido", False, False, None, None),
        ("responsable_primer_nombre", False, False, None, None),
        ("responsable_tipo_documento", False, False, None, None),
        ("responsable_numero_identificacion", False, False, 6, 12),
        ("responsable_correo", False, True, None, None),
        ("centralizada_descentralizada", False, False, None, None),
        ("cantidad_trabajadores_estudiantes", True, False, None, None),
        ("monto_total_cotizacion", True, False, None, None),
    ]
    center_codes_seen: Dict[str, Dict[str, Any]] = {}
    total_center_rows = 0
    total_center_workers = 0
    total_center_amount = 0
    for sheet_name in sede_sheet_names:
        for row_values in list(sede_center_rows.get(sheet_name) or []):
            total_center_rows += 1
            for field, require_numeric, require_email, min_length, max_length in center_required_fields:
                _append_center_cell_validation(
                    blockers,
                    sheet_name,
                    row_values,
                    field,
                    require_numeric=require_numeric,
                    require_email=require_email,
                    min_length=min_length,
                    max_length=max_length,
                )
            center_code_info = _center_cell_info(row_values, "codigo_centro_trabajo")
            center_code = normalize_text(center_code_info.get("value"))
            if center_code:
                if center_code in validated_sede_codes:
                    blockers.append(
                        {
                            "code": "XLSX_CENTRO_CODE_EQUALS_SEDE_CODE",
                            "severity": "blocker",
                            "field": "codigo_centro_trabajo",
                            "sheet": sheet_name,
                            "cell": center_code_info.get("cell"),
                            "row": center_code_info.get("row"),
                            "message": (
                                f"{sheet_name}, fila {center_code_info.get('row')}: el código del centro de trabajo "
                                f"({center_code_info.get('cell')}) no puede ser igual al código de una sede. "
                                f"Valor recibido: {center_code}."
                            ),
                        }
                    )
                previous = center_codes_seen.get(center_code)
                if previous:
                    blockers.append(
                        {
                            "code": "XLSX_CENTRO_CODE_DUPLICATE",
                            "severity": "blocker",
                            "field": "codigo_centro_trabajo",
                            "sheet": sheet_name,
                            "cell": center_code_info.get("cell"),
                            "row": center_code_info.get("row"),
                            "message": (
                                f"{sheet_name}, fila {center_code_info.get('row')}: el código del centro de trabajo "
                                f"({center_code}) está duplicado. Ya existe en {previous.get('sheet')} "
                                f"{previous.get('cell')}."
                            ),
                        }
                    )
                else:
                    center_codes_seen[center_code] = {
                        "sheet": sheet_name,
                        "cell": center_code_info.get("cell"),
                        "row": center_code_info.get("row"),
                    }
            activity_info = _center_cell_info(row_values, "codigo_actividad_economica")
            activity_value = activity_info.get("value")
            if normalize_text(expected_activity) and normalize_text(activity_value):
                expected_activity_digits = only_digits(expected_activity)
                activity_digits = only_digits(activity_value)
                if expected_activity_digits and activity_digits and expected_activity_digits != activity_digits:
                    blockers.append(
                        {
                            "code": "XLSX_CENTRO_ACTIVITY_MISMATCH",
                            "severity": "blocker",
                            "field": "codigo_actividad_economica",
                            "sheet": sheet_name,
                            "cell": activity_info.get("cell"),
                            "row": activity_info.get("row"),
                            "message": (
                                f"{sheet_name}, fila {activity_info.get('row')}: el código de actividad económica "
                                f"({activity_info.get('cell')}) debe coincidir con el formulario. "
                                f"Centro='{activity_value}' · Formulario='{expected_activity}'."
                            ),
                        }
                    )
            central_info = _center_cell_info(row_values, "centralizada_descentralizada")
            central_value = central_info.get("value")
            if normalize_text(central_value) and not _is_allowed_centralization_value(central_value):
                blockers.append(
                    {
                        "code": "XLSX_CENTRO_CENTRALIZACION_INVALID",
                        "severity": "blocker",
                        "field": "centralizada_descentralizada",
                        "sheet": sheet_name,
                        "cell": central_info.get("cell"),
                        "row": central_info.get("row"),
                        "message": (
                            f"{sheet_name}, fila {central_info.get('row')}: el campo 'Centralizada o descentralizada' "
                            f"({central_info.get('cell')}) debe ser Centralizada o Descentralizada. "
                            f"Valor recibido: {central_value}."
                        ),
                    }
                )
            total_center_workers += _parse_amount(_center_cell_info(row_values, "cantidad_trabajadores_estudiantes").get("value"))
            total_center_amount += _parse_amount(_center_cell_info(row_values, "monto_total_cotizacion").get("value"))

    if sede_sheet_names and total_center_rows <= 0 and not has_independientes_723:
        blockers.append(
            {
                "code": "XLSX_CENTRO_ROWS_MISSING",
                "severity": "blocker",
                "message": "Las hojas de sedes validadas no traen centros de trabajo desde la fila 24.",
            }
        )
    if normalize_text(expected_centros_value) and _parse_amount(expected_centros_value) != total_center_rows:
        blockers.append(
            {
                "code": "XLSX_CENTRO_TOTAL_COUNT_MISMATCH",
                "severity": "blocker",
                "message": (
                    "El número de centros de trabajo del formulario no coincide con las filas de centros "
                    f"detectadas desde la fila 24. Formulario='{expected_centros_value}' · Centros detectados='{total_center_rows}'."
                ),
            }
        )
    if normalize_text(expected_workers_value) and _parse_amount(expected_workers_value) != total_center_workers:
        blockers.append(
            {
                "code": "XLSX_CENTRO_TOTAL_WORKERS_MISMATCH",
                "severity": "blocker",
                "message": (
                    "El número de trabajadores/estudiantes del formulario no coincide con la suma de AJ "
                    f"en centros de trabajo. Formulario='{expected_workers_value}' · Suma AJ='{total_center_workers}'. "
                    f"{WORKER_DATA_START_REMINDER}"
                ),
            }
        )
    if normalize_text(expected_amount_value) and _parse_amount(expected_amount_value) != total_center_amount:
        blockers.append(
            {
                "code": "XLSX_CENTRO_TOTAL_AMOUNT_MISMATCH",
                "severity": "blocker",
                "message": (
                    "El valor total de nómina/cotización del formulario no coincide con la suma de AL "
                    f"en centros de trabajo. Formulario='{expected_amount_value}' · Suma AL='{total_center_amount}'. "
                    f"{WORKER_DATA_START_REMINDER}"
                ),
            }
        )

    worker_required_fields = [
        ("codigo_centro_trabajo", True, False, None, None),
        ("tipo_documento", False, False, None, None),
        ("numero_identificacion", False, False, 6, 12),
        ("primer_apellido", False, False, None, None),
        ("primer_nombre", False, False, None, None),
        ("fecha_nacimiento_dia", True, False, None, None),
        ("fecha_nacimiento_mes", True, False, None, None),
        ("fecha_nacimiento_anio", True, False, None, None),
        ("sexo_identificacion", False, False, None, None),
        ("cargo", False, False, None, None),
        ("salario", True, False, None, None),
        ("tipo_salario", False, False, None, None),
        ("eps", False, False, None, None),
        ("pension", False, False, None, None),
        ("direccion", False, False, None, None),
        ("celular", True, False, 6, 10),
        ("correo", False, True, None, None),
        ("municipio_distrito", False, False, None, None),
        ("zona", False, False, None, None),
        ("departamento", False, False, None, None),
        ("jornada", False, False, None, None),
        ("modalidad", False, False, None, None),
        ("codigo_tipo_trabajador", True, False, None, None),
        ("tipo_trabajador", False, False, None, None),
    ]
    _, smmlv_value = _resolve_smmlv_value(form_fields)
    total_structured_worker_rows = 0
    total_worker_salary = 0
    for sheet_name in sede_sheet_names:
        sheet_center_rows = list(sede_center_rows.get(sheet_name) or [])
        sheet_worker_rows = list(sede_worker_rows.get(sheet_name) or [])
        sheet_center_codes = {
            normalize_text(_center_cell_info(row_values, "codigo_centro_trabajo").get("value"))
            for row_values in sheet_center_rows
            if normalize_text(_center_cell_info(row_values, "codigo_centro_trabajo").get("value"))
        }
        expected_sheet_workers = sum(
            _parse_amount(_center_cell_info(row_values, "cantidad_trabajadores_estudiantes").get("value"))
            for row_values in sheet_center_rows
        )
        expected_sheet_salary = sum(
            _parse_amount(_center_cell_info(row_values, "monto_total_cotizacion").get("value"))
            for row_values in sheet_center_rows
        )
        sheet_salary = 0
        total_structured_worker_rows += len(sheet_worker_rows)
        for row_values in sheet_worker_rows:
            for field, require_numeric, require_email, min_length, max_length in worker_required_fields:
                _append_worker_cell_validation(
                    blockers,
                    sheet_name,
                    row_values,
                    field,
                    require_numeric=require_numeric,
                    require_email=require_email,
                    min_length=min_length,
                    max_length=max_length,
                    allow_zero_length=field == "celular",
                )
            for field in ["primer_apellido", "primer_nombre"]:
                cell_info = _worker_cell_info(row_values, field)
                _append_letters_only_validation(
                    blockers,
                    cell_info,
                    code="XLSX_TRABAJADOR_LETTERS_ONLY",
                    field=field,
                    sheet=sheet_name,
                    message_prefix=(
                        f"{sheet_name}, fila {cell_info.get('row')}: "
                        f"el campo '{cell_info.get('label') or field}' ({cell_info.get('cell') or 'celda requerida'})"
                    ),
                )
            address_info = _worker_cell_info(row_values, "direccion")
            _append_address_quality_validation(
                blockers,
                address_info,
                code="XLSX_TRABAJADOR_REQUIRED_CELL_INVALID_ADDRESS",
                field="direccion",
                sheet=sheet_name,
                message_prefix=(
                    f"{sheet_name}, fila {address_info.get('row')}: "
                    f"el campo '{address_info.get('label') or 'direccion'}' ({address_info.get('cell') or 'celda requerida'})"
                ),
            )
            worker_center_info = _worker_cell_info(row_values, "codigo_centro_trabajo")
            worker_center_code = normalize_text(worker_center_info.get("value"))
            if worker_center_code and worker_center_code not in sheet_center_codes:
                blockers.append(
                    {
                        "code": "XLSX_TRABAJADOR_CENTER_CODE_NOT_FOUND",
                        "severity": "blocker",
                        "field": "codigo_centro_trabajo",
                        "sheet": sheet_name,
                        "cell": worker_center_info.get("cell"),
                        "row": worker_center_info.get("row"),
                        "message": (
                            f"{sheet_name}, fila {worker_center_info.get('row')}: el código del centro de trabajo "
                            f"({worker_center_info.get('cell')}) debe coincidir con un centro registrado en la misma hoja. "
                            f"Valor recibido: {worker_center_code or 'vacío'}."
                        ),
                    }
                )
            day_value = _worker_cell_info(row_values, "fecha_nacimiento_dia").get("value")
            month_value = _worker_cell_info(row_values, "fecha_nacimiento_mes").get("value")
            year_value = _worker_cell_info(row_values, "fecha_nacimiento_anio").get("value")
            if normalize_text(day_value) and normalize_text(month_value) and normalize_text(year_value) and not _valid_date_parts(day_value, month_value, year_value):
                blockers.append(
                    {
                        "code": "XLSX_TRABAJADOR_BIRTHDATE_INVALID",
                        "severity": "blocker",
                        "field": "fecha_nacimiento",
                        "sheet": sheet_name,
                        "cell": _worker_cell_info(row_values, "fecha_nacimiento_dia").get("cell"),
                        "row": _worker_cell_info(row_values, "fecha_nacimiento_dia").get("row"),
                        "message": (
                            f"{sheet_name}, fila {_worker_cell_info(row_values, 'fecha_nacimiento_dia').get('row')}: "
                            f"la fecha de nacimiento debe tener día, mes y año válidos. "
                            f"Valor recibido: {day_value}/{month_value}/{year_value}."
                        ),
                    }
                )
            sex_info = _worker_cell_info(row_values, "sexo_identificacion")
            sex_value = sex_info.get("value")
            if normalize_text(sex_value) and not _is_allowed_worker_sex_value(sex_value):
                blockers.append(
                    {
                        "code": "XLSX_TRABAJADOR_SEX_INVALID",
                        "severity": "blocker",
                        "field": "sexo_identificacion",
                        "sheet": sheet_name,
                        "cell": sex_info.get("cell"),
                        "row": sex_info.get("row"),
                        "message": (
                            f"{sheet_name}, fila {sex_info.get('row')}: el sexo identificación ({sex_info.get('cell')}) "
                            "debe ser Masculino, Femenino, Otro, No Binario o Transexual. "
                            f"Valor recibido: {sex_value}."
                        ),
                    }
                )
            salary_info = _worker_cell_info(row_values, "salario")
            salary = _parse_amount(salary_info.get("value"))
            sheet_salary += salary
            total_worker_salary += salary
            if normalize_text(salary_info.get("value")) and salary < smmlv_value:
                blockers.append(
                    {
                        "code": "XLSX_TRABAJADOR_SALARY_BELOW_SMMLV",
                        "severity": "blocker",
                        "field": "salario",
                        "sheet": sheet_name,
                        "cell": salary_info.get("cell"),
                        "row": salary_info.get("row"),
                        "message": (
                            f"{sheet_name}, fila {salary_info.get('row')}: el salario ({salary_info.get('cell')}) "
                            f"debe ser mayor o igual a {smmlv_value}. Valor recibido: {salary_info.get('value')}."
                        ),
                    }
                )
            salary_type_info = _worker_cell_info(row_values, "tipo_salario")
            salary_type_value = salary_type_info.get("value")
            if normalize_text(salary_type_value) and not _is_allowed_salary_type_value(salary_type_value):
                blockers.append(
                    {
                        "code": "XLSX_TRABAJADOR_SALARY_TYPE_INVALID",
                        "severity": "blocker",
                        "field": "tipo_salario",
                        "sheet": sheet_name,
                        "cell": salary_type_info.get("cell"),
                        "row": salary_type_info.get("row"),
                        "message": (
                            f"{sheet_name}, fila {salary_type_info.get('row')}: el tipo de salario "
                            f"({salary_type_info.get('cell')}) debe ser 1-Fijo o 2-Variable. "
                            f"Valor recibido: {salary_type_value}."
                        ),
                    }
                )
        if sheet_center_rows and len(sheet_worker_rows) != expected_sheet_workers:
            blockers.append(
                {
                    "code": "XLSX_TRABAJADOR_SHEET_COUNT_MISMATCH",
                    "severity": "blocker",
                    "sheet": sheet_name,
                    "message": (
                        f"{sheet_name}: la cantidad de filas de trabajadores no coincide con la suma de AJ "
                        f"de los centros de trabajo. Trabajadores detectados='{len(sheet_worker_rows)}' · Suma AJ='{expected_sheet_workers}'."
                    ),
                }
            )
        if sheet_center_rows and sheet_salary != expected_sheet_salary:
            blockers.append(
                {
                    "code": "XLSX_TRABAJADOR_SHEET_SALARY_MISMATCH",
                    "severity": "blocker",
                    "sheet": sheet_name,
                    "message": (
                        f"{sheet_name}: la suma de salarios de trabajadores no coincide con la suma de AL "
                        f"de los centros de trabajo. Salarios='{sheet_salary}' · Suma AL='{expected_sheet_salary}'. "
                        f"{WORKER_DATA_START_REMINDER}"
                    ),
                }
            )

    if normalize_text(expected_workers_value) and _parse_amount(expected_workers_value) != total_structured_worker_rows:
        blockers.append(
            {
                "code": "XLSX_TRABAJADOR_TOTAL_COUNT_MISMATCH",
                "severity": "blocker",
                "message": (
                    "El total de trabajadores del formulario no coincide con las filas de trabajadores "
                    f"leídas en sedes. Formulario='{expected_workers_value}' · Trabajadores detectados='{total_structured_worker_rows}'. "
                    f"{WORKER_DATA_START_REMINDER}"
                ),
            }
        )
    if total_worker_salary and total_worker_salary != total_center_amount:
        blockers.append(
            {
                "code": "XLSX_TRABAJADOR_TOTAL_SALARY_CENTER_MISMATCH",
                "severity": "blocker",
                "message": (
                    "La suma total de salarios de trabajadores no coincide con la suma total de AL "
                    f"en centros de trabajo. Salarios='{total_worker_salary}' · Suma AL='{total_center_amount}'. "
                    f"{WORKER_DATA_START_REMINDER}"
                ),
            }
        )
    if normalize_text(expected_amount_value) and total_worker_salary and _parse_amount(expected_amount_value) != total_worker_salary:
        blockers.append(
            {
                "code": "XLSX_TRABAJADOR_TOTAL_SALARY_FORM_MISMATCH",
                "severity": "blocker",
                "message": (
                    "La suma total de salarios de trabajadores no coincide con el valor total de nómina/cotización "
                    f"del formulario. Formulario='{expected_amount_value}' · Salarios='{total_worker_salary}'. "
                    f"{WORKER_DATA_START_REMINDER}"
                ),
            }
        )

    total_worker_rows = sum(int(count or 0) for count in worker_sheet_counts.values())
    if not worker_sheet_counts and not has_independientes_723:
        blockers.append(
            {
                "code": "XLSX_PRIMARY_SEDE_SHEETS_MISSING",
                "severity": "blocker",
                "message": "El XLSX no trae al menos una hoja de sede/trabajadores para validar el contrato.",
            }
        )
    if total_worker_rows <= 0 and not has_independientes_723:
        blockers.append(
            {
                "code": "XLSX_PRIMARY_WORKERS_MISSING",
                "severity": "blocker",
                "message": "El XLSX no trae filas válidas de trabajadores en las hojas de sede.",
            }
        )
    if worker_sheet_counts and all(int(count or 0) <= 0 for count in worker_sheet_counts.values()) and not has_independientes_723:
        blockers.append(
            {
                "code": "XLSX_PRIMARY_SHEETS_EMPTY",
                "severity": "blocker",
                "message": "Las hojas de sedes/trabajadores del XLSX no traen registros mínimos válidos.",
            }
        )

    if missing_fields:
        missing_fields = sorted(set(missing_fields))
        blockers.append(
            {
                "code": "XLSX_PRIMARY_REQUIRED_FIELDS_MISSING",
                "severity": "blocker",
                "message": "El XLSX no trae completos estos campos obligatorios del formulario: " + ", ".join(missing_fields) + ".",
            }
        )
        next_actions.append("Completar los campos obligatorios del formulario del XLSX antes de continuar.")

    return {
        "blockers": blockers,
        "missing_fields": sorted(set(missing_fields)),
        "next_actions": next_actions,
        "form_fields": form_fields,
    }


def _parse_amount(value: Any) -> int:
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


def _valid_birth_parts(day: str, month: str, year: str) -> bool:
    day_digits = only_digits(day)
    month_digits = only_digits(month)
    year_digits = only_digits(year)
    if not (day_digits and month_digits and year_digits):
        return False
    if len(year_digits) == 2:
        year_digits = "19" + year_digits
    try:
        datetime(int(year_digits), int(month_digits), int(day_digits))
        return True
    except ValueError:
        return False


def _choose_form_block(form_fields: Dict[str, Any], record_count: int, actual_nomina: int) -> str:
    a_workers = _parse_amount(form_fields.get("a_numero_inicial_trabajadores_estudiantes"))
    b_workers = _parse_amount(form_fields.get("b_numero_total_trabajadores_estudiantes"))
    a_nomina = _parse_amount(form_fields.get("a_valor_total_nomina"))
    b_nomina = _parse_amount(form_fields.get("b_monto_total_cotizacion"))

    a_score = 0
    b_score = 0
    if a_workers and record_count and a_workers == record_count:
        a_score += 2
    if b_workers and record_count and b_workers == record_count:
        b_score += 2
    if a_nomina and actual_nomina and a_nomina == actual_nomina:
        a_score += 2
    if b_nomina and actual_nomina and b_nomina == actual_nomina:
        b_score += 2
    if any(normalize_text(form_fields.get(k, "")) for k in ["a_codigo_actividad_economica_principal", "a_valor_total_nomina"]):
        a_score += 1
    if any(normalize_text(form_fields.get(k, "")) for k in ["b_codigo_actividad_economica_principal", "b_monto_total_cotizacion", "b_arl_de_la_cual_se_traslada"]):
        b_score += 1
    return "b" if b_score > a_score else "a"
    if len(year_digits) == 2:
        year_digits = "19" + year_digits
    try:
        datetime(int(year_digits), int(month_digits), int(day_digits))
        return True
    except ValueError:
        return False


def run_xlsx_secondary_validations(xlsx_profile: Dict[str, Any]) -> Dict[str, Any]:
    form_fields = dict((xlsx_profile or {}).get("form_fields") or {})
    records = list((xlsx_profile or {}).get("records") or [])
    worker_sheet_salary_totals = dict((xlsx_profile or {}).get("worker_sheet_salary_totals") or {})

    alerts: List[Dict[str, Any]] = []
    blockers: List[Dict[str, Any]] = []

    actual_nomina_from_records = sum(
        _parse_amount(
            record.get("salario")
            or record.get("salario_basico")
            or record.get("ibc")
            or record.get("ingreso_base_de_cotizacion")
            or ""
        )
        for record in records
    )
    actual_nomina_from_controls = sum(int(value or 0) for value in worker_sheet_salary_totals.values())
    actual_nomina = actual_nomina_from_controls or actual_nomina_from_records
    block = _choose_form_block(form_fields, len(records), actual_nomina)
    expected_nomina = _parse_amount(
        form_fields.get("a_valor_total_nomina") if block == "a" else form_fields.get("b_monto_total_cotizacion")
    )
    if expected_nomina > 0 and actual_nomina > 0 and expected_nomina != actual_nomina:
        delta = abs(expected_nomina - actual_nomina)
        tolerance = max(1000, int(expected_nomina * 0.02))  # 2% tolerancia para diferencias de redondeo
        if delta > tolerance:
            blockers.append(
                {
                    "code": "XLSX_SECONDARY_NOMINA_MISMATCH",
                    "severity": "blocker",
                    "message": (
                        f"La nómina del formulario ({expected_nomina}) no coincide con la suma de salarios leídos ({actual_nomina}). "
                        f"{WORKER_DATA_START_REMINDER}"
                    ),
                }
            )

    expected_centros = _parse_amount(
        form_fields.get("a_numero_centros_trabajo") if block == "a" else form_fields.get("b_numero_centros_trabajo")
    )
    actual_centros = {
        only_digits(record.get("codigo_del_centro_de_trabajo") or record.get("codigo_centro_trabajo") or "")
        for record in records
        if only_digits(record.get("codigo_del_centro_de_trabajo") or record.get("codigo_centro_trabajo") or "")
    }
    if expected_centros > 0 and actual_centros and expected_centros != len(actual_centros):
        alerts.append(
            {
                "code": "XLSX_SECONDARY_CENTROS_MISMATCH",
                "severity": "alert",
                "message": (
                    f"El formulario declara {expected_centros} centro(s) de trabajo, pero los trabajadores referencian {len(actual_centros)} centro(s) distinto(s)."
                ),
            }
        )

    invalid_worker_documents = []
    for record in records[:1000]:
        raw_document = _worker_document_raw(record)
        if raw_document and not _is_strict_numeric_value(raw_document):
            invalid_worker_documents.append(
                (
                    raw_document,
                    normalize_text(record.get("_sheet", "")),
                    normalize_text(record.get("_row", "")),
                )
            )
            if len(invalid_worker_documents) >= 10:
                break
    if invalid_worker_documents:
        blockers.append(
            {
                "code": "XLSX_SECONDARY_DOCUMENTO_NO_NUMERICO",
                "severity": "blocker",
                "message": "Se identifican registros de trabajadores con documentos que contienen caracteres no numéricos: "
                + "; ".join(
                    " | ".join(part for part in [doc, sheet, f"fila {row}" if row else ""] if part)
                    for doc, sheet, row in invalid_worker_documents
                )
                + ".",
            }
        )

    smmlv_year, smmlv_value = _resolve_smmlv_value(form_fields)
    salarios_bajos = []
    for record in records[:500]:
        salario = _parse_amount(
            record.get("salario")
            or record.get("salario_basico")
            or record.get("ibc")
            or record.get("ingreso_base_de_cotizacion")
            or ""
        )
        documento = only_digits(_worker_document_raw(record))
        if salario and salario < smmlv_value:
            salarios_bajos.append((documento, salario, normalize_text(record.get("_sheet", "")), normalize_text(record.get("_row", ""))))
            if len(salarios_bajos) >= 5:
                break
    if salarios_bajos:
        blockers.append(
            {
                "code": "XLSX_SECONDARY_SMMLV_BLOCKER",
                "severity": "blocker",
                "message": f"Se detectaron trabajadores con salario inferior al salario mínimo configurado para {smmlv_year} ({smmlv_value}): "
                + "; ".join(
                    " | ".join(part for part in [doc or "n/d", str(sal), sheet, f"fila {row}" if row else ""] if part)
                    for doc, sal, sheet, row in salarios_bajos
                )
                + ".",
            }
        )

    eps_catalog = _load_name_catalog(EPS_CATALOG_PATH) | _load_pila_name_catalog("EPS")
    afp_catalog = _load_name_catalog(AFP_CATALOG_PATH) | _load_pila_name_catalog("AFP")
    invalid_eps = []
    invalid_afp = []
    try:
        valid_tokens = _build_valid_tokens(EPS_CATALOG_PATH, AFP_CATALOG_PATH)
        eps_token_sets = [_get_entity_tokens(i.get("nombre","")) for i in json.loads(EPS_CATALOG_PATH.read_text(encoding="utf-8")) if isinstance(i,dict) and i.get("nombre") and i["nombre"] not in ("SIN DEFINIR",)]
        afp_token_sets = [_get_entity_tokens(i.get("nombre","")) for i in json.loads(AFP_CATALOG_PATH.read_text(encoding="utf-8")) if isinstance(i,dict) and i.get("nombre") and i["nombre"] not in ("NO SUMINISTRADO","DESCONOCIDO")]
        for item in json.loads(PILA_CATALOG_PATH.read_text(encoding="utf-8")):
            if not isinstance(item, dict):
                continue
            values = _pila_alias_values(item)
            token_sets = [_get_entity_tokens(str(value)) for value in values if value]
            if str(item.get("subsistema") or "").upper() == "EPS":
                eps_token_sets.extend(token_sets)
            elif str(item.get("subsistema") or "").upper() == "AFP":
                afp_token_sets.extend(token_sets)
    except Exception:
        valid_tokens = set()
        eps_token_sets = []
        afp_token_sets = []
    for record in records[:1000]:
        documento = only_digits(_worker_document_raw(record))
        eps_value = normalize_text(record.get("eps", ""))
        afp_value = normalize_text(record.get("pension") or record.get("afp") or "")
        sheet = normalize_text(record.get("_sheet", ""))
        row = normalize_text(record.get("_row", ""))
        eps_norm = _normalize_catalog_name(eps_value) if eps_value else ""
        afp_norm = _normalize_catalog_name(afp_value) if afp_value else ""
        # Verificar EPS via tokens del dominio
        if eps_value:
            eps_match = eps_norm in eps_catalog or _check_entity_valid(eps_value, eps_token_sets, valid_tokens)
            if not eps_match:
                invalid_eps.append((documento, eps_value, sheet, row))
        # Verificar AFP via tokens del dominio
        if afp_value:
            afp_match = afp_norm in afp_catalog or _check_entity_valid(afp_value, afp_token_sets, valid_tokens)
            if not afp_match:
                invalid_afp.append((documento, afp_value, sheet, row))
    if invalid_eps:
        alerts.append(
            {
                "code": "XLSX_SECONDARY_EPS_INVALID",
                "severity": "warning",
                "message": "Se detectaron trabajadores con EPS que no cruza contra el catálogo PILA/EPS de referencia; revisar nombre, sin devolución automática: "
                + "; ".join(
                    " | ".join(part for part in [doc or "n/d", eps, sheet, f"fila {row}" if row else ""] if part)
                    for doc, eps, sheet, row in invalid_eps
                )
                + ".",
            }
        )
    if invalid_afp:
        alerts.append(
            {
                "code": "XLSX_SECONDARY_AFP_INVALID",
                "severity": "warning",
                "message": "Se detectaron trabajadores con AFP que no cruza contra el catálogo PILA/AFP de referencia; revisar nombre, sin devolución automática: "
                + "; ".join(
                    " | ".join(part for part in [doc or "n/d", afp, sheet, f"fila {row}" if row else ""] if part)
                    for doc, afp, sheet, row in invalid_afp
                )
                + ".",
            }
        )

    invalid_births = []
    for record in records[:500]:
        day = record.get("fecha_nacimiento_dia", "")
        month = record.get("fecha_nacimiento_mes", "")
        year = record.get("fecha_nacimiento_ano", "")
        combined_birth = normalize_text(record.get("fecha_de_nacimiento", ""))
        if combined_birth and _valid_date(combined_birth):
            continue
        has_any_birth_parts = any(normalize_text(part) for part in [day, month, year])
        if not has_any_birth_parts:
            continue
        if _valid_birth_parts(day, month, year):
            continue
        invalid_births.append(
            (
                only_digits(_worker_document_raw(record)),
                normalize_text(day),
                normalize_text(month),
                normalize_text(year),
                normalize_text(record.get("_sheet", "")),
                normalize_text(record.get("_row", "")),
            )
        )
        if len(invalid_births) >= 5:
            break
    if invalid_births:
        alerts.append(
            {
                "code": "XLSX_SECONDARY_BIRTHDATE_INVALID",
                "severity": "alert",
                "message": "Se detectaron fechas de nacimiento inválidas en trabajadores: "
                + "; ".join(
                    " | ".join(
                        item
                        for item in [
                            doc or "n/d",
                            f"{day}/{month}/{year}",
                            sheet,
                            f"fila {row}" if row else "",
                        ]
                        if item
                    )
                    for doc, day, month, year, sheet, row in invalid_births
                )
                + ".",
            }
        )

    special_worker_issues = []
    for record in records[:500]:
        tipo_trabajador = normalize_haystack(record.get("tipo_de_trabajador", ""))
        if not any(token in tipo_trabajador for token in ["independ", "estudiante"]):
            continue
        marked = 0
        for key, value in record.items():
            if not (key.startswith("dia_") or key.startswith("horario_")):
                continue
            text = normalize_haystack(value)
            if text in {"x", "si", "sí", "1", "true"}:
                marked += 1
        if marked < 2:
            special_worker_issues.append(
                (
                    only_digits(_worker_document_raw(record)),
                    normalize_text(record.get("tipo_de_trabajador", "")),
                    marked,
                    normalize_text(record.get("_sheet", "")),
                    normalize_text(record.get("_row", "")),
                )
            )
            if len(special_worker_issues) >= 5:
                break
    if special_worker_issues:
        alerts.append(
            {
                "code": "XLSX_SECONDARY_SPECIAL_WORKER_MARKS",
                "severity": "alert",
                "message": "Se detectaron trabajadores Independiente/Estudiante con menos de 2 marcas en días/horario: "
                + "; ".join(
                    " | ".join(
                        item
                        for item in [
                            doc or "n/d",
                            worker_type,
                            f"marcas={marked}",
                            sheet,
                            f"fila {row}" if row else "",
                        ]
                        if item
                    )
                    for doc, worker_type, marked, sheet, row in special_worker_issues
                )
                + ".",
            }
        )

    return {
        "alerts": alerts,
        "blockers": blockers,
        "selected_block": block,
        "expected_nomina": expected_nomina,
        "actual_nomina": actual_nomina,
        "actual_nomina_from_records": actual_nomina_from_records,
        "actual_nomina_from_controls": actual_nomina_from_controls,
        "actual_centros": sorted(actual_centros),
        "smmlv_year": smmlv_year,
        "smmlv_value": smmlv_value,
    }
