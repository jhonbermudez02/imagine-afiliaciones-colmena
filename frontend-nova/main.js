const API_URL =
    import.meta.env.VITE_API_URL ||
    `${window.location.protocol}//${window.location.hostname}:8000`;

const viewMeta = {
    processView: 'Proceso operativo',
    searchView: 'Búsqueda documental',
    adminView: 'Administración Imagine'
};

const workspaceTitle = document.getElementById('workspaceTitle');
const viewSwitcher = document.getElementById('viewSwitcher');
const chatContainer = document.getElementById('chatContainer');
const searchInput = document.getElementById('searchInput');
const sendButton = document.getElementById('sendButton');
const createCaseButton = document.getElementById('createCaseButton');
const runWorkflowButton = document.getElementById('runWorkflowButton');
const packageFilesInput = document.getElementById('packageFilesInput');
const caseStatusLine = document.getElementById('caseStatusLine');
const sourcesSection = document.getElementById('sourcesSection');
const sourcesContent = document.getElementById('sourcesContent');
const workflowContent = document.getElementById('workflowContent');
const caseChecklistContent = document.getElementById('caseChecklistContent');
const precheckReportContent = document.getElementById('precheckReportContent');
const executiveReportContent = document.getElementById('executiveReportContent');
const workflowRunContent = document.getElementById('workflowRunContent');
const workflowSection = document.getElementById('workflowSection');
const checklistSection = document.getElementById('checklistSection');
const precheckSection = document.getElementById('precheckSection');
const executiveSection = document.getElementById('executiveSection');
const workflowRunSection = document.getElementById('workflowRunSection');
const recover926Section = document.getElementById('recover926Section');
const recover926Content = document.getElementById('recover926Content');
const toggleRecover926Button = document.getElementById('toggleRecover926Button');
const caseSearchSection = document.getElementById('caseSearchSection');
const caseSearchContent = document.getElementById('caseSearchContent');
const compareLeftFile = document.getElementById('compareLeftFile');
const compareRightFile = document.getElementById('compareRightFile');
const compare926Button = document.getElementById('compare926Button');
const compare926Content = document.getElementById('compare926Content');

const REVIEW_TYPE_OPTIONS = [
    ['formulario_afiliacion', 'Afiliación (0)'],
    ['anexo_sedes', 'Sedes (1)'],
    ['listado_trabajadores', 'Listados (2)'],
    ['comision', 'Comisión (3)'],
    ['carta', 'Cartas (4)'],
    ['camara_comercio', 'Cámara de comercio (5)'],
    ['cedula', 'Cédula (6)'],
    ['constancia_afiliacion', 'Verificación (7)'],
    ['rut', 'Dian / RUT (8)'],
    ['entrega_documentos', 'Entrega Doc (10)'],
    ['soporte_ingresos', 'Pagos (11)'],
    ['contrato', 'Contrato (12)'],
    ['eps', 'EPS (13)'],
    ['afp', 'AFP (14)'],
    ['paz_y_salvo', 'Paz y Salvo (15)'],
    ['eps_afp', 'EPS - AFP (16)'],
    ['identificacion_peligros', 'Identificación de Peligros (19)'],
    ['examen_preocupacional', 'Examen Pre-ocupacional (20)'],
    ['autorizacion', 'Autorización (98)'],
    ['beneficiario_final', 'Beneficiario Final (27)'],
    ['sat', 'SAT (28)'],
    ['pdf', 'Imagen / PDF (99)'],
];
const documentModal = document.getElementById('documentModal');
const documentModalTitle = document.getElementById('documentModalTitle');
const documentModalBody = document.getElementById('documentModalBody');
const documentModalClose = document.getElementById('documentModalClose');
const documentModalBackdrop = document.getElementById('documentModalBackdrop');
const toggleIcon = document.querySelector('.toggle-icon');
const servicesGrid = document.getElementById('servicesGrid');
const actionsList = document.getElementById('actionsList');
const overallStatusText = document.getElementById('overallStatusText');
const overallStatusBadge = document.getElementById('overallStatusBadge');
const modelsText = document.getElementById('modelsText');
const knowledgeDocsChip = document.getElementById('knowledgeDocsChip');
const knowledgeChunksChip = document.getElementById('knowledgeChunksChip');
const feedProcessedChip = document.getElementById('feedProcessedChip');
const feedSkippedChip = document.getElementById('feedSkippedChip');
const feedFailedChip = document.getElementById('feedFailedChip');
const feedOcrChip = document.getElementById('feedOcrChip');
const feedTypes = document.getElementById('feedTypes');
const ocrStrategies = document.getElementById('ocrStrategies');
const feedErrors = document.getElementById('feedErrors');
const evalCasesChip = document.getElementById('evalCasesChip');
const evalAverageChip = document.getElementById('evalAverageChip');
const evalPassChip = document.getElementById('evalPassChip');
const evalWeakChip = document.getElementById('evalWeakChip');
const evalTopics = document.getElementById('evalTopics');
const evalLowest = document.getElementById('evalLowest');
const compareTotalChip = document.getElementById('compareTotalChip');
const compareExactChip = document.getElementById('compareExactChip');
const compareSimilarityChip = document.getElementById('compareSimilarityChip');
const compareLatest = document.getElementById('compareLatest');
const reindexButton = document.getElementById('reindexButton');
const exportReviewsButton = document.getElementById('exportReviewsButton');
const topicFilters = document.getElementById('topicFilters');
const workspaceViews = Array.from(document.querySelectorAll('.workspace-view'));
const selectedTopics = new Set();
let activeCaseId = null;
let activeCasePayload = null;
let activeDocumentUrl = null;
let activeDocumentDownloadName = null;
let caseProgressTimer = null;
let recover926Expanded = false;
const PROCESS_STATE_KEY = 'imagine-process-state-v1';
const cityNames = {
    '05001': 'Medellín',
    '08001': 'Barranquilla',
    '11001': 'Bogotá D.C.',
    '13001': 'Cartagena',
    '17001': 'Manizales',
    '23001': 'Montería',
    '54001': 'Cúcuta',
    '66001': 'Pereira',
    '68001': 'Bucaramanga',
    '73001': 'Ibagué',
    '76001': 'Cali',
};

function toggleSection(section, shouldShow) {
    if (!section) return;
    section.classList.toggle('hidden', !shouldShow);
}

function describeCity(code) {
    const digits = String(code || '').replace(/\D/g, '');
    if (!digits) return 'n/d';
    const padded = digits.padStart(5, '0');
    return cityNames[padded] ? `${digits} · ${cityNames[padded]}` : digits;
}

function formatDurationMs(value) {
    const ms = Number(value);
    if (!Number.isFinite(ms) || ms < 0) return 'n/d';
    if (ms < 1000) return `${ms} ms`;
    const seconds = ms / 1000;
    if (seconds < 60) return `${seconds.toFixed(1)} s`;
    const minutes = Math.floor(seconds / 60);
    const remSeconds = Math.round(seconds % 60);
    return `${minutes} min ${remSeconds} s`;
}

function buildExecutiveReportText(estado, empresa, nit, trabajadores, sedes) {
    return [
        `Estado final: ${estado || 'n/d'}`,
        `Afiliado: ${empresa || 'n/d'}`,
        `NIT: ${nit || 'n/d'}`,
        `Trabajadores: ${trabajadores ?? 'n/d'}`,
        `Sedes: ${sedes ?? 'n/d'}`,
    ].join('\n');
}

function buildCaseFileUrl(caseId, filename) {
    return `${API_URL}/api/cases/${encodeURIComponent(caseId)}/files/${filename.split('/').map(encodeURIComponent).join('/')}`;
}

function buildCaseFileRequestUrl(caseId, filename, downloadName = '') {
    const url = new URL(buildCaseFileUrl(caseId, filename), window.location.origin);
    if (downloadName) {
        url.searchParams.set('download_name', downloadName);
    }
    return url.toString();
}

function buildCase926Url(caseId) {
    return `${API_URL}/api/cases/${encodeURIComponent(caseId)}/926`;
}

function defaultProcessStatusText() {
    return 'Carga el paquete completo y ejecuta el proceso. Imagine hará la prevalidación y, si pasa, continuará hasta el 926.';
}

function resetProcessPanels() {
    renderCaseChecklist(null);
    renderWorkflowDecision(null);
    renderPrecheckReport(null);
    renderExecutiveReport(null);
    renderWorkflowRun(null);
}

