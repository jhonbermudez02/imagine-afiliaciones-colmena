#!/usr/bin/env python3
from __future__ import annotations

import ast
import datetime as dt
import json
import re
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]

FUN_API = ROOT / "backend/app/api/v1/funerarios.py"
NOT_API = ROOT / "backend/app/api/v1/notificaciones.py"
FUN_UI = ROOT / "frontend/src/features/funerarios/FunerariosPage.tsx"
NOT_UI = ROOT / "frontend/src/features/notificaciones/NotificacionesPage.tsx"

OUT_JSON = ROOT / "docs" / f"matriz_ui_paridad_legacy_{dt.date.today().isoformat()}.json"
OUT_MD = ROOT / "docs" / f"matriz_ui_paridad_legacy_{dt.date.today().isoformat()}.md"

# Operaciones legacy cubiertas por flujos REST equivalentes en UI (sin enviar `opc` literal).
UI_EQUIV_REST: dict[str, set[str]] = {
    "funerarios": {
        "asignar",
        "modEstado",
        "modEstadoAdm",
        "buscaReclamantes",
        "cargaReclamantes",
        "guardaBen",
        "actualizaDatosPago",
        "carguetxtbanco",
        "CargarExcelMasivo",
        "CargarExcelMasivoAsulado",
    },
    "notificaciones": {
        "modEstado",
        "finalizarTramite",
        "cargaReclamantes",
        "verReclamantes",
        "traerImagenesAValidar",
        "validarImagen",
        "consultarImagenes",
        "guardarPostEstado",
        "guardarPostGestion",
        "traerGestionPostPrestacion",
        "actualizarCategoria",
        "actualizarCategoriaNew",
        "eliminarImagenExistente",
    },
}

# Operaciones UI directas disparadas por selector dinámico (no aparecen como `opc: "..."` literal).
UI_DIRECT_EXTRA: dict[str, set[str]] = {
    "funerarios": {
        "cierraFiducia",
        "cierraAsulado",
        "cierraPensionado",
        "cierraOrigenFondos",
        "finaliza",
        "finalizaPen",
        "cargaPagosAuf",
        "cargaPagosAufFid",
        "cargaPagosAufAsu",
        "cargaPagosAufPen",
        "finoficinacheque",
        "informarCheque",
        "marcaDev",
        "marcaLla",
        "eliminatramite",
        "modificatramite",
        "cargaModalBancos",
        "pantallaR",
        "validaTrans",
        "bancos",
        "tipo_cuenta",
        "enviaContabilizacionOptima",
        "enviaContabilizacionAsulado",
        "muestraDatosPago",
        "muestraDatosPagoAjustar",
        "muestraDatosPagoFid",
        "muestraDatosPagoAsu",
        "muestraDatosPagoRech",
        "rechazaDatosPago",
        "rechazaDatosPagoAsu",
        "rechazaDatosPagoFid",
        "rechManualOptima",
        "50 Semanas y Accidente de Trabajo",
        "50 Semanas y Fidelidad",
        "Accidente de Trabajo",
        "Afiliado a Otro Regimen",
        "Fidelidad Menor a 20 A&ntilde;os",
        "No Cotizante 26 Semanas",
        "Pendiente Origen de Muerte",
        "Preexequial",
        "Reclamante No Procede",
    },
    "notificaciones": {
        "notificarIns",
        "validarTramite",
        "rechazarTramite",
        "consultaAfil",
        "cargaPlugInImages",
        "execValCloseImgNot",
        "cargaDocumentosCaso",
        "asignallamada",
        "mostrarDocumentos",
        "mostrarDocumentosNew",
        "indexaImagenes",
        "indexaImagenesNew",
        "eliminarImagenExistenteNew",
        "elimImgNoIndex",
    },
}


def _extract_supported_opcs(py_file: Path) -> set[str]:
    source = py_file.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "LEGACY_OPC_SOPORTADOS":
                    if isinstance(node.value, ast.Set):
                        values: set[str] = set()
                        for elt in node.value.elts:
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                values.add(elt.value)
                        return values
    return set()


def _extract_ui_direct_opcs(tsx_file: Path) -> set[str]:
    text = tsx_file.read_text(encoding="utf-8")
    return set(re.findall(r'opc\s*:\s*"([^"]+)"', text))


