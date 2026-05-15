# Despliegue Portable

Este proyecto debe desplegarse como un stack dedicado del sistema `Imagine Afiliaciones`, sin depender de rutas locales de Mac y sin integrarse a servicios ajenos del cliente.

## Stack oficial de entrega

El archivo oficial para despliegue portable es:

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
docker compose -f docker-compose.deploy.yml up -d --build
```

## Operación básica

Ver estado:

```bash
docker compose -f docker-compose.deploy.yml ps
```

Ver logs:

```bash
docker compose -f docker-compose.deploy.yml logs -f imagine_backend
docker compose -f docker-compose.deploy.yml logs -f imagine_compat_backend
docker compose -f docker-compose.deploy.yml logs -f imagine_frontend
```

Recrear servicios clave:

```bash
docker compose -f docker-compose.deploy.yml up -d --build imagine_backend
docker compose -f docker-compose.deploy.yml up -d --build imagine_frontend
```

Apagar:

```bash
docker compose -f docker-compose.deploy.yml down
```

## Verificación

Frontend:

- [http://localhost:8105](http://localhost:8105)

Health backend:

- [http://localhost:8000/health](http://localhost:8000/health)

Health compat backend:

- [http://localhost:8011/health](http://localhost:8011/health)

## Smoke test de entrega

Después del primer arranque, validar al menos esto:

1. Abrir la UI en `http://localhost:8105`.
2. Confirmar que el login / selección de sesión responde.
3. Abrir `Producción` y verificar que carga contratos.
4. Recuperar un contrato existente.
5. Ejecutar proceso y confirmar que la prevalidación termina.
6. Confirmar que un caso aprobable intenta continuar a la etapa `926`.

## Variables importantes

### Backend principal

- `MODEL_NAME`
- `EMBEDDING_MODEL`
- `FRONTEND_URL`

### Compat backend

Por defecto el `compat-backend` queda en modo:

- `COMPAT_LLM_PROVIDER=local-deterministic`

Eso permite levantar el sistema sin depender de un endpoint externo.

Si más adelante se quiere usar un LLM OpenAI-compatible, ajustar:

- `COMPAT_LLM_PROVIDER`
- `COMPAT_LLM_BASE_URL`
- `COMPAT_LLM_API_KEY`
- `COMPAT_LLM_MODEL`

## Persistencia

Los datos persistentes quedan en volúmenes Docker:

- `imagine_postgres_data`
- `imagine_compat_postgres_data`
- `imagine_qdrant_data`

Además, el proyecto usa la carpeta:

- `data`

para conocimiento, casos, reportes y otros artefactos operativos.

## Observaciones

- Este compose evita rutas absolutas de Mac.
- El sistema queda aislado del cliente a nivel de stack.
- Si se requiere otro sistema del mismo proveedor, debe desplegarse en otro proyecto Docker o con otro nombre de stack.
- El stack usa la carpeta local `data` para expedientes, reportes y artefactos operativos; esa carpeta debe viajar con el proyecto si se quiere conservar histórico.
