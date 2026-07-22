--
-- Esquema de las tablas "proc_servicios_*" (y afines: pymes_afiliacion_*,
-- independientes_apolo, proc_log) usadas por compat-backend.
--
-- Estas tablas NO son parte del esquema legacy real (Access/br/img004): las
-- creo este proyecto como capa intermedia que imita el esquema del sistema
-- externo "Ruta de Inclusión" (Portal Soporte Masivo Ruta Inclusión). El flujo
-- de aprobación de un caso primero parsea el Excel/documentos hacia estas
-- tablas (una fila por empleador/sede/trabajador/comisión), y luego
-- _load_proc_servicios_to_engine las lee para construir las filas legacy
-- reales (brempresasarp/brafiliadosarp/etc.).
--
-- Antes, cada endpoint de compat-backend creaba su propia tabla con
-- "CREATE TABLE IF NOT EXISTS" en el primer request que la necesitaba. Eso
-- funciona, pero implica que una base de datos nueva (ej. un ambiente de
-- pruebas apuntado por primera vez a un Postgres externo) recién "descubre"
-- que le faltan tablas cuando el flujo ya está corriendo -y falla con 503-.
-- Este script consolida el esquema completo (extraído con pg_dump de una base
-- de desarrollo con todas las columnas ya migradas) para correrlo una sola vez
-- al aprovisionar cualquier ambiente nuevo, igual que 10/20/30-*-schema.sql.
--
-- Uso (Postgres externo, fuera de docker-entrypoint-initdb.d):
--   psql -h <host> -U <usuario> -d temporal -f 40-temporal-proc-servicios-schema.sql
--
-- Es seguro correrlo más de una vez (todo con IF NOT EXISTS).
--
-- Nota: el código sigue teniendo sus propios "CREATE TABLE IF NOT EXISTS" y
-- "ALTER TABLE ADD COLUMN IF NOT EXISTS" como red de seguridad (son gratis y
-- evitan que esto se repita si alguien olvida correr este script en un
-- ambiente nuevo, o si se agrega una columna nueva antes de actualizar este
-- archivo) -- no se quitaron del código, este script solo evita que se
-- disparen en la práctica.
--

CREATE TABLE IF NOT EXISTS public.independientes_apolo (
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

CREATE SEQUENCE IF NOT EXISTS public.proc_log_sr_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

CREATE TABLE IF NOT EXISTS public.proc_log (
    sr integer NOT NULL DEFAULT nextval('public.proc_log_sr_seq'::regclass),
    fecha_insert timestamp with time zone DEFAULT now(),
    usuario text,
    campo text,
    valor_anterior text,
    valor_nuevo text,
    idtramite text
);

ALTER SEQUENCE public.proc_log_sr_seq OWNED BY public.proc_log.sr;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'proc_log_pkey'
    ) THEN
        ALTER TABLE ONLY public.proc_log ADD CONSTRAINT proc_log_pkey PRIMARY KEY (sr);
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS public.proc_servicios_causalesdevolucion (
    id_causal integer,
    descripcion text,
    estado integer
);

CREATE TABLE IF NOT EXISTS public.proc_servicios_consulta (
    idtramite numeric,
    estado text,
    fecharegistro timestamp with time zone,
    numerodocumentoempleador text,
    razonsocialempleador text,
    numerodocumento text,
    nombretrabajador text,
    actividad text
);

CREATE TABLE IF NOT EXISTS public.proc_servicios_obtenerarchivosadjuntos (
    sr integer,
    idtramite numeric,
    idarchivosadjuntostramite numeric,
    idadjuntostipotramite numeric,
    rutaadjunto text
);

CREATE TABLE IF NOT EXISTS public.proc_servicios_obtenercomisionestramite (
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

CREATE TABLE IF NOT EXISTS public.proc_servicios_obtenerempleadortramite (
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
    arlanteriorempleador text,
    tipoempresa text,
    tiponegociodetectado text,
    numerosedes text,
    numerocentrostrabajo text,
    numerotrabajadoresestudiantes text,
    valornomina text,
    autorizacion1 text,
    autorizacion2 text,
    autorizacion3 text,
    departamentoempleador text,
    respsedeprimerapellido text,
    respsedesegundoapellido text,
    respsedeprimernombre text,
    respsedesegundonombre text,
    respsedetipodocumento text,
    respsedenumerodocumento text,
    respsedecorreo text,
    sedeprincipalcorreo text,
    nombrelugar text,
    lugarafiliacion text,
    sedeprincipalcodigo text,
    sedeprincipalnombre text,
    numeroradicacion text,
    profilenumerotrabajadores text
);

CREATE TABLE IF NOT EXISTS public.proc_servicios_obtenerhoraslaborales (
    sr integer,
    idtramite numeric,
    idtrabajador integer,
    dia integer,
    hora integer,
    valor text
);

CREATE TABLE IF NOT EXISTS public.proc_servicios_obtenersedetramite (
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

CREATE TABLE IF NOT EXISTS public.proc_servicios_obtenertrabajadortramite (
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
    ct_montocotizacion text,
    ct_ciudad text,
    ct_departamento text,
    ct_zona text,
    ct_direccion text,
    ct_telefono text,
    ct_correo text,
    ct_responsable_pa text,
    ct_responsable_sa text,
    ct_responsable_pn text,
    ct_responsable_sn text,
    ct_responsable_td text,
    ct_responsable_doc text,
    ct_responsable_correo text,
    ct_cantidadtrabajadores text,
    departamento text
);

CREATE TABLE IF NOT EXISTS public.proc_servicios_obtenertramites (
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

CREATE TABLE IF NOT EXISTS public.proc_servicios_trazabilidad (
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

CREATE TABLE IF NOT EXISTS public.pymes_afiliacion_causas_devolucion (
    id_causal integer,
    descripcion_causal text,
    estado_causal integer
);

CREATE TABLE IF NOT EXISTS public.pymes_afiliacion_sub_causales_devolucion (
    id_sub_causal integer,
    descripcion_sub_causal text,
    id_causal integer,
    estado_sub_causal integer
);
