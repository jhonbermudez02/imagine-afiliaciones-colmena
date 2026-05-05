"""
Capa de abstracción de embeddings.
Soporta dos motores:
  - Ollama (nomic-embed-text, 768 dims) — motor actual
  - sentence-transformers (paraphrase-multilingual-MiniLM-L12-v2, 384 dims) — motor local

Se controla con la variable de entorno USE_LOCAL_EMBED=true/false
"""
import os
import logging
from typing import List, Optional

logger = logging.getLogger("afi.embeddings")

# Variable de entorno para controlar el motor
USE_LOCAL_EMBED = os.getenv("USE_LOCAL_EMBED", "false").lower() == "true"
LOCAL_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
OLLAMA_MODEL_NAME = "nomic-embed-text"
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://imagine_ollama:11434")

# Dimensiones por motor
EMBED_DIMS_OLLAMA = 768
EMBED_DIMS_LOCAL = 384
EMBED_DIMS = EMBED_DIMS_LOCAL if USE_LOCAL_EMBED else EMBED_DIMS_OLLAMA

# Modelo local (se carga una sola vez)
_local_model = None

def _get_local_model():
    global _local_model
    if _local_model is None:
        logger.info("Cargando modelo local %s...", LOCAL_MODEL_NAME)
        from sentence_transformers import SentenceTransformer
        _local_model = SentenceTransformer(LOCAL_MODEL_NAME)
        logger.info("Modelo local cargado. Dims: %d", _local_model.get_sentence_embedding_dimension())
    return _local_model

def embed_text(text: str) -> List[float]:
    """Genera embedding para un texto. Usa el motor configurado."""
    if not text or not text.strip():
        return []
    text = str(text).strip()[:2000]
    if USE_LOCAL_EMBED:
        return _embed_local(text)
    else:
        return _embed_ollama(text)

def _embed_local(text: str) -> List[float]:
    """Embedding con sentence-transformers (local, sin servidor)."""
    try:
        model = _get_local_model()
        vector = model.encode(text, normalize_embeddings=True, show_progress_bar=False)
        return vector.tolist()
    except Exception as e:
        logger.error("Error en embedding local: %s", e)
        return []

def _embed_ollama(text: str) -> List[float]:
    """Embedding con Ollama (servidor externo)."""
    try:
        import httpx
        r = httpx.post(
            f"{OLLAMA_URL}/api/embeddings",
            json={"model": OLLAMA_MODEL_NAME, "prompt": text},
            timeout=30,
        )
        return r.json().get("embedding", [])
    except Exception as e:
        logger.error("Error en embedding Ollama: %s", e)
        return []

def get_embed_dims() -> int:
    """Retorna las dimensiones del modelo activo."""
    return EMBED_DIMS

def get_engine_name() -> str:
    """Retorna el nombre del motor activo."""
    return LOCAL_MODEL_NAME if USE_LOCAL_EMBED else OLLAMA_MODEL_NAME

def is_local_embed_enabled() -> bool:
    """Indica si los embeddings se generan dentro de Python."""
    return USE_LOCAL_EMBED
