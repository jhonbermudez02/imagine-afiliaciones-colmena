# NOVA Offline

Este proyecto queda dividido en dos fases:

## 1. Fase de Alimentacion

Con internet disponible:

1. Levanta Docker:
   `docker compose up -d`
2. Instala dependencias del backend si trabajas fuera del contenedor.
3. Captura portales y normativa:
   `python3 scripts/feed_sources.py`
   Si no quieres instalar dependencias locales:
   `bash scripts/feed_sources_docker.sh`
4. Descubre URLs publicas adicionales de Colmena:
   `python3 scripts/discover_public_sources.py`
   Si no quieres depender de tu entorno local:
   `bash scripts/discover_public_sources_docker.sh`
5. Promueve automaticamente las URLs descubiertas al registro oficial:
   `python3 scripts/promote_discovered_sources.py`
6. Captura tambien imagenes, TIFF y PDFs escaneados con OCR usando el mismo feeder:
   `bash scripts/feed_sources_docker.sh`
   El resultado operativo queda en `data/feed_report.json`.
7. Reindexa:
   `curl -X POST http://127.0.0.1:8000/api/system/reindex`
8. Ejecuta evaluacion formal del RAG:
   `python3 scripts/run_eval.py`
9. Exporta bundle:
   `python3 scripts/export_offline_bundle.py`

## 2. Fase de Consulta

Sin internet:

1. Lleva la carpeta `offline_bundle/`.
2. Inicia con:
   `docker compose up -d`
3. NOVA respondera contra Qdrant y Ollama locales.

## Estructura relevante

- `data/source_registry.json`: fuentes web a capturar
- `data/source_registry_discovered.json`: fuentes publicas encontradas automaticamente
- `data/feed_report.json`: reporte de ingestiones, OCR y errores
- `data/evals/`: banco de casos y ultimo reporte de evaluacion
- `data/raw/`: snapshots originales HTML/PDF
- `data/knowledge/`: corpus listo para indexar
- `offline_bundle/`: paquete transportable para el cliente
