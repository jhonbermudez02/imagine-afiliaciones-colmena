#!/bin/bash
echo "🚀 Iniciando NOVA"

docker-compose up -d

echo "⏳ Esperando servicios..."
sleep 15

echo "📥 Descargando modelos Ollama..."
docker exec afi_ollama ollama pull llama3.2:1b &
docker exec afi_ollama ollama pull nomic-embed-text &

echo "✅ Listo! Verifica con: curl http://localhost:8000/health"
