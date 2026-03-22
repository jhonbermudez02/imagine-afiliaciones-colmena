import logging
import json
import uuid
from difflib import get_close_matches
from dataclasses import dataclass
from pathlib import Path
from math import sqrt
from typing import Any, Dict, List, Optional

import httpx
from qdrant_client import QdrantClient, models

from .config import settings

logger = logging.getLogger(__name__)


@dataclass
class KnowledgeChunk:
    source: str
    title: str
    text: str
    metadata: Dict[str, str]


def get_qdrant_client() -> QdrantClient:
    return QdrantClient(url=settings.qdrant_url, timeout=10.0)


def get_state_path() -> Path:
    return Path(settings.qdrant_state_path)


def get_active_collection_name() -> str:
    state_path = get_state_path()
    if state_path.exists():
        value = state_path.read_text(encoding="utf-8").strip()
        if value:
            return value
    return settings.qdrant_collection


def set_active_collection_name(collection_name: str) -> None:
    state_path = get_state_path()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(f"{collection_name}\n", encoding="utf-8")


def collection_exists(collection_name: str) -> bool:
    client = get_qdrant_client()
    collections = client.get_collections().collections
    return any(item.name == collection_name for item in collections)


def list_knowledge_files() -> List[Path]:
    base = Path(settings.knowledge_dir)
    if not base.exists():
        return []
    return sorted(
        path for path in base.rglob("*") if path.is_file() and path.suffix.lower() in {".md", ".txt"}
    )


def load_catalog() -> Dict[str, Dict[str, str]]:
    catalog_path = Path(settings.knowledge_dir) / "catalog.json"
    if not catalog_path.exists():
        return {}
    return json.loads(catalog_path.read_text(encoding="utf-8"))


def chunk_text(text: str) -> List[str]:
    normalized = " ".join(text.split())
    if not normalized:
        return []

    chunks: List[str] = []
    start = 0
    while start < len(normalized):
        end = min(len(normalized), start + settings.chunk_size)
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(normalized):
            break
        start = max(end - settings.chunk_overlap, start + 1)
    return chunks


def load_knowledge_chunks() -> List[KnowledgeChunk]:
    chunks: List[KnowledgeChunk] = []
    catalog = load_catalog()
    for path in list_knowledge_files():
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            continue
        title = path.stem.replace("-", " ").replace("_", " ").title()
        metadata = catalog.get(path.name, {})
        for chunk in chunk_text(text):
            chunks.append(KnowledgeChunk(source=str(path), title=title, text=chunk, metadata=metadata))
    return chunks


async def ollama_embed(text: str) -> List[float]:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.ollama_url}/api/embed",
            json={"model": settings.embedding_model, "input": text},
            timeout=60.0,
        )
        response.raise_for_status()
        payload = response.json()
    embeddings = payload.get("embeddings") or []
    if not embeddings:
        raise ValueError("Ollama no devolvio embeddings")
    return embeddings[0]


async def ollama_embed_many(texts: List[str], model: Optional[str] = None) -> List[List[float]]:
    clean_texts = [str(text or "") for text in texts]
    if not clean_texts:
        return []
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.ollama_url}/api/embed",
            json={"model": model or settings.embedding_model, "input": clean_texts},
            timeout=120.0,
        )
        response.raise_for_status()
        payload = response.json()
    embeddings = payload.get("embeddings") or []
    if not embeddings:
        raise ValueError("Ollama no devolvio embeddings")
    return embeddings


