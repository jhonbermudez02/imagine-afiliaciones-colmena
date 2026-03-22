#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import httpx
except ModuleNotFoundError as exc:
    missing = getattr(exc, "name", "dependencia")
    raise SystemExit(
        f"Falta la dependencia '{missing}'. "
        "Ejecuta `python3 -m pip install -r backend/requirements.txt`."
    ) from exc


ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = ROOT / "data" / "evals" / "cases.json"
REPORT_PATH = ROOT / "data" / "evals" / "latest_report.json"
API_URL_DEFAULT = "http://127.0.0.1:8000"
BACKEND_ROOT = ROOT / "backend"


@dataclass
class EvalCase:
    id: str
    consulta: str
    contexto: dict[str, Any]
    expected_keywords: list[str]
    expected_sources: list[str]
    min_sources: int
    notes: str


def load_cases() -> list[EvalCase]:
    payload = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    return [EvalCase(**item) for item in payload]


def keyword_score(answer: str, expected_keywords: list[str]) -> float:
    lowered = answer.lower()
    if not expected_keywords:
        return 1.0
    hits = sum(1 for keyword in expected_keywords if keyword.lower() in lowered)
    return round(hits / len(expected_keywords), 4)


def source_score(sources: list[dict[str, Any]], expected_sources: list[str], min_sources: int) -> tuple[float, list[str]]:
    matched: list[str] = []
    haystacks = []
    for source in sources:
        text = " ".join(
            [
                str(source.get("titulo", "")),
                str(source.get("source", "")),
                str(source.get("source_url", "")),
                str(source.get("document_type", "")),
            ]
        ).lower()
        haystacks.append(text)

    for expected in expected_sources:
        if any(expected.lower() in haystack for haystack in haystacks):
            matched.append(expected)

    expected_score = (len(matched) / len(expected_sources)) if expected_sources else 1.0
    coverage_score = min(len(sources) / max(min_sources, 1), 1.0)
    return round((expected_score * 0.7) + (coverage_score * 0.3), 4), matched


def overall_score(keyword_result: float, source_result: float, confidence: float) -> float:
    return round((keyword_result * 0.45) + (source_result * 0.4) + (confidence * 0.15), 4)


def grade(score: float) -> str:
    if score >= 0.85:
        return "excellent"
    if score >= 0.7:
        return "good"
    if score >= 0.5:
        return "weak"
    return "fail"


def summarize_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    avg_score = round(sum(item["score"] for item in results) / total, 4) if total else 0.0
    passed = [item for item in results if item["score"] >= 0.7]
    failed = [item for item in results if item["score"] < 0.5]
    weak = [item for item in results if 0.5 <= item["score"] < 0.7]

    topic_performance: dict[str, list[float]] = {}
    for item in results:
        for topic in item.get("topics", []):
            topic_performance.setdefault(topic, []).append(item["score"])

    return {
        "average_score": avg_score,
        "passed": len(passed),
        "weak": len(weak),
        "failed": len(failed),
        "pass_rate": round(len(passed) / total, 4) if total else 0.0,
        "topic_performance": {
            topic: round(sum(scores) / len(scores), 4)
            for topic, scores in sorted(topic_performance.items())
        },
        "lowest_cases": [
            {"id": item["id"], "score": item["score"], "grade": item["grade"]}
            for item in sorted(results, key=lambda row: row["score"])[:5]
        ],
    }


def run_api_eval(api_url: str) -> dict[str, Any]:
    cases = load_cases()
    results: list[dict[str, Any]] = []

    with httpx.Client(timeout=60.0) as client:
        for case in cases:
            response = client.post(
                f"{api_url}/api/afiliacion/consultar",
                json={"consulta": case.consulta, "contexto": case.contexto},
            )
            response.raise_for_status()
            payload = response.json()

            answer = str(payload.get("respuesta", ""))
            sources = payload.get("fuentes") or []
            confidence = float(payload.get("confianza") or 0.0)

            kw_score = keyword_score(answer, case.expected_keywords)
            src_score, matched_sources = source_score(sources, case.expected_sources, case.min_sources)
            score = overall_score(kw_score, src_score, confidence)

            results.append(
                {
                    "id": case.id,
                    "consulta": case.consulta,
                    "topics": case.contexto.get("topics", []),
                    "expected_keywords": case.expected_keywords,
                    "expected_sources": case.expected_sources,
                    "matched_sources": matched_sources,
                    "keyword_score": kw_score,
                    "source_score": src_score,
                    "confidence": confidence,
                    "score": score,
                    "grade": grade(score),
                    "notes": case.notes,
                    "answer_preview": answer[:400],
                    "source_titles": [source.get("titulo", "") for source in sources],
                }
            )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "api_url": api_url,
        "mode": "api",
        "cases_total": len(cases),
        "summary": summarize_results(results),
        "results": results,
    }
    return report


def run_retrieval_eval(api_url: str) -> dict[str, Any]:
    cases = load_cases()
    results: list[dict[str, Any]] = []
    with httpx.Client(timeout=60.0) as client:
        for case in cases:
            response = client.post(
                f"{api_url}/api/afiliacion/retrieve",
                json={"consulta": case.consulta, "contexto": case.contexto},
            )
            response.raise_for_status()
            payload = response.json()
            sources = payload.get("fuentes") or []
            source_result, matched_sources = source_score(sources, case.expected_sources, case.min_sources)
            score = round(source_result, 4)
            results.append(
                {
                    "id": case.id,
                    "consulta": case.consulta,
                    "topics": case.contexto.get("topics", []),
                    "expected_sources": case.expected_sources,
                    "matched_sources": matched_sources,
                    "source_score": source_result,
                    "score": score,
                    "grade": grade(score),
                    "notes": case.notes,
                    "source_titles": [source.get("titulo", "") for source in sources],
                }
            )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "retrieval",
        "api_url": api_url,
        "cases_total": len(cases),
        "summary": summarize_results(results),
        "results": results,
    }
    return report


def save_report(report: dict[str, Any]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ejecuta evaluacion formal de NOVA contra un banco de casos.")
    parser.add_argument("--api-url", default=API_URL_DEFAULT)
    parser.add_argument("--mode", choices=["api", "retrieval"], default="retrieval")
    args = parser.parse_args()

    report = run_api_eval(args.api_url) if args.mode == "api" else run_retrieval_eval(args.api_url)
    save_report(report)
    summary = report["summary"]
    print(
        "[ok] evaluacion completada "
        f"modo={report['mode']} "
        f"casos={report['cases_total']} "
        f"promedio={summary['average_score']} "
        f"pass_rate={summary['pass_rate']}"
    )
    print(f"[ok] reporte={REPORT_PATH}")


if __name__ == "__main__":
    main()
