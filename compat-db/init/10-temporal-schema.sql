--
-- PostgreSQL database dump
--

\restrict D6394tWrleeRfzfmQHAnxhEVU8sxbafwtX2rqQcXWwmVqQPVAfOblLgrzFAZnhq

-- Dumped from database version 15.17
-- Dumped by pg_dump version 15.17

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: auxilios; Type: SCHEMA; Schema: -; Owner: escobar
--

CREATE SCHEMA auxilios;


ALTER SCHEMA auxilios OWNER TO escobar;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: fun_bancos; Type: TABLE; Schema: auxilios; Owner: escobar
--

CREATE TABLE auxilios.fun_bancos (
    cod_banco text NOT NULL,
    nombre_banco text
);


ALTER TABLE auxilios.fun_bancos OWNER TO escobar;

--
-- Name: fun_log_cierre_masivo; Type: TABLE; Schema: auxilios; Owner: escobar
--

CREATE TABLE auxilios.fun_log_cierre_masivo (
    na integer NOT NULL,
    tramite text,
    id_reclamante text,
    valor text,
    cod_banco text,
    tipo_cta text,
    cuenta text,
    usuario_carga text,
    estado text,
    fecha_carga timestamp without time zone DEFAULT now()
);


ALTER TABLE auxilios.fun_log_cierre_masivo OWNER TO escobar;

--
-- Name: fun_log_cierre_masivo_na_seq; Type: SEQUENCE; Schema: auxilios; Owner: escobar
--

CREATE SEQUENCE auxilios.fun_log_cierre_masivo_na_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE auxilios.fun_log_cierre_masivo_na_seq OWNER TO escobar;

--
-- Name: fun_log_cierre_masivo_na_seq; Type: SEQUENCE OWNED BY; Schema: auxilios; Owner: escobar
--

ALTER SEQUENCE auxilios.fun_log_cierre_masivo_na_seq OWNED BY auxilios.fun_log_cierre_masivo.na;


--
-- Name: fun_log_reclamante; Type: TABLE; Schema: auxilios; Owner: escobar
--

CREATE TABLE auxilios.fun_log_reclamante (
    na integer NOT NULL,
    tramite text,
    id_reclamante text,
    usuario text,
    estado_anterior text,
    estado_actual text,
    fecha_insert timestamp without time zone DEFAULT now()
);


ALTER TABLE auxilios.fun_log_reclamante OWNER TO escobar;

--
-- Name: fun_log_reclamante_na_seq; Type: SEQUENCE; Schema: auxilios; Owner: escobar
--

CREATE SEQUENCE auxilios.fun_log_reclamante_na_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE auxilios.fun_log_reclamante_na_seq OWNER TO escobar;

--
-- Name: fun_log_reclamante_na_seq; Type: SEQUENCE OWNED BY; Schema: auxilios; Owner: escobar
--

ALTER SEQUENCE auxilios.fun_log_reclamante_na_seq OWNED BY auxilios.fun_log_reclamante.na;


--
-- Name: fun_pagos_reclamantes; Type: TABLE; Schema: auxilios; Owner: escobar
--

CREATE TABLE auxilios.fun_pagos_reclamantes (
    id integer NOT NULL,
    tramite text,
    id_reclamante text,
    forma_pago text,
    entidad_bancaria text,
    tipo_cuenta text,
    numero_cuenta text,
    valor_reconocido numeric
);


ALTER TABLE auxilios.fun_pagos_reclamantes OWNER TO escobar;

--
-- Name: fun_pagos_reclamantes_id_seq; Type: SEQUENCE; Schema: auxilios; Owner: escobar
--

CREATE SEQUENCE auxilios.fun_pagos_reclamantes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE auxilios.fun_pagos_reclamantes_id_seq OWNER TO escobar;

--
-- Name: fun_pagos_reclamantes_id_seq; Type: SEQUENCE OWNED BY; Schema: auxilios; Owner: escobar
--

ALTER SEQUENCE auxilios.fun_pagos_reclamantes_id_seq OWNED BY auxilios.fun_pagos_reclamantes.id;


--
-- Name: fun_reclamantes; Type: TABLE; Schema: auxilios; Owner: escobar
--

CREATE TABLE auxilios.fun_reclamantes (
    id_ben integer NOT NULL,
    tramite text,
    tipoid_beneficiario text,
    identificacion text,
    nombre_beneficiario text,
    estado_reclamante text
);


ALTER TABLE auxilios.fun_reclamantes OWNER TO escobar;

--
-- Name: fun_reclamantes_id_ben_seq; Type: SEQUENCE; Schema: auxilios; Owner: escobar
--

CREATE SEQUENCE auxilios.fun_reclamantes_id_ben_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE auxilios.fun_reclamantes_id_ben_seq OWNER TO escobar;

--
-- Name: fun_reclamantes_id_ben_seq; Type: SEQUENCE OWNED BY; Schema: auxilios; Owner: escobar
--

ALTER SEQUENCE auxilios.fun_reclamantes_id_ben_seq OWNED BY auxilios.fun_reclamantes.id_ben;


--
-- Name: fun_solicitudes; Type: TABLE; Schema: auxilios; Owner: escobar
--

CREATE TABLE auxilios.fun_solicitudes (
    tramite text,
    estado_flujo text
);


ALTER TABLE auxilios.fun_solicitudes OWNER TO escobar;

--
-- Name: not_bloqueo; Type: TABLE; Schema: auxilios; Owner: escobar
--

CREATE TABLE auxilios.not_bloqueo (
    na integer NOT NULL,
    estado integer,
    usuario text,
    fecha_bloqueo timestamp without time zone DEFAULT now()
);


ALTER TABLE auxilios.not_bloqueo OWNER TO escobar;

--
-- Name: not_bloqueo_na_seq; Type: SEQUENCE; Schema: auxilios; Owner: escobar
--

CREATE SEQUENCE auxilios.not_bloqueo_na_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE auxilios.not_bloqueo_na_seq OWNER TO escobar;

--
-- Name: not_bloqueo_na_seq; Type: SEQUENCE OWNED BY; Schema: auxilios; Owner: escobar
--

ALTER SEQUENCE auxilios.not_bloqueo_na_seq OWNED BY auxilios.not_bloqueo.na;


--
-- Name: not_documentos; Type: TABLE; Schema: auxilios; Owner: escobar
--

CREATE TABLE auxilios.not_documentos (
    id_documento integer NOT NULL,
    desc_documento text
);


ALTER TABLE auxilios.not_documentos OWNER TO escobar;

--
-- Name: not_documentos_prestaciones; Type: TABLE; Schema: auxilios; Owner: escobar
--

CREATE TABLE auxilios.not_documentos_prestaciones (
    id_documento integer,
    id_prestacion integer,
    obligatorio integer
);


ALTER TABLE auxilios.not_documentos_prestaciones OWNER TO escobar;

--
-- Name: not_estado_post; Type: TABLE; Schema: auxilios; Owner: escobar
--

CREATE TABLE auxilios.not_estado_post (
    estado_post_id integer NOT NULL,
    estado_post text,
    activo boolean
);


ALTER TABLE auxilios.not_estado_post OWNER TO escobar;

--
-- Name: not_estados_post_solicitud; Type: TABLE; Schema: auxilios; Owner: escobar
--

CREATE TABLE auxilios.not_estados_post_solicitud (
    id_estado_post_solicitud integer NOT NULL,
    solicitud_id integer,
    id_estado_post integer,
    marca boolean,
    observacion text,
    user_insert text,
    usuario_solucion text,
    fecha_insert timestamp without time zone,
    fecha_solucion timestamp without time zone
);


ALTER TABLE auxilios.not_estados_post_solicitud OWNER TO escobar;

--
-- Name: not_estados_post_solicitud_id_estado_post_solicitud_seq; Type: SEQUENCE; Schema: auxilios; Owner: escobar
--

CREATE SEQUENCE auxilios.not_estados_post_solicitud_id_estado_post_solicitud_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE auxilios.not_estados_post_solicitud_id_estado_post_solicitud_seq OWNER TO escobar;

--
-- Name: not_estados_post_solicitud_id_estado_post_solicitud_seq; Type: SEQUENCE OWNED BY; Schema: auxilios; Owner: escobar
--

ALTER SEQUENCE auxilios.not_estados_post_solicitud_id_estado_post_solicitud_seq OWNED BY auxilios.not_estados_post_solicitud.id_estado_post_solicitud;


--
-- Name: not_imagenes_temporal; Type: TABLE; Schema: auxilios; Owner: escobar
--

CREATE TABLE auxilios.not_imagenes_temporal (
    na text,
    clasificacion text
);


ALTER TABLE auxilios.not_imagenes_temporal OWNER TO escobar;

--
-- Name: not_log; Type: TABLE; Schema: auxilios; Owner: escobar
--

CREATE TABLE auxilios.not_log (
    solicitud_id integer,
    usuario text,
    estado_anterior text,
    estado_actual text,
    observacion text
);


ALTER TABLE auxilios.not_log OWNER TO escobar;

--
-- Name: not_marca_imagenes; Type: TABLE; Schema: auxilios; Owner: escobar
--

CREATE TABLE auxilios.not_marca_imagenes (
    id_marca integer NOT NULL,
    ax text,
    pn integer,
    tramite text,
    marca integer,
    solicitud_id integer
);


ALTER TABLE auxilios.not_marca_imagenes OWNER TO escobar;

--
-- Name: not_marca_imagenes_id_marca_seq; Type: SEQUENCE; Schema: auxilios; Owner: escobar
--

CREATE SEQUENCE auxilios.not_marca_imagenes_id_marca_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE auxilios.not_marca_imagenes_id_marca_seq OWNER TO escobar;

--
-- Name: not_marca_imagenes_id_marca_seq; Type: SEQUENCE OWNED BY; Schema: auxilios; Owner: escobar
--

ALTER SEQUENCE auxilios.not_marca_imagenes_id_marca_seq OWNED BY auxilios.not_marca_imagenes.id_marca;


--
-- Name: not_pagos_reclamantes; Type: TABLE; Schema: auxilios; Owner: escobar
--

CREATE TABLE auxilios.not_pagos_reclamantes (
    solicitud_id integer,
    id_reclamante text,
    apoderado text,
    nom_apoderado text,
    tel_apoderado text,
    forma_pago text,
    numero_cuenta text,
    entidad_bancaria text,
    tipo_cuenta text
);


ALTER TABLE auxilios.not_pagos_reclamantes OWNER TO escobar;

--
-- Name: not_reclamantes; Type: TABLE; Schema: auxilios; Owner: escobar
--

CREATE TABLE auxilios.not_reclamantes (
    id_ben integer NOT NULL,
    not_solicitud_id integer,
    tramite text,
    tipoid_beneficiario text,
    identificacion text,
    nombre_beneficiario text,
    direccion text,
    telefono_beneficiario text,
    estado_reclamante text
);


ALTER TABLE auxilios.not_reclamantes OWNER TO escobar;

--
-- Name: not_reclamantes_id_ben_seq; Type: SEQUENCE; Schema: auxilios; Owner: escobar
--

CREATE SEQUENCE auxilios.not_reclamantes_id_ben_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE auxilios.not_reclamantes_id_ben_seq OWNER TO escobar;

--
-- Name: not_reclamantes_id_ben_seq; Type: SEQUENCE OWNED BY; Schema: auxilios; Owner: escobar
--

ALTER SEQUENCE auxilios.not_reclamantes_id_ben_seq OWNED BY auxilios.not_reclamantes.id_ben;


--
-- Name: not_relacion_imagenes; Type: TABLE; Schema: auxilios; Owner: escobar
--

CREATE TABLE auxilios.not_relacion_imagenes (
    pn integer,
    tramite text,
    id_prestacion integer,
    solicitud_id integer,
    id_documento integer,
    modalidad text,
    eps text
);


ALTER TABLE auxilios.not_relacion_imagenes OWNER TO escobar;

--
-- Name: not_solicitudes; Type: TABLE; Schema: auxilios; Owner: escobar
--

CREATE TABLE auxilios.not_solicitudes (
    solicitud_id integer,
    tramite text,
    id_afiliado text,
    tipo_solicitud text,
    estado_flujo text,
    proceso text
);


ALTER TABLE auxilios.not_solicitudes OWNER TO escobar;

--
-- Name: brafiliadosarp; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.brafiliadosarp (
    sr integer NOT NULL,
    li smallint NOT NULL,
    f28 numeric,
    f36 integer,
    f29 smallint,
    f30 varchar,
    f31 varchar(20),
    f32 varchar(20),
    f33 varchar(30),
    f34 varchar(1),
    f35 numeric,
    f37 varchar(40),
    f38 numeric,
    f40 varchar(15),
    f41 varchar(15),
    e0 smallint,
    e1 smallint,
    e2 smallint,
    e3 smallint,
    e4 smallint,
    e5 smallint,
    e6 smallint,
    e7 smallint,
    e8 smallint,
    e9 smallint,
    e10 smallint,
    e11 smallint,
    e12 smallint,
    ob text,
    lt integer NOT NULL,
    combo40 varchar(40),
    combo41 varchar(40),
    fechainsert timestamp without time zone DEFAULT now(),
    telefono numeric,
    celular numeric,
    mail varchar,
    direccion varchar,
    municipio varchar,
    zona varchar,
    localidad varchar,
    departamento varchar,
    modalidad varchar,
    jornada varchar,
    trabajoalturas integer DEFAULT 0,
    tipo_salario varchar
);


ALTER TABLE public.brafiliadosarp OWNER TO escobar;

--
-- Name: brcentrot; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.brcentrot (
    sr integer NOT NULL,
    codigoct varchar NOT NULL,
    codigoactividad integer,
    nombreactividad varchar,
    totaltrabajadores numeric,
    claseriesgo varchar,
    montocotizacion numeric,
    ciudad varchar,
    departamento varchar,
    zona varchar,
    direccion varchar,
    telefono numeric,
    tipodocumento varchar,
    id_responsable varchar,
    primerapellido varchar,
    segundoapellido varchar,
    primernombre varchar,
    segundonombre varchar,
    mail varchar,
    lote numeric NOT NULL
);


ALTER TABLE public.brcentrot OWNER TO escobar;

--
-- Name: brempresasarp; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.brempresasarp (
    sr integer NOT NULL,
    f01 integer,
    f50 smallint NOT NULL,
    f48 numeric,
    f51 varchar,
    f15 numeric,
    f16 smallint,
    f12 varchar,
    f14 numeric,
    f20 numeric,
    f06 varchar(40),
    f04 varchar(20),
    f05 integer,
    f27 smallint,
    f25 smallint,
    f49 varchar(1),
    f02 numeric,
    f56 smallint,
    f63 integer,
    f24 smallint,
    f53 numeric,
    f18 varchar,
    f23 smallint,
    f57 numeric,
    f09 integer,
    f59 integer,
    f62 numeric,
    f55 varchar,
    f10 varchar(1),
    f03 smallint,
    f08 smallint,
    f07 double precision DEFAULT 0,
    f17 smallint,
    f11 numeric,
    f13 varchar(15),
    f19 integer,
    f54 smallint,
    f58 smallint,
    f60 smallint,
    f61 numeric,
    f69 varchar(50),
    f64 smallint,
    f65 numeric,
    f70 varchar(50),
    f66 smallint,
    f67 numeric,
    f71 varchar(50),
    f68 smallint,
    doccont1 numeric,
    nomcont1 varchar(50),
    carcont1 varchar(30),
    dircont1 varchar(30),
    ciucont1 varchar,
    nomciucont1 varchar(30),
    depcont1 varchar,
    nomdepcont1 varchar(30),
    telcont1 numeric,
    telcont21 numeric,
    emailcont1 varchar,
    doccont2 numeric,
    nomcont2 varchar(30),
    carcont2 varchar(30),
    dircont2 varchar(30),
    ciucont2 varchar,
    nomciucont2 varchar(30),
    depcont2 varchar,
    nomdepcont2 varchar(30),
    telcont2 numeric,
    telcont22 numeric,
    emailcont2 varchar,
    dev numeric,
    fp integer,
    tp varchar(1),
    ci smallint,
    cf smallint,
    lt integer NOT NULL,
    e0 smallint,
    e1 smallint,
    e2 smallint,
    e3 smallint,
    e4 smallint,
    e5 smallint,
    e6 smallint,
    e7 smallint,
    e8 smallint,
    e9 smallint,
    e10 smallint,
    e11 smallint,
    e12 smallint,
    e13 smallint,
    e14 smallint,
    e15 smallint,
    e16 smallint,
    e17 smallint,
    e18 smallint,
    e19 smallint,
    e20 smallint,
    vs smallint,
    zo smallint,
    d1 varchar(1),
    us varchar(8),
    ob text,
    combo50 varchar(2),
    combo15 varchar(40),
    combo16 varchar(25),
    combo05 varchar,
    combo56 varchar(40),
    combo24 varchar(40),
    combo23 varchar(40),
    combo57 varchar(40),
    pi varchar(80),
    clase varchar,
    obdev varchar(80),
    fechainsert timestamp without time zone DEFAULT now(),
    contratoant numeric,
    tipoempresa varchar(1),
    grupoecono varchar,
    tipoafiliacion varchar,
    tipoaportante numeric,
    tipoafiliado varchar,
    tipocodigo numeric,
    subtipoafiliado varchar,
    subtipocodigo numeric,
    zona varchar,
    localidad varchar,
    departamento varchar,
    aut46 smallint,
    aut47 smallint,
    aut48 smallint
);


