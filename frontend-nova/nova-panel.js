
const rawApiUrl = (import.meta.env.VITE_API_URL || '').trim();
const normalizedApiUrl = rawApiUrl.replace(/\/+$/, '');
const API_URL = (
    !normalizedApiUrl
    || normalizedApiUrl === '/api'
    || /^(https?:)?\/\/(localhost|127\.0\.0\.1)(:\d+)?(\/api)?$/i.test(normalizedApiUrl)
) ? '' : normalizedApiUrl;

const novaPanel        = document.getElementById('novaPanel');
const novaToggleBtn    = document.getElementById('novaToggleBtn');
const novaMinimizeBtn  = document.getElementById('novaMinimizeBtn');
const novaCloseBtn     = document.getElementById('novaCloseBtn');
const novaMinimizedTab = document.getElementById('novaMinimizedTab');
const novaChatContainer= document.getElementById('novaChatContainer');
const novaInput        = document.getElementById('novaInput');
const novaSendBtn      = document.getElementById('novaSendBtn');
const novaActivity     = document.getElementById('novaActivity');

let novaOpen=false, novaMinimized=false, novaSearching=false;
const CHAT_CONTEXT_KEY = 'imagine-chat-context-v1';
const PROCESS_STATE_KEY = 'imagine-process-state-v1';
const NOVA_OPEN_CURRENT_TERMS = new Set(['abralo', 'ábralo', 'abrelo', 'ábrelo', 'ese documento', 'esa fuente', 'ese archivo']);
const NOVA_OPEN_NEXT_TERMS = new Set(['muestrame el siguiente', 'muéstrame el siguiente', 'el siguiente', 'siguiente', 'abre el siguiente']);

function openNova(){novaOpen=true;novaMinimized=false;novaPanel.classList.add('nova-visible');novaMinimizedTab.classList.add('hidden');novaToggleBtn.classList.add('nova-open');document.body.classList.add('nova-open-layout');setTimeout(()=>novaInput?.focus(),320);}
function closeNova(){novaOpen=false;novaMinimized=false;novaPanel.classList.remove('nova-visible');novaMinimizedTab.classList.add('hidden');novaToggleBtn.classList.remove('nova-open');document.body.classList.remove('nova-open-layout');}
function minimizeNova(){novaMinimized=true;novaPanel.classList.remove('nova-visible');novaMinimizedTab.classList.remove('hidden');novaToggleBtn.classList.remove('nova-open');document.body.classList.remove('nova-open-layout');}
function toggleNova(){if(novaMinimized){openNova();}else if(novaOpen){minimizeNova();}else{openNova();}}

function clearWelcome(){const w=novaChatContainer.querySelector('.nova-welcome');if(w)w.remove();}

function readNovaChatContext() {
    try {
        return JSON.parse(window.localStorage.getItem(CHAT_CONTEXT_KEY) || '{}');
    } catch {
        return {};
    }
}

function readNovaProcessState() {
    try {
        return JSON.parse(window.localStorage.getItem(PROCESS_STATE_KEY) || '{}');
    } catch {
        return {};
    }
}

