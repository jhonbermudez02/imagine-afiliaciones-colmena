#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker-compose.deploy.yml"

echo "Levantando stack portable de Imagine Afiliaciones..."
docker compose -f "$COMPOSE_FILE" up -d --build

echo
echo "Servicios esperados:"
echo "- Frontend: http://localhost:${FRONTEND_PORT:-8105}"
echo "- Backend:  http://localhost:${BACKEND_PORT:-8000}/health"
echo "- Compat:   http://localhost:${COMPAT_BACKEND_PORT:-8011}/health"