async function loadRecoverable926Cases() {
    if (!recover926Content) return;
    recover926Content.innerHTML = '<div class="source-item">Cargando procesos con 926...</div>';
    try {
        const response = await fetch(`${API_URL}/api/cases`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const data = await response.json();
        const cases = Array.isArray(data.cases) ? data.cases : [];
        const recoverable = cases
            .filter((item) => {
                const workflow = (item.analysis || {}).workflow_run || {};
                const output926 = workflow.output_926 || (item.analysis || {}).output_926 || {};
                const integrated = output926.legacy || {};
                return (workflow.status === 'completed' || item.status === 'analyzed') && Boolean(integrated.ok);
            })
            .sort((a, b) => String(b.updated_at || '').localeCompare(String(a.updated_at || '')))
            .slice(0, 12);
        if (!recoverable.length) {
            recover926Content.innerHTML = '<div class="source-item">Aún no hay procesos terminados con 926 disponible.</div>';
            return;
        }
        recover926Content.innerHTML = recoverable.map((item) => {
            const analysis = item.analysis || {};
            const workflow = analysis.workflow_run || {};
            const report = workflow.executive_report_final || workflow.executive_report_precheck || analysis.reporte_ejecutivo || {};
            const resumen = report.resumen_ejecutivo || {};
            const empresa = resumen.empresa || ((analysis.xlsx_profile || {}).profile || {}).empresa || item.label || item.id;
            const nit = resumen.nit || ((analysis.xlsx_profile || {}).profile || {}).nit || 'n/d';
            const fecha = resumen.fecha_proceso_human || report.fecha_proceso_human || item.updated_at?.slice(0, 10) || 'n/d';
            const output926 = workflow.output_926 || analysis.output_926 || {};
            const filename = (output926.legacy || {}).filename || 'archivo_926.txt';
            return `
                <article class="workflow-card">
                    <div class="workflow-topline">
                        <div>
                            <div class="panel-label">${item.id}</div>
                            <strong>${empresa}</strong>
                        </div>
                        <div class="workflow-badges">
                            <span class="source-chip">${fecha}</span>
                        </div>
                    </div>
                    <p class="workflow-summary">NIT: ${nit}</p>
                    <div class="case-head-actions report-actions">
                        <button class="search-button secondary compact-button" type="button" data-recover-case="${item.id}">Recuperar</button>
                        <button class="search-button secondary compact-button" type="button" data-open-926-case="${item.id}" data-open-926-file="${filename}">Abrir 926</button>
                        <button class="search-button compact-button" type="button" data-download-926-case="${item.id}" data-download-926-file="${filename}">Descargar 926</button>
                    </div>
                </article>
            `;
        }).join('');
        recover926Content.querySelectorAll('[data-recover-case]').forEach((button) => {
            button.addEventListener('click', async () => {
                const caseId = button.dataset.recoverCase || '';
                if (!caseId) return;
                activeCaseId = caseId;
                persistProcessState({ activeCaseId: caseId, processing: false, error: false, statusText: `${caseId}: recuperado` });
                await loadActiveCase(caseId);
                switchView('processView');
            });
        });
        recover926Content.querySelectorAll('[data-open-926-case]').forEach((button) => {
            button.addEventListener('click', () => openCase926Viewer(button.dataset.open926Case || '', button.dataset.open926File || 'archivo_926.txt'));
        });
        recover926Content.querySelectorAll('[data-download-926-case]').forEach((button) => {
            button.addEventListener('click', () => downloadCase926(button.dataset.download926Case || '', button.dataset.download926File || 'archivo_926.txt'));
        });
    } catch (error) {
        console.error('No pude cargar procesos con 926:', error);
        recover926Content.innerHTML = '<div class="source-item">No pude cargar la lista de procesos con 926.</div>';
    }
}

function setRecover926Expanded(shouldExpand) {
    recover926Expanded = Boolean(shouldExpand);
    recover926Content?.classList.toggle('hidden', !recover926Expanded);
    if (toggleRecover926Button) {
        toggleRecover926Button.textContent = recover926Expanded ? 'Ocultar' : 'Mostrar';
    }
}

function clearProcessState() {
    try {
        window.localStorage.removeItem(PROCESS_STATE_KEY);
    } catch (error) {
        console.error('No pude limpiar el estado del proceso:', error);
    }
}

function getManualReviewEntry(manualReview = {}, kind, filename) {
    const bucketName = kind === 'xlsx' ? 'xlsx' : 'documents';
    return ((manualReview || {})[bucketName] || {})[filename] || null;
}

function formatManualReviewState(entry) {
    if (!entry?.verdict) return 'Pendiente';
    const base = entry.verdict === 'si' ? 'Marcado: sí' : 'Marcado: no';
    if (entry.expected_type) {
        const option = REVIEW_TYPE_OPTIONS.find(([value]) => value === entry.expected_type);
        return `${base} · corregir a ${option ? option[1] : entry.expected_type}`;
    }
    return base;
}

function formatConfidenceValue(value) {
    const num = Number(value);
    if (!Number.isFinite(num)) return 'n/d';
    return `${Math.round(num * 100)}%`;
}

function buildDocumentMetaMap(casePayload = null) {
    const docs = Array.isArray(casePayload?.analysis?.documents) ? casePayload.analysis.documents : [];
    return Object.fromEntries(docs.map((doc) => [doc.filename, doc]));
}

function getDisplayFilename(file, meta = null) {
    return meta?.display_filename || meta?.download_filename || file;
}

function buildXlsxMeta(casePayload = null, filename = '') {
    const profile = casePayload?.analysis?.xlsx_profile?.profile || {};
    if (!filename) return null;
    return {
        document_type: 'xlsx',
        classification_confidence: 1,
        ocr_quality_score: null,
        key_fields: {
            nit: profile.nit || '',
            documento: profile.documento || '',
            empresa: profile.empresa || '',
            trabajadores: profile.numero_trabajadores ?? profile.empleados_total ?? '',
            sedes: profile.numero_sedes ?? profile.sedes_validas ?? '',
            nomina_total: profile.nomina_total ?? '',
        },
        signals_detected: ['xlsx_profile_loaded'],
        field_confidence: {},
    };
}

function buildMetaEvidence(meta = null) {
    if (!meta) return '';
    const keyFields = meta.key_fields || {};
    const fieldConfidence = meta.field_confidence || {};
    const fieldRows = Object.entries(keyFields)
        .filter(([, value]) => value !== null && value !== undefined && String(value).trim() !== '')
        .map(([key, value]) => {
            const normalizedKey = key
                .replaceAll('_', ' ')
                .replace(/\b\w/g, (char) => char.toUpperCase());
            const displayValue = key.toLowerCase().includes('nomina')
                ? formatCurrencyCop(value)
                : String(value);
            const confidence = fieldConfidence[key];
            return `
                <div class="doc-meta-row">
                    <span>${normalizedKey}: ${displayValue}</span>
                    ${confidence !== undefined ? `<span class="doc-meta-chip subtle">conf. ${formatConfidenceValue(confidence)}</span>` : ''}
                </div>
            `;
        })
        .join('');
    const signals = Array.isArray(meta.signals_detected) ? meta.signals_detected.filter(Boolean).slice(0, 4) : [];
    const signalHtml = signals.length
        ? `<div class="doc-meta-signals">${signals.map((item) => `<span class="doc-meta-chip">${item}</span>`).join('')}</div>`
        : '';
    const confidenceHtml = `
        <div class="doc-meta-summary">
            <span class="doc-meta-chip">tipo ${formatConfidenceValue(meta.classification_confidence)}</span>
            ${meta.ocr_quality_score !== null && meta.ocr_quality_score !== undefined ? `<span class="doc-meta-chip">ocr ${formatConfidenceValue(meta.ocr_quality_score)}</span>` : ''}
        </div>
    `;
    if (!fieldRows && !signalHtml) {
        return confidenceHtml;
    }
    return `
        <div class="doc-meta-block">
            ${confidenceHtml}
            ${fieldRows ? `<div class="doc-meta-fields">${fieldRows}</div>` : ''}
            ${signalHtml}
        </div>
    `;
}

function collectXlsxFiles(casePayload = null) {
    const files = Array.isArray(casePayload?.files) ? casePayload.files : [];
    return files
        .map((item) => item?.filename)
        .filter((name) => /\.(xlsx|xls|xlsm)$/i.test(String(name || '')));
}

function buildDocumentReviewRow({ caseId, file, label, detail, kind = 'document', manualReview = {}, meta = null }) {
    const reviewEntry = getManualReviewEntry(manualReview, kind, file);
    const verdict = reviewEntry?.verdict || '';
    const expectedType = reviewEntry?.expected_type || '';
    const displayName = getDisplayFilename(file, meta);
    const correctionSelect = kind === 'document'
        ? `
            <label class="doc-correction-wrap">
                <span class="service-role">Tipo correcto si es NO</span>
                <select class="doc-correction-select" data-review-expected>
                    <option value="">Sin corrección</option>
                    ${REVIEW_TYPE_OPTIONS.map(([value, optionLabel]) => `<option value="${value}" ${expectedType === value ? 'selected' : ''}>${optionLabel}</option>`).join('')}
                </select>
            </label>
        `
        : '';
    return `
        <div class="document-row">
            <div class="document-row-copy">
                <div class="document-row-name">${displayName}</div>
                ${displayName !== file ? `<div class="service-role">origen: ${file}</div>` : ''}
                <div class="service-role">${detail}</div>
                ${buildMetaEvidence(meta)}
                <div class="document-review-state">${formatManualReviewState(reviewEntry)}</div>
            </div>
            <div class="document-row-actions">
                ${correctionSelect}
                <button class="search-button secondary compact-button" type="button" data-case="${caseId}" data-file="${file}" data-display-name="${displayName}">Ver</button>
                <div class="document-review-actions">
                    <button class="search-button secondary compact-button ${verdict === 'si' ? 'review-selected review-yes' : ''}" type="button" data-review-case="${caseId}" data-review-kind="${kind}" data-review-file="${file}" data-review-verdict="si">Sí</button>
                    <button class="search-button secondary compact-button ${verdict === 'no' ? 'review-selected review-no' : ''}" type="button" data-review-case="${caseId}" data-review-kind="${kind}" data-review-file="${file}" data-review-verdict="no">No</button>
                </div>
            </div>
        </div>
    `;
}

async function saveManualReview(caseId, kind, filename, verdict, button = null) {
    if (!caseId || !filename || !verdict) return;
    if (button) button.disabled = true;
    const row = button?.closest('.document-row');
    const expectedType = verdict === 'no'
        ? row?.querySelector('[data-review-expected]')?.value || ''
        : '';
    try {
        const response = await fetch(`${API_URL}/api/cases/${encodeURIComponent(caseId)}/manual-review`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ kind, filename, verdict, expected_type: expectedType })
        });
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const data = await response.json();
        const analysis = activeCasePayload?.analysis || {};
        analysis.manual_review = data.manual_review || {};
        activeCasePayload = { ...(activeCasePayload || {}), analysis };
        renderCaseChecklist(analysis.checklist || null, analysis.validacion_resumen || null, activeCasePayload);
    } catch (error) {
        console.error('No pude guardar la calificación manual:', error);
        addMessage('No pude guardar la calificación manual del documento.', 'nova');
    } finally {
        if (button) button.disabled = false;
    }
}

function persistProcessState(partial = {}) {
    try {
        const current = JSON.parse(window.localStorage.getItem(PROCESS_STATE_KEY) || '{}');
        window.localStorage.setItem(PROCESS_STATE_KEY, JSON.stringify({ ...current, ...partial }));
    } catch (error) {
        console.error('No pude guardar el estado del proceso:', error);
    }
}

function readProcessState() {
    try {
        return JSON.parse(window.localStorage.getItem(PROCESS_STATE_KEY) || '{}');
    } catch (error) {
        console.error('No pude leer el estado del proceso:', error);
        return {};
    }
}

function buildUploadProgressMessages(files) {
    const xlsx = files.find((file) => /\.(xlsx|xls|xlsm)$/i.test(file.name));
    const pdfs = files.filter((file) => /\.pdf$/i.test(file.name));
    const zips = files.filter((file) => /\.zip$/i.test(file.name));
    const messages = ['Subiendo paquete completo...'];
    if (xlsx) {
        messages.push(`Leyendo XLSX ${xlsx.name}...`);
    }
    if (zips.length) {
        messages.push(`Abriendo ZIP ${zips[0].name} y separando documentos...`);
    }
    if (pdfs.length) {
        messages.push(`Registrando PDF ${pdfs[0].name}...`);
        if (pdfs.length > 1) {
            messages.push(`Clasificando ${pdfs.length} PDF(s) del expediente...`);
        }
    }
    messages.push('Guardando empresa o independiente para ejecutar...');
    return messages;
}

