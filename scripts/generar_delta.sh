#!/usr/bin/env bash
# ============================================================================
#  GENERADOR de paquete DELTA (solo codigo) - AFI COLIMA
#  Produce un paquete liviano (~700 KB) para aplicar cambios de CODIGO en un
#  server sin salida a internet, PARTIENDO de las imagenes ya instaladas alli
#  (no ejecuta apt/pip/npm en el server).
#
#  Uso:
#    ./scripts/generar_delta.sh                # fecha de hoy, salida junto al repo
#    DATE=2026-08-10 OUT_BASE=/ruta ./scripts/generar_delta.sh
#
#  Requisitos locales: docker (para compilar el frontend se usa node local si
#  esta disponible; si no, se compila el dist dentro de un contenedor node).
#
#  IMPORTANTE: el delta solo sirve si en el server YA existe una instalacion
#  completa y NO cambiaron dependencias (requirements.txt / package.json). Si
#  cambian dependencias, use el paquete completo (imagenes docker save/load).
# ============================================================================
set -euo pipefail

RED='\033[0;31m'; GRN='\033[0;32m'; YLW='\033[1;33m'; NC='\033[0m'
err(){ echo -e "${RED}[ERROR]${NC} $*" >&2; }
ok(){  echo -e "${GRN}[OK]${NC} $*"; }
inf(){ echo -e "${YLW}[..]${NC} $*"; }

# ---- Rutas ----
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/.." && pwd)"
DATE="${DATE:-$(date +%F)}"
OUT_BASE="${OUT_BASE:-$(cd "$REPO/.." && pwd)}"
PKG="$OUT_BASE/AFI_COLIMA_DELTA_$DATE"
FRONT="$REPO/frontend-nova"

# ---- Aviso si cambiaron dependencias (el delta NO las aplica) ----
if git -C "$REPO" status --short 2>/dev/null | grep -qiE 'requirements\.txt|package\.json|package-lock|pnpm-lock'; then
  err "Detectados cambios en dependencias (requirements.txt / package.json)."
  err "El delta NO ejecuta pip/npm en el server: use el paquete COMPLETO de imagenes."
  err "Para forzar de todos modos: FORCE=1 $0"
  [[ "${FORCE:-0}" == "1" ]] || exit 1
fi

# ---- 1. Compilar el frontend (dist) ----
inf "Compilando frontend (dist) con VITE_API_URL=/api ..."
if [[ -d "$FRONT/dist" ]] && ! rm -rf "$FRONT/dist" 2>/dev/null; then
  err "No pude borrar $FRONT/dist (probablemente pertenece a root de un build previo en contenedor)."
  err "Ejecute:  sudo rm -rf $FRONT/dist   y vuelva a correr este generador."
  exit 1
fi
if [[ -f "$FRONT/node_modules/vite/bin/vite.js" ]]; then
  ( cd "$FRONT" && VITE_API_URL=/api node node_modules/vite/bin/vite.js build >/dev/null )
elif command -v npm >/dev/null 2>&1; then
  ( cd "$FRONT" && npm install >/dev/null 2>&1 && VITE_API_URL=/api npm run build >/dev/null )
else
  inf "Sin node local: compilando dentro de un contenedor node:18-alpine (como su usuario) ..."
  # --user evita que el dist quede con dueño root en el host.
  docker run --rm --user "$(id -u):$(id -g)" -v "$FRONT":/app -w /app -e VITE_API_URL=/api \
    -e npm_config_cache=/tmp/.npm node:18-alpine \
    sh -c "npm install >/dev/null 2>&1 && npm run build >/dev/null"
fi
[[ -d "$FRONT/dist" ]] || { err "No se genero el dist del frontend"; exit 1; }
ok "dist compilado"

# ---- 2. Armar el contexto build/ ----
inf "Ensamblando el paquete en $PKG ..."
rm -rf "$PKG"; mkdir -p "$PKG/build/backend" "$PKG/build/compat-backend" "$PKG/build/frontend"
rsync -a --exclude='__pycache__' --exclude='*.pyc' "$REPO/backend/" "$PKG/build/backend/"
rsync -a --exclude='__pycache__' --exclude='*.pyc' "$REPO/compat-backend/" "$PKG/build/compat-backend/"
cp -r "$FRONT/dist" "$PKG/build/frontend/dist"

