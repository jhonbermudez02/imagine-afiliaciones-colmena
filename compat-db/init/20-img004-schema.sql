--
-- PostgreSQL database dump
--
-- Base real: img004 (alias interno "wimg004" en compat-backend/conexion.php).
-- Archivo definitivo de backups (bk*) y radicacion (afi_rad/afi_devoluciones) tras el
-- reproceso de un lote, mas la tabla lc (maestro de cola de indexacion consultado por
-- las acciones SL/SL-2). Ademas: ux (login), consultores, salarios (referencia) y una
-- copia de solo lectura de planillasafiliadosarp (consultada por Exis_PalillaAfiliadoARP
-- para verificar planillas ya archivadas).

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
    f07 double precision,
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
    contratoant numeric,
    tipoempresa varchar,
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
    lote integer NOT NULL,
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
    afi_fechainsert timestamp DEFAULT now(),
    afi_rad_obs varchar(80),
    afi_rad_clase varchar(20),
    afi_rad_fechadigitacion varchar(10) DEFAULT 0,
    afi_rad_fechaplano varchar(10) DEFAULT 0,
    afi_rad_fechadevol varchar(10) DEFAULT 0,
    afi_rad_nit bigint,
    afi_rad_fecharecibido varchar(10) DEFAULT 0,
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
    afi_rad_canal varchar,
    afi_rad_sub_causal_dev varchar
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
-- Name: ux; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.ux (
    us varchar(20) NOT NULL,
    pw varchar(20) NOT NULL,
    dependencia varchar(10) DEFAULT 0,
    ai smallint,
    au smallint,
    ad smallint,
    ac smallint,
    an smallint,
    revmed smallint DEFAULT 0 NOT NULL,
    dev smallint DEFAULT 0 NOT NULL,
    conmed smallint DEFAULT 0 NOT NULL,
    c1 smallint,
    c2 smallint,
    c3 smallint,
    c4 smallint,
    c5 smallint,
    c6 smallint,
    c7 smallint,
    c8 smallint,
    c9 smallint,
    c10 smallint,
    c11 smallint,
    c12 smallint,
    recaudoarp smallint DEFAULT 0 NOT NULL,
    nm varchar(40),
    r1 numeric,
    r2 numeric,
    nv varchar(25),
    pa varchar(30),
    sa varchar(30),
    nom varchar(50),
    cargo varchar,
    email varchar(60),
    oficina varchar(50),
    ciudad varchar(50),
    usuariocra varchar(20),
    feccrea integer,
    nitras varchar(20) DEFAULT 0,
    fechatrab integer,
    fechainicial integer DEFAULT 0,
    fechafinal integer DEFAULT 0,
    validacion varchar(20),
    nivelplataforma varchar(20),
    autorizaciones smallint DEFAULT 0 NOT NULL,
    otraciudad smallint DEFAULT 0 NOT NULL,
    rezagos smallint DEFAULT 0 NOT NULL,
    cartas smallint DEFAULT 0 NOT NULL,
    password varchar(40),
    perfil varchar(100) DEFAULT 'basico'::character varying,
    identificacion varchar(15),
    administrativo varchar(10),
    pensionados_rol varchar(2),
    usuario_cod integer NOT NULL,
    act varchar(1) DEFAULT 0 NOT NULL,
    llamadas_rol varchar DEFAULT 0 NOT NULL,
    area numeric DEFAULT 0,
    sr integer NOT NULL,
    habilitado numeric DEFAULT 0
);


ALTER TABLE public.ux OWNER TO escobar;

--
-- Name: ux_usuario_cod_seq; Type: SEQUENCE; Schema: public; Owner: escobar
--

CREATE SEQUENCE public.ux_usuario_cod_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.ux_usuario_cod_seq OWNER TO escobar;

ALTER SEQUENCE public.ux_usuario_cod_seq OWNED BY public.ux.usuario_cod;


ALTER TABLE ONLY public.ux ALTER COLUMN usuario_cod SET DEFAULT nextval('public.ux_usuario_cod_seq'::regclass);

--
-- Name: ux_sr_seq; Type: SEQUENCE; Schema: public; Owner: escobar
--

CREATE SEQUENCE public.ux_sr_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.ux_sr_seq OWNER TO escobar;

ALTER SEQUENCE public.ux_sr_seq OWNED BY public.ux.sr;


ALTER TABLE ONLY public.ux ALTER COLUMN sr SET DEFAULT nextval('public.ux_sr_seq'::regclass);

--
-- Name: consultores; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.consultores (
    id_consultor integer NOT NULL,
    cedula numeric,
    nombre varchar
);


ALTER TABLE public.consultores OWNER TO escobar;

--
-- Name: consultores_id_consultor_seq; Type: SEQUENCE; Schema: public; Owner: escobar
--

CREATE SEQUENCE public.consultores_id_consultor_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.consultores_id_consultor_seq OWNER TO escobar;

ALTER SEQUENCE public.consultores_id_consultor_seq OWNED BY public.consultores.id_consultor;


ALTER TABLE ONLY public.consultores ALTER COLUMN id_consultor SET DEFAULT nextval('public.consultores_id_consultor_seq'::regclass);

--
-- Name: salarios; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.salarios (
    cod_salario integer NOT NULL,
    rige timestamp without time zone,
    sector_urbano double precision,
    sector_rural double precision,
    fechainsert timestamp with time zone DEFAULT now(),
    periodo varchar(4) DEFAULT 0 NOT NULL,
    ipc double precision DEFAULT 0 NOT NULL
);


ALTER TABLE public.salarios OWNER TO escobar;

--
-- Name: salarios_cod_salario_seq; Type: SEQUENCE; Schema: public; Owner: escobar
--

CREATE SEQUENCE public.salarios_cod_salario_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.salarios_cod_salario_seq OWNER TO escobar;

ALTER SEQUENCE public.salarios_cod_salario_seq OWNED BY public.salarios.cod_salario;


ALTER TABLE ONLY public.salarios ALTER COLUMN cod_salario SET DEFAULT nextval('public.salarios_cod_salario_seq'::regclass);

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
-- Name: tr; Type: TABLE; Schema: public; Owner: escobar
-- Requerida por el reproceso real (AfiliacionesReproceso.php borra wimg004.tr por nl).
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
-- PostgreSQL database dump complete
--
