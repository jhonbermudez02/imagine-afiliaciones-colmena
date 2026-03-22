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
    sr integer,
    lt text,
    li text,
    f28 text,
    f29 text,
    f30 text,
    f31 text,
    f32 text,
    f33 text,
    f34 text,
    f35 text,
    f37 text,
    f38 text,
    direccion text,
    telefono text,
    celular text,
    mail text,
    jornada text,
    tipo_salario text,
    f40 text,
    f41 text,
    municipio text
);


ALTER TABLE public.brafiliadosarp OWNER TO escobar;

--
-- Name: brcentrot; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.brcentrot (
    sr integer,
    lote text,
    codigoct text,
    codigoactividad text,
    nombreactividad text,
    ciudad text,
    zona text,
    direccion text,
    telefono text,
    tipodocumento text,
    id_responsable text,
    primerapellido text,
    segundoapellido text,
    primernombre text,
    segundonombre text,
    claseriesgo text,
    grado text,
    mail text,
    montocotizacion text,
    tasa text,
    totaltrabajadores text
);


ALTER TABLE public.brcentrot OWNER TO escobar;

--
-- Name: brempresasarp; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.brempresasarp (
    sr integer,
    lt text,
    f01 text,
    f50 text,
    f48 text,
    f51 text,
    f15 text,
    f12 text,
    f14 text,
    f18 text,
    f59 text,
    tp text,
    clase text,
    aut46 text,
    aut47 text,
    aut48 text,
    carcont2 text,
    contratoant text,
    dircont1 text,
    doccont1 text,
    f05 text,
    f06 text,
    f09 text,
    f20 text,
    f23 text,
    f49 text,
    f55 text,
    f56 text,
    f57 text,
    f60 text,
    f62 text,
    f65 text,
    f67 text,
    f69 text,
    f70 text,
    f71 text,
    fecesc text,
    fecloc text,
    grupoecono text,
    localidad text,
    nomcont2 text,
    nomdepcont2 text,
    subtipocodigo text,
    tipoafiliacion text,
    tipoafiliado text,
    tipoaportante text,
    tipocodigo text,
    tipoempresa text,
    zona text
);


ALTER TABLE public.brempresasarp OWNER TO escobar;

--
-- Name: brwdcomisiones; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.brwdcomisiones (
    sr integer,
    lote text,
    linea text,
    vendedor text,
    codigo_vendedor text,
    venta text,
    porcentaje text
);


ALTER TABLE public.brwdcomisiones OWNER TO escobar;

--
-- Name: brwddias; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.brwddias (
    sr integer,
    lote text,
    dia text,
    h1 text,
    h2 text,
    h3 text,
    h4 text,
    h5 text,
    h6 text,
    h7 text,
    h8 text,
    h9 text,
    h10 text,
    h11 text,
    h12 text,
    h13 text,
    h14 text,
    h15 text,
    h16 text,
    h17 text,
    h18 text,
    h19 text,
    h20 text,
    h21 text,
    h22 text,
    h23 text,
    h24 text
);


ALTER TABLE public.brwddias OWNER TO escobar;

--
-- Name: brwdestudiantes; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.brwdestudiantes (
    sr integer,
    lote text,
    linea text,
    codigo_ct text,
    tipodocumento text,
    documento text,
    primer_apellido text,
    segundo_apellido text,
    primer_nombre text,
    segundo_nombre text,
    fecha_nacimiento text,
    sexo text,
    cargo text,
    salario text,
    eps text,
    afp text,
    direccion text,
    telefono text,
    celular text,
    correo text,
    ciudad text,
    localidad text,
    zona text,
    departamento text,
    jornada text,
    modalidad text,
    codigo_actividad text,
    fecha_inicio text,
    fecha_final text,
    meses text,
    tipo_contrato text,
    monto_contrato text,
    lunes text,
    martes text,
    miercoles text,
    jueves text,
    viernes text,
    sabado text,
    domingo text,
    d1 text,
    d2 text,
    d3 text,
    d4 text,
    d5 text,
    d6 text,
    d7 text,
    d8 text,
    d9 text,
    d10 text,
    d11 text,
    d12 text,
    d13 text,
    d14 text,
    d15 text,
    d16 text,
    d17 text,
    d18 text,
    d19 text,
    d20 text,
    d21 text,
    d22 text,
    d23 text,
    d24 text,
    tipo_salario text
);


ALTER TABLE public.brwdestudiantes OWNER TO escobar;

--
-- Name: brwdindependientes; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.brwdindependientes (
    sr integer,
    lote text,
    linea text,
    tipodocumento text,
    documento text,
    primer_apellido text,
    segundo_apellido text,
    primer_nombre text,
    segundo_nombre text,
    fecha_nacimiento text,
    sexo text,
    direccion text,
    departamento text,
    municipio text,
    zona text,
    localidad text,
    telefono text,
    celular text,
    correo text,
    codigo_eps text,
    codigo_afp text,
    ibc text,
    actividad_economica text,
    tipo_contrato text,
    transporte text,
    fecha_inicio_contrato text,
    fecha_fin_contrato text,
    meses_contrato text,
    valor_contrato text,
    valor_mensual text,
    lunes text,
    martes text,
    miercoles text,
    jueves text,
    viernes text,
    sabado text,
    domingo text,
    d1 text,
    d2 text,
    d3 text,
    d4 text,
    d5 text,
    d6 text,
    d7 text,
    d8 text,
    d9 text,
    d10 text,
    d11 text,
    d12 text,
    d13 text,
    d14 text,
    d15 text,
    d16 text,
    d17 text,
    d18 text,
    d19 text,
    d20 text,
    d21 text,
    d22 text,
    d23 text,
    d24 text,
    codigo_ct text,
    localidad_ct text,
    zona_ct text,
    tipo_cotizante text,
    subtipo_cotizante text,
    tipo_salario text,
    afp text,
    arl_anterior text,
    codigo_arl_anterior text,
    eps text,
    linea_origen text,
    modalidad text,
    tipotramite text
);


ALTER TABLE public.brwdindependientes OWNER TO escobar;

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
    cb text,
    fc text,
    nl text,
    ob text,
    us text
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

