from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from qdrant_client import QdrantClient, models

from app.embeddings import embed_text, get_embed_dims, get_engine_name


QDRANT_HOST = "imagine_qdrant"
QDRANT_PORT = 6333
BACKUP_DIR = Path("/data/evals/qdrant_repair_backups")


def _collection_size(client: QdrantClient, name: str) -> int:
    try:
        info = client.get_collection(name)
    except Exception:
        return 0
    vectors = info.config.params.vectors
    if isinstance(vectors, dict):
        first = next(iter(vectors.values()), None)
        return int(getattr(first, "size", 0) or 0)
    return int(getattr(vectors, "size", 0) or 0)


def _scroll_all(client: QdrantClient, name: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset: Any = None
    while True:
        points, offset = client.scroll(
            collection_name=name,
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for point in points:
            rows.append({"id": point.id, "payload": point.payload or {}})
        if offset is None:
            break
    return rows


def _doc_text(payload: dict[str, Any]) -> str:
    return " ".join(
        str(part or "")
        for part in [
            "documento clasificacion",
            payload.get("document_type"),
            payload.get("legacy_code"),
            payload.get("filename"),
            payload.get("empresa"),
            payload.get("ocr_preview"),
        ]
    )


def _entity_text(payload: dict[str, Any]) -> str:
    tipo = str(payload.get("tipo") or "").upper()
    return " ".join(
        str(part or "")
        for part in [
            tipo,
            "catalogo entidad seguridad social",
            payload.get("nombre"),
            payload.get("codigo"),
        ]
    )


def _repair_collection(client: QdrantClient, name: str, text_builder: Callable[[dict[str, Any]], str]) -> dict[str, Any]:
    expected = get_embed_dims()
    current = _collection_size(client, name)
    rows = _scroll_all(client, name) if current else []
    result = {
        "collection": name,
        "previous_dim": current,
        "target_dim": expected,
        "points_before": len(rows),
        "recreated": False,
        "points_after": 0,
    }
    if current == expected:
        result["points_after"] = len(rows)
        return result

    if current:
        client.delete_collection(name)
    client.create_collection(
        collection_name=name,
        vectors_config=models.VectorParams(size=expected, distance=models.Distance.COSINE),
    )
    result["recreated"] = True

    batch: list[models.PointStruct] = []
    for row in rows:
        payload = row["payload"]
        vector = embed_text(text_builder(payload))
        if not vector:
            continue
        batch.append(models.PointStruct(id=row["id"], vector=vector, payload=payload))
        if len(batch) >= 128:
            client.upsert(collection_name=name, points=batch)
            result["points_after"] += len(batch)
            batch = []
    if batch:
        client.upsert(collection_name=name, points=batch)
        result["points_after"] += len(batch)
    return result


def main() -> None:
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    collections: dict[str, Callable[[dict[str, Any]], str]] = {
        "afi_doc_clasificaciones": _doc_text,
        "afi_eps_catalog": _entity_text,
        "afi_afp_catalog": _entity_text,
    }

    backup: dict[str, Any] = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "embedding_engine": get_engine_name(),
        "embedding_dims": get_embed_dims(),
        "collections": {},
    }
    for name in collections:
        try:
            backup["collections"][name] = {
                "dimension": _collection_size(client, name),
                "points": _scroll_all(client, name),
            }
        except Exception as exc:
            backup["collections"][name] = {"error": str(exc)}

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_path = BACKUP_DIR / f"qdrant_backup_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    backup_path.write_text(json.dumps(backup, ensure_ascii=False, indent=2), encoding="utf-8")

    results = [_repair_collection(client, name, builder) for name, builder in collections.items()]
    print(json.dumps({"backup": str(backup_path), "results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
