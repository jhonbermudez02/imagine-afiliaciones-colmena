#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data
    except Exception:
        return None
    return None


def summarize_smoke(data: dict[str, Any] | None) -> dict[str, Any]:
    if not data:
        return {"present": False, "ok": False, "total": 0, "passed": 0, "failed": 0}
    return {
        "present": True,
        "ok": bool(data.get("ok", False)),
        "total": int(data.get("total", 0) or 0),
        "passed": int(data.get("passed", 0) or 0),
        "failed": int(data.get("failed", 0) or 0),
        "mode": str(data.get("mode", "")),
    }


def summarize_stress(data: dict[str, Any] | None) -> dict[str, Any]:
    if not data:
        return {
            "present": False,
            "ok": False,
            "total": 0,
            "passed": 0,
            "failed": 0,
            "rps": 0.0,
            "avg_ms": 0.0,
            "p95_ms": 0.0,
            "max_ms": 0.0,
        }
    return {
        "present": True,
        "ok": bool(data.get("ok", False)),
        "total": int(data.get("total", data.get("total_requests", 0)) or 0),
        "passed": int(data.get("passed", 0) or 0),
        "failed": int(data.get("failed", 0) or 0),
        "rps": float(data.get("rps", data.get("throughput_rps", 0.0)) or 0.0),
        "avg_ms": float(data.get("avg_ms", ((data.get("latency_ms") or {}).get("avg", 0.0))) or 0.0),
        "p95_ms": float(data.get("p95_ms", ((data.get("latency_ms") or {}).get("p95", 0.0))) or 0.0),
        "max_ms": float(data.get("max_ms", ((data.get("latency_ms") or {}).get("max", 0.0))) or 0.0),
    }


def summarize_consistency(data: dict[str, Any] | None) -> dict[str, Any]:
    if not data:
        return {"present": False, "ok": False, "pass": 0, "warn": 0, "fail": 0}
    summary = data.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}
    return {
        "present": True,
        "ok": bool(data.get("ok", False)),
        "pass": int(summary.get("pass", 0) or 0),
        "warn": int(summary.get("warn", 0) or 0),
        "fail": int(summary.get("fail", 0) or 0),
    }