function buildWorkflowProgressMessages(caseId, files) {
    const xlsx = files.find((file) => /\.(xlsx|xls|xlsm)$/i.test(file.name));
    const pdfs = files.filter((file) => /\.pdf$/i.test(file.name));
    const mainPdf = pdfs[0]?.name;
    const messages = [
        `Ejecutando prevalidación para ${caseId}...`,
        xlsx ? `Validando estructura del XLSX ${xlsx.name}...` : `Validando estructura del XLSX de ${caseId}...`,
        mainPdf ? `Leyendo y clasificando ${mainPdf}...` : `Leyendo y clasificando documentos PDF de ${caseId}...`,
        'Verificando cédula, RUT, cámara y soportes del expediente...',
        `Construyendo flujo automático y salida 926 de ${caseId}...`,
    ];
    return messages;
}

function startCaseProgress(messages) {
    const steps = Array.isArray(messages) && messages.length ? messages : ['Procesando expediente...'];
    let index = 0;
    if (!caseStatusLine) return;
    if (caseProgressTimer) {
        clearInterval(caseProgressTimer);
    }
    caseStatusLine.classList.remove('error');
    caseStatusLine.classList.add('processing');
    caseStatusLine.textContent = steps[0];
    persistProcessState({ activeCaseId, processing: true, error: false, statusText: steps[0] });
    caseProgressTimer = setInterval(() => {
        index = (index + 1) % steps.length;
        caseStatusLine.textContent = steps[index];
        persistProcessState({ activeCaseId, processing: true, error: false, statusText: steps[index] });
    }, 1600);
}

function stopCaseProgress(message, isError = false) {
    if (!caseStatusLine) return;
    if (caseProgressTimer) {
        clearInterval(caseProgressTimer);
        caseProgressTimer = null;
    }
    caseStatusLine.classList.remove('processing', 'error');
    if (isError) {
        caseStatusLine.classList.add('error');
    }
    caseStatusLine.textContent = message;
    persistProcessState({ activeCaseId, processing: false, error: isError, statusText: message });
}

async function downloadCase926(caseId, filename = 'archivo_926.txt') {
    if (!caseId) return;
    try {
        const response = await fetch(buildCase926Url(caseId));
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const text = await response.text();
        const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
    } catch (error) {
        console.error('No pude descargar el 926:', error);
    }
}

async function openCase926Viewer(caseId, filename = 'archivo_926.txt') {
    if (!caseId) return;
    documentModalTitle.textContent = `${caseId} · ${filename}`;
    documentModalBody.innerHTML = '<div class="source-item">Cargando 926...</div>';
    documentModal.classList.remove('hidden');
    try {
        const response = await fetch(buildCase926Url(caseId));
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const text = await response.text();
        documentModalBody.innerHTML = `<pre class="document-text">${text.replace(/[&<>]/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}</pre>`;
    } catch (error) {
        console.error('No pude abrir el 926 en el visor:', error);
        documentModalBody.innerHTML = '<div class="source-item">No pude abrir el 926 dentro del visor.</div>';
    }
}

async function openDocumentUrlViewer(url, filename = 'archivo') {
    if (!url) return;
    const absoluteUrl = url.startsWith('http') ? url : `${API_URL}${url}`;
    const lower = filename.toLowerCase();
    documentModalTitle.textContent = filename;
    documentModalBody.innerHTML = '<div class="source-item">Cargando archivo...</div>';
    documentModal.classList.remove('hidden');
    try {
        const response = await fetch(absoluteUrl);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const blob = await response.blob();
        if (activeDocumentUrl) {
            URL.revokeObjectURL(activeDocumentUrl);
        }
        activeDocumentUrl = URL.createObjectURL(blob);
        if (lower.endsWith('.pdf')) {
            documentModalBody.innerHTML = `<object class="document-frame" data="${activeDocumentUrl}" type="application/pdf"><div class="source-item">No pude mostrar el PDF dentro del visor.</div></object>`;
        } else if (/\.(png|jpg|jpeg|webp|bmp|tif|tiff)$/i.test(lower)) {
            documentModalBody.innerHTML = `<img class="document-image" src="${activeDocumentUrl}" alt="${filename}">`;
        } else {
            const text = await blob.text();
            documentModalBody.innerHTML = `<pre class="document-text">${text.replace(/[&<>]/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}</pre>`;
        }
    } catch (error) {
        console.error('No pude abrir el archivo en el visor interno:', error);
        documentModalBody.innerHTML = '<div class="source-item">No pude abrir este archivo dentro del visor.</div>';
    }
}

async function openDocumentViewer(caseId, filename, displayName = '') {
    if (!caseId || !filename) return;
    const resolvedName = displayName || filename;
    const url = buildCaseFileRequestUrl(caseId, filename, resolvedName);
    const lower = filename.toLowerCase();
    documentModalTitle.textContent = `${caseId} · ${resolvedName}`;
    documentModalBody.innerHTML = '<div class="source-item">Cargando archivo...</div>';
    documentModal.classList.remove('hidden');
    try {
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const blob = await response.blob();
        if (activeDocumentUrl) {
            URL.revokeObjectURL(activeDocumentUrl);
        }
        activeDocumentUrl = URL.createObjectURL(blob);
        activeDocumentDownloadName = resolvedName;
        if (lower.endsWith('.pdf')) {
            documentModalBody.innerHTML = `<object class="document-frame" data="${activeDocumentUrl}" type="application/pdf"><div class="source-item">No pude mostrar el PDF dentro del visor.</div></object>`;
        } else if (/\.(png|jpg|jpeg|webp|bmp|tif|tiff)$/i.test(lower)) {
            documentModalBody.innerHTML = `<img class="document-image" src="${activeDocumentUrl}" alt="${resolvedName}">`;
        } else {
            documentModalBody.innerHTML = `<div class="source-item">No hay visor embebido para este archivo. <a class="source-link" href="${activeDocumentUrl}" download="${resolvedName}">Descargar archivo</a></div>`;
        }
    } catch (error) {
        console.error('No pude abrir el archivo en el visor:', error);
        documentModalBody.innerHTML = '<div class="source-item">No pude abrir este archivo dentro del visor.</div>';
    }
}

function closeDocumentViewer() {
    documentModal.classList.add('hidden');
    documentModalBody.innerHTML = '';
    if (activeDocumentUrl) {
        URL.revokeObjectURL(activeDocumentUrl);
        activeDocumentUrl = null;
    }
    activeDocumentDownloadName = null;
}

function switchView(viewId) {
    workspaceViews.forEach((section) => {
        section.classList.toggle('active', section.id === viewId);
    });
    viewSwitcher?.querySelectorAll('[data-view]').forEach((button) => {
        button.classList.toggle('active', button.dataset.view === viewId);
    });
    workspaceTitle.textContent = viewMeta[viewId] || 'Imagine';
    if (viewId === 'processView' && !activeCaseId) {
        renderWorkflowDecision(null);
        if (!getSelectedPackageFiles().length) {
            resetProcessPanels();
            caseStatusLine.classList.remove('processing', 'error');
            caseStatusLine.textContent = defaultProcessStatusText();
        }
    }
    if (viewId === 'processView') {
        loadRecoverable926Cases();
    }
    if (viewId === 'searchView' && searchInput) {
        queueMicrotask(() => {
            searchInput.focus();
            searchInput.select();
        });
    }
}

function resetSearchWorkspace() {
    chatContainer.innerHTML = '';
    renderSources([]);
    renderWorkflowDecision(null);
    renderCaseSearch([]);
}

async function copyText(text, trigger) {
    if (!text) return;
    const original = trigger?.textContent;
    try {
        await navigator.clipboard.writeText(text);
        if (trigger) {
            trigger.textContent = 'Copiado';
            setTimeout(() => {
                trigger.textContent = original;
            }, 1600);
        }
    } catch (error) {
        console.error('No pude copiar el texto:', error);
    }
}

