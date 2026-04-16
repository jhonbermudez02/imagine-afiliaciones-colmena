#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker-compose.github.yml"

FRONTEND_URL="${FRONTEND_URL:-http://127.0.0.1:8105}"
BACKEND_HEALTH_URL="http://localhost:8000/health"
COMPAT_HEALTH_URL="http://localhost:8011/health"

check_url() {
  local url="$1"
  curl -fsS --max-time 5 "$url" >/dev/null 2>&1
}

print_status() {
  echo "Frontend: $FRONTEND_URL"
  echo "Backend:  $BACKEND_HEALTH_URL"
  echo "Compat:   $COMPAT_HEALTH_URL"
}

wait_for_stack() {
  local retries="${1:-40}"
  local delay="${2:-3}"
  local i
  for ((i=1; i<=retries; i++)); do
    if check_url "$FRONTEND_URL" && check_url "$BACKEND_HEALTH_URL" && check_url "$COMPAT_HEALTH_URL"; then
      return 0
    fi
    sleep "$delay"
  done
  return 1
}

echo "Verificando stack de afiliaciones..."
print_status

if check_url "$FRONTEND_URL" && check_url "$BACKEND_HEALTH_URL" && check_url "$COMPAT_HEALTH_URL"; then
  echo "OK: el stack ya está arriba."
  exit 0
fi

echo "El stack no está completo. Levantando contenedores..."
docker compose -f "$COMPOSE_FILE" up -d

echo "Esperando disponibilidad de frontend/backend/compat..."
if wait_for_stack 50 3; then
  echo "OK: sistema arriba."
  print_status
  exit 0
fi

echo "ERROR: el stack no quedó disponible a tiempo."
echo "Revisa logs con:"
echo "docker compose -f \"$COMPOSE_FILE\" logs -f imagine_backend"
echo "docker compose -f \"$COMPOSE_FILE\" logs -f imagine_compat_backend"
echo "docker compose -f \"$COMPOSE_FILE\" logs -f imagine_frontend"
exit 1
