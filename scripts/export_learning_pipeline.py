#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CASES_ROOT = ROOT / "data" / "cases"
EVALS_ROOT = ROOT / "data" / "evals"
LEARNING_ROOT = EVALS_ROOT / "learning"

DOC_TYPE_TO_CODE = {
    "formulario_afiliacion": 0,
    "anexo_sedes": 1,
    "listado_trabajadores": 2,
    "comision": 3,
    "carta": 4,
    "camara_comercio": 5,
    "cedula": 6,
    "constancia_afiliacion": 7,
    "rut": 8,
    "entrega_documentos": 10,
    "soporte_ingresos": 11,
    "contrato": 12,
    "eps": 13,
    "afp": 14,
    "paz_y_salvo": 15,
    "eps_afp": 16,
    "beneficiario_final": 27,
    "sat": 28,
    "autorizacion": 98,
    "pdf": 99,
    "xlsx": -1,
}

LEGAL_SUFFIXES = {
    "sas",
    "s a s",
    "sa",
    "s a",
    "s",
    "a",
    "bic",
    "ltda",
    "s en c",
}

LEARNED_HINT_LIBRARY = {
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


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_haystack(value: Any) -> str:
    text = normalize_text(value).lower()
    text = text.replace("ñ", "n")
    text = re.sub(r"[^a-z0-9\s]+", " ", text)
    return normalize_text(text)


def only_digits(value: Any) -> str:
    return re.sub(r"\D+", "", str(value or ""))


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
    path.write_text(payload + ("\n" if payload else ""), encoding="utf-8")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_case_payloads() -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for metadata_path in sorted(CASES_ROOT.glob("*/case.json")):
        try:
            payloads.append(json.loads(metadata_path.read_text(encoding="utf-8")))
        except Exception:
            continue
    return payloads


def build_case_aliases(company: str, label: str) -> list[str]:
    company_clean = normalize_text(company)
    label_clean = normalize_text(label)
    aliases: list[str] = []
    if company_clean:
        aliases.append(company_clean)
        tokens = [
            token
            for token in normalize_haystack(company_clean).split()
            if token and token not in LEGAL_SUFFIXES and len(token) >= 2
        ]
        if tokens:
            reduced = " ".join(tokens)
            if len(reduced) >= 4:
                aliases.append(reduced)
            tail = tokens[-1]
            if len(tail) >= 4:
                aliases.append(tail)
            longest = max(tokens, key=len)
            if len(longest) >= 4:
                aliases.append(longest)
    if label_clean:
        aliases.append(label_clean)
    unique: list[str] = []
    seen = set()
    for alias in aliases:
        key = normalize_haystack(alias)
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(alias)
    return unique


def summarize_case(payload: dict[str, Any]) -> dict[str, Any]:
    analysis = payload.get("analysis") or {}
    profile = ((analysis.get("xlsx_profile") or {}).get("profile") or {})
    report = analysis.get("reporte_ejecutivo") or {}
    resumen = report.get("resumen_ejecutivo") or {}
    decision = analysis.get("decision") or {}
    precheck = (analysis.get("validacion_resumen") or {}).get("precheck") or {}
    output_926 = analysis.get("output_926") or {}
    legacy_926 = output_926.get("legacy") or {}
    docs = analysis.get("documents") or []
    received_summary = (analysis.get("checklist") or {}).get("received_summary") or []
    return {
        "case_id": str(payload.get("id") or ""),
        "label": str(payload.get("label") or ""),
        "updated_at": str(payload.get("updated_at") or ""),
        "empresa": str(resumen.get("empresa") or profile.get("empresa") or ""),
        "nit": str(resumen.get("nit") or profile.get("nit") or ""),
        "documento": str(resumen.get("documento") or profile.get("documento") or ""),
        "tipo_afiliado": str(profile.get("tipo_afiliado") or ""),
        "estado": str(resumen.get("estado") or ""),
        "recommended_status": str(decision.get("recommended_status") or ""),
        "summary": str(decision.get("summary") or ""),
        "precheck_approved": bool(precheck.get("approved")),
        "trabajadores": resumen.get("numero_trabajadores") or profile.get("numero_trabajadores"),
        "sedes": resumen.get("numero_sedes") or profile.get("numero_sedes"),
        "nomina_total": resumen.get("nomina_total") if resumen.get("nomina_total") is not None else profile.get("nomina_total"),
        "errores": list(resumen.get("errores") or []),
        "observaciones": list(resumen.get("observaciones") or []),
        "acciones_recomendadas": list(resumen.get("acciones_recomendadas") or []),
        "next_step": str(decision.get("next_step") or resumen.get("siguiente_paso") or ""),
        "has_926": bool((legacy_926 or {}).get("ok")),
        "mode_926": str(output_926.get("mode") or ""),
        "filename_926": str((legacy_926 or {}).get("filename") or ""),
        "document_count": len(docs),
        "received_types": [str(item.get("document_type") or "") for item in received_summary],
    }


def build_document_learning_rows(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
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
                    predicted_type = "xlsx"
                    ground_truth_type = expected_type or ("xlsx" if verdict == "si" else "")
                    rows.append(
                        {
                            "case_id": payload.get("id"),
                            "empresa": profile.get("empresa") or "",
                            "nit": profile.get("nit") or "",
                            "documento": profile.get("documento") or "",
                            "filename": filename,
                            "bucket": "xlsx",
                            "review_verdict": verdict,
                            "predicted_type": predicted_type,
                            "ground_truth_type": ground_truth_type,
                            "predicted_code": DOC_TYPE_TO_CODE.get(predicted_type),
                            "ground_truth_code": DOC_TYPE_TO_CODE.get(ground_truth_type) if ground_truth_type else None,
                            "supervision_status": "confirmed" if ground_truth_type else "pending_correction",
                            "classification_confidence": 1.0,
                            "ocr_quality_score": None,
                            "signals_detected": ["xlsx_profile_loaded"],
                            "text_preview": "",
                        }
                    )
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
                        "ground_truth_code": DOC_TYPE_TO_CODE.get(ground_truth_type) if ground_truth_type else None,
                        "supervision_status": "confirmed" if ground_truth_type else "pending_correction",
                        "classification_confidence": doc.get("classification_confidence"),
                        "ocr_quality_score": doc.get("ocr_quality_score"),
                        "signals_detected": doc.get("signals_detected") or [],
                        "text_preview": str(doc.get("text_preview") or doc.get("ocr_text") or "")[:800],
                    }
                )
    return rows


