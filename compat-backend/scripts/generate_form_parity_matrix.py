#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEGACY_ROOT = ROOT.parent / "_analysis" / "flujos" / "flujos"
FUN_UI = ROOT / "frontend" / "src" / "features" / "funerarios" / "FunerariosPage.tsx"
NOT_UI = ROOT / "frontend" / "src" / "features" / "notificaciones" / "NotificacionesPage.tsx"

OUT_JSON = ROOT / "docs" / f"matriz_formularios_legacy_{dt.date.today().isoformat()}.json"
OUT_MD = ROOT / "docs" / f"matriz_formularios_legacy_{dt.date.today().isoformat()}.md"

IGNORE_PARTS = (
    "/nusoap/",
    "/lib/",
    "/includes/nusoap/",
    "/php-wsdl/",
    "/tcpdf/",
    "/vendor/",
)


def should_ignore(path: Path) -> bool:
    s = str(path).replace("\\", "/")
    return any(part in s for part in IGNORE_PARTS)


def extract_attrs(tag: str, attr: str) -> list[str]:
    # attr="x" | attr='x'
    pat = re.compile(rf"{attr}\s*=\s*(['\"])(.*?)\1", re.IGNORECASE | re.DOTALL)
    return [m.group(2).strip() for m in pat.finditer(tag) if m.group(2).strip()]


def normalize_token(token: str) -> str:
    token = token.strip()
    token = re.sub(r"<\?=.*?\?>", "", token)
    token = re.sub(r"<\?.*?\?>", "", token)
    token = token.replace("<?= $uid?>", "").replace("<?= $uid ?>", "")
    token = token.replace("<?=$uid?>", "").replace("<?=$uid ?>", "")
    token = token.replace("<?=$cc?>", "").replace("<?=$tramite?>", "")
    token = token.replace("_<?=$cc?>", "").replace("_<?=$tramite?>", "")
    token = token.replace("<?= $cc?>", "").replace("<?= $tramite?>", "")
    token = re.sub(r"_\d+$", "", token)
    token = re.sub(r"[^a-zA-Z0-9_]", "", token)
    return token.lower()


def extract_form_specs(php_file: Path) -> list[dict]:
    text = php_file.read_text(encoding="utf-8", errors="ignore")
    specs: list[dict] = []

    form_blocks = re.finditer(r"(?is)<form\b(.*?)>(.*?)</form>", text)
    for i, m in enumerate(form_blocks, start=1):
        form_open = m.group(1)
        form_body = m.group(2)
        method = extract_attrs(form_open, "method")
        action = extract_attrs(form_open, "action")
        form_id = extract_attrs(form_open, "id")
        form_name = extract_attrs(form_open, "name")

        tags = re.findall(r"(?is)<(input|select|textarea|button)\b(.*?)(?:>|/>)", form_body)
        field_tokens: list[str] = []
        hidden_opc: list[str] = []
        for tag_name, attrs in tags:
            names = extract_attrs(attrs, "name")
            ids = extract_attrs(attrs, "id")
            values = extract_attrs(attrs, "value")
            t = extract_attrs(attrs, "type")
            for n in names + ids:
                norm = normalize_token(n)
                if norm:
                    field_tokens.append(norm)
            if tag_name.lower() == "input" and t and t[0].lower() == "hidden":
                if names and normalize_token(names[0]) == "opc":
                    for v in values:
                        ov = normalize_token(v)
                        if ov:
                            hidden_opc.append(ov)

        uniq_fields = sorted(set(field_tokens))
        specs.append(
            {
                "file": str(php_file),
                "form_index": i,
                "form_id": form_id[0] if form_id else "",
                "form_name": form_name[0] if form_name else "",
                "method": method[0].upper() if method else "",
                "action": action[0] if action else "",
                "field_count": len(uniq_fields),
                "fields": uniq_fields,
                "opc": sorted(set(hidden_opc)),
            }
        )
    return specs


def module_from_path(path: str) -> str:
    p = path.replace("\\", "/").lower()
    if "/funerarios/" in p:
        return "funerarios"
    if "/notificaciones/" in p:
        return "notificaciones"
    return "otros"


