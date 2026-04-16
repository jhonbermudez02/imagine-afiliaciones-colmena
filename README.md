# Imagine Afiliaciones

Sistema de afiliaciones ARL con:

- frontend web
- backend principal
- base de datos principal
- Qdrant para conocimiento/busqueda
- Ollama para respuestas locales
- backend de compatibilidad para flujo `926`
- base de datos de compatibilidad

## Contenedores del sistema

Al levantar el stack completo se crean estos servicios:

- `imagine_frontend`
- `imagine_backend`
- `imagine_db`
- `imagine_qdrant`
- `imagine_ollama`
- `imagine_compat_backend`
- `imagine_compat_db`

## Requisitos

- Docker Desktop
- En Windows: usar Docker Desktop con backend Linux/WSL2
- Recursos recomendados en Docker Desktop:
  - `CPU: 4`
  - `Memory: 12 GB` o mas
  - `Swap: 4 GB`

## Estructura del repo

- `backend`: backend principal
- `frontend-nova`: frontend operativo
- `compat-backend`: motor de compatibilidad del flujo `926`
- `compat-db/init`: esquema inicial de la base de compatibilidad
- `data/knowledge`: conocimiento operativo
- `docker-compose.github.yml`: compose interno de desarrollo y pruebas
- `docker-compose.deploy.yml`: compose oficial de entrega portable

## Levantar el sistema

1. Clona el repositorio.
2. Copia `.env.example` a `.env` si quieres cambiar credenciales o modelos.
3. Crea la carpeta `shared_downloads` en la raiz del repo si no existe.
4. Desde la raiz del repo ejecuta una de estas dos opciones:

Para desarrollo y pruebas internas:

```bash
docker compose -f docker-compose.github.yml up --build -d
```

Para entrega portable en Linux o Windows con Docker Desktop:

```bash
docker compose -f docker-compose.deploy.yml up --build -d
```

O usa el chequeo automático:

```bash
bash scripts/check_or_start_stack.sh
```

4. Verifica salud:

```bash
curl http://localhost:8000/health
```

Debe responder algo como:

```json
{"api":"healthy","version":"2.0","qdrant":"ok","ollama":"ok","postgres":"ok"}
```

5. Abre la aplicacion:

- frontend: [http://127.0.0.1:8105](http://127.0.0.1:8105)
- backend: [http://localhost:8000](http://localhost:8000)
- compat backend: [http://localhost:8011/health](http://localhost:8011/health)

## Primer arranque

La primera vez tarda mas porque:

- construye imagenes
- inicializa Postgres principal
- inicializa la base de compatibilidad
- instala el modelo/configuracion local de Ollama si aplica

## Datos que no se suben

Este repo esta preparado para no subir:

- expedientes procesados
- volumenes de Qdrant
- volumenes de Ollama
- descargas locales

Los casos procesados quedan en `data/cases/` al correr localmente, pero esa carpeta esta ignorada por Git.

## Comandos utiles

Levantar:

```bash
docker compose -f docker-compose.github.yml up --build -d
```

Verificar y levantar si está caído:

```bash
bash scripts/check_or_start_stack.sh
```

Apagar:

```bash
docker compose -f docker-compose.github.yml down
```

Ver logs:

```bash
docker compose -f docker-compose.github.yml logs -f imagine_backend
docker compose -f docker-compose.github.yml logs -f imagine_compat_backend
```

Prueba rápida de entrega:

```bash
curl http://localhost:8000/health
curl http://localhost:8011/health
curl http://localhost:8105/health
```

Smoke test operativo:

1. abrir el frontend
2. entrar a `Producción`
3. recuperar un contrato
4. reprocesarlo
5. confirmar que la prevalidación termina y que los casos aprobables intentan continuar a `926`

Recrear backend principal:

```bash
docker compose -f docker-compose.github.yml up -d --build imagine_backend
```

## Pipeline de aprendizaje

El proyecto ya puede exportar un banco de aprendizaje a partir de los contratos procesados y las correcciones humanas.

Ejecuta:

```bash
python3 scripts/export_learning_pipeline.py
```

Esto genera:

- `data/evals/learning/case_outcomes.jsonl`
  - verdad operativa por expediente
- `data/evals/learning/document_supervision.jsonl`
  - supervisión para clasificación documental
- `data/evals/learning/search_supervision.jsonl`
  - casos de búsqueda/intents para evaluación y ranking
- `data/evals/learning/flatfile_926_parity.jsonl`
  - inventario de casos con 926 disponible
- `data/evals/learning/document_calibration.json`
  - remapeos aprendidos confirmados para apoyo seguro de clasificación
- `data/evals/learning/search_calibration.json`
  - frases de disparo aprendidas para apoyar detección de intent en búsqueda
- `data/evals/learning/manifest.json`
  - resumen del pipeline exportado

Uso recomendado:

1. recalibrar clasificación documental con `document_supervision.jsonl`
2. usar `document_calibration.json` como capa segura de apoyo sobre errores ya confirmados
3. medir y afinar búsqueda con `search_supervision.jsonl`
4. usar `search_calibration.json` para reforzar detección de intent y grounding
5. usar `case_outcomes.jsonl` como banco patrón oro por expediente
6. usar `flatfile_926_parity.jsonl` para control de paridad contra legacy

Para medir la búsqueda libre contra ese banco:

```bash
python3 scripts/run_search_supervision_eval.py --api-url http://127.0.0.1:8000
```

Eso genera:

- `data/evals/learning/search_eval_report.json`

Úsalo para detectar:

- intents flojos
- expedientes mal seleccionados
- respuestas incoherentes
- queries que todavía caen en la plantilla genérica

## Publicar en GitHub

Si vas a subir este proyecto a `IOhernan/codeforbra`, hazlo desde una copia limpia del repo. Si ese repo local ya tiene otro contenido, no lo sobreescribas a ciegas; crea una rama o una copia nueva antes de reemplazar archivos.

Comandos tipicos:

```bash
git init
git add .
git commit -m "Initial Imagine Afiliaciones import"
git branch -M main
git remote add origin https://github.com/IOhernan/codeforbra.git
git push -u origin main
```