function normalizeNovaText(text='') {
    return String(text || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').trim();
}

function persistNovaChatContext(partial = {}) {
    try {
        const current = readNovaChatContext();
        window.localStorage.setItem(CHAT_CONTEXT_KEY, JSON.stringify({ ...current, ...partial }));
    } catch (error) {
        console.error('NOVA contexto:', error);
    }
}

function detectNovaIntent(query='') {
    const t = normalizeNovaText(query);
    if (t.includes('reporte de prevalidacion') || t.includes('reporte prevalidacion')) return 'reporte_prevalidacion';
    if (t.includes('observaciones') || t.includes('observacion')) return 'observaciones';
    if (t.includes('formulario')) return 'formulario';
    if (['que documentos recibio', 'documentos recibidos', 'adjuntos recibidos', 'soportes recibidos'].some(v => t.includes(v))) return 'documentos_recibidos';
    if (['cual es el nit', 'nit de', 'nit del expediente'].some(v => t.includes(v))) return 'nit';
    if (['siguiente paso', 'que sigue', 'que hago ahora', 'proximo paso'].some(v => t.includes(v))) return 'siguiente_paso';
    if (t.includes('926') || t.includes('bkcargue') || t.includes('archivo 926')) return '926';
    if (t.includes('bloqueantes') || t.includes('bloqueante')) return 'bloqueantes';
    if (['por que fue rechaz', 'porque fue rechaz', 'motivo del rechazo', 'duplicados'].some(v => t.includes(v))) return 'rechazo';
    if (['prevalidacion', 'pre validacion', 'estado del expediente', 'estado operativo', 'aprobado', 'rechazado', 'observado', 'radicacion', 'radicar'].some(v => t.includes(v))) return 'estado';
    if (['quien es el representante', 'representante de', 'representante legal', 'quien firma', 'firma'].some(v => t.includes(v))) return 'representante';
    if (t.includes('nomina') || t.includes('nómina')) return 'nomina';
    if (t.includes('trabajadores') || t.includes('cuantos trabajadores')) return 'trabajadores';
    if (t.includes('sedes') || t.includes('cuantas sedes') || t.includes('centros de trabajo')) return 'sedes';
    if (t.includes('cedula') || t.includes('cédula')) return 'cedula';
    if (t.includes('rut')) return 'rut';
    if (t.includes('camara') || t.includes('cámara')) return 'camara';
    return 'general';
}

function inferNovaSourceIntent(source = {}) {
    const explicit = String(source.intent || '').trim();
    if (explicit) return explicit;
    const type = normalizeNovaText(source.document_type || '');
    const title = normalizeNovaText(source.title || source.titulo || '');
    if (type.includes('rut') || title.includes('rut')) return 'rut';
    if (type.includes('camara') || type.includes('comercio') || title.includes('camara')) return 'camara';
    if (type.includes('cedula') || title.includes('cedula')) return 'cedula';
    if (type.includes('formulario') || type === 'xlsx' || title.endsWith('.xlsx')) return 'formulario';
    if (type.includes('926') || title.includes('bkcargue')) return '926';
    return '';
}

function normalizeNovaSources(items = []) {
    if (!Array.isArray(items)) return [];
    return items.slice(0, 8).map((item) => ({
        title: String(item?.titulo || item?.title || '').trim(),
        source_url: String(item?.source_url || '').trim(),
        document_type: String(item?.document_type || '').trim(),
        intent: inferNovaSourceIntent(item || {}),
    })).filter((item) => item.title || item.source_url);
}

function buildNovaReference() {
    const ctx = readNovaChatContext();
    const proc = readNovaProcessState();
    const visibleTitle = String(document.querySelector('.case-active-card h2, .case-dossier-card h2, h2')?.textContent || '').trim();
    return String(
        visibleTitle
        || ctx.active_company
        || ctx.active_nit
        || ctx.active_document
        || proc.activeCaseId
        || ''
    ).trim();
}

function buildNovaContext(query='') {
    const ctx = readNovaChatContext();
    const proc = readNovaProcessState();
    const reference = buildNovaReference();
    return {
        topics: [],
        operation: 'colima',
        active_case_id: proc.activeCaseId || ctx.active_case_id || ctx.last_case_id || '',
        active_company: reference || ctx.active_company || '',
        active_nit: ctx.active_nit || '',
        active_document: ctx.active_document || '',
        last_case_id: ctx.last_case_id || proc.activeCaseId || '',
        last_query: ctx.last_query || '',
        last_intent: ctx.last_intent || '',
        last_document_title: ctx.last_document_title || '',
        last_document_intent: ctx.last_document_intent || '',
        last_sources: Array.isArray(ctx.last_sources) ? ctx.last_sources.slice(0, 8) : [],
        last_source_index: Number.isFinite(Number(ctx.last_source_index)) ? Number(ctx.last_source_index) : 0,
        ui_view: 'search',
        query,
    };
}

function expandNovaQuery(query='') {
    const text = String(query || '').trim();
    const normalized = normalizeNovaText(text);
    const ctx = readNovaChatContext();
    const reference = buildNovaReference();
    if (!reference) return text;
    const intent = detectNovaIntent(text);
    const sources = Array.isArray(ctx.last_sources) ? ctx.last_sources : [];
    const sourceIndex = Number.isFinite(Number(ctx.last_source_index)) ? Number(ctx.last_source_index) : 0;
    const currentSource = sources[Math.min(sourceIndex, Math.max(sources.length - 1, 0))] || null;
    const nextSource = sources[Math.min(sourceIndex + 1, Math.max(sources.length - 1, 0))] || null;
    const buildFromIntent = (value) => {
        if (value === 'rut') return `rut de ${reference}`;
        if (value === 'camara') return `camara de comercio de ${reference}`;
        if (value === 'cedula') return `cedula de ${reference}`;
        if (value === 'formulario') return `formulario de ${reference}`;
        if (value === '926') return `926 de ${reference}`;
        if (value === 'estado') return `estado del expediente ${reference}`;
        if (value === 'observaciones') return `que observaciones tiene ${reference}`;
        if (value === 'bloqueantes') return `bloqueantes de ${reference}`;
        if (value === 'siguiente_paso') return `siguiente paso de ${reference}`;
        if (value === 'representante') return `quien es el representante de ${reference}`;
        if (value === 'nomina') return `nomina de ${reference}`;
        if (value === 'trabajadores') return `cuantos trabajadores tiene ${reference}`;
        if (value === 'sedes') return `cuantas sedes tiene ${reference}`;
        return '';
    };
    const buildFromSource = (source, fallbackIntent='') => {
        const sourceTitle = String(source?.title || '').trim();
        if (sourceTitle) return `abre el archivo ${sourceTitle} de ${reference}`;
        return buildFromIntent(fallbackIntent);
    };
    if (intent !== 'general') {
        return buildFromIntent(intent) || text;
    }
    if (['abralo', 'ábralo', 'abrelo', 'ábrelo', 'ese documento', 'esa fuente', 'ese archivo'].includes(normalized)) {
        return buildFromSource(currentSource, ctx.last_document_intent || ctx.last_intent || '') || text;
    }
    if (['muestrame el siguiente', 'muéstrame el siguiente', 'el siguiente', 'siguiente', 'abre el siguiente'].includes(normalized)) {
        return buildFromSource(nextSource, nextSource?.intent || currentSource?.intent || ctx.last_document_intent || ctx.last_intent || '') || text;
    }
    if (['y ahora?', 'y ahora', 'ahora que sigue', 'ahora que hago'].includes(normalized)) {
        return `siguiente paso de ${reference}`;
    }
    if (normalized.startsWith('y ')) {
        const remainder = text.slice(2).trim();
        if (remainder) return `${remainder} de ${reference}`;
    }
    return text;
}

/* ============================================================
   RENDERIZADOR DE RESPUESTA ESTRUCTURADA
   Parsea el texto del backend y lo convierte en HTML limpio
   ============================================================ */
function renderNovaResponse(text) {
    const div = document.createElement('div');
    div.className = 'nova-response';

    const lines = text.split('\n');
    let html = '';
    let inList = false;

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i].trim();
        if (!line) {
            if (inList) { html += '</ul>'; inList = false; }
            continue;
        }

        // Titulo de seccion (termina en : y no empieza con -)
        if (line.endsWith(':') && !line.startsWith('-') && line.length < 60) {
            if (inList) { html += '</ul>'; inList = false; }
            const title = line.replace(/:$/, '');
            // Icono segun tipo de seccion
            const icons = {
                'Empresa o independiente identificado': '🏢',
                'Estado operativo': '📋',
                'Adjuntos clasificados': '📁',
                'Documentos disponibles para abrir': '📄',
                'Siguiente paso': '➡️',
                'Respuesta ejecutiva': '✦',
            };
            const icon = icons[title] || '•';
            html += `<div class="nova-section-title"><span class="nova-section-icon">${icon}</span><span>${title}</span></div>`;
            continue;
        }

        // Item de lista (empieza con -)
        if (line.startsWith('- ')) {
            if (!inList) { html += '<ul class="nova-list">'; inList = true; }
            const content = line.substring(2);
            // Detectar pares clave: valor
            const colonIdx = content.indexOf(':');
            if (colonIdx > 0 && colonIdx < 30) {
                const key = content.substring(0, colonIdx).trim();
                const val = content.substring(colonIdx + 1).trim();
                if (val) {
                    // Colorear APROBADA / RECHAZADA
                    let valHtml = val;
                    if (val === 'APROBADA') valHtml = `<span class="nova-badge nova-badge-ok">APROBADA</span>`;
                    if (val === 'RECHAZADA') valHtml = `<span class="nova-badge nova-badge-error">RECHAZADA</span>`;
                    html += `<li><span class="nova-item-key">${key}</span><span class="nova-item-val">${valHtml}</span></li>`;
                } else {
                    html += `<li>${content}</li>`;
                }
            } else {
                html += `<li>${content}</li>`;
            }
            continue;
        }

        // Linea normal
        if (inList) { html += '</ul>'; inList = false; }
        html += `<p class="nova-text-line">${line}</p>`;
    }

    if (inList) html += '</ul>';
    div.innerHTML = html;
    return div;
}