def ui_text(module: str) -> str:
    if module == "funerarios":
        return FUN_UI.read_text(encoding="utf-8", errors="ignore").lower()
    if module == "notificaciones":
        return NOT_UI.read_text(encoding="utf-8", errors="ignore").lower()
    return (FUN_UI.read_text(encoding="utf-8", errors="ignore") + "\n" + NOT_UI.read_text(encoding="utf-8", errors="ignore")).lower()


def coverage_for_form(spec: dict, ui_lower: str) -> dict:
    fields = spec["fields"]
    if not fields:
        return {"matched": 0, "total": 0, "pct": 100.0, "missing": []}
    matched: list[str] = []
    missing: list[str] = []
    for f in fields:
        if len(f) < 3:
            continue
        if f in ui_lower:
            matched.append(f)
        else:
            missing.append(f)
    total = len(matched) + len(missing)
    pct = round((len(matched) / total) * 100.0, 2) if total else 100.0
    return {"matched": len(matched), "total": total, "pct": pct, "missing": missing}


def main() -> int:
    php_files = sorted(LEGACY_ROOT.rglob("*.php"))
    specs: list[dict] = []
    for f in php_files:
        if should_ignore(f):
            continue
        forms = extract_form_specs(f)
        specs.extend(forms)

    rows: list[dict] = []
    for s in specs:
        module = module_from_path(s["file"])
        cov = coverage_for_form(s, ui_text(module))
        row = {
            **s,
            "module": module,
            "coverage_pct_vs_react": cov["pct"],
            "matched_fields": cov["matched"],
            "comparable_fields": cov["total"],
            "missing_fields": cov["missing"][:40],
        }
        rows.append(row)

    by_module = {}
    for m in ("funerarios", "notificaciones", "otros"):
        subset = [r for r in rows if r["module"] == m]
        avg = round(sum(r["coverage_pct_vs_react"] for r in subset) / len(subset), 2) if subset else 0.0
        low = [r for r in subset if r["coverage_pct_vs_react"] < 50.0]
        by_module[m] = {
            "forms": len(subset),
            "avg_coverage_pct": avg,
            "forms_below_50_pct": len(low),
        }

    payload = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "source": {
            "legacy_root": str(LEGACY_ROOT),
            "fun_ui": str(FUN_UI),
            "not_ui": str(NOT_UI),
            "ignore_parts": list(IGNORE_PARTS),
        },
        "summary": by_module,
        "total_forms_detected": len(rows),
        "rows": rows,
    }
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    critical = sorted(rows, key=lambda x: (x["coverage_pct_vs_react"], -x["comparable_fields"]))[:30]
    md = [
        "# Matriz de Paridad de Formularios Legacy vs React",
        "",
        f"Generado: {payload['generated_at']}",
        "",
        "## Resumen",
        "",
        f"- Total formularios detectados (PHP user-facing): {payload['total_forms_detected']}",
        f"- Funerarios: forms={by_module['funerarios']['forms']} avg={by_module['funerarios']['avg_coverage_pct']}% bajo50={by_module['funerarios']['forms_below_50_pct']}",
        f"- Notificaciones: forms={by_module['notificaciones']['forms']} avg={by_module['notificaciones']['avg_coverage_pct']}% bajo50={by_module['notificaciones']['forms_below_50_pct']}",
        f"- Otros: forms={by_module['otros']['forms']} avg={by_module['otros']['avg_coverage_pct']}% bajo50={by_module['otros']['forms_below_50_pct']}",
        "",
        "## Formularios Críticos (menor cobertura vs React)",
        "",
    ]
    for c in critical:
        md.append(
            f"- [{Path(c['file']).name}]({c['file']}): module={c['module']} "
            f"coverage={c['coverage_pct_vs_react']}% fields={c['comparable_fields']} "
            f"opc={','.join(c['opc']) if c['opc'] else '-'}"
        )
        if c["missing_fields"]:
            md.append(f"  missing(top): {', '.join(c['missing_fields'][:12])}")
    md.append("")
    md.append("## Nota")
    md.append("- Esta métrica es de paridad de campos por nombre/id; la paridad visual exacta (layout/labels/orden) requiere ajuste manual de UI.")
    OUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")

    print(f"OK JSON: {OUT_JSON}")
    print(f"OK MD:   {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
