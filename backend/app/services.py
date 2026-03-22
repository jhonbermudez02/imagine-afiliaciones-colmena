import logging
import json
from typing import Dict, List
from pathlib import Path
from urllib.parse import urlparse

import asyncpg
import httpx

from .config import settings
from .rag import get_collection_stats, list_knowledge_files, load_catalog

logger = logging.getLogger(__name__)


async def check_http_service(url: str, path: str) -> str:
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{url}{path}", timeout=2.0)
        return "ok" if response.status_code == 200 else "error"
    except Exception as exc:
        logger.error("Error verificando %s%s: %s", url, path, exc)
        return "offline"


async def check_postgres() -> str:
    try:
        connection = await asyncpg.connect(settings.database_url, timeout=2.0)
        try:
            await connection.execute("SELECT 1")
        finally:
            await connection.close()
        return "ok"
    except Exception as exc:
        parsed = urlparse(settings.database_url)
        host = parsed.hostname or "unknown-host"
        logger.error("Error PostgreSQL en %s: %s", host, exc)
        return "offline"


async def get_system_health() -> Dict[str, str]:
    return {
        "api": "healthy",
        "version": settings.app_version,
        "qdrant": await check_http_service(settings.qdrant_url, "/healthz"),
        "ollama": await check_http_service(settings.ollama_url, "/api/tags"),
        "postgres": await check_postgres(),
    }


def get_feed_summary() -> Dict[str, object]:
    report_path = Path("/data/feed_report.json")
    if not report_path.exists():
        return {
            "available": False,
            "processed": 0,
            "failed": 0,
            "used_ocr": 0,
            "source_types": {},
            "last_errors": [],
        }

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    processed = [row for row in payload if row.get("status") == "ok"]
    failed = [row for row in payload if row.get("status") == "error"]
    skipped = [row for row in payload if row.get("status") == "skipped"]
    source_types: Dict[str, int] = {}
    ocr_strategies: Dict[str, int] = {}
    for row in processed:
        source_type = row.get("resolved_source_type") or row.get("source_type") or "unknown"
        source_types[source_type] = source_types.get(source_type, 0) + 1
        strategy = row.get("ocr_strategy")
        if strategy and strategy not in {"none", "direct"}:
            ocr_strategies[strategy] = ocr_strategies.get(strategy, 0) + 1

    return {
        "available": True,
        "processed": len(processed),
        "failed": len(failed),
        "skipped": len(skipped),
        "used_ocr": sum(1 for row in processed if row.get("used_ocr")),
        "source_types": source_types,
        "ocr_strategies": ocr_strategies,
        "last_errors": [
            {
                "slug": row.get("slug", ""),
                "error": row.get("error", ""),
            }
            for row in failed[:5]
        ],
    }


def get_eval_summary() -> Dict[str, object]:
    report_path = Path("/data/evals/latest_report.json")
    if not report_path.exists():
        return {
            "available": False,
            "cases_total": 0,
            "average_score": 0.0,
            "pass_rate": 0.0,
            "failed": 0,
            "weak": 0,
            "lowest_cases": [],
        }

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    summary = payload.get("summary", {})
    return {
        "available": True,
        "generated_at": payload.get("generated_at", ""),
        "cases_total": payload.get("cases_total", 0),
        "average_score": summary.get("average_score", 0.0),
        "pass_rate": summary.get("pass_rate", 0.0),
        "failed": summary.get("failed", 0),
        "weak": summary.get("weak", 0),
        "lowest_cases": summary.get("lowest_cases", []),
        "topic_performance": summary.get("topic_performance", {}),
    }