async function searchCaseContracts(query) {
    if (!query || query.trim().length < 2) {
        renderCaseSearch([]);
        return;
    }
    try {
    const response = await fetch(`${API_URL}/api/cases/search?q=${encodeURIComponent(query.trim())}&limit=8`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        renderCaseSearch(data.results || []);
    } catch (error) {
        console.error('Error buscando empresas o independientes:', error);
        renderCaseSearch([]);
    }
}

function getSelectedPackageFiles() {
    return Array.from(packageFilesInput?.files || []);
}

function describeSelectedPackage(files) {
    const counts = {
        xlsx: 0,
        pdf: 0,
        zip: 0,
        image: 0,
        other: 0
    };
    for (const file of files) {
        const name = file.name.toLowerCase();
        if (name.endsWith('.xlsx') || name.endsWith('.xls') || name.endsWith('.xlsm')) {
            counts.xlsx += 1;
        } else if (name.endsWith('.pdf')) {
            counts.pdf += 1;
        } else if (name.endsWith('.zip')) {
            counts.zip += 1;
        } else if (/\.(png|jpg|jpeg|tif|tiff|bmp|webp)$/.test(name)) {
            counts.image += 1;
        } else {
            counts.other += 1;
        }
    }
    return counts;
}

function deriveCaseLabel(files) {
    const xlsx = files.find((file) => /\.(xlsx|xls|xlsm)$/i.test(file.name));
    if (xlsx) {
        return xlsx.name.replace(/\.[^.]+$/, '');
    }
    const zip = files.find((file) => /\.zip$/i.test(file.name));
    if (zip) {
        return zip.name.replace(/\.[^.]+$/, '');
    }
    const first = files[0];
    if (first) {
        return first.name.replace(/\.[^.]+$/, '');
    }
    return `afiliacion-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}`;
}

async function loadSystemStatus() {
    try {
        const response = await fetch(`${API_URL}/api/system/status`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();
        renderSystemStatus(data);
    } catch (error) {
        console.error('Error cargando estado del sistema:', error);
        overallStatusText.textContent = 'No se pudo cargar el estado del sistema';
        overallStatusBadge.textContent = 'ERROR';
        overallStatusBadge.className = 'status-badge degraded';
        modelsText.textContent = `Backend esperado en ${API_URL}`;
        servicesGrid.innerHTML = '';
        actionsList.innerHTML = '<div class="action-card"><strong>Revisar backend</strong><p>El panel de control no pudo obtener el estado centralizado de Imagine.</p></div>';
    }
}

async function reindexKnowledge() {
    reindexButton.disabled = true;
    reindexButton.textContent = 'Reindexando...';
    try {
        const response = await fetch(`${API_URL}/api/system/reindex`, { method: 'POST' });
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const data = await response.json();
        addMessage(`Corpus reindexado: ${data.documents} documentos y ${data.chunks} chunks.`, 'nova');
        await loadSystemStatus();
    } catch (error) {
        console.error('Error reindexando conocimiento:', error);
        addMessage('No pude reindexar el corpus desde el panel de control.', 'nova');
    } finally {
        reindexButton.disabled = false;
        reindexButton.textContent = 'Reindexar conocimiento';
    }
}

async function exportManualReviewsDataset() {
    if (!exportReviewsButton) return;
    const original = exportReviewsButton.textContent;
    exportReviewsButton.disabled = true;
    exportReviewsButton.textContent = 'Exportando...';
    try {
        const response = await fetch(`${API_URL}/api/evals/document-reviews/export`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const blob = await response.blob();
        const filename = 'document_reviews.jsonl';
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
        exportReviewsButton.textContent = 'Exportado';
        setTimeout(() => {
            exportReviewsButton.textContent = original;
        }, 1200);
    } catch (error) {
        console.error('No pude exportar las revisiones:', error);
        exportReviewsButton.textContent = original;
    } finally {
        exportReviewsButton.disabled = false;
    }
}

async function sendMessage() {
    const message = searchInput.value.trim();
    if (!message) return;

    resetSearchWorkspace();
    addMessage(message, 'user');
    searchInput.value = '';

    try {
        const payload = { consulta: message, contexto: { topics: Array.from(selectedTopics) } };
        const [response, workflowResponse] = await Promise.all([
            fetch(`${API_URL}/api/afiliacion/consultar`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            }),
            fetch(`${API_URL}/api/afiliacion/operar`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            })
        ]);
        if (!response.ok || !workflowResponse.ok) {
            throw new Error(`HTTP ${response.status}/${workflowResponse.status}`);
        }

        const [data, workflow] = await Promise.all([response.json(), workflowResponse.json()]);
        addMessage(data.respuesta, 'nova', data.fuentes || []);
        if ((data.respuesta || '').includes('Coincidencias encontradas:')) {
            await searchCaseContracts(message);
        } else {
            renderCaseSearch([]);
        }
        renderSources(data.fuentes || []);
        renderWorkflowDecision(workflow);
    } catch (error) {
        console.error('Error consultando Imagine:', error);
        addMessage(`Error de conexión con Imagine (${API_URL})`, 'nova');
        renderSources([]);
        renderWorkflowDecision(null);
    }
}

async function createCase() {
    const files = getSelectedPackageFiles();
    if (!files.length) {
        stopCaseProgress('Debes cargar el paquete completo.', true);
        return null;
    }
    const label = deriveCaseLabel(files);
    closeDocumentViewer();
    resetProcessPanels();
    activeCaseId = null;
    activeCasePayload = null;
    clearProcessState();

    if (createCaseButton) createCaseButton.disabled = true;
    runWorkflowButton.disabled = true;
    startCaseProgress(buildUploadProgressMessages(files));
    try {
        const form = new FormData();
        form.append('label', label);
        for (const file of files) {
            form.append('files', file);
        }
        const response = await fetch(`${API_URL}/api/cases`, { method: 'POST', body: form });
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const data = await response.json();
        activeCasePayload = data;
        activeCaseId = data.id;
        persistProcessState({ activeCaseId: data.id });
        stopCaseProgress(`Registro ${data.id} cargado con ${data.files.length} archivo(s) listos para ejecutar.`);
        addMessage(`Paquete cargado: ${data.label} (${data.files.length} archivo(s) procesables).`, 'nova');
        renderCaseChecklist(null);
        renderWorkflowDecision(null);
        renderPrecheckReport(null);
        renderExecutiveReport(null);
        renderWorkflowRun(null);
        return data;
    } catch (error) {
        console.error('Error creando registro:', error);
        stopCaseProgress('No pude cargar el paquete.', true);
        return null;
    } finally {
        if (createCaseButton) createCaseButton.disabled = false;
        runWorkflowButton.disabled = false;
    }
}

async function runWorkflow() {
    const files = getSelectedPackageFiles();
    if (!activeCaseId) {
        const created = await createCase();
        if (!created?.id) {
            return;
        }
    }

    runWorkflowButton.disabled = true;
    if (createCaseButton) createCaseButton.disabled = true;
    startCaseProgress(buildWorkflowProgressMessages(activeCaseId, files));
    try {
        const response = await fetch(`${API_URL}/api/cases/${activeCaseId}/run-workflow`, { method: 'POST' });
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const data = await response.json();
        activeCasePayload = data;
        const analysis = data.analysis || {};
        const workflowRun = analysis.workflow_run || null;
        renderCaseChecklist(analysis.checklist || null, analysis.validacion_resumen || null, data);
        renderCaseDecision(analysis.decision || null, analysis.xlsx_profile || {});
        renderPrecheckReport(workflowRun?.executive_report_precheck || analysis.reporte_ejecutivo || null);
        renderExecutiveReport(workflowRun?.executive_report_final || null, workflowRun?.output_926 || analysis.output_926 || null);
        renderWorkflowRun(workflowRun);
        loadRecoverable926Cases();
        stopCaseProgress(`${activeCaseId}: ${workflowRun?.status || 'proceso ejecutado'}`);
        addMessage(`Proceso automático ${workflowRun?.status || 'ejecutado'} para ${data.label}.`, 'nova');
    } catch (error) {
        console.error('Error ejecutando flujo del expediente:', error);
        stopCaseProgress('No pude ejecutar el flujo automático.', true);
    } finally {
        runWorkflowButton.disabled = false;
        if (createCaseButton) createCaseButton.disabled = false;
    }
}

async function loadActiveCase(caseId) {
    if (!caseId) return;
    try {
        const response = await fetch(`${API_URL}/api/cases/${encodeURIComponent(caseId)}`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const data = await response.json();
        activeCasePayload = data;
        const analysis = data.analysis || {};
        const workflowRun = analysis.workflow_run || null;
        renderCaseChecklist(analysis.checklist || null, analysis.validacion_resumen || null, data);
        renderCaseDecision(analysis.decision || null, analysis.xlsx_profile || {});
        renderPrecheckReport(workflowRun?.executive_report_precheck || analysis.reporte_ejecutivo || null);
        renderExecutiveReport(workflowRun?.executive_report_final || null, workflowRun?.output_926 || analysis.output_926 || null);
        renderWorkflowRun(workflowRun);
        loadRecoverable926Cases();
        const statusText = `${caseId}: ${workflowRun?.status || data.status || 'listo'}`;
        caseStatusLine.classList.remove('processing', 'error');
        caseStatusLine.textContent = statusText;
        persistProcessState({ activeCaseId: caseId, processing: false, error: false, statusText });
    } catch (error) {
        console.error('No pude cargar el detalle del expediente activo:', error);
    }
}

function addMessage(text, sender, sources = []) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${sender}`;

    const content = document.createElement('div');
    content.className = 'message-content';
    content.textContent = text;

    messageDiv.appendChild(content);
    if (sender === 'nova' && Array.isArray(sources) && sources.length) {
        const docsBlock = document.createElement('div');
        docsBlock.className = 'message-doc-actions';
        const title = document.createElement('div');
        title.className = 'panel-label';
        title.textContent = 'Abrir documentos';
        docsBlock.appendChild(title);
        for (const source of sources.slice(0, 8)) {
            if (!source.source_url) continue;
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'search-button secondary compact-button';
            const typeLabel = source.document_type || 'documento';
            button.textContent = `${source.titulo} · ${typeLabel}`;
            button.addEventListener('click', () => {
                openDocumentUrlViewer(source.source_url, source.titulo || 'archivo');
            });
            docsBlock.appendChild(button);
        }
        if (docsBlock.children.length > 1) {
            messageDiv.appendChild(docsBlock);
        }
    }
    chatContainer.appendChild(messageDiv);
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

function toggleSources() {
    if (!sourcesSection || !toggleIcon) return;
    sourcesSection.classList.toggle('expanded');
    toggleIcon.textContent = sourcesSection.classList.contains('expanded') ? '▲' : '▼';
}

function renderSources(sources) {
    if (!sourcesContent) return;
    sourcesContent.innerHTML = '';

    if (!sources.length) {
        sourcesContent.innerHTML = '<div class="source-item">No hay fuentes para esta respuesta.</div>';
        return;
    }

    for (const source of sources) {
        const sourceItem = document.createElement('div');
        sourceItem.className = 'source-item';
        const relevancia = source.relevancia ? ` (${Math.round(source.relevancia * 100)}%)` : '';
        const meta = `
            <div class="source-meta">
                <span class="source-chip">${source.topic || 'sin-topic'}</span>
                <span class="source-chip">${source.document_type || 'sin-tipo'}</span>
            </div>
        `;
        const sourceLink = source.source_url
            ? `<button class="search-button secondary compact-button" type="button" data-source-url="${encodeURIComponent(source.source_url)}" data-source-title="${encodeURIComponent(source.titulo || 'archivo')}">Ver</button>`
            : '';
        sourceItem.innerHTML = `
            <strong>${source.titulo}${relevancia}</strong>
            ${meta}
            <div>${source.contenido}</div>
            ${sourceLink}
        `;
        sourcesContent.appendChild(sourceItem);
    }
    sourcesContent.querySelectorAll('[data-source-url]').forEach((button) => {
        button.addEventListener('click', () => {
            openDocumentUrlViewer(
                decodeURIComponent(button.dataset.sourceUrl || ''),
                decodeURIComponent(button.dataset.sourceTitle || 'archivo')
            );
        });
    });
}

function renderWorkflowDecision(decision) {
    workflowContent.innerHTML = '';
    toggleSection(workflowSection, Boolean(decision));

    if (!decision) {
        return;
    }

    const card = document.createElement('article');
    card.className = 'workflow-card';
    const renderList = (items, emptyLabel) => {
        if (!items?.length) {
            return `<div class="service-role">${emptyLabel}</div>`;
        }
        const rows = items.map((item) => {
            const text = String(item || '').trim();
            if (!text.includes(' | ') && !text.includes(';') && !text.includes('Detalle por hoja:')) {
                return `<li>${text}</li>`;
            }
            let segments = text
                .split(/\s*;\s*/)
                .map((segment) => segment.trim())
                .filter(Boolean);
            if (text.includes('Detalle por hoja:')) {
                const [head, detail] = text.split('Detalle por hoja:');
                const detailSegments = String(detail || '')
                    .split(/\s*,\s*/)
                    .map((segment) => segment.trim())
                    .filter(Boolean);
                segments = [String(head || '').trim(), ...detailSegments];
            }
            const detailList = segments.length
                ? `<ul class="workflow-detail-bullets">${segments.map((segment) => `<li>${segment}</li>`).join('')}</ul>`
                : '';
            return `<li>${detailList || text}</li>`;
        }).join('');
        return `<ul class="workflow-bullets">${rows}</ul>`;
    };

    card.innerHTML = `
        <div class="workflow-topline">
            <div>
                <div class="panel-label">Estado</div>
                <strong>${decision.recommended_status || 'n/d'}</strong>
            </div>
        </div>
        <p class="workflow-summary">${decision.summary}</p>
        <div class="workflow-grid">
            <div class="workflow-block">
                <div class="panel-label">Bloqueantes</div>
                ${renderList(decision.blockers, 'Sin bloqueantes inmediatos detectados.')}
            </div>
            <div class="workflow-block">
                <div class="panel-label">Siguiente paso</div>
                <p class="workflow-summary">${decision.next_step}</p>
                <div class="service-role">Canal: ${decision.recommended_channel}</div>
            </div>
        </div>
    `;

    workflowContent.appendChild(card);
}

function renderCaseDecision(decision, xlsxProfile) {
    if (!decision) {
        renderWorkflowDecision(null);
        return;
    }

    renderWorkflowDecision({
        flow: decision.flow,
        recommended_status: decision.recommended_status,
        summary: decision.summary,
        blockers: decision.blockers || [],
        next_step: decision.next_step,
        recommended_channel: 'expediente_local',
    });
}

function formatMatchStatus(ok) {
    return ok ? 'Coincide' : 'No coincide';
}

function buildValidationChecks(validationSummary = {}, checklist = {}) {
    const matches = validationSummary?.matches || {};
    const rows = [];
    if (matches.cedula_principal?.expected) {
        const principalSuffix = matches.cedula_principal.inferred
            ? ' · coincidencia inferida por el expediente'
            : '';
        rows.push({
            title: 'Documento principal',
            detail: `XLSX ${matches.cedula_principal.expected} vs cédula ${matches.cedula_principal.matched || 'n/d'}${matches.cedula_principal.filename ? ` (${matches.cedula_principal.filename})` : ''}${principalSuffix}`,
            ok: Boolean(matches.cedula_principal.ok),
        });
    }
    if (matches.rut_nit?.expected) {
        rows.push({
            title: 'NIT del empleador',
            detail: `XLSX ${matches.rut_nit.expected} vs RUT ${matches.rut_nit.matched || 'n/d'}${matches.rut_nit.filename ? ` (${matches.rut_nit.filename})` : ''}`,
            ok: Boolean(matches.rut_nit.ok),
        });
    }
    if (matches.representante_documento?.expected || matches.representante_documento?.matched) {
        const representativeFilename = matches.representante_documento.cedula
            ? ` (${matches.representante_documento.cedula})`
            : '';
        const representativeSuffix = matches.representante_documento.inferred
            ? ' · coincidencia inferida por el expediente'
            : '';
        rows.push({
            title: 'Documento del representante',
            detail: `Formulario ${matches.representante_documento.expected || 'n/d'} vs cédula ${matches.representante_documento.matched || 'n/d'}${representativeFilename}${representativeSuffix}`,
            ok: Boolean(matches.representante_documento.ok),
        });
    }
    if (matches.empresa_nombre?.camara || matches.empresa_nombre?.formulario) {
        rows.push({
            title: 'Razón social',
            detail: `Cámara ${matches.empresa_nombre.camara || 'n/d'} vs formulario ${matches.empresa_nombre.formulario || 'n/d'}`,
            ok: Boolean(matches.empresa_nombre.ok),
        });
    }
    if (matches.camara_vigencia?.issued_at_human) {
        rows.push({
            title: 'Vigencia de cámara',
            detail: `Fecha de expedición ${matches.camara_vigencia.issued_at_human} · antigüedad ${matches.camara_vigencia.age_days ?? 'n/d'} día(s)`,
            ok: Boolean(matches.camara_vigencia.ok),
        });
    }
    if (!rows.length && Array.isArray(checklist.matched_documents) && checklist.matched_documents.length) {
        rows.push({
            title: 'Coincidencias de documento principal',
            detail: `Se encontraron estas coincidencias directas contra el documento principal del XLSX: ${checklist.matched_documents.join(', ')}`,
            ok: true,
        });
    }
    return rows;
}

function humanizeOutputMode(mode) {
    if (mode === 'legacy') return 'integrado';
    if (mode === 'pending') return 'pendiente';
    return mode || 'n/d';
}

function formatCurrencyCop(value) {
    if (value === null || value === undefined || value === '' || value === 'n/d') {
        return 'n/d';
    }
    const digits = String(value).replace(/[^\d-]/g, '');
    if (!digits) {
        return String(value);
    }
    const amount = Number(digits);
    if (!Number.isFinite(amount)) {
        return String(value);
    }
    return new Intl.NumberFormat('es-CO', {
        style: 'currency',
        currency: 'COP',
        maximumFractionDigits: 0,
    }).format(amount);
}

function describeSedeValue(sede) {
    const code = String(sede?.sede || '').trim();
    const name = String(sede?.nombre_sede || '').trim();
    if (name.toUpperCase() === 'PRINCIPAL') {
        return 'Principal';
    }
    if (!code) {
        return 'n/d';
    }
    return code;
}

function humanizeWorkflowStep(step) {
    const mapping = {
        prevalidacion_documental: {
            title: 'Prevalidación documental',
            detail: step.status === 'blocked'
                ? 'Se detectaron inconsistencias documentales antes de continuar.'
                : 'Se revisaron documentos, cruces y consistencia del expediente.',
        },
        generacion_manifiesto: {
            title: 'Preparación del archivo base',
            detail: 'Se preparó el archivo base del trámite para continuar el proceso.',
        },
        carga_lote_legacy: {
            title: 'Registro del trámite',
            detail: 'Se registró el trámite y se asignó el número interno de proceso.',
        },
        limpieza_preparacion: {
            title: 'Limpieza y preparación',
            detail: 'Se organizaron y limpiaron los datos del expediente para validarlos.',
        },
        importacion_proc: {
            title: 'Carga de empresa, sedes y trabajadores',
            detail: step.detail?.replace('Se importó empleador', 'Se cargó el empleador').replace(' para idtrámite', ' para el trámite') || 'Se cargaron empresa, sedes y trabajadores.',
        },
        sync_engine: {
            title: 'Sincronización de datos',
            detail: 'La información quedó lista para validaciones y generación del 926.',
        },
        prebuild_validaciones: {
            title: 'Validación previa',
            detail: step.status === 'blocked'
                ? 'La validación previa detectó diferencias que deben corregirse.'
                : 'Se validaron estructura, conteos y consistencia del trámite.',
        },
        reporte_previo: {
            title: 'Reporte previo al 926',
            detail: 'Se generó el resumen ejecutivo previo a la salida 926.',
        },
        generacion_926: {
            title: 'Generación del 926',
            detail: step.detail?.replace('Archivo 926 generado para lote', 'Se generó el archivo 926 para el trámite') || 'Se generó el archivo 926.',
        },
        reporte_final: {
            title: 'Reporte final',
            detail: 'Se consolidó el resultado final del proceso.',
        },
        cierre_flujo: {
            title: 'Cierre del proceso',
            detail: 'El proceso terminó correctamente.',
        },
    };
    const preset = mapping[step.name] || {};
    return {
        title: preset.title || step.title || step.name || 'Paso',
        detail: (preset.detail || step.detail || 'Sin detalle disponible.')
            .replaceAll('legacy', 'integración')
            .replaceAll('clone', 'motor interno'),
    };
}

function renderDocumentGallery(receivedSummary, caseId = activeCaseId, options = {}) {
    const manualReview = options.manualReview || {};
    const enableReview = Boolean(options.enableReview && caseId);
    const xlsxFiles = Array.isArray(options.xlsxFiles) ? options.xlsxFiles : [];
    const documentMeta = options.documentMeta || {};
    const xlsxMetaFactory = options.xlsxMetaFactory || (() => null);
    const groups = [];
    if (enableReview && xlsxFiles.length) {
        groups.push({
            label: 'XLSX',
            meta: `${xlsxFiles.length} archivo(s) · archivo de origen`,
            kind: 'xlsx',
            files: xlsxFiles,
        });
    }
    for (const item of receivedSummary || []) {
        groups.push({
            label: item.label,
            meta: `${item.count} archivo(s) · códigos ${item.legacy_codes.join(', ') || 'n/d'}`,
            kind: 'document',
            legacyCodes: item.legacy_codes || [],
            files: Array.isArray(item.files) ? item.files : [],
        });
    }
    if (!groups.length) {
        return '<div class="service-role">Sin resumen documental todavía.</div>';
    }
    return `<div class="document-gallery">${groups.map((item) => `
        <article class="document-group">
            <div class="document-group-head">
                <strong>${item.label}</strong>
                <span class="service-role">${item.meta}</span>
            </div>
            <div class="document-list">
                ${(Array.isArray(item.files) ? item.files : []).map((file) => {
                    if (enableReview) {
                        const detail = item.kind === 'xlsx'
                            ? `${item.label} · archivo de origen`
                            : `${item.label} · código ${item.legacyCodes.join(', ') || 'n/d'}`;
                        return buildDocumentReviewRow({
                            caseId,
                            file,
                            label: item.label,
                            detail,
                            kind: item.kind,
                            manualReview,
                            meta: item.kind === 'xlsx' ? xlsxMetaFactory(file) : documentMeta[file],
                        });
                    }
                    const detail = item.kind === 'xlsx'
                        ? `${item.label} · archivo de origen`
                        : `${item.label} · código ${item.legacyCodes.join(', ') || 'n/d'}`;
                    const meta = item.kind === 'xlsx' ? xlsxMetaFactory(file) : documentMeta[file];
                    const displayName = getDisplayFilename(file, meta);
                    return `
                        <div class="document-row">
                            <div class="document-row-copy">
                                <div class="document-row-name">${displayName}</div>
                                ${displayName !== file ? `<div class="service-role">origen: ${file}</div>` : ''}
                                <div class="service-role">${detail}</div>
                            </div>
                            <button class="search-button secondary compact-button" type="button" data-case="${caseId}" data-file="${file}" data-display-name="${displayName}">Ver</button>
                        </div>
                    `;
                }).join('')}
            </div>
        </article>
    `).join('')}</div>`;
}

function renderCaseChecklist(checklist, validationSummary = null, casePayload = activeCasePayload) {
    caseChecklistContent.innerHTML = '';
    toggleSection(checklistSection, Boolean(checklist));
    if (!checklist) {
        return;
    }

    const card = document.createElement('article');
    card.className = 'workflow-card';
    const renderList = (items, emptyLabel) => items?.length
        ? `<ul class="workflow-bullets">${items.map((item) => `<li>${item}</li>`).join('')}</ul>`
        : `<div class="service-role">${emptyLabel}</div>`;
    const receivedSummary = Array.isArray(checklist.received_summary) ? checklist.received_summary : [];
    const validationChecks = buildValidationChecks(validationSummary, checklist);
    const manualReview = casePayload?.analysis?.manual_review || {};
    const xlsxFiles = collectXlsxFiles(casePayload);
    const documentMeta = buildDocumentMetaMap(casePayload);
    const xlsxMetaFactory = (filename) => buildXlsxMeta(casePayload, filename);
    card.innerHTML = `
        <div class="workflow-grid">
            <div class="workflow-block">
                <div class="panel-label">Requeridos</div>
                ${renderList(checklist.required, 'Sin checklist requerido.')}
            </div>
            <div class="workflow-block">
                <div class="panel-label">Recibidos</div>
                ${renderList(checklist.received, 'Sin documentos reconocidos.')}
            </div>
            <div class="workflow-block">
                <div class="panel-label">Faltantes</div>
                ${renderList(checklist.missing, 'No se detectan faltantes.')}
            </div>
            <div class="workflow-block">
                <div class="panel-label">Cruce XLSX</div>
                ${renderList(checklist.matched_documents, 'Ningun documento OCR coincide todavia con el XLSX.')}
            </div>
        </div>
        <div class="workflow-block">
            <div class="panel-label">Verificaciones realizadas</div>
            ${validationChecks.length
                ? `<div class="report-detail-list">${validationChecks.map((item) => `
                    <div class="report-detail-row">
                        <strong>${item.title}</strong>
                        <div class="service-role">${item.detail}</div>
                        <div class="service-role">${formatMatchStatus(item.ok)}</div>
                    </div>
                `).join('')}</div>`
                : '<div class="service-role">Aún no hay verificaciones detalladas para mostrar.</div>'}
        </div>
        <div class="workflow-block">
            <div class="panel-label">Resumen documental</div>
            ${renderDocumentGallery(receivedSummary, activeCaseId, { enableReview: true, manualReview, xlsxFiles, documentMeta, xlsxMetaFactory })}
        </div>
    `;
    caseChecklistContent.appendChild(card);
    card.querySelectorAll('[data-case][data-file]').forEach((button) => {
        button.addEventListener('click', () => openDocumentViewer(button.dataset.case, button.dataset.file, button.dataset.displayName || ''));
    });
    card.querySelectorAll('[data-review-case][data-review-file][data-review-verdict]').forEach((button) => {
        button.addEventListener('click', () => saveManualReview(
            button.dataset.reviewCase,
            button.dataset.reviewKind || 'document',
            button.dataset.reviewFile,
            button.dataset.reviewVerdict,
            button,
        ));
    });
}

function renderReportCard(container, report, emptyLabel, output926 = null) {
    container.innerHTML = '';
    if (!report) {
        return;
    }

    const card = document.createElement('article');
    card.className = 'workflow-card';
    const resumen = report.resumen_ejecutivo || {};
    const estadoFinal = resumen.estado || resumen.estado_final || report.estado_final || 'n/d';
    const empresa = resumen.empresa || report.empresa || 'n/d';
    const nit = resumen.nit || report.nit || 'n/d';
    const fechaProceso = resumen.fecha_proceso_human || report.fecha_proceso_human || resumen.fecha_proceso || report.fecha_proceso || 'n/d';
    const nominaTotal = formatCurrencyCop(resumen.nomina_total ?? report.nomina_total ?? 'n/d');
    const trabajadores = resumen.numero_trabajadores ?? resumen.empleados ?? resumen.empleados_total ?? resumen.desglose_sedes_totales?.empleados_total ?? 'n/d';
    const sedes = resumen.numero_sedes ?? resumen.sedes ?? resumen.sedes_excel ?? resumen.desglose_sedes?.length ?? 'n/d';
    const draft926 = output926?.draft || null;
    const legacy926 = output926?.legacy || null;
    const outputMode = output926?.mode || 'pending';
    const outputReason = output926?.reason || legacy926?.error || '';
    const file926Url = activeCaseId ? buildCase926Url(activeCaseId) : '';
    const desgloseSedes = Array.isArray(resumen.desglose_sedes) ? resumen.desglose_sedes : [];
    const reportText = report.texto || buildExecutiveReportText(estadoFinal, empresa, nit, trabajadores, sedes);
    const outputBadge = output926
        ? legacy926?.ok
            ? '<span class="source-chip">926 listo</span>'
            : draft926
                ? '<span class="source-chip">926 borrador listo</span>'
                : '<span class="source-chip">926 pendiente</span>'
        : '';
    card.innerHTML = `
        <div class="workflow-topline">
            <div>
                <div class="panel-label">Estado final</div>
                <strong>${estadoFinal}</strong>
            </div>
            <div class="workflow-badges">
                ${outputBadge}
                <button class="search-button secondary compact-button" type="button" data-copy-report>Copiar reporte</button>
            </div>
        </div>
        <div class="workflow-grid">
            <div class="workflow-block">
                <div class="panel-label">Afiliado</div>
                <p class="workflow-summary">${empresa}</p>
            </div>
            <div class="workflow-block">
                <div class="panel-label">NIT</div>
                <p class="workflow-summary">${nit}</p>
            </div>
            <div class="workflow-block">
                <div class="panel-label">Fecha del proceso</div>
                <p class="workflow-summary">${fechaProceso}</p>
            </div>
            <div class="workflow-block">
                <div class="panel-label">Nómina total</div>
                <p class="workflow-summary">${nominaTotal}</p>
            </div>
            <div class="workflow-block">
                <div class="panel-label">Trabajadores</div>
                <p class="workflow-summary">${trabajadores}</p>
            </div>
            <div class="workflow-block">
                <div class="panel-label">Sedes</div>
                <p class="workflow-summary">${sedes}</p>
            </div>
        </div>
        <div class="workflow-block">
            <div class="panel-label">Resumen ejecutivo</div>
            <div class="report-detail-list">
                ${reportText
                    .split('\n')
                    .filter(Boolean)
                    .map((line) => `<div class="report-detail-row"><div class="service-role">${line}</div></div>`)
                    .join('')}
            </div>
        </div>
        ${output926 ? `
            <div class="workflow-block">
                <div class="panel-label">Archivo 926</div>
                <p class="workflow-summary">${legacy926?.ok ? (legacy926.filename || 'legacy_926.txt') : draft926 ? draft926.filename : 'No disponible'}</p>
                <div class="service-role">Modo: ${humanizeOutputMode(outputMode)}</div>
                <div class="service-role">${legacy926?.ok ? 'Generado por la integración automática.' : draft926?.note || outputReason || 'Sin salida 926 todavía.'}</div>
                ${file926Url ? `
                    <div class="case-head-actions report-actions">
                        <button class="search-button secondary compact-button" type="button" data-open-926="${legacy926?.filename || draft926?.filename || 'archivo_926.txt'}">Abrir 926</button>
                        <button class="search-button compact-button" type="button" data-download-926="${legacy926?.filename || draft926?.filename || 'archivo_926.txt'}">Descargar 926</button>
                    </div>
                ` : ''}
            </div>
        ` : ''}
        ${desgloseSedes.length ? `
            <div class="workflow-block">
                <div class="panel-label">Sedes y trabajadores</div>
                <div class="report-detail-list">
                    ${desgloseSedes.map((sede) => `
                        <div class="report-detail-row">
                            <strong>${sede.nombre_sede || `Sede ${sede.sede || 'n/d'}`}</strong>
                            <div class="service-role">Sede: ${describeSedeValue(sede)} · Trabajadores: ${sede.empleados_total ?? 'n/d'} · Centros: ${sede.centros_costo ?? 'n/d'}</div>
                            <div class="service-role">${sede.direccion || 'Sin dirección'} · Ciudad: ${describeCity(sede.ciudad)}</div>
                        </div>
                    `).join('')}
                </div>
            </div>
        ` : ''}
    `;
    container.appendChild(card);
    const copyButton = card.querySelector('[data-copy-report]');
    copyButton?.addEventListener('click', () => copyText(report.texto || '', copyButton));
    const open926Button = card.querySelector('[data-open-926]');
    open926Button?.addEventListener('click', () => openCase926Viewer(activeCaseId, open926Button.dataset.open926 || 'archivo_926.txt'));
    const download926Button = card.querySelector('[data-download-926]');
    download926Button?.addEventListener('click', () => downloadCase926(activeCaseId, download926Button.dataset.download926 || 'archivo_926.txt'));
}

function renderPrecheckReport(report) {
    toggleSection(precheckSection, Boolean(report));
    renderReportCard(
        precheckReportContent,
        report,
        'Aún no hay reporte de prevalidación.'
    );
}

function renderExecutiveReport(report, output926 = null) {
    toggleSection(executiveSection, Boolean(report));
    renderReportCard(
        executiveReportContent,
        report,
        'Aún no hay reporte final del proceso.',
        output926
    );
}

function renderWorkflowRun(workflowRun) {
    workflowRunContent.innerHTML = '';
    toggleSection(workflowRunSection, Boolean(workflowRun));
    if (!workflowRun) {
        return;
    }

    const card = document.createElement('article');
    card.className = 'workflow-card';
    const steps = Array.isArray(workflowRun.steps) ? workflowRun.steps : [];
    const precheckSummary = workflowRun.executive_report_precheck?.resumen_ejecutivo || {};
    const finalSummary = workflowRun.executive_report_final?.resumen_ejecutivo || {};
    const precheckWorkers = precheckSummary.numero_trabajadores ?? 'n/d';
    const precheckSedes = precheckSummary.numero_sedes ?? 'n/d';
    const precheckFecha = precheckSummary.fecha_proceso_human || precheckSummary.fecha_proceso || workflowRun.executive_report_precheck?.fecha_proceso_human || workflowRun.executive_report_precheck?.fecha_proceso || 'n/d';
    const finalEstado = finalSummary.estado || finalSummary.estado_final || workflowRun.executive_report_final?.estado_final || 'n/d';
    const finalEmpresa = finalSummary.empresa || workflowRun.executive_report_final?.empresa || 'n/d';
    const finalNit = finalSummary.nit || workflowRun.executive_report_final?.nit || 'n/d';
    const finalWorkers = finalSummary.numero_trabajadores ?? finalSummary.empleados ?? finalSummary.desglose_sedes_totales?.empleados_total ?? 'n/d';
    const finalSedes = finalSummary.numero_sedes ?? finalSummary.sedes ?? finalSummary.desglose_sedes?.length ?? 'n/d';
    const finalFecha = finalSummary.fecha_proceso_human || finalSummary.fecha_proceso || workflowRun.executive_report_final?.fecha_proceso_human || workflowRun.executive_report_final?.fecha_proceso || 'n/d';
    const prebuildStep = steps.find((step) => step.name === 'prebuild_validaciones') || null;
    const salaryCheck = prebuildStep?.payload?.prebuild?.xlsx_sede_salary_check || null;
    const prebuildWarnings = prebuildStep?.payload?.prebuild?.prebuild?.warnings || [];
    const salaryErrors = Array.isArray(salaryCheck?.errors) ? salaryCheck.errors : [];
    const currentStep = humanizeWorkflowStep({ name: workflowRun.current_step, title: workflowRun.current_step, detail: workflowRun.stop_reason || '' });
    const workflowTimings = workflowRun.timings || {};
    const totalDuration = formatDurationMs(workflowTimings.total_duration_ms);
    const analysisDuration = formatDurationMs(workflowTimings.analysis_duration_ms);
    card.innerHTML = `
        <div class="workflow-topline">
            <div>
                <div class="panel-label">Estado del flujo</div>
                <strong>${workflowRun.status || 'n/d'}</strong>
            </div>
            <div class="workflow-badges">
                <span class="source-chip">${currentStep.title}</span>
            </div>
        </div>
        <p class="workflow-summary">${(workflowRun.stop_reason || 'Flujo completado sin bloqueos.').replaceAll('legacy', 'integración').replaceAll('clone', 'motor interno')}</p>
        <div class="workflow-grid">
            <div class="workflow-block">
                <div class="panel-label">Tiempo total</div>
                <p class="workflow-summary">${totalDuration}</p>
            </div>
            <div class="workflow-block">
                <div class="panel-label">Tiempo de prevalidación</div>
                <p class="workflow-summary">${analysisDuration}</p>
            </div>
        </div>
        ${(workflowRun.executive_report_precheck || workflowRun.executive_report_final)
            ? `<div class="workflow-grid">
                <div class="workflow-block">
                    <div class="panel-label">Reporte de prevalidación</div>
                    <p class="workflow-summary">Estado: ${precheckSummary.estado || workflowRun.executive_report_precheck?.estado_final || 'n/d'} · Fecha: ${precheckFecha} · Afiliado: ${precheckSummary.empresa || 'n/d'} · NIT: ${precheckSummary.nit || 'n/d'} · Trabajadores: ${precheckWorkers} · Sedes: ${precheckSedes}</p>
                </div>
                <div class="workflow-block">
                    <div class="panel-label">Reporte final</div>
                    <p class="workflow-summary">${workflowRun.executive_report_final ? `Estado: ${finalEstado} · Fecha: ${finalFecha} · Afiliado: ${finalEmpresa} · NIT: ${finalNit} · Trabajadores: ${finalWorkers} · Sedes: ${finalSedes}` : 'Pendiente o no disponible.'}</p>
                </div>
            </div>`
            : ''}
        ${(salaryErrors.length || prebuildWarnings.length) ? `
            <div class="workflow-block">
                <div class="panel-label">Detalle de validación</div>
                <div class="report-detail-list">
                    ${salaryErrors.map((item) => `
                        <div class="report-detail-row">
                            <strong>Salarios sede ${item.sede || 'n/d'}</strong>
                            <div class="service-role">Excel: ${item.total_excel ?? 'n/d'} · Importado: ${item.total_importado ?? 'n/d'} · Diferencia: ${item.diferencia ?? 'n/d'}</div>
                        </div>
                    `).join('')}
                    ${!salaryErrors.length && prebuildWarnings.length ? `
                        <div class="report-detail-row">
                            <strong>Observaciones técnicas</strong>
                            <div class="service-role">${prebuildWarnings.slice(0, 5).map((item) => item.detail || item.code || 'warning').join(' · ')}</div>
                        </div>
                    ` : ''}
                </div>
            </div>
        ` : ''}
        <div class="workflow-block">
            <div class="panel-label">Resumen del proceso</div>
            ${steps.length
                ? `<ul class="workflow-bullets">${steps.map((step) => {
                    const view = humanizeWorkflowStep(step);
                    const durationLabel = step.duration_ms != null ? ` · ${formatDurationMs(step.duration_ms)}` : '';
                    return `<li><strong>${view.title}</strong> · ${step.status}${durationLabel} · ${view.detail}</li>`;
                }).join('')}</ul>`
                : '<div class="service-role">Sin pasos ejecutados.</div>'}
        </div>
    `;
    workflowRunContent.appendChild(card);
}

function renderCaseSearch(results) {
    caseSearchContent.innerHTML = '';
    caseSearchSection?.classList.toggle('hidden', !results?.length);
    if (!results?.length) {
        return;
    }
    for (const result of results) {
        const card = document.createElement('article');
        card.className = 'workflow-card';
        const receivedSummary = Array.isArray(result.received_summary) ? result.received_summary : [];
        const precheck = result.precheck || {};
        const executiveReport = result.executive_report || {};
        const resumen = executiveReport.resumen_ejecutivo || {};
        const empresa = resumen.empresa || result.profile?.empresa || result.label || 'n/d';
        const nit = resumen.nit || result.profile?.nit || 'n/d';
        const documento = resumen.documento || result.profile?.documento || 'n/d';
        const trabajadores = resumen.numero_trabajadores ?? result.profile?.numero_trabajadores ?? 'n/d';
        const sedes = resumen.numero_sedes ?? result.profile?.numero_sedes ?? 'n/d';
        const fechaProceso = resumen.fecha_proceso_human || resumen.fecha_proceso || result.updated_at?.slice(0, 10) || 'n/d';
        const errores = Array.isArray(resumen.errores) ? resumen.errores : [];
        const observaciones = Array.isArray(resumen.observaciones) ? resumen.observaciones : [];
        card.innerHTML = `
            <div class="workflow-topline">
                <div>
                    <div class="panel-label">${result.case_id}</div>
                    <strong>${empresa}</strong>
                </div>
                <div class="workflow-badges">
                    <span class="source-chip">${precheck.approved ? 'Prevalidación OK' : 'Prevalidación NO OK'}</span>
                </div>
            </div>
            <div class="workflow-block">
                <div class="panel-label">Reporte ejecutivo</div>
                <div class="workflow-grid">
                    <div class="workflow-block">
                        <div class="panel-label">Afiliado</div>
                        <p class="workflow-summary">${empresa}</p>
                    </div>
                    <div class="workflow-block">
                        <div class="panel-label">NIT</div>
                        <p class="workflow-summary">${nit}</p>
                    </div>
                    <div class="workflow-block">
                        <div class="panel-label">Documento</div>
                        <p class="workflow-summary">${documento}</p>
                    </div>
                    <div class="workflow-block">
                        <div class="panel-label">Fecha del proceso</div>
                        <p class="workflow-summary">${fechaProceso}</p>
                    </div>
                    <div class="workflow-block">
                        <div class="panel-label">Trabajadores</div>
                        <p class="workflow-summary">${trabajadores}</p>
                    </div>
                    <div class="workflow-block">
                        <div class="panel-label">Sedes</div>
                        <p class="workflow-summary">${sedes}</p>
                    </div>
                </div>
                ${(errores.length || observaciones.length) ? `
                    <div class="report-detail-list">
                        ${errores.length ? `
                            <div class="report-detail-row">
                                <strong>Hallazgos</strong>
                                <ul class="workflow-bullets">${errores.map((item) => `<li>${item}</li>`).join('')}</ul>
                            </div>
                        ` : ''}
                        ${observaciones.length ? `
                            <div class="report-detail-row">
                                <strong>Observaciones</strong>
                                <ul class="workflow-bullets">${observaciones.map((item) => `<li>${item}</li>`).join('')}</ul>
                            </div>
                        ` : ''}
                    </div>
                ` : `<p class="workflow-summary">${precheck.approved ? 'Sin hallazgos bloqueantes.' : (executiveReport?.texto || 'Sin reporte ejecutivo disponible.')}</p>`}
            </div>
            <div class="workflow-block">
                <div class="panel-label">Adjuntos clasificados</div>
                ${renderDocumentGallery(receivedSummary, result.case_id)}
            </div>
            <div class="case-head-actions">
                <button class="search-button secondary compact-button" type="button" data-copy-report="${encodeURIComponent(executiveReport?.texto || '')}">Copiar reporte</button>
            </div>
        `;
        caseSearchContent.appendChild(card);
    }
    caseSearchContent.querySelectorAll('[data-case][data-file]').forEach((button) => {
        button.addEventListener('click', () => openDocumentViewer(button.dataset.case, button.dataset.file, button.dataset.displayName || ''));
    });
    caseSearchContent.querySelectorAll('[data-copy-report]').forEach((button) => {
        button.addEventListener('click', () => copyText(decodeURIComponent(button.dataset.copyReport || ''), button));
    });
}

async function compare926() {
    const leftContent = ((compareLeftFile?.dataset?.loadedContent || '').trim());
    const rightContent = ((compareRightFile?.dataset?.loadedContent || '').trim());
    if (!leftContent || !rightContent) {
        compare926Content.innerHTML = '<div class="source-item">Carga el 926 del clone y el 926 del sistema antiguo para compararlos.</div>';
        return;
    }
    compare926Button.disabled = true;
    compare926Content.innerHTML = '<div class="source-item">Comparando archivos 926...</div>';
    try {
        const response = await fetch(`${API_URL}/api/926/compare`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ left_content: leftContent, right_content: rightContent })
        });
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const data = await response.json();
        compare926Content.innerHTML = `
            <article class="workflow-card">
                <div class="workflow-topline">
                    <div>
                        <div class="panel-label">Resultado</div>
                        <strong>${data.match ? 'Coinciden' : 'Difieren'}</strong>
                    </div>
                    <div class="workflow-badges">
                        <span class="source-chip">Similitud ${Math.round((data.similarity || 0) * 100)}%</span>
                        <span class="source-chip">Diferencias ${data.different_lines || 0}</span>
                    </div>
                </div>
                <p class="workflow-summary">Clone: ${data.left_lines} líneas · Antiguo: ${data.right_lines} líneas</p>
                <div class="workflow-block">
                    <div class="panel-label">Primeras diferencias</div>
                    ${Array.isArray(data.diffs) && data.diffs.length
                        ? `<div class="diff-list">${data.diffs.slice(0, 20).map((item) => `
                            <div class="diff-card">
                                <div class="panel-label">Línea ${item.line}</div>
                                <div class="diff-line diff-left">Clone: ${item.left || '∅'}</div>
                                <div class="diff-line diff-right">Antiguo: ${item.right || '∅'}</div>
                            </div>
                        `).join('')}</div>`
                        : '<div class="service-role">Sin diferencias detectadas.</div>'}
                </div>
            </article>
        `;
    } catch (error) {
        console.error('Error comparando 926:', error);
        compare926Content.innerHTML = '<div class="source-item">No pude comparar los archivos 926.</div>';
    } finally {
        compare926Button.disabled = false;
    }
}

function renderSystemStatus(data) {
    overallStatusText.textContent = data.overall_status === 'ok'
        ? 'Imagine está operando como plano de control'
        : 'Imagine detectó componentes degradados';
    overallStatusBadge.textContent = data.overall_status === 'ok' ? 'OK' : 'DEGRADED';
    overallStatusBadge.className = `status-badge ${data.overall_status === 'ok' ? 'ok' : 'degraded'}`;
    modelsText.textContent = `Chat: ${data.models.chat} · Embeddings: ${data.models.embeddings} · Reranker: ${data.models.reranker}`;
    knowledgeDocsChip.textContent = `Corpus: ${data.knowledge_base.documents} docs`;
    knowledgeChunksChip.textContent = `Indice: ${data.knowledge_base.indexed_chunks} chunks`;
    renderFeedStatus(data.feeding || {});
    renderEvalStatus(data.evaluation || {});
    renderCompare926Status(data.compare_926 || {});
    renderTopicFilters(data.knowledge_base.available_topics || []);

    servicesGrid.innerHTML = '';
    for (const service of data.services) {
        const card = document.createElement('article');
        card.className = 'service-card';
        const badgeClass = service.status === 'ok' ? 'status-badge ok' : 'status-badge degraded';
        card.innerHTML = `
            <header>
                <div class="service-name">${service.name}</div>
                <div class="${badgeClass}">${service.status}</div>
            </header>
            <div class="service-role">${service.role}</div>
            <div class="service-target">${service.target}</div>
        `;
        servicesGrid.appendChild(card);
    }

    actionsList.innerHTML = '';
    for (const action of data.recommended_actions) {
        const card = document.createElement('article');
        card.className = 'action-card';
        card.innerHTML = `<strong>${action.title}</strong><p>${action.description}</p>`;
        actionsList.appendChild(card);
    }
}

function renderCompare926Status(summary) {
    compareTotalChip.textContent = `Comparaciones: ${summary.total ?? 0}`;
    compareExactChip.textContent = `Exactas: ${summary.exact_matches ?? 0}`;
    compareSimilarityChip.textContent = `Similitud: ${Math.round((summary.average_similarity ?? 0) * 100)}%`;
    compareLatest.innerHTML = '';
    const latest = Array.isArray(summary.latest) ? summary.latest : [];
    if (!latest.length) {
        compareLatest.innerHTML = '<div class="service-role">Aún no hay comparaciones de 926 registradas.</div>';
        return;
    }
    for (const item of latest) {
        const card = document.createElement('div');
        card.className = 'feed-error-card';
        card.innerHTML = `<strong>${item.empresa || item.left_case_id || 'sin expediente'}</strong><p>${item.nit ? `NIT ${item.nit} · ` : ''}${item.match ? 'Exacta' : 'Con diferencias'} · ${Math.round((item.similarity || 0) * 100)}% · ${item.different_lines || 0} línea(s)</p>`;
        compareLatest.appendChild(card);
    }
}

function renderEvalStatus(evaluation) {
    evalCasesChip.textContent = `Registros: ${evaluation.cases_total ?? 0}`;
    evalAverageChip.textContent = `Promedio: ${Math.round((evaluation.average_score ?? 0) * 100)}%`;
    evalPassChip.textContent = `Pass rate: ${Math.round((evaluation.pass_rate ?? 0) * 100)}%`;
    evalWeakChip.textContent = `Debiles: ${(evaluation.weak ?? 0) + (evaluation.failed ?? 0)}`;

    const topics = Object.entries(evaluation.topic_performance || {});
    evalTopics.innerHTML = topics.length
        ? topics.map(([topic, score]) => `<span class="source-chip">${topic}: ${Math.round(score * 100)}%</span>`).join('')
        : '<span class="service-role">Sin reporte de evaluacion todavia.</span>';

    const lowest = evaluation.lowest_cases || [];
    evalLowest.innerHTML = '';
    if (!lowest.length) {
        evalLowest.innerHTML = '<div class="service-role">Aun no hay registros débiles detectados.</div>';
        return;
    }

    for (const item of lowest) {
        const card = document.createElement('div');
        card.className = 'feed-error-card';
        card.innerHTML = `<strong>${item.id}</strong><p>Score ${Math.round((item.score || 0) * 100)}% · ${item.grade || 'unknown'}</p>`;
        evalLowest.appendChild(card);
    }
}

function renderFeedStatus(feeding) {
    feedProcessedChip.textContent = `Procesadas: ${feeding.processed ?? 0}`;
    feedSkippedChip.textContent = `Saltadas: ${feeding.skipped ?? 0}`;
    feedFailedChip.textContent = `Fallidas: ${feeding.failed ?? 0}`;
    feedOcrChip.textContent = `OCR: ${feeding.used_ocr ?? 0}`;

    const typeEntries = Object.entries(feeding.source_types || {});
    feedTypes.innerHTML = typeEntries.length
        ? typeEntries.map(([type, count]) => `<span class="source-chip">${type}: ${count}</span>`).join('')
        : '<span class="service-role">Sin detalle de tipos todavia.</span>';

    const strategyEntries = Object.entries(feeding.ocr_strategies || {});
    ocrStrategies.innerHTML = strategyEntries.length
        ? strategyEntries.map(([strategy, count]) => `<span class="source-chip">OCR ${strategy}: ${count}</span>`).join('')
        : '<span class="service-role">Sin estrategias OCR activas en la ultima corrida.</span>';

    const errors = feeding.last_errors || [];
    feedErrors.innerHTML = '';
    if (!errors.length) {
        feedErrors.innerHTML = '<div class="service-role">Sin errores recientes en la ultima alimentacion.</div>';
        return;
    }

    for (const item of errors) {
        const card = document.createElement('div');
        card.className = 'feed-error-card';
        card.innerHTML = `<strong>${item.slug}</strong><p>${item.error || 'Sin detalle disponible'}</p>`;
        feedErrors.appendChild(card);
    }
}

function renderTopicFilters(topics) {
    if (!topicFilters) return;
    const allTopics = ['all', ...topics];
    topicFilters.innerHTML = '';

    for (const topic of allTopics) {
        const button = document.createElement('button');
        button.type = 'button';
        const isAll = topic === 'all';
        const isActive = isAll ? selectedTopics.size === 0 : selectedTopics.has(topic);
        button.className = `topic-filter ${isActive ? 'active' : ''}`;
        button.textContent = topic === 'all' ? 'Todos' : topic;
        button.addEventListener('click', () => {
            if (isAll) {
                selectedTopics.clear();
            } else if (selectedTopics.has(topic)) {
                selectedTopics.delete(topic);
            } else {
                selectedTopics.add(topic);
            }
            renderTopicFilters(topics);
        });
        topicFilters.appendChild(button);
    }
}

searchInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') sendMessage();
});
sendButton.addEventListener('click', sendMessage);
createCaseButton?.addEventListener('click', createCase);
runWorkflowButton.addEventListener('click', runWorkflow);
reindexButton.addEventListener('click', reindexKnowledge);
exportReviewsButton?.addEventListener('click', exportManualReviewsDataset);
compare926Button?.addEventListener('click', compare926);
toggleRecover926Button?.addEventListener('click', () => setRecover926Expanded(!recover926Expanded));
compareRightFile?.addEventListener('change', async () => {
    const file = compareRightFile.files?.[0];
    if (!file) return;
    compareRightFile.dataset.loadedContent = await file.text();
    compare926Content.innerHTML = `<div class="source-item">Archivo ${file.name} cargado. Ya puedes comparar el 926.</div>`;
});
compareLeftFile?.addEventListener('change', async () => {
    const file = compareLeftFile.files?.[0];
    if (!file) return;
    compareLeftFile.dataset.loadedContent = await file.text();
    compare926Content.innerHTML = `<div class="source-item">Archivo clone ${file.name} cargado. Ya puedes comparar los dos 926 sin expediente.</div>`;
});
sourcesSection?.addEventListener('click', toggleSources);
packageFilesInput?.addEventListener('change', () => {
    const files = getSelectedPackageFiles();
    closeDocumentViewer();
    resetProcessPanels();
    activeCaseId = null;
    if (caseProgressTimer) {
        clearInterval(caseProgressTimer);
        caseProgressTimer = null;
    }
    clearProcessState();
    caseStatusLine.classList.remove('processing', 'error');
    const counts = describeSelectedPackage(files);
    const parts = [];
    if (counts.xlsx) parts.push(`${counts.xlsx} XLSX`);
    if (counts.pdf) parts.push(`${counts.pdf} PDF`);
    if (counts.zip) parts.push(`${counts.zip} ZIP`);
    if (counts.image) parts.push(`${counts.image} imagen(es)`);
    if (counts.other) parts.push(`${counts.other} otro(s)`);
    caseStatusLine.textContent = files.length
        ? `Paquete listo: ${parts.join(' · ')}. Pulsa "Ejecutar proceso".`
        : defaultProcessStatusText();
    if (files.length) {
        persistProcessState({ activeCaseId: null, processing: false, error: false, statusText: caseStatusLine.textContent });
    } else {
        persistProcessState({ activeCaseId: null, processing: false, error: false, statusText: caseStatusLine.textContent });
    }
});
documentModalClose?.addEventListener('click', closeDocumentViewer);
documentModalBackdrop?.addEventListener('click', closeDocumentViewer);
viewSwitcher?.querySelectorAll('[data-view]').forEach((button) => {
    button.addEventListener('click', () => switchView(button.dataset.view));
});

fetch(`${API_URL}/health`)
    .then((res) => res.json())
    .then((data) => console.log('✅ Conectado:', data))
    .catch((err) => console.error('❌ Error:', err));

renderSources([]);
renderWorkflowDecision(null);
renderPrecheckReport(null);
renderExecutiveReport(null);
renderCaseSearch([]);
closeDocumentViewer();
activeCaseId = null;
clearProcessState();
caseStatusLine.classList.remove('processing', 'error');
caseStatusLine.textContent = defaultProcessStatusText();
loadRecoverable926Cases();
setRecover926Expanded(false);
loadSystemStatus();
switchView('processView');
