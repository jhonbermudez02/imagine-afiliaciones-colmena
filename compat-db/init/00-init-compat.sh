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
# Catalogos de intermediacion, contra img004. Son los que respaldan la validacion del
# documento de comisiones: codigo 01 (Consultor) -> consultores, codigo 03
# (Corredor/Agencia) -> afi_intermediarios. Antes solo se creaban las tablas y quedaban
# vacias, porque estos seeds no se ejecutaban contra img004.
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname img004 -f /docker-entrypoint-initdb.d/45-seed-consultores-img004.sql
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname img004 -f /docker-entrypoint-initdb.d/46-seed-afi-intermediarios-img004.sql
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname pqr_colmena -f /docker-entrypoint-initdb.d/50-pqr-colmena-schema.sql
# La carga de datos depende de que los CSV esten montados en /pqr_seed; si el volumen no
# esta (ambiente que solo quiere el esquema vacio), se omite en vez de abortar el init.
if [ -d /pqr_seed ]; then
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname pqr_colmena -f /docker-entrypoint-initdb.d/55-pqr-colmena-data.sql
else
    echo "[init-compat] /pqr_seed no montado: pqr_colmena queda con el esquema vacio."
fi
# Adjuntos de radicacion y las filas nuevas de valores. No dependen de /pqr_seed: los
# INSERT van embebidos en el script, con guarda por id, asi que corre siempre.
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname pqr_colmena -f /docker-entrypoint-initdb.d/56-seed-pqr-adjuntos-valores.sql
# Reemplazo de afa_trazabilidad: deja solo las gestiones de las radicaciones del export
# actual y descarta el historico que acaba de cargar 55. Va al final a proposito -es un
# reemplazo, no un seed-; sacarlo de aca devuelve el historico completo.
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname pqr_colmena -f /docker-entrypoint-initdb.d/57-reload-pqr-trazabilidad.sql
# View afa_pendientes: copia literal del que ya existe en pruebas/produccion. Va al final
# porque depende de afa_trazabilidad, valores, tipo_solicitud_campo y campos.
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname pqr_colmena -f /docker-entrypoint-initdb.d/58-pqr-afa-pendientes-view.sql
