--
-- Esquema de la base "pqr_colmena" (alias de aplicacion: "pqr").
--
-- Cuarta base legacy del stack, junto a temporal / img004 (alias wimg004) / br
-- (alias ybr). Sirve la trazabilidad de PQR: afa_trazabilidad guarda una fila por
-- gestion sobre una radicacion (id_radicacion_sa), y campos / tipo_solicitud_campo /
-- valores son el formulario dinamico asociado al tipo de solicitud.
--
-- Origen: files_migration/schemassql/pqr_colmena/*_schema.csv, que es un export de
-- information_schema.columns de la base real. Ese export trae columnas, tipos,
-- nulabilidad y defaults -y eso es exactamente lo que se reproduce aca-.
--
-- Deliberadamente NO se declara ninguna PRIMARY KEY ni UNIQUE: el export no incluye
-- informacion de constraints, asi que agregarlas seria inventar una restriccion que la
-- base real puede no tener. Ya paso con img004.epsriesgos, donde una PK sobre `codigo`
-- que el legacy no tiene hizo perder filas legitimas en silencio. Las columnas id_* si
-- quedan NOT NULL con su secuencia, que es lo que el export si afirma.
--
-- Uso (Postgres externo, fuera de docker-entrypoint-initdb.d):
--   psql -h <host> -U <usuario> -d pqr_colmena -f 50-pqr-colmena-schema.sql
--
-- Es seguro correrlo mas de una vez (todo con IF NOT EXISTS).
--

--
-- Name: afa_trazabilidad; Type: TABLE; Schema: public; Owner: escobar
--

CREATE SEQUENCE IF NOT EXISTS public.afa_trazabilidad_id_trazabilidad_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

CREATE TABLE IF NOT EXISTS public.afa_trazabilidad (
    id_trazabilidad integer NOT NULL DEFAULT nextval('public.afa_trazabilidad_id_trazabilidad_seq'::regclass),
    id_radicacion_sa integer,
    afi_rad_na integer,
    actividad integer,
    usuario_gestion character varying,
    fecha_gestion timestamp with time zone,
    fecha_asignacion timestamp with time zone DEFAULT now(),
    observacion text
);

ALTER SEQUENCE public.afa_trazabilidad_id_trazabilidad_seq OWNED BY public.afa_trazabilidad.id_trazabilidad;


--
-- Name: campos; Type: TABLE; Schema: public; Owner: escobar
--

CREATE SEQUENCE IF NOT EXISTS public.campos_id_campo_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

CREATE TABLE IF NOT EXISTS public.campos (
    id_campo integer NOT NULL DEFAULT nextval('public.campos_id_campo_seq'::regclass),
    nombre character varying(255) NOT NULL,
    label character varying(255) NOT NULL,
    id_tipo_campo integer NOT NULL,
    help_user character varying
);

ALTER SEQUENCE public.campos_id_campo_seq OWNED BY public.campos.id_campo;


--
-- Name: tipo_solicitud_campo; Type: TABLE; Schema: public; Owner: escobar
--

CREATE SEQUENCE IF NOT EXISTS public.tipo_solicitud_campo_id_tipo_solicitud_campo_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

CREATE TABLE IF NOT EXISTS public.tipo_solicitud_campo (
    id_tipo_solicitud_campo integer NOT NULL DEFAULT nextval('public.tipo_solicitud_campo_id_tipo_solicitud_campo_seq'::regclass),
    id_tipo_solicitud integer,
    id_campo integer,
    activo boolean DEFAULT true,
    valor_default character varying,
    orden integer
);

ALTER SEQUENCE public.tipo_solicitud_campo_id_tipo_solicitud_campo_seq OWNED BY public.tipo_solicitud_campo.id_tipo_solicitud_campo;


--
-- Name: valores; Type: TABLE; Schema: public; Owner: escobar
--

CREATE SEQUENCE IF NOT EXISTS public.valores_id_valor_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

CREATE TABLE IF NOT EXISTS public.valores (
    id_valor integer NOT NULL DEFAULT nextval('public.valores_id_valor_seq'::regclass),
    id_radicacion_sa integer NOT NULL,
    id_tipo_solicitud_campo integer NOT NULL,
    valor text NOT NULL
);

ALTER SEQUENCE public.valores_id_valor_seq OWNED BY public.valores.id_valor;
