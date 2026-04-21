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

const FRONTEND_BUILD_ID = 'afi-colima-2026.04.16';
const PROFILE_KEY = 'afi-colima-profile-v1';
const TESTER_KEY = 'afi-colima-tester-v1';
const PROCESS_STATE_KEY = 'afi-colima-process-v1';
const CLASSIFICATION_ORDER_KEY = 'afi-colima-classif-order-v1';

const REVIEW_TYPE_OPTIONS = [
    ['formulario_afiliacion', 'Afiliación',        '01'],
    ['anexo_sedes',           'Sedes',              '01'],
    ['listado_trabajadores',  'Listados',           '03'],
    ['comision',              'Comisión',           '02'],
    ['carta',                 'Carta',              '04'],
    ['camara_comercio',       'Cámara de comercio', '05'],
    ['cedula',                'Cédula',             '06'],
    ['constancia_afiliacion', 'Verificación',       '07'],
    ['rut',                   'RUT / DIAN',         '08'],
    ['entrega_documentos',    'Entrega Doc',        '10'],
    ['soporte_ingresos',      'Pagos',              '11'],
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

function formatCurrency(v) {
    const n = Number(v);
    if (!Number.isFinite(n)) return String(v || 'n/d');
    return new Intl.NumberFormat('es-CO', { style:'currency', currency:'COP', minimumFractionDigits:0 }).format(n);
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
    const match = REVIEW_TYPE_OPTIONS.find(([v]) => v === type);
    return match ? match[1] : String(type||'Sin clasificar').replace(/_/g,' ');
}

function getReviewTypeCode(type) {
    const match = REVIEW_TYPE_OPTIONS.find(([v]) => v === type);
    return match ? match[2] : null;
}

function getReviewTypeLabelWithCode(type, legacyCode) {
    const label = getReviewTypeLabel(type);
    const code = legacyCode != null ? String(legacyCode).padStart(2,'0') : getReviewTypeCode(type);
    return code ? `${label} ·${code}` : label;
}

async function fetchWithRetry(url, options = {}, attempts = 2) {
    let lastErr;
    for (let i = 0; i < attempts; i++) {
        try {
            const r = await fetch(url, options);
            if (!r.ok) {
                const t = await r.text().catch(()=>'');
                let detail = '';
                try {
                    const parsed = JSON.parse(t);
                    if (Array.isArray(parsed?.detail)) {
                        // Errores de validación Pydantic
                        detail = parsed.detail.map(e => e.msg || JSON.stringify(e)).join('; ');
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
    const base = `${API_URL}/api/cases/${encodeURIComponent(caseId)}/files/${filename.split('/').map(encodeURIComponent).join('/')}`;
    const url = new URL(base, window.location.origin);
    if (inline) url.searchParams.set('inline', '1');
    return url.toString();
}

function case926Url(caseId) {
    return `${API_URL}/api/cases/${encodeURIComponent(caseId)}/926`;
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

function renderBlockers(blockers, cssClass = 'report-blocker') {
    if (!blockers?.length) return '';
    return blockers.slice(0,10).map(b => `
        <div class="${cssClass}">
            <span>✗</span>
            <span>${escapeHtml(blockerText(b))}</span>
        </div>
    `).join('');
}

function resolveCase(item) {
    const a = item?.analysis || {};
    const wf = a.workflow_run || {};
    const profile = (a.xlsx_profile || {}).profile || {};
    const report = wf.executive_report_final || wf.executive_report_precheck || a.reporte_ejecutivo || {};
    const resumen = report.resumen_ejecutivo || {};
    const empresa = resumen.empresa || profile.empresa || item?.empresa || item?.label || item?.id || 'n/d';
    const nit = resumen.nit || profile.nit || item?.nit || 'n/d';
    const status = wf.status || item?.status || '';
    const finalStatus = item?.final_status || resumen.estado || '';
    const fecha = resumen.fecha_proceso_human || item?.updated_at?.slice(0,10) || 'n/d';
    const has926 = Boolean(item?.has_926 || (wf.output_926||{}).legacy?.ok);
    const filename = (wf.output_926||{}).legacy?.filename || item?.filename || 'archivo_plano.txt';
    const blockers = Array.isArray(item?.blockers) ? item.blockers : [];
    // Número de contrato / afiliación
    const legacy = (wf.output_926||{}).legacy || {};
    const nroAfiliacion = legacy.numero_afiliacion || legacy.nro_afiliacion || profile.numero_contrato || profile.nro_contrato || item?.nro_afiliacion || '';
    const nroRadicacion = profile.numero_radicacion || profile.nro_radicacion || a.formulario_profile?.numero_radicacion || '';
    return { empresa, nit, status, finalStatus, fecha, has926, filename, blockers, nroAfiliacion, nroRadicacion };
}

function caseStatusClass(status, finalStatus) {
    const s = normalizeText(status);
    const f = normalizeText(finalStatus);
    if (s === 'stopped_prevalidacion' || f.includes('rechaz')) return 'err';
    if (s === 'completed' && (f.includes('aprob') || f === 'ok' || f === 'completed' || !f)) return 'ok';
    if (f.includes('observ')) return 'warn';
    if (s === 'failed') return 'err';
    if (s === 'analyzed') return 'warn';
    if (s === 'completed') return 'ok';
    return 'neutral';
}

function casePillLabel(status, finalStatus) {
    const s = normalizeText(status);
    const f = normalizeText(finalStatus);
    if (s === 'stopped_prevalidacion') return 'No pasó validación';
    if (f.includes('rechaz')) return 'No pasó validación';
    if (f.includes('aprob') || (s === 'completed' && (f === 'completed' || !f))) return 'Aprobable';
    if (f.includes('observ')) return 'Observado';
    if (f.includes('bloque')) return 'Bloqueado';
    if (s === 'completed') return 'Completado';
    if (s === 'analyzed') return 'Analizado';
    if (s === 'failed') return 'Error';
    if (['uploaded','pending','processing','queued'].includes(s)) return 'En proceso';
    return localizeStatus(status) || 'Pendiente';
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
    showNavColmena();
    switchView('bandeja');
    loadBandeja();
    document.getElementById('adminBuildId').textContent = FRONTEND_BUILD_ID;
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

function showNavColmena() {
    const p = readProfile();
    const isColmena = p === 'colmena';
    // Grupos solo para Imagine
    ['navOperacion', 'navRevision', 'navSistema'].forEach(id => {
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
    entrenamiento: { title: 'Entrenamiento',            breadcrumb: 'Sistema · feedback del operador' },
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
    document.getElementById('pageTitle').textContent = meta.title;
    document.getElementById('pageBreadcrumb').textContent = meta.breadcrumb;
    updateTopbarActions(viewId);

    if (viewId === 'flujo') resetFlujoView();
    if (viewId === 'bandeja') loadBandeja();
    if (viewId === 'produccion') loadProduccion();
    if (viewId === 'entrenamiento') { loadFeedbackNotes(); syncFeedbackName(); }
    if (viewId === 'busqueda') { doSearch(''); }
    if (viewId === 'admin') loadSystemStatus();
    if (viewId === 'clasificacion') {
        populateCaseSelect('classifCaseSelect', onClassifCaseChange);
        // Si hay un caso activo pendiente de cargar, cargarlo después del populate
        if (activeCaseId) setTimeout(() => loadClassifForCase(activeCaseId), 100);
    }
    if (viewId === 'validacion') populateCaseSelect('validacionCaseSelect', onValidacionCaseChange);
    if (viewId === 'visor') populateCaseSelect('visorCaseSelect', onVisorCaseChange);
    if (viewId === 'reporte') loadReporteSidebar();
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
        const r = await fetchWithRetry(`${API_URL}/api/cases/production-summary`);
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
    let enProceso = 0, aprobables = 0, observados = 0, noAprobados = 0;
    for (const c of cases) {
        const { status, finalStatus } = resolveCase(c);
        const s = normalizeText(status);
        const f = normalizeText(finalStatus);
        if (s === 'completed' && (f.includes('aprob') || f === 'ok' || f === 'completed' || !f)) { aprobables++; continue; }
        if (s === 'stopped_prevalidacion') { noAprobados++; continue; }
        if (f.includes('observ') || s === 'completed') { observados++; continue; }
        enProceso++;
    }
    document.getElementById('metricEnProceso').textContent = enProceso;
    document.getElementById('metricAprobables').textContent = aprobables;
    document.getElementById('metricObservados').textContent = observados;
    document.getElementById('metricNoAprobados').textContent = noAprobados;
    document.getElementById('metricEnProcesoSub').textContent = enProceso ? 'en prevalidación' : '';
    document.getElementById('metricAprobablesSub').textContent = aprobables ? 'listos para plano' : '';
    document.getElementById('metricObservadosSub').textContent = observados ? 'requieren revisión' : '';
    document.getElementById('metricNoAprobadosSub').textContent = noAprobados ? 'no pasaron validación' : '';
}

function filterCasesByTab(cases, tab) {
    if (tab === 'todos') return cases;
    if (tab === 'aprobables') return cases.filter(c => {
        const { status, finalStatus } = resolveCase(c);
        const s = normalizeText(status), f = normalizeText(finalStatus);
        return s === 'completed' && (f.includes('aprob') || f === 'ok' || f === 'completed' || !f);
    });
    if (tab === 'observados') return cases.filter(c => {
        const { status, finalStatus } = resolveCase(c);
        const s = normalizeText(status), f = normalizeText(finalStatus);
        return f.includes('observ') || (s === 'completed' && !f.includes('aprob') && f !== 'ok' && f !== 'completed');
    });
    if (tab === 'no-aprobados') return cases.filter(c => {
        const { status } = resolveCase(c);
        return normalizeText(status) === 'stopped_prevalidacion';
    });
    if (tab === 'cola') return cases.filter(c => {
        const { status, finalStatus } = resolveCase(c);
        const s = normalizeText(status), f = normalizeText(finalStatus);
        // Casos que NO están terminados ni rechazados — pendientes de acción
        return !['completed','stopped_prevalidacion'].includes(s) || 
               (['uploaded','pending','processing','queued','analyzing','analyzed'].includes(s));
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
            const r = await fetch(`${API_URL}/api/cases/production-summary`);
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
        const cls = isProcessing ? 'processing' : caseStatusClass(status, finalStatus);
        const label = isProcessing ? 'Procesando...' : casePillLabel(status, finalStatus);
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
                    <div class="case-card-empresa">${escapeHtml(empresa)}</div>
                    <div class="case-card-meta">NIT ${escapeHtml(nit)}${nroAfiliacion ? ` · Contrato ${escapeHtml(nroAfiliacion)}` : ''} · ${escapeHtml(fechaHora)}</div>
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
                    <div class="case-card-actions" role="group">
                        <button class="table-action-link" data-action="reporte" data-case="${escapeHtml(id)}" type="button">Reporte</button>
                        <button class="table-action-link" data-action="clasificacion" data-case="${escapeHtml(id)}" type="button">Docs</button>
                        <button class="table-action-link" data-action="recuperar" data-case="${escapeHtml(id)}" type="button">Recuperar</button>
                        ${has926 ? `<button class="table-action-link" data-action="descargar926" data-case="${escapeHtml(id)}" data-file="${escapeHtml(filename)}" type="button">Plano ↓</button>` : ''}
                        ${readProfile() !== 'colmena' ? `<button class="table-action-link table-action-danger" data-action="eliminar" data-case="${escapeHtml(id)}" data-empresa="${escapeHtml(empresa)}" type="button">✕</button>` : ''}
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
            if (el) renderReporte(el, activeCasePayload);
        }
    } else if (action === 'eliminar') {
        const empresa = document.querySelector(`[data-action="eliminar"][data-case="${caseId}"]`)?.dataset?.empresa || caseId;
        if (!confirm(`¿Eliminar el contrato de ${empresa}?\n\nEsta acción eliminará el expediente y todos sus archivos adjuntos. No se puede deshacer.`)) return;
        try {
            const r = await fetch(`${API_URL}/api/cases/${encodeURIComponent(caseId)}`, { method: 'DELETE' });
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            // Remover tarjeta del DOM inmediatamente
            const card = document.querySelector(`[data-default-case="${caseId}"]`);
            if (card) card.remove();
            // Actualizar métricas
            allCases = allCases.filter(c => c.id !== caseId);
            renderMetrics(allCases);
        } catch(e) {
            alert('No se pudo eliminar el contrato: ' + e.message);
        }
    }
}

async function loadActiveCaseFull(caseId) {
    try {
        const r = await fetchWithRetry(`${API_URL}/api/cases/${encodeURIComponent(caseId)}`);
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
    if (!tester.email) { alert('Por favor selecciona tu usuario antes de continuar.'); return; }

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
        formData.append('tester_email', tester.email);
        formData.append('tester_name', tester.name || tester.email);
        for (const f of files) formData.append('files', f, f.name);

        const uploadRes = await fetchWithRetry(`${API_URL}/api/cases`, {
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

        const wfRes = await fetchWithRetry(`${API_URL}/api/cases/${encodeURIComponent(caseId)}/run-workflow`, {
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
                const statusRes = await fetch(`${API_URL}/api/cases/${encodeURIComponent(caseId)}`);
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
        if (progressMsg) progressMsg.textContent = 'Error: ' + e.message;
        if (statusPill) { statusPill.className = 'status-pill err'; statusPill.textContent = 'Error'; }
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
    const isAprobable = normalizeText(estado).includes('aprob') || normalizeText(wf.status||'') === 'completed';
    const isNoAprobado = normalizeText(wf.status||'') === 'stopped_prevalidacion';
    const decision = a.decision || {};
    const blockers = Array.isArray(decision.blockers) ? decision.blockers :
                     Array.isArray(report.bloqueantes) ? report.bloqueantes : [];
    const has926 = Boolean((wf.output_926||{}).legacy?.ok);
    const filename926 = (wf.output_926||{}).legacy?.filename || 'archivo_core.txt';

    const stateClass = isNoAprobado ? 'err' : (isAprobable ? 'ok' : 'warn');
    const stateLabel = isNoAprobado ? 'No pasó validación' : (isAprobable ? 'Aprobable' : 'Observado');
    const stateIcon = isNoAprobado ? '✗' : (isAprobable ? '✓' : '⚠');

    el.innerHTML = `
        <div class="result-header">
            <div class="result-status-icon">${stateIcon}</div>
            <div>
                <div style="margin-bottom:6px"><span class="pill pill-${stateClass}">${escapeHtml(stateLabel)}</span></div>
                <div class="result-empresa">${escapeHtml(empresa)}</div>
                <div class="result-nit">NIT: ${escapeHtml(nit)}</div>
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
                    ${renderBlockers(blockers, 'result-blocker-item')}
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
}

// ── CLASIFICACIÓN ────────────────────────────────────────────
async function populateCaseSelect(selectId, onChangeFn) {
    const sel = document.getElementById(selectId);
    if (!sel) return;
    try {
        const r = await fetchWithRetry(`${API_URL}/api/cases/production-summary`);
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
    const sel = document.getElementById('classifCaseSelect');
    if (sel) sel.value = caseId;
    const listEl = document.getElementById('classifDocList');
    if (listEl) listEl.innerHTML = '<div class="loading-msg">Cargando documentos...</div>';
    try {
        const r = await fetchWithRetry(`${API_URL}/api/cases/${encodeURIComponent(caseId)}`);
        const payload = await r.json();
        activeCaseId = caseId;
        activeCasePayload = payload;

        // Mostrar nombre del contrato como contexto fijo
        const { empresa, nit } = resolveCase(payload);
        const labelEl = document.getElementById('classifCaseLabel');
        if (labelEl) {
            labelEl.style.display = '';
            labelEl.innerHTML = `📋 ${escapeHtml(empresa)}${nit !== 'n/d' ? ` · ${escapeHtml(nit)}` : ''}`;
        }

        renderClassifDocList(payload);
    } catch(e) {
        if (listEl) listEl.innerHTML = `<div class="error-msg">${escapeHtml(e.message)}</div>`;
    }
}

function onClassifCaseChange(caseId) { loadClassifForCase(caseId); }

function buildDocItems(payload) {
    if (!payload) return [];
    const items = [];
    const a = payload.analysis || {};
    const manualReview = a.manual_review || {};
    const docMeta = buildDocMetaMap(payload);
    const received = Array.isArray(a.checklist?.received_summary) ? a.checklist.received_summary : [];
    const seen = new Set();
    // Orden del workspace
    const workspaceOrder = Array.isArray(a.document_workspace?.order) ? a.document_workspace.order : [];

    // XLSX primero
    const xlsxFiles = collectXlsxFiles(payload);
    for (const f of xlsxFiles) {
        if (!f || seen.has(f)) continue;
        seen.add(f);
        items.push({ file: f, kind: 'xlsx', type: 'xlsx', label: 'Archivo base XLSX', displayName: f });
    }
    // PDFs desde received_summary (ya clasificados)
    for (const group of received) {
        for (const f of (group.files||[])) {
            if (!f || seen.has(f)) continue;
            seen.add(f);
            const meta = docMeta[f] || {};
            const reviewEntry = getManualReviewEntry(manualReview, 'document', f);
            const effectiveType = reviewEntry?.verdict === 'no' && reviewEntry.expected_type
                ? reviewEntry.expected_type
                : (meta.document_type || group.label || 'pdf');
            const isCorrected = reviewEntry?.verdict === 'no';
            const legacyCode = isCorrected ? null : (meta.legacy_code ?? null);
            items.push({ file: f, kind: 'document', type: effectiveType, label: getReviewTypeLabelWithCode(effectiveType, legacyCode), displayName: meta.display_name || f, corrected: isCorrected });
        }
    }
    // Agregar documentos del análisis que no aparecieron en received_summary
    for (const [f, meta] of Object.entries(docMeta)) {
        if (!f || seen.has(f)) continue;
        seen.add(f);
        const reviewEntry = getManualReviewEntry(manualReview, 'document', f);
        const effectiveType = reviewEntry?.verdict === 'no' && reviewEntry.expected_type
            ? reviewEntry.expected_type
            : (meta.document_type || 'pdf');
        items.push({ file: f, kind: 'document', type: effectiveType, label: getReviewTypeLabel(effectiveType), displayName: meta.display_name || f, corrected: reviewEntry?.verdict === 'no' });
    }
    // Agregar archivos físicos del caso que no aparecieron en ningún análisis
    const physicalFiles = (payload.files || []).map(f => f.filename || f.file || '').filter(Boolean);
    for (const f of physicalFiles) {
        if (!f || seen.has(f)) continue;
        const lower = f.toLowerCase();
        if (lower.endsWith('.xlsx') || lower.endsWith('.xls') || lower.endsWith('.xlsm')) continue;
        seen.add(f);
        items.push({ file: f, kind: 'document', type: 'pdf', label: f.replace(/\.[^.]+$/, ''), displayName: f, corrected: false });
    }
    // Aplicar orden del workspace si existe
    if (workspaceOrder.length) {
        const byFile = Object.fromEntries(items.map(it => [it.file, it]));
        const ordered = [];
        for (const f of workspaceOrder) {
            if (byFile[f]) { ordered.push(byFile[f]); delete byFile[f]; }
        }
        // Agregar los que no están en el orden al final
        for (const it of Object.values(byFile)) ordered.push(it);
        return ordered;
    }
    return items;
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
        if (entry) return { file, expected_type: entry.expected_type, verdict: entry.verdict };
    }
    // Formato legacy: manual_review.reviews es un array
    return (Array.isArray(manualReview.reviews) ? manualReview.reviews : []).find(r => r.file === file) || null;
}

function renderClassifDocList(payload, sortBy = 'default', sortDir = 1) {
    const el = document.getElementById('classifDocList');
    const preview = document.getElementById('classifPreviewBody');
    const previewTitle = document.getElementById('classifPreviewTitle');
    if (!el) return;
    let items = buildDocItems(payload);
    if (!items.length) {
        el.innerHTML = '<div class="empty-state">No hay documentos en este contrato</div>';
        return;
    }

    // Ordenar según columna seleccionada
    if (sortBy === 'tipo') {
        items = [...items].sort((a,b) => sortDir * (a.type||'').localeCompare(b.type||''));
    } else if (sortBy === 'nombre') {
        items = [...items].sort((a,b) => sortDir * (a.label||'').localeCompare(b.label||''));
    } else if (sortBy === 'estado') {
        items = [...items].sort((a,b) => sortDir * (Number(b.corrected||0) - Number(a.corrected||0)));
    }

    // Header con conteo y botones de ordenamiento
    const headerEl = el.previousElementSibling;
    if (headerEl && headerEl.classList.contains('classif-doc-header')) {
        headerEl.remove();
    }
    const header = document.createElement('div');
    header.className = 'classif-doc-header';
    header.style.cssText = 'padding:6px 8px 2px;font-size:11px;color:var(--c-text-2);border-bottom:1px solid var(--c-border);margin-bottom:2px';
    const dirs = (col) => sortBy === col ? (sortDir === 1 ? ' ↑' : ' ↓') : '';
    header.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
            <span>${items.length} documentos</span><span style="font-size:10px;opacity:0.7">↕ scroll</span>
        </div>
        <div style="display:flex;gap:4px;flex-wrap:wrap">
            <span style="font-size:10px;opacity:0.6;margin-right:2px">Ordenar:</span>
            <button class="classif-sort-btn ${sortBy==='default'?'active':''}" data-sort="default" type="button">Original</button>
            <button class="classif-sort-btn ${sortBy==='tipo'?'active':''}" data-sort="tipo" type="button">Tipo${dirs('tipo')}</button>
            <button class="classif-sort-btn ${sortBy==='nombre'?'active':''}" data-sort="nombre" type="button">Nombre${dirs('nombre')}</button>
            <button class="classif-sort-btn ${sortBy==='estado'?'active':''}" data-sort="estado" type="button">Estado${dirs('estado')}</button>
        </div>
    `;
    el.parentElement?.insertBefore(header, el);

    // Listeners de ordenamiento
    header.querySelectorAll('.classif-sort-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const col = btn.dataset.sort;
            const newDir = (sortBy === col) ? -sortDir : 1;
            renderClassifDocList(payload, col, newDir);
        });
    });

    el.innerHTML = items.map((item, i) => {
        const orderNum = i + 1;
        const orderOptions = items.map((_, j) => 
            `<option value="${j+1}" ${j+1===orderNum?'selected':''}>${j+1}</option>`
        ).join('');
        return `
        <div class="doc-item" data-index="${i}" data-file="${escapeHtml(item.file)}">
            <span class="doc-item-order">
                <select class="doc-order-select" data-file="${escapeHtml(item.file)}" title="Cambiar orden">${orderOptions}</select>
            </span>
            <span class="doc-item-type ${item.kind==='xlsx'?'ok':''}">
                ${item.kind==='xlsx'?'XLSX':escapeHtml(item.type?.toUpperCase().slice(0,6)||'DOC')}
            </span>
            <span class="doc-item-name" title="${escapeHtml(item.displayName||item.file)}">${escapeHtml(item.label)}</span>
            ${item.corrected ? '<span class="doc-item-corrected">corregido</span>' : ''}
        </div>
    `}).join('');
    el.querySelectorAll('.doc-item').forEach(el => {
        el.addEventListener('click', async (e) => {
            if (e.target.classList.contains('doc-order-select')) return; // no abrir al cambiar orden
            el.closest('.doc-list')?.querySelectorAll('.doc-item').forEach(d => d.classList.remove('active'));
            el.classList.add('active');
            const idx = parseInt(el.dataset.index);
            const item = items[idx];
            if (!item) return;
            if (previewTitle) previewTitle.textContent = item.label;
            if (preview) {
                preview.innerHTML = '<div class="loading-msg">Cargando documento...</div>';
                await renderDocPreview(preview, payload.id, item);
            }
            renderClassifActions(item, payload);
        });
    });

    // Listeners de reordenamiento
    el.querySelectorAll('.doc-order-select').forEach(sel => {
        sel.addEventListener('change', async () => {
            const file = sel.dataset.file;
            const newPos = parseInt(sel.value) - 1;
            // Reordenar items
            const currentIdx = items.findIndex(it => it.file === file);
            if (currentIdx === newPos) return;
            const newItems = [...items];
            const [moved] = newItems.splice(currentIdx, 1);
            newItems.splice(newPos, 0, moved);
            const newOrder = newItems.map(it => it.file);
            try {
                await fetchWithRetry(`${API_URL}/api/cases/${encodeURIComponent(payload.id)}/document-workspace`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action: 'set_order', order: newOrder }),
                });
                // Recargar la lista con el nuevo orden
                payload.analysis = payload.analysis || {};
                payload.analysis.document_workspace = payload.analysis.document_workspace || {};
                payload.analysis.document_workspace.order = newOrder;
                renderClassifDocList(payload, sortBy, sortDir);
            } catch(e) { console.warn('Error reordenando:', e); }
        });
    });
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
    if (item.kind === 'xlsx') { el.innerHTML = ''; return; }

    const currentLabel = item.effectiveTypeLabel || item.label || item.type || 'Sin clasificar';
    const isCorrected = item.corrected;

    el.innerHTML = `
        <div class="reclassify-panel">
            <div class="reclassify-current">
                <span class="reclassify-label">Clasificación actual:</span>
                <span class="reclassify-value ${isCorrected ? 'corrected' : ''}">${escapeHtml(currentLabel)}${isCorrected ? ' · corregido manualmente' : ''}</span>
            </div>
            <div class="reclassify-form">
                <select class="field-select" id="reclassifySelect" style="flex:1;min-width:160px">
                    <option value="">— Selecciona nuevo tipo —</option>
                    ${REVIEW_TYPE_OPTIONS.map(([v,l]) => `<option value="${v}" ${v===item.type?'selected':''}>${escapeHtml(l)}</option>`).join('')}
                </select>
                <button class="btn-warn" id="reclassifyBtn" type="button">Reclasificar</button>
            </div>
            <div class="reclassify-status" id="reclassifyStatus"></div>
        </div>
        ${item.type === 'entrega_documentos' ? `
        <div class="reclassify-panel" style="margin-top:10px;border-top:1px solid var(--c-border);padding-top:12px">
            <div style="font-size:12px;font-weight:600;color:var(--c-text-1);margin-bottom:8px">Corrección manual de comisiones</div>
            <div style="font-size:11px;color:var(--c-text-2);margin-bottom:10px">Si el sistema leyó mal la tabla CPS-F-11, ingresa los datos manualmente.</div>
            <div id="comisionRows" style="display:flex;flex-direction:column;gap:6px;margin-bottom:8px"></div>
            <button class="btn-secondary" id="addComisionRow" type="button" style="font-size:11px;padding:5px 10px">+ Agregar intermediario</button>
            <div style="margin-top:8px;display:flex;gap:6px">
                <button class="btn-primary" id="saveComisiones" type="button" style="font-size:12px;padding:6px 14px">Guardar comisiones</button>
                <span id="comisionStatus" style="font-size:11px;line-height:2.2"></span>
            </div>
        </div>` : ''}
    `;

    document.getElementById('reclassifyBtn')?.addEventListener('click', async () => {
        const sel = document.getElementById('reclassifySelect');
        const newType = sel?.value;
        if (!newType) { document.getElementById('reclassifyStatus').textContent = 'Selecciona un tipo primero.'; return; }
        if (!payload?.id) return;
        const btn = document.getElementById('reclassifyBtn');
        const status = document.getElementById('reclassifyStatus');
        if (btn) { btn.disabled = true; btn.textContent = 'Guardando...'; }
        if (status) { status.textContent = ''; status.style.color = ''; }
        try {
            const r = await fetchWithRetry(`${API_URL}/api/cases/${encodeURIComponent(payload.id)}/manual-review`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    kind: item.kind || 'document',
                    filename: item.file,
                    file: item.file,
                    expected_type: newType, 
                    verdict: 'no' 
                }),
            });
            if (!r.ok) {
                let errDetail = `HTTP ${r.status}`;
                try { const ed = await r.json(); errDetail = ed.detail || ed.message || errDetail; } catch {}
                throw new Error(errDetail);
            }

            const newLabel = getReviewTypeLabelWithCode(newType, null);

            // Actualizar el item en memoria
            item.type = newType;
            item.label = newLabel;
            item.corrected = true;

            // Actualizar el elemento en la lista sin recargar todo
            const activeDocItem = document.querySelector('.doc-item.active');
            if (activeDocItem) {
                const typeEl = activeDocItem.querySelector('.doc-item-type');
                const nameEl = activeDocItem.querySelector('.doc-item-name');
                if (typeEl) typeEl.textContent = newType.toUpperCase().slice(0,6);
                if (nameEl) nameEl.textContent = newLabel;
            }

            // Actualizar el header del visor
            const previewTitle = document.getElementById('classifPreviewTitle');
            if (previewTitle) previewTitle.textContent = newLabel;

            // Actualizar el panel de reclasificación
            if (status) { status.style.color = 'var(--c-ok)'; status.textContent = `✓ Reclasificado como "${newLabel}"`; }
            if (btn) { btn.disabled = false; btn.textContent = 'Reclasificar'; }

            // Actualizar la clasificación actual mostrada
            const currentEl = document.querySelector('.reclassify-value');
            if (currentEl) { currentEl.textContent = `${newLabel} · corregido manualmente`; currentEl.classList.add('corrected'); }

            // Recargar la lista en background para sincronizar
            setTimeout(() => loadClassifForCase(payload.id), 1500);

        } catch(e) {
            let errMsg = '';
            if (typeof e === 'string') errMsg = e;
            else if (e instanceof Error) errMsg = e.message;
            else if (e?.detail) errMsg = String(e.detail);
            else errMsg = JSON.stringify(e);
            if (status) { status.style.color = 'var(--c-err)'; status.textContent = 'Error: ' + errMsg; }
            if (btn) { btn.disabled = false; btn.textContent = 'Reclasificar'; }
        }
    });

    // ── Panel de comisiones manuales (solo para entrega_documentos) ──
    if (item.type === 'entrega_documentos') {
        const comisionRows = document.getElementById('comisionRows');
        const addBtn = document.getElementById('addComisionRow');
        const saveBtn = document.getElementById('saveComisiones');
        const comisionStatus = document.getElementById('comisionStatus');

        // Cargar correcciones existentes si las hay
        const existingComisiones = payload?.analysis?.manual_review?.comisiones?.[item.file] || [];
        
        function renderComisionRow(data = {}) {
            const idx = comisionRows.children.length;
            const div = document.createElement('div');
            div.style.cssText = 'display:flex;gap:6px;align-items:center;flex-wrap:wrap';
            div.innerHTML = `
                <select class="field-select comision-codigo" style="width:110px;font-size:11px">
                    <option value="1" ${data.codigo==='1'?'selected':''}>01 - Consultor</option>
                    <option value="3" ${data.codigo==='3'?'selected':''}>03 - Corredor</option>
                </select>
                <input class="field-input comision-cedula" placeholder="Nro. documento" 
                    value="${escapeHtml(data.cedula||'')}" style="width:130px;font-size:11px;padding:5px 8px">
                <input class="field-input comision-pct" placeholder="%" 
                    value="${escapeHtml(data.porcentaje||'100')}" style="width:55px;font-size:11px;padding:5px 8px">
                <button class="btn-icon" type="button" style="font-size:12px;padding:2px 6px" 
                    onclick="this.closest('div').remove()">✕</button>
            `;
            comisionRows.appendChild(div);
        }

        // Renderizar filas existentes o una vacía
        if (existingComisiones.length) {
            existingComisiones.forEach(c => renderComisionRow(c));
        } else {
            renderComisionRow();
        }

        addBtn?.addEventListener('click', () => renderComisionRow());

        saveBtn?.addEventListener('click', async () => {
            const rows = [...comisionRows.querySelectorAll('div')].map(row => ({
                codigo: row.querySelector('.comision-codigo')?.value || '',
                cedula: row.querySelector('.comision-cedula')?.value?.trim() || '',
                porcentaje: row.querySelector('.comision-pct')?.value?.trim() || '100',
            })).filter(r => r.cedula);

            if (!rows.length) { comisionStatus.textContent = 'Agrega al menos un intermediario.'; return; }

            try {
                saveBtn.disabled = true; saveBtn.textContent = 'Guardando...';
                const r = await fetchWithRetry(`${API_URL}/api/cases/${encodeURIComponent(payload.id)}/manual-review`, {
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
                comisionStatus.style.color = 'var(--c-ok)';
                comisionStatus.textContent = `✓ ${rows.length} intermediario(s) guardados`;
                saveBtn.disabled = false; saveBtn.textContent = 'Guardar comisiones';
            } catch(e) {
                comisionStatus.style.color = 'var(--c-err)';
                comisionStatus.textContent = 'Error: ' + e.message;
                saveBtn.disabled = false; saveBtn.textContent = 'Guardar comisiones';
            }
        });
    }
}

async function reclassifyDocument(caseId, item, newType) {
    try {
        const r = await fetchWithRetry(`${API_URL}/api/cases/${encodeURIComponent(caseId)}/manual-review`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ kind: item.kind||'document', filename: item.file, file: item.file, expected_type: newType, verdict: 'no' }),
        });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        await loadClassifForCase(caseId);
    } catch(e) {
        console.error('reclassifyDocument:', e);
        alert('No pude reclasificar el documento: ' + e.message);
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
        const r = await fetchWithRetry(`${API_URL}/api/cases/${encodeURIComponent(caseId)}`);
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
    const docs = Array.isArray(checklist.received_summary) ? checklist.received_summary :
                 Array.isArray(a.documents_summary) ? a.documents_summary : [];
    const profile = (a.xlsx_profile || {}).profile || {};
    const empresa = profile.empresa || payload.label || 'n/d';
    const nit = profile.nit || 'n/d';

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
            <div style="font-size:12px;color:var(--c-text-2)">NIT: ${escapeHtml(nit)}</div>
        </div>
    </div>`;

    // Documentos recibidos
    if (docs.length) {
        html += `<div class="report-section-title" style="margin-bottom:8px">Documentos clasificados</div>`;
        html += `<div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:20px">`;
        for (const group of docs) {
            const count = (group.files||[]).length;
            const label = getReviewTypeLabel(group.type || group.label) || group.label || 'Documento';
            const code = getReviewTypeCode(group.type || group.label);
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
            const ok = Boolean(v.passed || v.ok || v.result === 'ok');
            const label = v.label || v.field || v.rule || 'Validación';
            const valueFound = v.value_found || v.valor_encontrado || v.extracted || '';
            const valueExpected = v.value_expected || v.valor_esperado || v.expected || '';
            const detail = v.detail || v.detalle || '';
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
        const r = await fetchWithRetry(`${API_URL}/api/cases/${encodeURIComponent(caseId)}`);
        const payload = await r.json();
        const items = buildDocItems(payload);
        if (!items.length) { listEl.innerHTML = '<div class="empty-state">Sin documentos</div>'; return; }
        listEl.innerHTML = items.map((item, i) => `
            <div class="doc-item" data-index="${i}">
                <span class="doc-item-type ${item.kind==='xlsx'?'ok':''}">${item.kind==='xlsx'?'XLSX':item.type?.toUpperCase().slice(0,4)||'DOC'}</span>
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
        const r = await fetchWithRetry(`${API_URL}/api/cases/production-summary`);
        const data = await r.json();
        const cases = Array.isArray(data.cases) ? data.cases : [];
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
        const r = await fetchWithRetry(`${API_URL}/api/cases/${encodeURIComponent(caseId)}`);
        const payload = await r.json();
        el.dataset.caseId = caseId;  // confirmar después de cargar
        renderReporte(el, payload);
    } catch(e) {
        el.innerHTML = `<div class="error-msg">${escapeHtml(e.message)}</div>`;
    }
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

    // Resultado legacy APOLO
    const legacy926 = (wf.output_926||{}).legacy || (a.output_926||{}).legacy || {};
    const legacyOk = legacy926.ok || false;
    const legacyNumAfil = legacy926.numero_afiliacion || legacy926.nro_afiliacion || profile.numero_contrato || profile.nro_contrato || '';
    const legacyObs = legacy926.observacion || legacy926.observation || legacy926.message || '';
    const legacyFecha = legacy926.fecha || legacy926.processed_at || '';
    const legacyLote = legacy926.lote || legacy926.batch || '';

    const estadoNorm = normalizeText(estado);
    const isAprobable = estadoNorm.includes('aprob') || normalizeText(wf.status||'') === 'completed';
    const isNoAprobado = normalizeText(wf.status||'') === 'stopped_prevalidacion' || estadoNorm.includes('no aprob');
    const stateClass = isNoAprobado ? 'bloqueado' : (isAprobable ? 'aprobado' : 'observado');

    const blockers = Array.isArray(decision.blockers) ? decision.blockers :
                     Array.isArray(report.bloqueantes) ? report.bloqueantes : [];
    const observaciones = Array.isArray(report.observaciones) ? report.observaciones : [];

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
            <span class="report-state-badge ${stateClass}">${escapeHtml(estado)}</span>
            <div>
                <div class="report-empresa">${escapeHtml(empresa)}</div>
                <div class="report-nit">
                    NIT: <strong>${escapeHtml(nit)}</strong>
                    ${legacyNumAfil ? ` · Contrato: <strong>${escapeHtml(legacyNumAfil)}</strong>` : ''}
                    · ${escapeHtml(fecha)}
                </div>
            </div>
            <div style="margin-left:auto;display:flex;gap:8px;align-items:center">
                <button class="btn-secondary" data-action="clasificacion" data-case="${escapeHtml(caseId)}" type="button">Ver documentos</button>
                ${has926 ? `<button class="btn-primary" data-action="descargar926" data-case="${escapeHtml(caseId)}" data-file="${escapeHtml(filename926)}" type="button">Descargar plano</button>` : ''}
                ${!isAprobable ? `<button class="btn-warn" id="reprocesarBtn" data-case="${escapeHtml(caseId)}" type="button" title="Volver a ejecutar la prevalidación">↺ Reprocesar</button>` : ''}
            </div>
        </div>
        <div id="reprocesarStatus" style="display:none;padding:8px 16px;font-size:12px;background:var(--c-info-bg);color:var(--c-info);border-bottom:1px solid var(--c-border)"></div>
        <div class="report-body">
            <div class="report-section">
                <div class="report-section-title">Datos del contrato</div>
                <div class="report-grid">
                    <div class="report-kv clickable" data-panel="sedes" role="button" tabindex="0" title="Ver sedes, centros de trabajo y trabajadores">
                        <div class="report-kv-label">Sedes</div>
                        <div class="report-kv-val">${escapeHtml(String(sedes))}</div>
                        <div class="report-kv-hint">Ver sedes →</div>
                    </div>
                    <div class="report-kv">
                        <div class="report-kv-label">Nómina total</div>
                        <div class="report-kv-val">${escapeHtml(nomina)}</div>
                    </div>
                </div>
                <div id="reportDataPanel" class="report-data-panel hidden"></div>
            </div>
            ${blockers.length ? `
                <div class="report-section">
                    <div class="report-section-title">Bloqueantes (${blockers.length}) · haz clic en uno para ver el documento fuente</div>
                    <div class="report-blockers-list" id="reportBlockersList">
                        ${blockers.slice(0,10).map((b, i) => {
                            const raw = blockerText(b);
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
                                    ${isClickable ? `<span class="report-blocker-action-hint">${escapeHtml(parsed.actionLabel)} →</span>` : ''}
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
        ${legacyNumAfil || legacyObs ? `
        <div class="legacy-result-card">
            <div class="legacy-result-title">Resultado en sistema APOLO</div>
            <div class="legacy-result-grid">
                ${legacyNumAfil ? `<div class="legacy-result-kv"><div class="legacy-result-kv-label">Nro. Afiliación</div><div class="legacy-result-kv-val">${escapeHtml(legacyNumAfil)}</div></div>` : ''}
                ${legacyLote ? `<div class="legacy-result-kv"><div class="legacy-result-kv-label">Lote</div><div class="legacy-result-kv-val">${escapeHtml(legacyLote)}</div></div>` : ''}
                ${legacyFecha ? `<div class="legacy-result-kv"><div class="legacy-result-kv-label">Procesado</div><div class="legacy-result-kv-val">${escapeHtml(legacyFecha)}</div></div>` : ''}
                ${legacyObs ? `<div class="legacy-result-kv" style="grid-column:1/-1"><div class="legacy-result-kv-label">Observación APOLO</div><div class="legacy-result-kv-val" style="font-size:12px;color:${legacyOk?'var(--c-ok)':'var(--c-warn)'}">${escapeHtml(legacyObs)}</div></div>` : ''}
            </div>
        </div>
        ` : ''}
    `;

    // Botones de acción del header
    container.querySelectorAll('[data-action]').forEach(btn => {
        btn.addEventListener('click', () => handleCaseAction(btn.dataset.action, btn.dataset.case, btn.dataset.file));
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
                // Leer registros del XLSX agrupados por sede (_sheet)
                const xlsxRecords = a.xlsx_profile?.records || [];
                const workerCounts = a.xlsx_profile?.worker_sheet_counts || {};
                const salaryCounts = a.xlsx_profile?.worker_sheet_salary_totals || {};
                
                // Agrupar trabajadores por sede
                const bySede = {};
                for (const r of xlsxRecords) {
                    const sede = r._sheet || 'Sin sede';
                    if (!bySede[sede]) bySede[sede] = [];
                    bySede[sede].push(r);
                }
                
                const sedeNames = Object.keys(workerCounts).length ? Object.keys(workerCounts) : Object.keys(bySede);
                
                if (!sedeNames.length && !xlsxRecords.length) {
                    dataPanel.innerHTML = `<div style="padding:12px;font-size:12px;color:var(--c-text-2)">No hay información de sedes disponible.</div>`;
                } else {
                    const sedeBlocks = sedeNames.map((sedeName, si) => {
                        const workers = bySede[sedeName] || [];
                        const total = workerCounts[sedeName] ?? workers.length;
                        const salarioTotal = salaryCounts[sedeName] ? 
                            '$ ' + Number(salaryCounts[sedeName]).toLocaleString('es-CO') : '';
                        
                        if (!workers.length) return `
                            <div style="margin-bottom:16px">
                                <div style="font-weight:600;font-size:12px;color:var(--c-text-1);margin-bottom:4px">
                                    🏢 ${escapeHtml(sedeName)} · ${total} trabajador(es)
                                    ${salarioTotal ? `<span style="color:var(--c-text-2);font-weight:400;margin-left:8px">${escapeHtml(salarioTotal)}</span>` : ''}
                                </div>
                                <div style="font-size:11px;color:var(--c-text-2);padding:6px">Sin trabajadores registrados en esta sede.</div>
                            </div>`;
                        
                        const cols = [
                            {k: 'numero_de_identificacion', l: 'Documento'},
                            {k: ['primer_nombre','segundo_nombre','primer_apellido','segundo_apellido'], l: 'Nombre'},
                            {k: 'cargo', l: 'Cargo'},
                            {k: 'codigo_del_centro_de_trabajo', l: 'Centro'},
                            {k: 'tipo_de_trabajador', l: 'Tipo'},
                            {k: 'salario', l: 'Salario'},
                            {k: 'eps', l: 'EPS'},
                            {k: 'pension', l: 'Pensión'},
                            {k: 'direccion', l: 'Dirección'},
                        ];
                        
                        const rows = workers.map(w => {
                            return '<tr>' + cols.map(col => {
                                let val = '';
                                if (Array.isArray(col.k)) {
                                    val = col.k.map(k => w[k]||'').filter(Boolean).join(' ');
                                } else {
                                    val = String(w[col.k] ?? '');
                                }
                                if (col.k === 'salario' && val) {
                                    val = '$ ' + Number(val).toLocaleString('es-CO');
                                }
                                return `<td>${escapeHtml(val)}</td>`;
                            }).join('') + '</tr>';
                        }).join('');
                        
                        return `
                            <div style="margin-bottom:20px">
                                <div style="font-weight:600;font-size:12px;color:var(--c-text-1);margin-bottom:6px;padding:6px 8px;background:var(--c-info-bg);border-radius:4px">
                                    🏢 ${escapeHtml(sedeName)} · ${total} trabajador(es)
                                    ${salarioTotal ? `<span style="color:var(--c-text-2);font-weight:400;margin-left:8px">${escapeHtml(salarioTotal)}</span>` : ''}
                                </div>
                                <div style="overflow-x:auto">
                                <table class="blocker-table">
                                    <thead><tr>${cols.map(c=>`<th>${c.l}</th>`).join('')}</tr></thead>
                                    <tbody>${rows}</tbody>
                                </table>
                                </div>
                            </div>`;
                    }).join('');
                    
                    dataPanel.innerHTML = `
                        <div class="blocker-panel-head">
                            <span class="blocker-panel-title">🏢 Sedes (${sedeNames.length})</span>
                            <button class="btn-icon" id="dataPanelClose">✕</button>
                        </div>
                        <div style="padding:12px;max-height:500px;overflow-y:auto">
                            ${sedeBlocks}
                        </div>
                    `;
                }
            dataPanel.querySelector('#dataPanelClose')?.addEventListener('click', () => {
                dataPanel.classList.add('hidden');
                kv.classList.remove('active');
            });
            dataPanel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        });
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
        if (statusBar) { statusBar.style.display = ''; statusBar.textContent = 'Enviando a la cola de procesamiento...'; }
        try {
            const r = await fetch(`${API_URL}/api/cases/${encodeURIComponent(id)}/run-workflow`, { method: 'POST' });
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            if (statusBar) {
                statusBar.textContent = '✓ En cola — el contrato será reprocesado automáticamente. Puedes ver el progreso en la Bandeja.';
                statusBar.style.background = 'var(--c-ok-bg)';
                statusBar.style.color = 'var(--c-ok)';
            }
            btn.textContent = 'En cola ✓';
            // Actualizar sidebar después de 3s
            setTimeout(() => loadReporteSidebar(), 3000);
            // Activar live polling en bandeja
            startBandejaLivePolling();
        } catch(e) {
            if (statusBar) { statusBar.textContent = 'Error: ' + e.message; statusBar.style.background = 'var(--c-err-bg)'; statusBar.style.color = 'var(--c-err)'; }
            btn.disabled = false;
            btn.textContent = '↺ Reprocesar';
        }
    });
}

// ── PRODUCCIÓN (COLMENA) ─────────────────────────────────────
async function loadProduccion() {
    const el = document.getElementById('produccionContent');
    if (!el) return;
    if (productionLoadController) { try { productionLoadController.abort(); } catch {} }
    productionLoadController = new AbortController();
    el.innerHTML = '<div class="loading-msg">Cargando contratos...</div>';
    try {
        const r = await fetchWithRetry(`${API_URL}/api/cases/production-summary`, { signal: productionLoadController.signal });
        const data = await r.json();
        let cases = Array.isArray(data.cases) ? data.cases : [];
        cases = cases.filter(c => {
            const { status, finalStatus } = resolveCase(c);
            const s = normalizeText(status), f = normalizeText(finalStatus);
            return s === 'completed' && (f.includes('aprob') || f === 'ok' || f === 'completed' || !f);
        });
        cases.sort((a,b) => String(b.updated_at||'').localeCompare(String(a.updated_at||'')));
        if (!cases.length) { el.innerHTML = '<div class="empty-state">No hay contratos aprobados para Colmena</div>'; return; }
        el.innerHTML = `<div class="production-cards">${cases.map(item => {
            const { empresa, nit, fecha, has926, filename } = resolveCase(item);
            const id = item.id || '';
            return `
                <div class="prod-card">
                    <div class="prod-card-head">
                        <div>
                            <div class="prod-card-title">Contrato ${escapeHtml(nit)}</div>
                            <div class="prod-card-empresa">${escapeHtml(empresa)}</div>
                            <div class="prod-card-meta">${escapeHtml(fecha)}</div>
                        </div>
                        <div class="prod-card-badges">
                            <span class="pill pill-ok">Aprobable</span>
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
    if (!ids.length) { alert('Selecciona al menos un contrato para el lote'); return; }
    const btn = document.getElementById('downloadColmenaBtn');
    if (btn) { btn.disabled = true; btn.textContent = 'Descargando...'; }
    try {
        const r = await fetch(`${API_URL}/api/926/consolidated`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ case_ids: ids }),
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
        alert('Error descargando lote: ' + e.message);
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
        const r = await fetch(`${API_URL}/api/cases/production-summary`);
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
    if (!name || !text) { alert('Completa tu nombre y la observación'); return; }
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
            ? `${API_URL}/api/cases/search?q=${encodeURIComponent(query.trim())}&limit=20`
            : `${API_URL}/api/cases/production-summary`;
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
            const { empresa, nit, fecha, status, finalStatus } = resolveCase(item);
            const cls = caseStatusClass(status, finalStatus);
            const lbl = casePillLabel(status, finalStatus);
            const blockers = item.blockers || [];
            const id = item.id || '';
            return `
                <div class="search-result-item" data-case="${escapeHtml(id)}" tabindex="0" role="button">
                    <div class="search-result-main">
                        <div class="search-result-empresa">${escapeHtml(empresa)}</div>
                        <div class="search-result-meta">
                            ${nit !== 'n/d' ? `NIT ${escapeHtml(nit)} · ` : ''}${escapeHtml(fecha)}
                        </div>
                        ${blockers.length ? `<div style="font-size:11px;color:var(--c-err);margin-top:3px">
                            ${blockers.length} bloqueante${blockers.length>1?'s':''}: ${escapeHtml(String(blockers[0]).slice(0,60))}${blockers[0]?.length>60?'...':''}
                        </div>` : ''}
                    </div>
                    <span class="pill pill-${cls}" style="flex-shrink:0">${escapeHtml(lbl)}</span>
                </div>
            `;
        }).join('');
        el.querySelectorAll('[data-case]').forEach(row => {
            row.addEventListener('click', () => {
                const id = row.dataset.case;
                if (id) { activeCaseId = id; switchView('reporte'); loadReporteForCase(id); }
            });
            row.addEventListener('keydown', e => {
                if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); row.click(); }
            });
        });
    } catch(e) {
        el.innerHTML = `<div class="error-msg">${escapeHtml(e.message)}</div>`;
    }
}

// ── ADMIN ─────────────────────────────────────────────────────
async function loadSystemStatus() {
    const statusVal = document.getElementById('adminStatusVal');
    const statusSub = document.getElementById('adminStatusSub');
    const detail = document.getElementById('adminStatusDetail');
    if (statusVal) statusVal.textContent = '...';
    try {
        const r = await fetch(`${API_URL}/api/system/status`);
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const data = await r.json();
        const overall = data.overall || 'ok';
        const isOk = normalizeText(overall) === 'ok';
        if (statusVal) { statusVal.textContent = isOk ? 'OK' : overall; statusVal.style.color = isOk ? 'var(--c-ok)' : 'var(--c-err)'; }
        if (statusSub) statusSub.textContent = data.description || (isOk ? 'Todos los servicios operativos' : 'Revisar servicios');
        const services = Array.isArray(data.services) ? data.services : [];
        if (detail && services.length) {
            detail.innerHTML = `<div style="padding:0 16px 16px">${services.map(s => `
                <div class="admin-service-row">
                    <span class="admin-service-name">${escapeHtml(s.name||s.id||'Servicio')}</span>
                    <span class="admin-service-status ${normalizeText(s.status||'')}">${escapeHtml(s.status||'n/d')}</span>
                </div>
            `).join('')}</div>`;
        }
    } catch(e) {
        if (statusVal) { statusVal.textContent = 'Error'; statusVal.style.color = 'var(--c-err)'; }
        if (statusSub) statusSub.textContent = e.message;
    }
}

async function reindexKnowledge() {
    const btn = document.getElementById('reindexBtn');
    if (btn) { btn.disabled = true; btn.textContent = 'Reindexando...'; }
    try {
        const r = await fetch(`${API_URL}/api/system/reindex`, { method: 'POST' });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const data = await r.json();
        alert(`Reindexado: ${data.documents||0} documentos, ${data.chunks||0} chunks`);
        loadSystemStatus();
    } catch(e) {
        alert('Error reindexando: ' + e.message);
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = 'Reindexar conocimiento'; }
    }
}

async function exportReviews() {
    const btn = document.getElementById('exportReviewsBtn');
    if (btn) { btn.disabled = true; btn.textContent = 'Exportando...'; }
    try {
        const r = await fetch(`${API_URL}/api/evals/document-reviews/export`);
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const blob = await r.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a'); a.href = url; a.download = 'document_reviews.jsonl';
        document.body.appendChild(a); a.click(); a.remove();
        URL.revokeObjectURL(url);
    } catch(e) {
        alert('Error exportando: ' + e.message);
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = 'Exportar revisiones'; }
    }
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
            'cola': 'cola',
            'aprobables': 'aprobables',
            'observados': 'observados',
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

    // Admin
    document.getElementById('reindexBtn')?.addEventListener('click', reindexKnowledge);
    document.getElementById('exportReviewsBtn')?.addEventListener('click', exportReviews);
    document.getElementById('refreshStatusBtn')?.addEventListener('click', loadSystemStatus);

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
}

init();
