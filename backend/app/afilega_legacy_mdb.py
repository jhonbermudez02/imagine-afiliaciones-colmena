from __future__ import annotations

import re
from typing import Any, Dict, List

SOURCE_MDB_PATH = "data/source_registry/Afiliaciones.mdb"
MDB_VERSION = "5.2"

DIGITO_MULTIPLIERS: List[int] = [71, 67, 59, 53, 47, 43, 41, 37, 29, 23, 19, 17, 13, 7, 3]

DOCUMENT_CATALOG: Dict[int, Dict[str, str]] = {
    1: {"legacy_name": "AFILIACION", "document_type": "formulario_afiliacion"},
    2: {"legacy_name": "SEDES", "document_type": "anexo_sedes"},
    3: {"legacy_name": "LISTADO TRABAJADORES", "document_type": "relacion_ingreso_trabajadores"},
    4: {"legacy_name": "CARTA", "document_type": "carta_presentacion_trabajador"},
    5: {"legacy_name": "CEDULA", "document_type": "cedula"},
    6: {"legacy_name": "RUT", "document_type": "rut_contratista"},
    7: {"legacy_name": "CAMARA DE COMERCIO", "document_type": "camara_comercio_contratante"},
    10: {"legacy_name": "NOMINA ANEXA", "document_type": "nomina_anexa"},
}

FIELD_LIMITS: Dict[str, int] = {
    "empleador_tipo_documento": 3,
    "empleador_numero_documento_nit": 20,
    "empleador_razon_social": 200,
    "rep_legal_tipo_documento": 3,
    "rep_legal_numero_documento": 15,
    "rep_legal_nombre_completo": 80,
    "sede_principal_codigo": 10,
    "sede_principal_nombre": 80,
    "sede_principal_direccion": 80,
    "sede_principal_telefono": 10,
    "sede_principal_correo": 80,
    "sede_principal_departamento": 2,
    "sede_principal_municipio_distrito": 3,
    "a_codigo_actividad_economica_principal": 10,
    "b_codigo_actividad_economica_principal": 10,
    "a_clase_riesgo": 3,
    "b_clase_riesgo": 3,
    "empresa_forma_pago": 3,
    "empresa_tipo_aportante": 3,
    "empresa_vinculador_laboral": 3,
    "empresa_regimen": 3,
    "empresa_naturaleza": 3,
    "empresa_clase_sociedad": 3,
    "empresa_tamano": 3,
    "empresa_grupo": 3,
    "empresa_tipo_localizacion": 3,
    "empresa_zona_localizacion": 3,
    "empresa_pyme": 1,
    "empresa_olcsa": 1,
    "empresa_contratante": 1,
    "empresa_arl_anterior": 50,
}

WORKER_FIELD_LIMITS: Dict[str, int] = {
    "tipo_documento": 3,
    "tipo_de_documento": 3,
    "documento": 15,
    "numero_documento": 15,
    "num_id_trabajador": 15,
    "numero_de_identificacion": 15,
    "primer_apellido": 80,
    "segundo_apellido": 80,
    "primer_nombre": 80,
    "segundo_nombre": 80,
    "eps": 30,
    "nombre_eps": 30,
    "afp": 30,
    "pension": 30,
    "nombre_afp": 30,
    "cargo": 150,
    "actividad": 150,
    "ocupacion": 150,
    "tipo_cotizante": 3,
    "subtipo_cotizante": 3,
    "codigo_centro_trabajo": 10,
    "codigo_del_centro_de_trabajo": 10,
    "sede_fax": 10,
    "sede_transporte": 1,
    "sede_grado": 3,
    "sede_tarifa": 10,
    "sede_tipo_localizacion": 3,
    "sede_contacto": 80,
    "sede_cargo_contacto": 80,
}

ALLOWED_NOVEDAD_CODES = {"00", "08"}
ALLOWED_TIPO_COTIZANTE = {"1", "19"}
DEFAULT_SUBTIPO_COTIZANTE = "999"
ALLOWED_BOOLEAN_SN = {"S", "N"}
ALLOWED_ZONA = {"U", "R"}
ALLOWED_NOVEDAD_ESTADO = {"1"}
ALLOWED_NOVEDAD_AUTOLIQUIDACION = {"N"}
ALLOWED_NOVEDAD_ORIGEN = {"C"}

