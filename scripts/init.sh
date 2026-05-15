#!/bin/bash
echo "Iniciando NOVA"

docker-compose up -d

echo "Esperando servicios..."
sleep 15

echo "Listo. Verifica con: curl http://localhost:8000/health"
