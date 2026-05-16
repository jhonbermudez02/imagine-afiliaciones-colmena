from __future__ import annotations

import logging
from typing import Any

from qdrant_client import models

from .embeddings import get_embed_dims

logger = logging.getLogger("afi.qdrant_guard")


def vector_size_from_collection_info(info: Any) -> int:
    vectors = getattr(getattr(info, "config", None), "params", None)
    vectors = getattr(vectors, "vectors", None)
    if isinstance(vectors, dict):
        first = next(iter(vectors.values()), None)
        return int(getattr(first, "size", 0) or 0)
    return int(getattr(vectors, "size", 0) or 0)


def collection_vector_size(client: Any, collection_name: str) -> int:
    try:
        return vector_size_from_collection_info(client.get_collection(collection_name))
    except Exception:
        return 0


def collection_matches_current_embeddings(client: Any, collection_name: str) -> bool:
    size = collection_vector_size(client, collection_name)
    expected = get_embed_dims()
    if size == expected:
        return True
    if size:
        logger.warning(
            "Coleccion Qdrant incompatible: %s espera dim=%s y backend genera dim=%s",
            collection_name,
            size,
            expected,
        )
    return False


def ensure_current_vector_collection(client: Any, collection_name: str) -> bool:
    expected = get_embed_dims()
    size = collection_vector_size(client, collection_name)
    if size == expected:
        return True
    if size == 0:
        client.create_collection(
            collection_name=collection_name,
            vectors_config=models.VectorParams(size=expected, distance=models.Distance.COSINE),
        )
        return True
    logger.warning(
        "No se auto-recrea %s para evitar perdida de datos: dim actual=%s, dim esperada=%s",
        collection_name,
        size,
        expected,
    )
    return False
