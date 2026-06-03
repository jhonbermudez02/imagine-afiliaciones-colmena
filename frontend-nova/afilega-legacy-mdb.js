// Reglas fuente de verdad: data/source_registry/Afiliaciones.mdb (VersionL 5.2).
// Este MDB prevalece sobre matrices/catálogos de otros sistemas.

export const AFILEGA_MDB_VERSION = '5.2';

export const AFILEGA_MDB_DV_MULTIPLIERS = [71, 67, 59, 53, 47, 43, 41, 37, 29, 23, 19, 17, 13, 7, 3];

export const AFILEGA_MDB_DOCUMENT_TYPES = [
    ['formulario_afiliacion', 'AFILIACION', '01'],
    ['anexo_sedes', 'SEDES', '02'],
    ['relacion_ingreso_trabajadores', 'LISTADO TRABAJADORES', '03'],
    ['carta_presentacion_trabajador', 'CARTA', '04'],
    ['cedula', 'CEDULA', '05'],
    ['rut_contratista', 'RUT', '06'],
    ['camara_comercio_contratante', 'CAMARA DE COMERCIO', '07'],
    ['nomina_anexa', 'NOMINA ANEXA', '10'],
];

export const AFILEGA_MDB_FIELD_LIMITS = {
    razon_social: 200,
    empleador_tipo_documento: 3,
    nit: 20,
    nit_dv: 1,
    codigo_actividad_economica: 10,
    direccion_empresa: 50,
    correo_empresa: 80,
    numero_radicacion: 30,
    tipo_persona: 30,
    rep_legal_nombre_completo: 80,
    rep_legal_tipo_documento: 3,
    rep_legal_numero_documento: 15,
    rep_legal_correo: 80,
    responsable_sede_principal_nombre_completo: 80,
    responsable_sede_principal_tipo_documento: 3,
    responsable_sede_principal_numero_documento: 15,
    empresa_forma_pago: 3,
    empresa_tipo_aportante: 3,
    empresa_vinculador_laboral: 3,
    empresa_regimen: 3,
    empresa_naturaleza: 3,
    empresa_clase_sociedad: 3,
    empresa_tamano: 3,
    empresa_grupo: 3,
    empresa_tipo_localizacion: 3,
    empresa_zona_localizacion: 3,
    empresa_pyme: 1,
    empresa_olcsa: 1,
    empresa_contratante: 1,
    empresa_arl_anterior: 50,
    tipo_documento_afiliado: 3,
    documento_afiliado: 15,
    primer_apellido: 80,
    segundo_apellido: 80,
    primer_nombre: 80,
    segundo_nombre: 80,
    eps: 30,
    afp: 30,
    cargo_actividad: 150,
    tipo_cotizante: 3,
    subtipo_cotizante: 3,
    numero_contrato: 50,
    tipo_contrato: 50,
    a_numero_sedes: 3,
    a_numero_centros_trabajo: 3,
    a_numero_inicial_trabajadores_estudiantes: 6,
    a_valor_total_nomina: 20,
    b_numero_sedes: 3,
    b_numero_centros_trabajo: 3,
    b_numero_total_trabajadores_estudiantes: 6,
    b_monto_total_cotizacion: 20,
    estado_cuenta_empleador: 40,
    sede_nombre: 80,
    sede_centro_trabajo_nombre: 60,
    sede_codigo: 10,
    sede_direccion: 80,
    sede_telefono: 10,
    sede_correo: 80,
    sede_codigo_actividad: 7,
    sede_transporte: 1,
    sede_grado: 3,
    sede_tarifa: 10,
    sede_tipo_localizacion: 3,
    sede_contacto: 80,
    sede_cargo_contacto: 80,
    sede_fax: 10,
    nuevo_centro_trabajo: 80,
    nuevo_codigo_ocupacion: 10,
    novedad_contrato: 50,
    novedad_estado: 1,
    novedad_autoliquidacion: 1,
    novedad_origen: 1,
    novedad_dias: 3,
    novedad_valor_anterior: 20,
    novedad_valor_nuevo: 20,
    novedad_traslado: 1,
    camara_actividad_principal: 250,
};

