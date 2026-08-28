--
-- View "afa_pendientes" de pqr_colmena.
--
-- Reproduccion literal del view que ya existe en las bases de pruebas y produccion
-- (obtenido con: SELECT pg_get_viewdef('afa_pendientes'::regclass, true)). Se replica acá
-- para que el compat-db local exponga la misma superficie que el legacy real.
--
-- Que hace: lista las gestiones de afa_trazabilidad TODAVIA SIN GESTIONAR
-- (fecha_gestion IS NULL) y les pega, por subconsulta escalar, cuatro campos del
-- formulario dinamico de esa radicacion -Contrato, Nit, Razon Social y Numero de
-- trabajadores-. El pivot se hace por LABEL del campo, no por id: valores -> 
-- tipo_solicitud_campo -> campos, y se filtra por c.label.
--
-- Ojo con dos cosas heredadas del original, que se conservan a proposito para no
-- divergir del legacy:
--
--   1. Las subconsultas son escalares sin LIMIT. Si una radicacion llegara a tener dos
--      filas en "valores" para el mismo label, Postgres aborta la fila con
--      "more than one row returned by a subquery used as an expression". El legacy lo
--      asume unico; acá tambien.
--   2. El filtro es por texto exacto del label ('Razon Social', sin tilde y con esa
--      capitalizacion). Si el catalogo "campos" cambia el label, la columna sale NULL en
--      silencio, sin error.
--
-- CREATE OR REPLACE mantiene el OID si el view ya existe, pero exige misma lista de
-- columnas, mismo orden y mismos tipos. Si alguna vez cambia la forma, hay que DROP antes.
--
-- Uso sobre el compat-db local ya provisionado:
--   psql -U <usuario> -d pqr_colmena -f 58-pqr-afa-pendientes-view.sql
--
-- AMBITO: solo el compat-db local/de pruebas. En el servidor el view ya existe; esto no
-- se corre allá.
--

\set ON_ERROR_STOP on

CREATE OR REPLACE VIEW public.afa_pendientes AS
 SELECT ( SELECT a.valor
           FROM valores a
             JOIN tipo_solicitud_campo b ON a.id_tipo_solicitud_campo = b.id_tipo_solicitud_campo
             JOIN campos c ON c.id_campo = b.id_campo
          WHERE a.id_radicacion_sa = afa_trazabilidad.id_radicacion_sa AND c.label::text = 'Contrato'::text) AS contrato,
    ( SELECT a.valor
           FROM valores a
             JOIN tipo_solicitud_campo b ON a.id_tipo_solicitud_campo = b.id_tipo_solicitud_campo
             JOIN campos c ON c.id_campo = b.id_campo
          WHERE a.id_radicacion_sa = afa_trazabilidad.id_radicacion_sa AND c.label::text = 'Nit'::text) AS nit,
    ( SELECT a.valor
           FROM valores a
             JOIN tipo_solicitud_campo b ON a.id_tipo_solicitud_campo = b.id_tipo_solicitud_campo
             JOIN campos c ON c.id_campo = b.id_campo
          WHERE a.id_radicacion_sa = afa_trazabilidad.id_radicacion_sa AND c.label::text = 'Razon Social'::text) AS razon_social,
    ( SELECT a.valor
           FROM valores a
             JOIN tipo_solicitud_campo b ON a.id_tipo_solicitud_campo = b.id_tipo_solicitud_campo
             JOIN campos c ON c.id_campo = b.id_campo
          WHERE a.id_radicacion_sa = afa_trazabilidad.id_radicacion_sa AND c.label::text = 'Numero de trabajadores'::text) AS num_trabajadores,
    id_trazabilidad,
    id_radicacion_sa,
    afi_rad_na,
    actividad,
    usuario_gestion,
    fecha_gestion,
    fecha_asignacion,
    observacion
   FROM afa_trazabilidad
  WHERE fecha_gestion IS NULL;
