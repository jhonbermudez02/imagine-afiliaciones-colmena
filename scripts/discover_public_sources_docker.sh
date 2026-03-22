#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "Ejecutando descubrimiento dentro del contenedor backend..."
docker compose -f "$ROOT_DIR/docker-compose.yml" up -d backend >/dev/null
docker cp "$ROOT_DIR/scripts/discover_public_sources.py" afi_backend:/tmp/discover_public_sources.py
docker cp "$ROOT_DIR/data/source_registry.json" afi_backend:/data/source_registry.json
docker exec afi_backend python /tmp/discover_public_sources.py "$@"
docker cp afi_backend:/data/source_registry_discovered.json "$ROOT_DIR/data/source_registry_discovered.json"
echo "[ok] discovery sincronizado a $ROOT_DIR/data/source_registry_discovered.json"
