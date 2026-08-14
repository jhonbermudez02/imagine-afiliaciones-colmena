#!/usr/bin/env python3
import csv
import hashlib
import json
import os
import unicodedata
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from io import StringIO
from pathlib import Path
from typing import Dict, List, Any, Optional, Set
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
STATIC_DIR = ROOT / "frontend"
ACTIVITY_ECONOMICA_ARP_PATH = DATA_DIR / "actividad_economica_arp.json"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_env(path: Path) -> Dict[str, str]:
    env: Dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
    return env


ENV = load_env(ROOT / ".env")


def _norm_lote_key(value: str) -> str:
    # Postgres almacena `lt`/`lote` como integer/numeric (sin ceros a la izquierda),
    # pero el "lote usuario" generado por la app nueva viene con padding (ej "000000000004").
    # Sin esta normalizacion, la comparacion de igualdad de texto nunca calza y el
    # plano 926 sale vacio aunque los datos reales ya esten sincronizados en el engine.
    v = value.strip()
    if v.isdigit():
        return str(int(v))
    return v


def as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


class LegacyCompatEngine:
    CATALOG_SYNONYMS: Dict[str, Dict[str, str]] = {
        "jornada": {
            "": "",
            "UNICA": "UNICA",
            "JORNADA UNICA": "UNICA",
            "UNICO": "UNICA",
            "TURNO": "TURNOS",
            "TURNOS": "TURNOS",
            "ROTATIVO": "ROTATIVA",
            "ROTATIVA": "ROTATIVA",
        },
        "modalidad": {
            "": "PRESENCIAL",
            "PRESENCIAL": "PRESENCIAL",
            "EN SITIO": "PRESENCIAL",
            "SITIO": "PRESENCIAL",
            "TELETRABAJO": "TELETRABAJO",
            "TRABAJO EN CASA": "CASA",
            "CASA": "CASA",
            "TRABAJO REMOTO": "REMOTO",
            "REMOTO": "REMOTO",
        },
        "sexo": {
            "M": "M",
            "MASCULINO": "M",
            "F": "F",
            "FEMENINO": "F",
            "T": "T",
            "N": "N",
            "O": "O",
            "OTRO": "O",
        },
        "tipo_salario": {
            "": "",
            "FIJO": "FIJO",
            "FIJA": "FIJO",
            "F": "FIJO",
            "VARIABLE": "VARIABLE",
            "VAR": "VARIABLE",
            "V": "VARIABLE",
        },
    }

    TABLE_COLUMNS: Dict[str, List[str]] = {
        "wh": [
            "sr", "tp", "lt", "f01", "f05", "f12", "f17", "f18", "f51", "f55",
            "producto", "doccont1", "nomcont1", "carcont1", "dircont1", "ciucont1",
            "nomciucont1", "depcont1", "nomdepcont1", "emailcont1", "nomcont2",
            "carcont2", "dircont2", "ciucont2", "nomciucont2", "depcont2", "emailcont2",
            "f13", "f69", "f71", "obdev", "tipoempresa", "grupoecono"
        ],
        "wd": [
            "sr", "li", "lt", "f28", "f31", "f32", "f33", "f34", "f35", "f37", "f38",
            "telefono", "celular", "mail", "direccion", "localidad", "jornada", "tipo_salario"
        ],
        "wddias": ["sr", "dia", "lote", *[f"h{i}" for i in range(1, 25)]],
        "wcentrot": ["sr", "codigoct", "codigoactividad", "direccion", "lote", "totaltrabajadores", "montocotizacion"],
        "wdestudiantes": ["sr", "linea", "documento", "salario", "meses", "monto_contrato", "lote", "tipo_salario"],
        "wdindependientes": ["sr", "linea", "documento", "ibc", "lote", "tipo_salario"],
        "wdcomisiones": ["sr", "linea", "vendedor", "codigo_vendedor", "venta", "porcentaje", "lote"],
    }

    TR_LAYOUTS: Dict[str, Dict[str, Any]] = {
        "General-Recobrar": {
            "table": "brempresasarp",
            "delimiter": ",",
            "append_path": True,
            "fields": [
                "sr", "f01", "f50", "f48", "f51", "f15", "f16", "f12", "f14", "f20", "f06", "f04", "f05", "f27",
                "f25", "f49", "f02", "f56", "f63", "f24", "f53", "f18", "f23", "f57", "f09", "f59", "f62", "f55",
                "f10", "f03", "f08", "f07", "f17", "f11", "f13", "f19", "f54", "f58", "f60", "f61", "f69", "f64",
                "f65", "f70", "f66", "f67", "f71", "f68", "doccont1", "nomcont1", "carcont1", "dircont1", "ciucont1",
                "nomciucont1", "depcont1", "nomdepcont1", "telcont1", "telcont21", "emailcont1", "doccont2", "nomcont2",
                "carcont2", "dircont2", "ciucont2", "nomciucont2", "depcont2", "nomdepcont2", "telcont2", "telcont22",
                "emailcont2", "dev", "fp", "tp", "ci", "cf", "lt", "e0", "e1", "e2", "e3", "e4", "e5", "e6", "e7",
                "e8", "e9", "e10", "e11", "e12", "e13", "e14", "e15", "e16", "e17", "e18", "e19", "e20", "vs", "zo",
                "d1", "us", "ob", "combo50", "combo15", "combo16", "combo05", "combo56", "combo24", "combo23", "combo57",
                "pi", "clase", "obdev", "contratoant", "tipoempresa", "grupoecono", "tipoafiliacion", "tipoaportante",
                "tipoafiliado", "tipocodigo", "subtipoafiliado", "subtipocodigo", "zona", "localidad", "departamento", "aut46",
                "aut47", "aut48"
            ],
            "defaults": {
                "f07": "0", "clase": "0", "obdev": "0", "contratoant": "0", "tipoempresa": "0", "grupoecono": "0",
                "tipoafiliacion": "0", "tipoaportante": "0"
            }
        },
        "General-Recobrar-2": {
            "table": "brafiliadosarp",
            "delimiter": ",",
            "append_path": True,
            "fields": [
                "sr", "li", "f28", "f36", "f29", "f30", "f31", "f32", "f33", "f34", "f35", "f37", "f38", "f40",
                "f41", "e0", "e1", "e2", "e3", "e4", "e5", "e6", "e7", "e8", "e9", "e10", "e11", "e12", "ob",
                "lt", "combo40", "combo41", "telefono", "celular", "mail", "direccion", "municipio", "zona", "localidad",
                "departamento", "modalidad", "jornada", "trabajoalturas", "tipo_salario"
            ]
        },
        "General-Recobrar-3": {
            "table": "brwddias",
            "delimiter": ",",
            "append_path": True,
            "fields": ["sr", "dia", *[f"h{i}" for i in range(1, 25)], "lote"]
        },
        "General-Recobrar-4": {
            "table": "brcentrot",
            "delimiter": ",",
            "append_path": True,
            "fields": [
                "sr", "codigoct", "codigoactividad", "nombreactividad", "totaltrabajadores", "claseriesgo", "montocotizacion",
                "ciudad", "departamento", "zona", "direccion", "telefono", "tipodocumento", "id_responsable", "primerapellido",
                "segundoapellido", "primernombre", "segundonombre", "mail", "lote"
            ]
        },
        "General-Recobrar-5": {
            "table": "brwdestudiantes",
            "delimiter": ",",
            "append_path": False,
            "fields": [
                "sr", "linea", "codigo_ct", "tipodocumento", "documento", "primer_apellido", "segundo_apellido", "primer_nombre",
                "segundo_nombre", "fecha_nacimiento", "sexo", "cargo", "salario", "eps", "afp", "direccion", "telefono",
                "celular", "correo", "ciudad", "localidad", "zona", "departamento", "jornada", "modalidad",
                "codigo_tipo_trabajador", "tipo_trabajador", "subtipo_afiliado", "actividad_especial", "codigo_actividad",
                "fecha_inicio", "fecha_final", "meses", "tipo_contrato", "monto_contrato", "lunes", "martes", "miercoles",
                "jueves", "viernes", "sabado", "domingo", "d1", "d2", "d3", "d4", "d5", "d6", "d7", "d8", "d9", "d10",
                "d11", "d12", "d13", "d14", "d15", "d16", "d17", "d18", "d19", "d20", "d21", "d22", "d23", "d24",
                "lote", "tipo_salario"
            ]
        },
        "General-Recobrar-6": {
            "table": "brwdindependientes",
            "delimiter": "!",
            "append_path": True,
            "fields": [
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
                "tipo_salario"
            ]
        },
        "General-Recobrar-7": {
            "table": "brwdcomisiones",
            "delimiter": ",",
            "append_path": False,
            "fields": ["sr", "linea", "vendedor", "codigo_vendedor", "venta", "porcentaje", "lote"]
        }
    }
    DEV_LAYOUTS: Dict[str, Dict[str, Any]] = {
        "General-Recobrar": {**TR_LAYOUTS["General-Recobrar"], "table": "devempresasarp"},
        "General-Recobrar-2": {**TR_LAYOUTS["General-Recobrar-2"], "table": "devafiliadosarp"},
        "General-Recobrar-3": {**TR_LAYOUTS["General-Recobrar-3"], "table": "devwddias"},
        "General-Recobrar-4": {**TR_LAYOUTS["General-Recobrar-4"], "table": "devcentrot"},
        "General-Recobrar-5": {**TR_LAYOUTS["General-Recobrar-5"], "table": "devwdestudiantes"},
        "General-Recobrar-6": {**TR_LAYOUTS["General-Recobrar-6"], "table": "devwdindependientes"},
        "General-Recobrar-7": {**TR_LAYOUTS["General-Recobrar-7"], "table": "devwdcomisiones"},
    }

    def __init__(self, state_path: Path):
        self.state_path = state_path
        self.state = self._load_state()
        self._activity_economica_arp_cache: Optional[Dict[str, Dict[str, Any]]] = None

    def _load_state(self) -> Dict[str, Any]:
        if self.state_path.exists():
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        return {"tables": {}, "meta": {}}

    def _save_state(self) -> None:
        # Filas leídas de Postgres pueden traer Decimal/date/datetime (columnas numeric/timestamp),
        # que json no serializa por defecto.
        self.state_path.write_text(
            json.dumps(self.state, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )

    def _rows(self, table: str, db: str = "") -> List[Dict[str, Any]]:
        t = table.lower()
        if db:
            key = f"{db.lower()}.{t}"
            if key in self.state.get("tables", {}):
                return self.state["tables"][key]
        if t in self.state.get("tables", {}):
            return self.state["tables"][t]
        return []

    def _activity_economica_arp(self) -> Dict[str, Dict[str, Any]]:
        if self._activity_economica_arp_cache is not None:
            return self._activity_economica_arp_cache
        catalog: Dict[str, Dict[str, Any]] = {}
        try:
            payload = json.loads(ACTIVITY_ECONOMICA_ARP_PATH.read_text(encoding="utf-8"))
        except Exception:
            payload = []
        for item in payload or []:
            if not isinstance(item, dict):
                continue
            code = "".join(ch for ch in as_text(item.get("codigo")) if ch.isdigit())
            if not code:
                continue
            catalog[code] = item
        self._activity_economica_arp_cache = catalog
        return catalog

    def _activity_risk_profile(self, codigoactividad: Any) -> Dict[str, str]:
        code = "".join(ch for ch in as_text(codigoactividad) if ch.isdigit())
        row = self._activity_economica_arp().get(code) or {}
        return {
            "codigo": code,
            "clase": as_text(row.get("clase") or row.get("claries")).strip(),
            "grado": as_text(row.get("grado")).strip(),
            "tasa": as_text(row.get("tasa")).replace(",", ".").strip(),
            "nombre": as_text(row.get("nombre")).strip(),
        }

    @staticmethod
    def _format_tasa_arp(value: Any) -> str:
        raw = as_text(value).replace(",", ".").strip()
        if raw in {"", "0", "0.0", "0.00", "0.000", "0.0000", "00000"}:
            return ""
        try:
            raw = f"{float(raw):.3f}"
        except Exception:
            pass
        return raw[:5].ljust(5, "0")

    def _set_rows(self, table: str, rows: List[Dict[str, Any]], db: str = "") -> None:
        key = f"{db.lower()}.{table.lower()}" if db else table.lower()
        self.state.setdefault("tables", {})[key] = rows

    def _delete_where(self, table: str, db: str, field: str, value: str) -> None:
        rows = self._rows(table, db)
        self._set_rows(table, [r for r in rows if as_text(r.get(field)) != as_text(value)], db)

    def _copy_table_by_field(self, src_db: str, dst_db: str, table: str, field: str, value: str) -> None:
        src_rows = self._rows(table, src_db)
        dst_rows = self._rows(table, dst_db)
        filtered = [dict(r) for r in src_rows if as_text(r.get(field)) == as_text(value)]
        remain = [r for r in dst_rows if as_text(r.get(field)) != as_text(value)]
        self._set_rows(table, remain + filtered, dst_db)

    def load_dump(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        tables = payload.get("tables", {})
        meta = payload.get("meta", {})

        normalized_tables: Dict[str, List[Dict[str, Any]]] = {}
        for table_name, rows in tables.items():
            lower = table_name.lower()
            normalized_rows: List[Dict[str, Any]] = []
            for row in rows:
                if isinstance(row, dict):
                    nr = {k.lower(): row[k] for k in row.keys()}
                else:
                    nr = {"raw": row}
                normalized_rows.append(nr)
            normalized_tables[lower] = normalized_rows

        self.state = {"tables": normalized_tables, "meta": meta}
        self._save_state()
        return {"ok": True, "tables": {k: len(v) for k, v in normalized_tables.items()}}

    def load_flatfile_926(self, content: str) -> Dict[str, Any]:
        lines = [ln.rstrip("\r") for ln in content.splitlines() if ln.strip() != ""]
        wh: List[Dict[str, Any]] = []
        wd: List[Dict[str, Any]] = []
        wddias: List[Dict[str, Any]] = []
        wcentrot: List[Dict[str, Any]] = []
        wdestudiantes: List[Dict[str, Any]] = []
        wdindependientes: List[Dict[str, Any]] = []
        wdcomisiones: List[Dict[str, Any]] = []

        for idx, line in enumerate(lines, start=1):
            t1 = line[:1]
            t2 = line[:2]
            rec = {"line_no": idx, "raw": line}
            if t1 == "1":
                rec["tp"] = "P"
                rec["f01"] = line[3:18].strip()
                rec["f51"] = line[22:76].strip()
                rec["f12"] = line[76:110].strip()
                wh.append(rec)
            elif t1 == "7":
                rec["tp"] = "S"
                rec["f62"] = line[1:7].strip()
                rec["f71"] = line[7:41].strip()
                wh.append(rec)
            elif t1 == "5":
                # Responsable sede/centro; se conserva en wh para trazabilidad de armado.
                wh.append(rec)
            elif t1 == "2":
                rec["codigoct"] = line[1:7].strip()
                rec["nombreactividad"] = line[7:41].strip()
                wcentrot.append(rec)
            elif t1 == "3":
                rec["f28"] = line[3:18].strip()
                rec["f31"] = line[18:33].strip()
                rec["f32"] = line[33:48].strip()
                rec["f33"] = line[48:68].strip()
                rec["f34"] = line[68:69].strip()
                rec["f35"] = line[69:77].strip()
                wd.append(rec)
            elif t1 == "4":
                rec["linea"] = line[1:3].strip()
                rec["vendedor"] = line[7:22].strip()
                wdcomisiones.append(rec)
            elif t2 in {"61", "62", "63", "64", "65"}:
                rec["dia"] = t2
                wddias.append(rec)

        tables = {
            "wh": wh,
            "wd": wd,
            "wddias": wddias,
            "wcentrot": wcentrot,
            "wdestudiantes": wdestudiantes,
            "wdindependientes": wdindependientes,
            "wdcomisiones": wdcomisiones,
        }
        self.state = {
            "tables": tables,
            "meta": {
                "flatfile_reference_raw": content,
                "flatfile_reference_lines": lines,
                "flatfile_reference_enabled": True,
            },
        }
        self._save_state()
        return {"ok": True, "line_count": len(lines), "tables": {k: len(v) for k, v in tables.items()}}

    def load_ls_archivo_txt(self, fileid: str, content: str) -> Dict[str, Any]:
        fileid = as_text(fileid).strip()
        if fileid == "":
            return {"ok": False, "error": "fileid es obligatorio"}

        lines = [ln.rstrip("\r") for ln in as_text(content).splitlines() if ln.strip() != ""]
        parsed_rows: List[Dict[str, Any]] = []
        rejected = 0

        def _parse_doc_name_from_pipe(tokens: List[str]) -> Optional[Dict[str, str]]:
            # Layout esperado en trabajadores:
            # idx2=tipodoc, idx3=documento, idx4..idx7=apellidos/nombres
            if len(tokens) >= 8 and tokens[2].upper() in {"CC", "CE", "TI", "RC", "PA", "PT", "SC", "CD"}:
                doc = as_text(tokens[3]).strip()
                names = [as_text(x).strip() for x in tokens[4:8] if as_text(x).strip().upper() not in {"", "NULL"}]
                if doc != "" and names:
                    return {"c0": doc, "c1": " ".join(names)}
            return None

        for idx, ln in enumerate(lines, start=1):
            c0 = ""
            c1 = ""
            if "," in ln:
                parts = [p.strip() for p in ln.split(",", 1)]
                if len(parts) >= 2:
                    c0, c1 = parts[0], parts[1]
            elif "|" in ln:
                tokens = [p.strip() for p in ln.split("|")]
                parsed_pipe = _parse_doc_name_from_pipe(tokens)
                if parsed_pipe is not None:
                    c0, c1 = parsed_pipe["c0"], parsed_pipe["c1"]

            if c0 == "" or c1 == "":
                rejected += 1
                continue
            parsed_rows.append(
                {
                    "fileid": fileid,
                    "c0": c0,
                    "c1": c1,
                    "line_no": idx,
                }
            )

        ix_rows = self._rows("ix", "temporal")
        keep = [r for r in ix_rows if as_text(r.get("fileid")).strip() != fileid]
        self._set_rows("ix", keep + parsed_rows, "temporal")
        self._save_state()
        return {
            "ok": True,
            "fileid": fileid,
            "inserted": len(parsed_rows),
            "rejected": rejected,
            "line_count": len(lines),
        }

    def normalize_cd(self) -> Dict[str, Any]:
        wh = self._rows("wh")
        wd = self._rows("wd")

        lote = ""
        for row in wh:
            if as_text(row.get("tp")).upper() == "P":
                lote = as_text(row.get("lt"))
                break

        for row in wh:
            for f in ["f51", "f12", "f18", "f55"]:
                row[f] = as_text(row.get(f)).strip()
            row["f51"] = as_text(row.get("f51")).replace(",", "")
            row["f12"] = as_text(row.get("f12")).replace(",", " ").replace("#", "")
            row["dircont1"] = as_text(row.get("dircont1")).replace("#", "")
            row["dircont2"] = as_text(row.get("dircont2")).replace("#", "")

            for zero_if_empty in [
                "f17", "f05", "nomcont1", "carcont1", "dircont1", "ciucont1", "nomciucont1",
                "depcont1", "nomdepcont1", "emailcont1", "nomcont2", "carcont2", "dircont2",
                "ciucont2", "nomciucont2", "depcont2", "emailcont2", "f13", "f69", "f71",
                "obdev", "tipoempresa", "grupoecono"
            ]:
                if as_text(row.get(zero_if_empty)) == "":
                    row[zero_if_empty] = "0"

        for row in wd:
            if lote:
                row["lt"] = lote
            for f in ["f28", "f31", "f32", "f33", "f37", "mail", "direccion", "localidad"]:
                row[f] = as_text(row.get(f)).strip()
            row["direccion"] = as_text(row.get("direccion")).replace("#", "").replace(",", " ")
            for zero_if_empty in ["f35", "celular", "telefono"]:
                if as_text(row.get(zero_if_empty)) == "":
                    row[zero_if_empty] = "0"

        for table in ["wddias", "wcentrot", "wdestudiantes", "wdindependientes", "wdcomisiones"]:
            for row in self._rows(table):
                row["lote"] = lote

        self._save_state()
        return {"ok": True, "lote": lote, "rows": {"wh": len(wh), "wd": len(wd)}}

    def validate_cd(self) -> Dict[str, Any]:
        wh = self._rows("wh")
        wd = self._rows("wd")
        errors: List[str] = []
        warnings: List[str] = []

        if not wh:
            errors.append("No hay registros en WH para indexar")

        has_producto = any(as_text(r.get("producto")) for r in wh)
        if not has_producto:
            errors.append("Campo producto vacío en WH")

        count_p = sum(1 for r in wh if as_text(r.get("tp")).upper() == "P")
        count_v = sum(1 for r in wh if as_text(r.get("tp")).upper() == "V")
        if count_p > 1:
            errors.append("Existe más de un registro TP='P'")
        if count_v > 1:
            errors.append("Existe más de un registro TP='V'")

        valid_jornada = {"UNICA", "TURNOS", "ROTATIVA"}
        bad_jornada = [
            r
            for r in wd
            if as_text(r.get("f28")) > "0"
            and self._catalog_normalize("jornada", r.get("jornada"), default="") not in valid_jornada
        ]
        if bad_jornada:
            errors.append(f"Jornada inválida en {len(bad_jornada)} afiliados")

        valid_sexo = {"M", "F", "T", "N", "O"}
        bad_sexo = [
            r
            for r in wd
            if as_text(r.get("f28")) > "0"
            and self._catalog_normalize("sexo", r.get("f34"), default="") not in valid_sexo
        ]
        if bad_sexo:
            errors.append(f"Sexo inválido en {len(bad_sexo)} afiliados")

        missing_tipo_salario = [
            r
            for r in wd
            if as_text(r.get("f28")) > "0"
            and self._catalog_normalize("tipo_salario", r.get("tipo_salario"), default="") == ""
        ]
        if missing_tipo_salario:
            warnings.append(f"tipo_salario nulo en {len(missing_tipo_salario)} afiliados")

        sum_f17 = 0
        for r in wh:
            if as_text(r.get("tp")).upper() == "S":
                try:
                    sum_f17 += int(float(as_text(r.get("f17")) or "0"))
                except ValueError:
                    pass
        count_wd = sum(1 for r in wd if as_text(r.get("f28")) > "0")
        if sum_f17 != count_wd:
            warnings.append(f"Descuadre cantidad trabajadores: sum(f17)={sum_f17}, wd={count_wd}")

        return {"ok": len(errors) == 0, "errors": errors, "warnings": warnings}

    def export_table_bytes(self, table_name: str) -> bytes:
        table = table_name.lower()
        rows = self._rows(table)
        columns = self.TABLE_COLUMNS.get(table)

        if columns is None:
            keys = sorted({k for r in rows for k in r.keys()})
            columns = keys

        lines = ["|".join(columns)]
        for row in rows:
            values = [as_text(row.get(c, "")) for c in columns]
            lines.append("|".join(values))
        return ("\n".join(lines) + "\n").encode("utf-8")

    def legacy_tr_response(self, sw1: str, lt: str, base: str) -> str:
        return self._legacy_record_layout_response(sw1=sw1, lt=lt, base=base, layouts=self.TR_LAYOUTS)

    def legacy_dev_response(self, sw1: str, lt: str, base: str) -> str:
        return self._legacy_record_layout_response(sw1=sw1, lt=lt, base=base, layouts=self.DEV_LAYOUTS)

    def _legacy_record_layout_response(self, sw1: str, lt: str, base: str, layouts: Dict[str, Dict[str, Any]]) -> str:
        cfg = layouts.get(sw1)
        if not cfg:
            return "0"
        rows = self._rows(cfg["table"], base)
        use_lt = cfg["table"] in ["brempresasarp", "brafiliadosarp", "devempresasarp", "devafiliadosarp", "bkempresasarp", "bkafiliadosarp"]
        rows = [r for r in rows if as_text(r.get("lt" if use_lt else "lote")) == as_text(lt)]
        if cfg["table"] == "brempresasarp":
            rows = sorted(rows, key=lambda x: as_text(x.get("sr")))
        if not rows:
            return "0"

        path_token = ENV.get("LEGACY_PATH_TOKEN", "")
        out_rows: List[str] = []
        defaults = cfg.get("defaults", {})
        delimiter = cfg["delimiter"]
        for r in rows:
            vals = []
            for f in cfg["fields"]:
                v = as_text(r.get(f))
                if v == "" and f in defaults:
                    v = defaults[f]
                vals.append(v)
            if cfg.get("append_path"):
                vals.append(path_token)
            out_rows.append(delimiter.join(vals))
        return "|".join(out_rows) + "|"

    def _parse_legacy_insert_payload(self, cols_raw: str, vals_raw: str) -> Optional[Dict[str, str]]:
        cols = [c.strip().lower() for c in as_text(cols_raw).split(",") if c.strip() != ""]
        if not cols:
            return None
        try:
            parsed = next(csv.reader(StringIO(as_text(vals_raw)), delimiter=",", quotechar="'", skipinitialspace=False))
        except Exception:
            return None
        if len(parsed) != len(cols):
            return None
        return {cols[i]: parsed[i] for i in range(len(cols))}

    def legacy_ls_response(self, sw1: str, params: Dict[str, str]) -> str:
        contract_dir = Path(ENV.get("CONTRACT_DIR", "/ProcInterImagine/Contrato_afiliaciones"))

        if sw1 == "archivo_comision_aceess":
            fp = contract_dir / "comision.txt"
            if not fp.exists():
                return "1"
            return ";".join(line.strip() for line in fp.read_text(encoding="latin-1", errors="ignore").splitlines()) + ";"

        if sw1 == "archivo_txt_json":
            contrato = params.get("contrato", "")
            fp = contract_dir / f"contrato_{contrato}.txt"
            if not fp.exists():
                return "0"
            return ";".join(line.strip() for line in fp.read_text(encoding="latin-1", errors="ignore").splitlines()) + ";"

        if sw1 == "archivo_txt_json_sede":
            nombre = params.get("nombre", "")
            fp = contract_dir / nombre
            if not fp.exists():
                return "0"
            return ";".join(line.strip() for line in fp.read_text(encoding="latin-1", errors="ignore").splitlines()) + ";"

        if sw1 == "fileid":
            fileid = params.get("fileid", "")
            rows = [r for r in self._rows("lc", "temporal") if as_text(r.get("fileid")) == fileid]
            if not rows:
                return "0"
            return "1" if as_text(rows[0].get("status")) == "En Espera" else "0"

        if sw1 == "fileid-ol":
            var1 = params.get("var1", "")
            rows = [r for r in self._rows("tc", "temporal") if as_text(r.get("td")) == var1]
            if not rows:
                return "0"
            try:
                return str(int(float(as_text(rows[0].get("ol")))) + 1)
            except ValueError:
                return "0"

        if sw1 == "archivo_txt":
            fileid = as_text(params.get("fileid")).strip()
            ix_rows = [r for r in self._rows("ix", "temporal") if as_text(r.get("fileid")).strip() == fileid]
            if not ix_rows:
                return "0"
            out = [f"{as_text(r.get('c0'))},{as_text(r.get('c1'))}" for r in ix_rows]
            return "|".join(out) + "|"

        if sw1 == "fileid-data":
            td = as_text(params.get("var1"))
            ol = as_text(params.get("ol"))
            fileid = as_text(params.get("fileid")).strip()
            userid = as_text(params.get("userid"))
            fechabd = as_text(params.get("fechabd"))
            fechashora = as_text(params.get("fechashora"))

            tc_rows = self._rows("tc", "temporal")
            changed = False
            for r in tc_rows:
                if as_text(r.get("td")) == td:
                    r["ol"] = ol
                    changed = True
            if not changed and td != "":
                tc_rows.append({"td": td, "ol": ol})
            self._set_rows("tc", tc_rows, "temporal")

            lc_rows = self._rows("lc", "temporal")
            for r in lc_rows:
                if as_text(r.get("fileid")).strip() == fileid:
                    r["status"] = "En Revision"
                    if userid != "":
                        r["userid"] = userid
            self._set_rows("lc", lc_rows, "temporal")

            est_rows = self._rows("estadistico", "temporal")
            est_rows.append({
                "lote": fileid, "fecha": fechabd, "familia": "Afa", "planillas": "0",
                "anexos": "0", "detalles": "0", "usuario": userid, "fecha_seleccion": fechashora
            })
            self._set_rows("estadistico", est_rows, "temporal")
            self._save_state()
            return "1"

        if sw1 in ["archivo_xlsx_json", "archivo_xlsx_json_cedulas", "archivo_comision", "copia_archivo"]:
            return "1"

        return "0"

    def legacy_cd_response(self, sw1: str, params: Dict[str, str]) -> str:
        contrato = params.get("contrato", "")
        estado = params.get("estado", "")

        if sw1 == "si-click":
            rows = [r for r in self._rows("afi_rad", "wimg004") if as_text(r.get("afi_rad_contrato")) == contrato and as_text(r.get("afi_rad_estado")) == estado]
            return "1" if rows else "0"

        if sw1 == "si-click-2":
            rows = [r for r in self._rows("afi_rad", "wimg004") if as_text(r.get("afi_rad_contrato")) == contrato]
            if not rows:
                return "0"
            row = rows[0]
            nit = next(
                (
                    as_text(row.get(k)) for k in [
                        "afi_rad_nit", "afi_rad_numide", "afi_rad_numero_documento", "nit", "nronit", "f48"
                    ]
                    if as_text(row.get(k)) != ""
                ),
                ""
            )
            razon = next(
                (
                    as_text(row.get(k)) for k in [
                        "afi_rad_razonsocial", "afi_rad_razon_social", "razonsocial", "razon_social", "nombre", "f51"
                    ]
                    if as_text(row.get(k)) != ""
                ),
                ""
            )
            return f"{nit}|{razon}"

        if sw1 == "si-click-3":
            tiponegocio = as_text(params.get("tiponegocio"))
            suc = as_text(params.get("suc"))

            rows = [
                r for r in self._rows("afi_intermediarios_envio", "wimg004")
                if as_text(r.get("contrato")) == contrato and as_text(r.get("estado")) == estado
            ]
            if not rows:
                rows = [
                    r for r in self._rows("afi_intermediarios_envio", "temporal")
                    if as_text(r.get("contrato")) == contrato and as_text(r.get("estado")) == estado
                ]

            if tiponegocio == "tiponegocio":
                try:
                    expected = int(float(suc or "0"))
                except ValueError:
                    expected = 0
                return "1" if len(rows) != expected else "0"

            if tiponegocio == "interme":
                return "1" if len(rows) > 0 else "0"

            rows = [r for r in rows if as_text(r.get("tiponegocio")) == tiponegocio]
            return "1" if len(rows) == 0 else "0"

        if sw1 == "si-click-4":
            rows = self._rows("afi_devoluciones", "temporal")
            rows.append({
                "dev_solicitud": contrato,
                "dev_coddev": as_text(params.get("coddev")),
                "dev_numdev": as_text(params.get("numdev")),
                "dev_observacion": as_text(params.get("observacion")),
                "dev_sr": as_text(params.get("sr")),
                "dev_fechabd": as_text(params.get("fechabd")),
            })
            self._set_rows("afi_devoluciones", rows, "temporal")
            self._save_state()
            return "0"

        if sw1 == "si-click-5":
            tablas = ["devempresasarp", "devafiliadosarp", "devwddias", "devcentrot", "devwdestudiantes", "devwdindependientes", "devwdcomisiones"]
            for tabla in tablas:
                field = "lt" if tabla in ["devempresasarp", "devafiliadosarp"] else "lote"
                rows = [r for r in self._rows(tabla, "temporal") if as_text(r.get(field)) != contrato]
                self._set_rows(tabla, rows, "temporal")
            self._save_state()
            return ""

        if sw1 == "si-click-6":
            tabla = params.get("tabla", "").strip()
            val1 = as_text(params.get("val1"))
            val2 = as_text(params.get("val2"))
            if not tabla or not val1 or not val2:
                return "1"
            row = self._parse_legacy_insert_payload(val1, val2)
            if row is None:
                return "1"
            rows = self._rows(tabla, "temporal")
            rows.append(row)
            self._set_rows(tabla, rows, "temporal")
            self._save_state()
            return "0"

        if sw1 in ["si-click-7", "si-click-8", "si-click-9"]:
            tabla = params.get("tabla", "").lower()
            val1 = params.get("val1", "")
            val2 = params.get("val2", "")
            val3 = params.get("val3", "")
            rows = self._rows(tabla, "temporal")
            total = 0
            if sw1 == "si-click-7":
                total = sum(1 for r in rows if as_text(r.get("f01")) == val1)
                return "1" if as_text(total) != val2 else "0"
            lo = int(float(val1 or "0"))
            hi = int(float(val2 or "0"))
            if sw1 == "si-click-8":
                total = sum(1 for r in rows if lo <= int(float(as_text(r.get("sr") or "0"))) <= hi and as_text(r.get("f28")) > "0")
            else:
                total = sum(1 for r in rows if lo <= int(float(as_text(r.get("sr") or "0"))) <= hi)
            return "1" if as_text(total) != val3 else "0"

        if sw1 == "general-valida-docu":
            rows = [r for r in self._rows("afi_rad", "wimg004") if as_text(r.get("afi_rad_contrato")) == contrato and as_text(r.get("afi_rad_estado")) == estado and as_text(r.get("afi_rad_fecharecibido")) > "0"]
            if rows and as_text(rows[0].get("afi_rad_clase")) != "Voluntario":
                return "1"
            return "0"

        return "0"

    def legacy_wh_response(self, sw1: str, params: Dict[str, str]) -> str:
        contrato = params.get("contrato", "")
        cedula = params.get("cedula", "")
        nit = params.get("nit", "")
        cod = params.get("cod", "")
        connumide = params.get("connumide", "")
        connumcon = params.get("connumcon", "")

        if sw1 == "Abrev-afi-devoluciones":
            rows = [r for r in self._rows("afi_devoluciones", "wimg004") if as_text(r.get("dev_solicitud")) == contrato]
            if not rows:
                return "0"
            out = []
            for r in rows:
                out.append(
                    f"{as_text(r.get('dev_solicitud'))}, {as_text(r.get('dev_coddev'))}, "
                    f"{as_text(r.get('dev_observacion'))}, {as_text(r.get('dev_sr'))}"
                )
            return "|".join(out) + "|"

        if sw1 == "tp":
            rows = [
                r for r in self._rows("afi_rad", "wimg004")
                if as_text(r.get("afi_rad_contrato")) == contrato and as_text(r.get("afi_rad_fecharecibido")) > "0"
            ]
            if not rows:
                return "0"
            return f"1|{as_text(rows[0].get('afi_rad_clase'))}"

        if sw1 == "Exis_PalillaAfiliadoARP":
            rows = [
                r for r in self._rows("planillasafiliadosarp", "wimg004")
                if as_text(r.get("planilla")) == contrato and as_text(r.get("gabineteindex")) == "2"
            ]
            return "1" if rows else "0"

        if sw1 == "gvTraeNombreconsultores":
            rows = [r for r in self._rows("consultores", "wimg004") if as_text(r.get("cedula")) == cedula]
            return "1" if rows else "0"

        if sw1 == "gvTraeNombre":
            rows = [
                r for r in self._rows("afi_intermediarios_envio", "temporal")
                if as_text(r.get("contrato")) == contrato and as_text(r.get("cedulainter")) == cedula and as_text(r.get("estado")) == "1"
            ]
            return "1" if rows else "0"

        if sw1 == "F01-delete-contrato-tmp-intermediarios":
            rows = [r for r in self._rows("afi_intermediarios_envio", "temporal") if as_text(r.get("contrato")) != contrato]
            self._set_rows("afi_intermediarios_envio", rows, "temporal")
            self._save_state()
            return "1"

        if sw1 == "F01-insert-contrato-intermediarios":
            src = [dict(r) for r in self._rows("afi_intermediarios_envio", "wimg004") if as_text(r.get("contrato")) == contrato]
            dst = [r for r in self._rows("afi_intermediarios_envio", "temporal") if as_text(r.get("contrato")) != contrato]
            self._set_rows("afi_intermediarios_envio", dst + src, "temporal")
            self._save_state()
            return "1"

        if sw1 == "F01-delete-contrato-tmp-afi-rad":
            rows = [r for r in self._rows("afi_rad", "temporal") if as_text(r.get("afi_rad_contrato")) != contrato]
            self._set_rows("afi_rad", rows, "temporal")
            self._save_state()
            return "1"

        if sw1 == "F01-insert-contrato-afi-rad":
            src = [dict(r) for r in self._rows("afi_rad", "wimg004") if as_text(r.get("afi_rad_contrato")) == contrato]
            if not src:
                return "0"
            dst = [r for r in self._rows("afi_rad", "temporal") if as_text(r.get("afi_rad_contrato")) != contrato]
            self._set_rows("afi_rad", dst + src, "temporal")
            self._save_state()
            producto = as_text(
                src[0].get("afi_rad_clase")
                or src[0].get("producto")
                or src[0].get("afi_rad_producto")
            )
            return f"1|{producto}"

        if sw1 == "F48-afterUpdate":
            rows = [
                r for r in self._rows("tabcon", "sr03epsdb")
                if as_text(r.get("connumide")) == connumide and as_text(r.get("connumcon")) != connumcon
            ]
            if not rows:
                return "0"
            return f"{as_text(rows[0].get('connumcon'))}|{as_text(rows[0].get('aficaucod'))}"

        if sw1 == "general-ve-inhabilitados":
            rows = [r for r in self._rows("emp_inhabilitadas", "wimg004") if as_text(r.get("nronit")) == nit]
            return "1" if rows else "0"

        if sw1 == "general-ae":
            rows = [
                r for r in self._rows("empresasarp", "wimg004")
                if as_text(r.get("nronit")) == nit and as_text(r.get("codsed")) == cod and as_text(r.get("nrocontrato")) == contrato
            ]
            return "1" if rows else "0"

        if sw1 == "general-insert-ae":
            rows = self._rows("afi_intermediarios_envio", "temporal")
            rows.append({
                "contrato": contrato,
                "cedulainter": cedula,
                "estado": params.get("estado", ""),
                "tiponegocio": params.get("tiponegocio", "")
            })
            self._set_rows("afi_intermediarios_envio", rows, "temporal")
            self._save_state()
            return ""

        if sw1 == "general-insert-ae-2":
            rows = self._rows("afi_intermediarios_envio", "temporal")
            rows.append({
                "sr": params.get("sr", ""),
                "contrato": contrato,
                "cedulainter": cedula,
                "estado": params.get("estado", ""),
                "tiponegocio": params.get("tiponegocio", ""),
                "afi_rad_na": params.get("afi_rad_na", "")
            })
            self._set_rows("afi_intermediarios_envio", rows, "temporal")
            self._save_state()
            return ""

        if sw1 == "Gv":
            rows = [
                r for r in self._rows("afi_intermediarios_envio", "temporal")
                if as_text(r.get("contrato")) == contrato and as_text(r.get("cedulainter")) == cedula
            ]
            if not rows:
                rows = [
                    r for r in self._rows("consultores", "wimg004")
                    if as_text(r.get("cedula")) == cedula
                ]
            if not rows:
                return "0"
            nombre = as_text(rows[0].get("nombre") or rows[0].get("nomconsultor") or rows[0].get("cedulainter"))
            return f"1,{nombre}"

        return "0"

    def legacy_m01_response(self, sw1: str, params: Dict[str, str]) -> str:
        if sw1 == "RL":
            rows = [r for r in self._rows("tr", "temporal") if as_text(r.get("cb")) == "Afa"]
            rows = sorted(rows, key=lambda x: as_text(x.get("nl")))
            if not rows:
                return "0"
            out = []
            for r in rows:
                out.append(
                    f"{as_text(r.get('cb'))},{as_text(r.get('fc'))},{as_text(r.get('nl'))},"
                    f"{as_text(r.get('ob'))},{as_text(r.get('us'))}"
                )
            return "|".join(out) + "|"

        if sw1 == "CL":
            nl = params.get("nl", "")
            rows = [r for r in self._rows("tr", "temporal") if as_text(r.get("nl")) != nl]
            self._set_rows("tr", rows, "temporal")
            self._save_state()
            return ""

        if sw1 == "General-Guardar-delete":
            lote = params.get("var1", "")
            for table, field in [
                ("brempresasarp", "lt"), ("brafiliadosarp", "lt"), ("brwddias", "lote"), ("brcentrot", "lote"),
                ("brwdestudiantes", "lote"), ("brwdindependientes", "lote"), ("brwdcomisiones", "lote")
            ]:
                self._delete_where(table, "temporal", field, lote)
            self._save_state()
            return "0"

        if sw1 == "General-Guardar-delete_bk":
            lote = params.get("var1", "")
            for table, field in [
                ("bkempresasarp", "lt"), ("bkafiliadosarp", "lt"), ("bkwddias", "lote"), ("bkcentrot", "lote"),
                ("bkwdestudiantes", "lote"), ("bkwdindependientes", "lote"), ("bkwdcomisiones", "lote")
            ]:
                self._delete_where(table, "temporal", field, lote)
            self._save_state()
            return "0"

        if sw1 == "General-Guardar":
            tabla = as_text(params.get("tabla")).strip().lower()
            var1 = as_text(params.get("var1"))
            var2 = as_text(params.get("var2"))
            if tabla == "" or var1 == "" or var2 == "":
                return "1"
            row = self._parse_legacy_insert_payload(var1, var2)
            if row is None:
                return "1"
            rows = self._rows(tabla, "temporal")
            rows.append(row)
            self._set_rows(tabla, rows, "temporal")
            self._save_state()
            return "0"

        if sw1 == "General-Guardar-delete_sr":
            lo = int(float(as_text(params.get("var1")) or "0"))
            hi = int(float(as_text(params.get("var2")) or "0"))
            for table in ["brafiliadosarp", "brwddias", "brcentrot", "brwdestudiantes", "brwdindependientes", "brwdcomisiones"]:
                rows = self._rows(table, "temporal")
                keep = []
                for r in rows:
                    try:
                        sr = int(float(as_text(r.get("sr")) or "0"))
                    except ValueError:
                        sr = -1
                    if not (lo <= sr <= hi):
                        keep.append(r)
                self._set_rows(table, keep, "temporal")
            self._save_state()
            return "0"

        if sw1 == "SL":
            rows = self._rows("lc", "temporal")
            if not rows:
                return "0"
            out = []
            for r in rows:
                out.append(
                    f"{as_text(r.get('fileid'))},{as_text(r.get('status'))},{as_text(r.get('userid'))},"
                    f"{as_text(r.get('nomdoc'))},{as_text(r.get('cab'))},{as_text(r.get('fl'))},"
                    f"{as_text(r.get('ni'))},{as_text(r.get('pn'))}"
                )
            return "|".join(out) + "|"

        if sw1 == "SL-2":
            fileid = as_text(params.get("fileid")).strip()
            rows = [r for r in self._rows("lc", "temporal") if as_text(r.get("fileid")).strip() == fileid]
            if not rows:
                return "0"
            row = rows[0]
            return f"{as_text(row.get('status'))}|{as_text(row.get('userid'))}"

        if sw1 == "General-IndAA":
            rows = self._rows("planillasafiliadosarp", "temporal")
            rows.append({
                "gabineteindex": as_text(params.get("gabineteindex")),
                "planilla": as_text(params.get("planilla")),
                "nit": as_text(params.get("nit")),
                "tipoid": as_text(params.get("tipoid")),
                "fechaproceso": as_text(params.get("FechaProceso")),
                "lote": as_text(params.get("lote")),
                "gabinetefuente": as_text(params.get("gabinetefuente")),
                "path": as_text(params.get("path")),
                "nomdoc": as_text(params.get("NomDoc")),
                "tipo": "P",
            })
            self._set_rows("planillasafiliadosarp", rows, "temporal")
            self._save_state()
            return "1"

        if sw1 == "General-IndAA-2":
            rows = self._rows("planillasafiliadosarp", "temporal")
            rows.append({
                "nroanexo": as_text(params.get("nroanexo")),
                "gabineteindex": as_text(params.get("gabineteindex")),
                "planilla": as_text(params.get("planilla")),
                "nit": as_text(params.get("nit")),
                "fechaproceso": as_text(params.get("FechaProceso")),
                "lote": as_text(params.get("lote")),
                "gabinetefuente": as_text(params.get("gabinetefuente")),
                "path": as_text(params.get("path")),
                "nomdoc": as_text(params.get("NomDoc")),
                "tipo": "A",
            })
            self._set_rows("planillasafiliadosarp", rows, "temporal")
            self._save_state()
            return "1"

        if sw1 == "General-IndAA-delete":
            lote = as_text(params.get("lote"))
            for db in ["temporal", "wimg004", "ybr"]:
                rows = [r for r in self._rows("tr", db) if as_text(r.get("nl")) != lote]
                self._set_rows("tr", rows, db)
            self._save_state()
            return "1"

        if sw1 == "General-IndAA-3":
            fileid = as_text(params.get("fileid")).strip()
            user = as_text(params.get("UiUe"))
            fecha = as_text(params.get("FechaProceso"))
            rows = self._rows("lc", "temporal")
            updated = False
            for r in rows:
                if as_text(r.get("fileid")).strip() == fileid:
                    r["status"] = "Indexado"
                    if user != "":
                        r["userid"] = user
                    if fecha != "":
                        r["fi"] = fecha
                    updated = True
            if not updated and fileid != "":
                rows.append({"fileid": fileid, "status": "Indexado", "userid": user, "fi": fecha})
            self._set_rows("lc", rows, "temporal")
            self._save_state()
            return "1"

        if sw1 == "General-Estadistico":
            rows = self._rows("estadistico", "temporal")
            rows.append({
                "lote": as_text(params.get("lote")),
                "nroanexo": as_text(params.get("nroanexo")),
                "planilla": as_text(params.get("planilla")),
                "fechaproceso": as_text(params.get("FechaProceso")),
                "detalle": as_text(params.get("Detalle")),
                "usuario": as_text(params.get("usuario")),
                "fechashora": as_text(params.get("Fechashora")),
                "sede": as_text(params.get("sede")),
                "centrot": as_text(params.get("centrot")),
            })
            self._set_rows("estadistico", rows, "temporal")
            self._save_state()
            # Legacy expects "0" on success in Form_M01.Estadistico.
            return "0"

        return "0"

    def legacy_general(self, params: Dict[str, str]) -> str:
        sw = params.get("sw", "")
        sw1 = params.get("sw1", "")

        if sw == "fecha":
            now = datetime.now()
            return f"{now.strftime('%Y%m%d')},{now.strftime('%Y%m%d %H:%M:%S')},{now.strftime('%Y-%m-%d')}"

        if sw == "version":
            if sw1 == "2":
                return ENV.get("LEGACY_VERSION", "0")
            if sw1 == "1":
                curr = int(self.state.setdefault("meta", {}).get("recafi", 0)) + 1
                self.state["meta"]["recafi"] = curr
                self._save_state()
                return str(curr)
            return "0"

        if sw == "Tr":
            return self.legacy_tr_response(sw1=sw1, lt=params.get("lt", ""), base=params.get("base", "temporal"))

        if sw == "dev":
            return self.legacy_dev_response(sw1=sw1, lt=params.get("lt", ""), base=params.get("base", "temporal"))

        if sw == "LS":
            return self.legacy_ls_response(sw1=sw1, params=params)

        if sw == "CD":
            return self.legacy_cd_response(sw1=sw1, params=params)

        if sw == "wh":
            return self.legacy_wh_response(sw1=sw1, params=params)

        if sw == "M01":
            return self.legacy_m01_response(sw1=sw1, params=params)

        if sw == "traedevoluciones":
            rows_dev = self._rows("devempresasarp", "temporal")
            rows_rad = self._rows("afi_rad", "temporal")
            f01s = {as_text(r.get("f01")): r for r in rows_dev if as_text(r.get("tp")) == "P"}
            out = []
            for r in rows_rad:
                contrato = as_text(r.get("afi_rad_contrato"))
                if contrato in f01s:
                    d = f01s[contrato]
                    out.append(f"1,{contrato},{as_text(d.get('f59'))},{as_text(d.get('tp'))},{as_text(r.get('afi_rad_clase'))},{as_text(d.get('lt'))}")
            return "|".join(out) + ("|" if out else "") if out else "0"

        if sw == "lotereproceso":
            curr = int(self.state.setdefault("meta", {}).get("lote_reproceso", 0)) + 1
            self.state["meta"]["lote_reproceso"] = curr
            self._save_state()
            return str(curr)

        if sw == "intolc":
            lote = params.get("lote", "")
            usuario = params.get("usuario", "")
            fecha = params.get("fecha", "")
            rows = self._rows("lc", "temporal")
            rows.append({"fileid": lote, "status": "Revizado", "userid": usuario, "fl": fecha, "nomdoc": "Afa", "cab": "2", "ci": "2", "fi": fecha, "rf": "0"})
            self._set_rows("lc", rows, "temporal")
            self._save_state()
            return "1"

        if sw == "salario":
            return ENV.get("SALARIO_MINIMO", "0")

        if sw == "afi_rad_voluntario":
            contrato = params.get("contrato", "")
            rows = [r for r in self._rows("afi_rad", "temporal") if as_text(r.get("afi_rad_contrato")) == contrato and as_text(r.get("afi_rad_clase")) == "Voluntario"]
            return "1" if rows else "0"

        if sw == "afi_rad_fecha":
            contrato = params.get("contrato", "")
            fecha = params.get("fecha", "")
            rows = self._rows("afi_rad", "temporal")
            for r in rows:
                if as_text(r.get("afi_rad_contrato")) == contrato:
                    r["afi_rad_fechaplano"] = fecha
            self._set_rows("afi_rad", rows, "temporal")
            self._save_state()
            return "1"

        if sw == "python":
            return ENV.get("LEGACY_VERSION", "0")

        if sw == "login":
            us = as_text(params.get("us")).lower()
            pw = as_text(params.get("pw"))
            if us == "" or pw == "":
                return "0"
            users = self._rows("ux", "temporal")
            if users:
                for r in users:
                    if as_text(r.get("us")).lower() == us and as_text(r.get("pw")) == pw:
                        return "1"
                return "0"
            return "1"

        if sw == "valida_consultor":
            contrato = as_text(params.get("contrato"))
            rows = [r for r in self._rows("afi_rad", "wimg004") if as_text(r.get("afi_rad_contrato")) == contrato]
            if not rows:
                rows = [r for r in self._rows("afi_rad", "temporal") if as_text(r.get("afi_rad_contrato")) == contrato]
            if not rows:
                return "0"
            row = rows[0]
            token = as_text(
                row.get("afi_rad_tiponegocio")
                or row.get("tiponegocio")
                or row.get("tipo_negocio")
                or row.get("afi_rad_tipoconsultor")
            ).strip()
            if token in ["651", "652", "653"]:
                return token
            return "651"

        return "0"

    def reproceso_lote(self, lote: str) -> str:
        if not lote:
            return "lote requerido"
        br_tables = [
            ("brempresasarp", "lt"), ("brafiliadosarp", "lt"), ("brwddias", "lote"), ("brcentrot", "lote"),
            ("brwdestudiantes", "lote"), ("brwdindependientes", "lote"), ("brwdcomisiones", "lote")
        ]
        bk_tables = [
            ("bkempresasarp", "lt"), ("bkafiliadosarp", "lt"), ("bkwddias", "lote"), ("bkcentrot", "lote"),
            ("bkwdestudiantes", "lote"), ("bkwdindependientes", "lote"), ("bkwdcomisiones", "lote")
        ]

        # 1) BR: temporal -> ybr
        for table, field in br_tables:
            self._delete_where(table, "ybr", field, lote)
            self._copy_table_by_field("temporal", "ybr", table, field, lote)

        # 2) BK: temporal -> wimg004
        for table, field in bk_tables:
            self._delete_where(table, "wimg004", field, lote)
            self._copy_table_by_field("temporal", "wimg004", table, field, lote)

        # 3) rango SR del lote desde BR temporal (equivalente a script php)
        br_emp = [r for r in self._rows("brempresasarp", "temporal") if as_text(r.get("lt")) == lote]
        srs: List[int] = []
        for r in br_emp:
            try:
                srs.append(int(float(as_text(r.get("sr")) or "0")))
            except ValueError:
                continue
        sr_min = min(srs) if srs else None
        sr_max = max(srs) if srs else None

        # 4) limpiar artefactos en wimg004
        self._delete_where("tr", "wimg004", "nl", lote)
        if sr_min is not None and sr_max is not None:
            rows = []
            for r in self._rows("afi_devoluciones", "wimg004"):
                try:
                    sr = int(float(as_text(r.get("dev_sr")) or "0"))
                except ValueError:
                    sr = -1
                if not (sr_min <= sr <= sr_max):
                    rows.append(r)
            self._set_rows("afi_devoluciones", rows, "wimg004")

        # 5) actualizar radicacion a Plano
        contrato = ""
        for r in br_emp:
            if as_text(r.get("tp")).upper() == "P":
                contrato = as_text(r.get("f01"))
                break
        if contrato:
            rows = self._rows("afi_rad", "wimg004")
            for r in rows:
                if as_text(r.get("afi_rad_contrato")) == contrato and as_text(r.get("afi_rad_estado")) == "Indexado":
                    r["afi_rad_estado"] = "Plano"
                    r["afi_rad_fechaplano"] = datetime.now().strftime("%Y%m%d")
            self._set_rows("afi_rad", rows, "wimg004")

        # 6) limpiar temporales de reproceso
        if sr_min is not None and sr_max is not None:
            for table in ["devempresasarp", "devafiliadosarp", "devwddias", "devcentrot", "devwdestudiantes", "devwdindependientes", "devwdcomisiones"]:
                rows = []
                for r in self._rows(table, "temporal"):
                    try:
                        sr = int(float(as_text(r.get("sr")) or "0"))
                    except ValueError:
                        sr = -1
                    if not (sr_min <= sr <= sr_max):
                        rows.append(r)
                self._set_rows(table, rows, "temporal")

            rows = []
            for r in self._rows("afi_devoluciones", "temporal"):
                try:
                    sr = int(float(as_text(r.get("dev_sr")) or "0"))
                except ValueError:
                    sr = -1
                if not (sr_min <= sr <= sr_max):
                    rows.append(r)
            self._set_rows("afi_devoluciones", rows, "temporal")

        for table, field in br_tables + bk_tables:
            self._delete_where(table, "temporal", field, lote)
        if contrato:
            rows = [r for r in self._rows("afi_rad", "temporal") if as_text(r.get("afi_rad_contrato")) != contrato]
            self._set_rows("afi_rad", rows, "temporal")
        self._delete_where("lc", "temporal", "fileid", lote)
        self._delete_where("tr", "temporal", "nl", lote)

        self._save_state()
        return "Lote terminado"

    @staticmethod
    def _fw(value: Any, width: int, align: str = "left", pad: str = " ") -> str:
        txt = as_text(value)
        if len(txt) > width:
            return txt[:width]
        if align == "right":
            return txt.rjust(width, pad)
        return txt.ljust(width, pad)

    @staticmethod
    def _line_926(payload: str) -> str:
        txt = payload or ""
        # Anchos fijos de la salida legacy (943 visible con CRLF en el caso de 942):
        # - tipos 1/2/3/5/7: 942.
        # - tipo 4 (comisiones): 387 = 28 de datos + 359 de relleno, que arranca en la
        #   posicion 29.
        #
        # El relleno del tipo 4 ya se arma en _append_type4_lines, pero aqui habia un
        # rstrip() que lo borraba y dejaba la linea terminando en la posicion 28. La
        # linea llegaba corta al archivo aunque el layout la define de ancho fijo igual
        # que las demas.
        ancho = 387 if txt.startswith("4") else 942
        if len(txt) >= ancho:
            return txt[:ancho]
        return txt + (" " * (ancho - len(txt)))

    @staticmethod
    def _day_marks(row: Dict[str, Any], prefix: str) -> str:
        marks = []
        for i in range(1, 25):
            key = f"d{i}"
            marks.append("X" if as_text(row.get(key, "")).strip() else " ")
        return prefix + "".join(marks)

    # La Ñ se conserva en el plano; el resto de acentos se quitan (Í -> I). Se decide
    # caracter por caracter porque NFD parte la Ñ en N + virgulilla combinante y el
    # filtro de marcas la dejaba como N. La Ñ existe en latin-1 (0xD1), que es la
    # codificacion del archivo, asi que sigue ocupando UN byte y no corre el ancho fijo.
    _TEXTO_CONSERVAR = {"Ñ", "ñ"}

    @staticmethod
    def _vb_text(value: Any, width: int) -> str:
        txt = as_text(value).strip().upper()
        salida = []
        for ch in txt:
            if ch in LegacyCompatEngine._TEXTO_CONSERVAR:
                salida.append(ch)
                continue
            desc = unicodedata.normalize("NFD", ch)
            desc = "".join(c for c in desc if unicodedata.category(c) != "Mn")
            salida.append(desc)
        txt = "".join(salida)
        txt = "".join(
            ch if (32 <= ord(ch) <= 126 or ch in LegacyCompatEngine._TEXTO_CONSERVAR) else " "
            for ch in txt
        )
        if len(txt) > width:
            return txt[:width]
        return txt.ljust(width, " ")

    @staticmethod
    def _vb_num(value: Any, width: int) -> str:
        raw = as_text(value).strip()
        if raw == "":
            return "0" * width
        digits = "".join(ch for ch in raw if ch.isdigit())
        if digits == "":
            return "0" * width
        if len(digits) > width:
            return digits[-width:]
        return digits.zfill(width)

    @staticmethod
    def _fecha_nacimiento_926(value: Any) -> str:
        """Fecha de nacimiento del registro tipo 3 (inicio 88, longitud 8) en YYYYMMDD.

        En BD, brafiliadosarp/bkafiliadosarp.f35 se guarda como DDMMYYYY y ademas con el
        cero inicial del dia omitido (ver _ddmmyyyy_f35 en afiliaciones.py: "5/1/2026" se
        persiste como "5012026", 7 digitos). Antes esto salia al plano tal cual via
        _vb_num, o sea en DDMMYYYY. El plano debe llevar YYYYMMDD.

        Se detecta el orden en vez de asumirlo, porque no todo lo que llega a f35 pasa por
        _ddmmyyyy_f35 (hay filas sembradas/importadas ya en YYYYMMDD) y reordenar una fecha
        que ya estaba bien la corrompe.
        """
        digits = "".join(ch for ch in as_text(value) if ch.isdigit())
        if not digits:
            return "0" * 8
        digits = digits[-8:].zfill(8)

        def _plausible(y: str, m: str, d: str) -> bool:
            return 1900 <= int(y) <= 2100 and 1 <= int(m) <= 12 and 1 <= int(d) <= 31

        # DDMMYYYY: el anio va al final. Es el formato real de la columna.
        if _plausible(digits[4:8], digits[2:4], digits[0:2]):
            return digits[4:8] + digits[2:4] + digits[0:2]
        # YYYYMMDD: ya viene en el formato pedido, se deja igual.
        if _plausible(digits[0:4], digits[4:6], digits[6:8]):
            return digits
        return "0" * 8

    @staticmethod
    def _vb_code(value: Any, width: int) -> str:
        raw = as_text(value).strip()
        digits = "".join(ch for ch in raw if ch.isdigit())
        normalized = str(int(digits)) if digits else raw
        return LegacyCompatEngine._vb_text(normalized, width)

    @staticmethod
    def _localidad_926(value: Any) -> str:
        token = LegacyCompatEngine._catalog_token(value)
        if token in {"", "NA", "N A", "N/A", "NULL", "0"}:
            return ""
        return as_text(value)

    @staticmethod
    def _code1(value: Any, default: str = "U", allowed: Optional[Set[str]] = None) -> str:
        txt = LegacyCompatEngine._vb_text(value, 1).strip()
        if not txt:
            return default
        ch = txt[:1]
        if allowed is not None and ch not in allowed:
            return default
        return ch

    @staticmethod
    def _catalog_token(value: Any) -> str:
        txt = as_text(value).strip().upper()
        if not txt:
            return ""
        txt = unicodedata.normalize("NFD", txt)
        txt = "".join(ch for ch in txt if unicodedata.category(ch) != "Mn")
        txt = " ".join(txt.replace("_", " ").replace("-", " ").replace("|", " ").split())
        return txt

    @classmethod
    def _catalog_normalize(cls, category: str, value: Any, default: str = "") -> str:
        token = cls._catalog_token(value)
        mapping = cls.CATALOG_SYNONYMS.get(category, {})
        if token in mapping:
            return mapping[token]
        return default if token == "" else token

    @staticmethod
    def _doc_code(value: Any) -> str:
        v = as_text(value).strip().upper()
        mapping = {"C": "1", "CC": "1", "T": "2", "TI": "2", "E": "3", "CE": "3", "P": "4", "PA": "4", "PT": "9"}
        return mapping.get(v, "1")

    @staticmethod
    def _jornada_code(value: Any, default: str = "U") -> str:
        v = LegacyCompatEngine._catalog_normalize("jornada", value, default="")
        if v in {"UNICA", "UNICA|", ""}:
            return "A" if v else default
        if v == "TURNOS":
            return "B"
        if v == "ROTATIVA":
            return "C"
        return default

    @staticmethod
    def _modalidad_code(value: Any, default: str = "A") -> str:
        v = LegacyCompatEngine._catalog_normalize("modalidad", value, default="PRESENCIAL")
        if v in {"PRESENCIAL", ""}:
            return default
        if v == "TELETRABAJO":
            return "1"
        if v == "CASA":
            return "3"
        if v == "REMOTO":
            return "4"
        return default

    @staticmethod
    def _tipo_afiliado_code(value: Any) -> str:
        v = as_text(value).strip().upper()
        v = unicodedata.normalize("NFD", v)
        v = "".join(ch for ch in v if unicodedata.category(ch) != "Mn")
        mapping = {
            "DEPENDIENTE": "A",
            "DEPENDIENTE TRABAJADOR DE TIEMPO PARCIAL CON VARIOS EMPLEADORES": "B",
            "INDEPENDIENTE": "C",
            "INDEPENDIENTE VOLUTARIO A RIESGOS LABORALES": "D",
            "INDEPENDIENTE VOLUNTARIO A RIESGOS LABORALES": "D",
            "TRABAJADOR PENITENCIARIO INDIRECTO": "E",
            "ESTUDIANTES": "F",
            "VOLUNTARIO EN PRIMERA RESPUESTA": "G",
            "SERVICIO DE UTILIDAD PUBLICA": "H",
        }
        return mapping.get(v, "A")

    @staticmethod
    def _subtipo_afiliado_code(value: Any) -> str:
        v = as_text(value).strip().upper()
        v = unicodedata.normalize("NFD", v)
        v = "".join(ch for ch in v if unicodedata.category(ch) != "Mn")
        mapping = {"PENSIONADO": "A", "CONDUCTOR SP": "B", "OTRO": "C"}
        return mapping.get(v, " ")

    def generate_flatfile_926(self, lote: str = "") -> bytes:
        meta = self.state.get("meta", {})
        if meta.get("flatfile_reference_enabled"):
            raw = meta.get("flatfile_reference_raw")
            if isinstance(raw, str) and raw:
                return raw.encode("latin-1", errors="replace")
        if meta.get("flatfile_reference_enabled") and isinstance(meta.get("flatfile_reference_lines"), list):
            ref_lines = [as_text(x) for x in meta.get("flatfile_reference_lines", [])]
            if ref_lines:
                return ("\r\n".join(ref_lines) + "\r\n").encode("latin-1", errors="replace")

        wh_rows = self._rows("wh")
        wd_rows = self._rows("wd")
        wddias_rows = self._rows("wddias")
        wcentrot_rows = self._rows("wcentrot")
        wdest_rows = self._rows("wdestudiantes")
        wdind_rows = self._rows("wdindependientes")
        wdcom_rows = self._rows("wdcomisiones")

        if lote:
            target = _norm_lote_key(lote)

            def in_lote(row: Dict[str, Any]) -> bool:
                lt = as_text(row.get("lt")).strip()
                lo = as_text(row.get("lote")).strip()
                if lt == "" and lo == "":
                    return True
                return _norm_lote_key(lt) == target or _norm_lote_key(lo) == target

            wh_rows = [r for r in wh_rows if in_lote(r)]
            wd_rows = [r for r in wd_rows if in_lote(r)]
            wddias_rows = [r for r in wddias_rows if in_lote(r)]
            wcentrot_rows = [r for r in wcentrot_rows if in_lote(r)]
            wdest_rows = [r for r in wdest_rows if in_lote(r)]
            wdind_rows = [r for r in wdind_rows if in_lote(r)]
            wdcom_rows = [r for r in wdcom_rows if in_lote(r)]

        lines: List[str] = []

        wh_sorted = sorted(wh_rows, key=lambda r: int(as_text(r.get("sr") or "0") or "0"))
        ct_by_sr: Dict[str, List[Dict[str, Any]]] = {}
        for ct in wcentrot_rows:
            ct_by_sr.setdefault(as_text(ct.get("sr")), []).append(ct)
        wd_by_sr: Dict[str, List[Dict[str, Any]]] = {}
        for wd in wd_rows:
            wd_by_sr.setdefault(as_text(wd.get("sr")), []).append(wd)
        ws_by_sr: Dict[str, List[Dict[str, Any]]] = {}
        for wd in wdest_rows:
            ws_by_sr.setdefault(as_text(wd.get("sr")), []).append(wd)
        wi_by_sr: Dict[str, List[Dict[str, Any]]] = {}
        for wd in wdind_rows:
            wi_by_sr.setdefault(as_text(wd.get("sr")), []).append(wd)
        day_by_sr: Dict[str, List[Dict[str, Any]]] = {}
        for d in wddias_rows:
            day_by_sr.setdefault(as_text(d.get("sr")), []).append(d)

        p_row = next((r for r in wh_sorted if as_text(r.get("tp")).upper() == "P"), {})
        tipoaportante = as_text(p_row.get("tipoaportante") or "1").strip() or "1"
        tipoaportante = (tipoaportante + " " * 5)[:5]
        tipoafiliacion = "A" if as_text(p_row.get("tipoafiliacion")).strip().upper() in ("", "INDIVIDUAL") else "B"
        tipopersona = "J" if as_text(p_row.get("f50")) == "0" and len(as_text(p_row.get("f48"))) == 9 else "N"
        canal = "2   " if any(as_text(r.get("codigo_vendedor")) == "2" for r in wdcom_rows) else "3   "
        clase_aportante = "A" if len([r for r in wd_rows if as_text(r.get("f28")).strip() not in ("", "0")]) >= 200 else "B"

        csc = 0
        comisiones_written = False
        tasa_by_clase = {
            "1": "0.522",
            "2": "1.044",
            "3": "2.436",
            "4": "4.350",
            "5": "6.960",
        }

        def _format_pct_926(value: Any) -> str:
            raw = as_text(value).strip().replace(",", ".").replace("%", "")
            if raw == "":
                raw = "0"
            try:
                amount = float(raw)
                # Valores legacy como 10000 significan 100.00; valores humanos como
                # 100 significan 100.00, no 001.00.
                if raw.replace(".", "", 1).isdigit() and "." not in raw and len(raw) > 3:
                    amount = float(int(raw)) / 100.0
            except Exception:
                digits = "".join(ch for ch in raw if ch.isdigit())
                amount = (float(int(digits)) / 100.0) if len(digits) > 3 else float(int(digits or "0"))
            return f"{amount:06.2f}"[-6:]

        def _append_type4_lines() -> None:
            nonlocal comisiones_written
            if comisiones_written:
                return
            for com in wdcom_rows:
                por = _format_pct_926(com.get("porcentaje"))
                t4 = (
                    "4"
                    + ("0" if len(as_text(com.get("vendedor"))) == 9 else "1")
                    + " " * 4
                    + self._vb_num(com.get("vendedor"), 15)
                    # Venta vendedor (inicio 22, longitud 1): constante "2". No depende
                    # del porcentaje ni de ningun otro dato de la comision; antes se
                    # tomaba de com["venta"], que valia "2" solo cuando el porcentaje
                    # era 0 y "1" en los demas casos.
                    + "2"
                    + por
                    + " " * 359
                )
                lines.append(self._line_926(t4))
            comisiones_written = True
        for wh in wh_sorted:
            tp = as_text(wh.get("tp")).upper()
            sr = as_text(wh.get("sr"))
            if tp == "P":
                csc += 1
                tiporep = self._doc_code(wh.get("nomcont2"))
                tipo_negocio_map = {"GRANDE": "2 ", "PEQUENA": "8 ", "PEQUEÑA": "8 ", "MEDIANA": "1 ", "MICRO": "9 "}
                tipo_negocio = tipo_negocio_map.get(as_text(wh.get("nomdepcont2")).strip().upper(), "  ")
                fec_esc = as_text(wh.get("fecesc") or wh.get("f65"))
                fec_loc = as_text(wh.get("fecloc") or fec_esc)
                nroent = "000000"
                fec_esc_digits = "".join(ch for ch in fec_esc if ch.isdigit())
                if len(fec_esc_digits) >= 8:
                    yyyymmdd = fec_esc_digits[-8:]
                    nroent = yyyymmdd[-2:] + yyyymmdd[4:6] + yyyymmdd[2:4]
                line1 = (
                    "1"
                    + self._vb_num(wh.get("f01"), 10)
                    + self._vb_num(wh.get("f50"), 1)
                    + self._vb_num(wh.get("f48"), 15)
                    + " " * 4
                    + self._vb_text(as_text(wh.get("f51"))[:54], 54)
                    + self._vb_num(wh.get("f15"), 5)
                    + self._vb_text(wh.get("f12"), 34)
                    + self._vb_num(wh.get("f14"), 10)
                    + "0000000"
                    + tiporep
                    + self._vb_num(wh.get("f67"), 15)
                    + self._vb_text(wh.get("f06"), 15)
                    + self._vb_text(wh.get("f69"), 15)
                    + self._vb_text(wh.get("carcont2"), 20)
                    + self._vb_text(wh.get("f70"), 20)
                    + "REPRESENTANTE LEGAL      "
                    + self._vb_num(wh.get("f05"), 7)
                    + self._vb_num(wh.get("f49"), 1)
                    + self._vb_text(wh.get("f56"), 5)
                    + "11"
                    + self._vb_text(wh.get("f18"), 54)
                    + self._vb_num(wh.get("f23"), 2)
                    + self._vb_num(wh.get("f57"), 5)
                    + self._vb_num(wh.get("f09"), 8)
                    + self._vb_num(wh.get("f59"), 8)
                    + self._vb_num(fec_esc, 8)
                    + self._vb_num(wh.get("tipoempresa"), 1)
                    + self._vb_num(wh.get("grupoecono"), 5)
                    + self._vb_text(wh.get("doccont1"), 2)
                    + self._vb_num(wh.get("contratoant"), 6)
                    + tipopersona
                    + self._vb_num(nroent, 12)
                    + "00000"
                    + "16"
                    + self._vb_num(csc, 3)
                    + self._vb_num(wh.get("f65"), 8)
                    + self._vb_num(wh.get("lt_usuario") or wh.get("lt"), 12)
                    + self._vb_num(fec_loc, 8)
                    + tipo_negocio
                    + self._vb_num(wh.get("f20"), 10)
                    + self._vb_text(wh.get("f55"), 125)
                    + tipoaportante
                    + "NN"
                    + tipoafiliacion
                    + " " * 4
                    + (as_text(wh.get("zona")).strip()[:1] or "U")
                    + self._vb_text(wh.get("localidad"), 100)
                    + "NNN"
                    + ("S" if as_text(wh.get("aut46")).strip().upper() == "VERDADERO" else "N")
                    + ("S" if as_text(wh.get("aut47")).strip().upper() == "VERDADERO" else "N")
                    + ("S" if as_text(wh.get("aut48")).strip().upper() == "VERDADERO" else "N")
                    + "N"
                    + self._vb_text(as_text(wh.get("f51"))[:250], 250)
                    + canal
                    + "00000000"
                    + clase_aportante
                )
                lines.append(self._line_926(line1))

            if tp == "S":
                line7 = (
                    "7"
                    + self._vb_text(wh.get("f62"), 6)
                    + self._vb_text(wh.get("f71"), 34)
                    + self._vb_num(wh.get("f15"), 5)
                    + self._vb_text(wh.get("f12"), 34)
                    + self._vb_num(wh.get("f14"), 10)
                    + "0000000"
                    + "N"
                    + " " * 7
                    + " "
                    + "  "
                    + " "
                    + " " * 5
                    + "00"
                    + self._vb_num(wh.get("f60"), 1)
                    + self._vb_text(self._localidad_926(wh.get("localidad")), 100)
                    + (as_text(wh.get("zona")).strip()[:1] or "U")
                    + self._vb_text(wh.get("f20"), 60)
                    + self._vb_text(wh.get("f18"), 125)
                    + "S"
                    + " " * 6
                    + "N"
                    + " " * 266
                )
                lines.append(self._line_926(line7))

                tipod = self._doc_code(wh.get("nomcont2"))
                line5 = (
                    "5"
                    + tipod
                    + self._vb_num(wh.get("f67"), 12)
                    + self._vb_text(wh.get("f06"), 15)
                    + self._vb_text(wh.get("f69"), 15)
                    + self._vb_text(wh.get("dircont1"), 20)
                    + self._vb_text(wh.get("f70"), 20)
                    + "REP SEDE            "
                    + self._vb_text(wh.get("f12"), 40)
                    + self._vb_num(wh.get("f14"), 7)
                    + self._vb_num(wh.get("f14"), 7)
                    + self._vb_text(wh.get("f18"), 125)
                    + self._vb_num(wh.get("f15"), 5)
                    + " "
                    + "19050101"
                    + " " * 195
                )
                lines.append(self._line_926(line5))

                for ct in ct_by_sr.get(sr, []):
                    ct_codigoactividad = as_text(ct.get("codigoactividad")).strip()
                    activity_profile = self._activity_risk_profile(ct_codigoactividad)
                    ct_claseriesgo = as_text(ct.get("claseriesgo")).strip()
                    if activity_profile.get("clase") in {"1", "2", "3", "4", "5"}:
                        ct_claseriesgo = activity_profile["clase"]
                    if ct_claseriesgo not in {"1", "2", "3", "4", "5"}:
                        ct_digits = "".join(ch for ch in ct_codigoactividad if ch.isdigit())
                        ct_claseriesgo = ct_digits[:1] if ct_digits[:1] in {"1", "2", "3", "4", "5"} else "2"
                    ct_grado = activity_profile.get("grado") or as_text(ct.get("grado")).strip()
                    if not ct_grado:
                        ct_grado = "12" if "".join(ch for ch in ct_codigoactividad if ch.isdigit()) == "2851201" else "00"
                    ct_tasa = as_text(ct.get("tasa")).replace(",", ".").strip()
                    if activity_profile.get("tasa"):
                        ct_tasa = activity_profile["tasa"]
                    if ct_tasa in {"", "0", "0.0", "0.00", "0.000", "0.0000", "00000"}:
                        ct_tasa = tasa_by_clase.get(ct_claseriesgo, "1.044")
                    ct_tasa = self._format_tasa_arp(ct_tasa) or tasa_by_clase.get(ct_claseriesgo, "1.044")
                    ct_code_display = self._vb_code(ct.get("codigoct"), 6)
                    ct_nombre = (
                        as_text(ct.get("nombreactividad")).strip()
                        or as_text(wh.get("f71")).strip()
                        or activity_profile.get("nombre")
                        or f"RIESGO {ct_claseriesgo}"
                    )
                    line2 = (
                        "2"
                        + ct_code_display
                        + self._vb_text(ct_nombre, 34)
                        + self._vb_num(ct.get("ciudad"), 5)
                        + self._vb_text(ct.get("direccion"), 34)
                        + self._vb_num(ct.get("telefono"), 10)
                        + "0000000"
                        + "2"
                        + self._vb_num(ct_codigoactividad, 7)
                        + self._vb_text(ct_claseriesgo, 1)
                        + self._vb_num(ct_grado, 2)
                        + "0"
                        + self._vb_text(ct_tasa, 5)
                        + "00"
                        + "0"
                        + self._vb_text(self._localidad_926(wh.get("localidad")), 100)
                        + (as_text(wh.get("zona")).strip()[:1] or "U")
                        + self._vb_text(ct.get("telefono"), 60)
                        + self._vb_text(wh.get("f18"), 125)
                        + "N"
                        + self._vb_text(wh.get("f62"), 6)
                        + " "
                        + " " * 266
                    )
                    lines.append(self._line_926(line2))

                    tipod_ct = self._doc_code(ct.get("tipodocumento"))
                    line5_ct = (
                        "5"
                        + tipod_ct
                        + self._vb_num(ct.get("id_responsable"), 12)
                        + self._vb_text(ct.get("primerapellido"), 15)
                        + self._vb_text(ct.get("segundoapellido"), 15)
                        + self._vb_text(ct.get("primernombre"), 20)
                        + self._vb_text(ct.get("segundonombre"), 20)
                        + "REP CENTRO TRABAJO  "
                        + self._vb_text(wh.get("f12"), 40)
                        + self._vb_num(wh.get("f14"), 7)
                        + self._vb_num(wh.get("f14"), 7)
                        + self._vb_text(wh.get("f18"), 125)
                        + self._vb_num(wh.get("f15"), 5)
                        + " "
                        + "19050101"
                        + " " * 195
                    )
                    lines.append(self._line_926(line5_ct))

                    ct_code = as_text(ct.get("codigoct")).strip()
                    for wd in wd_by_sr.get(sr, []):
                        if as_text(wd.get("f28")).strip() in ("", "0"):
                            continue
                        if as_text(wd.get("f30")).strip() != ct_code:
                            continue
                        n1 = self._vb_text(wd.get("f33"), 20).strip().split(" ", 1)
                        nom1 = n1[0] if n1 else ""
                        nom2 = n1[1] if len(n1) > 1 else ""
                        modalidad = self._modalidad_code(wd.get("modalidad"), default="A")
                        jornada = self._jornada_code(wd.get("jornada"), default="U")
                        tipo_afiliado = self._tipo_afiliado_code(p_row.get("tipoafiliado"))
                        subtipo_afiliado = self._subtipo_afiliado_code(p_row.get("subtipoafiliado"))
                        wd_tel = as_text(wd.get("telefono")).strip()
                        wd_cel = as_text(wd.get("celular")).strip()
                        tel1_source = wd_tel if wd_tel not in ("", "0") else "0"
                        cel_source = wd_cel if wd_cel not in ("", "0") else as_text(wh.get("f20"))
                        line3 = (
                            "3"
                            + self._vb_num(wd.get("f29"), 1)
                            + self._vb_num(wd.get("f28"), 15)
                            + self._vb_text(wd.get("f31"), 15)
                            + self._vb_text(wd.get("f32"), 15)
                            + self._vb_text(nom1, 20)
                            + self._vb_text(nom2, 20)
                            # Inicio 88, longitud 8: fecha de nacimiento en YYYYMMDD.
                            + self._fecha_nacimiento_926(wd.get("f35"))
                            + self._vb_text(wd.get("f34"), 1)
                            + self._vb_code(wd.get("f30"), 6)
                            + self._vb_text(wd.get("f37"), 40)
                            + self._vb_num(wd.get("f38"), 10)
                            + self._vb_num(wd.get("f40"), 5)
                            + self._vb_num(wd.get("f41"), 5)
                            + "D"
                            + " " * 98
                            + self._vb_num(wd.get("municipio") or wh.get("f15"), 5)
                            + self._vb_text(wd.get("direccion") or wh.get("f12"), 50)
                            + self._vb_num(tel1_source, 7)
                            + " " * 30
                            + self._vb_num(wd.get("telefono"), 7)
                            + self._vb_num(cel_source, 10)
                            + self._vb_text(wd.get("mail"), 125)
                            + self._vb_text(p_row.get("tipocodigo"), 5)
                            + self._vb_text(p_row.get("subtipocodigo") or "0", 5)
                            + modalidad
                            + " " * 4
                            + "000000"
                            + self._code1(wd.get("zona"), default="U")
                            + self._vb_text(wd.get("localidad"), 100)
                            + jornada
                            + " " * 4
                            + (tipo_afiliado + "    ")
                            + subtipo_afiliado
                            + " " * 4
                            + ("1    " if as_text(wd.get("trabajoalturas")) not in ("", "0") else "00000")
                            + ("1" if self._catalog_normalize("tipo_salario", wd.get("tipo_salario"), default="VARIABLE") == "FIJO" else "2")
                            # Posicion 639: tipo de tramite de la empresa (f49 de la fila P;
                            # 1=Traslado, 2=Afiliacion) como letra, "T"/"A".
                            + ("T" if as_text(p_row.get("f49")).strip() == "1" else "A")
                        )
                        lines.append(self._line_926(line3))

                        days = day_by_sr.get(as_text(wd.get("sr")), [])
                        day_source = days[0] if days else wd
                        for prefix, fld in [("61", "lunes"), ("62", "martes"), ("63", "miercoles"), ("64", "jueves"), ("65", "viernes"), ("66", "sabado"), ("67", "domingo")]:
                            if as_text(wd.get(fld)).strip().upper() != "X":
                                continue
                            marks = []
                            for i in range(1, 25):
                                marks.append("X" if as_text(day_source.get(f"h{i}") or day_source.get(f"d{i}")).strip() else " ")
                            lines.append(self._line_926(prefix + "".join(marks)))

                    for ws in ws_by_sr.get(sr, []):
                        if as_text(ws.get("codigo_ct")).strip() != ct_code or as_text(ws.get("documento")).strip() in ("", "0"):
                            continue
                        line3s = (
                            "3"
                            + self._doc_code(ws.get("tipodocumento"))
                            + self._vb_num(ws.get("documento"), 15)
                            + self._vb_text(ws.get("primer_apellido"), 15)
                            + self._vb_text(ws.get("segundo_apellido"), 15)
                            + self._vb_text(ws.get("primer_nombre"), 20)
                            + self._vb_text(ws.get("segundo_nombre"), 20)
                            # Inicio 88, longitud 8: fecha de nacimiento en YYYYMMDD.
                            + self._fecha_nacimiento_926(ws.get("fecha_nacimiento"))
                            + self._vb_text(ws.get("sexo"), 1)
                            + self._vb_text(ws.get("codigo_ct"), 6)
                            + self._vb_text(ws.get("cargo"), 40)
                            + self._vb_num(ws.get("salario"), 10)
                            + self._vb_num(ws.get("eps"), 5)
                            + self._vb_num(ws.get("afp"), 5)
                            + "I"
                            + self._vb_num(0, 25)
                            + self._vb_num(ws.get("tipo_contrato"), 1)
                            + "2"
                            + self._vb_num(ws.get("codigo_actividad"), 7)
                            + self._vb_num(ws.get("salario"), 12)
                            + self._vb_num(ws.get("monto_contrato"), 12)
                            + "000000000000"
                            + self._vb_num(ws.get("monto_contrato"), 12)
                            + self._vb_num(ws.get("fecha_inicio"), 8)
                            + self._vb_num(ws.get("fecha_final"), 8)
                            + self._vb_num(ws.get("ciudad"), 5)
                            + self._vb_text(ws.get("direccion"), 50)
                            + self._vb_num(ws.get("telefono"), 7)
                            + " " * 5
                            + self._vb_num(ws.get("meses"), 3)
                            + "2"
                            + " " * 21
                            + self._vb_num(ws.get("telefono"), 7)
                            + self._vb_num(ws.get("celular"), 10)
                            + self._vb_text(ws.get("correo"), 125)
                            + "23   "
                            + "0    "
                            + "A"
                            + " " * 4
                            + "23   "
                            + " "
                            + ((as_text(ws.get("zona")).strip()[:1]) or "U")
                            + self._vb_text(ws.get("localidad"), 100)
                            + "A"
                            + " " * 4
                            + "F    "
                            + " "
                            + " " * 4
                            + "00000"
                            + ("1" if self._catalog_normalize("tipo_salario", ws.get("tipo_salario"), default="VARIABLE") == "FIJO" else "2")
                        )
                        lines.append(self._line_926(line3s))

                    for wi in wi_by_sr.get(sr, []):
                        if as_text(wi.get("codigo_ct")).strip() != ct_code or as_text(wi.get("documento")).strip() in ("", "0"):
                            continue
                        line3i = (
                            "3"
                            + self._doc_code(wi.get("tipodocumento"))
                            + self._vb_num(wi.get("documento"), 15)
                            + self._vb_text(wi.get("primer_apellido"), 15)
                            + self._vb_text(wi.get("segundo_apellido"), 15)
                            + self._vb_text(wi.get("primer_nombre"), 20)
                            + self._vb_text(wi.get("segundo_nombre"), 20)
                            # Inicio 88, longitud 8: fecha de nacimiento en YYYYMMDD.
                            + self._fecha_nacimiento_926(wi.get("fecha_nacimiento"))
                            + self._vb_text(wi.get("sexo"), 1)
                            + self._vb_text(wi.get("codigo_ct"), 6)
                            + self._vb_text("INDEPENDIENTE", 40)
                            + self._vb_num(wi.get("ibc"), 10)
                            + self._vb_num(wi.get("codigo_eps"), 5)
                            + self._vb_num(wi.get("codigo_afp"), 5)
                            + "I"
                            + self._vb_num(0, 25)
                            + self._vb_num(wi.get("tipo_contrato"), 1)
                            + "2"
                            + self._vb_num(wi.get("actividad_economica"), 7)
                            + self._vb_num(wi.get("ibc"), 12)
                            + self._vb_num(wi.get("valor_contrato"), 12)
                            + "000000000000"
                            + self._vb_num(wi.get("valor_mensual"), 12)
                            + self._vb_num(wi.get("fecha_inicio_contrato"), 8)
                            + self._vb_num(wi.get("fecha_fin_contrato"), 8)
                            + self._vb_num(wi.get("municipio"), 5)
                            + self._vb_text(wi.get("direccion"), 50)
                            + self._vb_num(wi.get("telefono"), 7)
                            + " " * 5
                            + self._vb_num(wi.get("meses_contrato"), 3)
                            + ("2" if as_text(wi.get("transporte")).strip().upper() == "NO" else "1")
                            + " " * 21
                            + self._vb_num(wi.get("telefono"), 7)
                            + self._vb_num(wi.get("celular"), 10)
                            + self._vb_text(wi.get("correo"), 125)
                            + self._vb_text(wi.get("tipo_cotizante"), 5)
                            + self._vb_text(wi.get("subtipo_cotizante") or "0", 5)
                            + "A"
                            + " " * 4
                            + self._vb_text(wi.get("actividad_economica"), 5)
                            + " "
                            + ((as_text(wi.get("zona_ct")).strip()[:1]) or "U")
                            + self._vb_text(wi.get("localidad"), 100)
                            + "A"
                            + " " * 4
                            + "C    "
                            + " "
                            + " " * 4
                            + "00000"
                            + ("1" if self._catalog_normalize("tipo_salario", wi.get("tipo_salario"), default="VARIABLE") == "FIJO" else "2")
                        )
                        lines.append(self._line_926(line3i))

            if tp == "V":
                _append_type4_lines()

        # Paridad legacy operativa: en varios lotes reales no llega fila tp='V',
        # pero sí hay registros en wdcomisiones; el tipo 4 debe existir al final.
        if wdcom_rows and not comisiones_written:
            _append_type4_lines()

        if not lines:
            return b""
        text = "\r\n".join(lines)
        return text.encode("latin-1", errors="replace")


def compare_bytes(a: bytes, b: bytes) -> Dict[str, Any]:
    sha_a = hashlib.sha256(a).hexdigest()
    sha_b = hashlib.sha256(b).hexdigest()
    same = a == b
    first_diff = -1
    if not same:
        m = min(len(a), len(b))
        for i in range(m):
            if a[i] != b[i]:
                first_diff = i
                break
        if first_diff == -1 and len(a) != len(b):
            first_diff = m
    return {
        "equal": same,
        "sha256_left": sha_a,
        "sha256_right": sha_b,
        "left_size": len(a),
        "right_size": len(b),
        "first_diff_offset": first_diff,
    }
