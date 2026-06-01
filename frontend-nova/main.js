// ============================================================
// AFI COLIMA · MAIN.JS — Frontend refactorizado
// ============================================================

const rawApiUrl = (import.meta.env.VITE_API_URL || '').trim();
const normalizedApiUrl = rawApiUrl.replace(/\/+$/, '');
const API_URL = (
    !normalizedApiUrl
    || normalizedApiUrl === '/api'
    || /^(https?:)?\/\/(localhost|127\.0\.0\.1)(:\d+)?(\/api)?$/i.test(normalizedApiUrl)
) ? '' : normalizedApiUrl;

const PROFILE_KEY = 'afi-colima-profile-v1';
const TESTER_KEY = 'afi-colima-tester-v1';
const PROCESS_STATE_KEY = 'afi-colima-process-v1';
const CLASSIFICATION_ORDER_KEY = 'afi-colima-classif-order-v1';

const OPERATION_OPTIONS = {
    colima: { key: 'colima', short: 'COLIMA', name: 'AFI Colima', brand: 'AFI Colima · Portal ARL', validation: 'Reglas Colima' },
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
        uploaded:'cargado', completed:'completado', blocked:'bloqueado',
        failed:'fallido', pending:'pendiente', analyzed:'analizado',
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
    const colors = {info:'var(--c-blue)', ok:'var(--c-ok)', err:'var(--c-err)', warn:'#f59e0b'};
    const icons = {info:'ℹ️', ok:'✅', err:'❌', warn:'⚠️'};
    toast.style.cssText = `background:var(--c-bg-2);border:1px solid var(--c-border);border-left:4px solid ${colors[type]||colors.info};border-radius:8px;padding:12px 16px;font-size:13px;color:var(--c-text-1);box-shadow:0 4px 16px rgba(0,0,0,0.12);display:flex;gap:10px;align-items:flex-start;animation:slideIn 0.2s ease`;
    toast.innerHTML = `<span style="flex-shrink:0">${icons[type]||icons.info}</span><span style="flex:1">${escapeHtml(msg)}</span><button onclick="this.parentElement.remove()" style="background:none;border:none;cursor:pointer;color:var(--c-text-2);font-size:16px;padding:0;line-height:1">×</button>`;
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

// ── Sesión / perfil ──────────────────────────────────────────
function readProfile() {
    try { return String(localStorage.getItem(PROFILE_KEY)||'').toLowerCase(); } catch { return ''; }
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
    if (!caseId || !blocker) return;
    const shortMsg = String(blocker.message || '').slice(0, 220);
    const reason = prompt(
        `Justificación para aceptar este hallazgo solo en este contrato:\n\n${shortMsg}`,
        'Validado manualmente por operador'
    );
    if (!reason || !reason.trim()) return;
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
    if (!payload) return;
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
    return item.contract_number || item.numero_contrato || item.nro_contrato || item.nro_afiliacion ||
        legacy.numero_afiliacion || legacy.nro_afiliacion ||
        profile.numero_contrato || profile.nro_contrato || profile.numero_radicacion || profile.nro_radicacion ||
        formFields.numero_radicacion || '';
}

function resolveManualApproval(item) {
    const approval = item?.manual_approval || item?.analysis?.manual_approval || {};
    if (approval && approval.approved) return approval;
    const status = normalizeText(item?.status || item?.analysis?.workflow_run?.status || '');
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
        showToast('Contrato aprobado manualmente.', 'ok', 3500);
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
                document.getElementById('loginNote').textContent = 'Primero selecciona un perfil (Imagine o Colmena).';
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
    document.getElementById('userRole').textContent = p === 'colmena' ? 'Perfil Colmena' : 'Perfil Imagine';
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
        showToast(`Operación activa: ${OPERATION_OPTIONS[next].name}. Bandejas y validaciones separadas.`, 'info');
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
    // Grupo Colmena solo para Colmena
    const navColmena = document.getElementById('navColmena');
    if (navColmena) navColmena.style.display = isColmena ? '' : 'none';
    // Si perfil es Colmena y vista actual no es producción, redirigir
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
    bandeja:       { title: 'Bandeja de entrada',      breadcrumb: 'Operación · contratos activos' },
    flujo:         { title: 'Nuevo contrato',           breadcrumb: 'Operación · cargar expediente' },
    clasificacion: { title: 'Clasificación documental', breadcrumb: 'Operación · documentos por revisar' },
    validacion:    { title: 'Validación OCR',           breadcrumb: 'Revisión · comparación de fuentes' },
    visor:         { title: 'Visor documental',         breadcrumb: 'Revisión · documentos adjuntos' },
    reporte:       { title: 'Reporte ejecutivo',        breadcrumb: 'Revisión · resumen de decisión' },
    produccion:    { title: 'Producción · Colmena',     breadcrumb: 'Colmena · archivo plano' },
    entrenamiento: { title: 'Hallazgos',                breadcrumb: 'Sistema · mejoras y ajustes' },
    busqueda:      { title: 'Búsqueda',                 breadcrumb: 'Sistema · búsqueda documental' },
    admin:         { title: 'Administración',           breadcrumb: 'Sistema · estado y configuración' },
};

function switchView(viewId) {
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
    document.getElementById('pageBreadcrumb').textContent = `${op.name} · ${meta.breadcrumb}`;
    updateMobileNavOptions();
    updateTopbarActions(viewId);

    if (viewId === 'flujo') resetFlujoView();
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
    const url = caseFileUrl(_galleryPayload.id, item.file, true);
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
            return ['processing','pending','uploaded','queued'].includes(s);
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
                return ['processing','pending','uploaded','queued'].includes(s);
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
        const isProcessing = ['processing','pending','uploaded','queued'].includes(wfStatus);
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
    } else if (action === 'clasificacion') {
        activeCaseId = caseId;
        switchView('clasificacion');
        loadClassifForCase(caseId);
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
    try {
        const r = await fetch(case926Url(caseId));
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const blob = await r.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = filename || 'archivo_926.txt';
        document.body.appendChild(a); a.click(); a.remove();
        URL.revokeObjectURL(url);
    } catch(e) { console.error('download926:', e); }
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

async function runWorkflow() {
    const files = window.__uploadFiles || [];
    if (!files.length) return;
    const tester = readTester();
    if (!tester.email) { showToast('Por favor selecciona tu usuario antes de continuar.', 'warn'); return; }

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
        { id: 'precheck', label: 'Ejecutando prevalidación...' },
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
        const label = deriveCaseLabel(files);
        formData.append('label', label);
        formData.append('operation', readOperation());
        formData.append('tester_email', tester.email);
        formData.append('tester_name', tester.name || tester.email);
        for (const f of files) formData.append('files', f, f.name);

        const uploadRes = await fetchWithRetry(operationApiUrl('/api/cases'), {
            method: 'POST',
            body: formData,
        });
        const uploadData = await uploadRes.json();
        const caseId = uploadData.id || uploadData.case_id;
        if (!caseId) throw new Error('El backend no devolvió un ID de caso.');
        activeCaseId = caseId;
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
        if (btn) { btn.disabled = false; btn.textContent = 'Ejecutar prevalidación'; }
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

    const stateClass = approved ? 'ok' : 'err';
    const stateLabel = approved ? 'Aprobado' : 'No aprobado';
    const stateIcon = approved ? '✓' : '✗';

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
            </div>
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
            try { await acceptValidationException(payload.id || activeCaseId, record); }
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
        const r = await fetchWithRetry(caseApiUrl(caseId));
        const payload = await r.json();
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
            try { await acceptValidationException(latestPayload.id || payload.id || activeCaseId, record); }
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

function bindComisionManualPanel(item, payload, root = document) {
    const comisionRows = root.querySelector('#comisionRows');
    const addBtn = root.querySelector('#addComisionRow');
    const saveBtn = root.querySelector('#saveComisiones');
    const saveTipoNegocioBtn = root.querySelector('#saveTipoNegocio');
    const comisionStatus = root.querySelector('#comisionStatus');
    const tipoNegocioSelect = root.querySelector('#tipoNegocioSelect');
    const tipoNegocioStatus = root.querySelector('#tipoNegocioStatus');
    
    if (!comisionRows || !saveBtn || !saveTipoNegocioBtn) return;

    const existingComisiones = payload?.analysis?.manual_review?.comisiones?.[item.file] || [];
    const rawTipoNegocio = payload?.analysis?.xlsx_profile?.profile?.tipo_negocio_detectado || '';

    function renderComisionRow(data = {}) {
        const div = document.createElement('div');
        div.className = 'comision-row';
        div.innerHTML = `
            <select class="field-select comision-codigo">
                <option value="1" ${data.codigo==='1'?'selected':''}>01 - Consultor</option>
                <option value="3" ${data.codigo==='3'?'selected':''}>03 - Corredor</option>
            </select>
            <input class="field-input comision-cedula" placeholder="Nro. documento" value="${escapeHtml(data.cedula||'')}">
            <input class="field-input comision-pct" placeholder="%" value="${escapeHtml(data.porcentaje||'100')}">
            <button class="btn-icon comision-remove-row" type="button">✕</button>
        `;
        div.querySelector('.comision-remove-row')?.addEventListener('click', () => div.remove());
        comisionRows.appendChild(div);
    }

    if (existingComisiones.length) existingComisiones.forEach(c => renderComisionRow(c));
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
                payload.analysis.xlsx_profile.profile.tipo_negocio = tipoNegocio;
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
        const rows = [...comisionRows.querySelectorAll('.comision-row')].map(row => ({
            codigo: row.querySelector('.comision-codigo')?.value || '',
            cedula: row.querySelector('.comision-cedula')?.value?.trim() || '',
            porcentaje: row.querySelector('.comision-pct')?.value?.trim() || '100',
        })).filter(r => r.cedula);

        if (!rows.length) {
            if (comisionStatus) comisionStatus.textContent = 'Agrega al menos un intermediario.';
            return;
        }

        try {
            saveBtn.disabled = true;
            saveBtn.textContent = 'Guardando...';
            const r = await fetchWithRetry(caseApiUrl(payload.id, '/manual-review'), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    kind: 'comisiones',
                    filename: item.file,
                    verdict: 'no',
                    comisiones: rows,
                }),
            });
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            if (comisionStatus) {
                comisionStatus.style.color = 'var(--c-ok)';
                comisionStatus.textContent = `✓ ${rows.length} intermediario(s) guardados`;
            }
            if (tipoNegocioSelect) {
                tipoNegocioSelect.style.color = 'var(--c-ok)';
                tipoNegocioStatus.textContent = `✓ Tipo de negocio: ${tipoNegocioSelect.value}`;
            }
        } catch(e) {
            if (comisionStatus) {
                comisionStatus.style.color = 'var(--c-err)';
                comisionStatus.textContent = 'Error: ' + e.message;
            }
            if (tipoNegocioStatus && !tipoNegocioSelect?.value) {
                tipoNegocioStatus.style.color = 'var(--c-err)';
                tipoNegocioStatus.textContent = 'Error: ' + e.message;
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
        if (!f || seen.has(f)) continue;
        seen.add(f);
        items.push({ file: f, kind: 'xlsx', type: 'xlsx', label: 'Archivo base XLSX', displayName: f, _sourceIndex: sourceIndex++ });
    }
    // PDFs desde received_summary (ya clasificados)
    for (const group of received) {
        for (const f of (group.files||[])) {
            if (!f || seen.has(f)) continue;
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
        if (!f || seen.has(f)) continue;
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
        if (!f || seen.has(f)) continue;
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
    // Formato legacy: manual_review.reviews es un array
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
            ${item.corrected ? '<span class="doc-item-corrected">corregido</span>' : ''}
            ${sedeLabel ? `<span class="doc-item-corrected" title="Sede asignada">${escapeHtml(sedeLabel)}</span>` : ''}
            ${item.kind !== 'xlsx' && !isApproved ? `
            <span class="doc-item-actions">
                <button class="doc-action-btn doc-duplicate-btn" data-file="${escapeHtml(item.file)}" title="Duplicar imagen" type="button">⧉ Dup</button>
                <button class="doc-action-btn doc-delete-btn" data-file="${escapeHtml(item.file)}" title="Eliminar imagen" type="button">✕ Elim</button>
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
                [newItems[currentIdx], newItems[targetIdx]] = [newItems[targetIdx], newItems[currentIdx]];
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

async function renderDocPreview(container, caseId, item) {
    if (!caseId || !item.file) { container.innerHTML = '<div class="empty-state">Sin vista previa</div>'; return; }
    const url = caseFileUrl(caseId, item.file, true);
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
            try {
                const respData = await r.json();
                ragMensaje = respData?.rag_mensaje || '';
            } catch {}

            const newLabel = getReviewTypeLabelWithCode(newType, null);

            // Actualizar el item en memoria
            item.type = newType;
            item.label = newLabel;
            item.corrected = true;

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
        html += `<div class="report-section-title" style="margin-bottom:8px">Bloqueantes de prevalidación</div>`;
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
            try { await acceptValidationException(payload.id || activeCaseId, record); }
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
        responsable_sede_principal_tipo_documento: 'Tipo doc. resp.',
        responsable_sede_principal_numero_documento: 'Documento resp.',
        responsable_sede_principal_documento: 'Documento responsable',
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
        ['Cotización', centro.monto_cotizacion],
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

function renderEmpresaInfoCollapsible(formFields, profile, resumen, meta = {}) {
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
        ['responsable_sede_principal_nombre_completo', formFields.responsable_sede_principal_nombre_completo],
        ['responsable_sede_principal_documento', responsableSedeDocumento],
    ];
    const sections = [
        ['Datos del empleador', empleadorEntries],
        ['Afiliación / traslado', afiliacionEntries],
        ['Representante legal', representanteEntries],
        ['Sede principal', sedePrincipalEntries],
    ].filter(([, entries]) => entries.some(([, value]) => !isBlankFormValue(value)));

    if (!sections.length) return '';
    return `
        <details class="company-info-collapse" id="companyInfoCollapse">
            <summary class="company-info-native-summary">Detalles</summary>
            <div class="company-info-body">
                ${sections.map(([title, entries]) => `
                    <section class="company-info-section">
                        <div class="company-info-section-title">${escapeHtml(title)}</div>
                        ${renderCompactInfoTable(entries)}
                    </section>
                `).join('')}
            </div>
        </details>
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
    const stateClass = approved ? 'aprobado' : 'bloqueado';
    const stateLabel = approved ? 'APROBADO' : 'NO APROBADO';
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
                <button class="btn-secondary" id="companyInfoToggle" type="button" aria-expanded="false" aria-controls="companyInfoCollapse">Información Empresa</button>
                <button class="btn-secondary" data-action="clasificacion" data-case="${escapeHtml(caseId)}" type="button">Ver documentos</button>
            </div>
        </div>
        ${renderEmpresaInfoCollapsible(formFields, profile, resumen, { nroAfiliacion, fecha })}
        <div class="report-body report-body-form">
            <div class="form-review-split">
                <section class="form-review-pane form-review-info">
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
    const companyInfoCollapse = container.querySelector('#companyInfoCollapse');
    const toggleSedeInfoBtn = container.querySelector('#toggleSedeInfoBtn');
    const formInfoPane = container.querySelector('.form-review-info');
    companyInfoToggle?.addEventListener('click', () => {
        if (!companyInfoCollapse) return;
        companyInfoCollapse.open = !companyInfoCollapse.open;
        companyInfoToggle.setAttribute('aria-expanded', companyInfoCollapse.open ? 'true' : 'false');
        companyInfoToggle.textContent = companyInfoCollapse.open ? 'Ocultar información' : 'Información Empresa';
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
    const stateClass = approved ? 'aprobado' : 'bloqueado';
    const stateLabel = approved ? 'APROBADO' : 'NO APROBADO';

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
                <button class="btn-secondary" data-panel="comisiones" id="btnComisiones" type="button">Comisiones</button>
                ${has926 ? `<button class="btn-primary" data-action="descargar926" data-case="${escapeHtml(caseId)}" data-file="${escapeHtml(filename926)}" type="button">Descargar plano</button>` : ''}
                ${!isAprobable ? `<button class="btn-warn" id="reprocesarBtn" data-case="${escapeHtml(caseId)}" type="button" title="Volver a ejecutar la prevalidación">↺ Reprocesar</button>` : ''}
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
            try { await acceptValidationException(caseId, record); }
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
                                <td style="text-align:right">${escapeHtml(c.monto_cotizacion||'')}</td>
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
                const mr = a.manual_review || {};
                const comisionesManuales = mr.comisiones || {};
                const docs = a.documents || [];
                const entregaDocs = docs.filter(d => d.document_type === 'entrega_documentos');
                const intermediarios = a.validacion_resumen?.matches?.entrega_documentos_intermediario || {};

                let comisionHTML = `
                    <div class="blocker-panel-head">
                        <span class="blocker-panel-title">💰 Comisiones e intermediación</span>
                        <button class="btn-icon" id="dataPanelClose">✕</button>
                    </div>
                    <div style="padding:12px;max-height:500px;overflow-y:auto">`;

                if (Object.keys(comisionesManuales).length) {
                    comisionHTML += `<div style="font-size:12px;font-weight:600;margin-bottom:8px">Comisiones registradas manualmente:</div>`;
                    for (const [fname, rows] of Object.entries(comisionesManuales)) {
                        comisionHTML += `<div style="font-size:11px;color:var(--c-text-2);margin-bottom:4px">📄 ${escapeHtml(fname)}</div>`;
                        comisionHTML += `<table class="blocker-table" style="margin-bottom:12px">
                            <thead><tr><th>Código</th><th>Documento</th><th>Porcentaje</th></tr></thead>
                            <tbody>${(rows||[]).map(r => `<tr>
                                <td>${escapeHtml(String(r.codigo||''))}</td>
                                <td>${escapeHtml(String(r.cedula||''))}</td>
                                <td>${escapeHtml(String(r.porcentaje||''))}%</td>
                            </tr>`).join('')}</tbody></table>`;
                    }
                } else if (intermediarios.codigo_intermediario) {
                    comisionHTML += `<div style="font-size:12px;font-weight:600;margin-bottom:8px">Comisiones leídas del OCR:</div>
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
                document.getElementById('btnComisiones')?.classList.remove('active');
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

        const mr = a.manual_review || {};
        const comisionesManuales = mr.comisiones || {};
        const docs = a.documents || [];
        const entregaDocs = docs.filter(d => d.document_type === 'entrega_documentos');
        const intermediarios = a.validacion_resumen?.matches?.entrega_documentos_intermediario || {};
        const todosInterm = intermediarios.todos_intermediarios || [];

        // Construir tabla de intermediarios
        let tablaHTML = '';
        if (Object.keys(comisionesManuales).length) {
            for (const [fname, rows] of Object.entries(comisionesManuales)) {
                tablaHTML += `<div style="font-size:11px;color:var(--c-text-2);margin-bottom:4px">📄 ${escapeHtml(fname)} (manual)</div>
                    <table class="blocker-table" style="margin-bottom:12px">
                    <thead><tr><th>Código</th><th>Documento</th><th>Nombre</th><th>% Participación</th></tr></thead>
                    <tbody>${(rows||[]).map(r => `<tr>
                        <td>${escapeHtml(String(r.codigo||''))}</td>
                        <td>${escapeHtml(String(r.cedula||''))}</td>
                        <td>${escapeHtml(String(r.nombre||''))}</td>
                        <td>${escapeHtml(String(r.porcentaje||''))}%</td>
                    </tr>`).join('')}</tbody></table>`;
            }
        } else if (todosInterm.length) {
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
        if (!confirm('¿Reprocesar este contrato? Se volverá a ejecutar la prevalidación completa.')) return;
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
        const r = await fetch(`${API_URL}/api/926/consolidated`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ case_ids: ids, operation: readOperation() }),
        });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
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

        // Asesores
        renderAsesoresTable(aseR);

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

function renderAsesoresTable(data) {
    const el = document.getElementById('tableContent_asesores');
    if (!el) return;
    window._aseData = { comerciales: [...data.comerciales], intermediarios: [...data.intermediarios] };

    window.renderAse = () => {
        ['comerciales','intermediarios'].forEach(tipo => {
            const items = window._aseData[tipo];
            const body = document.getElementById(`ase_${tipo}_body`);
            const count = document.getElementById(`ase_${tipo}_count`);
            if (count) count.textContent = items.length;
            if (body) body.innerHTML = `<div style="overflow-x:auto;max-height:300px;overflow-y:auto">
            <table class="blocker-table" style="font-size:11px">
                <thead><tr><th>Cédula/NIT</th><th>Nombre</th><th>Tipo</th><th style="width:40px"></th></tr></thead>
                <tbody>${items.map((row,i) => `<tr>
                    <td><input value="${escapeHtml(String(row.cedula??''))}" style="width:100%;border:none;background:transparent;font-size:11px" onchange="window._aseData.${tipo}[${i}].cedula=this.value"></td>
                    <td><input value="${escapeHtml(String(row.nombre??''))}" style="width:100%;border:none;background:transparent;font-size:11px" onchange="window._aseData.${tipo}[${i}].nombre=this.value"></td>
                    <td><input value="${escapeHtml(String(row.tipo??''))}" style="width:80px;border:none;background:transparent;font-size:11px" onchange="window._aseData.${tipo}[${i}].tipo=this.value"></td>
                    <td><button type="button" style="background:transparent;border:none;cursor:pointer;color:var(--c-err)" onclick="window._aseData.${tipo}.splice(${i},1);window.renderAse()">✕</button></td>
                </tr>`).join('')}</tbody>
            </table></div>`;
        });
    };

    el.innerHTML = `
    <div style="display:flex;justify-content:flex-end;margin-bottom:12px">
        <button class="btn-primary" style="font-size:11px;padding:5px 14px" type="button" onclick="window.saveAsesores()">💾 Guardar todos los asesores</button>
    </div>
    <div style="font-weight:600;font-size:12px;margin-bottom:6px;display:flex;align-items:center;gap:8px">
        Comerciales (<span id="ase_comerciales_count">${data.comerciales.length}</span>)
        <button class="classif-sort-btn" type="button" onclick="window._aseData.comerciales.unshift({cedula:'',nombre:'',tipo:'consultor'});window.renderAse()">+ Agregar</button>
    </div>
    <div id="ase_comerciales_body"></div>
    <div style="font-weight:600;font-size:12px;margin:14px 0 6px;display:flex;align-items:center;gap:8px">
        Intermediarios (<span id="ase_intermediarios_count">${data.intermediarios.length}</span>)
        <button class="classif-sort-btn" type="button" onclick="window._aseData.intermediarios.unshift({cedula:'',nombre:'',tipo:'AGENCIA'});window.renderAse()">+ Agregar</button>
    </div>
    <div id="ase_intermediarios_body"></div>`;

    window.renderAse();

    window.saveAsesores = async () => {
        try {
            const r = await fetch(`${API_URL}/api/admin/tables/asesores`, {
                method:'POST', headers:{'Content-Type':'application/json'},
                body: JSON.stringify({comerciales: window._aseData.comerciales, intermediarios: window._aseData.intermediarios})
            });
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            showToast(`Asesores guardados — ${window._aseData.comerciales.length + window._aseData.intermediarios.length} registros`, 'ok');
        } catch(e) { showToast('Error: ' + e.message, 'err'); }
    };
}

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
    const url = caseFileUrl(caseId, filename, true);
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

    // Modal
    document.getElementById('docModalClose')?.addEventListener('click', closeModal);
    document.getElementById('docModalBackdrop')?.addEventListener('click', closeModal);

    // Arranque
    fetch(`${API_URL}/health`)
        .then(r => r.json())
        .then(d => console.log('✅ AFI Colima conectado:', d))
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