def build_case_learning_rows(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [summarize_case(payload) for payload in payloads]


def build_search_learning_rows(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for payload in payloads:
        summary = summarize_case(payload)
        case_id = str(summary["case_id"])
        company = str(summary["empresa"])
        label = str(summary["label"])
        aliases = build_case_aliases(company, label)
        if not aliases:
            continue
        anchor = aliases[1] if len(aliases) > 1 and len(aliases[1]) >= 4 and len(aliases[1]) <= len(aliases[0]) else aliases[0]
        expected_keywords = [company] if company else []
        rows.extend(
            [
                {
                    "id": f"{case_id}:estado",
                    "case_id": case_id,
                    "intent": "estado",
                    "query": f"estado del expediente {anchor}",
                    "expected_company": company,
                    "expected_case_id": case_id,
                    "expected_keywords": expected_keywords + [str(summary["summary"])],
                },
                {
                    "id": f"{case_id}:representante",
                    "case_id": case_id,
                    "intent": "representante",
                    "query": f"quien firma {anchor}",
                    "expected_company": company,
                    "expected_case_id": case_id,
                    "expected_keywords": expected_keywords + [str(summary["documento"])],
                },
                {
                    "id": f"{case_id}:nit",
                    "case_id": case_id,
                    "intent": "nit",
                    "query": f"cual es el nit de {anchor}",
                    "expected_company": company,
                    "expected_case_id": case_id,
                    "expected_keywords": expected_keywords + [str(summary["nit"])],
                },
                {
                    "id": f"{case_id}:documentos",
                    "case_id": case_id,
                    "intent": "documentos_recibidos",
                    "query": f"que documentos recibio {anchor}",
                    "expected_company": company,
                    "expected_case_id": case_id,
                    "expected_keywords": expected_keywords + [str(summary["document_count"])],
                },
                {
                    "id": f"{case_id}:siguiente_paso",
                    "case_id": case_id,
                    "intent": "siguiente_paso",
                    "query": f"siguiente paso {anchor}",
                    "expected_company": company,
                    "expected_case_id": case_id,
                    "expected_keywords": expected_keywords + [str(summary["next_step"])],
                },
            ]
        )
        if summary["errores"]:
            rows.append(
                {
                    "id": f"{case_id}:rechazo",
                    "case_id": case_id,
                    "intent": "rechazo",
                    "query": f"por que fue rechazado {anchor}",
                    "expected_company": company,
                    "expected_case_id": case_id,
                    "expected_keywords": expected_keywords + [str(summary["errores"][0])],
                }
            )
        if summary["observaciones"]:
            rows.append(
                {
                    "id": f"{case_id}:observaciones",
                    "case_id": case_id,
                    "intent": "observaciones",
                    "query": f"que observaciones tiene {anchor}",
                    "expected_company": company,
                    "expected_case_id": case_id,
                    "expected_keywords": expected_keywords + [str(summary["observaciones"][0])],
                }
            )
        if summary["has_926"]:
            rows.append(
                {
                    "id": f"{case_id}:926",
                    "case_id": case_id,
                    "intent": "926",
                    "query": f"926 {anchor}",
                    "expected_company": company,
                    "expected_case_id": case_id,
                    "expected_keywords": expected_keywords + [str(summary["filename_926"])],
                }
            )

        analysis = payload.get("analysis") or {}
        received_summary = (analysis.get("checklist") or {}).get("received_summary") or []
        for item in received_summary:
            doc_type = str(item.get("document_type") or "")
            files = list(item.get("files") or [])
            if not files:
                continue
            if doc_type == "cedula":
                rows.append(
                    {
                        "id": f"{case_id}:cedula",
                        "case_id": case_id,
                        "intent": "cedula",
                        "query": f"abre la cedula de {anchor}",
                        "expected_company": company,
                        "expected_case_id": case_id,
                        "expected_keywords": [files[0]],
                    }
                )
            elif doc_type == "rut":
                rows.append(
                    {
                        "id": f"{case_id}:rut",
                        "case_id": case_id,
                        "intent": "rut",
                        "query": f"abre el rut de {anchor}",
                        "expected_company": company,
                        "expected_case_id": case_id,
                        "expected_keywords": [files[0]],
                    }
                )
            elif doc_type == "camara_comercio":
                rows.append(
                    {
                        "id": f"{case_id}:camara",
                        "case_id": case_id,
                        "intent": "camara",
                        "query": f"muestrame la camara de comercio de {anchor}",
                        "expected_company": company,
                        "expected_case_id": case_id,
                        "expected_keywords": [files[0]],
                    }
                )
            elif doc_type == "formulario_afiliacion":
                rows.append(
                    {
                        "id": f"{case_id}:formulario",
                        "case_id": case_id,
                        "intent": "formulario",
                        "query": f"muestrame el formulario de {anchor}",
                        "expected_company": company,
                        "expected_case_id": case_id,
                        "expected_keywords": [files[0]],
                    }
                )
    return rows


def build_926_learning_rows(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for payload in payloads:
        analysis = payload.get("analysis") or {}
        output_926 = analysis.get("output_926") or {}
        legacy = output_926.get("legacy") or {}
        if not legacy.get("ok") or not legacy.get("content"):
            continue
        profile = ((analysis.get("xlsx_profile") or {}).get("profile") or {})
        content = str(legacy.get("content") or "")
        rows.append(
            {
                "case_id": payload.get("id"),
                "empresa": profile.get("empresa") or "",
                "nit": profile.get("nit") or "",
                "filename": legacy.get("filename") or "",
                "mode": output_926.get("mode") or "",
                "line_count": len(content.splitlines()),
                "byte_size": len(content.encode("latin-1", errors="ignore")),
                "content_sha1": __import__("hashlib").sha1(content.encode("utf-8", errors="ignore")).hexdigest(),
            }
        )
    return rows


def build_document_calibration(document_rows: list[dict[str, Any]]) -> dict[str, Any]:
    confirmed_rows = [row for row in document_rows if row.get("supervision_status") == "confirmed"]
    mismatch_rows = [
        row
        for row in confirmed_rows
        if row.get("predicted_type") and row.get("ground_truth_type") and row.get("predicted_type") != row.get("ground_truth_type")
    ]
    remap_groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in mismatch_rows:
        key = (str(row.get("predicted_type") or ""), str(row.get("ground_truth_type") or ""))
        remap_groups.setdefault(key, []).append(row)

    remaps: list[dict[str, Any]] = []
    for (predicted_type, ground_truth_type), rows in sorted(remap_groups.items(), key=lambda item: len(item[1]), reverse=True):
        signal_counts: dict[str, int] = {}
        matched_hints: dict[str, int] = {}
        for row in rows:
            for signal in row.get("signals_detected") or []:
                normalized = normalize_text(signal)
                if not normalized:
                    continue
                signal_counts[normalized] = signal_counts.get(normalized, 0) + 1
            haystack = normalize_haystack(row.get("text_preview") or "")
            for hint in LEARNED_HINT_LIBRARY.get(ground_truth_type, []):
                if normalize_haystack(hint) in haystack:
                    matched_hints[hint] = matched_hints.get(hint, 0) + 1

        remaps.append(
            {
                "from_type": predicted_type,
                "to_type": ground_truth_type,
                "count": len(rows),
                "signal_hints": [
                    signal
                    for signal, _ in sorted(signal_counts.items(), key=lambda item: (-item[1], item[0]))[:6]
                ],
                "text_hints": [
                    hint
                    for hint, _ in sorted(matched_hints.items(), key=lambda item: (-item[1], item[0]))[:6]
                ],
                "sample_filenames": [str(row.get("filename") or "") for row in rows[:3]],
            }
        )

    stable_counts: dict[str, int] = {}
    for row in confirmed_rows:
        predicted_type = str(row.get("predicted_type") or "")
        ground_truth_type = str(row.get("ground_truth_type") or "")
        if predicted_type and predicted_type == ground_truth_type:
            stable_counts[predicted_type] = stable_counts.get(predicted_type, 0) + 1

    return {
        "generated_at": utc_now(),
        "confirmed_rows_total": len(confirmed_rows),
        "confirmed_mismatch_rows_total": len(mismatch_rows),
        "stable_counts": dict(sorted(stable_counts.items(), key=lambda item: (-item[1], item[0]))),
        "remaps": remaps,
        "notes": [
            "Esta calibración no es un modelo; es una capa de señales aprendidas desde revisiones confirmadas.",
            "Usar solo como apoyo de confianza o remapeo seguro cuando la evidencia documental coincide.",
        ],
    }


def build_search_calibration(search_rows: list[dict[str, Any]]) -> dict[str, Any]:
    intent_examples: dict[str, list[str]] = {}
    trigger_counts: dict[str, dict[str, int]] = {}
    for row in search_rows:
        intent = str(row.get("intent") or "").strip()
        query = normalize_haystack(row.get("query") or "")
        company = normalize_haystack(row.get("expected_company") or "")
        if not intent or not query:
            continue
        intent_examples.setdefault(intent, [])
        if query not in intent_examples[intent]:
            intent_examples[intent].append(query)

        query_tokens = query.split()
        company_tokens = set(company.split())
        trimmed_tokens = [token for token in query_tokens if token not in company_tokens]
        trigger = normalize_text(" ".join(trimmed_tokens)).lower()
        if not trigger:
            continue
        trigger_counts.setdefault(intent, {})
        trigger_counts[intent][trigger] = trigger_counts[intent].get(trigger, 0) + 1

    intents_payload: dict[str, Any] = {}
    for intent, counts in sorted(trigger_counts.items()):
        triggers = [
            phrase
            for phrase, count in sorted(counts.items(), key=lambda item: (-item[1], -len(item[0]), item[0]))
            if (
                phrase == "926"
                or (
                    len(phrase) >= 4
                    and len(phrase.split()) <= 6
                    and not re.search(r"\d{3,}", phrase)
                    and "case " not in phrase
                    and "formulario de afiliacion y novedades" not in phrase
                )
            )
        ][:8]
        intents_payload[intent] = {
            "trigger_phrases": triggers,
            "examples": intent_examples.get(intent, [])[:5],
        }

    return {
        "generated_at": utc_now(),
        "intents": intents_payload,
        "notes": [
            "Las frases de disparo se aprenden del banco de búsqueda supervisada.",
            "Usar esta calibración primero como prioridad suave sobre la detección de intent hardcoded.",
        ],
    }


def export_learning_pipeline() -> dict[str, Any]:
    payloads = load_case_payloads()
    LEARNING_ROOT.mkdir(parents=True, exist_ok=True)

    case_rows = build_case_learning_rows(payloads)
    document_rows = build_document_learning_rows(payloads)
    search_rows = build_search_learning_rows(payloads)
    parity_rows = build_926_learning_rows(payloads)

    case_path = LEARNING_ROOT / "case_outcomes.jsonl"
    document_path = LEARNING_ROOT / "document_supervision.jsonl"
    search_path = LEARNING_ROOT / "search_supervision.jsonl"
    parity_path = LEARNING_ROOT / "flatfile_926_parity.jsonl"
    calibration_path = LEARNING_ROOT / "document_calibration.json"
    search_calibration_path = LEARNING_ROOT / "search_calibration.json"
    manifest_path = LEARNING_ROOT / "manifest.json"

    write_jsonl(case_path, case_rows)
    write_jsonl(document_path, document_rows)
    write_jsonl(search_path, search_rows)
    write_jsonl(parity_path, parity_rows)
    write_json(calibration_path, build_document_calibration(document_rows))
    write_json(search_calibration_path, build_search_calibration(search_rows))

    manifest = {
        "generated_at": utc_now(),
        "root": str(LEARNING_ROOT),
        "cases_total": len(case_rows),
        "document_rows_total": len(document_rows),
        "search_rows_total": len(search_rows),
        "parity_926_rows_total": len(parity_rows),
        "files": {
            "case_outcomes": str(case_path),
            "document_supervision": str(document_path),
            "search_supervision": str(search_path),
            "flatfile_926_parity": str(parity_path),
            "document_calibration": str(calibration_path),
            "search_calibration": str(search_calibration_path),
        },
        "notes": [
            "case_outcomes.jsonl resume verdad operativa por expediente.",
            "document_supervision.jsonl sirve para recalibrar clasificacion documental.",
            "search_supervision.jsonl sirve para evaluar y ajustar intents/ranking de busqueda.",
            "flatfile_926_parity.jsonl resume los casos con 926 disponible para control de paridad.",
            "document_calibration.json resume remapeos aprendidos confirmados para apoyo de clasificacion.",
            "search_calibration.json resume frases de disparo aprendidas para intents de busqueda.",
        ],
    }
    write_json(manifest_path, manifest)
    return manifest


def main() -> None:
    manifest = export_learning_pipeline()
    print("[ok] pipeline de aprendizaje exportado")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