function addCopyButton(msgEl, text) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'nova-copy-btn';
    btn.innerHTML = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg> Copiar';
    btn.title = 'Copiar respuesta';
    btn.addEventListener('click', () => {
        navigator.clipboard.writeText(text).then(() => {
            btn.innerHTML = '✓ Copiado';
            btn.classList.add('nova-copy-ok');
            setTimeout(() => {
                btn.innerHTML = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg> Copiar';
                btn.classList.remove('nova-copy-ok');
            }, 2000);
        });
    });
    msgEl.appendChild(btn);
}

function addNovaMessage(text, role='nova', sources=[]) {
    clearWelcome();
    const msg = document.createElement('div');
    msg.className = `nova-msg nova-msg-${role}`;

    const label = document.createElement('div');
    label.className = 'nova-msg-label';
    label.textContent = role === 'user' ? 'Tu' : 'NOVA';

    const bubble = document.createElement('div');
    bubble.className = 'nova-msg-bubble';

    if (role === 'nova') {
        bubble.appendChild(renderNovaResponse(text));
    } else {
        bubble.textContent = text;
    }

    msg.appendChild(label);
    msg.appendChild(bubble);

    if (role === 'nova' && Array.isArray(sources) && sources.length) {
        const filtered = sources.filter(s => s.source_url).slice(0, 6);
        if (filtered.length) {
            const block = document.createElement('div');
            block.className = 'nova-msg-sources';
            const lbl = document.createElement('div');
            lbl.className = 'nova-sources-label';
            lbl.textContent = 'Documentos';
            block.appendChild(lbl);
            const grid = document.createElement('div');
            grid.className = 'nova-sources-grid';
            filtered.forEach(source => {
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'nova-source-btn';
                const type = source.document_type || 'doc';
                btn.innerHTML = `<span class="nova-source-type">${type}</span><span class="nova-source-name">${source.titulo || 'Archivo'}</span>`;
                btn.addEventListener('click', () => {
                    persistNovaChatContext({
                        last_document_title: source.titulo || 'Archivo',
                        last_document_intent: inferNovaSourceIntent(source),
                        last_sources: normalizeNovaSources(filtered),
                        last_source_index: filtered.findIndex((candidate) => candidate.source_url === source.source_url),
                    });
                    if (window.openDocumentUrlViewer) window.openDocumentUrlViewer(source.source_url, source.titulo || 'archivo');
                    else window.open(source.source_url, '_blank');
                });
                grid.appendChild(btn);
            });
            block.appendChild(grid);
            msg.appendChild(block);
        }
    }

        if (role === 'nova') addCopyButton(msg, text);
    novaChatContainer.appendChild(msg);
    novaChatContainer.scrollTop = novaChatContainer.scrollHeight;
}

