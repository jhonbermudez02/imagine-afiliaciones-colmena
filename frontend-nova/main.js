// ============================================================
// AFILEGA_FA_IMA_LA_V2 · MAIN.JS
// ============================================================

import { COLOMBIA_LOCATIONS } from './colombia-locations.js';
import { CAMARA_COMERCIO_ACTIVITY_CATALOG } from './camara-comercio-catalog.js';
import { CARGO_TRABAJADORES_CATALOG } from './cargo-trabajadores-catalog.js';
import { TIPO_COTIZANTE_TRABAJADORES_CATALOG } from './tipo-cotizante-trabajadores-catalog.js';
import { VINCULADOR_LABORAL_CONTRATANTE_CATALOG } from './vinculador-laboral-contratante-catalog.js';
import {
    ACTIVITY_RISK_CATALOG,
    AFP_CATALOG_NORMALIZED,
    AFP_CATALOG_OPTIONS,
    EPS_CATALOG_NORMALIZED,
    EPS_CATALOG_OPTIONS,
    SMMLV_BY_YEAR,
} from './digitacion-catalogs.js';
import {
    AFILEGA_MDB_ALLOWED_NOVEDAD_CODES,
    AFILEGA_MDB_ALLOWED_NOVEDAD_AUTOLIQUIDACION,
    AFILEGA_MDB_ALLOWED_NOVEDAD_ESTADO,
    AFILEGA_MDB_ALLOWED_NOVEDAD_ORIGEN,
    AFILEGA_MDB_ALLOWED_TIPO_COTIZANTE,
    AFILEGA_MDB_ALLOWED_BOOLEAN_SN,
    AFILEGA_MDB_ALLOWED_ZONA,
    AFILEGA_MDB_DEFAULT_SUBTIPO_COTIZANTE,
    AFILEGA_MDB_DOCUMENT_TYPES,
    AFILEGA_MDB_FIELD_LIMITS,
    AFILEGA_MDB_VERSION,
    calculateAfilegaNitDv,
    departmentLegacyCode,
    municipalityLegacyCode,
} from './afilega-legacy-mdb.js';
import { AFILEGA_MDB_VALUE_CATALOGS } from './afilega-mdb-value-catalogs.js';

const rawApiUrl = (import.meta.env.VITE_API_URL || '').trim();
const normalizedApiUrl = rawApiUrl.replace(/\/+$/, '');
const API_URL = (
    !normalizedApiUrl
    || normalizedApiUrl === '/api'
    || /^(https?:)?\/\/(localhost|127\.0\.0\.1)(:\d+)?(\/api)?$/i.test(normalizedApiUrl)
) ? '' : normalizedApiUrl;

const PROFILE_KEY = 'afilega-fa-ima-la-v2-profile-v1';
const TESTER_KEY = 'afilega-fa-ima-la-v2-tester-v1';
const PROCESS_STATE_KEY = 'afilega-fa-ima-la-v2-process-v1';
const CLASSIFICATION_ORDER_KEY = 'afilega-fa-ima-la-v2-classif-order-v1';
const DIGITACION_DRAFT_KEY = 'afilega-fa-ima-la-v2-digitacion-draft-v1';

const OPERATION_OPTIONS = {
    colima: { key: 'colima', short: 'AFILEGA', name: 'AFILEGA_FA_IMA_LA_V2', brand: '', validation: 'Reglas AFILEGA' },
};

const REVIEW_TYPE_OPTIONS = [
    ['formulario_afiliacion', 'Afiliación',        '01'],
    ['anexo_sedes',           'Sedes ·01',         '01'],
    ['listado_trabajadores',  'Listados',           '03'],
    ['comision',              'Comisión',           '02'],
    ['carta',                 'Carta',              '29'],
    ['camara_comercio',       'Cámara de comercio', '05'],
    ['cedula',                'Cédula',             '06'],
    ['inspector',             'Inspector',          '17'],
    ['constancia_afiliacion', 'Verificación',       '07'],
    ['rut',                   'RUT / DIAN',         '08'],
    ['entrega_documentos',    'Entrega Doc',        '10'],
    ['soporte_pagos',         'Pagos',              '11'],
    ['contrato',              'Contrato',           '13'],
    ['eps',                   'EPS',                '14'],
    ['afp',                   'AFP',                '15'],
    ['paz_y_salvo',           'Paz y Salvo',        '16'],
    ['eps_afp',               'EPS / AFP',          '17'],
    ['identificacion_peligros','Id. Peligros',      '20'],
    ['examen_preocupacional', 'Examen Pre-ocup.',   '21'],
    ['autorizacion',          'Autorización',       '98'],
    ['beneficiario_final',    'Beneficiario Final', '27'],
    ['sat',                   'SAT',                '99'],
    ['pdf',                   'PDF / Imagen',       '99'],
];

const DOCUMENT_DISPLAY_PRIORITY = [
    'formulario_afiliacion',
    'anexo_sedes',
    'camara_comercio',
    'rut',
    'cedula',
    'soporte_pagos',
    'inspector',
    'autorizacion',
    'entrega_documentos',
    'comision',
    'carta',
    'beneficiario_final',
];
const DOCUMENT_DISPLAY_PRIORITY_MAP = new Map(DOCUMENT_DISPLAY_PRIORITY.map((type, index) => [type, index]));

// ── Estado global ────────────────────────────────────────────
let activeCaseId = null;
let activeCasePayload = null;
let activeDocumentUrl = null;
let testerRoster = [];
let productionLoadController = null;
let workflowLaunchInFlight = false;
let workflowStatusPollTimer = null;
let flowRadicacionPromise = null;
let selectedColmenaCaseIds = new Set();
let currentView = 'bandeja';
let bandejaActiveTab = 'todos';
let allCases = [];
let classifDocListBusyCount = 0;

function applyClassifDocListBusyState() {
    const el = document.getElementById('classifDocList');
    if (!el) return;
    const busy = classifDocListBusyCount > 0;
    el.classList.toggle('is-busy', busy);
    el.setAttribute('aria-busy', busy ? 'true' : 'false');
    el.querySelectorAll('button, input, select, textarea').forEach(control => {
        control.disabled = busy;
    });
}

function setClassifDocListBusy(loading, message = 'Procesando cambios...') {
    if (loading) classifDocListBusyCount += 1;
    else classifDocListBusyCount = Math.max(0, classifDocListBusyCount - 1);
    const el = document.getElementById('classifDocList');
    if (el) el.dataset.busyMessage = message;
    applyClassifDocListBusyState();
}

async function refreshClassifAfterManualChange(caseId) {
    if (!caseId) return null;
    const r = await fetchWithRetry(caseApiUrl(caseId, '/refresh-validations'), { method: 'POST' });
    const payload = await r.json();
    activeCaseId = caseId;
    activeCasePayload = payload;
    if (currentView === 'clasificacion') {
        renderClassifBlockers(payload);
        renderClassifDocList(payload);
    }
    return payload;
}

async function refreshClassifAfterComisionChange(caseId, filename) {
    const payload = await refreshClassifAfterManualChange(caseId);
    if (!payload || currentView !== 'clasificacion' || !filename) return payload;
    const item = buildDocItems(payload).find(doc => doc.file === filename);
    if (item) {
        const docList = document.getElementById('classifDocList');
        docList?.querySelectorAll('.doc-item').forEach(el => {
            el.classList.toggle('active', el.dataset.file === filename);
        });
        renderClassifActions(item, payload);
    }
    return payload;
}

async function runFullCaseAnalyzeFromClassif(caseId) {
    if (!caseId) return null;
    if (!confirm('¿Ejecutar análisis completo? Se volverán a leer Excel y documentos, y puede tardar más.')) return null;
    setClassifDocListBusy(true, 'Ejecutando análisis completo...');
    try {
        showToast('Ejecutando análisis completo del contrato...', 'info', 3000);
        const r = await fetchWithRetry(caseApiUrl(caseId, '/analyze'), { method: 'POST' });
        const payload = await r.json();
        activeCaseId = caseId;
        activeCasePayload = payload;
        renderClassifBlockers(payload);
        renderClassifDocList(payload);
        const preview = document.getElementById('classifPreviewBody');
        if (preview) preview.innerHTML = '<div class="empty-state">Selecciona un documento</div>';
        const actions = document.getElementById('classifPreviewActions');
        if (actions) actions.innerHTML = '';
        showToast('Análisis completo finalizado.', 'ok', 3500);
        return payload;
    } catch(e) {
        showToast('No se pudo ejecutar /analyze: ' + e.message, 'err', 6000);
        return null;
    } finally {
        setClassifDocListBusy(false);
    }
}

function normalizeOperation(value = '') {
    return 'colima';
}

function readOperation() {
    return 'colima';
}

function saveOperation(operation) {
    return 'colima';
}

function currentOperation() {
    return OPERATION_OPTIONS[readOperation()] || OPERATION_OPTIONS.colima;
}

function operationApiUrl(path, params = {}) {
    const url = new URL(`${API_URL}${path}`, window.location.origin);
    url.searchParams.set('operation', readOperation());
    for (const [key, value] of Object.entries(params || {})) {
        if (value !== undefined && value !== null && value !== '') url.searchParams.set(key, String(value));
    }
    return url.toString();
}

function caseApiUrl(caseId, suffix = '', params = {}) {
    return operationApiUrl(`/api/cases/${encodeURIComponent(caseId)}${suffix}`, params);
}

// ── Utilidades ───────────────────────────────────────────────
function escapeHtml(v) {
    return String(v || '').replace(/[&<>"]/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
}

function normalizeText(v = '') {
    return String(v || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
}

function onlyDigits(v = '') {
    return String(v || '').replace(/\D/g, '');
}

function formatDateTime(v) {
    if (!v) return 'n/d';
    const d = new Date(v);
    if (isNaN(d.getTime())) return String(v);
    return d.toLocaleString('es-CO', { year:'numeric', month:'short', day:'numeric', hour:'2-digit', minute:'2-digit' });
}

function formatDate(v) {
    if (!v) return 'n/d';
    const d = new Date(v);
    if (isNaN(d.getTime())) return String(v).slice(0,10);
    return d.toLocaleDateString('es-CO', { year:'numeric', month:'short', day:'numeric' });
}

function formatDateOnlyValue(value) {
    const text = String(value || '').trim();
    if (!text) return '';
    const dateTimeMatch = text.match(/^(\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{4})[ T]+/);
    if (dateTimeMatch) return dateTimeMatch[1];
    const d = new Date(text);
    if (!isNaN(d.getTime())) return formatDate(text);
    return text.replace(/\s+\d{1,2}:\d{2}(?::\d{2})?(?:\s*(?:AM|PM))?$/i, '');
}

function formatCurrency(v) {
    const n = Number(v);
    if (!Number.isFinite(n)) return String(v || 'n/d');
    return new Intl.NumberFormat('es-CO', { style:'currency', currency:'COP', minimumFractionDigits:0 }).format(n);
}

function formatThousandsNumber(value) {
    const text = String(value || '').trim();
    if (!text) return '';
    const normalized = text.replace(/\s/g, '');
    const match = normalized.match(/^([0-9.,]+)(-[0-9A-Za-z])?$/);
    if (!match) return text;
    const digits = match[1].replace(/\D/g, '');
    if (digits.length < 4) return text;
    return `${new Intl.NumberFormat('es-CO').format(Number(digits))}${match[2] || ''}`;
}

function localizeStatus(v) {
    const map = {
        uploaded:'Pendiente', completed:'completado', blocked:'bloqueado',
        failed:'fallido', pending:'Pendiente', analyzed:'analizado',
        stopped_prevalidacion:'No pasó validación', ok:'ok', degraded:'degradado',
    };
    return map[String(v||'').toLowerCase()] || String(v||'n/d');
}

function getReviewTypeLabel(type) {
    const normalizedType = canonicalDocumentType(type);
    const match = REVIEW_TYPE_OPTIONS.find(([v]) => v === normalizedType);
    return match ? match[1] : String(type||'Sin clasificar').replace(/_/g,' ');
}

function getReviewTypeCode(type) {
    const normalizedType = canonicalDocumentType(type);
    const match = REVIEW_TYPE_OPTIONS.find(([v]) => v === normalizedType);
    return match ? match[2] : null;
}

function getReviewTypeLabelWithCode(type, legacyCode) {
    const label = getReviewTypeLabel(type);
    // Para sedes numeradas, el label ya incluye el número — no duplicar con legacy_code
    if (String(type||'').startsWith('anexo_sedes')) return label;
    const code = legacyCode != null ? String(legacyCode).padStart(2,'0') : getReviewTypeCode(type);
    return code ? `${label} ·${code}` : label;
}

function canonicalDocumentType(type = '') {
    const key = String(type || '').trim();
    if (key.startsWith('anexo_sedes')) return 'anexo_sedes';
    if (key === 'soporte_ingresos') return 'soporte_pagos';
    return key;
}

function documentDisplayRank(item) {
    if (item?.kind === 'xlsx' || canonicalDocumentType(item?.type) === 'xlsx') return 10_000;
    const rank = DOCUMENT_DISPLAY_PRIORITY_MAP.get(canonicalDocumentType(item?.type));
    return rank ?? 1_000;
}

function sortDocItemsByDisplayPriority(items) {
    return [...items].sort((a, b) => {
        const rankDiff = documentDisplayRank(a) - documentDisplayRank(b);
        if (rankDiff !== 0) return rankDiff;
        return (a._sourceIndex ?? 0) - (b._sourceIndex ?? 0);
    }).map(({ _sourceIndex, ...item }) => item);
}

function applyWorkspaceDocumentOrder(items, workspaceOrder = []) {
    if (!Array.isArray(workspaceOrder) || !workspaceOrder.length) return items;
    const byFile = Object.fromEntries(items.map(item => [item.file, item]));
    const ordered = [];
    for (const filename of workspaceOrder) {
        if (byFile[filename]) {
            ordered.push(byFile[filename]);
            delete byFile[filename];
        }
    }
    for (const item of Object.values(byFile)) ordered.push(item);
    return ordered;
}

function sortDocumentGroupsByDisplayPriority(groups) {
    return [...(groups || [])].sort((a, b) => {
        const aType = a?.document_type || a?.type || a?.label || '';
        const bType = b?.document_type || b?.type || b?.label || '';
        const aRank = DOCUMENT_DISPLAY_PRIORITY_MAP.get(canonicalDocumentType(aType)) ?? 1_000;
        const bRank = DOCUMENT_DISPLAY_PRIORITY_MAP.get(canonicalDocumentType(bType)) ?? 1_000;
        if (aRank !== bRank) return aRank - bRank;
        return canonicalDocumentType(aType).localeCompare(canonicalDocumentType(bType));
    });
}


// ── Notificaciones elegantes (reemplaza alert) ──────────────
function showToast(msg, type = 'info', duration = 4000) {
    let container = document.getElementById('toastContainer');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toastContainer';
        container.style.cssText = 'position:fixed;bottom:24px;right:24px;z-index:9999;display:flex;flex-direction:column;gap:8px;max-width:360px';
        document.body.appendChild(container);
    }
    const toast = document.createElement('div');
    // Acentos brillantes para que resalten sobre el fondo oscuro del toast.
    const colors = {info:'#60a5fa', ok:'#34d399', err:'#f87171', warn:'#fbbf24'};
    const icons = {info:'ℹ️', ok:'✅', err:'❌', warn:'⚠️'};
    // Fondo oscuro solido + texto claro: siempre visible sobre la pagina clara
    // (antes usaba var(--c-bg-2)/var(--c-text-1), que no existen -> fondo transparente).
    toast.style.cssText = `background:#1f2937;border:1px solid rgba(255,255,255,0.10);border-left:4px solid ${colors[type]||colors.info};border-radius:8px;padding:12px 16px;font-size:13px;color:#f9fafb;box-shadow:0 6px 22px rgba(0,0,0,0.35);display:flex;gap:10px;align-items:flex-start;animation:slideIn 0.2s ease`;
    toast.innerHTML = `<span style="flex-shrink:0">${icons[type]||icons.info}</span><span style="flex:1">${escapeHtml(msg)}</span><button onclick="this.parentElement.remove()" style="background:none;border:none;cursor:pointer;color:rgba(255,255,255,0.6);font-size:16px;padding:0;line-height:1">×</button>`;
    container.appendChild(toast);
    if (duration > 0) setTimeout(() => toast.remove(), duration);
}

async function fetchWithRetry(url, options = {}, attempts = 2) {
    let lastErr;
    for (let i = 0; i < attempts; i++) {
        try {
            const r = await fetch(url, options);
            // Detectar si la respuesta es HTML en vez de JSON (ej: error de túnel Cloudflare)
            const contentType = r.headers.get('content-type') || '';
            if (contentType.includes('text/html')) {
                throw new Error('Sin conexión con el servidor. Verifica que el sistema esté disponible.');
            }
            if (!r.ok) {
                const t = await r.text().catch(()=>'');
                let detail = '';
                try {
                    const parsed = JSON.parse(t);
                    if (Array.isArray(parsed?.detail)) {
                        detail = parsed.detail.map(e => e.msg || JSON.stringify(e)).join('; ');
                    } else if (parsed?.detail && typeof parsed.detail === 'object') {
                        detail = parsed.detail.message || parsed.detail.detail || JSON.stringify(parsed.detail);
                    } else {
                        detail = parsed?.detail || parsed?.message || t;
                    }
                } catch { detail = t; }
                throw new Error(detail || `HTTP ${r.status}`);
            }
            return r;
        } catch(e) {
            lastErr = e;
            if (i < attempts - 1) await new Promise(r => setTimeout(r, 400));
        }
    }
    throw lastErr;
}

function markFlowRadicacionUsed() {
    const field = document.getElementById('flowNumeroRadicacion');
    if (field) field.dataset.radUsed = '1';
}

async function ensureFlowNumeroRadicacion({ force = false } = {}) {
    const field = document.getElementById('flowNumeroRadicacion');
    if (!field) return '';
    field.readOnly = true;
    field.setAttribute('aria-readonly', 'true');
    if (force) {
        field.value = '';
        delete field.dataset.radUsed;
    }
    if (field.value && !force) return field.value;
    if (!flowRadicacionPromise) {
        flowRadicacionPromise = fetchWithRetry(`${API_URL}/api/radicacion/next`, { method: 'POST' })
            .then(async response => {
                const payload = await response.json().catch(() => ({}));
                if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
                return payload;
            })
            .finally(() => { flowRadicacionPromise = null; });
    }
    try {
        const payload = await flowRadicacionPromise;
        const nextValue = String(payload.numero_radicacion || '').trim();
        if (nextValue) field.value = nextValue;
        return field.value;
    } catch (error) {
        console.error('ensureFlowNumeroRadicacion:', error);
        showToast('No fue posible obtener el consecutivo de radicación.', 'err');
        return '';
    }
}

// ── Sesión / perfil ──────────────────────────────────────────
function readProfile() {
    try {
        const profile = String(localStorage.getItem(PROFILE_KEY) || 'imagine').toLowerCase();
        return profile === 'imagine' ? 'imagine' : 'imagine';
    } catch { return 'imagine'; }
}
function saveProfile(p) {
    try { localStorage.setItem(PROFILE_KEY, p); } catch {}
}
function readTester() {
    try { return JSON.parse(localStorage.getItem(TESTER_KEY)||'{}'); } catch { return {}; }
}
function saveTester(t) {
    try { localStorage.setItem(TESTER_KEY, JSON.stringify(t)); } catch {}
}
function clearSession() {
    try { localStorage.removeItem(PROFILE_KEY); localStorage.removeItem(TESTER_KEY); } catch {}
}
function hasSession() {
    const t = readTester();
    return Boolean(readProfile() && t.email);
}

// ── URL helpers ──────────────────────────────────────────────
function caseFileUrl(caseId, filename, inline = false) {
    const path = `/api/cases/${encodeURIComponent(caseId)}/files/${filename.split('/').map(encodeURIComponent).join('/')}`;
    const url = new URL(`${API_URL}${path}`, window.location.origin);
    url.searchParams.set('operation', readOperation());
    if (inline) url.searchParams.set('inline', '1');
    return url.toString();
}

function documentViewerUrl(caseId, filename, inline = true) {
    const url = caseFileUrl(caseId, filename, inline);
    if (/\.pdf$/i.test(filename || '')) {
        return `${url}#navpanes=0&view=FitH&zoom=page-width`;
    }
    return url;
}

function case926Url(caseId) {
    return caseApiUrl(caseId, '/926');
}

// ── Resolvers de caso ────────────────────────────────────────
function blockerText(b) {
    if (!b) return '';
    if (typeof b === 'string') return b;
    if (typeof b === 'object') {
        return b.message || b.detalle || b.detail || b.descripcion ||
               b.texto || b.text || b.reason || b.motivo ||
               (b.field ? `${b.field}: ${b.value || b.valor || ''}` : '') ||
               JSON.stringify(b).replace(/[{}"]/g,'').slice(0,120);
    }
    return String(b);
}

function isXlsxOrFormularioBlocker(b) {
    const code = String(b?.code || b?.raw?.code || '').toUpperCase();
    const msg = normalizeText(b?.message || blockerText(b?.raw || b));
    const isMissingDocumentBlocker =
        code.startsWith('MISSING_REQUIRED_DOCUMENTS') ||
        (
            ['faltan soportes', 'faltan documentos', 'soportes obligatorios', 'documentos obligatorios']
                .some(token => msg.includes(token)) &&
            !code.startsWith('XLSX_')
        );
    if (isMissingDocumentBlocker) return false;
    if (b?.can_accept_exception === false || b?.raw?.can_accept_exception === false) return true;
    const field = normalizeText(b?.field || b?.raw?.field || '');
    const cell = normalizeText(b?.cell || b?.raw?.cell || '');
    const legacyXlsxCodes = new Set([
        'EDAD_MINIMA_INVALIDA',
        'EDAD_MAXIMA_INVALIDA',
        'FECHA_NACIMIENTO_ANTIGUA_INVALIDA',
    ]);
    if (legacyXlsxCodes.has(code)) return true;
    const documentValidationCodes = [
        'CEDULA_MATCH',
        'RUT_MATCH',
        'CAMARA_',
        'EMPRESA_MATCH',
        'CONTRATO_MATCH',
        'AUTORIZACION_',
        'MISSING_REQUIRED_DOCUMENTS',
        'DOCUMENTS_',
        'ENTREGA_',
        'COMISION_',
        'ASESOR_',
    ];
    if (documentValidationCodes.some(prefix => code.startsWith(prefix))) return false;
    return code.startsWith('XLSX_') ||
           code.startsWith('FORMULARIO_') ||
           code.startsWith('RESPONSABLE_SEDE_') ||
           code.startsWith('SEDE_PRINCIPAL_') ||
           Boolean(field || cell) ||
           msg.startsWith('el xlsx ') ||
           msg.startsWith('el campo ') ||
           msg.startsWith('el correo ') ||
           msg.startsWith('la cedula del responsable ') ||
           msg.startsWith('la cédula del responsable ') ||
           msg.startsWith('el telefono de la sede principal ') ||
           msg.startsWith('el teléfono de la sede principal ') ||
           msg.startsWith('la direccion de la sede principal ') ||
           msg.startsWith('la dirección de la sede principal ') ||
           msg.includes('trabajadores, fila') ||
           (msg.includes(' en sede ') && msg.includes(', fila')) ||
           /\b[a-z]{1,3}\d{1,3}\b/i.test(String(b?.message || blockerText(b?.raw || b) || ''));
}

function validationExceptionButtonHtml(b, index, style = '') {
    if (isXlsxOrFormularioBlocker(b)) return '';
    const styleAttr = style ? ` style="${style}"` : '';
    return `<button class="btn-secondary validation-exception-btn" data-blocker-idx="${index}" type="button"${styleAttr}>Aceptar para este contrato</button>`;
}

function renderBlockers(blockers, cssClass = 'report-blocker') {
    if (!blockers?.length) return '';
    return blockers.map(b => `
        <div class="${cssClass}">
            <span>✗</span>
            <span>${escapeHtml(blockerText(b))}</span>
        </div>
    `).join('');
}

function getValidationBlockerRecords(payload) {
    const a = payload?.analysis || {};
    const reasons = a.validacion_resumen?.precheck?.motivos_de_rechazo || [];
    if (Array.isArray(reasons) && reasons.length) {
        return reasons.map((item, index) => ({
            code: item?.code || 'VALIDATION_ALERT',
            message: blockerText(item),
            fingerprint: item?.message ? (item?.fingerprint || '') : '',
            can_accept_exception: item?.can_accept_exception !== false,
            index,
            raw: item,
        }));
    }
    const decisionRecords = a.decision?.blocker_records || [];
    if (Array.isArray(decisionRecords) && decisionRecords.length) {
        return decisionRecords.map((item, index) => ({
            code: item?.code || 'VALIDATION_ALERT',
            message: blockerText(item),
            fingerprint: item?.message ? (item?.fingerprint || '') : '',
            can_accept_exception: item?.can_accept_exception !== false,
            index,
            raw: item,
        }));
    }
    const blockers = a.decision?.blockers || [];
    return (Array.isArray(blockers) ? blockers : []).map((message, index) => ({
        code: 'VALIDATION_ALERT',
        message: blockerText(message),
        fingerprint: '',
        index,
        raw: message,
    }));
}

function getAcceptedValidationExceptions(payload) {
    const a = payload?.analysis || {};
    return a.validacion_resumen?.precheck?.accepted_exceptions ||
           a.validacion_resumen?.accepted_exceptions ||
           [];
}

async function acceptValidationException(caseId, blocker) {
    if (!caseId || !blocker) return false;
    const shortMsg = String(blocker.message || '').slice(0, 220);
    const reason = prompt(
        `Justificación para aceptar este hallazgo solo en este contrato:\n\n${shortMsg}`,
        'Validado manualmente por operador'
    );
    if (!reason || !reason.trim()) return false;
    const note = prompt('Observación adicional opcional:', '') || '';
    const tester = readTester();
    await fetchWithRetry(caseApiUrl(caseId, '/validation-exceptions'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            code: blocker.code || 'VALIDATION_ALERT',
            message: blocker.message || '',
            fingerprint: blocker.fingerprint || '',
            reason: reason.trim(),
            note: note.trim(),
            operator: tester.email || tester.name || '',
        }),
    });
    showToast('Excepción guardada. Actualizando validaciones...', 'info', 2500);
    const payload = await refreshClassifAfterManualChange(caseId);
    if (!payload) return false;
    activeCasePayload = payload;
    const reportEl = document.getElementById('reporteContent');
    if (reportEl && currentView === 'reporte') renderReporte(reportEl, payload);
    const validationEl = document.getElementById('validacionContent');
    if (validationEl && currentView === 'validacion') renderValidacionOCR(validationEl, payload);
    if (currentView === 'clasificacion') {
        const { empresa, nit } = resolveCase(payload);
        const labelEl = document.getElementById('classifCaseLabel');
        if (labelEl) {
            labelEl.style.display = '';
            labelEl.innerHTML = `Contrato · ${escapeHtml(empresa)}${nit !== 'n/d' ? ` · ${escapeHtml(nit)}` : ''}`;
        }
        renderClassifBlockers(payload);
        renderClassifDocList(payload);
    }
    const resultCard = document.getElementById('workflowResultCard');
    if (resultCard && resultCard.style.display !== 'none') renderWorkflowResult(payload);
    loadBandeja().catch(() => {});
    showToast('Contrato reprocesado con la excepción aplicada.', 'ok', 4500);
    return true;
}

function setValidationExceptionButtonsLoading(root, activeButton, loading = true) {
    const buttons = Array.from((root || document).querySelectorAll('.validation-exception-btn'));
    buttons.forEach(btn => {
        if (loading) {
            if (!btn.dataset.originalText) btn.dataset.originalText = btn.textContent || 'Aceptar para este contrato';
            btn.disabled = true;
            btn.textContent = btn === activeButton ? 'Guardando y reprocesando...' : 'Esperando reproceso...';
        } else {
            btn.disabled = false;
            btn.textContent = btn.dataset.originalText || 'Aceptar para este contrato';
        }
    });
}

function resolveContractNumber(analysis, item = {}) {
    const a = analysis || {};
    const wf = a.workflow_run || {};
    const profile = (a.xlsx_profile || {}).profile || {};
    const formFields = (a.xlsx_profile || {}).form_fields || {};
    const output926 = wf.output_926 || a.output_926 || {};
    const legacy = output926.legacy || {};
    const digitacionValues = item.digitacion_values || a.digitacion_manual?.values || a.digitacion_prefill?.values || {};
    return item.contract_number || item.numero_contrato || item.nro_contrato || item.nro_afiliacion ||
        legacy.numero_afiliacion || legacy.nro_afiliacion ||
        digitacionValues.numero_contrato || digitacionValues.numero_radicacion ||
        profile.numero_contrato || profile.nro_contrato || profile.numero_radicacion || profile.nro_radicacion ||
        formFields.numero_radicacion || '';
}

function resolveManualApproval(item) {
    const a = item?.analysis || {};
    const wf = a.workflow_run || {};
    const approval = item?.manual_approval || a.manual_approval || {};
    if (approval && approval.approved) return approval;
    const output926 = wf.output_926 || a.output_926 || {};
    const legacy926 = output926.legacy || {};
    const draft926 = output926.draft || {};
    const revokedReason = normalizeText(approval?.revoked_reason || '');
    if (
        approval &&
        normalizeText(approval.status || '') === 'revoked' &&
        approval.approved_at &&
        revokedReason.includes('reproceso de validaciones') &&
        (legacy926.ok || legacy926.available || draft926.content)
    ) {
        return { ...approval, approved: true, status: 'approved', source: 'legacy_reprocess_recovery' };
    }
    const status = normalizeText(item?.status || wf.status || '');
    const finalStatus = normalizeText(item?.final_status || '');
    if (status === 'approved' || finalStatus === 'aprobado') {
        return { approved: true, status: 'approved', source: 'status' };
    }
    return null;
}

function isCaseManuallyApproved(item) {
    return Boolean(resolveManualApproval(item));
}

function getCaseBlockerRecords(payload) {
    const a = payload?.analysis || {};
    const decision = a.decision || {};
    const precheck = a.validacion_resumen?.precheck || {};
    const records = Array.isArray(decision.blocker_records) ? decision.blocker_records :
        Array.isArray(precheck.motivos_de_rechazo) ? precheck.motivos_de_rechazo : [];
    const blockers = Array.isArray(decision.blockers) ? decision.blockers : [];
    return { records, blockers, hasActiveBlockers: records.length > 0 || blockers.length > 0 };
}

function isCaseAprobableAfterManualExceptions(payload, estado = '', decisionStatus = '') {
    const a = payload?.analysis || {};
    const validationOk = Boolean(a.validacion_resumen?.ok || a.validacion_resumen?.precheck?.approved);
    const currentDecisionStatus = normalizeText(decisionStatus || a.decision?.recommended_status || '');
    const statusText = normalizeText(estado || a.workflow_run?.status || payload?.status || '');
    const { hasActiveBlockers } = getCaseBlockerRecords(payload);
    if (hasActiveBlockers) return false;
    return (
        currentDecisionStatus === 'aprobable' ||
        validationOk ||
        statusText.includes('aprob') ||
        statusText === 'completed'
    );
}

function resolveCase(item) {
    const a = item?.analysis || {};
    const wf = a.workflow_run || {};
    const profile = (a.xlsx_profile || {}).profile || {};
    const report = wf.executive_report_final || wf.executive_report_precheck || a.reporte_ejecutivo || {};
    const resumen = report.resumen_ejecutivo || {};
    const empresa = resumen.empresa || profile.empresa || item?.empresa || item?.label || item?.id || 'n/d';
    const nit = resumen.nit || profile.nit || item?.nit || 'n/d';
    const rawStatus = wf.status || item?.status || '';
    const approved = isCaseManuallyApproved(item);
    const status = approved ? 'approved' : rawStatus;
    const finalStatus = approved ? 'APROBADO' : 'NO APROBADO';
    const fecha = resumen.fecha_proceso_human || item?.updated_at?.slice(0,10) || 'n/d';
    const has926 = Boolean(item?.has_926 || (wf.output_926||{}).legacy?.ok);
    const filename = (wf.output_926||{}).legacy?.filename || item?.filename || 'archivo_plano.txt';
    const blockers = Array.isArray(item?.blockers) ? item.blockers : [];
    const formFields = a.xlsx_profile?.form_fields || {};
    const nroAfiliacion = resolveContractNumber(a, item);
    const nroRadicacion = formFields.numero_radicacion || profile.numero_radicacion || profile.nro_radicacion || a.formulario_profile?.numero_radicacion || '';
    return { empresa, nit, status, finalStatus, fecha, has926, filename, blockers, nroAfiliacion, nroRadicacion, approved };
}

function isApprovedCaseStatus(status, finalStatus) {
    const s = normalizeText(status);
    const f = normalizeText(finalStatus);
    if (f === 'aprobado' || f === 'ok' || s === 'approved') {
        return true;
    }
    if (
        f.includes('no aprob') ||
        f.includes('rechaz') ||
        f.includes('observ') ||
        f.includes('bloque') ||
        ['failed', 'stopped_prevalidacion'].includes(s)
    ) {
        return false;
    }
    return false;
}

function caseStatusClass(status, finalStatus) {
    return isApprovedCaseStatus(status, finalStatus) ? 'ok' : 'err';
}

function casePillLabel(status, finalStatus) {
    return isApprovedCaseStatus(status, finalStatus) ? 'Aprobado' : 'No aprobado';
}

async function approveCaseManually(caseId, container) {
    if (!caseId) return;
    const confirmed = confirm('¿Confirmas que quieres aprobar este contrato?\n\nEsta acción marcará el contrato como aprobado manualmente.');
    if (!confirmed) return;
    const reason = prompt('Justificación para aprobar este contrato:', 'Aprobado manualmente por operador');
    if (!reason || !reason.trim()) return;
    const tester = readTester();
    const btn = container?.querySelector('#approveCaseBtn');
    if (btn) { btn.disabled = true; btn.textContent = 'Aprobando...'; }
    try {
        const r = await fetchWithRetry(caseApiUrl(caseId, '/approve'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                reason: reason.trim(),
                operator: tester.email || tester.name || '',
            }),
        });
        const payload = await r.json();
        activeCasePayload = payload;
        showToast('Contrato aprobado manualmente. Iniciando generación del plano 926...', 'ok', 4500);
        try {
            if (btn) btn.textContent = 'Generando 926...';
            await fetchWithRetry(caseApiUrl(caseId, '/run-workflow'), { method: 'POST' });
            showToast('Generación del plano 926 iniciada. Estará disponible para Colmena cuando termine el flujo.', 'info', 6500);
        } catch(workflowError) {
            showToast('El contrato quedó aprobado, pero no pude iniciar la generación del 926: ' + workflowError.message, 'warn', 8000);
        }
        if (container?.id === 'reporteContent') renderFormularioReporte(container, payload);
        else if (container) renderReporte(container, payload);
        loadReporteSidebar();
    } catch(e) {
        showToast('No pude aprobar el contrato: ' + e.message, 'err', 6000);
        if (btn) { btn.disabled = false; btn.textContent = 'Aprobar contrato'; }
    }
}

// ── LOGIN ────────────────────────────────────────────────────
async function loadTesterRoster() {
    try {
        const r = await fetch(`${API_URL}/api/testers`);
        const d = await r.json();
        testerRoster = Array.isArray(d.testers) ? d.testers : Array.isArray(d.items) ? d.items : [];
    } catch(e) {
        console.warn('No pude cargar testers:', e.message);
        testerRoster = [];
    }
    renderLoginUsers();
}

function renderLoginUsers() {
    const el = document.getElementById('loginUsers');
    if (!el) return;
    if (!testerRoster.length) {
        el.innerHTML = '<div class="login-loading">No hay operadores registrados</div>';
        return;
    }
    const profile = readProfile();
    el.innerHTML = testerRoster.map(t => `
        <button class="login-user-btn${!profile ? ' disabled' : ''}" type="button"
            data-tester-email="${escapeHtml(t.email)}"
            ${!profile ? 'disabled' : ''}>
            ${escapeHtml(t.name || t.email)}
            <div class="login-user-email">${escapeHtml(t.email)}</div>
        </button>
    `).join('');
    el.querySelectorAll('[data-tester-email]').forEach(btn => {
        btn.addEventListener('click', () => {
            const email = btn.getAttribute('data-tester-email');
            const tester = testerRoster.find(t => t.email === email) || { email, name: email };
            if (!readProfile()) {
                document.getElementById('loginNote').textContent = 'Primero selecciona un perfil.';
                return;
            }
            saveTester(tester);
            bootApp();
        });
    });
}

function openLogin() {
    document.getElementById('loginScreen').classList.remove('hidden');
    document.getElementById('appShell').classList.add('hidden');
    updateOperationChrome();
    renderLoginUsers();
    const profile = readProfile();
    document.querySelectorAll('.login-profile-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.profile === profile);
    });
}

function bootApp() {
    if (!hasSession()) { openLogin(); return; }
    document.getElementById('loginScreen').classList.add('hidden');
    document.getElementById('appShell').classList.remove('hidden');
    updateSidebarUser();
    updateOperationChrome();
    showNavColmena();
    if (readProfile() === 'colmena') {
        switchView('produccion');
    } else {
        switchView('bandeja');
        loadBandeja();
    }
}

function updateSidebarUser() {
    const t = readTester();
    const p = readProfile();
    const name = t.name || t.email || 'Operador';
    const initials = name.split(' ').slice(0,2).map(w => w[0]||'').join('').toUpperCase() || 'OP';
    document.getElementById('userAvatar').textContent = initials;
    document.getElementById('userName').textContent = name;
    document.getElementById('userRole').textContent = 'Perfil Imagine';
}

function updateOperationChrome() {
    const op = currentOperation();
    document.body.dataset.operation = op.key;
    const brandSub = document.getElementById('brandSub');
    if (brandSub) brandSub.textContent = op.brand;
    const loginTitle = document.getElementById('loginTitle');
    if (loginTitle) loginTitle.textContent = op.name;
    const loginSub = document.getElementById('loginSub');
    if (loginSub) loginSub.textContent = 'Portal ARL · Afiliaciones';
    document.querySelectorAll('[data-operation-label]').forEach(el => {
        el.textContent = op.name;
    });
    document.querySelectorAll('[data-validation-profile-label]').forEach(el => {
        el.textContent = op.validation;
    });
}

function setActiveOperation(operation) {
    const next = normalizeOperation(operation);
    const previous = readOperation();
    saveOperation(next);
    updateOperationChrome();
    if (next === previous) return;
    activeCaseId = null;
    activeCasePayload = null;
    selectedColmenaCaseIds = new Set();
    allCases = [];
    bandejaActiveTab = 'todos';
    try { localStorage.removeItem(PROCESS_STATE_KEY); } catch {}
    stopBandejaLivePolling();
    if (hasSession()) {
        showToast(`Entidad activa: ${OPERATION_OPTIONS[next].name}.`, 'info');
        switchView(readProfile() === 'colmena' ? 'produccion' : 'bandeja');
    }
}

function showNavColmena() {
    const p = readProfile();
    const isColmena = p === 'colmena';
    // Grupos solo para Imagine
    ['navOperacion', 'navSistema'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.style.display = isColmena ? 'none' : '';
    });
    const navColmena = document.getElementById('navColmena');
    if (navColmena) navColmena.style.display = isColmena ? '' : 'none';
    if (isColmena && currentView !== 'produccion') {
        switchView('produccion');
    }
    updateMobileNavOptions();
}

function updateMobileNavOptions() {
    const select = document.getElementById('mobileViewSelect');
    if (!select) return;
    const isColmena = readProfile() === 'colmena';
    Array.from(select.options).forEach(option => {
        const isProduction = option.value === 'produccion';
        option.hidden = isColmena ? !isProduction : isProduction;
        option.disabled = option.hidden;
    });
    if (select.value !== currentView) select.value = currentView;
}

// ── NAVEGACIÓN ───────────────────────────────────────────────
const VIEW_META = {
    bandeja:       { title: 'Bandeja de entrada',        breadcrumb: 'Operación · contratos activos' },
    flujo:         { title: 'Nuevo contrato',            breadcrumb: 'Operación · cargue documental' },
    digitacion:    { title: 'Digitación',                breadcrumb: 'Operación · captura manual' },
    clasificacion: { title: 'Clasificación documental',  breadcrumb: 'Operación · documentos por revisar' },
    validacion:    { title: 'Validación OCR',            breadcrumb: 'Revisión · comparación de fuentes' },
    visor:         { title: 'Visor documental',          breadcrumb: 'Revisión · documentos adjuntos' },
    reporte:       { title: 'Reporte ejecutivo',         breadcrumb: 'Revisión · resumen de decisión' },
    produccion:    { title: 'Entrega de plano',          breadcrumb: 'Operación · archivo plano' },
    admin:         { title: 'Administración',            breadcrumb: 'Sistema · configuración' },
};

function switchView(viewId) {
    if (!VIEW_META[viewId]) viewId = 'bandeja';
    currentView = viewId;
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    const target = document.getElementById(`view-${viewId}`);
    if (target) target.classList.add('active');

    document.querySelectorAll('.nav-item').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.view === viewId);
    });

    const meta = VIEW_META[viewId] || { title: viewId, breadcrumb: '' };
    const op = currentOperation();
    document.getElementById('pageTitle').textContent = viewId === 'produccion' ? `${meta.title} · ${op.short}` : meta.title;
    document.getElementById('pageBreadcrumb').textContent = viewId === 'produccion' ? meta.breadcrumb : `${op.short} · ${meta.breadcrumb}`;
    updateMobileNavOptions();
    updateTopbarActions(viewId);

    if (viewId === 'flujo') resetFlujoView();
    if (viewId === 'digitacion') initDigitacionView();
    if (viewId === 'bandeja') loadBandeja();
    if (viewId === 'produccion') loadProduccion();
    if (viewId === 'entrenamiento') { loadFeedbackNotes(); syncFeedbackName(); }
    if (viewId === 'busqueda') { doSearch(''); }
    if (viewId === 'admin') { setTimeout(loadAdminTables, 200); }
    if (viewId === 'clasificacion') {
        if (activeCaseId) setTimeout(() => loadClassifForCase(activeCaseId), 100);
    }
    if (viewId === 'validacion') populateCaseSelect('validacionCaseSelect', onValidacionCaseChange);
    if (viewId === 'visor') populateCaseSelect('visorCaseSelect', onVisorCaseChange);
    if (viewId === 'reporte') loadReporteSidebar();
}

// ── Galería de verificación rápida ──────────────────────────────
let _galleryItems = [];
let _galleryIndex = 0;
let _galleryPayload = null;

function openGallery(items, payload, startIndex = 0) {
    _galleryItems = items.filter(i => i.kind !== 'xlsx');
    _galleryIndex = startIndex;
    _galleryPayload = payload;
    if (!_galleryItems.length) { showToast('No hay imágenes para mostrar en galería', 'warn'); return; }

    let overlay = document.getElementById('galleryOverlay');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'galleryOverlay';
        overlay.tabIndex = 0;
        overlay.style.cssText = 'position:fixed;inset:0;z-index:9000;background:rgba(0,0,0,0.92);display:flex;flex-direction:column;align-items:center;justify-content:center;outline:none';
        overlay.innerHTML = `
            <div style="position:absolute;top:12px;right:12px;display:flex;gap:8px;align-items:center">
                <span id="galleryCounter" style="color:#fff;font-size:13px"></span>
                <button id="galleryClose" style="background:transparent;border:1px solid #555;color:#fff;padding:4px 10px;border-radius:4px;cursor:pointer;font-size:13px">✕ Cerrar</button>
            </div>
            <div id="galleryLabel" style="color:#fff;font-size:11px;margin-bottom:4px;opacity:0.7;text-align:center;max-width:600px"></div>
            <div id="galleryType" style="color:#4af;font-size:14px;font-weight:600;margin-bottom:6px;text-align:center"></div>
            <div style="position:relative;display:flex;align-items:center;gap:12px">
                <button id="galleryPrev" style="background:transparent;border:1px solid #555;color:#fff;padding:8px 14px;border-radius:4px;cursor:pointer;font-size:22px">‹</button>
                <div id="galleryFrame" style="width:600px;height:68vh;border:1px solid #333;border-radius:6px;overflow:hidden;background:#111;display:flex;align-items:center;justify-content:center">
                    <div style="color:#888">Cargando...</div>
                </div>
                <button id="galleryNext" style="background:transparent;border:1px solid #555;color:#fff;padding:8px 14px;border-radius:4px;cursor:pointer;font-size:22px">›</button>
            </div>
            <div style="margin-top:8px;display:flex;gap:8px;align-items:center">
                <select id="galleryReclassify" style="padding:4px 8px;border-radius:4px;font-size:12px;background:#222;color:#fff;border:1px solid #555">
                    <option value="">— Reclasificar —</option>
                    ${REVIEW_TYPE_OPTIONS.map(([v,l]) => `<option value="${v}">${escapeHtml(l)}</option>`).join('')}
                </select>
                <button id="galleryReclassifyBtn" style="background:#1a6ef5;color:#fff;border:none;padding:4px 12px;border-radius:4px;cursor:pointer;font-size:12px">Aplicar</button>
                <span style="color:#888;font-size:11px">↑ ↓ ← → para navegar · Esc para cerrar</span>
            </div>
        `;
        document.body.appendChild(overlay);
        document.getElementById('galleryClose').addEventListener('click', closeGallery);
        document.getElementById('galleryPrev').addEventListener('click', () => galleryNav(-1));
        document.getElementById('galleryNext').addEventListener('click', () => galleryNav(1));
        document.getElementById('galleryReclassifyBtn').addEventListener('click', async () => {
            const sel = document.getElementById('galleryReclassify');
            const newType = sel.value;
            if (!newType || !_galleryPayload) return;
            const item = _galleryItems[_galleryIndex];
            if (!item) return;
            try {
                await fetch(caseApiUrl(_galleryPayload.id, '/manual-review'), {
                    method: 'POST',
                    headers: {'Content-Type':'application/json'},
                    body: JSON.stringify({kind: newType, filename: item.file, verdict: 'no', expected_type: newType})
                });
                showToast(`Reclasificado como "${getReviewTypeLabel(newType)}"`, 'ok');
                document.getElementById('galleryType').textContent = getReviewTypeLabel(newType);
                sel.value = '';
            } catch(e) {
                showToast('Error al reclasificar', 'err');
            }
        });
    }
    overlay.style.display = 'flex';
    renderGalleryItem();
    setTimeout(() => overlay.focus(), 50);
    overlay.addEventListener('keydown', galleryKeyHandler);
}

function closeGallery() {
    const overlay = document.getElementById('galleryOverlay');
    if (overlay) {
        overlay.style.display = 'none';
        overlay.removeEventListener('keydown', galleryKeyHandler);
    }
}

function galleryKeyHandler(e) {
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') galleryNav(1);
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') galleryNav(-1);
    else if (e.key === 'Escape') closeGallery();
}

function galleryNav(dir) {
    _galleryIndex = (_galleryIndex + dir + _galleryItems.length) % _galleryItems.length;
    renderGalleryItem();
}

function renderGalleryItem() {
    const item = _galleryItems[_galleryIndex];
    if (!item || !_galleryPayload) return;
    const url = documentViewerUrl(_galleryPayload.id, item.file, true);
    document.getElementById('galleryCounter').textContent = `${_galleryIndex + 1} / ${_galleryItems.length}`;
    document.getElementById('galleryLabel').textContent = item.displayName || item.file;
    document.getElementById('galleryType').textContent = item.label || item.type || '';
    const frame = document.getElementById('galleryFrame');
    const isPdf = item.file.toLowerCase().endsWith('.pdf');
    frame.innerHTML = isPdf
        ? `<iframe src="${escapeHtml(url)}" style="width:100%;height:100%;border:none"></iframe>`
        : `<img src="${escapeHtml(url)}" style="max-width:100%;max-height:100%;object-fit:contain" alt="${escapeHtml(item.label||'')}">`;
}

function updateTopbarActions(viewId) {
    const el = document.getElementById('topbarActions');
    if (!el) return;
    if (viewId === 'bandeja') {
        el.innerHTML = `<button class="btn-primary" id="topbarNewContract" type="button">+ Nuevo contrato</button>`;
        document.getElementById('topbarNewContract')?.addEventListener('click', () => switchView('flujo'));
    } else if (viewId === 'flujo') {
        el.innerHTML = `<button class="btn-secondary" id="topbarBackBandeja" type="button">← Bandeja</button>`;
        document.getElementById('topbarBackBandeja')?.addEventListener('click', () => switchView('bandeja'));
    } else {
        el.innerHTML = '';
    }
}

// ── DIGITACIÓN ───────────────────────────────────────────────
function getDigitacionFields() {
    return Array.from(document.querySelectorAll('.digitacion-field'));
}

function getVisibleDigitacionFields() {
    return getDigitacionFields().filter(field => !field.disabled && field.offsetParent !== null);
}

function focusNextDigitacionField(field, direction = 1) {
    const fields = getVisibleDigitacionFields();
    const index = fields.indexOf(field);
    if (index < 0 || !fields.length) return;
    const next = fields[index + direction] || fields[direction > 0 ? 0 : fields.length - 1];
    if (!next) return;
    const section = next.closest('[data-digitacion-panel]')?.dataset?.digitacionPanel;
    if (section && section !== digitacionActiveTab) switchDigitacionTab(section);
    setTimeout(() => {
        next.focus();
        if (next.select && next.tagName !== 'SELECT') next.select();
    }, 0);
}

const DIGITACION_REQUIRED = {
    radicacion: [
        'numero_radicacion', 'tipo_tramite', 'tipo_afiliacion', 'fecha_radicacion', 'fecha_inicio_cobertura',
        'fecha_recibido_imagine', 'empleador_tipo_documento', 'nit', 'razon_social', 'sucursal',
    ],
    afiliacion: [
        'empleador_tipo_documento', 'nit', 'razon_social',
        'nit_dv', 'codigo_actividad_economica', 'clase_riesgo_empresa',
        'direccion_empresa', 'municipio_empresa', 'departamento_empresa', 'correo_empresa', 'telefono_empresa',
        'rep_legal_nombre_completo', 'rep_legal_tipo_documento',
        'rep_legal_numero_documento', 'rep_legal_correo', 'rep_legal_cargo',
        'empresa_tipo_aportante', 'empresa_clase_aportante', 'empresa_vinculador_laboral',
        'camara_fecha_constitucion', 'camara_regimen', 'camara_codigo_actividad', 'camara_actividad_principal',
        'camara_olcsa_pyme', 'camara_naturaleza', 'camara_clase_sociedad', 'camara_tamano',
        'contacto_pagos_nombre', 'contacto_pagos_cargo', 'contacto_pagos_correo', 'contacto_pagos_direccion',
        'contacto_pagos_departamento', 'contacto_pagos_municipio', 'contacto_pagos_telefono', 'contacto_pagos_celular',
        'contacto_sst_nombre', 'contacto_sst_cargo', 'contacto_sst_correo', 'contacto_sst_direccion',
        'contacto_sst_departamento', 'contacto_sst_municipio', 'contacto_sst_telefono', 'contacto_sst_celular',
    ],
    sedes: [
        'sede_sucursal', 'sede_nombre', 'sede_centro_trabajo_nombre', 'sede_codigo', 'sede_direccion', 'sede_municipio', 'sede_departamento',
        'sede_zona', 'sede_codigo_actividad', 'sede_clase_riesgo', 'sede_numero_trabajadores',
        'sede_telefono', 'sede_celular', 'sede_transporte', 'sede_contacto', 'sede_cargo_contacto', 'sede_correo',
        'sede_grado', 'sede_tarifa',
    ],
    novedades: [
        'trabajador_centro_trabajo', 'tipo_documento_afiliado', 'documento_afiliado',
        'primer_apellido', 'primer_nombre', 'fecha_nacimiento', 'genero',
        'tipo_cotizante', 'ibc', 'cargo_actividad', 'eps', 'afp',
    ],
};

const DIGITACION_REQUIRED_AFILIACION_LEGACY = [];

const DIGITACION_REQUIRED_TRASLADO_LEGACY = [];

const DIGITACION_LEGACY_EMPRESA_KEYS = [
    'numero_radicacion',
    'tipo_persona',
    'actividad_principal_empresa',
    'telefono_empresa',
    'extension_empresa',
    'celular_empresa',
    'empresa_forma_pago',
    'empresa_tipo_aportante',
    'empresa_clase_aportante',
    'empresa_vinculador_laboral',
    'empresa_regimen',
    'empresa_naturaleza',
    'empresa_clase_sociedad',
    'empresa_tamano',
    'empresa_grupo',
    'empresa_tipo_localizacion',
    'empresa_zona_localizacion',
    'empresa_pyme',
    'empresa_olcsa',
    'empresa_contratante',
    'empresa_arl_anterior',
    'camara_fecha_constitucion',
    'camara_regimen',
    'camara_codigo_actividad',
    'camara_actividad_principal',
    'camara_olcsa_pyme',
    'camara_naturaleza',
    'camara_clase_sociedad',
    'camara_tamano',
    'camara_grupo_empresarial',
    'camara_tipo_localizacion',
    'camara_zona_localizacion',
    'contacto_pagos_nombre',
    'contacto_pagos_cargo',
    'contacto_pagos_correo',
    'contacto_pagos_direccion',
    'contacto_pagos_departamento',
    'contacto_pagos_municipio',
    'contacto_pagos_telefono',
    'contacto_pagos_extension',
    'contacto_pagos_celular',
    'contacto_sst_nombre',
    'contacto_sst_cargo',
    'contacto_sst_correo',
    'contacto_sst_direccion',
    'contacto_sst_departamento',
    'contacto_sst_municipio',
    'contacto_sst_telefono',
    'contacto_sst_extension',
    'contacto_sst_celular',
    'a_numero_sedes',
    'a_numero_centros_trabajo',
    'a_numero_inicial_trabajadores_estudiantes',
    'a_valor_total_nomina',
    'b_numero_sedes',
    'b_numero_centros_trabajo',
    'b_numero_total_trabajadores_estudiantes',
    'b_monto_total_cotizacion',
    'estado_cuenta_empleador',
];

const DIGITACION_TIPO_COTIZANTE_VALUES = new Set(Object.keys(TIPO_COTIZANTE_TRABAJADORES_CATALOG));
const DIGITACION_VINCULADOR_LABORAL_VALUES = new Set(Object.keys(VINCULADOR_LABORAL_CONTRATANTE_CATALOG));
const DIGITACION_CARGO_TRABAJADORES_CODES = new Set([
    ...Object.keys(CARGO_TRABAJADORES_CATALOG || {}),
    ...Object.values(CARGO_TRABAJADORES_CATALOG || {}).map(item => String(item?.codigo || '').trim()),
].filter(Boolean));
const DIGITACION_CARGO_CODE_BY_NAME = new Map(Object.entries(CARGO_TRABAJADORES_CATALOG || {})
    .flatMap(([code, profile]) => {
        const normalizedName = normalizeCatalogText(profile?.nombre || '');
        const normalizedLabel = normalizeCatalogText(`${code} · ${profile?.nombre || ''}`);
        return [
            [normalizedName, code],
            [normalizedLabel, code],
        ].filter(([key]) => key);
    }));
const DIGITACION_EPS_CODES = new Set(EPS_CATALOG_OPTIONS
    .map(item => String(item?.label || '').split('·')[0].trim())
    .filter(Boolean));
const DIGITACION_AFP_CODES = new Set(AFP_CATALOG_OPTIONS
    .map(item => String(item?.label || '').split('·')[0].trim())
    .filter(Boolean));

const DIGITACION_SECTION_KEYS = {
    radicacion: [...DIGITACION_REQUIRED.radicacion],
    afiliacion: [...DIGITACION_REQUIRED.afiliacion, ...DIGITACION_LEGACY_EMPRESA_KEYS],
    sedes: [...DIGITACION_REQUIRED.sedes, 'sede_celular', 'sede_fax', 'sede_transporte', 'sede_grado', 'sede_tarifa', 'sede_tipo_localizacion', 'responsable_sede_principal_nombre_completo', 'responsable_sede_principal_tipo_documento', 'responsable_sede_principal_numero_documento', 'sedes_adicionales'],
    novedades: [...DIGITACION_REQUIRED.novedades, 'segundo_apellido', 'segundo_nombre', 'edad', 'subtipo_cotizante', 'trabajadores_adicionales'],
};

const DIGITACION_WORKER_KEYS = [
    'trabajador_centro_trabajo',
    'tipo_documento_afiliado',
    'documento_afiliado',
    'primer_apellido',
    'segundo_apellido',
    'primer_nombre',
    'segundo_nombre',
    'fecha_nacimiento',
    'edad',
    'genero',
    'tipo_cotizante',
    'ibc',
    'cargo_actividad',
    'eps',
    'afp',
];

const DIGITACION_CENTRO_REQUIRED_KEYS = [
    'codigo',
    'nombre',
    'sucursal',
    'direccion',
    'departamento',
    'municipio',
    'zona',
    'telefono',
    'codigo_actividad',
    'clase',
    'trabajadores',
    'grado',
    'contacto',
    'cargo_contacto',
];

const DIGITACION_ALPHA_KEYS = new Set([
    'primer_apellido',
    'segundo_apellido',
    'primer_nombre',
    'segundo_nombre',
    'sede_nombre',
    'sede_contacto',
    'sede_cargo_contacto',
    'rep_legal_cargo',
    'contacto_pagos_nombre',
    'contacto_pagos_cargo',
    'contacto_sst_nombre',
    'contacto_sst_cargo',
    'rep_legal_nombre_completo',
    'responsable_sede_principal_nombre_completo',
    'arl_anterior',
    'empresa_arl_anterior',
    'nuevo_centro_trabajo',
]);

const DIGITACION_ALPHA_RE = /^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ .'-]{2,150}$/;
const DIGITACION_ALPHA_CLEAN_RE = /[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ .'-]/g;
const DIGITACION_ALNUM_RE = /^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9 .,&'°#/-]{2,200}$/;
const DIGITACION_ALNUM_CLEAN_RE = /[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9 .,&'°#/-]/g;
const DIGITACION_DIGIT_ONLY_KEYS = new Set([
    'nit',
    'nit_dv',
    'documento_afiliado',
    'ibc',
    'rep_legal_numero_documento',
    'responsable_sede_principal_numero_documento',
    'codigo_actividad_economica',
    'sede_codigo_actividad',
    'camara_codigo_actividad',
    'sede_codigo',
    'sede_telefono',
    'sede_celular',
    'sede_numero_trabajadores',
    'telefono_empresa',
    'extension_empresa',
    'celular_empresa',
    'contacto_pagos_telefono',
    'contacto_pagos_extension',
    'contacto_pagos_celular',
    'contacto_sst_telefono',
    'contacto_sst_extension',
    'contacto_sst_celular',
    'nuevo_codigo_ocupacion',
    'fecha_nacimiento',
    'tipo_cotizante',
    'subtipo_cotizante',
    'empresa_forma_pago',
    'empresa_tipo_aportante',
    'empresa_clase_aportante',
    'empresa_vinculador_laboral',
    'empresa_regimen',
    'empresa_naturaleza',
    'empresa_clase_sociedad',
    'empresa_tamano',
    'empresa_grupo',
    'empresa_tipo_localizacion',
    'sede_grado',
    'sede_tipo_localizacion',
    'novedad_dias',
    'novedad_estado',
    'a_numero_sedes',
    'a_numero_centros_trabajo',
    'a_numero_inicial_trabajadores_estudiantes',
    'b_numero_sedes',
    'b_numero_centros_trabajo',
    'b_numero_total_trabajadores_estudiantes',
]);
const DIGITACION_MONEY_KEYS = new Set(['ibc', 'nuevo_ibc', 'valor_total_contrato', 'valor_mensual_contrato', 'a_valor_total_nomina', 'b_monto_total_cotizacion', 'novedad_valor_anterior', 'novedad_valor_nuevo']);
const DIGITACION_SN_KEYS = new Set(['empresa_pyme', 'empresa_olcsa', 'empresa_contratante', 'sede_transporte', 'novedad_traslado']);
const DIGITACION_TIPO_APORTANTE_DEFAULTS = {
    '1': { clase: '1', vinculador: '1' },
    '2': { clase: '2', vinculador: '2' },
    '3': { clase: '3', vinculador: '3' },
    '4': { clase: '4', vinculador: '4' },
};
const DIGITACION_ALLOWED_WORKER_DOC_TYPES = new Set(['CC', 'CD', 'CE', 'PE', 'PT', 'RC', 'SC', 'TI', 'NI', 'NIT']);
const DIGITACION_CLASE_AFILIACION_VALUES = new Set(['primera vez', 'traslado', 'independiente contratista']);
const DIGITACION_CLASE_AFILIACION_ALIASES = {
    individual: 'Independiente - Contratista',
    contratista: 'Independiente - Contratista',
    independiente: 'Independiente - Contratista',
    'independiente empresa no afiliada': 'Independiente - Contratista',
    'empresa no afiliada': 'Independiente - Contratista',
    colectiva: 'Primera vez',
    empresa: 'Primera vez',
    'primera vez': 'Primera vez',
    traslado: 'Traslado',
    'independiente contratista': 'Independiente - Contratista',
};
const DIGITACION_ROMAN_RISK_TO_NUMBER = { I: '1', II: '2', III: '3', IV: '4', V: '5' };
const DIGITACION_RISK_TARIFFS = {
    1: '0.522',
    2: '1.044',
    3: '2.436',
    4: '4.360',
    5: '6.960',
};

function digitacionRequiredKeys() {
    const currentValues = readDigitacionDraft().values || {};
    const workerKeys = digitacionIsContratista(currentValues) ? [] : DIGITACION_REQUIRED.novedades;
    return new Set([
        ...DIGITACION_REQUIRED.radicacion,
        ...DIGITACION_REQUIRED.afiliacion,
        ...DIGITACION_REQUIRED.sedes,
        ...workerKeys,
        ...DIGITACION_REQUIRED_AFILIACION_LEGACY,
        ...DIGITACION_REQUIRED_TRASLADO_LEGACY,
    ]);
}

function markDigitacionRequiredFields() {
    const requiredKeys = digitacionRequiredKeys();
    getDigitacionFields().forEach(field => {
        const row = field.closest('.field-row');
        const isRequired = requiredKeys.has(field.dataset.digKey);
        field.required = isRequired;
        field.setAttribute('aria-required', isRequired ? 'true' : 'false');
        row?.classList.toggle('field-required', isRequired);
    });
    document.querySelectorAll('#digitacionCentroEditor [data-centro-field]').forEach(field => {
        const row = field.closest('.field-row');
        const isRequired = DIGITACION_CENTRO_REQUIRED_KEYS.includes(field.dataset.centroField);
        field.required = isRequired;
        field.setAttribute('aria-required', isRequired ? 'true' : 'false');
        row?.classList.toggle('field-required', isRequired);
    });
}

function setDatalistOptions(id, items, maxItems = 5000) {
    const list = document.getElementById(id);
    if (!list || list.dataset.loaded === '1') return;
    const seen = new Set();
    const options = [];
    for (const item of items) {
        const value = String(item?.value ?? item ?? '').trim();
        if (!value || seen.has(value)) continue;
        seen.add(value);
        const label = String(item?.label ?? value).trim();
        options.push(`<option value="${escapeHtml(value)}" label="${escapeHtml(label)}"></option>`);
        if (options.length >= maxItems) break;
    }
    list.innerHTML = options.join('');
    list.dataset.loaded = '1';
}

function setSelectOptions(select, items, maxItems = 5000) {
    if (!select) return;
    const currentValue = select.value || '';
    const seen = new Set();
    const options = ['<option value="">Selecciona...</option>'];
    for (const item of items) {
        const value = String(item?.value ?? item ?? '').trim();
        if (!value || seen.has(value)) continue;
        seen.add(value);
        const label = String(item?.label ?? value).trim();
        options.push(`<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`);
        if (options.length > maxItems) break;
    }
    select.innerHTML = options.join('');
    if (currentValue && seen.has(currentValue)) select.value = currentValue;
}

function populateDigitacionCatalogDatalists() {
    setDatalistOptions('epsCatalogOptions', EPS_CATALOG_OPTIONS, 1000);
    setDatalistOptions('afpCatalogOptions', AFP_CATALOG_OPTIONS, 1000);

    const activityRows = Object.entries(ACTIVITY_RISK_CATALOG)
        .map(([code, profile]) => ({
            value: code,
            label: `${code} · Clase ${profile?.clase || ''} · ${profile?.nombre || ''}`.trim(),
        }))
        .sort((a, b) => a.value.localeCompare(b.value, 'es', { numeric: true }));
    setDatalistOptions('actividadEconomicaOptions', activityRows, 10000);

    const camaraActivityRows = Object.entries(CAMARA_COMERCIO_ACTIVITY_CATALOG)
        .map(([code, profile]) => ({
            value: code,
            label: `${code} · Clase ${profile?.clase || ''} · ${profile?.nombre || ''}`.trim(),
        }))
        .sort((a, b) => a.value.localeCompare(b.value, 'es', { numeric: true }));
    setDatalistOptions('camaraActividadOptions', camaraActivityRows, 10000);

    const cargoRows = Object.entries(CARGO_TRABAJADORES_CATALOG)
        .map(([code, profile]) => ({
            value: String(code || profile?.codigo || '').trim(),
            label: `${code} · ${profile?.nombre || ''}`.trim(),
        }))
        .filter(item => item.value)
        .sort((a, b) => normalizeCatalogText(a.label).localeCompare(normalizeCatalogText(b.label), 'es', { numeric: true }));
    setDatalistOptions('cargoCatalogOptions', cargoRows, 10000);

    const tipoCotizanteSelect = document.getElementById('digTipoCotizante');
    if (tipoCotizanteSelect) {
        const rows = Object.entries(TIPO_COTIZANTE_TRABAJADORES_CATALOG)
            .map(([code, profile]) => ({
                value: code,
                label: `${code} · ${profile?.descripcion || ''}`.trim(),
            }))
            .sort((a, b) => a.value.localeCompare(b.value, 'es', { numeric: true }));
        const currentValue = tipoCotizanteSelect.value || '';
        tipoCotizanteSelect.innerHTML = [
            '<option value="">Selecciona...</option>',
            ...rows.map(item => `<option value="${escapeHtml(item.value)}">${escapeHtml(item.label)}</option>`),
        ].join('');
        if (currentValue && rows.some(item => item.value === currentValue)) tipoCotizanteSelect.value = currentValue;
    }

    const vinculadorSelect = document.getElementById('digEmpresaVinculador');
    if (vinculadorSelect) {
        const rows = Object.entries(VINCULADOR_LABORAL_CONTRATANTE_CATALOG)
            .map(([code, profile]) => ({
                value: code,
                label: `${code} · ${profile?.nombre || ''}`.trim(),
            }))
            .sort((a, b) => a.value.localeCompare(b.value, 'es', { numeric: true }));
        const currentValue = vinculadorSelect.value || '';
        vinculadorSelect.innerHTML = [
            '<option value="">Selecciona...</option>',
            ...rows.map(item => `<option value="${escapeHtml(item.value)}">${escapeHtml(item.label)}</option>`),
        ].join('');
        if (currentValue && rows.some(item => item.value === currentValue)) vinculadorSelect.value = currentValue;
    }
}

function digitacionAutocompleteCatalog(key = '') {
    if (key === 'eps') return EPS_CATALOG_OPTIONS;
    if (key === 'afp') return AFP_CATALOG_OPTIONS;
    if (key === 'cargo_actividad') {
        return Object.entries(CARGO_TRABAJADORES_CATALOG || {})
            .map(([code, profile]) => ({
                value: String(profile?.codigo || code || '').trim(),
                label: `${profile?.codigo || code} · ${profile?.nombre || ''}`.trim(),
            }))
            .filter(item => item.value)
            .sort((a, b) => normalizeCatalogText(a.label).localeCompare(normalizeCatalogText(b.label), 'es', { numeric: true }));
    }
    return [];
}

function digitacionAutocompleteSearchText(item = {}) {
    return normalizeCatalogText(`${item.value || ''} ${item.label || ''}`);
}

function digitacionAutocompleteMatches(key = '', query = '') {
    const normalizedQuery = normalizeCatalogText(query);
    const catalog = digitacionAutocompleteCatalog(key);
    if (!normalizedQuery) return key === 'cargo_actividad' ? catalog.slice(0, 8) : [];
    const tokens = normalizedQuery.split(/\s+/).filter(Boolean);
    return catalog
        .filter(item => {
            const haystack = digitacionAutocompleteSearchText(item);
            return tokens.every(token => haystack.includes(token));
        })
        .slice(0, 8);
}

function ensureDigitacionAutocompleteMenu(field) {
    const row = field?.closest('.field-row');
    if (!row) return null;
    let menu = row.querySelector('.field-autocomplete-menu');
    if (!menu) {
        menu = document.createElement('div');
        menu.className = 'field-autocomplete-menu';
        menu.hidden = true;
        menu.addEventListener('mousedown', event => event.preventDefault());
        menu.addEventListener('click', event => {
            const option = event.target.closest('[data-autocomplete-value]');
            if (!option) return;
            selectDigitacionAutocompleteOption(field, option.dataset.autocompleteValue || '');
        });
        row.appendChild(menu);
    }
    return menu;
}

function hideDigitacionAutocomplete(field) {
    const menu = field?.closest('.field-row')?.querySelector('.field-autocomplete-menu');
    if (menu) menu.hidden = true;
}

function renderDigitacionAutocomplete(field) {
    const key = field?.dataset?.digKey || '';
    if (!digitacionAutocompleteCatalog(key).length) return;
    const menu = ensureDigitacionAutocompleteMenu(field);
    if (!menu) return;
    const matches = digitacionAutocompleteMatches(key, field.value);
    if (!String(field.value || '').trim() && key !== 'cargo_actividad') {
        menu.hidden = true;
        menu.innerHTML = '';
        return;
    }
    if (!matches.length) {
        menu.innerHTML = '<div class="field-autocomplete-empty">Sin coincidencias</div>';
        menu.hidden = false;
        return;
    }
    menu.innerHTML = matches.map((item, index) => `
        <button class="field-autocomplete-option${index === 0 ? ' active' : ''}" type="button" data-autocomplete-value="${escapeHtml(item.value || '')}">
          ${escapeHtml(item.label || item.value || '')}
        </button>
    `).join('');
    menu.hidden = false;
}

function selectDigitacionAutocompleteOption(field, value = '') {
    if (!field || !value) return;
    if (field.dataset?.digKey === 'cargo_actividad') {
        setDigitacionCargoFieldDisplay(field, value);
    } else {
        field.value = value;
    }
    field.dispatchEvent(new Event('input', { bubbles: true }));
    field.dispatchEvent(new Event('change', { bubbles: true }));
    hideDigitacionAutocomplete(field);
    field.focus();
}

function moveDigitacionAutocomplete(field, direction = 1) {
    const menu = ensureDigitacionAutocompleteMenu(field);
    if (!menu || menu.hidden) return false;
    const options = Array.from(menu.querySelectorAll('.field-autocomplete-option'));
    if (!options.length) return false;
    const current = Math.max(0, options.findIndex(option => option.classList.contains('active')));
    const next = (current + direction + options.length) % options.length;
    options.forEach(option => option.classList.remove('active'));
    options[next].classList.add('active');
    options[next].scrollIntoView({ block: 'nearest' });
    return true;
}

function handleDigitacionAutocompleteKeydown(field, event) {
    const key = field?.dataset?.digKey || '';
    if (!digitacionAutocompleteCatalog(key).length) return false;
    const menu = ensureDigitacionAutocompleteMenu(field);
    if (event.key === 'ArrowDown') {
        event.preventDefault();
        renderDigitacionAutocomplete(field);
        moveDigitacionAutocomplete(field, 1);
        return true;
    }
    if (event.key === 'ArrowUp') {
        event.preventDefault();
        renderDigitacionAutocomplete(field);
        moveDigitacionAutocomplete(field, -1);
        return true;
    }
    if (event.key === 'Escape') {
        hideDigitacionAutocomplete(field);
        return true;
    }
    if (event.key === 'Enter' && menu && !menu.hidden) {
        const active = menu.querySelector('.field-autocomplete-option.active') || menu.querySelector('.field-autocomplete-option');
        if (active) {
            event.preventDefault();
            selectDigitacionAutocompleteOption(field, active.dataset.autocompleteValue || '');
            return true;
        }
    }
    return false;
}

const DIGITACION_FIELD_DOCUMENT_HINTS = [
    {
        keys: ['eps'],
        types: ['certificacion_afiliacion_eps', 'afiliacion_eps', 'eps', 'eps_afp'],
        label: 'Certificacion EPS',
    },
    {
        keys: ['afp'],
        types: ['certificacion_afiliacion_afp', 'afiliacion_afp', 'afp', 'eps_afp'],
        label: 'Certificacion AFP',
    },
    {
        keys: ['documento_afiliado', 'tipo_documento_afiliado', 'primer_apellido', 'segundo_apellido', 'primer_nombre', 'segundo_nombre', 'fecha_nacimiento', 'genero', 'tipo_cotizante', 'subtipo_cotizante', 'rep_legal_tipo_documento', 'rep_legal_numero_documento', 'responsable_sede_principal_tipo_documento', 'responsable_sede_principal_numero_documento'],
        types: ['cedula_trabajador_independiente', 'cedula_representante_legal_contratante', 'cedula_trabajadores', 'cedula'],
        label: 'Documento de identidad',
    },
    {
        keys: ['numero_contrato', 'tipo_contrato', 'fecha_inicio_contrato', 'fecha_fin_contrato', 'valor_total_contrato', 'valor_mensual_contrato', 'cargo_actividad', 'ibc'],
        types: ['contrato_contratista_contratante', 'contrato', 'contrato_trabajo_remoto', 'carta_presentacion_trabajador'],
        label: 'Contrato / carta',
    },
    {
        keys: ['sede_sucursal', 'sede_nombre', 'sede_centro_trabajo_nombre', 'sede_codigo', 'sede_direccion', 'sede_departamento', 'sede_municipio', 'sede_zona', 'sede_telefono', 'sede_celular', 'sede_numero_trabajadores', 'sede_fax', 'sede_correo', 'sede_codigo_actividad', 'sede_clase_riesgo', 'sede_transporte', 'sede_grado', 'sede_tarifa', 'sede_tipo_localizacion', 'sede_contacto', 'sede_cargo_contacto', 'responsable_sede_principal_nombre_completo', 'sedes_adicionales', 'nuevo_centro_trabajo'],
        types: ['centros_trabajo', 'anexo_sedes', 'formulario_afiliacion'],
        label: 'Sede / centro de trabajo',
    },
    {
        keys: ['nit', 'nit_dv', 'razon_social', 'empleador_tipo_documento', 'telefono_empresa', 'celular_empresa', 'rep_legal_nombre_completo', 'rep_legal_correo', 'rep_legal_cargo', 'codigo_actividad_economica', 'actividad_principal_empresa', 'clase_riesgo_empresa', ...DIGITACION_LEGACY_EMPRESA_KEYS],
        types: ['formulario_afiliacion', 'camara_comercio_contratante', 'camara_comercio', 'rut_contratista', 'rut'],
        label: 'Contratante',
    },
    {
        keys: ['direccion_empresa', 'departamento_empresa', 'municipio_empresa', 'correo_empresa', 'fecha_radicacion', 'fecha_inicio_cobertura', 'fecha_recibido_imagine', 'sucursal', 'tipo_tramite', 'tipo_afiliacion'],
        types: ['formulario_afiliacion', 'centros_trabajo', 'anexo_sedes'],
        label: 'Formulario',
    },
    {
        keys: ['tipo_novedad', 'fecha_novedad_inicio', 'fecha_novedad_fin', 'arl_anterior', 'nuevo_ibc', 'nuevo_codigo_ocupacion', 'novedad_contrato', 'novedad_dias', 'novedad_estado', 'novedad_autoliquidacion', 'novedad_origen', 'novedad_valor_anterior', 'novedad_valor_nuevo', 'novedad_traslado', 'novedad_observaciones'],
        types: ['carta_traslado_arl_anterior', 'paz_salvo_arl_anterior', 'formulario_afiliacion', 'contrato_contratista_contratante'],
        label: 'Novedad / traslado',
    },
];

function getDigitacionField(key) {
    return document.querySelector(`.digitacion-field[data-dig-key="${key}"]`);
}

function normalizeCatalogText(value = '') {
    return String(value || '')
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .replace(/[^A-Za-z0-9]+/g, ' ')
        .trim()
        .toUpperCase();
}

function normalizeCatalogName(value = '') {
    const tokens = normalizeCatalogText(value).split(/\s+/).filter(Boolean);
    const stop = new Set(['SA', 'SAS', 'LTDA', 'EPS', 'AFP']);
    return tokens.filter(token => !stop.has(token)).join('') || tokens.join('');
}

function isDigitacionCatalogCode(value, codeSet) {
    const text = String(value || '').trim();
    return Boolean(text) && /^\d+$/.test(text) && codeSet.has(text);
}

function normalizeImportedWorkerCatalogCode(value) {
    const text = String(value || '').trim();
    const digits = onlyDigits(text);
    return digits || text;
}

function normalizeDigitacionCargoCode(value) {
    const text = String(value || '').trim();
    if (!text) return '';
    const digits = onlyDigits(text);
    if (digits && DIGITACION_CARGO_TRABAJADORES_CODES.has(digits)) return digits;
    return DIGITACION_CARGO_CODE_BY_NAME.get(normalizeCatalogText(text)) || text;
}

function digitacionCargoProfile(value) {
    const code = normalizeDigitacionCargoCode(value);
    return code && CARGO_TRABAJADORES_CATALOG?.[code] ? CARGO_TRABAJADORES_CATALOG[code] : null;
}

function digitacionCargoDisplayName(value) {
    const profile = digitacionCargoProfile(value);
    return profile?.nombre || '';
}

function setDigitacionCargoFieldDisplay(field, value = '') {
    if (!field) return;
    const code = normalizeDigitacionCargoCode(value);
    const profile = digitacionCargoProfile(code);
    if (profile?.codigo || profile?.nombre) {
        field.dataset.catalogCode = String(profile.codigo || code);
        field.value = profile.nombre || String(profile.codigo || code);
        return;
    }
    delete field.dataset.catalogCode;
    field.value = String(value || '');
}

function isDigitacionEpsValid(value) {
    return isDigitacionCatalogCode(value, DIGITACION_EPS_CODES)
        || EPS_CATALOG_NORMALIZED.includes(normalizeCatalogName(value));
}

function isDigitacionAfpValid(value) {
    return isDigitacionCatalogCode(value, DIGITACION_AFP_CODES)
        || AFP_CATALOG_NORMALIZED.includes(normalizeCatalogName(value));
}

function digitacionRiskNumber(value = '') {
    const raw = String(value || '').trim().toUpperCase();
    return DIGITACION_ROMAN_RISK_TO_NUMBER[raw] || raw.replace(/\D/g, '').slice(0, 1);
}

function normalizeDigitacionDocumentTypeForUi(value = '') {
    const raw = String(value || '').trim().toUpperCase();
    return raw === 'NI' ? 'NIT' : raw;
}

function normalizeDigitacionDocumentTypeForLegacy(value = '') {
    const raw = String(value || '').trim().toUpperCase();
    return raw === 'NIT' ? 'NI' : raw;
}

function digitacionActivityCode(value = '') {
    const raw = String(value || '').trim();
    const leading = raw.match(/^\D*(\d{7})\b/);
    if (leading) return leading[1];
    const any = raw.match(/\d{7}/);
    return any ? any[0] : onlyDigits(raw).slice(0, 7);
}

function digitacionActivityProfile(value = '') {
    const code = digitacionActivityCode(value);
    return code ? ACTIVITY_RISK_CATALOG[code] : null;
}

function digitacionCamaraActivityProfile(value = '') {
    const code = onlyDigits(value);
    return code ? CAMARA_COMERCIO_ACTIVITY_CATALOG[code] : null;
}

function digitacionRiskGrade(value = '') {
    const raw = String(value || '').trim().toUpperCase();
    return DIGITACION_ROMAN_RISK_TO_NUMBER[raw] || onlyDigits(raw).slice(0, 1);
}

function digitacionTarifaForGrado(value = '') {
    return DIGITACION_RISK_TARIFFS[digitacionRiskGrade(value)] || '';
}

function syncDigitacionSedeTarifa() {
    const gradoField = getDigitacionField('sede_grado');
    const tarifaField = getDigitacionField('sede_tarifa');
    if (!gradoField || !tarifaField) return;
    tarifaField.value = digitacionTarifaForGrado(gradoField.value);
}

function digitacionAgeFromBirthDate(value = '') {
    const birth = parseDigitacionDate(value);
    if (!birth) return '';
    const today = new Date();
    let age = today.getFullYear() - birth.getFullYear();
    const beforeBirthday = today.getMonth() < birth.getMonth()
        || (today.getMonth() === birth.getMonth() && today.getDate() < birth.getDate());
    if (beforeBirthday) age -= 1;
    return age >= 0 && age < 130 ? String(age) : '';
}

function syncDigitacionWorkerAge() {
    const birthField = getDigitacionField('fecha_nacimiento');
    const ageField = getDigitacionField('edad');
    if (ageField) ageField.value = digitacionAgeFromBirthDate(birthField?.value || '');
}

function digitacionSmmlvForData(data = {}) {
    const date = parseDigitacionDate(data.fecha_radicacion || data.fecha_inicio_cobertura || '') || new Date();
    const year = String(date.getFullYear());
    return Number(SMMLV_BY_YEAR[year] || SMMLV_BY_YEAR['2026'] || SMMLV_BY_YEAR['2025'] || 0);
}

function digitacionDatePlusDays(value = '', days = 1) {
    const date = parseDigitacionDate(value);
    if (!date) return '';
    date.setDate(date.getDate() + days);
    return formatLocalIsoDate(date);
}

function digitacionStartOfMonthAfterNext(value = '') {
    const date = parseDigitacionDate(value);
    if (!date) return '';
    return formatLocalIsoDate(new Date(date.getFullYear(), date.getMonth() + 2, 1));
}

function syncDigitacionCoverageDate(force = false) {
    const radicacionField = getDigitacionField('fecha_radicacion');
    const coberturaField = getDigitacionField('fecha_inicio_cobertura');
    if (!radicacionField || !coberturaField || !radicacionField.value) return;
    const nextDay = digitacionDatePlusDays(radicacionField.value, 1);
    if (nextDay && (force || !coberturaField.value)) coberturaField.value = nextDay;
}

function syncRadicacionVigencia() {
    const tipoField = document.getElementById('flowTipoAfiliacion');
    const radicacionField = document.getElementById('flowFechaRadicacion');
    const vigenciaField = document.getElementById('flowFechaInicioVigencia');
    const arlField = document.getElementById('flowArlTraslado');
    const isTraslado = normalizeText(tipoField?.value || '').includes('traslado');
    if (arlField) {
        const row = arlField.closest('.field-row');
        row?.classList.toggle('field-required', isTraslado);
        arlField.disabled = !isTraslado;
        arlField.required = isTraslado;
        arlField.setAttribute('aria-required', isTraslado ? 'true' : 'false');
        arlField.setAttribute('aria-disabled', isTraslado ? 'false' : 'true');
        if (!isTraslado) arlField.value = '';
    }
    if (vigenciaField) {
        vigenciaField.required = true;
        vigenciaField.setAttribute('aria-required', 'true');
        const calculated = isTraslado ? digitacionStartOfMonthAfterNext(radicacionField?.value || '') : '';
        if (calculated) vigenciaField.value = calculated;
    }
}

function syncDigitacionActivityDependentFields(key = 'codigo_actividad_economica') {
    const field = getDigitacionField(key);
    if (!field) return;
    const activityCode = digitacionActivityCode(field.value);
    const profile = digitacionActivityProfile(field.value);
    if (profile && activityCode && field.value !== activityCode) field.value = activityCode;
    if (key === 'codigo_actividad_economica') {
        const activityField = getDigitacionField('actividad_principal_empresa');
        const riskField = getDigitacionField('clase_riesgo_empresa');
        if (activityField) activityField.value = profile?.nombre || profile?.actividad || '';
        if (riskField) riskField.value = profile?.clase || '';
    }
    if (key === 'sede_codigo_actividad') {
        const riskField = getDigitacionField('sede_clase_riesgo');
        if (riskField) riskField.value = profile?.clase || '';
    }
}

function normalizeDigitacionClaseAfiliacion(value = '') {
    const key = normalizeText(value).replace(/[^a-z0-9]+/g, ' ').trim();
    return DIGITACION_CLASE_AFILIACION_ALIASES[key] || value || '';
}

function sortedDepartments() {
    return Object.keys(COLOMBIA_LOCATIONS).sort((a, b) => a.localeCompare(b, 'es'));
}

function findDepartmentName(value = '') {
    const normalized = normalizeCatalogText(value);
    return sortedDepartments().find(dept => normalizeCatalogText(dept) === normalized) || '';
}

function findMunicipalityName(department, value = '') {
    const dept = findDepartmentName(department);
    if (!dept) return '';
    const normalized = normalizeCatalogText(value);
    return (COLOMBIA_LOCATIONS[dept] || []).find(mun => normalizeCatalogText(mun) === normalized) || '';
}

function allMunicipalityOptions() {
    return sortedDepartments().flatMap(dept => (COLOMBIA_LOCATIONS[dept] || []).map(mun => ({ dept, mun })))
        .sort((a, b) => normalizeCatalogText(a.mun).localeCompare(normalizeCatalogText(b.mun), 'es'));
}

function findDepartmentByMunicipality(value = '') {
    const normalized = normalizeCatalogText(value);
    const match = allMunicipalityOptions().find(item => normalizeCatalogText(item.mun) === normalized);
    return match?.dept || '';
}

function parseDigitacionCentrosAdicionales(value = '') {
    return String(value || '')
        .split('\n')
        .map(line => line.trim())
        .filter(Boolean)
        .map(line => {
            const parts = line.split('|').map(part => part.trim());
            if (parts.length >= 20) {
                const [
                    codigo = '', nombre = '', sucursal = '', direccion = '', departamento = '', municipio = '',
                    zona = '', telefono = '', celular = '', fax = '', correo = '', codigo_actividad = '',
                    clase = '', trabajadores = '', transporte = '', grado = '', tarifa = '', tipo_localizacion = '',
                    contacto = '', cargo_contacto = '',
                ] = parts;
                const safeGrado = grado || clase;
                return {
                    codigo, nombre, sucursal, direccion, departamento, municipio, zona,
                    telefono: onlyDigits(telefono), celular: onlyDigits(celular), fax: onlyDigits(fax),
                    correo, codigo_actividad: onlyDigits(codigo_actividad), clase,
                    trabajadores: onlyDigits(trabajadores), transporte, grado: safeGrado,
                    tarifa: tarifa || digitacionTarifaForGrado(safeGrado),
                    tipo_localizacion: onlyDigits(tipo_localizacion), contacto, cargo_contacto,
                };
            }
            const [codigo = '', nombre = '', direccion = '', municipio = '', departamento = '', clase = '', grado = '', tarifa = '', trabajadores = ''] = parts;
            const safeGrado = grado || clase;
            return { codigo, nombre, sucursal: '', direccion, departamento, municipio, zona: '', telefono: '', celular: '', fax: '', correo: '', codigo_actividad: '', clase, trabajadores, transporte: '', grado: safeGrado, tarifa: tarifa || digitacionTarifaForGrado(safeGrado), tipo_localizacion: '', contacto: '', cargo_contacto: '' };
        });
}

function serializeDigitacionCentroAdicional(row = {}) {
    return [
        row.codigo || '',
        row.nombre || '',
        row.sucursal || '',
        row.direccion || '',
        row.departamento || '',
        row.municipio || '',
        row.zona || '',
        onlyDigits(row.telefono || ''),
        onlyDigits(row.celular || ''),
        onlyDigits(row.fax || ''),
        row.correo || '',
        onlyDigits(row.codigo_actividad || ''),
        digitacionRiskGrade(row.clase) || '',
        onlyDigits(row.trabajadores || ''),
        row.transporte || '',
        digitacionRiskGrade(row.grado) || '',
        row.tarifa || digitacionTarifaForGrado(row.grado),
        onlyDigits(row.tipo_localizacion || ''),
        row.contacto || '',
        row.cargo_contacto || '',
    ].map(value => String(value || '').trim()).join(' | ');
}

function getDigitacionCentroEditorValues() {
    const row = {};
    document.querySelectorAll('#digitacionCentroEditor [data-centro-field]').forEach(field => {
        row[field.dataset.centroField] = field.value || '';
    });
    if (row.municipio && !row.departamento) {
        row.departamento = findDepartmentByMunicipality(row.municipio) || row.departamento;
    }
    row.clase = digitacionRiskGrade(row.clase);
    row.grado = digitacionRiskGrade(row.grado);
    row.tarifa = digitacionTarifaForGrado(row.grado);
    row.trabajadores = onlyDigits(row.trabajadores);
    row.telefono = onlyDigits(row.telefono);
    row.celular = onlyDigits(row.celular);
    row.fax = onlyDigits(row.fax);
    row.codigo_actividad = onlyDigits(row.codigo_actividad);
    row.tipo_localizacion = onlyDigits(row.tipo_localizacion);
    return row;
}

function setDigitacionCentroEditorValues(row = {}) {
    populateCentroDepartmentSelect();
    document.querySelectorAll('#digitacionCentroEditor [data-centro-field]').forEach(field => {
        const key = field.dataset.centroField;
        field.value = row[key] || '';
    });
    updateCentroMunicipalitySelect(row.municipio || '');
}

function isDigitacionCentroEditorOpen() {
    const editor = document.getElementById('digitacionCentroEditor');
    return Boolean(editor && !editor.classList.contains('hidden'));
}

function showDigitacionCentroEditor(editing = false) {
    const editor = document.getElementById('digitacionCentroEditor');
    const addBtn = document.getElementById('addCentroTrabajoBtn');
    if (!editor) return;
    populateCentroDepartmentSelect();
    updateCentroMunicipalitySelect();
    editor.classList.remove('hidden');
    if (addBtn) addBtn.textContent = editing ? 'Actualizar centro' : 'Guardar centro';
    getCentroField('codigo')?.focus();
}

function hideDigitacionCentroEditor() {
    const editor = document.getElementById('digitacionCentroEditor');
    const addBtn = document.getElementById('addCentroTrabajoBtn');
    if (editor) editor.classList.add('hidden');
    if (addBtn) addBtn.textContent = 'Agregar centro';
}

function clearDigitacionCentroEditor() {
    setDigitacionCentroEditorValues({});
    document.querySelectorAll('#digitacionCentroEditor [data-centro-field]').forEach(field => setCentroFieldError(field, ''));
    updateCentroMunicipalitySelect('');
    digitacionEditingCentroIndex = -1;
    hideDigitacionCentroEditor();
}

function populateCentroDepartmentSelect() {
    const select = document.querySelector('#digitacionCentroEditor [data-centro-field="departamento"]');
    if (!select || select.dataset.loaded === '1') return;
    const current = select.value;
    select.innerHTML = '<option value="">Selecciona...</option>' + sortedDepartments()
        .map(dept => `<option value="${escapeHtml(dept)}">${escapeHtml(dept)}</option>`)
        .join('');
    if (current) {
        const dept = findDepartmentName(current);
        if (dept) select.value = dept;
    }
    select.dataset.loaded = '1';
}

function updateCentroMunicipalitySelect(preferredValue = '') {
    const departmentSelect = document.querySelector('#digitacionCentroEditor [data-centro-field="departamento"]');
    const municipalitySelect = document.querySelector('#digitacionCentroEditor [data-centro-field="municipio"]');
    if (!departmentSelect || !municipalitySelect) return;
    const dept = findDepartmentName(departmentSelect.value);
    const current = preferredValue || municipalitySelect.value;
    if (!dept) {
        municipalitySelect.innerHTML = '<option value="">Selecciona departamento...</option>';
        municipalitySelect.disabled = true;
        return;
    }
    municipalitySelect.disabled = false;
    municipalitySelect.innerHTML = '<option value="">Selecciona...</option>' + (COLOMBIA_LOCATIONS[dept] || [])
        .map(mun => `<option value="${escapeHtml(mun)}">${escapeHtml(mun)}</option>`)
        .join('');
    const normalized = findMunicipalityName(dept, current);
    if (normalized) municipalitySelect.value = normalized;
}

function getCentroField(key) {
    return document.querySelector(`#digitacionCentroEditor [data-centro-field="${key}"]`);
}

function getCentroFieldLabel(key) {
    return getCentroField(key)?.closest('.field-row')?.querySelector('.field-label')?.textContent?.trim() || key;
}

function setCentroFieldError(field, message = '') {
    if (!field) return;
    const row = field.closest('.field-row') || field.parentElement;
    field.classList.toggle('field-invalid', Boolean(message));
    if (!row) return;
    let error = row.querySelector('.field-error-msg');
    if (message) {
        if (!error) {
            error = document.createElement('div');
            error.className = 'field-error-msg';
            row.appendChild(error);
        }
        error.textContent = message;
    } else if (error) {
        error.remove();
    }
}

function validateDigitacionCentroEditorValue(key, row = getDigitacionCentroEditorValues()) {
    const value = String(row[key] || '').trim();
    const label = getCentroFieldLabel(key);
    if (DIGITACION_CENTRO_REQUIRED_KEYS.includes(key) && !value) return `${label} es obligatorio.`;
    if (!value) return '';
    if (key === 'codigo' && !/^[0-9A-Za-z.-]{1,20}$/.test(value)) return `${label} debe ser un código válido.`;
    if (['nombre', 'contacto', 'cargo_contacto'].includes(key) && !DIGITACION_ALPHA_RE.test(value)) return `${label} solo permite letras y espacios.`;
    if (key === 'direccion' && value.length < 5) return `${label} es demasiado corta.`;
    if (key === 'departamento' && !findDepartmentName(value)) return `${label} debe existir en la tabla de departamentos.`;
    if (key === 'municipio') {
        const dept = findDepartmentName(row.departamento);
        return findMunicipalityName(dept, value) ? '' : `${label} debe pertenecer al departamento seleccionado.`;
    }
    if (key === 'zona' && !['urbana', 'rural', 'U', 'R'].includes(value)) return `${label} es obligatorio.`;
    if (key === 'telefono' && !/^\d{10}$/.test(value)) return `${label} debe tener 10 dígitos.`;
    if (key === 'celular' && value && !/^\d{10}$/.test(value)) return `${label} debe tener 10 dígitos.`;
    if (key === 'correo' && value && !/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/i.test(value)) return `${label} debe tener un correo válido.`;
    if (key === 'codigo_actividad') return digitacionActivityProfile(value) ? '' : `${label} no existe en el catálogo ARP/926.`;
    if (key === 'clase' && !['1', '2', '3', '4', '5'].includes(digitacionRiskGrade(value))) return `${label} debe estar entre 1 y 5.`;
    if (key === 'trabajadores' && !/^\d{1,6}$/.test(value)) return `${label} debe ser numérico.`;
    if (key === 'transporte' && !value) return `${label} es obligatorio.`;
    if (key === 'transporte' && !['S', 'N'].includes(value.toUpperCase())) return `${label} debe ser S o N.`;
    if (key === 'grado') {
        const grade = digitacionRiskGrade(value);
        if (!['1', '2', '3', '4', '5'].includes(grade)) return `${label} debe estar entre 1 y 5.`;
        const activityFirst = digitacionActivityCode(row.codigo_actividad).slice(0, 1);
        if (activityFirst && activityFirst !== grade) return `${label} debe ser ${activityFirst} porque el código de actividad inicia en ${activityFirst}.`;
    }
    if (key === 'tarifa') {
        const expected = digitacionTarifaForGrado(row.grado);
        return !expected || String(value) === expected ? '' : `${label} debe ser ${expected}.`;
    }
    if (key === 'tipo_localizacion' && value && !/^\d{1,3}$/.test(value)) return `${label} debe ser numérico.`;
    return '';
}

function validateDigitacionCentroEditor(editIndex = -1) {
    const row = getDigitacionCentroEditorValues();
    const errors = [];
    document.querySelectorAll('#digitacionCentroEditor [data-centro-field]').forEach(field => {
        const key = field.dataset.centroField;
        const message = validateDigitacionCentroEditorValue(key, row);
        setCentroFieldError(field, message);
        if (message) errors.push({ key, message, field });
    });
    if (row.codigo) {
        const existing = parseDigitacionCentrosAdicionales(getDigitacionField('sedes_adicionales')?.value || '');
        if (existing.some((item, index) => index !== editIndex && String(item.codigo || '').trim() === row.codigo)) {
            const field = getCentroField('codigo');
            const message = 'Ya existe un centro con este código.';
            setCentroFieldError(field, message);
            errors.push({ key: 'codigo', message, field });
        }
    }
    return { ok: !errors.length, errors, row };
}

function renderDigitacionCentrosAdicionales() {
    const hidden = getDigitacionField('sedes_adicionales');
    const list = document.getElementById('digitacionCentrosList');
    if (!hidden || !list) return;
    const rows = parseDigitacionCentrosAdicionales(hidden.value);
    if (!rows.length) {
        list.innerHTML = '<div class="digitacion-centros-empty">No hay centros adicionales registrados.</div>';
        return;
    }
    list.innerHTML = rows.map((row, index) => `
        <div class="digitacion-centro-row">
          <div class="digitacion-centro-main">
            <strong>${escapeHtml(row.codigo || `Centro ${index + 2}`)} · ${escapeHtml(row.nombre || 'Sin nombre')}</strong>
            <span>${escapeHtml(row.sucursal || 'Sin sucursal')} · ${escapeHtml(row.direccion || 'Sin dirección')} · ${escapeHtml(row.municipio || '')}${row.departamento ? `, ${escapeHtml(row.departamento)}` : ''}</span>
          </div>
          <div class="digitacion-centro-meta">
            <span>Clase ${escapeHtml(digitacionRiskGrade(row.clase) || '-')}</span>
            <span>Grado ${escapeHtml(digitacionRiskGrade(row.grado) || '-')}</span>
            <span>Tarifa ${escapeHtml(row.tarifa || digitacionTarifaForGrado(row.grado) || '-')}</span>
            <span>Trab. ${escapeHtml(row.trabajadores || '-')}</span>
            <button class="table-action-link" type="button" data-edit-centro="${index}">Editar</button>
            <button class="table-action-link table-action-danger" type="button" data-remove-centro="${index}">Quitar</button>
          </div>
        </div>
    `).join('');
}

function writeDigitacionCentrosAdicionales(rows = []) {
    const hidden = getDigitacionField('sedes_adicionales');
    if (!hidden) return;
    hidden.value = rows.map(serializeDigitacionCentroAdicional).join('\n');
    renderDigitacionCentrosAdicionales();
    updateTrabajadorCentroOptions();
    renderDigitacionTrabajadores();
}

function syncDigitacionCentroEditorTarifa() {
    const grado = document.querySelector('#digitacionCentroEditor [data-centro-field="grado"]');
    const tarifa = document.querySelector('#digitacionCentroEditor [data-centro-field="tarifa"]');
    if (tarifa) tarifa.value = digitacionTarifaForGrado(grado?.value || '');
}

function initDigitacionCentrosTrabajo() {
    const addBtn = document.getElementById('addCentroTrabajoBtn');
    const hidden = getDigitacionField('sedes_adicionales');
    if (!addBtn || !hidden) return;
    populateCentroDepartmentSelect();
    updateCentroMunicipalitySelect();
    document.querySelectorAll('#digitacionCentroEditor [data-centro-field]').forEach(field => {
        field.addEventListener('input', () => {
            if (['codigo', 'trabajadores', 'telefono', 'celular', 'fax', 'codigo_actividad', 'tipo_localizacion'].includes(field.dataset.centroField)) {
                const cleaned = field.value.replace(/\D/g, '');
                if (field.value !== cleaned) field.value = cleaned;
            }
            if (field.dataset.centroField === 'transporte') {
                const cleaned = field.value.toUpperCase().replace(/[^SN]/g, '').slice(0, 1);
                if (field.value !== cleaned) field.value = cleaned;
            }
            if (field.dataset.centroField === 'grado') syncDigitacionCentroEditorTarifa();
            if (field.dataset.centroField === 'codigo_actividad') {
                const profile = digitacionActivityProfile(field.value);
                const claseField = document.querySelector('#digitacionCentroEditor [data-centro-field="clase"]');
                if (claseField && profile?.clase) claseField.value = profile.clase;
            }
            setCentroFieldError(field, '');
        });
        field.addEventListener('change', () => {
            if (field.dataset.centroField === 'departamento') updateCentroMunicipalitySelect('');
            if (field.dataset.centroField === 'grado') syncDigitacionCentroEditorTarifa();
            if (field.dataset.centroField === 'codigo_actividad') {
                const profile = digitacionActivityProfile(field.value);
                const claseField = document.querySelector('#digitacionCentroEditor [data-centro-field="clase"]');
                if (claseField && profile?.clase) claseField.value = profile.clase;
            }
            setCentroFieldError(field, validateDigitacionCentroEditorValue(field.dataset.centroField));
        });
        field.addEventListener('keydown', e => {
            if (e.key !== 'Enter') return;
            e.preventDefault();
            const fields = Array.from(document.querySelectorAll('#digitacionCentroEditor [data-centro-field]'));
            const next = fields[fields.indexOf(field) + 1] || addBtn;
            next.focus();
        });
    });
    addBtn.addEventListener('click', () => {
        if (!isDigitacionCentroEditorOpen()) {
            setDigitacionCentroEditorValues({});
            document.querySelectorAll('#digitacionCentroEditor [data-centro-field]').forEach(field => setCentroFieldError(field, ''));
            digitacionEditingCentroIndex = -1;
            showDigitacionCentroEditor(false);
            return;
        }
        const rows = parseDigitacionCentrosAdicionales(hidden.value);
        const editIndex = digitacionEditingCentroIndex;
        const validation = validateDigitacionCentroEditor(editIndex);
        if (!validation.ok) {
            const first = validation.errors[0];
            first?.field?.focus();
            showToast(first?.message || 'Corrige los campos del centro de trabajo.', 'err');
            return;
        }
        const row = validation.row;
        if (editIndex >= 0 && editIndex < rows.length) {
            rows[editIndex] = row;
            showToast('Centro de trabajo actualizado', 'ok');
        } else {
            rows.push(row);
            showToast('Centro de trabajo agregado', 'ok');
        }
        writeDigitacionCentrosAdicionales(rows);
        clearDigitacionCentroEditor();
        updateDigitacionStatus('Cambios sin guardar', 'warn');
    });
    document.getElementById('digitacionCentrosList')?.addEventListener('click', e => {
        const rows = parseDigitacionCentrosAdicionales(hidden.value);
        const editBtn = e.target.closest('[data-edit-centro]');
        if (editBtn) {
            const index = Number(editBtn.dataset.editCentro);
            const row = rows[index];
            if (!row) return;
            digitacionEditingCentroIndex = index;
            setDigitacionCentroEditorValues(row);
            showDigitacionCentroEditor(true);
            showToast('Centro cargado para modificar', 'ok');
            return;
        }
        const removeBtn = e.target.closest('[data-remove-centro]');
        if (!removeBtn) return;
        const removeIndex = Number(removeBtn.dataset.removeCentro);
        rows.splice(removeIndex, 1);
        writeDigitacionCentrosAdicionales(rows);
        if (digitacionEditingCentroIndex === removeIndex) clearDigitacionCentroEditor();
        else if (digitacionEditingCentroIndex > removeIndex) digitacionEditingCentroIndex -= 1;
        updateDigitacionStatus('Cambios sin guardar', 'warn');
    });
    renderDigitacionCentrosAdicionales();
}

function digitacionCentroOptions() {
    const rows = [];
    const codigoPrincipal = String(getDigitacionField('sede_codigo')?.value || '').trim();
    const nombrePrincipal = String(getDigitacionField('sede_centro_trabajo_nombre')?.value || getDigitacionField('sede_nombre')?.value || '').trim() || 'Centro principal';
    if (codigoPrincipal || nombrePrincipal) {
        rows.push({
            value: codigoPrincipal || '1',
            label: `${codigoPrincipal || '1'} · ${nombrePrincipal}`,
        });
    }
    parseDigitacionCentrosAdicionales(getDigitacionField('sedes_adicionales')?.value || '').forEach((row, index) => {
        const value = row.codigo || String(index + 2);
        rows.push({ value, label: `${value} · ${row.nombre || 'Centro adicional'}` });
    });
    return rows;
}

function updateTrabajadorCentroOptions() {
    const select = getDigitacionField('trabajador_centro_trabajo');
    if (!select) return;
    const current = select.value || '';
    const rows = digitacionCentroOptions();
    setSelectOptions(select, rows, 500);
    if (current && rows.some(row => row.value === current)) select.value = current;
    if (!select.value && rows.length) select.value = rows[0].value;
    renderDigitacionTrabajadores();
}

function getDigitacionWorkerFormValues() {
    const row = {};
    DIGITACION_WORKER_KEYS.forEach(key => {
        row[key] = getDigitacionField(key)?.value || '';
    });
    if (row.fecha_nacimiento) row.fecha_nacimiento = formatDigitacionBirthDateInput(row.fecha_nacimiento);
    row.edad = row.edad || digitacionAgeFromBirthDate(row.fecha_nacimiento);
    row.documento_afiliado = onlyDigits(row.documento_afiliado);
    row.cargo_actividad = normalizeDigitacionCargoCode(row.cargo_actividad);
    return row;
}

function digitacionWorkerHasData(row = {}) {
    return DIGITACION_WORKER_KEYS
        .filter(key => key !== 'trabajador_centro_trabajo' && key !== 'edad')
        .some(key => String(row[key] || '').trim());
}

function parseDigitacionTrabajadores(value = '') {
    return String(value || '')
        .split('\n')
        .map(line => line.trim())
        .filter(Boolean)
        .map(line => {
            const [
                trabajador_centro_trabajo = '',
                tipo_documento_afiliado = '',
                documento_afiliado = '',
                primer_apellido = '',
                segundo_apellido = '',
                primer_nombre = '',
                segundo_nombre = '',
                fecha_nacimiento = '',
                edad = '',
                genero = '',
                tipo_cotizante = '',
                ibc = '',
                cargo_actividad = '',
                eps = '',
                afp = '',
            ] = line.split('|').map(part => part.trim());
            const normalizedBirth = formatDigitacionBirthDateInput(fecha_nacimiento);
            return {
                trabajador_centro_trabajo,
                tipo_documento_afiliado,
                documento_afiliado: onlyDigits(documento_afiliado),
                primer_apellido,
                segundo_apellido,
                primer_nombre,
                segundo_nombre,
                fecha_nacimiento: normalizedBirth,
                edad: onlyDigits(edad) || digitacionAgeFromBirthDate(normalizedBirth),
                genero,
                tipo_cotizante,
                ibc,
                cargo_actividad: normalizeDigitacionCargoCode(cargo_actividad),
                eps,
                afp,
            };
        });
}

function serializeDigitacionTrabajador(row = {}) {
    return DIGITACION_WORKER_KEYS.map(key => {
        const value = key === 'cargo_actividad' ? normalizeDigitacionCargoCode(row[key]) : row[key];
        return String(value || '').trim();
    }).join(' | ');
}

function digitacionWorkerRows(values = collectDigitacionData().values) {
    const rows = parseDigitacionTrabajadores(values.trabajadores_adicionales || '');
    const current = {};
    DIGITACION_WORKER_KEYS.forEach(key => { current[key] = values[key] || ''; });
    if (digitacionWorkerHasData(current)) {
        current.fecha_nacimiento = formatDigitacionBirthDateInput(current.fecha_nacimiento);
        current.edad = current.edad || digitacionAgeFromBirthDate(current.fecha_nacimiento);
        rows.push(current);
    }
    return rows;
}

function digitacionWorkerIdentityKey(row = {}) {
    const docType = normalizeDigitacionDocumentTypeForUi(row.tipo_documento_afiliado || '').toUpperCase();
    const docNumber = onlyDigits(row.documento_afiliado || '');
    return docType && docNumber ? `${docType}:${docNumber}` : '';
}

function validateDigitacionWorkerDuplicates(rows = []) {
    const seen = new Map();
    const errors = [];
    rows.forEach((row, index) => {
        const identity = digitacionWorkerIdentityKey(row);
        if (!identity) return;
        if (seen.has(identity)) {
            const firstIndex = seen.get(identity);
            errors.push({
                key: 'trabajadores_adicionales',
                section: 'novedades',
                message: `Trabajador ${index + 1}: ya existe un trabajador con el mismo tipo y número de documento que el Trabajador ${firstIndex + 1}.`,
            });
            return;
        }
        seen.set(identity, index);
    });
    return errors;
}

function digitacionExpectedWorkersByCenter(values = collectDigitacionData().values) {
    const centers = [];
    const mainCode = String(values.sede_codigo || '1').trim() || '1';
    const mainExpected = onlyDigits(values.sede_numero_trabajadores || '');
    if (mainExpected) {
        centers.push({
            code: mainCode,
            expected: Number(mainExpected),
            key: 'sede_numero_trabajadores',
            section: 'sedes',
            label: `Centro ${mainCode}`,
        });
    }
    parseDigitacionCentrosAdicionales(values.sedes_adicionales || '').forEach((row, index) => {
        const code = String(row.codigo || index + 2).trim();
        const expected = onlyDigits(row.trabajadores || '');
        if (!code || !expected) return;
        centers.push({
            code,
            expected: Number(expected),
            key: 'sedes_adicionales',
            section: 'sedes',
            label: `Centro ${code}${row.nombre ? ` · ${row.nombre}` : ''}`,
        });
    });
    return centers;
}

function validateDigitacionWorkerCenterCounts(values = collectDigitacionData().values) {
    const actualByCenter = new Map();
    digitacionWorkerRows(values)
        .filter(digitacionWorkerHasData)
        .forEach(row => {
            const code = String(row.trabajador_centro_trabajo || '').trim();
            if (!code) return;
            actualByCenter.set(code, (actualByCenter.get(code) || 0) + 1);
        });

    return digitacionExpectedWorkersByCenter(values)
        .filter(center => Number.isFinite(center.expected))
        .filter(center => (actualByCenter.get(center.code) || 0) !== center.expected)
        .map(center => {
            const actual = actualByCenter.get(center.code) || 0;
            return {
                key: center.key,
                section: center.section,
                message: `${center.label}: Nro trabajadores declara ${center.expected}, pero hay ${actual} trabajador(es) registrados en la pestaña Trabajadores.`,
            };
        });
}

function validateDigitacionWorkerRow(row = {}, index = 1, existingRows = []) {
    const errors = [];
    const contractValues = collectDigitacionData().values;
    const workerDoc = onlyDigits(row.documento_afiliado);
    const employerDoc = onlyDigits(contractValues.nit);
    for (const key of DIGITACION_REQUIRED.novedades) {
        if (!String(row[key] || '').trim()) {
            errors.push({ key: 'trabajadores_adicionales', section: 'novedades', message: `Trabajador ${index}: ${getDigitacionLabel(getDigitacionField(key))} es obligatorio.` });
        }
    }
    if (workerDoc && employerDoc && workerDoc === employerDoc) {
        errors.push({ key: 'documento_afiliado', section: 'novedades', message: `Trabajador ${index}: la cédula del trabajador no puede ser la misma que el número de identificación de la empresa.` });
    }
    const identity = digitacionWorkerIdentityKey(row);
    if (identity && existingRows.some(item => digitacionWorkerIdentityKey(item) === identity)) {
        errors.push({ key: 'documento_afiliado', section: 'novedades', message: `Trabajador ${index}: ya existe un trabajador con el mismo tipo y número de documento.` });
    }
    for (const key of DIGITACION_WORKER_KEYS) {
        const value = row[key] || '';
        if (!String(value).trim()) continue;
        const message = validateDigitacionValue(key, value, row);
        if (message) errors.push({ key: 'trabajadores_adicionales', section: 'novedades', message: `Trabajador ${index}: ${message}` });
    }
    return errors;
}

function renderDigitacionTrabajadores() {
    const hidden = getDigitacionField('trabajadores_adicionales');
    const list = document.getElementById('digitacionTrabajadoresList');
    if (!hidden || !list) return;
    const rows = parseDigitacionTrabajadores(hidden.value);
    if (!rows.length) {
        list.innerHTML = '<div class="digitacion-centros-empty">No hay trabajadores agregados al contrato.</div>';
        return;
    }
    const centers = new Map(digitacionCentroOptions().map(row => [row.value, row.label]));
    list.innerHTML = rows.map((row, index) => `
        <div class="digitacion-centro-row">
          <div class="digitacion-centro-main">
            <strong>${escapeHtml(row.tipo_documento_afiliado || 'ID')} ${escapeHtml(row.documento_afiliado || '')} · ${escapeHtml([row.primer_nombre, row.segundo_nombre, row.primer_apellido, row.segundo_apellido].filter(Boolean).join(' ') || `Trabajador ${index + 1}`)}</strong>
            <span>${escapeHtml(centers.get(row.trabajador_centro_trabajo) || row.trabajador_centro_trabajo || 'Sin centro')} · ${escapeHtml(row.eps || 'EPS pendiente')} · ${escapeHtml(row.afp || 'AFP pendiente')}</span>
          </div>
          <div class="digitacion-centro-meta">
            <span>IBC ${escapeHtml(row.ibc || '-')}</span>
            <span>Tipo ${escapeHtml(row.tipo_cotizante || '-')}</span>
            <span>Cargo ${escapeHtml(digitacionCargoDisplayName(row.cargo_actividad) || row.cargo_actividad || '-')}</span>
            <button class="table-action-link" type="button" data-edit-trabajador="${index}">Modificar</button>
            <button class="table-action-link table-action-danger" type="button" data-remove-trabajador="${index}">Quitar</button>
          </div>
        </div>
    `).join('');
}

function writeDigitacionTrabajadores(rows = []) {
    const hidden = getDigitacionField('trabajadores_adicionales');
    if (!hidden) return;
    hidden.value = rows.map(serializeDigitacionTrabajador).join('\n');
    renderDigitacionTrabajadores();
}

function setDigitacionWorkerFormValues(row = {}) {
    DIGITACION_WORKER_KEYS.forEach(key => {
        const field = getDigitacionField(key);
        if (!field) return;
        const aliases = {
            cargo_actividad: ['cargo', 'cargo_trabajador'],
            tipo_cotizante: ['afi_tipo', 'afi_tipo_cotizante'],
            documento_afiliado: ['numero_id', 'nroid', 'nro_id'],
            fecha_nacimiento: ['fec_nac'],
        };
        const aliasValue = (aliases[key] || []).map(alias => row[alias]).find(value => String(value || '').trim());
        if (key === 'cargo_actividad') {
            setDigitacionCargoFieldDisplay(field, row[key] || aliasValue || '');
        } else {
            field.value = row[key] || aliasValue || '';
        }
    });
    updateTrabajadorCentroOptions();
    const centro = getDigitacionField('trabajador_centro_trabajo');
    if (centro && row.trabajador_centro_trabajo) centro.value = row.trabajador_centro_trabajo;
    syncDigitacionWorkerAge();
}

function normalizeImportedWorkerRow(row = {}) {
    const normalized = {};
    DIGITACION_WORKER_KEYS.forEach(key => { normalized[key] = String(row[key] || '').trim(); });
    normalized.documento_afiliado = onlyDigits(normalized.documento_afiliado);
    normalized.fecha_nacimiento = formatDigitacionBirthDateInput(normalized.fecha_nacimiento);
    normalized.edad = onlyDigits(normalized.edad) || digitacionAgeFromBirthDate(normalized.fecha_nacimiento);
    normalized.tipo_documento_afiliado = normalizeDigitacionDocumentTypeForUi(normalized.tipo_documento_afiliado || '').toUpperCase();
    normalized.genero = String(normalized.genero || '').trim().toUpperCase().slice(0, 1);
    normalized.tipo_cotizante = onlyDigits(normalized.tipo_cotizante);
    normalized.ibc = onlyDigits(normalized.ibc);
    normalized.cargo_actividad = normalizeDigitacionCargoCode(normalizeImportedWorkerCatalogCode(normalized.cargo_actividad));
    normalized.eps = normalizeImportedWorkerCatalogCode(normalized.eps);
    normalized.afp = normalizeImportedWorkerCatalogCode(normalized.afp);
    return normalized;
}

async function importDigitacionTrabajadoresExcel(file) {
    const hidden = getDigitacionField('trabajadores_adicionales');
    const status = document.getElementById('trabajadoresImportStatus');
    if (!file || !hidden) return;
    if (status) {
        status.hidden = false;
        status.textContent = `Leyendo ${file.name}...`;
    }
    const form = new FormData();
    form.append('file', file);
    try {
        const response = await fetchWithRetry(`${API_URL}/api/digitacion/trabajadores/import-xlsx`, {
            method: 'POST',
            body: form,
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload?.detail || payload?.message || `HTTP ${response.status}`);
        const existingRows = parseDigitacionTrabajadores(hidden.value);
        const importedRows = (payload.rows || []).map(normalizeImportedWorkerRow).filter(digitacionWorkerHasData);
        const mergedRows = [...existingRows, ...importedRows];
        const errors = [];
        importedRows.forEach((row, index) => {
            validateDigitacionWorkerRow(row, existingRows.length + index + 1, [...existingRows, ...importedRows.slice(0, index)]).forEach(error => errors.push(error));
        });
        validateDigitacionWorkerDuplicates(mergedRows).forEach(error => errors.push(error));
        if (errors.length) {
            if (status) status.textContent = errors.slice(0, 5).map(error => error.message).join(' | ');
            showToast(errors[0].message, 'err');
            return;
        }
        writeDigitacionTrabajadores(mergedRows);
        clearDigitacionWorkerForm();
        updateDigitacionStatus('Cambios sin guardar', 'warn');
        if (status) status.textContent = `${importedRows.length} trabajador(es) importado(s) desde ${payload.filename || file.name}.`;
        showToast(`${importedRows.length} trabajador(es) importado(s)`, 'ok');
    } catch (error) {
        if (status) status.textContent = `No se pudo importar: ${error.message}`;
        showToast(`No se pudo importar trabajadores: ${error.message}`, 'err');
    }
}

function clearDigitacionWorkerForm() {
    DIGITACION_WORKER_KEYS.forEach(key => {
        const field = getDigitacionField(key);
        if (!field || field.readOnly) return;
        field.value = '';
        if (key === 'cargo_actividad') delete field.dataset.catalogCode;
        setDigitacionFieldError(field, '');
    });
    syncDigitacionWorkerAge();
    updateTrabajadorCentroOptions();
}

function initDigitacionTrabajadores() {
    const addBtn = document.getElementById('addTrabajadorBtn');
    const importBtn = document.getElementById('importTrabajadoresBtn');
    const importInput = document.getElementById('trabajadoresMasivoInput');
    const hidden = getDigitacionField('trabajadores_adicionales');
    if (!addBtn || !hidden) return;
    if (addBtn.dataset.bound === '1') {
        renderDigitacionTrabajadores();
        return;
    }
    addBtn.dataset.bound = '1';
    importBtn?.addEventListener('click', () => importInput?.click());
    importInput?.addEventListener('change', () => {
        const file = importInput.files?.[0];
        importInput.value = '';
        if (file) importDigitacionTrabajadoresExcel(file);
    });
    addBtn.addEventListener('click', () => {
        const row = getDigitacionWorkerFormValues();
        const rows = parseDigitacionTrabajadores(hidden.value);
        DIGITACION_WORKER_KEYS.forEach(key => setDigitacionFieldError(getDigitacionField(key), ''));
        const errors = validateDigitacionWorkerRow(row, rows.length + 1, rows);
        if (errors.length) {
            for (const error of errors) {
                const match = DIGITACION_WORKER_KEYS.includes(error.key)
                    ? error.key
                    : DIGITACION_WORKER_KEYS.find(key => error.message.includes(getDigitacionLabel(getDigitacionField(key))));
                if (match) setDigitacionFieldError(getDigitacionField(match), error.message.replace(/^Trabajador \d+:\s*/, ''));
            }
            showToast(errors[0].message, 'err');
            return;
        }
        rows.push(row);
        writeDigitacionTrabajadores(rows);
        clearDigitacionWorkerForm();
        updateDigitacionStatus('Cambios sin guardar', 'warn');
        showToast(`Trabajador agregado (${rows.length})`, 'ok');
    });
    document.getElementById('digitacionTrabajadoresList')?.addEventListener('click', e => {
        const editBtn = e.target.closest('[data-edit-trabajador]');
        const rows = parseDigitacionTrabajadores(hidden.value);
        if (editBtn) {
            const index = Number(editBtn.dataset.editTrabajador);
            const row = rows[index];
            if (!row) return;
            rows.splice(index, 1);
            writeDigitacionTrabajadores(rows);
            setDigitacionWorkerFormValues(row);
            updateDigitacionStatus('Cambios sin guardar', 'warn');
            showToast('Trabajador cargado para modificar', 'warn');
            return;
        }
        const btn = e.target.closest('[data-remove-trabajador]');
        if (!btn) return;
        rows.splice(Number(btn.dataset.removeTrabajador), 1);
        writeDigitacionTrabajadores(rows);
        updateDigitacionStatus('Cambios sin guardar', 'warn');
    });
    renderDigitacionTrabajadores();
}

function populateDepartmentSelect(select) {
    if (!select || select.dataset.loaded === '1') return;
    const current = select.value;
    select.innerHTML = '<option value="">Selecciona...</option>' + sortedDepartments()
        .map(dept => `<option value="${escapeHtml(dept)}">${escapeHtml(dept)}</option>`)
        .join('');
    if (current) {
        const dept = findDepartmentName(current);
        if (dept) select.value = dept;
    }
    select.dataset.loaded = '1';
}

function updateMunicipalitySelect(departmentSelect, preferredValue = '') {
    if (!departmentSelect) return;
    const municipalitySelect = document.getElementById(departmentSelect.dataset.municipalityTarget || '');
    if (!municipalitySelect) return;
    const dept = findDepartmentName(departmentSelect.value);
    const municipalityRows = dept
        ? (COLOMBIA_LOCATIONS[dept] || []).map(mun => ({ dept, mun, label: mun }))
        : allMunicipalityOptions().map(item => ({ ...item, label: `${item.mun} · ${item.dept}` }));
    municipalitySelect.disabled = municipalityRows.length === 0;
    municipalitySelect.innerHTML = municipalityRows.length
        ? '<option value="">Selecciona...</option>' + municipalityRows.map(item => `<option value="${escapeHtml(item.mun)}">${escapeHtml(item.label)}</option>`).join('')
        : '<option value="">Selecciona municipio...</option>';
    const match = municipalityRows.find(item => normalizeCatalogText(item.mun) === normalizeCatalogText(preferredValue));
    if (match) municipalitySelect.value = match.mun;
}

function syncDepartmentFromMunicipality(municipalitySelect) {
    if (!municipalitySelect?.value) return;
    const departmentSelect = document.getElementById(municipalitySelect.dataset.departmentSource || '');
    if (!departmentSelect) return;
    const currentDepartment = findDepartmentName(departmentSelect.value);
    const selectedMunicipality = municipalitySelect.value;
    const inferredDepartment = currentDepartment && findMunicipalityName(currentDepartment, selectedMunicipality)
        ? currentDepartment
        : findDepartmentByMunicipality(selectedMunicipality);
    if (!inferredDepartment) return;
    if (departmentSelect.value !== inferredDepartment) {
        departmentSelect.value = inferredDepartment;
        departmentSelect.dispatchEvent(new Event('input', { bubbles: true }));
    }
    updateMunicipalitySelect(departmentSelect, selectedMunicipality);
}

function setupDigitacionLocationSelects() {
    document.querySelectorAll('.js-department-select').forEach(select => {
        populateDepartmentSelect(select);
        updateMunicipalitySelect(select, document.getElementById(select.dataset.municipalityTarget || '')?.value || '');
    });
}

function getDigitacionLabel(field) {
    return field?.closest('.field-row')?.querySelector('.field-label')?.textContent?.trim() || field?.dataset?.digKey || 'Campo';
}

function formatLocalIsoDate(date) {
    if (!(date instanceof Date) || Number.isNaN(date.getTime())) return '';
    const yyyy = String(date.getFullYear());
    const mm = String(date.getMonth() + 1).padStart(2, '0');
    const dd = String(date.getDate()).padStart(2, '0');
    return `${yyyy}-${mm}-${dd}`;
}

function parseDigitacionDate(value) {
    const text = String(value || '').trim();
    const candidates = [];
    if (/^\d{4}-\d{2}-\d{2}$/.test(text)) {
        candidates.push(text);
    }
    const digits = onlyDigits(text);
    if (digits.length === 8) {
        candidates.push(`${digits.slice(0, 4)}-${digits.slice(4, 6)}-${digits.slice(6, 8)}`);
        candidates.push(`${digits.slice(4, 8)}-${digits.slice(2, 4)}-${digits.slice(0, 2)}`);
    }
    for (const iso of Array.from(new Set(candidates))) {
        const year = Number(iso.slice(0, 4));
        const month = Number(iso.slice(5, 7));
        const day = Number(iso.slice(8, 10));
        const date = new Date(year, month - 1, day);
        if (formatLocalIsoDate(date) === iso) return date;
    }
    return null;
}

function formatDigitacionBirthDateInput(value = '') {
    const text = String(value || '').trim();
    if (!text) return '';
    const parsed = parseDigitacionDate(text);
    if (!parsed) return onlyDigits(text).slice(0, 8);
    const iso = formatLocalIsoDate(parsed);
    return `${iso.slice(8, 10)}${iso.slice(5, 7)}${iso.slice(0, 4)}`;
}

function todayIsoDate() {
    const now = new Date();
    return formatLocalIsoDate(now);
}

function applyDigitacionLegacyLimits() {
    getDigitacionFields().forEach(field => {
        const key = field.dataset.digKey || '';
        const limit = AFILEGA_MDB_FIELD_LIMITS[key];
        if (!limit || field.tagName === 'SELECT') return;
        if (key === 'cargo_actividad') return;
        field.setAttribute('maxlength', String(limit));
    });
    const camaraFecha = getDigitacionField('camara_fecha_constitucion');
    if (camaraFecha) camaraFecha.max = todayIsoDate();
}

function shouldUppercaseDigitacionField(field) {
    if (!field || field.tagName === 'SELECT') return false;
    const key = field.dataset?.digKey || '';
    const type = String(field.type || '').toLowerCase();
    if (['date', 'hidden', 'number'].includes(type)) return false;
    if (DIGITACION_DIGIT_ONLY_KEYS.has(key)) return false;
    if (key === 'cargo_actividad') return false;
    if (key === 'fecha_nacimiento' || key.startsWith('fecha_') || key.includes('_fecha_')) return false;
    return true;
}

function normalizeDigitacionFieldDisplayValue(field, value = '') {
    const text = String(value ?? '');
    return shouldUppercaseDigitacionField(field) ? text.toUpperCase() : text;
}

function normalizeDigitacionFieldInPlace(field) {
    if (!field || field.tagName === 'SELECT') return;
    if (field.dataset?.digKey === 'cargo_actividad') {
        const cargoCode = normalizeDigitacionCargoCode(field.value);
        if (DIGITACION_CARGO_TRABAJADORES_CODES.has(cargoCode)) {
            setDigitacionCargoFieldDisplay(field, cargoCode);
        } else {
            delete field.dataset.catalogCode;
        }
        return;
    }
    const normalized = normalizeDigitacionFieldDisplayValue(field, field.value);
    if (field.value !== normalized) field.value = normalized;
    const key = field.dataset?.digKey || '';
    const limit = AFILEGA_MDB_FIELD_LIMITS[key];
    if (limit && field.value.length > limit) field.value = field.value.slice(0, limit).trim();
}

function setDigitacionFieldError(field, message = '') {
    if (!field) return;
    const row = field.closest('.field-row') || field.parentElement;
    field.classList.toggle('field-invalid', Boolean(message));
    if (!row) return;
    let error = row.querySelector('.field-error-msg');
    if (message) {
        if (!error) {
            error = document.createElement('div');
            error.className = 'field-error-msg';
            row.appendChild(error);
        }
        error.textContent = message;
    } else if (error) {
        error.remove();
    }
}

function getDigitacionFieldHint(key = '') {
    return DIGITACION_FIELD_DOCUMENT_HINTS.find(item => item.keys.includes(key)) || {
        keys: [],
        types: ['formulario_afiliacion'],
        label: 'Formulario',
    };
}

function getDigitacionCaseId() {
    const draft = readDigitacionDraft();
    return draft.source_case_id || activeCasePayload?.id || activeCaseId || '';
}

async function ensureDigitacionCasePayload() {
    const caseId = getDigitacionCaseId();
    if (!caseId) return activeCasePayload || null;
    if (activeCasePayload?.id === caseId) return activeCasePayload;
    const cached = allCases.find(item => item.id === caseId);
    if (cached?.analysis?.documents) {
        activeCasePayload = cached;
        return cached;
    }
    const response = await fetchWithRetry(caseApiUrl(caseId));
    const payload = await response.json();
    activeCasePayload = payload;
    return payload;
}

function getDigitacionDocuments(payload) {
    const meta = buildDocMetaMap(payload);
    return buildDocItems(payload)
        .filter(item => item.kind === 'document')
        .map(item => ({
            ...(meta[item.file] || {}),
            filename: item.file,
            document_type: item.type || meta[item.file]?.document_type || '',
            document_label: item.label || getReviewTypeLabel(item.type) || meta[item.file]?.document_label || '',
            display_filename: item.displayName || meta[item.file]?.display_filename || item.file,
            classification_confidence: meta[item.file]?.classification_confidence,
            ocr_quality_score: meta[item.file]?.ocr_quality_score,
            ocr_text: meta[item.file]?.ocr_text || meta[item.file]?.text_preview || '',
        }));
}

function digitacionSourceFilenameForKey(key, draft, payload) {
    const source = draft?.prefill_sources?.[key] || payload?.analysis?.digitacion_prefill?.sources?.[key] || null;
    if (!source || typeof source !== 'object') return '';
    return source.filename || source.file || source.document || source.document_file || '';
}

function pickDigitacionDocument(key, payload, forcedFilename = '') {
    const docs = getDigitacionDocuments(payload);
    if (!docs.length) return null;
    const draft = readDigitacionDraft();
    const sourceFilename = forcedFilename || digitacionSourceFilenameForKey(key, draft, payload);
    if (sourceFilename) {
        const direct = docs.find(doc => (doc.filename || '') === sourceFilename);
        if (direct) return direct;
    }
    const hint = getDigitacionFieldHint(key);
    const byType = docs.find(doc => hint.types.includes(doc.document_type));
    if (byType) return byType;
    const byText = docs.find(doc => {
        const haystack = normalizeText(`${doc.document_type || ''} ${doc.document_label || ''} ${doc.filename || ''}`);
        return hint.types.some(type => haystack.includes(normalizeText(type)));
    });
    return byText || docs[0];
}

function digitacionFieldNeedles(key, field, doc) {
    const value = String(field?.value || '').trim();
    const label = getDigitacionLabel(field);
    const needles = [];
    if (value.length >= 3) needles.push(value);
    const digits = onlyDigits(value);
    if (digits.length >= 5) needles.push(digits);
    const labelWords = normalizeText(label).split(/\s+/).filter(word => word.length >= 4).slice(0, 2);
    needles.push(...labelWords);
    const keyWords = String(key || '').split('_').filter(word => word.length >= 4).slice(0, 2);
    needles.push(...keyWords);
    if (doc?.document_type) needles.push(...String(doc.document_type).split('_').filter(word => word.length >= 5).slice(0, 2));
    return [...new Set(needles.filter(Boolean))];
}

function buildDigitacionOcrSnippet(doc, field, key) {
    const text = String(doc?.ocr_text || doc?.text_preview || '').replace(/\s+/g, ' ').trim();
    if (!text) return 'Este soporte no tiene texto OCR disponible; revisa directamente la imagen.';
    const needles = digitacionFieldNeedles(key, field, doc);
    const normalizedText = normalizeText(text);
    let index = -1;
    let selected = '';
    for (const needle of needles) {
        const n = normalizeText(needle);
        if (!n || n.length < 3) continue;
        index = normalizedText.indexOf(n);
        if (index >= 0) {
            selected = text.slice(index, index + String(needle).length);
            break;
        }
    }
    const start = index >= 0 ? Math.max(0, index - 180) : 0;
    const end = index >= 0 ? Math.min(text.length, index + 360) : Math.min(text.length, 520);
    let snippet = `${start > 0 ? '... ' : ''}${text.slice(start, end)}${end < text.length ? ' ...' : ''}`;
    if (selected) {
        const escaped = selected.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        snippet = snippet.replace(new RegExp(escaped, 'i'), match => `<mark>${escapeHtml(match)}</mark>`);
        return snippet;
    }
    return escapeHtml(snippet);
}

function renderDigitacionDocumentStage(payload, doc) {
    const stage = document.getElementById('digitacionDocumentStage');
    if (!stage) return;
    if (!payload?.id || !doc?.filename) {
        if (digitacionDocumentStageKey === 'empty' || stage.dataset.stageKey === 'empty') return;
        digitacionDocumentStageKey = 'empty';
        stage.dataset.stageKey = 'empty';
        stage.innerHTML = `
            <div class="digitacion-empty-evidence">
              <strong>Sin soporte cargado</strong>
              <span>Abre un caso desde Bandeja con prellenado OCR para asociar documentos a los campos.</span>
            </div>`;
        return;
    }
    const filename = doc.filename || '';
    const url = documentViewerUrl(payload.id, filename, true);
    const title = doc.display_filename || doc.document_label || filename;
    const stageKey = `${payload.id}::${filename}::${url}`;
    const currentFrame = stage.querySelector('iframe,img');
    const currentSrc = currentFrame?.getAttribute('src') || '';
    if (digitacionDocumentStageKey === stageKey || stage.dataset.stageKey === stageKey || currentSrc === url) {
        if (currentFrame && title) currentFrame.setAttribute('title', title);
        digitacionDocumentStageKey = stageKey;
        stage.dataset.stageKey = stageKey;
        return;
    }
    digitacionDocumentStageKey = stageKey;
    stage.dataset.stageKey = stageKey;
    if (/\.pdf$/i.test(filename)) {
        stage.innerHTML = `<iframe src="${escapeHtml(url)}" title="${escapeHtml(title)}"></iframe>`;
    } else if (/\.(png|jpg|jpeg|webp|bmp|tif|tiff)$/i.test(filename)) {
        stage.innerHTML = `<div style="padding:12px"><img src="${escapeHtml(url)}" alt="${escapeHtml(title)}"></div>`;
    } else {
        stage.innerHTML = `
            <div class="digitacion-empty-evidence">
              <strong>${escapeHtml(title)}</strong>
              <span>Este soporte no es imagen/PDF. Usa Abrir para verlo o descargarlo.</span>
            </div>`;
    }
}

function renderDigitacionDocList(payload, activeFilename = '') {
    const list = document.getElementById('digitacionDocList');
    if (!list) return;
    const docs = getDigitacionDocuments(payload);
    if (!docs.length) {
        list.innerHTML = '';
        renderDigitacionDocSelect(null, '');
        return;
    }
    list.innerHTML = docs.slice(0, 18).map(doc => {
        const filename = doc.filename || '';
        const label = doc.document_label || getReviewTypeLabel(doc.document_type) || filename;
        return `<button class="digitacion-doc-chip${filename === activeFilename ? ' active' : ''}" data-digitacion-doc-file="${escapeHtml(filename)}" type="button" title="${escapeHtml(filename)}">${escapeHtml(label)}</button>`;
    }).join('');
    renderDigitacionDocSelect(payload, activeFilename);
}

function setDigitacionFocusedField(field) {
    document.querySelectorAll('.field-row.digitacion-field-active').forEach(row => row.classList.remove('digitacion-field-active'));
    field?.closest('.field-row')?.classList.add('digitacion-field-active');
    digitacionActiveFieldKey = field?.dataset?.digKey || '';
}

function renderDigitacionDocSelect(payload, activeFilename = '') {
    const select = document.getElementById('digitacionDocSelect');
    if (!select) return;
    const docs = getDigitacionDocuments(payload);
    const current = digitacionEvidenceManualFile || '';
    select.innerHTML = '<option value="">Automático por campo</option>' + docs.map((doc, index) => {
        const filename = doc.filename || '';
        const label = doc.document_label || getReviewTypeLabel(doc.document_type) || filename;
        const name = doc.display_filename || filename;
        return `<option value="${escapeHtml(filename)}">${String(index + 1).padStart(2, '0')} · ${escapeHtml(label)} · ${escapeHtml(name)}</option>`;
    }).join('');
    if (current && docs.some(doc => doc.filename === current)) {
        select.value = current;
    } else {
        select.value = '';
        digitacionEvidenceManualFile = '';
    }
    select.title = select.value || activeFilename || 'Automático por campo';
}

async function updateDigitacionEvidenceForField(field, forcedFilename = '', options = {}) {
    setDigitacionFocusedField(field);
    const title = document.getElementById('digitacionEvidenceTitle');
    const sub = document.getElementById('digitacionEvidenceSub');
    const confidence = document.getElementById('digitacionEvidenceConfidence');
    const text = document.getElementById('digitacionOcrText');
    const openBtn = document.getElementById('digitacionOpenDocBtn');
    const key = field?.dataset?.digKey || '';
    if (!field || !key) {
        digitacionEvidenceDocFile = '';
        renderDigitacionDocumentStage(null, null);
        renderDigitacionDocList(null);
        if (title) title.textContent = 'Soporte del campo';
        if (sub) sub.textContent = 'Enfoca un campo para ver el documento asociado';
        if (confidence) confidence.textContent = 'n/d';
        if (text) text.textContent = 'No hay evidencia seleccionada.';
        if (openBtn) openBtn.disabled = true;
        return;
    }
    try {
        const payload = await ensureDigitacionCasePayload();
        const effectiveForcedFile = digitacionEvidenceManualFile || forcedFilename || '';
        const docs = getDigitacionDocuments(payload);
        const currentDoc = !effectiveForcedFile && digitacionEvidenceDocFile
            ? docs.find(item => (item.filename || '') === digitacionEvidenceDocFile)
            : null;
        const doc = currentDoc || pickDigitacionDocument(key, payload, effectiveForcedFile);
        digitacionEvidenceDocFile = doc?.filename || '';
        const hint = getDigitacionFieldHint(key);
        const source = readDigitacionDraft()?.prefill_sources?.[key] || payload?.analysis?.digitacion_prefill?.sources?.[key] || {};
        if (title) title.textContent = getDigitacionLabel(field);
        if (sub) sub.textContent = doc?.filename ? `${hint.label} · ${doc.display_filename || doc.filename}` : 'No encontré documento asociado en este caso';
        if (confidence) {
            const value = source?.confidence ?? doc?.classification_confidence ?? doc?.ocr_quality_score ?? '';
            const numeric = Number(value);
            confidence.textContent = Number.isFinite(numeric) ? `conf. ${Math.round(numeric * 100)}%` : 'n/d';
        }
        if (text) text.innerHTML = doc ? buildDigitacionOcrSnippet(doc, field, key) : 'No hay OCR para este campo.';
        renderDigitacionDocumentStage(payload, doc);
        renderDigitacionDocList(payload, doc?.filename || '');
        if (openBtn) {
            openBtn.disabled = !(payload?.id && doc?.filename);
            openBtn.dataset.case = payload?.id || '';
            openBtn.dataset.file = doc?.filename || '';
            openBtn.dataset.title = getDigitacionLabel(field);
            openBtn.dataset.displayName = doc?.display_filename || doc?.document_label || doc?.filename || '';
        }
    } catch (e) {
        console.warn('digitacion evidence:', e);
        if (sub) sub.textContent = 'No pude cargar la evidencia del caso activo';
        if (text) text.textContent = e.message || 'Error cargando evidencia.';
        if (openBtn) openBtn.disabled = true;
    }
}

function sectionHasDigitacionData(section) {
    const keys = DIGITACION_SECTION_KEYS[section] || [];
    return keys.some(key => String(getDigitacionField(key)?.value || '').trim());
}

function digitacionIsTraslado(data = collectDigitacionData().values) {
    return normalizeText(`${data.tipo_tramite || ''} ${data.tipo_afiliacion || ''}`).includes('traslado');
}

function digitacionIsContratista(data = collectDigitacionData().values) {
    const text = normalizeText(`${data.tipo_afiliacion || ''} ${data.source_entry_type || ''}`);
    return text.includes('contratista') || text.includes('independiente');
}

function digitacionRequiredKeysForSection(section, data = collectDigitacionData().values) {
    if (section === 'novedades' && digitacionIsContratista(data)) return [];
    const keys = [...(DIGITACION_REQUIRED[section] || [])];
    if (section === 'novedades' && parseDigitacionTrabajadores(data.trabajadores_adicionales || '').length) {
        return [];
    }
    if (section === 'afiliacion') {
        keys.push(...(digitacionIsTraslado(data) ? DIGITACION_REQUIRED_TRASLADO_LEGACY : DIGITACION_REQUIRED_AFILIACION_LEGACY));
    }
    return Array.from(new Set(keys));
}

function shouldRequireDigitacionSection(section, mode) {
    if (section === 'radicacion') return true;
    if (section === 'afiliacion') return true;
    if (section === 'novedades' && digitacionIsContratista()) return false;
    if (mode === 'full' && section === 'sedes') return true;
    if (mode === 'full' && section === 'novedades') return true;
    if (mode === 'all') return sectionHasDigitacionData(section);
    return digitacionActiveTab === section || sectionHasDigitacionData(section);
}

function digitacionDocumentNumberMessage(docTypeValue, documentValue, label) {
    const docType = normalizeDigitacionDocumentTypeForUi(docTypeValue || '').toUpperCase();
    const rawValue = String(documentValue || '').trim();
    const digits = onlyDigits(rawValue);
    if (!rawValue) return '';
    if (digits !== rawValue) return `${label} debe ser numérico.`;
    if (['CC', 'TI'].includes(docType)) {
        return digits.length > 6 && digits.length < 11 && digits.length !== 9
            ? ''
            : `${label} debe tener 7, 8 o 10 dígitos cuando el tipo de documento es ${docType}.`;
    }
    if (docType === 'CE') {
        return digits.length < 6
            ? ''
            : `${label} debe tener menos de 6 dígitos cuando el tipo de documento es CE.`;
    }
    return digits.length >= 5 && digits.length <= 15
        ? ''
        : `${label} debe tener entre 5 y 15 dígitos para el 926.`;
}

function validateDigitacionValue(key, value, data) {
    const v = String(value || '').trim();
    const label = getDigitacionLabel(getDigitacionField(key));
    if (!v) return '';

    const legacyLimit = AFILEGA_MDB_FIELD_LIMITS[key];
    if (legacyLimit && v.length > legacyLimit) {
        return `${label} excede el máximo permitido (${legacyLimit} caracteres).`;
    }
    const usesExternalCatalog = key === 'tipo_cotizante' && DIGITACION_TIPO_COTIZANTE_VALUES.size;
    const mdbValueCatalog = !usesExternalCatalog && Array.isArray(AFILEGA_MDB_VALUE_CATALOGS?.[key]) ? AFILEGA_MDB_VALUE_CATALOGS[key] : [];
    if (mdbValueCatalog.length && !mdbValueCatalog.map(item => String(item || '').trim().toUpperCase()).includes(v.toUpperCase())) {
        return `${label} no existe en el catálogo de valores AFILEGA (${mdbValueCatalog.join(', ')}).`;
    }

    if (DIGITACION_ALPHA_KEYS.has(key) && !DIGITACION_ALPHA_RE.test(v)) {
        return `${label} solo permite letras y espacios.`;
    }
    if (key === 'tipo_afiliacion') {
        const clase = normalizeText(v).replace(/[^a-z0-9]+/g, ' ').trim();
        return DIGITACION_CLASE_AFILIACION_VALUES.has(clase) ? '' : `${label} debe ser Primera vez, Traslado o Independiente - Contratista.`;
    }
    if (key === 'razon_social') {
        return DIGITACION_ALNUM_RE.test(v) ? '' : `${label} debe ser alfanumérica.`;
    }
    if (key === 'sede_centro_trabajo_nombre') {
        if (!DIGITACION_ALNUM_RE.test(v)) return `${label} debe ser alfanumérico.`;
        return v.length <= 60 ? '' : `${label} no puede superar 60 caracteres.`;
    }
    if (key === 'genero') {
        return ['F', 'M'].includes(v.toUpperCase()) ? '' : `${label} debe ser M o F.`;
    }
    if (key === 'eps') {
        return isDigitacionEpsValid(v) ? '' : `${label} debe ser un código EPS válido del catálogo estandarizado.`;
    }
    if (key === 'afp') {
        return isDigitacionAfpValid(v) ? '' : `${label} debe ser un código AFP válido del catálogo estandarizado.`;
    }
    if (key === 'cargo_actividad') {
        return DIGITACION_CARGO_TRABAJADORES_CODES.has(normalizeDigitacionCargoCode(v)) ? '' : `${label} debe ser un código de cargo válido del catálogo de trabajadores.`;
    }
    if (key.includes('correo')) {
        return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/i.test(v) ? '' : `${label} debe tener un correo válido.`;
    }
    if (key.includes('celular')) {
        return /^\d{10}$/.test(v) ? '' : `${label} debe ser numérico de 10 dígitos.`;
    }
    if (key.includes('telefono') || key === 'sede_telefono') {
        return /^\d{10}$/.test(v) ? '' : `${label} debe ser numérico de 10 dígitos.`;
    }
    if (key.includes('extension')) {
        return /^\d{1,6}$/.test(v) ? '' : `${label} debe tener solo dígitos.`;
    }
    if (key === 'tipo_documento_afiliado') {
        return ['CC', 'TI', 'PE', 'PT', 'CE'].includes(v.toUpperCase()) ? '' : `${label} debe ser CC, TI, PE, PT o CE.`;
    }
    if (['empleador_tipo_documento', 'rep_legal_tipo_documento', 'responsable_sede_principal_tipo_documento'].includes(key)) {
        return DIGITACION_ALLOWED_WORKER_DOC_TYPES.has(normalizeDigitacionDocumentTypeForUi(v)) ? '' : `${label} no es válido según el catálogo AFILEGA.`;
    }
    if (key === 'trabajador_centro_trabajo') {
        return digitacionCentroOptions().some(row => row.value === v) ? '' : `${label} debe corresponder a un centro de trabajo registrado.`;
    }
    if (key === 'fecha_nacimiento') {
        return /^\d{8}$/.test(v) && parseDigitacionDate(v) ? '' : `${label} debe ser numérica en formato DDMMAAAA.`;
    }
    if (key === 'camara_fecha_constitucion') {
        const parsed = parseDigitacionDate(v);
        if (!parsed) return `${label} debe ser una fecha válida.`;
        return formatLocalIsoDate(parsed) <= todayIsoDate()
            ? ''
            : `${label} no puede ser mayor a la fecha actual.`;
    }
    if (key === 'nit') {
        const digits = onlyDigits(v);
        if (digits !== v) return `${label} debe ser numérico.`;
        const tipoDoc = normalizeDigitacionDocumentTypeForUi(data?.empleador_tipo_documento || '');
        if (tipoDoc === 'NIT' && digits.length !== 9) {
            return `${label} debe tener 9 dígitos cuando el Tipo Id es NIT.`;
        }
        if (tipoDoc === 'CC' && !(digits.length > 6 && digits.length < 11 && digits.length !== 9)) {
            return `${label} debe tener 7, 8 o 10 dígitos cuando el Tipo Id es CC.`;
        }
        return /^\d{5,20}$/.test(digits) ? '' : `${label} debe tener entre 5 y 20 dígitos.`;
    }
    if (key === 'nit_dv') {
        if (!/^\d$/.test(v)) return `${label} debe ser un solo dígito.`;
        const expected = calculateAfilegaNitDv(data.nit || '');
        return expected && v === expected ? '' : `${label} no coincide con el cálculo AFILEGA; esperado ${expected || 'n/d'}.`;
    }
    if (key === 'tipo_cotizante') {
        const allowed = DIGITACION_TIPO_COTIZANTE_VALUES.size ? DIGITACION_TIPO_COTIZANTE_VALUES : AFILEGA_MDB_ALLOWED_TIPO_COTIZANTE;
        return allowed.has(v) ? '' : `${label} debe existir en la tabla de tipo cotizante de trabajadores.`;
    }
    if (key === 'subtipo_cotizante') {
        return v === AFILEGA_MDB_DEFAULT_SUBTIPO_COTIZANTE ? '' : `${label} debe ser ${AFILEGA_MDB_DEFAULT_SUBTIPO_COTIZANTE} según reglas AFILEGA.`;
    }
    if (key === 'tipo_novedad') {
        return AFILEGA_MDB_ALLOWED_NOVEDAD_CODES.has(v) ? '' : `${label} debe usar código 00 u 08 según reglas de novedades.`;
    }
    if (key === 'novedad_estado') {
        return AFILEGA_MDB_ALLOWED_NOVEDAD_ESTADO.has(v) ? '' : `${label} debe ser 1 según Plano_Nov_Tmp.`;
    }
    if (key === 'novedad_autoliquidacion') {
        return AFILEGA_MDB_ALLOWED_NOVEDAD_AUTOLIQUIDACION.has(v.toUpperCase()) ? '' : `${label} debe ser N según Plano_Nov_Tmp.`;
    }
    if (key === 'novedad_origen') {
        return AFILEGA_MDB_ALLOWED_NOVEDAD_ORIGEN.has(v.toUpperCase()) ? '' : `${label} debe ser C según Plano_Nov_Tmp.`;
    }
    if (key === 'empresa_zona_localizacion') {
        return AFILEGA_MDB_ALLOWED_ZONA.has(v.toUpperCase()) ? '' : `${label} debe ser U o R según reglas AFILEGA.`;
    }
    if (key === 'empresa_vinculador_laboral') {
        return DIGITACION_VINCULADOR_LABORAL_VALUES.has(v) ? '' : `${label} debe existir en la tabla de vinculador laboral del contratante.`;
    }
    if (DIGITACION_SN_KEYS.has(key)) {
        return AFILEGA_MDB_ALLOWED_BOOLEAN_SN.has(v.toUpperCase()) ? '' : `${label} debe ser S o N según reglas AFILEGA.`;
    }
    if ([
        'empresa_forma_pago',
        'empresa_tipo_aportante',
        'empresa_clase_aportante',
        'empresa_vinculador_laboral',
        'empresa_regimen',
        'empresa_naturaleza',
        'empresa_clase_sociedad',
        'empresa_tamano',
        'empresa_grupo',
        'empresa_tipo_localizacion',
        'sede_tipo_localizacion',
        'novedad_dias',
    ].includes(key)) {
        return /^\d{1,3}$/.test(v) ? '' : `${label} debe ser código numérico de máximo 3 dígitos según reglas AFILEGA.`;
    }
    if ([
        'a_numero_sedes',
        'a_numero_centros_trabajo',
        'a_numero_inicial_trabajadores_estudiantes',
        'sede_numero_trabajadores',
        'b_numero_sedes',
        'b_numero_centros_trabajo',
        'b_numero_total_trabajadores_estudiantes',
    ].includes(key)) {
        return /^\d{1,6}$/.test(v) ? '' : `${label} debe ser un conteo numérico válido.`;
    }
    if (key === 'sede_numero_trabajadores' && data.a_numero_inicial_trabajadores_estudiantes && String(v) !== String(data.a_numero_inicial_trabajadores_estudiantes)) {
        return `${label} debe coincidir con A trabajadores iniciales.`;
    }
    if (key === 'sede_tarifa') {
        const n = Number(v);
        if (!Number.isFinite(n) || n < 0) return `${label} debe ser una tarifa numérica válida.`;
        const expected = digitacionTarifaForGrado(data.sede_grado);
        if (expected && String(v) !== expected) return `${label} debe ser ${expected} para grado de riesgo ${digitacionRiskGrade(data.sede_grado)}.`;
        return '';
    }
    if (key === 'sede_grado') {
        const grade = digitacionRiskGrade(v);
        if (!['1', '2', '3', '4', '5'].includes(grade)) return `${label} debe ser un grado de riesgo entre 1 y 5.`;
        const activityFirst = digitacionActivityCode(data?.sede_codigo_actividad || '').slice(0, 1);
        if (activityFirst && activityFirst !== grade) {
            return `${label} debe ser ${activityFirst} porque el código de actividad económica inicia en ${activityFirst}.`;
        }
        return '';
    }
    if (key === 'estado_cuenta_empleador') {
        return ['al dia', 'al día', 'en mora', 'acuerdo de pago', 'incumplimiento de acuerdo de pago'].includes(normalizeText(v)) ? '' : `${label} no es válido para traslado.`;
    }
    if (key.includes('fecha')) {
        return parseDigitacionDate(v) ? '' : `${label} debe ser una fecha válida.`;
    }
    if (DIGITACION_MONEY_KEYS.has(key)) {
        const n = Number(v);
        if (!Number.isFinite(n) || n < 0 || (['ibc', 'nuevo_ibc', 'valor_total_contrato', 'valor_mensual_contrato'].includes(key) && n <= 0)) return `${label} debe ser un valor numérico válido.`;
        const smmlv = digitacionSmmlvForData(data);
        const allowsBelowSmmlv = key === 'ibc' && onlyDigits(data?.tipo_cotizante || '') === '51';
        if ((key === 'ibc' || key === 'nuevo_ibc') && !allowsBelowSmmlv && smmlv && n < smmlv) return `${label} no puede ser inferior al SMMLV configurado (${smmlv}).`;
        if ((key === 'ibc' || key === 'nuevo_ibc') && smmlv && n > smmlv * 25) return `${label} no puede superar 25 SMMLV configurados (${smmlv * 25}).`;
        return '';
    }
    if (key.includes('clase_riesgo')) {
        return ['1', '2', '3', '4', '5'].includes(digitacionRiskGrade(v)) ? '' : `${label} debe estar entre 1 y 5.`;
    }
    if (key === 'camara_codigo_actividad') {
        if (!/^\d{4,7}$/.test(v)) return `${label} debe tener un código numérico de la tabla de Cámara de Comercio.`;
        return digitacionCamaraActivityProfile(v) ? '' : `${label} no existe en la tabla de actividad de Cámara de Comercio.`;
    }
    if (key.includes('codigo_actividad')) {
        const activityCode = digitacionActivityCode(v);
        if (!/^\d{7}$/.test(activityCode)) return `${label} debe tener 7 dígitos para el catálogo ARP/926.`;
        return digitacionActivityProfile(v) ? '' : `${label} no existe en el catálogo de actividad económica ARP usado por el 926.`;
    }
    if (key === 'nuevo_codigo_ocupacion') {
        return /^\d{4,10}$/.test(v) ? '' : `${label} debe ser un código numérico CUOC/ocupación válido.`;
    }
    if (key === 'edad') {
        return /^\d{1,3}$/.test(v) ? '' : `${label} se calcula con la fecha de nacimiento.`;
    }
    if (key === 'documento_afiliado') {
        return digitacionDocumentNumberMessage(data?.tipo_documento_afiliado, v, label);
    }
    if (key === 'nit' || key === 'rep_legal_numero_documento' || key === 'responsable_sede_principal_numero_documento') {
        const digits = onlyDigits(v);
        const max = key === 'nit' ? 15 : 15;
        return digits === v && digits.length >= 5 && digits.length <= max ? '' : `${label} debe ser numérico y tener entre 5 y ${max} dígitos para el 926.`;
    }
    if (key === 'sede_codigo') {
        return /^\d{1,6}$/.test(v) ? '' : `${label} debe ser numérico, máximo 6 dígitos.`;
    }
    if (key.includes('municipio')) {
        const sourceId = getDigitacionField(key)?.dataset?.departmentSource;
        const departmentField = sourceId ? document.getElementById(sourceId) : null;
        const dept = findDepartmentName(departmentField?.value || '');
        return findMunicipalityName(dept, v) ? '' : `${label} debe pertenecer al departamento seleccionado.`;
    }
    if (key.includes('departamento')) {
        return findDepartmentName(v) ? '' : `${label} debe existir en la tabla de departamentos.`;
    }
    if (key === 'razon_social') {
        return v.length >= 2 ? '' : `${label} debe tener al menos 2 caracteres.`;
    }
    if (key === 'sedes_adicionales') {
        const rows = parseDigitacionCentrosAdicionales(v);
        for (const [index, row] of rows.entries()) {
            const { codigo, nombre, sucursal, direccion, municipio, departamento, zona, telefono, celular, correo, codigo_actividad, clase, trabajadores, transporte, grado, tarifa, contacto, cargo_contacto } = row;
            if (!/^[0-9A-Za-z.-]{1,20}$/.test(codigo)) return `Sede adicional línea ${index + 1}: código inválido.`;
            if (!DIGITACION_ALPHA_RE.test(nombre)) return `Sede adicional línea ${index + 1}: nombre solo permite letras y espacios.`;
            if (!sucursal) return `Sede adicional línea ${index + 1}: sucursal es obligatoria.`;
            if (direccion.length < 5) return `Sede adicional línea ${index + 1}: dirección demasiado corta.`;
            const dept = findDepartmentName(departamento);
            if (!dept) return `Sede adicional línea ${index + 1}: departamento no existe en la tabla.`;
            if (!findMunicipalityName(dept, municipio)) return `Sede adicional línea ${index + 1}: municipio no pertenece al departamento.`;
            if (!['urbana', 'rural', 'U', 'R'].includes(String(zona || '').trim())) return `Sede adicional línea ${index + 1}: zona es obligatoria.`;
            if (!/^\d{10}$/.test(telefono)) return `Sede adicional línea ${index + 1}: teléfono debe tener 10 dígitos.`;
            if (celular && !/^\d{10}$/.test(celular)) return `Sede adicional línea ${index + 1}: celular debe tener 10 dígitos.`;
            if (correo && !/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/i.test(correo)) return `Sede adicional línea ${index + 1}: correo no es válido.`;
            if (!digitacionActivityProfile(codigo_actividad)) return `Sede adicional línea ${index + 1}: código de actividad no existe en el catálogo ARP/926.`;
            if (!['1', '2', '3', '4', '5'].includes(digitacionRiskGrade(clase))) return `Centro adicional línea ${index + 1}: clase de riesgo debe estar entre 1 y 5.`;
            if (!/^\d{1,6}$/.test(trabajadores)) return `Centro adicional línea ${index + 1}: número de trabajadores debe ser numérico.`;
            if (!transporte) return `Centro adicional línea ${index + 1}: transporte es obligatorio.`;
            if (!['S', 'N'].includes(transporte.toUpperCase())) return `Centro adicional línea ${index + 1}: transporte debe ser S o N.`;
            if (!['1', '2', '3', '4', '5'].includes(digitacionRiskGrade(grado))) return `Centro adicional línea ${index + 1}: grado de riesgo debe estar entre 1 y 5.`;
            const activityFirst = digitacionActivityCode(codigo_actividad).slice(0, 1);
            if (activityFirst && activityFirst !== digitacionRiskGrade(grado)) return `Centro adicional línea ${index + 1}: grado de riesgo debe ser ${activityFirst} porque el código de actividad inicia en ${activityFirst}.`;
            const expected = digitacionTarifaForGrado(grado);
            if (expected && tarifa && String(tarifa) !== expected) return `Centro adicional línea ${index + 1}: tarifa debe ser ${expected} para grado ${digitacionRiskGrade(grado)}.`;
            if (!DIGITACION_ALPHA_RE.test(contacto)) return `Centro adicional línea ${index + 1}: contacto solo permite letras y espacios.`;
            if (!DIGITACION_ALPHA_RE.test(cargo_contacto)) return `Centro adicional línea ${index + 1}: cargo contacto solo permite letras y espacios.`;
        }
        return '';
    }
    return '';
}

function buildDigitacionLegacyMdbPayload(values = {}) {
    const deptEmpresa = departmentLegacyCode(values.departamento_empresa);
    const munEmpresa = municipalityLegacyCode(values.municipio_empresa);
    const deptSede = departmentLegacyCode(values.sede_departamento);
    const munSede = municipalityLegacyCode(values.sede_municipio);
    const trabajadores = digitacionWorkerRows(values).map(row => ({
        afi_tipoid: row.tipo_documento_afiliado || '',
        afi_nroid: onlyDigits(row.documento_afiliado),
        afi_centro_trabajo: row.trabajador_centro_trabajo || '',
        afi_apellido1: row.primer_apellido || '',
        afi_apellido2: row.segundo_apellido || '',
        afi_nombre1: row.primer_nombre || '',
        afi_nombre2: row.segundo_nombre || '',
        afi_fecha_nacimiento: row.fecha_nacimiento || '',
        afi_edad: row.edad || digitacionAgeFromBirthDate(row.fecha_nacimiento),
        afi_genero: row.genero || '',
        afi_ibc: row.ibc || '',
        afi_cod_cargo: row.cargo_actividad || '',
        afi_cod_eps: row.eps || '',
        afi_cod_afp: row.afp || '',
        afi_tipo_cotizante: row.tipo_cotizante || '',
        afi_subtipo_cotizante: row.subtipo_cotizante || values.subtipo_cotizante || '',
    }));
    const trabajadorPrincipal = trabajadores[0] || {};
    return {
        source: `Afiliaciones.mdb v${AFILEGA_MDB_VERSION}`,
        formulario: {
            tipo_tramite: values.tipo_tramite || '',
            tipo_afiliacion: values.tipo_afiliacion || '',
            numero_radicacion: values.numero_radicacion || '',
            fecha_radicacion: values.fecha_radicacion || '',
            fecha_inicio_cobertura: values.fecha_inicio_cobertura || '',
            tipo_persona: values.tipo_persona || '',
            a_numero_sedes: onlyDigits(values.a_numero_sedes),
            a_numero_centros_trabajo: onlyDigits(values.a_numero_centros_trabajo),
            a_numero_inicial_trabajadores_estudiantes: onlyDigits(values.a_numero_inicial_trabajadores_estudiantes),
            a_valor_total_nomina: values.a_valor_total_nomina || '',
            b_numero_sedes: onlyDigits(values.b_numero_sedes),
            b_numero_centros_trabajo: onlyDigits(values.b_numero_centros_trabajo),
            b_numero_total_trabajadores_estudiantes: onlyDigits(values.b_numero_total_trabajadores_estudiantes),
            b_monto_total_cotizacion: values.b_monto_total_cotizacion || '',
            estado_cuenta_empleador: values.estado_cuenta_empleador || '',
        },
        empresa: {
            emp_tipoid: normalizeDigitacionDocumentTypeForLegacy(values.empleador_tipo_documento || 'NIT'),
            emp_nit: onlyDigits(values.nit),
            emp_digito: values.nit_dv || calculateAfilegaNitDv(values.nit),
            emp_razonsocial: values.razon_social || '',
            emp_departamento: deptEmpresa,
            emp_ciudad: munEmpresa,
            emp_direccion: values.direccion_empresa || '',
            emp_email: values.correo_empresa || '',
            emp_actividad: onlyDigits(values.codigo_actividad_economica),
            emp_clase: digitacionRiskNumber(values.clase_riesgo_empresa),
            emp_forma_pago: values.empresa_forma_pago || '',
            emp_aportante: values.empresa_tipo_aportante || '',
            emp_vinculador: values.empresa_vinculador_laboral || '',
            emp_regimen: values.empresa_regimen || '',
            emp_cod_naturaleza: values.empresa_naturaleza || '',
            emp_cod_clase_soc: values.empresa_clase_sociedad || '',
            emp_cod_tam_empresa: values.empresa_tamano || '',
            emp_cod_grupo_emp: values.empresa_grupo || '',
            emp_cod_tipo_loc: values.empresa_tipo_localizacion || '',
            emp_cod_zona_loc: values.empresa_zona_localizacion || '',
            emp_pyme: values.empresa_pyme || '',
            emp_olcsa: values.empresa_olcsa || '',
            bln_contratante: values.empresa_contratante || '',
            emp_arp: values.empresa_arl_anterior || '',
        },
        representante_legal: {
            rep_legal_nombre_completo: values.rep_legal_nombre_completo || '',
            rep_legal_tipo_documento: values.rep_legal_tipo_documento || '',
            rep_legal_numero_documento: onlyDigits(values.rep_legal_numero_documento),
            rep_legal_correo: values.rep_legal_correo || '',
        },
        centro_trabajo: {
            cen_codigo: values.sede_codigo || '',
            cen_nombre: values.sede_centro_trabajo_nombre || values.sede_nombre || '',
            cen_departamento: deptSede,
            cen_ciudad: munSede,
            cen_direccion: values.sede_direccion || '',
            cen_telefono: onlyDigits(values.sede_telefono),
            cen_fax: onlyDigits(values.sede_fax),
            cen_email: values.sede_correo || '',
            cen_transporte: values.sede_transporte || '',
            cen_clase: digitacionRiskNumber(values.sede_clase_riesgo),
            cen_grado: values.sede_grado || '',
            cen_tarifa: values.sede_tarifa || '',
            cen_actividad: onlyDigits(values.sede_codigo_actividad),
            cen_cod_tipo_loc: values.sede_tipo_localizacion || '',
            cen_zona: values.sede_zona === 'urbana' ? 'U' : values.sede_zona === 'rural' ? 'R' : values.sede_zona || '',
            cen_contacto: values.sede_contacto || '',
            cen_cargo_contacto: values.sede_cargo_contacto || '',
        },
        centros_trabajo_adicionales: parseDigitacionCentrosAdicionales(values.sedes_adicionales),
        responsable_sede_principal: {
            responsable_sede_principal_nombre_completo: values.responsable_sede_principal_nombre_completo || '',
            responsable_sede_principal_tipo_documento: values.responsable_sede_principal_tipo_documento || '',
            responsable_sede_principal_numero_documento: onlyDigits(values.responsable_sede_principal_numero_documento),
        },
        trabajador: {
            afi_tipoid: trabajadorPrincipal.afi_tipoid || '',
            afi_nroid: trabajadorPrincipal.afi_nroid || '',
            afi_centro_trabajo: trabajadorPrincipal.afi_centro_trabajo || '',
            afi_apellido1: trabajadorPrincipal.afi_apellido1 || '',
            afi_apellido2: trabajadorPrincipal.afi_apellido2 || '',
            afi_nombre1: trabajadorPrincipal.afi_nombre1 || '',
            afi_nombre2: trabajadorPrincipal.afi_nombre2 || '',
            afi_fecha_nacimiento: trabajadorPrincipal.afi_fecha_nacimiento || '',
            afi_edad: trabajadorPrincipal.afi_edad || '',
            afi_genero: trabajadorPrincipal.afi_genero || '',
            afi_ibc: trabajadorPrincipal.afi_ibc || '',
            afi_cod_cargo: trabajadorPrincipal.afi_cod_cargo || '',
            afi_cod_eps: trabajadorPrincipal.afi_cod_eps || '',
            afi_cod_afp: trabajadorPrincipal.afi_cod_afp || '',
            afi_tipo_cotizante: trabajadorPrincipal.afi_tipo_cotizante || '',
            afi_subtipo_cotizante: trabajadorPrincipal.afi_subtipo_cotizante || '',
        },
        trabajadores,
        contrato: {
            numero_contrato: values.numero_contrato || '',
            tipo_contrato: values.tipo_contrato || '',
            fecha_inicio_contrato: values.fecha_inicio_contrato || '',
            fecha_fin_contrato: values.fecha_fin_contrato || '',
            valor_total_contrato: values.valor_total_contrato || '',
            valor_mensual_contrato: values.valor_mensual_contrato || '',
        },
        novedad: {
            cod_tipo_novedad_trabajador: values.tipo_novedad || '',
            fec_inicio: values.fecha_novedad_inicio || '',
            fec_final: values.fecha_novedad_fin || '',
            arl_anterior: values.arl_anterior || '',
            nuevo_ibc: values.nuevo_ibc || '',
            nuevo_centro_trabajo: values.nuevo_centro_trabajo || '',
            nuevo_codigo_ocupacion: onlyDigits(values.nuevo_codigo_ocupacion),
            novedad_contrato: values.novedad_contrato || '',
            num_dias: values.novedad_dias || '',
            cod_estado_novedad: values.novedad_estado || '',
            bln_autoliquidacion: values.novedad_autoliquidacion || '',
            valor_anterior: values.novedad_valor_anterior || '',
            valor_nuevo: values.novedad_valor_nuevo || '',
            traslado: values.novedad_traslado || '',
            origen: values.novedad_origen || '',
            observaciones: values.novedad_observaciones || '',
        },
    };
}

function validateDigitacionForm(mode = 'active') {
    const data = collectDigitacionData().values;
    const errors = [];
    getDigitacionFields().forEach(field => setDigitacionFieldError(field, ''));

    for (const section of Object.keys(DIGITACION_REQUIRED)) {
        if (!shouldRequireDigitacionSection(section, mode)) continue;
        for (const key of digitacionRequiredKeysForSection(section, data)) {
            const field = getDigitacionField(key);
            if (!field) continue;
            if (!String(field.value || '').trim()) {
                const message = `${getDigitacionLabel(field)} es obligatorio.`;
                setDigitacionFieldError(field, message);
                errors.push({ key, section, message });
            }
        }
    }

    for (const field of getDigitacionFields()) {
        const key = field.dataset.digKey;
        const message = validateDigitacionValue(key, field.value, data);
        if (message) {
            setDigitacionFieldError(field, message);
            errors.push({ key, section: field.closest('[data-digitacion-panel]')?.dataset?.digitacionPanel || '', message });
        }
    }

    const workerRows = digitacionWorkerRows(data);
    if (!digitacionIsContratista(data)) {
        workerRows.forEach((row, index) => {
            validateDigitacionWorkerRow(row, index + 1).forEach(error => {
                setDigitacionFieldError(getDigitacionField('trabajadores_adicionales'), error.message);
                errors.push(error);
            });
        });
        validateDigitacionWorkerDuplicates(workerRows).forEach(error => {
            setDigitacionFieldError(getDigitacionField('trabajadores_adicionales'), error.message);
            errors.push(error);
        });

        validateDigitacionWorkerCenterCounts(data).forEach(error => {
            setDigitacionFieldError(getDigitacionField(error.key), error.message);
            errors.push(error);
        });
    }

    const radicacion = parseDigitacionDate(data.fecha_radicacion);
    const cobertura = parseDigitacionDate(data.fecha_inicio_cobertura);
    if (radicacion && cobertura && cobertura < radicacion) {
        const field = getDigitacionField('fecha_inicio_cobertura');
        const message = 'La cobertura no puede ser anterior a la radicación.';
        setDigitacionFieldError(field, message);
        errors.push({ key: 'fecha_inicio_cobertura', section: 'radicacion', message });
    }
    if (radicacion && cobertura && data.tipo_tramite === 'afiliacion') {
        const isTraslado = normalizeCatalogText(data.tipo_afiliacion).includes('TRASLADO');
        const vigencia = parseDigitacionDate(data.fecha_inicio_vigencia);
        const expected = isTraslado && vigencia ? new Date(vigencia) : new Date(radicacion);
        if (!isTraslado) expected.setDate(expected.getDate() + 1);
        if (formatLocalIsoDate(cobertura) !== formatLocalIsoDate(expected)) {
            const field = getDigitacionField('fecha_inicio_cobertura');
            const message = isTraslado
                ? 'Para traslado, la cobertura debe coincidir con la fecha inicio vigencia.'
                : 'Para afiliación inicial, la cobertura debe ser exactamente un día después de la radicación.';
            setDigitacionFieldError(field, message);
            errors.push({ key: 'fecha_inicio_cobertura', section: 'radicacion', message });
        }
    }

    const nacimiento = parseDigitacionDate(data.fecha_nacimiento);
    if (nacimiento && nacimiento >= new Date()) {
        const field = getDigitacionField('fecha_nacimiento');
        const message = 'La fecha de nacimiento debe ser anterior a hoy.';
        setDigitacionFieldError(field, message);
        errors.push({ key: 'fecha_nacimiento', section: 'novedades', message });
    }

    const inicioContrato = parseDigitacionDate(data.fecha_inicio_contrato);
    const finContrato = parseDigitacionDate(data.fecha_fin_contrato);
    if (inicioContrato && finContrato && finContrato < inicioContrato) {
        const field = getDigitacionField('fecha_fin_contrato');
        const message = 'La fecha de terminación no puede ser anterior al inicio del contrato.';
        setDigitacionFieldError(field, message);
        errors.push({ key: 'fecha_fin_contrato', section: 'afiliacion', message });
    }
    const valorTotal = Number(data.valor_total_contrato || 0);
    const valorMensual = Number(data.valor_mensual_contrato || 0);
    if (Number.isFinite(valorTotal) && Number.isFinite(valorMensual) && valorTotal > 0 && valorMensual > valorTotal) {
        const field = getDigitacionField('valor_mensual_contrato');
        const message = 'El valor mensual no puede ser mayor al valor total del contrato.';
        setDigitacionFieldError(field, message);
        errors.push({ key: 'valor_mensual_contrato', section: 'afiliacion', message });
    }

    const mainActivity = digitacionActivityProfile(data.codigo_actividad_economica);
    const mainRisk = digitacionRiskNumber(data.clase_riesgo_empresa);
    if (mainActivity?.clase && mainRisk && mainActivity.clase !== mainRisk) {
        const field = getDigitacionField('clase_riesgo_empresa');
        const message = `La clase de riesgo no coincide con la actividad ${onlyDigits(data.codigo_actividad_economica)}; el catálogo ARP indica clase ${mainActivity.clase}.`;
        setDigitacionFieldError(field, message);
        errors.push({ key: 'clase_riesgo_empresa', section: 'afiliacion', message });
    }

    const sedeActivity = digitacionActivityProfile(data.sede_codigo_actividad);
    const sedeRisk = digitacionRiskNumber(data.sede_clase_riesgo);
    if (sedeActivity?.clase && sedeRisk && sedeActivity.clase !== sedeRisk) {
        const field = getDigitacionField('sede_clase_riesgo');
        const message = `La clase de riesgo del centro no coincide con la actividad ${onlyDigits(data.sede_codigo_actividad)}; el catálogo ARP indica clase ${sedeActivity.clase}.`;
        setDigitacionFieldError(field, message);
        errors.push({ key: 'sede_clase_riesgo', section: 'sedes', message });
    }

    const inicioNovedad = parseDigitacionDate(data.fecha_novedad_inicio);
    const finNovedad = parseDigitacionDate(data.fecha_novedad_fin);
    if (inicioNovedad && finNovedad && finNovedad < inicioNovedad) {
        const field = getDigitacionField('fecha_novedad_fin');
        const message = 'La fecha final de novedad no puede ser anterior a la fecha inicial.';
        setDigitacionFieldError(field, message);
        errors.push({ key: 'fecha_novedad_fin', section: 'novedades', message });
    }

    if (errors.length) {
        const first = errors[0];
        if (first.section && document.querySelector(`[data-digitacion-tab="${first.section}"]`)) switchDigitacionTab(first.section);
        setTimeout(() => {
            const field = getDigitacionField(first.key);
            if (field?.offsetParent !== null) field.focus();
        }, 50);
        updateDigitacionStatus(`${errors.length} campo(s) por corregir`, 'err');
        return { ok: false, errors };
    }

    updateDigitacionStatus('Validación correcta', 'ok');
    return { ok: true, errors: [] };
}

function digitacionDraftStorageKey(caseId = '') {
    const id = String(caseId || '').trim();
    return id ? `${DIGITACION_DRAFT_KEY}:${id}` : DIGITACION_DRAFT_KEY;
}

function readDigitacionDraft(caseId = '') {
    try {
        const targetCaseId = String(caseId || activeCaseId || '').trim();
        if (targetCaseId) {
            const scoped = JSON.parse(localStorage.getItem(digitacionDraftStorageKey(targetCaseId)) || '{}');
            if (scoped && Object.keys(scoped).length) return scoped;
            const legacy = JSON.parse(localStorage.getItem(DIGITACION_DRAFT_KEY) || '{}');
            if (legacy?.source_case_id === targetCaseId) return legacy;
            return {};
        }
        return JSON.parse(localStorage.getItem(DIGITACION_DRAFT_KEY) || '{}');
    } catch {
        return {};
    }
}

function writeDigitacionDraft(data) {
    try {
        const serialized = JSON.stringify(data || {});
        const caseId = String(data?.source_case_id || activeCaseId || '').trim();
        if (caseId) localStorage.setItem(digitacionDraftStorageKey(caseId), serialized);
        localStorage.setItem(DIGITACION_DRAFT_KEY, serialized);
    } catch {}
}

function collectDigitacionData() {
    const values = {};
    getDigitacionFields().forEach(field => {
        normalizeDigitacionFieldInPlace(field);
        const key = field.dataset.digKey;
        if (!key) return;
        values[key] = key === 'cargo_actividad'
            ? normalizeDigitacionCargoCode(field.dataset.catalogCode || field.value)
            : field.value || '';
    });
    const existing = readDigitacionDraft();
    return {
        ...existing,
        proyecto: 'AFILEGA_FA_IMA_LA_V2',
        formato: existing.formato || 'digitacion_formato_afiliacion',
        updated_at: new Date().toISOString(),
        values,
        legacy_mdb: buildDigitacionLegacyMdbPayload(values),
    };
}

function normalizeDigitacionDraftForLegacy(data = {}) {
    const sourceValues = data.values || {};
    const values = { ...sourceValues };
    let changed = false;
    Object.entries(AFILEGA_MDB_FIELD_LIMITS || {}).forEach(([key, limit]) => {
        if (!limit || !Object.prototype.hasOwnProperty.call(values, key)) return;
        const value = String(values[key] ?? '');
        if (value.length <= limit) return;
        values[key] = value.slice(0, limit).trim();
        changed = true;
    });
    if (!changed) return data;
    return {
        ...data,
        values,
        validation: null,
    };
}

function fillDigitacionForm(data = {}) {
    data = normalizeDigitacionDraftForLegacy(data);
    setupDigitacionLocationSelects();
    applyDigitacionLegacyLimits();
    const values = data.values || {};
    getDigitacionFields().forEach(field => {
        const key = field.dataset.digKey;
        if (!key) return;
        if (field.classList.contains('js-municipality-select')) return;
        if (Object.prototype.hasOwnProperty.call(values, key)) {
            if (field.classList.contains('js-department-select')) {
                field.value = findDepartmentName(values[key]) || '';
            } else if (key === 'empleador_tipo_documento') {
                field.value = normalizeDigitacionDocumentTypeForUi(values[key]);
            } else if (key === 'tipo_afiliacion') {
                field.value = normalizeDigitacionClaseAfiliacion(values[key]);
            } else if (key === 'fecha_nacimiento') {
                field.value = formatDigitacionBirthDateInput(values[key]);
            } else if (key === 'cargo_actividad') {
                setDigitacionCargoFieldDisplay(field, values[key] || '');
            } else {
                field.value = normalizeDigitacionFieldDisplayValue(field, values[key] || '');
            }
            normalizeDigitacionFieldInPlace(field);
        }
    });
    const centroNombreField = getDigitacionField('sede_centro_trabajo_nombre');
    const sedeNombreField = getDigitacionField('sede_nombre');
    if (centroNombreField && !centroNombreField.value && sedeNombreField?.value) {
        centroNombreField.value = String(sedeNombreField.value || '').replace(DIGITACION_ALNUM_CLEAN_RE, '').slice(0, 60);
    }
    syncDigitacionCoverageDate(false);
    syncDigitacionActivityDependentFields('codigo_actividad_economica');
    syncDigitacionActivityDependentFields('sede_codigo_actividad');
    syncDigitacionSedeTarifa();
    syncDigitacionWorkerAge();
    renderDigitacionCentrosAdicionales();
    updateTrabajadorCentroOptions();
    renderDigitacionTrabajadores();
    updateDigitacionContractorMode(data, { clearWorkers: digitacionIsContratista({ ...(values || {}), source_entry_type: data.source_entry_type || '' }) });
    document.querySelectorAll('.js-department-select').forEach(select => {
        const target = document.getElementById(select.dataset.municipalityTarget || '');
        updateMunicipalitySelect(select, target?.dataset?.digKey ? values[target.dataset.digKey] : '');
    });
    updateDigitacionStatus(data.updated_at ? `Guardado ${formatDateTime(data.updated_at)}` : 'Borrador local');
    renderDigitacionValidationSummary(data.validation || null);
    updateDigitacionContext(data);
    const focused = document.activeElement?.classList?.contains('digitacion-field') ? document.activeElement : getDigitacionFields()[0];
    updateDigitacionEvidenceForField(focused);
}

function digitacionPrefillFromPayload(payload) {
    return payload?.analysis?.digitacion_prefill || null;
}

function applyDigitacionPrefillFromPayload(payload, options = {}) {
    const prefill = digitacionPrefillFromPayload(payload);
    const values = prefill?.values || {};
    if (!prefill || !Object.keys(values).length) return false;
    const existing = readDigitacionDraft();
    const sameCase = existing.source_case_id && existing.source_case_id === payload.id;
    const mergedValues = sameCase ? { ...values, ...(existing.values || {}) } : { ...values };
    const draft = {
        proyecto: 'AFILEGA_FA_IMA_LA_V2',
        formato: `digitacion_${prefill.form_target || prefill.entry_type || 'afiliacion'}`,
        source_case_id: payload.id || '',
        source_entry_type: prefill.entry_type || '',
        source_label: payload.label || '',
        prefill_sources: prefill.sources || {},
        updated_at: new Date().toISOString(),
        values: mergedValues,
    };
    writeDigitacionDraft(draft);
    fillDigitacionForm(draft);
    updateDigitacionStatus(`Prellenado OCR · ${prefill.entry_type || 'entrada'}`, 'ok');
    if (!options.silent) showToast('Digitación prellenada con OCR', 'ok');
    return true;
}

function emptyDigitacionDraftForCase(caseId = '', payload = null) {
    return {
        proyecto: 'AFILEGA_FA_IMA_LA_V2',
        formato: 'digitacion_formato_afiliacion',
        source_case_id: caseId || '',
        source_entry_type: payload?.entry_type || payload?.analysis?.digitacion_prefill?.entry_type || '',
        source_label: payload?.label || '',
        updated_at: new Date().toISOString(),
        values: {},
    };
}

function updateDigitacionContext(data = readDigitacionDraft()) {
    const el = document.getElementById('digitacionContext');
    if (!el) return;
    const values = data?.values || {};
    const resolved = activeCasePayload ? resolveCase(activeCasePayload) : {};
    const empresa = values.razon_social || data?.source_label || resolved.empresa || activeCasePayload?.label || '';
    const nit = values.nit || resolved.nit || '';
    const radicado = values.numero_radicacion || resolved.nroRadicacion || '';
    const contrato = values.numero_contrato || resolveContractNumber(activeCasePayload?.analysis || {}, activeCasePayload || {});
    const parts = [];
    if (empresa) parts.push(`<strong>${escapeHtml(empresa)}</strong>`);
    if (nit && nit !== 'n/d') parts.push(`ID/NIT ${escapeHtml(nit)}`);
    if (radicado) parts.push(`Radicación ${escapeHtml(radicado)}`);
    if (contrato) parts.push(`Contrato ${escapeHtml(contrato)}`);
    el.innerHTML = parts.length ? `Gestionando: ${parts.join(' · ')}` : 'Sin contrato seleccionado';
}

function updateDigitacionContractorMode(data = readDigitacionDraft(), options = {}) {
    const values = data?.values || data || {};
    const isContratista = digitacionIsContratista({ ...values, source_entry_type: data?.source_entry_type || '' });
    const tab = document.querySelector('[data-digitacion-tab="novedades"]');
    const panel = document.querySelector('[data-digitacion-panel="novedades"]');
    if (tab) {
        tab.hidden = isContratista;
        tab.disabled = isContratista;
    }
    if (panel && isContratista) panel.classList.remove('active');
    if (isContratista && options.clearWorkers) {
        DIGITACION_WORKER_KEYS.forEach(key => {
            const field = getDigitacionField(key);
            if (field && !field.readOnly) {
                field.value = '';
                if (key === 'cargo_actividad') delete field.dataset.catalogCode;
                setDigitacionFieldError(field, '');
            }
        });
        const hidden = getDigitacionField('trabajadores_adicionales');
        if (hidden) hidden.value = '';
        renderDigitacionTrabajadores();
    }
    if (isContratista && digitacionActiveTab === 'novedades') {
        digitacionActiveTab = 'afiliacion';
    }
}

async function loadDigitacionDraftFromBackend(caseId) {
    if (!caseId) return null;
    const response = await fetchWithRetry(caseApiUrl(caseId, '/digitacion'));
    const payload = await response.json();
    return payload?.digitacion || null;
}

async function openDigitacionForCase(caseId) {
    if (!caseId) return false;
    activeCaseId = caseId;
    const currentDraft = readDigitacionDraft();
    if (currentDraft.source_case_id && currentDraft.source_case_id !== caseId) {
        writeDigitacionDraft(emptyDigitacionDraftForCase(caseId));
    }
    if (!activeCasePayload || activeCasePayload.id !== caseId) await loadActiveCaseFull(caseId);

    let backendDraft = null;
    try {
        backendDraft = await loadDigitacionDraftFromBackend(caseId);
    } catch (error) {
        console.warn('digitacion backend draft:', error);
    }

    if (backendDraft && Object.keys(backendDraft.values || {}).length) {
        const draft = {
            ...backendDraft,
            source_case_id: backendDraft.source_case_id || caseId,
            source_label: backendDraft.source_label || activeCasePayload?.label || '',
        };
        writeDigitacionDraft(draft);
        switchView('digitacion');
        fillDigitacionForm(draft);
        updateDigitacionStatus(`Data capturada · ${formatDateTime(draft.updated_at)}`, draft.validation?.ok === false ? 'err' : 'ok');
        return true;
    }

    writeDigitacionDraft(emptyDigitacionDraftForCase(caseId, activeCasePayload));
    switchView('digitacion');
    if (applyDigitacionPrefillFromPayload(activeCasePayload || { id: caseId }, { silent: true })) {
        updateDigitacionStatus('Prellenado OCR del contrato seleccionado', 'ok');
        showToast('Data OCR cargada para digitación', 'ok');
        return true;
    }
    fillDigitacionForm(readDigitacionDraft());
    updateDigitacionStatus('Contrato sin data capturada todavía', 'warn');
    showToast('El contrato está abierto en digitación, pero no tiene data capturada todavía', 'warn');
    return false;
}

function getDigitacionFieldLabel(key = '') {
    const field = getDigitacionField(key);
    return field?.closest('.field-row')?.querySelector('.field-label')?.textContent?.trim() || key || 'Campo';
}

function renderDigitacionValidationSummary(validation) {
    const panel = document.getElementById('digitacionValidationPanel');
    if (!panel) return;
    const errors = Array.isArray(validation?.errors) ? validation.errors : [];
    const warnings = Array.isArray(validation?.warnings) ? validation.warnings : [];
    if (!validation || (!errors.length && !warnings.length)) {
        panel.classList.add('hidden');
        panel.innerHTML = '';
        return;
    }
    const rows = [
        ...errors.map(item => ({ ...item, kind: 'err', label: 'Error' })),
        ...warnings.map(item => ({ ...item, kind: 'warn', label: 'Alerta' })),
    ];
    panel.classList.remove('hidden');
    panel.innerHTML = `
        <div class="digitacion-validation-head">
            <div>
                <div class="digitacion-validation-title">Validación de reglas</div>
                <div class="digitacion-validation-sub">${escapeHtml(validation.source || 'Reglas AFILEGA')}</div>
            </div>
            <span class="status-pill ${validation.ok ? 'ok' : 'err'}">${validation.ok ? 'Correcto' : `${errors.length} error(es)`}</span>
        </div>
        <div class="digitacion-validation-list">
            ${rows.slice(0, 8).map(item => `
                <button class="digitacion-validation-item ${item.kind}" type="button" data-dig-error-key="${escapeHtml(item.key || '')}" data-dig-error-section="${escapeHtml(item.section || '')}">
                    <span class="digitacion-validation-badge">${escapeHtml(item.label)}</span>
                    <span class="digitacion-validation-copy"><strong>${escapeHtml(getDigitacionFieldLabel(item.key || ''))}</strong>${escapeHtml(item.message ? `: ${item.message}` : '')}</span>
                </button>
            `).join('')}
            ${rows.length > 8 ? `<div class="digitacion-validation-more">+${rows.length - 8} hallazgo(s) adicional(es)</div>` : ''}
        </div>
    `;
    panel.querySelectorAll('[data-dig-error-key]').forEach(btn => {
        btn.addEventListener('click', () => {
            const section = btn.dataset.digErrorSection;
            const key = btn.dataset.digErrorKey;
            if (section) switchDigitacionTab(section);
            if (key) setTimeout(() => getDigitacionField(key)?.focus(), 50);
        });
    });
}

function applyBackendDigitacionErrors(validation) {
    getDigitacionFields().forEach(field => setDigitacionFieldError(field, ''));
    renderDigitacionValidationSummary(validation);
    const errors = Array.isArray(validation?.errors) ? validation.errors : [];
    for (const item of errors) {
        const field = getDigitacionField(item.key || '');
        if (field) setDigitacionFieldError(field, item.message || 'Campo inválido para reglas AFILEGA.');
    }
    const first = errors.find(item => getDigitacionField(item.key || ''));
    if (first?.section) switchDigitacionTab(first.section);
    if (first?.key) setTimeout(() => getDigitacionField(first.key)?.focus(), 50);
}

function updateDigitacionStatus(text, kind = '') {
    const status = document.getElementById('digitacionSaveStatus');
    if (!status) return;
    status.textContent = text;
    status.classList.remove('ok', 'warn', 'err');
    if (kind) status.classList.add(kind);
}

function switchDigitacionTab(tab) {
    digitacionActiveTab = tab || 'afiliacion';
    const targetTab = document.querySelector(`[data-digitacion-tab="${digitacionActiveTab}"]`);
    if (targetTab?.hidden || targetTab?.disabled) digitacionActiveTab = 'afiliacion';
    document.querySelectorAll('[data-digitacion-tab]').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.digitacionTab === digitacionActiveTab);
    });
    document.querySelectorAll('[data-digitacion-panel]').forEach(panel => {
        panel.classList.toggle('active', panel.dataset.digitacionPanel === digitacionActiveTab);
    });
    const activeField = document.querySelector(`[data-digitacion-panel="${digitacionActiveTab}"] .digitacion-field`);
    if (activeField) updateDigitacionEvidenceForField(activeField);
}

async function saveDigitacionDraft(options = {}) {
    const mode = options.mode || 'active';
    const requireAll = Boolean(options.requireAll);
    const shouldValidateBeforeSave = options.validate === true || requireAll || mode === 'full';
    if (shouldValidateBeforeSave) {
        const validation = validateDigitacionForm(mode);
        if (!validation.ok) {
            showToast(`Corrige ${validation.errors.length} campo(s) antes de guardar`, 'err');
            return null;
        }
    }
    const data = collectDigitacionData();
    writeDigitacionDraft(data);
    const caseId = data.source_case_id || getDigitacionCaseId();
    if (!caseId) {
        updateDigitacionStatus(`Guardado local ${formatDateTime(data.updated_at)}`, 'warn');
        showToast('Borrador de digitación guardado localmente', 'warn');
        return data;
    }
    updateDigitacionStatus('Guardando en caso...', 'warn');
    try {
        const response = await fetchWithRetry(caseApiUrl(caseId, '/digitacion'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ...data, require_all: requireAll }),
        });
        const payload = await response.json();
        const saved = payload?.digitacion || data;
        writeDigitacionDraft(saved);
        if (saved.validation && !saved.validation.ok) {
            applyBackendDigitacionErrors(saved.validation);
            updateDigitacionStatus(`${saved.validation.errors.length} error(es) de reglas`, 'err');
            showToast('El backend guardó el borrador, pero encontró errores de reglas', 'err');
            return saved;
        }
        fillDigitacionForm(saved);
        updateDigitacionStatus(`Guardado en caso ${formatDateTime(saved.updated_at)}`, 'ok');
        showToast('Borrador de digitación guardado en el caso', 'ok');
        return saved;
    } catch (error) {
        updateDigitacionStatus(`Guardado local: ${formatDateTime(data.updated_at)}`, 'warn');
        showToast(`No pude guardar en backend; quedó local. ${error.message}`, 'warn');
        return data;
    }
}

async function validateDigitacionWithBackend(options = {}) {
    const mode = options.mode || 'active';
    const requireAll = Boolean(options.requireAll);
    const localValidation = validateDigitacionForm(mode);
    if (!localValidation.ok) {
        showToast(`Corrige ${localValidation.errors.length} campo(s) antes de validar reglas`, 'err');
        return null;
    }
    const data = collectDigitacionData();
    const caseId = data.source_case_id || getDigitacionCaseId();
    if (!caseId) {
        updateDigitacionStatus('Sin caso activo para validar reglas', 'err');
        showToast('Abre la digitación desde un contrato para validar reglas', 'err');
        return null;
    }
    updateDigitacionStatus('Validando reglas...', 'warn');
    try {
        const response = await fetchWithRetry(caseApiUrl(caseId, '/digitacion/validate-mdb'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ...data, require_all: requireAll }),
        });
        const payload = await response.json();
        const validation = payload?.validation || null;
        if (!validation) throw new Error('El backend no devolvió validación de reglas.');
        applyBackendDigitacionErrors(validation);
        if (!validation.ok) {
            updateDigitacionStatus(`${validation.errors.length} error(es) de reglas`, 'err');
            showToast('Validación de reglas con errores', 'err');
            return validation;
        }
        updateDigitacionStatus('Reglas correctas', 'ok');
        showToast('Validación de reglas correcta', 'ok');
        return validation;
    } catch (error) {
        updateDigitacionStatus('Error validando reglas', 'err');
        showToast(error.message || 'No pude validar reglas', 'err');
        return null;
    }
}

async function pollDigitacionWorkflow(caseId, button = null) {
    let latest = null;
    const terminal = new Set(['completed', 'stopped_prevalidacion', 'stopped_lote', 'stopped_importacion', 'stopped_sync_engine', 'stopped_prebuild', 'stopped_926', 'failed']);
    for (let index = 0; index < 180; index++) {
        await new Promise(resolve => setTimeout(resolve, 2000));
        const response = await fetchWithRetry(caseApiUrl(caseId));
        latest = await response.json();
        const wf = latest?.analysis?.workflow_run || {};
        const status = normalizeText(wf.status || latest.status || '');
        const step = wf.current_step || status || 'procesando';
        updateDigitacionStatus(`Workflow: ${step}`, status === 'completed' ? 'ok' : 'warn');
        if (button) button.textContent = status === 'completed' ? '926 generado' : `Procesando ${index + 1}`;
        if (terminal.has(status)) break;
    }
    return latest;
}

async function runDigitacionWorkflow() {
    const caseId = getDigitacionCaseId();
    if (!caseId) {
        showToast('No hay contrato activo para generar 926', 'err');
        return;
    }
    const btn = document.getElementById('digitacionRunBtn');
    const btnIdleLabel = 'Guardar + generar 926';
    if (btn) { btn.disabled = true; btn.textContent = 'Guardando...'; }
    try {
        const saved = await saveDigitacionDraft({ mode: 'full', requireAll: true });
        if (!saved) return;
        if (saved.validation && !saved.validation.ok) return;
        if (btn) btn.textContent = 'Enviando workflow...';
        updateDigitacionStatus('Reanalizando con digitación...', 'warn');
        const response = await fetchWithRetry(caseApiUrl(caseId, '/run-workflow'), { method: 'POST' });
        const launched = await response.json();
        activeCaseId = caseId;
        activeCasePayload = launched;
        const finalPayload = await pollDigitacionWorkflow(caseId, btn);
        if (finalPayload) activeCasePayload = finalPayload;
        const wf = finalPayload?.analysis?.workflow_run || {};
        const output926 = wf.output_926 || finalPayload?.analysis?.output_926 || {};
        const legacyOk = Boolean(output926?.legacy?.ok);
        if (normalizeText(wf.status) === 'completed' && legacyOk) {
            updateDigitacionStatus('Plano generado', 'ok');
            showToast('Plano generado con la digitación guardada', 'ok');
            loadBandeja().catch(() => {});
            return;
        }
        updateDigitacionStatus(wf.stop_reason || 'Workflow no completado', 'err');
        showToast(wf.stop_reason || 'El workflow no completó generación 926', 'err');
    } catch (error) {
        updateDigitacionStatus('Error generando 926', 'err');
        showToast(error.message || 'No pude generar 926 desde digitación', 'err');
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = btnIdleLabel; }
    }
}

function clearDigitacionDraft() {
    if (!confirm('¿Limpiar todos los campos de digitación?')) return;
    getDigitacionFields().forEach(field => { field.value = ''; });
    clearDigitacionCentroEditor();
    renderDigitacionCentrosAdicionales();
    renderDigitacionTrabajadores();
    updateTrabajadorCentroOptions();
    setupDigitacionLocationSelects();
    writeDigitacionDraft({});
    updateDigitacionStatus('Borrador local', 'warn');
    updateDigitacionEvidenceForField(null);
    showToast('Digitación limpiada', 'warn');
}

function exportDigitacionJson() {
    const validation = validateDigitacionForm('all');
    if (!validation.ok) {
        showToast(`Corrige ${validation.errors.length} campo(s) antes de exportar`, 'err');
        return;
    }
    const data = collectDigitacionData();
    const contract = normalizeText(data.values.numero_contrato || data.values.documento_afiliado || 'borrador').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'borrador';
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `digitacion-afilega-${contract}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    showToast('JSON de digitación generado', 'ok');
}

function initDigitacionView() {
    applyDigitacionLegacyLimits();
    populateDigitacionCatalogDatalists();
    let draft = readDigitacionDraft();
    if (activeCaseId && draft.source_case_id && draft.source_case_id !== activeCaseId) {
        draft = emptyDigitacionDraftForCase(activeCaseId, activeCasePayload);
        writeDigitacionDraft(draft);
    }
    const defaults = {
        subtipo_cotizante: AFILEGA_MDB_DEFAULT_SUBTIPO_COTIZANTE,
        novedad_estado: '1',
        novedad_autoliquidacion: 'N',
        novedad_origen: 'C',
        sede_transporte: 'N',
    };
    Object.entries(defaults).forEach(([key, value]) => {
        const field = getDigitacionField(key);
        if (field && !field.value) field.value = value;
    });
    setupDigitacionLocationSelects();
    initDigitacionCentrosTrabajo();
    initDigitacionTrabajadores();
    fillDigitacionForm(draft);
    markDigitacionRequiredFields();
    hydrateDigitacionDraftFromActiveCase();
    switchDigitacionTab(digitacionActiveTab);
}

async function hydrateDigitacionDraftFromActiveCase() {
    const caseId = getDigitacionCaseId();
    if (!caseId) return;
    try {
        const backendDraft = await loadDigitacionDraftFromBackend(caseId);
        if (!backendDraft || !Object.keys(backendDraft.values || {}).length) return;
        const localDraft = readDigitacionDraft();
        const sameCase = localDraft.source_case_id && localDraft.source_case_id === caseId;
        const localTime = sameCase ? Date.parse(localDraft.updated_at || '') : 0;
        const backendTime = Date.parse(backendDraft.updated_at || '') || 0;
        if (sameCase && localTime && localTime >= backendTime) return;
        writeDigitacionDraft(backendDraft);
        fillDigitacionForm(backendDraft);
        updateDigitacionStatus(`Borrador del caso · ${formatDateTime(backendDraft.updated_at)}`, backendDraft.validation?.ok === false ? 'err' : 'ok');
    } catch (error) {
        console.warn('hydrateDigitacionDraftFromActiveCase:', error);
    }
}

// ── BANDEJA ──────────────────────────────────────────────────
async function loadBandeja() {
    const wrap = document.getElementById('casesTableWrap');
    if (!wrap) return;
    wrap.innerHTML = '<div class="loading-msg">Cargando contratos...</div>';
    try {
        const r = await fetchWithRetry(operationApiUrl('/api/cases/production-summary'));
        const data = await r.json();
        allCases = Array.isArray(data.cases) ? data.cases : [];
        allCases.sort((a,b) => String(b.updated_at||'').localeCompare(String(a.updated_at||'')));
        renderMetrics(allCases);
        renderCasesTable(allCases, bandejaActiveTab);
        // Arrancar live polling si hay contratos activos
        const hasActive = allCases.some(c => {
            const s = normalizeText(resolveCase(c).status);
            return ['processing','queued'].includes(s);
        });
        if (hasActive) startBandejaLivePolling();
    } catch(e) {
        console.error('loadBandeja:', e);
        wrap.innerHTML = `<div class="error-msg">No pude cargar los contratos: ${escapeHtml(e.message)}</div>`;
    }
}

function renderMetrics(cases) {
    let aprobados = 0, noAprobados = 0;
    for (const c of cases) {
        const { status, finalStatus } = resolveCase(c);
        if (isApprovedCaseStatus(status, finalStatus)) aprobados++;
        else noAprobados++;
    }
    document.getElementById('metricAprobables').textContent = aprobados;
    document.getElementById('metricNoAprobados').textContent = noAprobados;
    document.getElementById('metricAprobablesSub').textContent = aprobados ? 'resultado satisfactorio' : '';
    document.getElementById('metricNoAprobadosSub').textContent = noAprobados ? 'pendientes por revisión' : '';
}

function filterCasesByTab(cases, tab) {
    if (tab === 'todos') return cases;
    if (tab === 'aprobados') return cases.filter(c => {
        const { status, finalStatus } = resolveCase(c);
        return isApprovedCaseStatus(status, finalStatus);
    });
    if (tab === 'no-aprobados') return cases.filter(c => {
        const { status, finalStatus } = resolveCase(c);
        return !isApprovedCaseStatus(status, finalStatus);
    });
    return cases;
}

// Mapa de paso backend → % progreso y descripción
const STEP_PROGRESS = {
    'clasificacion_documental':   { pct: 20, label: 'Clasificando documentos...' },
    'prevalidacion_documental':   { pct: 40, label: 'Validando documentos...' },
    'validacion_xlsx':            { pct: 55, label: 'Revisando trabajadores...' },
    'validacion_sedes':           { pct: 65, label: 'Verificando sedes...' },
    'validacion_aportes':         { pct: 75, label: 'Comprobando aportes...' },
    'validacion_camara':          { pct: 82, label: 'Comparando cámara de comercio...' },
    'validacion_representante':   { pct: 88, label: 'Verificando representante legal...' },
    'calcular_decision':          { pct: 93, label: 'Calculando decisión...' },
    'generar_926':                { pct: 97, label: 'Generando archivo 926...' },
};

let bandejaLiveInterval = null;

function startBandejaLivePolling() {
    if (bandejaLiveInterval) return;
    bandejaLiveInterval = setInterval(async () => {
        if (currentView !== 'bandeja') return;
        try {
            const r = await fetch(operationApiUrl('/api/cases/production-summary'));
            const data = await r.json();
            const cases = Array.isArray(data.cases) ? data.cases : [];

            // Detectar si algo cambió (nuevo estado terminal)
            let changed = false;
            for (const fresh of cases) {
                const prev = allCases.find(c => c.id === fresh.id);
                if (!prev) { changed = true; break; }
                const prevStatus = normalizeText(resolveCase(prev).status);
                const freshStatus = normalizeText(resolveCase(fresh).status);
                if (prevStatus !== freshStatus) { changed = true; break; }
            }

            const stillProcessing = cases.some(c => {
                const s = normalizeText(resolveCase(c).status);
                return ['processing','queued'].includes(s);
            });

            if (changed) {
                // Refrescar bandeja completa
                allCases = cases;
                allCases.sort((a,b) => String(b.updated_at||'').localeCompare(String(a.updated_at||'')));
                renderMetrics(allCases);
                renderCasesTable(allCases, bandejaActiveTab);
            } else {
                // Solo actualizar spinners en tarjetas procesando
                const processingCards = document.querySelectorAll('.case-card-processing');
                for (const card of processingCards) {
                    const caseId = card.dataset.defaultCase;
                    const fresh = cases.find(c => c.id === caseId);
                    if (!fresh) continue;
                    const liveEl = card.querySelector('.case-card-live-status');
                    const fillEl = card.querySelector('.case-card-progress-fill');
                    const stepInfo = STEP_PROGRESS[fresh.current_step || ''] || null;
                    if (fillEl && stepInfo) fillEl.style.width = `${stepInfo.pct}%`;
                    if (liveEl && stepInfo) liveEl.innerHTML = `<span class="spin-dot"></span>${escapeHtml(stepInfo.label)}`;
                }
            }

            if (!stillProcessing) stopBandejaLivePolling();
        } catch(e) { console.warn('livePolling:', e); }
    }, 3000);
}

function stopBandejaLivePolling() {
    if (bandejaLiveInterval) { clearInterval(bandejaLiveInterval); bandejaLiveInterval = null; }
}

function renderCasesTable(cases, tab = 'todos') {
    const wrap = document.getElementById('casesTableWrap');
    if (!wrap) return;
    const filtered = filterCasesByTab(cases, tab);
    if (!filtered.length) {
        wrap.innerHTML = '<div class="empty-state">No hay contratos en esta categoría</div>';
        return;
    }
    let hasProcessing = false;
    wrap.innerHTML = `<div class="case-cards">${filtered.map(item => {
        const { empresa, nit, fecha, status, finalStatus, has926, filename, nroAfiliacion } = resolveCase(item);
        const wfStatus = normalizeText(status);
        const isProcessing = ['processing','queued'].includes(wfStatus);
        if (isProcessing) hasProcessing = true;
        const cls = caseStatusClass(status, finalStatus);
        const label = casePillLabel(status, finalStatus);
        const id = item.id || '';
        const stepInfo = isProcessing ? (STEP_PROGRESS[item.current_step || ''] || { pct: 15, label: 'Iniciando...' }) : null;

        // Hora formateada
        const updatedAt = item.updated_at || '';
        const horaStr = updatedAt ? new Date(updatedAt).toLocaleTimeString('es-CO', { hour:'2-digit', minute:'2-digit' }) : '';
        const fechaHora = horaStr ? `${fecha} ${horaStr}` : fecha;

        return `
            <div class="case-card ${isProcessing ? 'case-card-processing' : ''}"
                data-default-case="${escapeHtml(id)}" tabindex="0" role="button"
                aria-label="Ver reporte de ${escapeHtml(empresa)}">
                <div class="case-card-main" style="flex:1;min-width:0">
                    ${nroAfiliacion ? `<div class="case-card-contract">Contrato ${escapeHtml(nroAfiliacion)}</div>` : ''}
                    <div class="case-card-empresa">${escapeHtml(empresa)}</div>
                    <div class="case-card-meta">NIT ${escapeHtml(nit)} · ${escapeHtml(fechaHora)}</div>
                    ${isProcessing ? `
                        <div class="case-card-live-status">
                            <span class="spin-dot"></span>
                            ${escapeHtml(stepInfo?.label || 'Procesando...')}
                        </div>
                        <div class="case-card-progress-bar">
                            <div class="case-card-progress-fill" style="width:${stepInfo?.pct || 10}%"></div>
                        </div>
                    ` : ''}
                </div>
                <div class="case-card-right">
                    <span class="pill pill-${cls}">${escapeHtml(label)}</span>
                    <span class="pill pill-neutral">${escapeHtml((item.operation_label || currentOperation().name))}</span>
                    <div class="case-card-actions" role="group">
                        ${readProfile() !== 'colmena' ? `<button class="table-action-link table-action-danger table-action-delete" data-action="eliminar" data-case="${escapeHtml(id)}" data-empresa="${escapeHtml(empresa)}" type="button">Eliminar</button>` : ''}
                    </div>
                </div>
            </div>
        `;
    }).join('')}</div>`;

    // Iniciar live polling si hay contratos procesando
    if (hasProcessing) startBandejaLivePolling();

    // Click handlers
    wrap.querySelectorAll('.case-card').forEach(card => {
        card.addEventListener('click', e => {
            const btn = e.target.closest('[data-action]');
            if (btn) {
                e.stopPropagation();
                handleCaseAction(btn.dataset.action, btn.dataset.case, btn.dataset.file);
            } else {
                const id = card.dataset.defaultCase;
                if (id) handleCaseAction('reporte', id);
            }
        });
        card.addEventListener('keydown', e => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                handleCaseAction('reporte', card.dataset.defaultCase);
            }
        });
    });
}

async function handleCaseAction(action, caseId, file) {
    if (!caseId) return;
    if (action === 'reporte') {
        activeCaseId = caseId;
        switchView('reporte');
        loadReporteForCase(caseId);
    } else if (action === 'digitacion-prefill') {
        await openDigitacionForCase(caseId);
    } else if (action === 'descargar926') {
        await download926(caseId, file);
    } else if (action === 'clasificacion') {
        activeCaseId = caseId;
        switchView('clasificacion');
        loadClassifForCase(caseId);
    } else if (action === 'descargar926') {
        const btn = document.querySelector(`[data-action="descargar926"][data-case="${caseId}"]`);
        const original = btn?.textContent || 'Descargar plano';
        if (btn) { btn.textContent = 'Descargando...'; btn.disabled = true; }
        try {
            await download926(caseId, file || btn?.dataset?.file || 'archivo_926.txt');
        } finally {
            if (btn) { btn.textContent = original; btn.disabled = false; }
        }
    } else if (action === 'recuperar') {
        activeCaseId = caseId;
        const btn = document.querySelector(`[data-action="recuperar"][data-case="${caseId}"]`);
        if (btn) { btn.textContent = 'Cargando...'; btn.disabled = true; }
        await loadActiveCaseFull(caseId);
        if (btn) { btn.textContent = 'Recuperar'; btn.disabled = false; }
        switchView('reporte');
        if (activeCasePayload) {
            const el = document.getElementById('reporteContent');
            const sel = document.getElementById('reporteCaseSelect');
            if (sel) sel.value = caseId;
            if (el) renderFormularioReporte(el, activeCasePayload);
        }
    } else if (action === 'eliminar') {
        const empresa = document.querySelector(`[data-action="eliminar"][data-case="${caseId}"]`)?.dataset?.empresa || caseId;
        if (!confirm(`¿Eliminar el contrato de ${empresa}?\n\nSe eliminarán todos los archivos adjuntos. No se puede deshacer.`)) return;
        try {
            const r = await fetch(caseApiUrl(caseId), { method: 'DELETE' });
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            const card = document.querySelector(`[data-default-case="${caseId}"]`);
            if (card) { card.style.opacity = '0'; card.style.transition = 'opacity 0.3s'; setTimeout(() => card.remove(), 300); }
            allCases = allCases.filter(c => c.id !== caseId);
            renderMetrics(allCases);
            showToast(`Contrato de ${empresa} eliminado`, 'ok');
        } catch(e) {
            showToast('No se pudo eliminar: ' + e.message, 'err');
        }
    }
}

async function loadActiveCaseFull(caseId) {
    try {
        const r = await fetchWithRetry(caseApiUrl(caseId));
        activeCasePayload = await r.json();
    } catch(e) {
        console.error('loadActiveCaseFull:', e);
    }
}

async function download926(caseId, filename) {
    if (!caseId) return;
    try {
        const r = await fetchWithRetry(case926Url(caseId));
        const blob = await r.blob();
        const disposition = r.headers.get('Content-Disposition') || '';
        const match = disposition.match(/filename="?([^"]+)"?/i);
        const resolvedFilename = filename || match?.[1] || 'archivo_926.txt';
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = resolvedFilename;
        document.body.appendChild(a); a.click(); a.remove();
        URL.revokeObjectURL(url);
        showToast('Plano descargado', 'ok');
    } catch(e) {
        console.error('download926:', e);
        showToast('No se pudo descargar el plano: ' + e.message, 'err');
    }
}

function resetFlujoView() {
    // Limpiar archivos seleccionados
    const zone = document.getElementById('uploadZone');
    const selected = document.getElementById('uploadSelected');
    const input = document.getElementById('packageFilesInput');
    const progressCard = document.getElementById('workflowProgressCard');
    const resultCard = document.getElementById('workflowResultCard');
    const progressSteps = document.getElementById('progressSteps');
    const progressMsg = document.getElementById('progressMsg');
    const statusPill = document.getElementById('workflowStatusPill');
    if (zone) zone.style.display = '';
    if (selected) selected.style.display = 'none';
    if (input) input.value = '';
    if (progressCard) progressCard.style.display = 'none';
    if (resultCard) resultCard.style.display = 'none';
    if (progressSteps) progressSteps.innerHTML = '';
    if (progressMsg) progressMsg.textContent = '';
    if (statusPill) { statusPill.className = 'status-pill'; statusPill.textContent = 'En curso'; }
    window.__uploadFiles = [];
    workflowLaunchInFlight = false;
    const radicacionField = document.getElementById('flowNumeroRadicacion');
    if (radicacionField?.dataset?.radUsed === '1') {
        ensureFlowNumeroRadicacion({ force: true });
    } else {
        ensureFlowNumeroRadicacion();
    }
}

function setupEntryTypeControls() {
    document.querySelectorAll('[data-entry-type]').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.entryType === uploadEntryType);
        btn.addEventListener('click', () => {
            uploadEntryType = btn.dataset.entryType || 'empresa';
            document.querySelectorAll('[data-entry-type]').forEach(item => {
                item.classList.toggle('active', item.dataset.entryType === uploadEntryType);
            });
        });
    });
}

function setupUploadZone() {
    const zone = document.getElementById('uploadZone');
    const input = document.getElementById('packageFilesInput');
    if (!zone || !input) return;

    zone.addEventListener('click', () => input.click());
    zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('drag-over'); });
    zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
    zone.addEventListener('drop', e => {
        e.preventDefault(); zone.classList.remove('drag-over');
        if (e.dataTransfer?.files?.length) handleFilesSelected(Array.from(e.dataTransfer.files));
    });
    input.addEventListener('change', () => {
        if (input.files?.length) handleFilesSelected(Array.from(input.files));
    });

    document.getElementById('clearFilesBtn')?.addEventListener('click', clearUpload);
    document.getElementById('runWorkflowBtn')?.addEventListener('click', runWorkflow);
    const today = todayIsoDate();
    const flowFechaRadicacion = document.getElementById('flowFechaRadicacion');
    const flowFechaInicioVigencia = document.getElementById('flowFechaInicioVigencia');
    const flowFechaRecibido = document.getElementById('flowFechaRecibidoImagine');
    if (flowFechaRadicacion) flowFechaRadicacion.max = today;
    if (flowFechaInicioVigencia) flowFechaInicioVigencia.min = today;
    if (flowFechaRecibido) {
        flowFechaRecibido.max = today;
        if (!flowFechaRecibido.value) flowFechaRecibido.value = today;
    }
    ensureFlowNumeroRadicacion();
    document.querySelectorAll('.radicacion-field').forEach(field => {
        field.addEventListener('input', () => {
            if (field.dataset.radKey === 'nit') {
                field.value = onlyDigits(field.value).slice(0, 15);
            }
            if (field.dataset.radKey === 'razon_social') {
                const cleaned = field.value.replace(DIGITACION_ALNUM_CLEAN_RE, '');
                const upper = cleaned.toUpperCase();
                if (field.value !== upper) field.value = upper;
            }
            if (field.dataset.radKey === 'fecha_radicacion' && flowFechaRecibido) {
                flowFechaRecibido.min = field.value || '';
            }
            if (['tipo_afiliacion', 'fecha_radicacion'].includes(field.dataset.radKey)) {
                syncRadicacionVigencia();
            }
            setDigitacionFieldError(field, '');
        });
        field.addEventListener('change', () => {
            if (['tipo_afiliacion', 'fecha_radicacion'].includes(field.dataset.radKey)) {
                syncRadicacionVigencia();
            }
            setDigitacionFieldError(field, '');
        });
    });
    syncRadicacionVigencia();
}

function handleFilesSelected(files) {
    const zone = document.getElementById('uploadZone');
    const selected = document.getElementById('uploadSelected');
    const list = document.getElementById('uploadFilesList');
    if (!zone || !selected || !list) return;
    zone.style.display = 'none';
    selected.style.display = '';
    list.innerHTML = files.map(f => {
        const ext = f.name.split('.').pop().toLowerCase();
        const isXlsx = ['xlsx','xls','xlsm'].includes(ext);
        const isPdf = ext === 'pdf';
        const size = f.size > 1024*1024
            ? `${(f.size/1024/1024).toFixed(1)} MB`
            : `${Math.round(f.size/1024)} KB`;
        return `
            <div class="upload-file-item">
                <span class="upload-file-type ${isXlsx?'xlsx':isPdf?'pdf':''}">${escapeHtml(ext.toUpperCase())}</span>
                <span class="upload-file-name">${escapeHtml(f.name)}</span>
                <span class="upload-file-size">${size}</span>
            </div>
        `;
    }).join('');
    window.__uploadFiles = files;
}

function clearUpload() {
    const zone = document.getElementById('uploadZone');
    const selected = document.getElementById('uploadSelected');
    const input = document.getElementById('packageFilesInput');
    if (zone) zone.style.display = '';
    if (selected) selected.style.display = 'none';
    if (input) input.value = '';
    window.__uploadFiles = [];
    document.getElementById('workflowProgressCard').style.display = 'none';
    document.getElementById('workflowResultCard').style.display = 'none';
}

function getRadicacionContractFields() {
    return Array.from(document.querySelectorAll('.radicacion-field'));
}

function collectRadicacionContractData() {
    const values = {
        tipo_tramite: 'afiliacion',
    };
    getRadicacionContractFields().forEach(field => {
        const key = field.dataset.radKey;
        if (!key) return;
        values[key] = String(field.value || '').trim();
    });
    const isTraslado = normalizeText(values.tipo_afiliacion || '').includes('traslado');
    if (isTraslado && values.fecha_radicacion) {
        values.fecha_inicio_vigencia = digitacionStartOfMonthAfterNext(values.fecha_radicacion);
        const vigenciaField = document.querySelector('.radicacion-field[data-rad-key="fecha_inicio_vigencia"]');
        if (vigenciaField) vigenciaField.value = values.fecha_inicio_vigencia;
    }
    if (values.fecha_radicacion) {
        values.fecha_inicio_cobertura = isTraslado && values.fecha_inicio_vigencia
            ? values.fecha_inicio_vigencia
            : digitacionDatePlusDays(values.fecha_radicacion, 1);
    }
    values.empleador_tipo_documento = normalizeDigitacionDocumentTypeForUi(values.empleador_tipo_documento || '') || '';
    values.tipo_afiliacion = normalizeDigitacionClaseAfiliacion(values.tipo_afiliacion || '') || '';
    values.nit = onlyDigits(values.nit || '');
    values.razon_social = String(values.razon_social || '').toUpperCase();
    return values;
}

function radicacionValidationMessage(field, rule) {
    return `En el formulario Radicación del contrato, campo ${field}: ${rule}`;
}

function validateRadicacionContractData(values = collectRadicacionContractData()) {
    const errors = [];
    const requiredKeys = [
        'numero_radicacion', 'tipo_afiliacion', 'fecha_radicacion', 'fecha_inicio_vigencia', 'fecha_recibido_imagine',
        'empleador_tipo_documento', 'nit', 'razon_social', 'sucursal',
    ];
    if (normalizeText(values.tipo_afiliacion || '').includes('traslado')) {
        requiredKeys.push('empresa_arl_anterior');
    }
    getRadicacionContractFields().forEach(field => setDigitacionFieldError(field, ''));
    for (const key of requiredKeys) {
        const field = document.querySelector(`.radicacion-field[data-rad-key="${key}"]`);
        if (!String(values[key] || '').trim()) {
            const message = radicacionValidationMessage(getDigitacionLabel(field), 'es obligatorio para radicar el contrato.');
            setDigitacionFieldError(field, message);
            errors.push({ key, message });
        }
    }
    if (values.nit && values.empleador_tipo_documento === 'NIT' && values.nit.length !== 9) {
        const field = document.querySelector('.radicacion-field[data-rad-key="nit"]');
        const message = radicacionValidationMessage('No. de identificación', 'debe tener 9 dígitos cuando el Tipo de Documento es NIT.');
        setDigitacionFieldError(field, message);
        errors.push({ key: 'nit', message });
    } else if (values.nit && values.empleador_tipo_documento === 'CC' && !(values.nit.length > 6 && values.nit.length < 11 && values.nit.length !== 9)) {
        const field = document.querySelector('.radicacion-field[data-rad-key="nit"]');
        const message = radicacionValidationMessage('No. de identificación', 'debe tener 7, 8 o 10 dígitos cuando el Tipo de Documento es CC.');
        setDigitacionFieldError(field, message);
        errors.push({ key: 'nit', message });
    } else if (values.nit && !/^\d{5,15}$/.test(values.nit)) {
        const field = document.querySelector('.radicacion-field[data-rad-key="nit"]');
        const message = radicacionValidationMessage('No. de identificación', 'debe ser numérico y tener entre 5 y 15 dígitos.');
        setDigitacionFieldError(field, message);
        errors.push({ key: 'nit', message });
    }
    if (values.razon_social && !DIGITACION_ALNUM_RE.test(values.razon_social)) {
        const field = document.querySelector('.radicacion-field[data-rad-key="razon_social"]');
        const message = radicacionValidationMessage('Razón social', 'debe ser alfanumérica y se guarda en mayúscula.');
        setDigitacionFieldError(field, message);
        errors.push({ key: 'razon_social', message });
    }
    for (const key of ['fecha_radicacion', 'fecha_inicio_vigencia', 'fecha_recibido_imagine']) {
        if (values[key] && !parseDigitacionDate(values[key])) {
            const field = document.querySelector(`.radicacion-field[data-rad-key="${key}"]`);
            const message = radicacionValidationMessage(getDigitacionLabel(field), 'debe ser una fecha válida.');
            setDigitacionFieldError(field, message);
            errors.push({ key, message });
        }
    }
    const today = todayIsoDate();
    if (values.fecha_radicacion && values.fecha_radicacion > today) {
        const field = document.querySelector('.radicacion-field[data-rad-key="fecha_radicacion"]');
        const message = radicacionValidationMessage('Fecha radicación Alfa', 'debe ser menor o igual a la fecha actual.');
        setDigitacionFieldError(field, message);
        errors.push({ key: 'fecha_radicacion', message });
    }
    if (values.fecha_recibido_imagine && values.fecha_radicacion && values.fecha_recibido_imagine < values.fecha_radicacion) {
        const field = document.querySelector('.radicacion-field[data-rad-key="fecha_recibido_imagine"]');
        const message = radicacionValidationMessage('Fecha recibido Imagine', 'debe ser mayor o igual al campo Fecha radicación Alfa.');
        setDigitacionFieldError(field, message);
        errors.push({ key: 'fecha_recibido_imagine', message });
    }
    if (values.fecha_recibido_imagine && values.fecha_recibido_imagine > today) {
        const field = document.querySelector('.radicacion-field[data-rad-key="fecha_recibido_imagine"]');
        const message = radicacionValidationMessage('Fecha recibido Imagine', 'debe ser menor o igual a la fecha actual.');
        setDigitacionFieldError(field, message);
        errors.push({ key: 'fecha_recibido_imagine', message });
    }
    if (normalizeText(values.tipo_afiliacion || '').includes('traslado') && values.fecha_radicacion && values.fecha_inicio_vigencia) {
        const expected = digitacionStartOfMonthAfterNext(values.fecha_radicacion);
        if (expected && values.fecha_inicio_vigencia !== expected) {
            const field = document.querySelector('.radicacion-field[data-rad-key="fecha_inicio_vigencia"]');
            const message = radicacionValidationMessage('Fecha inicio vigencia', `debe ser ${expected}, mes subsiguiente a la Fecha radicación Alfa.`);
            setDigitacionFieldError(field, message);
            errors.push({ key: 'fecha_inicio_vigencia', message });
        }
    }
    return { ok: errors.length === 0, errors };
}

async function runWorkflow() {
    const files = window.__uploadFiles || [];
    if (!files.length) return;
    const tester = readTester();
    if (!tester.email) { showToast('Por favor selecciona tu usuario antes de continuar.', 'warn'); return; }
    const radicacionValues = collectRadicacionContractData();
    const radicacionValidation = validateRadicacionContractData(radicacionValues);
    if (!radicacionValidation.ok) {
        showToast(`Corrige ${radicacionValidation.errors.length} campo(s) de radicación antes de continuar.`, 'err');
        radicacionValidation.errors[0]?.key && document.querySelector(`.radicacion-field[data-rad-key="${radicacionValidation.errors[0].key}"]`)?.focus();
        return;
    }

    const btn = document.getElementById('runWorkflowBtn');
    const progressCard = document.getElementById('workflowProgressCard');
    const progressSteps = document.getElementById('progressSteps');
    const progressMsg = document.getElementById('progressMsg');
    const statusPill = document.getElementById('workflowStatusPill');

    if (progressCard) progressCard.style.display = '';
    if (progressSteps) progressSteps.innerHTML = '';

    const steps = [
        { id: 'upload',   label: 'Cargando expediente...' },
        { id: 'classify', label: 'Clasificando documentos...' },
        { id: 'precheck', label: 'Ejecutando validación documental...' },
        { id: 'decision', label: 'Calculando decisión...' },
        { id: 'legado',   label: 'Generando plano...' },
    ];

    function renderStep(index, state) {
        const icons = { pending:'○', active:'⠋', done:'✓', error:'✗' };
        const s = steps[index];
        const existing = document.getElementById(`step-${s.id}`);
        const html = `
            <div class="progress-step ${state}" id="step-${s.id}">
                <span class="progress-step-icon">${icons[state]||'○'}</span>
                <span class="progress-step-label">${escapeHtml(s.label)}</span>
            </div>
        `;
        if (existing) { existing.outerHTML = html; }
        else if (progressSteps) { progressSteps.insertAdjacentHTML('beforeend', html); }
    }

    steps.forEach((_, i) => renderStep(i, 'pending'));

    // Deshabilitar solo durante el upload inicial (segundos)
    if (btn) { btn.disabled = true; btn.textContent = 'Enviando...'; }

    try {
        // Paso 1: subir archivos
        renderStep(0, 'active');
        const formData = new FormData();
        const label = radicacionValues.razon_social || deriveCaseLabel(files);
        formData.append('label', label);
        formData.append('operation', readOperation());
        formData.append('entry_type', uploadEntryType);
        formData.append('tester_email', tester.email);
        formData.append('tester_name', tester.name || tester.email);
        formData.append('radicacion_json', JSON.stringify(radicacionValues));
        for (const f of files) formData.append('files', f, f.name);

        const uploadRes = await fetchWithRetry(operationApiUrl('/api/cases'), {
            method: 'POST',
            body: formData,
        });
        const uploadData = await uploadRes.json();
        const caseId = uploadData.id || uploadData.case_id;
        if (!caseId) throw new Error('El backend no devolvió un ID de caso.');
        activeCaseId = caseId;
        activeCasePayload = {
            ...uploadData,
            id: caseId,
            label,
            entry_type: uploadEntryType,
        };
        writeDigitacionDraft({
            ...emptyDigitacionDraftForCase(caseId, activeCasePayload),
            values: { ...radicacionValues },
        });
        markFlowRadicacionUsed();
        renderStep(0, 'done');

        // Lanzar workflow (encolado automático)
        renderStep(1, 'active');
        if (statusPill) { statusPill.className = 'status-pill info'; statusPill.textContent = 'En cola...'; }

        const wfRes = await fetchWithRetry(caseApiUrl(caseId, '/run-workflow'), {
            method: 'POST',
        });
        if (!wfRes.ok) throw new Error(`HTTP ${wfRes.status}`);

        renderStep(1, 'done');
        renderStep(2, 'active');

        // ✅ Reactivar botón inmediatamente — el operador puede enviar más contratos
        if (btn) { btn.disabled = false; btn.textContent = 'Radicar y validar documentos'; }
        if (progressMsg) {
            progressMsg.innerHTML = `<span style="font-weight:600;color:var(--c-brand)">${escapeHtml(label)}</span> · En cola de procesamiento`;
        }
        if (statusPill) { statusPill.className = 'status-pill info'; statusPill.textContent = 'En cola'; }

        // Poll en background sin bloquear UI
        let done = false;
        let pollCount = 0;
        let spinnerFrame = 0;
        const spinnerChars = ['⠋','⠙','⠹','⠸','⠼','⠴','⠦','⠧','⠇','⠏'];
        const stepLabels = {
            'clasificacion_documental':   'Clasificando documentos...',
            'prevalidacion_documental':   'Validando documentos adjuntos...',
            'validacion_xlsx':            'Revisando trabajadores...',
            'validacion_sedes':           'Verificando sedes...',
            'validacion_aportes':         'Comprobando aportes...',
            'validacion_camara':          'Comparando cámara de comercio...',
            'validacion_representante':   'Verificando representante legal...',
            'calcular_decision':          'Calculando decisión final...',
            'generar_926':                'Generando archivo 926...',
        };

        while (!done && pollCount < 180) {
            await new Promise(r => setTimeout(r, 2000));
            pollCount++;
            try {
                const statusRes = await fetch(caseApiUrl(caseId));
                const statusData = await statusRes.json();
                const wfRun = statusData?.analysis?.workflow_run || {};
                const wfStatus = normalizeText(wfRun.status || statusData?.status || '');
                const currentStep = wfRun.current_step || '';
                const profile = statusData?.analysis?.xlsx_profile?.profile || {};
                const empresa = profile.empresa || statusData?.label || label;
                const nit = profile.nit || '';
                const stepDesc = stepLabels[currentStep] || (currentStep ? `${currentStep}...` : 'Procesando...');
                const spinner = spinnerChars[spinnerFrame % spinnerChars.length];
                spinnerFrame++;

                const activeStepEl = document.getElementById('step-precheck');
                if (activeStepEl && !['completed','stopped_prevalidacion','failed'].includes(wfStatus)) {
                    activeStepEl.querySelector('.progress-step-label').textContent = stepDesc;
                    activeStepEl.querySelector('.progress-step-icon').textContent = spinner;
                }

                if (progressMsg) {
                    const nitStr = nit ? ` · NIT: ${nit}` : '';
                    const empresaStr = empresa && empresa !== label ? empresa : label;
                    progressMsg.innerHTML = `<span style="font-weight:600;color:var(--c-text)">${escapeHtml(empresaStr)}</span>${escapeHtml(nitStr)}`;
                }

                if (['completed','stopped_prevalidacion','failed','analyzed'].includes(wfStatus)) {
                    done = true;
                    activeCasePayload = statusData;
                }
            } catch(pollErr) { console.warn('poll:', pollErr); }
        }

        // Resultado final
        const finalWfStatus = normalizeText(activeCasePayload?.analysis?.workflow_run?.status || '');
        renderStep(2, 'done');
        renderStep(3, 'done');
        renderStep(4, finalWfStatus === 'completed' ? 'done' : 'pending');

        if (statusPill) {
            statusPill.className = 'status-pill ' + (finalWfStatus === 'completed' ? 'ok' : finalWfStatus === 'stopped_prevalidacion' ? 'warn' : 'err');
            statusPill.textContent = finalWfStatus === 'completed' ? 'Completado' : finalWfStatus === 'stopped_prevalidacion' ? 'No pasó validación' : localizeStatus(finalWfStatus);
        }
        if (progressMsg) progressMsg.innerHTML = '';

        renderWorkflowResult(activeCasePayload);
        if (applyDigitacionPrefillFromPayload(activeCasePayload, { silent: true })) {
            showToast('OCR llevó datos a Digitación', 'ok');
        }
        document.getElementById('workflowResultCard').style.display = '';

        // Actualizar bandeja en background
        loadBandeja().catch(() => {});

    } catch(e) {
        console.error('runWorkflow:', e);
        renderStep(0, 'error');
        if (progressMsg) {
            progressMsg.innerHTML = `<span style="color:var(--c-err);font-weight:700">Error:</span> <span style="color:var(--c-err)">${escapeHtml(e.message)}</span>`;
        }
        if (statusPill) { statusPill.className = 'status-pill err'; statusPill.textContent = 'Error'; }
        showToast(e.message, 'err', 8000);
        if (btn) { btn.disabled = false; btn.textContent = 'Ejecutar prevalidación'; }
    }
}


function deriveCaseLabel(files) {
    const xlsx = files.find(f => /\.(xlsx|xls|xlsm)$/i.test(f.name));
    if (xlsx) return xlsx.name.replace(/\.[^.]+$/,'');
    return `afi-${Date.now()}`;
}

function renderWorkflowResult(payload) {
    const el = document.getElementById('workflowResultContent');
    if (!el || !payload) return;
    const a = payload.analysis || {};
    const wf = a.workflow_run || {};
    const profile = (a.xlsx_profile || {}).profile || {};
    const report = wf.executive_report_final || wf.executive_report_precheck || a.reporte_ejecutivo || {};
    const resumen = report.resumen_ejecutivo || {};
    const empresa = resumen.empresa || profile.empresa || payload.label || 'n/d';
    const nit = resumen.nit || profile.nit || 'n/d';
    const estado = resumen.estado || wf.status || payload.status || 'n/d';
    const trabajadores = resumen.numero_trabajadores ?? profile.numero_trabajadores ?? 'n/d';
    const sedes = resumen.numero_sedes ?? profile.numero_sedes ?? 'n/d';
    const nomina = profile.nomina_total ? formatCurrency(profile.nomina_total) : 'n/d';
    const decision = a.decision || {};
    const blockers = Array.isArray(decision.blockers) ? decision.blockers :
                     Array.isArray(report.bloqueantes) ? report.bloqueantes : [];
    const blockerRecords = getValidationBlockerRecords(payload);
    const acceptedExceptions = getAcceptedValidationExceptions(payload);
    const has926 = Boolean((wf.output_926||{}).legacy?.ok);
    const filename926 = (wf.output_926||{}).legacy?.filename || 'archivo_core.txt';
    const nroAfiliacion = resolveContractNumber(a, payload);
    const decisionStatus = normalizeText(decision.recommended_status || '');
    const hasActiveBlockers = blockers.length > 0 || blockerRecords.length > 0;
    const approved = isCaseManuallyApproved(payload);
    const isAprobable = isCaseAprobableAfterManualExceptions(payload, estado, decisionStatus);
    const isNoAprobado = !isAprobable && normalizeText(wf.status||'') === 'stopped_prevalidacion';

    const stateClass = approved ? 'ok' : (isAprobable ? 'warn' : 'err');
    const stateLabel = approved ? 'Aprobado' : (isAprobable ? 'Aprobable' : 'No aprobado');
    const stateIcon = approved ? '✓' : (isAprobable ? '!' : '✗');

    el.innerHTML = `
        <div class="result-header">
            <div class="result-status-icon">${stateIcon}</div>
            <div>
                <div style="margin-bottom:6px"><span class="pill pill-${stateClass}">${escapeHtml(stateLabel)}</span></div>
                <div class="result-empresa">${escapeHtml(empresa)}</div>
                <div class="result-nit">NIT: ${escapeHtml(nit)}${nroAfiliacion ? ` · Contrato ${escapeHtml(nroAfiliacion)}` : ''}</div>
            </div>
            <div style="margin-left:auto">
                ${isAprobable && !approved ? `<button class="btn-success" id="approveCaseBtn" type="button">Aprobar contrato</button>` : ''}
            </div>
        </div>
        <div class="result-body">
            <div class="result-kv-grid">
                <div class="result-kv"><div class="result-kv-label">Trabajadores</div><div class="result-kv-val">${escapeHtml(String(trabajadores))}</div></div>
                <div class="result-kv"><div class="result-kv-label">Sedes</div><div class="result-kv-val">${escapeHtml(String(sedes))}</div></div>
                <div class="result-kv"><div class="result-kv-label">Nómina total</div><div class="result-kv-val">${escapeHtml(nomina)}</div></div>
                <div class="result-kv"><div class="result-kv-label">Estado</div><div class="result-kv-val">${escapeHtml(estado)}</div></div>
                <div class="result-kv"><div class="result-kv-label">Entrada</div><div class="result-kv-val">${escapeHtml(entryTypeLabel)}</div></div>
            </div>
            ${digitacionPrefillCount ? `
                <div class="result-blockers" style="border-left-color:var(--c-info)">
                    <div class="result-blockers-title">Digitación OCR</div>
                    <div class="result-blocker-item">
                        <span>✓</span>
                        <span>${digitacionPrefillCount} campo(s) prellenados desde ${digitacionPrefill.documents_processed || 0} documento(s) OCR.</span>
                    </div>
                </div>
            ` : ''}
            ${blockers.length ? `
                <div class="result-blockers">
                    <div class="result-blockers-title">Bloqueantes detectados (${blockers.length})</div>
                    ${(blockerRecords.length ? blockerRecords : blockers.map((b, i) => ({ message: blockerText(b), code: 'VALIDATION_ALERT', fingerprint: '', index: i }))).map((b, i) => `
                        <div class="result-blocker-item">
                            <span>✗</span>
                            <span style="flex:1">${escapeHtml(b.message)}</span>
                            ${validationExceptionButtonHtml(b, i)}
                        </div>
                    `).join('')}
                </div>
            ` : ''}
            ${acceptedExceptions.length ? `
                <div class="result-blockers" style="border-left-color:var(--c-ok)">
                    <div class="result-blockers-title">Aceptados manualmente (${acceptedExceptions.length})</div>
                    ${acceptedExceptions.map(item => `
                        <div class="result-blocker-item" style="background:var(--c-ok-bg);color:var(--c-ok)">
                            <span>✓</span>
                            <span>${escapeHtml(item.message || '')}<br><small>${escapeHtml(item.accepted_reason || item.reason || '')}</small></span>
                        </div>
                    `).join('')}
                </div>
            ` : ''}
            <div class="result-actions">
                <button class="btn-secondary" data-action="reporte" data-case="${escapeHtml(payload.id||'')}" type="button">Ver reporte ejecutivo</button>
                <button class="btn-secondary" data-action="clasificacion" data-case="${escapeHtml(payload.id||'')}" type="button">Ver documentos</button>
                ${digitacionPrefillCount ? `<button class="btn-secondary" data-action="digitacion-prefill" data-case="${escapeHtml(payload.id||'')}" type="button">Abrir digitación prellenada</button>` : ''}
                ${has926 ? `<button class="btn-primary" data-action="descargar926" data-case="${escapeHtml(payload.id||'')}" data-file="${escapeHtml(filename926)}" type="button">Descargar plano</button>` : ''}
            </div>
        </div>
    `;
    el.querySelectorAll('[data-action]').forEach(btn => {
        btn.addEventListener('click', () => handleCaseAction(btn.dataset.action, btn.dataset.case, btn.dataset.file));
    });
    el.querySelector('#approveCaseBtn')?.addEventListener('click', () => approveCaseManually(payload.id || activeCaseId, el));
    el.querySelectorAll('.validation-exception-btn').forEach(btn => {
        btn.addEventListener('click', async () => {
            const records = blockerRecords.length ? blockerRecords : blockers.map((b, i) => ({ message: blockerText(b), code: 'VALIDATION_ALERT', fingerprint: '', index: i }));
            const record = records[Number(btn.dataset.blockerIdx || 0)];
            setValidationExceptionButtonsLoading(el, btn, true);
            try {
                const saved = await acceptValidationException(payload.id || activeCaseId, record);
                if (!saved) setValidationExceptionButtonsLoading(el, btn, false);
            }
            catch(e) {
                showToast('No pude guardar la excepción: ' + e.message, 'err', 6000);
                setValidationExceptionButtonsLoading(el, btn, false);
            }
        });
    });
}

// ── CLASIFICACIÓN ────────────────────────────────────────────
async function populateCaseSelect(selectId, onChangeFn) {
    const sel = document.getElementById(selectId);
    if (!sel) return;
    try {
        const r = await fetchWithRetry(operationApiUrl('/api/cases/production-summary'));
        const data = await r.json();
        const cases = Array.isArray(data.cases) ? data.cases : [];
        sel.innerHTML = '<option value="">Selecciona un contrato...</option>' +
            cases.map(c => {
                const { empresa, nit } = resolveCase(c);
                return `<option value="${escapeHtml(c.id||'')}">${escapeHtml(empresa)} · ${escapeHtml(nit)}</option>`;
            }).join('');
        if (activeCaseId) sel.value = activeCaseId;
        sel.addEventListener('change', () => onChangeFn(sel.value));
        if (activeCaseId && sel.value) onChangeFn(sel.value);
    } catch(e) {
        console.error('populateCaseSelect:', e);
    }
}

async function loadClassifForCase(caseId) {
    if (!caseId) return;
    const listEl = document.getElementById('classifDocList');
    if (listEl) listEl.innerHTML = '<div class="loading-msg">Cargando documentos...</div>';
    try {
        let r = await fetchWithRetry(caseApiUrl(caseId));
        let payload = await r.json();
        // Si el caso nunca se analizo (recien cargado), el OCR/clasificacion de
        // documentos todavia no corrio -se dispara aqui, durante la revision, para
        // que "Aprobar contrato" no tenga que hacerlo por primera vez (y quede caro).
        const hasDocs = Array.isArray(payload?.files) && payload.files.some(f => !/\.(xlsx|xlsm|xls)$/i.test(f.filename || ''));
        const alreadyAnalyzed = !!(payload?.analysis && Array.isArray(payload.analysis.documents) && payload.analysis.documents.length > 0);
        if (hasDocs && !alreadyAnalyzed) {
            if (listEl) listEl.innerHTML = '<div class="loading-msg">Analizando documentos (OCR)...</div>';
            r = await fetchWithRetry(caseApiUrl(caseId, '/analyze'), { method: 'POST' });
            payload = await r.json();
        }
        activeCaseId = caseId;
        activeCasePayload = payload;

        // Mostrar nombre del contrato como contexto fijo
        const { empresa, nit, approved } = resolveCase(payload);
        const labelEl = document.getElementById('classifCaseLabel');
        if (labelEl) {
            labelEl.style.display = '';
            labelEl.innerHTML = `Contrato · ${escapeHtml(empresa)}${nit !== 'n/d' ? ` · ${escapeHtml(nit)}` : ''}${approved ? ' · APROBADO' : ''}`;
        }

        renderClassifBlockers(payload);
        renderClassifDocList(payload);
    } catch(e) {
        if (listEl) listEl.innerHTML = `<div class="error-msg">${escapeHtml(e.message)}</div>`;
    }
}

function ensureClassifBlockersPanel() {
    let panel = document.getElementById('classifBlockersPanel');
    if (panel) return panel;
    const previewBody = document.getElementById('classifPreviewBody');
    if (!previewBody?.parentElement) return null;
    panel = document.createElement('div');
    panel.id = 'classifBlockersPanel';
    previewBody.parentElement.insertBefore(panel, previewBody.nextSibling);
    return panel;
}

function renderClassifBlockers(payload) {
    const panel = ensureClassifBlockersPanel();
    if (!panel) return;
    const previewCard = document.getElementById('classifPreviewCard');
    const a = payload?.analysis || {};
    const decision = a.decision || {};
    const report = (a.workflow_run || {}).executive_report_final || (a.workflow_run || {}).executive_report_precheck || a.reporte_ejecutivo || {};
    const blockers = Array.isArray(decision.blockers) ? decision.blockers :
                     Array.isArray(report.bloqueantes) ? report.bloqueantes : [];
    const blockerRecords = getValidationBlockerRecords(payload);
    const records = blockerRecords.length ? blockerRecords : blockers.map((b, i) => ({ message: blockerText(b), code: 'VALIDATION_ALERT', fingerprint: '', index: i }));
    const acceptedExceptions = getAcceptedValidationExceptions(payload);
    const isApproved = isCaseManuallyApproved(payload);
    if (!records.length && !acceptedExceptions.length) {
        panel.querySelectorAll('.classif-blockers-box').forEach(el => el.remove());
        if (!panel.querySelector('#classifComisionWorkspace')) {
            panel.innerHTML = '';
            panel.style.display = 'none';
            previewCard?.classList.remove('has-classif-blockers');
        }
        return;
    }
    panel.querySelectorAll('.classif-blockers-box').forEach(el => el.remove());
    panel.style.display = '';
    previewCard?.classList.add('has-classif-blockers');
    const blockersHtml = `
        ${records.length ? `
            <div class="classif-blockers-box">
                <div class="classif-blockers-title">Bloqueantes para validar (${records.length})</div>
                ${records.map((b, i) => `
                    <div class="classif-blocker-item">
                        <span class="report-blocker-icon">✗</span>
                        <span class="classif-blocker-text">${escapeHtml(b.message || blockerText(b))}</span>
                        ${isApproved ? '' : validationExceptionButtonHtml(b, i, 'margin-left:auto')}
                    </div>
                `).join('')}
            </div>
        ` : ''}
        ${acceptedExceptions.length ? `
            <div class="classif-blockers-box accepted">
                <div class="classif-blockers-title ok">Aceptados manualmente (${acceptedExceptions.length})</div>
                ${acceptedExceptions.slice(0, 5).map(item => `
                    <div class="classif-blocker-item accepted">
                        <span>✓</span>
                        <span class="classif-blocker-text">${escapeHtml(item.message || '')}</span>
                    </div>
                `).join('')}
            </div>
        ` : ''}
    `;
    const workspace = panel.querySelector('#classifComisionWorkspace');
    if (workspace) workspace.insertAdjacentHTML('afterend', blockersHtml);
    else panel.insertAdjacentHTML('afterbegin', blockersHtml);
    panel.querySelectorAll('.validation-exception-btn').forEach(btn => {
        btn.addEventListener('click', async (event) => {
            event.stopPropagation();
            const latestPayload = activeCasePayload?.id === payload.id ? activeCasePayload : payload;
            const latestRecords = getValidationBlockerRecords(latestPayload);
            const availableRecords = latestRecords.length ? latestRecords : records;
            const record = availableRecords[Number(btn.dataset.blockerIdx || 0)] || records[Number(btn.dataset.blockerIdx || 0)];
            setValidationExceptionButtonsLoading(panel, btn, true);
            try {
                const saved = await acceptValidationException(latestPayload.id || payload.id || activeCaseId, record);
                if (!saved) setValidationExceptionButtonsLoading(panel, btn, false);
            }
            catch(e) {
                showToast('No pude guardar la excepción: ' + e.message, 'err', 6000);
                setValidationExceptionButtonsLoading(panel, btn, false);
            }
        });
    });
}

function renderComisionManualPanelHtml() {
    return `
        <div class="reclassify-panel comision-manual-panel">
            <div class="comision-panel-title">Corrección manual de comisiones</div>
            <div id="comisionRows"></div>
            <div class="comision-actions-grid">
                <button class="btn-secondary" id="addComisionRow" type="button">+ Agregar intermediario</button>
                <button class="btn-primary" id="saveComisiones" type="button">Guardar comisiones</button>
            </div>
            <span id="comisionStatus"></span>
        </div>
    `;
}

function renderTipoNegocioPanelHtml() {
    return `
        <div class="reclassify-panel tipo-negocio-panel">
            <div class="comision-panel-title">Corrección manual de tipo de negocio</div>
            <div class="comision-actions-grid">
                <select id="tipoNegocioSelect" class="field-select">
                    <option value="">Selecciona el tipo de negocio...</option>
                    <option value="Micro">Micro</option>
                    <option value="Pequeña">Pequeña</option>
                    <option value="Mediana">Mediana</option>
                    <option value="Grande">Grande</option>
                </select>
                <button class="btn-primary" id="saveTipoNegocio" type="button">Guardar tipo de negocio</button>
            </div>
            <span id="tipoNegocioStatus"></span>
        </div>
    `;
}

async function saveManualComisiones(caseId, filename, rows) {
    if (!caseId || !filename) return null;
    const r = await fetchWithRetry(caseApiUrl(caseId, '/manual-review'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            kind: 'comisiones',
            filename,
            verdict: 'no',
            comisiones: rows,
        }),
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json().catch(() => null);
}

async function deleteManualComision(caseId, filename, rows, index, onDone = null) {
    const currentRows = Array.isArray(rows) ? rows : [];
    const row = currentRows[index];
    if (!caseId || !filename || !row) return;
    const doc = row.cedula || row.vendedor_documento || row.documento || '';
    const label = doc ? ` del documento ${doc}` : '';
    if (!confirm(`¿Eliminar esta comisión${label}?`)) return;
    const nextRows = currentRows.filter((_, i) => i !== index);
    await saveManualComisiones(caseId, filename, nextRows);
    showToast('Comisión eliminada.', 'ok');
    await refreshClassifAfterComisionChange(caseId, filename);
    if (typeof onDone === 'function') onDone(nextRows);
}

function bindComisionManualPanel(item, payload, root = document) {
    const comisionRows = root.querySelector('#comisionRows');
    const addBtn = root.querySelector('#addComisionRow');
    const saveBtn = root.querySelector('#saveComisiones');
    const saveTipoNegocioBtn = root.querySelector('#saveTipoNegocio');
    const comisionStatus = root.querySelector('#comisionStatus');
    const tipoNegocioSelect = root.querySelector('#tipoNegocioSelect');
    const tipoNegocioStatus = root.querySelector('#tipoNegocioStatus');
    
    if (!comisionRows || !saveBtn || !saveTipoNegocioBtn) return;

    const matchIntermediarios = payload?.analysis?.validacion_resumen?.matches?.entrega_documentos_intermediario?.todos_intermediarios;
    const reviewIntermediarios = payload?.analysis?.manual_review?.entrega_documentos_intermediario?.todos_intermediarios;
    const existingComisiones = Array.isArray(matchIntermediarios)
        ? matchIntermediarios
        : (Array.isArray(reviewIntermediarios) ? reviewIntermediarios : []);
    const rawTipoNegocio = payload?.analysis?.xlsx_profile?.profile?.tipo_negocio_detectado || '';

    function collectComisionRows() {
        return [...comisionRows.querySelectorAll('.comision-row')].map(row => ({
            codigo: String(row.querySelector('.comision-codigo')?.value || '').replace(/^0+/, '') || '',
            cedula: row.querySelector('.comision-cedula')?.value?.trim() || '',
            porcentaje: row.querySelector('.comision-pct')?.value?.trim() || '100',
        })).filter(r => r.cedula);
    }

    function renderComisionRow(data = {}, existingIndex = -1) {
        const div = document.createElement('div');
        div.className = 'comision-row';
        const codigo = String(data.codigo || data.codigo_intermediario || '').replace(/^0+/, '') || '';
        const cedula = data.cedula || data.vendedor_documento || data.documento || '';
        const porcentaje = data.porcentaje || data.porcentaje_venta || '100';
        const isValidCodigo = ['1', '3'].includes(codigo);
        const invalidCodigoOption = codigo && !isValidCodigo
            ? `<option value="${escapeHtml(codigo)}" selected>${escapeHtml(codigo.padStart(2, '0'))} - No válido, selecciona 01 o 03</option>`
            : '';
        div.innerHTML = `
            <select class="field-select comision-codigo">
                <option value="" ${!codigo ? 'selected' : ''}>Seleccionar código</option>
                ${invalidCodigoOption}
                <option value="1" ${isValidCodigo && codigo==='1'?'selected':''}>01 - Consultor</option>
                <option value="3" ${isValidCodigo && codigo==='3'?'selected':''}>03 - Corredor</option>
            </select>
            <input class="field-input comision-cedula" placeholder="Nro. documento" value="${escapeHtml(cedula)}">
            <input class="field-input comision-pct" placeholder="%" value="${escapeHtml(porcentaje)}">
            <button class="btn-icon comision-remove-row" type="button">✕</button>
        `;
        div.querySelector('.comision-remove-row')?.addEventListener('click', async () => {
            if (existingIndex < 0) {
                div.remove();
                return;
            }
            try {
                const visibleRows = [...comisionRows.querySelectorAll('.comision-row')];
                const currentIndex = visibleRows.indexOf(div);
                await deleteManualComision(payload.id, item.file, collectComisionRows(), currentIndex, (nextRows) => {
                    div.remove();
                    if (!nextRows.length && comisionRows && !comisionRows.querySelector('.comision-row')) {
                        renderComisionRow();
                    }
                    if (comisionStatus) {
                        comisionStatus.style.color = 'var(--c-ok)';
                        comisionStatus.textContent = '✓ Comisión eliminada';
                    }
                });
            } catch(e) {
                if (comisionStatus) {
                    comisionStatus.style.color = 'var(--c-err)';
                    comisionStatus.textContent = 'Error: ' + e.message;
                }
            }
        });
        comisionRows.appendChild(div);
    }

    if (existingComisiones.length) existingComisiones.forEach((c, idx) => renderComisionRow(c, idx));
    else renderComisionRow();

    if (tipoNegocioSelect && rawTipoNegocio) {
        const opciones = [...tipoNegocioSelect.options].map(o => o.value);
        const match = opciones.find(
            o => o.toLowerCase().trim() === rawTipoNegocio.toLowerCase().trim()
        );
        if (match) tipoNegocioSelect.value = match;
    }

    addBtn?.addEventListener('click', () => renderComisionRow());

    saveTipoNegocioBtn.addEventListener('click', async () => {
        const tipoNegocio = tipoNegocioSelect?.value?.trim() || '';
        if (!tipoNegocio) {
            if (tipoNegocioStatus) {
                tipoNegocioStatus.style.color = 'var(--c-err)';
                tipoNegocioStatus.textContent = 'Selecciona un tipo de negocio antes de guardar.';
            }
            return;
        }
        try {
            saveTipoNegocioBtn.disabled = true;
            saveTipoNegocioBtn.textContent = 'Guardando...';
            const r = await fetchWithRetry(caseApiUrl(payload.id, '/manual-review'), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    kind: 'tipo_negocio_detectado',
                    filename: item.file || '',
                    verdict: 'si',
                    tipo_negocio_detectado: tipoNegocio,
                }),
            });
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            if (tipoNegocioStatus) {
                tipoNegocioStatus.style.color = 'var(--c-ok)';
                tipoNegocioStatus.textContent = `✓ Tipo de negocio guardado: ${tipoNegocio}`;
            }
            if (payload?.analysis?.xlsx_profile?.profile) {
                payload.analysis.xlsx_profile.profile.tipo_negocio_detectado = tipoNegocio;
            }
        } catch (e) {
            if (tipoNegocioStatus) {
                tipoNegocioStatus.style.color = 'var(--c-err)';
                tipoNegocioStatus.textContent = 'Error: ' + (e.message || e);
            }
        } finally {
            saveTipoNegocioBtn.disabled = false;
            saveTipoNegocioBtn.textContent = 'Guardar tipo de negocio';
        }
    });

    saveBtn.addEventListener('click', async () => {
        const rows = collectComisionRows();

        if (!rows.length) {
            if (comisionStatus) comisionStatus.textContent = 'Agrega al menos un intermediario.';
            return;
        }
        const invalidCodigoRows = rows.filter(r => !['1', '3'].includes(r.codigo));
        if (invalidCodigoRows.length) {
            if (comisionStatus) {
                comisionStatus.style.color = 'var(--c-err)';
                comisionStatus.textContent = 'Selecciona un código válido 01 o 03 para cada comisión.';
            }
            return;
        }

        try {
            saveBtn.disabled = true;
            saveBtn.textContent = 'Guardando...';
            const responseData = await saveManualComisiones(payload.id, item.file, rows);
            const invalidAsesores = responseData?.manual_review?.comisiones_validation?.[item.file]?.invalid || [];
            if (comisionStatus) {
                if (invalidAsesores.length) {
                    comisionStatus.style.color = 'var(--c-warn)';
                    comisionStatus.textContent = `Comisiones guardadas. ${invalidAsesores.length} documento(s) no existen en asesores Colmena; se generó bloqueante aceptable.`;
                } else {
                    comisionStatus.style.color = 'var(--c-ok)';
                    comisionStatus.textContent = `✓ ${rows.length} intermediario(s) guardados y validados`;
                }
            }
            if (invalidAsesores.length) {
                showToast('Hay comisiones con documentos no registrados en asesores Colmena. Revisa el bloqueante.', 'warn', 6000);
            }
            await refreshClassifAfterComisionChange(payload.id, item.file);
        } catch(e) {
            if (comisionStatus) {
                comisionStatus.style.color = 'var(--c-err)';
                comisionStatus.textContent = 'Error: ' + e.message;
            }
        } finally {
            saveBtn.disabled = false;
            saveBtn.textContent = 'Guardar comisiones';
        }
    });
}

function renderClassifComisionWorkspace(item, payload) {
    const panel = ensureClassifBlockersPanel();
    const previewCard = document.getElementById('classifPreviewCard');
    if (!panel || !previewCard) return;
    let workspace = document.getElementById('classifComisionWorkspace');
    const isComision = canonicalDocumentType(item?.type) === 'comision';
    if (!isComision) {
        workspace?.remove();
        if (!panel.textContent.trim()) {
            panel.style.display = 'none';
            previewCard.classList.remove('has-classif-blockers');
        }
        return;
    }
    if (!workspace) {
        workspace = document.createElement('div');
        workspace.id = 'classifComisionWorkspace';
        panel.insertBefore(workspace, panel.firstChild);
    }
    panel.style.display = '';
    previewCard.classList.add('has-classif-blockers');
    workspace.innerHTML = `
        <div class="classif-comision-grid">
            ${renderComisionManualPanelHtml()}
            ${renderTipoNegocioPanelHtml()}
        </div>
    `;
    bindComisionManualPanel(item, payload, workspace);
}

function buildDocItems(payload) {
    if (!payload) return [];
    const items = [];
    let sourceIndex = 0;
    const a = payload.analysis || {};
    const manualReview = a.manual_review || {};
    const docMeta = buildDocMetaMap(payload);
    const received = Array.isArray(a.checklist?.received_summary) ? a.checklist.received_summary : [];
    const workspace = a.document_workspace || {};
    const workspaceOrder = workspace.manual_order === true && Array.isArray(workspace.order) ? workspace.order : [];
    const seen = new Set();

    // XLSX al final, segun prioridad documental.
    const xlsxFiles = collectXlsxFiles(payload);
    for (const f of xlsxFiles) {
        if (!f || seen.has(f) || isRemoved(f)) continue;
        seen.add(f);
        items.push({ file: f, kind: 'xlsx', type: 'xlsx', label: 'Archivo base XLSX', displayName: f, _sourceIndex: sourceIndex++ });
    }
    // PDFs desde received_summary (ya clasificados)
    for (const group of received) {
        for (const f of (group.files||[])) {
            if (!f || seen.has(f) || isRemoved(f)) continue;
            seen.add(f);
            const meta = docMeta[f] || {};
            const reviewEntry = getManualReviewEntry(manualReview, 'document', f);
            const effectiveType = canonicalDocumentType(reviewEntry?.verdict === 'no' && reviewEntry.expected_type
                ? reviewEntry.expected_type
                : (meta.document_type || group.label || 'pdf'));
            const isCorrected = reviewEntry?.verdict === 'no';
            const legacyCode = isCorrected ? null : (meta.legacy_code ?? null);
            items.push({ file: f, kind: 'document', type: effectiveType, label: getReviewTypeLabelWithCode(effectiveType, legacyCode), displayName: meta.display_name || f, corrected: isCorrected, codeSource: meta.code_source || '', sedeKey: reviewEntry?.sede_key || meta.sede_key || '', _sourceIndex: sourceIndex++ });
        }
    }
    // Agregar documentos del análisis que no aparecieron en received_summary
    for (const [f, meta] of Object.entries(docMeta)) {
        if (!f || seen.has(f) || isRemoved(f)) continue;
        seen.add(f);
        const reviewEntry = getManualReviewEntry(manualReview, 'document', f);
        const effectiveType = canonicalDocumentType(reviewEntry?.verdict === 'no' && reviewEntry.expected_type
            ? reviewEntry.expected_type
            : (meta.document_type || 'pdf'));
        items.push({ file: f, kind: 'document', type: effectiveType, label: getReviewTypeLabel(effectiveType), displayName: meta.display_name || f, corrected: reviewEntry?.verdict === 'no', sedeKey: reviewEntry?.sede_key || meta.sede_key || '', _sourceIndex: sourceIndex++ });
    }
    // Agregar archivos físicos del caso que no aparecieron en ningún análisis
    const physicalFiles = (payload.files || []).map(f => f.filename || f.file || '').filter(Boolean);
    for (const f of physicalFiles) {
        if (!f || seen.has(f) || isRemoved(f)) continue;
        const lower = f.toLowerCase();
        if (lower.endsWith('.xlsx') || lower.endsWith('.xls') || lower.endsWith('.xlsm')) continue;
        seen.add(f);
        items.push({ file: f, kind: 'document', type: 'pdf', label: f.replace(/\.[^.]+$/, ''), displayName: f, corrected: false, _sourceIndex: sourceIndex++ });
    }
    return applyWorkspaceDocumentOrder(sortDocItemsByDisplayPriority(items), workspaceOrder);
}

function collectXlsxFiles(payload) {
    const a = payload?.analysis || {};
    const f = a.xlsx_profile?.filename || a.xlsx_filename;
    const files = Array.isArray(a.xlsx_files) ? [...a.xlsx_files] : [];
    if (f && !files.includes(f)) files.unshift(f);
    // También buscar en payload.files (archivos físicos del caso)
    if (!files.length && Array.isArray(payload?.files)) {
        for (const pf of payload.files) {
            const name = pf.filename || pf.original_filename || pf.name || '';
            if (/\.(xlsx|xlsm|xls)$/i.test(name) && !files.includes(name)) {
                files.push(name);
            }
        }
    }
    return files;
}

function buildSedeOptions(payload) {
    const a = payload?.analysis || {};
    const xlsx = a.xlsx_profile || {};
    const options = [];
    const seen = new Set();
    const add = (name) => {
        const key = String(name || '').trim();
        if (!key || seen.has(key)) return;
        seen.add(key);
        options.push({
            key,
            label: key.replace(/\s*-\s*Trabajadores\s*$/i, ''),
        });
    };

    Object.keys(xlsx.worker_sheet_counts || {}).forEach(add);
    for (const record of (xlsx.records || [])) add(record?._sheet);

    if (!options.length) {
        const profile = xlsx.profile || {};
        const formFields = xlsx.form_fields || {};
        const rawCount = profile.numero_sedes || formFields.b_numero_sedes || formFields.a_numero_sedes;
        const count = Number.parseInt(String(rawCount || '').replace(/\D/g, ''), 10);
        if (Number.isFinite(count) && count > 0) {
            for (let i = 1; i <= count; i += 1) add(`Sede ${String(i).padStart(2, '0')} - Trabajadores`);
        }
    }
    return options;
}

function manualDocumentReviewEntry(payload, filename) {
    const manualDocs = payload?.analysis?.manual_review?.documents || {};
    const entry = manualDocs[filename];
    return entry && typeof entry === 'object' ? entry : {};
}

function documentSedeKey(payload, docOrItem) {
    const filename = docOrItem?.filename || docOrItem?.file || '';
    return String(docOrItem?.sede_key || manualDocumentReviewEntry(payload, filename).sede_key || '').trim();
}

function groupSedeDocumentsByAssignment(payload, sedeNames = []) {
    const a = payload?.analysis || {};
    const manualDocs = a.manual_review?.documents || {};
    const docs = (a.documents || []).filter(d => String(d.document_type || '').startsWith('anexo_sedes'));
    const groups = {};
    const unassignedByOriginal = {};

    docs.forEach(doc => {
        const assigned = String(doc.sede_key || manualDocs[doc.filename]?.sede_key || '').trim();
        if (assigned) {
            if (!groups[assigned]) groups[assigned] = [];
            groups[assigned].push(doc);
            return;
        }
        const prefix = String(doc.filename || '').replace(/__p\d+\.pdf$/i, '');
        if (!unassignedByOriginal[prefix]) unassignedByOriginal[prefix] = [];
        unassignedByOriginal[prefix].push(doc);
    });

    Object.values(unassignedByOriginal).forEach((docsGroup, index) => {
        const sedeName = sedeNames[index];
        if (!sedeName) return;
        if (!groups[sedeName]) groups[sedeName] = [];
        groups[sedeName].push(...docsGroup);
    });
    return groups;
}

function buildDocMetaMap(payload) {
    const map = {};
    const a = payload?.analysis || {};
    const docs = a.documents || a.document_list || [];
    for (const d of docs) {
        if (d?.filename) map[d.filename] = d;
    }
    return map;
}

function getManualReviewEntry(manualReview, kind, file) {
    if (!manualReview || kind === 'xlsx') return null;
    // Formato nuevo: manual_review.documents es un dict por filename
    if (manualReview.documents && typeof manualReview.documents === 'object') {
        const entry = manualReview.documents[file];
        if (entry) return { file, expected_type: entry.expected_type, verdict: entry.verdict, sede_key: entry.sede_key || '' };
    }
    // Compatibilidad con revisiones guardadas en versiones anteriores.
    return (Array.isArray(manualReview.reviews) ? manualReview.reviews : []).find(r => r.file === file) || null;
}

function renderClassifDocList(payload, sortBy = 'default', sortDir = 1) {
    const el = document.getElementById('classifDocList');
    const preview = document.getElementById('classifPreviewBody');
    if (!el) return;
    const isApproved = isCaseManuallyApproved(payload);
    let items = buildDocItems(payload);
    if (!items.length) {
        el.innerHTML = '<div class="empty-state">No hay documentos en este contrato</div>';
        return;
    }

    // Header con conteo y botones de ordenamiento
    const headerEl = el.previousElementSibling;
    if (headerEl && headerEl.classList.contains('classif-doc-header')) {
        headerEl.remove();
    }
    const header = document.createElement('div');
    header.className = 'classif-doc-header';
    header.style.cssText = 'padding:6px 8px 2px;font-size:11px;color:var(--c-text-2);border-bottom:1px solid var(--c-border);margin-bottom:2px';
    header.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
            <span>${items.length} documentos</span>
            <button class="classif-sort-btn" id="btnBackToCaseInfo" type="button">Volver a información</button>
        </div>
        <div style="display:flex;gap:4px;flex-wrap:wrap;align-items:center">
            <span style="font-size:10px;opacity:0.6;margin-right:2px">Orden:</span>
            <span class="classif-sort-btn active" style="cursor:default">Prioridad documental</span>
            ${isApproved ? '<span class="classif-readonly-pill">Aprobado · solo lectura</span>' : ''}
            <button class="classif-sort-btn" id="btnFullAnalyze" type="button" style="margin-left:auto;color:var(--c-warn)">Análisis completo</button>
            <button class="classif-sort-btn" id="btnGalleryMode" type="button" style="color:var(--c-blue)">🖼 Galería</button>
        </div>
    `;
    el.parentElement?.insertBefore(header, el);

    header.querySelector('#btnFullAnalyze')?.addEventListener('click', async () => {
        const btn = header.querySelector('#btnFullAnalyze');
        if (btn) {
            btn.disabled = true;
            btn.textContent = 'Analizando...';
        }
        await runFullCaseAnalyzeFromClassif(payload.id || activeCaseId);
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Análisis completo';
        }
    });

    // Listener galería
    header.querySelector('#btnGalleryMode')?.addEventListener('click', () => {
        console.log(payload);
        openGallery(items, payload, 0);
    });
    header.querySelector('#btnBackToCaseInfo')?.addEventListener('click', () => handleCaseAction('reporte', payload.id || activeCaseId));

    el.innerHTML = items.map((item, i) => {
        const isRag = item.codeSource === 'rag_classification';
        const canDuplicate = item.kind !== 'xlsx' && canonicalDocumentType(item.type) === 'entrega_documentos';
        const sedeLabel = canonicalDocumentType(item.type) === 'anexo_sedes' && item.sedeKey
            ? (buildSedeOptions(payload).find(s => s.key === item.sedeKey)?.label || item.sedeKey)
            : '';
        return `
        <div class="doc-item" data-index="${i}" data-file="${escapeHtml(item.file)}">
            <span class="doc-item-order">
                <input class="doc-order-input" data-file="${escapeHtml(item.file)}" type="number" min="1" max="${items.length}" value="${i + 1}" title="${isApproved ? 'Contrato aprobado: orden bloqueado' : 'Cambiar orden'}" aria-label="Orden del documento" ${isApproved ? 'disabled' : ''}>
            </span>
            <span class="doc-item-name" title="${escapeHtml(item.displayName||item.file)}">${escapeHtml(item.label)}</span>
            ${isRag ? '<span class="doc-item-corrected" style="background:var(--c-info-bg);color:var(--c-blue)" title="Clasificado por RAG">🧠</span>' : ''}
            ${item.requiresValidation ? '<span class="doc-item-corrected" style="background:var(--c-warn-bg);color:var(--c-warn)" title="Requiere validar tipificación">validar</span>' : ''}
            ${item.corrected ? '<span class="doc-item-corrected">corregido</span>' : ''}
            ${sedeLabel ? `<span class="doc-item-corrected" title="Sede asignada">${escapeHtml(sedeLabel)}</span>` : ''}
            ${item.kind !== 'xlsx' && !isApproved ? `
            <span class="doc-item-actions">
                ${canDuplicate ? `<button class="doc-action-btn doc-duplicate-btn" data-file="${escapeHtml(item.file)}" title="Duplicar imagen" aria-label="Duplicar imagen" type="button">⧉</button>` : ''}
                <button class="doc-action-btn doc-delete-btn" data-file="${escapeHtml(item.file)}" title="Eliminar imagen" aria-label="Eliminar imagen" type="button">✕</button>
            </span>` : ''}
        </div>
    `}).join('');
    el.querySelectorAll('.doc-item').forEach(el => {
        el.addEventListener('click', async (e) => {
            if (e.target.classList.contains('doc-order-input')) return;
            if (e.target.classList.contains('doc-action-btn')) return; // manejar por separado
            el.closest('.doc-list')?.querySelectorAll('.doc-item').forEach(d => d.classList.remove('active'));
            el.classList.add('active');
            const idx = parseInt(el.dataset.index);
            const item = items[idx];
            if (!item) return;
            if (preview) {
                preview.innerHTML = '<div class="loading-msg">Cargando documento...</div>';
                await renderDocPreview(preview, payload.id, item);
            }
            renderClassifActions(item, payload);
        });
    });

    // Botón Eliminar
    el.querySelectorAll('.doc-delete-btn').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.stopPropagation();
            const filename = btn.dataset.file;
            if (!filename || !payload?.id) return;
            if (!confirm(`¿Eliminar "${filename}"?\n\nEste archivo se eliminará permanentemente del expediente.`)) return;
            try {
                const r = await fetchWithRetry(caseApiUrl(payload.id, `/files/${encodeURIComponent(filename)}`), { method: 'DELETE' });
                if (r.ok) {
                    showToast(`Archivo eliminado: ${filename}`, 'ok');
                    if (preview) preview.innerHTML = '<div class="empty-state">Selecciona un documento</div>';
                    const actions = document.getElementById('classifPreviewActions');
                    if (actions) actions.innerHTML = '';
                    await loadClassifForCase(payload.id);
                } else {
                    showToast('No se pudo eliminar el archivo', 'err');
                }
            } catch(e) {
                showToast('Error al eliminar: ' + e.message, 'err');
            }
        });
    });

    // Botón Duplicar
    el.querySelectorAll('.doc-duplicate-btn').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.stopPropagation();
            const filename = btn.dataset.file;
            if (!filename || !payload?.id) return;
            try {
                const r = await fetchWithRetry(caseApiUrl(payload.id, `/files/${encodeURIComponent(filename)}/duplicate`), { method: 'POST' });
                if (r.ok) {
                    const data = await r.json();
                    showToast(`Duplicado creado: ${data.filename || filename}`, 'ok');
                    await loadClassifForCase(payload.id);
                } else {
                    showToast('No se pudo duplicar el archivo', 'err');
                }
            } catch(e) {
                showToast('Error al duplicar: ' + e.message, 'err');
            }
        });
    });

    // Orden manual por número. El orden por prioridad queda como base cuando no hay ajuste guardado.
    el.querySelectorAll('.doc-order-input').forEach(input => {
        input.addEventListener('change', async () => {
            const file = input.dataset.file;
            const currentIdx = items.findIndex(it => it.file === file);
            if (currentIdx < 0 || !payload?.id) return;
            const requested = Number.parseInt(input.value, 10);
            const requestedPosition = Number.isFinite(requested) ? requested : currentIdx + 1;
            const targetIdx = requestedPosition < 1 ? 0 : (requestedPosition > items.length ? items.length - 1 : requestedPosition - 1);
            input.value = String(requestedPosition > items.length ? items.length : targetIdx + 1);
            if (currentIdx === targetIdx) return;

            const newItems = [...items];
            if (requestedPosition < 1) {
                const [moved] = newItems.splice(currentIdx, 1);
                newItems.unshift(moved);
            } else if (requestedPosition > items.length) {
                const [moved] = newItems.splice(currentIdx, 1);
                newItems.push(moved);
            } else {
                const [moved] = newItems.splice(currentIdx, 1);
                newItems.splice(targetIdx, 0, moved);
            }
            const currentOrder = items.map(it => it.file);
            const newOrder = newItems.map(it => it.file);
            setClassifDocListBusy(true, 'Guardando orden...');
            try {
                const response = await fetchWithRetry(caseApiUrl(payload.id, '/document-workspace'), {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        action: 'set_position',
                        filename: file,
                        target_position: requestedPosition,
                        order: currentOrder,
                    }),
                });
                const data = await response.json().catch(() => null);
                const updatedCase = data?.case || payload;
                payload.analysis = payload.analysis || {};
                payload.analysis.document_workspace = payload.analysis.document_workspace || {};
                payload.analysis.document_workspace.order = data?.document_workspace?.order || newOrder;
                payload.analysis.document_workspace.manual_order = true;
                activeCasePayload = updatedCase;
                renderClassifDocList(updatedCase, sortBy, sortDir);
            } catch(e) {
                console.warn('Error reordenando:', e);
                input.value = String(currentIdx + 1);
                showToast('No se pudo guardar el orden del documento', 'err');
            } finally {
                setClassifDocListBusy(false);
            }
        });
    });
    applyClassifDocListBusyState();

}

function navigateClassifDocument(dir) {
    if (currentView !== 'clasificacion') return false;
    const list = document.getElementById('classifDocList');
    if (!list || list.classList.contains('is-busy')) return false;
    const rows = Array.from(list.querySelectorAll('.doc-item'));
    if (!rows.length) return false;
    const activeIndex = rows.findIndex(row => row.classList.contains('active'));
    const currentIndex = activeIndex >= 0 ? activeIndex : (dir > 0 ? -1 : rows.length);
    const nextIndex = Math.max(0, Math.min(rows.length - 1, currentIndex + dir));
    if (nextIndex === activeIndex) return false;
    rows[nextIndex].scrollIntoView({ block: 'nearest' });
    rows[nextIndex].click();
    return true;
}

function handleClassifDocumentKeyboardNav(e) {
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
    if (e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;
    if (document.getElementById('galleryOverlay')?.style.display === 'flex') return;
    const target = e.target;
    if (target?.closest?.('input, textarea, select, button, [contenteditable="true"]')) return;
    if (navigateClassifDocument(e.key === 'ArrowRight' ? 1 : -1)) e.preventDefault();
}

function removeDocumentFromPayload(payload, filename) {
    if (!payload || !filename) return payload;
    payload.files = (payload.files || []).filter(item => (item.filename || item.file || '') !== filename);
    const analysis = payload.analysis || {};
    ['documents', 'document_list'].forEach(key => {
        if (Array.isArray(analysis[key])) analysis[key] = analysis[key].filter(item => (item.filename || '') !== filename);
    });
    const checklist = analysis.checklist || {};
    (checklist.received_summary || []).forEach(group => {
        group.files = (group.files || []).filter(item => item !== filename);
        group.count = group.files.length;
    });
    const workspace = analysis.document_workspace || {};
    workspace.order = (workspace.order || []).filter(item => item !== filename);
    workspace.removed_files = (workspace.removed_files || []).filter(item => item !== filename);
    const manual = analysis.manual_review || {};
    if (manual.documents) delete manual.documents[filename];
    if (manual.comisiones) delete manual.comisiones[filename];
    if (Array.isArray(manual.reviews)) {
        manual.reviews = manual.reviews.filter(item => (item.file || item.filename || '') !== filename);
    }
    payload.analysis = analysis;
    return payload;
}

async function renderDocPreview(container, caseId, item) {
    if (!caseId || !item.file) { container.innerHTML = '<div class="empty-state">Sin vista previa</div>'; return; }
    const url = documentViewerUrl(caseId, item.file, true);
    const lower = item.file.toLowerCase();
    if (lower.endsWith('.pdf')) {
        container.innerHTML = `<div class="doc-frame"><iframe src="${escapeHtml(url)}" title="${escapeHtml(item.displayName||item.file)}"></iframe></div>`;
    } else if (/\.(png|jpg|jpeg|webp|bmp|tif|tiff)$/i.test(lower)) {
        container.innerHTML = `<div class="doc-frame" style="padding:12px"><img src="${escapeHtml(url)}" alt="${escapeHtml(item.displayName||item.file)}" style="max-width:100%"></div>`;
    } else if (item.kind === 'xlsx') {
        const profile = activeCasePayload?.analysis?.xlsx_profile?.profile || {};
        container.innerHTML = `
            <div style="padding:16px">
                <div class="result-kv-grid">
                    <div class="result-kv"><div class="result-kv-label">Empresa</div><div class="result-kv-val">${escapeHtml(profile.empresa||'n/d')}</div></div>
                    <div class="result-kv"><div class="result-kv-label">NIT</div><div class="result-kv-val">${escapeHtml(profile.nit||'n/d')}</div></div>
                    <div class="result-kv"><div class="result-kv-label">Trabajadores</div><div class="result-kv-val">${escapeHtml(String(profile.numero_trabajadores??'n/d'))}</div></div>
                    <div class="result-kv"><div class="result-kv-label">Sedes</div><div class="result-kv-val">${escapeHtml(String(profile.numero_sedes??'n/d'))}</div></div>
                    <div class="result-kv"><div class="result-kv-label">Nómina</div><div class="result-kv-val">${escapeHtml(formatCurrency(profile.nomina_total)||'n/d')}</div></div>
                </div>
                <a class="btn-secondary" href="${escapeHtml(caseFileUrl(caseId, item.file))}" download="${escapeHtml(item.displayName||item.file)}" style="display:inline-flex;margin-top:12px">Descargar XLSX</a>
            </div>
        `;
    } else {
        container.innerHTML = `<div class="empty-state"><a class="btn-secondary" href="${escapeHtml(url)}" target="_blank">Abrir archivo</a></div>`;
    }
}

function renderClassifActions(item, payload) {
    const el = document.getElementById('classifPreviewActions');
    if (!el) return;
    if (item.kind === 'xlsx') {
        el.innerHTML = '';
        renderClassifComisionWorkspace(null, payload);
        return;
    }
    const isApproved = isCaseManuallyApproved(payload);

    const currentLabel = item.effectiveTypeLabel || item.label || item.type || 'Sin clasificar';
    const isCorrected = item.corrected;
    const sedeOptions = buildSedeOptions(payload);
    const currentSedeKey = item.sedeKey || documentSedeKey(payload, item);
    const isAnexoSedes = canonicalDocumentType(item.type) === 'anexo_sedes';

    if (isApproved) {
        el.innerHTML = `
            <div class="reclassify-panel">
                <div class="reclassify-current">
                    <span class="reclassify-label">Clasificación actual:</span>
                    <span class="reclassify-value ${isCorrected ? 'corrected' : ''}">${escapeHtml(currentLabel)}${isCorrected ? ' · corregido manualmente' : ''}</span>
                </div>
                ${isAnexoSedes && currentSedeKey ? `<div class="reclassify-current">
                    <span class="reclassify-label">Sede asignada:</span>
                    <span class="reclassify-value">${escapeHtml(sedeOptions.find(s => s.key === currentSedeKey)?.label || currentSedeKey)}</span>
                </div>` : ''}
                <div class="reclassify-status" style="color:var(--c-ok)">Contrato aprobado · edición documental bloqueada</div>
            </div>
        `;
        renderClassifComisionWorkspace(null, payload);
        return;
    }

    el.innerHTML = `
        <div class="reclassify-panel">
            <div class="reclassify-current">
                <span class="reclassify-label">Clasificación actual:</span>
                <span class="reclassify-value ${isCorrected ? 'corrected' : ''}">${escapeHtml(currentLabel)}${isCorrected ? ' · corregido manualmente' : ''}</span>
            </div>
            <div class="reclassify-form">
                <select class="field-select" id="reclassifySelect" style="flex:1;min-width:160px">
                    <option value="">— Selecciona nuevo tipo —</option>
                    ${[...REVIEW_TYPE_OPTIONS]
                        .sort(([, a], [, b]) => a.localeCompare(b, 'es'))
                        .map(([v,l]) => `<option value="${v}" ${v===item.type?'selected':''}>${escapeHtml(l)}</option>`)
                        .join('')}
                </select>
                <select class="field-select" id="anexoSedeSelect" style="flex:1;min-width:180px;${isAnexoSedes ? '' : 'display:none'}">
                    <option value="">— Asignar sede —</option>
                    ${sedeOptions.map(s => `<option value="${escapeHtml(s.key)}" ${s.key === currentSedeKey ? 'selected' : ''}>${escapeHtml(s.label)}</option>`).join('')}
                </select>
                <button class="btn-warn" id="reclassifyBtn" type="button">Reclasificar</button>
            </div>
            <div class="reclassify-status" id="reclassifyStatus"></div>
        </div>
    `;
    renderClassifComisionWorkspace(item, payload);

    document.getElementById('reclassifyBtn')?.addEventListener('click', async () => {
        const sel = document.getElementById('reclassifySelect');
        const newType = sel?.value;
        if (!newType) { document.getElementById('reclassifyStatus').textContent = 'Selecciona un tipo primero.'; return; }
        if (!payload?.id) return;
        const btn = document.getElementById('reclassifyBtn');
        const status = document.getElementById('reclassifyStatus');
        if (btn) { btn.disabled = true; btn.textContent = 'Guardando...'; }
        if (status) { status.textContent = ''; status.style.color = ''; }
        setClassifDocListBusy(true, 'Reclasificando documento...');
        try {
            const r = await fetchWithRetry(caseApiUrl(payload.id, '/manual-review'), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    kind: item.kind || 'document',
                    filename: item.file,
                    file: item.file,
                    expected_type: newType, 
                    verdict: 'no',
                    sede_key: document.getElementById('anexoSedeSelect')?.value || item.sedeKey || ''
                }),
            });
            if (!r.ok) {
                let errDetail = `HTTP ${r.status}`;
                try { const ed = await r.json(); errDetail = ed.detail || ed.message || errDetail; } catch {}
                throw new Error(errDetail);
            }

            // Leer respuesta para ver si RAG aprendió
            let ragMensaje = '';
            let respData = null;
            try {
                respData = await r.json();
                ragMensaje = respData?.rag_mensaje || '';
            } catch {}

            const newLabel = getReviewTypeLabelWithCode(newType, null);

            // Actualizar el item en memoria
            item.type = newType;
            item.label = newLabel;
            item.corrected = true;
            payload.analysis = payload.analysis || {};
            if (respData?.manual_review) {
                payload.analysis.manual_review = respData.manual_review;
            } else {
                payload.analysis.manual_review = payload.analysis.manual_review || {};
                payload.analysis.manual_review.documents = payload.analysis.manual_review.documents || {};
                payload.analysis.manual_review.documents[item.file] = {
                    expected_type: newType,
                    verdict: 'no',
                    updated_at: new Date().toISOString(),
                };
            }
            if (activeCasePayload?.id === payload.id) activeCasePayload = payload;

            // Actualizar el elemento en la lista sin recargar todo
            const activeDocItem = document.querySelector('.doc-item.active');
            if (activeDocItem) {
                const nameEl = activeDocItem.querySelector('.doc-item-name');
                if (nameEl) nameEl.textContent = newLabel;
            }

            // Mostrar confirmación + mensaje RAG
            if (status) {
                status.style.color = 'var(--c-ok)';
                status.innerHTML = `✓ Reclasificado como "${escapeHtml(newLabel)}"` +
                    (ragMensaje ? `<div style="margin-top:6px;padding:8px 10px;background:var(--c-info-bg);border-radius:6px;font-size:11px;color:var(--c-blue);border-left:3px solid var(--c-blue)">🧠 ${escapeHtml(ragMensaje)}</div>` : '');
            }
            if (btn) { btn.disabled = false; btn.textContent = 'Reclasificar'; }

            // Actualizar la clasificación actual mostrada
            const currentEl = document.querySelector('.reclassify-value');
            if (currentEl) { currentEl.textContent = `${newLabel} · corregido manualmente`; currentEl.classList.add('corrected'); }

            status?.insertAdjacentHTML('beforeend', '<div style="margin-top:6px;font-size:11px;color:var(--c-text-2)">Actualizando validaciones...</div>');
            await refreshClassifAfterManualChange(payload.id);

        } catch(e) {
            let errMsg = '';
            if (typeof e === 'string') errMsg = e;
            else if (e instanceof Error) errMsg = e.message;
            else if (e?.detail) errMsg = String(e.detail);
            else errMsg = JSON.stringify(e);
            if (status) { status.style.color = 'var(--c-err)'; status.textContent = 'Error: ' + errMsg; }
            if (btn) { btn.disabled = false; btn.textContent = 'Reclasificar'; }
        } finally {
            setClassifDocListBusy(false);
        }
    });

    const sedeSelect = document.getElementById('anexoSedeSelect');
    const reclassifySelect = document.getElementById('reclassifySelect');
    reclassifySelect?.addEventListener('change', () => {
        if (!sedeSelect) return;
        sedeSelect.style.display = canonicalDocumentType(reclassifySelect.value || item.type) === 'anexo_sedes' ? '' : 'none';
    });
    sedeSelect?.addEventListener('change', async () => {
        if (!payload?.id) return;
        const status = document.getElementById('reclassifyStatus');
        if (status) { status.textContent = ''; status.style.color = ''; }
        sedeSelect.disabled = true;
        try {
            const currentReview = manualDocumentReviewEntry(payload, item.file);
            const expectedType = currentReview.expected_type || item.type || 'anexo_sedes';
            const verdict = currentReview.verdict || (item.corrected ? 'no' : 'si');
            const r = await fetchWithRetry(caseApiUrl(payload.id, '/manual-review'), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    kind: item.kind || 'document',
                    filename: item.file,
                    file: item.file,
                    expected_type: expectedType,
                    verdict,
                    sede_key: sedeSelect.value,
                }),
            });
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            item.sedeKey = sedeSelect.value;
            payload.analysis = payload.analysis || {};
            payload.analysis.manual_review = payload.analysis.manual_review || {};
            payload.analysis.manual_review.documents = payload.analysis.manual_review.documents || {};
            payload.analysis.manual_review.documents[item.file] = {
                ...currentReview,
                kind: item.kind || 'document',
                filename: item.file,
                expected_type: expectedType,
                verdict,
                sede_key: sedeSelect.value,
            };
            if (status) {
                status.style.color = 'var(--c-ok)';
                status.textContent = sedeSelect.value ? '✓ Sede asignada al documento.' : '✓ Asignación de sede limpiada.';
            }
        } catch(e) {
            if (status) { status.style.color = 'var(--c-err)'; status.textContent = 'Error asignando sede: ' + e.message; }
        } finally {
            sedeSelect.disabled = false;
        }
    });

}

async function reclassifyDocument(caseId, item, newType) {
    setClassifDocListBusy(true, 'Reclasificando documento...');
    try {
        const r = await fetchWithRetry(caseApiUrl(caseId, '/manual-review'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ kind: item.kind||'document', filename: item.file, file: item.file, expected_type: newType, verdict: 'no' }),
        });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        await refreshClassifAfterManualChange(caseId);
    } catch(e) {
        console.error('reclassifyDocument:', e);
        showToast('No se pudo reclasificar: ' + e.message, 'err');
    } finally {
        setClassifDocListBusy(false);
    }
}

// ── VALIDACIÓN OCR ───────────────────────────────────────────
function onValidacionCaseChange(caseId) {
    if (!caseId) return;
    // Ocultar selector al entrar al detalle
    const selectorRow = document.getElementById('validacionSelectorRow');
    if (selectorRow) selectorRow.style.display = 'none';
    loadValidacionForCase(caseId);
}

async function loadValidacionForCase(caseId) {
    const el = document.getElementById('validacionContent');
    if (!el) return;
    el.innerHTML = '<div class="loading-msg">Cargando validaciones...</div>';
    try {
        const r = await fetchWithRetry(caseApiUrl(caseId));
        const payload = await r.json();
        renderValidacionOCR(el, payload);
    } catch(e) {
        el.innerHTML = `<div class="error-msg">${escapeHtml(e.message)}</div>`;
    }
}

function renderValidacionOCR(container, payload) {
    const a = payload?.analysis || {};
    const wf = a.workflow_run || {};
    const checklist = a.checklist || {};
    const validaciones = Array.isArray(a.validacion_resumen) ? a.validacion_resumen :
                         Array.isArray(checklist.validations) ? checklist.validations : [];
    const docs = sortDocumentGroupsByDisplayPriority(
        Array.isArray(checklist.received_summary) ? checklist.received_summary :
        Array.isArray(a.documents_summary) ? a.documents_summary : []
    );
    const profile = (a.xlsx_profile || {}).profile || {};
    const empresa = profile.empresa || payload.label || 'n/d';
    const nit = profile.nit || 'n/d';
    const nroAfiliacion = resolveContractNumber(a, payload);
    const blockerRecords = getValidationBlockerRecords(payload);
    const acceptedExceptions = getAcceptedValidationExceptions(payload);

    // Extraer validaciones adicionales de múltiples fuentes
    const vrMatches = a.validacion_resumen?.matches || a.reporte_ejecutivo?.matches || {};
    const camara = a.camara_profile || {};
    const formulario = a.formulario_profile || {};

    let html = `<div style="padding:16px">`;

    // Header con botón back
    html += `<div style="display:flex;align-items:center;gap:12px;margin-bottom:16px">
        <button class="btn-secondary" id="validacionBackBtn" type="button" style="font-size:11px;padding:5px 10px">← Otro contrato</button>
        <div>
            <div style="font-size:13px;font-weight:700">${escapeHtml(empresa)}</div>
            <div style="font-size:12px;color:var(--c-text-2)">NIT: ${escapeHtml(nit)}${nroAfiliacion ? ` · Contrato ${escapeHtml(nroAfiliacion)}` : ''}</div>
        </div>
    </div>`;

    if (blockerRecords.length) {
        html += `<div class="report-section-title" style="margin-bottom:8px">Bloqueantes de validación documental</div>`;
        html += `<div style="display:flex;flex-direction:column;gap:8px;margin-bottom:20px">`;
        for (const [i, b] of blockerRecords.entries()) {
            html += `
                <div class="ocr-field mismatch">
                    <div class="ocr-field-label">${escapeHtml(b.code || 'Validación')}</div>
                    <div class="ocr-field-val">✗ Bloqueante</div>
                    <div style="font-size:11px;color:var(--c-text-2);margin-top:4px">${escapeHtml(b.message || '')}</div>
                    ${validationExceptionButtonHtml(b, i, 'margin-top:8px')}
                </div>
            `;
        }
        html += `</div>`;
    }

    if (acceptedExceptions.length) {
        html += `<div class="report-section-title" style="margin-bottom:8px">Aceptados manualmente</div>`;
        html += `<div style="display:flex;flex-direction:column;gap:8px;margin-bottom:20px">`;
        for (const item of acceptedExceptions) {
            html += `
                <div class="ocr-field match">
                    <div class="ocr-field-label">${escapeHtml(item.code || 'Validación')}</div>
                    <div class="ocr-field-val">✓ Aceptado para este contrato</div>
                    <div style="font-size:11px;color:var(--c-text-2);margin-top:4px">${escapeHtml(item.message || '')}</div>
                    <div style="font-size:11px;color:var(--c-text-2);margin-top:2px">Motivo: ${escapeHtml(item.accepted_reason || item.reason || 'Validado manualmente')}</div>
                </div>
            `;
        }
        html += `</div>`;
    }

    // Documentos recibidos
    if (docs.length) {
        html += `<div class="report-section-title" style="margin-bottom:8px">Documentos clasificados</div>`;
        html += `<div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:20px">`;
        for (const group of docs) {
            const count = (group.files||[]).length;
            const groupType = group.document_type || group.type || group.label;
            const label = getReviewTypeLabel(groupType) || group.label || 'Documento';
            const code = getReviewTypeCode(groupType);
            html += `<span class="pill pill-neutral">${escapeHtml(label)}${code?` ·${code}`:''} (${count})</span>`;
        }
        html += `</div>`;
    }

    // Comparaciones de datos cruzados (OCR real)
    const crossChecks = [];
    if (vrMatches.empresa_nombre) {
        const m = vrMatches.empresa_nombre;
        crossChecks.push({ label: 'Razón social', camara: m.camara||'', formulario: m.formulario||m.xlsx||'', ok: m.ok ?? m.match ?? (m.camara_compare === m.formulario_compare) });
    }
    if (camara.nit || formulario.nit) {
        crossChecks.push({ label: 'NIT', camara: camara.nit||'', formulario: formulario.nit||profile.nit||'', ok: camara.nit===formulario.nit });
    }
    if (camara.representante_legal || formulario.representante_legal) {
        crossChecks.push({ label: 'Representante Legal', camara: camara.representante_legal||'', formulario: formulario.representante_legal||'', ok: camara.representante_legal===formulario.representante_legal });
    }

    if (crossChecks.length) {
        html += `<div class="report-section-title" style="margin-bottom:8px">Comparación OCR · Cámara vs Formulario</div>`;
        html += `<div style="display:flex;flex-direction:column;gap:6px;margin-bottom:20px">`;
        for (const c of crossChecks) {
            html += `
                <div class="ocr-field ${c.ok?'match':'mismatch'}">
                    <div class="ocr-field-label">${escapeHtml(c.label)}</div>
                    <div class="ocr-field-val">${c.ok ? '✓ Coincide' : '✗ No coincide'}</div>
                    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:6px;font-size:11px">
                        <div><span style="color:var(--c-text-2)">Cámara:</span><br><strong>${escapeHtml(c.camara||'—')}</strong></div>
                        <div><span style="color:var(--c-text-2)">Formulario/XLSX:</span><br><strong>${escapeHtml(c.formulario||'—')}</strong></div>
                    </div>
                </div>`;
        }
        html += `</div>`;
    }

    // Validaciones del checklist
    if (validaciones.length) {
        html += `<div class="report-section-title" style="margin-bottom:8px">Validaciones del sistema</div>`;
        html += `<div style="display:flex;flex-direction:column;gap:8px">`;
        for (const v of validaciones) {
            const status = normalizeText(v.status || v.estado || v.result || '');
            const ok = Boolean(v.passed || v.ok || status === 'ok');
            const label = v.label || v.field || v.rule || 'Validación';
            const valueFound = v.value_found || v.valor_encontrado || v.extracted || '';
            const valueExpected = v.value_expected || v.valor_esperado || v.expected || '';
            const detail = v.detail || v.detalle || v.message || '';
            html += `
                <div class="ocr-field ${ok?'match':'mismatch'}">
                    <div class="ocr-field-label">${escapeHtml(label)}</div>
                    <div class="ocr-field-val">${ok ? '✓ Ok' : '✗ No pasó'}</div>
                    ${valueFound ? `<div style="font-size:11px;margin-top:4px;color:var(--c-text-2)">Encontrado: <strong>${escapeHtml(String(valueFound))}</strong></div>` : ''}
                    ${valueExpected ? `<div style="font-size:11px;color:var(--c-text-2)">Esperado: <strong>${escapeHtml(String(valueExpected))}</strong></div>` : ''}
                    ${detail ? `<div style="font-size:11px;color:var(--c-text-2);margin-top:2px">${escapeHtml(detail)}</div>` : ''}
                </div>
            `;
        }
        html += `</div>`;
    } else if (!crossChecks.length) {
        html += `<div class="empty-state">No hay validaciones OCR disponibles para este contrato</div>`;
    }

    html += `</div>`;
    container.innerHTML = html;

    // Back button — muestra el selector de nuevo
    container.querySelector('#validacionBackBtn')?.addEventListener('click', () => {
        container.innerHTML = '<div class="empty-state">Selecciona un contrato para revisar las validaciones OCR</div>';
        const selectorRow = document.getElementById('validacionSelectorRow');
        if (selectorRow) selectorRow.style.display = '';
        const sel = document.getElementById('validacionCaseSelect');
        if (sel) sel.value = '';
    });
    container.querySelectorAll('.validation-exception-btn').forEach(btn => {
        btn.addEventListener('click', async () => {
            const record = blockerRecords[Number(btn.dataset.blockerIdx || 0)];
            setValidationExceptionButtonsLoading(container, btn, true);
            try {
                const saved = await acceptValidationException(payload.id || activeCaseId, record);
                if (!saved) setValidationExceptionButtonsLoading(container, btn, false);
            }
            catch(e) {
                showToast('No pude guardar la excepción: ' + e.message, 'err', 6000);
                setValidationExceptionButtonsLoading(container, btn, false);
            }
        });
    });

}

// ── VISOR DOCUMENTAL ─────────────────────────────────────────
function onVisorCaseChange(caseId) {
    if (!caseId) return;
    loadVisorForCase(caseId);
}

async function loadVisorForCase(caseId) {
    const listEl = document.getElementById('visorDocList');
    const frame = document.getElementById('visorDocFrame');
    if (!listEl) return;
    listEl.innerHTML = '<div class="loading-msg">Cargando...</div>';
    if (frame) frame.innerHTML = '<div class="empty-state">Selecciona un documento</div>';
    try {
        const r = await fetchWithRetry(caseApiUrl(caseId));
        const payload = await r.json();
        const items = buildDocItems(payload);
        if (!items.length) { listEl.innerHTML = '<div class="empty-state">Sin documentos</div>'; return; }
        listEl.innerHTML = items.map((item, i) => `
            <div class="doc-item" data-index="${i}">
                <span class="doc-item-name" title="${escapeHtml(item.displayName)}">${escapeHtml(item.label)}</span>
            </div>
        `).join('');
        listEl.querySelectorAll('.doc-item').forEach(el => {
            el.addEventListener('click', async () => {
                listEl.querySelectorAll('.doc-item').forEach(d => d.classList.remove('active'));
                el.classList.add('active');
                const item = items[parseInt(el.dataset.index)];
                if (!item) return;
                const title = document.getElementById('visorDocTitle');
                const actions = document.getElementById('visorDocActions');
                if (title) title.textContent = item.label;
                if (actions) {
                    const url = caseFileUrl(caseId, item.file);
                    actions.innerHTML = `<a class="btn-secondary" href="${escapeHtml(url)}" download="${escapeHtml(item.displayName||item.file)}" style="font-size:11px;padding:5px 10px">Descargar</a>`;
                }
                if (frame) await renderDocPreview(frame, caseId, item);
            });
        });
    } catch(e) {
        listEl.innerHTML = `<div class="error-msg">${escapeHtml(e.message)}</div>`;
    }
}

// ── REPORTE EJECUTIVO ────────────────────────────────────────
function onReporteCaseChange(caseId) {
    if (!caseId) return;
    loadReporteForCase(caseId);
}

async function loadReporteSidebar() {
    const listEl = document.getElementById('reporteSidebarList');
    if (!listEl) return;
    listEl.innerHTML = '<div class="loading-msg">Cargando...</div>';
    try {
        const r = await fetchWithRetry(operationApiUrl('/api/cases/production-summary'));
        const data = await r.json();
        let cases = Array.isArray(data.cases) ? data.cases : [];
        // Perfil Colmena: solo mostrar contratos aprobados
        if (readProfile() === 'colmena') {
            cases = cases.filter(c => {
                const { status, finalStatus } = resolveCase(c);
                return isApprovedCaseStatus(status, finalStatus);
            });
        }
        cases.sort((a,b) => String(b.updated_at||'').localeCompare(String(a.updated_at||'')));
        renderReporteSidebar(cases);
        // Si hay un caso activo, seleccionarlo — pero NO recargar el reporte si ya se está mostrando
        if (activeCaseId) {
            highlightSidebarItem(activeCaseId);
            // Solo recargar si el reporte actual no es del caso correcto
            const reporteContent = document.getElementById('reporteContent');
            const currentCaseShown = reporteContent?.dataset?.caseId;
            if (currentCaseShown !== activeCaseId) {
                loadReporteForCase(activeCaseId);
            }
        } else if (cases.length) {
            // Seleccionar el primero automáticamente
            const first = cases[0];
            if (first?.id) { activeCaseId = first.id; highlightSidebarItem(first.id); loadReporteForCase(first.id); }
        }
        // Filtro de búsqueda
        const searchEl = document.getElementById('reporteSidebarSearch');
        if (searchEl) {
            searchEl.addEventListener('input', () => {
                const q = searchEl.value.toLowerCase();
                listEl.querySelectorAll('.reporte-sidebar-item').forEach(item => {
                    const text = (item.dataset.empresa || '') + (item.dataset.nit || '');
                    item.style.display = text.toLowerCase().includes(q) ? '' : 'none';
                });
            });
        }
    } catch(e) {
        listEl.innerHTML = `<div class="error-msg">${escapeHtml(e.message)}</div>`;
    }
}

function renderReporteSidebar(cases) {
    const listEl = document.getElementById('reporteSidebarList');
    if (!listEl) return;
    listEl.innerHTML = cases.map(c => {
        const { empresa, nit, status, finalStatus } = resolveCase(c);
        const cls = caseStatusClass(status, finalStatus);
        const dotCls = cls === 'ok' ? 'ok' : cls === 'warn' ? 'warn' : cls === 'err' ? 'err' : 'neutral';
        const lbl = casePillLabel(status, finalStatus);
        const nitStr = nit !== 'n/d' ? nit : '';
        return `
            <div class="reporte-sidebar-item" data-case="${escapeHtml(c.id||'')}"
                data-empresa="${escapeHtml(empresa)}" data-nit="${escapeHtml(nitStr)}">
                <div class="reporte-sidebar-item-empresa">${escapeHtml(empresa)}</div>
                <div class="reporte-sidebar-item-meta">
                    <span class="reporte-sidebar-dot ${dotCls}"></span>
                    <span>${escapeHtml(lbl)}</span>
                    ${nitStr ? `<span style="opacity:0.7;font-weight:600">· ${escapeHtml(nitStr)}</span>` : ''}
                </div>
            </div>
        `;
    }).join('');
    listEl.querySelectorAll('.reporte-sidebar-item').forEach(item => {
        item.addEventListener('click', () => {
            const id = item.dataset.case;
            if (id) { activeCaseId = id; highlightSidebarItem(id); loadReporteForCase(id); }
        });
    });
}

function highlightSidebarItem(caseId) {
    const listEl = document.getElementById('reporteSidebarList');
    if (!listEl) return;
    listEl.querySelectorAll('.reporte-sidebar-item').forEach(item => {
        item.classList.toggle('active', item.dataset.case === caseId);
    });
    const active = listEl.querySelector(`.reporte-sidebar-item[data-case="${caseId}"]`);
    if (active) active.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
}

async function loadReporteForCase(caseId) {
    const el = document.getElementById('reporteContent');
    if (!el) return;
    el.dataset.caseId = caseId;  // marcar qué caso se está mostrando
    el.innerHTML = '<div class="loading-msg">Cargando reporte...</div>';
    try {
        const r = await fetchWithRetry(caseApiUrl(caseId));
        const payload = await r.json();
        el.dataset.caseId = caseId;  // confirmar después de cargar
        renderFormularioReporte(el, payload);
    } catch(e) {
        el.innerHTML = `<div class="error-msg">${escapeHtml(e.message)}</div>`;
    }
}

function formFieldLabel(key) {
    const custom = {
        empleador_razon_social: 'Razón social',
        empleador_tipo_documento: 'Tipo documento empleador',
        empleador_numero_documento_nit: 'Documento / NIT',
        empleador_documento: 'Documento / NIT',
        fecha_radicacion: 'Fecha radicación',
        fecha_inicio_cobertura: 'Inicio cobertura',
        numero_radicacion: 'Número radicación',
        tipo_tramite: 'Tipo trámite',
        lugar_afiliacion: 'Lugar afiliación',
        codigo_lugar: 'Código lugar',
        nombre_lugar: 'Nombre lugar',
        naturaleza_juridica_empleador: 'Naturaleza jurídica',
        naturaleza_juridica_codigo_tramite: 'Cód. naturaleza',
        naturaleza_juridica_nombre: 'Naturaleza',
        tipo_aportante: 'Tipo aportante',
        tipo_aportante_codigo: 'Cód. aportante',
        tipo_aportante_nombre: 'Aportante',
        tipo_persona: 'Tipo persona',
        rep_legal_nombre_completo: 'Nombre completo',
        rep_legal_primer_apellido: 'Primer apellido',
        rep_legal_primer_nombre: 'Primer nombre',
        rep_legal_tipo_documento: 'Tipo documento',
        rep_legal_numero_documento: 'Número documento',
        rep_legal_documento: 'Documento representante',
        rep_legal_correo: 'Correo',
        rep_legal_correo_electronico: 'Correo electrónico',
        sede_principal_codigo: 'Código',
        sede_principal_nombre: 'Nombre',
        sede_principal_direccion: 'Dirección',
        sede_principal_telefono: 'Teléfono',
        sede_principal_correo: 'Correo',
        sede_principal_municipio_distrito: 'Municipio / distrito',
        sede_principal_zona: 'Zona',
        sede_principal_departamento: 'Departamento',
        sede_principal_localidad_comuna: 'Localidad / comuna',
        sede_principal_as22: 'Dato adicional sede',
        responsable_sede_principal_nombre_completo: 'Responsable sede',
        responsable_sede_principal_primer_apellido: 'Primer apellido resp.',
        responsable_sede_principal_primer_nombre: 'Primer nombre resp.',
        responsable_sede_principal_tipo_documento: 'Tipo doc. resp.',
        responsable_sede_principal_numero_documento: 'Documento resp.',
        responsable_sede_principal_documento: 'Documento responsable',
        responsable_sede_principal_correo: 'Correo responsable sede',
        a_codigo_actividad_economica_principal: 'Código actividad económica',
        a_clase_riesgo: 'Clase de riesgo',
        a_numero_sedes: 'Número de sedes',
        a_numero_centros_trabajo: 'Número de centros de trabajo',
        a_numero_inicial_trabajadores_estudiantes: 'Trabajadores / estudiantes',
        a_valor_total_nomina: 'Valor total nómina',
        b_arl_de_la_cual_se_traslada: 'ARL de la cual se traslada',
        b_clase_riesgo: 'Clase de riesgo',
        b_codigo_actividad_economica_principal: 'Código actividad económica',
        b_numero_sedes: 'Número de sedes',
        b_numero_centros_trabajo: 'Número de centros de trabajo',
        b_numero_total_trabajadores_estudiantes: 'Trabajadores / estudiantes',
        b_monto_total_cotizacion: 'Monto total cotización',
        estado_cuenta_empleador: 'Estado cuenta empleador',
        numero_contrato: 'Contrato',
        fecha_actualizacion: 'Actualizado',
    };
    if (custom[key]) return custom[key];
    return String(key || '')
        .replace(/^a_/, '')
        .replace(/^b_/, '')
        .replace(/^rep_legal_/, '')
        .replace(/^sede_principal_/, '')
        .replace(/^empleador_/, '')
        .replace(/_/g, ' ')
        .replace(/\b\w/g, ch => ch.toUpperCase());
}

function isBlankFormValue(value) {
    if (value === null || value === undefined) return true;
    if (Array.isArray(value)) return value.length === 0;
    if (typeof value === 'object') return Object.keys(value).length === 0;
    return String(value).trim() === '';
}

function formatFormValue(key, value) {
    if (isBlankFormValue(value)) return '';
    if (Array.isArray(value)) return `${value.length} registro(s)`;
    if (typeof value === 'object') return JSON.stringify(value);
    const text = String(value).trim();
    if (key === 'fecha_radicacion' || key === 'fecha_inicio_cobertura') {
        return formatDateOnlyValue(text);
    }
    const numeric = Number(String(text).replace(/[^\d.-]/g, ''));
    if (/nomina|nómina|monto|cotizacion|cotización|salario|ibc/i.test(key) && Number.isFinite(numeric) && numeric > 0) {
        return formatCurrency(numeric);
    }
    return text;
}

function joinDocumentParts(type, number) {
    return [type, formatThousandsNumber(number)].filter(value => !isBlankFormValue(value)).join(' ');
}

function renderFormFieldGrid(entries) {
    const items = entries.filter(([, value]) => !isBlankFormValue(value));
    if (!items.length) return '<div class="form-empty">Sin información recuperada.</div>';
    return `
        <div class="form-info-grid">
            ${items.map(([key, value]) => `
                <div class="form-info-item">
                    <div class="form-info-label">${escapeHtml(formFieldLabel(key))}</div>
                    <div class="form-info-value">${escapeHtml(formatFormValue(key, value))}</div>
                </div>
            `).join('')}
        </div>
    `;
}

function renderCompactInfoTable(entries) {
    const items = entries.filter(([, value]) => !isBlankFormValue(value));
    if (!items.length) return '<div class="form-empty">Sin información recuperada.</div>';
    const rows = [];
    for (let i = 0; i < items.length; i += 3) rows.push(items.slice(i, i + 3));
    return `
        <table class="company-info-table">
            <tbody>
                ${rows.map(row => `
                    <tr>
                        ${[0, 1, 2].map(index => {
                            const item = row[index];
                            if (!item) return '<th></th><td></td>';
                            const [key, value] = item;
                            return `
                                <th>${escapeHtml(formFieldLabel(key))}</th>
                                <td>${escapeHtml(formatFormValue(key, value))}</td>
                            `;
                        }).join('')}
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
}

function renderCentrosTrabajo(centros) {
    if (!Array.isArray(centros) || !centros.length) return '';
    return `
        <div class="form-table-wrap">
            <table class="form-table">
                <thead>
                    <tr>
                        <th>Código</th>
                        <th>Nombre</th>
                        <th>Actividad</th>
                        <th>Riesgo</th>
                        <th>Trab.</th>
                        <th>Dirección</th>
                        <th>Responsable</th>
                    </tr>
                </thead>
                <tbody>
                    ${centros.map(c => `
                        <tr>
                            <td>${escapeHtml(c.codigo || c.codigo_ct || c.centro_trabajo || '')}</td>
                            <td>${escapeHtml(c.nombre || c.nombre_ct || '')}</td>
                            <td>${escapeHtml(c.actividad_economica_codigo || c.actividad_economica || '')}</td>
                            <td>${escapeHtml(c.clase_riesgo || c.clase_riesgo_ct || '')}</td>
                            <td>${escapeHtml(c.cantidad_trabajadores || c.trabajadores || '')}</td>
                            <td>${escapeHtml(c.direccion || c.direccion_ct || '')}</td>
                            <td>${escapeHtml(c.responsable_nombre || c.responsable || '')}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
    `;
}

function parseSedeNumber(value, fallback = 1) {
    const match = String(value || '').match(/sedes?[_\s-]*(?:principal|0*(\d+))|Sede\s*0*(\d+)/i);
    if (!match) return fallback;
    if (/principal/i.test(match[0])) return 1;
    return Number(match[1] || match[2] || fallback) || fallback;
}

function sedeCodeFromValue(value, fallback = '') {
    const text = String(value || '');
    const match = text.match(/sede[_\s-]*(principal|0*\d+)|Sede\s*0*(\d+)\s*[-–]\s*Trabajadores/i);
    const raw = match ? (match[1] || match[2] || '') : fallback;
    if (/principal/i.test(raw)) return '1';
    const digits = String(raw || '').replace(/[^\d]/g, '');
    if (!digits) return String(fallback || '').trim();
    return String(Number(digits) || digits);
}

function sedePrefixFromCode(code) {
    const num = Number(String(code || '').replace(/[^\d]/g, '')) || 1;
    return num === 1 ? 'sede_principal' : `sede_${String(num).padStart(2, '0')}`;
}

function sedeSheetCellValue(sedeSheetValues, sheetName, field) {
    return (sedeSheetValues?.[sheetName]?.[field] || {}).value || '';
}

function buildFormularioSedes(payload, declaredTotal) {
    const a = payload?.analysis || {};
    const xlsxProfile = a.xlsx_profile || {};
    const formFields = xlsxProfile.form_fields || {};
    const records = xlsxProfile.records || [];
    const workerCounts = xlsxProfile.worker_sheet_counts || {};
    const salaryCounts = xlsxProfile.worker_sheet_salary_totals || {};
    const sedeSheetValues = xlsxProfile.sede_sheet_values || {};
    const activeSheets = Array.isArray(xlsxProfile.active_sede_worker_sheet_names)
        ? xlsxProfile.active_sede_worker_sheet_names
        : [];
    const bySedeCode = new Map();
    const declaredCount = Number(String(declaredTotal || '').replace(/[^\d]/g, '')) || 0;
    const ensureSede = (code, sourceName = '', order = bySedeCode.size + 1) => {
        const normalizedCode = sedeCodeFromValue(code, code) || String(order);
        if (!bySedeCode.has(normalizedCode)) {
            bySedeCode.set(normalizedCode, {
                code: normalizedCode,
                number: order,
                label: `Sede ${normalizedCode}`,
                sourceName,
                workers: [],
            });
        }
        const sede = bySedeCode.get(normalizedCode);
        if (sourceName && !sede.sourceName) sede.sourceName = sourceName;
        return sede;
    };

    const orderedSheets = activeSheets.length
        ? activeSheets
        : Object.keys(workerCounts).length
            ? Object.keys(workerCounts)
            : Object.keys(sedeSheetValues);
    const sheetsToRender = declaredCount ? orderedSheets.slice(0, declaredCount) : orderedSheets;
    sheetsToRender.forEach((name, index) => {
        const code = sedeSheetCellValue(sedeSheetValues, name, 'codigo_sede') || sedeCodeFromValue(name, String(index + 1));
        ensureSede(code, name, index + 1);
    });

    Object.keys(formFields).forEach(key => {
        const match = key.match(/^sede_(principal|\d+)_/);
        if (match && !sheetsToRender.length) ensureSede(match[1] === 'principal' ? '1' : match[1]);
    });

    records.forEach(record => {
        const code = sedeSheetCellValue(sedeSheetValues, record._sheet, 'codigo_sede') || sedeCodeFromValue(record._sheet, String(bySedeCode.size + 1));
        const sede = ensureSede(code, record._sheet);
        if (sede) sede.workers.push(record);
    });

    Object.entries(workerCounts).forEach(([name, count]) => {
        const code = sedeSheetCellValue(sedeSheetValues, name, 'codigo_sede') || sedeCodeFromValue(name, String(bySedeCode.size + 1));
        const sede = ensureSede(code, name);
        if (sede) {
            sede.workerCount = count;
            sede.sourceName = name;
        }
    });

    Object.entries(salaryCounts).forEach(([name, amount]) => {
        const code = sedeSheetCellValue(sedeSheetValues, name, 'codigo_sede') || sedeCodeFromValue(name, String(bySedeCode.size + 1));
        const sede = ensureSede(code, name);
        if (sede) sede.salaryTotal = amount;
    });

    return [...bySedeCode.values()].sort((a, b) => a.number - b.number).map(sede => {
        const prefix = sedePrefixFromCode(sede.code);
        const centros = Array.isArray(formFields[`${prefix}_centros_de_trabajo`])
            ? formFields[`${prefix}_centros_de_trabajo`]
            : [];
        const workersSalary = sede.workers.reduce((sum, worker) => sum + (Number(worker.salario) || 0), 0);
        const salary = workersSalary || Number(sede.salaryTotal || 0);
        const responsableNombre = formFields[`responsable_${prefix}_nombre_completo`] || '';
        const responsableTipoDoc = formFields[`responsable_${prefix}_tipo_documento`] || '';
        const responsableNumeroDoc = formFields[`responsable_${prefix}_numero_documento`] || '';
        const responsableDoc = [
            responsableTipoDoc,
            responsableNumeroDoc,
        ].filter(Boolean).join(' ');

        return {
            ...sede,
            codigo: formFields[`${prefix}_codigo`] || sede.code || '',
            label: `Sede ${formFields[`${prefix}_codigo`] || sede.code || sede.number}`,
            nombre: formFields[`${prefix}_nombre`] || '',
            direccion: formFields[`${prefix}_direccion`] || '',
            municipio: formFields[`${prefix}_municipio_distrito`] || '',
            departamento: formFields[`${prefix}_departamento`] || '',
            zona: formFields[`${prefix}_zona`] || '',
            telefono: formFields[`${prefix}_telefono`] || '',
            correo: formFields[`${prefix}_correo`] || '',
            responsable: responsableNombre,
            responsableTipoDoc,
            responsableNumeroDoc,
            responsableCorreo: formFields[`responsable_${prefix}_correo`] || '',
            responsableDoc,
            centros,
            centrosCount: centros.length,
            workerCount: sede.workerCount ?? sede.workers.length,
            salary,
        };
    });
}

function centroTrabajoLabel(centro, index) {
    const code = centroTrabajoCode(centro);
    return `C. Trabajo ${code || String(index + 1).padStart(2, '0')}`;
}

function renderFormularioCentroDetalle(centro) {
    if (!centro) return '';
    const responsable = [
        centro.responsable_apellido1,
        centro.responsable_apellido2,
        centro.responsable_nombre1,
        centro.responsable_nombre2,
    ].filter(Boolean).join(' ');
    const responsableDoc = [centro.responsable_tipo_doc, centro.responsable_num_doc].filter(Boolean).join(' ');
    const fields = [
        ['Código', centro.codigo || centro.codigo_ct],
        ['Nombre', centro.nombre || centro.nombre_ct],
        ['Actividad', centro.actividad_economica_codigo || centro.actividad_economica],
        ['Riesgo', centro.clase_riesgo || centro.clase_riesgo_ct],
        ['Trabajadores', centro.cantidad_trabajadores || centro.trabajadores],
        ['Monto total cotización', centroTrabajoMontoCotizacion(centro)],
        ['Municipio', centro.municipio],
        ['Departamento', centro.departamento],
        ['Zona', centro.zona],
        ['Dirección', centro.direccion || centro.direccion_ct],
        ['Teléfono', centro.telefono],
        ['Correo', centro.correo],
        ['Responsable', responsable || centro.responsable_nombre || centro.responsable],
        ['Doc. responsable', responsableDoc],
        ['Correo resp.', centro.responsable_correo],
        ['Novedades', centro.novedades],
    ].filter(([, value]) => !isBlankFormValue(value));
    if (!fields.length) return '';
    return `
        <div class="sede-detail-subtitle">Centro de trabajo</div>
        <div class="sede-info-flow">
            ${fields.map(([label, value]) => `
                <span><strong>${escapeHtml(label)}:</strong> ${escapeHtml(formatFormValue(label, value))}</span>
            `).join('')}
        </div>
    `;
}

function centroTrabajoCode(centro) {
    return String(centro?.codigo || centro?.codigo_ct || centro?.centro_trabajo || '').trim();
}

function centroTrabajoMontoCotizacion(centro) {
    const value = centro?.monto_total_cotizacion ||
        centro?.monto_cotizacion ||
        centro?.monto_total_de_cotizacion ||
        centro?.valor_total_cotizacion ||
        '';
    return isBlankFormValue(value) ? '' : formatFormValue('monto_total_cotizacion', value);
}

function filterSedeWorkers(sede, centroIndex = 'all') {
    const workers = sede?.workers || [];
    if (centroIndex === 'all') return workers;
    const centro = (sede?.centros || [])[Number(centroIndex) || 0];
    const code = normalizeText(centroTrabajoCode(centro));
    if (!code) return workers;
    return workers.filter(worker => normalizeText(worker.codigo_del_centro_de_trabajo || worker.codigo_centro_trabajo || '') === code);
}

function sumWorkersSalary(workers) {
    return (workers || []).reduce((sum, worker) => sum + (Number(worker.salario) || 0), 0);
}

function splitPersonName(value) {
    const parts = String(value || '').trim().split(/\s+/).filter(Boolean);
    if (!parts.length) return {};
    if (parts.length === 1) return { primerNombre: parts[0] };
    if (parts.length === 2) return { primerApellido: parts[0], primerNombre: parts[1] };
    if (parts.length === 3) return { primerApellido: parts[0], segundoApellido: parts[1], primerNombre: parts[2] };
    return {
        primerApellido: parts[0],
        segundoApellido: parts[1],
        primerNombre: parts[2],
        segundoNombre: parts.slice(3).join(' '),
    };
}

function onlyDigits(value) {
    return String(value ?? '').replace(/\D/g, '');
}

function humanizeKey(key) {
    return String(key || '')
        .replace(/^_+/, '')
        .replace(/_/g, ' ')
        .replace(/\b\w/g, char => char.toUpperCase());
}

function workerValue(worker, keys) {
    for (const key of keys) {
        const value = worker?.[key];
        if (!isBlankFormValue(value)) return value;
    }
    return '';
}

function workerDocumentValue(worker) {
    const type = workerValue(worker, ['tipo_documento', 'tipo_de_documento', 'tipo_identificacion', 'tipodocumento']);
    const number = workerValue(worker, [
        'numero_identificacion',
        'numero_de_identificacion',
        'documento',
        'numero_documento',
        'num_id_trabajador',
        '_raw_numero_de_identificacion',
    ]);
    return [type, number].filter(value => !isBlankFormValue(value)).join(' ');
}

function workerFullName(worker) {
    const parts = [
        workerValue(worker, ['primer_apellido']),
        workerValue(worker, ['segundo_apellido']),
        workerValue(worker, ['primer_nombre']),
        workerValue(worker, ['segundo_nombre']),
    ].filter(value => !isBlankFormValue(value));
    return parts.join(' ') || workerValue(worker, ['nombre', 'nombre_trabajador']);
}

function workerBirthDate(worker) {
    const direct = workerValue(worker, ['fecha_de_nacimiento', 'fecha_nacimiento']);
    if (!isBlankFormValue(direct)) return direct;
    const day = onlyDigits(workerValue(worker, ['fecha_nacimiento_dia'])).padStart(2, '0');
    const month = onlyDigits(workerValue(worker, ['fecha_nacimiento_mes'])).padStart(2, '0');
    const year = onlyDigits(workerValue(worker, ['fecha_nacimiento_anio', 'fecha_nacimiento_ano', 'fecha_nacimiento_año']));
    if (!day.trim() && !month.trim() && !year.trim()) return '';
    return [year, month, day].filter(value => value && value !== '00').join('-');
}

function workerTypeValue(worker) {
    const code = workerValue(worker, ['codigo_tipo_trabajador', 'codigo_del_tipo_de_trabajador']);
    const label = workerValue(worker, ['tipo_trabajador', 'tipo_de_trabajador']);
    return [code, label].filter(value => !isBlankFormValue(value)).join(' · ');
}

function workerDaysValue(worker) {
    const labels = [
        ['dia_l', 'L'],
        ['dia_m1', 'M'],
        ['dia_m2', 'M'],
        ['dia_j', 'J'],
        ['dia_v', 'V'],
        ['dia_s', 'S'],
        ['dia_d', 'D'],
    ];
    return labels
        .filter(([key]) => normalizeText(worker?.[key]).toLowerCase() === 'x' || normalizeText(worker?.[key]).toLowerCase() === 'true')
        .map(([, label]) => label)
        .join(', ');
}

function workerScheduleValue(worker) {
    const items = Object.keys(worker || {})
        .filter(key => key.startsWith('horario_') && !isBlankFormValue(worker[key]))
        .sort((a, b) => a.localeCompare(b, undefined, { numeric: true }))
        .map(key => `${key.replace('horario_', '')}: ${worker[key]}`);
    return items.join(' · ');
}

function workerDetailEntries(worker) {
    const primary = [
        ['Documento', workerDocumentValue(worker)],
        ['Primer apellido', workerValue(worker, ['primer_apellido'])],
        ['Segundo apellido', workerValue(worker, ['segundo_apellido'])],
        ['Primer nombre', workerValue(worker, ['primer_nombre'])],
        ['Segundo nombre', workerValue(worker, ['segundo_nombre'])],
        ['Fecha nacimiento', workerBirthDate(worker)],
        ['Sexo', workerValue(worker, ['sexo_identificacion', 'sexo'])],
        ['Centro de trabajo', workerValue(worker, ['codigo_del_centro_de_trabajo', 'codigo_centro_trabajo'])],
        ['Cargo', workerValue(worker, ['cargo', 'nombre_del_cargo'])],
        ['Salario', workerValue(worker, ['salario'])],
        ['Tipo salario', workerValue(worker, ['tipo_salario', 'tipo_de_salario'])],
        ['EPS', workerValue(worker, ['eps'])],
        ['Pensión/AFP', workerValue(worker, ['pension', 'afp'])],
        ['Dirección', workerValue(worker, ['direccion', 'dirección'])],
        ['Celular/Teléfono', workerValue(worker, ['celular', 'telefono', 'teléfono'])],
        ['Correo', workerValue(worker, ['correo', 'correo_electronico', 'correo_electrónico'])],
        ['Municipio/Distrito', workerValue(worker, ['municipio_distrito', 'municipio'])],
        ['Departamento', workerValue(worker, ['departamento'])],
        ['Zona', workerValue(worker, ['zona'])],
        ['Jornada', workerValue(worker, ['jornada'])],
        ['Modalidad', workerValue(worker, ['modalidad'])],
        ['Tipo trabajador', workerTypeValue(worker)],
        ['Días actividad', workerDaysValue(worker)],
        ['Horario', workerScheduleValue(worker)],
        ['Hoja', workerValue(worker, ['_sheet'])],
        ['Fila', workerValue(worker, ['_row'])],
    ];
    const consumed = new Set([
        'tipo_documento', 'tipo_de_documento', 'tipo_identificacion', 'tipodocumento',
        'numero_identificacion', 'numero_de_identificacion', 'documento', 'numero_documento', 'num_id_trabajador', '_raw_numero_de_identificacion',
        'nombre', 'nombre_trabajador', 'primer_apellido', 'segundo_apellido', 'primer_nombre', 'segundo_nombre',
        'fecha_de_nacimiento', 'fecha_nacimiento', 'fecha_nacimiento_dia', 'fecha_nacimiento_mes', 'fecha_nacimiento_anio', 'fecha_nacimiento_ano', 'fecha_nacimiento_año',
        'sexo_identificacion', 'sexo', 'codigo_del_centro_de_trabajo', 'codigo_centro_trabajo',
        'cargo', 'nombre_del_cargo', 'salario', 'tipo_salario', 'tipo_de_salario', 'eps', 'pension', 'afp',
        'direccion', 'dirección', 'celular', 'telefono', 'teléfono', 'correo', 'correo_electronico', 'correo_electrónico',
        'municipio_distrito', 'municipio', 'departamento', 'zona', 'jornada', 'modalidad',
        'codigo_tipo_trabajador', 'codigo_del_tipo_de_trabajador', 'tipo_trabajador', 'tipo_de_trabajador',
        'dia_l', 'dia_m1', 'dia_m2', 'dia_j', 'dia_v', 'dia_s', 'dia_d', '_sheet', '_row',
    ]);
    Object.entries(worker || {}).forEach(([key, value]) => {
        if (key.startsWith('_raw_') || consumed.has(key) || key.startsWith('horario_') || isBlankFormValue(value)) return;
        primary.push([humanizeKey(key), value]);
    });
    return primary.filter(([, value]) => !isBlankFormValue(value));
}

function workerTableColumns(workers) {
    const base = [
        ['Documento', workerDocumentValue],
        ['Nombre', workerFullName],
        ['Nacimiento', workerBirthDate],
        ['Sexo', worker => workerValue(worker, ['sexo_identificacion', 'sexo'])],
        ['Centro', worker => workerValue(worker, ['codigo_del_centro_de_trabajo', 'codigo_centro_trabajo'])],
        ['Cargo', worker => workerValue(worker, ['cargo', 'nombre_del_cargo'])],
        ['Salario', worker => {
            const salary = workerValue(worker, ['salario']);
            return salary ? formatCurrency(salary) : '';
        }],
        ['Tipo salario', worker => workerValue(worker, ['tipo_salario', 'tipo_de_salario'])],
        ['EPS', worker => workerValue(worker, ['eps'])],
        ['Pensión/AFP', worker => workerValue(worker, ['pension', 'afp'])],
        ['Dirección', worker => workerValue(worker, ['direccion', 'dirección'])],
        ['Celular/Teléfono', worker => workerValue(worker, ['celular', 'telefono', 'teléfono'])],
        ['Correo', worker => workerValue(worker, ['correo', 'correo_electronico', 'correo_electrónico'])],
        ['Municipio/Distrito', worker => workerValue(worker, ['municipio_distrito', 'municipio'])],
        ['Departamento', worker => workerValue(worker, ['departamento'])],
        ['Zona', worker => workerValue(worker, ['zona'])],
        ['Jornada', worker => workerValue(worker, ['jornada'])],
        ['Modalidad', worker => workerValue(worker, ['modalidad'])],
        ['Tipo trabajador', workerTypeValue],
        ['Días actividad', workerDaysValue],
        ['Horario', workerScheduleValue],
    ];
    return base.filter(([, getter]) => workers.some(worker => !isBlankFormValue(getter(worker))));
}

function renderSedeOfficialInfo(sede) {
    const title = sede?.number === 1 ? 'Información de la sede principal' : `Información de la sede ${String(sede?.number || '').padStart(2, '0')}`;
    return `
        <table class="sede-official-table">
            <thead>
                <tr><th colspan="6">${escapeHtml(title)}</th></tr>
            </thead>
            <tbody>
                <tr>
                    <th>Código de la sede:</th>
                    <td>${escapeHtml(sede?.codigo || '')}</td>
                    <th>Nombre de la sede:</th>
                    <td colspan="3">${escapeHtml(sede?.nombre || '')}</td>
                </tr>
                <tr>
                    <th>Municipio:</th>
                    <td>${escapeHtml(sede?.municipio || '')}</td>
                    <th>Departamento:</th>
                    <td>${escapeHtml(sede?.departamento || '')}</td>
                    <th>Zona sede:</th>
                    <td>${escapeHtml(sede?.zona || '')}</td>
                </tr>
                <tr>
                    <th>Dirección de la sede:</th>
                    <td colspan="5">${escapeHtml(sede?.direccion || '')}</td>
                </tr>
                <tr>
                    <th>Teléfono fijo/celular:</th>
                    <td colspan="2">${escapeHtml(sede?.telefono || '')}</td>
                    <th>Correo electrónico de la sede:</th>
                    <td colspan="2">${escapeHtml(sede?.correo || '')}</td>
                </tr>
            </tbody>
        </table>
    `;
}

function renderSedeResponsibleOfficialInfo(sede) {
    if (!sede?.responsable && !sede?.responsableDoc && !sede?.responsableCorreo) return '';
    const nameParts = splitPersonName(sede.responsable);
    return `
        <table class="sede-official-table sede-official-table-responsible">
            <thead>
                <tr><th colspan="6">Información del responsable de la sede</th></tr>
            </thead>
            <tbody>
                <tr>
                    <th>Primer apellido:</th>
                    <td>${escapeHtml(nameParts.primerApellido || '')}</td>
                    <th>Segundo apellido:</th>
                    <td>${escapeHtml(nameParts.segundoApellido || '')}</td>
                    <th>Primer nombre:</th>
                    <td>${escapeHtml(nameParts.primerNombre || '')}</td>
                </tr>
                <tr>
                    <th>Segundo nombre:</th>
                    <td>${escapeHtml(nameParts.segundoNombre || '')}</td>
                    <th>Tipo de documento:</th>
                    <td>${escapeHtml(sede.responsableTipoDoc || '')}</td>
                    <th>Número de documento:</th>
                    <td>${escapeHtml(sede.responsableNumeroDoc || '')}</td>
                </tr>
                <tr>
                    <th>Correo electrónico:</th>
                    <td colspan="5">${escapeHtml(sede.responsableCorreo || sede.correo || '')}</td>
                </tr>
            </tbody>
        </table>
    `;
}

function renderCentroTrabajoOfficialInfo(centro) {
    if (!centro) return '';
    const responsable = [
        centro.responsable_apellido1,
        centro.responsable_apellido2,
        centro.responsable_nombre1,
        centro.responsable_nombre2,
    ].filter(Boolean).join(' ');
    const responsableDoc = [centro.responsable_tipo_doc, centro.responsable_num_doc].filter(Boolean).join(' ');
    const montoCotizacion = centroTrabajoMontoCotizacion(centro);
    return `
        <table class="sede-official-table sede-official-table-centro">
            <thead>
                <tr><th colspan="6">Información del centro de trabajo</th></tr>
            </thead>
            <tbody>
                <tr>
                    <th>Código:</th>
                    <td>${escapeHtml(centro.codigo || centro.codigo_ct || '')}</td>
                    <th>Nombre:</th>
                    <td colspan="3">${escapeHtml(centro.nombre || centro.nombre_ct || '')}</td>
                </tr>
                <tr>
                    <th>Actividad:</th>
                    <td>${escapeHtml(centro.actividad_economica_codigo || centro.actividad_economica || '')}</td>
                    <th>Riesgo:</th>
                    <td>${escapeHtml(centro.clase_riesgo || centro.clase_riesgo_ct || '')}</td>
                    <th>Trabajadores:</th>
                    <td>${escapeHtml(centro.cantidad_trabajadores || centro.trabajadores || '')}</td>
                </tr>
                ${montoCotizacion ? `
                <tr>
                    <th>Monto total cotización:</th>
                    <td colspan="5">${escapeHtml(montoCotizacion)}</td>
                </tr>
                ` : ''}
                <tr>
                    <th>Municipio:</th>
                    <td>${escapeHtml(centro.municipio || '')}</td>
                    <th>Departamento:</th>
                    <td>${escapeHtml(centro.departamento || '')}</td>
                    <th>Zona:</th>
                    <td>${escapeHtml(centro.zona || '')}</td>
                </tr>
                <tr>
                    <th>Dirección:</th>
                    <td colspan="3">${escapeHtml(centro.direccion || centro.direccion_ct || '')}</td>
                    <th>Teléfono:</th>
                    <td>${escapeHtml(centro.telefono || '')}</td>
                </tr>
                <tr>
                    <th>Responsable:</th>
                    <td colspan="2">${escapeHtml(responsable || centro.responsable_nombre || centro.responsable || '')}</td>
                    <th>Documento:</th>
                    <td colspan="2">${escapeHtml(responsableDoc)}</td>
                </tr>
                <tr>
                    <th>Correo:</th>
                    <td colspan="5">${escapeHtml(centro.responsable_correo || centro.correo || '')}</td>
                </tr>
            </tbody>
        </table>
    `;
}

function renderFormularioSedeDetalle(sede, centroIndex = 'all') {
    if (!sede) return '<div class="form-empty">Sin información de sede.</div>';
    const centro = centroIndex === 'all' ? null : (sede.centros || [])[Number(centroIndex) || 0];
    return `
        <div class="sede-official-stack">
            ${renderSedeOfficialInfo(sede)}
            ${renderSedeResponsibleOfficialInfo(sede)}
            ${renderCentroTrabajoOfficialInfo(centro)}
        </div>
    `;
}

function renderFormularioTrabajadoresTable(workers) {
    if (!workers || !workers.length) return '<div class="form-empty">Sin trabajadores para esta selección.</div>';
    const columns = workerTableColumns(workers);
    return `
        <div class="sede-workers-table-wrap">
            <table class="sede-workers-table">
                <thead>
                    <tr>
                        <th class="sede-workers-index">#</th>
                        ${columns.map(([label]) => `<th>${escapeHtml(label)}</th>`).join('')}
                    </tr>
                </thead>
                <tbody>
                    ${workers.map((worker, index) => `
                        <tr>
                            <td class="sede-workers-index">${index + 1}</td>
                            ${columns.map(([, getter]) => `<td>${escapeHtml(formatFormValue('', getter(worker)))}</td>`).join('')}
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
    `;
}

function formularioDocLabel(doc, index) {
    const type = String(doc?.document_type || '');
    if (type === 'formulario_afiliacion') return 'Formulario afiliación';
    if (type.startsWith('anexo_sedes')) return `Anexo sede ${String(parseSedeNumber(`${type} ${doc?.filename || ''}`, index + 1)).padStart(2, '0')}`;
    return doc?.filename || `Documento ${index + 1}`;
}

function formularioDocsForSede(payload, sede) {
    const docs = payload?.analysis?.documents || payload?.documents || [];
    const sedeNumber = sede?.number || 1;
    return docs.filter(doc => {
        const type = String(doc.document_type || '');
        if (type === 'formulario_afiliacion') return true;
        if (!type.startsWith('anexo_sedes')) return false;
        const parsed = parseSedeNumber(`${type} ${doc.filename || ''}`, NaN);
        return Number.isFinite(parsed) ? parsed === sedeNumber : sedeNumber === 1;
    });
}

function renderFormularioPdfPanel(payload, sede) {
    const caseId = payload?.id || '';
    const docs = formularioDocsForSede(payload, sede);
    if (!caseId || !docs.length) return '<div class="form-empty">Sin PDFs de formulario o anexo para esta sede.</div>';
    const firstUrl = caseFileUrl(caseId, docs[0].filename || '', true);
    return `
        <div class="sede-pdf-tools">
            <select id="formPdfSelect" class="field-select sede-select">
                ${docs.map((doc, index) => `<option value="${index}" data-url="${escapeHtml(caseFileUrl(caseId, doc.filename || '', true))}">${escapeHtml(formularioDocLabel(doc, index))}</option>`).join('')}
            </select>
        </div>
        <iframe id="formPdfFrame" class="sede-pdf-frame" src="${escapeHtml(firstUrl)}" title="PDF formulario"></iframe>
    `;
}

function renderFormularioSedePanels(payload, sede, centroIndex = 'all') {
    return `
        <div class="sede-split-layout">
            <div class="sede-split-panel">
                ${renderFormularioTrabajadoresTable(filterSedeWorkers(sede, centroIndex))}
            </div>
            <div class="sede-split-panel">
                ${renderFormularioPdfPanel(payload, sede)}
            </div>
        </div>
    `;
}

function renderFormularioDocumentViewer(docItems) {
    if (!docItems.length) return '<div class="form-empty">Sin documentos para visualizar.</div>';
    return `
        <div class="form-document-tools">
            <select id="formDocumentSelect" class="field-select sede-select">
                ${docItems.map((item, index) => `
                    <option value="${index}">${escapeHtml(item.label || item.displayName || item.file)}</option>
                `).join('')}
            </select>
            <button class="btn-secondary form-document-reset-btn" id="resetFormDocumentFilterBtn" type="button" title="Mostrar todos los documentos">Todos</button>
        </div>
        <div id="formDocumentPreview" class="form-document-preview">
            <div class="loading-msg">Cargando documento...</div>
        </div>
    `;
}

function buildEmpresaInfoSections(formFields, profile, resumen, meta = {}) {
    const tipoTramite = formFields.tipo_tramite || profile.tipo_tramite || profile.tipo_afiliado || '';
    const tipoPersona = formFields.tipo_persona || profile.tipo_persona || '';
    const naturalezaJuridica = formFields.naturaleza_juridica_nombre;
    const tipoAportante = formFields.tipo_aportante_nombre;
    const empleadorDocumento = joinDocumentParts(
        formFields.empleador_tipo_documento,
        formFields.empleador_numero_documento_nit || resumen.nit || profile.nit
    );
    const representanteDocumento = joinDocumentParts(
        formFields.rep_legal_tipo_documento,
        formFields.rep_legal_numero_documento
    );
    const responsableSedeDocumento = joinDocumentParts(
        formFields.responsable_sede_principal_tipo_documento,
        formFields.responsable_sede_principal_numero_documento
    );
    const empleadorEntries = [
        ['tipo_tramite', tipoTramite],
        ['tipo_persona', tipoPersona],
        ['naturaleza_juridica_empleador', naturalezaJuridica],
        ['tipo_aportante', tipoAportante],
        ['empleador_razon_social', formFields.empleador_razon_social || resumen.empresa || profile.empresa],
        ['empleador_documento', empleadorDocumento],
        ['numero_contrato', meta.nroAfiliacion],
        ['fecha_radicacion', formFields.fecha_radicacion],
        ['fecha_inicio_cobertura', formFields.fecha_inicio_cobertura],
        ['lugar_afiliacion', formFields.lugar_afiliacion || formFields.nombre_lugar],
        ['codigo_lugar', formFields.codigo_lugar],
    ];
    const afiliacionEntries = [
        ['a_numero_sedes', formFields.a_numero_sedes || formFields.b_numero_sedes || profile.numero_sedes || resumen.numero_sedes],
        ['a_numero_centros_trabajo', formFields.a_numero_centros_trabajo || formFields.b_numero_centros_trabajo],
        ['a_numero_inicial_trabajadores_estudiantes', formFields.a_numero_inicial_trabajadores_estudiantes || formFields.b_numero_total_trabajadores_estudiantes || profile.numero_trabajadores || resumen.numero_trabajadores],
        ['a_valor_total_nomina', formFields.a_valor_total_nomina || formFields.b_monto_total_cotizacion || profile.nomina_total || resumen.nomina_total],
        ['a_clase_riesgo', formFields.a_clase_riesgo || formFields.b_clase_riesgo],
        ['a_codigo_actividad_economica_principal', formFields.a_codigo_actividad_economica_principal || formFields.b_codigo_actividad_economica_principal],
        ['b_arl_de_la_cual_se_traslada', formFields.b_arl_de_la_cual_se_traslada],
        ['estado_cuenta_empleador', formFields.estado_cuenta_empleador],
    ];
    const representanteEntries = [
        ['rep_legal_nombre_completo', formFields.rep_legal_nombre_completo],
        ['rep_legal_primer_nombre', formFields.rep_legal_primer_nombre],
        ['rep_legal_primer_apellido', formFields.rep_legal_primer_apellido],
        ['rep_legal_documento', representanteDocumento],
        ['rep_legal_correo', formFields.rep_legal_correo || formFields.rep_legal_correo_electronico],
    ];
    const sedePrincipalEntries = [
        ['sede_principal_codigo', formFields.sede_principal_codigo],
        ['sede_principal_nombre', formFields.sede_principal_nombre],
        ['sede_principal_direccion', formFields.sede_principal_direccion],
        ['sede_principal_municipio_distrito', formFields.sede_principal_municipio_distrito],
        ['sede_principal_departamento', formFields.sede_principal_departamento],
        ['sede_principal_zona', formFields.sede_principal_zona],
        ['sede_principal_localidad_comuna', formFields.sede_principal_localidad_comuna],
        ['sede_principal_telefono', formFields.sede_principal_telefono],
        ['sede_principal_correo', formFields.sede_principal_correo],
        ['responsable_sede_principal_primer_nombre', formFields.responsable_sede_principal_primer_nombre],
        ['responsable_sede_principal_primer_apellido', formFields.responsable_sede_principal_primer_apellido],
        ['responsable_sede_principal_documento', responsableSedeDocumento],
        ['responsable_sede_principal_correo', formFields.responsable_sede_principal_correo],
    ];
    const sections = [
        ['Datos del empleador', empleadorEntries],
        ['Afiliación / traslado', afiliacionEntries],
        ['Representante legal', representanteEntries],
        ['Sede principal', sedePrincipalEntries],
    ].filter(([, entries]) => entries.some(([, value]) => !isBlankFormValue(value)));

    return sections;
}

function renderEmpresaInfoContent(formFields, profile, resumen, meta = {}) {
    const sections = buildEmpresaInfoSections(formFields, profile, resumen, meta);
    if (!sections.length) return '';
    return `
        <div class="company-info-body">
            ${sections.map(([title, entries]) => `
                <section class="company-info-section">
                    <div class="company-info-section-title">${escapeHtml(title)}</div>
                    ${renderCompactInfoTable(entries)}
                </section>
            `).join('')}
        </div>
    `;
}

function commissionDocumentPriority(item) {
    const type = canonicalDocumentType(item?.type || item?.document_type || '');
    if (type === 'comision') return 1;
    if (type === 'entrega_documentos') return 2;
    return 0;
}

function renderComisionesInfoContent(payload) {
    const a = payload?.analysis || {};
    const intermediarios = a.validacion_resumen?.matches?.entrega_documentos_intermediario || {};
    const todosInterm = Array.isArray(intermediarios.todos_intermediarios) ? intermediarios.todos_intermediarios : [];
    const docs = buildDocItems(payload).filter(item => commissionDocumentPriority(item) > 0)
        .sort((left, right) => commissionDocumentPriority(left) - commissionDocumentPriority(right));

    let tableHtml = '';
    if (todosInterm.length) {
        tableHtml = `
            <section class="commission-info-section">
                <div class="company-info-section-title">Comisiones registradas</div>
                <table class="blocker-table commission-info-table">
                    <thead><tr><th>Código</th><th>Documento</th><th>Nombre</th><th>%</th></tr></thead>
                    <tbody>${todosInterm.map(row => `
                        <tr>
                            <td>${escapeHtml(String(row.codigo_intermediario || ''))}</td>
                            <td>${escapeHtml(String(row.vendedor_documento || ''))}</td>
                            <td>${escapeHtml(String(row.nombre_intermediario || ''))}</td>
                            <td>${escapeHtml(String(row.porcentaje_venta || ''))}%</td>
                        </tr>
                    `).join('')}</tbody>
                </table>
            </section>
        `;
    } else if (intermediarios.codigo_intermediario) {
        tableHtml = `
            <section class="commission-info-section">
                <div class="company-info-section-title">Comisiones leídas del OCR</div>
                <table class="blocker-table commission-info-table">
                    <thead><tr><th>Código</th><th>% Participación</th><th>Archivo</th></tr></thead>
                    <tbody><tr>
                        <td>${escapeHtml(String(intermediarios.codigo_intermediario || ''))}</td>
                        <td>${escapeHtml(String(intermediarios.porcentaje_venta || ''))}%</td>
                        <td>${escapeHtml(String(intermediarios.filename || ''))}</td>
                    </tr></tbody>
                </table>
            </section>
        `;
    } else {
        tableHtml = '<div class="form-empty">No se encontró información de comisiones. Verifica el documento de entrega de documentos.</div>';
    }

    const docsHtml = docs.length ? `
        <section class="commission-info-section">
            <div class="company-info-section-title">Documentos fuente</div>
            <div class="commission-doc-list">
                ${docs.map(item => `
                    <button class="btn-secondary commission-doc-jump" data-file="${escapeHtml(item.file)}" type="button">
                        ${escapeHtml(item.label || item.displayName || item.file)}
                    </button>
                `).join('')}
            </div>
        </section>
    ` : '<div class="form-empty">No hay documento de comisión o entrega de documentos asociado.</div>';

    return `
        <div class="commission-info-body">
            <div class="commission-info-title">Comisiones e intermediación</div>
            ${tableHtml}
            ${docsHtml}
        </div>
    `;
}

function renderFormularioReporte(container, payload) {
    const a = payload?.analysis || {};
    const wf = a.workflow_run || {};
    const xlsxProfile = a.xlsx_profile || {};
    const profile = xlsxProfile.profile || {};
    const formFields = xlsxProfile.form_fields || {};
    const report = wf.executive_report_final || wf.executive_report_precheck || a.reporte_ejecutivo || {};
    const resumen = report.resumen_ejecutivo || {};
    const decision = a.decision || {};

    const empresa = formFields.empleador_razon_social || resumen.empresa || profile.empresa || payload.label || 'n/d';
    const nroAfiliacion = resolveContractNumber(a, payload);
    const nroNit = formFields.empleador_numero_documento_nit || resumen.nit || profile.nit || '';
    const tipoNegocio = profile.tipo_negocio_detectado || '';
    const estado = resumen.estado || decision.recommended_status || wf.status || 'n/d';
    const estadoNorm = normalizeText(estado);
    const decisionStatus = normalizeText(decision.recommended_status || '');
    const approved = isCaseManuallyApproved(payload);
    const { hasActiveBlockers } = getCaseBlockerRecords(payload);
    const isNoAprobado = hasActiveBlockers && (estadoNorm.includes('no aprob') || estadoNorm.includes('rechaz') || normalizeText(wf.status || '') === 'stopped_prevalidacion');
    const isAprobable = isCaseAprobableAfterManualExceptions(payload, estado, decisionStatus);
    const stateClass = approved ? 'aprobado' : (isAprobable ? 'observado' : 'bloqueado');
    const stateLabel = approved ? 'APROBADO' : (isAprobable ? 'APROBABLE' : 'NO APROBADO');
    const fecha = resumen.fecha_proceso_human || formatDateTime(payload.updated_at);

    const totalSedes = formFields.a_numero_sedes || formFields.b_numero_sedes || profile.numero_sedes || resumen.numero_sedes || 'n/d';
    const sedesFormulario = buildFormularioSedes(payload, totalSedes);
    const caseId = payload?.id || activeCaseId || '';
    const docItems = buildDocItems(payload);
    let currentFormDocItems = docItems;
    const sedeGroupNames = sedesFormulario.map((sede, index) => (
        sede.sourceName || `Sede ${String(sede.number || index + 1).padStart(2, '0')} - Trabajadores`
    ));
    const docsBySede = groupSedeDocumentsByAssignment(payload, sedeGroupNames);

    container.innerHTML = `
        <div class="report-case-summary">
            <span class="report-state-badge ${stateClass}">${escapeHtml(stateLabel)}</span>
            <div class="report-empresa">
                <div class="report-empresa-name">${escapeHtml(empresa)}</div>
                <small class="report-empresa-meta">
                    ${nroAfiliacion ? `Contrato: <strong>${escapeHtml(nroAfiliacion)}</strong>` : ''}
                    ${nroNit ? `NIT: <strong>${escapeHtml(Number(nroNit).toLocaleString('es-CO'))}</strong>` : ''}
                    ${tipoNegocio ? `Tipo de negocio: <strong>${escapeHtml(tipoNegocio)}</strong>` : ''}
                </small>
            </div>
            <div class="report-header-actions">
                ${isAprobable && !approved ? `<button class="btn-success" id="approveCaseBtn" type="button">Aprobar contrato</button>` : ''}
                <button class="btn-secondary" id="companyInfoToggle" type="button" aria-expanded="false" aria-controls="formCompanyInfoPanel">Información Empresa</button>
                <button class="btn-secondary" id="commissionsInfoToggle" type="button" aria-expanded="false" aria-controls="formCommissionsInfoPanel">Comisiones</button>
                <button class="btn-secondary" data-action="clasificacion" data-case="${escapeHtml(caseId)}" type="button">Ver documentos</button>
            </div>
        </div>
        <div class="report-body report-body-form">
            <div class="form-review-split">
                <section class="form-review-pane form-review-info">
                    <div id="formSedeInfoContent" class="form-sede-info-content">
                        <div class="sede-selector-panel form-review-selectors">
                            <select id="formSedeSelect" class="field-select sede-select" ${sedesFormulario.length ? '' : 'disabled'}>
                                ${sedesFormulario.length
                                    ? sedesFormulario.map((sede, index) => `<option value="${index}">${escapeHtml(sede.label)}</option>`).join('')
                                    : '<option>Sin sedes</option>'}
                            </select>
                            <select id="formCentroSelect" class="field-select sede-select" ${sedesFormulario.length ? '' : 'disabled'}>
                                ${(sedesFormulario[0]?.centros || []).length
                                    ? `<option value="all">Todos</option>${sedesFormulario[0].centros.map((centro, index) => `<option value="${index}">${escapeHtml(centroTrabajoLabel(centro, index))}</option>`).join('')}`
                                    : '<option>Sin centros</option>'}
                            </select>
                            <button class="btn-secondary form-toggle-info-btn" id="toggleSedeInfoBtn" type="button" aria-pressed="false">Ocultar info</button>
                        </div>
                        <div class="sede-detail-panel" id="formSedeDetail">
                            ${renderFormularioSedeDetalle(sedesFormulario[0])}
                        </div>
                        <div class="form-workers-panel" id="formWorkersPanel">
                            ${renderFormularioTrabajadoresTable(filterSedeWorkers(sedesFormulario[0], 'all'))}
                        </div>
                    </div>
                    <div class="form-company-info-panel" id="formCompanyInfoPanel" hidden>
                        ${renderEmpresaInfoContent(formFields, profile, resumen, { nroAfiliacion, fecha }) || '<div class="form-empty">Sin información de empresa recuperada.</div>'}
                    </div>
                    <div class="form-commissions-info-panel" id="formCommissionsInfoPanel" hidden>
                        ${renderComisionesInfoContent(payload)}
                    </div>
                </section>
                <section class="form-review-pane form-review-documents">
                    ${renderFormularioDocumentViewer(docItems)}
                </section>
            </div>
        </div>
    `;

    const sedeSelect = container.querySelector('#formSedeSelect');
    const centroSelect = container.querySelector('#formCentroSelect');
    const sedeDetail = container.querySelector('#formSedeDetail');
    const workersPanel = container.querySelector('#formWorkersPanel');
    const renderDocumentSelectOptions = (items) => {
        const documentSelect = container.querySelector('#formDocumentSelect');
        const documentPreview = container.querySelector('#formDocumentPreview');
        if (!documentSelect || !documentPreview) return;
        currentFormDocItems = items;
        if (!items.length) {
            documentSelect.innerHTML = '<option value="">Sin documentos para esta sede</option>';
            documentSelect.disabled = true;
            documentPreview.innerHTML = '<div class="form-empty">Sin documentos para esta sede.</div>';
            return;
        }
        documentSelect.disabled = false;
        documentSelect.innerHTML = items.map((item, index) => `
            <option value="${index}">${escapeHtml(item.label || item.displayName || item.file)}</option>
        `).join('');
        documentSelect.value = '0';
    };
    const renderSelectedDocument = async () => {
        const documentSelect = container.querySelector('#formDocumentSelect');
        const documentPreview = container.querySelector('#formDocumentPreview');
        if (!documentSelect || !documentPreview || !currentFormDocItems.length) return;
        const item = currentFormDocItems[Number(documentSelect.value) || 0];
        if (item) await renderDocPreview(documentPreview, caseId, item);
    };
    const filterDocumentsForSede = async (sede, autoPreview = true) => {
        if (!sede) return;
        const groupName = sede.sourceName || `Sede ${String(sede.number || 1).padStart(2, '0')} - Trabajadores`;
        const filenames = new Set((docsBySede[groupName] || []).map(doc => doc.filename).filter(Boolean));
        const filteredItems = docItems.filter(item => filenames.has(item.file));
        renderDocumentSelectOptions(filteredItems);
        if (autoPreview) await renderSelectedDocument();
    };
    const resetDocumentFilter = async () => {
        renderDocumentSelectOptions(docItems);
        await renderSelectedDocument();
    };
    const bindDocumentViewer = async () => {
        const documentSelect = container.querySelector('#formDocumentSelect');
        if (!documentSelect || !docItems.length) return;
        documentSelect.addEventListener('change', renderSelectedDocument);
        container.querySelector('#resetFormDocumentFilterBtn')?.addEventListener('click', resetDocumentFilter);
        renderDocumentSelectOptions(docItems);
        await renderSelectedDocument();
    };
    const renderSelectedSede = () => {
        const selectedSede = sedesFormulario[Number(sedeSelect?.value) || 0];
        const centros = selectedSede?.centros || [];
        if (centroSelect) {
            centroSelect.innerHTML = centros.length
                ? `<option value="all">Todos</option>${centros.map((centro, index) => `<option value="${index}">${escapeHtml(centroTrabajoLabel(centro, index))}</option>`).join('')}`
                : '<option>Sin centros</option>';
            centroSelect.disabled = !selectedSede;
        }
        if (sedeDetail) sedeDetail.innerHTML = renderFormularioSedeDetalle(selectedSede, 'all');
        if (workersPanel) workersPanel.innerHTML = renderFormularioTrabajadoresTable(filterSedeWorkers(selectedSede, 'all'));
        filterDocumentsForSede(selectedSede);
    };
    sedeSelect?.addEventListener('change', () => {
        renderSelectedSede();
    });
    centroSelect?.addEventListener('change', () => {
        const selectedSede = sedesFormulario[Number(sedeSelect?.value) || 0];
        const selectedCentro = centroSelect.value === 'all' ? 'all' : Number(centroSelect.value) || 0;
        if (sedeDetail) sedeDetail.innerHTML = renderFormularioSedeDetalle(selectedSede, selectedCentro);
        if (workersPanel) workersPanel.innerHTML = renderFormularioTrabajadoresTable(filterSedeWorkers(selectedSede, selectedCentro));
    });
    container.querySelectorAll('[data-action]').forEach(btn => {
        btn.addEventListener('click', () => handleCaseAction(btn.dataset.action, btn.dataset.case, btn.dataset.file));
    });
    container.querySelector('#approveCaseBtn')?.addEventListener('click', () => approveCaseManually(caseId, container));
    const companyInfoToggle = container.querySelector('#companyInfoToggle');
    const commissionsInfoToggle = container.querySelector('#commissionsInfoToggle');
    const companyInfoPanel = container.querySelector('#formCompanyInfoPanel');
    const commissionsInfoPanel = container.querySelector('#formCommissionsInfoPanel');
    const sedeInfoContent = container.querySelector('#formSedeInfoContent');
    const toggleSedeInfoBtn = container.querySelector('#toggleSedeInfoBtn');
    const formInfoPane = container.querySelector('.form-review-info');
    const setLeftPanel = (panelName) => {
        if (!companyInfoPanel || !commissionsInfoPanel || !sedeInfoContent) return;
        const showCompany = panelName === 'company';
        const showCommissions = panelName === 'commissions';
        companyInfoPanel.hidden = !showCompany;
        commissionsInfoPanel.hidden = !showCommissions;
        sedeInfoContent.hidden = showCompany || showCommissions;
        companyInfoToggle?.setAttribute('aria-expanded', showCompany ? 'true' : 'false');
        commissionsInfoToggle?.setAttribute('aria-expanded', showCommissions ? 'true' : 'false');
        if (companyInfoToggle) companyInfoToggle.textContent = showCompany ? 'Ocultar información' : 'Información Empresa';
        if (commissionsInfoToggle) commissionsInfoToggle.textContent = showCommissions ? 'Ocultar comisiones' : 'Comisiones';
    };
    const selectDocumentByFile = async (filename) => {
        if (!filename) return false;
        renderDocumentSelectOptions(docItems);
        const documentSelect = container.querySelector('#formDocumentSelect');
        if (!documentSelect) return false;
        const index = currentFormDocItems.findIndex(item => item.file === filename);
        if (index < 0) return false;
        documentSelect.value = String(index);
        await renderSelectedDocument();
        return true;
    };
    const selectCommissionsDocument = async () => {
        const commissionDoc = docItems
            .filter(item => commissionDocumentPriority(item) > 0)
            .sort((left, right) => commissionDocumentPriority(left) - commissionDocumentPriority(right))[0];
        const selected = await selectDocumentByFile(commissionDoc?.file || '');
        if (!selected) showToast('No encontré un documento de comisiones para mostrar.', 'warn', 3500);
    };
    companyInfoToggle?.addEventListener('click', () => {
        const showingCompany = companyInfoPanel && !companyInfoPanel.hidden;
        setLeftPanel(showingCompany ? 'sede' : 'company');
    });
    commissionsInfoToggle?.addEventListener('click', async () => {
        const showingCommissions = commissionsInfoPanel && !commissionsInfoPanel.hidden;
        setLeftPanel(showingCommissions ? 'sede' : 'commissions');
        if (!showingCommissions) await selectCommissionsDocument();
    });
    container.querySelectorAll('.commission-doc-jump').forEach(btn => {
        btn.addEventListener('click', () => selectDocumentByFile(btn.dataset.file || ''));
    });
    toggleSedeInfoBtn?.addEventListener('click', () => {
        if (!formInfoPane || !sedeDetail) return;
        const hidden = formInfoPane.classList.toggle('hide-sede-info');
        toggleSedeInfoBtn.textContent = hidden ? 'Mostrar info' : 'Ocultar info';
        toggleSedeInfoBtn.setAttribute('aria-pressed', hidden ? 'true' : 'false');
    });
    bindDocumentViewer();
}

function renderReporte(container, payload) {
    const a = payload?.analysis || {};
    const wf = a.workflow_run || {};
    const profile = (a.xlsx_profile || {}).profile || {};
    const report = wf.executive_report_final || wf.executive_report_precheck || a.reporte_ejecutivo || {};
    const resumen = report.resumen_ejecutivo || {};
    const decision = a.decision || {};
    const caseId = payload?.id || '';

    const empresa = resumen.empresa || profile.empresa || payload.label || 'n/d';
    const nit = resumen.nit || profile.nit || 'n/d';
    const nroAfiliacion = resolveContractNumber(a, payload);
    const estado = resumen.estado || decision.recommended_status || wf.status || 'n/d';
    const trabajadores = resumen.numero_trabajadores ?? profile.numero_trabajadores ?? 'n/d';
    const sedes = resumen.numero_sedes ?? profile.numero_sedes ?? 'n/d';
    const nomina = profile.nomina_total ? formatCurrency(profile.nomina_total) : 'n/d';
    const fecha = resumen.fecha_proceso_human || (() => {
        const raw = payload.updated_at || '';
        if (!raw) return 'n/d';
        const d = new Date(raw);
        const fecha = d.toLocaleDateString('es-CO', { day:'numeric', month:'long', year:'numeric' });
        const hora = d.toLocaleTimeString('es-CO', { hour:'2-digit', minute:'2-digit' });
        return `${fecha} ${hora}`;
    })();
    const has926 = Boolean((wf.output_926||{}).legacy?.ok);
    const filename926 = (wf.output_926||{}).legacy?.filename || 'archivo_core.txt';

    const blockers = Array.isArray(decision.blockers) ? decision.blockers :
                     Array.isArray(report.bloqueantes) ? report.bloqueantes : [];
    const blockerRecords = getValidationBlockerRecords(payload);
    const acceptedExceptions = getAcceptedValidationExceptions(payload);
    const observaciones = Array.isArray(report.observaciones) ? report.observaciones : [];
    const estadoNorm = normalizeText(estado);
    const decisionStatus = normalizeText(decision.recommended_status || '');
    const hasActiveBlockers = blockers.length > 0 || blockerRecords.length > 0;
    const approved = isCaseManuallyApproved(payload);
    const isAprobable = isCaseAprobableAfterManualExceptions(payload, estado, decisionStatus);
    const isNoAprobado = !isAprobable && (normalizeText(wf.status||'') === 'stopped_prevalidacion' || estadoNorm.includes('no aprob'));
    const stateClass = approved ? 'aprobado' : (isAprobable ? 'observado' : 'bloqueado');
    const stateLabel = approved ? 'APROBADO' : (isAprobable ? 'APROBABLE' : 'NO APROBADO');

    // Extraer datos de comparación de razón social
    const vrMatches = (a.validacion_resumen?.matches || a.reporte_ejecutivo?.matches || {});
    const empMatch = vrMatches.empresa_nombre || {};
    const camaraName = empMatch.camara || '';
    const formularioName = empMatch.formulario || '';

    // Función para enriquecer texto de bloqueante con contexto
    function enrichBlockerText(txt) {
        if (!txt) return '';
        const lower = txt.toLowerCase();
        if (lower.includes('razón social') || lower.includes('razon social')) {
            if (camaraName || formularioName) {
                const camaraDisplay = camaraName || '(no leído por OCR)';
                const formDisplay = formularioName || profile.empresa || '(no disponible)';
                return `${txt}\n→ Cámara: "${camaraDisplay}"\n→ Formulario/XLSX: "${formDisplay}"`;
            }
        }
        return txt;
    }

    // Documentos del contrato para comparación rápida — todos
    const docItems = buildDocItems(payload);

    // Parser de bloqueantes para detectar fuente y contexto
    function parseBlocker(b) {
        const txt = blockerText(b);
        const lower = txt.toLowerCase();
        let sourceType = null; // 'xlsx_row', 'pdf_doc', 'cross_compare'
        let sheetName = '';
        let rowNum = '';
        let docType = b?.document_type || b?.tipo_documento || '';
        let workerDoc = '';
        let actionLabel = '';

        // XLSX - salario, correo, duplicado, tipo trabajador, AFP, EPS
        const sheetMatch = txt.match(/Sede\s+\d+\s*[-–]\s*Trabajadores/i) ||
                           txt.match(/SEDE\s+\d+/i);
        const filaMatch = txt.match(/fila\s+(\d+)/i);
        const docMatch = txt.match(/(\d{6,12})/);

        if (sheetMatch || filaMatch || lower.includes('xlsx') || lower.includes('salario') ||
            lower.includes('correo') || lower.includes('duplicado') || lower.includes('fila') ||
            lower.includes('tipo de trabajador') || lower.includes('afp') || lower.includes('eps')) {
            sourceType = 'xlsx_row';
            sheetName = sheetMatch ? sheetMatch[0] : '';
            rowNum = filaMatch ? filaMatch[1] : '';
            workerDoc = docMatch ? docMatch[1] : '';
            actionLabel = sheetName ? `Ver fila · ${sheetName}` : (rowNum ? `Ver fila ${rowNum}` : 'Ver en XLSX');
        }
        // Razón social / cámara / documento
        else if (lower.includes('razón social') || lower.includes('razon social') ||
                 lower.includes('cámara') || lower.includes('camara') ||
                 lower.includes('cedula') || lower.includes('cédula') ||
                 lower.includes('representante')) {
            sourceType = 'pdf_doc';
            docType = docType || (lower.includes('cámara') || lower.includes('camara') ? 'camara_comercio' :
                                  lower.includes('cedula') || lower.includes('cédula') ? 'cedula' : 'formulario_afiliacion');
            actionLabel = `Ver ${getReviewTypeLabel(docType)}`;
        }

        return { sourceType, sheetName, rowNum, workerDoc, docType, actionLabel };
    }

    // Workers del XLSX para mostrar en panel
    const xlsxRecords = (a.xlsx_profile?.records || []);

    container.innerHTML = `
        <div class="report-header">
            <span class="report-state-badge ${stateClass}">${escapeHtml(stateLabel)}</span>
            <div>
                <div class="report-empresa">${escapeHtml(empresa)}</div>
                <div class="report-nit">
                    NIT: <strong>${escapeHtml(nit)}</strong>${nroAfiliacion ? ` · Contrato <strong>${escapeHtml(nroAfiliacion)}</strong>` : ''}
                    · ${escapeHtml(fecha)}
                </div>
            </div>
            <div style="margin-left:auto;display:flex;gap:8px;align-items:center">
                ${isAprobable && !approved ? `<button class="btn-success" id="approveCaseBtn" type="button">Aprobar contrato</button>` : ''}
                <button class="btn-secondary" data-action="clasificacion" data-case="${escapeHtml(caseId)}" type="button">Ver documentos</button>
                ${has926 ? `<button class="btn-primary" data-action="descargar926" data-case="${escapeHtml(caseId)}" data-file="${escapeHtml(filename926)}" type="button">Descargar plano</button>` : ''}
                ${!isAprobable ? `<button class="btn-warn" id="reprocesarBtn" data-case="${escapeHtml(caseId)}" type="button" title="Volver a ejecutar la validación documental">↺ Reprocesar</button>` : ''}
            </div>
        </div>
        <div id="reprocesarStatus" style="display:none;padding:8px 16px;font-size:12px;background:var(--c-info-bg);color:var(--c-info);border-bottom:1px solid var(--c-border)"></div>
        <div class="report-body">
            <div class="report-section">
                <div class="report-section-title">Datos del contrato</div>
                <div class="report-grid">
                    <div class="report-kv">
                        <div class="report-kv-label">Sedes</div>
                        <div class="report-kv-val">${escapeHtml(String(sedes))}</div>
                    </div>
                    <div class="report-kv">
                        <div class="report-kv-label">Nómina total</div>
                        <div class="report-kv-val">${escapeHtml(nomina)}</div>
                    </div>
                </div>
                <div id="reportSedesInline" style="margin-top:12px"></div>
            </div>
            ${blockers.length ? `
                <div class="report-section">
                    <div class="report-section-title">Bloqueantes (${blockers.length}) · haz clic en uno para ver el documento fuente</div>
                    <div class="report-blockers-list" id="reportBlockersList">
                        ${(blockerRecords.length ? blockerRecords : blockers.map((b, i) => ({ message: blockerText(b), code: 'VALIDATION_ALERT', fingerprint: '', index: i }))).map((b, i) => {
                            const raw = b.message || blockerText(b);
                            const txt = enrichBlockerText(raw);
                            const parsed = parseBlocker(b);
                            const isMultiLine = txt.includes('\n');
                            const isClickable = parsed.sourceType !== null;
                            return `
                                <div class="report-blocker-interactive ${isClickable?'clickable':''}"
                                    data-blocker-idx="${i}"
                                    data-source-type="${escapeHtml(parsed.sourceType||'')}"
                                    data-sheet="${escapeHtml(parsed.sheetName)}"
                                    data-row="${escapeHtml(parsed.rowNum)}"
                                    data-worker-doc="${escapeHtml(parsed.workerDoc)}"
                                    data-doc-type="${escapeHtml(parsed.docType)}"
                                    ${isClickable ? 'role="button" tabindex="0"' : ''}>
                                    <div class="report-blocker-main">
                                        <span class="report-blocker-icon">✗</span>
                                        <div class="report-blocker-content">
                                            ${isMultiLine
                                                ? txt.split('\n').map((line, li) => li === 0
                                                    ? `<div class="report-blocker-text">${escapeHtml(line)}</div>`
                                                    : `<div class="report-blocker-meta" style="color:var(--c-text-2);margin-top:3px">${escapeHtml(line)}</div>`
                                                ).join('')
                                                : `<div class="report-blocker-text">${escapeHtml(txt)}</div>`
                                            }
                                        </div>
                                    </div>
                                    <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
                                        ${isClickable ? `<span class="report-blocker-action-hint">${escapeHtml(parsed.actionLabel)} →</span>` : ''}
                                        ${validationExceptionButtonHtml(b, i)}
                                    </div>
                                </div>
                            `;
                        }).join('')}
                    </div>
                    <div id="reportBlockerPanel" class="report-blocker-panel hidden"></div>
                    ${docItems.length ? `
                        <div class="report-docs-quick">
                            <div class="report-section-title" style="margin-top:14px">Documentos del contrato · abre y compara</div>
                            <div class="report-docs-chips">
                                ${docItems.map(d => `
                                    <button class="doc-chip" data-case="${escapeHtml(caseId)}" data-file="${escapeHtml(d.file)}" data-display="${escapeHtml(d.displayName||d.file)}" type="button">
                                        ${escapeHtml(d.label)}
                                    </button>
                                `).join('')}
                            </div>
                        </div>
                    ` : ''}
                </div>
            ` : '<div class="empty-state" style="color:var(--c-ok);padding:16px">✓ Sin bloqueantes — contrato aprobable</div>'}
            ${acceptedExceptions.length ? `
                <div class="report-section">
                    <div class="report-section-title">Hallazgos aceptados manualmente (${acceptedExceptions.length})</div>
                    <div style="display:flex;flex-direction:column;gap:6px">
                        ${acceptedExceptions.map(item => `
                            <div style="padding:8px 12px;background:var(--c-ok-bg);border-radius:var(--radius);font-size:12px;color:var(--c-ok)">
                                <strong>Aceptado para este contrato:</strong> ${escapeHtml(item.message || '')}
                                <div style="margin-top:3px;color:var(--c-text-2)">Motivo: ${escapeHtml(item.accepted_reason || item.reason || 'Validado manualmente')}</div>
                            </div>
                        `).join('')}
                    </div>
                </div>
            ` : ''}
            ${observaciones.length ? `
                <div class="report-section">
                    <div class="report-section-title">Observaciones</div>
                    <div style="display:flex;flex-direction:column;gap:6px">
                        ${observaciones.slice(0,10).map(o => `
                            <div style="padding:8px 12px;background:var(--c-warn-bg);border-radius:var(--radius);font-size:12px;color:var(--c-warn)">
                                ${escapeHtml(typeof o === 'string' ? o : o.message || JSON.stringify(o))}
                            </div>
                        `).join('')}
                    </div>
                </div>
            ` : ''}
        </div>
        <div class="report-doc-preview hidden" id="reportDocPreview">
            <div class="section-card-head">
                <div class="section-title" id="reportDocPreviewTitle">Documento</div>
                <button class="btn-icon" id="reportDocPreviewClose" type="button">✕</button>
            </div>
            <div id="reportDocPreviewBody" style="min-height:400px"></div>
        </div>
    `;

    // Botones de acción del header
    container.querySelectorAll('[data-action]').forEach(btn => {
        btn.addEventListener('click', () => handleCaseAction(btn.dataset.action, btn.dataset.case, btn.dataset.file));
    });
    container.querySelector('#approveCaseBtn')?.addEventListener('click', () => approveCaseManually(caseId, container));
    container.querySelectorAll('.validation-exception-btn').forEach(btn => {
        btn.addEventListener('click', async (event) => {
            event.stopPropagation();
            const records = blockerRecords.length ? blockerRecords : blockers.map((b, i) => ({ message: blockerText(b), code: 'VALIDATION_ALERT', fingerprint: '', index: i }));
            const record = records[Number(btn.dataset.blockerIdx || 0)];
            setValidationExceptionButtonsLoading(container, btn, true);
            try {
                const saved = await acceptValidationException(caseId, record);
                if (!saved) setValidationExceptionButtonsLoading(container, btn, false);
            }
            catch(e) {
                showToast('No pude guardar la excepción: ' + e.message, 'err', 6000);
                setValidationExceptionButtonsLoading(container, btn, false);
            }
        });
    });

    // Chips de documentos → abrir preview inline
    container.querySelectorAll('.doc-chip').forEach(chip => {
        chip.addEventListener('click', async () => {
            const previewSection = document.getElementById('reportDocPreview');
            const previewTitle = document.getElementById('reportDocPreviewTitle');
            const previewBody = document.getElementById('reportDocPreviewBody');
            const display = chip.dataset.display || chip.dataset.file;
            if (previewTitle) previewTitle.textContent = display;
            if (previewSection) previewSection.classList.remove('hidden');
            if (previewBody) previewBody.innerHTML = '<div class="loading-msg">Cargando...</div>';
            container.querySelectorAll('.doc-chip').forEach(c => c.classList.remove('active'));
            chip.classList.add('active');
            if (previewBody) {
                const item = docItems.find(d => d.file === chip.dataset.file);
                if (item) await renderDocPreview(previewBody, chip.dataset.case, item);
            }
            previewSection?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        });
    });

    // Cerrar preview
    document.getElementById('reportDocPreviewClose')?.addEventListener('click', () => {
        document.getElementById('reportDocPreview')?.classList.add('hidden');
        container.querySelectorAll('.doc-chip').forEach(c => c.classList.remove('active'));
    });

    // ── Bloqueantes clickeables ──────────────────────────────
    container.querySelectorAll('.report-blocker-interactive.clickable').forEach(el => {
        el.addEventListener('click', () => {
            const panel = document.getElementById('reportBlockerPanel');
            if (!panel) return;
            const sourceType = el.dataset.sourceType;
            const sheet = el.dataset.sheet;
            const row = el.dataset.row;
            const workerDoc = el.dataset.workerDoc;
            const docType = el.dataset.docType;

            // Toggle si ya está abierto el mismo
            const alreadyOpen = !panel.classList.contains('hidden') && panel.dataset.activeBlocker === el.dataset.blockerIdx;
            container.querySelectorAll('.report-blocker-interactive').forEach(b => b.classList.remove('active'));
            if (alreadyOpen) { panel.classList.add('hidden'); return; }
            el.classList.add('active');
            panel.dataset.activeBlocker = el.dataset.blockerIdx;
            panel.classList.remove('hidden');

            if (sourceType === 'xlsx_row') {
                // Buscar trabajadores relevantes
                const rowInt = parseInt(row) || 0;
                const matches = xlsxRecords.filter(r => {
                    const rDoc = String(r.documento||r.cedula||r.doc||'');
                    if (workerDoc && rDoc === workerDoc) return true;
                    if (sheet && String(r.sede||r.sheet||'').toLowerCase().includes(sheet.toLowerCase())) return true;
                    return false;
                }).slice(0, 15);

                if (matches.length) {
                    panel.innerHTML = `
                        <div class="blocker-panel-head">
                            <span class="blocker-panel-title">📋 ${escapeHtml(sheet || 'Trabajadores relevantes')}</span>
                            ${row ? `<span style="font-size:11px;color:var(--c-text-2)">Fila ${escapeHtml(row)}</span>` : ''}
                            <button class="btn-icon" id="blockerPanelClose">✕</button>
                        </div>
                        <div style="overflow-x:auto">
                        <table class="blocker-table">
                            <thead><tr>
                                <th>Documento</th><th>Nombre</th><th>Sede</th>
                                <th>Salario</th><th>Correo</th>
                            </tr></thead>
                            <tbody>
                            ${matches.map(r => `<tr class="${workerDoc && String(r.documento||r.cedula||r.doc||'') === workerDoc ? 'blocker-row-highlight' : ''}">
                                <td>${escapeHtml(String(r.documento||r.cedula||r.doc||''))}</td>
                                <td>${escapeHtml(String(r.nombre||r.name||[r.primer_nombre,r.segundo_nombre,r.primer_apellido,r.segundo_apellido].filter(Boolean).join(' ')||''))}</td>
                                <td>${escapeHtml(String(r.sede||r.sheet||''))}</td>
                                <td>${escapeHtml(String(r.salario||r.salary||''))}</td>
                                <td>${escapeHtml(String(r.correo||r.email||''))}</td>
                            </tr>`).join('')}
                            </tbody>
                        </table>
                        </div>
                    `;
                } else {
                    // Sin registros exactos — mostrar contexto del bloqueante
                    // Buscar el XLSX del expediente — primero en docItems, luego en payload.files
                    let xlsxDoc = docItems.find(d => d.kind === 'xlsx');
                    if (!xlsxDoc && Array.isArray(payload?.files)) {
                        const pf = payload.files.find(f => /\.(xlsx|xlsm|xls)$/i.test(f.filename||f.name||''));
                        if (pf) {
                            const fname = pf.filename || pf.name || '';
                            xlsxDoc = { file: fname, kind: 'xlsx', displayName: fname };
                        }
                    }
                    panel.innerHTML = `
                        <div class="blocker-panel-head">
                            <span class="blocker-panel-title">📋 ${escapeHtml(sheet || 'XLSX')}</span>
                            ${row ? `<span style="font-size:11px;color:var(--c-text-2)">Fila ${escapeHtml(row)}</span>` : ''}
                            <button class="btn-icon" id="blockerPanelClose">✕</button>
                        </div>
                        <div style="padding:14px 16px">
                            <div style="font-size:12px;color:var(--c-text-2);margin-bottom:12px">
                                Error detectado en el XLSX · hoja <strong>${escapeHtml(sheet||'Trabajadores')}</strong>${row ? `, fila <strong>${escapeHtml(row)}</strong>` : ''}.
                                ${workerDoc ? `<br>Documento: <strong style="color:var(--c-err)">${escapeHtml(workerDoc)}</strong>` : ''}
                            </div>
                            ${xlsxDoc ? `
                            <div style="display:flex;gap:8px;flex-wrap:wrap">
                                <a class="btn-primary" href="${escapeHtml(caseFileUrl(caseId, xlsxDoc.file))}" 
                                   download="${escapeHtml(xlsxDoc.displayName||xlsxDoc.file)}"
                                   style="font-size:12px;padding:7px 14px;display:inline-flex;align-items:center;gap:6px">
                                   ⬇ Descargar XLSX
                                </a>
                                <button class="btn-secondary" id="blockerOpenClassif" 
                                    style="font-size:12px;padding:7px 14px" type="button">
                                    📂 Ver en Clasificación
                                </button>
                            </div>` : `
                            <div style="font-size:11px;color:var(--c-text-3)">
                                XLSX no encontrado en el expediente.
                            </div>`}
                        </div>
                    `;
                    // Botón para ir a clasificación con este caso seleccionado
                    panel.querySelector('#blockerOpenClassif')?.addEventListener('click', () => {
                        switchView('clasificacion');
                        loadClassifForCase(caseId);
                    });
                }
            } else if (sourceType === 'pdf_doc') {
                // Buscar el PDF correspondiente y mostrarlo
                const doc = docItems.find(d => d.type === docType || d.type?.includes(docType));
                if (doc) {
                    panel.innerHTML = `
                        <div class="blocker-panel-head">
                            <span class="blocker-panel-title">📄 ${escapeHtml(getReviewTypeLabel(docType))}</span>
                            <button class="btn-icon" id="blockerPanelClose">✕</button>
                        </div>
                        <div id="blockerDocPreview" style="min-height:300px">
                            <div class="loading-msg">Abriendo documento...</div>
                        </div>
                    `;
                    const previewEl = panel.querySelector('#blockerDocPreview');
                    if (previewEl) renderDocPreview(previewEl, caseId, doc);
                } else {
                    panel.innerHTML = `
                        <div class="blocker-panel-head">
                            <span class="blocker-panel-title">📄 ${escapeHtml(getReviewTypeLabel(docType))}</span>
                            <button class="btn-icon" id="blockerPanelClose">✕</button>
                        </div>
                        <div style="padding:12px;font-size:12px;color:var(--c-text-2)">
                            Documento <strong>${escapeHtml(getReviewTypeLabel(docType))}</strong> no encontrado en este expediente.
                        </div>
                    `;
                }
            }

            panel.querySelector('#blockerPanelClose')?.addEventListener('click', () => {
                panel.classList.add('hidden');
                el.classList.remove('active');
            });
            panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        });
    });

    // ── Tarjetas Trabajadores / Sedes clickeables ────────────
    container.querySelectorAll('.report-kv.clickable').forEach(kv => {
        kv.addEventListener('click', () => {
            const panelType = kv.dataset.panel;
            const dataPanel = document.getElementById('reportDataPanel');
            if (!dataPanel) return;
            const alreadyOpen = !dataPanel.classList.contains('hidden') && dataPanel.dataset.panel === panelType;
            container.querySelectorAll('.report-kv.clickable').forEach(k => k.classList.remove('active'));
            if (alreadyOpen) { dataPanel.classList.add('hidden'); return; }
            kv.classList.add('active');
            dataPanel.dataset.panel = panelType;
            dataPanel.classList.remove('hidden');

            if (panelType === 'workers') {
                const workers = xlsxRecords.slice(0, 100);
                if (!workers.length) {
                    dataPanel.innerHTML = `<div style="padding:12px;font-size:12px;color:var(--c-text-2)">No hay registros de trabajadores disponibles.</div>`;
                } else {
                    dataPanel.innerHTML = `
                        <div class="blocker-panel-head">
                            <span class="blocker-panel-title">👷 Trabajadores (${workers.length}${xlsxRecords.length>100?' de '+xlsxRecords.length:''})</span>
                            <button class="btn-icon" id="dataPanelClose">✕</button>
                        </div>
                        <div style="overflow-x:auto;max-height:300px;overflow-y:auto">
                        <table class="blocker-table">
                            <thead><tr><th>Documento</th><th>Nombre</th><th>Sede</th><th>Salario</th><th>AFP</th><th>EPS</th></tr></thead>
                            <tbody>${workers.map(r => `<tr>
                                <td>${escapeHtml(String(r.documento||r.cedula||r.doc||''))}</td>
                                <td>${escapeHtml(String(r.nombre||r.name||[r.primer_nombre,r.segundo_nombre,r.primer_apellido,r.segundo_apellido].filter(Boolean).join(' ')||''))}</td>
                                <td>${escapeHtml(String(r.sede||r.sheet||''))}</td>
                                <td>${escapeHtml(String(r.salario||r.salary||''))}</td>
                                <td>${escapeHtml(String(r.afp||''))}</td>
                                <td>${escapeHtml(String(r.eps||''))}</td>
                            </tr>`).join('')}</tbody>
                        </table>
                        </div>
                    `;
                }
            } else if (panelType === 'sedes') {
                const sedeRecords = a.xlsx_profile?.records || [];
                const workerCounts = a.xlsx_profile?.worker_sheet_counts || {};
                const salaryCounts = a.xlsx_profile?.worker_sheet_salary_totals || {};

                // Agrupar por sede
                const bySede = {};
                for (const r of sedeRecords) {
                    const sede = r._sheet || 'Sin sede';
                    if (!bySede[sede]) bySede[sede] = [];
                    bySede[sede].push(r);
                }
                // Agrupar por centro de trabajo
                const byCentro = {};
                for (const r of sedeRecords) {
                    const centro = String(r.codigo_del_centro_de_trabajo || 'Sin centro');
                    if (!byCentro[centro]) byCentro[centro] = [];
                    byCentro[centro].push(r);
                }

                const sedeNames = Object.keys(workerCounts).length ? Object.keys(workerCounts) : Object.keys(bySede);

                if (!sedeNames.length && !sedeRecords.length) {
                    dataPanel.innerHTML = `<div style="padding:12px;font-size:12px;color:var(--c-text-2)">No hay información de sedes disponible.</div>`;
                } else {
                    const cols = [
                        {k: 'numero_de_identificacion', l: 'Documento'},
                        {k: ['primer_nombre','segundo_nombre','primer_apellido','segundo_apellido'], l: 'Nombre'},
                        {k: 'cargo', l: 'Cargo'},
                        {k: 'tipo_de_trabajador', l: 'Tipo'},
                        {k: 'salario', l: 'Salario'},
                        {k: 'tipo_de_salario', l: 'T.Salario'},
                        {k: 'eps', l: 'EPS'},
                        {k: 'pension', l: 'Pensión'},
                        {k: 'municipio/distrito', l: 'Municipio'},
                        {k: 'departamento', l: 'Depto'},
                        {k: 'direccion', l: 'Dirección'},
                        {k: 'celular', l: 'Celular'},
                        {k: 'correo_electronico', l: 'Correo'},
                        {k: 'jornada', l: 'Jornada'},
                        {k: 'modalidad', l: 'Modalidad'},
                    ];

                    function buildWorkerTable(workers) {
                        if (!workers.length) return '<div style="font-size:11px;color:var(--c-text-2);padding:6px">Sin trabajadores.</div>';
                        const rows = workers.map(w => '<tr>' + cols.map(col => {
                            let val = Array.isArray(col.k) ? col.k.map(k=>w[k]||'').filter(Boolean).join(' ') : String(w[col.k]??'');
                            if (col.k==='salario' && val) val = '$ ' + Number(val).toLocaleString('es-CO');
                            return `<td>${escapeHtml(val)}</td>`;
                        }).join('') + '</tr>').join('');
                        return `<div style="overflow-x:auto"><table class="blocker-table">
                            <thead><tr>${cols.map(c=>`<th>${c.l}</th>`).join('')}</tr></thead>
                            <tbody>${rows}</tbody></table></div>`;
                    }

                    // Datos de sede desde form_fields
                    const formFields = a.xlsx_profile?.form_fields || {};
                    function getSedeInfo(sedeName) {
                        const num = parseInt(sedeName.match(/\d+/)?.[0] || '1');
                        const prefix = num === 1 ? 'sede_principal' : `sede_0${num}`;
                        return {
                            codigo: formFields[`${prefix}_codigo`] || '',
                            nombre: formFields[`${prefix}_nombre`] || '',
                            direccion: formFields[`${prefix}_direccion`] || '',
                            municipio: formFields[`${prefix}_municipio_distrito`] || '',
                            departamento: formFields[`${prefix}_departamento`] || '',
                            telefono: formFields[`${prefix}_telefono`] || '',
                            correo: formFields[`${prefix}_correo`] || '',
                            zona: formFields[`${prefix}_zona`] || '',
                            responsable: formFields[`responsable_${prefix}_nombre_completo`] || '',
                            centros: formFields[`${prefix}_centros_de_trabajo`] || [],
                        };
                    }

                    function renderCentrosTable(centros) {
                        if (!centros || !centros.length) return '<div style="font-size:11px;color:var(--c-text-2)">Sin centros de trabajo registrados.</div>';
                        return `<div style="overflow-x:auto"><table class="blocker-table" style="font-size:11px;min-width:900px">
                            <thead><tr>
                                <th>N°</th><th>Código</th><th>Nombre</th>
                                <th>Cód. Act.</th><th>Actividad económica</th>
                                <th>Riesgo</th><th>Municipio</th><th>Depto</th><th>Zona</th>
                                <th>Dirección</th><th>Teléfono</th><th>Correo sede</th>
                                <th>Responsable</th><th>Doc</th><th>Correo resp.</th>
                                <th>Novedades</th><th>Trabajadores</th><th>Cotización</th>
                            </tr></thead>
                            <tbody>${centros.map(c => {
                                const responsable = [c.responsable_apellido1, c.responsable_apellido2, c.responsable_nombre1, c.responsable_nombre2].filter(Boolean).join(' ');
                                const docResp = c.responsable_tipo_doc && c.responsable_num_doc ? `${c.responsable_tipo_doc} ${c.responsable_num_doc}` : '';
                                return `<tr>
                                <td>${escapeHtml(c.numero||'')}</td>
                                <td>${escapeHtml(c.codigo||'')}</td>
                                <td style="white-space:nowrap">${escapeHtml(c.nombre||'')}</td>
                                <td>${escapeHtml(c.actividad_economica_codigo||'')}</td>
                                <td style="max-width:200px;white-space:normal">${escapeHtml((c.actividad_economica||'').slice(0,100))}${(c.actividad_economica||'').length>100?'...':''}</td>
                                <td style="text-align:center">${escapeHtml(c.clase_riesgo||'')}</td>
                                <td>${escapeHtml(c.municipio||'')}</td>
                                <td>${escapeHtml(c.departamento||'')}</td>
                                <td>${escapeHtml(c.zona||'')}</td>
                                <td>${escapeHtml(c.direccion||'')}</td>
                                <td>${escapeHtml(c.telefono||'')}</td>
                                <td>${escapeHtml(c.correo||'')}</td>
                                <td style="white-space:nowrap">${escapeHtml(responsable)}</td>
                                <td>${escapeHtml(docResp)}</td>
                                <td>${escapeHtml(c.responsable_correo||'')}</td>
                                <td>${escapeHtml(c.novedades||'')}</td>
                                <td style="text-align:center">${escapeHtml(c.cantidad_trabajadores||'')}</td>
                                <td style="text-align:right">${escapeHtml(centroTrabajoMontoCotizacion(c))}</td>
                            </tr>`;}).join('')}</tbody>
                        </table></div>`;
                    }

                    function renderSedeInfoCard(info) {
                        const fields = [
                            ['Código', info.codigo], ['Nombre', info.nombre],
                            ['Dirección', info.direccion], ['Municipio', info.municipio],
                            ['Departamento', info.departamento], ['Zona', info.zona],
                            ['Teléfono', info.telefono], ['Correo', info.correo],
                            ['Responsable', info.responsable],
                        ].filter(([,v]) => v);
                        if (!fields.length) return '';
                        return `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:6px;margin-bottom:12px;padding:10px;background:var(--c-bg);border-radius:6px;border:1px solid var(--c-border)">
                            ${fields.map(([k,v]) => `<div style="font-size:11px">
                                <span style="color:var(--c-text-2);font-weight:600">${escapeHtml(k)}: </span>
                                <span style="color:var(--c-text-1)">${escapeHtml(String(v))}</span>
                            </div>`).join('')}
                        </div>`;
                    }

                    const sedeDocGroupsBySede = groupSedeDocumentsByAssignment(payload, sedeNames);

                    function renderBySede() {
                        let html = '';
                        sedeNames.forEach((sedeName, si) => {
                            const workers = bySede[sedeName] || [];
                            const total = workerCounts[sedeName] ?? workers.length;
                            if (!total && !workers.length) return;
                            const nominaSede = workers.reduce((sum, w) => sum + (Number(w.salario) || 0), 0);
                            const sal = nominaSede > 0
                                ? '$ ' + nominaSede.toLocaleString('es-CO')
                                : salaryCounts[sedeName] ? '$ ' + Number(salaryCounts[sedeName]).toLocaleString('es-CO') : '';
                            const sedeInfo = getSedeInfo(sedeName);
                            const porCentro = {};
                            for (const w of workers) {
                                const c = String(w.codigo_del_centro_de_trabajo || 'Sin centro');
                                if (!porCentro[c]) porCentro[c] = [];
                                porCentro[c].push(w);
                            }
                            const numCentros = Object.keys(porCentro).length;
                            const infoCard = renderSedeInfoCard(sedeInfo);

                            const sedeGroup = sedeDocGroupsBySede[sedeName] || [];
                            const pdfLinks = sedeGroup.map(doc =>
                                caseFileUrl(caseId, doc.filename, true)
                            );

                            html += `<div style="margin-bottom:16px;border:0.5px solid var(--c-border);border-radius:8px;overflow:hidden">
                                <div style="display:flex;align-items:center;gap:10px;padding:10px 14px;background:var(--c-info-bg);flex-wrap:wrap">
                                    <span style="font-weight:600;font-size:13px;color:var(--c-text-1)">🏢 ${escapeHtml(sedeName.replace(' - Trabajadores',''))}</span>
                                    <button class="classif-sort-btn" onclick="var t=document.getElementById('sc_${si}_centros');t.style.display=t.style.display==='none'?'':'none';this.classList.toggle('active')" type="button" style="font-size:11px">Centros: <strong>${numCentros}</strong></button>
                                    <button class="classif-sort-btn" onclick="var t=document.getElementById('sc_${si}_workers');t.style.display=t.style.display==='none'?'':'none';this.classList.toggle('active')" type="button" style="font-size:11px">Trabajadores: <strong>${total}</strong></button>
                                    ${sal ? `<span style="font-size:12px;color:var(--c-text-1);font-weight:500;margin-left:auto">${escapeHtml(sal)}</span>` : ''}
                                </div>
                                <div style="padding:12px">
                                    ${infoCard}
                                    ${pdfLinks.length ? `<details style="margin-bottom:10px"><summary style="cursor:pointer;font-size:11px;font-weight:600;color:var(--c-blue);padding:4px 0;list-style:none">📄 Ver formulario de sede (${pdfLinks.length} página${pdfLinks.length>1?'s':''})</summary>
                                        ${pdfLinks.map((url, pi) => `
                                        <div style="margin-top:6px">
                                            <div style="font-size:10px;color:var(--c-text-2);margin-bottom:2px">Página ${pi+1}</div>
                                            <iframe src="${escapeHtml(url)}" style="width:100%;height:380px;border:1px solid var(--c-border);border-radius:6px"></iframe>
                                        </div>`).join('')}
                                    </details>` : ''}
                                    <div id="sc_${si}_centros" style="display:none;margin-bottom:8px">
                                        <div style="font-size:11px;font-weight:600;color:var(--c-text-2);margin-bottom:6px;padding-bottom:4px;border-bottom:1px solid var(--c-border)">Centros de trabajo</div>
                                        ${renderCentrosTable(sedeInfo.centros)}
                                    </div>
                                    <div id="sc_${si}_workers" style="display:none">
                                        <div style="font-size:11px;font-weight:600;color:var(--c-text-2);margin-bottom:6px;padding-bottom:4px;border-bottom:1px solid var(--c-border)">Trabajadores</div>
                                        ${buildWorkerTable(workers)}
                                    </div>
                                </div>
                            </div>`;
                        });
                        return html || '<div style="color:var(--c-text-2);font-size:12px">Sin sedes con trabajadores.</div>';
                    }

                    function renderByCentro() {
                        return Object.entries(byCentro).map(([centro, workers]) => `
                            <div style="margin-bottom:16px">
                                <div style="font-weight:600;font-size:12px;color:var(--c-text-1);padding:6px 8px;background:var(--c-info-bg);border-radius:4px;margin-bottom:6px">
                                    🏭 Centro de trabajo ${escapeHtml(centro)} · ${workers.length} trabajador(es)
                                </div>
                                ${buildWorkerTable(workers)}
                            </div>`).join('');
                    }

                    const sedesCount = sedeNames.filter(s => (workerCounts[s] ?? (bySede[s]||[]).length) > 0).length;
                    dataPanel.innerHTML = `
                        <div class="blocker-panel-head">
                            <div style="display:flex;gap:6px">
                                <button class="classif-sort-btn active" id="btnVerSedes" type="button">Por sede</button>
                                <button class="classif-sort-btn" id="btnVerCentros" type="button">Por centro</button>
                            </div>
                            <button class="btn-icon" id="dataPanelClose">✕</button>
                        </div>
                        <div id="sedesContent" style="padding:12px;max-height:500px;overflow-y:auto">
                            ${renderBySede()}
                        </div>
                    `;
                    dataPanel.querySelector('#btnVerSedes')?.addEventListener('click', () => {
                        dataPanel.querySelector('#sedesContent').innerHTML = renderBySede();
                        dataPanel.querySelector('#btnVerSedes')?.classList.add('active');
                        dataPanel.querySelector('#btnVerCentros')?.classList.remove('active');
                    });
                    dataPanel.querySelector('#btnVerCentros')?.addEventListener('click', () => {
                        dataPanel.querySelector('#sedesContent').innerHTML = renderByCentro();
                        dataPanel.querySelector('#btnVerCentros').classList.add('active');
                        dataPanel.querySelector('#btnVerSedes').classList.remove('active');
                    });
                }
            } else if (panelType === 'comisiones') {
                // Panel de comisiones con visor de documento
                const docs = a.documents || [];
                const entregaDocs = docs.filter(d => d.document_type === 'entrega_documentos');
                const intermediarios = a.validacion_resumen?.matches?.entrega_documentos_intermediario || {};
                const todosInterm = Array.isArray(intermediarios.todos_intermediarios) ? intermediarios.todos_intermediarios : [];

                let comisionHTML = `
                    <div class="blocker-panel-head">
                        <span class="blocker-panel-title">💰 Comisiones e intermediación</span>
                        <button class="btn-icon" id="dataPanelClose">✕</button>
                    </div>
                    <div style="padding:12px;max-height:500px;overflow-y:auto">`;

                if (todosInterm.length) {
                    comisionHTML += `<div style="font-size:12px;font-weight:600;margin-bottom:8px">Comisiones registradas:</div>
                        <table class="blocker-table" style="margin-bottom:12px">
                            <thead><tr><th>Código</th><th>Documento</th><th>Nombre</th><th>% Participación</th></tr></thead>
                            <tbody>${todosInterm.map(r => `<tr>
                                <td>${escapeHtml(String(r.codigo_intermediario||''))}</td>
                                <td>${escapeHtml(String(r.vendedor_documento||''))}</td>
                                <td>${escapeHtml(String(r.nombre_intermediario||''))}</td>
                                <td>${escapeHtml(String(r.porcentaje_venta||''))}%</td>
                            </tr>`).join('')}</tbody></table>`;
                } else if (intermediarios.codigo_intermediario) {
                    comisionHTML += `<div style="font-size:12px;font-weight:600;margin-bottom:8px">Comisiones registradas:</div>
                        <table class="blocker-table"><thead><tr><th>Código</th><th>% Participación</th><th>Archivo</th></tr></thead>
                        <tbody><tr>
                            <td>${escapeHtml(String(intermediarios.codigo_intermediario||''))}</td>
                            <td>${escapeHtml(String(intermediarios.porcentaje_venta||''))}%</td>
                            <td>${escapeHtml(String(intermediarios.filename||''))}</td>
                        </tr></tbody></table>`;
                } else {
                    comisionHTML += `<div style="color:var(--c-text-2);font-size:12px">No se encontró información de comisiones. Verifica el documento Entrega Doc.</div>`;
                }

                // Mostrar documentos Entrega Doc para validación visual
                if (entregaDocs.length) {
                    comisionHTML += `<div style="font-size:12px;font-weight:600;margin-top:16px;margin-bottom:8px">Documentos fuente (Entrega Doc):</div>
                        <div style="display:flex;flex-wrap:wrap;gap:8px">`;
                    for (const doc of entregaDocs) {
                        const url = caseFileUrl(caseId, doc.filename || '');
                        comisionHTML += `<a href="${escapeHtml(url)}" target="_blank" class="btn-secondary" style="font-size:11px;padding:5px 10px">
                            📄 ${escapeHtml(doc.filename||'Entrega Doc')}
                        </a>`;
                    }
                    comisionHTML += `</div>`;
                }

                comisionHTML += `</div>`;
                dataPanel.innerHTML = comisionHTML;
            }
            dataPanel.querySelector('#dataPanelClose')?.addEventListener('click', () => {
                dataPanel.classList.add('hidden');
            });
            dataPanel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        });
    });

    // ── Botón Comisiones ──────────────────────────────────────
    document.getElementById('btnComisiones')?.addEventListener('click', function() {
        const dataPanel = document.getElementById('reportDataPanel');
        if (!dataPanel) return;
        if (!dataPanel.classList.contains('hidden') && dataPanel.dataset.panel === 'comisiones') {
            dataPanel.classList.add('hidden');
            this.classList.remove('active');
            return;
        }
        dataPanel.dataset.panel = 'comisiones';
        dataPanel.classList.remove('hidden');
        this.classList.add('active');

        const docs = a.documents || [];
        const entregaDocs = docs.filter(d => d.document_type === 'entrega_documentos');
        const intermediarios = a.validacion_resumen?.matches?.entrega_documentos_intermediario || {};
        const todosInterm = Array.isArray(intermediarios.todos_intermediarios) ? intermediarios.todos_intermediarios : [];

        // Construir tabla de intermediarios
        let tablaHTML = '';
        if (todosInterm.length) {
            tablaHTML += `<table class="blocker-table" style="margin-bottom:12px">
                <thead><tr><th>Código</th><th>Documento</th><th>Nombre</th><th>% Participación</th></tr></thead>
                <tbody>${todosInterm.map(r => `<tr>
                    <td>${escapeHtml(String(r.codigo_intermediario||''))}</td>
                    <td>${escapeHtml(String(r.vendedor_documento||''))}</td>
                    <td>${escapeHtml(String(r.nombre_intermediario||''))}</td>
                    <td>${escapeHtml(String(r.porcentaje_venta||''))}%</td>
                </tr>`).join('')}</tbody></table>`;
        } else if (intermediarios.codigo_intermediario) {
            tablaHTML += `<table class="blocker-table" style="margin-bottom:12px">
                <thead><tr><th>Código</th><th>% Participación</th></tr></thead>
                <tbody><tr>
                    <td>${escapeHtml(String(intermediarios.codigo_intermediario||''))}</td>
                    <td>${escapeHtml(String(intermediarios.porcentaje_venta||''))}%</td>
                </tr></tbody></table>`;
        } else {
            tablaHTML = `<div style="color:var(--c-text-2);font-size:12px;margin-bottom:12px">No se encontró información de comisiones. Verifica el documento Entrega Doc.</div>`;
        }

        // Visor PDF inline del primer documento Entrega Doc
        let visorHTML = '';
        if (entregaDocs.length) {
            const firstDoc = entregaDocs[0];
            const pdfUrl = caseFileUrl(caseId, firstDoc.filename || '', true);
            visorHTML = `
                <div style="font-size:12px;font-weight:600;margin-top:12px;margin-bottom:6px">📄 Documento fuente — ${escapeHtml(firstDoc.filename||'Entrega Doc')}</div>
                <iframe src="${escapeHtml(pdfUrl)}" style="width:100%;height:480px;border:1px solid var(--c-border);border-radius:6px" title="Entrega Doc"></iframe>
                ${entregaDocs.length > 1 ? `<div style="margin-top:6px;display:flex;gap:6px;flex-wrap:wrap">${entregaDocs.slice(1).map(d => {
                    const u = caseFileUrl(caseId, d.filename || '', true);
                    return `<button class="btn-secondary" style="font-size:11px" onclick="this.closest('.report-data-panel').querySelector('iframe').src='${escapeHtml(u)}'">📄 ${escapeHtml(d.filename||'')}</button>`;
                }).join('')}</div>` : ''}`;
        }

        dataPanel.innerHTML = `
            <div class="blocker-panel-head">
                <span class="blocker-panel-title">💰 Comisiones e intermediación</span>
                <button class="btn-icon" id="dataPanelClose2">✕</button>
            </div>
            <div style="padding:12px;overflow-y:auto;max-height:700px">
                ${tablaHTML}
                ${visorHTML}
            </div>`;

        dataPanel.querySelector('#dataPanelClose2')?.addEventListener('click', () => {
            dataPanel.classList.add('hidden');
            document.getElementById('btnComisiones')?.classList.remove('active');
        });
        dataPanel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    });
    // ── Botón Reprocesar ─────────────────────────────────────
    document.getElementById('reprocesarBtn')?.addEventListener('click', async function() {
        const btn = this;
        const statusBar = document.getElementById('reprocesarStatus');
        const id = btn.dataset.case;
        if (!id) return;
        if (!confirm('¿Reprocesar este contrato? Se volverá a ejecutar la validación documental completa.')) return;
        btn.disabled = true;
        btn.textContent = '↺ Enviando...';
        if (statusBar) { statusBar.style.display = ''; statusBar.textContent = 'Enviando a la cola...'; }
        try {
            const r = await fetch(caseApiUrl(id, '/run-workflow'), { method: 'POST' });
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            if (statusBar) {
                statusBar.textContent = '✓ En cola — puedes ver el progreso en la Bandeja.';
                statusBar.style.background = 'var(--c-ok-bg)';
                statusBar.style.color = 'var(--c-ok)';
            }
            btn.textContent = 'En cola ✓';
            showToast('Contrato enviado a reprocesar. RAG aprenderá del resultado.', 'info');
            setTimeout(() => loadReporteSidebar(), 3000);
            startBandejaLivePolling();
        } catch(e) {
            if (statusBar) { statusBar.textContent = 'Error: ' + e.message; statusBar.style.background = 'var(--c-err-bg)'; statusBar.style.color = 'var(--c-err)'; }
            btn.disabled = false;
            btn.textContent = '↺ Reprocesar';
            showToast('Error al reprocesar: ' + e.message, 'err');
        }
    });

    // ── Sedes inline automático ──────────────────────────────
    setTimeout(() => {
        const sedesInline = document.getElementById('reportSedesInline');
        if (!sedesInline) return;
        const sedeRecords = a.xlsx_profile?.records || [];
        const workerCounts = a.xlsx_profile?.worker_sheet_counts || {};
        const salaryCounts = a.xlsx_profile?.worker_sheet_salary_totals || {};
        const formFields = a.xlsx_profile?.form_fields || {};
        const bySede = {};
        for (const r of sedeRecords) {
            const sede = r._sheet || 'Sin sede';
            if (!bySede[sede]) bySede[sede] = [];
            bySede[sede].push(r);
        }
        const sedeNames = Object.keys(workerCounts).length ? Object.keys(workerCounts) : Object.keys(bySede);
        if (!sedeNames.length) { sedesInline.innerHTML = ''; return; }
        const sedeDocGroupsBySede = groupSedeDocumentsByAssignment(payload, sedeNames);

        function getSedeInfoInline(sedeName) {
            const num = parseInt(sedeName.match(/\d+/)?.[0] || '1');
            const prefix = num === 1 ? 'sede_principal' : `sede_0${num}`;
            return {
                codigo: formFields[`${prefix}_codigo`] || '',
                nombre: formFields[`${prefix}_nombre`] || '',
                direccion: formFields[`${prefix}_direccion`] || '',
                municipio: formFields[`${prefix}_municipio_distrito`] || '',
                departamento: formFields[`${prefix}_departamento`] || '',
                telefono: formFields[`${prefix}_telefono`] || '',
                correo: formFields[`${prefix}_correo`] || '',
                zona: formFields[`${prefix}_zona`] || '',
                responsable: formFields[`responsable_${prefix}_nombre_completo`] || '',
                centros: formFields[`${prefix}_centros_de_trabajo`] || [],
            };
        }

        let html = '';
        sedeNames.forEach((sedeName, si) => {
            const workers = bySede[sedeName] || [];
            const total = workerCounts[sedeName] ?? workers.length;
            if (!total && !workers.length) return;
            const nominaSede = workers.reduce((sum, w) => sum + (Number(w.salario) || 0), 0);
            const sal = nominaSede > 0 ? '$ ' + nominaSede.toLocaleString('es-CO') : '';
            const info = getSedeInfoInline(sedeName);
            const sedeGroup = sedeDocGroupsBySede[sedeName] || [];
            const pdfUrl = sedeGroup[0] ? caseFileUrl(caseId, sedeGroup[0].filename, true) : '';

            const infoFields = [
                ['Código', info.codigo], ['Nombre', info.nombre],
                ['Dirección', info.direccion], ['Municipio', info.municipio],
                ['Departamento', info.departamento], ['Zona', info.zona],
                ['Teléfono', info.telefono], ['Correo', info.correo],
                ['Responsable', info.responsable],
            ].filter(([,v]) => v);

            const trabId = `ri_trab_${si}`;
            // Tabla simple de trabajadores para el reporte inline
            function buildWorkerTableSimple(ws) {
                if (!ws || !ws.length) return '<div style="font-size:11px;color:var(--c-text-2);padding:8px">Sin trabajadores.</div>';
                return `<div style="overflow-x:auto"><table class="blocker-table" style="font-size:11px;min-width:600px">
                    <thead><tr><th>Documento</th><th>Nombre</th><th>Cargo</th><th>Salario</th><th>EPS</th><th>Pensión</th><th>Municipio</th></tr></thead>
                    <tbody>${ws.map(w => `<tr>
                        <td>${escapeHtml(w.numero_de_identificacion||'')}</td>
                        <td>${escapeHtml([w.primer_apellido,w.segundo_apellido,w.primer_nombre,w.segundo_nombre].filter(Boolean).join(' '))}</td>
                        <td>${escapeHtml(w.cargo||w.nombre_del_cargo||'')}</td>
                        <td>${escapeHtml(w.salario?'$ '+Number(w.salario).toLocaleString('es-CO'):'')}</td>
                        <td>${escapeHtml(w.eps||'')}</td>
                        <td>${escapeHtml(w.pension||w.afp||'')}</td>
                        <td>${escapeHtml(w.municipio_distrito||w.municipio||'')}</td>
                    </tr>`).join('')}</tbody>
                </table></div>`;
            }

            html += `<div style="margin-bottom:12px;border:0.5px solid var(--c-border);border-radius:8px;overflow:hidden">
                <div style="display:flex;align-items:center;gap:10px;padding:10px 14px;background:var(--c-info-bg);flex-wrap:wrap">
                    <span style="font-weight:600;font-size:13px;color:var(--c-text-1)">🏢 ${escapeHtml(sedeName.replace(' - Trabajadores',''))}</span>
                    <button class="classif-sort-btn" onclick="var t=document.getElementById('${trabId}');var open=t.style.display!=='none';t.style.display=open?'none':'';this.classList.toggle('active',!open)" type="button" style="font-size:11px">👷 Trabajadores: <strong>${total}</strong></button>
                    ${sal ? `<span style="font-size:12px;color:var(--c-text-1);font-weight:500">${escapeHtml(sal)}</span>` : ''}
                </div>
                <div style="padding:10px 12px">
                    ${infoFields.length ? `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:4px;margin-bottom:8px">
                        ${infoFields.map(([k,v]) => `<div style="font-size:11px"><span style="color:var(--c-text-2);font-weight:600">${escapeHtml(k)}: </span><span style="color:var(--c-text-1)">${escapeHtml(String(v))}</span></div>`).join('')}
                    </div>` : ''}
                    ${pdfUrl ? `<details style="margin-bottom:6px"><summary style="cursor:pointer;font-size:11px;color:var(--c-blue);font-weight:600">📄 Ver formulario (${sedeGroup.length} pág.)</summary>
                        ${sedeGroup.map((doc,pi) => `<iframe src="${escapeHtml(caseFileUrl(caseId, doc.filename, true))}" style="width:100%;height:350px;border:1px solid var(--c-border);border-radius:4px;margin-top:4px"></iframe>`).join('')}
                    </details>` : ''}
                    <div id="${trabId}" style="display:none;margin-top:8px;max-height:400px;overflow-y:auto">${buildWorkerTableSimple(workers)}</div>
                </div>
            </div>`;
        });
        sedesInline.innerHTML = html;
    }, 100);
}

// ── PRODUCCIÓN (COLMENA) ─────────────────────────────────────
async function loadProduccion() {
    const el = document.getElementById('produccionContent');
    if (!el) return;
    if (productionLoadController) { try { productionLoadController.abort(); } catch {} }
    productionLoadController = new AbortController();
    el.innerHTML = '<div class="loading-msg">Cargando contratos...</div>';
    try {
        const r = await fetchWithRetry(operationApiUrl('/api/cases/production-summary'), { signal: productionLoadController.signal });
        const data = await r.json();
        let cases = Array.isArray(data.cases) ? data.cases : [];
        cases = cases.filter(c => {
            const { status, finalStatus } = resolveCase(c);
            return isApprovedCaseStatus(status, finalStatus);
        });
        const selectableCaseIds = new Set(cases.map(item => item.id).filter(Boolean));
        selectedColmenaCaseIds = new Set([...selectedColmenaCaseIds].filter(id => selectableCaseIds.has(id)));
        cases.sort((a,b) => String(b.updated_at||'').localeCompare(String(a.updated_at||'')));
        if (!cases.length) { el.innerHTML = `<div class="empty-state">No hay contratos aprobados para ${escapeHtml(currentOperation().name)}</div>`; return; }
        el.innerHTML = `<div class="production-cards">${cases.map(item => {
            const { empresa, nit, fecha, has926, filename, nroAfiliacion } = resolveCase(item);
            const id = item.id || '';
            return `
                <div class="prod-card">
                    <div class="prod-card-head">
                        <div>
                            <div class="prod-card-title">${nroAfiliacion ? `Contrato ${escapeHtml(nroAfiliacion)}` : `NIT ${escapeHtml(nit)}`}</div>
                            <div class="prod-card-empresa">${escapeHtml(empresa)}</div>
                            <div class="prod-card-meta">${escapeHtml(fecha)}</div>
                        </div>
                        <div class="prod-card-badges">
                            <span class="pill pill-ok">Aprobado</span>
                            ${has926 ? '<span class="pill pill-info">926 listo</span>' : ''}
                        </div>
                    </div>
                    <div class="prod-card-actions">
                        <label style="font-size:12px;display:flex;align-items:center;gap:6px;cursor:pointer">
                            <input type="checkbox" data-colmena-case="${escapeHtml(id)}" ${selectedColmenaCaseIds.has(id)?'checked':''}>
                            Incluir en lote
                        </label>
                        <button class="btn-secondary" data-action="reporte" data-case="${escapeHtml(id)}" type="button">Reporte</button>
                        <button class="btn-secondary" data-action="clasificacion" data-case="${escapeHtml(id)}" type="button">Docs</button>
                        ${has926 ? `<button class="btn-primary" data-action="descargar926" data-case="${escapeHtml(id)}" data-file="${escapeHtml(filename)}" type="button">Descargar plano</button>` : ''}
                    </div>
                </div>
            `;
        }).join('')}</div>`;
        el.querySelectorAll('[data-colmena-case]').forEach(inp => {
            inp.addEventListener('change', () => {
                const id = inp.getAttribute('data-colmena-case');
                if (inp.checked) selectedColmenaCaseIds.add(id);
                else selectedColmenaCaseIds.delete(id);
            });
        });
        el.querySelectorAll('[data-action]').forEach(btn => {
            btn.addEventListener('click', () => handleCaseAction(btn.dataset.action, btn.dataset.case, btn.dataset.file));
        });
    } catch(e) {
        if (e.name === 'AbortError') return;
        el.innerHTML = `<div class="error-msg">${escapeHtml(e.message)}</div>`;
    } finally {
        productionLoadController = null;
    }
}

async function downloadColmenaBatch() {
    const ids = Array.from(selectedColmenaCaseIds);
    if (!ids.length) { showToast('Selecciona al menos un contrato para el lote', 'warn'); return; }
    const btn = document.getElementById('downloadColmenaBtn');
    if (btn) { btn.disabled = true; btn.textContent = 'Descargando...'; }
    try {
        const r = await fetchWithRetry(operationApiUrl('/api/926/consolidated'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ case_ids: ids, operation: readOperation() }),
        });
        const blob = await r.blob();
        const disposition = r.headers.get('Content-Disposition') || '';
        const match = disposition.match(/filename="?([^"]+)"?/i);
        const filename = match?.[1] || 'lote_colmena.txt';
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = filename;
        document.body.appendChild(a); a.click(); a.remove();
        URL.revokeObjectURL(url);
    } catch(e) {
        showToast('Error descargando lote: ' + e.message, 'err');
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = 'Descargar lote plano'; }
    }
}

// ── ENTRENAMIENTO / FEEDBACK ──────────────────────────────────
function syncFeedbackName() {
    const t = readTester();
    const el = document.getElementById('feedbackName');
    if (el && t.name) { el.value = t.name; }
    // Cargar selector de contratos
    loadFeedbackCaseSelect();
}

async function loadFeedbackCaseSelect() {
    const sel = document.getElementById('feedbackCaseSelect');
    if (!sel) return;
    try {
        const r = await fetch(operationApiUrl('/api/cases/production-summary'));
        const data = await r.json();
        const cases = Array.isArray(data.cases) ? data.cases : [];
        cases.sort((a,b) => String(b.updated_at||'').localeCompare(String(a.updated_at||'')));
        sel.innerHTML = '<option value="">— Contrato relacionado (opcional) —</option>' +
            cases.map(c => {
                const { empresa, nit } = resolveCase(c);
                const label = empresa !== 'n/d' ? empresa : c.label || c.id;
                const nitStr = nit !== 'n/d' ? ` · ${nit}` : '';
                return `<option value="${escapeHtml(c.id)}">${escapeHtml(label)}${escapeHtml(nitStr)}</option>`;
            }).join('');
    } catch(e) { console.warn('loadFeedbackCaseSelect:', e); }
}

async function loadFeedbackNotes() {
    const el = document.getElementById('feedbackNotesList');
    if (!el) return;
    el.innerHTML = '<div class="loading-msg">Cargando observaciones...</div>';
    try {
        const r = await fetchWithRetry(`${API_URL}/api/feedback-notes`);
        const data = await r.json();
        const items = Array.isArray(data.items) ? data.items.slice().reverse() : [];
        if (!items.length) { el.innerHTML = '<div class="empty-state">No hay observaciones registradas aún</div>'; return; }
        el.innerHTML = items.map(item => {
            const category = item.category || '';
            const caseId = item.case_id || '';
            const caseLabel = item.case_label || caseId;
            const categoryColors = {
                'falso_positivo': 'var(--c-warn)',
                'ocr_error': 'var(--c-info)',
                'clasificacion_erronea': 'var(--c-err)',
                'sugerencia': 'var(--c-ok)',
                'otro': 'var(--c-text-2)',
            };
            const categoryLabels = {
                'falso_positivo': '⚠ Falso positivo',
                'ocr_error': '🔍 Error OCR',
                'clasificacion_erronea': '📄 Clasificación errónea',
                'sugerencia': '💡 Sugerencia',
                'otro': '📝 Otro',
            };
            return `
                <div class="feedback-note-item">
                    <div class="feedback-note-meta" style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
                        <span style="font-weight:600">${escapeHtml(item.name||'Anónimo')}</span>
                        <span style="color:var(--c-text-3)">${formatDateTime(item.created_at)}</span>
                        ${category ? `<span style="font-size:11px;color:${categoryColors[category]||'var(--c-text-2)'}">${escapeHtml(categoryLabels[category]||category)}</span>` : ''}
                        ${caseLabel ? `<span class="pill pill-neutral" style="font-size:10px;cursor:pointer" data-goto-case="${escapeHtml(caseId)}">${escapeHtml(caseLabel.slice(0,30))}</span>` : ''}
                    </div>
                    <div class="feedback-note-text">${escapeHtml(item.text||item.comment||'')}</div>
                </div>
            `;
        }).join('');
        // Click en pill del contrato → ir al reporte
        el.querySelectorAll('[data-goto-case]').forEach(pill => {
            pill.addEventListener('click', () => {
                const id = pill.dataset.gotoCase;
                if (id) { activeCaseId = id; switchView('reporte'); loadReporteForCase(id); }
            });
        });
    } catch(e) {
        el.innerHTML = `<div class="error-msg">${escapeHtml(e.message)}</div>`;
    }
}

async function saveFeedbackNote() {
    const t = readTester();
    const name = t.name || String(document.getElementById('feedbackName')?.value||'').trim();
    const text = String(document.getElementById('feedbackNote')?.value||'').trim();
    const category = String(document.getElementById('feedbackCategory')?.value||'').trim();
    const caseId = String(document.getElementById('feedbackCaseSelect')?.value||'').trim();
    if (!name || !text) { showToast('Completa tu nombre y la observación', 'warn'); return; }
    const btn = document.getElementById('saveFeedbackBtn');
    const status = document.getElementById('feedbackSaveStatus');
    if (btn) { btn.disabled = true; btn.textContent = 'Guardando...'; }

    // Obtener label del contrato seleccionado
    let caseLabel = '';
    if (caseId) {
        const sel = document.getElementById('feedbackCaseSelect');
        const opt = sel?.querySelector(`option[value="${caseId}"]`);
        caseLabel = opt?.textContent?.trim() || caseId;
    }

    try {
        const r = await fetch(`${API_URL}/api/feedback-notes`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, text, category, case_id: caseId, case_label: caseLabel }),
        });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const noteEl = document.getElementById('feedbackNote');
        if (noteEl) noteEl.value = '';
        if (status) { status.style.color = 'var(--c-ok)'; status.textContent = '✓ Observación registrada'; }
        await loadFeedbackNotes();
        setTimeout(() => { if (status) status.textContent = ''; }, 3000);
    } catch(e) {
        if (status) { status.style.color = 'var(--c-err)'; status.textContent = 'Error: ' + e.message; }
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = 'Guardar observación'; }
    }
}

// ── BÚSQUEDA ──────────────────────────────────────────────────
async function doSearch(query) {
    const el = document.getElementById('searchResults');
    if (!el) return;
    el.innerHTML = '<div class="loading-msg">Buscando...</div>';
    try {
        const url = query?.trim()
            ? operationApiUrl('/api/cases/search', { q: query.trim(), limit: 20 })
            : operationApiUrl('/api/cases/production-summary');
        const r = await fetch(url);
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const data = await r.json();
        const results = Array.isArray(data.results) ? data.results :
                        Array.isArray(data.cases) ? data.cases : [];
        if (!results.length) {
            el.innerHTML = '<div class="empty-state">Sin resultados' + (query?.trim() ? ` para "${escapeHtml(query)}"` : '') + '</div>';
            return;
        }
        el.innerHTML = results.map(item => {
            const { empresa, nit, fecha, status, finalStatus, nroAfiliacion } = resolveCase(item);
            const cls = caseStatusClass(status, finalStatus);
            const lbl = casePillLabel(status, finalStatus);
            const blockers = item.blockers || [];
            const wfStatus = item.workflow_run?.status || item.status || '';
            const isFailed = wfStatus === 'failed';
            const id = item.id || '';
            return `
                <div class="search-result-item" data-case="${escapeHtml(id)}" tabindex="0" role="button">
                    <div class="search-result-main">
                        <div class="search-result-empresa">${escapeHtml(empresa)}</div>
                        <div class="search-result-meta">
                            ${nit !== 'n/d' ? `NIT ${escapeHtml(nit)}` : ''}${nroAfiliacion ? ` · Contrato ${escapeHtml(nroAfiliacion)}` : ''} · ${escapeHtml(fecha)}
                        </div>
                        ${isFailed ? `<div style="font-size:11px;color:var(--c-err);margin-top:3px">⚠ Procesamiento fallido — clic para ver documentos</div>` : ''}
                        ${blockers.length ? `<div style="font-size:11px;color:var(--c-err);margin-top:3px">
                            ${blockers.length} bloqueante${blockers.length>1?'s':''}: ${escapeHtml(String(blockers[0]).slice(0,60))}${blockers[0]?.length>60?'...':''}
                        </div>` : ''}
                    </div>
                    <span class="pill pill-${isFailed?'warn':cls}" style="flex-shrink:0">${isFailed?'Error':escapeHtml(lbl)}</span>
                </div>
            `;
        }).join('');
        el.querySelectorAll('[data-case]').forEach(row => {
            row.addEventListener('click', () => {
                const id = row.dataset.case;
                if (!id) return;
                activeCaseId = id;
                // Si el caso tiene reporte ejecutivo ir ahí, si no al visor documental
                const item = results.find(r => r.id === id);
                const st = String(item?.status || item?.workflow_run?.status || '');
                if (st === 'completed' || st === 'stopped_prevalidacion' || st === 'stopped_926') {
                    switchView('reporte');
                    loadReporteForCase(id);
                } else {
                    switchView('clasificacion');
                    loadClassifForCase(id);
                }
            });
            row.addEventListener('keydown', e => {
                if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); row.click(); }
            });
        });
    } catch(e) {
        el.innerHTML = `<div class="error-msg">${escapeHtml(e.message)}</div>`;
    }
}

// ── Panel de Administración de Tablas ──────────────────────────
const ADMIN_CATALOG_FIELD_TYPES = {
    codigo: 'number',
    na: 'number',
    activo: 'boolean',
    cedula: 'text',
    nombre: 'text',
    subsistema: 'text',
    codigo_pila: 'text',
    nombre_oficial: 'text',
    alias: 'text',
    fuente: 'text',
    fecha_fuente: 'text',
};

function normalizeAdminFieldValue(field, value) {
    const type = ADMIN_CATALOG_FIELD_TYPES[field] || 'text';
    if (type === 'boolean') return Boolean(value);
    if (type === 'number') {
        const trimmed = String(value ?? '').trim();
        if (!trimmed) return '';
        const n = Number(trimmed);
        return Number.isFinite(n) ? n : trimmed;
    }
    return String(value ?? '').trim();
}

function readAdminRowSearchText(row, fields) {
    return fields.map(f => String(row?.[f] ?? '')).join(' ').toLowerCase();
}

function assertAdminSaveOk(response, tableName) {
    if (!response.ok) throw new Error(`${tableName}: HTTP ${response.status}`);
    return response.json().catch(() => ({ok: true}));
}

function adminAliasText(value) {
    return Array.isArray(value) ? value.join(', ') : String(value ?? '');
}

function showTable(name) {
    ['pila','eps','afp','asesores','smmlv','destinatarios'].forEach(t => {
        const panel = document.getElementById(`tableContent_${t}`);
        const btn = document.getElementById(`tabBtn_${t}`);
        if (panel) panel.style.display = t === name ? '' : 'none';
        if (btn) btn.classList.toggle('active', t === name);
    });
}
window.showTable = showTable;

async function loadAdminTables() {
    const el = document.getElementById('adminTablesPanel');
    if (!el) return;
    el.innerHTML = `<div style="font-size:12px;color:var(--c-text-2)">Cargando tablas...</div>`;

    try {
        const [pilaR, epsR, afpR, aseR, smlR, recR] = await Promise.all([
            fetch(`${API_URL}/api/admin/tables/pila`).then(r=>r.json()),
            fetch(`${API_URL}/api/admin/tables/eps`).then(r=>r.json()),
            fetch(`${API_URL}/api/admin/tables/afp`).then(r=>r.json()),
            fetch(`${API_URL}/api/admin/tables/asesores`).then(r=>r.json()),
            fetch(`${API_URL}/api/admin/tables/smmlv`).then(r=>r.json()),
            fetch(`${API_URL}/api/admin/tables/recipients`).then(r=>r.json()),
        ]);

        el.innerHTML = `
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px">
            ${['pila','eps','afp','asesores','smmlv','destinatarios'].map(t=>`
            <button class="classif-sort-btn ${t==='pila'?'active':''}" onclick="showTable('${t}')" type="button" id="tabBtn_${t}">${
                t==='pila'?'PILA':t==='eps'?'EPS':t==='afp'?'AFP':t==='asesores'?'Asesores':t==='smmlv'?'SMMLV':'Destinatarios'
            }</button>`).join('')}
        </div>
        <div id="tableContent_pila" class="table-panel"></div>
        <div id="tableContent_eps" class="table-panel"></div>
        <div id="tableContent_afp" class="table-panel" style="display:none"></div>
        <div id="tableContent_asesores" class="table-panel" style="display:none"></div>
        <div id="tableContent_smmlv" class="table-panel" style="display:none"></div>
        <div id="tableContent_destinatarios" class="table-panel" style="display:none"></div>
        `;

        // PILA
        renderPilaTable(pilaR.items || []);

        // EPS
        renderCatalogTable('eps', epsR.items || [], ['codigo','nombre','na'], ['Código','Nombre','N/A'],
            async (items) => {
                const r = await fetch(`${API_URL}/api/admin/tables/eps`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({items})});
                await assertAdminSaveOk(r, 'EPS');
            }
        );

        // AFP
        renderCatalogTable('afp', afpR.items || [], ['codigo','nombre','na','activo'], ['Código','Nombre','N/A','Activo'],
            async (items) => {
                const r = await fetch(`${API_URL}/api/admin/tables/afp`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({items})});
                await assertAdminSaveOk(r, 'AFP');
            }
        );

        // Consultores (tabla plana img004.consultores)
        renderCatalogTable('asesores', aseR.items || [], ['cedula','nombre'],
            ['Cédula','Nombre'],
            async (items) => {
                const r = await fetch(`${API_URL}/api/admin/tables/asesores`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({items})});
                await assertAdminSaveOk(r, 'Consultores');
            }
        );

        // SMMLV
        renderSmmlvTable(smlR);

        // Destinatarios
        renderRecipientsTable(recR);

        showTable('pila');

    } catch(e) {
        el.innerHTML = `<div style="color:var(--c-err)">Error cargando tablas: ${e.message}</div>`;
    }
}

function renderPilaTable(items) {
    const el = document.getElementById('tableContent_pila');
    if (!el) return;
    let data = Array.isArray(items) ? items.map(row => ({...row, alias: Array.isArray(row.alias) ? [...row.alias] : adminAliasText(row.alias)})) : [];
    const fields = ['subsistema','codigo_pila','nombre_oficial','alias','activo','fuente','fecha_fuente'];

    const render = () => {
        data = window._pilaData || data;
        const counts = data.reduce((acc, row) => {
            const key = String(row.subsistema || 'SIN').toUpperCase();
            acc[key] = (acc[key] || 0) + 1;
            return acc;
        }, {});
        el.innerHTML = `
        <div class="admin-table-toolbar">
            <span style="font-size:11px;color:var(--c-text-2)">
                ${data.length} registros · ${Object.entries(counts).sort().map(([k,v]) => `${k}: ${v}`).join(' · ')}
            </span>
            <div class="admin-table-actions">
                <select id="filter_pila_subsistema" class="admin-table-search" onchange="filterPilaTable()">
                    <option value="">Todos</option>
                    ${['EPS','AFP','ARL','CCF','ICBF','SENA','ADRES'].map(s => `<option value="${s}">${s}</option>`).join('')}
                </select>
                <input id="search_pila" class="admin-table-search" placeholder="Buscar..." oninput="filterPilaTable()">
                <button class="classif-sort-btn" type="button" onclick="addPilaRow()">+ Agregar</button>
                <button class="btn-primary" style="font-size:11px;padding:4px 10px" type="button" onclick="savePilaCatalog()">Guardar</button>
            </div>
        </div>
        <div style="font-size:11px;color:var(--c-text-2);margin-bottom:8px">
            Catálogo maestro de administradoras PILA. Se usa como referencia para normalizar nombres y códigos; no debe causar devolución automática.
        </div>
        <div style="overflow-x:auto;max-height:460px;overflow-y:auto">
        <table class="blocker-table" style="font-size:11px;min-width:980px" id="tbl_pila">
            <thead><tr>
                <th>Subsistema</th><th>Código PILA</th><th>Nombre oficial</th><th>Alias</th><th>Activo</th><th>Fuente</th><th>Fecha</th><th style="width:40px"></th>
            </tr></thead>
            <tbody>
            ${data.map((row,i) => `<tr data-index="${i}">
                <td>
                    <select class="admin-table-input" onchange="updatePilaRow(${i},'subsistema',this.value)">
                        ${['EPS','AFP','ARL','CCF','ICBF','SENA','ADRES'].map(s => `<option value="${s}" ${String(row.subsistema||'').toUpperCase()===s?'selected':''}>${s}</option>`).join('')}
                    </select>
                </td>
                <td><input value="${escapeHtml(String(row.codigo_pila ?? ''))}" class="admin-table-input" oninput="updatePilaRow(${i},'codigo_pila',this.value)"></td>
                <td><input value="${escapeHtml(String(row.nombre_oficial ?? ''))}" class="admin-table-input" oninput="updatePilaRow(${i},'nombre_oficial',this.value)"></td>
                <td><input value="${escapeHtml(adminAliasText(row.alias))}" class="admin-table-input" oninput="updatePilaRow(${i},'alias',this.value)"></td>
                <td><input type="checkbox" ${row.activo !== false ? 'checked' : ''} onchange="updatePilaRow(${i},'activo',this.checked)"></td>
                <td><input value="${escapeHtml(String(row.fuente ?? ''))}" class="admin-table-input" oninput="updatePilaRow(${i},'fuente',this.value)"></td>
                <td><input value="${escapeHtml(String(row.fecha_fuente ?? ''))}" class="admin-table-input" oninput="updatePilaRow(${i},'fecha_fuente',this.value)"></td>
                <td><button type="button" style="background:transparent;border:none;cursor:pointer;color:var(--c-err);font-size:12px" onclick="deletePilaRow(${i})">✕</button></td>
            </tr>`).join('')}
            </tbody>
        </table>
        </div>`;
        window._pilaData = data;
        window._pilaFields = fields;
    };

    window._pilaRender = render;
    render();
}

window.addPilaRow = function() {
    const data = window._pilaData || [];
    data.unshift({
        subsistema: 'EPS',
        codigo_pila: '',
        nombre_oficial: '',
        alias: '',
        activo: true,
        fuente: 'manual',
        fecha_fuente: new Date().toISOString().slice(0, 7),
    });
    window._pilaData = data;
    window._pilaRender?.();
};

window.updatePilaRow = function(idx, field, value) {
    const data = window._pilaData || [];
    if (!data[idx]) return;
    data[idx][field] = field === 'activo' ? Boolean(value) : String(value ?? '').trim();
};

window.deletePilaRow = function(idx) {
    const data = window._pilaData || [];
    data.splice(idx, 1);
    window._pilaRender?.();
};

window.filterPilaTable = function() {
    const q = document.getElementById('search_pila')?.value?.toLowerCase() || '';
    const subsystem = document.getElementById('filter_pila_subsistema')?.value || '';
    const data = window._pilaData || [];
    const fields = window._pilaFields || [];
    document.querySelectorAll('#tbl_pila tbody tr').forEach(tr => {
        const idx = Number(tr.dataset.index);
        const row = data[idx] || {};
        const rowSubsystem = String(row.subsistema || '').toUpperCase();
        const matchesSubsystem = !subsystem || rowSubsystem === subsystem;
        const matchesText = readAdminRowSearchText(row, fields).includes(q);
        tr.style.display = matchesSubsystem && matchesText ? '' : 'none';
    });
};

window.savePilaCatalog = async function() {
    const data = window._pilaData || [];
    try {
        const items = data
            .map(row => ({
                ...row,
                alias: Array.isArray(row.alias)
                    ? row.alias
                    : String(row.alias || '').split(/[,;\n]+/).map(x => x.trim()).filter(Boolean),
            }))
            .filter(row => row.subsistema || row.codigo_pila || row.nombre_oficial);
        const r = await fetch(`${API_URL}/api/admin/tables/pila`, {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify({items}),
        });
        await assertAdminSaveOk(r, 'PILA');
        window._pilaData = items;
        window._pilaRender?.();
        showToast(`Catálogo PILA guardado (${items.length} registros)`, 'ok');
    } catch(e) {
        showToast('Error guardando PILA: ' + e.message, 'err');
    }
};

function renderCatalogTable(type, items, fields, headers, saveFn) {
    const el = document.getElementById(`tableContent_${type}`);
    if (!el) return;
    let data = Array.isArray(items) ? items.map(row => ({...row})) : [];

    const render = () => {
        el.innerHTML = `
        <div class="admin-table-toolbar">
            <span style="font-size:11px;color:var(--c-text-2)">${data.length} registros</span>
            <div class="admin-table-actions">
                <input id="search_${type}" class="admin-table-search" placeholder="Buscar..." oninput="filterTable('${type}')">
                <button class="classif-sort-btn" type="button" onclick="addRowCatalog('${type}')">+ Agregar</button>
                <button class="btn-primary" style="font-size:11px;padding:4px 10px" type="button" onclick="saveCatalog('${type}')">Guardar</button>
            </div>
        </div>
        <div style="overflow-x:auto;max-height:400px;overflow-y:auto">
        <table class="blocker-table" style="font-size:11px" id="tbl_${type}">
            <thead><tr>${headers.map(h=>`<th>${h}</th>`).join('')}<th style="width:40px"></th></tr></thead>
            <tbody>
            ${data.map((row,i) => `<tr data-index="${i}">
                ${fields.map(f=>`<td>${renderAdminCatalogInput(type, row, i, f)}</td>`).join('')}
                <td><button type="button" style="background:transparent;border:none;cursor:pointer;color:var(--c-err);font-size:12px" onclick="deleteRowCatalog('${type}',${i})">✕</button></td>
            </tr>`).join('')}
            </tbody>
        </table>
        </div>`;
        window[`_tableData_${type}`] = data;
        window[`_tableFields_${type}`] = fields;
        window[`_tableSaveFn_${type}`] = saveFn;
    };
    render();
    window[`_tableData_${type}`] = data;
    window[`_tableFields_${type}`] = fields;
    window[`_tableSaveFn_${type}`] = saveFn;
    window[`_tableRender_${type}`] = render;
}

function renderAdminCatalogInput(type, row, idx, field) {
    const fieldType = ADMIN_CATALOG_FIELD_TYPES[field] || 'text';
    const value = row?.[field];
    if (fieldType === 'boolean') {
        const checked = value === true || String(value).toLowerCase() === 'true' || String(value) === '1';
        return `<input type="checkbox" ${checked ? 'checked' : ''} data-field="${field}" onchange="updateRowCatalog('${type}',${idx},'${field}',this.checked)">`;
    }
    const inputType = fieldType === 'number' ? 'number' : 'text';
    return `<input value="${escapeHtml(String(value ?? ''))}" type="${inputType}" data-field="${field}" class="admin-table-input" oninput="updateRowCatalog('${type}',${idx},'${field}',this.value)">`;
}

window.addRowCatalog = function(type) {
    const data = window[`_tableData_${type}`];
    const fields = window[`_tableFields_${type}`] || [];
    const newRow = {};
    fields.forEach(f => newRow[f] = ADMIN_CATALOG_FIELD_TYPES[f] === 'boolean' ? true : '');
    data.push(newRow);
    window[`_tableRender_${type}`]?.();
};

window.updateRowCatalog = function(type, idx, field, value) {
    const data = window[`_tableData_${type}`];
    if (data[idx]) data[idx][field] = normalizeAdminFieldValue(field, value);
};

window.deleteRowCatalog = function(type, idx) {
    const data = window[`_tableData_${type}`];
    data.splice(idx, 1);
    window[`_tableRender_${type}`]?.();
};

window.saveCatalog = async function(type) {
    const data = window[`_tableData_${type}`];
    const saveFn = window[`_tableSaveFn_${type}`];
    try {
        const normalized = data
            .map(row => ({...row}))
            .filter(row => Object.values(row).some(value => String(value ?? '').trim() !== ''));
        await saveFn(normalized);
        window[`_tableData_${type}`] = normalized;
        window[`_tableRender_${type}`]?.();
        showToast(`Tabla ${type.toUpperCase()} guardada (${normalized.length} registros)`, 'ok');
    } catch(e) {
        showToast('Error guardando: ' + e.message, 'err');
    }
};

window.filterTable = function(type) {
    const q = document.getElementById(`search_${type}`)?.value?.toLowerCase() || '';
    const data = window[`_tableData_${type}`] || [];
    const fields = window[`_tableFields_${type}`] || [];
    document.querySelectorAll(`#tbl_${type} tbody tr`).forEach(tr => {
        const idx = Number(tr.dataset.index);
        tr.style.display = readAdminRowSearchText(data[idx], fields).includes(q) ? '' : 'none';
    });
};

function renderSmmlvTable(data) {
    const el = document.getElementById('tableContent_smmlv');
    if (!el) return;
    window._smmlvData = {...data};

    const render = () => {
        el.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
            <span style="font-size:12px;color:var(--c-text-2)">Salario Mínimo Mensual Legal Vigente por año</span>
            <div style="display:flex;gap:6px">
                <button class="classif-sort-btn" type="button" onclick="addSmmlvYear()">+ Agregar año</button>
                <button class="btn-primary" style="font-size:11px;padding:4px 10px" type="button" onclick="saveSmmlv()">💾 Guardar</button>
            </div>
        </div>
        <table class="blocker-table" style="font-size:12px;width:300px">
            <thead><tr><th>Año</th><th>SMMLV ($)</th><th style="width:40px"></th></tr></thead>
            <tbody>
            ${Object.entries(window._smmlvData).sort().map(([year,val]) => `<tr>
                <td><strong>${escapeHtml(year)}</strong></td>
                <td><input value="${val}" type="number" style="width:120px;border:1px solid var(--c-border);border-radius:4px;padding:2px 6px;font-size:12px" onchange="window._smmlvData['${year}']=parseInt(this.value)"></td>
                <td><button type="button" style="background:transparent;border:none;cursor:pointer;color:var(--c-err)" onclick="delete window._smmlvData['${year}'];renderSmmlvInner()">✕</button></td>
            </tr>`).join('')}
            </tbody>
        </table>`;
        window.renderSmmlvInner = render;
    };
    render();

    window.addSmmlvYear = () => {
        const year = prompt('Año (ej: 2027):');
        const val = prompt('Valor SMMLV:');
        if (year && val) { window._smmlvData[year] = parseInt(val); render(); }
    };
    window.saveSmmlv = async () => {
        try {
            await fetch(`${API_URL}/api/admin/tables/smmlv`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(window._smmlvData)});
            showToast('SMMLV guardado', 'ok');
        } catch(e) { showToast('Error: ' + e.message, 'err'); }
    };
}

function renderRecipientsTable(data) {
    const el = document.getElementById('tableContent_destinatarios');
    if (!el) return;
    window._recData = { sender: data.sender || {}, recipients: [...(data.recipients || [])] };

    const render = () => {
        el.innerHTML = `
        <div style="margin-bottom:12px;padding:10px;background:var(--c-info-bg);border-radius:6px">
            <div style="font-size:11px;font-weight:600;margin-bottom:6px">Remitente</div>
            <div style="display:flex;gap:8px;flex-wrap:wrap">
                <input placeholder="Nombre remitente" value="${escapeHtml(window._recData.sender.name||'')}" style="padding:4px 8px;border:1px solid var(--c-border);border-radius:4px;font-size:11px;flex:1" onchange="window._recData.sender.name=this.value">
                <input placeholder="Correo remitente" value="${escapeHtml(window._recData.sender.email||'')}" style="padding:4px 8px;border:1px solid var(--c-border);border-radius:4px;font-size:11px;flex:1" onchange="window._recData.sender.email=this.value">
            </div>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
            <span style="font-size:11px;font-weight:600">Destinatarios (${window._recData.recipients.length})</span>
            <div style="display:flex;gap:6px">
                <button class="classif-sort-btn" type="button" onclick="window._recData.recipients.push({name:'',email:''});renderRecInner()">+ Agregar</button>
                <button class="btn-primary" style="font-size:11px;padding:4px 10px" type="button" onclick="saveRecipients()">💾 Guardar</button>
            </div>
        </div>
        <table class="blocker-table" style="font-size:11px">
            <thead><tr><th>Nombre</th><th>Correo electrónico</th><th style="width:40px"></th></tr></thead>
            <tbody>
            ${window._recData.recipients.map((r,i) => `<tr>
                <td><input value="${escapeHtml(r.name||'')}" style="width:100%;border:none;background:transparent;font-size:11px;padding:2px" onchange="window._recData.recipients[${i}].name=this.value"></td>
                <td><input value="${escapeHtml(r.email||'')}" style="width:100%;border:none;background:transparent;font-size:11px;padding:2px" onchange="window._recData.recipients[${i}].email=this.value"></td>
                <td><button type="button" style="background:transparent;border:none;cursor:pointer;color:var(--c-err);font-size:12px" onclick="window._recData.recipients.splice(${i},1);renderRecInner()">✕</button></td>
            </tr>`).join('')}
            </tbody>
        </table>`;
        window.renderRecInner = render;
    };
    render();

    window.saveRecipients = async () => {
        try {
            await fetch(`${API_URL}/api/admin/tables/recipients`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(window._recData)});
            showToast('Destinatarios guardados', 'ok');
        } catch(e) { showToast('Error: ' + e.message, 'err'); }
    };
}

// ── MODAL DOCUMENTO ───────────────────────────────────────────
function openModal(title, caseId, filename, displayName) {
    const modal = document.getElementById('docModal');
    const backdrop = document.getElementById('docModalBackdrop');
    const titleEl = document.getElementById('docModalTitle');
    const body = document.getElementById('docModalBody');
    if (!modal || !body) return;
    titleEl.textContent = displayName || title || filename;
    body.innerHTML = '<div class="loading-msg">Cargando...</div>';
    modal.classList.remove('hidden');
    backdrop.classList.remove('hidden');
    const url = documentViewerUrl(caseId, filename, true);
    const lower = filename.toLowerCase();
    if (lower.endsWith('.pdf')) {
        body.innerHTML = `<div class="doc-frame" style="min-height:500px"><iframe src="${escapeHtml(url)}" style="width:100%;height:600px;border:none"></iframe></div>`;
    } else if (/\.(png|jpg|jpeg|webp|bmp|tif|tiff)$/i.test(lower)) {
        body.innerHTML = `<div style="padding:16px"><img src="${escapeHtml(url)}" style="max-width:100%" alt="${escapeHtml(displayName||filename)}"></div>`;
    } else {
        body.innerHTML = `<div style="padding:16px"><a class="btn-secondary" href="${escapeHtml(url)}" target="_blank">Abrir archivo</a></div>`;
    }
}

function closeModal() {
    document.getElementById('docModal')?.classList.add('hidden');
    document.getElementById('docModalBackdrop')?.classList.add('hidden');
    const body = document.getElementById('docModalBody');
    if (body) body.innerHTML = '';
    if (activeDocumentUrl) { URL.revokeObjectURL(activeDocumentUrl); activeDocumentUrl = null; }
}

// ── INIT ──────────────────────────────────────────────────────
function init() {
    // Login bindings
    document.querySelectorAll('.login-profile-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            saveProfile(btn.dataset.profile);
            document.querySelectorAll('.login-profile-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            document.getElementById('loginNote').textContent = '';
            renderLoginUsers();
        });
    });

    // Sidebar nav
    document.querySelectorAll('.nav-item[data-view]').forEach(btn => {
        btn.addEventListener('click', () => switchView(btn.dataset.view));
    });
    document.getElementById('mobileViewSelect')?.addEventListener('change', e => {
        switchView(e.target.value);
    });

    document.getElementById('digitacionTabs')?.addEventListener('click', e => {
        const tab = e.target.closest('[data-digitacion-tab]');
        if (!tab) return;
        switchDigitacionTab(tab.dataset.digitacionTab);
    });
    document.getElementById('digitacionSaveBtn')?.addEventListener('click', saveDigitacionDraft);
    document.getElementById('digitacionValidateBtn')?.addEventListener('click', () => validateDigitacionWithBackend({ mode: 'full', requireAll: true }));
    document.getElementById('digitacionRunBtn')?.addEventListener('click', runDigitacionWorkflow);
    document.getElementById('digitacionClearBtn')?.addEventListener('click', clearDigitacionDraft);
    document.getElementById('digitacionExportBtn')?.addEventListener('click', exportDigitacionJson);
    document.getElementById('digitacionOpenDocBtn')?.addEventListener('click', e => {
        const btn = e.currentTarget;
        if (!btn?.dataset?.case || !btn?.dataset?.file) return;
        openModal(btn.dataset.title || 'Soporte', btn.dataset.case, btn.dataset.file, btn.dataset.displayName || btn.dataset.file);
    });
    document.getElementById('digitacionDocList')?.addEventListener('click', e => {
        const btn = e.target.closest('[data-digitacion-doc-file]');
        if (!btn) return;
        digitacionEvidenceManualFile = btn.dataset.digitacionDocFile || '';
        const select = document.getElementById('digitacionDocSelect');
        if (select) select.value = digitacionEvidenceManualFile;
        const field = document.activeElement?.classList?.contains('digitacion-field')
            ? document.activeElement
            : digitacionActiveFieldKey
                ? getDigitacionField(digitacionActiveFieldKey)
            : document.querySelector(`[data-digitacion-panel="${digitacionActiveTab}"] .digitacion-field`);
        updateDigitacionEvidenceForField(field, digitacionEvidenceManualFile);
    });
    document.getElementById('digitacionDocSelect')?.addEventListener('change', e => {
        digitacionEvidenceManualFile = e.target.value || '';
        if (!digitacionEvidenceManualFile) digitacionEvidenceDocFile = '';
        const field = document.activeElement?.classList?.contains('digitacion-field')
            ? document.activeElement
            : digitacionActiveFieldKey
                ? getDigitacionField(digitacionActiveFieldKey)
                : document.querySelector(`[data-digitacion-panel="${digitacionActiveTab}"] .digitacion-field`);
        updateDigitacionEvidenceForField(field, digitacionEvidenceManualFile);
    });
    document.querySelectorAll('.js-department-select').forEach(select => {
        select.addEventListener('change', () => {
            updateMunicipalitySelect(select, '');
            const municipality = document.getElementById(select.dataset.municipalityTarget || '');
            if (municipality) {
                municipality.value = '';
                setDigitacionFieldError(municipality, '');
            }
        });
    });
    document.querySelectorAll('.js-municipality-select').forEach(select => {
        select.addEventListener('change', () => {
            syncDepartmentFromMunicipality(select);
            setDigitacionFieldError(select, '');
        });
    });
    getDigitacionFields().forEach(field => {
        field.addEventListener('input', () => {
            const key = field.dataset.digKey;
            if (DIGITACION_ALPHA_KEYS.has(key)) {
                const cleaned = field.value.replace(DIGITACION_ALPHA_CLEAN_RE, '');
                if (field.value !== cleaned) field.value = cleaned;
            }
            if (key === 'sede_centro_trabajo_nombre') {
                const cleaned = field.value.replace(DIGITACION_ALNUM_CLEAN_RE, '').slice(0, 60);
                if (field.value !== cleaned) field.value = cleaned;
            }
            if (DIGITACION_DIGIT_ONLY_KEYS.has(key)) {
                const cleaned = field.value.replace(/\D/g, '');
                if (field.value !== cleaned) field.value = cleaned;
            }
            if (key === 'razon_social') {
                const cleaned = field.value.replace(DIGITACION_ALNUM_CLEAN_RE, '');
                if (field.value !== cleaned) field.value = cleaned;
            }
            if (DIGITACION_SN_KEYS.has(key) || ['novedad_autoliquidacion', 'novedad_origen', 'empresa_zona_localizacion'].includes(key)) {
                const cleaned = field.value.toUpperCase().replace(/[^A-Z]/g, '').slice(0, 1);
                if (field.value !== cleaned) field.value = cleaned;
            }
            normalizeDigitacionFieldInPlace(field);
            const limit = AFILEGA_MDB_FIELD_LIMITS[key];
            if (limit && key !== 'cargo_actividad' && field.value.length > limit) field.value = field.value.slice(0, limit);
            if (key === 'nit') {
                const dvField = getDigitacionField('nit_dv');
                const expected = calculateAfilegaNitDv(field.value);
                if (dvField && expected && !dvField.value) dvField.value = expected;
            }
            if (key === 'fecha_radicacion') {
                syncDigitacionCoverageDate(true);
            }
            if (key === 'fecha_nacimiento') {
                syncDigitacionWorkerAge();
            }
            if (key === 'tipo_documento_afiliado') {
                setDigitacionFieldError(getDigitacionField('documento_afiliado'), '');
            }
            if (key === 'sede_codigo' || key === 'sede_nombre' || key === 'sede_centro_trabajo_nombre') {
                updateTrabajadorCentroOptions();
            }
            if (key === 'codigo_actividad_economica') {
                syncDigitacionActivityDependentFields('codigo_actividad_economica');
            }
            if (key === 'camara_codigo_actividad') {
                const profile = digitacionCamaraActivityProfile(field.value);
                const cameraActivityField = getDigitacionField('camara_actividad_principal');
                const activityName = profile?.nombre || profile?.actividad || '';
                if (cameraActivityField && activityName) {
                    cameraActivityField.value = activityName;
                    normalizeDigitacionFieldInPlace(cameraActivityField);
                }
            }
            if (key === 'sede_codigo_actividad') {
                syncDigitacionActivityDependentFields('sede_codigo_actividad');
            }
            if (key === 'sede_grado') {
                syncDigitacionSedeTarifa();
            }
            if (key === 'empresa_tipo_aportante') {
                const defaults = DIGITACION_TIPO_APORTANTE_DEFAULTS[field.value] || {};
                const claseField = getDigitacionField('empresa_clase_aportante');
                const vinculadorField = getDigitacionField('empresa_vinculador_laboral');
                if (claseField && defaults.clase && !claseField.value) claseField.value = defaults.clase;
                if (vinculadorField && defaults.vinculador && !vinculadorField.value) vinculadorField.value = defaults.vinculador;
            }
            renderDigitacionAutocomplete(field);
            setDigitacionFieldError(field, '');
            updateDigitacionStatus('Cambios sin guardar', 'warn');
            updateDigitacionEvidenceForField(field);
        });
        field.addEventListener('change', () => {
            if (field.dataset.digKey === 'tipo_afiliacion') {
                const data = collectDigitacionData();
                updateDigitacionContractorMode(data, { clearWorkers: digitacionIsContratista(data.values) });
                markDigitacionRequiredFields();
                switchDigitacionTab(digitacionActiveTab);
            }
            if (field.dataset.digKey === 'fecha_radicacion') {
                syncDigitacionCoverageDate(true);
            }
            if (field.dataset.digKey === 'fecha_nacimiento') {
                syncDigitacionWorkerAge();
            }
            if (field.dataset.digKey === 'tipo_documento_afiliado') {
                const docField = getDigitacionField('documento_afiliado');
                if (docField?.value) {
                    setDigitacionFieldError(
                        docField,
                        validateDigitacionValue('documento_afiliado', docField.value, collectDigitacionData().values),
                    );
                }
            }
            if (field.dataset.digKey === 'sede_codigo' || field.dataset.digKey === 'sede_nombre' || field.dataset.digKey === 'sede_centro_trabajo_nombre') {
                updateTrabajadorCentroOptions();
            }
            if (field.dataset.digKey === 'codigo_actividad_economica') {
                syncDigitacionActivityDependentFields('codigo_actividad_economica');
            }
            if (field.dataset.digKey === 'sede_codigo_actividad') {
                syncDigitacionActivityDependentFields('sede_codigo_actividad');
            }
            if (field.dataset.digKey === 'sede_grado') {
                syncDigitacionSedeTarifa();
            }
            if (field.dataset.digKey === 'empresa_tipo_aportante') {
                const defaults = DIGITACION_TIPO_APORTANTE_DEFAULTS[field.value] || {};
                const claseField = getDigitacionField('empresa_clase_aportante');
                const vinculadorField = getDigitacionField('empresa_vinculador_laboral');
                if (claseField && defaults.clase && !claseField.value) claseField.value = defaults.clase;
                if (vinculadorField && defaults.vinculador && !vinculadorField.value) vinculadorField.value = defaults.vinculador;
            }
            const message = validateDigitacionValue(field.dataset.digKey, field.value, collectDigitacionData().values);
            setDigitacionFieldError(field, message);
            updateDigitacionStatus('Cambios sin guardar', 'warn');
            updateDigitacionEvidenceForField(field);
        });
        field.addEventListener('focus', () => {
            renderDigitacionAutocomplete(field);
            updateDigitacionEvidenceForField(field);
        });
        field.addEventListener('blur', () => {
            window.setTimeout(() => hideDigitacionAutocomplete(field), 140);
        });
        field.addEventListener('keydown', e => {
            if (handleDigitacionAutocompleteKeydown(field, e)) return;
            if (e.key !== 'Enter') return;
            if (field.tagName === 'TEXTAREA' && e.shiftKey) return;
            e.preventDefault();
            field.dispatchEvent(new Event('change', { bubbles: true }));
            focusNextDigitacionField(field, e.shiftKey ? -1 : 1);
        });
    });

    // Logout
    document.getElementById('logoutBtn')?.addEventListener('click', () => {
        clearSession(); activeCaseId = null; activeCasePayload = null;
        openLogin();
    });

    // Bandeja tabs
    document.getElementById('bandejaTabsRow')?.addEventListener('click', e => {
        const tab = e.target.closest('.tab');
        if (!tab) return;
        document.querySelectorAll('#bandejaTabsRow .tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        bandejaActiveTab = tab.dataset.tab;
        renderCasesTable(allCases, bandejaActiveTab);
    });

    // Métricas clickeables — filtran la lista de contratos
    document.getElementById('metricsRow')?.addEventListener('click', e => {
        const card = e.target.closest('[data-filter]');
        if (!card) return;
        const filter = card.dataset.filter;
        // Mapear filtro a tab
        const tabMap = {
            'aprobados': 'aprobados',
            'no-aprobados': 'no-aprobados',
        };
        const tab = tabMap[filter] || 'todos';
        // Activar tab correspondiente
        document.querySelectorAll('#bandejaTabsRow .tab').forEach(t => {
            t.classList.toggle('active', t.dataset.tab === tab);
        });
        // Resaltar métrica activa
        document.querySelectorAll('[data-filter]').forEach(c => c.classList.remove('active'));
        card.classList.add('active');
        bandejaActiveTab = tab;
        renderCasesTable(allCases, tab);
        // Scroll a la lista
        document.getElementById('casesTableWrap')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });

    // Refresh bandeja
    document.getElementById('refreshBandejaBtn')?.addEventListener('click', loadBandeja);

    // Upload zone
    setupEntryTypeControls();
    setupUploadZone();

    // Producción
    document.getElementById('clearColmenaBtn')?.addEventListener('click', () => {
        selectedColmenaCaseIds = new Set();
        loadProduccion();
    });
    document.getElementById('downloadColmenaBtn')?.addEventListener('click', downloadColmenaBatch);

    // Entrenamiento
    document.getElementById('saveFeedbackBtn')?.addEventListener('click', saveFeedbackNote);
    document.getElementById('refreshFeedbackBtn')?.addEventListener('click', loadFeedbackNotes);

    // Búsqueda
    document.getElementById('searchBtn')?.addEventListener('click', () => {
        doSearch(document.getElementById('searchInput')?.value);
    });
    document.getElementById('searchInput')?.addEventListener('keydown', e => {
        if (e.key === 'Enter') doSearch(e.target.value);
    });
    document.addEventListener('keydown', handleClassifDocumentKeyboardNav);

    // Modal
    document.getElementById('docModalClose')?.addEventListener('click', closeModal);
    document.getElementById('docModalBackdrop')?.addEventListener('click', closeModal);

    // Arranque
    fetch(`${API_URL}/health`)
        .then(r => r.json())
        .then(d => console.log('AFILEGA_FA_IMA_LA_V2 conectado:', d))
        .catch(e => console.warn('⚠ Health check:', e.message));

    loadTesterRoster();

    if (hasSession()) {
        bootApp();
    } else {
        openLogin();
    }

    // Widget flotante de recursos — polling cada 20s
    async function updateResourceWidget() {
        try {
            const [hR, cR] = await Promise.all([
                fetch(`${API_URL}/health`).catch(() => null),
                fetch(operationApiUrl('/api/cases/production-summary')).catch(() => null),
            ]);
            const h = hR?.ok ? await hR.json() : {};
            const c = cR?.ok ? await cR.json() : {};
            const res = h.resources || {};
            const cases = c.cases || [];
            const enCola = cases.filter(x => ['queued','processing','pending'].includes(String(x.status||''))).length;
            const isOk = h.api === 'healthy';

            const dot = document.getElementById('rwDot');
            const status = document.getElementById('rwStatus');
            const ram = document.getElementById('rwRam');
            const rss = document.getElementById('rwRss');
            const queueEl = document.getElementById('rwQueue');
            const queueVal = document.getElementById('rwQueueVal');

            if (dot) dot.style.background = isOk ? 'var(--c-ok)' : 'var(--c-err)';
            if (status) status.textContent = isOk ? 'OK' : 'Error';
            if (ram) ram.textContent = res.mem_used_mb ? `${res.mem_used_mb}MB` : '—';
            if (rss) rss.textContent = res.process_rss_mb ? `${res.process_rss_mb}MB` : '—';
            if (queueEl) queueEl.style.display = enCola > 0 ? '' : 'none';
            if (queueVal) queueVal.textContent = enCola;
        } catch {}
    }
    updateResourceWidget();
    setInterval(updateResourceWidget, 20000);
}

init();
