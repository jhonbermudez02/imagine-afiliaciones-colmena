#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
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
DATASET_PATH = ROOT / "data" / "evals" / "learning" / "search_supervision.jsonl"
REPORT_PATH = ROOT / "data" / "evals" / "learning" / "search_eval_report.json"
API_URL_DEFAULT = "http://127.0.0.1:8000"


def load_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not DATASET_PATH.exists():
        raise SystemExit(f"No existe el dataset: {DATASET_PATH}")
    for line in DATASET_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def keyword_hit_score(answer: str, expected_keywords: list[str]) -> tuple[float, list[str]]:
    lowered = answer.lower()
    matched = [keyword for keyword in expected_keywords if str(keyword or "").lower() in lowered]
    score = round(len(matched) / len(expected_keywords), 4) if expected_keywords else 1.0
    return score, matched


def expected_case_score(payload: dict[str, Any], expected_case_id: str) -> float:
    if not expected_case_id:
        return 1.0
    case_ids = set()
    for source in payload.get("fuentes") or []:
        url = str(source.get("source_url") or "")
        parts = url.split("/api/cases/")
        if len(parts) < 2:
            continue
        case_ids.add(parts[1].split("/")[0])
    answer = str(payload.get("respuesta") or "")
    if expected_case_id in case_ids:
        return 1.0
    if expected_case_id in answer:
        return 1.0
    return 0.0


def company_score(answer: str, expected_company: str) -> float:
    if not expected_company:
        return 1.0
    return 1.0 if expected_company.lower() in answer.lower() else 0.0


def overall_score(keyword_score: float, case_score: float, company_score_value: float, confidence: float) -> float:
    return round((keyword_score * 0.4) + (case_score * 0.3) + (company_score_value * 0.2) + (confidence * 0.1), 4)


def grade(score: float) -> str:
    if score >= 0.9:
        return "excellent"
    if score >= 0.75:
        return "good"
    if score >= 0.55:
        return "weak"
    return "fail"


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    average = round(sum(item["score"] for item in results) / total, 4) if total else 0.0
    intents: dict[str, list[float]] = {}
    for item in results:
        intents.setdefault(item["intent"], []).append(item["score"])
    return {
        "average_score": average,
        "total": total,
        "excellent": sum(1 for item in results if item["grade"] == "excellent"),
        "good": sum(1 for item in results if item["grade"] == "good"),
        "weak": sum(1 for item in results if item["grade"] == "weak"),
        "fail": sum(1 for item in results if item["grade"] == "fail"),
        "intent_scores": {intent: round(sum(values) / len(values), 4) for intent, values in sorted(intents.items())},
        "lowest_cases": [
            {"id": item["id"], "query": item["query"], "score": item["score"], "grade": item["grade"]}
            for item in sorted(results, key=lambda row: row["score"])[:10]
        ],
    }


def run_eval(api_url: str, limit: int | None = None) -> dict[str, Any]:
    rows = load_rows()
    if limit is not None:
        rows = rows[:limit]
    results: list[dict[str, Any]] = []
    with httpx.Client(timeout=60.0) as client:
        for row in rows:
            response = client.post(
                f"{api_url}/api/afiliacion/consultar",
                json={"consulta": row["query"]},
            )
            response.raise_for_status()
            payload = response.json()
            answer = str(payload.get("respuesta") or "")
            confidence = float(payload.get("confianza") or 0.0)
            kw_score, matched_keywords = keyword_hit_score(answer, list(row.get("expected_keywords") or []))
            case_match = expected_case_score(payload, str(row.get("expected_case_id") or ""))
            company_match = company_score(answer, str(row.get("expected_company") or ""))
            score = overall_score(kw_score, case_match, company_match, confidence)
            results.append(
                {
                    "id": row["id"],
                    "case_id": row.get("case_id"),
                    "intent": row.get("intent"),
                    "query": row["query"],
                    "expected_case_id": row.get("expected_case_id"),
                    "expected_company": row.get("expected_company"),
                    "matched_keywords": matched_keywords,
                    "keyword_score": kw_score,
                    "case_score": case_match,
                    "company_score": company_match,
                    "confidence": confidence,
                    "score": score,
                    "grade": grade(score),
                    "answer_preview": answer[:500],
                }
            )
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "api_url": api_url,
        "dataset_path": str(DATASET_PATH),
        "summary": summarize(results),
        "results": results,
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Evalua la búsqueda libre usando search_supervision.jsonl.")
    parser.add_argument("--api-url", default=API_URL_DEFAULT)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    report = run_eval(args.api_url, limit=args.limit)
    summary = report["summary"]
    print(
        "[ok] search eval completado "
        f"casos={summary['total']} "
        f"promedio={summary['average_score']} "
        f"fails={summary['fail']}"
    )
    print(f"[ok] reporte={REPORT_PATH}")


if __name__ == "__main__":
    main()
