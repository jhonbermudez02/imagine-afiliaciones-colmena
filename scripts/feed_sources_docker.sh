#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "Ejecutando alimentacion dentro del contenedor backend..."
docker compose -f "$ROOT_DIR/docker-compose.yml" up -d backend >/dev/null
docker cp "$ROOT_DIR/scripts/feed_sources.py" afi_backend:/tmp/feed_sources.py
docker cp "$ROOT_DIR/data/source_registry.json" afi_backend:/data/source_registry.json
docker exec afi_backend python /tmp/feed_sources.py "$@"
docker cp afi_backend:/data/feed_report.json "$ROOT_DIR/data/feed_report.json"
echo "[ok] reporte sincronizado a $ROOT_DIR/data/feed_report.json"