async function sendNovaMessage() {
    const text = novaInput.value.trim();
    if (!text || novaSearching) return;
    const normalizedText = normalizeNovaText(text);
    const storedContext = readNovaChatContext();
    const storedSources = Array.isArray(storedContext.last_sources) ? storedContext.last_sources : [];
    const storedSourceIndex = Number.isFinite(Number(storedContext.last_source_index)) ? Number(storedContext.last_source_index) : 0;
    const currentSource = storedSources[Math.min(storedSourceIndex, Math.max(storedSources.length - 1, 0))] || null;
    const nextIndex = Math.min(storedSourceIndex + 1, Math.max(storedSources.length - 1, 0));
    const nextSource = storedSources[nextIndex] || null;

    const intent = detectNovaIntent(text);
    const effectiveText = expandNovaQuery(text);
    const context = buildNovaContext(text);
    novaInput.value = '';
    autoResizeNovaInput();
    addNovaMessage(text, 'user');

    const openSourceDirectly = (source, sourceIndex) => {
        if (!source?.source_url) return false;
        persistNovaChatContext({
            last_query: text,
            last_intent: intent,
            last_document_title: source.title || storedContext.last_document_title || '',
            last_document_intent: source.intent || storedContext.last_document_intent || '',
            last_sources: storedSources,
            last_source_index: sourceIndex,
        });
        if (window.openDocumentUrlViewer) window.openDocumentUrlViewer(source.source_url, source.title || 'archivo');
        else window.open(source.source_url, '_blank');
        addNovaMessage(`Abrí el archivo ${source.title || 'seleccionado'} del contrato activo.`, 'nova', [source]);
        return true;
    };

    if (NOVA_OPEN_CURRENT_TERMS.has(normalizedText) && openSourceDirectly(currentSource, storedSourceIndex)) {
        return;
    }
    if (NOVA_OPEN_NEXT_TERMS.has(normalizedText) && openSourceDirectly(nextSource, nextIndex)) {
        return;
    }

    novaSearching = true;
    novaSendBtn.disabled = true;
    novaActivity.classList.remove('hidden');
    persistNovaChatContext({ last_query: text, last_intent: intent });
    try {
        const res = await fetch(`${API_URL}/api/afiliacion/consultar`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({consulta: effectiveText, contexto: context})
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        const normalizedSources = normalizeNovaSources(data.fuentes || []);
        const firstSource = normalizedSources[0] || null;
        persistNovaChatContext({
            last_query: text,
            last_intent: intent,
            last_case_id: readNovaChatContext().last_case_id || context.active_case_id || '',
            last_document_title: firstSource?.title || readNovaChatContext().last_document_title || '',
            last_document_intent: firstSource?.intent || readNovaChatContext().last_document_intent || '',
            last_sources: normalizedSources,
            last_source_index: 0,
        });
        addNovaMessage(data.respuesta || 'Sin respuesta.', 'nova', data.fuentes || []);
    } catch(e) {
        console.error('NOVA:', e);
        addNovaMessage('No pude conectarme con el backend.', 'nova');
    } finally {
        novaSearching = false;
        novaSendBtn.disabled = false;
        novaActivity.classList.add('hidden');
        novaInput.focus();
    }
}

function autoResizeNovaInput() {
    if (!novaInput) return;
    novaInput.style.height = 'auto';
    novaInput.style.height = Math.min(novaInput.scrollHeight, 100) + 'px';
}

document.addEventListener('keydown', e => {
    if (e.altKey && e.key === 'n') { e.preventDefault(); toggleNova(); }
    if (e.key === 'Escape' && novaOpen && !novaMinimized) {
        const m = document.getElementById('documentModal');
        if (m && !m.classList.contains('hidden')) return;
        minimizeNova();
    }
});

novaToggleBtn?.addEventListener('click', toggleNova);
novaMinimizeBtn?.addEventListener('click', minimizeNova);
novaCloseBtn?.addEventListener('click', closeNova);
novaMinimizedTab?.addEventListener('click', openNova);
novaSendBtn?.addEventListener('click', sendNovaMessage);
novaInput?.addEventListener('keydown', e => { if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendNovaMessage();} });
novaInput?.addEventListener('input', autoResizeNovaInput);

console.log('NOVA Panel listo — Alt+N para abrir/cerrar');