def get_compare_926_summary() -> Dict[str, object]:
    report_path = Path(settings.compare_926_history_path)
    if not report_path.exists():
        return {
            "available": False,
            "total": 0,
            "exact_matches": 0,
            "different": 0,
            "average_similarity": 0.0,
            "latest": [],
        }
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "available": False,
            "total": 0,
            "exact_matches": 0,
            "different": 0,
            "average_similarity": 0.0,
            "latest": [],
        }
    comparisons = payload if isinstance(payload, list) else []
    total = len(comparisons)
    exact = sum(1 for item in comparisons if item.get("match"))
    average = round(sum(float(item.get("similarity") or 0.0) for item in comparisons) / total, 4) if total else 0.0
    latest = []
    for item in comparisons[-5:][::-1]:
        latest.append(
            {
                "generated_at": item.get("generated_at", ""),
                "left_case_id": item.get("left_case_id", ""),
                "empresa": item.get("empresa", ""),
                "nit": item.get("nit", ""),
                "match": bool(item.get("match")),
                "similarity": float(item.get("similarity") or 0.0),
                "different_lines": int(item.get("different_lines") or 0),
            }
        )
    return {
        "available": True,
        "total": total,
        "exact_matches": exact,
        "different": total - exact,
        "average_similarity": average,
        "latest": latest,
    }


def build_recommended_actions(health: Dict[str, str]) -> List[Dict[str, str]]:
    actions: List[Dict[str, str]] = []
    collection_stats = get_collection_stats()

    if health["postgres"] != "ok":
        actions.append(
            {
                "id": "check-postgres",
                "title": "Revisar Postgres",
                "description": "Validar credenciales, volumen y conectividad del servicio de base de datos.",
            }
        )
    if health["qdrant"] != "ok":
        actions.append(
            {
                "id": "check-qdrant",
                "title": "Revisar Qdrant",
                "description": "Confirmar que la memoria vectorial esta disponible antes de habilitar RAG real.",
            }
        )
    if health["ollama"] != "ok":
        actions.append(
            {
                "id": "check-ollama",
                "title": "Revisar Ollama",
                "description": "Comprobar que los modelos locales esten descargados y listos para responder.",
            }
        )
    if collection_stats["points"] == 0:
        actions.append(
            {
                "id": "reindex-knowledge",
                "title": "Reindexar base documental",
                "description": "Qdrant esta vacio o sin chunks activos. Ejecuta una reindexacion desde NOVA.",
            }
        )
    if not actions:
        actions.append(
            {
                "id": "build-rag",
                "title": "Ampliar corpus documental",
                "description": "Siguiente paso: agregar mas normativa y procedimientos a data/knowledge para mejorar respuestas.",
            }
        )

    return actions


async def get_system_status() -> Dict[str, object]:
    health = await get_system_health()
    collection_stats = get_collection_stats()
    catalog = load_catalog()
    available_topics = sorted({metadata.get("topic", "") for metadata in catalog.values() if metadata.get("topic")})
    degraded_components = [
        name
        for name, status in health.items()
        if name not in {"api", "version"} and status != "ok"
    ]
    overall = "ok" if not degraded_components else "degraded"

    return {
        "system": "nova",
        "overall_status": overall,
        "health": health,
        "models": {
            "chat": settings.model_name,
            "embeddings": settings.embedding_model,
            "reranker": settings.reranker_model if settings.reranker_enabled else "disabled",
        },
        "knowledge_base": {
            "collection": settings.qdrant_collection,
            "documents": len(list_knowledge_files()),
            "indexed_chunks": collection_stats["points"],
            "available_topics": available_topics,
        },
        "feeding": get_feed_summary(),
        "evaluation": get_eval_summary(),
        "compare_926": get_compare_926_summary(),
        "services": [
            {
                "id": "frontend-nova",
                "name": "NOVA UI",
                "role": "Panel principal y asistente operador",
                "status": "ok",
                "target": settings.frontend_url,
            },
            {
                "id": "backend",
                "name": "NOVA API",
                "role": "Orquestacion y reglas de negocio",
                "status": health["api"],
                "target": "http://localhost:8000",
            },
            {
                "id": "postgres",
                "name": "Postgres",
                "role": "Persistencia operacional",
                "status": health["postgres"],
                "target": "postgres:5432",
            },
            {
                "id": "qdrant",
                "name": "Qdrant",
                "role": "Memoria vectorial y recuperacion",
                "status": health["qdrant"],
                "target": settings.qdrant_url,
            },
            {
                "id": "ollama",
                "name": "Ollama",
                "role": "Modelos locales de lenguaje y embeddings",
                "status": health["ollama"],
                "target": settings.ollama_url,
            },
        ],
        "recommended_actions": build_recommended_actions(health),
    }
