const path = require('node:path');
const { createRequire } = require('node:module');

const projectRoot = path.resolve(__dirname, '..');
const requireFromFrontend = createRequire(path.join(projectRoot, 'frontend-nova', 'package.json'));
const { chromium } = requireFromFrontend('playwright');

const baseUrl = process.env.AFILEGA_BASE_URL || 'http://127.0.0.1:8140/';
const apiUrl = process.env.AFILEGA_API_URL || 'http://127.0.0.1:8141';
const PROFILE_KEY = 'afilega-fa-ima-la-v2-profile-v1';
const TESTER_KEY = 'afilega-fa-ima-la-v2-tester-v1';
const fixtureDir = process.env.AFILEGA_RPA_FIXTURE_DIR || path.join(projectRoot, 'shared_downloads', 'rpa');

const samples = {
  empresa: [
    path.join(fixtureDir, 'EMPRESA.pdf'),
  ],
  contratista: [
    path.join(fixtureDir, 'CONTRATISTA.pdf'),
  ],
};

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function waitForCase(caseId, timeoutMs = 180000) {
  const started = Date.now();
  let latest = null;
  while (Date.now() - started < timeoutMs) {
    const response = await fetch(`${apiUrl}/api/cases/${caseId}`);
    latest = await response.json();
    const status = String(latest?.analysis?.workflow_run?.status || latest?.status || '');
    if (['completed', 'stopped_prevalidacion', 'failed', 'analyzed'].includes(status)) return latest;
    await new Promise(resolve => setTimeout(resolve, 2000));
  }
  throw new Error(`Timeout esperando analisis del caso ${caseId}. Ultimo estado: ${latest?.status || 'n/d'}`);
}

async function runEntry(page, entryType, files) {
  await page.click('.nav-item[data-view="flujo"]');
  await page.waitForSelector('#view-flujo.active', { timeout: 10000 });
  await page.click(`[data-entry-type="${entryType}"]`);
  const activeType = await page.locator('[data-entry-type].active').getAttribute('data-entry-type');
  assert(activeType === entryType, `No quedo activo entry_type=${entryType}`);

  await page.setInputFiles('#packageFilesInput', files);
  await page.waitForSelector('#uploadSelected:not([style*="none"])', { timeout: 10000 });
  const selectedCount = await page.locator('#uploadFilesList .upload-file-item').count();
  assert(selectedCount === files.length, `Seleccionados ${selectedCount}, esperados ${files.length}`);

  const uploadResponsePromise = page.waitForResponse(response => {
    return response.request().method() === 'POST'
      && response.url().includes('/api/cases')
      && !response.url().includes('/run-workflow');
  }, { timeout: 30000 });
  await page.click('#runWorkflowBtn');
  const uploadResponse = await uploadResponsePromise;
  const uploadPayload = await uploadResponse.json();
  const caseId = uploadPayload.id || uploadPayload.case_id;
  assert(caseId, `Upload sin caseId para ${entryType}`);
  assert(uploadPayload.entry_type === entryType, `Backend devolvio ${uploadPayload.entry_type}, esperado ${entryType}`);

  const finalPayload = await waitForCase(caseId);
  const prefill = finalPayload?.analysis?.digitacion_prefill || {};
  assert(prefill.entry_type === entryType, `Prefill sin entry_type correcto para ${caseId}`);
  assert(Object.keys(prefill.values || {}).length >= 2, `Prefill muy pobre para ${caseId}`);
  assert((finalPayload.files || []).length >= files.length, `No guardo archivos esperados en ${caseId}`);
  return {
    entryType,
    caseId,
    status: finalPayload?.analysis?.workflow_run?.status || finalPayload.status,
    files: (finalPayload.files || []).length,
    prefillCount: Object.keys(prefill.values || {}).length,
    prefillValues: prefill.values || {},
  };
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true });
  const page = await context.newPage();
  const results = [];

  await page.goto(baseUrl, { waitUntil: 'networkidle', timeout: 30000 });
  await page.evaluate(({ PROFILE_KEY, TESTER_KEY }) => {
    localStorage.setItem(PROFILE_KEY, 'imagine');
    localStorage.setItem(TESTER_KEY, JSON.stringify({ name: 'RPA Bandeja', email: 'rpa.bandeja@afilega.test' }));
  }, { PROFILE_KEY, TESTER_KEY });
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForSelector('#appShell:not(.hidden)', { timeout: 15000 });

  results.push(await runEntry(page, 'empresa', samples.empresa));
  results.push(await runEntry(page, 'contratista', samples.contratista));

  await page.screenshot({ path: '/tmp/afilega_bandeja_rpa.png', fullPage: true });
  await browser.close();
  console.log(JSON.stringify({ ok: true, results, screenshot: '/tmp/afilega_bandeja_rpa.png' }, null, 2));
})().catch(async err => {
  console.error(JSON.stringify({ ok: false, error: err.message, stack: err.stack }, null, 2));
  process.exit(1);
});