ALTER TABLE public.brempresasarp OWNER TO escobar;

--
-- Name: brwdcomisiones; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.brwdcomisiones (
    sr numeric NOT NULL,
    linea numeric NOT NULL,
    vendedor numeric NOT NULL,
    codigo_vendedor numeric NOT NULL,
    venta numeric NOT NULL,
    porcentaje numeric NOT NULL,
    lote numeric NOT NULL
);


ALTER TABLE public.brwdcomisiones OWNER TO escobar;

--
-- Name: brwddias; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.brwddias (
    sr integer NOT NULL,
    dia varchar NOT NULL,
    h1 varchar,
    h2 varchar,
    h3 varchar,
    h4 varchar,
    h5 varchar,
    h6 varchar,
    h7 varchar,
    h8 varchar,
    h9 varchar,
    h10 varchar,
    h11 varchar,
    h12 varchar,
    h13 varchar,
    h14 varchar,
    h15 varchar,
    h16 varchar,
    h17 varchar,
    h18 varchar,
    h19 varchar,
    h20 varchar,
    h21 varchar,
    h22 varchar,
    h23 varchar,
    h24 varchar,
    lote numeric NOT NULL
);


ALTER TABLE public.brwddias OWNER TO escobar;

--
-- Name: brwdestudiantes; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.brwdestudiantes (
    sr numeric NOT NULL,
    linea smallint DEFAULT 0 NOT NULL,
    codigo_ct numeric NOT NULL,
    tipodocumento varchar NOT NULL,
    documento varchar NOT NULL,
    primer_apellido varchar NOT NULL,
    segundo_apellido varchar,
    primer_nombre varchar NOT NULL,
    segundo_nombre varchar,
    fecha_nacimiento numeric NOT NULL,
    sexo varchar NOT NULL,
    cargo varchar NOT NULL,
    salario numeric NOT NULL,
    eps varchar NOT NULL,
    afp varchar NOT NULL,
    direccion varchar NOT NULL,
    telefono numeric NOT NULL,
    celular numeric NOT NULL,
    correo varchar NOT NULL,
    ciudad varchar NOT NULL,
    localidad varchar NOT NULL,
    zona varchar NOT NULL,
    departamento varchar NOT NULL,
    jornada varchar NOT NULL,
    modalidad varchar NOT NULL,
    codigo_tipo_trabajador varchar NOT NULL,
    tipo_trabajador varchar NOT NULL,
    subtipo_afiliado varchar,
    actividad_especial varchar,
    codigo_actividad numeric NOT NULL,
    fecha_inicio numeric NOT NULL,
    fecha_final numeric NOT NULL,
    meses numeric NOT NULL,
    tipo_contrato varchar NOT NULL,
    monto_contrato numeric NOT NULL,
    lunes varchar,
    martes varchar,
    miercoles varchar,
    jueves varchar,
    viernes varchar,
    sabado varchar,
    domingo varchar,
    d1 varchar,
    d2 varchar,
    d3 varchar,
    d4 varchar,
    d5 varchar,
    d6 varchar,
    d7 varchar,
    d8 varchar,
    d9 varchar,
    d10 varchar,
    d11 varchar,
    d12 varchar,
    d13 varchar,
    d14 varchar,
    d15 varchar,
    d16 varchar,
    d17 varchar,
    d18 varchar,
    d19 varchar,
    d20 varchar,
    d21 varchar,
    d22 varchar,
    d23 varchar,
    d24 varchar,
    lote numeric NOT NULL,
    tipo_salario varchar
);


ALTER TABLE public.brwdestudiantes OWNER TO escobar;

--
-- Name: brwdindependientes; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.brwdindependientes (
    sr numeric NOT NULL,
    linea smallint DEFAULT 0 NOT NULL,
    tipodocumento varchar NOT NULL,
    documento varchar NOT NULL,
    primer_apellido varchar NOT NULL,
    segundo_apellido varchar,
    primer_nombre varchar NOT NULL,
    segundo_nombre varchar,
    fecha_nacimiento numeric NOT NULL,
    sexo varchar NOT NULL,
    direccion varchar NOT NULL,
    departamento varchar NOT NULL,
    municipio varchar NOT NULL,
    zona varchar NOT NULL,
    localidad varchar,
    telefono numeric NOT NULL,
    celular numeric NOT NULL,
    correo varchar NOT NULL,
    eps varchar NOT NULL,
    codigo_eps varchar,
    afp varchar,
    codigo_afp varchar,
    arl_anterior varchar,
    codigo_arl_anterior varchar,
    tipo_cotizante varchar NOT NULL,
    subtipo_cotizante varchar,
    modalidad varchar NOT NULL,
    actividad_especial varchar,
    tipo_contrato varchar NOT NULL,
    transporte varchar,
    fecha_inicio_contrato numeric NOT NULL,
    fecha_fin_contrato numeric NOT NULL,
    meses_contrato numeric NOT NULL,
    valor_contrato numeric NOT NULL,
    valor_mensual numeric NOT NULL,
    ibc numeric NOT NULL,
    actividad_economica varchar NOT NULL,
    nombre_actividad varchar NOT NULL,
    clase_riesgo varchar,
    tasa_riesgo varchar,
    lunes varchar,
    martes varchar,
    miercoles varchar,
    jueves varchar,
    viernes varchar,
    sabado varchar,
    domingo varchar,
    d1 varchar,
    d2 varchar,
    d3 varchar,
    d4 varchar,
    d5 varchar,
    d6 varchar,
    d7 varchar,
    d8 varchar,
    d9 varchar,
    d10 varchar,
    d11 varchar,
    d12 varchar,
    d13 varchar,
    d14 varchar,
    d15 varchar,
    d16 varchar,
    d17 varchar,
    d18 varchar,
    d19 varchar,
    d20 varchar,
    d21 varchar,
    d22 varchar,
    d23 varchar,
    d24 varchar,
    codigo_ct varchar NOT NULL,
    nombre_ct varchar,
    actividad_economica_ct varchar,
    clase_riesgo_ct varchar,
    tasa_riesgo_ct varchar,
    direccion_ct varchar,
    departamento_ct varchar,
    ciudad_ct varchar,
    zona_ct varchar NOT NULL,
    telefono_ct numeric,
    celular_ct numeric,
    correo_ct varchar,
    localidad_ct varchar,
    lote numeric NOT NULL,
    tipo_salario varchar
);


ALTER TABLE public.brwdindependientes OWNER TO escobar;

--
-- Name: bkempresasarp; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.bkempresasarp (
    sr integer NOT NULL,
    f01 integer,
    f50 smallint NOT NULL,
    f48 numeric,
    f51 varchar,
    f15 numeric,
    f16 smallint,
    f12 varchar,
    f14 numeric,
    f20 numeric,
    f06 varchar(40),
    f04 varchar(20),
    f05 integer,
    f27 smallint,
    f25 smallint,
    f49 varchar(1),
    f02 numeric,
    f56 smallint,
    f63 integer,
    f24 smallint,
    f53 numeric,
    f18 varchar,
    f23 smallint,
    f57 numeric,
    f09 integer,
    f59 integer,
    f62 numeric,
    f55 varchar,
    f10 varchar(1),
    f03 smallint,
    f08 smallint,
    f07 double precision,
    f17 smallint,
    f11 numeric,
    f13 varchar(15),
    f19 integer,
    f54 smallint,
    f58 smallint,
    f60 smallint,
    f61 numeric,
    f69 varchar(50),
    f64 smallint,
    f65 numeric,
    f70 varchar(50),
    f66 smallint,
    f67 numeric,
    f71 varchar(50),
    f68 smallint,
    doccont1 numeric,
    nomcont1 varchar(50),
    carcont1 varchar(30),
    dircont1 varchar,
    ciucont1 varchar,
    nomciucont1 varchar(30),
    depcont1 varchar,
    nomdepcont1 varchar(30),
    telcont1 numeric,
    telcont21 numeric,
    emailcont1 varchar,
    doccont2 numeric,
    nomcont2 varchar(30),
    carcont2 varchar(30),
    dircont2 varchar(30),
    ciucont2 varchar,
    nomciucont2 varchar(30),
    depcont2 varchar,
    nomdepcont2 varchar(30),
    telcont2 numeric,
    telcont22 numeric,
    emailcont2 varchar,
    dev numeric,
    fp integer,
    tp varchar(1),
    ci smallint,
    cf smallint,
    lt integer,
    e0 smallint,
    e1 smallint,
    e2 smallint,
    e3 smallint,
    e4 smallint,
    e5 smallint,
    e6 smallint,
    e7 smallint,
    e8 smallint,
    e9 smallint,
    e10 smallint,
    e11 smallint,
    e12 smallint,
    e13 smallint,
    e14 smallint,
    e15 smallint,
    e16 smallint,
    e17 smallint,
    e18 smallint,
    e19 smallint,
    e20 smallint,
    vs smallint,
    zo smallint,
    d1 varchar(1),
    us varchar(8),
    ob text,
    combo50 varchar(2),
    combo15 varchar(40),
    combo16 varchar(25),
    combo05 varchar,
    combo56 varchar(40),
    combo24 varchar(40),
    combo23 varchar(40),
    combo57 varchar(40),
    pi varchar(80),
    clase varchar,
    obdev varchar,
    contratoant numeric,
    tipoempresa varchar(1),
    grupoecono varchar,
    tipoafiliacion varchar,
    tipoaportante numeric,
    tipoafiliado varchar,
    tipocodigo numeric,
    subtipoafiliado varchar,
    subtipocodigo numeric,
    zona varchar,
    localidad varchar,
    departamento varchar,
    aut46 smallint,
    aut47 smallint,
    aut48 smallint
);


ALTER TABLE public.bkempresasarp OWNER TO escobar;

--
-- Name: bkafiliadosarp; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.bkafiliadosarp (
    sr integer NOT NULL,
    li smallint NOT NULL,
    f28 numeric,
    f36 integer,
    f29 smallint,
    f30 varchar,
    f31 varchar(20),
    f32 varchar(20),
    f33 varchar(30),
    f34 varchar(1),
    f35 numeric,
    f37 varchar(40),
    f38 numeric,
    f40 varchar(15),
    f41 varchar(15),
    e0 smallint,
    e1 smallint,
    e2 smallint,
    e3 smallint,
    e4 smallint,
    e5 smallint,
    e6 smallint,
    e7 smallint,
    e8 smallint,
    e9 smallint,
    e10 smallint,
    e11 smallint,
    e12 smallint,
    ob text,
    combo40 varchar(40),
    combo41 varchar(40),
    lt integer NOT NULL,
    telefono numeric,
    celular numeric,
    mail varchar,
    direccion varchar,
    municipio varchar,
    zona varchar,
    localidad varchar,
    departamento varchar,
    modalidad varchar,
    jornada varchar,
    trabajoalturas integer DEFAULT 0,
    tipo_salario varchar
);


ALTER TABLE public.bkafiliadosarp OWNER TO escobar;

--
-- Name: bkwddias; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.bkwddias (
    sr integer NOT NULL,
    dia varchar NOT NULL,
    h1 varchar,
    h2 varchar,
    h3 varchar,
    h4 varchar,
    h5 varchar,
    h6 varchar,
    h7 varchar,
    h8 varchar,
    h9 varchar,
    h10 varchar,
    h11 varchar,
    h12 varchar,
    h13 varchar,
    h14 varchar,
    h15 varchar,
    h16 varchar,
    h17 varchar,
    h18 varchar,
    h19 varchar,
    h20 varchar,
    h21 varchar,
    h22 varchar,
    h23 varchar,
    h24 varchar,
    lote numeric NOT NULL
);


ALTER TABLE public.bkwddias OWNER TO escobar;

--
-- Name: bkcentrot; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.bkcentrot (
    sr integer NOT NULL,
    codigoct varchar NOT NULL,
    codigoactividad integer,
    nombreactividad varchar,
    totaltrabajadores numeric,
    claseriesgo varchar,
    montocotizacion numeric,
    ciudad varchar,
    departamento varchar,
    zona varchar,
    direccion varchar,
    telefono numeric,
    tipodocumento varchar,
    id_responsable varchar,
    primerapellido varchar,
    segundoapellido varchar,
    primernombre varchar,
    segundonombre varchar,
    mail varchar,
    lote numeric
);


ALTER TABLE public.bkcentrot OWNER TO escobar;

--
-- Name: bkwdestudiantes; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.bkwdestudiantes (
    sr numeric NOT NULL,
    linea smallint DEFAULT 0 NOT NULL,
    codigo_ct numeric NOT NULL,
    tipodocumento varchar NOT NULL,
    documento varchar NOT NULL,
    primer_apellido varchar NOT NULL,
    segundo_apellido varchar,
    primer_nombre varchar NOT NULL,
    segundo_nombre varchar,
    fecha_nacimiento numeric NOT NULL,
    sexo varchar NOT NULL,
    cargo varchar NOT NULL,
    salario numeric NOT NULL,
    eps varchar NOT NULL,
    afp varchar NOT NULL,
    direccion varchar NOT NULL,
    telefono numeric NOT NULL,
    celular numeric NOT NULL,
    correo varchar NOT NULL,
    ciudad varchar NOT NULL,
    localidad varchar NOT NULL,
    zona varchar NOT NULL,
    departamento varchar NOT NULL,
    jornada varchar NOT NULL,
    modalidad varchar NOT NULL,
    codigo_tipo_trabajador varchar NOT NULL,
    tipo_trabajador varchar NOT NULL,
    subtipo_afiliado varchar,
    actividad_especial varchar,
    codigo_actividad numeric NOT NULL,
    fecha_inicio numeric NOT NULL,
    fecha_final numeric NOT NULL,
    meses numeric NOT NULL,
    tipo_contrato varchar NOT NULL,
    monto_contrato numeric NOT NULL,
    lunes varchar,
    martes varchar,
    miercoles varchar,
    jueves varchar,
    viernes varchar,
    sabado varchar,
    domingo varchar,
    d1 varchar,
    d2 varchar,
    d3 varchar,
    d4 varchar,
    d5 varchar,
    d6 varchar,
    d7 varchar,
    d8 varchar,
    d9 varchar,
    d10 varchar,
    d11 varchar,
    d12 varchar,
    d13 varchar,
    d14 varchar,
    d15 varchar,
    d16 varchar,
    d17 varchar,
    d18 varchar,
    d19 varchar,
    d20 varchar,
    d21 varchar,
    d22 varchar,
    d23 varchar,
    d24 varchar,
    lote numeric NOT NULL,
    tipo_salario varchar
);


