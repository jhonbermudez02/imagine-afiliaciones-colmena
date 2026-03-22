#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path


def http_json(method: str, url: str, body: dict | None, timeout: float) -> tuple[int, dict]:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url=url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8") or "{}"
            payload = json.loads(raw)
            return resp.getcode(), payload
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8") or "{}"
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"raw": raw}
        return exc.code, payload
    except urllib.error.URLError as exc:
        return 599, {"error": "network_unreachable", "detail": str(exc)}


def write_json_report(path: str, payload: dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_junit_report(path: str, suite_name: str, cases: list[dict]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    failures = sum(1 for c in cases if not c["ok"])
    ts = dt.datetime.utcnow().isoformat() + "Z"
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<testsuite name="{suite_name}" tests="{len(cases)}" failures="{failures}" timestamp="{ts}">',
    ]
    for case in cases:
        lines.append(f'  <testcase classname="{case["module"]}" name="{case["name"]}">')
        if not case["ok"]:
            lines.append(
                f'    <failure message="{case["message"]}">{case.get("detail", "")}</failure>'
            )
        lines.append("  </testcase>")
    lines.append("</testsuite>")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _case(
    name: str, module: str, method: str, path: str, body: dict | None, expected_statuses: set[int]
) -> dict:
    return {
        "name": name,
        "module": module,
        "method": method,
        "path": path,
        "body": body,
        "expected_statuses": expected_statuses,
    }


def build_cases() -> list[dict]:
    return [
        _case(
            "funerarios.legacy.missing_opc",
            "funerarios",
            "POST",
            "/funerarios/legacy/opc",
            {},
            {400},
        ),
        _case(
            "notificaciones.legacy.missing_opc",
            "notificaciones",
            "POST",
            "/notificaciones/legacy/opc",
            {},
            {400},
        ),
        _case(
            "funerarios.legacy.unknown_opc",
            "funerarios",
            "POST",
            "/funerarios/legacy/opc",
            {"opc": "__NO_EXISTE__"},
            {501},
        ),
        _case(
            "notificaciones.legacy.unknown_opc",
            "notificaciones",
            "POST",
            "/notificaciones/legacy/opc",
            {"opc": "__NO_EXISTE__"},
            {501},
        ),
        _case(
            "funerarios.cpp_missing_sworigen",
            "funerarios",
            "POST",
            "/funerarios/legacy/opc",
            {"opc": "cppOptimaMasivo", "tramites": ["456_123456789"], "usuario": "NEG"},
            {400},
        ),
        _case(
            "notificaciones.guardar_post_estado_missing_solicitud",
            "notificaciones",
            "POST",
            "/notificaciones/legacy/opc",
            {"opc": "guardarPostEstado", "id_estado_post": 1, "marca": "true", "user": "NEG"},
            {400},
        ),
        _case(
            "notificaciones.rest_schema_422",
            "notificaciones",
            "POST",
            "/notificaciones/afiliado/consultar",
            {},
            {422},
        ),
        _case(
            "notificaciones.rest_path_type_422",
            "notificaciones",
            "GET",
            "/notificaciones/solicitudes/abc/reclamantes",
            None,
            {422},
        ),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Negative smoke test API")
    parser.add_argument("--base-url", default="http://localhost:8000/api/v1")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--report-json", default="")
    parser.add_argument("--report-junit", default="")
    args = parser.parse_args()

    total = 0
    failed = 0
    cases_out: list[dict] = []
    base_url = args.base_url.rstrip("/")
    for case in build_cases():
        total += 1
        status, response = http_json(
            method=case["method"],
            url=f"{base_url}{case['path']}",
            body=case["body"],
            timeout=args.timeout,
        )
        ok = status in case["expected_statuses"]
        if not ok:
            failed += 1
            print(f"[FAIL] {case['name']} -> {status} {response}")
        elif args.verbose:
            print(f"[OK] {case['name']} -> {status}")
        cases_out.append(
            {
                "module": case["module"],
                "name": case["name"],
                "ok": ok,
                "status": status,
                "message": "ok" if ok else "unexpected_status",
                "detail": "" if ok else json.dumps(response, ensure_ascii=False),
            }
        )

    summary = {
        "mode": "negative",
        "base_url": base_url,
        "total": total,
        "passed": total - failed,
        "failed": failed,
        "ok": failed == 0,
        "cases": cases_out,
    }
    print(f"[SUMMARY] mode=negative total={total} passed={total - failed} failed={failed}")

    if args.report_json:
        write_json_report(args.report_json, summary)
        print(f"[INFO] JSON report: {args.report_json}")
    if args.report_junit:
        write_junit_report(args.report_junit, "smoke_negative", cases_out)
        print(f"[INFO] JUnit report: {args.report_junit}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
