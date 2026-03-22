#!/usr/bin/env python3
from __future__ import annotations

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
CASES_PATH = ROOT / "data" / "evals" / "workflow_cases.json"
REPORT_PATH = ROOT / "data" / "evals" / "latest_workflow_report.json"
API_URL_DEFAULT = "http://127.0.0.1:8000"


@dataclass
class WorkflowCase:
    id: str
    consulta: str
    contexto: dict[str, Any]
    expected_flow: str
    expected_status: str
    expected_channel: str
    expected_next_step_keywords: list[str]


def load_cases() -> list[WorkflowCase]:
    payload = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    return [WorkflowCase(**item) for item in payload]


def keyword_score(text: str, expected_keywords: list[str]) -> float:
    lowered = text.lower()
    if not expected_keywords:
        return 1.0
    hits = sum(1 for keyword in expected_keywords if keyword.lower() in lowered)
    return round(hits / len(expected_keywords), 4)


def grade(score: float) -> str:
    if score >= 0.85:
        return "excellent"
    if score >= 0.7:
        return "good"
    if score >= 0.5:
        return "weak"
    return "fail"


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    average = round(sum(item["score"] for item in results) / total, 4) if total else 0.0
    passed = [item for item in results if item["score"] >= 0.7]
    weak = [item for item in results if 0.5 <= item["score"] < 0.7]
    failed = [item for item in results if item["score"] < 0.5]
    return {
        "average_score": average,
        "passed": len(passed),
        "weak": len(weak),
        "failed": len(failed),
        "pass_rate": round(len(passed) / total, 4) if total else 0.0,
        "lowest_cases": [
            {"id": item["id"], "score": item["score"], "grade": item["grade"]}
            for item in sorted(results, key=lambda row: row["score"])[:5]
        ],
    }


def run_eval(api_url: str) -> dict[str, Any]:
    cases = load_cases()
    results: list[dict[str, Any]] = []

    with httpx.Client(timeout=30.0) as client:
        for case in cases:
            response = client.post(
                f"{api_url}/api/afiliacion/operar",
                json={"consulta": case.consulta, "contexto": case.contexto},
            )
            response.raise_for_status()
            payload = response.json()

            flow_score = 1.0 if payload.get("flow") == case.expected_flow else 0.0
            status_score = 1.0 if payload.get("recommended_status") == case.expected_status else 0.0
            channel_score = 1.0 if payload.get("recommended_channel") == case.expected_channel else 0.0
            next_step_score = keyword_score(str(payload.get("next_step", "")), case.expected_next_step_keywords)
            score = round((flow_score * 0.35) + (status_score * 0.25) + (channel_score * 0.2) + (next_step_score * 0.2), 4)

            results.append(
                {
                    "id": case.id,
                    "score": score,
                    "grade": grade(score),
                    "flow": payload.get("flow"),
                    "recommended_status": payload.get("recommended_status"),
                    "recommended_channel": payload.get("recommended_channel"),
                    "next_step": payload.get("next_step"),
                    "summary": payload.get("summary"),
                }
            )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "api_url": api_url,
        "cases_total": len(cases),
        "summary": summarize(results),
        "results": results,
    }


def main() -> None:
    report = run_eval(API_URL_DEFAULT)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    summary = report["summary"]
    print(
        "[ok] workflow-eval completada "
        f"casos={report['cases_total']} "
        f"promedio={summary['average_score']} "
        f"pass_rate={summary['pass_rate']}"
    )
    print(f"[ok] reporte={REPORT_PATH}")


if __name__ == "__main__":
    main()