DEPARTMENT_CODES: Dict[str, str] = {
    "AMAZONAS": "91",
    "ANTIOQUIA": "05",
    "ARAUCA": "81",
    "ATLANTICO": "08",
    "ATLÁNTICO": "08",
    "BOGOTA, D.C.": "11",
    "BOGOTÁ, D.C.": "11",
    "BOLIVAR": "13",
    "BOLÍVAR": "13",
    "BOYACA": "15",
    "BOYACÁ": "15",
    "CALDAS": "17",
    "CAQUETA": "18",
    "CAQUETÁ": "18",
    "CASANARE": "85",
    "CAUCA": "19",
    "CESAR": "20",
    "CHOCO": "27",
    "CHOCÓ": "27",
    "CORDOBA": "23",
    "CÓRDOBA": "23",
    "CUNDINAMARCA": "25",
    "GUAINIA": "94",
    "GUAINÍA": "94",
    "GUAVIARE": "95",
    "HUILA": "41",
    "LA GUAJIRA": "44",
    "MAGDALENA": "47",
    "META": "50",
    "NARINO": "52",
    "NARIÑO": "52",
    "NORTE DE SANTANDER": "54",
    "PUTUMAYO": "86",
    "QUINDIO": "63",
    "QUINDÍO": "63",
    "RISARALDA": "66",
    "SAN ANDRES": "88",
    "SAN ANDRÉS": "88",
    "SAN ANDRES Y PROVIDENCIA": "88",
    "SAN ANDRÉS Y PROVIDENCIA": "88",
    "SANTANDER": "68",
    "SUCRE": "70",
    "TOLIMA": "73",
    "VALLE DEL CAUCA": "76",
    "VAUPES": "97",
    "VAUPÉS": "97",
    "VICHADA": "99",
}

MUNICIPALITY_CODES: Dict[str, str] = {
    "ARAUCA": "001",
    "ARMENIA": "001",
    "BARRANQUILLA": "001",
    "BOGOTA": "001",
    "BOGOTA D.C.": "001",
    "BOGOTA, D.C.": "001",
    "BUCARAMANGA": "001",
    "CALI": "001",
    "CARTAGENA": "001",
    "CARTAGENA DE INDIAS": "001",
    "CUCUTA": "001",
    "FLORENCIA": "001",
    "IBAGUE": "001",
    "INIRIDA": "001",
    "LETICIA": "001",
    "MANIZALES": "001",
    "MEDELLIN": "001",
    "MITU": "001",
    "MOCOA": "001",
    "MONTERIA": "001",
    "NEIVA": "001",
    "PASTO": "001",
    "PEREIRA": "001",
    "POPAYAN": "001",
    "PUERTO CARRENO": "001",
    "PUERTO INIRIDA": "001",
    "QUIBDO": "001",
    "RIOHACHA": "001",
    "SAN ANDRES": "001",
    "SAN JOSE DEL GUAVIARE": "001",
    "SANTA MARTA": "001",
    "SINCELEJO": "001",
    "TUNJA": "001",
    "VALLEDUPAR": "001",
    "VILLAVICENCIO": "001",
    "YOPAL": "001",
}


def only_digits(value: Any) -> str:
    return re.sub(r"\D+", "", str(value or ""))


def calculate_nit_dv(nit: Any) -> str:
    digits = only_digits(nit)
    if not digits or len(digits) > len(DIGITO_MULTIPLIERS):
        return ""
    padded = digits.rjust(len(DIGITO_MULTIPLIERS), "0")
    total = sum(int(digit) * DIGITO_MULTIPLIERS[index] for index, digit in enumerate(padded))
    remainder = total % 11
    return str(11 - remainder if remainder > 1 else remainder)


def validate_nit_dv(nit: Any, dv: Any) -> bool:
    expected = calculate_nit_dv(nit)
    return bool(expected and only_digits(dv) == expected)


def normalize_legacy_token(value: Any) -> str:
    import unicodedata

    text = str(value or "").strip().upper()
    return "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))


def department_code(value: Any) -> str:
    digits = only_digits(value)
    if len(digits) == 2:
        return digits
    return DEPARTMENT_CODES.get(normalize_legacy_token(value), "")


def municipality_code(value: Any) -> str:
    digits = only_digits(value)
    if len(digits) == 3:
        return digits
    if len(digits) == 5:
        return digits[-3:]
    normalized = normalize_legacy_token(value)
    return MUNICIPALITY_CODES.get(normalized, "")