def summarize_parity(data: dict[str, Any] | None) -> dict[str, Any]:
    if not data:
        return {"present": False, "ok": False, "total_forms": 0, "by_module": {}}
    summary = data.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}
    by_module: dict[str, Any] = {}
    ok = True
    for module in ("funerarios", "notificaciones", "otros"):
        info = summary.get(module, {})
        if not isinstance(info, dict):
            info = {}
        avg = float(info.get("avg_coverage_pct", 0.0) or 0.0)
        below50 = int(info.get("forms_below_50_pct", 0) or 0)
        by_module[module] = {
            "forms": int(info.get("forms", 0) or 0),
            "avg_coverage_pct": avg,
            "forms_below_50_pct": below50,
        }
        if avg < 100.0 or below50 > 0:
            ok = False
    return {
        "present": True,
        "ok": ok,
        "total_forms": int(data.get("total_forms_detected", 0) or 0),
        "by_module": by_module,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Consolida reportes E2E en JSON y Markdown.")
    parser.add_argument("--docs-dir", default=os.getenv("AFILEGA_E2E_DOCS_DIR", str(Path(__file__).resolve().parents[2] / "docs")))
    parser.add_argument("--out-json", default="")
    parser.add_argument("--out-md", default="")
    args = parser.parse_args()

    docs_dir = Path(args.docs_dir)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_json = Path(args.out_json) if args.out_json else docs_dir / f"e2e_consolidado_{ts}.json"
    out_md = Path(args.out_md) if args.out_md else docs_dir / f"e2e_consolidado_{ts}.md"

    smoke_behavior = summarize_smoke(load_json(docs_dir / "smoke_behavior.json"))
    smoke_real_ready = summarize_smoke(load_json(docs_dir / "smoke_real_ready.json"))
    smoke_workbench = summarize_smoke(load_json(docs_dir / "smoke_workbench.json"))
    smoke_negative = summarize_smoke(load_json(docs_dir / "smoke_negative.json"))
    smoke_nova = summarize_smoke(load_json(docs_dir / "smoke_nova_regression.json"))
    stress_basic = summarize_stress(load_json(docs_dir / "stress_basic.json"))
    db_consistency = summarize_consistency(load_json(docs_dir / "db_consistency.json"))
    parity = summarize_parity(load_json(docs_dir / "matriz_formularios_legacy_2026-02-25.json"))

    required = [smoke_behavior, smoke_real_ready, smoke_workbench, smoke_negative, stress_basic, parity]
    if smoke_nova.get("present", False):
        required.append(smoke_nova)
    all_present = all(item.get("present", False) for item in required)
    all_ok = all(item.get("ok", False) for item in required)
    db_gate_ok = (not db_consistency.get("present", False)) or db_consistency.get("ok", False)
    gate_ok = all_present and all_ok and db_gate_ok

    consolidated: dict[str, Any] = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "docs_dir": str(docs_dir),
        "gate_ok": gate_ok,
        "checks": {
            "smoke_behavior": smoke_behavior,
            "smoke_real_ready": smoke_real_ready,
            "smoke_workbench": smoke_workbench,
            "smoke_negative": smoke_negative,
            "smoke_nova_regression": smoke_nova,
            "stress_basic": stress_basic,
            "db_consistency": db_consistency,
            "form_parity": parity,
        },
    }

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(consolidated, ensure_ascii=False, indent=2), encoding="utf-8")

    lines: list[str] = []
    lines.append("# Consolidado E2E")
    lines.append("")
    lines.append(f"- Fecha: `{consolidated['generated_at']}`")
    lines.append(f"- Gate E2E: `{'PASS' if gate_ok else 'FAIL'}`")
    lines.append("")
    lines.append("## Smokes")
    lines.append(f"- behavior: `{smoke_behavior['passed']}/{smoke_behavior['total']}` ok=`{smoke_behavior['ok']}`")
    lines.append(f"- real-ready: `{smoke_real_ready['passed']}/{smoke_real_ready['total']}` ok=`{smoke_real_ready['ok']}`")
    lines.append(f"- workbench: `{smoke_workbench['passed']}/{smoke_workbench['total']}` ok=`{smoke_workbench['ok']}`")
    lines.append(f"- negative: `{smoke_negative['passed']}/{smoke_negative['total']}` ok=`{smoke_negative['ok']}`")
    if smoke_nova["present"]:
        lines.append(f"- nova-regression: `{smoke_nova['passed']}/{smoke_nova['total']}` ok=`{smoke_nova['ok']}`")
    lines.append("")
    lines.append("## Stress")
    lines.append(
        f"- total={stress_basic['total']} passed={stress_basic['passed']} failed={stress_basic['failed']} "
        f"rps={stress_basic['rps']:.2f} avg_ms={stress_basic['avg_ms']:.2f} "
        f"p95_ms={stress_basic['p95_ms']:.2f} max_ms={stress_basic['max_ms']:.2f}"
    )
    lines.append("")
    lines.append("## DB Consistency")
    if db_consistency["present"]:
        lines.append(
            f"- pass={db_consistency['pass']} warn={db_consistency['warn']} fail={db_consistency['fail']} ok={db_consistency['ok']}"
        )
    else:
        lines.append("- no ejecutado")
    lines.append("")
    lines.append("## Paridad Formularios")
    lines.append(f"- total_forms={parity['total_forms']} ok={parity['ok']}")
    for module, info in parity["by_module"].items():
        lines.append(
            f"- {module}: forms={info['forms']} avg={info['avg_coverage_pct']:.2f}% below50={info['forms_below_50_pct']}"
        )

    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"[OK] JSON: {out_json}")
    print(f"[OK] MD:   {out_md}")
    print(f"[OK] GATE: {'PASS' if gate_ok else 'FAIL'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
