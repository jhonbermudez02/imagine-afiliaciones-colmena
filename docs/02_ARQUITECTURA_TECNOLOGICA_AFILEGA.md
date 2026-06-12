# 02 - Arquitectura tecnologica AFILEGA_FA_IMA_LA_V2

## Vision general

El sistema esta construido como un stack Docker compuesto por frontend, backend principal, backend compatible, bases de datos, motor vectorial RAG y servicios opcionales de modelo local. La arquitectura esta pensada para que todo viaje junto al repositorio y pueda instalarse en Linux con Docker Compose.

Archivo principal de orquestacion:

```bash
docker-compose.deploy.yml
```

## Componentes principales

### 1. Frontend web

Servicio Docker:

```text
imagine_frontend
```

Carpeta:

```text
frontend-nova/
```

Tecnologia:

- HTML, CSS y JavaScript.
- Vite como herramienta de build.
- Nginx como servidor estatico en produccion.
- Playwright como herramienta de prueba/RPA.

Responsabilidades:

- Login operativo.
- Bandeja de entrada.
- Nuevo contrato.
- Clasificacion documental.
- Digitacion de formularios.
- Visor documental.
- Reportes y acciones operativas.
- Consumo de APIs del backend principal.

Archivos clave:

- `frontend-nova/index.html`
- `frontend-nova/main.js`
- `frontend-nova/styles.css`
- `frontend-nova/package.json`
- `frontend-nova/nginx.conf`
- `frontend-nova/Dockerfile.prod`

Catalogos frontend:

- `frontend-nova/digitacion-catalogs.js`
- `frontend-nova/colombia-locations.js`
- `frontend-nova/camara-comercio-catalog.js`
- `frontend-nova/cargo-trabajadores-catalog.js`
- `frontend-nova/tipo-cotizante-trabajadores-catalog.js`
- `frontend-nova/vinculador-laboral-contratante-catalog.js`
- `frontend-nova/afilega-legacy-mdb.js`
- `frontend-nova/afilega-mdb-value-catalogs.js`

## 2. Backend principal

Servicio Docker:

```text
imagine_backend
```

Carpeta:

```text
backend/
```

Tecnologia:

- Python.
- FastAPI.
- Uvicorn.
- SQLAlchemy / asyncpg / psycopg2.
- Pydantic.
- Qdrant client.
- Sentence Transformers.
- OCR con Tesseract/PyTesseract, PDF/image tooling y librerias de documentos.

Responsabilidades:

- API principal del sistema.
- Carga y gestion de casos.
- Orquestacion de paquetes documentales.
- OCR sobre documentos.
- Indexacion y consulta RAG.
- Validaciones de expediente.
- Comunicacion con backend compatible.
- Generacion/consulta de informacion 926.
- Reportes operativos.
- Persistencia de casos y artefactos bajo `data/`.

Archivos clave:

- `backend/app/main.py`
- `backend/app/cases.py`
- `backend/app/rag.py`
- `backend/app/embeddings.py`
- `backend/app/xlsx_rules.py`
- `backend/app/legacy_bridge.py`
- `backend/app/afilega_legacy_mdb.py`
- `backend/requirements.txt`
- `backend/Dockerfile`

## 3. Backend compatible / motor legacy

Servicio Docker:

```text
imagine_compat_backend
```

Carpeta:

```text
compat-backend/
```

Responsabilidades:

- Mantener compatibilidad con reglas y estructura operativa heredada.
- Gestionar endpoints especificos de afiliaciones.
- Apoyar validaciones y generacion asociada al flujo 926.
- Persistir estado operativo compatible.
- Operar contra la base `imagine_compat_db`.

Archivos clave:

- `compat-backend/app/api/v1/afiliaciones.py`
- `compat-backend/app/services/nova/orchestrator.py`
- `compat-backend/scripts/bootstrap_nuevo_sistema_afiliaciones.py`
- `compat-backend/scripts/consolidate_e2e_reports.py`

## 4. Base de datos principal

Servicio Docker:

```text
imagine_db
```

Tecnologia:

- PostgreSQL 15.

Uso:

- Persistencia principal de afiliaciones, casos y datos operativos del backend principal.

Persistencia:

```text
data/postgres
```

## 5. Base compatible

Servicio Docker:

```text
imagine_compat_db
```

Tecnologia:

- PostgreSQL 15.

Uso:

- Bases compatibles `temporal`, `wimg004` y `ybr`.
- Estado de integracion legacy.
- Reglas/flujo operativo complementario.

Persistencia:

```text
imagine_compat_postgres_data
```

## 6. RAG / base de conocimiento

