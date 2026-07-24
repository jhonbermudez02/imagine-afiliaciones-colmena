#!/usr/bin/env python3
"""Carga variaciones sinteticas derivadas de los dos paquetes AFILEGA reales."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CASES_DIR = ROOT / "data" / "cases"
KNOWLEDGE_DIR = ROOT / "data" / "knowledge"
KNOWLEDGE_FILE = KNOWLEDGE_DIR / "afilega-aprendizaje-sintetico-variaciones-2026-05-10.md"


DOC_LABELS = {
    "formulario_afiliacion": "Formulario de Afiliacion. (firmado por ambas partes)",
    "centros_trabajo": "Centros de trabajo",
    "relacion_ingreso_trabajadores": "Relacion de ingreso de trabajadores",
    "rut_contratista": "Copia RUT del Contratista",
    "camara_comercio_contratante": "Camara de Comercio de la empresa contratante original menor a 90 dias",
    "cedula_representante_legal_contratante": "Cedula de representante legal de la empresa contratante",
    "cedula_trabajador_independiente": "Cedula de trabajador independiente / contratista",
    "certificacion_afiliacion_eps": "Certificacion de afiliacion del trabajador a la EPS",
    "certificacion_afiliacion_afp": "Certificacion de afiliacion del trabajador a la AFP",
    "contrato_contratista_contratante": "Contrato entre el contratista y el contratante",
    "autorizacion_uso_datos_personales": "Autorizacion Uso Datos Personales",
    "pagos_seguridad_social": "Pagos seguridad social",
    "paz_salvo_arl_anterior": "Paz y salvo con la anterior ARL",
    "carta_presentacion_trabajador": "Carta de presentacion del trabajador por parte del Contratante",
    "imagen": "Pagina no clasificada / imagen generica",
}


def iso(minutes_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()


def document(filename: str, document_type: str, text: str, confidence: float = 0.92) -> dict[str, Any]:
    return {
        "filename": filename,
        "display_filename": filename,
        "document_type": document_type,
        "document_label": DOC_LABELS.get(document_type, document_type),
        "legacy_code": {
            "formulario_afiliacion": 0,
            "centros_trabajo": 1,
            "relacion_ingreso_trabajadores": 2,
            "camara_comercio_contratante": 5,
            "cedula_representante_legal_contratante": 6,
            "cedula_trabajador_independiente": 6,
            "rut_contratista": 8,
            "pagos_seguridad_social": 11,
            "contrato_contratista_contratante": 12,
            "certificacion_afiliacion_eps": 23,
            "certificacion_afiliacion_afp": 24,
            "autorizacion_uso_datos_personales": 98,
            "carta_presentacion_trabajador": 4,
        }.get(document_type, 99),
        "classification_confidence": confidence,
        "ocr_quality_score": confidence,
        "text_preview": text[:320],
        "signals_detected": [document_type, "synthetic_variation"],
    }


def prefill(entry_type: str, values: dict[str, str], noisy_fields: list[str] | None = None) -> dict[str, Any]:
    noisy = set(noisy_fields or [])
    merged = {
        "tipo_tramite": "afiliacion",
        "tipo_afiliacion": "colectiva" if entry_type == "empresa" else "individual",
        **values,
    }
    return {
        "entry_type": entry_type,
        "values": merged,
        "sources": {
            key: {
                "source": "synthetic_variation",
                "confidence": 0.55 if key in noisy else 0.92,
                "requires_manual_review": key in noisy,
            }
            for key in merged
        },
    }


def make_case(
    *,
    case_id: str,
    title: str,
    entry_type: str,
    minutes_ago: int,
    expected_decision: str,
    docs: list[dict[str, Any]],
    values: dict[str, str],
    learned_rules: list[str],
    blockers: list[str] | None = None,
    noisy_fields: list[str] | None = None,
) -> dict[str, Any]:
    now = iso(minutes_ago)
    blockers = blockers or []
    return {
        "id": case_id,
        "label": title,
        "entry_type": entry_type,
        "operation": "colima",
        "operation_label": "AFILEGA_FA_IMA_LA_V2",
        "validation_profile": "colima",
        "status": "completed" if expected_decision == "aprobable" else "stopped_prevalidacion",
        "created_at": iso(minutes_ago + 4),
        "updated_at": now,
        "files": [
            {
                "filename": item["filename"],
                "stored_path": str(CASES_DIR / case_id / "files" / item["filename"]),
                "size_bytes": len(item["text_preview"].encode("utf-8")),
                "content_type": ".txt",
            }
            for item in docs
        ],
        "analysis": {
            "operation": "colima",
            "operation_label": "AFILEGA_FA_IMA_LA_V2",
            "validation_profile": "colima",
            "documents": docs,
            "received_summary": {
                item["document_type"]: {
                    "label": item["document_label"],
                    "count": sum(1 for doc in docs if doc["document_type"] == item["document_type"]),
                }
                for item in docs
            },
            "digitacion_prefill": prefill(entry_type, values, noisy_fields=noisy_fields),
            "synthetic_learning": {
                "source_real_cases": ["case-colima-849c7f2999", "case-colima-6104b466ae"],
                "expected_decision": expected_decision,
                "blockers": blockers,
                "learned_rules": learned_rules,
            },
            "decision": {
                "recommended_status": expected_decision,
                "summary": f"Variacion sintetica AFILEGA: {title}.",
                "blockers": blockers,
                "next_step": "Usar como regresion de OCR, clasificacion documental, Digitacion y generacion 926.",
            },
            "workflow_run": {
                "status": "completed" if expected_decision == "aprobable" else "stopped_prevalidacion",
                "current_step": "synthetic_learning",
                "steps": [
                    {"id": "explosion_multipdf", "status": "ok"},
                    {"id": "ocr_por_pagina", "status": "ok"},
                    {"id": "clasificacion_documental", "status": "ok"},
                    {"id": "prellenado_digitacion", "status": "ok" if not noisy_fields else "observed"},
                ],
                "output_926": {
                    "legacy": {
                        "ok": expected_decision == "aprobable",
                        "filename": f"BkCargue_{case_id[-3:]}.txt",
                    }
                },
            },
        },
    }


def write_case(payload: dict[str, Any]) -> None:
    case_dir = CASES_DIR / payload["id"]
    files_dir = case_dir / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    for item in payload["analysis"]["documents"]:
        (files_dir / item["filename"]).write_text(
            "\n".join(
                [
                    f"CASO SINTETICO: {payload['label']}",
                    f"TIPO ENTRADA: {payload['entry_type']}",
                    f"TIPO DOCUMENTAL: {item['document_label']}",
                    "",
                    item["text_preview"],
                ]
            )
            + "\n",
            encoding="utf-8",
        )
    (case_dir / "case.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_cases() -> list[dict[str, Any]]:
    return [
        make_case(
            case_id="case-afilega-syn-empresa-completo-001",
            title="Empresa multipdf completo aprobable",
            entry_type="empresa",
            minutes_ago=10,
            expected_decision="aprobable",
            docs=[
                document("EMPRESA_SYN__p001.txt", "formulario_afiliacion", "Formulario firmado por contratante y trabajador. NIT 901880001. Razon social AFILEGA EMPRESA COMPLETA SAS."),
                document("EMPRESA_SYN__p002.txt", "centros_trabajo", "Centro de trabajo Principal, Bogota D.C., direccion Calle 72 10 20, riesgo I."),
                document("EMPRESA_SYN__p003.txt", "camara_comercio_contratante", "Camara de Comercio expedida hace 15 dias. Razon social AFILEGA EMPRESA COMPLETA SAS."),
                document("EMPRESA_SYN__p004.txt", "rut_contratista", "RUT DIAN NIT 901880001 actividad economica homologable."),
                document("EMPRESA_SYN__p005.txt", "cedula_representante_legal_contratante", "Republica de Colombia cedula de ciudadania 101880001 representante legal."),
                document("EMPRESA_SYN__p006.txt", "relacion_ingreso_trabajadores", "Plantilla cargue masivo con trabajador CC 101880101 salario 1800000."),
            ],
            values={"razon_social": "AFILEGA EMPRESA COMPLETA SAS", "nit": "901880001", "sede_nombre": "Principal", "sede_codigo": "1", "sede_direccion": "Calle 72 10 20", "documento_afiliado": "101880101"},
            learned_rules=["El orden de paginas no importa si todos los soportes obligatorios se clasifican.", "Empresa completa debe proponer tipo_afiliacion colectiva."],
        ),
        make_case(
            case_id="case-afilega-syn-empresa-desorden-002",
            title="Empresa paginas desordenadas y autorizacion duplicada",
            entry_type="empresa",
            minutes_ago=14,
            expected_decision="aprobable",
            docs=[
                document("EMPRESA_SYN__p010.txt", "autorizacion_uso_datos_personales", "Autorizacion tratamiento de datos personales firmada."),
                document("EMPRESA_SYN__p003.txt", "camara_comercio_contratante", "Camara de Comercio valida para AFILEGA DESORDEN SAS."),
                document("EMPRESA_SYN__p001.txt", "formulario_afiliacion", "Formulario afiliacion AFILEGA DESORDEN SAS NIT 901880002."),
                document("EMPRESA_SYN__p010_copia1.txt", "autorizacion_uso_datos_personales", "Copia duplicada de autorizacion de datos personales."),
                document("EMPRESA_SYN__p004.txt", "relacion_ingreso_trabajadores", "Relacion de ingreso con dos trabajadores."),
            ],
            values={"razon_social": "AFILEGA DESORDEN SAS", "nit": "901880002", "sede_nombre": "Principal", "sede_codigo": "1"},
            learned_rules=["Las paginas desordenadas no deben afectar el resultado.", "Documentos duplicados se cuentan como evidencia repetida y no deben crear campos duplicados."],
        ),
        make_case(
            case_id="case-afilega-syn-empresa-sin-camara-003",
            title="Empresa sin Camara de Comercio",
            entry_type="empresa",
            minutes_ago=18,
            expected_decision="observado",
            docs=[
                document("EMPRESA_SYN__p001.txt", "formulario_afiliacion", "Formulario afiliacion AFILEGA SIN CAMARA SAS NIT 901880003."),
                document("EMPRESA_SYN__p002.txt", "centros_trabajo", "Centro de trabajo Principal."),
                document("EMPRESA_SYN__p003.txt", "rut_contratista", "RUT NIT 901880003."),
            ],
            values={"razon_social": "AFILEGA SIN CAMARA SAS", "nit": "901880003", "sede_nombre": "Principal", "sede_codigo": "1"},
            blockers=["Falta Camara de Comercio de la empresa contratante menor a 90 dias."],
            learned_rules=["Si falta Camara de Comercio, no aprobar aunque formulario y RUT existan.", "RAG debe pedir soporte o reclasificacion manual si la camara esta en paginas no clasificadas."],
        ),
        make_case(
            case_id="case-afilega-syn-empresa-ocr-ruido-004",
            title="Empresa con OCR ruidoso en datos alfa y email",
            entry_type="empresa",
            minutes_ago=22,
            expected_decision="observado",
            docs=[
                document("EMPRESA_SYN__p001.txt", "formulario_afiliacion", "Razon social leida como AFILEGA 77 SAS Tipo de documento. Correo ofuala@gmal.communicipio."),
                document("EMPRESA_SYN__p002.txt", "camara_comercio_contratante", "Camara valida, OCR parcial no extrae razon social limpia.", confidence=0.62),
            ],
            values={"razon_social": "AFILEGA 77 SAS Tipo de documento", "correo_empresa": "ofuala@gmal.communicipio", "nit": "901880004", "eps": "menor a 30 dias de expedicion"},
            noisy_fields=["razon_social", "correo_empresa", "eps"],
            blockers=["Campos OCR ruidosos no deben pasar validacion alfa, email ni catalogo EPS."],
            learned_rules=["Campos alfa no aceptan numeros mezclados ni etiquetas de formulario.", "Correos con municipio/comuna o dominios mal leidos deben rechazarse.", "Frases normativas no son EPS/AFP validas."],
        ),
        make_case(
            case_id="case-afilega-syn-contratista-completo-005",
            title="Contratista multipdf completo aprobable",
            entry_type="contratista",
            minutes_ago=26,
            expected_decision="aprobable",
            docs=[
                document("CONTRATISTA_SYN__p001.txt", "carta_presentacion_trabajador", "Carta de presentacion del trabajador independiente por parte del contratante."),
                document("CONTRATISTA_SYN__p002.txt", "formulario_afiliacion", "Formulario afiliacion individual CC 102880005."),
                document("CONTRATISTA_SYN__p003.txt", "cedula_trabajador_independiente", "Republica de Colombia cedula de ciudadania 102880005."),
                document("CONTRATISTA_SYN__p004.txt", "certificacion_afiliacion_eps", "Certificacion EPS activa expedida hace 10 dias. EPS Sanitas."),
                document("CONTRATISTA_SYN__p005.txt", "certificacion_afiliacion_afp", "Certificacion AFP Proteccion expedida hace 12 dias."),
                document("CONTRATISTA_SYN__p006.txt", "contrato_contratista_contratante", "Contrato prestacion de servicios con fecha inicial y final."),
            ],
            values={"nit": "102880005", "tipo_documento_afiliado": "CC", "documento_afiliado": "102880005", "eps": "EPS SANITAS", "afp": "PROTECCION", "sede_nombre": "Principal", "sede_codigo": "1"},
            learned_rules=["Contratista completo debe proponer tipo_afiliacion individual.", "EPS y AFP validas deben mapear contra catalogos."],
        ),
        make_case(
            case_id="case-afilega-syn-contratista-sin-cedula-006",
            title="Contratista con documento en contrato pero sin cedula",
            entry_type="contratista",
            minutes_ago=30,
            expected_decision="observado",
            docs=[
                document("CONTRATISTA_SYN__p001.txt", "carta_presentacion_trabajador", "Carta menciona CC 102880006."),
                document("CONTRATISTA_SYN__p002.txt", "contrato_contratista_contratante", "Contrato menciona contratista CC 102880006."),
                document("CONTRATISTA_SYN__p003.txt", "certificacion_afiliacion_eps", "Certificacion EPS activa."),
            ],
            values={"nit": "102880006", "tipo_documento_afiliado": "CC", "documento_afiliado": "102880006"},
            blockers=["Falta soporte clasificado como Cedula de trabajador independiente / contratista."],
            learned_rules=["El numero de documento en carta o contrato no reemplaza la cedula.", "RAG debe sugerir buscar la cedula en paginas no clasificadas o pedir el soporte."],
        ),
        make_case(
            case_id="case-afilega-syn-contratista-eps-afp-frase-007",
            title="Contratista con EPS/AFP leidas como frases del formato",
            entry_type="contratista",
            minutes_ago=34,
            expected_decision="observado",
            docs=[
                document("CONTRATISTA_SYN__p001.txt", "formulario_afiliacion", "Formulario individual CC 102880007."),
                document("CONTRATISTA_SYN__p002.txt", "cedula_trabajador_independiente", "Cedula ciudadania 102880007."),
                document("CONTRATISTA_SYN__p003.txt", "certificacion_afiliacion_eps", "OCR lee solamente menor a 30 dias de expedicion.", confidence=0.58),
                document("CONTRATISTA_SYN__p004.txt", "certificacion_afiliacion_afp", "OCR lee para pensionado adjuntar resolucion de pension.", confidence=0.58),
            ],
            values={"documento_afiliado": "102880007", "eps": "menor a 30 dias de expedicion", "afp": "para pensionado adjuntar resolucion de pension"},
            noisy_fields=["eps", "afp"],
            blockers=["EPS y AFP no son entidades homologables; son instrucciones del formato."],
            learned_rules=["Frases del formato deben bloquear prellenado EPS/AFP.", "La certificacion puede existir pero aun requerir lectura manual de entidad."],
        ),
        make_case(
            case_id="case-afilega-syn-contratista-duplicados-008",
            title="Contratista con pagos y contrato duplicados",
            entry_type="contratista",
            minutes_ago=38,
            expected_decision="aprobable",
            docs=[
                document("CONTRATISTA_SYN__p001.txt", "formulario_afiliacion", "Formulario individual CC 102880008."),
                document("CONTRATISTA_SYN__p002.txt", "cedula_trabajador_independiente", "Cedula ciudadania 102880008."),
                document("CONTRATISTA_SYN__p003.txt", "contrato_contratista_contratante", "Contrato prestacion de servicios."),
                document("CONTRATISTA_SYN__p003_copia1.txt", "contrato_contratista_contratante", "Copia duplicada contrato prestacion de servicios."),
                document("CONTRATISTA_SYN__p004.txt", "pagos_seguridad_social", "Planilla PILA pagada."),
                document("CONTRATISTA_SYN__p004_copia1.txt", "pagos_seguridad_social", "Copia duplicada planilla PILA pagada."),
            ],
            values={"documento_afiliado": "102880008", "nit": "102880008", "sede_nombre": "Principal", "sede_codigo": "1"},
            learned_rules=["Duplicados no deben bloquear si existe al menos un soporte valido por tipo requerido.", "El resumen debe mostrar cantidad para auditoria."],
        ),
    ]


def write_knowledge(cases: list[dict[str, Any]]) -> None:
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        "# AFILEGA - aprendizaje sintetico por variaciones controladas",
        "",
        "Fecha de carga: 2026-05-10.",
        "Proyecto: AFILEGA_FA_IMA_LA_V2.",
        "Origen: variaciones sinteticas derivadas de los paquetes reales `case-colima-849c7f2999` y `case-colima-6104b466ae`.",
        "",
        "Este documento no agrega nuevos datos reales. Usa los mismos patrones observados en empresa y contratista para entrenar reglas operativas, regresion de OCR, prellenado de Digitacion y decision previa al archivo 926.",
        "",
        "## Escenarios sinteticos creados",
        "",
    ]
    for case in cases:
        synthetic = case["analysis"]["synthetic_learning"]
        values = case["analysis"]["digitacion_prefill"]["values"]
        docs = case["analysis"]["documents"]
        lines.extend(
            [
                f"### {case['id']} - {case['label']}",
                "",
                f"- Tipo de entrada: `{case['entry_type']}`.",
                f"- Decision esperada: `{synthetic['expected_decision']}`.",
                f"- Documentos: {', '.join(sorted({doc['document_label'] for doc in docs}))}.",
                f"- Campos esperados de Digitacion: {', '.join(f'`{key}={value}`' for key, value in values.items())}.",
            ]
        )
        if synthetic["blockers"]:
            lines.append(f"- Bloqueos esperados: {'; '.join(synthetic['blockers'])}.")
        for rule in synthetic["learned_rules"]:
            lines.append(f"- Regla aprendida: {rule}")
        lines.append("")
    lines.extend(
        [
            "## Reglas reforzadas",
            "",
            "1. Repetir los mismos paquetes reales no agrega datos nuevos, pero si permite probar estabilidad, duplicados, orden de paginas y ruido OCR.",
            "2. Las variaciones sinteticas deben marcarse como sinteticas y no mezclarse con evidencia real.",
            "3. Para `empresa`, `tipo_afiliacion` esperado es `colectiva`; para `contratista`, `individual`.",
            "4. Paginas desordenadas o duplicadas no deben cambiar la decision si los soportes obligatorios estan presentes.",
            "5. Faltantes documentales como Camara de Comercio o Cedula deben dejar el caso observado aunque otros documentos mencionen la informacion.",
            "6. Campos OCR ruidosos, correos mal leidos y frases normativas usadas como EPS/AFP deben bloquear prellenado automatico y pedir revision manual.",
            "7. Un caso aprobable puede generar archivo 926; un caso observado debe detenerse antes de generar plano definitivo.",
            "",
        ]
    )
    KNOWLEDGE_FILE.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    CASES_DIR.mkdir(parents=True, exist_ok=True)
    cases = build_cases()
    for payload in cases:
        write_case(payload)
    write_knowledge(cases)
    print(json.dumps({"ok": True, "cases": len(cases), "knowledge": str(KNOWLEDGE_FILE)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
