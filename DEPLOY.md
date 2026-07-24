# Despliegue Docker Linux

Este proyecto se entrega como un stack Docker portable llamado `AFILEGA_FA_IMA_LA_V2`. La forma oficial de montaje es copiar la carpeta del proyecto a un servidor Linux y levantarla con Docker Compose.

No debe depender de instalaciones manuales de Python, Node, Postgres, Qdrant, OCR ni frontend en el servidor. Todo eso queda dentro de contenedores.

## Stack oficial

- `docker-compose.deploy.yml`

Este compose deja aislados los servicios del sistema:

- `imagine_frontend`
- `imagine_backend`
- `imagine_compat_backend`
- `imagine_db`
- `imagine_compat_db`
- `imagine_qdrant`

## Compatibilidad

Funciona en:

- Linux con Docker Engine + Docker Compose
- Windows con Docker Desktop usando contenedores Linux

No está pensado para contenedores Windows nativos.

## Principio de despliegue

El stack debe poder levantarse por sí mismo.

Eso significa:

- sin rutas absolutas de Mac
- sin depender del entorno personal del desarrollador
- sin depender por defecto de un endpoint LLM externo

Si luego se quiere conectar un proveedor OpenAI-compatible adicional para el `compat-backend`, se hace por variables de entorno, pero no es requisito para el arranque base.

## Preparación

1. Copiar el proyecto completo al servidor o estación destino.
2. Copiar `.env.example` a `.env`.
3. Crear la carpeta `shared_downloads` en la raíz del proyecto si aún no existe.
3. Ajustar únicamente las variables necesarias en `.env`:

- credenciales de Postgres
- puertos si hay conflicto
- SMTP si se usarán correos reales
- parámetros del LLM del `compat-backend` si se desea usar proveedor externo

## Arranque

```bash
docker-compose.deploy.yml
```

Servicios incluidos:

- `imagine_frontend`: interfaz web.
- `imagine_backend`: API principal, OCR, RAG, validaciones y expediente.
- `imagine_compat_backend`: motor compatible con reglas legacy.
- `imagine_db`: Postgres principal.
- `imagine_compat_db`: Postgres del backend compatible.
- `imagine_qdrant`: vector store del RAG.
- `imagine_ollama`: opcional, solo si se levanta con perfil `ollama`.

## Requisitos del servidor Linux

- Docker Engine 24 o superior.
- Docker Compose plugin, comando `docker compose`.
- CPU recomendado: 4 cores o mas.
- RAM recomendada: 8 GB o mas.
- Disco recomendado: 20 GB libres como base, mas el crecimiento de paquetes/documentos.
- Acceso a internet para el primer `build` y descarga de imagenes, salvo que se entregue un bundle offline de imagenes.

## Preparacion inicial

Desde la raiz del proyecto:

```bash
cp .env.example .env
```

Editar `.env` si el servidor requiere otros puertos, credenciales o SMTP.

Puertos por defecto:

- Frontend: `8105`
- Backend principal: `8000`
- Compat backend: `8011`
- Qdrant HTTP: `6333`
- Qdrant gRPC: `6334`
- Ollama: `11434`

En la maquina local de desarrollo se pueden usar otros puertos en `.env`, como `8140`, `8141`, `8142`, `8143` y `8144`.

## Arranque recomendado

```bash
chmod +x scripts/deploy_portable.sh
./scripts/deploy_portable.sh
```

El script:

- valida que Docker y Docker Compose existan;
- crea `.env` desde `.env.example` si no existe;
- crea carpetas persistentes bajo `data/`;
- levanta todos los servicios con `docker-compose.deploy.yml`;
- muestra estado y endpoints de salud.

Arranque manual equivalente:

```bash
docker compose --env-file .env -f docker-compose.deploy.yml up -d --build
```

## Verificacion

Estado de contenedores:

```bash
docker compose --env-file .env -f docker-compose.deploy.yml ps
```

Health backend:

```bash
curl -fsS http://localhost:8000/health
```

Health compat:

```bash
curl -fsS http://localhost:8011/health
```

UI:

```text
http://localhost:8105
```

Si `.env` usa otros puertos, validar con esos valores.

## Operacion

Logs:

```bash
docker compose --env-file .env -f docker-compose.deploy.yml logs -f imagine_backend
docker compose --env-file .env -f docker-compose.deploy.yml logs -f imagine_compat_backend
docker compose --env-file .env -f docker-compose.deploy.yml logs -f imagine_frontend
```