Servicios y carpetas:

```text
imagine_qdrant
data/knowledge/
backend/app/rag.py
backend/app/embeddings.py
backend/seed_afilega_document_rag.py
```

Tecnologia:

- Qdrant como vector store.
- Sentence Transformers con modelo local `paraphrase-multilingual-MiniLM-L12-v2`.
- Documentos semilla en Markdown/JSON.

Funcion:

El RAG mantiene conocimiento operativo consultable sobre:

- Catalogo documental.
- Formatos oficiales.
- Campos esperados.
- Validaciones.
- Casos reales usados como referencia.
- Aprendizajes sinteticos.
- Reglas y criterios de afiliacion.

Importante:

El RAG ayuda a consultar y contextualizar. No debe ser la unica autoridad para aprobar o rechazar reglas criticas. Las validaciones bloqueantes deben quedar implementadas como reglas deterministicas auditables.

Documentos de conocimiento:

- `data/knowledge/afilega-catalogo-documental-operativo.md`
- `data/knowledge/afilega-formatos-oficiales-campos.md`
- `data/knowledge/afilega-mdb-fuente-oficial-validaciones.md`
- `data/knowledge/afilega-paquete-real-afi-alfa-empresa-2026-05-11.md`
- `data/knowledge/afilega-rpa-completo-digitacion-926-2026-05-11.md`
- `data/knowledge/catalog.json`

Semilla RAG:

```bash
docker exec afilega_fa_ima_la_v2-imagine_backend-1 python /app/seed_afilega_document_rag.py
```

## 7. OCR

El OCR se usa para leer documentos cargados: PDFs, imagenes y paquetes documentales. El backend procesa documentos y extrae texto para:

- Clasificacion documental.
- Comparacion contra campos digitados.
- Evidencia del contrato.
- Alimentacion del RAG por expediente.
- Prellenado asistido cuando el dato es confiable.

Tecnologias:

- PyTesseract.
- Tesseract OCR con idioma espanol.
- Poppler/pdf2image.
- Pillow.
- pypdf.

## 8. Generacion y validacion 926

El sistema conserva reglas y estructura para validar o generar informacion compatible con el archivo 926.

Componentes relacionados:

- `backend/app/legacy_bridge.py`
- `backend/app/afilega_legacy_mdb.py`
- `compat-backend/app/api/v1/afiliaciones.py`
- `data/compat/926_history/`
- `docs/VALIDACIONES_AFILIACIONES_AFILEGA.md`
- `docs/afilega_digitacion_legacy_matrix.md`

El flujo 926 depende de:

- Datos de radicacion.
- Datos de afiliacion.
- Sedes y centros de trabajo.
- Trabajadores.
- Catalogos.
- Validaciones de negocio.

## 9. Persistencia y datos

Carpetas importantes:

```text
data/
shared_downloads/
.env
```

Contenido de `data/`:

- `data/postgres`: base principal.
- `data/compat`: estado compatible y historico 926.
- `data/cases`: expedientes, archivos, OCR y resultados.
- `data/evals`: catalogos y evidencias.
- `data/knowledge`: conocimiento RAG semilla.
- `data/raw`: insumos crudos.

Volumenes Docker:

- `imagine_qdrant_data`: indice vectorial.
- `imagine_compat_postgres_data`: base compatible.
- `imagine_ollama_data`: modelos locales si se activa Ollama.

## 10. Puertos

En `.env.example` los puertos por defecto son:

- Frontend: `8105`
- Backend: `8000`
- Compat backend: `8011`
- Qdrant HTTP: `6333`
- Qdrant gRPC: `6334`
- Ollama: `11434`

En esta maquina local se han usado:

- Frontend: `8140`
- Backend: `8141`
- Compat backend: `8142`
- Qdrant HTTP: `8143`
- Qdrant gRPC: `8144`
- Ollama reservado: `8145`

## 11. Diagrama simple

```text
Usuario
  |
  v
Frontend Vite/Nginx
  |
  v
Backend FastAPI
  |---------------------> Postgres principal
  |---------------------> Qdrant / RAG
  |---------------------> OCR / documentos
  |---------------------> Compat backend
                              |
                              v
                       Compat Postgres
```

## 12. Repositorio oficial

Repositorio:

```text
https://github.com/IOhernan/imagine-afiliaciones.git
```

Rama oficial actual:

```text
main
```

Commit base de esta entrega:

```text
eca5d91 Complete AFILEGA local deployment state
```

Rama de respaldo de la version funcional:

```text
afilega-local-container-state-2026-06-12
```

Rama de respaldo del main anterior:

```text
backup-main-github-2026-06-12
```