# ---- 3. Dockerfiles delta ----
cat > "$PKG/build/backend/Dockerfile.delta" <<'DF'
# Delta: parte de la imagen backend ya presente y solo re-copia el codigo.
# NO ejecuta apt/pip (deps sin cambios) -> funciona sin salida a internet.
ARG BASE_IMAGE=imagine-afiliaciones-imagine_backend:latest
FROM ${BASE_IMAGE}
WORKDIR /app
COPY . .
DF
cat > "$PKG/build/compat-backend/Dockerfile.delta" <<'DF'
ARG BASE_IMAGE=imagine-afiliaciones-imagine_compat_backend:latest
FROM ${BASE_IMAGE}
WORKDIR /app
COPY . .
DF
cat > "$PKG/build/frontend/Dockerfile.delta" <<'DF'
# La imagen base ya trae nginx + nginx.conf; solo se reemplaza el bundle.
ARG BASE_IMAGE=imagine-afiliaciones-imagine_frontend:latest
FROM ${BASE_IMAGE}
RUN rm -rf /usr/share/nginx/html/*
COPY dist/ /usr/share/nginx/html/
DF

# ---- 4. Script que se ejecuta EN EL SERVER (auto-detecta nombres de imagen) ----
cat > "$PKG/aplicar_delta.sh" <<'APPLY'
#!/usr/bin/env bash
# APLICAR DELTA (solo codigo) - reconstruye las 3 imagenes partiendo de las que
# ya estan en el server y solo re-copiando el codigo. NO apt/pip/npm.
# NO toca .env, ni la BD, ni ./data.
set -euo pipefail
RED='\033[0;31m'; GRN='\033[0;32m'; YLW='\033[1;33m'; NC='\033[0m'
err(){ echo -e "${RED}[ERROR]${NC} $*" >&2; }
ok(){  echo -e "${GRN}[OK]${NC} $*"; }
inf(){ echo -e "${YLW}[..]${NC} $*"; }
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${APP_DIR:-/opt/project/imagine-afiliaciones}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.deploy.external-db.yml}"
[[ -f "$APP_DIR/$COMPOSE_FILE" ]] || { err "No existe $APP_DIR/$COMPOSE_FILE (revise APP_DIR)"; exit 1; }
[[ -f "$APP_DIR/.env" ]] || { err "No existe $APP_DIR/.env (debe existir instalacion previa)"; exit 1; }
cd "$APP_DIR"
detect_img() {
  local svc="$1" cid img
  cid="$(docker compose -f "$COMPOSE_FILE" ps -q "$svc" 2>/dev/null | head -1)"
  if [[ -n "$cid" ]]; then
    img="$(docker inspect --format '{{.Config.Image}}' "$cid" 2>/dev/null || true)"
    [[ -n "$img" && "$img" != sha256:* ]] && { echo "$img"; return 0; }
  fi
  img="$(docker compose -f "$COMPOSE_FILE" config --images 2>/dev/null | grep -E "(^|[-_])${svc}(:|$)" | head -1 || true)"
  [[ -n "$img" ]] && { echo "$img"; return 0; }
  img="$(docker images --format '{{.Repository}}:{{.Tag}}' | grep -E "[-_]${svc}:" | grep -v '<none>' | head -1 || true)"
  [[ -n "$img" ]] && { echo "$img"; return 0; }
  return 1
}
BACK_IMG="${BACK_IMG:-$(detect_img imagine_backend || true)}"
COMPAT_IMG="${COMPAT_IMG:-$(detect_img imagine_compat_backend || true)}"
FRONT_IMG="${FRONT_IMG:-$(detect_img imagine_frontend || true)}"
for pair in "backend:$BACK_IMG" "compat:$COMPAT_IMG" "frontend:$FRONT_IMG"; do
  if [[ -z "${pair#*:}" ]]; then
    err "No pude detectar la imagen de '${pair%%:*}'. Fije la variable, p.ej.:"
    err "   BACK_IMG=<repo:tag> COMPAT_IMG=<repo:tag> FRONT_IMG=<repo:tag> ./aplicar_delta.sh"
    exit 1
  fi
done
ok "Imagenes detectadas:"; echo "     backend : $BACK_IMG"; echo "     compat  : $COMPAT_IMG"; echo "     frontend: $FRONT_IMG"
inf "Delta backend (solo COPY)..."; docker build --build-arg BASE_IMAGE="$BACK_IMG" -t "$BACK_IMG" -f "$HERE/build/backend/Dockerfile.delta" "$HERE/build/backend"
inf "Delta compat...";             docker build --build-arg BASE_IMAGE="$COMPAT_IMG" -t "$COMPAT_IMG" -f "$HERE/build/compat-backend/Dockerfile.delta" "$HERE/build/compat-backend"
inf "Delta frontend (bundle)...";  docker build --build-arg BASE_IMAGE="$FRONT_IMG" -t "$FRONT_IMG" -f "$HERE/build/frontend/Dockerfile.delta" "$HERE/build/frontend"
inf "Recreando stack (sin build)..."; docker compose -f "$COMPOSE_FILE" up -d --no-build --force-recreate
docker image prune -f >/dev/null 2>&1 || true
echo; docker compose -f "$COMPOSE_FILE" ps
echo; ok "Delta aplicado. .env, BD y ./data intactos."
APPLY
chmod +x "$PKG/aplicar_delta.sh"

# ---- 5. README ----
cat > "$PKG/README_DELTA.txt" <<RD
AFI COLIMA - ACTUALIZACION DELTA (solo codigo) $DATE
====================================================
Version liviana para aplicar cambios de CODIGO sin mover las imagenes completas.
Requiere instalacion completa previa en el server y que NO cambien dependencias.
NO toca .env, ni la BD, ni ./data.

APLICAR EN EL SERVER:
  sha256sum -c afi_colima_delta_$DATE.sha256
  mkdir -p /opt/project/afiliaciones/delta_$DATE
  tar -xzf afi_colima_delta_$DATE.tar.gz -C /opt/project/afiliaciones/delta_$DATE
  cd /opt/project/afiliaciones/delta_$DATE
  chmod +x aplicar_delta.sh
  APP_DIR=/opt/project/imagine-afiliaciones ./aplicar_delta.sh

Si no detecta las imagenes, fijelas a mano:
  BACK_IMG=<repo:tag> COMPAT_IMG=<repo:tag> FRONT_IMG=<repo:tag> ./aplicar_delta.sh
RD

# ---- 6. Empaquetar ----
inf "Comprimiendo..."
( cd "$PKG" && tar -czf "afi_colima_delta_$DATE.tar.gz" build aplicar_delta.sh README_DELTA.txt \
    && sha256sum "afi_colima_delta_$DATE.tar.gz" > "afi_colima_delta_$DATE.sha256" \
    && rm -rf build aplicar_delta.sh )

echo
ok "Paquete delta generado:"
ls -lh "$PKG"
echo
echo "Copielo al server y ejecute aplicar_delta.sh (ver README_DELTA.txt)."
