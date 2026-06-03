from __future__ import annotations

import os
import re
import csv
import io
import json
import base64
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from sqlalchemy.exc import NoSuchTableError, SQLAlchemyError
try:
    from openpyxl import load_workbook
except Exception:  # pragma: no cover - fallback defensivo
    load_workbook = None

from app.core.db import (
    execute_by_alias,
    fetch_all_by_alias,
    get_table_columns_by_alias,
    list_alias_status,
    ping_alias,
)
from app.services.legacy_compat_engine import LegacyCompatEngine, as_text, compare_bytes
from app.services.afiliaciones_rules_engine import AfiliacionesRulesEngine
from app.services.ruta_inclusion_adjuntos_service import RutaInclusionAdjuntosService

router = APIRouter()

LEGACY_OPC_SOPORTADOS = {
    "traedevoluciones",
    "version",
    "python",
    "Tr",
    "tr_importar_lote",
    "tr_reprocesar_lote",
}
DEFAULT_VERSION = os.getenv("AFILIACIONES_VERSION", "1.0.0")
DEFAULT_PLANILLAS = [
    {
        "f01": "900123456",
        "f59": "001",
        "tp": "C",
        "afi_rad_clase": "NUEVO",
        "lote": "L-20260225-01",
    },
    {
        "f01": "901777222",
        "f59": "002",
        "tp": "I",
        "afi_rad_clase": "DEV",
        "lote": "L-20260225-01",
    },
]

TR_STAGE_ORDER = [
    "General-Recobrar",
    "General-Recobrar-2",
    "General-Recobrar-3",
    "General-Recobrar-4",
    "General-Recobrar-5",
    "General-Recobrar-6",
    "General-Recobrar-7",
]
TR_STAGE_TABLE = {
    "General-Recobrar": "wh",
    "General-Recobrar-2": "wd",
    "General-Recobrar-3": "wddias",
    "General-Recobrar-4": "wcentrot",
    "General-Recobrar-5": "wdestudiantes",
    "General-Recobrar-6": "wdindependientes",
    "General-Recobrar-7": "wdcomisiones",
}
TR_STAGE_DELIMITER = {"General-Recobrar-6": "!"}
TR_IMPORT_RUNS: dict[str, dict[str, Any]] = {}
FLATFILE_926_REPORTS: dict[str, dict[str, Any]] = {}
FLATFILE_926_HISTORY_DIR = Path(os.getenv("AFILIACIONES_926_HISTORY_DIR", "/tmp/afiliaciones_926_history"))
FLATFILE_926_HISTORY_INDEX = FLATFILE_926_HISTORY_DIR / "index.json"
ACTIVITY_ECONOMICA_ARP_PATH = Path(__file__).resolve().parents[2] / "data" / "actividad_economica_arp.json"
LEGACY_ENGINE = LegacyCompatEngine(
    Path(os.getenv("AFILIACIONES_ENGINE_STATE_PATH", "/tmp/afiliaciones_engine_state.json"))
)
RULES_ENGINE = AfiliacionesRulesEngine()
RUTA_ADJ_SERVICE = RutaInclusionAdjuntosService()
DEFAULT_ORACLE_FLATFILE = os.getenv(
    "AFILIACIONES_ORACLE_FLATFILE",
    "/data/raw/BkCargue_reference.txt",
)
SAFE_SQL_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
RUTA_IDTRAMITE_PYMES_RE = re.compile(r"^200\d{5}$")
_ACTIVITY_ECONOMICA_ARP_CACHE: Optional[dict[str, dict[str, Any]]] = None


def _activity_economica_arp_catalog() -> dict[str, dict[str, Any]]:
    global _ACTIVITY_ECONOMICA_ARP_CACHE
    if _ACTIVITY_ECONOMICA_ARP_CACHE is not None:
        return _ACTIVITY_ECONOMICA_ARP_CACHE
    catalog: dict[str, dict[str, Any]] = {}
    try:
        payload = json.loads(ACTIVITY_ECONOMICA_ARP_PATH.read_text(encoding="utf-8"))
    except Exception:
        payload = []
    for item in payload or []:
        if not isinstance(item, dict):
            continue
        code = "".join(ch for ch in as_text(item.get("codigo")) if ch.isdigit())
        if code:
            catalog[code] = item
    _ACTIVITY_ECONOMICA_ARP_CACHE = catalog
    return catalog


def _activity_risk_profile_arp(codigoactividad: Any) -> dict[str, str]:
    code = "".join(ch for ch in as_text(codigoactividad) if ch.isdigit())
    row = _activity_economica_arp_catalog().get(code) or {}
    return {
        "codigo": code,
        "nombre": as_text(row.get("nombre")).strip(),
        "clase": as_text(row.get("clase") or row.get("claries")).strip(),
        "grado": as_text(row.get("grado")).strip(),
        "tasa": as_text(row.get("tasa")).replace(",", ".").strip(),
    }


def _format_tasa_arp(value: Any) -> str:
    raw = as_text(value).replace(",", ".").strip()
    if raw in {"", "0", "0.0", "0.00", "0.000", "0.0000", "00000"}:
        return ""
    try:
        raw = f"{float(raw):.3f}"
    except Exception:
        pass
    return raw[:5].ljust(5, "0")

LOTE_FIELD_BY_TABLE = {
    "brempresasarp": "lt",
    "brafiliadosarp": "lt",
    "brwddias": "lote",
    "brcentrot": "lote",
    "brwdestudiantes": "lote",
    "brwdindependientes": "lote",
    "brwdcomisiones": "lote",
    "bkempresasarp": "lt",
    "bkafiliadosarp": "lt",
    "bkwddias": "lote",
    "bkcentrot": "lote",
    "bkwdestudiantes": "lote",
    "bkwdindependientes": "lote",
    "bkwdcomisiones": "lote",
    "devempresasarp": "lt",
    "devafiliadosarp": "lt",
    "devwddias": "lote",
    "devcentrot": "lote",
    "devwdestudiantes": "lote",
    "devwdindependientes": "lote",
    "devwdcomisiones": "lote",
    "tr": "nl",
    "lc": "fileid",
}
REAL_LOTE_TABLES = [
    "brempresasarp",
    "brafiliadosarp",
    "brwddias",
    "brcentrot",
    "brwdestudiantes",
    "brwdindependientes",
    "brwdcomisiones",
]


def _normalize_opc(payload: dict[str, Any]) -> str:
    opc = str(payload.get("opc") or payload.get("sw") or "").strip()
    if not opc:
        raise HTTPException(status_code=400, detail="Campo requerido: opc o sw")
    return opc


def _stringify_payload(payload: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in payload.items():
        if value is None:
            continue
        out[str(key)] = str(value)
    return out


def _validate_926_structure(content: str) -> dict[str, Any]:
    # Perfil de salida real del clon/legacy observado:
    # tipos 1/2/3/5/7 a 942, tipo 4 corto (comisiones), tipo 6 marcas día.
    expected_lengths_by_type = {
        "1": {942},
        "2": {942},
        "3": {942},
        "4": {28},
        "5": {942},
        "6": {26},
        "7": {942},
    }
    lines = content.splitlines()
    bad_len_internal = []
    bad_len_final = []  # compatibilidad de contrato de respuesta
    unknown_types = []
    non_ascii = []
    for i, line in enumerate(lines, start=1):
        if not line:
            bad_len_final.append({"line": i, "expected": "non-empty", "got": 0})
            continue
        t = line[:1]
        allowed = expected_lengths_by_type.get(t)
        if allowed is None:
            unknown_types.append({"line": i, "type": t})
            continue
        if len(line) not in allowed:
            bad_len_internal.append(
                {
                    "line": i,
                    "type": t,
                    "expected_any_of": sorted(list(allowed)),
                    "got": len(line),
                }
            )
        for j, ch in enumerate(line, start=1):
            code = ord(ch)
            if code < 32 or code > 126:
                non_ascii.append({"line": i, "col": j, "char_code": code})
                break
    semantic = _validate_926_type2_semantics(lines)
    return {
        "ok": (
            len(lines) > 0
            and len(bad_len_internal) == 0
            and len(bad_len_final) == 0
            and len(unknown_types) == 0
            and len(non_ascii) == 0
            and semantic.get("ok", True)
        ),
        "line_count": len(lines),
        "bad_length_internal_count": len(bad_len_internal),
        "bad_length_final926_count": len(bad_len_final),
        "unknown_type_count": len(unknown_types),
        "non_ascii_count": len(non_ascii),
        "semantic_type2_ok": semantic.get("ok", True),
        "semantic_type2_error_count": semantic.get("error_count", 0),
        "semantic_type2_warning_count": semantic.get("warning_count", 0),
        "semantic_type2_errors_preview": semantic.get("errors", [])[:20],
        "semantic_type2_warnings_preview": semantic.get("warnings", [])[:20],
        "bad_lengths_internal_preview": bad_len_internal[:20],
        "bad_lengths_final926_preview": bad_len_final[:20],
        "unknown_types_preview": unknown_types[:20],
        "non_ascii_preview": non_ascii[:20],
    }


def _validate_926_type2_semantics(lines: list[str]) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    zero_tokens = {"", "0", "0.0", "0.00", "0.000", "0.0000", "00000", "0000", "000"}
    expected_by_clase = {
        "1": "0.522",
        "2": "1.044",
        "3": "2.436",
        "4": "4.350",
        "5": "6.960",
    }

    def _norm_rate(v: str) -> str:
        txt = as_text(v).replace(",", ".").strip()
        if txt in zero_tokens:
            return ""
        if "." in txt:
            left, right = txt.split(".", 1)
            left = "".join(ch for ch in left if ch.isdigit()) or "0"
            right = "".join(ch for ch in right if ch.isdigit())
            right = (right + "000")[:3]
            return f"{left}.{right}"
        digits = "".join(ch for ch in txt if ch.isdigit())
        if digits == "":
            return ""
        if len(digits) <= 3:
            return f"0.{digits.rjust(3, '0')}"
        return f"{digits[:-3]}.{digits[-3:]}"

    for i, line in enumerate(lines, start=1):
        if line[:1] != "2":
            continue
        codigoct = as_text(line[1:7]).strip()
        codigoactividad = as_text(line[98:105]).strip()
        claseriesgo = as_text(line[105:106]).strip()
        tasa = as_text(line[109:114]).strip()

        if tasa in zero_tokens:
            errors.append(
                {
                    "line": i,
                    "code": "tipo2_tarifa_cero",
                    "codigoct": codigoct,
                    "codigoactividad": codigoactividad,
                    "detail": "La tarifa/tasa del tipo 2 está en cero o vacía.",
                }
            )
            continue

        tasa_norm = _norm_rate(tasa)
        if not tasa_norm:
            errors.append(
                {
                    "line": i,
                    "code": "tipo2_tarifa_invalida",
                    "codigoct": codigoct,
                    "codigoactividad": codigoactividad,
                    "detail": f"Formato de tarifa/tasa inválido ({tasa}).",
                }
            )
            continue

        expected = expected_by_clase.get(claseriesgo)
        if expected and tasa_norm != expected:
            warnings.append(
                {
                    "line": i,
                    "code": "tipo2_tarifa_vs_clase",
                    "codigoct": codigoct,
                    "codigoactividad": codigoactividad,
                    "claseriesgo": claseriesgo,
                    "tasa": tasa,
                    "expected": expected,
                    "detail": "La tarifa/tasa no coincide con la tabla estándar de clase de riesgo.",
                }
            )

    return {
        "ok": len(errors) == 0,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
    }


def _txt_norm(v: Any) -> str:
    return as_text(v).strip()


def _has_value(v: Any) -> bool:
    return _txt_norm(v) not in ("", "0", "00000", "000000", "0000000", "00000000")


def _operational_precheck_926(lote: str = "") -> dict[str, Any]:
    wh_rows = _rows_in_lote("wh", lote=lote)
    ct_rows = _rows_in_lote("wcentrot", lote=lote)
    wd_rows = _rows_in_lote("wd", lote=lote)
    wdest_rows = _rows_in_lote("wdestudiantes", lote=lote)
    wdind_rows = _rows_in_lote("wdindependientes", lote=lote)

    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    def _norm_ct_code(v: Any) -> str:
        txt = _txt_norm(v)
        if txt == "":
            return ""
        digits = "".join(ch for ch in txt if ch.isdigit())
        if digits != "":
            try:
                return str(int(digits))
            except Exception:
                return digits.lstrip("0") or "0"
        return txt.upper()

    for r in wh_rows:
        sr = _txt_norm(r.get("sr"))
        tp = _txt_norm(r.get("tp")).upper()
        if not _has_value(r.get("f48")):
            errors.append({"type": "critical_field_missing", "sr": sr, "field": "nit_empleador", "value": as_text(r.get("f48"))})
        if not _has_value(r.get("f51")):
            errors.append({"type": "critical_field_missing", "sr": sr, "field": "razon_social", "value": as_text(r.get("f51"))})
        if not _has_value(r.get("f12")):
            errors.append({"type": "critical_field_missing", "sr": sr, "field": "direccion_empleador", "value": as_text(r.get("f12"))})
        city_ok = _has_value(r.get("f15")) or _has_value(r.get("f57"))
        if not city_ok:
            if tp == "P":
                errors.append({"type": "critical_field_missing", "sr": sr, "field": "ciudad_empleador", "value": as_text(r.get("f15"))})
            else:
                warnings.append({"type": "critical_field_missing", "sr": sr, "field": "ciudad_sede", "value": as_text(r.get("f15"))})
        rep_doc_ok = _has_value(r.get("f67")) or _has_value(r.get("f49"))
        rep_name_ok = _has_value(r.get("f06")) or _has_value(r.get("f69")) or _has_value(r.get("f70"))
        if not rep_doc_ok:
            warnings.append({"type": "critical_field_missing", "sr": sr, "field": "doc_representante", "value": as_text(r.get("f67"))})
        if not rep_name_ok:
            warnings.append({"type": "critical_field_missing", "sr": sr, "field": "nombre_representante", "value": ""})

    worker_keys: set[tuple[str, str]] = set()
    for w in wd_rows:
        if _has_value(w.get("f28")):
            worker_keys.add((_txt_norm(w.get("sr")), _norm_ct_code(w.get("f30"))))
    for w in wdest_rows:
        if _has_value(w.get("documento")):
            worker_keys.add((_txt_norm(w.get("sr")), _norm_ct_code(w.get("codigo_ct"))))
    for w in wdind_rows:
        if _has_value(w.get("documento")):
            worker_keys.add((_txt_norm(w.get("sr")), _norm_ct_code(w.get("codigo_ct"))))

    for ct in ct_rows:
        sr = _txt_norm(ct.get("sr"))
        code = _norm_ct_code(ct.get("codigoct"))
        if not code:
            warnings.append({"type": "centro_sin_codigo", "sr": sr})
            continue
        if (sr, code) not in worker_keys:
            errors.append({"type": "centro_sin_trabajadores", "sr": sr, "codigoct": code})

    # Regla de negocio legacy: por cada sede (tp=S) debe existir al menos un centro
    # y cada centro debe tener al menos un trabajador (regla validada arriba).
    centers_by_sr: dict[str, int] = {}
    for ct in ct_rows:
        sr = _txt_norm(ct.get("sr"))
        code = _txt_norm(ct.get("codigoct"))
        if not sr or not code:
            continue
        centers_by_sr[sr] = centers_by_sr.get(sr, 0) + 1
    for r in wh_rows:
        if _txt_norm(r.get("tp")).upper() != "S":
            continue
        sr = _txt_norm(r.get("sr"))
        if centers_by_sr.get(sr, 0) <= 0:
            errors.append({"type": "sede_sin_centros", "sr": sr})

    return {
        "ok": len(errors) == 0,
        "lote": lote,
        "errors": errors,
        "warnings": warnings,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "counts": {
            "wh": len(wh_rows),
            "wcentrot": len(ct_rows),
            "wd": len(wd_rows),
            "wdestudiantes": len(wdest_rows),
            "wdindependientes": len(wdind_rows),
        },
    }


def _line_type_counts(content: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for ln in content.splitlines():
        t = (ln[:1] or "?")
        out[t] = out.get(t, 0) + 1
    return out


def _store_flatfile_926_report(report: dict[str, Any]) -> str:
    report_id = str(uuid4())
    FLATFILE_926_REPORTS[report_id] = report
    if len(FLATFILE_926_REPORTS) > 200:
        old_key = next(iter(FLATFILE_926_REPORTS))
        FLATFILE_926_REPORTS.pop(old_key, None)
    return report_id


def _ensure_926_history_store() -> None:
    FLATFILE_926_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    if not FLATFILE_926_HISTORY_INDEX.exists():
        FLATFILE_926_HISTORY_INDEX.write_text("[]", encoding="utf-8")


def _load_926_history_index() -> list[dict[str, Any]]:
    _ensure_926_history_store()
    try:
        raw = FLATFILE_926_HISTORY_INDEX.read_text(encoding="utf-8")
        data = json.loads(raw)
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
    except Exception:
        pass
    return []


def _save_926_history_index(rows: list[dict[str, Any]]) -> None:
    _ensure_926_history_store()
    FLATFILE_926_HISTORY_INDEX.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _sanitize_filename_part(value: str) -> str:
    txt = re.sub(r"[^A-Za-z0-9._-]+", "_", as_text(value).strip())
    return txt.strip("._-") or "NA"


def _empresa_nit_from_wh_lote(lote: str) -> tuple[str, str]:
    wh_rows = _rows_in_lote("wh", lote=lote)
    p_rows = [r for r in wh_rows if _txt_norm(r.get("tp")).upper() == "P"]
    row = p_rows[0] if p_rows else (wh_rows[0] if wh_rows else {})
    empresa = as_text(row.get("f51")).strip()
    nit = as_text(row.get("f48")).strip()
    return empresa, nit


def _persist_926_history_entry(
    *,
    lote: str,
    base: str,
    report_id: str,
    content: bytes,
    fallback_filename: str,
) -> dict[str, Any]:
    _ensure_926_history_store()
    empresa, nit = _empresa_nit_from_wh_lote(lote)
    ts = datetime.now()
    stamp = ts.strftime("%Y%m%d_%H%M%S")
    item_id = str(uuid4())
    empresa_tag = _sanitize_filename_part(empresa)[:60]
    nit_tag = _sanitize_filename_part(nit)[:20]
    lote_tag = _sanitize_filename_part(lote)[:20]
    filename = f"{stamp}_{lote_tag}_{nit_tag}_{empresa_tag}.txt"
    if filename.strip("._") == "":
        filename = fallback_filename
    out_path = FLATFILE_926_HISTORY_DIR / filename
    out_path.write_bytes(content)
    entry = {
        "id": item_id,
        "created_at": ts.isoformat(),
        "lote": lote,
        "base": base,
        "report_id": report_id,
        "empresa": empresa,
        "nit": nit,
        "filename": filename,
        "path": str(out_path),
        "size_bytes": len(content),
    }
    idx = _load_926_history_index()
    idx.append(entry)
    # Mantener un histórico operativo acotado para no crecer sin control.
    idx = idx[-500:]
    _save_926_history_index(idx)
    return entry


def _rows_in_lote(table: str, lote: str) -> list[dict[str, Any]]:
    rows = LEGACY_ENGINE._rows(table)
    if not lote:
        return rows

    def in_lote(row: dict[str, Any]) -> bool:
        lt = as_text(row.get("lt")).strip()
        lo = as_text(row.get("lote")).strip()
        if lt == "" and lo == "":
            return True
        return lt == lote or lo == lote

    return [r for r in rows if in_lote(r)]


def _prebuild_rules_check(lote: str = "") -> dict[str, Any]:
    wh_rows = _rows_in_lote("wh", lote=lote)
    wd_rows = _rows_in_lote("wd", lote=lote)
    wdind_rows = _rows_in_lote("wdindependientes", lote=lote)
    return RULES_ENGINE.validate_prebuild_state(
        wh_rows=wh_rows,
        wd_rows=wd_rows,
        wdind_rows=wdind_rows,
        lote=lote,
    )


def _sede_salary_totals_from_engine(lote: str = "") -> dict[str, int]:
    wh_rows = _rows_in_lote("wh", lote=lote)
    wd_rows = _rows_in_lote("wd", lote=lote)
    wdest_rows = _rows_in_lote("wdestudiantes", lote=lote)
    wdind_rows = _rows_in_lote("wdindependientes", lote=lote)
    # En práctica legacy/clone, la relación de conciliación por sede debe seguir el
    # SR de la sede en WH (2..N), no el código textual f62, que puede llegar repetido.
    sr_to_sede: dict[str, str] = {}
    sede_rows = [r for r in wh_rows if _txt_norm(r.get("tp")).upper() == "S"]
    sede_rows_sorted = sorted(
        sede_rows,
        key=lambda r: _to_int_safe(_txt_norm(r.get("sr")), default=0),
    )
    for idx, row in enumerate(sede_rows_sorted, start=1):
        sr = _txt_norm(row.get("sr"))
        if sr:
            sr_to_sede[sr] = str(idx)

    totals: dict[str, int] = {}
    for row in wd_rows:
        doc = _txt_norm(row.get("f28"))
        if not doc or doc == "0":
            continue
        sr = _txt_norm(row.get("sr"))
        sede_code = sr_to_sede.get(sr, sr or "")
        if not sede_code:
            continue
        salary = _to_int_safe(row.get("f38"), default=0)
        totals[sede_code] = totals.get(sede_code, 0) + salary
    for row in wdest_rows:
        doc = _txt_norm(row.get("documento"))
        if not doc or doc == "0":
            continue
        sr = _txt_norm(row.get("sr"))
        sede_code = sr_to_sede.get(sr, sr or "")
        if not sede_code:
            continue
        salary = _to_int_safe(row.get("salario"), default=0)
        totals[sede_code] = totals.get(sede_code, 0) + salary
    for row in wdind_rows:
        doc = _txt_norm(row.get("documento"))
        if not doc or doc == "0":
            continue
        sr = _txt_norm(row.get("sr"))
        sede_code = sr_to_sede.get(sr, sr or "")
        if not sede_code:
            continue
        salary = _to_int_safe(row.get("ibc"), default=0)
        totals[sede_code] = totals.get(sede_code, 0) + salary
    return totals


def _sede_salary_totals_from_xlsx(excel_bytes: bytes) -> dict[str, Any]:
    if load_workbook is None:
        return {
            "ok": False,
            "error": "openpyxl no está disponible en backend.",
            "totals": {},
            "details": [],
        }
    try:
        wb = load_workbook(io.BytesIO(excel_bytes), data_only=False, read_only=True)
    except Exception as exc:
        return {
            "ok": False,
            "error": f"No fue posible leer el Excel: {type(exc).__name__}: {exc}",
            "totals": {},
            "details": [],
        }

    totals: dict[str, int] = {}
    details: list[dict[str, Any]] = []
    sede_pat = re.compile(r"sede\s*0*(\d+)", re.IGNORECASE)
    sum_pat = re.compile(r"SUM\(\s*S(\d+)\s*:\s*S(\d+)\s*\)", re.IGNORECASE)
    docs = {"CC", "CE", "TI", "RC", "PA", "PT", "SC", "CD", "NI"}

    def _fallback_total_by_rows(ws: Any) -> tuple[int, int]:
        total = 0
        workers = 0
        max_scan = int(ws.max_row or 0)
        for rr in range(1, max_scan + 1):
            doc_type = as_text(ws.cell(rr, 6).value).strip().upper()
            if doc_type not in docs:
                continue
            doc = re.sub(r"\D+", "", as_text(ws.cell(rr, 7).value))
            if not re.fullmatch(r"\d{6,15}", doc):
                continue
            salario_txt, _ = _parse_money_text(ws.cell(rr, 19).value)
            salario = _to_int_safe(salario_txt, default=0)
            total += salario
            workers += 1
        return total, workers

    for ws in wb.worksheets:
        name = as_text(ws.title)
        low = name.lower()
        if "sede" not in low or "trabajadores" not in low:
            continue
        m = sede_pat.search(name)
        if not m:
            continue
        sede_code = str(int(m.group(1)))

        total_label_row: Optional[int] = None
        max_scan_rows = min(int(ws.max_row or 0), 400)
        for r in range(1, max_scan_rows + 1):
            v = ws.cell(r, 19).value  # Columna S
            if isinstance(v, str) and "total salarios" in v.lower():
                total_label_row = r
                break
        if total_label_row is None:
            fb_total, fb_workers = _fallback_total_by_rows(ws)
            if fb_workers > 0:
                totals[sede_code] = fb_total
                details.append(
                    {
                        "sede": sede_code,
                        "sheet": name,
                        "ok": True,
                        "reason": "fallback_rows_doc_salary",
                        "workers_detected": fb_workers,
                        "total_salarios": fb_total,
                    }
                )
                continue
            details.append(
                {
                    "sede": sede_code,
                    "sheet": name,
                    "ok": False,
                    "reason": "total_salarios_no_encontrado",
                }
            )
            continue

        formula = ws.cell(total_label_row + 1, 19).value
        r0 = r1 = None
        if isinstance(formula, str):
            fm = sum_pat.search(formula.replace("$", ""))
            if fm:
                r0, r1 = int(fm.group(1)), int(fm.group(2))
        if r0 is None or r1 is None:
            fb_total, fb_workers = _fallback_total_by_rows(ws)
            if fb_workers > 0:
                totals[sede_code] = fb_total
                details.append(
                    {
                        "sede": sede_code,
                        "sheet": name,
                        "ok": True,
                        "reason": "fallback_rows_doc_salary",
                        "workers_detected": fb_workers,
                        "total_salarios": fb_total,
                    }
                )
                continue
            details.append(
                {
                    "sede": sede_code,
                    "sheet": name,
                    "ok": False,
                    "reason": "formula_total_salarios_no_detectada",
                }
            )
            continue

        total_float = 0.0
        numeric_rows = 0
        for rr in range(r0, r1 + 1):
            raw = ws.cell(rr, 19).value
            if raw in (None, ""):
                continue
            if isinstance(raw, (int, float)):
                total_float += float(raw)
                numeric_rows += 1
                continue
            parsed, _ = _parse_money_text(raw)
            if parsed != "0":
                total_float += float(int(parsed))
                numeric_rows += 1
        total = int(round(total_float))

        totals[sede_code] = total
        details.append(
            {
                "sede": sede_code,
                "sheet": name,
                "ok": True,
                "range": f"S{r0}:S{r1}",
                "rows_numeric": numeric_rows,
                "total_salarios": total,
            }
        )

    return {"ok": True, "totals": totals, "details": details}


def _prebuild_xlsx_sede_salary_check(lote: str, excel_bytes: bytes) -> dict[str, Any]:
    xlsx = _sede_salary_totals_from_xlsx(excel_bytes)
    if not xlsx.get("ok", False):
        return {
            "ok": False,
            "lote": lote,
            "error": xlsx.get("error", "No fue posible procesar Excel de contrato."),
            "rows": [],
            "error_count": 1,
        }
    imported_totals = _sede_salary_totals_from_engine(lote=lote)
    excel_totals: dict[str, int] = xlsx.get("totals", {})
    all_codes = sorted(set(excel_totals.keys()) | set(imported_totals.keys()), key=lambda x: int(x) if x.isdigit() else 999999)

    rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for code in all_codes:
        total_excel = int(excel_totals.get(code, 0))
        total_importado = int(imported_totals.get(code, 0))
        diff = total_importado - total_excel
        ok = diff == 0
        row = {
            "sede": code,
            "total_excel": total_excel,
            "total_importado": total_importado,
            "diferencia": diff,
            "estado": "OK" if ok else "ERROR",
        }
        rows.append(row)
        if not ok:
            errors.append(
                {
                    "type": "total_salario_sede_mismatch",
                    "sede": code,
                    "total_excel": total_excel,
                    "total_importado": total_importado,
                    "diferencia": diff,
                }
            )

    return {
        "ok": len(errors) == 0,
        "lote": lote,
        "rows": rows,
        "errors": errors,
        "error_count": len(errors),
        "xlsx_details": xlsx.get("details", []),
        "totals": {
            "excel": sum(excel_totals.values()),
            "importado": sum(imported_totals.values()),
            "diferencia": sum(imported_totals.values()) - sum(excel_totals.values()),
        },
    }


def _prebuild_expected_sede_salary_check(
    *,
    lote: str,
    expected_totals: dict[str, int],
    expected_details: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    imported_totals = _sede_salary_totals_from_engine(lote=lote)
    all_codes = sorted(
        set(expected_totals.keys()) | set(imported_totals.keys()),
        key=lambda x: int(x) if x.isdigit() else 999999,
    )

    rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for code in all_codes:
        total_excel = int(expected_totals.get(code, 0))
        total_importado = int(imported_totals.get(code, 0))
        diff = total_importado - total_excel
        ok = diff == 0
        row = {
            "sede": code,
            "total_excel": total_excel,
            "total_importado": total_importado,
            "diferencia": diff,
            "estado": "OK" if ok else "ERROR",
        }
        rows.append(row)
        if not ok:
            errors.append(
                {
                    "type": "total_salario_sede_mismatch",
                    "sede": code,
                    "total_excel": total_excel,
                    "total_importado": total_importado,
                    "diferencia": diff,
                }
            )

    return {
        "ok": len(errors) == 0,
        "lote": lote,
        "rows": rows,
        "errors": errors,
        "error_count": len(errors),
        "xlsx_details": list(expected_details or []),
        "totals": {
            "excel": sum(expected_totals.values()),
            "importado": sum(imported_totals.values()),
            "diferencia": sum(imported_totals.values()) - sum(expected_totals.values()),
        },
        "source": "expected_sede_totals",
    }


def _excel_contract_executive_summary(excel_bytes: bytes) -> dict[str, Any]:
    if load_workbook is None:
        return {"ok": False, "error": "openpyxl no está disponible en backend."}
    try:
        wb = load_workbook(io.BytesIO(excel_bytes), data_only=True, read_only=True)
    except Exception as exc:
        return {"ok": False, "error": f"No fue posible leer el Excel: {type(exc).__name__}: {exc}"}

    docs = {"CC", "CE", "TI", "RC", "PA", "PT", "SC", "CD", "NI"}
    worker_sheets = [sh for sh in wb.sheetnames if ("sede" in sh.lower() and "trabajador" in sh.lower())]
    if not worker_sheets:
        return {
            "ok": False,
            "error": "No se detectaron hojas de sedes de trabajadores en el Excel.",
            "worker_sheets": [],
        }

    total_workers = 0
    total_salary = 0
    center_codes: set[str] = set()
    by_sede: list[dict[str, Any]] = []

    for sh in worker_sheets:
        ws = wb[sh]
        sede_workers = 0
        sede_salary = 0
        sede_centers: set[str] = set()
        max_scan = int(ws.max_row or 0)
        for rr in range(1, max_scan + 1):
            doc_type = as_text(ws.cell(rr, 6).value).strip().upper()
            if doc_type not in docs:
                continue
            doc = re.sub(r"\D+", "", as_text(ws.cell(rr, 7).value))
            if not re.fullmatch(r"\d{6,15}", doc):
                continue
            sede_workers += 1
            salario_txt, _ = _parse_money_text(ws.cell(rr, 19).value)
            salario = _to_int_safe(salario_txt, default=0)
            sede_salary += salario
            ct = re.sub(r"\D+", "", as_text(ws.cell(rr, 5).value))
            if ct:
                norm_ct = str(int(ct)) if ct.isdigit() else ct
                sede_centers.add(norm_ct)
                center_codes.add(norm_ct)
        by_sede.append(
            {
                "sheet": sh,
                "workers": sede_workers,
                "salary_total": sede_salary,
                "center_count": len(sede_centers),
            }
        )
        total_workers += sede_workers
        total_salary += sede_salary

    sedes_con_trabajadores = sum(1 for s in by_sede if int(s.get("workers", 0)) > 0)

    return {
        "ok": True,
        "worker_sheets": worker_sheets,
        "empresa": {"razon_social": "", "nit": ""},
        "totals": {
            "empleados": total_workers,
            # Regla operativa: para conciliación final solo cuentan sedes con afiliados.
            "sedes": int(sedes_con_trabajadores),
            "sedes_detectadas": len(worker_sheets),
            "centros_costo": len(center_codes),
            "salarios": total_salary,
        },
        "by_sede": by_sede,
    }


def _contract_executive_report(
    *,
    lote: str,
    from_db: bool = False,
    base: str = "temporal",
    excel_bytes: Optional[bytes] = None,
    flatfile_926_content: str = "",
    generate_926_if_missing: bool = True,
) -> dict[str, Any]:
    sync_info: Optional[dict[str, Any]] = None
    if from_db and lote:
        sync_info = _sync_engine_from_db(lote=lote, base=base)

    wh_rows = _rows_in_lote("wh", lote=lote)
    wd_rows = _rows_in_lote("wd", lote=lote)
    wdest_rows = _rows_in_lote("wdestudiantes", lote=lote)
    wdind_rows = _rows_in_lote("wdindependientes", lote=lote)
    wct_rows = _rows_in_lote("wcentrot", lote=lote)

    p_rows = [r for r in wh_rows if _txt_norm(r.get("tp")).upper() == "P"]
    empresa_row = (p_rows[0] if p_rows else (wh_rows[0] if wh_rows else {}))
    razon_social = as_text(empresa_row.get("f51")).strip()
    nit = as_text(empresa_row.get("f48")).strip()

    docs_wd = sum(1 for r in wd_rows if _has_value(r.get("f28")))
    docs_est = sum(1 for r in wdest_rows if _has_value(r.get("documento")))
    docs_ind = sum(1 for r in wdind_rows if _has_value(r.get("documento")))
    empleados_total = docs_wd + docs_est + docs_ind
    salarios_total = 0
    for r in wd_rows:
        if not _has_value(r.get("f28")):
            continue
        s_txt, _ = _parse_money_text(r.get("f38"))
        salarios_total += _to_int_safe(s_txt, default=0)
    for r in wdest_rows:
        if not _has_value(r.get("documento")):
            continue
        s_txt, _ = _parse_money_text(r.get("salario"))
        salarios_total += _to_int_safe(s_txt, default=0)
    for r in wdind_rows:
        if not _has_value(r.get("documento")):
            continue
        s_txt, _ = _parse_money_text(r.get("ibc"))
        salarios_total += _to_int_safe(s_txt, default=0)

    sedes_codes: set[str] = set()
    for r in wh_rows:
        if _txt_norm(r.get("tp")).upper() != "S":
            continue
        code = re.sub(r"\D+", "", _txt_norm(r.get("f62")))
        if code:
            sedes_codes.add(str(int(code)))
    centros_codes: set[str] = set()
    for r in wct_rows:
        code = re.sub(r"\D+", "", _txt_norm(r.get("codigoct")))
        if code:
            centros_codes.add(str(int(code)))
    for r in wd_rows:
        if not _has_value(r.get("f28")):
            continue
        code = re.sub(r"\D+", "", _txt_norm(r.get("f30")))
        if code:
            centros_codes.add(str(int(code)))
    for r in wdest_rows:
        if not _has_value(r.get("documento")):
            continue
        code = re.sub(r"\D+", "", _txt_norm(r.get("codigo_ct")))
        if code:
            centros_codes.add(str(int(code)))
    for r in wdind_rows:
        if not _has_value(r.get("documento")):
            continue
        code = re.sub(r"\D+", "", _txt_norm(r.get("codigo_ct")))
        if code:
            centros_codes.add(str(int(code)))

    engine_totals = {
        "empleados": int(empleados_total),
        "sedes": int(len(sedes_codes)),
        "centros_costo": int(len(centros_codes)),
        "salarios": int(salarios_total),
    }

    # Desglose operativo por sede (para reporte ejecutivo de negocio).
    def _norm_code(v: Any) -> str:
        d = re.sub(r"\D+", "", _txt_norm(v))
        return str(int(d)) if d else ""

    sede_rows = [r for r in wh_rows if _txt_norm(r.get("tp")).upper() == "S"]
    ct_codes_by_sr: dict[str, set[str]] = {}
    ct_sr_by_code: dict[str, str] = {}
    for ct in wct_rows:
        sr = _txt_norm(ct.get("sr"))
        code = _norm_code(ct.get("codigoct"))
        if not sr or not code:
            continue
        ct_codes_by_sr.setdefault(sr, set()).add(code)
        ct_sr_by_code[code] = sr

    sede_breakdown_map: dict[str, dict[str, Any]] = {}
    for s in sede_rows:
        sr = _txt_norm(s.get("sr"))
        sede_code = _norm_code(s.get("f62")) or _norm_code(sr) or sr
        sede_breakdown_map[sr] = {
            "sr": sr,
            "sede": sede_code or "-",
            "nombre_sede": _txt_norm(s.get("f71")) or _txt_norm(s.get("f51")) or f"SEDE {sede_code or sr}",
            "direccion": _txt_norm(s.get("f12")),
            "ciudad": _norm_code(s.get("f57")) or _norm_code(s.get("f15")) or _txt_norm(s.get("f15")),
            "centros_codigos": sorted(list(ct_codes_by_sr.get(sr, set())), key=lambda x: int(x) if x.isdigit() else x),
            "centros_costo": 0,
            "empleados_dependientes": 0,
            "empleados_estudiantes": 0,
            "empleados_independientes": 0,
            "empleados_total": 0,
            "valor_nomina_sede": 0,
        }

    def _ensure_sede_by_worker(sr: str, ct_code: str) -> Optional[dict[str, Any]]:
        if sr and sr in sede_breakdown_map:
            return sede_breakdown_map[sr]
        if ct_code and ct_code in ct_sr_by_code and ct_sr_by_code[ct_code] in sede_breakdown_map:
            return sede_breakdown_map[ct_sr_by_code[ct_code]]
        return None

    for wd in wd_rows:
        if not _has_value(wd.get("f28")):
            continue
        sr = _txt_norm(wd.get("sr"))
        ct_code = _norm_code(wd.get("f30"))
        sede_ref = _ensure_sede_by_worker(sr, ct_code)
        if not sede_ref:
            continue
        s_txt, _ = _parse_money_text(wd.get("f38"))
        sede_ref["empleados_dependientes"] += 1
        sede_ref["empleados_total"] += 1
        sede_ref["valor_nomina_sede"] += _to_int_safe(s_txt, default=0)
        if ct_code and ct_code not in sede_ref["centros_codigos"]:
            sede_ref["centros_codigos"].append(ct_code)

    for ws in wdest_rows:
        if not _has_value(ws.get("documento")):
            continue
        sr = _txt_norm(ws.get("sr"))
        ct_code = _norm_code(ws.get("codigo_ct"))
        sede_ref = _ensure_sede_by_worker(sr, ct_code)
        if not sede_ref:
            continue
        s_txt, _ = _parse_money_text(ws.get("salario"))
        sede_ref["empleados_estudiantes"] += 1
        sede_ref["empleados_total"] += 1
        sede_ref["valor_nomina_sede"] += _to_int_safe(s_txt, default=0)
        if ct_code and ct_code not in sede_ref["centros_codigos"]:
            sede_ref["centros_codigos"].append(ct_code)

    for wi in wdind_rows:
        if not _has_value(wi.get("documento")):
            continue
        sr = _txt_norm(wi.get("sr"))
        ct_code = _norm_code(wi.get("codigo_ct"))
        sede_ref = _ensure_sede_by_worker(sr, ct_code)
        if not sede_ref:
            continue
        ibc_txt, _ = _parse_money_text(wi.get("ibc"))
        sede_ref["empleados_independientes"] += 1
        sede_ref["empleados_total"] += 1
        sede_ref["valor_nomina_sede"] += _to_int_safe(ibc_txt, default=0)
        if ct_code and ct_code not in sede_ref["centros_codigos"]:
            sede_ref["centros_codigos"].append(ct_code)

    sede_breakdown: list[dict[str, Any]] = []
    for sr, row in sede_breakdown_map.items():
        row["centros_codigos"] = sorted(list(set(row.get("centros_codigos", []))), key=lambda x: int(x) if str(x).isdigit() else str(x))
        row["centros_costo"] = len(row["centros_codigos"])
        sede_breakdown.append(row)
    sede_breakdown.sort(key=lambda r: int(str(r.get("sede", "0"))) if str(r.get("sede", "")).isdigit() else str(r.get("sede", "")))

    sede_breakdown_totals = {
        "empleados_total": sum(int(r.get("empleados_total", 0)) for r in sede_breakdown),
        "centros_costo_total": sum(int(r.get("centros_costo", 0)) for r in sede_breakdown),
        "valor_nomina_total": sum(int(r.get("valor_nomina_sede", 0)) for r in sede_breakdown),
    }

    excel_summary: Optional[dict[str, Any]] = None
    excel_match: dict[str, Any] = {"ok": False, "reason": "excel_no_provided"}
    if excel_bytes:
        excel_summary = _excel_contract_executive_summary(excel_bytes)
        if bool(excel_summary.get("ok")):
            ex_tot = excel_summary.get("totals", {})
            row_cmp = {
                "empleados": {
                    "excel": int(ex_tot.get("empleados", 0)),
                    "engine": int(engine_totals["empleados"]),
                },
                "sedes": {
                    "excel": int(ex_tot.get("sedes", 0)),
                    "engine": int(engine_totals["sedes"]),
                },
                "centros_costo": {
                    "excel": int(ex_tot.get("centros_costo", 0)),
                    "engine": int(engine_totals["centros_costo"]),
                },
                "salarios": {
                    "excel": int(ex_tot.get("salarios", 0)),
                    "engine": int(engine_totals["salarios"]),
                },
            }
            for k in row_cmp.keys():
                row_cmp[k]["diferencia"] = int(row_cmp[k]["engine"]) - int(row_cmp[k]["excel"])
                row_cmp[k]["ok"] = row_cmp[k]["diferencia"] == 0
            excel_match = {
                "ok": all(bool(v.get("ok")) for v in row_cmp.values()),
                "rows": row_cmp,
                "by_sede": excel_summary.get("by_sede", []),
            }
        else:
            excel_match = {"ok": False, "error": excel_summary.get("error", "No se pudo procesar Excel")}

    content_926 = flatfile_926_content
    source_926 = "none"
    gen_error = ""
    if not content_926 and generate_926_if_missing:
        try:
            gen = LEGACY_ENGINE.generate_flatfile_926(lote=lote)
            content_926 = gen.decode("latin-1", errors="replace")
            source_926 = "generated"
        except Exception as exc:
            gen_error = f"{type(exc).__name__}: {exc}"
    elif content_926:
        source_926 = "provided"

    report_926: dict[str, Any] = {
        "ok": False,
        "source": source_926,
        "error": gen_error or "No hay 926 para validar.",
    }
    if content_926:
        v926 = _validate_926_structure(content_926)
        t926 = _line_type_counts(content_926)
        count_checks = {
            "empleados_vs_linea3": {
                "engine": int(engine_totals["empleados"]),
                "txt_926": int(t926.get("3", 0)),
            },
            "centros_vs_linea2": {
                "engine": int(engine_totals["centros_costo"]),
                "txt_926": int(t926.get("2", 0)),
            },
            "sedes_vs_linea7": {
                "engine": int(engine_totals["sedes"]),
                "txt_926": int(t926.get("7", 0)),
            },
        }
        for k in count_checks.keys():
            count_checks[k]["diferencia"] = int(count_checks[k]["txt_926"]) - int(count_checks[k]["engine"])
            count_checks[k]["ok"] = count_checks[k]["diferencia"] == 0
        structural_min_ok = (
            int(v926.get("line_count", 0)) > 0
            and int(v926.get("unknown_type_count", 0)) == 0
            and int(v926.get("non_ascii_count", 0)) == 0
        )
        report_926 = {
            "ok": structural_min_ok and all(bool(v.get("ok")) for v in count_checks.values()),
            "source": source_926,
            "strict_validate_ok": bool(v926.get("ok")),
            "validate_926": v926,
            "line_type_counts": t926,
            "count_checks": count_checks,
        }

    excel_rows = excel_match.get("rows", {}) if isinstance(excel_match, dict) else {}
    overall_data_ok = bool(excel_match.get("ok"))
    overall_ok = overall_data_ok and bool(report_926.get("ok"))
    return {
        "ok": True,
        "overall_ok": overall_ok,
        "overall_data_ok": overall_data_ok,
        "lote": lote,
        "sync": sync_info,
        "empresa": {
            "razon_social": razon_social,
            "nit": nit,
        },
        "engine_totals": engine_totals,
        "excel_summary": excel_summary,
        "excel_match": excel_match,
        "report_926": report_926,
        "resumen_ejecutivo": {
            "empresa": razon_social,
            "nit": nit,
            "empleados": engine_totals["empleados"],
            "empleados_excel": int(((excel_rows.get("empleados") or {}).get("excel", 0))) if excel_rows else None,
            "sedes": engine_totals["sedes"],
            "sedes_excel": int(((excel_rows.get("sedes") or {}).get("excel", 0))) if excel_rows else None,
            "centros_costo": engine_totals["centros_costo"],
            "centros_costo_excel": int(((excel_rows.get("centros_costo") or {}).get("excel", 0))) if excel_rows else None,
            "salarios_total": engine_totals["salarios"],
            "salarios_total_excel": int(((excel_rows.get("salarios") or {}).get("excel", 0))) if excel_rows else None,
            "salarios_diferencia": int(((excel_rows.get("salarios") or {}).get("diferencia", 0))) if excel_rows else None,
            "coincide_con_excel": bool(excel_match.get("ok")),
            "926_ok": bool(report_926.get("ok")),
            "estado_final": "OK" if overall_ok else "CON_OBSERVACIONES",
            "desglose_sedes": sede_breakdown,
            "desglose_sedes_totales": sede_breakdown_totals,
        },
    }


def _in_lote(row: dict[str, Any], lote: str) -> bool:
    if not lote:
        return True
    lt = as_text(row.get("lt")).strip()
    lo = as_text(row.get("lote")).strip()
    if lt == "" and lo == "":
        return True
    return lt == lote or lo == lote


def _reproceso_split_by_precheck(lote: str, precheck: dict[str, Any], apply: bool = False) -> dict[str, Any]:
    invalid_sr = {
        as_text(err.get("sr")).strip()
        for err in precheck.get("errors", [])
        if as_text(err.get("sr")).strip() != ""
    }
    tables = ["wh", "wd", "wddias", "wcentrot", "wdestudiantes", "wdindependientes", "wdcomisiones"]
    table_stats: list[dict[str, Any]] = []

    for table in tables:
        all_rows = LEGACY_ENGINE._rows(table)
        rejected_rows = []
        kept_rows = []
        scoped_rows = 0
        for row in all_rows:
            scoped = _in_lote(row, lote)
            if scoped:
                scoped_rows += 1
            sr = as_text(row.get("sr")).strip()
            reject = scoped and sr in invalid_sr
            if reject:
                rejected_rows.append(row)
            else:
                kept_rows.append(row)

        if apply:
            LEGACY_ENGINE._set_rows(table, kept_rows)
        table_stats.append(
            {
                "table": table,
                "rows_scoped": scoped_rows,
                "rows_rejected": len(rejected_rows),
                "rows_kept": scoped_rows - len(rejected_rows),
            }
        )

    if apply:
        meta = LEGACY_ENGINE.state.setdefault("meta", {})
        meta["last_rules_reproceso"] = {
            "lote": lote,
            "applied_at": datetime.now().isoformat(),
            "invalid_sr_count": len(invalid_sr),
            "table_stats": table_stats,
        }
        LEGACY_ENGINE._save_state()

    return {"invalid_sr_count": len(invalid_sr), "invalid_sr": sorted(invalid_sr), "table_stats": table_stats}


def _observaciones_csv(lote: str, precheck: dict[str, Any], include_warnings: bool = True) -> str:
    rows: list[dict[str, str]] = []
    now = datetime.now().isoformat()
    for err in precheck.get("errors", []):
        rows.append(
            {
                "timestamp": now,
                "lote": lote,
                "nivel": "ERROR",
                "tabla": as_text(err.get("table")),
                "sr": as_text(err.get("sr")),
                "linea": as_text(err.get("linea")),
                "codigo": as_text(err.get("code")),
                "detalle": as_text(err.get("detail")),
            }
        )
    if include_warnings:
        for warn in precheck.get("warnings", []):
            rows.append(
                {
                    "timestamp": now,
                    "lote": lote,
                    "nivel": "WARNING",
                    "tabla": as_text(warn.get("table")),
                    "sr": as_text(warn.get("sr")),
                    "linea": as_text(warn.get("linea")),
                    "codigo": as_text(warn.get("code")),
                    "detalle": as_text(warn.get("detail")),
                }
            )
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=["timestamp", "lote", "nivel", "tabla", "sr", "linea", "codigo", "detalle"])
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


def _sync_planillas(payload: dict[str, Any]) -> dict[str, Any]:
    incoming = payload.get("items")
    items = incoming if isinstance(incoming, list) and incoming else DEFAULT_PLANILLAS
    return {
        "ok": True,
        "opc": "traedevoluciones",
        "count": len(items),
        "items": items,
        "message": "Sincronizacion de planillas preparada para persistencia en DB.",
    }


def _version(payload: dict[str, Any]) -> dict[str, Any]:
    current_version = str(payload.get("current_version") or DEFAULT_VERSION)
    local_version = str(payload.get("local_version") or payload.get("version") or "").strip()
    return {
        "ok": True,
        "opc": "version",
        "server_version": current_version,
        "local_version": local_version,
        "match": bool(local_version) and local_version == current_version,
    }


def _python(payload: dict[str, Any]) -> dict[str, Any]:
    server_version = str(payload.get("server_version") or DEFAULT_VERSION)
    local_version = str(payload.get("local_version") or "").strip()
    return {
        "ok": True,
        "opc": "python",
        "server_version": server_version,
        "local_version": local_version,
        "ready": bool(local_version) and local_version == server_version,
        "message": "listo" if local_version and local_version == server_version else "pendiente-version",
    }


def _normalize_stages(raw: Any) -> list[str]:
    if raw is None:
        return list(TR_STAGE_ORDER)
    if not isinstance(raw, list):
        raise HTTPException(status_code=400, detail="Campo 'stages' debe ser lista.")
    stages = [str(s).strip() for s in raw if str(s).strip()]
    if not stages:
        raise HTTPException(status_code=400, detail="Campo 'stages' no puede estar vacio.")
    invalid = [s for s in stages if s not in TR_STAGE_TABLE]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Stages no soportados: {', '.join(invalid)}")
    return stages


def _generate_default_rows(stage: str, lote: str) -> list[dict[str, Any]]:
    table = TR_STAGE_TABLE[stage]
    if table == "wh":
        return [{"sr": 1001, "f01": "900123456", "f59": "001", "tp": "P", "lt": lote}]
    if table == "wd":
        return [{"sr": 1001, "li": 1, "f28": "CC", "f36": "12345678", "lt": lote}]
    if table == "wddias":
        return [{"sr": 1001, "dia": "01", "h1": "N", "h2": "N", "lote": lote}]
    if table == "wcentrot":
        return [{"sr": 1001, "codigoct": "001", "codigoactividad": "6201", "lote": lote}]
    if table == "wdestudiantes":
        return [{"sr": 1001, "linea": 1, "documento": "100200300", "lote": lote}]
    if table == "wdindependientes":
        return [{"sr": 1001, "linea": 1, "documento": "900800700", "lote": lote}]
    return [{"sr": 1001, "linea": 1, "vendedor": "1001", "lote": lote}]


def _stage_input_rows(payload: dict[str, Any], stage: str, lote: str) -> list[dict[str, Any]]:
    rows_by_stage = payload.get("rows_by_stage")
    if isinstance(rows_by_stage, dict) and stage in rows_by_stage and isinstance(rows_by_stage[stage], list):
        rows = rows_by_stage[stage]
        if rows:
            return [dict(r) if isinstance(r, dict) else {"raw": str(r), "lote": lote} for r in rows]
    rows = payload.get("rows")
    if isinstance(rows, list) and rows:
        return [dict(r) if isinstance(r, dict) else {"raw": str(r), "lote": lote} for r in rows]
    return _generate_default_rows(stage, lote)


def _importar_lote_tr(payload: dict[str, Any], lote: Optional[str] = None) -> dict[str, Any]:
    resolved_lote = str(lote or payload.get("lote") or "").strip()
    if not resolved_lote:
        raise HTTPException(status_code=400, detail="Campo requerido: lote")
    base = str(payload.get("base") or "temporal").strip().lower()
    if base not in {"temporal", "ybr"}:
        raise HTTPException(status_code=400, detail="Campo 'base' debe ser temporal o ybr.")
    stages = _normalize_stages(payload.get("stages"))
    dry_run = bool(payload.get("dry_run", False))

    stage_runs: list[dict[str, Any]] = []
    total_rows = 0
    sr_values: list[int] = []
    for stage in stages:
        rows = _stage_input_rows(payload, stage, resolved_lote)
        inserted = len(rows)
        total_rows += inserted
        for row in rows:
            sr = row.get("sr")
            if isinstance(sr, int):
                sr_values.append(sr)
        stage_runs.append(
            {
                "stage": stage,
                "table": TR_STAGE_TABLE[stage],
                "delimiter": TR_STAGE_DELIMITER.get(stage, ","),
                "legacy_request": {"sw": "Tr", "sw1": stage, "lt": resolved_lote, "base": base},
                "inserted": inserted,
                "sample": rows[0] if rows else {},
                "dry_run": dry_run,
            }
        )

    run = {
        "lote": resolved_lote,
        "base": base,
        "stages": stage_runs,
        "rows_total": total_rows,
        "sr_min": min(sr_values) if sr_values else None,
        "sr_max": max(sr_values) if sr_values else None,
        "status": "dry_run" if dry_run else "imported",
    }
    TR_IMPORT_RUNS[resolved_lote] = run
    return {"ok": True, **run}


def _reprocesar_lote_tr(payload: dict[str, Any], lote: Optional[str] = None) -> dict[str, Any]:
    resolved_lote = str(lote or payload.get("lote") or "").strip()
    if not resolved_lote:
        raise HTTPException(status_code=400, detail="Campo requerido: lote")
    if resolved_lote not in TR_IMPORT_RUNS:
        raise HTTPException(status_code=404, detail=f"No existe importacion previa para lote {resolved_lote}.")

    apply_changes = not bool(payload.get("dry_run", False))
    imported = TR_IMPORT_RUNS[resolved_lote]
    stage_count_map = {s["table"]: int(s.get("inserted", 0)) for s in imported.get("stages", [])}

    target_cleanups = [
        {"db": "ybr", "table": "brempresasarp"},
        {"db": "ybr", "table": "brafiliadosarp"},
        {"db": "ybr", "table": "brwddias"},
        {"db": "ybr", "table": "brcentrot"},
        {"db": "ybr", "table": "brwdestudiantes"},
        {"db": "ybr", "table": "brwdindependientes"},
        {"db": "ybr", "table": "brwdcomisiones"},
        {"db": "wimg004", "table": "bkempresasarp"},
        {"db": "wimg004", "table": "bkafiliadosarp"},
        {"db": "wimg004", "table": "bkwddias"},
        {"db": "wimg004", "table": "bkcentrot"},
        {"db": "wimg004", "table": "bkwdestudiantes"},
        {"db": "wimg004", "table": "bkwdindependientes"},
        {"db": "wimg004", "table": "bkwdcomisiones"},
    ]
    copy_plan = [
        {"source": "temporal.brempresasarp", "target": "ybr.brempresasarp", "count": stage_count_map.get("wh", 0)},
        {"source": "temporal.brafiliadosarp", "target": "ybr.brafiliadosarp", "count": stage_count_map.get("wd", 0)},
        {"source": "temporal.brwddias", "target": "ybr.brwddias", "count": stage_count_map.get("wddias", 0)},
        {"source": "temporal.brcentrot", "target": "ybr.brcentrot", "count": stage_count_map.get("wcentrot", 0)},
        {
            "source": "temporal.brwdestudiantes",
            "target": "ybr.brwdestudiantes",
            "count": stage_count_map.get("wdestudiantes", 0),
        },
        {
            "source": "temporal.brwdindependientes",
            "target": "ybr.brwdindependientes",
            "count": stage_count_map.get("wdindependientes", 0),
        },
        {"source": "temporal.brwdcomisiones", "target": "ybr.brwdcomisiones", "count": stage_count_map.get("wdcomisiones", 0)},
        {"source": "temporal.bkempresasarp", "target": "wimg004.bkempresasarp", "count": stage_count_map.get("wh", 0)},
        {"source": "temporal.bkafiliadosarp", "target": "wimg004.bkafiliadosarp", "count": stage_count_map.get("wd", 0)},
    ]

    staging_cleanup = [
        "temporal.devempresasarp",
        "temporal.devafiliadosarp",
        "temporal.devwddias",
        "temporal.devcentrot",
        "temporal.devwdestudiantes",
        "temporal.devwdindependientes",
        "temporal.devwdcomisiones",
        "temporal.brempresasarp",
        "temporal.brafiliadosarp",
        "temporal.brwddias",
        "temporal.brcentrot",
        "temporal.brwdestudiantes",
        "temporal.brwdindependientes",
        "temporal.brwdcomisiones",
        "temporal.bkempresasarp",
        "temporal.bkafiliadosarp",
        "temporal.bkwddias",
        "temporal.bkcentrot",
        "temporal.bkwdestudiantes",
        "temporal.bkwdindependientes",
        "temporal.bkwdcomisiones",
        "temporal.afi_rad",
        "temporal.afi_devoluciones",
        "temporal.lc",
        "temporal.tr",
    ]

    result = {
        "ok": True,
        "lote": resolved_lote,
        "apply": apply_changes,
        "source_import_status": imported.get("status"),
        "sr_min": imported.get("sr_min"),
        "sr_max": imported.get("sr_max"),
        "rows_total": imported.get("rows_total"),
        "cleanup_target": target_cleanups,
        "copy_plan": copy_plan,
        "status_updates": [
            {
                "target": "wimg004.afi_rad",
                "set": {"afi_rad_estado": "Plano"},
                "where": {"afi_rad_contrato": "por-lote", "afi_rad_estado": "Indexado"},
            }
        ],
        "cleanup_staging": staging_cleanup,
        "message": "Reproceso TR preparado (equivalente funcional a AfiliacionesReproceso.php).",
    }
    if apply_changes:
        TR_IMPORT_RUNS[resolved_lote] = {**imported, "status": "reprocessed"}
        result["final_status"] = "reprocessed"
    else:
        result["final_status"] = "dry_run"
    return result


def _dispatch_tr_legacy(payload: dict[str, Any]) -> dict[str, Any]:
    sw1 = str(payload.get("sw1") or "").strip()
    if sw1 in TR_STAGE_TABLE:
        lote = str(payload.get("lt") or payload.get("lote") or "").strip()
        if not lote:
            raise HTTPException(status_code=400, detail="Campo requerido: lt/lote")
        base = str(payload.get("base") or "temporal").strip().lower()
        run = _importar_lote_tr({"lote": lote, "base": base, "stages": [sw1], "rows_by_stage": payload.get("rows_by_stage")})
        single = run["stages"][0]
        return {
            "ok": True,
            "sw": "Tr",
            "sw1": sw1,
            "lote": lote,
            "base": base,
            "table": single["table"],
            "count": single["inserted"],
            "items": payload.get("rows_by_stage", {}).get(sw1, []) if isinstance(payload.get("rows_by_stage"), dict) else [],
            "delimiter": single["delimiter"],
        }
    if sw1 == "reproceso":
        return _reprocesar_lote_tr(payload, lote=str(payload.get("lt") or payload.get("lote") or ""))
    raise HTTPException(status_code=501, detail=f"sw1 no soportado para sw=Tr: {sw1}")


def _dispatch(payload: dict[str, Any]) -> dict[str, Any]:
    if "sw" in payload:
        params = _stringify_payload(payload)
        db_response = _dispatch_db_aware(params)
        if db_response is not None:
            return {"ok": True, "legacy": True, "source": "db_alias", "sw": params.get("sw"), "sw1": params.get("sw1"), "response_text": db_response}
        raw = LEGACY_ENGINE.legacy_general(params)
        return {"ok": True, "legacy": True, "sw": params.get("sw"), "sw1": params.get("sw1"), "response_text": raw}

    opc = _normalize_opc(payload)
    if opc == "traedevoluciones":
        return _sync_planillas(payload)
    if opc == "version":
        return _version(payload)
    if opc == "python":
        return _python(payload)
    if opc == "Tr":
        return _dispatch_tr_legacy(payload)
    if opc == "tr_importar_lote":
        return _importar_lote_tr(payload)
    if opc == "tr_reprocesar_lote":
        return _reprocesar_lote_tr(payload)
    raise HTTPException(status_code=501, detail=f"opc no soportado para afiliaciones: {opc}")


def _dispatch_db_aware(params: dict[str, str]) -> Optional[str]:
    sw = params.get("sw", "")
    if sw == "M01":
        return _dispatch_db_m01(params)

    if sw not in {"Tr", "dev"}:
        return None

    sw1 = params.get("sw1", "")
    lt = params.get("lt", "")
    base = params.get("base", "temporal")
    if not sw1 or not lt:
        return None

    layouts = LEGACY_ENGINE.TR_LAYOUTS if sw == "Tr" else LEGACY_ENGINE.DEV_LAYOUTS
    cfg = layouts.get(sw1)
    if not cfg:
        return None

    table = cfg["table"]
    use_lt = table in {"brempresasarp", "brafiliadosarp", "devempresasarp", "devafiliadosarp", "bkempresasarp", "bkafiliadosarp"}
    key_field = "lt" if use_lt else "lote"
    order_clause = " ORDER BY sr" if table in {"brempresasarp", "devempresasarp"} else ""
    sql = f"SELECT * FROM {table} WHERE {key_field} = :lt{order_clause}"

    try:
        rows = fetch_all_by_alias(base, sql, {"lt": lt})
    except (ValueError, SQLAlchemyError):
        return None

    if not rows:
        return "0"

    path_token = os.getenv("LEGACY_PATH_TOKEN", "")
    defaults = cfg.get("defaults", {})
    delimiter = cfg["delimiter"]
    out_rows: list[str] = []

    for row in rows:
        vals = []
        for field in cfg["fields"]:
            value = as_text(row.get(field))
            if value == "" and field in defaults:
                value = as_text(defaults[field])
            vals.append(value)
        if cfg.get("append_path"):
            vals.append(path_token)
        out_rows.append(delimiter.join(vals))

    return "|".join(out_rows) + "|"


def _dispatch_db_m01(params: dict[str, str]) -> Optional[str]:
    sw1 = params.get("sw1", "")
    path_token = os.getenv("LEGACY_PATH_TOKEN", "")
    m01_insert_tables = {
        "brempresasarp",
        "brafiliadosarp",
        "brwddias",
        "brcentrot",
        "brwdestudiantes",
        "brwdindependientes",
        "brwdcomisiones",
        "bkempresasarp",
        "bkafiliadosarp",
        "bkwddias",
        "bkcentrot",
        "bkwdestudiantes",
        "bkwdindependientes",
        "bkwdcomisiones",
    }

    if sw1 == "RL":
        try:
            rows = fetch_all_by_alias("temporal", "SELECT cb, fc, nl, ob, us FROM tr WHERE cb='Afa' ORDER BY nl")
        except (ValueError, SQLAlchemyError):
            return None
        if not rows:
            return "0"
        out = []
        for r in rows:
            out.append(
                f"{as_text(r.get('cb'))},{as_text(r.get('fc'))},{as_text(r.get('nl'))},"
                f"{as_text(r.get('ob'))},{as_text(r.get('us'))},{path_token}"
            )
        return "|".join(out) + "|"

    if sw1 == "SL":
        try:
            rows = fetch_all_by_alias(
                "wimg004",
                "SELECT fileid,status,userid,nomdoc,cab,fl,ni,pn "
                "FROM lc WHERE status IN ('En Espera','En Revisión','En Revision') AND nomdoc='Afa' ORDER BY 1",
            )
        except (ValueError, SQLAlchemyError):
            return None
        if not rows:
            return "0"

        out = []
        for r in rows:
            pn_path = as_text(r.get("pn")).replace("\\", "/")
            out.append(
                f"{as_text(r.get('fileid'))},{as_text(r.get('status'))},{as_text(r.get('userid'))},"
                f"{as_text(r.get('nomdoc'))},{as_text(r.get('cab'))},{as_text(r.get('fl'))},"
                f"{as_text(r.get('ni'))},{pn_path}"
            )
            # Replica behavior legacy: cachea LC en temporal si no existe.
            try:
                exists = fetch_all_by_alias("temporal", "SELECT fileid FROM lc WHERE fileid = :fileid", {"fileid": r.get("fileid")})
                if not exists:
                    execute_by_alias(
                        "temporal",
                        "INSERT INTO lc(fileid,status,userid,nomdoc,cab,fl,ni,pn) "
                        "VALUES (:fileid,:status,:userid,:nomdoc,:cab,:fl,:ni,:pn)",
                        {
                            "fileid": r.get("fileid"),
                            "status": r.get("status"),
                            "userid": r.get("userid"),
                            "nomdoc": r.get("nomdoc"),
                            "cab": r.get("cab"),
                            "fl": r.get("fl"),
                            "ni": r.get("ni"),
                            "pn": r.get("pn"),
                        },
                    )
            except (ValueError, SQLAlchemyError):
                pass
        return "|".join(out) + "|"

    if sw1 == "SL-2":
        fileid = as_text(params.get("fileid")).strip()
        if not fileid:
            return "0"
        try:
            rows = fetch_all_by_alias("wimg004", "SELECT status, userid, fileid FROM lc WHERE fileid = :fileid", {"fileid": fileid})
        except (ValueError, SQLAlchemyError):
            return None
        if not rows:
            return "0"
        r0 = rows[0]
        return f"{as_text(r0.get('status'))}|{as_text(r0.get('userid'))}|{as_text(r0.get('fileid'))}"

    if sw1 == "CL":
        nl = as_text(params.get("nl")).strip()
        cb = as_text(params.get("cb")).strip()
        fc = as_text(params.get("FechaProceso")).strip()
        ob = as_text(params.get("ob")).strip()
        if not nl:
            return ""
        try:
            execute_by_alias("temporal", "DELETE FROM tr WHERE nl = :nl", {"nl": nl})
            execute_by_alias(
                "temporal",
                "INSERT INTO tr(cb,nl,fc,ob) VALUES(:cb,:nl,:fc,:ob)",
                {"cb": cb, "nl": nl, "fc": fc, "ob": ob},
            )
            return ""
        except (ValueError, SQLAlchemyError):
            return None

    if sw1 == "General-Guardar-delete_sr":
        lo = as_text(params.get("var1")).strip()
        hi = as_text(params.get("var2")).strip()
        if not lo or not hi:
            return "0"
        try:
            execute_by_alias("temporal", "DELETE FROM bkempresasarp WHERE sr BETWEEN :lo AND :hi", {"lo": lo, "hi": hi})
            execute_by_alias("temporal", "DELETE FROM bkafiliadosarp WHERE sr BETWEEN :lo AND :hi", {"lo": lo, "hi": hi})
            execute_by_alias("temporal", "DELETE FROM bkwddias WHERE sr BETWEEN :lo AND :hi", {"lo": lo, "hi": hi})
            execute_by_alias("temporal", "DELETE FROM bkcentrot WHERE sr BETWEEN :lo AND :hi", {"lo": lo, "hi": hi})
            execute_by_alias("temporal", "DELETE FROM bkwdestudiantes WHERE sr BETWEEN :lo AND :hi", {"lo": lo, "hi": hi})
            execute_by_alias("temporal", "DELETE FROM bkwdindependientes WHERE sr BETWEEN :lo AND :hi", {"lo": lo, "hi": hi})
            execute_by_alias("temporal", "DELETE FROM bkwdcomisiones WHERE sr BETWEEN :lo AND :hi", {"lo": lo, "hi": hi})
            return "1"
        except (ValueError, SQLAlchemyError):
            return None

    if sw1 == "General-Guardar-delete":
        lote = as_text(params.get("var1")).strip()
        if not lote:
            return "0"
        try:
            execute_by_alias("temporal", "DELETE FROM brempresasarp WHERE lt = :lote", {"lote": lote})
            execute_by_alias("temporal", "DELETE FROM brafiliadosarp WHERE lt = :lote", {"lote": lote})
            execute_by_alias("temporal", "DELETE FROM brwddias WHERE lote = :lote", {"lote": lote})
            execute_by_alias("temporal", "DELETE FROM brcentrot WHERE lote = :lote", {"lote": lote})
            execute_by_alias("temporal", "DELETE FROM brwdestudiantes WHERE lote = :lote", {"lote": lote})
            execute_by_alias("temporal", "DELETE FROM brwdindependientes WHERE lote = :lote", {"lote": lote})
            execute_by_alias("temporal", "DELETE FROM brwdcomisiones WHERE lote = :lote", {"lote": lote})
            return "1"
        except (ValueError, SQLAlchemyError):
            return None

    if sw1 == "General-Guardar-delete_bk":
        lote = as_text(params.get("var1")).strip()
        if not lote:
            return "0"
        try:
            execute_by_alias("temporal", "DELETE FROM bkempresasarp WHERE lt = :lote", {"lote": lote})
            execute_by_alias("temporal", "DELETE FROM bkafiliadosarp WHERE lt = :lote", {"lote": lote})
            execute_by_alias("temporal", "DELETE FROM bkwddias WHERE lote = :lote", {"lote": lote})
            execute_by_alias("temporal", "DELETE FROM bkcentrot WHERE lote = :lote", {"lote": lote})
            execute_by_alias("temporal", "DELETE FROM bkwdestudiantes WHERE lote = :lote", {"lote": lote})
            execute_by_alias("temporal", "DELETE FROM bkwdindependientes WHERE lote = :lote", {"lote": lote})
            execute_by_alias("temporal", "DELETE FROM bkwdcomisiones WHERE lote = :lote", {"lote": lote})
            return "1"
        except (ValueError, SQLAlchemyError):
            return None

    if sw1 == "General-Guardar":
        tabla = as_text(params.get("tabla")).strip().lower()
        var1 = as_text(params.get("var1"))
        var2 = as_text(params.get("var2"))
        if tabla not in m01_insert_tables:
            return None
        row = LEGACY_ENGINE._parse_legacy_insert_payload(var1, var2)
        if row is None:
            return "1"
        cols = [c for c in row.keys() if c != ""]
        if not cols:
            return "1"
        placeholders = ", ".join([f":{c}" for c in cols])
        sql = f"INSERT INTO {tabla} ({', '.join(cols)}) VALUES ({placeholders})"
        try:
            execute_by_alias("temporal", sql, {c: row[c] for c in cols})
            return "0"
        except (ValueError, SQLAlchemyError):
            return None

    if sw1 == "General-IndAA":
        payload = {
            "gabineteindex": as_text(params.get("gabineteindex")),
            "planilla": as_text(params.get("planilla")),
            "nit": as_text(params.get("nit")),
            "tipoid": as_text(params.get("tipoid")),
            "fechaproceso": as_text(params.get("FechaProceso")),
            "lote": as_text(params.get("lote")),
            "gabinetefuente": as_text(params.get("gabinetefuente")),
            "path": as_text(params.get("path")),
            "nomdoc": as_text(params.get("NomDoc")),
        }
        try:
            execute_by_alias(
                "temporal",
                "INSERT INTO planillasafiliadosarp("
                "gabineteindex,planilla,nit,tipoid,fechaproceso,descripcion,lote,gabinetefuente,path,nomdoc,fecha_sade"
                ") VALUES ("
                ":gabineteindex,:planilla,:nit,:tipoid,:fechaproceso,'Afiliacion ARL',:lote,:gabinetefuente,:path,:nomdoc,0"
                ")",
                payload,
            )
            execute_by_alias(
                "temporal",
                "UPDATE afi_rad SET fecha_detectar=:lote, afi_rad_fechadigitacion=:fechaproceso, afi_rad_estado='Indexado' "
                "WHERE afi_rad_contrato=:planilla AND afi_rad_estado='Radicada'",
                payload,
            )
            return "1"
        except (ValueError, SQLAlchemyError):
            return None

    if sw1 == "General-IndAA-2":
        payload = {
            "nroanexo": as_text(params.get("nroanexo")),
            "gabineteindex": as_text(params.get("gabineteindex")),
            "planilla": as_text(params.get("planilla")),
            "fechaproceso": as_text(params.get("FechaProceso")),
            "lote": as_text(params.get("lote")),
            "gabinetefuente": as_text(params.get("gabinetefuente")),
            "nit": as_text(params.get("nit")),
            "path": as_text(params.get("path")),
            "nomdoc": as_text(params.get("NomDoc")),
        }
        try:
            execute_by_alias(
                "temporal",
                "INSERT INTO anexosafiliadosarp("
                "nroanexo,gabineteindex,planilla,fechaproceso,descripcion,lote,gabinetefuente,nit,path,nomdoc"
                ") VALUES ("
                ":nroanexo,:gabineteindex,:planilla,:fechaproceso,'Anexo Afiliacion ARL',:lote,:gabinetefuente,:nit,:path,:nomdoc"
                ")",
                payload,
            )
            return "1"
        except (ValueError, SQLAlchemyError):
            return None

    if sw1 == "General-IndAA-delete":
        lote = as_text(params.get("lote")).strip()
        if not lote:
            return "0"
        try:
            execute_by_alias("temporal", "DELETE FROM tr WHERE nl = :lote", {"lote": lote})
            return "1"
        except (ValueError, SQLAlchemyError):
            return None

    if sw1 == "General-IndAA-3":
        payload = {
            "fileid": as_text(params.get("fileid")).strip(),
            "fechaproceso": as_text(params.get("FechaProceso")),
            "uiue": as_text(params.get("UiUe")),
        }
        if not payload["fileid"]:
            return "0"
        try:
            execute_by_alias(
                "temporal",
                "UPDATE lc SET cs=0, status='Indexado', fe=:fechaproceso, ui=:uiue, ue=:uiue, fh=:fechaproceso, fx=:fechaproceso "
                "WHERE fileid=:fileid",
                payload,
            )
            return "1"
        except (ValueError, SQLAlchemyError):
            return None

    if sw1 == "General-Estadistico":
        payload = {
            "lote": as_text(params.get("lote")),
            "fechaproceso": as_text(params.get("FechaProceso")),
            "planilla": as_text(params.get("planilla")),
            "nroanexo": as_text(params.get("nroanexo")),
            "detalle": as_text(params.get("Detalle")),
            "usuario": as_text(params.get("Usuario") or params.get("usuario")),
            "sede": as_text(params.get("sede")),
            "centrot": as_text(params.get("centrot")),
            "fechashora": as_text(params.get("Fechashora")),
        }
        if not payload["lote"]:
            return "1"
        try:
            rows = fetch_all_by_alias("temporal", "SELECT lote FROM estadistico WHERE lote=:lote", {"lote": payload["lote"]})
            if not rows:
                execute_by_alias(
                    "temporal",
                    "INSERT INTO estadistico(lote,fecha,familia,planillas,anexos,detalles,usuario) "
                    "VALUES (:lote,:fechaproceso,'Afa',:planilla,:nroanexo,:detalle,:usuario)",
                    payload,
                )
            else:
                execute_by_alias(
                    "temporal",
                    "UPDATE estadistico SET sede=:sede, centrot=:centrot, fecha_entrega=:fechashora, "
                    "planillas=:planilla, anexos=:nroanexo, detalles=:detalle "
                    "WHERE lote=:lote",
                    payload,
                )
            return "0"
        except (ValueError, SQLAlchemyError):
            return None

    return None


def _sync_engine_from_db(lote: str, base: str = "temporal", fecha_proceso: str = "", lote_usuario: str = "") -> dict[str, Any]:
    lote = lote.strip()
    base = base.strip() or "temporal"
    if not lote:
        raise HTTPException(status_code=400, detail="Parametro requerido: lote")
    fecha_digits = _only_digits(fecha_proceso)[:8]
    if len(fecha_digits) != 8:
        fecha_digits = datetime.now().strftime("%Y%m%d")

    def q_table(table: str, lote_field: str, order_candidates: list[str]) -> list[dict[str, Any]]:
        try:
            cols = {c.lower() for c in get_table_columns_by_alias(base, table)}
        except NoSuchTableError:
            return []
        except (ValueError, SQLAlchemyError) as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Error leyendo columnas de {base}.{table}: {type(exc).__name__}: {exc}",
            )
        if lote_field.lower() not in cols:
            alt = next((c for c in ("lt", "lote", "nl", "fileid") if c in cols), "")
            if not alt:
                return []
            lote_field = alt
        order_cols = [c for c in order_candidates if c.lower() in cols]
        order_clause = f" ORDER BY {', '.join(order_cols)}" if order_cols else ""
        sql = f"SELECT * FROM {table} WHERE {lote_field} = :lote{order_clause}"
        try:
            return fetch_all_by_alias(base, sql, {"lote": lote})
        except (ValueError, SQLAlchemyError) as exc:
            raise HTTPException(status_code=503, detail=f"Error leyendo {base}: {type(exc).__name__}: {exc}")

    lote_usuario_force = _only_digits(lote_usuario) or as_text(lote_usuario).strip()

    def _resolve_lote_usuario() -> tuple[str, str, dict[str, Any]]:
        d = _diagnose_lote_usuario(base=base, lote=lote)
        if lote_usuario_force:
            d["selected"] = lote_usuario_force
            d["selected_source"] = "manual"
            d["forced"] = True
            d["forced_value"] = lote_usuario_force
        return as_text(d.get("selected")).strip(), as_text(d.get("selected_source")).strip(), d

    wh = q_table("brempresasarp", "lt", ["sr"])
    wd = q_table("brafiliadosarp", "lt", ["sr", "li"])
    wddias = q_table("brwddias", "lote", ["sr"])
    wcentrot = q_table("brcentrot", "lote", ["sr"])
    wdest = q_table("brwdestudiantes", "lote", ["sr", "linea"])
    wdind = q_table("brwdindependientes", "lote", ["sr", "linea"])
    wdcom = q_table("brwdcomisiones", "lote", ["sr", "linea"])

    # Normalizacion de paridad para motor legacy:
    # - producto en WH no siempre existe en brempresasarp, pero validate_cd lo exige.
    # - tipoempresa (1/2/3) es requerido por prebuild-check.
    # - f17 por sede (TP='S') debe cuadrar con cantidad de trabajadores.
    wd_by_sr: dict[str, int] = {}
    for row in wd:
        sr = as_text(row.get("sr")).strip()
        if sr:
            wd_by_sr[sr] = wd_by_sr.get(sr, 0) + 1

    lote_usuario, lote_usuario_source, lote_usuario_diag = _resolve_lote_usuario()

    for idx, row in enumerate(wh):
        tp = as_text(row.get("tp")).strip().upper()
        if not tp:
            tp = "P" if idx == 0 else "S"
            row["tp"] = tp

        # Default conservador para que no rompa validaciones base.
        if not as_text(row.get("producto")).strip():
            row["producto"] = "AFA"

        tipoempresa = as_text(row.get("tipoempresa")).strip()
        if tipoempresa not in {"1", "2", "3", "8", "9"}:
            # 2 = privada (default operativo usado en pruebas legacy)
            row["tipoempresa"] = "2"

        if tp == "S":
            sr = as_text(row.get("sr")).strip()
            row["f17"] = str(wd_by_sr.get(sr, 0))
        # El valor que el plano expone en el segmento "lote usuario" viene de Wh!Lt.
        # Para no romper el scope por lote, se guarda aparte y se usa solo al render del 926.
        if lote_usuario:
            row["lt_usuario"] = lote_usuario
        # Regla operativa de clon: fecha de proceso consistente para generación del 926.
        if not as_text(row.get("f65")).strip():
            row["f65"] = fecha_digits
        row["fecesc"] = fecha_digits
        row["fecloc"] = fecha_digits

    # En algunos ambientes clone, brcentrot llega "recortada" (sin clase/grado/tasa).
    # Completar estos campos evita que el tipo 2 salga con tarifa en cero.
    wh_by_sr: dict[str, dict[str, Any]] = {}
    for row in wh:
        sr_key = as_text(row.get("sr")).strip()
        if sr_key:
            wh_by_sr[sr_key] = row

    tasa_by_clase = {
        "1": "0.522",
        "2": "1.044",
        "3": "2.436",
        "4": "4.350",
        "5": "6.960",
    }
    zero_tasa_tokens = {"", "0", "0.0", "0.00", "0.000", "0.0000", "00000"}
    for ct in wcentrot:
        sr_key = as_text(ct.get("sr")).strip()
        wh_ref = wh_by_sr.get(sr_key, {})

        codigoactividad = as_text(ct.get("codigoactividad") or wh_ref.get("f05")).strip()
        codigoactividad_digits = _only_digits(codigoactividad)
        activity_profile = _activity_risk_profile_arp(codigoactividad_digits or codigoactividad)
        claseriesgo = as_text(ct.get("claseriesgo") or wh_ref.get("f49")).strip()
        if activity_profile.get("clase") in {"1", "2", "3", "4", "5"}:
            claseriesgo = activity_profile["clase"]
        if claseriesgo not in {"1", "2", "3", "4", "5"}:
            claseriesgo = codigoactividad_digits[:1] if codigoactividad_digits[:1] in {"1", "2", "3", "4", "5"} else "2"

        grado = activity_profile.get("grado") or as_text(ct.get("grado")).strip()
        if not grado:
            grado = "12" if codigoactividad_digits == "2851201" else "00"

        tasa = as_text(ct.get("tasa")).replace(",", ".").strip()
        if activity_profile.get("tasa"):
            tasa = activity_profile["tasa"]
        if tasa in zero_tasa_tokens:
            tasa = tasa_by_clase.get(claseriesgo, "1.044")
        if codigoactividad_digits == "2851201":
            tasa = "1.044"
        tasa = _format_tasa_arp(tasa) or tasa_by_clase.get(claseriesgo, "1.044")

        ct["codigoactividad"] = codigoactividad or "0"
        ct["claseriesgo"] = claseriesgo
        ct["grado"] = grado
        ct["tasa"] = tasa
        if not as_text(ct.get("nombreactividad")).strip():
            ct["nombreactividad"] = as_text(wh_ref.get("f71")).strip() or activity_profile.get("nombre") or f"RIESGO {claseriesgo}"

    payload = {
        "tables": {
            "wh": wh,
            "wd": wd,
            "wddias": wddias,
            "wcentrot": wcentrot,
            "wdestudiantes": wdest,
            "wdindependientes": wdind,
            "wdcomisiones": wdcom,
        },
        "meta": {
            "source": "db_alias",
            "base": base,
            "lote": lote,
            "fecha_proceso": fecha_digits,
            "flatfile_reference_enabled": False,
            "flatfile_reference_lines": [],
            "flatfile_reference_raw": "",
        },
    }
    LEGACY_ENGINE.load_dump(payload)
    return {
        "ok": True,
        "source": "db_alias",
        "base": base,
        "lote": lote,
        "fecha_proceso": fecha_digits,
        "lote_usuario": lote_usuario,
        "lote_usuario_source": lote_usuario_source,
        "lote_usuario_diagnostico": lote_usuario_diag,
        "rows": {k: len(v) for k, v in payload["tables"].items()},
    }


def _diagnose_lote_usuario(base: str, lote: str) -> dict[str, Any]:
    """
    Diagnóstico de fuente para Wh!Lt (lote usuario) en paridad legacy.
    """
    base = as_text(base).strip() or "temporal"
    lote = as_text(lote).strip()
    default_lt = _only_digits(lote) or lote
    candidates: list[dict[str, Any]] = []

    def _add_candidate(source: str, value: Any) -> None:
        raw = as_text(value).strip()
        digits = _only_digits(raw)
        if not raw and not digits:
            return
        candidates.append({"source": source, "raw": raw, "digits": digits})

    try:
        lc_cols = {c.lower() for c in get_table_columns_by_alias(base, "lc")}
    except (ValueError, SQLAlchemyError, NoSuchTableError):
        lc_cols = set()
    if "ni" in lc_cols:
        fileid_col = "fileid" if "fileid" in lc_cols else ("lote" if "lote" in lc_cols else "")
        order_cols = [c for c in ("fi", "fl", "fe", "fecha", "fecha_insert", "sr") if c in lc_cols]
        order_clause = f" ORDER BY {', '.join(order_cols)} DESC" if order_cols else ""
        if fileid_col and lote:
            try:
                rows = fetch_all_by_alias(
                    base,
                    f"SELECT ni FROM lc WHERE {fileid_col} = :fileid{order_clause} LIMIT 20",
                    {"fileid": lote},
                )
                for r in rows:
                    _add_candidate("lc.ni(fileid)", r.get("ni"))
            except (ValueError, SQLAlchemyError):
                pass
        try:
            rows = fetch_all_by_alias(base, f"SELECT ni FROM lc{order_clause} LIMIT 20")
            for r in rows:
                _add_candidate("lc.ni(latest)", r.get("ni"))
        except (ValueError, SQLAlchemyError):
            pass

    try:
        tr_cols = {c.lower() for c in get_table_columns_by_alias(base, "tr")}
    except (ValueError, SQLAlchemyError, NoSuchTableError):
        tr_cols = set()
    if "nl" in tr_cols:
        where = " WHERE cb = 'Afa'" if "cb" in tr_cols else ""
        order_cols = [c for c in ("fc", "sr", "nl") if c in tr_cols]
        order_clause = f" ORDER BY {', '.join(order_cols)} DESC" if order_cols else ""
        try:
            rows = fetch_all_by_alias(base, f"SELECT nl FROM tr{where}{order_clause} LIMIT 20")
            for r in rows:
                _add_candidate("tr.nl", r.get("nl"))
        except (ValueError, SQLAlchemyError):
            pass

    selected = default_lt
    selected_source = "lote"
    for c in candidates:
        digits = as_text(c.get("digits")).strip()
        if digits:
            selected = digits
            selected_source = as_text(c.get("source")).strip() or "unknown"
            break

    return {
        "ok": True,
        "base": base,
        "lote": lote,
        "selected": selected,
        "selected_source": selected_source,
        "default_fallback": default_lt,
        "candidates": candidates,
    }


def _yyyymmdd(value: Any) -> str:
    txt = as_text(value).strip()
    if not txt:
        return ""
    if len(txt) >= 10 and txt[4] == "-" and txt[7] == "-":
        return txt[:10].replace("-", "")
    return "".join(ch for ch in txt if ch.isdigit())[:8]


def _split_name(full_name: str) -> tuple[str, str, str, str]:
    parts = [p for p in as_text(full_name).strip().split() if p]
    if not parts:
        return "", "", "", ""
    if len(parts) == 1:
        return parts[0], "", "", ""
    if len(parts) == 2:
        return parts[0], parts[1], "", ""
    if len(parts) == 3:
        return parts[0], parts[1], parts[2], ""
    return parts[0], parts[1], parts[2], " ".join(parts[3:])


def _load_proc_servicios_to_engine(payload: dict[str, Any]) -> dict[str, Any]:
    base = as_text(payload.get("base") or "temporal").strip() or "temporal"
    lote = as_text(payload.get("lote")).strip() or f"PROC-{datetime.now().strftime('%Y%m%d')}"
    estado = as_text(payload.get("estado")).strip()
    idtramite = as_text(payload.get("idtramite")).strip()
    limit = int(payload.get("limit") or 1000)
    if limit < 1:
        limit = 1
    if limit > 5000:
        limit = 5000
    fecha_proceso_raw = as_text(payload.get("fecha_proceso")).strip()
    fecha_proceso = ""
    if fecha_proceso_raw:
        digits = _only_digits(fecha_proceso_raw)
        if len(digits) >= 8:
            fecha_proceso = digits[:8]
    if not fecha_proceso:
        fecha_proceso = datetime.now().strftime("%Y%m%d")

    conditions = ["1=1"]
    params: dict[str, Any] = {"limit": limit}
    if estado:
        conditions.append("t.estado = :estado")
        params["estado"] = estado
    if idtramite:
        conditions.append("t.idtramite = :idtramite")
        params["idtramite"] = idtramite

    tramite_cols: set[str] = set()
    empleador_cols: set[str] = set()
    trabajador_cols: set[str] = set()
    sede_cols: set[str] = set()
    eps_cols: set[str] = set()
    afp_cols: set[str] = set()
    ciudades_cols: set[str] = set()
    actividad_cols: set[str] = set()
    comisiones_cols: set[str] = set()
    try:
        tramite_cols = {str(c).lower() for c in get_table_columns_by_alias(base, "proc_servicios_obtenertramites")}
    except (ValueError, SQLAlchemyError, NoSuchTableError):
        tramite_cols = set()
    try:
        empleador_cols = {str(c).lower() for c in get_table_columns_by_alias(base, "proc_servicios_obtenerempleadortramite")}
    except (ValueError, SQLAlchemyError, NoSuchTableError):
        empleador_cols = set()
    try:
        trabajador_cols = {str(c).lower() for c in get_table_columns_by_alias(base, "proc_servicios_obtenertrabajadortramite")}
    except (ValueError, SQLAlchemyError, NoSuchTableError):
        trabajador_cols = set()
    try:
        sede_cols = {str(c).lower() for c in get_table_columns_by_alias(base, "proc_servicios_obtenersedetramite")}
    except (ValueError, SQLAlchemyError, NoSuchTableError):
        sede_cols = set()
    try:
        eps_cols = {str(c).lower() for c in get_table_columns_by_alias(base, "epsriesgos")}
    except (ValueError, SQLAlchemyError, NoSuchTableError):
        eps_cols = set()
    try:
        afp_cols = {str(c).lower() for c in get_table_columns_by_alias(base, "afpriesgos")}
    except (ValueError, SQLAlchemyError, NoSuchTableError):
        afp_cols = set()
    try:
        ciudades_cols = {str(c).lower() for c in get_table_columns_by_alias(base, "ciudades")}
    except (ValueError, SQLAlchemyError, NoSuchTableError):
        ciudades_cols = set()
    try:
        actividad_cols = {str(c).lower() for c in get_table_columns_by_alias(base, "actividadeconomicaarp")}
    except (ValueError, SQLAlchemyError, NoSuchTableError):
        actividad_cols = set()
    try:
        comisiones_cols = {str(c).lower() for c in get_table_columns_by_alias(base, "proc_servicios_obtenercomisionestramite")}
    except (ValueError, SQLAlchemyError, NoSuchTableError):
        comisiones_cols = set()

    # Hardening: en varios esquemas legacy no existe t.fecha_insert.
    # Si existe, se usa para paridad de fechas de salida en plano.
    tramite_fecha_insert_expr = (
        "t.fecha_insert AS tramite_fecha_insert"
        if "fecha_insert" in tramite_cols
        else "NULL::timestamptz AS tramite_fecha_insert"
    )
    empleador_fecha_insert_expr = (
        "e.fecha_insert AS empleador_fecha_insert"
        if "fecha_insert" in empleador_cols
        else "NULL::timestamptz AS empleador_fecha_insert"
    )
    contrato_expr = "t.idtramite::text AS numero_contrato"
    for candidate in ("numerocontrato", "numero_contrato", "nrocontrato", "contrato"):
        if candidate in empleador_cols:
            contrato_expr = f"e.{candidate}::text AS numero_contrato"
            break
    else:
        for candidate in ("numerocontrato", "numero_contrato", "nrocontrato", "contrato"):
            if candidate in tramite_cols:
                contrato_expr = f"t.{candidate}::text AS numero_contrato"
                break
    rep_doc_expr = "NULL::text AS numerodocumentorepresnetantelegal"
    for candidate in ("numerodocumentorepresnetantelegal", "numerodocumentorepresentantelegal"):
        if candidate in empleador_cols:
            rep_doc_expr = f"e.{candidate}::text AS numerodocumentorepresnetantelegal"
            break
    rep_tipodoc_expr = "NULL::text AS tipodocumentorepresentantelegal"
    for candidate in ("tipodocumentorepresentantelegal", "tipodocumentorepresnetantelegal"):
        if candidate in empleador_cols:
            rep_tipodoc_expr = f"e.{candidate}::text AS tipodocumentorepresentantelegal"
            break
    sucursal_expr = "NULL::text AS sucursal_codigo"
    for candidate in ("sucursal", "codigosucursal", "idsucursal", "lugarafiliacion"):
        if candidate in tramite_cols:
            sucursal_expr = f"t.{candidate}::text AS sucursal_codigo"
            break
    arl_emp_expr = "NULL::text AS arlanteriorempleador"
    for candidate in ("arlanteriorempleador", "arlanterior", "codigoarlanterior"):
        if candidate in empleador_cols:
            arl_emp_expr = f"e.{candidate}::text AS arlanteriorempleador"
            break
    cargo_expr = "NULL::text AS cargo"
    if "cargo" in trabajador_cols:
        cargo_expr = "w.cargo AS cargo"
    codigoct_expr = "NULL::text AS codigoct"
    if "codigoct" in trabajador_cols:
        codigoct_expr = "w.codigoct AS codigoct"
    ct_nombre_expr = "NULL::text AS ct_nombreactividad"
    if "ct_nombreactividad" in trabajador_cols:
        ct_nombre_expr = "w.ct_nombreactividad AS ct_nombreactividad"
    ct_codigo_expr = "NULL::text AS ct_codigoactividad"
    if "ct_codigoactividad" in trabajador_cols:
        ct_codigo_expr = "w.ct_codigoactividad AS ct_codigoactividad"
    ct_clase_expr = "NULL::text AS ct_claseriesgo"
    if "ct_claseriesgo" in trabajador_cols:
        ct_clase_expr = "w.ct_claseriesgo AS ct_claseriesgo"
    ct_cot_expr = "NULL::text AS ct_montocotizacion"
    if "ct_montocotizacion" in trabajador_cols:
        ct_cot_expr = "w.ct_montocotizacion AS ct_montocotizacion"
    def _worker_col_expr(column: str) -> str:
        return f"w.{column} AS {column}" if column in trabajador_cols else f"NULL::text AS {column}"
    ciudad_trab_expr = "w.ciudadresidencia"
    if "municipioresidencia" in trabajador_cols:
        ciudad_trab_expr = "w.municipioresidencia"

    sql = f"""
    SELECT
      t.idtramite,
      t.estado,
      t.fecharegistro,
      {tramite_fecha_insert_expr},
      {contrato_expr},
      e.tipodocumentoempleador,
      e.numerodocumentoempleador,
      e.telefonoprincipalempleador,
      e.direccionempleador,
      e.telefonocelularempleador,
      e.correoelectronicoempleador,
      e.ciudadempleador,
      e.zonaempleador,
      e.localidadempleador,
      e.nombrerepresentantelegal,
      {rep_tipodoc_expr},
      {rep_doc_expr},
      e.correoelectronicorepresentantelegal,
      e.actividadeconomicaempleador,
      e.razonsocialempleador,
      e.naturalezajuridica,
      e.tipoafiliacion,
      e.tipoaportante,
      {arl_emp_expr},
      {sucursal_expr},
      {empleador_fecha_insert_expr},
      w.idtrabajador,
      w.sr AS worker_sr,
      w.tipodocumento,
      w.numerodocumento,
      w.primerapellido,
      w.segundoapellido,
      w.primernombre,
      w.segundonombre,
      w.fechanacimiento,
      w.sexo,
      w.direccionresidencia,
      {ciudad_trab_expr} AS ciudadresidencia,
      w.localidad,
      w.zona,
      w.telefono,
      w.celular,
      w.correoelectronico,
      w.eps,
      w.actividadeconomica,
      {cargo_expr},
      {codigoct_expr},
      {ct_nombre_expr},
      {ct_codigo_expr},
      {ct_clase_expr},
      {ct_cot_expr},
      {_worker_col_expr("ct_ciudad")},
      {_worker_col_expr("ct_departamento")},
      {_worker_col_expr("ct_zona")},
      {_worker_col_expr("ct_direccion")},
      {_worker_col_expr("ct_telefono")},
      {_worker_col_expr("ct_correo")},
      {_worker_col_expr("ct_responsable_pa")},
      {_worker_col_expr("ct_responsable_sa")},
      {_worker_col_expr("ct_responsable_pn")},
      {_worker_col_expr("ct_responsable_sn")},
      {_worker_col_expr("ct_responsable_td")},
      {_worker_col_expr("ct_responsable_doc")},
      {_worker_col_expr("ct_responsable_correo")},
      w.modalidad,
      w.arlanterior,
      w.afp,
      w.iniciocontrato,
      w.finalizacioncontrato,
      w.valorcontrato,
      w.ingresomensual,
      w.deducciones,
      w.ibc,
      w.iniciocobertura,
      w.tipoafiliadocotizante,
      w.subtipoafiliadocotizante,
      w.tipocontrato,
      w.jornada,
      w.suministratransporte,
      w.numeromesescontrato
    FROM proc_servicios_obtenertramites t
    LEFT JOIN proc_servicios_obtenerempleadortramite e ON e.idtramite = t.idtramite
    LEFT JOIN proc_servicios_obtenertrabajadortramite w ON w.idtramite = t.idtramite
    WHERE {" AND ".join(conditions)}
    ORDER BY t.idtramite, w.sr, w.idtrabajador
    LIMIT :limit
    """
    try:
        rows = fetch_all_by_alias(base, sql, params)
    except (ValueError, SQLAlchemyError) as exc:
        msg = str(exc)
        if "UndefinedColumn" in msg or "does not exist" in msg:
            msg = "estructura proc_servicios_* incompleta para esta consulta (faltan columnas esperadas)"
        raise HTTPException(
            status_code=503,
            detail=f"Error leyendo proc_servicios_* en {base}: {msg}",
        )

    if not rows:
        return {
            "ok": True,
            "source": "proc_servicios",
            "base": base,
            "lote": lote,
            "rows_query": 0,
            "rows_engine": {"wh": 0, "wdestudiantes": 0, "wdindependientes": 0, "wdcomisiones": 0},
            "message": "Sin datos para los filtros solicitados.",
        }

    tramites: dict[str, dict[str, Any]] = {}
    trabajadores_by_tramite: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        t_id = as_text(row.get("idtramite")).strip()
        if not t_id:
            continue
        if t_id not in tramites:
            tramites[t_id] = row
            trabajadores_by_tramite[t_id] = []
        if as_text(row.get("numerodocumento")).strip():
            trabajadores_by_tramite[t_id].append(row)

    wh: list[dict[str, Any]] = []
    wcentrot: list[dict[str, Any]] = []
    wd: list[dict[str, Any]] = []
    wdest: list[dict[str, Any]] = []
    wdind: list[dict[str, Any]] = []
    wdcom: list[dict[str, Any]] = []
    sr_counter = 1
    wd_line_counter = 1
    city_cache: dict[str, str] = {}
    eps_cache: dict[str, str] = {}
    afp_cache: dict[str, str] = {}
    actividad_cache: dict[str, tuple[str, str, str]] = {}

    def _city_code(value: Any) -> str:
        txt = as_text(value).strip()
        if txt == "":
            return ""
        digits = "".join(ch for ch in txt if ch.isdigit())
        if len(digits) >= 5:
            return digits[-5:]
        key = txt.upper()
        if key in city_cache:
            return city_cache[key]
        # Fallback operativo (cuando no están catálogos ciudades/departamentos en temporal).
        # Debe mantenerse acotado a códigos DANE conocidos usados en afiliaciones.
        city_fallback = {
            "BARRANQUILLA": "08001",
            "TUBARA": "08832",
            "TUBARÁ": "08832",
            "BOGOTA": "11001",
            "BOGOTÁ": "11001",
            "BOGOTA D.C.": "11001",
            "BOGOTÁ D.C.": "11001",
            "CHIA": "25175",
            "CHÍA": "25175",
            "TOCANCIPA": "25817",
            "TOCANCIPÁ": "25817",
            "SOLEDAD": "08758",
            "MEDELLIN": "05001",
            "MEDELLÍN": "05001",
            "CALI": "76001",
        }
        if key in city_fallback:
            city_cache[key] = city_fallback[key]
            return city_fallback[key]
        for name, code in city_fallback.items():
            if name in key:
                city_cache[key] = code
                return code
        if {"ciudad", "codigo"}.issubset(ciudades_cols):
            try:
                rows_ci = fetch_all_by_alias(
                    base,
                    "SELECT codigo FROM ciudades WHERE UPPER(TRIM(ciudad)) = UPPER(TRIM(:c)) LIMIT 1",
                    {"c": txt},
                )
                if rows_ci:
                    code = as_text(rows_ci[0].get("codigo")).strip()
                    city_cache[key] = code
                    return code
            except (ValueError, SQLAlchemyError):
                pass
        city_cache[key] = ""
        return ""

    def _eps_code(value: Any) -> str:
        txt = as_text(value).strip()
        if txt == "":
            return ""
        digits = "".join(ch for ch in txt if ch.isdigit())
        if digits != "":
            return digits[-5:]
        key = txt.upper()
        eps_fallback = {
            "NUEVA EPS": "00037",
            "SANITAS": "00005",
            "SALUD TOTAL": "00002",
        }
        if key in eps_fallback:
            eps_cache[key] = eps_fallback[key]
            return eps_fallback[key]
        if key in eps_cache:
            return eps_cache[key]
        if {"nombre", "codigo"}.issubset(eps_cols):
            try:
                rows_eps = fetch_all_by_alias(
                    base,
                    "SELECT codigo FROM epsriesgos WHERE UPPER(TRIM(nombre)) = UPPER(TRIM(:n)) LIMIT 1",
                    {"n": txt},
                )
                if rows_eps:
                    code = as_text(rows_eps[0].get("codigo")).strip()
                    eps_cache[key] = code
                    return code
            except (ValueError, SQLAlchemyError):
                pass
        eps_cache[key] = "99"
        return "99"

    def _afp_code(value: Any) -> str:
        txt = as_text(value).strip()
        if txt == "":
            return ""
        digits = "".join(ch for ch in txt if ch.isdigit())
        if digits != "":
            return digits[-5:]
        key = txt.upper()
        afp_fallback = {
            "COLPENSIONES": "00002",
            "PROTECCION": "00014",
        }
        if key in afp_fallback:
            afp_cache[key] = afp_fallback[key]
            return afp_fallback[key]
        if key in afp_cache:
            return afp_cache[key]
        if {"nombre", "codigo"}.issubset(afp_cols):
            try:
                rows_afp = fetch_all_by_alias(
                    base,
                    "SELECT codigo FROM afpriesgos WHERE UPPER(TRIM(nombre)) = UPPER(TRIM(:n)) LIMIT 1",
                    {"n": txt},
                )
                if rows_afp:
                    code = as_text(rows_afp[0].get("codigo")).strip()
                    afp_cache[key] = code
                    return code
            except (ValueError, SQLAlchemyError):
                pass
        afp_cache[key] = "99"
        return "99"

    def _actividad_info(code_raw: Any) -> tuple[str, str, str]:
        code = as_text(code_raw).strip()
        if code == "":
            return ("6201", "SERVICIOS", "2")
        digits = "".join(ch for ch in code if ch.isdigit())
        norm = digits[-7:] if digits else code
        if norm in actividad_cache:
            return actividad_cache[norm]
        activity_profile = _activity_risk_profile_arp(norm)
        if activity_profile.get("nombre") or activity_profile.get("clase"):
            out = (
                activity_profile.get("codigo") or norm,
                activity_profile.get("nombre") or "SERVICIOS",
                activity_profile.get("clase") or "2",
            )
            actividad_cache[norm] = out
            return out
        if {"codigo", "nombre"}.issubset(actividad_cols):
            try:
                rows_act = fetch_all_by_alias(
                    base,
                    "SELECT codigo, nombre, claseriesgo FROM actividadeconomicaarp WHERE CAST(codigo AS text) = :c LIMIT 1",
                    {"c": norm},
                )
                if rows_act:
                    r0 = rows_act[0]
                    out = (
                        as_text(r0.get("codigo")).strip() or norm,
                        as_text(r0.get("nombre")).strip() or "SERVICIOS",
                        as_text(r0.get("claseriesgo")).strip() or "2",
                    )
                    actividad_cache[norm] = out
                    return out
            except (ValueError, SQLAlchemyError):
                pass
        out = (norm, "SERVICIOS", "2")
        actividad_cache[norm] = out
        return out

    def _tipo_doc_persona_code(value: Any) -> str:
        v = as_text(value).strip().upper()
        mapping = {
            "C": "1",
            "CC": "1",
            "T": "2",
            "TI": "2",
            "E": "3",
            "CE": "3",
            "P": "4",
            "PA": "4",
            "PE": "8",
            "PT": "9",
        }
        return mapping.get(v, "1")

    def _tipo_tramite_f49(value: Any) -> str:
        txt = as_text(value).strip().upper()
        if "TRASL" in txt:
            return "1"
        return "2"

    def _is_aprendiz_worker(row: dict[str, Any]) -> bool:
        tipo_txt = as_text(row.get("tipo_trabajador_text")).strip().upper()
        cargo_txt = as_text(row.get("cargo")).strip().upper()
        return ("APREND" in tipo_txt) or ("APREND" in cargo_txt)

    def _is_independiente_worker(row: dict[str, Any]) -> bool:
        tipo_txt = as_text(row.get("tipo_trabajador_text")).strip().upper()
        if "INDEPEND" in tipo_txt:
            return True
        tc_raw = as_text(row.get("tipoafiliadocotizante")).strip()
        if tc_raw.isdigit():
            tc = int(tc_raw)
            # Catálogo operativo: cotizantes 5x se manejan por ruta independientes.
            if 50 <= tc <= 59:
                return True
        return False

    for idtramite_key in sorted(tramites.keys(), key=lambda x: float(x) if x.replace(".", "", 1).isdigit() else x):
        row = tramites[idtramite_key]
        tipodoc_emp = as_text(row.get("tipodocumentoempleador")).upper()
        numdoc_emp = as_text(row.get("numerodocumentoempleador"))
        contrato_num = as_text(row.get("numero_contrato")).strip() or idtramite_key
        rep = as_text(row.get("nombrerepresentantelegal"))
        rep_p1, rep_p2, rep_p3, rep_p4 = _split_name(rep)
        ciudad_emp = _city_code(row.get("ciudadempleador") or row.get("ciudad") or row.get("municipio")) or "11001"
        correo_emp = as_text(row.get("correoelectronicoempleador"))
        razon_social_emp = as_text(row.get("razonsocialempleador"))
        rep_doc = as_text(row.get("numerodocumentorepresnetantelegal"))
        rep_tipodoc = as_text(row.get("tipodocumentorepresentantelegal"))
        sucursal_codigo = as_text(row.get("sucursal_codigo") or "0")
        arl_emp = as_text(row.get("arlanteriorempleador") or "").strip()
        tipoaportante_raw = as_text(row.get("tipoaportante") or "1").strip() or "1"
        if tipoaportante_raw.isdigit():
            tipoaportante_raw = str(int(tipoaportante_raw))

        naturaleza_code = RULES_ENGINE.map_naturaleza_juridica(row.get("naturalezajuridica"))
        tipoempresa_override = as_text(row.get("tipoempresa")).strip()
        if tipoempresa_override not in {"1", "2", "3", "8", "9"}:
            tipoempresa_override = ""
        if naturaleza_code == 0:
            naturaleza_code = 2
        tipoempresa_value = tipoempresa_override or str(naturaleza_code)
        f49_code = _tipo_tramite_f49(row.get("tipoafiliacion"))
        if arl_emp == "" and f49_code == "1":
            arl_emp = "10"
        localidad_emp = as_text(row.get("localidadempleador")).strip()
        if localidad_emp.upper() in {"NA", "N/A", "NULL", "0"}:
            localidad_emp = ""

        wh.append(
            {
                "sr": sr_counter,
                "lt": lote,
                "tp": "P",
                "clase": "Afa",
                "f01": contrato_num,
                "f50": RULES_ENGINE.tipo_ident_empresa_codigo(tipodoc_emp),
                "f48": numdoc_emp,
                "f51": razon_social_emp[:54],
                "f15": ciudad_emp,
                "f12": as_text(row.get("direccionempleador")),
                "f14": as_text(row.get("telefonoprincipalempleador")),
                "f67": rep_doc,
                "f06": rep_p1,
                "f69": rep_p2,
                "carcont2": rep_p3,
                "f70": rep_p4,
                "nomcont2": rep_tipodoc,
                "f05": as_text(row.get("actividadeconomicaempleador")),
                "f49": f49_code,
                "f56": arl_emp,
                "f18": razon_social_emp,
                "f23": sucursal_codigo,
                "f57": ciudad_emp,
                "f09": _yyyymmdd(row.get("fecharegistro")),
                "f59": _yyyymmdd(row.get("iniciocobertura")),
                "f65": _yyyymmdd(row.get("fecharegistro")),
                "fecesc": fecha_proceso,
                "fecloc": fecha_proceso,
                "f20": as_text(row.get("telefonocelularempleador") or row.get("telefonoprincipalempleador")),
                "f55": correo_emp,
                "tipoempresa": tipoempresa_value,
                "grupoecono": "00000",
                "doccont1": "3",
                "contratoant": "000000",
                "tipoaportante": tipoaportante_raw,
                "tipoafiliacion": "INDIVIDUAL",
                "tipocodigo": "1",
                "subtipocodigo": "0",
                "tipoafiliado": "DEPENDIENTE",
                "nomdepcont2": "MICRO",
                "zona": RULES_ENGINE.normalize_zona(row.get("zonaempleador") or "U"),
                "localidad": localidad_emp,
                "aut46": "Verdadero",
                "aut47": "Verdadero",
                "aut48": "Verdadero",
            }
        )
        # Multi-sede: cada fila de proc_servicios_obtenersedetramite genera su WH tipo S.
        sede_rows: list[dict[str, Any]] = []
        try:
            sede_rows = fetch_all_by_alias(
                base,
                "SELECT * FROM proc_servicios_obtenersedetramite WHERE idtramite = :idtramite ORDER BY sr",
                {"idtramite": idtramite_key},
            )
        except (ValueError, SQLAlchemyError):
            sede_rows = []
        if not sede_rows:
            sede_rows = [{}]

        trabajadores = trabajadores_by_tramite.get(idtramite_key, [])
        trabajadores_by_ct: dict[str, list[dict[str, Any]]] = {}
        trabajadores_by_proc_sr: dict[int, str] = {}
        trabajadores_by_proc_sr_codes: dict[int, list[str]] = {}
        for wr in trabajadores:
            ct = as_text(wr.get("codigoct")).strip()
            if ct:
                trabajadores_by_ct.setdefault(ct, []).append(wr)
            sr_proc = _to_int_safe(wr.get("worker_sr"), default=0)
            if sr_proc > 0 and ct:
                ordered_ct_codes = trabajadores_by_proc_sr_codes.setdefault(sr_proc, [])
                if ct not in ordered_ct_codes:
                    ordered_ct_codes.append(ct)
                if sr_proc not in trabajadores_by_proc_sr:
                    trabajadores_by_proc_sr[sr_proc] = ct

        cod_act, nom_act, clase_riesgo = _actividad_info(row.get("actividadeconomicaempleador"))
        sede_slots: list[dict[str, Any]] = []
        ct_to_sede_sr: dict[str, int] = {}
        first_sede_sr = sr_counter + 1

        for sede_idx, sede_row in enumerate(sede_rows):
            sede_sr = sr_counter + 1 + sede_idx
            if rep_doc == "":
                rep_doc = as_text((sede_row or {}).get("documentoresponsable"))
            if rep.strip() == "":
                rep = as_text((sede_row or {}).get("nombreresponsable"))
                rep_p1, rep_p2, rep_p3, rep_p4 = _split_name(rep)
            resp_td = as_text((sede_row or {}).get("tipodocumentoresponsable") or rep_tipodoc)
            resp_nom = as_text((sede_row or {}).get("nombreresponsable") or rep)
            r1, r2, r3, r4 = _split_name(resp_nom)
            sede_ciudad_code = _city_code((sede_row or {}).get("ciudad") or row.get("ciudadempleador")) or ciudad_emp or "11001"
            sede_codigo = (
                as_text((sede_row or {}).get("codigosede"))
                or as_text((sede_row or {}).get("sede"))
                or as_text((sede_row or {}).get("numerosede"))
                or str(sede_idx + 1)
            )
            sede_nombre = as_text((sede_row or {}).get("nombresede") or f"SEDE {sede_idx + 1}")
            correo_sede = (
                as_text((sede_row or {}).get("correosede"))
                or as_text((sede_row or {}).get("correoelectronico"))
                or correo_emp
            )
            sede_zona = RULES_ENGINE.normalize_zona((sede_row or {}).get("zona") or row.get("zonaempleador") or "U")
            sede_localidad = as_text((sede_row or {}).get("localidad") or row.get("localidadempleador")).strip()
            if sede_localidad.upper() in {"NA", "N/A", "NULL", "0"}:
                sede_localidad = ""
            sede_direccion = as_text((sede_row or {}).get("direccion") or row.get("direccionempleador"))
            sede_telefono = as_text((sede_row or {}).get("telefono") or row.get("telefonoprincipalempleador"))
            sede_sr_proc = _to_int_safe((sede_row or {}).get("sr"), default=0)
            derived_ct_from_workers = trabajadores_by_proc_sr.get(sede_sr_proc, "")
            sede_ct_code = (
                _normalize_ct_code_token((sede_row or {}).get("codigocentrotrabajo"))
                or _normalize_ct_code_token((sede_row or {}).get("codigoct"))
                or _normalize_ct_code_token(derived_ct_from_workers)
                or _normalize_ct_code_token((sede_row or {}).get("codigosede"))
                or _normalize_ct_code_token(sede_idx + 1)
                or "000001"
            )

            wh.append(
                {
                    "sr": sede_sr,
                    "lt": lote,
                    "tp": "S",
                    "clase": "Afa",
                    "f01": contrato_num,
                    "f50": "0",
                    "f48": numdoc_emp,
                    "f51": sede_nombre[:54],
                    "f15": sede_ciudad_code,
                    "f12": sede_direccion,
                    "f14": sede_telefono,
                    "f67": as_text((sede_row or {}).get("documentoresponsable") or rep_doc),
                    "f06": r1,
                    "f69": r2,
                    "carcont2": r3,
                    "f70": r4,
                    "nomcont2": resp_td,
                    "dircont1": r3,
                    "f05": as_text(row.get("actividadeconomicaempleador")),
                    "f49": f49_code,
                    "f56": arl_emp,
                    "f18": correo_sede,
                    "f23": sucursal_codigo,
                    "f57": sede_ciudad_code,
                    "f09": _yyyymmdd(row.get("fecharegistro")),
                    "f59": _yyyymmdd(row.get("iniciocobertura")),
                    "f65": _yyyymmdd(row.get("fecharegistro")),
                    "fecesc": fecha_proceso,
                    "fecloc": fecha_proceso,
                    "f20": as_text((sede_row or {}).get("telefono") or row.get("telefonocelularempleador")),
                    "f55": correo_sede,
                    "tipoempresa": tipoempresa_value,
                    "grupoecono": "00000",
                    "doccont1": "3",
                    "contratoant": "000000",
                    "tipoaportante": tipoaportante_raw,
                    "tipoafiliacion": "INDIVIDUAL",
                    "tipocodigo": "1",
                    "subtipocodigo": "0",
                    "tipoafiliado": "DEPENDIENTE",
                    "nomdepcont2": "MICRO",
                    "f62": sede_codigo,
                    "f71": sede_nombre,
                    "f60": "1",
                    "zona": sede_zona,
                    "localidad": sede_localidad,
                    "aut46": "Verdadero",
                    "aut47": "Verdadero",
                    "aut48": "Verdadero",
                }
            )

            sede_slots.append(
                {
                    "sr": sede_sr,
                    "ct_code": sede_ct_code,
                    "sede_row": sede_row,
                    "resp_td": resp_td,
                    "resp_nom": resp_nom,
                    "resp_doc": as_text((sede_row or {}).get("documentoresponsable") or row.get("numerodocumentorepresnetantelegal")),
                    "ciudad": sede_ciudad_code,
                    "zona": sede_zona,
                    "direccion": sede_direccion,
                    "telefono": sede_telefono,
                    "nombre_sede": sede_nombre,
                    "mail": as_text((sede_row or {}).get("correoresponsable") or row.get("correoelectronicorepresentantelegal")),
                }
            )
            ct_codes_for_sede = list(trabajadores_by_proc_sr_codes.get(sede_sr_proc, []))
            if not ct_codes_for_sede:
                ct_codes_for_sede = [sede_ct_code]
            for ct_code_item in ct_codes_for_sede:
                norm_ct_code = _normalize_ct_code_token(ct_code_item) or sede_ct_code
                if norm_ct_code:
                    ct_to_sede_sr[norm_ct_code] = sede_sr
            sede_slots[-1]["ct_codes"] = ct_codes_for_sede

        for slot in sede_slots:
            sede_sr = int(slot["sr"])
            sede_row = slot["sede_row"]
            r1, r2, r3, r4 = _split_name(as_text(slot["resp_nom"]))
            ct_codes_for_sede = slot.get("ct_codes") or [as_text(slot.get("ct_code"))]
            for ct_code_item in ct_codes_for_sede:
                sede_ct_code = _normalize_ct_code_token(ct_code_item) or as_text(slot.get("ct_code"))
                sede_workers = trabajadores_by_ct.get(sede_ct_code, [])
                ct_ref = sede_workers[0] if sede_workers else {}
                ct_cod_act = as_text(ct_ref.get("ct_codigoactividad") or cod_act)
                activity_profile = _activity_risk_profile_arp(ct_cod_act)
                ct_nom_act = as_text(
                    ct_ref.get("ct_nombre")
                    or ct_ref.get("nombre_ct")
                    or ct_ref.get("ct_nombreactividad")
                    or slot.get("nombre_sede")
                    or ""
                ).strip()
                if ct_nom_act == "":
                    ct_nom_act = activity_profile.get("nombre") or nom_act or f"RIESGO {clase_riesgo}"
                ct_clase = as_text(ct_ref.get("ct_claseriesgo") or clase_riesgo or "2")
                if activity_profile.get("clase") in {"1", "2", "3", "4", "5"}:
                    ct_clase = activity_profile["clase"]
                ct_cot = as_text(ct_ref.get("ct_montocotizacion") or "0")
                ct_grado = activity_profile.get("grado") or "0"
                ct_tasa = as_text(
                    ct_ref.get("ct_tasa_riesgo")
                    or ct_ref.get("ct_tasa_riesgo_ct")
                    or ct_ref.get("tasa_riesgo")
                    or "",
                ).strip()
                if activity_profile.get("tasa"):
                    ct_tasa = activity_profile["tasa"]
                ct_tasa_norm = ct_tasa.replace(",", ".").strip()
                if ct_tasa_norm in {"", "0", "0.0", "0.00", "0.000", "0.0000", "00000"}:
                    tasa_by_clase = {
                        "1": "0.522",
                        "2": "1.044",
                        "3": "2.436",
                        "4": "4.350",
                        "5": "6.960",
                    }
                    ct_tasa = tasa_by_clase.get(as_text(ct_clase).strip(), "0")
                if _only_digits(ct_cod_act) == "2851201":
                    ct_grado = activity_profile.get("grado") or "12"
                    ct_tasa = activity_profile.get("tasa") or "1.044"
                ct_tasa = _format_tasa_arp(ct_tasa)
                wcentrot.append(
                    {
                        "sr": sede_sr,
                        "lote": lote,
                        "codigoct": sede_ct_code,
                        "codigoactividad": ct_cod_act,
                        "nombreactividad": ct_nom_act,
                        "claseriesgo": ct_clase,
                        "grado": ct_grado,
                        "tasa": ct_tasa,
                        "totaltrabajadores": str(len(sede_workers)),
                        "montocotizacion": ct_cot,
                        "ciudad": _city_code(ct_ref.get("ct_ciudad")) or as_text(slot["ciudad"]),
                        "zona": RULES_ENGINE.normalize_zona(ct_ref.get("ct_zona") or slot["zona"]),
                        "direccion": as_text(ct_ref.get("ct_direccion") or slot["direccion"]),
                        "telefono": as_text(ct_ref.get("ct_telefono") or slot["telefono"]),
                        "tipodocumento": as_text(ct_ref.get("ct_responsable_td") or slot["resp_td"]),
                        "id_responsable": as_text(ct_ref.get("ct_responsable_doc") or slot["resp_doc"]),
                        "primerapellido": as_text(ct_ref.get("ct_responsable_pa") or r1),
                        "segundoapellido": as_text(ct_ref.get("ct_responsable_sa") or r2),
                        "primernombre": as_text(ct_ref.get("ct_responsable_pn") or r3),
                        "segundonombre": as_text(ct_ref.get("ct_responsable_sn") or r4),
                        "mail": as_text(ct_ref.get("ct_responsable_correo") or ct_ref.get("ct_correo") or slot["mail"]),
                    }
                )

        valid_sede_srs = {int(s.get("sr") or 0) for s in sede_slots if int(s.get("sr") or 0) > 0}
        sede_count = len(sede_slots)
        for idx, wr in enumerate(trabajadores, start=1):
            worker_ct_code = _normalize_ct_code_token(wr.get("codigoct"))
            worker_sr_raw = _to_int_safe(wr.get("worker_sr"), default=0)
            # Prioridad 1: sr operativo de proc_servicios (1..N sedes) mapeado al SR de WH (2..N+1).
            # Prioridad 2: sr ya expresado en el dominio WH.
            # Prioridad 3: resolver por codigoct.
            # Fallback: primera sede.
            mapped_worker_sr = 0
            if worker_sr_raw > 0 and sede_count > 0 and worker_sr_raw <= sede_count:
                mapped_worker_sr = first_sede_sr + (worker_sr_raw - 1)
            if mapped_worker_sr > 0 and mapped_worker_sr in valid_sede_srs:
                worker_sr = mapped_worker_sr
            elif worker_sr_raw > 0 and worker_sr_raw in valid_sede_srs:
                worker_sr = worker_sr_raw
            else:
                worker_sr = ct_to_sede_sr.get(worker_ct_code, first_sede_sr)
            worker_ct_code = worker_ct_code or next(
                (
                    _normalize_ct_code_token(s.get("ct_code"))
                    for s in sede_slots
                    if _normalize_ct_code_token(s.get("ct_code"))
                ),
                "000001",
            )
            first_name = as_text(wr.get("primernombre"))
            second_name = as_text(wr.get("segundonombre"))
            full_name = " ".join(part for part in [first_name, second_name] if part).strip()
            telefono_raw = _only_digits(wr.get("telefono"))
            celular_raw = _only_digits(wr.get("celular"))
            telefono_norm = telefono_raw if len(telefono_raw) == 7 else "0"
            celular_norm = celular_raw if len(celular_raw) == 10 else "0"
            direccion_norm = as_text(wr.get("direccionresidencia")).replace("#", "").replace("-", "")
            if _is_aprendiz_worker(wr):
                wdest.append(
                    {
                        "sr": worker_sr,
                        "linea": idx,
                        "lote": lote,
                        "codigo_ct": worker_ct_code,
                        "tipodocumento": as_text(wr.get("tipodocumento")),
                        "documento": as_text(wr.get("numerodocumento")),
                        "primer_apellido": as_text(wr.get("primerapellido")),
                        "segundo_apellido": as_text(wr.get("segundoapellido")),
                        "primer_nombre": as_text(wr.get("primernombre")),
                        "segundo_nombre": as_text(wr.get("segundonombre")),
                        "fecha_nacimiento": _yyyymmdd(wr.get("fechanacimiento")),
                        "sexo": as_text(wr.get("sexo")),
                        "cargo": as_text(wr.get("cargo") or wr.get("actividadeconomica") or ""),
                        "salario": as_text(wr.get("ingresomensual")),
                        "eps": _eps_code(wr.get("eps")),
                        "afp": _afp_code(wr.get("afp")),
                        "direccion": as_text(wr.get("direccionresidencia")),
                        "telefono": telefono_norm,
                        "celular": celular_norm,
                        "correo": as_text(wr.get("correoelectronico")),
                        "ciudad": _city_code(wr.get("ciudadresidencia")),
                        "localidad": as_text(wr.get("localidad")),
                        "zona": RULES_ENGINE.normalize_zona(wr.get("zona")),
                        "departamento": "",
                        "jornada": as_text(wr.get("jornada")),
                        "modalidad": as_text(wr.get("modalidad")),
                        "codigo_actividad": as_text(wr.get("actividadeconomica")),
                        "fecha_inicio": _yyyymmdd(wr.get("iniciocontrato")),
                        "fecha_final": _yyyymmdd(wr.get("finalizacioncontrato")),
                        "meses": str(max(_ruta_to_int(wr.get("numeromesescontrato")) or 0, 1)),
                        "tipo_contrato": as_text(wr.get("tipocontrato")),
                        "monto_contrato": as_text(wr.get("valorcontrato")),
                        "tipo_salario": as_text(wr.get("tipo_salario") or "FIJO"),
                    }
                )
            else:
                wd.append(
                    {
                        "sr": worker_sr,
                        "lt": lote,
                        "li": idx,
                        "f28": as_text(wr.get("numerodocumento")),
                        "f29": _tipo_doc_persona_code(wr.get("tipodocumento")),
                        "f30": worker_ct_code,
                        "f31": as_text(wr.get("primerapellido")),
                        "f32": as_text(wr.get("segundoapellido")),
                        "f33": full_name,
                        "f34": as_text(wr.get("sexo")),
                        "f35": _yyyymmdd(wr.get("fechanacimiento")),
                        "f37": as_text(wr.get("cargo") or wr.get("actividadeconomica") or ""),
                        "f38": as_text(wr.get("ingresomensual")),
                        "f40": _eps_code(wr.get("eps")),
                        "f41": _afp_code(wr.get("afp")),
                        "direccion": direccion_norm,
                        "municipio": _city_code(wr.get("ciudadresidencia")),
                        "telefono": telefono_norm,
                        "celular": celular_norm,
                        "mail": as_text(wr.get("correoelectronico")),
                        "jornada": as_text(wr.get("jornada")),
                        "tipo_salario": as_text(wr.get("tipo_salario") or "FIJO"),
                    }
                )
                if _is_independiente_worker(wr):
                    wdind.append(
                        {
                            "sr": worker_sr,
                            "linea": idx,
                            "lote": lote,
                            "tipodocumento": as_text(wr.get("tipodocumento")),
                            "documento": as_text(wr.get("numerodocumento")),
                            "primer_apellido": as_text(wr.get("primerapellido")),
                            "segundo_apellido": as_text(wr.get("segundoapellido")),
                            "primer_nombre": as_text(wr.get("primernombre")),
                            "segundo_nombre": as_text(wr.get("segundonombre")),
                            "fecha_nacimiento": _yyyymmdd(wr.get("fechanacimiento")),
                            "sexo": as_text(wr.get("sexo")),
                            "direccion": as_text(wr.get("direccionresidencia")),
                            "municipio": as_text(wr.get("ciudadresidencia")),
                            "zona": RULES_ENGINE.normalize_zona(wr.get("zona")),
                            "localidad": as_text(wr.get("localidad")),
                            "telefono": as_text(wr.get("telefono")),
                            "celular": as_text(wr.get("celular")),
                            "correo": as_text(wr.get("correoelectronico")),
                            "eps": as_text(wr.get("eps")),
                            "codigo_eps": _eps_code(wr.get("eps")),
                            "afp": as_text(wr.get("afp")),
                            "codigo_afp": _afp_code(wr.get("afp")),
                            "arl_anterior": as_text(wr.get("arlanterior")),
                            "codigo_arl_anterior": as_text(wr.get("arlanterior")),
                            "tipo_cotizante": as_text(wr.get("tipoafiliadocotizante")),
                            "subtipo_cotizante": as_text(wr.get("subtipoafiliadocotizante")),
                            "tipotramite": as_text(wr.get("tipotramite")),
                            "modalidad": as_text(wr.get("modalidad")),
                            "tipo_contrato": as_text(wr.get("tipocontrato")),
                            "transporte": RULES_ENGINE.normalize_transporte(wr.get("suministratransporte")),
                            "fecha_inicio_contrato": _yyyymmdd(wr.get("iniciocontrato")),
                            "fecha_fin_contrato": _yyyymmdd(wr.get("finalizacioncontrato")),
                            "meses_contrato": str(max(_ruta_to_int(wr.get("numeromesescontrato")) or 0, 1)),
                            "valor_contrato": as_text(wr.get("valorcontrato")),
                            "valor_mensual": as_text(wr.get("ingresomensual")),
                            "ibc": as_text(wr.get("ibc")),
                            "actividad_economica": as_text(wr.get("actividadeconomica")),
                            "codigo_ct": worker_ct_code,
                            "tipo_salario": "1",
                            "linea_origen": wd_line_counter,
                        }
                    )
            wd_line_counter += 1

        if {"idtramite", "vendedor", "porcentaje"}.issubset(comisiones_cols):
            try:
                crows = fetch_all_by_alias(
                    base,
                    "SELECT * FROM proc_servicios_obtenercomisionestramite WHERE idtramite = :idtramite ORDER BY linea, sr",
                    {"idtramite": idtramite_key},
                )
            except (ValueError, SQLAlchemyError):
                crows = []
            for idxc, cr in enumerate(crows, start=1):
                vend = _only_digits(cr.get("vendedor"))[:10]
                wdcom.append(
                    {
                        "sr": sr_counter,
                        "linea": as_text(cr.get("linea") or idxc),
                        "vendedor": vend,
                        "codigo_vendedor": as_text(cr.get("codigo_vendedor") or "1"),
                        "venta": as_text(cr.get("venta") or "2"),
                        "porcentaje": as_text(cr.get("porcentaje") or "0"),
                        "lote": lote,
                    }
                )

        sr_counter += 1 + len(sede_rows)

    LEGACY_ENGINE.load_dump(
        {
            "tables": {
                "wh": wh,
                "wd": wd,
                "wddias": [],
                "wcentrot": wcentrot,
                "wdestudiantes": wdest,
                "wdindependientes": wdind,
                "wdcomisiones": wdcom,
            },
            "meta": {
                "source": "proc_servicios",
                "base": base,
                "lote": lote,
                "flatfile_reference_enabled": False,
                "flatfile_reference_lines": [],
                "flatfile_reference_raw": "",
            },
        }
    )

    if bool(payload.get("apply_to_db", False)):
        _import_real_lote_to_db(
            {
                "lote": lote,
                "base": base,
                "tables": {
                    "brempresasarp": wh,
                    "brafiliadosarp": wd,
                    "brcentrot": wcentrot,
                    "brwddias": [],
                    "brwdestudiantes": wdest,
                    "brwdindependientes": wdind,
                    "brwdcomisiones": wdcom,
                },
            }
        )

    return {
        "ok": True,
        "source": "proc_servicios",
        "base": base,
        "lote": lote,
        "rows_query": len(rows),
        "rows_engine": {
            "wh": len(wh),
            "wd": len(wd),
            "wcentrot": len(wcentrot),
            "wdestudiantes": len(wdest),
            "wdindependientes": len(wdind),
            "wdcomisiones": len(wdcom),
        },
        "filters": {"estado": estado, "idtramite": idtramite, "limit": limit},
    }


def _ruta_to_int(value: Any) -> Optional[int]:
    txt = as_text(value).strip()
    if txt == "":
        return None
    try:
        return int(float(txt))
    except ValueError:
        return None


def _ruta_inclusion_open_trace(base: str, idtramite: str) -> Optional[dict[str, Any]]:
    try:
        rows = fetch_all_by_alias(
            base,
            "SELECT * FROM proc_servicios_trazabilidad "
            "WHERE idtramite = :idtramite AND fecha_gestion IS NULL "
            "ORDER BY sr DESC LIMIT 1",
            {"idtramite": idtramite},
        )
    except (ValueError, SQLAlchemyError):
        return None
    return rows[0] if rows else None


def _ruta_inclusion_legacy_validaciones(base: str, idtramite: str) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    try:
        cab = fetch_all_by_alias(
            base,
            "SELECT idtramite, idtipotramite, tipotramite, estado "
            "FROM proc_servicios_obtenertramites WHERE idtramite = :idtramite LIMIT 1",
            {"idtramite": idtramite},
        )
    except (ValueError, SQLAlchemyError) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Error consultando cabecera de tramite en {base}: {type(exc).__name__}: {exc}",
        )
    if not cab:
        raise HTTPException(status_code=404, detail=f"idtramite no encontrado: {idtramite}")

    try:
        empleadores = fetch_all_by_alias(
            base,
            "SELECT sr, tipodocumentoempleador, numerodocumentoempleador "
            "FROM proc_servicios_obtenerempleadortramite WHERE idtramite = :idtramite ORDER BY sr",
            {"idtramite": idtramite},
        )
    except (ValueError, SQLAlchemyError) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Error consultando empleador de tramite en {base}: {type(exc).__name__}: {exc}",
        )

    try:
        trabajadores = fetch_all_by_alias(
            base,
            "SELECT sr, idtrabajador, numerodocumento, numeromesescontrato "
            "FROM proc_servicios_obtenertrabajadortramite WHERE idtramite = :idtramite ORDER BY sr",
            {"idtramite": idtramite},
        )
    except (ValueError, SQLAlchemyError) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Error consultando trabajador de tramite en {base}: {type(exc).__name__}: {exc}",
        )

    # Legacy validacionesGeneral()
    for row in empleadores:
        tipodoc = as_text(row.get("tipodocumentoempleador")).strip()
        numdoc = as_text(row.get("numerodocumentoempleador")).strip()
        if not tipodoc:
            errors.append(
                {
                    "code": "RI-VAL-001",
                    "message": "Error Tipo Documento",
                    "table": "proc_servicios_obtenerempleadortramite",
                    "row_sr": row.get("sr"),
                    "field": "tipodocumentoempleador",
                }
            )
        if not numdoc.isdigit():
            errors.append(
                {
                    "code": "RI-VAL-002",
                    "message": "Error El numero de documento no es numerico",
                    "table": "proc_servicios_obtenerempleadortramite",
                    "row_sr": row.get("sr"),
                    "field": "numerodocumentoempleador",
                    "value": numdoc,
                }
            )

    if not empleadores:
        warnings.append(
            {
                "code": "RI-WARN-001",
                "message": "No hay registro de empleador para este tramite.",
                "table": "proc_servicios_obtenerempleadortramite",
            }
        )

    # Legacy normalization used in ejecutaLectura(): if NumeroMesesContrato < 1 => 1.
    for row in trabajadores:
        meses = _ruta_to_int(row.get("numeromesescontrato"))
        if meses is None or meses < 1:
            errors.append(
                {
                    "code": "RI-VAL-003",
                    "message": "NumeroMesesContrato debe ser >= 1",
                    "table": "proc_servicios_obtenertrabajadortramite",
                    "row_sr": row.get("sr"),
                    "field": "numeromesescontrato",
                    "value": row.get("numeromesescontrato"),
                }
            )

    trace = _ruta_inclusion_open_trace(base, idtramite)
    if trace is None:
        warnings.append(
            {
                "code": "RI-WARN-002",
                "message": "No hay traza abierta (fecha_gestion IS NULL) para gestionar el caso.",
                "table": "proc_servicios_trazabilidad",
            }
        )

    idtxt = as_text(idtramite).strip()
    return {
        "ok": len(errors) == 0,
        "base": base,
        "idtramite": idtxt,
        "is_idtramite_pymes_pattern_200xxxxx": bool(RUTA_IDTRAMITE_PYMES_RE.match(idtxt)),
        "idtipotramite": cab[0].get("idtipotramite"),
        "tipotramite": as_text(cab[0].get("tipotramite")),
        "estado": as_text(cab[0].get("estado")),
        "counts": {
            "empleador": len(empleadores),
            "trabajador": len(trabajadores),
            "errores": len(errors),
            "warnings": len(warnings),
        },
        "errors": errors,
        "warnings": warnings,
    }


def _ruta_inclusion_validaciones_scope(base: str, estado: str, idtramite: str, limit: int) -> dict[str, Any]:
    ids: list[str] = []
    if idtramite:
        ids = [idtramite]
    else:
        params: dict[str, Any] = {"limit": limit}
        where = ""
        if estado:
            where = "WHERE estado = :estado"
            params["estado"] = estado
        try:
            rows = fetch_all_by_alias(
                base,
                "SELECT idtramite FROM proc_servicios_obtenertramites "
                f"{where} ORDER BY idtramite LIMIT :limit",
                params,
            )
        except (ValueError, SQLAlchemyError) as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Error consultando tramite para validaciones en {base}: {type(exc).__name__}: {exc}",
            )
        ids = [as_text(r.get("idtramite")).strip() for r in rows if as_text(r.get("idtramite")).strip()]

    reports = [_ruta_inclusion_legacy_validaciones(base, idt) for idt in ids]
    total_errors = sum(int(r.get("counts", {}).get("errores", 0)) for r in reports)
    return {
        "ok": total_errors == 0,
        "base": base,
        "scope": {"estado": estado, "idtramite": idtramite, "limit": limit},
        "count_tramites": len(reports),
        "error_count": total_errors,
        "reports": reports,
    }


def _ruta_inclusion_tipo_cargue_local(base: str, idtramite: str, numide: str = "0") -> dict[str, Any]:
    try:
        cab = fetch_all_by_alias(
            base,
            "SELECT idtramite, estado FROM proc_servicios_obtenertramites WHERE idtramite = :idtramite LIMIT 1",
            {"idtramite": idtramite},
        )
        empleador = fetch_all_by_alias(
            base,
            "SELECT * FROM proc_servicios_obtenerempleadortramite WHERE idtramite = :idtramite ORDER BY sr LIMIT 1",
            {"idtramite": idtramite},
        )
        trabajador = fetch_all_by_alias(
            base,
            "SELECT * FROM proc_servicios_obtenertrabajadortramite WHERE idtramite = :idtramite ORDER BY sr LIMIT 1",
            {"idtramite": idtramite},
        )
    except (ValueError, SQLAlchemyError) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Error resolviendo tipoCargue local en {base}: {type(exc).__name__}: {exc}",
        )

    if not cab:
        raise HTTPException(status_code=404, detail=f"idtramite no encontrado: {idtramite}")

    emp = empleador[0] if empleador else {}
    trab = trabajador[0] if trabajador else {}

    # En legacy se decide contra Apolo (TabCon/TabSed). En este clone usamos regla local
    # deterministica para mantener el flujo operativo cuando no hay origen Apolo.
    is_pymes = bool(RUTA_IDTRAMITE_PYMES_RE.match(as_text(idtramite).strip()))
    tipo_tramite = "Afiliacion" if is_pymes else "Afiliacion"
    cont_madre = as_text(idtramite).strip() if is_pymes else as_text(emp.get("numerodocumentoempleador")).strip() or as_text(idtramite).strip()
    concon = ""
    codsede = "1" if tipo_tramite == "Afiliacion" else "Creacion"
    datossede: dict[str, Any] | None = None
    if tipo_tramite == "Afiliacion":
        actividad_emp = as_text(emp.get("actividadeconomicaempleador")).strip()
        clase = actividad_emp[:1] if actividad_emp else ""
        tasa_map = {"1": "0.522", "2": "1.044", "3": "2.436", "4": "4.35", "5": "6.96"}
        datossede = {
            "nom_centro_trabajo": "I" if clase == "1" else (clase if clase else "I"),
            "cod_act_economica_sede": actividad_emp,
            "clase_riesgo_sede": clase,
            "tasa_riesgo_sede": tasa_map.get(clase, ""),
        }

    respuestas = ""
    if as_text(numide).strip() not in {"", "0"}:
        respuestas = f"Nit {as_text(numide).strip()} no validado en Apolo (modo clone local)."

    return {
        "tipo_tramite": tipo_tramite,
        "cont_madre": cont_madre,
        "concon": concon,
        "codsede": codsede,
        "datossede": datossede,
        "codsederror": "NO",
        "respuestas": respuestas,
        "source": "local_clone_inference",
        "context": {
            "idtramite": as_text(cab[0].get("idtramite")),
            "estado": as_text(cab[0].get("estado")),
            "empleador_doc": as_text(emp.get("numerodocumentoempleador")),
            "trabajador_doc": as_text(trab.get("numerodocumento")),
        },
    }


def _legacy_form_section(payload: dict[str, Any], section: str) -> dict[str, Any]:
    raw = payload.get(section)
    if isinstance(raw, dict):
        return raw
    return {}


def _clean_token(v: Any) -> str:
    txt = as_text(v).strip()
    if txt.upper() == "NULL":
        return ""
    return txt


def _only_digits(value: Any) -> str:
    return "".join(ch for ch in as_text(value) if ch.isdigit())


def _extract_between(tokens: list[str], key: str, offset: int = 1) -> str:
    low = _clean_token(key).lower()
    low_norm = _norm_label(key)
    for i, t in enumerate(tokens):
        token = _clean_token(t)
        if token.lower() == low and i + offset < len(tokens):
            return _clean_token(tokens[i + offset])
        if low_norm and _norm_label(token) == low_norm and i + offset < len(tokens):
            return _clean_token(tokens[i + offset])
    return ""


def _norm_label(value: str) -> str:
    txt = unicodedata.normalize("NFKD", _clean_token(value))
    txt = "".join(ch for ch in txt if not unicodedata.combining(ch))
    txt = txt.lower()
    txt = re.sub(r"\s+", " ", txt)
    return txt.strip()


def _extract_between_fuzzy(tokens: list[str], key: str, offset: int = 1) -> str:
    needle = _norm_label(key)
    if not needle:
        return ""
    for i, t in enumerate(tokens):
        if _norm_label(t) == needle and i + offset < len(tokens):
            return _clean_token(tokens[i + offset])
    return ""


def _extract_after_key_non_empty(tokens: list[str], key: str, max_lookahead: int = 40) -> str:
    low = _clean_token(key).lower()
    low_norm = _norm_label(key)
    for i, t in enumerate(tokens):
        token = _clean_token(t)
        if token.lower() == low or (low_norm and _norm_label(token) == low_norm):
            end = min(len(tokens), i + max_lookahead + 1)
            for j in range(i + 1, end):
                v = _clean_token(tokens[j])
                if v:
                    return v
    return ""


def _collect_after_key_non_empty(tokens: list[str], key: str, max_items: int = 4, max_lookahead: int = 80) -> list[str]:
    low = _clean_token(key).lower()
    low_norm = _norm_label(key)
    for i, t in enumerate(tokens):
        token = _clean_token(t)
        if token.lower() == low or (low_norm and _norm_label(token) == low_norm):
            out: list[str] = []
            end = min(len(tokens), i + max_lookahead + 1)
            stop_tokens = {"CC", "CE", "TI", "RC", "PA", "PT", "SC", "CD", "NU", "PE"}
            for j in range(i + 1, end):
                v = _clean_token(tokens[j])
                if not v:
                    continue
                if v.upper() in stop_tokens and out:
                    break
                out.append(v)
                if len(out) >= max_items:
                    break
            return out
    return []


def _extract_after_key_numeric(tokens: list[str], key: str, digits_min: int = 1, digits_max: int = 2, max_lookahead: int = 60) -> str:
    low = _clean_token(key).lower()
    low_norm = _norm_label(key)
    for i, t in enumerate(tokens):
        token = _clean_token(t)
        if token.lower() == low or (low_norm and _norm_label(token) == low_norm):
            end = min(len(tokens), i + max_lookahead + 1)
            for j in range(i + 1, end):
                v = _only_digits(tokens[j])
                if digits_min <= len(v) <= digits_max:
                    return v
    return ""


def _extract_after_key_naturaleza(tokens: list[str], key: str, max_lookahead: int = 60) -> str:
    low = _clean_token(key).lower()
    low_norm = _norm_label(key)
    allowed = {"PRIVADA", "PUBLICA", "PÚBLICA", "MIXTA"}
    for i, t in enumerate(tokens):
        token = _clean_token(t)
        if token.lower() == low or (low_norm and _norm_label(token) == low_norm):
            end = min(len(tokens), i + max_lookahead + 1)
            for j in range(i + 1, end):
                v = _clean_token(tokens[j])
                if not v:
                    continue
                uv = v.upper().rstrip(".")
                if uv in allowed:
                    return v.rstrip(".")
                if v.isdigit() and 1 <= len(v) <= 2:
                    return v
    return ""


def _normalize_zona_token(value: str) -> str:
    v = _clean_token(value).upper()
    if v in {"U", "URBANA"}:
        return "U"
    if v in {"R", "RURAL"}:
        return "R"
    return v


def _parse_empleador_from_contrato_clean(content: str) -> dict[str, str]:
    lines = [ln.strip() for ln in as_text(content).splitlines() if ln.strip()]
    out: dict[str, str] = {
        "tipodocumentoempleador": "",
        "numerodocumentoempleador": "",
        "razonsocialempleador": "",
        "telefonoprincipalempleador": "",
        "telefonocelularempleador": "",
        "direccionempleador": "",
        "ciudadempleador": "",
        "zonaempleador": "",
        "localidadempleador": "",
        "correoelectronicoempleador": "",
        "tipodocumentorepresentantelegal": "",
        "numerodocumentorepresnetantelegal": "",
        "nombrerepresentantelegal": "",
        "correoelectronicorepresentantelegal": "",
        "actividadeconomicaempleador": "",
        "naturalezajuridica": "",
        "tipoempresa": "",
        "tipoafiliacion": "Inicial",
        "tipoaportante": "",
        "arlanteriorempleador": "",
        "fecharadicacion": "",
        "sucursalcodigo": "",
        "iniciocobertura": "",
        "numerocontrato": "",
    }

    def _has_mark_after_label(tokens: list[str], label: str) -> bool:
        label_norm = _norm_label(label)
        for idx, token in enumerate(tokens):
            if _norm_label(token) != label_norm:
                continue
            window = tokens[idx + 1 : idx + 8]
            for candidate in window:
                mark = _clean_token(candidate).upper()
                if mark == "X":
                    return True
                if mark and mark not in {"NULL", "A. AFILIACION", "A. AFILIACIÓN", "B. TRASLADO", "C. TERMINACION DE LA AFILIACION", "C. TERMINACIÓN DE LA AFILIACIÓN"}:
                    break
        return False

    for ln in lines:
        parts = [_clean_token(p) for p in ln.split("|")]
        low_ln = ln.lower()
        norm_ln = _norm_label(ln)

        if "1. apellidos y nombres o razón social" in low_ln:
            # ...|RAZON SOCIAL|2. Tipo de documento|NI|3. Número...|900...
            out["razonsocialempleador"] = _extract_after_key_non_empty(parts, "1. Apellidos y nombres o razón social")
            out["tipodocumentoempleador"] = _extract_after_key_non_empty(parts, "2. Tipo de documento")
            out["numerodocumentoempleador"] = _only_digits(_extract_after_key_non_empty(parts, "3. Número de documento o NIT"))
            if not out["tipodocumentoempleador"]:
                out["tipodocumentoempleador"] = _extract_between_fuzzy(parts, "2. Tipo de documento")
            if not out["numerodocumentoempleador"]:
                out["numerodocumentoempleador"] = _only_digits(_extract_between_fuzzy(parts, "3. Número de documento o NIT"))

        elif "1. tipo de trámite" in low_ln and "2. naturaleza jurídica del empleador" in low_ln:
            # Los formularios limpios del clone suelen venir como:
            # A. Afiliación|...|B. Traslado|...|X|...
            # y no en posiciones fijas.
            if _has_mark_after_label(parts, "B. Traslado"):
                out["tipoafiliacion"] = "Traslado"
            elif _has_mark_after_label(parts, "A. Afiliación") or _has_mark_after_label(parts, "A. Afiliacion"):
                out["tipoafiliacion"] = "Inicial"
            # En el mismo renglón suele venir naturaleza y tipo de aportante.
            nat = _extract_after_key_naturaleza(parts, "2. Naturaleza jurídica del empleador")
            if not nat:
                nat = _extract_between_fuzzy(parts, "2. Naturaleza jurídica del empleador", 2)
            if nat.endswith("."):
                nat = nat[:-1]
            if nat:
                out["naturalezajuridica"] = nat
            tip_ap = _extract_after_key_numeric(parts, "3. Tipo de aportante", digits_min=1, digits_max=2)
            if not tip_ap:
                tip_ap = _extract_between_fuzzy(parts, "3. Tipo de aportante")
            if tip_ap:
                out["tipoaportante"] = _only_digits(tip_ap) or tip_ap

        elif "tipo de negocio homologado" in low_ln:
            tipoempresa = _extract_after_key_numeric(parts, "4. Tipo de negocio homologado", digits_min=1, digits_max=1)
            if not tipoempresa:
                tipoempresa = _only_digits(_extract_between_fuzzy(parts, "4. Tipo de negocio homologado"))
            if tipoempresa:
                out["tipoempresa"] = tipoempresa

        elif "apellidos y nombres del representante legal" in low_ln:
            # 4. Apellidos ...|AP1|AP2|N1|N2
            name_parts = _collect_after_key_non_empty(parts, "4. Apellidos y nombres del Representante Legal", max_items=4)
            name = " ".join([p for p in name_parts if p])
            if name:
                out["nombrerepresentantelegal"] = name

        elif "5. tipo de documento" in low_ln and "7. correo electrónico" in low_ln:
            out["tipodocumentorepresentantelegal"] = _extract_after_key_non_empty(parts, "5. Tipo de documento")
            out["numerodocumentorepresnetantelegal"] = _only_digits(_extract_after_key_non_empty(parts, "6. Número de documento"))
            out["correoelectronicorepresentantelegal"] = _extract_after_key_non_empty(parts, "7. Correo electrónico")

        elif "1. datos de la sede principal" in low_ln:
            out["direccionempleador"] = _extract_after_key_non_empty(parts, "Dirección de la sede principal")
            out["telefonoprincipalempleador"] = _only_digits(_extract_after_key_non_empty(parts, "Teléfono fijo/celular"))

        elif "correo electrónico" in low_ln and parts[:4] == ["", "1", "PRINCIPAL", "Correo electrónico"]:
            if len(parts) > 4 and parts[4]:
                out["correoelectronicoempleador"] = parts[4]

        elif "municipio/distrito" in low_ln and "departamento" in low_ln:
            out["ciudadempleador"] = _extract_after_key_non_empty(parts, "Municipio/Distrito")
            out["zonaempleador"] = _normalize_zona_token(_extract_after_key_non_empty(parts, "Zona"))
            out["localidadempleador"] = _extract_after_key_non_empty(parts, "Localidad/Comuna")
            if not out["ciudadempleador"]:
                out["ciudadempleador"] = _extract_between_fuzzy(parts, "Municipio/Distrito")
            if not out["zonaempleador"]:
                out["zonaempleador"] = _normalize_zona_token(_extract_between_fuzzy(parts, "Zona"))
            if not out["localidadempleador"]:
                out["localidadempleador"] = _extract_between_fuzzy(parts, "Localidad/Comuna")

        elif "naturaleza juridica del empleador" in norm_ln and "tipo de aportante" in norm_ln:
            # ...|2|Privada.|...|01|Empleador.
            nat = _extract_after_key_naturaleza(parts, "2. Naturaleza jurídica del empleador")
            if not nat:
                nat = _extract_between_fuzzy(parts, "2. Naturaleza jurídica del empleador", 2)
            if nat.endswith("."):
                nat = nat[:-1]
            out["naturalezajuridica"] = nat
            out["tipoaportante"] = _extract_after_key_numeric(parts, "3. Tipo de aportante", digits_min=1, digits_max=2)
            if not out["tipoaportante"]:
                out["tipoaportante"] = _only_digits(_extract_between_fuzzy(parts, "3. Tipo de aportante"))

        elif "1. arl de la cual se traslada" in low_ln and "clase de riesgo" in low_ln:
            # ...|II|NULL|2851201|...
            for token in parts:
                t = token.strip()
                if t.isdigit() and len(t) >= 4:
                    out["actividadeconomicaempleador"] = t
                    break
            joined = " ".join(parts)
            arl_match = re.search(r"\b(\d{1,2})\s*-\s*(\d{2})\b", joined)
            if arl_match and not out["arlanteriorempleador"]:
                out["arlanteriorempleador"] = f"{arl_match.group(1)}{arl_match.group(2)}"
            # En contratos legacy de traslado, cuando no viene legible el nombre de ARL,
            # se usa Positiva (10) como fallback operativo histórico.
            if out["tipoafiliacion"].strip().lower() == "traslado" and not out["arlanteriorempleador"]:
                out["arlanteriorempleador"] = "10"

        elif ("2. clase de riesgo" in low_ln) and ("número de sedes" in low_ln or "numero de sedes" in low_ln):
            # Fallback en formatos donde la actividad económica aparece en la línea de
            # "Clase de riesgo / Número de sedes" (ej. 5429001).
            if not out["actividadeconomicaempleador"]:
                for token in parts:
                    d = _only_digits(token)
                    if len(d) == 7:
                        out["actividadeconomicaempleador"] = d
                        break

        elif "fecha de radicación" in low_ln and "fecha inicio de cobertura" in low_ln:
            # encabezado del bloque de fechas; el valor viene en la siguiente línea
            continue
        elif not out["iniciocobertura"] and len(parts) >= 2:
            # línea típica: 2026-02-27T00:00:00|2026-04-01T00:00:00|...
            date_tokens = []
            for t in parts:
                tok = _clean_token(t)
                mdt = re.match(r"^(\d{4}-\d{2}-\d{2})", tok)
                if mdt:
                    date_tokens.append(mdt.group(1))
            if date_tokens:
                out["fecharadicacion"] = date_tokens[0]
            if len(date_tokens) > 1:
                out["iniciocobertura"] = date_tokens[1]
            if not out["numerocontrato"]:
                for t in parts:
                    if "-" in _clean_token(t) or ":" in _clean_token(t):
                        continue
                    d = _only_digits(t)
                    if len(d) >= 6:
                        out["numerocontrato"] = d
                        break
            if not out["sucursalcodigo"]:
                for idx, token in enumerate(parts):
                    token_norm = _norm_label(token)
                    if token_norm == "codigo" or token_norm.startswith("codigo"):
                        for candidate in parts[idx + 1 : idx + 5]:
                            digits = _only_digits(candidate)
                            if digits:
                                out["sucursalcodigo"] = digits[:2]
                                break
                        if out["sucursalcodigo"]:
                            break
            if not out["sucursalcodigo"] and len(parts) >= 5:
                out["sucursalcodigo"] = _only_digits(parts[4])[:2]

        elif low_ln.startswith("14-") and "positiva" in low_ln and not out["arlanteriorempleador"]:
            arl_match = re.search(r"\b(\d{1,2})\s*-\s*(\d{2})\b", ln)
            if arl_match:
                out["arlanteriorempleador"] = f"{arl_match.group(1)}{arl_match.group(2)}"

    # fallback de celular/correo representante si no se obtuvo explícito
    if not out["telefonocelularempleador"]:
        out["telefonocelularempleador"] = out["telefonoprincipalempleador"]
    if not out["correoelectronicoempleador"]:
        out["correoelectronicoempleador"] = out["correoelectronicorepresentantelegal"]
    if out["tipoafiliacion"].strip().lower() == "traslado" and not out["arlanteriorempleador"]:
        out["arlanteriorempleador"] = "10"
    if not out["tipoaportante"]:
        out["tipoaportante"] = "01"

    return out


def _validate_empleador_import_data(data: dict[str, str]) -> list[str]:
    errors: list[str] = []
    required_fields = {
        "tipodocumentoempleador": "Tipo documento empleador",
        "numerodocumentoempleador": "Número documento empleador",
        "razonsocialempleador": "Razón social",
        "direccionempleador": "Dirección empleador",
        "ciudadempleador": "Ciudad empleador",
        "zonaempleador": "Zona empleador",
        "tipodocumentorepresentantelegal": "Tipo doc representante legal",
        "numerodocumentorepresnetantelegal": "No doc representante legal",
        "nombrerepresentantelegal": "Nombre representante legal",
        "actividadeconomicaempleador": "Actividad económica",
        "naturalezajuridica": "Naturaleza jurídica",
        "tipoaportante": "Tipo aportante",
    }
    for key, label in required_fields.items():
        if not _clean_token(data.get(key)):
            errors.append(f"{label} es obligatorio.")

    zona = _clean_token(data.get("zonaempleador")).upper()
    if zona and zona not in {"U", "R"}:
        errors.append("Zona empleador inválida (debe ser U o R).")

    tipo_aportante = _clean_token(data.get("tipoaportante"))
    if tipo_aportante and (not tipo_aportante.isdigit() or len(tipo_aportante) > 2):
        errors.append("Tipo aportante inválido (numérico de 1-2 dígitos).")

    actividad = _clean_token(data.get("actividadeconomicaempleador"))
    if actividad and not actividad.isdigit():
        errors.append("Actividad económica inválida (debe ser numérica).")

    tipoempresa = _clean_token(data.get("tipoempresa"))
    if tipoempresa and tipoempresa not in {"1", "2", "3", "8", "9"}:
        errors.append("tipoempresa inválido (debe ser 1, 2, 3, 8 o 9).")

    mail_emp = _clean_token(data.get("correoelectronicoempleador"))
    if mail_emp and "@" not in mail_emp:
        errors.append("Correo electrónico empleador inválido.")

    mail_rep = _clean_token(data.get("correoelectronicorepresentantelegal"))
    if mail_rep and "@" not in mail_rep:
        errors.append("Correo electrónico representante legal inválido.")

    # Reusar reglas de tipo/doc y naturaleza jurídica del motor.
    rule = RULES_ENGINE.validate_record(
        {
            "tipodocumentoempleador": _clean_token(data.get("tipodocumentoempleador")),
            "numerodocumentoempleador": _clean_token(data.get("numerodocumentoempleador")),
            "naturalezajuridica": _clean_token(data.get("naturalezajuridica")),
        },
        mode="afiliacion",
    )
    if not rule.ok:
        errors.extend(rule.errors)

    return errors


def _parse_sede_from_contrato_clean(content: str) -> dict[str, str]:
    lines = [ln.strip() for ln in as_text(content).splitlines() if ln.strip()]
    out: dict[str, str] = {
        "codigosede": "1",
        "nombresede": "PRINCIPAL",
        "direccion": "",
        "telefono": "",
        "correo": "",
        "ciudad": "",
        "zona": "",
        "localidad": "",
        "departamento": "",
        "tipodocumentoresponsable": "",
        "documentoresponsable": "",
        "nombreresponsable": "",
        "correoresponsable": "",
    }
    resp_ap1 = ""
    resp_ap2 = ""
    resp_n1 = ""
    resp_n2 = ""

    for ln in lines:
        parts = [_clean_token(p) for p in ln.split("|")]
        low_ln = ln.lower()
        norm_ln = _norm_label(ln)

        if "codigo de la sede:" in norm_ln:
            code = _extract_after_key_non_empty(parts, "Código de la sede:")
            if code:
                out["codigosede"] = _only_digits(code) or _clean_token(code)
        if "nombre de la sede:" in norm_ln:
            sede_name = _extract_after_key_non_empty(parts, "Nombre de la sede:")
            if sede_name:
                out["nombresede"] = sede_name.upper()
        if "primer apellido:" in norm_ln:
            resp_ap1 = _extract_after_key_non_empty(parts, "Primer apellido:")
        if "segundo apellido:" in norm_ln:
            resp_ap2 = _extract_after_key_non_empty(parts, "Segundo apellido:")
        if "primer nombre:" in norm_ln:
            resp_n1 = _extract_after_key_non_empty(parts, "Primer nombre:")
        if "segundo nombre:" in norm_ln:
            resp_n2 = _extract_after_key_non_empty(parts, "Segundo nombre:")
        if "municipio:" in norm_ln:
            city = _extract_after_key_non_empty(parts, "Municipio:")
            if city:
                out["ciudad"] = city.upper()
        if "departamento:" in norm_ln:
            dep = _extract_after_key_non_empty(parts, "Departamento:")
            if dep:
                out["departamento"] = dep.upper()
        if "direccion de la sede:" in norm_ln:
            direction = _extract_after_key_non_empty(parts, "Dirección de la sede:")
            if direction:
                out["direccion"] = direction.upper()
        if "zona sede:" in norm_ln:
            zone = _extract_after_key_non_empty(parts, "Zona sede:")
            if zone:
                out["zona"] = _normalize_zona_token(zone)
        if "tipo de documento:" in norm_ln:
            tdoc = _extract_after_key_non_empty(parts, "Tipo de documento:")
            if tdoc:
                out["tipodocumentoresponsable"] = tdoc.upper()
        if "numero de documento:" in norm_ln or "número de documento:" in norm_ln:
            doc = _extract_after_key_non_empty(parts, "Número de documento:")
            if not doc:
                doc = _extract_after_key_non_empty(parts, "Numero de documento:")
            if doc:
                out["documentoresponsable"] = _only_digits(doc) or doc
        if "telefono fijo/celular:" in norm_ln:
            phone = _extract_after_key_non_empty(parts, "Teléfono fijo/celular:")
            if not phone:
                phone = _extract_after_key_non_empty(parts, "Telefono fijo/celular:")
            if phone:
                out["telefono"] = _to_num_text(phone)
        if "correo electronico:" in norm_ln:
            mail = _extract_after_key_non_empty(parts, "Correo electrónico:")
            if not mail:
                mail = _extract_after_key_non_empty(parts, "Correo electronico:")
            if mail:
                out["correoresponsable"] = mail.lower()
        if "correo electronico de la sede:" in norm_ln:
            mail_sede = _extract_after_key_non_empty(parts, "Correo electrónico de la sede:")
            if not mail_sede:
                mail_sede = _extract_after_key_non_empty(parts, "Correo electronico de la sede:")
            if mail_sede:
                out["correo"] = mail_sede.lower()
        if "municipio/distrito" in low_ln:
            city2 = _extract_after_key_non_empty(parts, "Municipio/Distrito")
            city2_u = city2.upper()
            if city2 and city2_u not in {"LOCALIDAD", "ZONA", "DEPARTAMENTO", "MUNICIPIO", "DISTRITO"}:
                out["ciudad"] = city2.upper()
        if "localidad/comuna" in norm_ln:
            loc = _extract_after_key_non_empty(parts, "Localidad/Comuna")
            if loc:
                out["localidad"] = loc.upper()
        if "zona" in norm_ln and not out.get("zona"):
            zone2 = _extract_after_key_non_empty(parts, "Zona")
            if zone2:
                out["zona"] = _normalize_zona_token(zone2)

    if not out["nombreresponsable"]:
        nombre = " ".join([x for x in [resp_ap1, resp_ap2, resp_n1, resp_n2] if x])
        if nombre:
            out["nombreresponsable"] = nombre.upper()
    if not out["correo"]:
        out["correo"] = out["correoresponsable"]
    if not out["nombresede"]:
        out["nombresede"] = "PRINCIPAL"
    return out


def _validate_sede_import_data(data: dict[str, str]) -> list[str]:
    errors: list[str] = []
    required_fields = {
        "codigosede": "Código sede",
        "nombresede": "Nombre sede",
        "direccion": "Dirección sede",
        "ciudad": "Ciudad sede",
        "zona": "Zona sede",
        "tipodocumentoresponsable": "Tipo documento responsable",
        "documentoresponsable": "Documento responsable",
        "nombreresponsable": "Nombre responsable",
    }
    for key, label in required_fields.items():
        if not _clean_token(data.get(key)):
            errors.append(f"{label} es obligatorio.")

    zona = _clean_token(data.get("zona")).upper()
    if zona and zona not in {"U", "R"}:
        errors.append("Zona sede inválida (debe ser U o R).")

    mail_sede = _clean_token(data.get("correo"))
    if mail_sede and "@" not in mail_sede:
        errors.append("Correo sede inválido.")

    mail_resp = _clean_token(data.get("correoresponsable"))
    if mail_resp and "@" not in mail_resp:
        errors.append("Correo responsable inválido.")
    return errors


def _parse_date_from_tokens(day: str, month: str, year: str) -> str:
    dd = _only_digits(_clean_token(day))
    mm = _only_digits(_clean_token(month))
    yy = _only_digits(_clean_token(year))
    if len(dd) == 0 or len(mm) == 0 or len(yy) == 0:
        return ""
    try:
        dt = datetime(int(yy), int(mm), int(dd))
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return ""


def _to_int_safe(value: Any, default: int = 0) -> int:
    txt = _only_digits(_clean_token(value))
    if not txt:
        return default
    try:
        return int(txt)
    except ValueError:
        return default


def _to_num_text(value: Any) -> str:
    txt = _clean_token(value)
    if not txt:
        return "0"
    digits = "".join(ch for ch in txt if ch.isdigit())
    return digits or "0"


def _normalize_ct_code_token(value: Any) -> str:
    """
    Normaliza código de centro de trabajo a formato legacy numérico (6 dígitos).
    Retorna vacío cuando no hay un código válido.
    """
    digits = _only_digits(_clean_token(value))
    if not digits:
        return ""
    if len(digits) > 6:
        digits = digits[-6:]
    try:
        n = int(digits)
    except ValueError:
        return ""
    if n <= 0:
        return ""
    return str(n).zfill(6)


def _parse_money_text(value: Any) -> tuple[str, bool]:
    """
    Convierte montos a entero texto sin inflar por formatos mixtos.
    Retorna (valor_sanitizado, fue_sanitizado).
    """
    txt = _clean_token(value)
    if not txt or txt.upper() == "NULL":
        return "0", False
    compact = re.sub(r"\s+", "", txt)
    if compact.isdigit():
        return compact, False

    seps = {".", ","}
    has_sep = any(ch in compact for ch in seps)
    if has_sep:
        # Caso de miles legible: 1.234.567 o 1,234,567
        if re.match(r"^\d{1,3}([.,]\d{3})+$", compact):
            digits = "".join(ch for ch in compact if ch.isdigit())
            return (digits or "0"), True

        # Caso mixto/decimal contaminado: tomar parte entera previa al último separador.
        if "." in compact and "," in compact:
            cut = max(compact.rfind("."), compact.rfind(","))
            int_part = compact[:cut]
            digits = "".join(ch for ch in int_part if ch.isdigit())
            if digits:
                return digits, True
        else:
            sep = "." if "." in compact else ","
            parts = compact.split(sep)
            if len(parts) >= 2:
                int_join = "".join(parts[:-1]) if len(parts) > 1 else parts[0]
                digits = "".join(ch for ch in int_join if ch.isdigit())
                if digits:
                    return digits, True

    # Fallback conservador: extraer dígitos (evita vacío), pero marcar saneamiento.
    digits = "".join(ch for ch in compact if ch.isdigit())
    return (digits or "0"), True


def _parse_trabajadores_from_sede_clean(
    content: str, cobertura_fallback: str = ""
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    sanitize_warnings: list[dict[str, Any]] = []
    doc_types = {"CC", "CE", "TI", "RC", "PA", "PT", "SC", "CD", "NI"}
    ct_meta_by_code: dict[str, dict[str, str]] = {}

    def _part(parts: list[str], idx: int) -> str:
        if idx < 0 or idx >= len(parts):
            return ""
        val = _clean_token(parts[idx])
        return "" if val.upper() == "NULL" else val

    for line_no, ln in enumerate(as_text(content).splitlines(), start=1):
        line = ln.strip()
        if not line:
            continue
        parts = [_clean_token(p) for p in line.split("|")]
        if len(parts) >= 19 and parts[0].isdigit() and parts[1].isdigit() and parts[2].upper() not in doc_types:
            ct_code = _clean_token(parts[1])
            ct_meta = {
                "ct_nombreactividad": _part(parts, 2).upper(),
                # Layout XLSX clean preserva columnas vacías con NULL:
                # actividad=5, clase=9, ciudad=10, dirección=15, teléfono=17, cotización=34.
                "ct_codigoactividad": _to_num_text(_part(parts, 5) or _part(parts, 3)),
                "ct_claseriesgo": _part(parts, 9) or _part(parts, 4),
                "ct_ciudad": _part(parts, 10),
                "ct_departamento": _part(parts, 12),
                "ct_zona": _part(parts, 14),
                "ct_direccion": _part(parts, 15),
                "ct_telefono": _to_num_text(_part(parts, 17)),
                "ct_correo": _part(parts, 18).lower(),
                "ct_responsable_pa": _part(parts, 21).upper(),
                "ct_responsable_sa": _part(parts, 22).upper(),
                "ct_responsable_pn": _part(parts, 23).upper(),
                "ct_responsable_sn": _part(parts, 24).upper(),
                "ct_responsable_td": _part(parts, 25).upper(),
                "ct_responsable_doc": _to_num_text(_part(parts, 26)),
                "ct_responsable_correo": _part(parts, 27).lower(),
                "ct_montocotizacion": _to_num_text(_part(parts, 34) or _part(parts, 20)),
            }
            ct_meta_by_code[ct_code] = ct_meta
            norm_ct_code = _normalize_ct_code_token(ct_code)
            if norm_ct_code:
                ct_meta_by_code[norm_ct_code] = ct_meta
            continue
        if len(parts) < 31:
            continue
        # Filtrar filas de trabajadores (no cabeceras/centro de trabajo)
        # patrón esperado: idx2=tipo doc, idx3=documento.
        if parts[2].upper() not in doc_types:
            continue
        if not _only_digits(parts[3]):
            continue

        seq = _to_int_safe(parts[0], default=len(rows) + 1)
        # Soportar dos layouts:
        # - legacy compacto (sexo en idx 11)
        # - clean generado desde XLSX (sexo en idx 13, con columnas intermedias NULL)
        sexo_idx = 11
        day_idx, mon_idx, year_idx = 8, 9, 10
        if len(parts) > 13:
            s13 = _clean_token(parts[13]).upper()
            if ("FEM" in s13) or ("MAS" in s13) or s13 in {"F", "M"}:
                sexo_idx = 13
                day_idx, mon_idx, year_idx = 10, 11, 12
        sexo_raw = _clean_token(parts[sexo_idx]).upper() if len(parts) > sexo_idx else ""
        sexo = "F" if "FEM" in sexo_raw else ("M" if "MAS" in sexo_raw else sexo_raw[:1])
        fechanac = _parse_date_from_tokens(
            parts[day_idx] if len(parts) > day_idx else "",
            parts[mon_idx] if len(parts) > mon_idx else "",
            parts[year_idx] if len(parts) > year_idx else "",
        )
        iniciocontrato = ""
        finalizacion = ""
        if len(parts) > 33:
            fi = _clean_token(parts[32])
            ff = _clean_token(parts[33])
            if len(_only_digits(fi)) == 8:
                iniciocontrato = f"{fi[0:4]}-{fi[4:6]}-{fi[6:8]}"
            if len(_only_digits(ff)) == 8:
                finalizacion = f"{ff[0:4]}-{ff[4:6]}-{ff[6:8]}"

        tipoaf_idx = 27 if sexo_idx == 11 else 29
        subtipo_idx = 29 if sexo_idx == 11 else 31
        meses_idx = 34 if sexo_idx == 11 else 36
        valor_contrato_idx = 36 if sexo_idx == 11 else 38
        ingreso_idx = 13 if sexo_idx == 11 else 15
        tipoaf = _to_int_safe(parts[tipoaf_idx], default=0) if len(parts) > tipoaf_idx else 0
        subtipo = _to_int_safe(parts[subtipo_idx], default=0) if len(parts) > subtipo_idx else 0
        meses = _to_int_safe(parts[meses_idx], default=0) if len(parts) > meses_idx else 0
        valor_contrato = _to_num_text(parts[valor_contrato_idx]) if len(parts) > valor_contrato_idx else "0"
        ingreso_mensual_raw = parts[ingreso_idx] if len(parts) > ingreso_idx else ""
        ingreso_mensual, was_sanitized = _parse_money_text(ingreso_mensual_raw)
        if valor_contrato == "0" and ingreso_mensual != "0":
            valor_contrato = ingreso_mensual
        actividad_idx = 31 if sexo_idx == 11 else 33
        actividad = _to_num_text(parts[actividad_idx]) if len(parts) > actividad_idx else "0"
        ct_code = _normalize_ct_code_token(parts[1]) if len(parts) > 1 else ""
        ct_meta = ct_meta_by_code.get(ct_code, {})

        ap2 = _clean_token(parts[5]).upper() if len(parts) > 5 else ""
        if (not ap2 or ap2 == "NULL") and len(parts) > 6:
            ap2 = _clean_token(parts[6]).upper()
        pn = _clean_token(parts[6]).upper() if len(parts) > 6 else ""
        sn = _clean_token(parts[7]).upper() if len(parts) > 7 else ""
        if sexo_idx == 13:
            pn = _clean_token(parts[8]).upper() if len(parts) > 8 else pn
            sn = _clean_token(parts[9]).upper() if len(parts) > 9 else sn

        row = {
            "sr": seq,
            "idtrabajador": seq,
            "codigoct": ct_code,
            "tipodocumento": _clean_token(parts[2]).upper(),
            "numerodocumento": _only_digits(parts[3]),
            "primerapellido": _clean_token(parts[4]).upper(),
            "segundoapellido": ap2,
            "primernombre": pn,
            "segundonombre": sn,
            "fechanacimiento": fechanac or None,
            "sexo": sexo,
            "direccionresidencia": _clean_token(parts[17 if sexo_idx == 11 else 19]).upper() if len(parts) > (17 if sexo_idx == 11 else 19) else "",
            "ciudadresidencia": _clean_token(parts[21 if sexo_idx == 11 else 23]).upper() if len(parts) > (21 if sexo_idx == 11 else 23) else "",
            "localidad": _clean_token(parts[22 if sexo_idx == 11 else 24]).upper() if len(parts) > (22 if sexo_idx == 11 else 24) else "",
            "zona": ("U" if "URB" in _clean_token(parts[23 if sexo_idx == 11 else 25]).upper() else ("R" if "RUR" in _clean_token(parts[23 if sexo_idx == 11 else 25]).upper() else _clean_token(parts[23 if sexo_idx == 11 else 25]).upper()[:1])) if len(parts) > (23 if sexo_idx == 11 else 25) else "",
            "telefono": _to_num_text(parts[18 if sexo_idx == 11 else 20]) if len(parts) > (18 if sexo_idx == 11 else 20) else "0",
            "celular": _to_num_text(parts[19 if sexo_idx == 11 else 21]) if len(parts) > (19 if sexo_idx == 11 else 21) else "0",
            "correoelectronico": _clean_token(parts[20 if sexo_idx == 11 else 22]).lower() if len(parts) > (20 if sexo_idx == 11 else 22) else "",
            "eps": _clean_token(parts[15 if sexo_idx == 11 else 17]).upper() if len(parts) > (15 if sexo_idx == 11 else 17) else "",
            "actividadeconomica": actividad,
            "cargo": _clean_token(parts[12 if sexo_idx == 11 else 14]).upper() if len(parts) > (12 if sexo_idx == 11 else 14) else "",
            "modalidad": _clean_token(parts[26 if sexo_idx == 11 else 28]).upper() if len(parts) > (26 if sexo_idx == 11 else 28) else "",
            "arlanterior": "99",
            "afp": _clean_token(parts[16 if sexo_idx == 11 else 18]).upper() if len(parts) > (16 if sexo_idx == 11 else 18) else "",
            "iniciocontrato": iniciocontrato or None,
            "finalizacioncontrato": finalizacion or None,
            "valorcontrato": valor_contrato,
            "ingresomensual": ingreso_mensual,
            "deducciones": "0",
            "ibc": ingreso_mensual,
            "iniciocobertura": (iniciocontrato or _clean_token(cobertura_fallback) or None),
            "tipoafiliadocotizante": tipoaf,
            "subtipoafiliadocotizante": subtipo,
            "tipo_trabajador_text": _clean_token(parts[28 if sexo_idx == 11 else 30]).upper() if len(parts) > (28 if sexo_idx == 11 else 30) else "",
            "tipocontrato": _clean_token(parts[14 if sexo_idx == 11 else 16]) if len(parts) > (14 if sexo_idx == 11 else 16) else "",
            "jornada": _clean_token(parts[25 if sexo_idx == 11 else 27]).upper() if len(parts) > (25 if sexo_idx == 11 else 27) else "",
            "suministratransporte": ("NO" if "NO" in _clean_token(parts[30 if sexo_idx == 11 else 32]).upper() else "SI") if len(parts) > (30 if sexo_idx == 11 else 32) else "NO",
            "numeromesescontrato": meses,
            "tipotramite": 1,
            "ct_nombreactividad": ct_meta.get("ct_nombreactividad", ""),
            "ct_codigoactividad": ct_meta.get("ct_codigoactividad", ""),
            "ct_claseriesgo": ct_meta.get("ct_claseriesgo", ""),
            "ct_montocotizacion": ct_meta.get("ct_montocotizacion", ""),
            "ct_ciudad": ct_meta.get("ct_ciudad", ""),
            "ct_departamento": ct_meta.get("ct_departamento", ""),
            "ct_zona": ct_meta.get("ct_zona", ""),
            "ct_direccion": ct_meta.get("ct_direccion", ""),
            "ct_telefono": ct_meta.get("ct_telefono", ""),
            "ct_correo": ct_meta.get("ct_correo", ""),
            "ct_responsable_pa": ct_meta.get("ct_responsable_pa", ""),
            "ct_responsable_sa": ct_meta.get("ct_responsable_sa", ""),
            "ct_responsable_pn": ct_meta.get("ct_responsable_pn", ""),
            "ct_responsable_sn": ct_meta.get("ct_responsable_sn", ""),
            "ct_responsable_td": ct_meta.get("ct_responsable_td", ""),
            "ct_responsable_doc": ct_meta.get("ct_responsable_doc", ""),
            "ct_responsable_correo": ct_meta.get("ct_responsable_correo", ""),
        }
        if was_sanitized:
            sanitize_warnings.append(
                {
                    "sede": ct_code,
                    "linea": line_no,
                    "field": "salario",
                    "valor_original": ingreso_mensual_raw,
                    "valor_sanitizado": ingreso_mensual,
                    "documento": row.get("numerodocumento", ""),
                }
            )
        rows.append(row)
    return rows, sanitize_warnings


def _parse_trabajadores_from_legacy_independientes(
    content: str,
    cobertura_fallback: str = "",
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    cfg = LEGACY_ENGINE.TR_LAYOUTS.get("General-Recobrar-6", {})
    fields = list(cfg.get("fields") or [])
    if not fields:
        return rows

    raw_lines = [ln.strip() for ln in as_text(content).splitlines() if ln.strip()]
    # Legacy often serializes rows as row1|row2|... with each row delimited by "!"
    if len(raw_lines) == 1 and "|" in raw_lines[0] and "!" in raw_lines[0]:
        raw_lines = [x.strip() for x in raw_lines[0].split("|") if x.strip()]

    def _to_iso_yyyymmdd(v: Any) -> Optional[str]:
        d = _only_digits(v)
        if len(d) != 8:
            return None
        return f"{d[0:4]}-{d[4:6]}-{d[6:8]}"

    seq = 1
    for ln in raw_lines:
        if "!" not in ln:
            continue
        parts = [_clean_token(p) for p in ln.strip("|").split("!")]
        if len(parts) < len(fields):
            continue
        data = {fields[i]: parts[i] for i in range(len(fields))}
        doc = _only_digits(data.get("documento"))
        if not doc:
            continue
        tdoc = _clean_token(data.get("tipodocumento")).upper()
        if not tdoc:
            continue

        valor_mensual = _to_num_text(data.get("valor_mensual"))
        ibc = _to_num_text(data.get("ibc"))
        if valor_mensual == "0" and ibc != "0":
            valor_mensual = ibc
        valor_contrato = _to_num_text(data.get("valor_contrato"))
        if valor_contrato == "0" and valor_mensual != "0":
            valor_contrato = valor_mensual

        rows.append(
            {
                "sr": _to_int_safe(data.get("sr"), default=seq),
                "idtrabajador": seq,
                "codigoct": _normalize_ct_code_token(data.get("codigo_ct")),
                "tipodocumento": tdoc,
                "numerodocumento": doc,
                "primerapellido": _clean_token(data.get("primer_apellido")).upper(),
                "segundoapellido": _clean_token(data.get("segundo_apellido")).upper(),
                "primernombre": _clean_token(data.get("primer_nombre")).upper(),
                "segundonombre": _clean_token(data.get("segundo_nombre")).upper(),
                "fechanacimiento": _to_iso_yyyymmdd(data.get("fecha_nacimiento")),
                "sexo": _clean_token(data.get("sexo")).upper()[:1],
                "direccionresidencia": _clean_token(data.get("direccion")).upper(),
                "ciudadresidencia": _clean_token(data.get("municipio")).upper(),
                "localidad": _clean_token(data.get("localidad")).upper(),
                "zona": _clean_token(data.get("zona")).upper()[:1] or "U",
                "telefono": _to_num_text(data.get("telefono")),
                "celular": _to_num_text(data.get("celular")),
                "correoelectronico": _clean_token(data.get("correo")).lower(),
                "eps": _clean_token(data.get("codigo_eps") or data.get("eps")).upper(),
                "actividadeconomica": _to_num_text(data.get("actividad_economica")),
                "cargo": "INDEPENDIENTE",
                "modalidad": _clean_token(data.get("modalidad")).upper(),
                "arlanterior": _clean_token(data.get("codigo_arl_anterior") or data.get("arl_anterior")).upper(),
                "afp": _clean_token(data.get("codigo_afp") or data.get("afp")).upper(),
                "iniciocontrato": _to_iso_yyyymmdd(data.get("fecha_inicio_contrato")),
                "finalizacioncontrato": _to_iso_yyyymmdd(data.get("fecha_fin_contrato")),
                "valorcontrato": valor_contrato,
                "ingresomensual": valor_mensual,
                "deducciones": "0",
                "ibc": ibc if ibc != "0" else valor_mensual,
                "iniciocobertura": (_to_iso_yyyymmdd(data.get("fecha_inicio_contrato")) or _clean_token(cobertura_fallback) or None),
                "tipoafiliadocotizante": _to_int_safe(data.get("tipo_cotizante"), default=51),
                "subtipoafiliadocotizante": _to_int_safe(data.get("subtipo_cotizante"), default=0),
                "tipo_trabajador_text": "INDEPENDIENTE",
                "tipocontrato": _clean_token(data.get("tipo_contrato")),
                "jornada": "UNICA",
                "suministratransporte": ("NO" if _clean_token(data.get("transporte")).upper() == "NO" else "SI"),
                "numeromesescontrato": _to_int_safe(data.get("meses_contrato"), default=1),
                "tipotramite": 1,
                "ct_nombreactividad": "",
                "ct_codigoactividad": "",
                "ct_claseriesgo": "",
                "ct_montocotizacion": "",
            }
        )
        seq += 1
    return rows


def _parse_comisiones_from_legacy_text(content: str) -> list[dict[str, str]]:
    """
    Replica la lógica legacy de carga de comisiones (carga contrato):
    - Codigo 1 -> codigo_vendedor 2
    - Codigo 3 -> codigo_vendedor 3
    - Codigo 2 -> se omite
    - default  -> codigo_vendedor 1
    - porcentaje = valor + "00"
    - venta fija = 2
    """
    rows: list[dict[str, str]] = []
    codigo_vendedor = "1"
    vendedor = ""
    skip_current = False
    for ln in as_text(content).splitlines():
        line = ln.strip()
        if not line or ":" not in line:
            continue
        key_raw, val_raw = line.split(":", 1)
        key = _norm_label(key_raw)
        val = _clean_token(val_raw)

        if key == "codigo":
            v = _only_digits(val)
            if v == "1":
                codigo_vendedor = "2"
                skip_current = False
            elif v in {"2", "3"}:
                skip_current = True
            else:
                codigo_vendedor = "1"
                skip_current = False
            continue

        if ("documento" in key and ("nro" in key or "numero" in key)) or key == "nro. de documento":
            vendedor = _only_digits(val)[:10]
            continue

        if "particip" in key or "porcentaje" in key:
            if skip_current:
                continue
            pct = _only_digits(val)
            if vendedor and pct:
                rows.append(
                    {
                        "vendedor": vendedor,
                        "codigo_vendedor": codigo_vendedor,
                        "venta": "2",
                        "porcentaje": f"{pct}00",
                    }
                )
            vendedor = ""
    if rows:
        return rows

    compact = " ".join(as_text(content).split())
    pattern = re.compile(
        r"(?:CODIGO|CÓDIGO)\s+NRO\.?\s+DE\s+DOCUMENTO\s+NOMBRES\s+Y\s+APELLIDOS\s+%\s+DE\s+PARTICIPACI[ÓO]N\s+"
        r"(?P<codigo>\d+)\s+(?P<documento>\d{7,12})\s+(?P<nombre>[A-ZÁÉÍÓÚÑ ]+?)\s+(?P<porcentaje>\d{1,3})%",
        re.IGNORECASE,
    )
    for match in pattern.finditer(compact):
        codigo = _only_digits(match.group("codigo"))
        vendedor = _only_digits(match.group("documento"))[:10]
        pct = _only_digits(match.group("porcentaje"))
        if not vendedor or not pct:
            continue
        if codigo == "1":
            codigo_vendedor = "2"
        elif codigo in {"2", "3"}:
            continue
        else:
            codigo_vendedor = "1"
        rows.append(
            {
                "vendedor": vendedor,
                "codigo_vendedor": codigo_vendedor,
                "venta": "2",
                "porcentaje": f"{pct}00",
            }
        )
    return rows


def _validate_trabajadores_import_data(rows: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    if not rows:
        errors.append("No se detectaron filas de trabajadores en el archivo clean.")
        return errors
    seen_docs: set[str] = set()
    for idx, r in enumerate(rows, start=1):
        doc = _clean_token(r.get("numerodocumento"))
        tdoc = _clean_token(r.get("tipodocumento"))
        if not doc:
            errors.append(f"Fila {idx}: numerodocumento obligatorio.")
        if not tdoc:
            errors.append(f"Fila {idx}: tipodocumento obligatorio.")
        key = f"{tdoc}|{doc}"
        if doc and key in seen_docs:
            errors.append(f"Fila {idx}: trabajador duplicado ({tdoc}-{doc}).")
        seen_docs.add(key)
        if _clean_token(r.get("sexo")) not in {"M", "F"}:
            errors.append(f"Fila {idx}: sexo inválido ({_clean_token(r.get('sexo'))}).")
    return errors


def _proc_log_table_available(base: str) -> bool:
    try:
        get_table_columns_by_alias(base, "proc_log")
        return True
    except NoSuchTableError:
        return False
    except (ValueError, SQLAlchemyError):
        return False


def _proc_log_permite_modificar(base: str, idtramite: str) -> bool:
    if not _proc_log_table_available(base):
        return True
    try:
        rows = fetch_all_by_alias(
            base,
            "SELECT sr FROM proc_log WHERE idtramite = :idtramite ORDER BY sr LIMIT 1",
            {"idtramite": idtramite},
        )
        return len(rows) == 0
    except (ValueError, SQLAlchemyError):
        # Si no se puede validar, no bloqueamos para no frenar operación.
        return True


def _proc_log_insert_change(
    *,
    base: str,
    idtramite: str,
    usuario: str,
    campo: str,
    valor_anterior: Any,
    valor_nuevo: Any,
) -> dict[str, Any]:
    if not _proc_log_table_available(base):
        return {"ok": True, "skipped": True, "reason": "proc_log_no_existe"}
    try:
        inserted = execute_by_alias(
            base,
            "INSERT INTO proc_log (fecha_insert, usuario, campo, valor_anterior, valor_nuevo, idtramite) "
            "VALUES (now(), :usuario, :campo, :valor_anterior, :valor_nuevo, :idtramite)",
            {
                "usuario": usuario,
                "campo": campo,
                "valor_anterior": as_text(valor_anterior),
                "valor_nuevo": as_text(valor_nuevo),
                "idtramite": idtramite,
            },
        )
        return {"ok": inserted > 0, "rows": inserted}
    except (ValueError, SQLAlchemyError) as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _safe_name(name: str, kind: str) -> str:
    cleaned = name.strip()
    if not SAFE_SQL_NAME.match(cleaned):
        raise HTTPException(status_code=400, detail=f"{kind} invalido: {name}")
    return cleaned


def _import_real_lote_to_db(payload: dict[str, Any]) -> dict[str, Any]:
    lote = as_text(payload.get("lote")).strip()
    base = as_text(payload.get("base") or "temporal").strip() or "temporal"
    tables = payload.get("tables")

    if not lote:
        raise HTTPException(status_code=400, detail="Campo requerido: lote")
    if not isinstance(tables, dict) or not tables:
        raise HTTPException(status_code=400, detail="Campo requerido: tables (objeto con listas por tabla)")

    inserted_summary: dict[str, int] = {}
    deleted_summary: dict[str, int] = {}

    for raw_table, rows_any in tables.items():
        table = _safe_name(as_text(raw_table).lower(), "tabla")
        if table not in LOTE_FIELD_BY_TABLE:
            raise HTTPException(status_code=400, detail=f"Tabla no permitida: {table}")
        if not isinstance(rows_any, list):
            raise HTTPException(status_code=400, detail=f"Tabla {table} debe contener una lista")

        preferred_lote_field = LOTE_FIELD_BY_TABLE[table]
        try:
            table_cols = {c.lower() for c in get_table_columns_by_alias(base, table)}
        except NoSuchTableError:
            table_cols = set()
        except (ValueError, SQLAlchemyError) as exc:
            raise HTTPException(
                status_code=503,
                detail=f"No se pudieron leer columnas de {table}: {type(exc).__name__}: {exc}",
            )

        # Auto-create missing target table for clone/import scenarios.
        if not table_cols:
            discovered_cols: set[str] = set()
            for row_any in rows_any:
                if isinstance(row_any, dict):
                    for k in row_any.keys():
                        c = _safe_name(as_text(k).strip().lower(), "columna")
                        if c:
                            discovered_cols.add(c)
            discovered_cols.add(preferred_lote_field)
            if not discovered_cols:
                discovered_cols = {preferred_lote_field}
            create_cols = ", ".join([f"{c} text" for c in sorted(discovered_cols)])
            try:
                execute_by_alias(base, f"CREATE TABLE IF NOT EXISTS {table} ({create_cols})")
                table_cols = {c.lower() for c in get_table_columns_by_alias(base, table)}
            except (ValueError, SQLAlchemyError) as exc:
                raise HTTPException(
                    status_code=503,
                    detail=f"No se pudo crear tabla {table}: {type(exc).__name__}: {exc}",
                )
        if not table_cols:
            raise HTTPException(status_code=400, detail=f"La tabla {table} no tiene columnas visibles")

        # Paridad clone: si la tabla existe con esquema parcial, agregar columnas faltantes
        # detectadas en el payload para no perder datos al insertar.
        discovered_cols: set[str] = set()
        for row_any in rows_any:
            if isinstance(row_any, dict):
                for k in row_any.keys():
                    c = _safe_name(as_text(k).strip().lower(), "columna")
                    if c:
                        discovered_cols.add(c)
        missing_cols = sorted(c for c in discovered_cols if c not in table_cols)
        if missing_cols:
            try:
                for col in missing_cols:
                    execute_by_alias(base, f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} text")
                table_cols = {c.lower() for c in get_table_columns_by_alias(base, table)}
            except (ValueError, SQLAlchemyError) as exc:
                raise HTTPException(
                    status_code=503,
                    detail=f"No se pudieron agregar columnas faltantes en {table}: {type(exc).__name__}: {exc}",
                )

        lote_field = preferred_lote_field
        if lote_field.lower() not in table_cols:
            alt = next((c for c in ("lt", "lote", "nl", "fileid") if c in table_cols), "")
            if not alt:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"La tabla {table} no tiene columna de lote compatible. "
                        f"Esperada '{preferred_lote_field}' o una de lt/lote/nl/fileid."
                    ),
                )
            lote_field = alt

        try:
            deleted = execute_by_alias(base, f"DELETE FROM {table} WHERE {lote_field} = :lote", {"lote": lote})
            deleted_summary[table] = deleted
        except (ValueError, SQLAlchemyError) as exc:
            raise HTTPException(status_code=503, detail=f"Error limpiando {table}: {type(exc).__name__}: {exc}")

        inserted = 0
        for row_any in rows_any:
            if not isinstance(row_any, dict):
                continue
            row = {as_text(k).strip().lower(): row_any[k] for k in row_any.keys()}
            if lote_field not in row:
                if lote_field == "lt" and "lote" in row:
                    row["lt"] = row.get("lote")
                elif lote_field == "lote" and "lt" in row:
                    row["lote"] = row.get("lt")
                elif lote_field == "nl" and "lote" in row:
                    row["nl"] = row.get("lote")
                elif lote_field == "fileid" and "lote" in row:
                    row["fileid"] = row.get("lote")
            if lote_field not in row or as_text(row.get(lote_field)).strip() == "":
                row[lote_field] = lote

            cols = [_safe_name(c, "columna") for c in row.keys() if c and c.lower() in table_cols]
            if not cols:
                continue
            placeholders = ", ".join([f":{c}" for c in cols])
            sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})"
            params = {c: row[c] for c in cols}
            try:
                execute_by_alias(base, sql, params)
                inserted += 1
            except (ValueError, SQLAlchemyError) as exc:
                raise HTTPException(
                    status_code=503,
                    detail=f"Error insertando en {table}: {type(exc).__name__}: {exc}",
                )
        inserted_summary[table] = inserted

    return {
        "ok": True,
        "base": base,
        "lote": lote,
        "tables": {
            "deleted": deleted_summary,
            "inserted": inserted_summary,
        },
    }


def _export_lote_from_db(payload: dict[str, Any]) -> dict[str, Any]:
    lote = as_text(payload.get("lote")).strip()
    base = as_text(payload.get("base") or "temporal").strip() or "temporal"
    include_empty = bool(payload.get("include_empty", False))
    raw_tables = payload.get("tables")

    if not lote:
        raise HTTPException(status_code=400, detail="Campo requerido: lote")

    if raw_tables is None:
        tables = list(REAL_LOTE_TABLES)
    elif isinstance(raw_tables, list) and raw_tables:
        tables = [_safe_name(as_text(t).lower(), "tabla") for t in raw_tables]
    else:
        raise HTTPException(status_code=400, detail="Campo tables debe ser lista no vacia o ausente.")

    out_tables: dict[str, list[dict[str, Any]]] = {}
    counts: dict[str, int] = {}
    for table in tables:
        if table not in LOTE_FIELD_BY_TABLE:
            raise HTTPException(status_code=400, detail=f"Tabla no permitida: {table}")
        lote_field = LOTE_FIELD_BY_TABLE[table]

        try:
            table_cols = {c.lower() for c in get_table_columns_by_alias(base, table)}
        except (ValueError, SQLAlchemyError) as exc:
            raise HTTPException(
                status_code=503,
                detail=f"No se pudieron leer columnas de {table}: {type(exc).__name__}: {exc}",
            )
        if lote_field.lower() not in table_cols:
            alt = next((c for c in ("lt", "lote", "nl", "fileid") if c in table_cols), "")
            if not alt:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"La tabla {table} no tiene columna de lote compatible. "
                        f"Esperada '{lote_field}' o una de lt/lote/nl/fileid."
                    ),
                )
            lote_field = alt

        order_cols = [c for c in ("sr", "li", "linea") if c in table_cols]
        order_clause = f" ORDER BY {', '.join(order_cols)}" if order_cols else ""
        sql = f"SELECT * FROM {table} WHERE {lote_field} = :lote{order_clause}"
        try:
            rows = fetch_all_by_alias(base, sql, {"lote": lote})
        except (ValueError, SQLAlchemyError) as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Error leyendo {table}: {type(exc).__name__}: {exc}",
            )
        counts[table] = len(rows)
        if rows or include_empty:
            out_tables[table] = rows

    return {
        "ok": True,
        "base": base,
        "lote": lote,
        "counts": counts,
        "payload": {
            "base": base,
            "lote": lote,
            "tables": out_tables,
        },
    }


def _clone_lote_between_bases(payload: dict[str, Any]) -> dict[str, Any]:
    lote = as_text(payload.get("lote")).strip()
    source_base = as_text(payload.get("source_base") or "temporal").strip() or "temporal"
    target_base = as_text(payload.get("target_base") or "temporal").strip() or "temporal"
    tables = payload.get("tables")

    if not lote:
        raise HTTPException(status_code=400, detail="Campo requerido: lote")

    export_req: dict[str, Any] = {"lote": lote, "base": source_base, "include_empty": True}
    if tables is not None:
        export_req["tables"] = tables
    exported = _export_lote_from_db(export_req)
    import_payload = {
        "lote": lote,
        "base": target_base,
        "tables": exported["payload"]["tables"],
    }
    imported = _import_real_lote_to_db(import_payload)
    return {
        "ok": True,
        "lote": lote,
        "source_base": source_base,
        "target_base": target_base,
        "counts_source": exported.get("counts", {}),
        "import_result": imported,
    }


@router.get("/legacy/opc/soportados")
def legacy_opc_soportados() -> dict[str, Any]:
    return {"ok": True, "count": len(LEGACY_OPC_SOPORTADOS), "items": sorted(LEGACY_OPC_SOPORTADOS)}


@router.post("/legacy/opc")
def legacy_opc(payload: dict[str, Any]) -> dict[str, Any]:
    return _dispatch(payload)


@router.get("/legacy/db/aliases")
def legacy_db_aliases() -> dict[str, Any]:
    aliases = list_alias_status()
    return {"ok": True, "count": len(aliases), "items": aliases}


@router.get("/legacy/db/ping")
def legacy_db_ping(alias: str) -> dict[str, Any]:
    result = ping_alias(alias)
    if not result.get("ok"):
        raise HTTPException(status_code=503, detail=result)
    return result


@router.post("/legacy/db/bootstrap-demo")
def legacy_db_bootstrap_demo(lote: str = "1001") -> dict[str, Any]:
    lote = lote.strip()
    if not lote:
        raise HTTPException(status_code=400, detail="Parametro requerido: lote")

    statements_temporal = [
        "CREATE TABLE IF NOT EXISTS tr (cb text, fc text, nl text, ob text, us text)",
        "CREATE TABLE IF NOT EXISTS brempresasarp (sr int, lt text, f01 text, f50 text, f48 text, f51 text, f15 text, f12 text, f14 text, f18 text, f59 text, tp text, clase text)",
        "CREATE TABLE IF NOT EXISTS brafiliadosarp (sr int, lt text, li text, f28 text, f29 text, f30 text, f31 text, f32 text, f33 text, f34 text, f35 text, f37 text, f38 text, direccion text, telefono text, celular text, mail text, jornada text, tipo_salario text)",
        "CREATE TABLE IF NOT EXISTS brwddias (sr int, lote text, dia text, h1 text, h2 text, h3 text, h4 text, h5 text, h6 text, h7 text, h8 text, h9 text, h10 text, h11 text, h12 text, h13 text, h14 text, h15 text, h16 text, h17 text, h18 text, h19 text, h20 text, h21 text, h22 text, h23 text, h24 text)",
        "CREATE TABLE IF NOT EXISTS brcentrot (sr int, lote text, codigoct text, codigoactividad text, nombreactividad text, ciudad text, zona text, direccion text, telefono text, tipodocumento text, id_responsable text, primerapellido text, segundoapellido text, primernombre text, segundonombre text)",
        "CREATE TABLE IF NOT EXISTS brwdestudiantes (sr int, lote text, linea text, codigo_ct text, tipodocumento text, documento text, primer_apellido text, segundo_apellido text, primer_nombre text, segundo_nombre text, fecha_nacimiento text, sexo text, cargo text, salario text, eps text, afp text, direccion text, telefono text, celular text, correo text, ciudad text, localidad text, zona text, departamento text, jornada text, modalidad text, codigo_actividad text, fecha_inicio text, fecha_final text, meses text, tipo_contrato text, monto_contrato text, lunes text, martes text, miercoles text, jueves text, viernes text, sabado text, domingo text, d1 text, d2 text, d3 text, d4 text, d5 text, d6 text, d7 text, d8 text, d9 text, d10 text, d11 text, d12 text, d13 text, d14 text, d15 text, d16 text, d17 text, d18 text, d19 text, d20 text, d21 text, d22 text, d23 text, d24 text, tipo_salario text)",
        "CREATE TABLE IF NOT EXISTS brwdindependientes (sr int, lote text, linea text, tipodocumento text, documento text, primer_apellido text, segundo_apellido text, primer_nombre text, segundo_nombre text, fecha_nacimiento text, sexo text, direccion text, departamento text, municipio text, zona text, localidad text, telefono text, celular text, correo text, codigo_eps text, codigo_afp text, ibc text, actividad_economica text, tipo_contrato text, transporte text, fecha_inicio_contrato text, fecha_fin_contrato text, meses_contrato text, valor_contrato text, valor_mensual text, lunes text, martes text, miercoles text, jueves text, viernes text, sabado text, domingo text, d1 text, d2 text, d3 text, d4 text, d5 text, d6 text, d7 text, d8 text, d9 text, d10 text, d11 text, d12 text, d13 text, d14 text, d15 text, d16 text, d17 text, d18 text, d19 text, d20 text, d21 text, d22 text, d23 text, d24 text, codigo_ct text, localidad_ct text, zona_ct text, tipo_cotizante text, subtipo_cotizante text, tipo_salario text)",
        "CREATE TABLE IF NOT EXISTS brwdcomisiones (sr int, lote text, linea text, vendedor text, codigo_vendedor text, venta text, porcentaje text)",
        "DELETE FROM tr WHERE nl = :lote",
        "DELETE FROM brempresasarp WHERE lt = :lote",
        "DELETE FROM brafiliadosarp WHERE lt = :lote",
        "DELETE FROM brwddias WHERE lote = :lote",
        "DELETE FROM brcentrot WHERE lote = :lote",
        "DELETE FROM brwdestudiantes WHERE lote = :lote",
        "DELETE FROM brwdindependientes WHERE lote = :lote",
        "DELETE FROM brwdcomisiones WHERE lote = :lote",
        "INSERT INTO tr(cb,fc,nl,ob,us) VALUES('Afa','20260225',:lote,'Lote demo bootstrap','escobar')",
        "INSERT INTO brempresasarp(sr,lt,f01,f50,f48,f51,f15,f12,f14,f18,f59,tp,clase) VALUES(1,:lote,'9001','0','900100001','EMPRESA DEMO', '11001','CLL 1 # 1-01','1234567','EMPRESA DEMO','20260225','P','Afa')",
        "INSERT INTO brempresasarp(sr,lt,f01,f50,f48,f51,f15,f12,f14,f18,f59,tp,clase) VALUES(2,:lote,'9001','0','900100001','SEDE DEMO', '11001','CLL 2 # 2-02','1234567','SEDE DEMO','20260225','S','Afa')",
        "INSERT INTO brafiliadosarp(sr,lt,li,f28,f29,f30,f31,f32,f33,f34,f35,f37,f38,direccion,telefono,celular,mail,jornada,tipo_salario) VALUES(2,:lote,'1','100200300','1','000001','PEREZ','GOMEZ','ANA','F','19900101','ANALISTA','1500000','CLL 3','1234567','3001234567','ana@demo.com','UNICA','FIJO')",
        "INSERT INTO brwddias(sr,lote,dia,h1,h2,h3,h4,h5,h6,h7,h8,h9,h10,h11,h12,h13,h14,h15,h16,h17,h18,h19,h20,h21,h22,h23,h24) VALUES(2,:lote,'lunes','X','X','X','','','','','','','','','','','','','','','','','','','','','')",
        "INSERT INTO brcentrot(sr,lote,codigoct,codigoactividad,nombreactividad,ciudad,zona,direccion,telefono,tipodocumento,id_responsable,primerapellido,segundoapellido,primernombre,segundonombre) VALUES(2,:lote,'000001','6201','SERVICIOS','11001','U','CLL 5','1234567','CC','12345678','RESP','CT','NOMBRE','DOS')",
        "INSERT INTO brwdestudiantes(sr,lote,linea,codigo_ct,tipodocumento,documento,primer_apellido,segundo_apellido,primer_nombre,segundo_nombre,fecha_nacimiento,sexo,cargo,salario,eps,afp,direccion,telefono,celular,correo,ciudad,localidad,zona,departamento,jornada,modalidad,codigo_actividad,fecha_inicio,fecha_final,meses,tipo_contrato,monto_contrato,lunes,martes,miercoles,jueves,viernes,d1,d2,d3,d4,d5,tipo_salario) VALUES(2,:lote,'1','000001','CC','900200300','EST','DOS','NOMBRE','DOS','20000101','F','PRACTICANTE','1300000','00001','00002','CLL 8','1234567','3001112222','est@demo.com','11001','LOCAL','U','11','UNICA','PRESENCIAL','6201','20260201','20261231','12','1','12000000','X','X','X','X','X','X','','','','','FIJO')",
        "INSERT INTO brwdindependientes(sr,lote,linea,tipodocumento,documento,primer_apellido,segundo_apellido,primer_nombre,segundo_nombre,fecha_nacimiento,sexo,direccion,departamento,municipio,zona,localidad,telefono,celular,correo,codigo_eps,codigo_afp,ibc,actividad_economica,tipo_contrato,transporte,fecha_inicio_contrato,fecha_fin_contrato,meses_contrato,valor_contrato,valor_mensual,lunes,martes,miercoles,jueves,viernes,d1,d2,d3,d4,d5,codigo_ct,localidad_ct,zona_ct,tipo_cotizante,subtipo_cotizante,tipo_salario) VALUES(2,:lote,'1','CC','900300400','INDE','UNO','NOMBRE','DOS','19950101','M','CLL 9','11','11001','U','LOCAL','1234567','3009998888','ind@demo.com','00001','00002','2000000','6201','1','NO','20260201','20261231','12','24000000','2000000','X','X','X','X','X','X','','','','','000001','LOCAL','U','51','0','VARIABLE')",
        "INSERT INTO brwdcomisiones(sr,lote,linea,vendedor,codigo_vendedor,venta,porcentaje) VALUES(3,:lote,'1','123456789','2','1','100')",
    ]

    statements_wimg004 = [
        "CREATE TABLE IF NOT EXISTS lc (fileid text, status text, userid text, nomdoc text, cab text, fl text, ni text, pn text)",
        "DELETE FROM lc WHERE fileid = :lote",
        "INSERT INTO lc(fileid,status,userid,nomdoc,cab,fl,ni,pn) VALUES(:lote,'En Espera','escobar','Afa','2','20260225','1','/tmp/demo')",
    ]

    try:
        for sql in statements_temporal:
            execute_by_alias("temporal", sql, {"lote": lote})
        for sql in statements_wimg004:
            execute_by_alias("wimg004", sql, {"lote": lote})
    except (ValueError, SQLAlchemyError) as exc:
        raise HTTPException(status_code=500, detail=f"Error bootstrap demo: {type(exc).__name__}: {exc}")

    return {"ok": True, "lote": lote, "message": "Datos demo cargados en temporal/wimg004."}


@router.post("/legacy/db/bootstrap-ruta-inclusion-demo")
def legacy_db_bootstrap_ruta_inclusion_demo(base: str = "temporal") -> dict[str, Any]:
    base = as_text(base).strip() or "temporal"
    try:
        stmts = [
            "CREATE TABLE IF NOT EXISTS proc_servicios_obtenertramites (sr int, idtipotramite int, tipotramite text, idestadotipotramite int, estado text, fecharegistro timestamptz, causalestramite text, observacionsolicitudafiliacion text, fecha_insert timestamptz default now(), idtramite numeric)",
            "ALTER TABLE proc_servicios_obtenertramites ADD COLUMN IF NOT EXISTS fecha_insert timestamptz default now()",
            "CREATE TABLE IF NOT EXISTS proc_servicios_obtenerempleadortramite (sr int, tipodocumentoempleador text, numerodocumentoempleador text, telefonoprincipalempleador text, direccionempleador text, telefonocelularempleador text, correoelectronicoempleador text, ciudadempleador text, zonaempleador text, localidadempleador text, nombrerepresentantelegal text, tipodocumentorepresentantelegal text, numerodocumentorepresnetantelegal text, correoelectronicorepresentantelegal text, actividadeconomicaempleador text, razonsocialempleador text, naturalezajuridica text, tipoafiliacion text, tipoaportante text, digito_verificacion text, idtramite numeric, fecha_insert timestamptz default now())",
            "CREATE TABLE IF NOT EXISTS proc_servicios_obtenertrabajadortramite (sr int, idtrabajador int, tipodocumento text, numerodocumento text, primerapellido text, segundoapellido text, primernombre text, segundonombre text, fechanacimiento date, sexo text, direccionresidencia text, ciudadresidencia text, localidad text, zona text, telefono text, celular text, correoelectronico text, eps text, actividadeconomica text, modalidad text, arlanterior text, afp text, iniciocontrato date, finalizacioncontrato date, valorcontrato numeric, ingresomensual numeric, deducciones numeric, ibc numeric, iniciocobertura date, tipoafiliadocotizante int, subtipoafiliadocotizante int, tipocontrato text, jornada text, suministratransporte text, numeromesescontrato numeric, tipotramite int, idtramite numeric)",
            "CREATE TABLE IF NOT EXISTS proc_servicios_obtenerarchivosadjuntos (sr int, idtramite numeric, idarchivosadjuntostramite numeric, idadjuntostipotramite numeric, rutaadjunto text)",
            "CREATE TABLE IF NOT EXISTS proc_servicios_trazabilidad (sr int, idtramite numeric, estado numeric, usuario_asignado text, fecha_asignacion timestamptz default now(), usuario_gestion text, fecha_gestion timestamptz, observacion text, actividad numeric)",
            "CREATE TABLE IF NOT EXISTS proc_servicios_obtenerhoraslaborales (sr int, idtramite numeric, idtrabajador int, dia int, hora int, valor text)",
            "CREATE TABLE IF NOT EXISTS proc_servicios_consulta (idtramite numeric, estado text, fecharegistro timestamptz, numerodocumentoempleador text, razonsocialempleador text, numerodocumento text, nombretrabajador text, actividad text)",
            "CREATE TABLE IF NOT EXISTS proc_servicios_causalesdevolucion (id_causal int, descripcion text, estado int)",
            "CREATE TABLE IF NOT EXISTS pymes_afiliacion_causas_devolucion (id_causal int, descripcion_causal text, estado_causal int)",
            "CREATE TABLE IF NOT EXISTS pymes_afiliacion_sub_causales_devolucion (id_sub_causal int, descripcion_sub_causal text, id_causal int, estado_sub_causal int)",
            "CREATE TABLE IF NOT EXISTS independientes_apolo (idtramite numeric, cont_madre text, cont_independiente text, tipo_tramite text, id_empresa text, nom_empresa text, num_id_trabajador text, pri_ape text, seg_ape text, pri_nom text, seg_nom text, fechainsert timestamptz default now())",
            "CREATE TABLE IF NOT EXISTS proc_log (sr serial primary key, fecha_insert timestamptz default now(), usuario text, campo text, valor_anterior text, valor_nuevo text, idtramite text)",
            "DELETE FROM proc_servicios_obtenertramites WHERE idtramite IN (24370,20012345)",
            "DELETE FROM proc_servicios_obtenerempleadortramite WHERE idtramite IN (24370,20012345)",
            "DELETE FROM proc_servicios_obtenertrabajadortramite WHERE idtramite IN (24370,20012345)",
            "DELETE FROM proc_servicios_obtenerarchivosadjuntos WHERE idtramite IN (24370,20012345)",
            "DELETE FROM proc_servicios_trazabilidad WHERE idtramite IN (24370,20012345)",
            "DELETE FROM proc_servicios_obtenerhoraslaborales WHERE idtramite IN (24370,20012345)",
            "DELETE FROM proc_servicios_consulta WHERE idtramite IN (24370,20012345)",
            "DELETE FROM independientes_apolo WHERE idtramite IN (24370,20012345)",
            "DELETE FROM proc_servicios_causalesdevolucion WHERE id_causal IN (1,2,3)",
            "DELETE FROM pymes_afiliacion_causas_devolucion WHERE id_causal IN (10,11)",
            "DELETE FROM pymes_afiliacion_sub_causales_devolucion WHERE id_sub_causal IN (1001,1002,1101)",
            "INSERT INTO proc_servicios_obtenertramites(sr,idtipotramite,tipotramite,idestadotipotramite,estado,fecharegistro,causalestramite,observacionsolicitudafiliacion,idtramite) VALUES (1,1,'723',1,'Estudio',now(),'','',24370)",
            "INSERT INTO proc_servicios_obtenertramites(sr,idtipotramite,tipotramite,idestadotipotramite,estado,fecharegistro,causalestramite,observacionsolicitudafiliacion,idtramite) VALUES (2,1,'723',1,'Estudio',now(),'','',20012345)",
            "INSERT INTO proc_servicios_obtenerempleadortramite(sr,tipodocumentoempleador,numerodocumentoempleador,telefonoprincipalempleador,direccionempleador,telefonocelularempleador,correoelectronicoempleador,ciudadempleador,zonaempleador,localidadempleador,nombrerepresentantelegal,tipodocumentorepresentantelegal,numerodocumentorepresnetantelegal,correoelectronicorepresentantelegal,actividadeconomicaempleador,razonsocialempleador,naturalezajuridica,tipoafiliacion,tipoaportante,digito_verificacion,idtramite) VALUES (1,'NI','830067597','2202172','CARRERA 59 26 21','3505589763','demo@empresa.test','11001','U','Fontibon','REP DEMO','CC','80721568','rep@empresa.test','5861001','EMPRESA DEMO SAS','Privada','Inicial','05','7',24370)",
            "INSERT INTO proc_servicios_obtenerempleadortramite(sr,tipodocumentoempleador,numerodocumentoempleador,telefonoprincipalempleador,direccionempleador,telefonocelularempleador,correoelectronicoempleador,ciudadempleador,zonaempleador,localidadempleador,nombrerepresentantelegal,tipodocumentorepresentantelegal,numerodocumentorepresnetantelegal,correoelectronicorepresentantelegal,actividadeconomicaempleador,razonsocialempleador,naturalezajuridica,tipoafiliacion,tipoaportante,digito_verificacion,idtramite) VALUES (2,'NI','900555666','6010000','CL 10 # 10-10','3001112222','pymes@empresa.test','11001','U','Chapinero','REP PYMES','CC','90011122','rep.pymes@test','6201','PYMES DEMO SAS','Privada','Inicial','05','5',20012345)",
            "INSERT INTO proc_servicios_obtenertrabajadortramite(sr,idtrabajador,tipodocumento,numerodocumento,primerapellido,segundoapellido,primernombre,segundonombre,fechanacimiento,sexo,direccionresidencia,ciudadresidencia,localidad,zona,telefono,celular,correoelectronico,eps,actividadeconomica,modalidad,arlanterior,afp,iniciocontrato,finalizacioncontrato,valorcontrato,ingresomensual,deducciones,ibc,iniciocobertura,tipoafiliadocotizante,subtipoafiliadocotizante,tipocontrato,jornada,suministratransporte,numeromesescontrato,tipotramite,idtramite) VALUES (1,24315,'CC','80721568','GALVIS','CASTILLO','DAVID','RICARDO','1990-01-01','M','Calle 22A #72B 48','11001','Fontibon','U','4647078','3124146011','davidg8214@gmail.com','5','5861001','A','99','3','2026-01-01','2026-12-31',77700000,19425000,1942500,7770000,'2026-01-01',59,0,'1','0','0',4,1,24370)",
            "INSERT INTO proc_servicios_obtenertrabajadortramite(sr,idtrabajador,tipodocumento,numerodocumento,primerapellido,segundoapellido,primernombre,segundonombre,fechanacimiento,sexo,direccionresidencia,ciudadresidencia,localidad,zona,telefono,celular,correoelectronico,eps,actividadeconomica,modalidad,arlanterior,afp,iniciocontrato,finalizacioncontrato,valorcontrato,ingresomensual,deducciones,ibc,iniciocobertura,tipoafiliadocotizante,subtipoafiliadocotizante,tipocontrato,jornada,suministratransporte,numeromesescontrato,tipotramite,idtramite) VALUES (2,24316,'CC','90012345','LOPEZ','RUIZ','MARIA','ELENA','1995-05-05','F','CL 99 # 12-34','11001','Usaquen','U','6011111','3000000000','maria@test.com','5','6201','A','99','3','2026-02-01','2026-11-30',36000000,3000000,300000,3000000,'2026-02-01',59,0,'1','0','0',10,1,20012345)",
            "INSERT INTO proc_servicios_obtenerarchivosadjuntos(sr,idtramite,idarchivosadjuntostramite,idadjuntostipotramite,rutaadjunto) VALUES (1,24370,49151,1,'D:\\\\PortalSoporteMasivoRutaInclusion\\\\723\\\\ContratoPrestacionServicios_1_1_24370.pdf')",
            "INSERT INTO proc_servicios_obtenerarchivosadjuntos(sr,idtramite,idarchivosadjuntostramite,idadjuntostipotramite,rutaadjunto) VALUES (2,24370,49152,2,'D:\\\\PortalSoporteMasivoRutaInclusion\\\\723\\\\CedulaCiudadania_1_2_24370.pdf')",
            "INSERT INTO proc_servicios_obtenerarchivosadjuntos(sr,idtramite,idarchivosadjuntostramite,idadjuntostipotramite,rutaadjunto) VALUES (3,20012345,59151,1,'D:\\\\PortalSoporteMasivoRutaInclusion\\\\723\\\\ContratoPrestacionServicios_1_1_20012345.pdf')",
            "INSERT INTO proc_servicios_trazabilidad(sr,idtramite,estado,usuario_asignado,fecha_asignacion,usuario_gestion,fecha_gestion,observacion,actividad) VALUES (1,24370,1,'demo_user',now() - interval '1 day',NULL,NULL,'',378)",
            "INSERT INTO proc_servicios_trazabilidad(sr,idtramite,estado,usuario_asignado,fecha_asignacion,usuario_gestion,fecha_gestion,observacion,actividad) VALUES (2,20012345,1,'demo_user',now() - interval '2 day',NULL,NULL,'',378)",
            "INSERT INTO proc_servicios_obtenerhoraslaborales(sr,idtramite,idtrabajador,dia,hora,valor) VALUES (1,24370,24315,1,8,'X')",
            "INSERT INTO proc_servicios_obtenerhoraslaborales(sr,idtramite,idtrabajador,dia,hora,valor) VALUES (2,24370,24315,1,9,'X')",
            "INSERT INTO proc_servicios_obtenerhoraslaborales(sr,idtramite,idtrabajador,dia,hora,valor) VALUES (3,24370,24315,2,8,'X')",
            "INSERT INTO proc_servicios_consulta(idtramite,estado,fecharegistro,numerodocumentoempleador,razonsocialempleador,numerodocumento,nombretrabajador,actividad) VALUES (24370,'Estudio',now(),'830067597','EMPRESA DEMO SAS','80721568','GALVIS CASTILLO DAVID RICARDO','Pendientes Imagine')",
            "INSERT INTO proc_servicios_consulta(idtramite,estado,fecharegistro,numerodocumentoempleador,razonsocialempleador,numerodocumento,nombretrabajador,actividad) VALUES (20012345,'Estudio',now(),'900555666','PYMES DEMO SAS','90012345','LOPEZ RUIZ MARIA ELENA','Pendientes Imagine')",
            "INSERT INTO proc_servicios_causalesdevolucion(id_causal,descripcion,estado) VALUES (1,'Documento incompleto',1)",
            "INSERT INTO proc_servicios_causalesdevolucion(id_causal,descripcion,estado) VALUES (2,'Inconsistencia de datos',1)",
            "INSERT INTO proc_servicios_causalesdevolucion(id_causal,descripcion,estado) VALUES (3,'Firma no válida',1)",
            "INSERT INTO pymes_afiliacion_causas_devolucion(id_causal,descripcion_causal,estado_causal) VALUES (10,'Pymes - Datos faltantes',1)",
            "INSERT INTO pymes_afiliacion_causas_devolucion(id_causal,descripcion_causal,estado_causal) VALUES (11,'Pymes - Documentación inválida',1)",
            "INSERT INTO pymes_afiliacion_sub_causales_devolucion(id_sub_causal,descripcion_sub_causal,id_causal,estado_sub_causal) VALUES (1001,'Cámara de comercio vencida',10,1)",
            "INSERT INTO pymes_afiliacion_sub_causales_devolucion(id_sub_causal,descripcion_sub_causal,id_causal,estado_sub_causal) VALUES (1002,'RUT no legible',10,1)",
            "INSERT INTO pymes_afiliacion_sub_causales_devolucion(id_sub_causal,descripcion_sub_causal,id_causal,estado_sub_causal) VALUES (1101,'Certificado no vigente',11,1)",
            "INSERT INTO independientes_apolo(idtramite,cont_madre,cont_independiente,tipo_tramite,id_empresa,nom_empresa,num_id_trabajador,pri_ape,seg_ape,pri_nom,seg_nom,fechainsert) VALUES (24370,'830067597','IND-24370','Afiliacion','830067597','EMPRESA DEMO SAS','80721568','GALVIS','CASTILLO','DAVID','RICARDO',now())",
            "INSERT INTO independientes_apolo(idtramite,cont_madre,cont_independiente,tipo_tramite,id_empresa,nom_empresa,num_id_trabajador,pri_ape,seg_ape,pri_nom,seg_nom,fechainsert) VALUES (20012345,'20012345','IND-20012345','Afiliacion','900555666','PYMES DEMO SAS','90012345','LOPEZ','RUIZ','MARIA','ELENA',now())",
        ]
        for sql in stmts:
            execute_by_alias(base, sql)
    except (ValueError, SQLAlchemyError) as exc:
        raise HTTPException(status_code=500, detail=f"Error bootstrap ruta inclusion demo: {type(exc).__name__}: {exc}")
    return {"ok": True, "base": base, "message": "Datos demo de Ruta Inclusion cargados.", "idtramites": [24370, 20012345]}


@router.post("/legacy/db/import-real-lote")
def legacy_db_import_real_lote(payload: dict[str, Any]) -> dict[str, Any]:
    return _import_real_lote_to_db(payload)


@router.post("/legacy/db/import-proc-servicios")
def legacy_db_import_proc_servicios(payload: dict[str, Any]) -> dict[str, Any]:
    return _load_proc_servicios_to_engine(payload)


@router.post("/ruta-inclusion/bootstrap-tramite")
def ruta_inclusion_bootstrap_tramite(payload: dict[str, Any]) -> dict[str, Any]:
    base = as_text(payload.get("base") or "temporal").strip() or "temporal"
    idtramite_raw = as_text(payload.get("idtramite")).strip()
    lote = as_text(payload.get("lote")).strip() or idtramite_raw
    estado = as_text(payload.get("estado") or "Estudio").strip() or "Estudio"
    usuario = as_text(payload.get("usuario") or "nova_bridge").strip() or "nova_bridge"
    lote_usuario = _only_digits(payload.get("lote_usuario")) or as_text(payload.get("lote_usuario")).strip()
    fecha_proceso = _only_digits(payload.get("fecha_proceso"))[:8] or datetime.now().strftime("%Y%m%d")
    if not idtramite_raw:
        raise HTTPException(status_code=400, detail="Campo requerido: idtramite")
    if not _only_digits(idtramite_raw):
        raise HTTPException(status_code=400, detail="idtramite debe ser numérico")
    idtramite = _only_digits(idtramite_raw)

    try:
        execute_by_alias(
            base,
            "CREATE TABLE IF NOT EXISTS proc_servicios_obtenertramites ("
            "sr int, idtipotramite int, tipotramite text, idestadotipotramite int, estado text, "
            "fecharegistro timestamptz, causalestramite text, observacionsolicitudafiliacion text, "
            "fecha_insert timestamptz default now(), idtramite numeric, lote text)"
        )
        try:
            execute_by_alias(base, "ALTER TABLE proc_servicios_obtenertramites ADD COLUMN IF NOT EXISTS lote text")
        except (ValueError, SQLAlchemyError):
            pass
        rows = fetch_all_by_alias(
            base,
            "SELECT sr, idtramite FROM proc_servicios_obtenertramites WHERE idtramite = :idtramite LIMIT 1",
            {"idtramite": idtramite},
        )
        if rows:
            updated = execute_by_alias(
                base,
                "UPDATE proc_servicios_obtenertramites "
                "SET estado = :estado, tipotramite = '723', idtipotramite = 1, idestadotipotramite = 1, "
                "fecharegistro = now(), lote = :lote "
                "WHERE idtramite = :idtramite",
                {"idtramite": idtramite, "estado": estado, "lote": lote},
            )
            action = "updated"
            affected = updated
        else:
            max_sr_row = fetch_all_by_alias(
                base,
                "SELECT COALESCE(MAX(sr), 0) AS max_sr FROM proc_servicios_obtenertramites",
                {},
            )
            next_sr = int((max_sr_row[0] or {}).get("max_sr") or 0) + 1
            inserted = execute_by_alias(
                base,
                "INSERT INTO proc_servicios_obtenertramites("
                "sr, idtipotramite, tipotramite, idestadotipotramite, estado, fecharegistro, "
                "causalestramite, observacionsolicitudafiliacion, idtramite, lote"
                ") VALUES ("
                ":sr, 1, '723', 1, :estado, now(), '', '', :idtramite, :lote"
                ")",
                {"sr": next_sr, "idtramite": idtramite, "estado": estado, "lote": lote},
            )
            action = "inserted"
            affected = inserted

        try:
            execute_by_alias(
                base,
                "CREATE TABLE IF NOT EXISTS proc_servicios_trazabilidad ("
                "sr int, idtramite numeric, estado numeric, usuario_asignado text, "
                "fecha_asignacion timestamptz default now(), usuario_gestion text, fecha_gestion timestamptz, "
                "observacion text, actividad numeric)"
            )
            max_tr = fetch_all_by_alias(
                base,
                "SELECT COALESCE(MAX(sr), 0) AS max_sr FROM proc_servicios_trazabilidad WHERE idtramite = :idtramite",
                {"idtramite": idtramite},
            )
            next_tr = int((max_tr[0] or {}).get("max_sr") or 0) + 1
            execute_by_alias(
                base,
                "INSERT INTO proc_servicios_trazabilidad(sr,idtramite,estado,usuario_asignado,observacion,actividad) "
                "VALUES (:sr,:idtramite,1,:usuario,:observacion,378)",
                {"sr": next_tr, "idtramite": idtramite, "usuario": usuario, "observacion": f'Bootstrap NOVA lote {lote}'},
            )
        except (ValueError, SQLAlchemyError):
            pass
        if lote_usuario:
            try:
                execute_by_alias(
                    base,
                    "CREATE TABLE IF NOT EXISTS tr (cb text, fc text, nl text, ob text, us text)",
                )
                execute_by_alias(base, "DELETE FROM tr WHERE cb = 'Afa' AND nl = :nl", {"nl": lote_usuario})
                execute_by_alias(
                    base,
                    "INSERT INTO tr(cb,fc,nl,ob,us) VALUES(:cb,:fc,:nl,:ob,:us)",
                    {
                        "cb": "Afa",
                        "fc": fecha_proceso,
                        "nl": lote_usuario,
                        "ob": f"Bootstrap NOVA lote {lote}",
                        "us": usuario,
                    },
                )
            except (ValueError, SQLAlchemyError):
                pass
    except (ValueError, SQLAlchemyError) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Error bootstrap tramite en {base}: {type(exc).__name__}: {exc}",
        )

    return {
        "ok": affected > 0,
        "base": base,
        "idtramite": idtramite,
        "lote": lote,
        "lote_usuario": lote_usuario,
        "fecha_proceso": fecha_proceso,
        "estado": estado,
        "action": action,
        "rows_affected": affected,
    }


@router.post("/legacy/db/export-lote")
def legacy_db_export_lote(payload: dict[str, Any]) -> dict[str, Any]:
    return _export_lote_from_db(payload)


@router.post("/legacy/db/clone-lote")
def legacy_db_clone_lote(payload: dict[str, Any]) -> dict[str, Any]:
    return _clone_lote_between_bases(payload)


@router.get("/version")
def obtener_version(local_version: Optional[str] = None) -> dict[str, Any]:
    return _version({"opc": "version", "local_version": local_version, "current_version": DEFAULT_VERSION})


@router.post("/planillas/sync")
def sincronizar_planillas(payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    data = payload or {}
    data["opc"] = "traedevoluciones"
    return _sync_planillas(data)


@router.post("/tr/lotes/{lote}/importar")
def importar_lote_tr(lote: str, payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    data = payload or {}
    return _importar_lote_tr(data, lote=lote)


@router.post("/tr/lotes/{lote}/reprocesar")
def reprocesar_lote_tr(lote: str, payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    data = payload or {}
    return _reprocesar_lote_tr(data, lote=lote)


@router.post("/legacy/load-dump")
def legacy_load_dump(payload: dict[str, Any]) -> dict[str, Any]:
    return LEGACY_ENGINE.load_dump(payload)


@router.post("/legacy/engine/sync-from-db")
def legacy_engine_sync_from_db(payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    data = payload or {}
    lote = as_text(data.get("lote")).strip()
    base = as_text(data.get("base") or "temporal").strip() or "temporal"
    lote_usuario = as_text(data.get("lote_usuario")).strip()
    if not lote:
        raise HTTPException(status_code=400, detail="Campo requerido: lote")
    return _sync_engine_from_db(lote=lote, base=base, lote_usuario=lote_usuario)


@router.get("/legacy/engine/lote-usuario-diagnostico")
def legacy_engine_lote_usuario_diagnostico(lote: str, base: str = "temporal") -> dict[str, Any]:
    lote = as_text(lote).strip()
    base = as_text(base).strip() or "temporal"
    if not lote:
        raise HTTPException(status_code=400, detail="Parametro requerido: lote")
    return _diagnose_lote_usuario(base=base, lote=lote)


@router.post("/legacy/normalize")
def legacy_normalize() -> dict[str, Any]:
    return LEGACY_ENGINE.normalize_cd()


@router.post("/legacy/validate")
def legacy_validate() -> dict[str, Any]:
    return LEGACY_ENGINE.validate_cd()


@router.post("/legacy/reproceso")
def legacy_reproceso(payload: dict[str, Any]) -> dict[str, Any]:
    lote = str(payload.get("lote") or "").strip()
    if not lote:
        raise HTTPException(status_code=400, detail="Campo requerido: lote")
    text = LEGACY_ENGINE.reproceso_lote(lote)
    return {"ok": text == "Lote terminado", "response_text": text}


@router.get("/legacy/export/{table}")
def legacy_export_table(table: str) -> Response:
    content = LEGACY_ENGINE.export_table_bytes(table_name=table)
    return Response(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{table}.txt"'},
    )


@router.post("/legacy/byte-compare")
def legacy_byte_compare(payload: dict[str, Any]) -> dict[str, Any]:
    left = str(payload.get("left") or "").encode("utf-8")
    right = str(payload.get("right") or "").encode("utf-8")
    return compare_bytes(left, right)


@router.post("/legacy/flatfile/validate-926")
def legacy_flatfile_validate_926(payload: dict[str, Any]) -> dict[str, Any]:
    content = str(payload.get("content") or "")
    if not content:
        raise HTTPException(status_code=400, detail="Campo requerido: content")
    return _validate_926_structure(content)


@router.post("/legacy/flatfile/load")
def legacy_flatfile_load(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("content"):
        content = str(payload.get("content"))
        return LEGACY_ENGINE.load_flatfile_926(content)
    path = Path(str(payload.get("path") or DEFAULT_ORACLE_FLATFILE))
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Archivo no encontrado: {path}")
    content = path.read_bytes().decode("latin-1", errors="replace")
    out = LEGACY_ENGINE.load_flatfile_926(content)
    out["path"] = str(path)
    return out


@router.post("/legacy/ls/upload-archivo-txt")
def legacy_ls_upload_archivo_txt(payload: dict[str, Any]) -> dict[str, Any]:
    fileid = as_text(payload.get("fileid")).strip()
    content = as_text(payload.get("content"))
    if fileid == "":
        raise HTTPException(status_code=400, detail="Campo requerido: fileid")
    if content.strip() == "":
        raise HTTPException(status_code=400, detail="Campo requerido: content")
    return LEGACY_ENGINE.load_ls_archivo_txt(fileid=fileid, content=content)


@router.get("/legacy/flatfile/generate")
def legacy_flatfile_generate_from_oracle(path: Optional[str] = None) -> Response:
    file_path = Path(path or DEFAULT_ORACLE_FLATFILE)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Archivo no encontrado: {file_path}")
    content = file_path.read_bytes()
    return Response(
        content=content,
        media_type="text/plain; charset=latin-1",
        headers={"Content-Disposition": f'attachment; filename="{file_path.name}"'},
    )


@router.get("/legacy/flatfile/build")
def legacy_flatfile_build(
    lote: str = "",
    from_db: bool = True,
    base: str = "temporal",
    strict_validate: bool = False,
    fecha_proceso: str = "",
    lote_usuario: str = "",
) -> Response:
    if lote and from_db:
        _sync_engine_from_db(lote=lote, base=base, fecha_proceso=fecha_proceso, lote_usuario=lote_usuario)
    precheck = _prebuild_rules_check(lote=lote)
    if strict_validate and not precheck.get("ok", False):
        raise HTTPException(status_code=400, detail={"message": "Prevalidacion de reglas fallo", "precheck": precheck})
    operational = _operational_precheck_926(lote=lote)
    if strict_validate and not operational.get("ok", False):
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Prevalidación operativa 926 falló; hay inconsistencias bloqueantes.",
                "operational_precheck": operational,
            },
        )
    content = LEGACY_ENGINE.generate_flatfile_926(lote=lote)
    if not content:
        raise HTTPException(status_code=404, detail="No hay datos en estado para construir el plano.")
    content_txt = content.decode("latin-1", errors="replace")
    validate_926 = _validate_926_structure(content_txt)
    if strict_validate and not validate_926.get("ok", False):
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Validación estructural/semántica 926 falló.",
                "validate_926": validate_926,
            },
        )
    report = {
        "generated_at": datetime.now().isoformat(),
        "base": base,
        "lote": lote,
        "strict_validate": strict_validate,
        "precheck": precheck,
        "operational_precheck": operational,
        "validate_926": validate_926,
        "line_type_counts": _line_type_counts(content_txt),
        "size_bytes": len(content),
    }
    report_id = _store_flatfile_926_report(report)
    filename = f"BkCargue_{lote}.txt" if lote else "BkCargue_generated.txt"
    history_entry = _persist_926_history_entry(
        lote=lote or "sin_lote",
        base=base,
        report_id=report_id,
        content=content,
        fallback_filename=filename,
    )
    return Response(
        content=content,
        media_type="text/plain; charset=latin-1",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Precheck-Ok": "1" if precheck.get("ok") else "0",
            "X-Precheck-Errors": str(precheck.get("error_count", 0)),
            "X-Precheck-Warnings": str(precheck.get("warning_count", 0)),
            "X-Operational-Precheck-Ok": "1" if operational.get("ok") else "0",
            "X-Operational-Errors": str(operational.get("error_count", 0)),
            "X-Operational-Warnings": str(operational.get("warning_count", 0)),
            "X-926-Valid-Ok": "1" if validate_926.get("ok") else "0",
            "X-Report-Id": report_id,
            "X-Report-Url": f"/api/v1/afiliaciones/legacy/flatfile/report/{report_id}",
            "X-926-History-Id": as_text(history_entry.get("id")),
        },
    )


@router.get("/legacy/flatfile/report/{report_id}")
def legacy_flatfile_report(report_id: str) -> dict[str, Any]:
    report = FLATFILE_926_REPORTS.get(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Reporte 926 no encontrado o expirado.")
    return {"ok": True, "report_id": report_id, "report": report}


@router.get("/legacy/flatfile/history")
def legacy_flatfile_history(limit: int = 50) -> dict[str, Any]:
    lim = max(1, min(int(limit or 50), 500))
    idx = _load_926_history_index()
    rows = sorted(
        idx,
        key=lambda x: as_text(x.get("created_at")),
        reverse=True,
    )[:lim]
    return {"ok": True, "count": len(rows), "rows": rows}


@router.get("/legacy/flatfile/history/{item_id}/download")
def legacy_flatfile_history_download(item_id: str) -> Response:
    idx = _load_926_history_index()
    row = next((r for r in idx if as_text(r.get("id")) == item_id), None)
    if row is None:
        raise HTTPException(status_code=404, detail="Archivo 926 no encontrado en histórico.")
    path = Path(as_text(row.get("path")))
    if not path.exists():
        raise HTTPException(status_code=404, detail="Archivo 926 histórico no existe en disco.")
    filename = as_text(row.get("filename")) or path.name
    content = path.read_bytes()
    return Response(
        content=content,
        media_type="text/plain; charset=latin-1",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/legacy/flatfile/compare-oracle")
def legacy_flatfile_compare_oracle(payload: dict[str, Any]) -> dict[str, Any]:
    lote = str(payload.get("lote") or "").strip()
    from_db = bool(payload.get("from_db", True))
    base = str(payload.get("base") or "temporal").strip() or "temporal"
    sync_info: Optional[dict[str, Any]] = None
    if lote and from_db:
        sync_info = _sync_engine_from_db(lote=lote, base=base)
    precheck = _prebuild_rules_check(lote=lote)
    if bool(payload.get("strict_validate", False)) and not precheck.get("ok", False):
        raise HTTPException(status_code=400, detail={"message": "Prevalidacion de reglas fallo", "precheck": precheck})
    oracle_path = Path(str(payload.get("path") or DEFAULT_ORACLE_FLATFILE))
    if not oracle_path.exists():
        raise HTTPException(status_code=404, detail=f"Archivo oracle no encontrado: {oracle_path}")
    generated = LEGACY_ENGINE.generate_flatfile_926(lote=lote)
    if not generated:
        raise HTTPException(status_code=404, detail="No hay datos en estado para construir el plano.")
    oracle = oracle_path.read_bytes()
    compare = compare_bytes(oracle, generated)
    validate = _validate_926_structure(generated.decode("latin-1", errors="replace"))
    return {
        "ok": compare["equal"],
        "lote": lote,
        "oracle_path": str(oracle_path),
        "sync": sync_info,
        "precheck": precheck,
        "compare": compare,
        "validate_926_generated": validate,
    }


@router.post("/legacy/rules/validate-record")
def legacy_rules_validate_record(payload: dict[str, Any]) -> dict[str, Any]:
    record = payload.get("record")
    if not isinstance(record, dict):
        raise HTTPException(status_code=400, detail="Campo requerido: record (objeto)")
    mode = str(payload.get("mode") or "afiliacion").strip().lower()
    if mode not in {"afiliacion", "novedad"}:
        raise HTTPException(status_code=400, detail="Campo 'mode' debe ser afiliacion o novedad")
    temporales = payload.get("temporales")
    if temporales is not None and not isinstance(temporales, list):
        raise HTTPException(status_code=400, detail="Campo 'temporales' debe ser lista")
    out = RULES_ENGINE.validate_record(record=record, mode=mode, temporales=temporales)
    return {"ok": out.ok, "mode": mode, "errors": out.errors, "derived": out.derived}


@router.post("/legacy/rules/validate-csv")
def legacy_rules_validate_csv(payload: dict[str, Any]) -> dict[str, Any]:
    path_value = str(payload.get("path") or "").strip()
    if not path_value:
        raise HTTPException(status_code=400, detail="Campo requerido: path")
    csv_path = Path(path_value)
    if not csv_path.exists():
        raise HTTPException(status_code=404, detail=f"Archivo no encontrado: {csv_path}")
    mode = str(payload.get("mode") or "afiliacion").strip().lower()
    if mode not in {"afiliacion", "novedad"}:
        raise HTTPException(status_code=400, detail="Campo 'mode' debe ser afiliacion o novedad")

    raw = csv_path.read_text(encoding="utf-8-sig", errors="replace")
    reader = csv.DictReader(raw.splitlines())
    rows = []
    for row in reader:
        rows.append({(k or "").strip(): (v or "").strip() for k, v in row.items()})
    out = RULES_ENGINE.validate_records(rows, mode=mode)
    out["path"] = str(csv_path)
    return out


@router.get("/legacy/rules/prebuild-check")
def legacy_rules_prebuild_check(lote: str = "") -> dict[str, Any]:
    return _prebuild_rules_check(lote=lote)


@router.post("/legacy/rules/prebuild-check")
def legacy_rules_prebuild_check_post(payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    data = payload or {}
    lote = as_text(data.get("lote")).strip()
    from_db = bool(data.get("from_db", False))
    base = as_text(data.get("base") or "temporal").strip() or "temporal"
    sync_info: Optional[dict[str, Any]] = None
    if from_db and lote:
        sync_info = _sync_engine_from_db(lote=lote, base=base)
    prebuild = _prebuild_rules_check(lote=lote)

    expected_map_raw = data.get("excel_sede_totals")
    if isinstance(expected_map_raw, dict) and expected_map_raw:
        expected_totals: dict[str, int] = {}
        for k, v in expected_map_raw.items():
            key = "".join(ch for ch in as_text(k) if ch.isdigit())
            if not key:
                continue
            try:
                expected_totals[str(int(key))] = int(float(as_text(v) or "0"))
            except Exception:
                expected_totals[str(int(key))] = 0
        details_raw = data.get("excel_sede_details")
        details = details_raw if isinstance(details_raw, list) else []
        conc = _prebuild_expected_sede_salary_check(
            lote=lote,
            expected_totals=expected_totals,
            expected_details=details,
        )
        return {
            "ok": bool(prebuild.get("ok", False)) and bool(conc.get("ok", False)),
            "lote": lote,
            "sync": sync_info,
            "prebuild": prebuild,
            "xlsx_sede_salary_check": conc,
        }

    excel_b64 = as_text(data.get("excel_file_base64")).strip()
    if not excel_b64:
        return prebuild

    try:
        excel_bytes = base64.b64decode(excel_b64, validate=False)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"excel_file_base64 inválido: {type(exc).__name__}: {exc}")

    conc = _prebuild_xlsx_sede_salary_check(lote=lote, excel_bytes=excel_bytes)
    return {
        "ok": bool(prebuild.get("ok", False)) and bool(conc.get("ok", False)),
        "lote": lote,
        "sync": sync_info,
        "prebuild": prebuild,
        "xlsx_sede_salary_check": conc,
    }


@router.post("/legacy/reporte-ejecutivo-contrato")
def legacy_reporte_ejecutivo_contrato(payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    data = payload or {}
    lote = as_text(data.get("lote")).strip()
    if not lote:
        raise HTTPException(status_code=400, detail="Campo requerido: lote")
    from_db = bool(data.get("from_db", False))
    base = as_text(data.get("base")).strip() or "temporal"

    excel_b64 = as_text(data.get("excel_file_base64")).strip()
    excel_bytes: Optional[bytes] = None
    if excel_b64:
        try:
            excel_bytes = base64.b64decode(excel_b64, validate=False)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"excel_file_base64 inválido: {type(exc).__name__}: {exc}")

    flat_926_b64 = as_text(data.get("flatfile_926_base64")).strip()
    flat_926_content = ""
    if flat_926_b64:
        try:
            flat_926_content = base64.b64decode(flat_926_b64, validate=False).decode("latin-1", errors="replace")
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"flatfile_926_base64 inválido: {type(exc).__name__}: {exc}")

    out = _contract_executive_report(
        lote=lote,
        from_db=from_db,
        base=base,
        excel_bytes=excel_bytes,
        flatfile_926_content=flat_926_content,
        generate_926_if_missing=bool(data.get("generate_926_if_missing", True)),
    )
    return out


@router.post("/legacy/rules/reproceso-lote")
def legacy_rules_reproceso_lote(payload: dict[str, Any]) -> dict[str, Any]:
    lote = str(payload.get("lote") or "").strip()
    if not lote:
        raise HTTPException(status_code=400, detail="Campo requerido: lote")
    from_db = bool(payload.get("from_db", False))
    base = str(payload.get("base") or "temporal").strip() or "temporal"
    if from_db:
        _sync_engine_from_db(lote=lote, base=base)

    precheck = _prebuild_rules_check(lote=lote)
    apply = bool(payload.get("apply", False))
    include_warnings = bool(payload.get("include_warnings", True))
    split = _reproceso_split_by_precheck(lote=lote, precheck=precheck, apply=apply)
    observaciones_csv = _observaciones_csv(lote=lote, precheck=precheck, include_warnings=include_warnings)

    return {
        "ok": precheck.get("ok", False),
        "lote": lote,
        "from_db": from_db,
        "base": base,
        "applied": apply,
        "precheck": precheck,
        "split": split,
        "observaciones_csv": observaciones_csv,
    }


@router.get("/ruta-inclusion/adjuntos/{idtramite}")
def ruta_inclusion_adjuntos_get(
    idtramite: str,
    base: str = "temporal",
    stage_copy: bool = False,
    overwrite: bool = True,
    transfer_mode: str = "",
) -> dict[str, Any]:
    sql = (
        "SELECT idtramite, idarchivosadjuntostramite, idadjuntostipotramite, rutaadjunto "
        "FROM proc_servicios_obtenerarchivosadjuntos "
        "WHERE idtramite = :idtramite "
        "ORDER BY idarchivosadjuntostramite"
    )
    try:
        rows = fetch_all_by_alias(base, sql, {"idtramite": idtramite})
    except (ValueError, SQLAlchemyError) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Error consultando proc_servicios_obtenerarchivosadjuntos en {base}: {type(exc).__name__}: {exc}",
        )

    enriched = []
    for row in rows:
        raw = as_text(row.get("rutaadjunto"))
        resolved = RUTA_ADJ_SERVICE.resolve_origen(raw)
        enriched.append({**row, "rutaadjunto_resuelta": resolved})

    stage_result: dict[str, Any] | None = None
    if stage_copy and enriched:
        stage_result = RUTA_ADJ_SERVICE.stage_many(
            enriched,
            overwrite=overwrite,
            mode=(transfer_mode.strip().lower() if transfer_mode else None),
        )

    return {
        "ok": True,
        "base": base,
        "idtramite": idtramite,
        "count": len(enriched),
        "can_be_zero_one_many": True,
        "tipotramite_constante": {"idtipotramite": 1, "tipotramite": "723"},
        "estados_operativos": ["Devuelto", "Afiliado", "Estudio"],
        "rows": enriched,
        "staging": stage_result,
        "consume_behavior": {
            "pendientes_sp": "consume",
            "detalle_empleador_trabajador": "re-consultable",
            "devolucion": "genera_nuevo_idtramite",
        },
        "destino_pattern": f"{RUTA_ADJ_SERVICE.settings.destino_root}/YYYYMMDD/{RUTA_ADJ_SERVICE.settings.destino_subpath}/<basename>",
    }


@router.post("/ruta-inclusion/adjuntos/importar-desde-ls")
def ruta_inclusion_adjuntos_importar_desde_ls(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Vuelca contenido LS (archivo_txt por fileid) a proc_servicios_obtenerarchivosadjuntos
    para visibilidad de TODOS los PDFs del manifiesto en el trámite.
    """
    base = as_text(payload.get("base") or "temporal").strip() or "temporal"
    idtramite = as_text(payload.get("idtramite")).strip()
    fileid = as_text(payload.get("fileid")).strip()
    replace_existing = bool(payload.get("replace_existing", True))
    if not idtramite:
        raise HTTPException(status_code=400, detail="Campo requerido: idtramite")
    if not fileid:
        raise HTTPException(status_code=400, detail="Campo requerido: fileid")

    try:
        execute_by_alias(
            base,
            "CREATE TABLE IF NOT EXISTS proc_servicios_obtenerarchivosadjuntos ("
            "sr int, idtramite numeric, idarchivosadjuntostramite numeric, idadjuntostipotramite numeric, rutaadjunto text)"
        )
    except (ValueError, SQLAlchemyError) as exc:
        raise HTTPException(status_code=503, detail=f"Error preparando tabla adjuntos en {base}: {type(exc).__name__}: {exc}")

    ls = _dispatch({"sw": "LS", "sw1": "archivo_txt", "fileid": fileid})
    raw = as_text(ls.get("response_text"))
    if not raw or raw == "0":
        return {"ok": False, "base": base, "idtramite": idtramite, "fileid": fileid, "inserted": 0, "source_rows": 0}

    parsed: list[dict[str, Any]] = []
    for token in [x.strip() for x in raw.split("|") if x.strip()]:
        if "," not in token:
            continue
        ruta, tipo = token.rsplit(",", 1)
        ruta = ruta.strip()
        if not ruta:
            continue
        tipo_num = int(tipo) if tipo.strip().isdigit() else 0
        parsed.append({"rutaadjunto": ruta, "idadjuntostipotramite": tipo_num})

    if not parsed:
        return {"ok": False, "base": base, "idtramite": idtramite, "fileid": fileid, "inserted": 0, "source_rows": 0}

    try:
        if replace_existing:
            execute_by_alias(
                base,
                "DELETE FROM proc_servicios_obtenerarchivosadjuntos WHERE idtramite = :idtramite",
                {"idtramite": idtramite},
            )

        max_rows = fetch_all_by_alias(
            base,
            "SELECT COALESCE(MAX(idarchivosadjuntostramite), 0) AS max_id FROM proc_servicios_obtenerarchivosadjuntos",
        )
        max_id = int(max_rows[0].get("max_id") or 0) if max_rows else 0

        inserted = 0
        for idx, row in enumerate(parsed, start=1):
            execute_by_alias(
                base,
                "INSERT INTO proc_servicios_obtenerarchivosadjuntos("
                "sr,idtramite,idarchivosadjuntostramite,idadjuntostipotramite,rutaadjunto"
                ") VALUES ("
                ":sr,:idtramite,:idarchivosadjuntostramite,:idadjuntostipotramite,:rutaadjunto)",
                {
                    "sr": idx,
                    "idtramite": idtramite,
                    "idarchivosadjuntostramite": max_id + idx,
                    "idadjuntostipotramite": row["idadjuntostipotramite"],
                    "rutaadjunto": row["rutaadjunto"],
                },
            )
            inserted += 1
    except (ValueError, SQLAlchemyError) as exc:
        raise HTTPException(status_code=503, detail=f"Error importando adjuntos LS en {base}: {type(exc).__name__}: {exc}")

    return {
        "ok": inserted > 0,
        "base": base,
        "idtramite": idtramite,
        "fileid": fileid,
        "inserted": inserted,
        "source_rows": len(parsed),
    }


@router.post("/ruta-inclusion/retention/cleanup")
def ruta_inclusion_retention_cleanup(payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    data = payload or {}
    keep_days = int(data.get("keep_days") or 180)
    dry_run = bool(data.get("dry_run", True))
    return RUTA_ADJ_SERVICE.cleanup_retention(keep_days=keep_days, dry_run=dry_run)


@router.get("/ruta-inclusion/causales")
def ruta_inclusion_causales(base: str = "temporal", only_active: bool = True) -> dict[str, Any]:
    try:
        cols = get_table_columns_by_alias(base, "proc_servicios_causalesdevolucion")
    except NoSuchTableError:
        return {"ok": True, "base": base, "count": 0, "items": [], "warning": "tabla_no_existe"}
    except (ValueError, SQLAlchemyError) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Error consultando causales en {base}: {type(exc).__name__}: {exc}",
        )
    cols_low = {c.lower() for c in cols}
    where = " WHERE estado = 1" if only_active and "estado" in cols_low else ""
    sql = f"SELECT * FROM proc_servicios_causalesdevolucion{where} ORDER BY id_causal"
    try:
        items = fetch_all_by_alias(base, sql)
    except (ValueError, SQLAlchemyError) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Error leyendo causales en {base}: {type(exc).__name__}: {exc}",
        )
    return {"ok": True, "base": base, "count": len(items), "items": items}


def _ruta_inclusion_pymes_causales(base: str, idtramite: str) -> list[dict[str, Any]]:
    try:
        cols = {c.lower() for c in get_table_columns_by_alias(base, "pymes_afiliacion_causas_devolucion")}
    except (NoSuchTableError, ValueError, SQLAlchemyError):
        return []
    if not {"id_causal", "descripcion_causal"}.issubset(cols):
        return []
    # En legacy el filtro usa clase_contri según tipo_contri. En clone mantenemos activos sin bloquear por esa dimensión.
    where = " WHERE estado_causal = 1" if "estado_causal" in cols else ""
    try:
        return fetch_all_by_alias(
            base,
            "SELECT id_causal, descripcion_causal "
            "FROM pymes_afiliacion_causas_devolucion"
            f"{where} ORDER BY id_causal",
        )
    except (ValueError, SQLAlchemyError):
        return []


def _ruta_inclusion_pymes_subcausales(base: str, causal_ids: list[str]) -> list[dict[str, Any]]:
    if not causal_ids:
        return []
    try:
        cols = {c.lower() for c in get_table_columns_by_alias(base, "pymes_afiliacion_sub_causales_devolucion")}
    except (NoSuchTableError, ValueError, SQLAlchemyError):
        return []
    if not {"id_sub_causal", "descripcion_sub_causal", "id_causal"}.issubset(cols):
        return []
    ids = [c for c in (as_text(x).strip() for x in causal_ids) if c.isdigit()]
    if not ids:
        return []
    in_list = ",".join(ids)
    where = f" WHERE id_causal IN ({in_list})"
    if "estado_sub_causal" in cols:
        where += " AND estado_sub_causal = 1"
    try:
        return fetch_all_by_alias(
            base,
            "SELECT id_sub_causal, descripcion_sub_causal, id_causal "
            "FROM pymes_afiliacion_sub_causales_devolucion"
            f"{where} ORDER BY id_sub_causal",
        )
    except (ValueError, SQLAlchemyError):
        return []


def _ruta_inclusion_informe_rows(base: str, fecha_inicio: str, fecha_fin: str) -> list[dict[str, Any]]:
    sql = """
    SELECT
      t.idtramite,
      t.estado,
      CAST(t.fecharegistro AS date) AS fecharegistro,
      e.tipodocumentoempleador,
      e.numerodocumentoempleador,
      e.telefonoprincipalempleador,
      e.direccionempleador,
      e.telefonocelularempleador,
      e.correoelectronicoempleador,
      e.ciudadempleador,
      e.zonaempleador,
      e.localidadempleador,
      e.nombrerepresentantelegal,
      e.tipodocumentorepresentantelegal,
      e.numerodocumentorepresnetantelegal,
      e.correoelectronicorepresentantelegal,
      e.actividadeconomicaempleador,
      e.razonsocialempleador,
      e.naturalezajuridica,
      e.tipoafiliacion,
      e.tipoaportante,
      w.tipodocumento,
      w.numerodocumento,
      w.primerapellido,
      w.segundoapellido,
      w.primernombre,
      w.segundonombre,
      w.fechanacimiento,
      w.sexo,
      w.direccionresidencia,
      w.ciudadresidencia,
      w.localidad,
      w.zona,
      w.telefono,
      w.celular,
      w.correoelectronico,
      w.eps,
      w.actividadeconomica,
      w.modalidad,
      w.arlanterior,
      w.afp,
      w.iniciocontrato,
      w.finalizacioncontrato,
      w.valorcontrato,
      w.ingresomensual,
      w.deducciones,
      w.ibc,
      w.iniciocobertura,
      w.tipoafiliadocotizante,
      w.subtipoafiliadocotizante,
      w.tipocontrato,
      w.jornada,
      w.suministratransporte,
      w.numeromesescontrato,
      w.tipotramite,
      (SELECT MAX(tr.fecha_asignacion) FROM proc_servicios_trazabilidad tr WHERE tr.idtramite = t.idtramite) AS fecha_ultima_asignacion,
      (SELECT MAX(tr.fecha_gestion) FROM proc_servicios_trazabilidad tr WHERE tr.idtramite = t.idtramite) AS fecha_ultima_gestion,
      (SELECT tr2.actividad FROM proc_servicios_trazabilidad tr2 WHERE tr2.idtramite = t.idtramite ORDER BY tr2.sr DESC LIMIT 1) AS etapa,
      t.causalestramite AS causales_devolucion,
      t.observacionsolicitudafiliacion AS observacion_devolucion
    FROM proc_servicios_obtenertramites t
    INNER JOIN proc_servicios_obtenerempleadortramite e ON e.idtramite = t.idtramite
    INNER JOIN proc_servicios_obtenertrabajadortramite w ON w.idtramite = t.idtramite
    WHERE CAST(t.fecharegistro AS date) BETWEEN :fecha_inicio AND :fecha_fin
    ORDER BY t.idtramite, w.sr
    """
    try:
        return fetch_all_by_alias(
            base,
            sql,
            {"fecha_inicio": fecha_inicio, "fecha_fin": fecha_fin},
        )
    except (ValueError, SQLAlchemyError) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Error generando informe ruta inclusion en {base}: {type(exc).__name__}: {exc}",
        )


def _ruta_inclusion_informe_csv(base: str, fecha_inicio: str, fecha_fin: str) -> tuple[str, int]:
    rows = _ruta_inclusion_informe_rows(base=base, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin)
    headers = [
        "Id tramite", "Estado", "Fecha Registro", "Tipo Documento Empleador", "Numero Documento Empleador",
        "Telefono Principal Empleador", "Direccion Empleador", "Telefono Celular Empleador",
        "Correo Electronico Empleador", "Ciudad Empleador", "Zona Empleador", "Localidad Empleador",
        "Nombre Representante Legal", "Tipo Documento Representante Legal", "Numero Documento Represnetante Legal",
        "Correo Electronico Representante Legal", "Actividad Economica Empleador", "Razon Social Empleador",
        "Naturaleza Juridica", "Tipo Afiliacion", "Tipo Aportante", "Tipo Documento", "Numero Documento",
        "Primer Apellido", "Segundo Apellido", "Primer Nombre", "Segundo Nombre", "Fecha Nacimiento", "Sexo",
        "Direccion Residencia", "Ciudad Residencia", "Localidad", "Zona", "Telefono", "Celular", "Correo Electronico",
        "Eps", "Actividad Economica", "Modalidad", "Arl Anterior", "Afp", "Inicio Contrato", "Finalizacion Contrato",
        "Valor Contrato", "Ingreso Mensual", "Deducciones", "Ibc", "Inicio Cobertura", "Tipo Afiliado Cotizante",
        "Subtipo Afiliado Cotizante", "Tipo Contrato", "Jornada", "Suministra Transporte", "Numero Meses Contrato",
        "Tipo Tramite", "Fecha Ultima Asignacion", "Fecha Ultima Gestion", "Etapa", "Causales Devolucion",
        "Observacion Devolucion", "Contrato Madre", "Contrato Independiente",
    ]
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(headers)
    for r in rows:
        writer.writerow(
            [
                as_text(r.get("idtramite")),
                as_text(r.get("estado")),
                as_text(r.get("fecharegistro")),
                as_text(r.get("tipodocumentoempleador")),
                as_text(r.get("numerodocumentoempleador")),
                as_text(r.get("telefonoprincipalempleador")),
                as_text(r.get("direccionempleador")),
                as_text(r.get("telefonocelularempleador")),
                as_text(r.get("correoelectronicoempleador")),
                as_text(r.get("ciudadempleador")),
                as_text(r.get("zonaempleador")),
                as_text(r.get("localidadempleador")),
                as_text(r.get("nombrerepresentantelegal")),
                as_text(r.get("tipodocumentorepresentantelegal")),
                as_text(r.get("numerodocumentorepresnetantelegal")),
                as_text(r.get("correoelectronicorepresentantelegal")),
                as_text(r.get("actividadeconomicaempleador")),
                as_text(r.get("razonsocialempleador")),
                as_text(r.get("naturalezajuridica")),
                as_text(r.get("tipoafiliacion")),
                as_text(r.get("tipoaportante")),
                as_text(r.get("tipodocumento")),
                as_text(r.get("numerodocumento")),
                as_text(r.get("primerapellido")),
                as_text(r.get("segundoapellido")),
                as_text(r.get("primernombre")),
                as_text(r.get("segundonombre")),
                as_text(r.get("fechanacimiento")),
                as_text(r.get("sexo")),
                as_text(r.get("direccionresidencia")),
                as_text(r.get("ciudadresidencia")),
                as_text(r.get("localidad")),
                as_text(r.get("zona")),
                as_text(r.get("telefono")),
                as_text(r.get("celular")),
                as_text(r.get("correoelectronico")),
                as_text(r.get("eps")),
                as_text(r.get("actividadeconomica")),
                as_text(r.get("modalidad")),
                as_text(r.get("arlanterior")),
                as_text(r.get("afp")),
                as_text(r.get("iniciocontrato")),
                as_text(r.get("finalizacioncontrato")),
                as_text(r.get("valorcontrato")),
                as_text(r.get("ingresomensual")),
                as_text(r.get("deducciones")),
                as_text(r.get("ibc")),
                as_text(r.get("iniciocobertura")),
                as_text(r.get("tipoafiliadocotizante")),
                as_text(r.get("subtipoafiliadocotizante")),
                as_text(r.get("tipocontrato")),
                as_text(r.get("jornada")),
                as_text(r.get("suministratransporte")),
                as_text(r.get("numeromesescontrato")),
                as_text(r.get("tipotramite")),
                as_text(r.get("fecha_ultima_asignacion")),
                as_text(r.get("fecha_ultima_gestion")),
                as_text(r.get("etapa")),
                as_text(r.get("causales_devolucion")),
                as_text(r.get("observacion_devolucion")),
                "",
                "",
            ]
        )
    return out.getvalue(), len(rows)


def _ri_days_between_festivos(base: str, from_dt: str, to_dt: str) -> int:
    if not from_dt or not to_dt:
        return 0
    ymd_a = _yyyymmdd(from_dt)
    ymd_b = _yyyymmdd(to_dt)
    if not ymd_a or not ymd_b:
        return 0
    try:
        cols = {c.lower() for c in get_table_columns_by_alias(base, "festivos")}
        if "festivos" in cols:
            rows = fetch_all_by_alias(
                base,
                "SELECT count(*) AS dias FROM festivos WHERE festivos BETWEEN :a AND :b",
                {"a": ymd_a, "b": ymd_b},
            )
            cnt = int(rows[0].get("dias") or 0) if rows else 0
            return max(cnt - 1, 0) if cnt > 0 else 0
    except (NoSuchTableError, ValueError, SQLAlchemyError):
        pass
    # Fallback si no existe festivos: diferencia calendario.
    try:
        d1 = datetime.fromisoformat(as_text(from_dt)[:19].replace("Z", "+00:00"))
        d2 = datetime.fromisoformat(as_text(to_dt)[:19].replace("Z", "+00:00"))
        return max((d2.date() - d1.date()).days, 0)
    except ValueError:
        return 0


def _ruta_inclusion_informe_consolidado_rows(base: str, fecha_inicio: str, fecha_fin: str) -> list[dict[str, Any]]:
    sql = """
    SELECT
      c.idtramite,
      c.estado,
      e.tipodocumentoempleador,
      e.numerodocumentoempleador,
      t.fecharegistro,
      (SELECT tr.fecha_asignacion FROM proc_servicios_trazabilidad tr WHERE tr.idtramite = c.idtramite AND tr.actividad = 376 ORDER BY tr.sr LIMIT 1) AS fecha_recepcion_imagine,
      (SELECT tr.fecha_asignacion FROM proc_servicios_trazabilidad tr WHERE tr.idtramite = c.idtramite AND tr.actividad = 379 ORDER BY tr.sr LIMIT 1) AS fecha_creacion_sede,
      (SELECT tr.fecha_asignacion FROM proc_servicios_trazabilidad tr WHERE tr.idtramite = c.idtramite AND tr.actividad = 381 ORDER BY tr.sr LIMIT 1) AS fecha_cargue_plano,
      (SELECT tr.fecha_gestion FROM proc_servicios_trazabilidad tr WHERE tr.idtramite = c.idtramite AND tr.actividad = 377 ORDER BY tr.sr LIMIT 1) AS fecha_cierre_caso,
      (SELECT tr2.observacion FROM proc_servicios_trazabilidad tr2 WHERE tr2.idtramite = c.idtramite AND tr2.actividad = 378 ORDER BY tr2.sr LIMIT 1) AS observacion_devolucion,
      (SELECT cd.descripcion FROM proc_servicios_infodevolucion d INNER JOIN proc_servicios_causalesdevolucion cd ON cd.id_causal = d.causal WHERE d.idtramite = c.idtramite ORDER BY d.sr LIMIT 1) AS causales_devolucion,
      (SELECT a.actividad FROM proc_servicios_trazabilidad tr3
         LEFT JOIN actividad_tipologia atp ON atp.id = tr3.actividad
         LEFT JOIN actividades a ON a.id = atp.id_actividad
       WHERE tr3.idtramite = c.idtramite ORDER BY tr3.sr DESC LIMIT 1) AS etapa,
      (SELECT ia.cont_madre FROM independientes_apolo ia WHERE ia.idtramite = c.idtramite ORDER BY ia.idtramite LIMIT 1) AS cont_madre,
      (SELECT ia.cont_independiente FROM independientes_apolo ia WHERE ia.idtramite = c.idtramite ORDER BY ia.idtramite LIMIT 1) AS cont_independiente
    FROM proc_servicios_consulta c
    INNER JOIN proc_servicios_obtenerempleadortramite e ON e.idtramite = c.idtramite
    INNER JOIN proc_servicios_obtenertramites t ON t.idtramite = c.idtramite
    WHERE CAST(e.fecha_insert AS date) BETWEEN :fecha_inicio AND :fecha_fin
    ORDER BY c.idtramite
    """
    try:
        return fetch_all_by_alias(base, sql, {"fecha_inicio": fecha_inicio, "fecha_fin": fecha_fin})
    except (ValueError, SQLAlchemyError) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Error generando informe consolidado ruta inclusion en {base}: {type(exc).__name__}: {exc}",
        )


def _ruta_inclusion_informe_consolidado_csv(base: str, fecha_inicio: str, fecha_fin: str) -> tuple[str, int]:
    rows = _ruta_inclusion_informe_consolidado_rows(base=base, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin)
    headers = [
        "Id tramite", "Estado", "Tipo Documento", "Numero Documento", "Fecha de Registro en Portal",
        "Fecha de Recepcion Imagine", "Dias RegistroPortal-RecepcionImgine",
        "Fecha Creacion Sede", "Dias Recep-CreaSede", "Fecha de Cargue Plano", "Dias Recep-CargPlano",
        "Fecha Cargue Temporal", "CargTemp-CreaSede/CargTemp-Recep",
        "Fecha de Cierre de Caso", "Dias Regis-Cierre", "Etapa", "Causales Devolucion",
        "Observacion Devolucion", "Contrato Madre", "Contrato Independiente",
    ]
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(headers)
    for r in rows:
        fechreg = as_text(r.get("fecharegistro"))
        fechasig = as_text(r.get("fecha_recepcion_imagine"))
        fechcreasd = as_text(r.get("fecha_creacion_sede"))
        fechpln = as_text(r.get("fecha_cargue_plano"))
        fechcrrc = as_text(r.get("fecha_cierre_caso"))
        dia1 = _ri_days_between_festivos(base, fechreg, fechasig)
        dia2 = _ri_days_between_festivos(base, fechasig, fechcreasd)
        dia3 = _ri_days_between_festivos(base, fechasig, fechpln)
        dia4 = _ri_days_between_festivos(base, fechcreasd if fechcreasd else fechasig, fechpln)
        dia5 = _ri_days_between_festivos(base, fechreg, fechcrrc)
        writer.writerow(
            [
                as_text(r.get("idtramite")),
                as_text(r.get("estado")),
                as_text(r.get("tipodocumentoempleador")),
                as_text(r.get("numerodocumentoempleador")),
                fechreg,
                fechasig,
                dia1,
                fechcreasd,
                dia2,
                fechpln,
                dia3,
                fechpln,  # legacy usa también fechpln en columna L (cargue temporal)
                dia4,
                fechcrrc,
                dia5,
                as_text(r.get("etapa")),
                as_text(r.get("causales_devolucion")),
                as_text(r.get("observacion_devolucion")),
                as_text(r.get("cont_madre")),
                as_text(r.get("cont_independiente")),
            ]
        )
    return out.getvalue(), len(rows)


@router.get("/ruta-inclusion/informe/export")
def ruta_inclusion_informe_export(
    fecha_inicio: str,
    fecha_fin: str,
    base: str = "temporal",
) -> Response:
    csv_text, count = _ruta_inclusion_informe_csv(base=base, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin)
    filename = f"informe_tramites_{fecha_inicio}_{fecha_fin}.csv"
    return Response(
        content=csv_text.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Export-Row-Count": str(count),
        },
    )


@router.post("/ruta-inclusion/informe-legacy")
def ruta_inclusion_informe_legacy(payload: dict[str, Any]) -> dict[str, Any]:
    base = as_text(payload.get("base") or "temporal").strip() or "temporal"
    fecha_inicio = as_text(payload.get("fecha_inicio")).strip()
    fecha_fin = as_text(payload.get("fecha_fin")).strip()
    if not fecha_inicio or not fecha_fin:
        return {"status": "error", "content": "fecha_inicio y fecha_fin son obligatorias"}
    try:
        _, count = _ruta_inclusion_informe_csv(base=base, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin)
    except HTTPException as exc:
        return {"status": "error", "content": as_text(exc.detail)}
    archivo = (
        f"/api/v1/afiliaciones/ruta-inclusion/informe/export"
        f"?base={base}&fecha_inicio={fecha_inicio}&fecha_fin={fecha_fin}"
    )
    return {
        "status": "success",
        "content": "Informacion generada Correctamente",
        "archivo": archivo,
        "count": count,
    }


@router.get("/ruta-inclusion/informe-consolidado/export")
def ruta_inclusion_informe_consolidado_export(
    fecha_inicio: str,
    fecha_fin: str,
    base: str = "temporal",
) -> Response:
    csv_text, count = _ruta_inclusion_informe_consolidado_csv(base=base, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin)
    filename = f"informe_consolidado_{fecha_inicio}_{fecha_fin}.csv"
    return Response(
        content=csv_text.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Export-Row-Count": str(count),
        },
    )


@router.post("/ruta-inclusion/informe-consolidado-legacy")
def ruta_inclusion_informe_consolidado_legacy(payload: dict[str, Any]) -> dict[str, Any]:
    base = as_text(payload.get("base") or "temporal").strip() or "temporal"
    fecha_inicio = as_text(payload.get("fecha_inicio")).strip()
    fecha_fin = as_text(payload.get("fecha_fin")).strip()
    if not fecha_inicio or not fecha_fin:
        return {"status": "error", "content": "fecha_inicio y fecha_fin son obligatorias"}
    try:
        _, count = _ruta_inclusion_informe_consolidado_csv(base=base, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin)
    except HTTPException as exc:
        return {"status": "error", "content": as_text(exc.detail)}
    archivo = (
        f"/api/v1/afiliaciones/ruta-inclusion/informe-consolidado/export"
        f"?base={base}&fecha_inicio={fecha_inicio}&fecha_fin={fecha_fin}"
    )
    return {
        "status": "success",
        "content": "Informacion generada Correctamente",
        "archivo": archivo,
        "count": count,
    }


@router.post("/ruta-inclusion/devolucion-legacy")
def ruta_inclusion_devolucion_legacy(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Compatibilidad con actionDevolucion/actionDevolucionPymes del PHP:
    - apertura modal devolucion (pymes/no pymes)
    - traeSubcaus para pymes
    """
    base = as_text(payload.get("base") or "temporal").strip() or "temporal"
    if payload.get("traeSubcaus"):
        causal_txt = as_text(payload.get("causal")).strip()
        ids = [c.strip() for c in causal_txt.split(",") if c.strip()]
        sub = _ruta_inclusion_pymes_subcausales(base=base, causal_ids=ids)
        return {"status": "success", "content": {"mode": "subcausales", "items": sub}}

    idtramite = as_text(payload.get("idtipotramite") or payload.get("idtramite")).strip()
    actividad = int(payload.get("actividad") or 380)
    if not idtramite:
        return {"status": "error", "content": "idtipotramite es obligatorio"}
    is_pymes = bool(RUTA_IDTRAMITE_PYMES_RE.match(idtramite))
    causales_std: list[dict[str, Any]] = []
    try:
        std = ruta_inclusion_causales(base=base, only_active=True)
        causales_std = list(std.get("items", []))
    except HTTPException:
        causales_std = []
    causales_pymes = _ruta_inclusion_pymes_causales(base=base, idtramite=idtramite) if is_pymes else []
    return {
        "status": "success",
        "content": {
            "mode": "devolucion_pymes" if is_pymes else "devolucion",
            "idtramite": idtramite,
            "actividad": actividad,
            "is_pymes": is_pymes,
            "causales": causales_pymes if causales_pymes else causales_std,
        },
    }


@router.get("/ruta-inclusion/validaciones/{idtramite}")
def ruta_inclusion_validaciones(idtramite: str, base: str = "temporal") -> dict[str, Any]:
    return _ruta_inclusion_legacy_validaciones(base=base, idtramite=idtramite)


@router.get("/ruta-inclusion/permite-modificar/{idtramite}")
def ruta_inclusion_permite_modificar(idtramite: str, base: str = "temporal") -> dict[str, Any]:
    permite = _proc_log_permite_modificar(base=base, idtramite=idtramite)
    return {
        "ok": True,
        "base": base,
        "idtramite": idtramite,
        "permite_modificar": permite,
        "source": "proc_log" if _proc_log_table_available(base) else "no_proc_log",
    }


@router.get("/ruta-inclusion/tipo-cargue/{idtramite}")
def ruta_inclusion_tipo_cargue(idtramite: str, base: str = "temporal", numide: str = "0") -> dict[str, Any]:
    data = _ruta_inclusion_tipo_cargue_local(base=base, idtramite=idtramite, numide=numide)
    return {"ok": True, "base": base, "idtramite": idtramite, "tipo_cargue": data}


@router.post("/ruta-inclusion/devolucion")
def ruta_inclusion_devolucion(payload: dict[str, Any]) -> dict[str, Any]:
    frm = _legacy_form_section(payload, "ProcServiciosInfodevolucion")
    base = as_text(payload.get("base") or "temporal").strip() or "temporal"
    idtramite = as_text(payload.get("idtramite") or frm.get("idtramite")).strip()
    observacion = as_text(payload.get("observacion") or frm.get("observacion")).strip()
    actividad = int(payload.get("actividad") or frm.get("actividad") or 380)
    usuario = as_text(payload.get("usuario") or "api_ruta_inclusion").strip()
    causales_raw = payload.get("causales")
    if causales_raw is None:
        causales_raw = frm.get("causal")

    if not idtramite:
        raise HTTPException(status_code=400, detail="Campo requerido: idtramite")
    if not observacion:
        raise HTTPException(status_code=400, detail="Campo requerido: observacion")

    causales: list[str] = []
    subcausas = _legacy_form_section(payload, "PymesAfiliacionInfodevolucion").get("sub_causal")
    if isinstance(subcausas, list) and subcausas:
        causales = [as_text(c) for c in subcausas if as_text(c)]
    elif isinstance(causales_raw, list):
        causales = [as_text(c) for c in causales_raw if as_text(c)]
    elif as_text(causales_raw):
        causales = [c.strip() for c in as_text(causales_raw).split(",") if c.strip()]

    if not causales:
        raise HTTPException(status_code=400, detail="Campo requerido: causales (lista o csv)")

    causal_csv = ",".join(causales)
    updated_rows = 0
    trazas_insertadas = 0
    devoluciones_insertadas = 0
    warnings: list[str] = []

    try:
        updated_rows = execute_by_alias(
            base,
            "UPDATE proc_servicios_obtenertramites "
            "SET estado='Devuelto', idestadotipotramite=2, causalestramite=:causales, observacionsolicitudafiliacion=:obs "
            "WHERE idtramite=:idtramite",
            {"idtramite": idtramite, "causales": causal_csv, "obs": observacion},
        )
    except (ValueError, SQLAlchemyError) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Error actualizando estado en proc_servicios_obtenertramites: {type(exc).__name__}: {exc}",
        )

    try:
        execute_by_alias(
            base,
            "UPDATE proc_servicios_trazabilidad "
            "SET usuario_gestion=:usuario, fecha_gestion=now(), observacion=:obs "
            "WHERE idtramite=:idtramite AND fecha_gestion IS NULL",
            {"idtramite": idtramite, "usuario": usuario, "obs": "devolucion aplicada"},
        )
        trazas_insertadas += execute_by_alias(
            base,
            "INSERT INTO proc_servicios_trazabilidad (idtramite, estado, usuario_asignado, actividad, observacion) "
            "VALUES (:idtramite, 1, :usuario, :actividad, :obs)",
            {"idtramite": idtramite, "usuario": usuario, "actividad": actividad, "obs": observacion},
        )
    except (ValueError, SQLAlchemyError):
        warnings.append("No se pudo registrar trazabilidad en proc_servicios_trazabilidad.")

    try:
        get_table_columns_by_alias(base, "proc_servicios_infodevolucion")
        for causal in causales:
            devoluciones_insertadas += execute_by_alias(
                base,
                "INSERT INTO proc_servicios_infodevolucion (idtramite, causal, observacion) "
                "VALUES (:idtramite, :causal, :obs)",
                {"idtramite": idtramite, "causal": causal, "obs": "devolucion exitosa"},
            )
    except NoSuchTableError:
        warnings.append("Tabla proc_servicios_infodevolucion no existe en esta base.")
    except (ValueError, SQLAlchemyError):
        warnings.append("No se pudo insertar detalle en proc_servicios_infodevolucion.")

    return {
        "ok": updated_rows > 0,
        "base": base,
        "idtramite": idtramite,
        "estado_final": "Devuelto",
        "idestadotipotramite_final": 2,
        "causales": causales,
        "observacion": observacion,
        "rows_updated_proc_servicios_obtenertramites": updated_rows,
        "trazas_insertadas": trazas_insertadas,
        "registros_infodevolucion_insertados": devoluciones_insertadas,
        "warnings": warnings,
    }


@router.get("/ruta-inclusion/trazabilidad/{idtramite}")
def ruta_inclusion_trazabilidad(idtramite: str, base: str = "temporal") -> dict[str, Any]:
    try:
        rows = fetch_all_by_alias(
            base,
            "SELECT * FROM proc_servicios_trazabilidad WHERE idtramite = :idtramite ORDER BY sr",
            {"idtramite": idtramite},
        )
    except (ValueError, SQLAlchemyError) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Error consultando proc_servicios_trazabilidad en {base}: {type(exc).__name__}: {exc}",
        )

    for row in rows:
        actividad = as_text(row.get("actividad"))
        row["actividad_nombre"] = f"Actividad {actividad}" if actividad else ""
    return {"ok": True, "base": base, "idtramite": idtramite, "count": len(rows), "rows": rows}


@router.post("/ruta-inclusion/trazabilidad-legacy")
def ruta_inclusion_trazabilidad_legacy(payload: dict[str, Any]) -> dict[str, Any]:
    idtramite = as_text(payload.get("idtipotramite") or payload.get("idtramite")).strip()
    base = as_text(payload.get("base") or "temporal").strip() or "temporal"
    if not idtramite:
        return {"status": "error", "content": "idtipotramite es obligatorio"}
    try:
        out = ruta_inclusion_trazabilidad(idtramite=idtramite, base=base)
    except HTTPException as exc:
        return {"status": "error", "content": as_text(exc.detail)}
    return {"status": "success", "content": out.get("rows", []), "raw": out}


@router.get("/ruta-inclusion/trabajador/{idtramite}/{idtrabajador}")
def ruta_inclusion_detalle_trabajador(idtramite: str, idtrabajador: str, base: str = "temporal") -> dict[str, Any]:
    try:
        rows = fetch_all_by_alias(
            base,
            "SELECT * FROM proc_servicios_obtenertrabajadortramite "
            "WHERE idtramite = :idtramite AND idtrabajador = :idtrabajador "
            "ORDER BY sr LIMIT 1",
            {"idtramite": idtramite, "idtrabajador": idtrabajador},
        )
    except (ValueError, SQLAlchemyError) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Error consultando detalle trabajador en {base}: {type(exc).__name__}: {exc}",
        )
    if not rows:
        return {"ok": False, "base": base, "idtramite": idtramite, "idtrabajador": idtrabajador, "detail": None}
    return {"ok": True, "base": base, "idtramite": idtramite, "idtrabajador": idtrabajador, "detail": rows[0]}


@router.post("/ruta-inclusion/detalle-trabajadores-legacy")
def ruta_inclusion_detalle_trabajadores_legacy(payload: dict[str, Any]) -> dict[str, Any]:
    idtramite = as_text(payload.get("idtramite")).strip()
    idtrabajador = as_text(payload.get("idtrabajador")).strip()
    base = as_text(payload.get("base") or "temporal").strip() or "temporal"
    if not idtramite or not idtrabajador:
        return {"status": "error", "content": "idtramite e idtrabajador son obligatorios"}
    try:
        out = ruta_inclusion_detalle_trabajador(idtramite=idtramite, idtrabajador=idtrabajador, base=base)
    except HTTPException as exc:
        return {"status": "error", "content": as_text(exc.detail)}
    return {"status": "success", "content": out.get("detail"), "raw": out}


@router.get("/ruta-inclusion/horas/{idtramite}/{idtrabajador}")
def ruta_inclusion_detalle_horas(idtramite: str, idtrabajador: str, base: str = "temporal") -> dict[str, Any]:
    # Estructura esperada por clone UI: 7 dias x 24 horas.
    matriz = {str(day): {str(hour): "" for hour in range(1, 25)} for day in range(1, 8)}

    try:
        cols = get_table_columns_by_alias(base, "proc_servicios_obtenerhoraslaborales")
    except NoSuchTableError:
        return {
            "ok": True,
            "base": base,
            "idtramite": idtramite,
            "idtrabajador": idtrabajador,
            "has_source_table": False,
            "hours": matriz,
        }
    except (ValueError, SQLAlchemyError) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Error consultando estructura horas en {base}: {type(exc).__name__}: {exc}",
        )

    cols_low = {c.lower() for c in cols}
    if not {"idtramite", "idtrabajador"}.issubset(cols_low):
        return {
            "ok": True,
            "base": base,
            "idtramite": idtramite,
            "idtrabajador": idtrabajador,
            "has_source_table": True,
            "warning": "tabla_horas_sin_columnas_id",
            "hours": matriz,
        }

    try:
        rows = fetch_all_by_alias(
            base,
            "SELECT * FROM proc_servicios_obtenerhoraslaborales "
            "WHERE idtramite = :idtramite AND idtrabajador = :idtrabajador",
            {"idtramite": idtramite, "idtrabajador": idtrabajador},
        )
    except (ValueError, SQLAlchemyError) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Error consultando horas laborales en {base}: {type(exc).__name__}: {exc}",
        )

    # Intento de mapeo flexible: si la tabla trae columnas dia/hora/valor.
    for row in rows:
        day = as_text(row.get("dia") or row.get("day_week") or row.get("dia_semana"))
        hour = as_text(row.get("hora") or row.get("hour") or row.get("start_hour"))
        val = as_text(row.get("valor") or row.get("marca") or row.get("activo") or "X")
        if day.isdigit() and hour.isdigit():
            d = int(day)
            h = int(hour)
            if 1 <= d <= 7 and 1 <= h <= 24:
                matriz[str(d)][str(h)] = val

    return {
        "ok": True,
        "base": base,
        "idtramite": idtramite,
        "idtrabajador": idtrabajador,
        "has_source_table": True,
        "source_rows": len(rows),
        "hours": matriz,
    }


@router.post("/ruta-inclusion/detalle-horas-legacy")
def ruta_inclusion_detalle_horas_legacy(payload: dict[str, Any]) -> dict[str, Any]:
    idtramite = as_text(payload.get("idtramite")).strip()
    idtrabajador = as_text(payload.get("idtrabajador")).strip()
    base = as_text(payload.get("base") or "temporal").strip() or "temporal"
    if not idtramite or not idtrabajador:
        return {"status": "error", "content": "idtramite e idtrabajador son obligatorios"}
    try:
        out = ruta_inclusion_detalle_horas(idtramite=idtramite, idtrabajador=idtrabajador, base=base)
    except HTTPException as exc:
        return {"status": "error", "content": as_text(exc.detail)}
    return {"status": "success", "content": out.get("hours", {}), "raw": out}


@router.post("/ruta-inclusion/reabrir-flujo")
def ruta_inclusion_reabrir_flujo(payload: dict[str, Any]) -> dict[str, Any]:
    base = as_text(payload.get("base") or "temporal").strip() or "temporal"
    idtramite = as_text(payload.get("idtramite")).strip()
    usuario = as_text(payload.get("usuario") or "api_ruta_inclusion").strip()
    if not idtramite:
        raise HTTPException(status_code=400, detail="Campo requerido: idtramite")

    updated = 0
    inserted = 0
    deleted_indep_apolo = 0
    try:
        updated = execute_by_alias(
            base,
            "UPDATE proc_servicios_trazabilidad "
            "SET usuario_gestion = :usuario, fecha_gestion = now(), observacion = 'Caso retomado' "
            "WHERE idtramite = :idtramite AND fecha_gestion IS NULL",
            {"idtramite": idtramite, "usuario": usuario},
        )
        inserted = execute_by_alias(
            base,
            "INSERT INTO proc_servicios_trazabilidad (usuario_asignado, idtramite, estado, actividad, observacion) "
            "VALUES (:usuario, :idtramite, 1, 378, 'Caso retomado')",
            {"idtramite": idtramite, "usuario": usuario},
        )
        # Paridad legacy: limpia independientes_apolo para permitir reproceso del caso.
        try:
            cols = {c.lower() for c in get_table_columns_by_alias(base, "independientes_apolo")}
            if "idtramite" in cols:
                deleted_indep_apolo = execute_by_alias(
                    base,
                    "DELETE FROM independientes_apolo WHERE idtramite = :idtramite",
                    {"idtramite": idtramite},
                )
        except NoSuchTableError:
            deleted_indep_apolo = 0
    except (ValueError, SQLAlchemyError) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Error reabriendo flujo en {base}: {type(exc).__name__}: {exc}",
        )

    return {
        "ok": True,
        "base": base,
        "idtramite": idtramite,
        "usuario": usuario,
        "rows_updated_open_traces": updated,
        "rows_inserted_new_trace": inserted,
        "rows_deleted_independientes_apolo": deleted_indep_apolo,
        "actividad_nueva": 378,
    }


@router.post("/ruta-inclusion/reabrir-flujo-legacy")
def ruta_inclusion_reabrir_flujo_legacy(payload: dict[str, Any]) -> dict[str, Any]:
    base = as_text(payload.get("base") or "temporal").strip() or "temporal"
    idtipotramite = as_text(payload.get("idtipotramite") or payload.get("idtramite")).strip()
    usuario = as_text(payload.get("usuario") or "api_ruta_inclusion").strip()
    if not idtipotramite:
        return {"status": "error", "content": "idtipotramite es obligatorio"}
    try:
        _ = ruta_inclusion_reabrir_flujo({"base": base, "idtramite": idtipotramite, "usuario": usuario})
    except HTTPException as exc:
        return {"status": "error", "content": as_text(exc.detail)}
    return {"status": "success", "content": "Caso retornado con exito"}


@router.get("/ruta-inclusion/actividades")
def ruta_inclusion_actividades(base: str = "temporal") -> dict[str, Any]:
    fallback = [
        {"actividad": 376, "nombre": "Recepcion"},
        {"actividad": 377, "nombre": "Cierre de caso"},
        {"actividad": 378, "nombre": "Pendientes Imagine"},
        {"actividad": 379, "nombre": "Creacion de sede"},
        {"actividad": 380, "nombre": "Devolucion"},
        {"actividad": 381, "nombre": "Generar plano"},
    ]
    try:
        cols_act = {c.lower() for c in get_table_columns_by_alias(base, "actividades")}
        cols_tip = {c.lower() for c in get_table_columns_by_alias(base, "actividad_tipologia")}
    except NoSuchTableError:
        return {"ok": True, "base": base, "source": "fallback", "items": fallback}
    except (ValueError, SQLAlchemyError):
        return {"ok": True, "base": base, "source": "fallback", "items": fallback}

    if not {"id", "actividad"}.issubset(cols_act) or not {"id_actividad", "id"}.issubset(cols_tip):
        return {"ok": True, "base": base, "source": "fallback", "items": fallback}

    try:
        rows = fetch_all_by_alias(
            base,
            "SELECT t.id as actividad, a.actividad as nombre "
            "FROM actividad_tipologia t "
            "INNER JOIN actividades a ON a.id = t.id_actividad "
            "ORDER BY t.id",
        )
        if not rows:
            return {"ok": True, "base": base, "source": "fallback", "items": fallback}
        return {"ok": True, "base": base, "source": "db", "items": rows}
    except (ValueError, SQLAlchemyError):
        return {"ok": True, "base": base, "source": "fallback", "items": fallback}


@router.post("/ruta-inclusion/gestionar")
def ruta_inclusion_gestionar(payload: dict[str, Any]) -> dict[str, Any]:
    frm = _legacy_form_section(payload, "ProcServiciosTrazabilidad")
    base = as_text(payload.get("base") or "temporal").strip() or "temporal"
    idtramite = as_text(payload.get("idtramite") or frm.get("idtramite")).strip()
    actividad = int(payload.get("actividad") or frm.get("actividad") or 0)
    observacion = as_text(payload.get("observacion") or frm.get("observacion")).strip()
    usuario = as_text(payload.get("usuario") or "api_ruta_inclusion").strip()

    if not idtramite:
        raise HTTPException(status_code=400, detail="Campo requerido: idtramite")
    if actividad <= 0:
        raise HTTPException(status_code=400, detail="Campo requerido: actividad (>0)")
    if not observacion:
        raise HTTPException(status_code=400, detail="Campo requerido: observacion")

    validaciones = _ruta_inclusion_legacy_validaciones(base=base, idtramite=idtramite)
    if not validaciones.get("ok", False):
        return {
            "ok": False,
            "base": base,
            "idtramite": idtramite,
            "status": "error",
            "actividad": actividad,
            "message": "Por favor corrija validaciones del caso antes de gestionar.",
            "validaciones": validaciones,
        }
    if _ruta_inclusion_open_trace(base=base, idtramite=idtramite) is None:
        return {
            "ok": False,
            "base": base,
            "idtramite": idtramite,
            "status": "error",
            "actividad": actividad,
            "message": "No hay traza abierta para gestionar este caso.",
            "validaciones": validaciones,
        }

    # Legacy behavior: actividad 380 abre flujo de devolucion.
    if actividad == 380:
        return {
            "ok": True,
            "base": base,
            "idtramite": idtramite,
            "status": "devolucion",
            "actividad": actividad,
            "message": "Actividad de devolucion, continuar con formulario de devolucion.",
        }

    plano = False
    tipo_tramite = ""
    actividad_resuelta = actividad
    tipo_cargue: dict[str, Any] | None = None
    action_message = ""

    if actividad == 381:
        tipo_cargue = _ruta_inclusion_tipo_cargue_local(base=base, idtramite=idtramite, numide="0")
        tipo_tramite = as_text(tipo_cargue.get("tipo_tramite"))
        codsederror = as_text(tipo_cargue.get("codsederror"))
        codsede = as_text(tipo_cargue.get("codsede"))
        datossede = tipo_cargue.get("datossede")
        if codsederror == "SI":
            return {
                "ok": False,
                "base": base,
                "idtramite": idtramite,
                "status": "error",
                "actividad": actividad,
                "message": "Las actividades economicas no coinciden o no hay sede correspondiente.",
                "tipo_cargue": tipo_cargue,
            }
        if tipo_tramite == "Novedad" and codsede != "Creacion":
            plano = True
            actividad_resuelta = 381
            action_message = "Plano generado para novedad con sede existente."
        elif tipo_tramite == "Afiliacion":
            plano = True
            actividad_resuelta = 381
            action_message = "Plano generado para afiliacion."
        elif datossede is None:
            return {
                "ok": False,
                "base": base,
                "idtramite": idtramite,
                "status": "error",
                "actividad": actividad,
                "message": "Consulta de sedes no arrojo resultado.",
                "tipo_cargue": tipo_cargue,
            }
        else:
            plano = False
            actividad_resuelta = 379
            action_message = "Novedad sin sede: se enruta a creacion de sede."
    elif actividad == 379:
        actividad_resuelta = 379
        action_message = "Pendiente de creacion de sede."

    updated = 0
    inserted = 0
    try:
        updated = execute_by_alias(
            base,
            "UPDATE proc_servicios_trazabilidad "
            "SET usuario_gestion = :usuario, fecha_gestion = now(), observacion = :observacion "
            "WHERE idtramite = :idtramite AND fecha_gestion IS NULL",
            {"idtramite": idtramite, "usuario": usuario, "observacion": observacion},
        )
        inserted = execute_by_alias(
            base,
            "INSERT INTO proc_servicios_trazabilidad (usuario_asignado, idtramite, estado, actividad, observacion) "
            "VALUES (:usuario, :idtramite, 1, :actividad, '')",
            {"idtramite": idtramite, "usuario": usuario, "actividad": actividad_resuelta},
        )
    except (ValueError, SQLAlchemyError) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Error gestionando tramite en {base}: {type(exc).__name__}: {exc}",
        )

    return {
        "ok": True,
        "base": base,
        "idtramite": idtramite,
        "status": "success",
        "actividad": actividad_resuelta,
        "plano": plano,
        "tipo_tramite": tipo_tramite,
        "tipo_cargue": tipo_cargue,
        "message": action_message or "Gestion realizada.",
        "rows_updated_open_traces": updated,
        "rows_inserted_new_trace": inserted,
    }


@router.post("/ruta-inclusion/gestionar-caso-legacy")
def ruta_inclusion_gestionar_caso_legacy(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Respuesta compatible con actionGestionarCaso de PHP:
    - success: {status, plano, tipo_tramite}
    - devolucion: {status:'devolucion', content: actividad}
    - error: {status:'error', content: mensaje}
    """
    out = ruta_inclusion_gestionar(payload)
    status = as_text(out.get("status"))
    if status == "devolucion":
        return {"status": "devolucion", "content": as_text(out.get("actividad") or "380")}
    if status == "success":
        return {
            "status": "success",
            "plano": bool(out.get("plano", False)),
            "tipo_tramite": as_text(out.get("tipo_tramite")),
            "content": as_text(out.get("message")),
            "raw": out,
        }
    return {"status": "error", "content": as_text(out.get("message") or "Ha ocurrido un error"), "raw": out}


@router.post("/ruta-inclusion/editar-informacion")
def ruta_inclusion_editar_informacion(payload: dict[str, Any]) -> dict[str, Any]:
    # Compatibilidad con actionEditarInformacion del legacy:
    # 1) abrir form: idtipotramite + campo + valor (sin actualizaInformacionEmpleador)
    # 2) guardar: valor + campo + tabla + idtramite + actualizaInformacionEmpleador=true
    if as_text(payload.get("idtipotramite")).strip() and not as_text(payload.get("tabla")).strip():
        return {
            "ok": True,
            "status": "success",
            "mode": "legacy_open_form",
            "idtipotramite": as_text(payload.get("idtipotramite")).strip(),
            "campo": as_text(payload.get("campo")).strip(),
            "valor": payload.get("valor"),
        }

    base = as_text(payload.get("base") or "temporal").strip() or "temporal"
    idtramite = as_text(payload.get("idtramite")).strip()
    tabla = as_text(payload.get("tabla")).strip().lower()
    campo = as_text(payload.get("campo")).strip().lower()
    valor = payload.get("valor")
    usuario = as_text(payload.get("usuario") or "ui_clone").strip()

    if not idtramite:
        raise HTTPException(status_code=400, detail="Campo requerido: idtramite")
    if not tabla:
        raise HTTPException(status_code=400, detail="Campo requerido: tabla")
    if not campo:
        raise HTTPException(status_code=400, detail="Campo requerido: campo")
    if not _proc_log_permite_modificar(base=base, idtramite=idtramite):
        return {
            "ok": False,
            "status": "error",
            "base": base,
            "idtramite": idtramite,
            "message": "La informacion ya fue editada para este tramite.",
            "permite_modificar": False,
        }

    allowed: dict[str, set[str]] = {
        "proc_servicios_obtenerempleadortramite": {
            "tipodocumentoempleador",
            "numerodocumentoempleador",
            "telefonoprincipalempleador",
            "direccionempleador",
            "telefonocelularempleador",
            "correoelectronicoempleador",
            "ciudadempleador",
            "zonaempleador",
            "localidadempleador",
            "nombrerepresentantelegal",
            "tipodocumentorepresentantelegal",
            "numerodocumentorepresnetantelegal",
            "correoelectronicorepresentantelegal",
            "actividadeconomicaempleador",
            "razonsocialempleador",
            "naturalezajuridica",
            "tipoafiliacion",
            "tipoaportante",
            "digito_verificacion",
        },
        "proc_servicios_obtenertrabajadortramite": {
            "tipodocumento",
            "numerodocumento",
            "primerapellido",
            "segundoapellido",
            "primernombre",
            "segundonombre",
            "fechanacimiento",
            "sexo",
            "direccionresidencia",
            "ciudadresidencia",
            "localidad",
            "zona",
            "telefono",
            "celular",
            "correoelectronico",
            "eps",
            "actividadeconomica",
            "modalidad",
            "arlanterior",
            "afp",
            "iniciocontrato",
            "finalizacioncontrato",
            "valorcontrato",
            "ingresomensual",
            "deducciones",
            "ibc",
            "iniciocobertura",
            "tipoafiliadocotizante",
            "subtipoafiliadocotizante",
            "tipocontrato",
            "jornada",
            "suministratransporte",
            "numeromesescontrato",
        },
    }

    if tabla not in allowed:
        raise HTTPException(status_code=400, detail=f"Tabla no permitida: {tabla}")
    if campo not in allowed[tabla]:
        raise HTTPException(status_code=400, detail=f"Campo no permitido para {tabla}: {campo}")

    # Legacy special behavior: numerodocumentoempleador can come with verification digit merged.
    if tabla == "proc_servicios_obtenerempleadortramite" and campo == "numerodocumentoempleador":
        try:
            old_row = fetch_all_by_alias(
                base,
                "SELECT numerodocumentoempleador, digito_verificacion FROM proc_servicios_obtenerempleadortramite "
                "WHERE idtramite=:idtramite ORDER BY sr LIMIT 1",
                {"idtramite": idtramite},
            )
        except (ValueError, SQLAlchemyError):
            old_row = []
        old_nit = as_text(old_row[0].get("numerodocumentoempleador")) if old_row else ""
        old_dv = as_text(old_row[0].get("digito_verificacion")) if old_row else ""
        old_combined = f"{old_nit}{old_dv}"
        raw = as_text(valor)
        digits = "".join(ch for ch in raw if ch.isdigit())
        if len(digits) < 2:
            raise HTTPException(status_code=400, detail="numerodocumentoempleador debe ser numerico")
        nit = digits[:-1]
        dv = digits[-1]
        try:
            updated = execute_by_alias(
                base,
                "UPDATE proc_servicios_obtenerempleadortramite "
                "SET numerodocumentoempleador=:nit, digito_verificacion=:dv "
                "WHERE idtramite=:idtramite",
                {"idtramite": idtramite, "nit": nit, "dv": dv},
            )
        except (ValueError, SQLAlchemyError) as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Error actualizando NIT/DV en {tabla}: {type(exc).__name__}: {exc}",
            )
        proc_log = _proc_log_insert_change(
            base=base,
            idtramite=idtramite,
            usuario=usuario,
            campo=f"{tabla}.{campo}",
            valor_anterior=old_combined,
            valor_nuevo=f"{nit}{dv}",
        )
        return {
            "ok": updated > 0,
            "base": base,
            "idtramite": idtramite,
            "tabla": tabla,
            "campo": campo,
            "valor_nuevo": nit,
            "digito_verificacion": dv,
            "rows_updated": updated,
            "usuario": usuario,
            "permite_modificar": False,
            "proc_log": proc_log,
        }

    if tabla == "proc_servicios_obtenerempleadortramite" and campo == "tipodocumentoempleador" and as_text(valor).strip() == "":
        raise HTTPException(status_code=400, detail="tipodocumentoempleador es obligatorio")
    if tabla == "proc_servicios_obtenerempleadortramite" and campo == "numerodocumentoempleador":
        if not as_text(valor).strip().isdigit():
            raise HTTPException(status_code=400, detail="numerodocumentoempleador debe ser numerico")
    if tabla == "proc_servicios_obtenertrabajadortramite" and campo == "numeromesescontrato":
        meses = _ruta_to_int(valor)
        valor = str(max(meses or 0, 1))

    try:
        old = fetch_all_by_alias(
            base,
            f"SELECT {campo} FROM {tabla} WHERE idtramite = :idtramite ORDER BY sr LIMIT 1",
            {"idtramite": idtramite},
        )
    except (ValueError, SQLAlchemyError):
        old = []
    old_value = old[0].get(campo) if old else None

    try:
        sql = f"UPDATE {tabla} SET {campo} = :valor WHERE idtramite = :idtramite"
        updated = execute_by_alias(base, sql, {"idtramite": idtramite, "valor": valor})
    except (ValueError, SQLAlchemyError) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Error actualizando {tabla}.{campo}: {type(exc).__name__}: {exc}",
        )
    proc_log = _proc_log_insert_change(
        base=base,
        idtramite=idtramite,
        usuario=usuario,
        campo=f"{tabla}.{campo}",
        valor_anterior=old_value,
        valor_nuevo=valor,
    )

    return {
        "ok": updated > 0,
        "base": base,
        "idtramite": idtramite,
        "tabla": tabla,
        "campo": campo,
        "valor_nuevo": valor,
        "valor_anterior": old_value,
        "rows_updated": updated,
        "usuario": usuario,
        "permite_modificar": False,
        "proc_log": proc_log,
    }


@router.post("/ruta-inclusion/editar-informacion-legacy")
def ruta_inclusion_editar_informacion_legacy(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Respuesta compatible con actionEditarInformacion del PHP ajax:
    - success => {status:'success', content:'...'}
    - error   => {status:'error', content:'...'}
    """
    try:
        out = ruta_inclusion_editar_informacion(payload)
    except HTTPException as exc:
        return {"status": "error", "content": as_text(exc.detail) or "No fue posible actualizar"}
    if out.get("ok", False):
        msg = "Informacion actualizada con exito."
        return {"status": "success", "content": msg, "raw": out}
    return {"status": "error", "content": as_text(out.get("message") or "No fue posible actualizar"), "raw": out}


@router.post("/ruta-inclusion/importar-empleador-contrato")
def ruta_inclusion_importar_empleador_contrato(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Carga datos de empleador desde contrato_*_clean.txt del pipeline Excel
    hacia proc_servicios_obtenerempleadortramite para el idtramite activo.
    """
    base = as_text(payload.get("base") or "temporal").strip() or "temporal"
    idtramite = as_text(payload.get("idtramite")).strip()
    content = as_text(payload.get("content"))
    usuario = as_text(payload.get("usuario") or "ui_clone").strip()
    strict_validate = bool(payload.get("strict_validate", True))
    if not idtramite:
        raise HTTPException(status_code=400, detail="Campo requerido: idtramite")
    if not content.strip():
        raise HTTPException(status_code=400, detail="Campo requerido: content")

    data = _parse_empleador_from_contrato_clean(content)
    validation_errors = _validate_empleador_import_data(data)
    if strict_validate and validation_errors:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Validación de empleador falló. No se realizó actualización.",
                "errors": validation_errors,
                "parsed_preview": data,
            },
        )

    try:
        rows = fetch_all_by_alias(
            base,
            "SELECT sr FROM proc_servicios_obtenerempleadortramite WHERE idtramite = :idtramite ORDER BY sr LIMIT 1",
            {"idtramite": idtramite},
        )
        exists = len(rows) > 0
    except (ValueError, SQLAlchemyError) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Error consultando empleador para tramite {idtramite}: {type(exc).__name__}: {exc}",
        )

    fields = [
        "tipodocumentoempleador",
        "numerodocumentoempleador",
        "telefonoprincipalempleador",
        "direccionempleador",
        "telefonocelularempleador",
        "correoelectronicoempleador",
        "ciudadempleador",
        "zonaempleador",
        "localidadempleador",
        "nombrerepresentantelegal",
        "tipodocumentorepresentantelegal",
        "numerodocumentorepresnetantelegal",
        "correoelectronicorepresentantelegal",
        "actividadeconomicaempleador",
        "razonsocialempleador",
        "naturalezajuridica",
        "tipoempresa",
        "tipoafiliacion",
        "tipoaportante",
        "arlanteriorempleador",
    ]
    params = {k: data.get(k, "") for k in fields}
    params["idtramite"] = idtramite

    try:
        try:
            execute_by_alias(
                base,
                "ALTER TABLE proc_servicios_obtenerempleadortramite "
                "ADD COLUMN IF NOT EXISTS arlanteriorempleador text",
            )
        except (ValueError, SQLAlchemyError):
            pass
        try:
            execute_by_alias(
                base,
                "ALTER TABLE proc_servicios_obtenerempleadortramite "
                "ADD COLUMN IF NOT EXISTS tipoempresa text",
            )
        except (ValueError, SQLAlchemyError):
            pass
        # Paridad legacy: conservar número de radicación/contrato en trámite para el tipo 1 del 926.
        numero_contrato = _only_digits(data.get("numerocontrato"))
        if numero_contrato:
            try:
                execute_by_alias(
                    base,
                    "ALTER TABLE proc_servicios_obtenertramites ADD COLUMN IF NOT EXISTS numerocontrato text",
                )
            except (ValueError, SQLAlchemyError):
                pass
            try:
                execute_by_alias(
                    base,
                    "UPDATE proc_servicios_obtenertramites SET numerocontrato = :numerocontrato WHERE idtramite = :idtramite",
                    {"numerocontrato": numero_contrato, "idtramite": idtramite},
                )
            except (ValueError, SQLAlchemyError):
                pass
        fecha_radicacion = _clean_token(data.get("fecharadicacion"))
        sucursal_codigo = _only_digits(data.get("sucursalcodigo"))
        if fecha_radicacion or sucursal_codigo:
            try:
                execute_by_alias(
                    base,
                    "ALTER TABLE proc_servicios_obtenertramites "
                    "ADD COLUMN IF NOT EXISTS sucursal text",
                )
            except (ValueError, SQLAlchemyError):
                pass
        if fecha_radicacion:
            try:
                execute_by_alias(
                    base,
                    "UPDATE proc_servicios_obtenertramites "
                    "SET fecharegistro = :fecharegistro "
                    "WHERE idtramite = :idtramite",
                    {"fecharegistro": fecha_radicacion, "idtramite": idtramite},
                )
            except (ValueError, SQLAlchemyError):
                pass
        if sucursal_codigo:
            try:
                execute_by_alias(
                    base,
                    "UPDATE proc_servicios_obtenertramites "
                    "SET sucursal = :sucursal "
                    "WHERE idtramite = :idtramite",
                    {"sucursal": sucursal_codigo, "idtramite": idtramite},
                )
            except (ValueError, SQLAlchemyError):
                pass

        if exists:
            set_clause = ", ".join([f"{f} = :{f}" for f in fields])
            updated = execute_by_alias(
                base,
                f"UPDATE proc_servicios_obtenerempleadortramite SET {set_clause} WHERE idtramite = :idtramite",
                params,
            )
            action = "updated"
            affected = updated
        else:
            cols = ", ".join(["sr"] + fields + ["idtramite"])
            vals = ", ".join([":sr"] + [f":{f}" for f in fields] + [":idtramite"])
            params["sr"] = 1
            inserted = execute_by_alias(
                base,
                f"INSERT INTO proc_servicios_obtenerempleadortramite ({cols}) VALUES ({vals})",
                params,
            )
            action = "inserted"
            affected = inserted
    except (ValueError, SQLAlchemyError) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Error guardando empleador desde contrato para tramite {idtramite}: {type(exc).__name__}: {exc}",
        )

    log_info = _proc_log_insert_change(
        base=base,
        idtramite=idtramite,
        usuario=usuario,
        campo="importar_empleador_contrato",
        valor_anterior="",
        valor_nuevo=f"razonsocial={data.get('razonsocialempleador','')}",
    )

    return {
        "ok": affected > 0,
        "base": base,
        "idtramite": idtramite,
        "action": action,
        "rows_affected": affected,
        "empleador": data,
        "validation": {
            "strict": strict_validate,
            "ok": len(validation_errors) == 0,
            "errors": validation_errors,
        },
        "proc_log": log_info,
    }


@router.post("/ruta-inclusion/importar-trabajadores-contrato")
def ruta_inclusion_importar_trabajadores_contrato(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Carga trabajadores desde Sede01-Trabajadores_*_clean.txt del pipeline Excel
    hacia proc_servicios_obtenertrabajadortramite para el idtramite activo.
    """
    base = as_text(payload.get("base") or "temporal").strip() or "temporal"
    idtramite = as_text(payload.get("idtramite")).strip()
    content = as_text(payload.get("content"))
    contrato_content = as_text(payload.get("contrato_content"))
    usuario = as_text(payload.get("usuario") or "ui_clone").strip()
    strict_validate = bool(payload.get("strict_validate", True))
    replace_existing = bool(payload.get("replace_existing", True))
    allow_empty = bool(payload.get("allow_empty", False))
    auto_skip_empty_clean = bool(payload.get("auto_skip_empty_clean", True))
    source_kind = as_text(payload.get("source_kind")).strip().lower()
    sr_override = _to_int_safe(payload.get("sr_override"), default=0)
    codigoct_override = as_text(payload.get("codigoct_override")).strip()

    if not idtramite:
        raise HTTPException(status_code=400, detail="Campo requerido: idtramite")
    if not content.strip():
        raise HTTPException(status_code=400, detail="Campo requerido: content")

    cobertura_fallback = _parse_empleador_from_contrato_clean(contrato_content).get("iniciocobertura", "")
    parse_source = "sede_clean"
    salary_sanitize_warnings: list[dict[str, Any]] = []
    if source_kind == "independientes_legacy":
        rows = _parse_trabajadores_from_legacy_independientes(content, cobertura_fallback=cobertura_fallback)
        parse_source = "legacy_independientes"
    else:
        rows, salary_sanitize_warnings = _parse_trabajadores_from_sede_clean(content, cobertura_fallback=cobertura_fallback)
    if len(rows) == 0 and (allow_empty or auto_skip_empty_clean):
        return {
            "ok": True,
            "skipped": True,
            "reason": (
                "legacy_format_not_detected"
                if source_kind == "independientes_legacy"
                else "no_rows_detected"
            ),
            "parse_source": parse_source,
            "base": base,
            "idtramite": idtramite,
            "replace_existing": replace_existing,
            "rows_deleted": 0,
            "rows_inserted": 0,
            "validation": {
                "strict": strict_validate,
                "ok": True,
                "errors": [],
            },
        }
    if sr_override > 0 or codigoct_override:
        for r in rows:
            if sr_override > 0:
                r["sr"] = sr_override
            if codigoct_override:
                r["codigoct"] = codigoct_override

    def _worker_key(r: dict[str, Any]) -> str:
        td = as_text(r.get("tipodocumento")).strip().upper()
        nd = _only_digits(r.get("numerodocumento"))
        return f"{td}|{nd}" if td and nd else ""

    existing_keys: set[str] = set()
    if not replace_existing:
        try:
            existing_rows = fetch_all_by_alias(
                base,
                "SELECT tipodocumento, numerodocumento FROM proc_servicios_obtenertrabajadortramite WHERE idtramite = :idtramite",
                {"idtramite": idtramite},
            )
            for er in existing_rows:
                td = as_text(er.get("tipodocumento")).strip().upper()
                nd = _only_digits(er.get("numerodocumento"))
                if td and nd:
                    existing_keys.add(f"{td}|{nd}")
        except (ValueError, SQLAlchemyError):
            existing_keys = set()

    dedup_seen: set[str] = set()
    dedup_rows: list[dict[str, Any]] = []
    duplicates_skipped = 0
    duplicate_conflicts: list[dict[str, Any]] = []
    for r in rows:
        k = _worker_key(r)
        if not k:
            dedup_rows.append(r)
            continue
        if k in dedup_seen or k in existing_keys:
            duplicates_skipped += 1
            duplicate_conflicts.append(
                {
                    "tipodocumento": as_text(r.get("tipodocumento")).strip().upper(),
                    "numerodocumento": _only_digits(r.get("numerodocumento")),
                    "source": "archivo_actual" if k in dedup_seen else "ya_existente_en_tramite",
                }
            )
            continue
        dedup_seen.add(k)
        dedup_rows.append(r)
    rows = dedup_rows

    if strict_validate and duplicate_conflicts:
        preview = duplicate_conflicts[:20]
        rendered = [
            f"{str(x.get('tipodocumento') or '')}-{str(x.get('numerodocumento') or '')} ({str(x.get('source') or '')})"
            for x in preview
        ]
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Validación de trabajadores falló. Hay cédulas/documentos repetidos; no se realizó actualización.",
                "errors": [f"Documentos repetidos detectados: {', '.join(rendered)}"],
                "duplicate_count": len(duplicate_conflicts),
                "duplicates_preview": preview,
                "detected_rows": len(rows),
            },
        )

    validation_errors = _validate_trabajadores_import_data(rows)
    if strict_validate and validation_errors:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Validación de trabajadores falló. No se realizó actualización.",
                "errors": validation_errors,
                "detected_rows": len(rows),
            },
        )

    inserted = 0
    deleted = 0
    try:
        execute_by_alias(
            base,
            "ALTER TABLE proc_servicios_obtenertrabajadortramite "
            "ADD COLUMN IF NOT EXISTS cargo text, "
            "ADD COLUMN IF NOT EXISTS codigoct text, "
            "ADD COLUMN IF NOT EXISTS ct_nombreactividad text, "
            "ADD COLUMN IF NOT EXISTS ct_codigoactividad text, "
            "ADD COLUMN IF NOT EXISTS ct_claseriesgo text, "
            "ADD COLUMN IF NOT EXISTS ct_montocotizacion text, "
            "ADD COLUMN IF NOT EXISTS ct_ciudad text, "
            "ADD COLUMN IF NOT EXISTS ct_departamento text, "
            "ADD COLUMN IF NOT EXISTS ct_zona text, "
            "ADD COLUMN IF NOT EXISTS ct_direccion text, "
            "ADD COLUMN IF NOT EXISTS ct_telefono text, "
            "ADD COLUMN IF NOT EXISTS ct_correo text, "
            "ADD COLUMN IF NOT EXISTS ct_responsable_pa text, "
            "ADD COLUMN IF NOT EXISTS ct_responsable_sa text, "
            "ADD COLUMN IF NOT EXISTS ct_responsable_pn text, "
            "ADD COLUMN IF NOT EXISTS ct_responsable_sn text, "
            "ADD COLUMN IF NOT EXISTS ct_responsable_td text, "
            "ADD COLUMN IF NOT EXISTS ct_responsable_doc text, "
            "ADD COLUMN IF NOT EXISTS ct_responsable_correo text",
        )
        if replace_existing:
            deleted = execute_by_alias(
                base,
                "DELETE FROM proc_servicios_obtenertrabajadortramite WHERE idtramite = :idtramite",
                {"idtramite": idtramite},
            )

        sql = (
            "INSERT INTO proc_servicios_obtenertrabajadortramite("
            "sr,idtrabajador,tipodocumento,numerodocumento,primerapellido,segundoapellido,primernombre,segundonombre,"
            "fechanacimiento,sexo,direccionresidencia,ciudadresidencia,localidad,zona,telefono,celular,correoelectronico,"
            "eps,actividadeconomica,modalidad,arlanterior,afp,iniciocontrato,finalizacioncontrato,valorcontrato,"
            "ingresomensual,deducciones,ibc,iniciocobertura,tipoafiliadocotizante,subtipoafiliadocotizante,tipocontrato,"
            "jornada,suministratransporte,numeromesescontrato,tipotramite,idtramite,"
            "cargo,codigoct,ct_nombreactividad,ct_codigoactividad,ct_claseriesgo,ct_montocotizacion,"
            "ct_ciudad,ct_departamento,ct_zona,ct_direccion,ct_telefono,ct_correo,"
            "ct_responsable_pa,ct_responsable_sa,ct_responsable_pn,ct_responsable_sn,"
            "ct_responsable_td,ct_responsable_doc,ct_responsable_correo"
            ") VALUES ("
            ":sr,:idtrabajador,:tipodocumento,:numerodocumento,:primerapellido,:segundoapellido,:primernombre,:segundonombre,"
            ":fechanacimiento,:sexo,:direccionresidencia,:ciudadresidencia,:localidad,:zona,:telefono,:celular,:correoelectronico,"
            ":eps,:actividadeconomica,:modalidad,:arlanterior,:afp,:iniciocontrato,:finalizacioncontrato,:valorcontrato,"
            ":ingresomensual,:deducciones,:ibc,:iniciocobertura,:tipoafiliadocotizante,:subtipoafiliadocotizante,:tipocontrato,"
            ":jornada,:suministratransporte,:numeromesescontrato,:tipotramite,:idtramite,"
            ":cargo,:codigoct,:ct_nombreactividad,:ct_codigoactividad,:ct_claseriesgo,:ct_montocotizacion,"
            ":ct_ciudad,:ct_departamento,:ct_zona,:ct_direccion,:ct_telefono,:ct_correo,"
            ":ct_responsable_pa,:ct_responsable_sa,:ct_responsable_pn,:ct_responsable_sn,"
            ":ct_responsable_td,:ct_responsable_doc,:ct_responsable_correo)"
        )
        for r in rows:
            params = dict(r)
            for key in (
                "ct_ciudad", "ct_departamento", "ct_zona", "ct_direccion", "ct_telefono", "ct_correo",
                "ct_responsable_pa", "ct_responsable_sa", "ct_responsable_pn", "ct_responsable_sn",
                "ct_responsable_td", "ct_responsable_doc", "ct_responsable_correo",
            ):
                params.setdefault(key, "")
            params["idtramite"] = idtramite
            execute_by_alias(base, sql, params)
            inserted += 1
    except (ValueError, SQLAlchemyError) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Error guardando trabajadores desde contrato para tramite {idtramite}: {type(exc).__name__}: {exc}",
        )

    log_info = _proc_log_insert_change(
        base=base,
        idtramite=idtramite,
        usuario=usuario,
        campo="importar_trabajadores_contrato",
        valor_anterior=str(deleted),
        valor_nuevo=str(inserted),
    )

    return {
        "ok": inserted > 0,
        "base": base,
        "idtramite": idtramite,
        "replace_existing": replace_existing,
        "parse_source": parse_source,
        "overrides": {
            "sr_override": sr_override if sr_override > 0 else "",
            "codigoct_override": codigoct_override,
        },
        "duplicates_skipped": duplicates_skipped,
        "rows_deleted": deleted,
        "rows_inserted": inserted,
        "validation": {
            "strict": strict_validate,
            "ok": len(validation_errors) == 0,
            "errors": validation_errors,
        },
        "salary_sanitization": {
            "count": len(salary_sanitize_warnings),
            "warnings_preview": salary_sanitize_warnings[:20],
        },
        "proc_log": log_info,
    }


@router.post("/ruta-inclusion/importar-comisiones-contrato")
def ruta_inclusion_importar_comisiones_contrato(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Carga comisiones en tabla proc, replicando la semántica legacy de `carga contrato`.
    """
    base = as_text(payload.get("base") or "temporal").strip() or "temporal"
    idtramite = as_text(payload.get("idtramite")).strip()
    content = as_text(payload.get("content"))
    usuario = as_text(payload.get("usuario") or "ui_clone").strip()
    replace_existing = bool(payload.get("replace_existing", True))
    if not idtramite:
        raise HTTPException(status_code=400, detail="Campo requerido: idtramite")
    if not content.strip():
        raise HTTPException(status_code=400, detail="Campo requerido: content")

    rows = _parse_comisiones_from_legacy_text(content)

    try:
        execute_by_alias(
            base,
            "CREATE TABLE IF NOT EXISTS proc_servicios_obtenercomisionestramite ("
            "sr int, idtramite numeric, linea int, vendedor text, codigo_vendedor text, venta text, porcentaje text, "
            "fuente text, fecha_insert timestamptz default now())"
        )
    except (ValueError, SQLAlchemyError) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Error preparando tabla de comisiones en {base}: {type(exc).__name__}: {exc}",
        )

    deleted = 0
    inserted = 0
    try:
        if replace_existing:
            deleted = execute_by_alias(
                base,
                "DELETE FROM proc_servicios_obtenercomisionestramite WHERE idtramite = :idtramite",
                {"idtramite": idtramite},
            )
        sql = (
            "INSERT INTO proc_servicios_obtenercomisionestramite("
            "sr,idtramite,linea,vendedor,codigo_vendedor,venta,porcentaje,fuente"
            ") VALUES ("
            ":sr,:idtramite,:linea,:vendedor,:codigo_vendedor,:venta,:porcentaje,:fuente)"
        )
        for i, r in enumerate(rows, start=1):
            execute_by_alias(
                base,
                sql,
                {
                    "sr": i,
                    "idtramite": idtramite,
                    "linea": i,
                    "vendedor": r.get("vendedor", ""),
                    "codigo_vendedor": r.get("codigo_vendedor", "1"),
                    "venta": r.get("venta", "2"),
                    "porcentaje": r.get("porcentaje", "0"),
                    "fuente": "legacy_text",
                },
            )
            inserted += 1
    except (ValueError, SQLAlchemyError) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Error guardando comisiones para tramite {idtramite}: {type(exc).__name__}: {exc}",
        )

    log_info = _proc_log_insert_change(
        base=base,
        idtramite=idtramite,
        usuario=usuario,
        campo="importar_comisiones_contrato",
        valor_anterior=str(deleted),
        valor_nuevo=str(inserted),
    )

    return {
        "ok": True,
        "base": base,
        "idtramite": idtramite,
        "replace_existing": replace_existing,
        "rows_deleted": deleted,
        "rows_inserted": inserted,
        "proc_log": log_info,
    }


@router.post("/ruta-inclusion/importar-sede-contrato")
def ruta_inclusion_importar_sede_contrato(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Carga datos de sede principal desde contrato_*_clean.txt del pipeline Excel
    hacia proc_servicios_obtenersedetramite para el idtramite activo.
    """
    base = as_text(payload.get("base") or "temporal").strip() or "temporal"
    idtramite = as_text(payload.get("idtramite")).strip()
    content = as_text(payload.get("content"))
    usuario = as_text(payload.get("usuario") or "ui_clone").strip()
    strict_validate = bool(payload.get("strict_validate", True))
    replace_existing = bool(payload.get("replace_existing", True))
    auto_skip_empty_clean = bool(payload.get("auto_skip_empty_clean", True))
    if not idtramite:
        raise HTTPException(status_code=400, detail="Campo requerido: idtramite")
    if not content.strip():
        raise HTTPException(status_code=400, detail="Campo requerido: content")

    parsed_rows_preview, _ = _parse_trabajadores_from_sede_clean(content)
    if auto_skip_empty_clean and len(parsed_rows_preview) == 0:
        return {
            "ok": True,
            "skipped": True,
            "reason": "no_worker_rows_detected",
            "base": base,
            "idtramite": idtramite,
            "replace_existing": replace_existing,
            "rows_deleted": 0,
            "rows_inserted": 0,
            "sr_inserted": 0,
            "sede": {},
            "validation": {"strict": strict_validate, "ok": True, "errors": []},
            "proc_log": {"ok": True, "skipped": True},
        }

    try:
        execute_by_alias(
            base,
            "CREATE TABLE IF NOT EXISTS proc_servicios_obtenersedetramite ("
            "sr int, idtramite numeric, codigosede text, nombresede text, direccion text, "
            "telefono text, correo text, ciudad text, zona text, localidad text, departamento text, "
            "tipodocumentoresponsable text, documentoresponsable text, nombreresponsable text, correoresponsable text, "
            "fecha_insert timestamptz default now())"
        )
    except (ValueError, SQLAlchemyError) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Error preparando tabla de sede en {base}: {type(exc).__name__}: {exc}",
        )

    data = _parse_sede_from_contrato_clean(content)
    validation_errors = _validate_sede_import_data(data)
    if strict_validate and validation_errors:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Validación de sede falló. No se realizó actualización.",
                "errors": validation_errors,
                "parsed_preview": data,
            },
        )

    try:
        deleted = 0
        if replace_existing:
            deleted = execute_by_alias(
                base,
                "DELETE FROM proc_servicios_obtenersedetramite WHERE idtramite = :idtramite",
                {"idtramite": idtramite},
            )
        max_sr_rows = fetch_all_by_alias(
            base,
            "SELECT COALESCE(MAX(sr), 0) AS max_sr FROM proc_servicios_obtenersedetramite WHERE idtramite = :idtramite",
            {"idtramite": idtramite},
        )
        next_sr = _to_int_safe((max_sr_rows[0] or {}).get("max_sr"), default=0) + 1
        cols = [
            "sr",
            "idtramite",
            "codigosede",
            "nombresede",
            "direccion",
            "telefono",
            "correo",
            "ciudad",
            "zona",
            "localidad",
            "departamento",
            "tipodocumentoresponsable",
            "documentoresponsable",
            "nombreresponsable",
            "correoresponsable",
        ]
        vals = ", ".join([f":{c}" for c in cols])
        params = {k: data.get(k, "") for k in cols}
        params["sr"] = next_sr
        params["idtramite"] = idtramite
        inserted = execute_by_alias(
            base,
            f"INSERT INTO proc_servicios_obtenersedetramite ({', '.join(cols)}) VALUES ({vals})",
            params,
        )
    except (ValueError, SQLAlchemyError) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Error guardando sede desde contrato para tramite {idtramite}: {type(exc).__name__}: {exc}",
        )

    log_info = _proc_log_insert_change(
        base=base,
        idtramite=idtramite,
        usuario=usuario,
        campo="importar_sede_contrato",
        valor_anterior=str(deleted),
        valor_nuevo=f"codigosede={data.get('codigosede','')}",
    )

    return {
        "ok": inserted > 0,
        "base": base,
        "idtramite": idtramite,
        "replace_existing": replace_existing,
        "rows_deleted": deleted,
        "rows_inserted": inserted,
        "sr_inserted": params.get("sr", 0),
        "sede": data,
        "validation": {
            "strict": strict_validate,
            "ok": len(validation_errors) == 0,
            "errors": validation_errors,
        },
        "proc_log": log_info,
    }


def _query_optional_table_by_idtramite(base: str, table: str, idtramite: str) -> dict[str, Any]:
    try:
        cols = get_table_columns_by_alias(base, table)
    except NoSuchTableError:
        return {"ok": True, "table": table, "exists": False, "count": 0, "rows": []}
    except (ValueError, SQLAlchemyError) as exc:
        return {"ok": False, "table": table, "exists": False, "error": f"{type(exc).__name__}: {exc}", "count": 0, "rows": []}
    if "idtramite" not in {c.lower() for c in cols}:
        return {"ok": True, "table": table, "exists": True, "count": 0, "rows": [], "warning": "sin_columna_idtramite"}
    try:
        rows = fetch_all_by_alias(base, f"SELECT * FROM {table} WHERE idtramite = :idtramite", {"idtramite": idtramite})
        return {"ok": True, "table": table, "exists": True, "count": len(rows), "rows": rows}
    except (ValueError, SQLAlchemyError) as exc:
        return {"ok": False, "table": table, "exists": True, "error": f"{type(exc).__name__}: {exc}", "count": 0, "rows": []}


def _query_optional_table_by_lote(base: str, table: str, lote: str) -> dict[str, Any]:
    if not lote:
        return {"ok": True, "table": table, "exists": False, "count": 0, "rows": [], "warning": "lote_vacio"}
    try:
        cols = get_table_columns_by_alias(base, table)
    except NoSuchTableError:
        return {"ok": True, "table": table, "exists": False, "count": 0, "rows": []}
    except (ValueError, SQLAlchemyError) as exc:
        return {"ok": False, "table": table, "exists": False, "error": f"{type(exc).__name__}: {exc}", "count": 0, "rows": []}
    lower_cols = {c.lower() for c in cols}
    if "lote" not in lower_cols:
        return {"ok": True, "table": table, "exists": True, "count": 0, "rows": [], "warning": "sin_columna_lote"}
    try:
        rows = fetch_all_by_alias(base, f"SELECT * FROM {table} WHERE lote = :lote", {"lote": lote})
        return {"ok": True, "table": table, "exists": True, "count": len(rows), "rows": rows}
    except (ValueError, SQLAlchemyError) as exc:
        return {"ok": False, "table": table, "exists": True, "error": f"{type(exc).__name__}: {exc}", "count": 0, "rows": []}


def _query_centros_for_case(base: str, idtramite: str, lote: str) -> dict[str, Any]:
    by_id = _query_optional_table_by_idtramite(base, "proc_servicios_obtenercentrotrabajotramite", idtramite)
    if bool(by_id.get("exists")) and int(by_id.get("count") or 0) > 0:
        return by_id
    by_lote = _query_optional_table_by_lote(base, "brcentrot", lote)
    if bool(by_lote.get("exists")) and int(by_lote.get("count") or 0) > 0:
        return by_lote
    return by_id if bool(by_id.get("exists")) else by_lote


@router.post("/ruta-inclusion/lectura/pipeline")
def ruta_inclusion_lectura_pipeline(payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    data = payload or {}
    base = as_text(data.get("base") or "temporal").strip() or "temporal"
    limit = int(data.get("limit") or 100)
    if limit < 1:
        limit = 1
    if limit > 2000:
        limit = 2000
    estado = as_text(data.get("estado") or "Estudio").strip()
    idtramite_single = as_text(data.get("idtramite")).strip()
    lote = as_text(data.get("lote")).strip()

    if idtramite_single:
        cabecera_rows = _query_optional_table_by_idtramite(base, "proc_servicios_obtenertramites", idtramite_single).get("rows", [])
    else:
        where_estado = " WHERE estado = :estado" if estado else ""
        params: dict[str, Any] = {"limit": limit}
        if estado:
            params["estado"] = estado
        try:
            cabecera_rows = fetch_all_by_alias(
                base,
                "SELECT * FROM proc_servicios_obtenertramites"
                f"{where_estado} ORDER BY idtramite LIMIT :limit",
                params,
            )
        except (ValueError, SQLAlchemyError) as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Error consultando proc_servicios_obtenertramites en {base}: {type(exc).__name__}: {exc}",
            )

    pipeline_cases: list[dict[str, Any]] = []
    for cab in cabecera_rows:
        idt = as_text(cab.get("idtramite")).strip()
        if not idt:
            continue

        empleador = _query_optional_table_by_idtramite(base, "proc_servicios_obtenerempleadortramite", idt)
        trabajador = _query_optional_table_by_idtramite(base, "proc_servicios_obtenertrabajadortramite", idt)
        sede = _query_optional_table_by_idtramite(base, "proc_servicios_obtenersedetramite", idt)
        centros = _query_centros_for_case(base, idt, lote)
        horas = _query_optional_table_by_idtramite(base, "proc_servicios_obtenerhoraslaborales", idt)
        simultanea = _query_optional_table_by_idtramite(base, "proc_servicios_obtenerafiliacionsimultanea", idt)
        autorizaciones = _query_optional_table_by_idtramite(base, "proc_servicios_obtenerautorizaciones", idt)
        adjuntos = _query_optional_table_by_idtramite(base, "proc_servicios_obtenerarchivosadjuntos", idt)

        adjuntos_enriched = []
        for row in adjuntos.get("rows", []):
            raw = as_text(row.get("rutaadjunto"))
            adjuntos_enriched.append({**row, "rutaadjunto_resuelta": RUTA_ADJ_SERVICE.resolve_origen(raw)})
        adjuntos["rows"] = adjuntos_enriched
        adjuntos["count"] = len(adjuntos_enriched)

        pipeline_cases.append(
            {
                "idtramite": idt,
                "idtipotramite": cab.get("idtipotramite"),
                "tipotramite": cab.get("tipotramite"),
                "idestadotipotramite": cab.get("idestadotipotramite"),
                "estado": cab.get("estado"),
                "permite_modificar": _proc_log_permite_modificar(base=base, idtramite=idt),
                "cabecera": cab,
                "detalle_empleador": empleador,
                "detalle_sede": sede,
                "detalle_centros": centros,
                "detalle_trabajador": trabajador,
                "horas_laborales": horas,
                "afiliacion_simultanea": simultanea,
                "autorizaciones": autorizaciones,
                "adjuntos": adjuntos,
            }
        )

    return {
        "ok": True,
        "base": base,
        "filters": {"idtramite": idtramite_single, "estado": estado, "lote": lote, "limit": limit},
        "pipeline_order": [
            "Proc_Servicios_ObtenerTramites",
            "Proc_Servicios_ObtenerEmpleadorTramite",
            "Proc_Servicios_ObtenerSedeTramite",
            "Proc_Servicios_ObtenerTrabajadorTramite",
            "Proc_Servicios_ObtenerHorasLaborales",
            "Proc_Servicios_ObtenerAfiliacionSimultanea",
            "Proc_Servicios_ObtenerAutorizaciones",
            "Proc_Servicios_ObtenerArchivosAdjuntos",
        ],
        "notes": {
            "idtramite_is_primary_key_for_imagine": True,
            "tipotramite_operativo_constante": {"idtipotramite": 1, "tipotramite": "723"},
            "pendientes_sp_is_consuming": True,
            "detalle_is_requeryable": True,
        },
        "count": len(pipeline_cases),
        "cases": pipeline_cases,
    }


@router.post("/ruta-inclusion/run-full")
def ruta_inclusion_run_full(payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    data = payload or {}
    base = as_text(data.get("base") or "temporal").strip() or "temporal"
    lote = as_text(data.get("lote")).strip() or f"PROC-{datetime.now().strftime('%Y%m%d')}"
    estado = as_text(data.get("estado") or "Estudio").strip()
    idtramite = as_text(data.get("idtramite")).strip()
    limit = int(data.get("limit") or 200)
    strict_validate = bool(data.get("strict_validate", True))
    apply_reproceso = bool(data.get("apply_reproceso", False))
    build_flatfile = bool(data.get("build_flatfile", True))
    include_observaciones_csv = bool(data.get("include_observaciones_csv", True))
    fecha_proceso = as_text(data.get("fecha_proceso")).strip()

    import_out = _load_proc_servicios_to_engine(
        {
            "base": base,
            "lote": lote,
            "estado": estado,
            "idtramite": idtramite,
            "limit": limit,
            "fecha_proceso": fecha_proceso,
            "apply_to_db": bool(data.get("apply_to_db", False)),
        }
    )

    precheck = _prebuild_rules_check(lote=lote)
    split = _reproceso_split_by_precheck(lote=lote, precheck=precheck, apply=apply_reproceso)
    validaciones_legacy = _ruta_inclusion_validaciones_scope(
        base=base,
        estado=estado,
        idtramite=idtramite,
        limit=limit,
    )
    observaciones_csv = (
        _observaciones_csv(lote=lote, precheck=precheck, include_warnings=bool(data.get("include_warnings", True)))
        if include_observaciones_csv
        else ""
    )

    if strict_validate and (not precheck.get("ok", False) or not validaciones_legacy.get("ok", False)):
        return {
            "ok": False,
            "stage": "precheck",
            "base": base,
            "lote": lote,
            "import": import_out,
            "precheck": precheck,
            "validaciones_legacy": validaciones_legacy,
            "split": split,
            "observaciones_csv": observaciones_csv,
            "message": "Prevalidacion de reglas fallo; plano no generado.",
        }

    flatfile_b64 = ""
    flatfile_size = 0
    if build_flatfile:
        content = LEGACY_ENGINE.generate_flatfile_926(lote=lote)
        flatfile_size = len(content or b"")
        flatfile_b64 = (content or b"").decode("latin-1", errors="replace")

    return {
        "ok": True,
        "base": base,
        "lote": lote,
        "import": import_out,
        "precheck": precheck,
        "validaciones_legacy": validaciones_legacy,
        "split": split,
        "applied_reproceso": apply_reproceso,
        "build_flatfile": build_flatfile,
        "flatfile_size_bytes": flatfile_size,
        "flatfile_content_latin1": flatfile_b64,
        "observaciones_csv": observaciones_csv,
        "pipeline_order": [
            "import-proc-servicios",
            "rules-prebuild-check",
            "rules-reproceso-lote",
            "flatfile-build",
        ],
    }


@router.get("/ruta-inclusion/plano/{idtramite}")
def ruta_inclusion_plano_by_idtramite(
    idtramite: str,
    base: str = "temporal",
    estado: str = "Estudio",
    lote: str = "",
    strict_validate: bool = True,
    fecha_proceso: str = "",
) -> Response:
    data = {
        "base": base,
        "lote": lote or f"PLANO-{idtramite}",
        "estado": estado,
        "idtramite": idtramite,
        # Debe traer todas las filas del tramite (empleador + N trabajadores).
        # Usar limit=1 truncaba el JOIN y generaba plano incompleto.
        "limit": 5000,
        "strict_validate": strict_validate,
        "apply_reproceso": False,
        "build_flatfile": True,
        "include_observaciones_csv": True,
        "apply_to_db": False,
        "fecha_proceso": fecha_proceso,
    }
    out = ruta_inclusion_run_full(data)
    if not out.get("ok", False):
        raise HTTPException(
            status_code=400,
            detail={
                "message": "No se pudo generar plano para idtramite.",
                "result": out,
            },
        )

    flat_text = as_text(out.get("flatfile_content_latin1"))
    if flat_text == "":
        raise HTTPException(status_code=404, detail="Plano vacio para los filtros solicitados.")

    tipo_cargue = _ruta_inclusion_tipo_cargue_local(base=base, idtramite=idtramite, numide="0")
    tipo_tramite = as_text(tipo_cargue.get("tipo_tramite"))
    fname_prefix = "planoAfiNov" if tipo_tramite == "Novedad" else "planoIndp"
    filename = f"{fname_prefix}_{idtramite}.txt"
    content = flat_text.encode("latin-1", errors="replace")
    return Response(
        content=content,
        media_type="text/plain; charset=latin-1",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/ruta-inclusion/actualizaestado/options")
def ruta_inclusion_actualizaestado_options(base: str = "temporal", limit: int = 200) -> dict[str, Any]:
    if limit < 1:
        limit = 1
    if limit > 2000:
        limit = 2000
    try:
        rows = fetch_all_by_alias(
            base,
            "SELECT idtramite, estado, fecharegistro "
            "FROM proc_servicios_obtenertramites "
            "WHERE UPPER(TRIM(COALESCE(estado,''))) IN ('ESTUDIO','DEVUELTO','AFILIADO') "
            "ORDER BY fecharegistro DESC NULLS LAST, idtramite DESC "
            "LIMIT :limit",
            {"limit": limit},
        )
        # Fallback: si no hay estados procesables exactos, mostrar tramites recientes
        # para no dejar el selector vacio en ambientes con datos sucios/inconsistentes.
        if not rows:
            rows = fetch_all_by_alias(
                base,
                "SELECT idtramite, estado, fecharegistro "
                "FROM proc_servicios_obtenertramites "
                "WHERE idtramite IS NOT NULL "
                "ORDER BY fecharegistro DESC NULLS LAST, idtramite DESC "
                "LIMIT :limit",
                {"limit": limit},
            )
    except (ValueError, SQLAlchemyError) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Error cargando opciones de actualizaestado en {base}: {type(exc).__name__}: {exc}",
        )
    items = []
    for row in rows:
        idt = as_text(row.get("idtramite")).strip()
        if not idt:
            continue
        items.append(
            {
                "idtramite": idt,
                "estado": as_text(row.get("estado")),
                "fecharegistro": as_text(row.get("fecharegistro")),
                "label": f"{idt} - {as_text(row.get('estado'))}",
            }
        )
    return {"ok": True, "base": base, "count": len(items), "items": items}


@router.post("/ruta-inclusion/actualizaestado")
def ruta_inclusion_actualizaestado(payload: dict[str, Any]) -> dict[str, Any]:
    base = as_text(payload.get("base") or "temporal").strip() or "temporal"
    idtramite = as_text(payload.get("idtramite")).strip()
    if not idtramite:
        indep = _legacy_form_section(payload, "IndependientesApolo")
        idtramite = as_text(indep.get("idtramite")).strip()
    if not idtramite:
        raise HTTPException(status_code=400, detail="Campo requerido: idtramite")

    import_out = _load_proc_servicios_to_engine(
        {
            "base": base,
            "lote": f"AE-{idtramite}",
            "idtramite": idtramite,
            "limit": 1,
            "apply_to_db": bool(payload.get("apply_to_db", False)),
        }
    )
    precheck = _prebuild_rules_check(lote=f"AE-{idtramite}")
    return {
        "ok": True,
        "base": base,
        "idtramite": idtramite,
        "import": import_out,
        "precheck": precheck,
        "message": "Proceso Finalizado con exito!",
    }


@router.post("/ruta-inclusion/actualizaestado-legacy")
def ruta_inclusion_actualizaestado_legacy(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Compatibilidad con actionActualizaestado del PHP:
    - recibe IndependientesApolo[idtramite]
    - responde status/content literal para ajax legacy
    """
    base = as_text(payload.get("base") or "temporal").strip() or "temporal"
    try:
        out = ruta_inclusion_actualizaestado({**payload, "base": base})
    except HTTPException as exc:
        return {"status": "error", "content": as_text(exc.detail)}
    return {
        "status": "success",
        "content": "<div class=\"alert alert-success\" role=\"alert\">Proceso Finalizado con exito!</div>",
        "raw": out,
    }


@router.post("/ruta-inclusion/codificaid-legacy")
def ruta_inclusion_codificaid_legacy(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Equivale a actionCodificaid:
    recibe idtipotramite y devuelve URL de gestioncaso con id codificado.
    """
    idtipotramite = as_text(payload.get("idtipotramite")).strip()
    if not idtipotramite:
        return {"status": "error", "content": "idtipotramite es obligatorio"}
    encoded = base64.b64encode(idtipotramite.encode("utf-8")).decode("ascii")
    url = f"gestioncaso?idtipotramite={encoded}"
    return {"status": "success", "content": url, "idtipotramite": encoded}


@router.post("/ruta-inclusion/codifica-consulta-id-legacy")
def ruta_inclusion_codifica_consulta_id_legacy(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Equivale a actionCodificaConsultaId:
    recibe idtipotramite y devuelve URL de consultacaso con id codificado.
    """
    idtipotramite = as_text(payload.get("idtipotramite")).strip()
    if not idtipotramite:
        return {"status": "error", "content": "idtipotramite es obligatorio"}
    encoded = base64.b64encode(idtipotramite.encode("utf-8")).decode("ascii")
    url = f"consultacaso?idtipotramite={encoded}"
    return {"status": "success", "content": url, "idtipotramite": encoded}


@router.post("/ruta-inclusion/gestioncaso-legacy-open")
def ruta_inclusion_gestioncaso_legacy_open(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Equivale a actionGestioncaso (apertura de pantalla por id codificado).
    """
    encoded = as_text(payload.get("idtipotramite")).strip()
    if not encoded:
        return {"status": "error", "content": "idtipotramite es obligatorio"}
    try:
        decoded = base64.b64decode(encoded.encode("ascii")).decode("utf-8", errors="ignore").strip()
    except Exception:
        return {"status": "error", "content": "idtipotramite invalido"}
    if not decoded:
        return {"status": "error", "content": "idtipotramite invalido"}
    return {
        "status": "success",
        "content": {
            "screen": "gestioncaso",
            "idtipotramite": decoded,
            "idtramite": decoded,
            "url": f"gestioncaso?idtipotramite={encoded}",
        },
    }


@router.post("/ruta-inclusion/consultacaso-legacy-open")
def ruta_inclusion_consultacaso_legacy_open(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Equivale a actionConsultacaso (apertura de pantalla por id codificado).
    """
    encoded = as_text(payload.get("idtipotramite")).strip()
    if not encoded:
        return {"status": "error", "content": "idtipotramite es obligatorio"}
    try:
        decoded = base64.b64decode(encoded.encode("ascii")).decode("utf-8", errors="ignore").strip()
    except Exception:
        return {"status": "error", "content": "idtipotramite invalido"}
    if not decoded:
        return {"status": "error", "content": "idtipotramite invalido"}
    return {
        "status": "success",
        "content": {
            "screen": "consultacaso",
            "idtipotramite": decoded,
            "idtramite": decoded,
            "url": f"consultacaso?idtipotramite={encoded}",
        },
    }


def _ruta_inclusion_grid_payload(*, base: str, estado: str, actividad: int, limit: int) -> dict[str, Any]:
    pipe = ruta_inclusion_lectura_pipeline({"base": base, "estado": estado, "limit": limit})
    cases = list(pipe.get("cases", []))
    if actividad == 378:
        cases = [c for c in cases if int(c.get("adjuntos", {}).get("count", 0) or 0) > 0]
    nombre_actividad = {378: "Pendientes Imagine", 379: "Creacion de sede"}.get(actividad, f"Actividad {actividad}")
    for case in cases:
        case["actividad"] = actividad
        case["nombre_actividad"] = nombre_actividad
        case["cantiadj"] = int(case.get("adjuntos", {}).get("count", 0) or 0)
    return {
        "ok": True,
        "status": "success",
        "content": {
            "screen": "pendientes",
            "actividad": actividad,
            "count": len(cases),
            "cases": cases,
        },
    }


@router.post("/ruta-inclusion/pendientes-legacy-open")
def ruta_inclusion_pendientes_legacy_open(payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """
    Equivale a actionPendientes (actividad 378).
    """
    data = payload or {}
    base = as_text(data.get("base") or "temporal").strip() or "temporal"
    limit = int(data.get("limit") or 200)
    if limit < 1:
        limit = 1
    if limit > 2000:
        limit = 2000
    return _ruta_inclusion_grid_payload(base=base, estado="Estudio", actividad=378, limit=limit)


@router.post("/ruta-inclusion/cargue-legacy-open")
def ruta_inclusion_cargue_legacy_open(payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """
    Equivale a actionCargue (actividad 379).
    """
    data = payload or {}
    base = as_text(data.get("base") or "temporal").strip() or "temporal"
    limit = int(data.get("limit") or 200)
    if limit < 1:
        limit = 1
    if limit > 2000:
        limit = 2000
    return _ruta_inclusion_grid_payload(base=base, estado="Estudio", actividad=379, limit=limit)


@router.post("/ruta-inclusion/consulta-legacy-open")
def ruta_inclusion_consulta_legacy_open(payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """
    Equivale a actionConsulta (consulta general no consumible desde tablas locales).
    """
    data = payload or {}
    base = as_text(data.get("base") or "temporal").strip() or "temporal"
    limit = int(data.get("limit") or 500)
    if limit < 1:
        limit = 1
    if limit > 5000:
        limit = 5000
    try:
        rows = fetch_all_by_alias(
            base,
            "SELECT * FROM proc_servicios_consulta ORDER BY idtramite DESC LIMIT :limit",
            {"limit": limit},
        )
    except NoSuchTableError:
        rows = []
    except (ValueError, SQLAlchemyError) as exc:
        raise HTTPException(status_code=503, detail=f"Error consultando proc_servicios_consulta en {base}: {type(exc).__name__}: {exc}")
    return {
        "ok": True,
        "status": "success",
        "content": {
            "screen": "consulta",
            "count": len(rows),
            "rows": rows,
        },
    }


@router.post("/ruta-inclusion/generar-planos-tramite-legacy")
def ruta_inclusion_generar_planos_tramite_legacy(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Equivale a actionGenerarPlanosTramite:
    retorna URL de generaPlanoTramiteId.
    """
    idtramite = as_text(payload.get("idtramite")).strip()
    tipo_tramite = as_text(payload.get("tipo_tramite")).strip()
    if not idtramite:
        return {"status": "error", "content": "idtramite es obligatorio"}
    url = f"generaPlanoTramiteId?idtramite={idtramite}&tipo_tramite={tipo_tramite}"
    return {"status": "success", "content": url}


@router.get("/ruta-inclusion/genera-plano-tramite-id-legacy")
def ruta_inclusion_genera_plano_tramite_id_legacy(
    idtramite: str,
    tipo_tramite: str = "",
    base: str = "temporal",
) -> Response:
    """
    Equivale a actionGeneraPlanoTramiteId.
    En clone delega al endpoint moderno de plano por trámite.
    """
    _ = tipo_tramite  # se conserva por compatibilidad de firma.
    return ruta_inclusion_plano_by_idtramite(idtramite=idtramite, base=base, estado="Estudio", lote="", strict_validate=True)