export const AFILEGA_MDB_ALLOWED_NOVEDAD_CODES = new Set(['00', '08']);
export const AFILEGA_MDB_ALLOWED_TIPO_COTIZANTE = new Set(['1', '19']);
export const AFILEGA_MDB_DEFAULT_SUBTIPO_COTIZANTE = '999';
export const AFILEGA_MDB_ALLOWED_BOOLEAN_SN = new Set(['S', 'N']);
export const AFILEGA_MDB_ALLOWED_ZONA = new Set(['U', 'R']);
export const AFILEGA_MDB_ALLOWED_NOVEDAD_ESTADO = new Set(['1']);
export const AFILEGA_MDB_ALLOWED_NOVEDAD_AUTOLIQUIDACION = new Set(['N']);
export const AFILEGA_MDB_ALLOWED_NOVEDAD_ORIGEN = new Set(['C']);

export const AFILEGA_DEPARTMENT_CODES = {
    'AMAZONAS': '91',
    'ANTIOQUIA': '05',
    'ARAUCA': '81',
    'ATLANTICO': '08',
    'ATLÁNTICO': '08',
    'BOGOTA, D.C.': '11',
    'BOGOTÁ, D.C.': '11',
    'BOLIVAR': '13',
    'BOLÍVAR': '13',
    'BOYACA': '15',
    'BOYACÁ': '15',
    'CALDAS': '17',
    'CAQUETA': '18',
    'CAQUETÁ': '18',
    'CASANARE': '85',
    'CAUCA': '19',
    'CESAR': '20',
    'CHOCO': '27',
    'CHOCÓ': '27',
    'CORDOBA': '23',
    'CÓRDOBA': '23',
    'CUNDINAMARCA': '25',
    'GUAINIA': '94',
    'GUAINÍA': '94',
    'GUAVIARE': '95',
    'HUILA': '41',
    'LA GUAJIRA': '44',
    'MAGDALENA': '47',
    'META': '50',
    'NARINO': '52',
    'NARIÑO': '52',
    'NORTE DE SANTANDER': '54',
    'PUTUMAYO': '86',
    'QUINDIO': '63',
    'QUINDÍO': '63',
    'RISARALDA': '66',
    'SAN ANDRES': '88',
    'SAN ANDRÉS': '88',
    'SAN ANDRES Y PROVIDENCIA': '88',
    'SAN ANDRÉS Y PROVIDENCIA': '88',
    'SANTANDER': '68',
    'SUCRE': '70',
    'TOLIMA': '73',
    'VALLE DEL CAUCA': '76',
    'VAUPES': '97',
    'VAUPÉS': '97',
    'VICHADA': '99',
};

export function calculateAfilegaNitDv(nit) {
    const digits = String(nit || '').replace(/\D/g, '');
    if (!digits || digits.length > AFILEGA_MDB_DV_MULTIPLIERS.length) return '';
    const padded = digits.padStart(AFILEGA_MDB_DV_MULTIPLIERS.length, '0');
    const total = padded
        .split('')
        .reduce((sum, digit, index) => sum + Number(digit) * AFILEGA_MDB_DV_MULTIPLIERS[index], 0);
    const mod = total % 11;
    return String(mod > 1 ? 11 - mod : mod);
}

export function normalizeLegacyToken(value) {
    return String(value || '')
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .trim()
        .toUpperCase();
}

export function departmentLegacyCode(value) {
    const rawDigits = String(value || '').replace(/\D/g, '');
    if (/^\d{2}$/.test(rawDigits)) return rawDigits;
    return AFILEGA_DEPARTMENT_CODES[normalizeLegacyToken(value)] || '';
}

export function municipalityLegacyCode(value) {
    const rawDigits = String(value || '').replace(/\D/g, '');
    if (/^\d{3}$/.test(rawDigits)) return rawDigits;
    if (/^\d{5}$/.test(rawDigits)) return rawDigits.slice(-3);
    const normalized = normalizeLegacyToken(value);
    if (normalized === 'BOGOTA, D.C.' || normalized === 'BOGOTA D.C.' || normalized === 'BOGOTA') return '001';
    return '';
}
