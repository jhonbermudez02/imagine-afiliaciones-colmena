#!/bin/sh
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
SELECT 'CREATE DATABASE temporal'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'temporal')\gexec
SELECT 'CREATE DATABASE wimg004'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'wimg004')\gexec
SELECT 'CREATE DATABASE ybr'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'ybr')\gexec
SQL

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname temporal -f /docker-entrypoint-initdb.d/10-temporal-schema.sql
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname wimg004 -f /docker-entrypoint-initdb.d/20-wimg004-schema.sql
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname ybr -f /docker-entrypoint-initdb.d/30-ybr-schema.sql
