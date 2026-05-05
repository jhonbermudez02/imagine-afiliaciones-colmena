# Entrega tecnica - Imagine Afiliaciones

Este documento es la guia rapida para quien recibe el repositorio y debe montar el sistema completo en pruebas o produccion.

## Repositorio

- GitHub: `https://github.com/IOhernan/imagine-afiliaciones`
- Stack oficial: `docker-compose.deploy.yml`
- Frontend: `frontend-nova`
- Backend principal: `backend`
- Backend compatibilidad/legacy 926: `compat-backend`
- Base de conocimiento RAG: `data/knowledge`
- Catalogos operativos: `data/evals`

## Accesos recomendados en GitHub

Para el responsable de infraestructura/despliegue, usar permiso `Maintain` o `Admin`.

El repositorio debe contener codigo, documentacion, catalogos base y conocimiento operativo. No debe contener credenciales reales ni expedientes productivos.

## Datos sensibles fuera de Git

Entregar por canal seguro:

- `.env` productivo
- credenciales SMTP
- credenciales de servidor
- backups de base de datos
- expedientes/casos reales
- certificados, llaves o tokens

No versionar:

- `data/cases`
- `data/postgres`
- volumenes Qdrant/Ollama
- logs de notificacion
- `.env`

## Arranque en servidor

```bash
git clone https://github.com/IOhernan/imagine-afiliaciones.git
cd imagine-afiliaciones
cp .env.example .env
docker compose -f docker-compose.deploy.yml up -d --build
```

Ver estado:

```bash
docker compose -f docker-compose.deploy.yml ps
curl -s http://localhost:${BACKEND_PORT:-8000}/health
```

Abrir:

- Frontend: `http://IP_SERVIDOR:${FRONTEND_PORT:-8105}`
- Backend health: `http://IP_SERVIDOR:${BACKEND_PORT:-8000}/health`
- Compat health: `http://IP_SERVIDOR:${COMPAT_BACKEND_PORT:-8011}/health`

## Servicios Docker

- `imagine_frontend`: interfaz operativa
- `imagine_backend`: API principal, OCR, validaciones, RAG, expedientes
- `imagine_db`: Postgres principal
- `imagine_qdrant`: vector store RAG
- `imagine_compat_backend`: compatibilidad legacy y generacion 926
- `imagine_compat_db`: base legacy/compatibilidad
- `imagine_ollama`: opcional, solo si se activa el perfil `ollama`

## RAG y embeddings

El sistema debe operar con embeddings locales en Python:

- `USE_LOCAL_EMBED=true`
- `EMBEDDING_MODEL=paraphrase-multilingual-MiniLM-L12-v2`
- `QDRANT_URL=http://imagine_qdrant:6333`
- `KNOWLEDGE_DIR=/data/knowledge`

Ollama no es obligatorio para el flujo actual. El servicio `imagine_ollama` queda bajo profile `ollama`; no se levanta en el despliegue normal.

## Actualizacion

```bash
git pull origin main
docker compose -f docker-compose.deploy.yml build imagine_backend imagine_frontend imagine_compat_backend
docker compose -f docker-compose.deploy.yml up -d imagine_backend imagine_frontend imagine_compat_backend
docker compose -f docker-compose.deploy.yml ps
```

## Validaciones criticas actuales

El backend valida, entre otros puntos:

- documento de trabajador estrictamente numerico
- modalidad laboral normalizada
- contrato duplicado si ya existe un caso aprobable
- numero de contrato contra soportes, con tolerancia controlada para OCR ambiguo
- razon social formal entre Excel/Formulario, Camara y Entrega de documentos
- `S.A.S.` y `SAS` se consideran diferentes para aprobacion
- EPS/AFP/ARL/catalogos operativos
- actividad economica y datos para plano 926
- intermediarios/comisiones segun reglas Colmena

## Smoke test minimo

1. Abrir frontend.
2. Cargar expediente con Excel y PDFs.
3. Confirmar que la bandeja muestra el contrato.
4. Abrir clasificacion documental.
5. Revisar bloqueantes/prevalidacion.
6. Confirmar que un caso aprobable habilita el flujo 926.
7. Confirmar que un caso observado no genera plano final.

## Comandos utiles

Logs:

```bash
docker compose -f docker-compose.deploy.yml logs -f imagine_backend
docker compose -f docker-compose.deploy.yml logs -f imagine_frontend
docker compose -f docker-compose.deploy.yml logs -f imagine_compat_backend
```

Reiniciar:

```bash
docker compose -f docker-compose.deploy.yml restart
```

Apagar:

```bash
docker compose -f docker-compose.deploy.yml down
```

Uso de recursos:

```bash
docker stats --no-stream
```

## Contacto operativo

Imagine S.A.S. coordina la entrega de credenciales y datos sensibles por canal seguro.
