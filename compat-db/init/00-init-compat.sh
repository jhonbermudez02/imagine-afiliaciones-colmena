#!/bin/sh
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
SELECT 'CREATE DATABASE temporal'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'temporal')\gexec
SELECT 'CREATE DATABASE img004'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'img004')\gexec
SELECT 'CREATE DATABASE br'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'br')\gexec
SQL

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname temporal -f /docker-entrypoint-initdb.d/10-temporal-schema.sql
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname img004 -f /docker-entrypoint-initdb.d/20-img004-schema.sql
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname br -f /docker-entrypoint-initdb.d/30-br-schema.sql