Recrear un servicio:

```bash
docker compose --env-file .env -f docker-compose.deploy.yml up -d --build imagine_backend
docker compose --env-file .env -f docker-compose.deploy.yml up -d --build imagine_frontend
```

Apagar sin borrar datos:

```bash
docker compose --env-file .env -f docker-compose.deploy.yml down
```

Apagar y borrar contenedores, redes y volumenes anonimos, conservando carpetas del proyecto:

```bash
docker compose --env-file .env -f docker-compose.deploy.yml down --remove-orphans
```

## Persistencia

La informacion operativa que debe viajar con el proyecto vive principalmente en:

- `imagine_postgres_data`
- `imagine_compat_postgres_data`
- `imagine_qdrant_data`

Dentro de `data/` se conservan:

- `data/postgres`: base principal de afiliaciones.
- `data/compat`: estado operativo del motor legacy compatible e historico 926.
- `data/cases`: paquetes, expedientes, OCR y resultados.
- `data/evals`: catalogos, evidencias y aprendizaje operacional.
- `data/knowledge`: conocimiento/RAG semilla.
- `data/raw`: insumos crudos cuando aplique.

El compose tambien usa volumenes Docker para servicios auxiliares:

- `imagine_compat_postgres_data`: base compatible legacy.
- `imagine_qdrant_data`: indice vectorial Qdrant.
- `imagine_ollama_data`: modelos locales si se usa Ollama.

El backend compatible monta `./data:/data`, por eso estos valores quedan preparados para Linux:

```text
AFILIACIONES_ENGINE_STATE_PATH=/data/compat/afiliaciones_engine_state.json
AFILIACIONES_926_HISTORY_DIR=/data/compat/926_history
AFILIACIONES_ORACLE_FLATFILE=/data/raw/BkCargue_reference.txt
```

Para mover historico completo a otro Linux, se deben copiar la carpeta del proyecto y respaldar/restaurar esos volumenes Docker. Si solo se copia el codigo sin datos, el sistema levanta limpio, pero sin historico ni aprendizaje acumulado en volumenes.

## Respaldo de volumenes Docker

Ejemplo para exportar volumenes desde el servidor origen:

```bash
docker run --rm -v afilega_fa_ima_la_v2_imagine_qdrant_data:/volume -v "$PWD/backups":/backup alpine tar czf /backup/qdrant.tar.gz -C /volume .
docker run --rm -v afilega_fa_ima_la_v2_imagine_compat_postgres_data:/volume -v "$PWD/backups":/backup alpine tar czf /backup/compat_postgres.tar.gz -C /volume .
```

Ejemplo para restaurar en el servidor destino, despues de crear los volumenes con un primer `docker compose up -d`:

```bash
docker compose --env-file .env -f docker-compose.deploy.yml down
docker run --rm -v afilega_fa_ima_la_v2_imagine_qdrant_data:/volume -v "$PWD/backups":/backup alpine sh -c "rm -rf /volume/* && tar xzf /backup/qdrant.tar.gz -C /volume"
docker run --rm -v afilega_fa_ima_la_v2_imagine_compat_postgres_data:/volume -v "$PWD/backups":/backup alpine sh -c "rm -rf /volume/* && tar xzf /backup/compat_postgres.tar.gz -C /volume"
docker compose --env-file .env -f docker-compose.deploy.yml up -d
```

El prefijo real del volumen puede cambiar si se modifica el nombre de la carpeta/proyecto. Confirmar con:

```bash
docker volume ls | grep imagine
```

## Prueba minima de entrega

Despues de levantar en Linux:

1. Abrir la UI.
2. Crear un nuevo contrato.
3. Cargar un PDF multipagina.
4. Ejecutar validacion documental + OCR.
5. Entrar a digitacion.
6. Confirmar que los campos con catalogos despliegan valores.
7. Confirmar que la imagen flotante no se recarga al cambiar de campo.
8. Guardar y revisar que el expediente quede persistido.

## Observaciones

- El stack no usa rutas absolutas de Mac.
- El servidor destino solo necesita Docker y los archivos del proyecto.
- Los puertos se parametrizan por `.env`.
- El modo base no requiere un proveedor LLM externo.
- Si se activa Ollama, usar `docker compose --env-file .env -f docker-compose.deploy.yml --profile ollama up -d --build`.