ALTER TABLE public.bkwdestudiantes OWNER TO escobar;

--
-- Name: bkwdindependientes; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.bkwdindependientes (
    sr numeric NOT NULL,
    linea smallint DEFAULT 0 NOT NULL,
    tipodocumento varchar NOT NULL,
    documento varchar NOT NULL,
    primer_apellido varchar NOT NULL,
    segundo_apellido varchar,
    primer_nombre varchar NOT NULL,
    segundo_nombre varchar,
    fecha_nacimiento numeric NOT NULL,
    sexo varchar NOT NULL,
    direccion varchar NOT NULL,
    departamento varchar NOT NULL,
    municipio varchar NOT NULL,
    zona varchar NOT NULL,
    localidad varchar,
    telefono numeric NOT NULL,
    celular numeric NOT NULL,
    correo varchar NOT NULL,
    eps varchar NOT NULL,
    codigo_eps varchar,
    afp varchar,
    codigo_afp varchar,
    arl_anterior varchar,
    codigo_arl_anterior varchar,
    tipo_cotizante varchar NOT NULL,
    subtipo_cotizante varchar,
    modalidad varchar NOT NULL,
    actividad_especial varchar,
    tipo_contrato varchar NOT NULL,
    transporte varchar,
    fecha_inicio_contrato numeric NOT NULL,
    fecha_fin_contrato numeric NOT NULL,
    meses_contrato numeric NOT NULL,
    valor_contrato numeric NOT NULL,
    valor_mensual numeric NOT NULL,
    ibc numeric NOT NULL,
    actividad_economica varchar NOT NULL,
    nombre_actividad varchar NOT NULL,
    clase_riesgo varchar,
    tasa_riesgo varchar,
    lunes varchar,
    martes varchar,
    miercoles varchar,
    jueves varchar,
    viernes varchar,
    sabado varchar,
    domingo varchar,
    d1 varchar,
    d2 varchar,
    d3 varchar,
    d4 varchar,
    d5 varchar,
    d6 varchar,
    d7 varchar,
    d8 varchar,
    d9 varchar,
    d10 varchar,
    d11 varchar,
    d12 varchar,
    d13 varchar,
    d14 varchar,
    d15 varchar,
    d16 varchar,
    d17 varchar,
    d18 varchar,
    d19 varchar,
    d20 varchar,
    d21 varchar,
    d22 varchar,
    d23 varchar,
    d24 varchar,
    codigo_ct varchar NOT NULL,
    nombre_ct varchar,
    actividad_economica_ct varchar,
    clase_riesgo_ct varchar,
    tasa_riesgo_ct varchar,
    direccion_ct varchar,
    departamento_ct varchar,
    ciudad_ct varchar,
    zona_ct varchar NOT NULL,
    telefono_ct numeric,
    celular_ct numeric,
    correo_ct varchar,
    localidad_ct varchar,
    lote numeric NOT NULL,
    tipo_salario varchar
);


ALTER TABLE public.bkwdindependientes OWNER TO escobar;

--
-- Name: bkwdcomisiones; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.bkwdcomisiones (
    sr numeric NOT NULL,
    linea numeric NOT NULL,
    vendedor numeric NOT NULL,
    codigo_vendedor numeric NOT NULL,
    venta numeric NOT NULL,
    porcentaje numeric NOT NULL,
    lote numeric NOT NULL
);


ALTER TABLE public.bkwdcomisiones OWNER TO escobar;

--
-- Name: afi_rad; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.afi_rad (
    afi_rad_na bigint NOT NULL,
    afi_rad_numero numeric NOT NULL,
    afi_rad_contrato numeric NOT NULL,
    afi_rad_razonsoc varchar(150) NOT NULL,
    afi_rad_folios varchar(4) NOT NULL,
    afi_rad_usuario varchar(12) NOT NULL,
    afi_rad_estado varchar(12) NOT NULL,
    afi_rad_envio numeric,
    afi_rad_sucursal numeric NOT NULL,
    afi_fecharadica varchar(12) DEFAULT to_char(now(), 'YYYYmmdd'::text),
    afi_fechainsert varchar,
    afi_rad_obs varchar(80),
    afi_rad_clase varchar,
    afi_rad_fechadigitacion varchar(8) DEFAULT 0,
    afi_rad_fechaplano varchar(8) DEFAULT 0,
    afi_rad_fechadevol varchar(8) DEFAULT 0,
    afi_rad_nit bigint,
    afi_rad_fecharecibido varchar(8) DEFAULT 0,
    afi_rad_contratom numeric,
    afi_rad_sede numeric,
    afi_rad_trabajadores varchar(10),
    afi_rad_ruta varchar(150),
    fec_apolo varchar(20) DEFAULT 0,
    impreso numeric DEFAULT 0,
    afi_rad_inivig varchar(20),
    afi_rad_plano_det varchar(250) DEFAULT 0,
    afi_rad_ima_det varchar(250) DEFAULT 0,
    afi_rad_arc_det varchar(250) DEFAULT 0,
    fecha_detectar varchar DEFAULT 0,
    afi_rad_causal_dev varchar,
    afi_rad_canal varchar
);


ALTER TABLE public.afi_rad OWNER TO escobar;

--
-- Name: afi_devoluciones; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.afi_devoluciones (
    dev_numdev integer NOT NULL,
    dev_solicitud varchar(13) NOT NULL,
    dev_coddev integer NOT NULL,
    dev_observacion varchar(250),
    dev_sr integer NOT NULL,
    dev_fechainsert timestamp without time zone DEFAULT now(),
    dev_estado varchar(1),
    dev_fechamodificacion varchar(8),
    dev_usuario varchar(20),
    dev_sucursal varchar(3),
    dev_na integer NOT NULL,
    dev_respuesta varchar(300),
    dev_fechacargue varchar(8)
);


ALTER TABLE public.afi_devoluciones OWNER TO escobar;

