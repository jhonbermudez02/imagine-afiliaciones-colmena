# AFILEGA_FA_IMA_LA_V2 local

Proyecto local aislado para pruebas de afiliaciones ARL.

## Puertos

- Frontend: http://localhost:8140
- Backend: http://localhost:8141
- Compat backend: http://localhost:8142
- Qdrant HTTP: http://localhost:8143
- Qdrant gRPC: 8144
- Ollama reservado: 8145

## Arranque local

```bash
docker compose -f docker-compose.deploy.yml up -d --build
```

## Datos sinteticos

```bash
python3 scripts/seed_afilega_synthetic.py
curl -X POST "http://localhost:8142/api/v1/afiliaciones/legacy/db/bootstrap-demo?lote=814001"
curl -X POST "http://localhost:8142/api/v1/afiliaciones/legacy/db/bootstrap-ruta-inclusion-demo"
```

## Catálogo documental AFILEGA

El paquete documental puede cargarse sin XLSX. La matriz oficial de nombres vive en:

- `data/knowledge/afilega-catalogo-documental-operativo.md`
- `backend/seed_afilega_document_rag.py`

Para alimentar el clasificador RAG documental dentro del backend:

```bash
docker exec afilega_fa_ima_la_v2-imagine_backend-1 python /app/seed_afilega_document_rag.py
```
