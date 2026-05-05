from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _only_digits(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def _normalize_catalog_text(value: Any) -> str:
    text = _text(value).upper()
    replacements = {
        "Á": "A",
        "É": "E",
        "Í": "I",
        "Ó": "O",
        "Ú": "U",
        "Ü": "U",
        "Ñ": "N",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return "".join(ch for ch in text if ch.isalnum())


def _normalize_modalidad(value: Any) -> str:
    aliases = {
        "PRESENCIAL": "PRESENCIAL",
        "ENSITIO": "PRESENCIAL",
        "SITIO": "PRESENCIAL",
        "TELETRABAJO": "TELETRABAJO",
        "CASA": "CASA",
        "TRABAJOENCASA": "CASA",
        "REMOTO": "REMOTO",
        "REMOTA": "REMOTO",
        "TRABAJOREMOTO": "REMOTO",
    }
    text = _normalize_catalog_text(value)
    return aliases.get(text, text)


@dataclass
class RuleResult:
    ok: bool
    errors: list[str]
    derived: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "errors": self.errors, "derived": self.derived}


class AfiliacionesRulesEngine:
    SUBTIPO_AFILIADO_MAP = {2: "A", 3: "C", 4: "C", 5: "C", 6: "C", 9: "A"}
    TIPO_IDENT_EMPRESA_CODIGO = {
        "CC": "1",
        "CD": "6",
        "CE": "3",
        "NI": "0",
        "NU": "9",
        "PA": "4",
        "TI": "2",
        "PE": "8",
    }

    def tipo_persona(self, tipid_empresa: str, id_empresa: str) -> str:
        tipo = _text(tipid_empresa).upper()
        doc = _text(id_empresa)
        doc_digits = _only_digits(doc)
        if tipo == "NI":
            # Legacy-compatible: aceptar NIT con o sin dígito de verificación anexado.
            if not doc_digits:
                return "error"
            nit_base = doc_digits
            if len(doc_digits) == 10:
                nit_base = doc_digits[:9]
            elif len(doc_digits) != 9:
                return "error"
            nit = int(nit_base)
            if 600000000 <= nit <= 799999999:
                return "N"
            if 800000000 <= nit <= 999999999:
                return "J"
            return "error"
        if tipo in {"RC", "TI"}:
            return "N" if 10 <= len(doc) <= 11 else "error"
        if tipo == "CE":
            return "N" if len(doc) <= 7 else "error"
        if tipo == "PA":
            return "N" if 3 <= len(doc) <= 16 else "error"
        if tipo in {"CD", "CC"}:
            return "N" if 3 <= len(doc) <= 11 else "error"
        if tipo == "SC":
            return "N" if len(doc) == 9 else "error"
        if tipo == "PE":
            return "N" if len(doc) == 15 else "error"
        return "J"

    def trae_subtipo_afiliado(self, sub_tip_cot: Any) -> str:
        raw = _text(sub_tip_cot)
        if not raw:
            return ""
        if not raw.isdigit():
            return ""
        return self.SUBTIPO_AFILIADO_MAP.get(int(raw), "")

    def tipo_ident_empresa_codigo(self, tipid_empresa: str) -> str:
        return self.TIPO_IDENT_EMPRESA_CODIGO.get(_text(tipid_empresa).upper(), "0")

    def map_naturaleza_juridica(self, naturaleza: Any) -> int:
        val = _text(naturaleza)
        upper = val.upper()
        if upper == "PRIVADA":
            return 2
        if upper in {"PUBLICA", "PÚBLICA"}:
            return 1
        if upper == "MIXTA":
            return 3
        if val.isdigit():
            return int(val)
        return 0

    def normalize_transporte(self, value: Any) -> str:
        upper = _text(value).upper()
        if upper == "SI":
            return "S"
        if upper == "NO":
            return "N"
        return "N"

    def normalize_zona(self, value: Any) -> str:
        upper = _text(value).upper()
        if upper in {"U", "URBANA"}:
            return "U"
        if upper in {"R", "RURAL"}:
            return "R"
        return "U"

    def parse_date_ddmmyyyy(self, value: Any) -> str:
        raw = _text(value)
        if not raw:
            return ""
        try:
            dt = datetime.strptime(raw, "%d/%m/%Y")
            return dt.strftime("%Y%m%d")
        except ValueError:
            return ""

    def validate_record(self, record: dict[str, Any], mode: str = "afiliacion", temporales: list[dict[str, Any]] | None = None) -> RuleResult:
        errors: list[str] = []
        tipid_empresa = _text(record.get("tipodocumentoempleador") or record.get("tipid_empresa"))
        id_empresa = _text(record.get("numerodocumentoempleador") or record.get("id_empresa"))
        tipo_persona = self.tipo_persona(tipid_empresa, id_empresa)
        if tipo_persona == "error":
            errors.append(f"Tipo/doc empleador invalido ({tipid_empresa}-{id_empresa})")

        naturaleza = record.get("naturalezajuridica") or record.get("naturaleza_juridica_empresa")
        naturaleza_codigo = self.map_naturaleza_juridica(naturaleza)
        if naturaleza_codigo == 0:
            errors.append(f"Naturaleza juridica invalida ({_text(naturaleza)})")

        subtipo = record.get("subtipoafiliadocotizante") or record.get("subtipocot")
        subtipo_afiliado = self.trae_subtipo_afiliado(subtipo)

        derived = {
            "tipo_persona_empresa": tipo_persona,
            "tipo_ident_empresa_codigo": self.tipo_ident_empresa_codigo(tipid_empresa),
            "naturaleza_juridica_codigo": naturaleza_codigo,
            "subtipo_afiliado_codigo": subtipo_afiliado,
            "transporte_sn": self.normalize_transporte(record.get("suministratransporte") or record.get("transporte")),
            "zona_empresa": self.normalize_zona(record.get("zonaempleador") or record.get("zona_empresa")),
        }

        if mode == "novedad":
            temporal_rows = temporales or []
            documento = _text(record.get("numerodocumento") or record.get("num_id_trabajador"))
            contrato = _text(record.get("cont_madre") or record.get("numerodocumentoempleador"))
            fec_ini = _text(record.get("iniciocontrato") or record.get("fecinicon"))
            exists_temporal = any(
                _text(r.get("num_id_trabajador")) == documento
                and _text(r.get("cont_madre")) == contrato
                and _text(r.get("fecinicon")) == fec_ini
                for r in temporal_rows
            )
            derived["validacion_temporal"] = "EXISTE" if exists_temporal else "NO"
            if not exists_temporal:
                errors.append("No existe en temporal para num_id_trabajador/cont_madre/fecinicon")

        return RuleResult(ok=len(errors) == 0, errors=errors, derived=derived)

    def validate_records(self, records: list[dict[str, Any]], mode: str = "afiliacion") -> dict[str, Any]:
        results = []
        ok_count = 0
        for idx, row in enumerate(records, start=1):
            res = self.validate_record(row, mode=mode)
            if res.ok:
                ok_count += 1
            result = res.to_dict()
            result["index"] = idx
            result["idtramite"] = _text(row.get("idtramite"))
            results.append(result)
        return {
            "ok": ok_count == len(records),
            "mode": mode,
            "count": len(records),
            "ok_count": ok_count,
            "error_count": len(records) - ok_count,
            "results": results,
        }

    @staticmethod
    def _pick(row: dict[str, Any], *keys: str) -> str:
        for key in keys:
            value = _text(row.get(key))
            if value:
                return value
        return ""

    def validate_prebuild_state(
        self,
        wh_rows: list[dict[str, Any]],
        wd_rows: list[dict[str, Any]],
        wdind_rows: list[dict[str, Any]],
        lote: str = "",
    ) -> dict[str, Any]:
        errors: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []

        for row in wh_rows:
            sr = self._pick(row, "sr")
            tipoempresa = self._pick(row, "tipoempresa")
            if not tipoempresa or tipoempresa not in {"1", "2", "3", "8", "9"}:
                errors.append(
                    {
                        "table": "wh",
                        "sr": sr,
                        "code": "tipoempresa_invalid",
                        "detail": f"tipoempresa invalido ({tipoempresa or 'vacio'})",
                    }
                    )

        employer_docs: set[str] = set()
        for row in wh_rows:
            doc = self._pick(row, "f48", "numerodocumentoempleador")
            if doc:
                employer_docs.add(doc)

        seen_wd_docs: set[str] = set()
        for row in wd_rows:
            sr = self._pick(row, "sr")
            linea = self._pick(row, "li", "linea")
            tipodoc = self._pick(row, "f29", "tipodocumento")
            documento = self._pick(row, "f28", "documento")

            if not documento:
                errors.append(
                    {
                        "table": "wd",
                        "sr": sr,
                        "linea": linea,
                        "code": "documento_requerido",
                        "detail": "Documento trabajador requerido.",
                    }
                )
            else:
                key = f"{tipodoc}|{documento}"
                if key in seen_wd_docs:
                    errors.append(
                        {
                            "table": "wd",
                            "sr": sr,
                            "linea": linea,
                            "code": "trabajador_duplicado",
                            "detail": f"Trabajador duplicado ({key})",
                        }
                    )
                seen_wd_docs.add(key)
                if documento in employer_docs:
                    errors.append(
                        {
                            "table": "wd",
                            "sr": sr,
                            "linea": linea,
                            "code": "documento_igual_empleador",
                            "detail": "Documento trabajador no puede ser igual al del empleador.",
                        }
                    )

            sexo = self._pick(row, "f34", "sexo").upper()
            if sexo and sexo not in {"M", "F"}:
                errors.append(
                    {
                        "table": "wd",
                        "sr": sr,
                        "linea": linea,
                        "code": "sexo_invalido",
                        "detail": f"Sexo inválido ({sexo})",
                    }
                )

            zona = self._pick(row, "zona")
            if zona and self.normalize_zona(zona) not in {"U", "R"}:
                errors.append(
                    {
                        "table": "wd",
                        "sr": sr,
                        "linea": linea,
                        "code": "zona_invalida",
                        "detail": f"Zona inválida ({zona})",
                    }
                )

            modalidad = _normalize_modalidad(self._pick(row, "modalidad"))
            if modalidad and modalidad not in {"PRESENCIAL", "TELETRABAJO", "CASA", "REMOTO"}:
                errors.append(
                    {
                        "table": "wd",
                        "sr": sr,
                        "linea": linea,
                        "code": "modalidad_invalida",
                        "detail": f"Modalidad inválida ({modalidad})",
                    }
                )

            jornada = self._pick(row, "jornada").upper().replace("Ú", "U")
            if jornada and jornada not in {"UNICA", "TURNOS", "ROTATIVA"}:
                errors.append(
                    {
                        "table": "wd",
                        "sr": sr,
                        "linea": linea,
                        "code": "jornada_invalida",
                        "detail": f"Jornada inválida ({jornada})",
                    }
                )

            tel = self._pick(row, "telefono")
            if tel and len(_only_digits(tel)) not in {0, 7}:
                warnings.append(
                    {
                        "table": "wd",
                        "sr": sr,
                        "linea": linea,
                        "code": "telefono_formato",
                        "detail": f"Telefono con longitud no legacy ({tel})",
                    }
                )
            cel = self._pick(row, "celular")
            if cel and len(_only_digits(cel)) not in {0, 10}:
                warnings.append(
                    {
                        "table": "wd",
                        "sr": sr,
                        "linea": linea,
                        "code": "celular_formato",
                        "detail": f"Celular con longitud no legacy ({cel})",
                    }
                )
            mail = self._pick(row, "mail", "correo")
            if mail and "@" not in mail:
                warnings.append(
                    {
                        "table": "wd",
                        "sr": sr,
                        "linea": linea,
                        "code": "correo_formato",
                        "detail": f"Correo con formato no válido ({mail})",
                    }
                )

        for row in wdind_rows:
            sr = self._pick(row, "sr")
            linea = self._pick(row, "linea")
            tipodoc = self._pick(row, "tipodocumento")
            documento = self._pick(row, "documento")
            if tipodoc and documento:
                tipo = self.tipo_persona(tipodoc, documento)
                if tipo == "error":
                    errors.append(
                        {
                            "table": "wdindependientes",
                            "sr": sr,
                            "linea": linea,
                            "code": "tipodocumento_documento_invalid",
                            "detail": f"Tipo/doc invalido ({tipodoc}-{documento})",
                        }
                    )

            subtip = self._pick(row, "subtipo_cotizante", "subtipoafiliadocotizante")
            if subtip:
                subtipo_map = self.trae_subtipo_afiliado(subtip)
                if subtip.isdigit() and int(subtip) > 0 and not subtipo_map:
                    warnings.append(
                        {
                            "table": "wdindependientes",
                            "sr": sr,
                            "linea": linea,
                            "code": "subtipo_no_mapeado",
                            "detail": f"Subtipo cotizante sin mapeo ({subtip})",
                        }
                    )

        return {
            "ok": len(errors) == 0,
            "lote": lote,
            "tables_checked": {"wh": len(wh_rows), "wd": len(wd_rows), "wdindependientes": len(wdind_rows)},
            "error_count": len(errors),
            "warning_count": len(warnings),
            "errors": errors[:300],
            "warnings": warnings[:300],
        }