--
-- Name: estadistico; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.estadistico (
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


ALTER TABLE public.estadistico OWNER TO escobar;

--
-- Name: lc; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.lc (
    fileid integer NOT NULL,
    status varchar,
    userid varchar(20),
    nomdoc varchar(3) NOT NULL,
    cab smallint,
    pq integer,
    fl integer,
    ni smallint,
    np smallint,
    na smallint,
    ne smallint,
    nd smallint,
    nc integer,
    cs smallint,
    cp smallint,
    ce integer,
    fi varchar(20),
    hi varchar(20),
    fir varchar(20),
    fh integer,
    ffr varchar(20),
    fdt integer,
    fe varchar(20),
    hx varchar(20),
    pn varchar(60),
    ci smallint,
    rf integer,
    si smallint,
    sd smallint,
    ud varchar(8),
    ui varchar(8),
    ue varchar(8),
    udt varchar(8),
    fs integer,
    fx integer,
    fd integer,
    usuarioasignado varchar(20),
    punteado varchar(20) DEFAULT 'No punteado'::character varying,
    observacion varchar(200)
);


ALTER TABLE public.lc OWNER TO escobar;

--
-- Name: afi_rad_afi_rad_na_seq; Type: SEQUENCE; Schema: public; Owner: escobar
--

CREATE SEQUENCE public.afi_rad_afi_rad_na_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.afi_rad_afi_rad_na_seq OWNER TO escobar;

ALTER SEQUENCE public.afi_rad_afi_rad_na_seq OWNED BY public.afi_rad.afi_rad_na;


ALTER TABLE ONLY public.afi_rad ALTER COLUMN afi_rad_na SET DEFAULT nextval('public.afi_rad_afi_rad_na_seq'::regclass);

--
-- Name: afi_devoluciones_dev_na_seq; Type: SEQUENCE; Schema: public; Owner: escobar
--

CREATE SEQUENCE public.afi_devoluciones_dev_na_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.afi_devoluciones_dev_na_seq OWNER TO escobar;

ALTER SEQUENCE public.afi_devoluciones_dev_na_seq OWNED BY public.afi_devoluciones.dev_na;


ALTER TABLE ONLY public.afi_devoluciones ALTER COLUMN dev_na SET DEFAULT nextval('public.afi_devoluciones_dev_na_seq'::regclass);

--
-- Name: ciudades; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.ciudades (
    codigo varchar(5),
    ciudad varchar(40),
    coddep varchar(2),
    codmun varchar(3)
);

ALTER TABLE public.ciudades OWNER TO escobar;

INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05001', 'MEDELLIN', '05', '001');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05002', 'ABEJORRAL', '05', '002');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05004', 'ABRIAQUI', '05', '004');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05021', 'ALEJANDRIA', '05', '021');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05030', 'AMAGA', '05', '030');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05031', 'AMALFI', '05', '031');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05034', 'ANDES', '05', '034');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05036', 'ANGELOPOLIS', '05', '036');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05038', 'ANGOSTURA', '05', '038');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05040', 'ANORI', '05', '040');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05042', 'SANTAFE DE', '05', '042');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05044', 'ANZA', '05', '044');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05045', 'APARTADO', '05', '045');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05051', 'ARBOLETES', '05', '051');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05055', 'ARGELIA', '05', '055');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05059', 'ARMENIA', '05', '059');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05079', 'BARBOSA', '05', '079');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05086', 'BELMIRA', '05', '086');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05088', 'BELLO', '05', '088');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05091', 'BETANIA', '05', '091');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05093', 'BETULIA', '05', '093');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05101', 'CIUDAD BOLIVAR', '05', '101');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05107', 'BRICENO', '05', '107');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05113', 'BURITICA', '05', '113');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05120', 'CACERES', '05', '120');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05125', 'CAICEDO', '05', '125');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05129', 'CALDAS', '05', '129');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05134', 'CAMPAMENTO', '05', '134');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05138', 'CA�AS GORDAS', '05', '138');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05142', 'CARACOLI', '05', '142');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05145', 'CARAMANTA', '05', '145');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05147', 'CAREPA', '05', '147');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05148', 'EL CARMEN DE', '05', '148');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05150', 'CAROLINA', '05', '150');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05154', 'CAUCASIA', '05', '154');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05172', 'CHIGORODO', '05', '172');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05190', 'CISNEROS', '05', '190');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05197', 'COCORNA', '05', '197');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05206', 'CONCEPCION', '05', '206');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05209', 'CONCORDIA', '05', '209');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05212', 'COPACABANA', '05', '212');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05234', 'DABEIBA', '05', '234');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05237', 'DON MATIAS', '05', '237');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05240', 'EBEJICO', '05', '240');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05250', 'EL BAGRE', '05', '250');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05264', 'ENTRERRIOS', '05', '264');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05266', 'ENVIGADO', '05', '266');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05282', 'FREDONIA', '05', '282');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05284', 'FRONTINO', '05', '284');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05306', 'GIRALDO', '05', '306');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05308', 'GIRARDOTA', '05', '308');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05310', 'GOMEZ PLATA', '05', '310');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05313', 'GRANADA', '05', '313');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05315', 'GUADALUPE', '05', '315');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05318', 'GUARNE', '05', '318');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05321', 'GUATAPE', '05', '321');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05347', 'HELICONIA', '05', '347');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05353', 'HISPANIA', '05', '353');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05360', 'ITAGUI', '05', '360');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05361', 'ITUANGO', '05', '361');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05364', 'JARDIN', '05', '364');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05368', 'JERICO', '05', '368');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05376', 'LA CEJA', '05', '376');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05380', 'LA ESTRELLA', '05', '380');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05390', 'LA PINTADA', '05', '390');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05400', 'LA UNION', '05', '400');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05411', 'LIBORINA', '05', '411');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05425', 'MACEO', '05', '425');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05440', 'MARINILLA', '05', '440');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05467', 'MONTEBELLO', '05', '467');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05475', 'MURINDO', '05', '475');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05480', 'MUTATA', '05', '480');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05483', 'NARINO', '05', '483');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05490', 'NECOCLI', '05', '490');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05495', 'NECHI', '05', '495');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05501', 'OLAYA', '05', '501');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05541', 'PENOL', '05', '541');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05543', 'PEQUE', '05', '543');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05576', 'PUEBLORRICO', '05', '576');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05579', 'PUERTO BERRIO', '05', '579');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05585', 'PUERTO NARE', '05', '585');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05591', 'PUERTO TRIUNFO', '05', '591');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05604', 'REMEDIOS', '05', '604');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05607', 'RETIRO', '05', '607');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05615', 'RIONEGRO', '05', '615');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05628', 'SABANALARGA', '05', '628');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05631', 'SABANETA', '05', '631');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05642', 'SALGAR', '05', '642');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05647', 'SAN ANDRES DE', '05', '647');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05649', 'SAN CARLOS', '05', '649');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05652', 'SAN FRANCISCO', '05', '652');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05656', 'SAN JERONIMO', '05', '656');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05658', 'SAN JOSE DE LA', '05', '658');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05659', 'SAN JUAN DE URABA', '05', '659');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05660', 'SAN LUIS', '05', '660');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05664', 'SAN PEDRO', '05', '664');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05665', 'SAN PEDRO DE URABA', '05', '665');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05667', 'SAN RAFAEL', '05', '667');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05670', 'SAN ROQUE', '05', '670');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05674', 'SAN VICENTE', '05', '674');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05679', 'SANTA BARBARA', '05', '679');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05686', 'SANTA ROSA DE OSOS', '05', '686');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05690', 'SANTO DOMINGO', '05', '690');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05697', 'EL SANTUARIO', '05', '697');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05736', 'SEGOVIA', '05', '736');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05756', 'SONSON', '05', '756');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05761', 'SOPETRAN', '05', '761');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05789', 'TAMESIS', '05', '789');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05790', 'TARAZA', '05', '790');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05792', 'TARSO', '05', '792');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05809', 'TITIRIBI', '05', '809');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05819', 'TOLEDO', '05', '819');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05837', 'TURBO', '05', '837');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05842', 'URAMITA', '05', '842');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05847', 'URRAO', '05', '847');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05854', 'VALDIVIA', '05', '854');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05856', 'VALPARAISO', '05', '856');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05858', 'VEGACHI', '05', '858');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05861', 'VENECIA', '05', '861');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05873', 'VIGIA DEL FUERTE', '05', '873');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05885', 'YALI', '05', '885');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05887', 'YARUMAL', '05', '887');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05890', 'YOLOMBO', '05', '890');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05893', 'YONDO', '05', '893');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('05895', 'ZARAGOZA', '05', '895');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('08001', 'BARRANQUILLA', '08', '001');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('08078', 'BARANOA', '08', '078');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('08137', 'CAMPO DE LA CRUZ', '08', '137');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('08141', 'CANDELARIA', '08', '141');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('08296', 'GALAPA', '08', '296');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('08372', 'JUAN DE ACOSTA', '08', '372');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('08421', 'LURUACO', '08', '421');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('08433', 'MALAMBO', '08', '433');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('08436', 'MANATI', '08', '436');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('08520', 'PALMAR DE VARELA', '08', '520');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('08549', 'PIOJO', '08', '549');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('08558', 'POLONUEVO', '08', '558');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('08560', 'PONEDERA', '08', '560');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('08573', 'PUERTO COLOMBIA', '08', '573');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('08606', 'REPELON', '08', '606');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('08634', 'SABANAGRANDE', '08', '634');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('08638', 'SABANALARGA', '08', '638');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('08675', 'SANTA LUCIA', '08', '675');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('08685', 'SANTO TOMAS', '08', '685');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('08758', 'SOLEDAD', '08', '758');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('08770', 'SUAN', '08', '770');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('08832', 'TUBARA', '08', '832');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('08849', 'USIACURI', '08', '849');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('11001', 'BOGOTA', '11', '001');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('11001', 'BOGOTA DC', '11', '001');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('11001', 'BOGOTA,  DC', '11', '001');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('11001', 'BOGOTA, DC', '11', '001');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('13001', 'CARTAGENA', '13', '001');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('13006', 'ACHI', '13', '006');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('13030', 'ALTOS DEL ROSARIO', '13', '030');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('13042', 'ARENAL', '13', '042');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('13052', 'ARJONA', '13', '052');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('13062', 'ARROYOHONDO', '13', '062');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('13074', 'BARRANCO DE LOBA', '13', '074');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('13140', 'CALAMAR', '13', '140');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('13160', 'CANTAGALLO', '13', '160');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('13188', 'CICUCO', '13', '188');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('13212', 'CORDOBA', '13', '212');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('13222', 'CLEMENCIA', '13', '222');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('13244', 'EL CARMEN DE', '13', '244');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('13248', 'EL GUAMO', '13', '248');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('13268', 'EL PENOL', '13', '268');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('13300', 'HATILLO DE LOBA', '13', '300');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('13430', 'MAGANGUE', '13', '430');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('13433', 'MAHATES', '13', '433');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('13440', 'MARGARITA', '13', '440');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('13442', 'MARIA LA BAJA', '13', '442');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('13458', 'MONTECRISTO', '13', '458');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('13468', 'MOMPOS', '13', '468');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('13473', 'MORALES', '13', '473');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('13490', 'NOROSI', '13', '490');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('13549', 'PINILLOS', '13', '549');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('13580', 'REGIDOR', '13', '580');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('13600', 'RIO VIEJO', '13', '600');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('13620', 'SAN CRISTOBAL', '13', '620');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('13647', 'SAN ESTANISLAO', '13', '647');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('13650', 'SAN FERNANDO', '13', '650');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('13654', 'SAN JACINTO', '13', '654');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('13655', 'SAN JACINTO DEL CAUCA', '13', '655');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('13657', 'SAN JUAN NEPOMUCENO', '13', '657');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('13667', 'SAN MARTIN DE LOBA', '13', '667');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('13670', 'SAN PABLO', '13', '670');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('13673', 'SANTA CATALINA', '13', '673');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('13683', 'SANTA ROSA', '13', '683');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('13688', 'SANTA ROSA DEL SUR', '13', '688');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('13744', 'SIMITI', '13', '744');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('13760', 'SOPLAVIENTO', '13', '760');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('13780', 'TALAIGUA NUEVO', '13', '780');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('13810', 'TIQUISIO', '13', '810');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('13836', 'TURBACO', '13', '836');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('13838', 'TURBANA', '13', '838');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('13873', 'VILLANUEVA', '13', '873');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('13894', 'ZAMBRANO', '13', '894');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15001', 'TUNJA', '15', '001');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15022', 'ALMEIDA', '15', '022');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15047', 'AQUITANIA', '15', '047');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15051', 'ARCABUCO', '15', '051');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15087', 'BELEN', '15', '087');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15090', 'BERBEO', '15', '090');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15092', 'BETEITIVA', '15', '092');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15097', 'BOAVITA', '15', '097');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15104', 'BOYACA', '15', '104');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15106', 'BRICENO', '15', '106');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15109', 'BUENAVISTA', '15', '109');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15114', 'BUSBANZA', '15', '114');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15131', 'CALDAS', '15', '131');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15135', 'CAMPOHERMOSO', '15', '135');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15162', 'CERINZA', '15', '162');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15172', 'CHINAVITA', '15', '172');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15176', 'CHIQUINQUIRA', '15', '176');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15180', 'CHISCAS', '15', '180');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15183', 'CHITA', '15', '183');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15185', 'CHITARAQUE', '15', '185');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15187', 'CHIVATA', '15', '187');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15189', 'CIENEGA', '15', '189');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15204', 'COMBITA', '15', '204');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15212', 'COPER', '15', '212');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15215', 'CORRALES', '15', '215');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15218', 'COVARACHIA', '15', '218');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15223', 'CUBARA', '15', '223');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15224', 'CUCAITA', '15', '224');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15226', 'CUITIVA', '15', '226');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15232', 'CHIQUIZA', '15', '232');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15236', 'CHIVOR', '15', '236');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15238', 'DUITAMA', '15', '238');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15244', 'EL COCUY', '15', '244');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15248', 'EL ESPINO', '15', '248');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15272', 'FIRAVITOBA', '15', '272');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15276', 'FLORESTA', '15', '276');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15293', 'GACHANTIVA', '15', '293');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15296', 'GAMEZA', '15', '296');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15299', 'GARAGOA', '15', '299');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15317', 'GUACAMAYAS', '15', '317');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15322', 'GUATEQUE', '15', '322');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15325', 'GUAYATA', '15', '325');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15332', 'GsICAN', '15', '332');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15362', 'IZA', '15', '362');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15367', 'JENESANO', '15', '367');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15368', 'JERICO', '15', '368');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15377', 'LABRANZAGRANDE', '15', '377');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15380', 'LA CAPILLA', '15', '380');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15401', 'LA VICTORIA', '15', '401');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15403', 'LA UVITA', '15', '403');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15407', 'VILLA DE LEYVA', '15', '407');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15425', 'MACANAL', '15', '425');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15442', 'MARIPI', '15', '442');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15455', 'MIRAFLORES', '15', '455');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15464', 'MONGUA', '15', '464');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15466', 'MONGUI', '15', '466');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15469', 'MONIQUIRA', '15', '469');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15476', 'MOTAVITA', '15', '476');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15480', 'MUZO', '15', '480');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15491', 'NOBSA', '15', '491');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15494', 'NUEVO COLON', '15', '494');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15500', 'OICATA', '15', '500');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15507', 'OTANCHE', '15', '507');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15511', 'PACHAVITA', '15', '511');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15514', 'PAEZ', '15', '514');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15516', 'PAIPA', '15', '516');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15518', 'PAJARITO', '15', '518');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15522', 'PANQUEBA', '15', '522');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15531', 'PAUNA', '15', '531');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15533', 'PAYA', '15', '533');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15537', 'PAZ DE RIO', '15', '537');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15542', 'PESCA', '15', '542');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15550', 'PISBA', '15', '550');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15572', 'PUERTO BOYACA', '15', '572');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15580', 'QUIPAMA', '15', '580');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15599', 'RAMIRIQUI', '15', '599');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15600', 'RAQUIRA', '15', '600');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15621', 'RONDON', '15', '621');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15632', 'SABOYA', '15', '632');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15638', 'SACHICA', '15', '638');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15646', 'SAMACA', '15', '646');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15660', 'SAN EDUARDO', '15', '660');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15664', 'SAN JOSE DE PARE', '15', '664');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15667', 'SAN LUIS DE GACENO', '15', '667');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15673', 'SAN MATEO', '15', '673');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15676', 'SAN MIGUEL DE SEMA', '15', '676');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15681', 'SAN PABLO DE', '15', '681');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15686', 'SANTANA', '15', '686');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15690', 'SANTA MARIA', '15', '690');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15693', 'SANTA ROSA DE', '15', '693');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15696', 'SANTA SOFIA', '15', '696');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15720', 'SATIVANORTE', '15', '720');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15723', 'SATIVASUR', '15', '723');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15740', 'SIACHOQUE', '15', '740');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15753', 'SOATA', '15', '753');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15755', 'SOCOTA', '15', '755');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15757', 'SOCHA', '15', '757');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15759', 'SOGAMOSO', '15', '759');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15761', 'SOMONDOCO', '15', '761');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15762', 'SORA', '15', '762');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15763', 'SOTAQUIRA', '15', '763');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15764', 'SORACA', '15', '764');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15774', 'SUSACON', '15', '774');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15776', 'SUTAMARCHAN', '15', '776');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15778', 'SUTATENZA', '15', '778');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15790', 'TASCO', '15', '790');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15798', 'TENZA', '15', '798');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15804', 'TIBANA', '15', '804');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15806', 'TIBASOSA', '15', '806');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15808', 'TINJACA', '15', '808');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15810', 'TIPACOQUE', '15', '810');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15814', 'TOCA', '15', '814');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15816', 'TOGsI', '15', '816');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15820', 'TOPAGA', '15', '820');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15822', 'TOTA', '15', '822');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15832', 'TUNUNGUA', '15', '832');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15835', 'TURMEQUE', '15', '835');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15837', 'TUTA', '15', '837');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15839', 'TUTAZA', '15', '839');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15842', 'UMBITA', '15', '842');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15861', 'VENTAQUEMADA', '15', '861');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15879', 'VIRACACHA', '15', '879');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('15897', 'ZETAQUIRA', '15', '897');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('17001', 'MANIZALES', '17', '001');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('17013', 'AGUADAS', '17', '013');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('17042', 'ANSERMA', '17', '042');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('17050', 'ARANZAZU', '17', '050');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('17088', 'BELALCAZAR', '17', '088');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('17174', 'CHINCHINA', '17', '174');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('17272', 'FILADELFIA', '17', '272');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('17380', 'LA DORADA', '17', '380');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('17388', 'LA MERCED', '17', '388');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('17433', 'MANZANARES', '17', '433');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('17442', 'MARMATO', '17', '442');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('17444', 'MARQUETALIA', '17', '444');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('17446', 'MARULANDA', '17', '446');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('17486', 'NEIRA', '17', '486');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('17495', 'NORCASIA', '17', '495');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('17513', 'PACORA', '17', '513');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('17524', 'PALESTINA', '17', '524');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('17541', 'PENSILVANIA', '17', '541');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('17614', 'RIOSUCIO', '17', '614');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('17616', 'RISARALDA', '17', '616');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('17653', 'SALAMINA', '17', '653');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('17662', 'SAMANA', '17', '662');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('17665', 'SAN JOSE', '17', '665');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('17777', 'SUPIA', '17', '777');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('17867', 'VICTORIA', '17', '867');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('17873', 'VILLAMARIA', '17', '873');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('17877', 'VITERBO', '17', '877');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('18001', 'FLORENCIA', '18', '001');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('18029', 'ALBANIA', '18', '029');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('18094', 'BELEN DE LOS', '18', '094');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('18150', 'CARTAGENA DEL CHAIRA', '18', '150');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('18205', 'CURILLO', '18', '205');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('18247', 'EL DONCELLO', '18', '247');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('18256', 'EL PAUJIL', '18', '256');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('18410', 'LA MONTAÑITA', '18', '410');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('18460', 'MILAN', '18', '460');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('18479', 'MORELIA', '18', '479');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('18592', 'PUERTO RICO', '18', '592');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('18610', 'SAN JOSE DEL FRAGUA', '18', '610');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('18753', 'SAN VICENTE DEL', '18', '753');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('18756', 'SOLANO', '18', '756');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('18785', 'SOLITA', '18', '785');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('18860', 'VALPARAISO', '18', '860');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('19001', 'POPAYAN', '19', '001');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('19022', 'ALMAGUER', '19', '022');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('19050', 'ARGELIA', '19', '050');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('19075', 'BALBOA', '19', '075');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('19100', 'BOLIVAR', '19', '100');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('19110', 'BUENOS AIRES', '19', '110');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('19130', 'CAJIBIO', '19', '130');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('19137', 'CALDONO', '19', '137');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('19142', 'CALOTO', '19', '142');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('19212', 'CORINTO', '19', '212');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('19256', 'EL TAMBO', '19', '256');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('19290', 'FLORENCIA', '19', '290');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('19300', 'GUACHENE', '19', '300');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('19318', 'GUAPI', '19', '318');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('19355', 'INZA', '19', '355');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('19364', 'JAMBALO', '19', '364');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('19392', 'LA SIERRA', '19', '392');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('19397', 'LA VEGA', '19', '397');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('19418', 'LOPEZ', '19', '418');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('19450', 'MERCADERES', '19', '450');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('19455', 'MIRANDA', '19', '455');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('19473', 'MORALES', '19', '473');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('19513', 'PADILLA', '19', '513');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('19517', 'PAEZ', '19', '517');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('19532', 'PATIA', '19', '532');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('19533', 'PIAMONTE', '19', '533');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('19548', 'PIENDAMO', '19', '548');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('19573', 'PUERTO TEJADA', '19', '573');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('19585', 'PURACE', '19', '585');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('19622', 'ROSAS', '19', '622');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('19693', 'SAN SEBASTIAN', '19', '693');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('19698', 'SANTANDER DE', '19', '698');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('19701', 'SANTA ROSA', '19', '701');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('19743', 'SILVIA', '19', '743');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('19760', 'SOTARA', '19', '760');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('19780', 'SUAREZ', '19', '780');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('19785', 'SUCRE', '19', '785');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('19807', 'TIMBIO', '19', '807');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('19809', 'TIMBIQUI', '19', '809');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('19821', 'TORIBIO', '19', '821');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('19824', 'TOTORO', '19', '824');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('19845', 'VILLA RICA', '19', '845');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('20001', 'VALLEDUPAR', '20', '001');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('20011', 'AGUACHICA', '20', '011');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('20013', 'AGUSTIN CODAZZI', '20', '013');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('20032', 'ASTREA', '20', '032');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('20045', 'BECERRIL', '20', '045');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('20060', 'BOSCONIA', '20', '060');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('20175', 'CHIMICHAGUA', '20', '175');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('20178', 'CHIRIGUANA', '20', '178');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('20228', 'CURUMANI', '20', '228');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('20238', 'EL COPEY', '20', '238');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('20250', 'EL PASO', '20', '250');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('20295', 'GAMARRA', '20', '295');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('20310', 'GONZALEZ', '20', '310');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('20383', 'LA GLORIA', '20', '383');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('20400', 'LA JAGUA DE IBIRICO', '20', '400');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('20443', 'MANAURE', '20', '443');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('20517', 'PAILITAS', '20', '517');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('20550', 'PELAYA', '20', '550');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('20570', 'PUEBLO BELLO', '20', '570');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('20614', 'RIO DE ORO', '20', '614');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('20621', 'LA PAZ', '20', '621');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('20710', 'SAN ALBERTO', '20', '710');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('20750', 'SAN DIEGO', '20', '750');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('20770', 'SAN MARTIN', '20', '770');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('20787', 'TAMALAMEQUE', '20', '787');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('23001', 'MONTERIA', '23', '001');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('23068', 'AYAPEL', '23', '068');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('23079', 'BUENAVISTA', '23', '079');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('23090', 'CANALETE', '23', '090');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('23162', 'CERETE', '23', '162');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('23168', 'CHIMA', '23', '168');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('23182', 'CHINU', '23', '182');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('23189', 'CIENAGA DE ORO', '23', '189');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('23300', 'COTORRA', '23', '300');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('23350', 'LA APARTADA', '23', '350');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('23417', 'LORICA', '23', '417');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('23419', 'LOS CORDOBAS', '23', '419');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('23464', 'MOMIL', '23', '464');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('23466', 'MONTELIBANO', '23', '466');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('23500', 'MOÑITOS', '23', '500');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('23555', 'PLANETA RICA', '23', '555');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('23570', 'PUEBLO NUEVO', '23', '570');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('23574', 'PUERTO ESCONDIDO', '23', '574');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('23580', 'PUERTO LIBERTADOR', '23', '580');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('23586', 'PURISIMA', '23', '586');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('23660', 'SAHAGUN', '23', '660');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('23670', 'SAN ANDRES', '23', '670');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('23672', 'SAN ANTERO', '23', '672');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('23675', 'SAN BERNARDO DEL', '23', '675');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('23678', 'SAN CARLOS', '23', '678');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('23682', 'SAN JOSE DE URE', '23', '682');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('23686', 'SAN PELAYO', '23', '686');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('23807', 'TIERRALTA', '23', '807');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('23855', 'VALENCIA', '23', '855');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25001', 'AGUA DE DIOS', '25', '001');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25019', 'ALBAN', '25', '019');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25035', 'ANAPOIMA', '25', '035');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25040', 'ANOLAIMA', '25', '040');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25053', 'ARBELAEZ', '25', '053');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25086', 'BELTRAN', '25', '086');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25095', 'BITUIMA', '25', '095');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25099', 'BOJACA', '25', '099');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25120', 'CABRERA', '25', '120');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25123', 'CACHIPAY', '25', '123');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25126', 'CAJICA', '25', '126');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25148', 'CAPARRAPI', '25', '148');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25151', 'CAQUEZA', '25', '151');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25154', 'CARMEN DE CARUPA', '25', '154');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25168', 'CHAGUANI', '25', '168');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25175', 'CHIA', '25', '175');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25178', 'CHIPAQUE', '25', '178');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25181', 'CHOACHI', '25', '181');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25183', 'CHOCONTA', '25', '183');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25200', 'COGUA', '25', '200');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25214', 'COTA', '25', '214');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25224', 'CUCUNUBA', '25', '224');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25245', 'EL COLEGIO', '25', '245');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25258', 'EL PENOL', '25', '258');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25260', 'EL ROSAL', '25', '260');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25269', 'FACATATIVA', '25', '269');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25279', 'FOMEQUE', '25', '279');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25281', 'FOSCA', '25', '281');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25286', 'FUNZA', '25', '286');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25288', 'FUQUENE', '25', '288');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25290', 'FUSAGASUGA', '25', '290');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25293', 'GACHALA', '25', '293');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25295', 'GACHANCIPA', '25', '295');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25297', 'GACHETA', '25', '297');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25299', 'GAMA', '25', '299');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25307', 'GIRARDOT', '25', '307');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25312', 'GRANADA', '25', '312');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25317', 'GUACHETA', '25', '317');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25320', 'GUADUAS', '25', '320');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25322', 'GUASCA', '25', '322');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25324', 'GUATAQUI', '25', '324');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25326', 'GUATAVITA', '25', '326');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25328', 'GUAYABAL DE SIQUIMA', '25', '328');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25335', 'GUAYABETAL', '25', '335');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25339', 'GUTIERREZ', '25', '339');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25368', 'JERUSALEN', '25', '368');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25372', 'JUNIN', '25', '372');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25377', 'LA CALERA', '25', '377');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25386', 'LA MESA', '25', '386');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25394', 'LA PALMA', '25', '394');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25398', 'LA PENA', '25', '398');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25402', 'LA VEGA', '25', '402');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25407', 'LENGUAZAQUE', '25', '407');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25426', 'MACHETA', '25', '426');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25430', 'MADRID', '25', '430');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25436', 'MANTA', '25', '436');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25438', 'MEDINA', '25', '438');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25473', 'MOSQUERA', '25', '473');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25483', 'NARINO', '25', '483');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25486', 'NEMOCON', '25', '486');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25488', 'NILO', '25', '488');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25489', 'NIMAIMA', '25', '489');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25491', 'NOCAIMA', '25', '491');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25506', 'VENECIA', '25', '506');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25513', 'PACHO', '25', '513');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25518', 'PAIME', '25', '518');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25524', 'PANDI', '25', '524');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25530', 'PARATEBUENO', '25', '530');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25535', 'PASCA', '25', '535');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25572', 'PUERTO SALGAR', '25', '572');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25580', 'PULI', '25', '580');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25592', 'QUEBRADANEGRA', '25', '592');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25594', 'QUETAME', '25', '594');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25596', 'QUIPILE', '25', '596');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25599', 'APULO', '25', '599');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25612', 'RICAURTE', '25', '612');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25645', 'SAN ANTONIO DEL', '25', '645');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25649', 'SAN BERNARDO', '25', '649');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25653', 'SAN CAYETANO', '25', '653');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25658', 'SAN FRANCISCO', '25', '658');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25662', 'SAN JUAN DE RIO SECO', '25', '662');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25718', 'SASAIMA', '25', '718');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25736', 'SESQUILE', '25', '736');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25740', 'SIBATE', '25', '740');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25743', 'SILVANIA', '25', '743');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25745', 'SIMIJACA', '25', '745');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25754', 'SOACHA', '25', '754');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25758', 'SOPO', '25', '758');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25769', 'SUBACHOQUE', '25', '769');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25772', 'SUESCA', '25', '772');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25777', 'SUPATA', '25', '777');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25779', 'SUSA', '25', '779');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25781', 'SUTATAUSA', '25', '781');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25785', 'TABIO', '25', '785');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25793', 'TAUSA', '25', '793');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25797', 'TENA', '25', '797');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25799', 'TENJO', '25', '799');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25805', 'TIBACUY', '25', '805');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25807', 'TIBIRITA', '25', '807');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25815', 'TOCAIMA', '25', '815');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25817', 'TOCANCIPA', '25', '817');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25823', 'TOPAIPI', '25', '823');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25839', 'UBALA', '25', '839');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25841', 'UBAQUE', '25', '841');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25843', 'UBATE', '25', '843');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25845', 'UNE', '25', '845');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25851', 'UTICA', '25', '851');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25862', 'VERGARA', '25', '862');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25867', 'VIANI', '25', '867');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25871', 'VILLAGOMEZ', '25', '871');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25873', 'VILLAPINZON', '25', '873');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25875', 'VILLETA', '25', '875');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25878', 'VIOTA', '25', '878');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25885', 'YACOPI', '25', '885');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25898', 'ZIPACON', '25', '898');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('25899', 'ZIPAQUIRA', '25', '899');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('27001', 'QUIBDO', '27', '001');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('27006', 'ACANDI', '27', '006');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('27025', 'ALTO BAUDO', '27', '025');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('27050', 'ATRATO', '27', '050');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('27073', 'BAGADO', '27', '073');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('27075', 'BAHIA SOLANO', '27', '075');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('27077', 'BAJO BAUDO', '27', '077');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('27099', 'BOJAYA', '27', '099');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('27135', 'EL CANTON DEL SAN', '27', '135');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('27150', 'CARMEN DEL DARIEN', '27', '150');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('27160', 'CERTEGUI', '27', '160');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('27205', 'CONDOTO', '27', '205');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('27245', 'EL CARMEN DE', '27', '245');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('27250', 'EL LITORAL DEL SAN', '27', '250');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('27361', 'ISTMINA', '27', '361');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('27372', 'JURADO', '27', '372');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('27413', 'LLORO', '27', '413');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('27425', 'MEDIO ATRATO', '27', '425');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('27430', 'MEDIO BAUDO', '27', '430');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('27450', 'MEDIO SAN JUAN', '27', '450');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('27491', 'NOVITA', '27', '491');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('27495', 'NUQUI', '27', '495');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('27580', 'RIO IRO', '27', '580');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('27600', 'RIO QUITO', '27', '600');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('27615', 'RIOSUCIO', '27', '615');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('27660', 'SAN JOSE DEL PALMAR', '27', '660');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('27745', 'SIPI', '27', '745');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('27787', 'TADO', '27', '787');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('27800', 'UNGUIA', '27', '800');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('27810', 'UNION PANAMERICANA', '27', '810');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('41001', 'NEIVA', '41', '001');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('41006', 'ACEVEDO', '41', '006');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('41013', 'AGRADO', '41', '013');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('41016', 'AIPE', '41', '016');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('41020', 'ALGECIRAS', '41', '020');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('41026', 'ALTAMIRA', '41', '026');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('41078', 'BARAYA', '41', '078');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('41132', 'CAMPOALEGRE', '41', '132');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('41206', 'COLOMBIA', '41', '206');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('41244', 'ELIAS', '41', '244');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('41298', 'GARZON', '41', '298');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('41306', 'GIGANTE', '41', '306');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('41319', 'GUADALUPE', '41', '319');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('41349', 'HOBO', '41', '349');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('41357', 'IQUIRA', '41', '357');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('41359', 'ISNOS', '41', '359');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('41378', 'LA ARGENTINA', '41', '378');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('41396', 'LA PLATA', '41', '396');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('41483', 'NATAGA', '41', '483');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('41503', 'OPORAPA', '41', '503');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('41518', 'PAICOL', '41', '518');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('41524', 'PALERMO', '41', '524');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('41530', 'PALESTINA', '41', '530');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('41548', 'PITAL', '41', '548');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('41551', 'PITALITO', '41', '551');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('41615', 'RIVERA', '41', '615');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('41660', 'SALADOBLANCO', '41', '660');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('41668', 'SAN AGUSTIN', '41', '668');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('41676', 'SANTA MARIA', '41', '676');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('41770', 'SUAZA', '41', '770');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('41791', 'TARQUI', '41', '791');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('41797', 'TESALIA', '41', '797');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('41799', 'TELLO', '41', '799');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('41801', 'TERUEL', '41', '801');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('41807', 'TIMANA', '41', '807');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('41872', 'VILLAVIEJA', '41', '872');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('41885', 'YAGUARA', '41', '885');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('44001', 'RIOHACHA', '44', '001');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('44035', 'ALBANIA', '44', '035');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('44078', 'BARRANCAS', '44', '078');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('44090', 'DIBULLA', '44', '090');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('44098', 'DISTRACCION', '44', '098');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('44110', 'EL MOLINO', '44', '110');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('44279', 'FONSECA', '44', '279');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('44378', 'HATONUEVO', '44', '378');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('44420', 'LA JAGUA DEL PILAR', '44', '420');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('44430', 'MAICAO', '44', '430');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('44560', 'MANAURE', '44', '560');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('44650', 'SAN JUAN DEL CESAR', '44', '650');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('44847', 'URIBIA', '44', '847');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('44855', 'URUMITA', '44', '855');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('44874', 'VILLANUEVA', '44', '874');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('47001', 'SANTA MARTA', '47', '001');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('47030', 'ALGARROBO', '47', '030');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('47053', 'ARACATACA', '47', '053');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('47058', 'ARIGUANI', '47', '058');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('47161', 'CERRO SAN ANTONIO', '47', '161');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('47170', 'CHIBOLO', '47', '170');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('47189', 'CIENAGA', '47', '189');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('47205', 'CONCORDIA', '47', '205');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('47245', 'EL BANCO', '47', '245');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('47258', 'EL PINON', '47', '258');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('47268', 'EL RETEN', '47', '268');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('47288', 'FUNDACION', '47', '288');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('47318', 'GUAMAL', '47', '318');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('47460', 'NUEVA GRANADA', '47', '460');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('47541', 'PEDRAZA', '47', '541');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('47545', 'PIJI�O DEL CARMEN', '47', '545');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('47551', 'PIVIJAY', '47', '551');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('47555', 'PLATO', '47', '555');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('47570', 'PUEBLOVIEJO', '47', '570');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('47605', 'REMOLINO', '47', '605');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('47660', 'SABANAS DE SAN', '47', '660');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('47675', 'SALAMINA', '47', '675');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('47692', 'SAN SEBASTIAN DE', '47', '692');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('47703', 'SAN ZENON', '47', '703');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('47707', 'SANTA ANA', '47', '707');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('47720', 'SANTA BARBARA DE', '47', '720');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('47745', 'SITIONUEVO', '47', '745');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('47798', 'TENERIFE', '47', '798');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('47960', 'ZAPAYAN', '47', '960');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('47980', 'ZONA BANANERA', '47', '980');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('50001', 'VILLAVICENCIO', '50', '001');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('50006', 'ACACIAS', '50', '006');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('50110', 'BARRANCA DE UPIA', '50', '110');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('50124', 'CABUYARO', '50', '124');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('50150', 'CASTILLA LA NUEVA', '50', '150');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('50223', 'CUBARRAL', '50', '223');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('50226', 'CUMARAL', '50', '226');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('50245', 'EL CALVARIO', '50', '245');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('50251', 'EL CASTILLO', '50', '251');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('50270', 'EL DORADO', '50', '270');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('50287', 'FUENTE DE ORO', '50', '287');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('50313', 'GRANADA', '50', '313');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('50318', 'GUAMAL', '50', '318');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('50325', 'MAPIRIPAN', '50', '325');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('50330', 'MESETAS', '50', '330');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('50350', 'LA MACARENA', '50', '350');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('50370', 'URIBE', '50', '370');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('50400', 'LEJANIAS', '50', '400');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('50450', 'PUERTO CONCORDIA', '50', '450');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('50568', 'PUERTO GAITAN', '50', '568');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('50573', 'PUERTO LOPEZ', '50', '573');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('50577', 'PUERTO LLERAS', '50', '577');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('50590', 'PUERTO RICO', '50', '590');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('50606', 'RESTREPO', '50', '606');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('50680', 'SAN CARLOS DE', '50', '680');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('50683', 'SAN JUAN DE ARAMA', '50', '683');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('50686', 'SAN JUANITO', '50', '686');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('50689', 'SAN MARTIN Meta', '50', '689');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('50711', 'VISTAHERMOSA', '50', '711');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52001', 'PASTO', '52', '001');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52019', 'ALBAN', '52', '019');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52022', 'ALDANA', '52', '022');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52036', 'ANCUYA', '52', '036');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52051', 'ARBOLEDA', '52', '051');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52079', 'BARBACOAS', '52', '079');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52083', 'BELEN', '52', '083');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52110', 'BUESACO', '52', '110');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52203', 'COLON', '52', '203');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52207', 'CONSACA', '52', '207');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52210', 'CONTADERO', '52', '210');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52215', 'CORDOBA', '52', '215');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52224', 'CUASPUD', '52', '224');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52227', 'CUMBAL', '52', '227');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52233', 'CUMBITARA', '52', '233');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52240', 'CHACHAGsI', '52', '240');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52250', 'EL CHARCO', '52', '250');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52254', 'EL PENOL', '52', '254');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52256', 'EL ROSARIO', '52', '256');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52258', 'EL TABLON DE GOMEZ', '52', '258');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52260', 'EL TAMBO', '52', '260');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52287', 'FUNES', '52', '287');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52317', 'GUACHUCAL', '52', '317');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52320', 'GUAITARILLA', '52', '320');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52323', 'GUALMATAN', '52', '323');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52352', 'ILES', '52', '352');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52354', 'IMUES', '52', '354');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52356', 'IPIALES', '52', '356');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52378', 'LA CRUZ', '52', '378');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52381', 'LA FLORIDA', '52', '381');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52385', 'LA LLANADA', '52', '385');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52390', 'LA TOLA', '52', '390');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52399', 'LA UNION', '52', '399');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52405', 'LEIVA', '52', '405');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52411', 'LINARES', '52', '411');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52418', 'LOS ANDES', '52', '418');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52427', 'MAGsI', '52', '427');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52435', 'MALLAMA', '52', '435');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52473', 'MOSQUERA', '52', '473');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52480', 'NARINO', '52', '480');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52490', 'OLAYA HERRERA', '52', '490');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52506', 'OSPINA', '52', '506');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52520', 'FRANCISCO PIZARRO', '52', '520');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52540', 'POLICARPA', '52', '540');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52560', 'POTOSI', '52', '560');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52565', 'PROVIDENCIA', '52', '565');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52573', 'PUERRES', '52', '573');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52585', 'PUPIALES', '52', '585');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52612', 'RICAURTE', '52', '612');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52621', 'ROBERTO PAYAN', '52', '621');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52678', 'SAMANIEGO', '52', '678');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52683', 'SANDONA', '52', '683');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52685', 'SAN BERNARDO', '52', '685');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52687', 'SAN LORENZO', '52', '687');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52693', 'SAN PABLO', '52', '693');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52694', 'SAN PEDRO DE', '52', '694');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52696', 'SANTA BARBARA', '52', '696');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52699', 'SANTACRUZ', '52', '699');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52720', 'SAPUYES', '52', '720');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52786', 'TAMINANGO', '52', '786');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52788', 'TANGUA', '52', '788');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52835', 'SAN ANDRES DE', '52', '835');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52838', 'TUQUERRES', '52', '838');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('52885', 'YACUANQUER', '52', '885');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('54001', 'CUCUTA', '54', '001');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('54003', 'ABREGO', '54', '003');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('54051', 'ARBOLEDAS', '54', '051');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('54099', 'BOCHALEMA', '54', '099');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('54109', 'BUCARASICA', '54', '109');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('54125', 'CACOTA', '54', '125');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('54128', 'CACHIRA', '54', '128');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('54172', 'CHINACOTA', '54', '172');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('54174', 'CHITAGA', '54', '174');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('54206', 'CONVENCION', '54', '206');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('54223', 'CUCUTILLA', '54', '223');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('54239', 'DURANIA', '54', '239');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('54245', 'EL CARMEN', '54', '245');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('54250', 'EL TARRA', '54', '250');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('54261', 'EL ZULIA', '54', '261');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('54313', 'GRAMALOTE', '54', '313');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('54344', 'HACARI', '54', '344');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('54347', 'HERRAN', '54', '347');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('54377', 'LABATECA', '54', '377');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('54385', 'LA ESPERANZA', '54', '385');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('54398', 'LA PLAYA', '54', '398');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('54405', 'LOS PATIOS', '54', '405');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('54418', 'LOURDES', '54', '418');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('54480', 'MUTISCUA', '54', '480');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('54498', 'OCANA', '54', '498');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('54518', 'PAMPLONA', '54', '518');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('54520', 'PAMPLONITA', '54', '520');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('54553', 'PUERTO SANTANDER', '54', '553');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('54599', 'RAGONVALIA', '54', '599');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('54660', 'SALAZAR', '54', '660');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('54670', 'SAN CALIXTO', '54', '670');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('54673', 'SAN CAYETANO', '54', '673');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('54680', 'SANTIAGO', '54', '680');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('54720', 'SARDINATA', '54', '720');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('54743', 'SILOS', '54', '743');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('54800', 'TEORAMA', '54', '800');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('54810', 'TIBU', '54', '810');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('54820', 'TOLEDO', '54', '820');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('54871', 'VILLA CARO', '54', '871');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('54874', 'VILLA DEL ROSARIO', '54', '874');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('63001', 'ARMENIA', '63', '001');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('63111', 'BUENAVISTA', '63', '111');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('63130', 'CALARCA', '63', '130');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('63190', 'CIRCASIA', '63', '190');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('63212', 'CORDOBA', '63', '212');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('63272', 'FILANDIA', '63', '272');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('63302', 'GENOVA', '63', '302');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('63401', 'LA TEBAIDA', '63', '401');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('63470', 'MONTENEGRO', '63', '470');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('63548', 'PIJAO', '63', '548');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('63594', 'QUIMBAYA', '63', '594');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('63690', 'SALENTO', '63', '690');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('66001', 'PEREIRA', '66', '001');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('66045', 'APIA', '66', '045');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('66075', 'BALBOA', '66', '075');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('66088', 'BELEN DE UMBRIA', '66', '088');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('66170', 'DOSQUEBRADAS', '66', '170');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('66318', 'GUATICA', '66', '318');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('66383', 'LA CELIA', '66', '383');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('66400', 'LA VIRGINIA', '66', '400');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('66440', 'MARSELLA', '66', '440');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('66456', 'MISTRATO', '66', '456');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('66572', 'PUEBLO RICO', '66', '572');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('66594', 'QUINCHIA', '66', '594');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('66682', 'SANTA ROSA DE CABAL', '66', '682');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('66687', 'SANTUARIO', '66', '687');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68001', 'BUCARAMANGA', '68', '001');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68013', 'AGUADA', '68', '013');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68020', 'ALBANIA', '68', '020');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68051', 'ARATOCA', '68', '051');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68077', 'BARBOSA', '68', '077');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68079', 'BARICHARA', '68', '079');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68081', 'BARRANCABERMEJA', '68', '081');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68092', 'BETULIA', '68', '092');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68101', 'BOLIVAR', '68', '101');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68121', 'CABRERA', '68', '121');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68132', 'CALIFORNIA', '68', '132');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68147', 'CAPITANEJO', '68', '147');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68152', 'CARCASI', '68', '152');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68160', 'CEPITA', '68', '160');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68162', 'CERRITO', '68', '162');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68167', 'CHARALA', '68', '167');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68169', 'CHARTA', '68', '169');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68176', 'CHIMA', '68', '176');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68179', 'CHIPATA', '68', '179');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68190', 'CIMITARRA', '68', '190');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68207', 'CONCEPCION', '68', '207');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68209', 'CONFINES', '68', '209');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68211', 'CONTRATACION', '68', '211');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68217', 'COROMORO', '68', '217');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68229', 'CURITI', '68', '229');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68235', 'EL CARMEN DE', '68', '235');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68245', 'EL GUACAMAYO', '68', '245');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68250', 'EL PENOL', '68', '250');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68255', 'EL PLAYON', '68', '255');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68264', 'ENCINO', '68', '264');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68266', 'ENCISO', '68', '266');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68271', 'FLORIAN', '68', '271');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68276', 'FLORIDABLANCA', '68', '276');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68296', 'GALAN', '68', '296');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68298', 'GAMBITA', '68', '298');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68307', 'GIRON', '68', '307');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68318', 'GUACA', '68', '318');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68320', 'GUADALUPE', '68', '320');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68322', 'GUAPOTA', '68', '322');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68324', 'GUAVATA', '68', '324');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68327', 'GsEPSA', '68', '327');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68344', 'HATO', '68', '344');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68368', 'JESUS MARIA', '68', '368');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68370', 'JORDAN', '68', '370');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68377', 'LA BELLEZA', '68', '377');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68385', 'LANDAZURI', '68', '385');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68397', 'LA PAZ', '68', '397');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68406', 'LEBRIJA', '68', '406');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68418', 'LOS SANTOS', '68', '418');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68425', 'MACARAVITA', '68', '425');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68432', 'MALAGA', '68', '432');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68444', 'MATANZA', '68', '444');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68464', 'MOGOTES', '68', '464');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68468', 'MOLAGAVITA', '68', '468');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68498', 'OCAMONTE', '68', '498');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68500', 'OIBA', '68', '500');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68502', 'ONZAGA', '68', '502');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68522', 'PALMAR', '68', '522');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68524', 'PALMAS DEL SOCORRO', '68', '524');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68533', 'PARAMO', '68', '533');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68547', 'PIEDECUESTA', '68', '547');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68549', 'PINCHOTE', '68', '549');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68572', 'PUENTE NACIONAL', '68', '572');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68573', 'PUERTO PARRA', '68', '573');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68575', 'PUERTO WILCHES', '68', '575');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68615', 'RIONEGRO', '68', '615');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68655', 'SABANA DE TORRES', '68', '655');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68669', 'SAN ANDRES', '68', '669');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68673', 'SAN BENITO', '68', '673');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68679', 'SAN GIL', '68', '679');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68682', 'SAN JOAQUIN', '68', '682');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68684', 'SAN JOSE DE MIRANDA', '68', '684');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68686', 'SAN MIGUEL', '68', '686');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68689', 'SAN VICENTE DE', '68', '689');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68705', 'SANTA BARBARA', '68', '705');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68720', 'SANTA HELENA DEL', '68', '720');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68745', 'SIMACOTA', '68', '745');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68755', 'SOCORRO', '68', '755');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68770', 'SUAITA', '68', '770');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68773', 'SUCRE', '68', '773');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68780', 'SURATA', '68', '780');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68820', 'TONA', '68', '820');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68855', 'VALLE DE SAN JOSE', '68', '855');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68861', 'VELEZ', '68', '861');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68867', 'VETAS', '68', '867');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68872', 'VILLANUEVA', '68', '872');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('68895', 'ZAPATOCA', '68', '895');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('70001', 'SINCELEJO', '70', '001');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('70110', 'BUENAVISTA', '70', '110');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('70124', 'CAIMITO', '70', '124');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('70204', 'COLOSO', '70', '204');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('70215', 'COROZAL', '70', '215');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('70221', 'COVE�AS', '70', '221');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('70230', 'CHALAN', '70', '230');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('70233', 'EL ROBLE', '70', '233');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('70235', 'GALERAS', '70', '235');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('70265', 'GUARANDA', '70', '265');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('70400', 'LA UNION', '70', '400');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('70418', 'LOS PALMITOS', '70', '418');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('70429', 'MAJAGUAL', '70', '429');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('70473', 'MORROA', '70', '473');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('70508', 'OVEJAS', '70', '508');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('70523', 'PALMITO', '70', '523');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('70670', 'SAMPUES', '70', '670');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('70678', 'SAN BENITO ABAD', '70', '678');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('70702', 'SAN JUAN DE BETULIA', '70', '702');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('70708', 'SAN MARCOS', '70', '708');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('70713', 'SAN ONOFRE', '70', '713');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('70717', 'SAN PEDRO', '70', '717');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('70742', 'SAN LUIS DE SINCE', '70', '742');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('70771', 'SUCRE', '70', '771');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('70820', 'SANTIAGO DE TOLU', '70', '820');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('70823', 'TOLU VIEJO', '70', '823');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('73001', 'IBAGUE', '73', '001');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('73024', 'ALPUJARRA', '73', '024');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('73026', 'ALVARADO', '73', '026');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('73030', 'AMBALEMA', '73', '030');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('73043', 'ANZOATEGUI', '73', '043');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('73055', 'ARMERO', '73', '055');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('73067', 'ATACO', '73', '067');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('73124', 'CAJAMARCA', '73', '124');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('73148', 'CARMEN DE APICALA', '73', '148');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('73152', 'CASABIANCA', '73', '152');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('73168', 'CHAPARRAL', '73', '168');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('73200', 'COELLO', '73', '200');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('73217', 'COYAIMA', '73', '217');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('73226', 'CUNDAY', '73', '226');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('73236', 'DOLORES', '73', '236');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('73268', 'ESPINAL', '73', '268');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('73270', 'FALAN', '73', '270');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('73275', 'FLANDES', '73', '275');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('73283', 'FRESNO', '73', '283');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('73319', 'GUAMO', '73', '319');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('73347', 'HERVEO', '73', '347');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('73349', 'HONDA', '73', '349');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('73352', 'ICONONZO', '73', '352');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('73408', 'LERIDA', '73', '408');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('73411', 'LIBANO', '73', '411');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('73443', 'MARIQUITA', '73', '443');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('73449', 'MELGAR', '73', '449');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('73461', 'MURILLO', '73', '461');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('73483', 'NATAGAIMA', '73', '483');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('73504', 'ORTEGA', '73', '504');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('73520', 'PALOCABILDO', '73', '520');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('73547', 'PIEDRAS', '73', '547');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('73555', 'PLANADAS', '73', '555');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('73563', 'PRADO', '73', '563');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('73585', 'PURIFICACION', '73', '585');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('73616', 'RIOBLANCO', '73', '616');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('73622', 'RONCESVALLES', '73', '622');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('73624', 'ROVIRA', '73', '624');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('73671', 'SALDAÑA', '73', '671');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('73675', 'SAN ANTONIO', '73', '675');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('73678', 'SAN LUIS', '73', '678');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('73686', 'SANTA ISABEL', '73', '686');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('73770', 'SUAREZ', '73', '770');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('73854', 'VALLE DE SAN JUAN', '73', '854');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('73861', 'VENADILLO', '73', '861');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('73870', 'VILLAHERMOSA', '73', '870');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('73873', 'VILLARRICA', '73', '873');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('76001', 'CALI', '76', '001');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('76020', 'ALCALA', '76', '020');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('76036', 'ANDALUCIA', '76', '036');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('76041', 'ANSERMANUEVO', '76', '041');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('76054', 'ARGELIA', '76', '054');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('76100', 'BOLIVAR', '76', '100');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('76109', 'BUENAVENTURA', '76', '109');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('76111', 'GUADALAJARA DE', '76', '111');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('76113', 'BUGALAGRANDE', '76', '113');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('76122', 'CAICEDONIA', '76', '122');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('76126', 'CALIMA', '76', '126');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('76130', 'CANDELARIA', '76', '130');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('76147', 'CARTAGO', '76', '147');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('76233', 'DAGUA', '76', '233');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('76243', 'EL AGUILA', '76', '243');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('76246', 'EL CAIRO', '76', '246');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('76248', 'EL CERRITO', '76', '248');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('76250', 'EL DOVIO', '76', '250');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('76275', 'FLORIDA', '76', '275');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('76306', 'GINEBRA', '76', '306');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('76318', 'GUACARI', '76', '318');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('76364', 'JAMUNDI', '76', '364');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('76377', 'LA CUMBRE', '76', '377');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('76400', 'LA UNION', '76', '400');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('76403', 'LA VICTORIA', '76', '403');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('76497', 'OBANDO', '76', '497');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('76520', 'PALMIRA', '76', '520');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('76563', 'PRADERA', '76', '563');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('76606', 'RESTREPO', '76', '606');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('76616', 'RIOFRIO', '76', '616');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('76622', 'ROLDANILLO', '76', '622');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('76670', 'SAN PEDRO', '76', '670');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('76736', 'SEVILLA', '76', '736');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('76823', 'TORO', '76', '823');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('76828', 'TRUJILLO', '76', '828');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('76834', 'TULUA', '76', '834');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('76845', 'ULLOA', '76', '845');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('76863', 'VERSALLES', '76', '863');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('76869', 'VIJES', '76', '869');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('76890', 'YOTOCO', '76', '890');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('76892', 'YUMBO', '76', '892');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('76895', 'ZARZAL', '76', '895');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('81001', 'ARAUCA', '81', '001');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('81065', 'ARAUQUITA', '81', '065');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('81220', 'CRAVO NORTE', '81', '220');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('81300', 'FORTUL', '81', '300');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('81591', 'PUERTO RONDON', '81', '591');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('81736', 'SARAVENA', '81', '736');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('81794', 'TAME', '81', '794');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('85001', 'YOPAL', '85', '001');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('85010', 'AGUAZUL', '85', '010');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('85015', 'CHAMEZA', '85', '015');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('85125', 'HATO COROZAL', '85', '125');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('85136', 'LA SALINA', '85', '136');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('85139', 'MANI', '85', '139');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('85162', 'MONTERREY', '85', '162');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('85225', 'NUNCHIA', '85', '225');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('85230', 'OROCUE', '85', '230');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('85250', 'PAZ DE ARIPORO', '85', '250');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('85263', 'PORE', '85', '263');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('85279', 'RECETOR', '85', '279');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('85300', 'SABANALARGA', '85', '300');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('85315', 'SACAMA', '85', '315');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('85325', 'SAN LUIS DE', '85', '325');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('85400', 'TAMARA', '85', '400');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('85410', 'TAURAMENA', '85', '410');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('85430', 'TRINIDAD', '85', '430');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('85440', 'VILLANUEVA', '85', '440');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('86001', 'MOCOA', '86', '001');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('86219', 'COLON', '86', '219');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('86320', 'ORITO', '86', '320');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('86568', 'PUERTO ASIS', '86', '568');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('86569', 'PUERTO CAICEDO', '86', '569');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('86571', 'PUERTO GUZMAN', '86', '571');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('86573', 'LEGUIZAMO', '86', '573');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('86749', 'SIBUNDOY', '86', '749');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('86755', 'SAN FRANCISCO', '86', '755');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('86757', 'SAN MIGUEL', '86', '757');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('86760', 'SANTIAGO', '86', '760');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('86865', 'VALLE DEL GUAMUEZ', '86', '865');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('86885', 'VILLAGARZON', '86', '885');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('88001', 'SAN ANDRES', '88', '001');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('88564', 'PROVIDENCIA', '88', '564');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('91001', 'LETICIA', '91', '001');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('91263', 'EL ENCANTO', '91', '263');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('91405', 'LA CHORRERA', '91', '405');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('91407', 'LA PEDRERA', '91', '407');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('91430', 'LA VICTORIA', '91', '430');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('91460', 'MIRITI - PARANA', '91', '460');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('91530', 'PUERTO ALEGRIA', '91', '530');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('91536', 'PUERTO ARICA', '91', '536');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('91540', 'PUERTO NARINO', '91', '540');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('91669', 'PUERTO SANTANDER', '91', '669');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('91798', 'TARAPACA', '91', '798');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('94001', 'INIRIDA', '94', '001');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('94343', 'BARRANCO MINAS', '94', '343');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('94663', 'MAPIRIPANA', '94', '663');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('94883', 'SAN FELIPE', '94', '883');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('94884', 'PUERTO COLOMBIA', '94', '884');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('94885', 'LA GUADALUPE', '94', '885');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('94886', 'CACAHUAL', '94', '886');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('94887', 'PANA PANA', '94', '887');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('94888', 'MORICHAL', '94', '888');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('95001', 'SAN JOSE DEL', '95', '001');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('95015', 'CALAMAR', '95', '015');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('95025', 'EL RETORNO', '95', '025');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('95200', 'MIRAFLORES', '95', '200');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('97001', 'MITU', '97', '001');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('97161', 'CARURU', '97', '161');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('97511', 'PACOA', '97', '511');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('97666', 'TARAIRA', '97', '666');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('97777', 'PAPUNAUA', '97', '777');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('97889', 'YAVARATE', '97', '889');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('99001', 'PUERTO CARRENO', '99', '001');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('99524', 'LA PRIMAVERA', '99', '524');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('99624', 'SANTA ROSALIA', '99', '624');
INSERT INTO public.ciudades (codigo, ciudad, coddep, codmun) VALUES ('99773', 'CUMARIBO', '99', '773');


