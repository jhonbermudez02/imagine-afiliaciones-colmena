--
-- PostgreSQL database dump
--
-- Base real: br (alias interno "ybr" en compat-backend/conexion.php).
-- Archivo definitivo de br* entregados (copiados desde temporal.br* durante el reproceso
-- de AfiliacionesReproceso.php).

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

SET default_tablespace = '';

SET default_table_access_method = heap;

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
    f06 varchar,
    f04 varchar,
    f05 integer,
    f27 smallint,
    f25 smallint,
    f49 varchar,
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
    f10 varchar,
    f03 smallint,
    f08 smallint,
    f17 smallint,
    f11 numeric,
    f13 varchar,
    f19 integer,
    f54 smallint,
    f58 smallint,
    f60 smallint,
    f61 numeric,
    f69 varchar,
    f64 smallint,
    f65 numeric,
    f70 varchar,
    f66 smallint,
    f67 numeric,
    f71 varchar,
    f68 smallint,
    doccont1 numeric,
    nomcont1 varchar,
    carcont1 varchar,
    dircont1 varchar,
    ciucont1 varchar,
    nomciucont1 varchar,
    depcont1 varchar,
    nomdepcont1 varchar,
    telcont1 numeric,
    telcont21 numeric,
    emailcont1 varchar,
    doccont2 numeric,
    nomcont2 varchar,
    carcont2 varchar,
    dircont2 varchar,
    ciucont2 varchar,
    nomciucont2 varchar,
    depcont2 varchar,
    nomdepcont2 varchar,
    telcont2 numeric,
    telcont22 numeric,
    emailcont2 varchar,
    dev numeric,
    fp integer,
    tp varchar,
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
    d1 varchar,
    us varchar,
    ob text,
    combo50 varchar,
    combo15 varchar,
    combo16 varchar,
    combo05 varchar,
    combo56 varchar,
    combo24 varchar,
    combo23 varchar,
    combo57 varchar,
    pi varchar,
    clase varchar,
    obdev varchar,
    fechainsert timestamp DEFAULT now(),
    contratoant numeric,
    tipoempresa varchar,
    grupoecono varchar,
    f07 double precision DEFAULT 0,
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
    codigo_tipo_trabajador varchar,
    tipo_trabajador varchar,
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
-- PostgreSQL database dump complete
--
