# 03 - Guia para modificar AFILEGA_FA_IMA_LA_V2

Este documento explica como debe trabajar un desarrollador sobre el sistema sin perder lo que ya funciona en contenedores.

## 1. Regla principal

Antes de modificar:

1. Confirmar que se esta en el repositorio correcto.
2. Confirmar que `main` esta actualizado.
3. Crear una rama de trabajo.
4. Probar localmente con Docker.
5. Hacer commit.
6. Subir la rama o acordar si se actualiza `main`.

Repositorio oficial:

```bash
git clone https://github.com/IOhernan/imagine-afiliaciones.git
cd imagine-afiliaciones
git checkout main
```

La version funcional base es:

```text
eca5d91 Complete AFILEGA local deployment state
```

## 2. Preparar ambiente local

Copiar variables:

```bash
cp .env.example .env
```

Editar `.env` si los puertos del servidor ya estan ocupados.

Levantar:

```bash
docker compose --env-file .env -f docker-compose.deploy.yml up -d --build
```

Verificar:

```bash
docker compose --env-file .env -f docker-compose.deploy.yml ps
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:8011/health
```

Si se usa la configuracion local de esta maquina:

```bash
curl -fsS http://localhost:8140/health
curl -fsS http://localhost:8141/health
```

## 3. Donde modificar cada cosa

### Frontend

Carpeta:

```text
frontend-nova/
```

Archivos principales:

- `frontend-nova/index.html`: estructura visual de pantallas.
- `frontend-nova/main.js`: comportamiento, eventos, validaciones frontend, llamadas API.
- `frontend-nova/styles.css`: estilos.
- `frontend-nova/package.json`: scripts y dependencias.

Cuando modificar aqui:

- Cambios visuales.
- Nuevos campos.
- Reordenar formularios.
- Cambiar labels.
- Agregar validaciones inmediatas de input.
- Ajustar combos.
- Cambiar navegacion del operador.
- Mejorar visor documental o digitacion.

Probar build:

```bash
cd frontend-nova
npm run build
```

Reconstruir contenedor frontend:

```bash
docker compose --env-file .env -f docker-compose.deploy.yml up -d --build imagine_frontend
```

### Backend principal

Carpeta:

```text
backend/
```

Archivos principales:

- `backend/app/main.py`: endpoints principales.
- `backend/app/cases.py`: manejo de expedientes/casos.
- `backend/app/rag.py`: busqueda e indexacion RAG.
- `backend/app/embeddings.py`: embeddings.
- `backend/app/xlsx_rules.py`: reglas de hojas/campos.
- `backend/app/legacy_bridge.py`: puente con motor compatible.
- `backend/app/afilega_legacy_mdb.py`: reglas/campos heredados AFILEGA.

Cuando modificar aqui:

- Nuevos endpoints.
- Validaciones backend.
- Cambios OCR/RAG.
- Reglas de negocio que no deben depender solo del navegador.
- Generacion o comparacion 926.
- Persistencia de casos.

Probar sintaxis:

```bash
python3 -m py_compile backend/app/main.py backend/app/cases.py backend/app/rag.py
```

Reconstruir backend:

```bash
docker compose --env-file .env -f docker-compose.deploy.yml up -d --build imagine_backend
```

### Backend compatible

Carpeta:

```text
compat-backend/
```

Archivos principales:

- `compat-backend/app/api/v1/afiliaciones.py`
- `compat-backend/app/services/nova/orchestrator.py`
- `compat-backend/scripts/bootstrap_nuevo_sistema_afiliaciones.py`

Cuando modificar aqui:

- Cambios del flujo compatible.
- Validaciones o consultas heredadas.
- Reglas especificas usadas por el motor de afiliaciones.
- Soporte a historico 926.

Reconstruir:

```bash
docker compose --env-file .env -f docker-compose.deploy.yml up -d --build imagine_compat_backend
```

### Catalogos

Catalogos frontend:

```text
frontend-nova/digitacion-catalogs.js
frontend-nova/colombia-locations.js
frontend-nova/camara-comercio-catalog.js
frontend-nova/cargo-trabajadores-catalog.js
frontend-nova/tipo-cotizante-trabajadores-catalog.js
frontend-nova/vinculador-laboral-contratante-catalog.js
```