--
-- Name: epsriesgos; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.epsriesgos (
    codigo varchar(5),
    nombre varchar(75),
    na integer
);

ALTER TABLE public.epsriesgos OWNER TO escobar;

INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('1', 'ALIANSALUD', 1);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('77', 'ANAS WAYUU', 2);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('72', 'ASMET SALUD', 3);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('188', 'ASOC MUTUAL EMPRESA SOLIDARIA DE SALUD DE NARINO', 4);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('213', 'ASOCIACION INDIGENA DEL CAUCA', 6);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('76', 'ASOCIACION MUTUAL BARRIOS UNIDOS DE QUIBDO', 8);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('71', 'ASOCIACION MUTUAL SER', 9);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('189', 'ASOCIACION MUTUAL SER ESS CONTRIBUTIVO', 7);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('212', 'CABILDOS INDIGENAS DEL RESGUARDO INDIGENA ZENU', 10);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('204', 'CAFAM', 12);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('208', 'CAJACOPI', 14);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('98', 'CAJANAL', 15);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('63', 'CAPITAL SALUD', 16);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('218', 'CAPRECOM', 17);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('20', 'CAPRECOM SUBSIDIADO', 18);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('210', 'CAPRESOCA', 19);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('11', 'COLSEGUROS', 20);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('209', 'COLSUBSIDIO', 11);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('202', 'COMFABOY', 21);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('60', 'COMFACHOCO', 22);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('203', 'COMFACOR', 23);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('17', 'COMFACOR', 13);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('207', 'COMFACUNDI', 24);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('201', 'COMFAMILIAR CARTAGENA', 25);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('205', 'COMFAMILIAR DE LA GUAJIRA', 26);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('78', 'COMFAMILIAR DE PEREIRA', 27);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('1024', 'COMFAMILIAR HUILA', 28);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('41', 'COMFANDI', 29);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('74', 'COMFAORIENTE', 30);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('206', 'COMFASUCRE', 31);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('93', 'COMFENALCO', 32);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('16', 'COMFENALCO ANTIOQUIA', 34);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('13', 'COMFENALCO SANTANDER', 35);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('12', 'COMFENALCO VALLE', 33);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('217', 'COMPARTA', 36);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('8', 'COMPENSAR', 37);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('62', 'CONFAMILIAR NARINO', 38);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('22', 'CONVIDA', 40);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('23', 'COOMEVA', 41);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('215', 'COOSALUD', 42);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('65', 'COSMITET', 43);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('24', 'CRUZ BLANCA', 44);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('27000', 'DIRECCION DEPARTAMANETAL DE SALUD DEL CHOCO', 45);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('211', 'DUSAKA', 5);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('216', 'ECOOPSOS', 47);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('1026', 'ECOPETROL', 48);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('2002', 'EMP. MUTUAL PARA EL DES. INTE. DE SALUD EMDISALUD', 49);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('86', 'EMPRESAS PUBLICAS DE MEDELLIN', 50);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('61', 'EMSANAR', 51);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('94', 'FAMISANAR', 55);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('35', 'FIDUFOSYGA', 39);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('14', 'FONDO DE PASIVO SOCIAL DE F.N.C.', 56);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('4', 'FONDO DE PRESTACIONES SOCIALES DEL MAGISTERIO', 57);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('49', 'FUNDACION MEDICOPREVENTIVO', 58);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('1025', 'FUNDACION SALUD MIA', 54);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('39', 'GOLDEN GROUP', 59);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('15', 'HOSPITAL MILITAR CENTRAL', 60);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('95', 'HUMANA VIVIR', 61);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('6', 'ISS', 62);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('200', 'MALLAMAS', 53);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('3', 'MEDIMAS', 63);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('38', 'MULTIMEDICA', 65);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('37', 'NUEVA EPS', 66);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('214', 'PIJAO SALUD', 52);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('30', 'POLICIA NACIONAL', 64);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('53', 'RED SALUD ATENCION HUMANA', 67);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('92', 'SALUD COLPATRIA', 68);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('55', 'SALUD MIA', 88);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('2', 'SALUD TOTAL', 69);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('2', 'SALUD TOTAL EPS', 69);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('80', 'SALUDCOLOMBIA', 70);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('10', 'SALUDCOOP', 71);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('42', 'SALUDVIDA', 72);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('20', 'SANIDAD MILITAR', 46);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('5', 'SANITAS', 73);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('5', 'SANITAS EPS', 73);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('66', 'SAVIA SALUD', 74);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('31', 'SELVASALUD', 75);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('51', 'SERVICIO MEDICO', 76);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('99', 'SIN AFILIACION', 77);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('0', 'SIN DEFINIR', 78);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('64', 'SISBEN', 79);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('26', 'SOLSALUD', 80);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('18', 'SOS', 81);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('9', 'SURA', 82);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('9', 'SURA EPS', 82);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('7', 'UNIMEC', 83);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('29', 'UNISALUD', 84);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('34', 'UNIV DEL CAUCA UNIDAD SERVICIO DE SALUD', 85);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('36', 'UNIVERSIDAD DE ANTIOQUIA', 86);
INSERT INTO public.epsriesgos (codigo, nombre, na) VALUES ('79', 'UNIVERSIDAD DEL VALLE', 87);


