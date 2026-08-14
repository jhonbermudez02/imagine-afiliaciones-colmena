-- ============================================================================
--  MIGRACION DE BASE DE DATOS - 2026-08-12
--
--  El paquete delta SOLO reemplaza codigo. Esto hay que correrlo aparte, ANTES
--  de aplicar el delta, en el Postgres de cada ambiente (pruebas y produccion).
--
--  Todo es idempotente: se puede correr dos veces sin romper nada.
--
--  Ojo con los nombres de base: los alias de la app (wimg004 / ybr / pqr) NO son
--  los nombres reales. Aca se usan los reales: img004, br, temporal, pqr_colmena.
-- ============================================================================


-- ----------------------------------------------------------------------------
-- 1. img004: el codigo de EPS/AFP deja de ser unico
-- ----------------------------------------------------------------------------
-- La misma entidad puede estar varias veces con nombres distintos; desde que la
-- homologacion exige coincidencia EXACTA de nombre, repetir el codigo es como se
-- registran las variantes ("NUEVA EPS" / "NUEVA EPS S.A."). El catalogo legacy
-- real ya lo hace: temporal.afpriesgos trae dos filas con codigo 0.
--
-- Verificar ANTES como se llama la constraint (si no es <tabla>_pkey, el DROP de
-- abajo no hace nada en silencio):
--   SELECT c.relname, con.conname FROM pg_class c
--   JOIN pg_constraint con ON con.conrelid=c.oid AND con.contype='p'
--   WHERE c.relname IN ('epsriesgos','afpriesgos');
--
-- \c img004
ALTER TABLE IF EXISTS public.epsriesgos DROP CONSTRAINT IF EXISTS epsriesgos_pkey;
ALTER TABLE IF EXISTS public.afpriesgos DROP CONSTRAINT IF EXISTS afpriesgos_pkey;

-- El compat repite este DROP al guardar el catalogo (red de seguridad), asi que
-- si la constraint tiene el nombre convencional el ambiente se corrige solo la
-- primera vez que se guarde desde la app.


-- ----------------------------------------------------------------------------
-- 2. temporal: componentes separados del nombre del responsable de sede
-- ----------------------------------------------------------------------------
-- El documento de la sede trae los cuatro campos por etiqueta y el consumidor
-- (f06/f69/carcont2/f70 de brempresasarp) los quiere separados. Guardarlos solo
-- concatenados obligaba a re-partirlos por posicion, y eso pierde el dato cuando
-- un apellido tiene dos palabras ("DE LA CRUZ") o falta una casilla.
--
-- \c temporal
ALTER TABLE IF EXISTS public.proc_servicios_obtenersedetramite
    ADD COLUMN IF NOT EXISTS respsedeprimerapellido  text,
    ADD COLUMN IF NOT EXISTS respsedesegundoapellido text,
    ADD COLUMN IF NOT EXISTS respsedeprimernombre    text,
    ADD COLUMN IF NOT EXISTS respsedesegundonombre   text;


-- ----------------------------------------------------------------------------
-- 3. img004: tabla estadistico
-- ----------------------------------------------------------------------------
-- El legacy copiaba estadistico de temporal al archivo, pero la tabla nunca se
-- creo en img004, asi que la copia no tenia destino. Ahora la entrega escribe
-- directo aca y limpia temporal.
--
-- \c img004
CREATE TABLE IF NOT EXISTS public.estadistico (
    lote integer NOT NULL,
    fecha integer,
    familia varchar(3),
    planillas integer,
    anexos integer,
    detalles integer,
    usuario varchar(15),
    fecha_seleccion timestamp without time zone,
    fecha_entrega timestamp without time zone,
    fecha_guardado timestamp without time zone,
    fecha_recobro timestamp without time zone,
    rango varchar(2),
    sede numeric,
    centrot numeric
);


-- ----------------------------------------------------------------------------
-- 4. pqr_colmena: base nueva (trazabilidad de PQR)
-- ----------------------------------------------------------------------------
-- Al aprobar un contrato se cierra su gestion pendiente en afa_trazabilidad y se
-- inserta el registro de actividad 390.
--
-- IMPORTANTE: si esta base YA existe en el ambiente (viene del sistema de PQR
-- real), NO correr 50/55: las tablas y los datos ya estan, y 55 cargaria la
-- semilla de desarrollo encima. Solo verificar que el usuario de la app tenga
-- permisos de lectura/escritura sobre afa_trazabilidad.
--
-- Si la base NO existe (ambiente nuevo):
--   psql -U <usuario> -d postgres -c "CREATE DATABASE pqr_colmena"
--   psql -U <usuario> -d pqr_colmena -f compat-db/init/50-pqr-colmena-schema.sql
--   -- y solo si hace falta la semilla de prueba:
--   psql -U <usuario> -d pqr_colmena -f compat-db/init/55-pqr-colmena-data.sql


-- ----------------------------------------------------------------------------
-- 5. Verificacion posterior
-- ----------------------------------------------------------------------------
-- img004:
--   SELECT count(*) FROM pg_constraint con JOIN pg_class c ON c.oid=con.conrelid
--   WHERE c.relname IN ('epsriesgos','afpriesgos') AND con.contype='p';   -- 0
--   SELECT to_regclass('public.estadistico');                             -- estadistico
-- temporal:
--   SELECT count(*) FROM information_schema.columns
--   WHERE table_name='proc_servicios_obtenersedetramite'
--     AND column_name LIKE 'respsede%';                                   -- 4
-- pqr_colmena:
--   SELECT count(*) FROM afa_trazabilidad;