Catalogos backend/evals:

```text
data/evals/activity_risk_catalog.json
data/evals/afilega_mdb_value_catalogs.json
data/evals/camara_comercio_activity_catalog.json
data/evals/cargo_trabajadores_catalog.json
data/evals/tipo_cotizante_trabajadores_catalog.json
data/evals/vinculador_laboral_contratante_catalog.json
data/evals/eps_catalog.json
data/evals/afp_catalog.json
```

Regla:

- Si se cambia un catalogo que usa el frontend, probar busqueda y seleccion en Digitacion.
- Si se cambia un catalogo que usa backend, validar que la regla backend sigue aceptando los codigos.
- Si el catalogo viene de Excel/CSV oficial, conservar fuente y fecha.

### RAG y conocimiento

Carpeta:

```text
data/knowledge/
```

Archivos relevantes:

- `data/knowledge/catalog.json`
- `data/knowledge/afilega-catalogo-documental-operativo.md`
- `data/knowledge/afilega-formatos-oficiales-campos.md`
- `data/knowledge/afilega-mdb-fuente-oficial-validaciones.md`
- `data/knowledge/afilega-paquete-real-afi-alfa-empresa-2026-05-11.md`

Cuando modificar:

- Agregar nuevos criterios documentales.
- Alimentar conocimiento de formatos.
- Documentar nuevas reglas.
- Agregar ejemplos de OCR/documentos.

Reindexar semilla documental:

```bash
docker exec afilega_fa_ima_la_v2-imagine_backend-1 python /app/seed_afilega_document_rag.py
```

Importante:

El RAG ayuda a consultar y clasificar, pero una validacion critica debe implementarse tambien como regla deterministica.

### Documentacion

Carpeta:

```text
docs/
```

Documentos principales:

- `docs/01_QUE_ES_AFILEGA_FA_IMA_LA_V2.md`
- `docs/02_ARQUITECTURA_TECNOLOGICA_AFILEGA.md`
- `docs/03_GUIA_MODIFICACION_AFILEGA.md`
- `docs/VALIDACIONES_AFILIACIONES_AFILEGA.md`
- `docs/ESPECIFICACION_FORMULARIOS_DIGITACION_AFILEGA.md`
- `docs/afilega_digitacion_legacy_matrix.md`

Cada cambio funcional importante debe actualizar la documentacion relacionada.

## 4. Como agregar o modificar un campo de digitacion

Ejemplo de proceso seguro:

1. Ubicar el formulario en `frontend-nova/index.html`.
2. Agregar el input/select con `data-dig-key`.
3. Si es obligatorio, agregar la clave a `DIGITACION_REQUIRED` en `frontend-nova/main.js`.
4. Si requiere validacion, ajustar `validateDigitacionValue` en `frontend-nova/main.js`.
5. Si requiere catalogo, agregar o actualizar catalogo.
6. Si viaja al backend/926, mapearlo en el payload correspondiente.
7. Probar captura, guardado, recarga y validacion.
8. Actualizar `docs/ESPECIFICACION_FORMULARIOS_DIGITACION_AFILEGA.md`.
9. Actualizar `docs/VALIDACIONES_AFILIACIONES_AFILEGA.md` si cambia una regla.

## 5. Como modificar una validacion

Regla:

- Validacion visual inmediata: frontend.
- Validacion bloqueante real: backend o motor compatible.
- Validacion explicativa/documental: RAG como apoyo, no como unica decision.

Pasos:

1. Identificar el campo y la regla exacta.
2. Buscar la clave tecnica del campo en `index.html`.
3. Buscar la validacion actual en `main.js`, `backend/app/*` o `compat-backend/*`.
4. Cambiar la regla en un solo lugar si es posible; si se requiere frontend y backend, mantener mensajes consistentes.
5. Probar caso valido y caso invalido.
6. Documentar la regla.

## 6. Como modificar documentos y OCR

Para ajustar clasificacion documental:

- Revisar tipos documentales en `data/knowledge/afilega-catalogo-documental-operativo.md`.
- Revisar reglas OCR/clasificacion en backend y compat-backend.
- Si se agrega un tipo nuevo, actualizar UI de clasificacion y RAG.

Para reprocesar aprendizaje:

1. Clasificar correctamente documentos.
2. Reindexar o reprocesar fuente si el flujo lo requiere.
3. Validar con un paquete real.

## 7. Pruebas minimas antes de entregar cambios

Siempre ejecutar:

```bash
cd frontend-nova
npm run build
```

Health:

```bash
curl -fsS http://localhost:8140/health
curl -fsS http://localhost:8141/health
```

Flujo manual minimo:

1. Abrir bandeja.
2. Crear nuevo contrato.
3. Cargar documentos.
4. Clasificar documentos.
5. Abrir digitacion.
6. Probar Afiliacion.
7. Probar Sede.
8. Probar Trabajadores.
9. Guardar.
10. Validar reglas.
11. Confirmar que el visor documental funciona.

Pruebas RPA existentes:

```text
scripts/afilega_bandeja_rpa.cjs
scripts/afilega_digitacion_catalogs_rpa.cjs
scripts/afilega_digitacion_evidence_rpa.cjs
```

## 8. Trabajo con Git

Estado:

```bash
git status --short --branch
```

Crear rama:

```bash
git checkout -b fix/nombre-del-ajuste
```

Commit:

```bash
git add .
git commit -m "Describe ajuste AFILEGA"
```

Subir:

```bash
git push upstream fix/nombre-del-ajuste
```

Si se va a tocar `main`, primero confirmar con el responsable del proyecto.

## 9. No perder datos

Antes de cambios grandes:

1. Confirmar que Git esta limpio.
2. Hacer backup de rama actual.
3. Respaldar `data/` si hay historico importante.
4. Respaldar volumenes Docker si se necesita conservar Qdrant o compat DB.

Backup de volumenes:

```bash
mkdir -p backups
docker run --rm -v afilega_fa_ima_la_v2_imagine_qdrant_data:/volume -v "$PWD/backups":/backup alpine tar czf /backup/qdrant.tar.gz -C /volume .
docker run --rm -v afilega_fa_ima_la_v2_imagine_compat_postgres_data:/volume -v "$PWD/backups":/backup alpine tar czf /backup/compat_postgres.tar.gz -C /volume .
```

## 10. Errores comunes

### Cambiar solo el frontend

Si la regla es critica, tambien debe validarse en backend.

### Cambiar catalogo sin actualizar validacion

Puede provocar que el combo muestre valores que luego backend rechaza.

### Subir datos sensibles

No subir `.env` con claves reales ni documentos privados si no estan autorizados.

### Generar nueva pantalla sin revisar flujo real

Antes de crear un modulo nuevo, confirmar si pertenece a Bandeja, Nuevo contrato, Clasificacion, Digitacion, Validacion OCR, Visor o Reporte.

### Romper el estado de contenedores

Si un cambio toca Docker, reconstruir y validar todos los health checks.

## 11. Comandos utiles

Levantar todo:

```bash
docker compose --env-file .env -f docker-compose.deploy.yml up -d --build
```

Ver estado:

```bash
docker compose --env-file .env -f docker-compose.deploy.yml ps
```

Logs backend:

```bash
docker compose --env-file .env -f docker-compose.deploy.yml logs -f imagine_backend
```

Logs compat:

```bash
docker compose --env-file .env -f docker-compose.deploy.yml logs -f imagine_compat_backend
```

Logs frontend:

```bash
docker compose --env-file .env -f docker-compose.deploy.yml logs -f imagine_frontend
```

Apagar sin borrar datos:

```bash
docker compose --env-file .env -f docker-compose.deploy.yml down
```

## 12. Criterio para aceptar un cambio

Un cambio se considera listo si:

- Compila frontend.
- Contenedores levantan.
- Health checks pasan.
- No rompe login.
- No rompe bandeja.
- No rompe digitacion.
- No rompe catalogos.
- No rompe visor documental.
- No rompe validacion de reglas.
- La documentacion queda actualizada.