--
-- Name: afpriesgos; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.afpriesgos (
    codigo varchar(5),
    nombre varchar(65),
    na integer,
    activo boolean
);

ALTER TABLE public.afpriesgos OWNER TO escobar;

INSERT INTO public.afpriesgos (codigo, nombre, na, activo) VALUES ('0', 'NO SUMINISTRADO', 1, false);
INSERT INTO public.afpriesgos (codigo, nombre, na, activo) VALUES ('0', 'DESCONOCIDO', 2, false);
INSERT INTO public.afpriesgos (codigo, nombre, na, activo) VALUES ('1', 'COLPATRIA', 3, true);
INSERT INTO public.afpriesgos (codigo, nombre, na, activo) VALUES ('10', 'COLFONDOS', 4, false);
INSERT INTO public.afpriesgos (codigo, nombre, na, activo) VALUES ('11', 'INVERTIR', 5, false);
INSERT INTO public.afpriesgos (codigo, nombre, na, activo) VALUES ('12', 'ING', 6, false);
INSERT INTO public.afpriesgos (codigo, nombre, na, activo) VALUES ('13', 'OLD MUTUAL', 7, false);
INSERT INTO public.afpriesgos (codigo, nombre, na, activo) VALUES ('14', 'PROTECCION', 8, false);
INSERT INTO public.afpriesgos (codigo, nombre, na, activo) VALUES ('16', 'CALDAS', 9, false);
INSERT INTO public.afpriesgos (codigo, nombre, na, activo) VALUES ('19', 'PENSIONAR', 10, false);
INSERT INTO public.afpriesgos (codigo, nombre, na, activo) VALUES ('2', 'COLPENSIONES', 11, false);
INSERT INTO public.afpriesgos (codigo, nombre, na, activo) VALUES ('20', 'FONPRENOR', 12, false);
INSERT INTO public.afpriesgos (codigo, nombre, na, activo) VALUES ('23', 'CAJANAL', 13, false);
INSERT INTO public.afpriesgos (codigo, nombre, na, activo) VALUES ('24', 'PENSIONADOS', 14, false);
INSERT INTO public.afpriesgos (codigo, nombre, na, activo) VALUES ('25', 'BONSALUD', 15, false);
INSERT INTO public.afpriesgos (codigo, nombre, na, activo) VALUES ('3', 'PORVENIR', 16, false);
INSERT INTO public.afpriesgos (codigo, nombre, na, activo) VALUES ('4', 'SKANDIA', 17, false);
INSERT INTO public.afpriesgos (codigo, nombre, na, activo) VALUES ('5', 'HORIZONTE', 18, false);
INSERT INTO public.afpriesgos (codigo, nombre, na, activo) VALUES ('50', 'MUNICIPIO', 19, false);
INSERT INTO public.afpriesgos (codigo, nombre, na, activo) VALUES ('6', 'GANADERA', 20, false);
INSERT INTO public.afpriesgos (codigo, nombre, na, activo) VALUES ('73', 'CONSORCIO  FIDUFOSYGA', 21, false);
INSERT INTO public.afpriesgos (codigo, nombre, na, activo) VALUES ('75', 'CAJA DE PREVISION SOCIAL UNIV.DCT', 22, false);
INSERT INTO public.afpriesgos (codigo, nombre, na, activo) VALUES ('77', 'SERV. DE SALUD DE LA UNIV. DEL CAUCA', 23, false);
INSERT INTO public.afpriesgos (codigo, nombre, na, activo) VALUES ('8', 'DAVIVIR', 24, false);
INSERT INTO public.afpriesgos (codigo, nombre, na, activo) VALUES ('9', 'SKANDIA', 25, false);
INSERT INTO public.afpriesgos (codigo, nombre, na, activo) VALUES ('95', 'CAJA DE PREVISION SOCIAL STAFE DE BOGOTA', 26, false);
INSERT INTO public.afpriesgos (codigo, nombre, na, activo) VALUES ('98', 'CAPRECUNDI', 27, false);
INSERT INTO public.afpriesgos (codigo, nombre, na, activo) VALUES ('99', 'SIN AFP', 28, false);


