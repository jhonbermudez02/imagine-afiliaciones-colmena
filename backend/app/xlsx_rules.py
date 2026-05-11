from __future__ import annotations

import json
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_haystack(value: Any) -> str:
    return normalize_text(value).lower()


def only_digits(value: Any) -> str:
    return re.sub(r"\D+", "", str(value or ""))


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
    return bool(re.fullmatch(r"\d+", text))


def _is_blank_value(value: Any) -> bool:
    return not normalize_text(value)


def _is_email_value(value: Any) -> bool:
    text = normalize_text(value)
    if not text:
        return False
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", text))


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
                "message": f"El campo '{label}' ({cell}) debe tener formato de correo electrónico válido. Valor recibido: {raw_value}.",
            }
        )


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
        qdrant = QdrantClient(host="imagine_qdrant", port=6333)
        col = "afi_eps_catalog" if tipo == "eps" else "afi_afp_catalog"
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
            ("b_clase_riesgo", True),
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
        ("lugar_afiliacion", False, False),
        ("codigo_lugar", False, False),
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

    for field in ["autorizacion_1", "autorizacion_2", "autorizacion_3"]:
        _append_required_cell_validation(
            blockers,
            form_cell_values,
            field,
            require_numeric=False,
            code_prefix="XLSX_AUTHORIZATION_REQUIRED_CELL",
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
                        f"La nómina del formulario ({expected_nomina}) no coincide con la suma de salarios leídos ({actual_nomina})."
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
