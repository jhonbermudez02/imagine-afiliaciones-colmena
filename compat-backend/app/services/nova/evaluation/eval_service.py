from __future__ import annotations

import time
from typing import Any, Callable


class EvalService:
    def run(
        self,
        cases: list[dict[str, Any]],
        answer_fn: Callable[[str, str, bool, int], dict[str, Any]],
    ) -> dict[str, Any]:
        started = time.time()
        results: list[dict[str, Any]] = []
        passed = 0
        for c in cases:
            question = str(c.get("question", "")).strip()
            expected = str(c.get("expected_contains", "")).strip().lower()
            template = str(c.get("template", "operacion")).strip() or "operacion"
            if not question:
                continue
            out = answer_fn(question, template, True, 4)
            answer = str(out.get("answer", "")).lower()
            ok = bool(expected) and expected in answer
            if ok:
                passed += 1
            results.append(
                {
                    "question": question,
                    "expected_contains": expected,
                    "passed": ok,
                    "answer_preview": str(out.get("answer", ""))[:240],
                }
            )
        total = len(results)
        duration_ms = int((time.time() - started) * 1000)
        return {
            "ok": True,
            "total": total,
            "passed": passed,
            "failed": max(0, total - passed),
            "pass_rate": round((passed / total) * 100, 2) if total else 0.0,
            "duration_ms": duration_ms,
            "results": results,
        }