--
-- Name: server; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.server (
    id numeric NOT NULL,
    nservervt varchar(30),
    nserver varchar(30),
    ndisco varchar(30),
    formato varchar(30),
    servicio varchar(30),
    direccion varchar(30),
    recarp varchar(4),
    recemp varchar(4),
    rectra varchar(4),
    recingret varchar(4),
    entregando smallint,
    recafi varchar(4),
    recfac varchar(4),
    host integer DEFAULT 0
);


ALTER TABLE public.server OWNER TO escobar;

--
-- Name: planillasafiliadosarp; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.planillasafiliadosarp (
    gabineteindex smallint NOT NULL,
    planilla numeric NOT NULL,
    nit varchar(20) NOT NULL,
    tipoid varchar(2) NOT NULL,
    fechaproceso integer,
    descripcion varchar(24),
    lote integer,
    gabinetefuente smallint,
    path varchar,
    estado varchar(15),
    nomdoc varchar(20),
    fechainsert timestamp with time zone DEFAULT now(),
    sade varchar(50),
    fecha_sade numeric
);


ALTER TABLE public.planillasafiliadosarp OWNER TO escobar;

--
-- Name: anexosafiliadosarp; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.anexosafiliadosarp (
    nroanexo integer NOT NULL,
    gabineteindex smallint NOT NULL,
    planilla numeric NOT NULL,
    fechaproceso integer,
    descripcion varchar(24),
    lote integer,
    gabinetefuente smallint,
    nit varchar(20),
    path varchar(80),
    nomdoc varchar,
    fechainsert timestamp with time zone DEFAULT now()
);


ALTER TABLE public.anexosafiliadosarp OWNER TO escobar;

