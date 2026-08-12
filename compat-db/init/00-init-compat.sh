#!/bin/sh
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
SELECT 'CREATE DATABASE temporal'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'temporal')\gexec
SELECT 'CREATE DATABASE img004'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'img004')\gexec
SELECT 'CREATE DATABASE br'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'br')\gexec
SELECT 'CREATE DATABASE pqr_colmena'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'pqr_colmena')\gexec
SQL

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname temporal -f /docker-entrypoint-initdb.d/10-temporal-schema.sql
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname img004 -f /docker-entrypoint-initdb.d/20-img004-schema.sql
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname br -f /docker-entrypoint-initdb.d/30-br-schema.sql
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname temporal -f /docker-entrypoint-initdb.d/40-temporal-proc-servicios-schema.sql
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname pqr_colmena -f /docker-entrypoint-initdb.d/50-pqr-colmena-schema.sql
# La carga de datos depende de que los CSV esten montados en /pqr_seed; si el volumen no
# esta (ambiente que solo quiere el esquema vacio), se omite en vez de abortar el init.
if [ -d /pqr_seed ]; then
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname pqr_colmena -f /docker-entrypoint-initdb.d/55-pqr-colmena-data.sql
else
    echo "[init-compat] /pqr_seed no montado: pqr_colmena queda con el esquema vacio."
fi
