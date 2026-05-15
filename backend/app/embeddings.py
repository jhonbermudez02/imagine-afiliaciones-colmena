"""Embeddings locales determinísticos sin depender de Ollama ni Torch."""
import hashlib
import logging
import math
from typing import List

logger = logging.getLogger("afi.embeddings")

LOCAL_MODEL_NAME = "local-hash-embedding-v1"
EMBED_DIMS = 384


def embed_text(text: str) -> List[float]:
    """Genera un vector local liviano para busqueda aproximada en Qdrant."""
    if not text or not text.strip():
        return []
    text = str(text).strip()[:2000]
    vector = [0.0] * EMBED_DIMS
    tokens = [tok for tok in text.lower().split() if tok]
    for token in tokens:
        digest = hashlib.blake2b(token.encode("utf-8", errors="ignore"), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "big") % EMBED_DIMS
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[bucket] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    if not norm:
        return []
    return [value / norm for value in vector]


def get_embed_dims() -> int:
    """Retorna las dimensiones del modelo activo."""
    return EMBED_DIMS


def get_engine_name() -> str:
    """Retorna el nombre del motor activo."""
    return LOCAL_MODEL_NAME


def is_local_embed_enabled() -> bool:
    """Indica si los embeddings se generan dentro del backend."""
    return True
