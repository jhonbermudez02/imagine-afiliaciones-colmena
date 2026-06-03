const path = require('node:path');
const { createRequire } = require('node:module');

const projectRoot = path.resolve(__dirname, '..');
const requireFromFrontend = createRequire(path.join(projectRoot, 'frontend-nova', 'package.json'));
const { chromium } = requireFromFrontend('playwright');

const baseUrl = process.env.AFILEGA_BASE_URL || 'http://127.0.0.1:8140/';
const apiUrl = process.env.AFILEGA_API_URL || 'http://127.0.0.1:8141';
const PROFILE_KEY = 'afilega-fa-ima-la-v2-profile-v1';
const TESTER_KEY = 'afilega-fa-ima-la-v2-tester-v1';
const DIGITACION_DRAFT_KEY = 'afilega-fa-ima-la-v2-digitacion-draft-v1';

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function latestCase(entryType) {
  const response = await fetch(`${apiUrl}/api/cases?operation=colima`);
  assert(response.ok, `No pude listar casos: HTTP ${response.status}`);
  const payload = await response.json();
  const cases = Array.isArray(payload?.cases) ? payload.cases : [];
  const found = cases.find(item => item.entry_type === entryType && (item.files || []).length > 10);
  assert(found?.id, `No encontre caso ${entryType} con evidencia documental`);
  return found;
}

(async () => {
  const contractorCase = await latestCase('contratista');
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1500, height: 980 } });
  const page = await context.newPage();

  await page.goto(baseUrl, { waitUntil: 'networkidle', timeout: 30000 });
  await page.evaluate(({ PROFILE_KEY, TESTER_KEY, DIGITACION_DRAFT_KEY, contractorCase }) => {
    localStorage.setItem(PROFILE_KEY, 'imagine');
    localStorage.setItem(TESTER_KEY, JSON.stringify({ name: 'RPA Digitacion Evidencia', email: 'rpa.digitacion.evidencia@afilega.test' }));
    localStorage.setItem(DIGITACION_DRAFT_KEY, JSON.stringify({
      proyecto: 'AFILEGA_FA_IMA_LA_V2',
      formato: 'digitacion_contratista',
      source_case_id: contractorCase.id,
      source_entry_type: 'contratista',
      source_label: contractorCase.label || 'Caso real contratista',
      prefill_sources: {
        afp: { source: 'certificacion AFP/OCR', confidence: 0.84 },
        documento_afiliado: { source: 'OCR/documento de identidad', confidence: 0.78 }
      },
      values: {
        tipo_tramite: 'afiliacion',
        tipo_afiliacion: 'Independiente - Empresa no afiliada',
        nit: '1073157358',
        tipo_documento_afiliado: 'CC',
        documento_afiliado: '1073157358',
        afp: 'COLFONDOS'
      }
    }));
  }, { PROFILE_KEY, TESTER_KEY, DIGITACION_DRAFT_KEY, contractorCase });

  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForSelector('#appShell:not(.hidden)', { timeout: 15000 });
  await page.click('.nav-item[data-view="digitacion"]');
  await page.waitForSelector('#view-digitacion.active', { timeout: 10000 });

  await page.focus('#digAfp');
  try {
    await page.waitForFunction(() => {
      const frame = document.querySelector('#digitacionDocumentStage iframe')?.getAttribute('src') || '';
      const activeInput = document.querySelector('#digitacionActiveInput');
      const select = document.querySelector('#digitacionDocSelect');
      return frame.includes('CONTRATRISTA__') && activeInput && select?.options?.length > 10;
    }, null, { timeout: 15000 });
  } catch (err) {
    const debug = await page.evaluate(() => ({
      title: document.querySelector('#digitacionEvidenceTitle')?.textContent || '',
      sub: document.querySelector('#digitacionEvidenceSub')?.textContent || '',
      frame: document.querySelector('#digitacionDocumentStage iframe')?.getAttribute('src') || '',
      stage: document.querySelector('#digitacionDocumentStage')?.textContent?.slice(0, 300) || '',
      chips: Array.from(document.querySelectorAll('#digitacionDocList .digitacion-doc-chip')).slice(0, 8).map(btn => btn.textContent),
      activeInput: document.querySelector('#digitacionActiveInput')?.value || '',
      selectCount: document.querySelector('#digitacionDocSelect')?.options?.length || 0,
      focused: document.activeElement?.id || '',
    }));
    throw new Error(`${err.message} debug=${JSON.stringify(debug)}`);
  }

  await page.fill('#digitacionActiveInput', 'COLFONDOS TEST');
  await page.waitForFunction(() => document.querySelector('#digAfp')?.value === 'COLFONDOS TEST', null, { timeout: 5000 });
  await page.selectOption('#digitacionDocSelect', 'CONTRATRISTA__p001.pdf');
  await page.waitForFunction(() => {
    const frame = document.querySelector('#digitacionDocumentStage iframe')?.getAttribute('src') || '';
    return frame.includes('CONTRATRISTA__p001.pdf');
  }, null, { timeout: 10000 });

  const state = await page.evaluate(() => ({
    title: document.querySelector('#digitacionEvidenceTitle')?.textContent || '',
    sub: document.querySelector('#digitacionEvidenceSub')?.textContent || '',
    frame: document.querySelector('#digitacionDocumentStage iframe')?.getAttribute('src') || '',
    ocr: document.querySelector('#digitacionOcrText')?.textContent || '',
    activeValue: document.querySelector('#digitacionActiveInput')?.value || '',
    originalValue: document.querySelector('#digAfp')?.value || '',
    selectedDoc: document.querySelector('#digitacionDocSelect')?.value || '',
    selectCount: document.querySelector('#digitacionDocSelect')?.options?.length || 0,
    chipCount: document.querySelectorAll('#digitacionDocList .digitacion-doc-chip').length,
    activeRows: document.querySelectorAll('.field-row.digitacion-field-active').length,
  }));
  assert(state.title.includes('AFP'), `Titulo de evidencia inesperado: ${state.title}`);
  assert(state.originalValue === 'COLFONDOS TEST', `Campo activo no sincronizo original: ${state.originalValue}`);
  assert(state.frame.includes('CONTRATRISTA__p001.pdf'), `Selector de imagen no cambio el visor: ${state.frame}`);
  assert(state.selectedDoc === 'CONTRATRISTA__p001.pdf', `Selector no quedo en p001: ${state.selectedDoc}`);
  assert(state.selectCount > 10, 'El menu de imagenes no cargo el paquete completo');
  assert(state.chipCount > 0, 'No renderizo lista de documentos');
  assert(state.activeRows === 1, `Filas activas inesperadas: ${state.activeRows}`);

  await page.screenshot({ path: '/tmp/afilega_digitacion_evidence_rpa.png', fullPage: true });
  await browser.close();
  console.log(JSON.stringify({ ok: true, state, screenshot: '/tmp/afilega_digitacion_evidence_rpa.png' }, null, 2));
})().catch(async err => {
  let debug = {};
  try {
    const pages = await chromium._debugPages?.();
    void pages;
  } catch {}
  console.error(JSON.stringify({ ok: false, error: err.message, stack: err.stack, debug }, null, 2));
  process.exit(1);
});
