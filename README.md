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

- [`backend`](/Users/escobar/Desktop/afi-nueva/backend): backend principal
- [`frontend-nova`](/Users/escobar/Desktop/afi-nueva/frontend-nova): frontend operativo
- [`compat-backend`](/Users/escobar/Desktop/afi-nueva/compat-backend): motor de compatibilidad del flujo `926`
- [`compat-db/init`](/Users/escobar/Desktop/afi-nueva/compat-db/init): esquema inicial de la base de compatibilidad
- [`data/knowledge`](/Users/escobar/Desktop/afi-nueva/data/knowledge): conocimiento operativo
- [`docker-compose.github.yml`](/Users/escobar/Desktop/afi-nueva/docker-compose.github.yml): compose recomendado para otro equipo

## Levantar el sistema

1. Clona el repositorio.
2. Copia `.env.example` a `.env` si quieres cambiar credenciales o modelos.
3. Desde la raiz del repo ejecuta:

```bash
docker compose -f docker-compose.github.yml up --build -d
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

- frontend: [http://localhost:3000](http://localhost:3000)
- backend: [http://localhost:8000](http://localhost:8000)

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

Apagar:

```bash
docker compose -f docker-compose.github.yml down
```

Ver logs:

```bash
docker compose -f docker-compose.github.yml logs -f imagine_backend
docker compose -f docker-compose.github.yml logs -f imagine_compat_backend
```

Recrear backend principal:

```bash
docker compose -f docker-compose.github.yml up -d --build imagine_backend
```

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