def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = sqrt(sum(a * a for a in vec_a))
    norm_b = sqrt(sum(b * b for b in vec_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


async def ensure_collection(collection_name: str, vector_size: int) -> None:
    client = get_qdrant_client()
    if collection_exists(collection_name):
        client.delete_collection(collection_name)
    client.create_collection(
        collection_name=collection_name,
        vectors_config=models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
    )


async def reindex_knowledge() -> Dict[str, int]:
    chunks = load_knowledge_chunks()
    if not chunks:
        return {"documents": 0, "chunks": 0}

    sample_vector = await ollama_embed(chunks[0].text)
    previous_collection = get_active_collection_name()
    target_collection = f"{settings.qdrant_collection}_rebuild_{uuid.uuid4().hex[:8]}"
    await ensure_collection(target_collection, len(sample_vector))

    client = get_qdrant_client()
    points_batch: List[models.PointStruct] = []
    total_points = 0
    batch_size = 16

    for chunk in chunks:
        vector = await ollama_embed(chunk.text)
        points_batch.append(
            models.PointStruct(
                id=str(uuid.uuid4()),
                vector=vector,
                payload={
                    "source": chunk.source,
                    "title": chunk.title,
                    "text": chunk.text,
                    **chunk.metadata,
                },
            )
        )
        if len(points_batch) >= batch_size:
            client.upsert(collection_name=target_collection, points=points_batch, wait=True)
            total_points += len(points_batch)
            points_batch = []

    if points_batch:
        client.upsert(collection_name=target_collection, points=points_batch, wait=True)
        total_points += len(points_batch)

    set_active_collection_name(target_collection)

    if previous_collection != target_collection and collection_exists(previous_collection):
        try:
            client.delete_collection(previous_collection)
        except Exception as exc:
            logger.warning("No se pudo eliminar la coleccion anterior %s: %s", previous_collection, exc)

    return {
        "documents": len(list_knowledge_files()),
        "chunks": total_points,
    }


def get_collection_stats() -> Dict[str, int]:
    try:
        client = get_qdrant_client()
        collection_name = get_active_collection_name()
        if not collection_exists(collection_name):
            return {"points": 0, "segments": 0}
        info = client.get_collection(collection_name)
        return {
            "points": info.points_count or 0,
            "segments": info.segments_count or 0,
        }
    except Exception:
        return {
            "points": 0,
            "segments": 0,
        }


def build_query_hints(query: str) -> List[str]:
    lowered = query.lower()
    tokens = lowered.replace("?", " ").replace(",", " ").replace(".", " ").split()
    hints: List[str] = []
    mapping = {
        "estandares-minimos": ["estandares minimos", "estandares", "sg-sst"],
        "1072": ["1072", "decreto 1072", "sg-sst"],
        "decreto": ["decreto", "normativa"],
        "flujo-casos-observados": ["observado", "observaciones", "subsanacion", "inconsistencia"],
        "validaciones": ["validaciones", "documental", "ilegible", "vigente"],
        "inscripciones": ["inscripciones", "capacitaciones", "calendario"],
        "e-learning": ["e-learning", "elearning", "formacion virtual", "fiso"],
        "convenios": ["convenios", "universitarios", "gestion del conocimiento"],
        "manual_gestion_escritorio": ["manual", "gestion de escritorio", "escritorio", "instalacion"],
        "gestion-escritorio": ["gestion escritorio", "escritorio", "instalacion", "actualizacion"],
        "pqrs": ["pqrs", "quejas", "reclamos", "sugerencias"],
        "independientes": ["independiente", "independientes"],
        "radicacion": ["radicacion", "solicitud", "tramite"],
        "productos-de-prevencion": ["productos de prevencion", "prevencion"],
        "aportes-y-plazos": ["pila", "recaudo", "aportes", "plazos"],
        "resolucion-2388": ["2388", "resolucion 2388", "pila", "recaudo"],
        "afiliacion-independientes": ["afiliacion", "afiliar", "independiente", "independientes"],
        "documentos-afiliacion": ["documento", "documentos", "soporte", "rut", "cedula"],
    }
    for label, keywords in mapping.items():
        if any(keyword in lowered for keyword in keywords):
            hints.append(label)
            continue
        flattened = [item for keyword in keywords for item in keyword.split()]
        if any(get_close_matches(token, flattened, n=1, cutoff=0.82) for token in tokens):
            hints.append(label)
    return hints


def build_preferred_sources(query: str) -> List[str]:
    lowered = query.lower()
    tokens = lowered.replace("?", " ").replace(",", " ").replace(".", " ").split()
    preferred: List[str] = []
    mapping = {
        "radicacion": [
            "cliente-colmena-tramites.md",
            "cliente-colmena-colmena-tramites-riesgos-laborales.md",
            "cliente-colmena-colmena-radicacion-solicitudes.md",
            "cliente-colmena-arl-paginas-formularios-radicacion-solicitudes-aspx.md",
            "cliente-colmena-colmena-radicacion-incapacidades.md",
        ],
        "res2388": [
            "normativa-resolucion-2388-2016.md",
            "cliente-colmena-resolucion-2388-2016.md",
            "aportes-y-plazos.md",
        ],
        "independientes": [
            "afiliacion-independientes.md",
            "documentos-afiliacion.md",
            "validaciones-documentales.md",
        ],
        "estandares": [
            "colmena-estandares-minimos-operativo.md",
            "cliente-colmena-arl-herramientas-estandares-minimos.md",
        ],
        "decreto1072": [
            "normativa-sgsst-decreto-1072-aplicado.md",
            "normativa-decreto-1072-2015.md",
            "cliente-colmena-decreto-1072-2015.md",
        ],
        "observaciones": [
            "observaciones-subsanacion-operativo.md",
            "flujo-casos-observados.md",
            "validaciones-documentales.md",
        ],
        "capacitaciones": [
            "colmena-capacitaciones-operativo.md",
            "cliente-colmena-inscripciones.md",
            "cliente-colmena-arl-gestion-conocimiento-formar-virtual-paginas-e-learning-fiso-aspx.md",
            "cliente-colmena-arl-gestion-conocimiento-paginas-convenios-universitarios-aspx.md",
        ],
        "manual": [
            "colmena-manual-gestion-escritorio.md",
            "cliente-colmena-imagenescolmenaarp-contenido-arl-manual-gestion-escritorio-v03-web-pdf.md",
        ],
        "pqrs": [
            "colmena-pqrs-operativo.md",
            "cliente-colmena-atencion-al-cliente-pqrs.md",
        ],
    }

    if any(token in lowered for token in ["radicacion", "tramites", "tramite", "solicitudes", "solicitud"]):
        preferred.extend(mapping["radicacion"])
    if any(token in lowered for token in ["2388", "resolucion 2388", "pila", "recaudo"]):
        preferred.extend(mapping["res2388"])
    if any(token in lowered for token in ["independiente", "independientes", "afiliacion", "afiliar", "documentos", "documento"]):
        preferred.extend(mapping["independientes"])
    if any(get_close_matches(token, ["afiliacion", "independientes", "documentos", "validaciones"], n=1, cutoff=0.82) for token in tokens):
        preferred.extend(mapping["independientes"])
    if any(token in lowered for token in ["estandares", "sg-sst"]):
        preferred.extend(mapping["estandares"])
    if any(token in lowered for token in ["1072", "decreto 1072", "sg-sst"]):
        preferred.extend(mapping["decreto1072"])
    if any(token in lowered for token in ["observado", "observaciones", "subsanacion", "inconsistencia"]):
        preferred.extend(mapping["observaciones"])
    if any(token in lowered for token in ["capacitaciones", "capacitacion", "calendario", "e-learning", "formacion"]):
        preferred.extend(mapping["capacitaciones"])
    if any(token in lowered for token in ["manual", "escritorio", "instalacion", "actualizacion"]):
        preferred.extend(mapping["manual"])
    if "pqrs" in lowered:
        preferred.extend(mapping["pqrs"])

    unique: List[str] = []
    for item in preferred:
        if item not in unique:
            unique.append(item)
    return unique


def build_curated_matches(query: str) -> List[Dict[str, object]]:
    preferred_sources = build_preferred_sources(query)
    if not preferred_sources:
        return []

    catalog = load_catalog()
    matches: List[Dict[str, object]] = []
    for path in list_knowledge_files():
        if path.name not in preferred_sources:
            continue
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            continue
        metadata = catalog.get(path.name, {})
        chunks = chunk_text(text)
        snippet = chunks[0] if chunks else text[:900]
        matches.append(
            {
                "titulo": humanize_source_name(path.stem),
                "contenido": snippet,
                "source": str(path),
                "source_url": metadata.get("source_url", ""),
                "topic": metadata.get("topic", ""),
                "document_type": metadata.get("document_type", ""),
                "relevancia": 0.61,
            }
        )
    return matches


def humanize_source_name(value: str) -> str:
    title = value.replace("-", " ").replace("_", " ").title()
    return title.replace("Sgsst", "SG-SST").replace("Pqrs", "PQRS")


def rerank_matches(query: str, matches: List[Dict[str, object]]) -> List[Dict[str, object]]:
    lowered = query.lower()
    hints = build_query_hints(query)
    preferred_sources = build_preferred_sources(query)

    def rerank_score(match: Dict[str, object]) -> float:
        score = float(match.get("relevancia", 0.0))
        title = str(match.get("titulo", "")).lower()
        source = str(match.get("source", "")).lower()
        source_url = str(match.get("source_url", "")).lower()
        doc_type = str(match.get("document_type", "")).lower()
        topic = str(match.get("topic", "")).lower()
        content = str(match.get("contenido", "")).lower()[:800]
        haystack = " ".join([title, source, source_url, doc_type, topic, content])

        for hint in hints:
            if hint in haystack:
                score += 0.22

        for preferred in preferred_sources:
            if preferred.lower() in source:
                score += 0.42

        if doc_type in {"workflow", "checklist", "requisitos", "guia_operativa", "capacitacion", "tramites", "decreto", "resolucion", "informe"}:
            score += 0.08
        if doc_type == "portal":
            score -= 0.08
        if doc_type == "formulario":
            score += 0.08

        if any(token in lowered for token in ["manual", "escritorio"]) and "manual" in haystack:
            score += 0.18
        if any(token in lowered for token in ["radicacion", "tramites", "tramite", "solicitudes"]) and any(token in haystack for token in ["radicacion", "tramites", "solicitudes"]):
            score += 0.24
        if any(token in lowered for token in ["2388", "pila", "recaudo", "resolucion"]) and any(token in haystack for token in ["2388", "resolucion", "pila", "recaudo"]):
            score += 0.24
        if any(token in lowered for token in ["independiente", "independientes", "afiliacion", "documentos", "validaciones"]) and any(token in haystack for token in ["independientes", "afiliacion", "documentos", "validaciones"]):
            score += 0.2
        if any(token in lowered for token in ["capacitaciones", "capacitacion", "e-learning", "formacion"]) and any(token in haystack for token in ["inscripciones", "e-learning", "convenios", "capacitacion"]):
            score += 0.18
        if any(token in lowered for token in ["observado", "subsanacion", "inconsistencia"]) and any(token in haystack for token in ["observaciones", "subsanacion", "workflow"]):
            score += 0.2
        if any(token in lowered for token in ["1072", "decreto", "sg-sst"]) and any(token in haystack for token in ["1072", "decreto", "sg-sst"]):
            score += 0.2
        if "pqrs" in lowered and "pqrs" in haystack:
            score += 0.2
        if any(token in lowered for token in ["estandares", "sg-sst"]) and any(token in haystack for token in ["estandares-minimos", "estandares minimos", "sg-sst"]):
            score += 0.2

        return round(score, 4)

    ranked = []
    for match in matches:
        enriched = dict(match)
        enriched["relevancia"] = rerank_score(match)
        ranked.append(enriched)

    ranked.sort(key=lambda item: float(item.get("relevancia", 0.0)), reverse=True)
    deduped: List[Dict[str, object]] = []
    seen: set[str] = set()
    for item in ranked:
        key = str(item.get("source")) or str(item.get("source_url")) or str(item.get("titulo"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
        if len(deduped) >= settings.search_limit:
            break
    return deduped


async def apply_optional_reranker(query: str, matches: List[Dict[str, object]]) -> List[Dict[str, object]]:
    if not settings.reranker_enabled or not settings.reranker_model:
        return matches
    if len(matches) <= 1:
        return matches
    top_k = max(1, min(settings.reranker_top_k, len(matches)))
    primary = list(matches[:top_k])
    remainder = list(matches[top_k:])
    try:
        query_embedding = await ollama_embed_many([query], model=settings.reranker_model)
        doc_embeddings = await ollama_embed_many(
            [str(item.get("contenido") or item.get("titulo") or "")[:2400] for item in primary],
            model=settings.reranker_model,
        )
        reranked: List[Dict[str, object]] = []
        query_vector = query_embedding[0] if query_embedding else []
        for item, doc_vector in zip(primary, doc_embeddings):
            enriched = dict(item)
            reranker_score = cosine_similarity(query_vector, doc_vector)
            enriched["reranker_score"] = round(reranker_score, 4)
            enriched["relevancia"] = round(float(item.get("relevancia", 0.0)) + max(reranker_score, 0.0) * 0.35, 4)
            reranked.append(enriched)
        reranked.sort(key=lambda item: (float(item.get("relevancia", 0.0)), float(item.get("reranker_score", 0.0))), reverse=True)
        return reranked + remainder
    except Exception as exc:
        logger.warning("No se pudo aplicar el reranker %s: %s", settings.reranker_model, exc)
        return matches


async def search_knowledge(query: str, selected_topics: Optional[List[str]] = None) -> List[Dict[str, object]]:
    stats = get_collection_stats()
    if stats["points"] == 0:
        return []

    filters = build_query_filter(query, selected_topics=selected_topics)
    vector = await ollama_embed(query)
    client = get_qdrant_client()
    collection_name = get_active_collection_name()
    results = client.search(
        collection_name=collection_name,
        query_vector=vector,
        limit=max(settings.search_limit * 3, 12),
        with_payload=True,
        query_filter=filters,
    )

    matches: List[Dict[str, object]] = []
    for result in results:
        payload = result.payload or {}
        matches.append(
            {
                "titulo": humanize_source_name(str(payload.get("title", "Documento"))),
                "contenido": payload.get("text", ""),
                "source": payload.get("source", ""),
                "source_url": payload.get("source_url", ""),
                "topic": payload.get("topic", ""),
                "document_type": payload.get("document_type", ""),
                "relevancia": round(result.score, 4),
            }
        )
    matches.extend(build_curated_matches(query))
    lexical_ranked = rerank_matches(query, matches)
    return await apply_optional_reranker(query, lexical_ranked)


def infer_topics(query: str) -> List[str]:
    lowered = query.lower()
    tokens = lowered.replace("?", " ").replace(",", " ").replace(".", " ").split()
    mappings = {
        "independientes": ["independiente", "independientes", "contratista"],
        "documentos": ["documento", "documentos", "soporte", "rut", "pqrs", "solicitud", "radicacion"],
        "aportes": ["aporte", "aportes", "cotizacion", "pago", "ingreso base"],
        "observaciones": ["observado", "observacion", "rechazo", "inconsistencia", "subsanacion", "subsanar"],
        "checklist": ["checklist", "pasos", "flujo", "procedimiento"],
        "empresas": ["empresa", "empresas", "nit", "camara de comercio", "manual", "escritorio"],
        "validaciones": ["validar", "validacion", "validaciones", "legible", "vigente", "estandares", "capacitaciones", "capacitacion", "sg-sst"],
        "glosario": ["que significa", "definicion", "glosario", "concepto"],
        "normativa": ["norma", "normativa", "decreto", "resolucion", "ley", "pila", "sg-sst", "sistema de gestion"],
    }
    matches: List[str] = []
    for topic, keywords in mappings.items():
        if any(keyword in lowered for keyword in keywords):
            matches.append(topic)
            continue
        flattened = [item for keyword in keywords for item in keyword.split()]
        fuzzy_hits = [token for token in tokens if get_close_matches(token, flattened, n=1, cutoff=0.82)]
        if fuzzy_hits:
            matches.append(topic)
    return matches


def infer_document_types(query: str) -> List[str]:
    lowered = query.lower()
    tokens = lowered.replace("?", " ").replace(",", " ").replace(".", " ").split()
    mappings = {
        "checklist": ["checklist", "lista", "pasos"],
        "workflow": ["flujo", "observado", "observacion", "rechazo"],
        "control": ["validar", "validacion", "control"],
        "requisitos": ["requisito", "documento", "documentos"],
        "guia_operativa": ["afiliar", "afiliacion", "operar"],
        "capacitacion": ["capacitacion", "capacitaciones", "curso", "evento", "formacion"],
        "informe": ["manual", "instructivo", "instalacion", "escritorio"],
        "tramites": ["pqrs", "radicacion", "solicitud", "tramite"],
        "referencia": ["glosario", "definicion", "concepto"],
        "reglas": ["regla", "plazo", "plazos", "aporte"],
        "norma_marco": ["ley", "marco", "norma"],
        "decreto": ["decreto"],
        "resolucion": ["resolucion", "pila"],
    }
    matches: List[str] = []
    for doc_type, keywords in mappings.items():
        if any(keyword in lowered for keyword in keywords):
            matches.append(doc_type)
            continue
        fuzzy_hits = [token for token in tokens if get_close_matches(token, keywords, n=1, cutoff=0.82)]
        if fuzzy_hits:
            matches.append(doc_type)
    return matches


def build_query_filter(query: str, selected_topics: Optional[List[str]] = None) -> Optional[models.Filter]:
    if selected_topics:
        normalized_topics = [topic for topic in selected_topics if topic and topic != "all"]
        if normalized_topics:
            return models.Filter(
                should=[
                    models.FieldCondition(
                        key="topic",
                        match=models.MatchValue(value=topic),
                    )
                    for topic in normalized_topics
                ]
            )

    topics = infer_topics(query)
    document_types = infer_document_types(query)
    should: List[models.FieldCondition] = []

    for topic in topics:
        should.append(
            models.FieldCondition(
                key="topic",
                match=models.MatchValue(value=topic),
            )
        )

    for document_type in document_types:
        should.append(
            models.FieldCondition(
                key="document_type",
                match=models.MatchValue(value=document_type),
            )
        )

    if not should:
        return None

    return models.Filter(should=should)


def infer_response_mode(query: str, sources: List[Dict[str, object]]) -> str:
    lowered = query.lower()
    topics = {source.get("topic", "") for source in sources}
    doc_types = {source.get("document_type", "") for source in sources}

    if "pqrs" in lowered:
        return "pqrs"
    if any(token in lowered for token in ["productos de prevencion", "prevencion"]) and "arl" in lowered:
        return "prevention"
    if any(token in lowered for token in ["accidente", "accidentes", "asistencia en salud"]):
        return "accident"
    if any(token in lowered for token in ["capacitacion", "capacitaciones", "calendario", "eventos", "e-learning", "formacion"]):
        return "training"
    if any(token in lowered for token in ["manual", "instalar", "instalacion", "actualizar", "escritorio"]):
        return "manual"
    if "checklist" in lowered or "checklist" in topics or "checklist" in doc_types:
        return "checklist"
    if "observaciones" in topics or "workflow" in doc_types or "observado" in lowered:
        return "remediation"
    if "empresas" in topics:
        return "business"
    if "documentos" in topics or "requisitos" in doc_types:
        return "requirements"
    if "normativa" in topics:
        return "normative"
    return "general"


def build_tone_instruction(response_mode: str) -> str:
    tones = {
        "checklist": "Responde como checklist operativo numerado, breve y ejecutivo.",
        "remediation": "Responde como guia de correccion ejecutiva, separando validaciones y siguiente paso.",
        "business": "Responde como orientacion ejecutiva para empresas, separando documentos y validaciones.",
        "requirements": "Responde como lista ejecutiva de requisitos y soportes. No pegues texto crudo de fuentes.",
        "normative": "Responde con tono tecnico y ejecutivo, aclarando que es una sintesis operativa de soporte normativo.",
        "general": "Responde con un resumen ejecutivo, accionable y breve.",
    }
    return tones.get(response_mode, tones["general"])


def build_response_header(query: str, response_mode: str) -> str:
    lowered = query.lower()
    if response_mode == "pqrs":
        return "Canal PQRS Colmena"
    if response_mode == "prevention":
        return "Productos de prevencion ARL"
    if response_mode == "accident":
        return "Atencion de accidentes de trabajo"
    if response_mode == "training":
        return "Capacitaciones y eventos"
    if response_mode == "manual":
        return "Manual de gestion de escritorio"
    if any(token in lowered for token in ["independiente", "independientes", "afiliacion", "afiliar"]):
        return "Afiliacion de independientes"
    if any(token in lowered for token in ["pila", "recaudo", "2388", "resolucion"]):
        return "Soporte normativo de PILA y recaudo"
    if any(token in lowered for token in ["radicacion", "tramites", "solicitudes", "canales"]):
        return "Tramites y canales de radicacion"
    if any(token in lowered for token in ["observado", "subsanacion", "inconsistencia"]):
        return "Ruta de subsanacion"
    if any(token in lowered for token in ["sg-sst", "sgsst", "1072", "estandares"]):
        return "Orientacion SG-SST"
    if response_mode == "normative":
        return "Soporte normativo"
    return "Respuesta ejecutiva"


def source_priority(source: Dict[str, object]) -> tuple[int, float]:
    doc_type = str(source.get("document_type", ""))
    topic = str(source.get("topic", ""))
    score = float(source.get("relevancia", 0.0))
    penalties = {
        "portal": 4,
        "documento": 3,
    }
    boosts = {
        "checklist": -3,
        "requisitos": -3,
        "workflow": -3,
        "guia_operativa": -2,
        "reglas": -2,
        "control": -2,
        "capacitacion": -1,
        "tramites": -1,
        "decreto": -2,
        "resolucion": -2,
        "norma_marco": -2,
    }
    base = penalties.get(doc_type, 0) + boosts.get(doc_type, 0)
    if topic in {"observaciones", "validaciones", "normativa", "documentos", "independientes"}:
        base -= 1
    return (base, -score)


def rank_sources_for_answer(sources: List[Dict[str, object]]) -> List[Dict[str, object]]:
    return sorted(sources, key=source_priority)


def extract_candidate_points(text: str) -> List[str]:
    prepared = text.replace(" - ", "\n- ").replace(". - ", ".\n- ")
    lines = [line.strip(" -") for line in prepared.splitlines()]
    candidates: List[str] = []
    for line in lines:
        normalized = " ".join(line.split()).strip()
        if len(normalized) < 8:
            continue
        if normalized.startswith("#"):
            continue
        if any(noisy in normalized.lower() for noisy in ["saltar al contenido principal", "please enter", "impresión de escarapelas", "currently selected", "actualmente seleccionado"]):
            continue
        if normalized.lower().startswith(("fuente:", "hallazgos clave:", "checklist sugerido:", "ruta recomendada:")):
            continue
        normalized = normalized.removeprefix("Reglas operativas: ").removeprefix("Controles sugeridos: ")
        normalized = normalized.removeprefix("Para afiliar a un trabajador independiente se requiere, como base operativa: ")
        normalized = normalized.replace("•", "").strip()
        if "  " in normalized:
            normalized = " ".join(normalized.split())
        words = normalized.split()
        half = len(words) // 2
        if half and words[:half] == words[half:half * 2]:
            normalized = " ".join(words[:half])
        candidates.append(normalized)
    if not candidates:
        normalized_text = " ".join(text.split())
        candidates = [chunk.strip() for chunk in normalized_text.split(". ") if len(chunk.strip()) > 12]
    return candidates


def collect_executive_points(sources: List[Dict[str, object]]) -> Dict[str, List[str]]:
    buckets = {"documents": [], "validations": [], "actions": []}
    seen: set[str] = set()
    doc_words = ("cedula", "rut", "certificado", "contrato", "formulario", "soporte", "documento")
    validation_words = ("validar", "verificar", "vigente", "legible", "consistencia", "control", "brecha")
    action_words = ("solicitar", "registrar", "dirigir", "usar", "revisar", "seguir", "indicar")

    for source in rank_sources_for_answer(sources)[:4]:
        for point in extract_candidate_points(str(source.get("contenido", ""))):
            key = point.lower()
            if key in seen:
                continue
            seen.add(key)
            if any(word in key for word in doc_words):
                buckets["documents"].append(point)
            elif any(word in key for word in validation_words):
                buckets["validations"].append(point)
            elif any(word in key for word in action_words):
                buckets["actions"].append(point)
            else:
                buckets["actions"].append(point)
    return {name: values[:4] for name, values in buckets.items()}


def collect_named_references(sources: List[Dict[str, object]]) -> List[str]:
    references: List[str] = []
    seen: set[str] = set()
    for source in sources[:5]:
        title = str(source.get("titulo", ""))
        lowered = title.lower()
        if "2388" in lowered:
            label = "Resolucion 2388 de 2016"
        elif "1072" in lowered:
            label = "Decreto 1072 de 2015"
        elif "ley 100" in lowered or "100 1993" in lowered:
            label = "Ley 100 de 1993"
        else:
            label = title
        if label and label not in seen:
            seen.add(label)
            references.append(label)
    return references


def find_source_by_keywords(sources: List[Dict[str, object]], keywords: List[str]) -> Optional[Dict[str, object]]:
    for source in sources:
        haystack = " ".join(
            [
                str(source.get("titulo", "")),
                str(source.get("source", "")),
                str(source.get("source_url", "")),
                str(source.get("document_type", "")),
                str(source.get("topic", "")),
                str(source.get("contenido", ""))[:300],
            ]
        ).lower()
        if all(keyword in haystack for keyword in keywords):
            return source
    for source in sources:
        haystack = " ".join(
            [
                str(source.get("titulo", "")),
                str(source.get("source", "")),
                str(source.get("source_url", "")),
            ]
        ).lower()
        if any(keyword in haystack for keyword in keywords):
            return source
    return None


def summarize_query_context(query: str, sources: List[Dict[str, object]]) -> Dict[str, Any]:
    response_mode = infer_response_mode(query, sources)
    ranked_sources = rank_sources_for_answer(sources)
    points = collect_executive_points(ranked_sources)
    references = collect_named_references(ranked_sources)
    return {
        "response_mode": response_mode,
        "header": build_response_header(query, response_mode),
        "ranked_sources": ranked_sources,
        "points": points,
        "references": references,
    }


def infer_operational_decision(query: str, sources: List[Dict[str, object]]) -> Dict[str, Any]:
    if not sources:
        return {
            "flow": "sin_contexto",
            "classification": "sin_contexto",
            "recommended_status": "pendiente_de_contexto",
            "summary": "No hay base documental suficiente para decidir el flujo.",
            "required_documents": [],
            "critical_validations": [],
            "blockers": ["Falta contexto indexado para emitir una decision operativa."],
            "next_step": "Reindexar el corpus o agregar documentos del flujo correspondiente.",
            "recommended_channel": "n/a",
        }

    context = summarize_query_context(query, sources)
    response_mode = context["response_mode"]
    points = context["points"]
    ranked_sources = context["ranked_sources"]
    references = context["references"]
    lowered = query.lower()

    decision = {
        "flow": "orientacion_general",
        "classification": response_mode,
        "recommended_status": "orientar",
        "summary": "NOVA encontro contexto suficiente para orientar el caso.",
        "required_documents": points["documents"][:3],
        "critical_validations": points["validations"][:3],
        "blockers": [],
        "next_step": points["actions"][0] if points["actions"] else "Usar la fuente principal como referencia operativa inmediata.",
        "recommended_channel": "consulta_documental",
        "references": references[:3],
    }

    if response_mode == "requirements":
        decision.update(
            {
                "flow": "afiliacion_independientes",
                "classification": "recoleccion_documental",
                "recommended_status": "pendiente_documentos",
                "summary": "El caso requiere recopilar soportes y validar consistencia antes de radicar.",
                "next_step": "Consolidar soportes del afiliado, validar consistencia documental y radicar el caso cuando el expediente este completo.",
                "recommended_channel": "radicacion_afiliacion",
            }
        )
    elif response_mode == "remediation":
        blockers = [
            "Documento ilegible o inconsistente frente al expediente."
            if any(token in lowered for token in ["ilegible", "inconsistente", "inconsistencia"])
            else "El expediente presenta observaciones que requieren subsanacion."
        ]
        decision.update(
            {
                "flow": "subsanacion_documental",
                "classification": "observado",
                "recommended_status": "observado",
                "summary": "El caso debe mantenerse observado hasta corregir el soporte o completar la evidencia.",
                "blockers": blockers,
                "next_step": "Solicitar subsanacion documental y dejar el caso en espera del soporte corregido.",
                "recommended_channel": "subsanacion_operativa",
            }
        )
    elif response_mode == "accident":
        decision.update(
            {
                "flow": "accidente_de_trabajo",
                "classification": "atencion_inmediata",
                "recommended_status": "escalar_inmediato",
                "summary": "El caso debe escalarse por el canal ARL de accidentes de trabajo.",
                "required_documents": ["Reporte inicial del evento.", "Soportes del accidente cuando existan."],
                "critical_validations": ["Confirmar que el evento corresponde a accidente de trabajo.", "Activar la ruta ARL de asistencia en salud."],
                "next_step": "Usar el canal de atencion de accidentes de trabajo y registrar el reporte con los soportes del evento.",
                "recommended_channel": "atencion_accidentes_colmena",
            }
        )
    elif response_mode == "training":
        decision.update(
            {
                "flow": "capacitaciones_colmena",
                "classification": "orientacion_a_canal",
                "recommended_status": "derivar_a_capacitaciones",
                "summary": "El caso debe dirigirse al calendario o canal de inscripciones y e-learning de Colmena.",
                "next_step": "Validar el evento requerido y dirigir al usuario al calendario o canal de inscripciones de Colmena.",
                "recommended_channel": "inscripciones_y_formacion_virtual",
            }
        )
    elif response_mode == "manual":
        decision.update(
            {
                "flow": "gestion_de_escritorio",
                "classification": "soporte_operativo",
                "recommended_status": "ejecutar_manual",
                "summary": "El caso debe resolverse con el manual vigente de gestion de escritorio.",
                "required_documents": ["Manual vigente de gestion de escritorio."],
                "critical_validations": ["Confirmar si el caso es instalacion, configuracion o actualizacion."],
                "next_step": "Tomar el manual vigente y ejecutar instalacion o actualizacion segun el escenario del equipo.",
                "recommended_channel": "soporte_local",
            }
        )
    elif response_mode == "pqrs":
        decision.update(
            {
                "flow": "pqrs_colmena",
                "classification": "radicacion_externa",
                "recommended_status": "radicar_pqrs",
                "summary": "El caso debe radicarse por el canal oficial de PQRS de Colmena.",
                "required_documents": ["Detalle de la solicitud.", "Soportes del caso, si aplican."],
                "critical_validations": ["Confirmar que la solicitud corresponda a peticion, queja, reclamo o sugerencia."],
                "next_step": "Dirigir al canal PQRS de Colmena y validar que la solicitud quede radicada con sus soportes.",
                "recommended_channel": "pqrs_colmena",
            }
        )
    elif response_mode == "prevention":
        decision.update(
            {
                "flow": "productos_prevencion",
                "classification": "orientacion_comercial_operativa",
                "recommended_status": "orientar_portafolio",
                "summary": "El caso debe orientarse al portafolio de productos de prevencion ARL de Colmena.",
                "critical_validations": ["Identificar el producto o necesidad preventiva de la empresa."],
                "next_step": "Validar el producto de prevencion requerido y dirigir a la ruta ARL de Colmena para su gestion.",
                "recommended_channel": "portafolio_prevencion_arl",
            }
        )
    elif response_mode == "normative":
        decision.update(
            {
                "flow": "consulta_normativa",
                "classification": "soporte_normativo",
                "recommended_status": "emitir_soporte",
                "summary": "El caso cuenta con soporte normativo suficiente para orientar la decision operativa.",
                "required_documents": references[:3],
                "recommended_channel": "base_normativa_local",
            }
        )

    return decision


async def generate_grounded_answer(query: str, sources: List[Dict[str, object]]) -> str:
    if not sources:
        return (
            "No encontre contexto indexado suficiente para responder con base documental. "
            "Reindexa el corpus o agrega mas documentos a data/knowledge."
        )

    context = summarize_query_context(query, sources)
    response_mode = context["response_mode"]
    ranked_sources = context["ranked_sources"]
    fallback_answer = build_fallback_answer(query, ranked_sources, response_mode)
    return fallback_answer


def build_fallback_answer(query: str, sources: List[Dict[str, object]], response_mode: str) -> str:
    points = collect_executive_points(sources)
    references = collect_named_references(sources)
    header = build_response_header(query, response_mode)

    if response_mode == "pqrs":
        lines = [f"{header}:", "", "Canal disponible:"]
        lines.append("- Colmena dispone de un canal PQRS para peticiones, quejas, reclamos y sugerencias.")
        lines.append("- El usuario debe usar el canal oficial de Colmena y adjuntar la informacion del caso.")
        lines.extend(["", "Siguiente paso:"])
        lines.append("- Dirigir al canal PQRS de Colmena y validar que la solicitud quede radicada con sus soportes.")
        return "\n".join(lines)

    if response_mode == "prevention":
        lines = [f"{header}:", "", "Oferta principal:"]
        lines.append("- Colmena ARL ofrece productos de prevencion para empresas afiliadas dentro de su linea de riesgos laborales.")
        lines.append("- La orientacion debe darse por el portafolio de prevencion y acompanamiento ARL para empresa.")
        lines.extend(["", "Siguiente paso:"])
        lines.append("- Validar el producto de prevencion requerido y dirigir a la ruta ARL de Colmena para su gestion.")
        return "\n".join(lines)

    if response_mode == "accident":
        lines = [f"{header}:", "", "Cobertura y orientacion:"]
        lines.append("- Colmena ARL orienta la atencion inicial de accidentes de trabajo desde su ruta de asistencia en salud.")
        lines.append("- El caso debe tratarse como evento laboral y canalizarse por la ruta ARL definida por Colmena.")
        lines.extend(["", "Siguiente paso:"])
        lines.append("- Usar el canal de atencion de accidentes de trabajo y registrar el reporte con los soportes del evento.")
        return "\n".join(lines)

    if response_mode == "training":
        lines = [f"{header}:", "", "Canales disponibles:"]
        lines.append("- Colmena publica rutas de capacitaciones, eventos, formacion virtual y e-learning para sus empresas afiliadas.")
        lines.append("- El calendario operativo se consulta por los canales de inscripciones, formacion virtual y e-learning del portal.")
        lines.extend(["", "Siguiente paso:"])
        lines.append("- Validar el evento requerido y dirigir al usuario al calendario o canal de inscripciones de Colmena.")
        return "\n".join(lines)

    if response_mode == "manual":
        lines = [f"{header}:", "", "Uso operativo:"]
        lines.append("- El manual aplica para la gestion operativa ARL de instalar, actualizar o mantener la herramienta de escritorio.")
        lines.append("- Debe usarse como referencia operativa de instalacion, configuracion y actualizacion del componente local.")
        lines.extend(["", "Siguiente paso:"])
        lines.append("- Tomar el manual vigente y ejecutar instalacion o actualizacion segun el escenario del equipo.")
        return "\n".join(lines)

    if response_mode == "checklist":
        checklist = points["documents"] + points["validations"] + points["actions"]
        lines = [f"{header}:", "", "Checklist ejecutivo:"]
        for index, point in enumerate(checklist[:5], start=1):
            lines.append(f"{index}. {point}")
        return "\n".join(lines)

    if response_mode == "remediation":
        lines = [f"{header}:", "", "Validaciones clave:"]
        remediation_points = points["validations"][:]
        if any(token in query.lower() for token in ["ilegible", "inconsistente", "documento"]):
            remediation_points = [
                "Validar si el documento esta ilegible, vencido o inconsistente frente al expediente.",
                "Enumerar la inconsistencia puntual.",
                "Confirmar si el soporte debe reemplazarse o complementarse.",
            ]
        for point in remediation_points[:3]:
            lines.append(f"- {point}")
        lines.append("")
        lines.append("Siguiente paso:")
        next_step = points["actions"][0] if points["actions"] else "Solicitar subsanacion documental y dejar el caso en espera del soporte corregido."
        lines.append(f"- {next_step}")
        return "\n".join(lines)

    if response_mode == "normative":
        lines = [f"{header}:", "", "Referencias principales:"]
        for reference in references[:4]:
            lines.append(f"- {reference}")
        if not references:
            for source in sources[:4]:
                doc_type = source.get("document_type", "norma")
                lines.append(f"- {source.get('titulo', 'Documento')} [{doc_type}]")
        if points["actions"]:
            action = points["actions"][0]
            if any(token in query.lower() for token in ["pila", "recaudo", "2388"]):
                action = "Aplicar la Resolucion 2388 de 2016 como base de PILA y usar las reglas operativas de aportes y plazos."
            if any(token in query.lower() for token in ["brecha", "plan de accion", "estandares"]):
                action = "Usar el diagnostico de estandares minimos para identificar brechas y definir plan de accion."
            lines.extend(["", "Aplicacion operativa:", f"- {action}"])
        return "\n".join(lines)

    if response_mode == "requirements":
        lines = [f"{header}:", "", "Documentos requeridos:"]
        for point in points["documents"][:4]:
            lines.append(f"- {point}")
        if not points["documents"]:
            lines.append("- Revisar soportes base del afiliado y formulario del flujo.")
        lines.extend(["", "Validaciones clave:"])
        for point in points["validations"][:3]:
            lines.append(f"- {point}")
        if not points["validations"]:
            lines.append("- Validar legibilidad, vigencia y consistencia de los soportes.")
        lines.extend(["", "Siguiente paso:"])
        lines.append(f"- {(points['actions'][0] if points['actions'] else 'Confirmar expediente completo antes de activar el caso.')}")
        return "\n".join(lines)

    lines = [f"{header}:", "", "Puntos clave:"]
    for point in (points["documents"] + points["validations"] + points["actions"])[:5]:
        lines.append(f"- {point}")
    if len(lines) == 3:
        lines.append(f"- {sources[0].get('titulo', 'Documento base')}")
    lines.extend(["", "Siguiente paso:", f"- {(points['actions'][0] if points['actions'] else 'Usar la fuente principal como referencia operativa inmediata.')}"])
    return "\n".join(lines)
