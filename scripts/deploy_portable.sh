#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker-compose.deploy.yml"
ENV_FILE="$ROOT_DIR/.env"
ENV_EXAMPLE="$ROOT_DIR/.env.example"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "ERROR: falta instalar '$1'." >&2
    exit 1
  fi
}

wait_url() {
  local name="$1"
  local url="$2"
  local retries="${3:-30}"

  if ! command -v curl >/dev/null 2>&1; then
    return 0
  fi

  printf "Esperando %s" "$name"
  for _ in $(seq 1 "$retries"); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      printf " OK\n"
      return 0
    fi
    printf "."
    sleep 2
  done

  printf " pendiente\n"
  return 0
}

require_cmd docker

if ! docker compose version >/dev/null 2>&1; then
  echo "ERROR: Docker Compose plugin no esta disponible. Instala Docker Engine con 'docker compose'." >&2
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  cp "$ENV_EXAMPLE" "$ENV_FILE"
  echo "Se creo .env desde .env.example. Revisa puertos y credenciales si es un servidor nuevo."
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

mkdir -p \
  "$ROOT_DIR/data/cases" \
  "$ROOT_DIR/data/compat" \
  "$ROOT_DIR/data/compat/926_history" \
  "$ROOT_DIR/data/evals" \
  "$ROOT_DIR/data/knowledge" \
  "$ROOT_DIR/data/ollama" \
  "$ROOT_DIR/data/postgres" \
  "$ROOT_DIR/data/qdrant" \
  "$ROOT_DIR/data/raw" \
  "$ROOT_DIR/shared_downloads"

echo "Levantando stack Docker portable de AFILEGA_FA_IMA_LA_V2..."
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --build

echo
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" ps

echo
echo "Servicios esperados:"
echo "- Frontend: http://localhost:${FRONTEND_PORT:-8105}"
echo "- Backend:  http://localhost:${BACKEND_PORT:-8000}/health"
echo "- Compat:   http://localhost:${COMPAT_BACKEND_PORT:-8011}/health"

echo
wait_url "backend" "http://localhost:${BACKEND_PORT:-8000}/health" 30
wait_url "compat backend" "http://localhost:${COMPAT_BACKEND_PORT:-8011}/health" 30
