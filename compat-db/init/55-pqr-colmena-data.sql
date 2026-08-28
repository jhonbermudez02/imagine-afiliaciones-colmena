--
-- Carga inicial de datos de "pqr_colmena" desde los CSV de
-- files_migration/schemassql/pqr_colmena, montados en el contenedor como /pqr_seed
-- (ver el volumen ":/pqr_seed:ro" del servicio imagine_compat_db).
--
-- Se corre despues de 50-pqr-colmena-schema.sql. Solo carga si la tabla esta vacia,
-- para que re-ejecutar el script en un ambiente ya provisionado no duplique filas
-- (estas tablas no declaran PK -ver el comentario del schema-, asi que nada impediria
-- la duplicacion a nivel de motor).
--
-- Sobre el formato: los data-*.csv vienen SIN encabezado, excepto data-valores.csv que
-- si lo trae. En modo CSV un campo vacio sin comillas ya se interpreta como NULL, que
-- es lo que corresponde a las columnas enteras opcionales (afi_rad_na, orden, etc.).
--
-- Uso (Postgres externo, fuera de docker-entrypoint-initdb.d): copiar los CSV al host
-- de psql y ajustar las rutas, o usar \copy desde el cliente.
--

\set ON_ERROR_STOP on

-- afa_trazabilidad
-- OJO: 57-reload-pqr-trazabilidad.sql corre despues y reemplaza el contenido de esta
-- tabla por las 11 gestiones del export vigente. Este \copy queda como la fuente del
-- historico completo, para poder volver atras sacando el 57 del init.
SELECT CASE WHEN EXISTS (SELECT 1 FROM public.afa_trazabilidad) THEN '/dev/null' ELSE '/pqr_seed/data-afa_trazabilidad.csv' END AS ruta \gset
\copy public.afa_trazabilidad (id_trazabilidad, id_radicacion_sa, afi_rad_na, actividad, usuario_gestion, fecha_gestion, fecha_asignacion, observacion) FROM :'ruta' WITH (FORMAT csv)

-- campos
SELECT CASE WHEN EXISTS (SELECT 1 FROM public.campos) THEN '/dev/null' ELSE '/pqr_seed/data-campos.csv' END AS ruta \gset
\copy public.campos (id_campo, nombre, label, id_tipo_campo, help_user) FROM :'ruta' WITH (FORMAT csv)

-- tipo_solicitud_campo
SELECT CASE WHEN EXISTS (SELECT 1 FROM public.tipo_solicitud_campo) THEN '/dev/null' ELSE '/pqr_seed/data-tipo_solicitud_campo.csv' END AS ruta \gset
\copy public.tipo_solicitud_campo (id_tipo_solicitud_campo, id_tipo_solicitud, id_campo, activo, valor_default, orden) FROM :'ruta' WITH (FORMAT csv)

-- valores (este CSV si trae encabezado)
SELECT CASE WHEN EXISTS (SELECT 1 FROM public.valores) THEN '/dev/null' ELSE '/pqr_seed/data-valores.csv' END AS ruta \gset
\copy public.valores (id_valor, id_radicacion_sa, id_tipo_solicitud_campo, valor) FROM :'ruta' WITH (FORMAT csv, HEADER true)

--
-- Las secuencias se alinean con el maximo id cargado: los CSV traen los ids explicitos,
-- asi que sin esto el primer INSERT nuevo arrancaria en 1 y chocaria con datos
-- existentes. setval(..., false) deja el proximo nextval en el valor indicado.
--
SELECT setval('public.afa_trazabilidad_id_trazabilidad_seq', COALESCE((SELECT max(id_trazabilidad) FROM public.afa_trazabilidad), 0) + 1, false);
SELECT setval('public.campos_id_campo_seq', COALESCE((SELECT max(id_campo) FROM public.campos), 0) + 1, false);
SELECT setval('public.tipo_solicitud_campo_id_tipo_solicitud_campo_seq', COALESCE((SELECT max(id_tipo_solicitud_campo) FROM public.tipo_solicitud_campo), 0) + 1, false);
SELECT setval('public.valores_id_valor_seq', COALESCE((SELECT max(id_valor) FROM public.valores), 0) + 1, false);
