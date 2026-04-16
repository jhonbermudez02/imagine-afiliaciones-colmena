from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
API_URL = "http://127.0.0.1:8000"
OUTPUT_PATH = ROOT / "data" / "evals" / "latest_consulta_rpa_report.json"

QUERIES = [
    "protegemos",
    "grupo editorial protegemos",
    "empresa protegemos",
    "nit protegemos",
    "cedula representante protegemos",
    "14761012",
    "quien es el representante de protegemos",
    "muestrame la cedula de protegemos",
    "camara protegemos",
    "rut protegemos",
    "monca",
    "empresa monca",
    "85437815",
    "quien es el representante de monca",
    "muestrame la camara de comercio de monca",
    "puerto gaitan",
    "palmas de puerto gaitan",
    "empresa puerto gaitan",
    "79151538",
    "cabrera",
    "quien es el representante de puerto gaitan",
    "muestrame el rut de puerto gaitan",
    "entrega documentos puerto gaitan",
    "hernandez herrera",
    "rut monca",
    "muestrame la cedula de monca",
    "policarpo montes",
    "juan francisco hernandez herrera",
    "documento 900199617",
    "documento 900284394",
    "cedula 14761012",
    "cedula 85437815",
    "cedula 79151538",
    "busca la empresa por el nit 900199617",
    "busca la empresa por el nit 900284394",
]


def run_query(query: str) -> dict:
    response = requests.post(
        f"{API_URL}/api/afiliacion/consultar",
        json={"consulta": query, "contexto": {"topics": ["documentos", "empresas"]}},
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    return {
        "query": query,
        "confidence": payload.get("confianza"),
        "response": payload.get("respuesta", ""),
        "sources": [
            {
                "title": item.get("titulo"),
                "document_type": item.get("document_type"),
                "source_url": item.get("source_url"),
            }
            for item in payload.get("fuentes") or []
        ],
    }


def main() -> None:
    results = [run_query(query) for query in QUERIES]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "queries_total": len(results),
        "results": results,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[ok] consultas={len(results)} reporte={OUTPUT_PATH}")
    for item in results:
        first_line = item["response"].splitlines()[0] if item["response"] else ""
        print(f"- {item['query']} | confianza={item['confidence']} | {first_line}")


if __name__ == "__main__":
    main()
