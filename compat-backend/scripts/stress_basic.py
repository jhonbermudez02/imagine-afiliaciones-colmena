#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
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


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    rank = int((len(sorted_values) - 1) * p)
    return sorted_values[rank]


def build_targets(sample_usuario: str) -> list[dict]:
    return [
        {
            "name": "notificaciones.consultaAfil",
            "method": "POST",
            "path": "/notificaciones/legacy/opc",
            "body": {"opc": "consultaAfil", "ti": "CC", "cc": "123456789", "ts": "INV"},
        },
        {
            "name": "funerarios.listarBancos",
            "method": "POST",
            "path": "/funerarios/legacy/opc",
            "body": {"opc": "listarBancos", "page": 1, "rp": 10, "sortname": "id", "sortorder": "asc"},
        },
        {
            "name": "funerarios.listarValores",
            "method": "POST",
            "path": "/funerarios/legacy/opc",
            "body": {"opc": "listarValores", "tipo": "bancos", "usuario": sample_usuario},
        },
    ]


def run_once(base_url: str, timeout: float, target: dict) -> dict:
    started = time.perf_counter()
    status, payload = http_json(
        method=target["method"],
        url=f"{base_url}{target['path']}",
        body=target["body"],
        timeout=timeout,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return {
        "name": target["name"],
        "status": status,
        "ok": status == 200,
        "elapsed_ms": elapsed_ms,
        "payload": payload,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Stress basico concurrente para endpoints legacy")
    parser.add_argument("--base-url", default="http://localhost:8000/api/v1")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--total-requests", type=int, default=150)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--sample-usuario", default="IMAGINE")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--report-json", default="")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    targets = build_targets(args.sample_usuario)
    total_requests = max(1, args.total_requests)
    concurrency = max(1, args.concurrency)

    started = time.perf_counter()
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = []
        for i in range(total_requests):
            target = targets[i % len(targets)]
            futures.append(pool.submit(run_once, base_url, args.timeout, target))
        for fut in as_completed(futures):
            result = fut.result()
            results.append(result)
            if args.verbose:
                print(
                    f"[{'OK' if result['ok'] else 'FAIL'}] {result['name']} "
                    f"status={result['status']} elapsed_ms={result['elapsed_ms']:.2f}"
                )

    duration = time.perf_counter() - started
    failures = [r for r in results if not r["ok"]]
    latencies = [r["elapsed_ms"] for r in results]
    per_endpoint: dict[str, dict] = {}
    for r in results:
        agg = per_endpoint.setdefault(r["name"], {"total": 0, "failed": 0, "latencies": []})
        agg["total"] += 1
        agg["failed"] += 0 if r["ok"] else 1
        agg["latencies"].append(r["elapsed_ms"])
    for name in list(per_endpoint.keys()):
        agg = per_endpoint[name]
        agg["passed"] = agg["total"] - agg["failed"]
        agg["avg_ms"] = round(statistics.mean(agg["latencies"]), 2) if agg["latencies"] else 0.0
        agg["p95_ms"] = round(percentile(agg["latencies"], 0.95), 2) if agg["latencies"] else 0.0
        del agg["latencies"]

    summary = {
        "mode": "stress-basic",
        "base_url": base_url,
        "total_requests": total_requests,
        "concurrency": concurrency,
        "duration_seconds": round(duration, 2),
        "throughput_rps": round(total_requests / duration, 2) if duration > 0 else 0.0,
        "passed": total_requests - len(failures),
        "failed": len(failures),
        "ok": len(failures) == 0,
        "latency_ms": {
            "avg": round(statistics.mean(latencies), 2) if latencies else 0.0,
            "p95": round(percentile(latencies, 0.95), 2) if latencies else 0.0,
            "max": round(max(latencies), 2) if latencies else 0.0,
        },
        "per_endpoint": per_endpoint,
    }

    print(
        f"[SUMMARY] mode=stress-basic total={total_requests} passed={summary['passed']} "
        f"failed={summary['failed']} concurrency={concurrency} rps={summary['throughput_rps']}"
    )
    print(
        f"[LATENCY] avg_ms={summary['latency_ms']['avg']} "
        f"p95_ms={summary['latency_ms']['p95']} max_ms={summary['latency_ms']['max']}"
    )

    if args.report_json:
        write_json_report(args.report_json, summary)
        print(f"[INFO] JSON report: {args.report_json}")

    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