--
-- Name: document_fields; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.document_fields (
    field_id text NOT NULL,
    document_id text NOT NULL,
    field_name text NOT NULL,
    value_text text,
    normalized_value text,
    confidence numeric(6,4) DEFAULT 0 NOT NULL,
    status text DEFAULT 'UNRELIABLE'::text NOT NULL,
    page integer,
    region_id text,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.document_fields OWNER TO escobar;

--
-- Name: document_pages; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.document_pages (
    page_id text NOT NULL,
    document_id text NOT NULL,
    page_number integer NOT NULL,
    source_mode text DEFAULT ''::text NOT NULL,
    text_layer boolean DEFAULT false NOT NULL,
    chars integer DEFAULT 0 NOT NULL,
    text_preview text DEFAULT ''::text NOT NULL,
    details jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.document_pages OWNER TO escobar;

--
-- Name: document_quality_reports; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.document_quality_reports (
    quality_id text NOT NULL,
    document_id text NOT NULL,
    report jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.document_quality_reports OWNER TO escobar;

--
-- Name: document_review_queue; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.document_review_queue (
    review_id text NOT NULL,
    document_id text NOT NULL,
    needs_human_review boolean DEFAULT false NOT NULL,
    priority text DEFAULT 'media'::text NOT NULL,
    reasons jsonb DEFAULT '[]'::jsonb NOT NULL,
    suggested_review_fields jsonb DEFAULT '[]'::jsonb NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.document_review_queue OWNER TO escobar;

--
-- Name: documents; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.documents (
    document_id text NOT NULL,
    source_file jsonb DEFAULT '{}'::jsonb NOT NULL,
    document_classification jsonb DEFAULT '{}'::jsonb NOT NULL,
    processing jsonb DEFAULT '{}'::jsonb NOT NULL,
    retrieval_text text DEFAULT ''::text NOT NULL,
    raw_payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.documents OWNER TO escobar;

--
-- Name: independientes_apolo; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.independientes_apolo (
    idtramite numeric,
    cont_madre text,
    cont_independiente text,
    tipo_tramite text,
    id_empresa text,
    nom_empresa text,
    num_id_trabajador text,
    pri_ape text,
    seg_ape text,
    pri_nom text,
    seg_nom text,
    fechainsert timestamp with time zone DEFAULT now()
);


ALTER TABLE public.independientes_apolo OWNER TO escobar;

--
-- Name: nova_doc_code_examples; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.nova_doc_code_examples (
    id text NOT NULL,
    code integer NOT NULL,
    name text DEFAULT ''::text NOT NULL,
    filename text DEFAULT ''::text NOT NULL,
    norm_name text DEFAULT ''::text NOT NULL,
    tokens_json text DEFAULT '[]'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.nova_doc_code_examples OWNER TO escobar;

--
-- Name: nova_rag_chunks; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.nova_rag_chunks (
    chunk_id text NOT NULL,
    doc_id text NOT NULL,
    source text NOT NULL,
    text_content text NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.nova_rag_chunks OWNER TO escobar;

--
-- Name: proc_log; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.proc_log (
    sr integer NOT NULL,
    fecha_insert timestamp with time zone DEFAULT now(),
    usuario text,
    campo text,
    valor_anterior text,
    valor_nuevo text,
    idtramite text
);


ALTER TABLE public.proc_log OWNER TO escobar;

--
-- Name: proc_log_sr_seq; Type: SEQUENCE; Schema: public; Owner: escobar
--

CREATE SEQUENCE public.proc_log_sr_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.proc_log_sr_seq OWNER TO escobar;

--
-- Name: proc_log_sr_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: escobar
--

ALTER SEQUENCE public.proc_log_sr_seq OWNED BY public.proc_log.sr;


--
-- Name: proc_servicios_causalesdevolucion; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.proc_servicios_causalesdevolucion (
    id_causal integer,
    descripcion text,
    estado integer
);


ALTER TABLE public.proc_servicios_causalesdevolucion OWNER TO escobar;

--
-- Name: proc_servicios_consulta; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.proc_servicios_consulta (
    idtramite numeric,
    estado text,
    fecharegistro timestamp with time zone,
    numerodocumentoempleador text,
    razonsocialempleador text,
    numerodocumento text,
    nombretrabajador text,
    actividad text
);


ALTER TABLE public.proc_servicios_consulta OWNER TO escobar;

--
-- Name: proc_servicios_obtenerarchivosadjuntos; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.proc_servicios_obtenerarchivosadjuntos (
    sr integer,
    idtramite numeric,
    idarchivosadjuntostramite numeric,
    idadjuntostipotramite numeric,
    rutaadjunto text
);


ALTER TABLE public.proc_servicios_obtenerarchivosadjuntos OWNER TO escobar;

--
-- Name: proc_servicios_obtenercomisionestramite; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.proc_servicios_obtenercomisionestramite (
    sr integer,
    idtramite numeric,
    linea integer,
    vendedor text,
    codigo_vendedor text,
    venta text,
    porcentaje text,
    fuente text,
    fecha_insert timestamp with time zone DEFAULT now()
);


ALTER TABLE public.proc_servicios_obtenercomisionestramite OWNER TO escobar;

--
-- Name: proc_servicios_obtenerempleadortramite; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.proc_servicios_obtenerempleadortramite (
    sr integer,
    tipodocumentoempleador text,
    numerodocumentoempleador text,
    telefonoprincipalempleador text,
    direccionempleador text,
    telefonocelularempleador text,
    correoelectronicoempleador text,
    ciudadempleador text,
    zonaempleador text,
    localidadempleador text,
    nombrerepresentantelegal text,
    tipodocumentorepresentantelegal text,
    numerodocumentorepresnetantelegal text,
    correoelectronicorepresentantelegal text,
    actividadeconomicaempleador text,
    razonsocialempleador text,
    naturalezajuridica text,
    tipoafiliacion text,
    tipoaportante text,
    digito_verificacion text,
    idtramite numeric,
    fecha_insert timestamp with time zone DEFAULT now(),
    arlanteriorempleador text
);


ALTER TABLE public.proc_servicios_obtenerempleadortramite OWNER TO escobar;

--
-- Name: proc_servicios_obtenerhoraslaborales; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.proc_servicios_obtenerhoraslaborales (
    sr integer,
    idtramite numeric,
    idtrabajador integer,
    dia integer,
    hora integer,
    valor text
);


ALTER TABLE public.proc_servicios_obtenerhoraslaborales OWNER TO escobar;

--
-- Name: proc_servicios_obtenersedetramite; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.proc_servicios_obtenersedetramite (
    sr integer,
    idtramite numeric,
    codigosede text,
    nombresede text,
    direccion text,
    telefono text,
    correo text,
    ciudad text,
    zona text,
    localidad text,
    departamento text,
    tipodocumentoresponsable text,
    documentoresponsable text,
    nombreresponsable text,
    correoresponsable text,
    fecha_insert timestamp with time zone DEFAULT now()
);


ALTER TABLE public.proc_servicios_obtenersedetramite OWNER TO escobar;

--
-- Name: proc_servicios_obtenertrabajadortramite; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.proc_servicios_obtenertrabajadortramite (
    sr integer,
    idtrabajador integer,
    tipodocumento text,
    numerodocumento text,
    primerapellido text,
    segundoapellido text,
    primernombre text,
    segundonombre text,
    fechanacimiento date,
    sexo text,
    direccionresidencia text,
    ciudadresidencia text,
    localidad text,
    zona text,
    telefono text,
    celular text,
    correoelectronico text,
    eps text,
    actividadeconomica text,
    modalidad text,
    arlanterior text,
    afp text,
    iniciocontrato date,
    finalizacioncontrato date,
    valorcontrato numeric,
    ingresomensual numeric,
    deducciones numeric,
    ibc numeric,
    iniciocobertura date,
    tipoafiliadocotizante integer,
    subtipoafiliadocotizante integer,
    tipocontrato text,
    jornada text,
    suministratransporte text,
    numeromesescontrato numeric,
    tipotramite integer,
    idtramite numeric,
    cargo text,
    codigoct text,
    ct_nombreactividad text,
    ct_codigoactividad text,
    ct_claseriesgo text,
    ct_montocotizacion text
);


ALTER TABLE public.proc_servicios_obtenertrabajadortramite OWNER TO escobar;

--
-- Name: proc_servicios_obtenertramites; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.proc_servicios_obtenertramites (
    sr integer,
    idtipotramite integer,
    tipotramite text,
    idestadotipotramite integer,
    estado text,
    fecharegistro timestamp with time zone,
    causalestramite text,
    observacionsolicitudafiliacion text,
    fecha_insert timestamp with time zone DEFAULT now(),
    idtramite numeric,
    numerocontrato text,
    sucursal text,
    lote text
);


ALTER TABLE public.proc_servicios_obtenertramites OWNER TO escobar;

--
-- Name: proc_servicios_trazabilidad; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.proc_servicios_trazabilidad (
    sr integer,
    idtramite numeric,
    estado numeric,
    usuario_asignado text,
    fecha_asignacion timestamp with time zone DEFAULT now(),
    usuario_gestion text,
    fecha_gestion timestamp with time zone,
    observacion text,
    actividad numeric
);


ALTER TABLE public.proc_servicios_trazabilidad OWNER TO escobar;

--
-- Name: pymes_afiliacion_causas_devolucion; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.pymes_afiliacion_causas_devolucion (
    id_causal integer,
    descripcion_causal text,
    estado_causal integer
);


ALTER TABLE public.pymes_afiliacion_causas_devolucion OWNER TO escobar;

--
-- Name: pymes_afiliacion_sub_causales_devolucion; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.pymes_afiliacion_sub_causales_devolucion (
    id_sub_causal integer,
    descripcion_sub_causal text,
    id_causal integer,
    estado_sub_causal integer
);


ALTER TABLE public.pymes_afiliacion_sub_causales_devolucion OWNER TO escobar;

--
-- Name: tblanpension; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.tblanpension (
    pi text,
    lo text,
    ax text,
    pn integer,
    ce text,
    stiker text
);


ALTER TABLE public.tblanpension OWNER TO escobar;

--
-- Name: tblcodigospension; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.tblcodigospension (
    codigo text,
    categoria text,
    descripcion text
);


ALTER TABLE public.tblcodigospension OWNER TO escobar;

--
-- Name: tblpnpension; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.tblpnpension (
    pi text,
    lo text,
    pn integer,
    ce text,
    codoficina text
);


ALTER TABLE public.tblpnpension OWNER TO escobar;

--
-- Name: tr; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.tr (
    cb varchar(3) NOT NULL,
    nl numeric NOT NULL,
    ob varchar(100),
    fc integer,
    us varchar(8)
);


ALTER TABLE public.tr OWNER TO escobar;

--
-- Name: fun_log_cierre_masivo na; Type: DEFAULT; Schema: auxilios; Owner: escobar
--

ALTER TABLE ONLY auxilios.fun_log_cierre_masivo ALTER COLUMN na SET DEFAULT nextval('auxilios.fun_log_cierre_masivo_na_seq'::regclass);


--
-- Name: fun_log_reclamante na; Type: DEFAULT; Schema: auxilios; Owner: escobar
--

ALTER TABLE ONLY auxilios.fun_log_reclamante ALTER COLUMN na SET DEFAULT nextval('auxilios.fun_log_reclamante_na_seq'::regclass);


--
-- Name: fun_pagos_reclamantes id; Type: DEFAULT; Schema: auxilios; Owner: escobar
--

ALTER TABLE ONLY auxilios.fun_pagos_reclamantes ALTER COLUMN id SET DEFAULT nextval('auxilios.fun_pagos_reclamantes_id_seq'::regclass);


--
-- Name: fun_reclamantes id_ben; Type: DEFAULT; Schema: auxilios; Owner: escobar
--

ALTER TABLE ONLY auxilios.fun_reclamantes ALTER COLUMN id_ben SET DEFAULT nextval('auxilios.fun_reclamantes_id_ben_seq'::regclass);


--
-- Name: not_bloqueo na; Type: DEFAULT; Schema: auxilios; Owner: escobar
--

ALTER TABLE ONLY auxilios.not_bloqueo ALTER COLUMN na SET DEFAULT nextval('auxilios.not_bloqueo_na_seq'::regclass);


--
-- Name: not_estados_post_solicitud id_estado_post_solicitud; Type: DEFAULT; Schema: auxilios; Owner: escobar
--

ALTER TABLE ONLY auxilios.not_estados_post_solicitud ALTER COLUMN id_estado_post_solicitud SET DEFAULT nextval('auxilios.not_estados_post_solicitud_id_estado_post_solicitud_seq'::regclass);


--
-- Name: not_marca_imagenes id_marca; Type: DEFAULT; Schema: auxilios; Owner: escobar
--

ALTER TABLE ONLY auxilios.not_marca_imagenes ALTER COLUMN id_marca SET DEFAULT nextval('auxilios.not_marca_imagenes_id_marca_seq'::regclass);


--
-- Name: not_reclamantes id_ben; Type: DEFAULT; Schema: auxilios; Owner: escobar
--

ALTER TABLE ONLY auxilios.not_reclamantes ALTER COLUMN id_ben SET DEFAULT nextval('auxilios.not_reclamantes_id_ben_seq'::regclass);


--
-- Name: proc_log sr; Type: DEFAULT; Schema: public; Owner: escobar
--

ALTER TABLE ONLY public.proc_log ALTER COLUMN sr SET DEFAULT nextval('public.proc_log_sr_seq'::regclass);


--
-- Name: fun_bancos fun_bancos_pkey; Type: CONSTRAINT; Schema: auxilios; Owner: escobar
--

ALTER TABLE ONLY auxilios.fun_bancos
    ADD CONSTRAINT fun_bancos_pkey PRIMARY KEY (cod_banco);


--
-- Name: fun_log_cierre_masivo fun_log_cierre_masivo_pkey; Type: CONSTRAINT; Schema: auxilios; Owner: escobar
--

ALTER TABLE ONLY auxilios.fun_log_cierre_masivo
    ADD CONSTRAINT fun_log_cierre_masivo_pkey PRIMARY KEY (na);


--
-- Name: fun_log_reclamante fun_log_reclamante_pkey; Type: CONSTRAINT; Schema: auxilios; Owner: escobar
--

ALTER TABLE ONLY auxilios.fun_log_reclamante
    ADD CONSTRAINT fun_log_reclamante_pkey PRIMARY KEY (na);


--
-- Name: fun_pagos_reclamantes fun_pagos_reclamantes_pkey; Type: CONSTRAINT; Schema: auxilios; Owner: escobar
--

ALTER TABLE ONLY auxilios.fun_pagos_reclamantes
    ADD CONSTRAINT fun_pagos_reclamantes_pkey PRIMARY KEY (id);


--
-- Name: fun_reclamantes fun_reclamantes_pkey; Type: CONSTRAINT; Schema: auxilios; Owner: escobar
--

ALTER TABLE ONLY auxilios.fun_reclamantes
    ADD CONSTRAINT fun_reclamantes_pkey PRIMARY KEY (id_ben);


--
-- Name: not_bloqueo not_bloqueo_pkey; Type: CONSTRAINT; Schema: auxilios; Owner: escobar
--

ALTER TABLE ONLY auxilios.not_bloqueo
    ADD CONSTRAINT not_bloqueo_pkey PRIMARY KEY (na);


--
-- Name: not_documentos not_documentos_pkey; Type: CONSTRAINT; Schema: auxilios; Owner: escobar
--

ALTER TABLE ONLY auxilios.not_documentos
    ADD CONSTRAINT not_documentos_pkey PRIMARY KEY (id_documento);


--
-- Name: not_estado_post not_estado_post_pkey; Type: CONSTRAINT; Schema: auxilios; Owner: escobar
--

ALTER TABLE ONLY auxilios.not_estado_post
    ADD CONSTRAINT not_estado_post_pkey PRIMARY KEY (estado_post_id);


--
-- Name: not_estados_post_solicitud not_estados_post_solicitud_pkey; Type: CONSTRAINT; Schema: auxilios; Owner: escobar
--

ALTER TABLE ONLY auxilios.not_estados_post_solicitud
    ADD CONSTRAINT not_estados_post_solicitud_pkey PRIMARY KEY (id_estado_post_solicitud);


--
-- Name: not_marca_imagenes not_marca_imagenes_pkey; Type: CONSTRAINT; Schema: auxilios; Owner: escobar
--

ALTER TABLE ONLY auxilios.not_marca_imagenes
    ADD CONSTRAINT not_marca_imagenes_pkey PRIMARY KEY (id_marca);


--
-- Name: not_reclamantes not_reclamantes_pkey; Type: CONSTRAINT; Schema: auxilios; Owner: escobar
--

ALTER TABLE ONLY auxilios.not_reclamantes
    ADD CONSTRAINT not_reclamantes_pkey PRIMARY KEY (id_ben);


--
-- Name: document_fields document_fields_pkey; Type: CONSTRAINT; Schema: public; Owner: escobar
--

ALTER TABLE ONLY public.document_fields
    ADD CONSTRAINT document_fields_pkey PRIMARY KEY (field_id);


--
-- Name: document_pages document_pages_pkey; Type: CONSTRAINT; Schema: public; Owner: escobar
--

ALTER TABLE ONLY public.document_pages
    ADD CONSTRAINT document_pages_pkey PRIMARY KEY (page_id);


--
-- Name: document_quality_reports document_quality_reports_pkey; Type: CONSTRAINT; Schema: public; Owner: escobar
--

ALTER TABLE ONLY public.document_quality_reports
    ADD CONSTRAINT document_quality_reports_pkey PRIMARY KEY (quality_id);


--
-- Name: document_review_queue document_review_queue_pkey; Type: CONSTRAINT; Schema: public; Owner: escobar
--

ALTER TABLE ONLY public.document_review_queue
    ADD CONSTRAINT document_review_queue_pkey PRIMARY KEY (review_id);


--
-- Name: documents documents_pkey; Type: CONSTRAINT; Schema: public; Owner: escobar
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT documents_pkey PRIMARY KEY (document_id);


--
-- Name: nova_doc_code_examples nova_doc_code_examples_pkey; Type: CONSTRAINT; Schema: public; Owner: escobar
--

ALTER TABLE ONLY public.nova_doc_code_examples
    ADD CONSTRAINT nova_doc_code_examples_pkey PRIMARY KEY (id);


--
-- Name: nova_rag_chunks nova_rag_chunks_pkey; Type: CONSTRAINT; Schema: public; Owner: escobar
--

ALTER TABLE ONLY public.nova_rag_chunks
    ADD CONSTRAINT nova_rag_chunks_pkey PRIMARY KEY (chunk_id);


--
-- Name: proc_log proc_log_pkey; Type: CONSTRAINT; Schema: public; Owner: escobar
--

ALTER TABLE ONLY public.proc_log
    ADD CONSTRAINT proc_log_pkey PRIMARY KEY (sr);


--
-- Name: document_fields_document_id_idx; Type: INDEX; Schema: public; Owner: escobar
--

CREATE INDEX document_fields_document_id_idx ON public.document_fields USING btree (document_id);


--
-- Name: document_pages_document_id_idx; Type: INDEX; Schema: public; Owner: escobar
--

CREATE INDEX document_pages_document_id_idx ON public.document_pages USING btree (document_id);


--
-- Name: document_quality_reports_document_id_idx; Type: INDEX; Schema: public; Owner: escobar
--

CREATE INDEX document_quality_reports_document_id_idx ON public.document_quality_reports USING btree (document_id);


--
-- Name: document_review_queue_document_id_idx; Type: INDEX; Schema: public; Owner: escobar
--

CREATE INDEX document_review_queue_document_id_idx ON public.document_review_queue USING btree (document_id);


--
-- Name: documents_created_at_idx; Type: INDEX; Schema: public; Owner: escobar
--

CREATE INDEX documents_created_at_idx ON public.documents USING btree (created_at DESC);


--
-- Name: nova_rag_chunks_created_idx; Type: INDEX; Schema: public; Owner: escobar
--

CREATE INDEX nova_rag_chunks_created_idx ON public.nova_rag_chunks USING btree (created_at DESC);


--
-- Name: nova_rag_chunks_doc_id_idx; Type: INDEX; Schema: public; Owner: escobar
--

CREATE INDEX nova_rag_chunks_doc_id_idx ON public.nova_rag_chunks USING btree (doc_id);


--
-- PostgreSQL database dump complete
--

\unrestrict D6394tWrleeRfzfmQHAnxhEVU8sxbafwtX2rqQcXWwmVqQPVAfOblLgrzFAZnhq