def _rows(module: str, supported: Iterable[str], direct_ui: set[str]) -> list[dict]:
    rows: list[dict] = []
    equiv_rest = UI_EQUIV_REST.get(module, set())
    direct_ui = set(direct_ui) | UI_DIRECT_EXTRA.get(module, set())
    for opc in sorted(set(supported)):
        if opc in direct_ui:
            coverage = "direct_ui"
            note = "Operacion con formulario/boton dedicado en workbench"
        elif opc in equiv_rest:
            coverage = "equiv_rest_ui"
            note = "Operacion cubierta por endpoint REST equivalente en workbench"
        else:
            coverage = "legacy_tester"
            note = "Disponible desde pestaña Legacy OPC (payload JSON manual)"
        rows.append(
            {
                "module": module,
                "opc": opc,
                "coverage": coverage,
                "note": note,
            }
        )
    return rows


def _summary(rows: list[dict], module: str) -> dict:
    subset = [r for r in rows if r["module"] == module]
    total = len(subset)
    direct = sum(1 for r in subset if r["coverage"] in {"direct_ui", "equiv_rest_ui"})
    direct_literal = sum(1 for r in subset if r["coverage"] == "direct_ui")
    equiv_rest = sum(1 for r in subset if r["coverage"] == "equiv_rest_ui")
    tester = total - direct
    return {
        "module": module,
        "total_supported": total,
        "direct_ui_total": direct,
        "direct_ui_literal": direct_literal,
        "equiv_rest_ui": equiv_rest,
        "legacy_tester": tester,
        "direct_ui_total_pct": round((direct / total * 100.0), 2) if total else 0.0,
    }


def main() -> int:
    fun_supported = _extract_supported_opcs(FUN_API)
    not_supported = _extract_supported_opcs(NOT_API)

    fun_ui = _extract_ui_direct_opcs(FUN_UI)
    not_ui = _extract_ui_direct_opcs(NOT_UI)

    rows = _rows("funerarios", fun_supported, fun_ui) + _rows("notificaciones", not_supported, not_ui)

    payload = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "source": {
            "funerarios_api": str(FUN_API),
            "notificaciones_api": str(NOT_API),
            "funerarios_ui": str(FUN_UI),
            "notificaciones_ui": str(NOT_UI),
        },
        "summary": [
            _summary(rows, "funerarios"),
            _summary(rows, "notificaciones"),
        ],
        "rows": rows,
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    fun_sum = payload["summary"][0]
    not_sum = payload["summary"][1]

    md_lines = [
        "# Matriz UI Paridad Legacy",
        "",
        f"Generado: {payload['generated_at']}",
        "",
        "## Resumen",
        "",
        (
            f"- Funerarios: {fun_sum['direct_ui_total']}/{fun_sum['total_supported']} cubiertos en UI "
            f"({fun_sum['direct_ui_total_pct']}%). "
            f"literal opc={fun_sum['direct_ui_literal']}, equivalente REST={fun_sum['equiv_rest_ui']}, "
            f"resto por Legacy OPC Tester={fun_sum['legacy_tester']}."
        ),
        (
            f"- Notificaciones: {not_sum['direct_ui_total']}/{not_sum['total_supported']} cubiertos en UI "
            f"({not_sum['direct_ui_total_pct']}%). "
            f"literal opc={not_sum['direct_ui_literal']}, equivalente REST={not_sum['equiv_rest_ui']}, "
            f"resto por Legacy OPC Tester={not_sum['legacy_tester']}."
        ),
        "",
        "## Leyenda",
        "",
        "- `direct_ui`: operación con flujo/botón/formulario dedicado en workbench.",
        "- `equiv_rest_ui`: operación legacy cubierta por endpoint REST equivalente en workbench.",
        "- `legacy_tester`: operación disponible por pestaña `Legacy OPC` con payload JSON.",
        "",
        "## Top pendientes de UI directa",
        "",
    ]

    for module in ("funerarios", "notificaciones"):
        pending = [r["opc"] for r in rows if r["module"] == module and r["coverage"] == "legacy_tester"][:25]
        md_lines.append(f"### {module.title()}")
        if pending:
            for opc in pending:
                md_lines.append(f"- {opc}")
        else:
            md_lines.append("- Sin pendientes")
        md_lines.append("")

    OUT_MD.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    print(f"OK JSON: {OUT_JSON}")
    print(f"OK MD:   {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
