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

async function latestCase() {
  const response = await fetch(`${apiUrl}/api/cases?operation=colima`);
  assert(response.ok, `No pude listar casos: HTTP ${response.status}`);
  const payload = await response.json();
  const cases = Array.isArray(payload?.cases) ? payload.cases : [];
  const found = cases.find(item => item.entry_type === 'empresa' && (item.files || []).length > 10) || cases[0];
  assert(found?.id, 'No encontre caso disponible para digitacion');
  return found;
}

(async () => {
  const sourceCase = await latestCase();
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1500, height: 980 } });
  const page = await context.newPage();

  await page.goto(baseUrl, { waitUntil: 'networkidle', timeout: 30000 });
  await page.evaluate(({ PROFILE_KEY, TESTER_KEY, DIGITACION_DRAFT_KEY, sourceCase }) => {
    localStorage.setItem(PROFILE_KEY, 'imagine');
    localStorage.setItem(TESTER_KEY, JSON.stringify({ name: 'RPA Catalogos Digitacion', email: 'rpa.catalogos@afilega.test' }));
    localStorage.setItem(DIGITACION_DRAFT_KEY, JSON.stringify({
      proyecto: 'AFILEGA_FA_IMA_LA_V2',
      formato: 'digitacion_empresa',
      source_case_id: sourceCase.id,
      source_entry_type: sourceCase.entry_type || 'empresa',
      source_label: sourceCase.label || 'Caso real empresa',
      values: {
        numero_radicacion: 'IMG202630',
        fecha_radicacion: '2026-05-11',
        fecha_inicio_cobertura: '2026-05-12',
        fecha_recibido_imagine: '2026-05-12',
        empleador_tipo_documento: 'NIT',
        nit: '830119224',
        razon_social: 'VIRMA Y CIA SAS',
        sucursal: 'Dirección General',
        tipo_tramite: 'afiliacion',
        tipo_afiliacion: 'Primera vez',
        tipo_novedad: '00',
        subtipo_cotizante: '999'
      }
    }));
  }, { PROFILE_KEY, TESTER_KEY, DIGITACION_DRAFT_KEY, sourceCase });

  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForSelector('#appShell:not(.hidden)', { timeout: 15000 });
  await page.click('.nav-item[data-view="flujo"]');
  await page.waitForSelector('#view-flujo.active', { timeout: 10000 });

  const flowState = await page.evaluate(() => ({
    visibleFields: Array.from(document.querySelectorAll('.radicacion-field'))
      .filter(element => element.offsetParent !== null && !element.disabled && element.id)
      .map(element => element.dataset.radKey || ''),
    buttonLabel: document.querySelector('#runWorkflowBtn')?.textContent?.trim() || '',
    docTypeLabels: Array.from(document.querySelector('#flowEmpleadorTipoDocumento')?.options || []).map(option => option.textContent.trim()),
  }));
  assert(flowState.visibleFields.length === 8, `Nuevo contrato debe tener 8 campos de radicacion visibles: ${JSON.stringify(flowState.visibleFields)}`);
  for (const key of ['numero_radicacion', 'tipo_afiliacion', 'fecha_radicacion', 'fecha_recibido_imagine', 'empleador_tipo_documento', 'nit', 'razon_social', 'sucursal']) {
    assert(flowState.visibleFields.includes(key), `Nuevo contrato no muestra radicacion ${key}`);
  }
  assert(flowState.buttonLabel === 'Radicar y ejecutar prevalidación', `Boton de nuevo contrato inesperado: ${flowState.buttonLabel}`);
  assert(flowState.docTypeLabels.includes('NIT'), 'Tipo documento de radicacion no muestra NIT');
  assert(!flowState.docTypeLabels.some(label => label.includes('NI · NIT')), 'Tipo documento de radicacion aun muestra NI · NIT');

  await page.fill('#flowNumeroRadicacion', 'IMG202630');
  await page.selectOption('#flowTipoAfiliacion', 'Traslado');
  assert(await page.$eval('#flowTipoAfiliacion', el => el.value) === 'Traslado', 'Clase afiliacion de nuevo contrato no permite seleccionar');
  await page.selectOption('#flowTipoAfiliacion', 'Primera vez');
  await page.fill('#flowFechaRadicacion', '2026-05-12');
  await page.fill('#flowFechaRecibidoImagine', '2026-05-12');
  await page.selectOption('#flowEmpleadorTipoDocumento', 'NIT');
  await page.fill('#flowNit', '830119224');
  await page.fill('#flowRazonSocial', 'VIRMA Y CIA SAS');
  await page.selectOption('#flowSucursal', 'Cali');
  assert(await page.$eval('#flowSucursal', el => el.value) === 'Cali', 'Sucursal de nuevo contrato no permite seleccionar');

  await page.click('.nav-item[data-view="digitacion"]');
  await page.waitForSelector('#view-digitacion.active', { timeout: 10000 });

  const uiState = await page.evaluate(() => {
    const field = key => document.querySelector(`.digitacion-field[data-dig-key="${key}"]`);
    const rowRequired = key => field(key)?.closest('.field-row')?.classList.contains('field-required') || false;
    const label = selector => document.querySelector(selector)?.textContent?.trim() || '';
    const optionValues = selector => Array.from(document.querySelector(selector)?.options || []).map(option => option.value);
    return {
      tabs: Array.from(document.querySelectorAll('[data-digitacion-tab]')).map(tab => ({
        key: tab.dataset.digitacionTab || '',
        label: tab.textContent.trim(),
        active: tab.classList.contains('active'),
      })),
      panels: Array.from(document.querySelectorAll('[data-digitacion-panel]')).map(panel => ({
        key: panel.dataset.digitacionPanel || '',
        active: panel.classList.contains('active'),
      })),
      epsList: field('eps')?.getAttribute('list') || '',
      afpList: field('afp')?.getAttribute('list') || '',
      cargoList: field('cargo_actividad')?.getAttribute('list') || '',
      actividadList: field('codigo_actividad_economica')?.getAttribute('list') || '',
      camaraActividadList: field('camara_codigo_actividad')?.getAttribute('list') || '',
      sedeActividadList: field('sede_codigo_actividad')?.getAttribute('list') || '',
      epsOptions: document.querySelector('#epsCatalogOptions')?.options?.length || 0,
      afpOptions: document.querySelector('#afpCatalogOptions')?.options?.length || 0,
      epsValues: optionValues('#epsCatalogOptions').slice(0, 160),
      afpValues: optionValues('#afpCatalogOptions').slice(0, 40),
      cargoOptions: document.querySelector('#cargoCatalogOptions')?.options?.length || 0,
      actividadOptions: document.querySelector('#actividadEconomicaOptions')?.options?.length || 0,
      camaraOptions: document.querySelector('#camaraActividadOptions')?.options?.length || 0,
      generoTag: field('genero')?.tagName || '',
      generoOptions: optionValues('#digGenero'),
      afiTipoTag: field('tipo_cotizante')?.tagName || '',
      afiTipoOptions: optionValues('#digTipoCotizante'),
      vinculadorTag: field('empresa_vinculador_laboral')?.tagName || '',
      vinculadorOptions: optionValues('#digEmpresaVinculador'),
      salarioLabel: label('label[for="digIbc"]'),
      afiTipoLabel: label('label[for="digTipoCotizante"]'),
      required: {
        genero: rowRequired('genero') && field('genero')?.required,
        eps: rowRequired('eps') && field('eps')?.required,
        afp: rowRequired('afp') && field('afp')?.required,
        ibc: rowRequired('ibc') && field('ibc')?.required,
        cargo: rowRequired('cargo_actividad') && field('cargo_actividad')?.required,
        afiTipo: rowRequired('tipo_cotizante') && field('tipo_cotizante')?.required,
        actividad: rowRequired('codigo_actividad_economica') && field('codigo_actividad_economica')?.required,
      },
    };
  });

  assert(uiState.tabs.map(tab => tab.key).slice(0, 3).join('|') === 'afiliacion|sedes|novedades', `Orden de tabs inesperado: ${JSON.stringify(uiState.tabs)}`);
  assert(uiState.tabs.find(tab => tab.key === 'afiliacion')?.active, 'Afiliación debe iniciar activa en Digitación');
  assert(uiState.tabs.find(tab => tab.key === 'novedades')?.label === 'Trabajadores', `La pestaña Novedades debe verse como Trabajadores: ${JSON.stringify(uiState.tabs)}`);
  assert(uiState.panels.find(panel => panel.key === 'afiliacion')?.active, 'Panel Afiliación debe iniciar activo');
  assert(uiState.epsList === 'epsCatalogOptions', 'EPS no quedo conectado al catalogo');
  assert(uiState.afpList === 'afpCatalogOptions', 'AFP no quedo conectado al catalogo');
  assert(uiState.cargoList === 'cargoCatalogOptions', 'Cargo no quedo conectado al catalogo');
  assert(uiState.actividadList === 'actividadEconomicaOptions', 'Actividad empresa no quedo conectada al catalogo');
  assert(uiState.camaraActividadList === 'camaraActividadOptions', 'Actividad camara no quedo conectada a su tabla de Camara de Comercio');
  assert(uiState.sedeActividadList === 'actividadEconomicaOptions', 'Actividad sede no quedo conectada al catalogo');
  assert(uiState.epsOptions > 50, `Catalogo EPS pobre: ${uiState.epsOptions}`);
  assert(uiState.afpOptions > 5, `Catalogo AFP pobre: ${uiState.afpOptions}`);
  assert(uiState.epsValues.includes('FAMISANAR'), 'Catalogo EPS no cargo la tabla adjunta: falta FAMISANAR');
  assert(uiState.afpValues.includes('PORVENIR'), 'Catalogo AFP no cargo la tabla adjunta: falta PORVENIR');
  assert(uiState.cargoOptions > 100, `Catalogo cargo pobre: ${uiState.cargoOptions}`);
  assert(uiState.actividadOptions > 100, `Catalogo actividad economica pobre: ${uiState.actividadOptions}`);
  assert(uiState.camaraOptions > 100, `Catalogo actividad Camara de Comercio pobre: ${uiState.camaraOptions}`);
  assert(uiState.generoTag === 'SELECT', 'Genero no es select');
  assert(['F', 'M', 'T', 'NB', 'O'].every(value => uiState.generoOptions.includes(value)), 'Genero no tiene todas las opciones esperadas');
  assert(uiState.afiTipoTag === 'SELECT', 'Afi tipo no es select');
  assert(['1', '19'].every(value => uiState.afiTipoOptions.includes(value)), 'Afi tipo no tiene codigos esperados');
  assert(uiState.vinculadorTag === 'SELECT', 'Vinculador laboral no es select');
  assert(['1', '2', '10'].every(value => uiState.vinculadorOptions.includes(value)), 'Vinculador laboral no tiene codigos esperados');
  assert(uiState.salarioLabel === 'Salario / IBC', `Etiqueta salario inesperada: ${uiState.salarioLabel}`);
  assert(uiState.afiTipoLabel === 'Afi tipo', `Etiqueta afi tipo inesperada: ${uiState.afiTipoLabel}`);
  for (const [key, ok] of Object.entries(uiState.required)) {
    assert(ok, `${key} no quedo marcado como obligatorio`);
  }

  const radicacionInitialState = await page.evaluate(() => ({
    visiblePanel: Boolean(document.querySelector('[data-digitacion-panel="radicacion"]')),
    visibleTab: Boolean(document.querySelector('[data-digitacion-tab="radicacion"]')),
    visibleFields: Array.from(document.querySelectorAll('.digitacion-field[data-dig-key="numero_radicacion"], .digitacion-field[data-dig-key="tipo_afiliacion"], .digitacion-field[data-dig-key="fecha_radicacion"], .digitacion-field[data-dig-key="fecha_recibido_imagine"], .digitacion-field[data-dig-key="empleador_tipo_documento"], .digitacion-field[data-dig-key="nit"], .digitacion-field[data-dig-key="razon_social"], .digitacion-field[data-dig-key="sucursal"]'))
      .filter(element => element.offsetParent !== null && !element.disabled && element.id)
      .map(element => element.dataset.digKey || ''),
    tipoTramite: document.querySelector('#digTipoTramite')?.value || '',
    tipoTramiteType: document.querySelector('#digTipoTramite')?.getAttribute('type') || '',
    coberturaType: document.querySelector('#digFechaCobertura')?.getAttribute('type') || '',
    novedadLabel: document.querySelector('[data-digitacion-panel="novedades"] .digitacion-block-title')?.textContent?.trim() || '',
    tipoNovedadValue: document.querySelector('#digTipoNovedad')?.value || '',
    tipoNovedadType: document.querySelector('#digTipoNovedad')?.getAttribute('type') || '',
  }));
  assert(!radicacionInitialState.visiblePanel && !radicacionInitialState.visibleTab, 'Radicación no debe aparecer como pestaña de Digitación');
  assert(radicacionInitialState.visibleFields.length === 0, `Radicación no debe tener campos visibles en Digitación: ${JSON.stringify(radicacionInitialState.visibleFields)}`);
  assert(radicacionInitialState.tipoTramite === 'afiliacion' && radicacionInitialState.tipoTramiteType === 'hidden', 'Tipo trámite debe quedar interno como afiliación');
  assert(radicacionInitialState.coberturaType === 'hidden', 'Fecha inicio cobertura debe quedar interna y calculada');
  assert(radicacionInitialState.novedadLabel === 'Ingreso de trabajadores', `Titulo de trabajadores inesperado: ${radicacionInitialState.novedadLabel}`);
  assert(radicacionInitialState.tipoNovedadValue === '00' && radicacionInitialState.tipoNovedadType === 'hidden', 'Tipo novedad debe quedar oculto y fijo como ingreso 00');

  const dateState = await page.evaluate(() => ({
    radicacion: document.querySelector('#digFechaRadicacion')?.value || '',
    cobertura: document.querySelector('#digFechaCobertura')?.value || '',
    recibido: document.querySelector('#digFechaRecibidoImagine')?.value || '',
  }));
  assert(dateState.radicacion === '2026-05-11', 'Fecha radicacion no se conserva desde la radicacion');
  assert(dateState.cobertura === '2026-05-12', 'Fecha inicio cobertura no se conserva/calcula automaticamente');
  assert(dateState.recibido === '2026-05-12', 'Fecha recibido Imagine no permite digitar');

  const docTypeState = await page.evaluate(() => ({
    value: document.querySelector('#digEmpleadorTipoDocumento')?.value || '',
    visible: Boolean(document.querySelector('#digEmpleadorTipoDocumento')?.offsetParent),
    extensionFields: document.querySelectorAll('.digitacion-field[data-dig-key*="extension"]').length,
    numeroRadicacionVisible: Boolean(document.querySelector('.digitacion-field[data-dig-key="numero_radicacion"]')?.offsetParent),
    riesgoExists: Boolean(document.querySelector('#digClaseRiesgoEmpresa')),
    riesgoRequired: Boolean(document.querySelector('#digClaseRiesgoEmpresa')?.required),
  }));
  assert(docTypeState.value === 'NIT', `Tipo documento empleador debe iniciar en NIT, actual ${docTypeState.value}`);
  assert(!docTypeState.visible, 'Tipo documento de radicacion no debe verse en Digitación');
  assert(docTypeState.extensionFields === 0, `Aun hay campos extension visibles en digitacion: ${docTypeState.extensionFields}`);
  assert(!docTypeState.numeroRadicacionVisible, 'Consecutivo Radicación no debe verse en Digitación');
  assert(docTypeState.riesgoExists, 'Riesgo no esta creado en digitación');
  assert(docTypeState.riesgoRequired, 'Riesgo debe estar marcado como obligatorio');

  await page.fill('#digActividadEconomica', '1131202');
  await page.waitForTimeout(150);
  const riskState = await page.evaluate(() => ({
    activity: document.querySelector('#digActividadEconomica')?.value || '',
    risk: document.querySelector('#digClaseRiesgoEmpresa')?.value || '',
  }));
  assert(riskState.risk === '1', `Riesgo empresa no se lleno desde actividad economica: ${JSON.stringify(riskState)}`);

  await page.fill('#digCamaraCodigoActividad', '0111');
  await page.waitForTimeout(150);
  const camaraActivityState = await page.evaluate(() => ({
    code: document.querySelector('#digCamaraCodigoActividad')?.value || '',
    activity: document.querySelector('#digCamaraActividadPrincipal')?.value || '',
  }));
  assert(camaraActivityState.activity.length > 20, `Actividad principal Camara no se lleno desde tabla: ${JSON.stringify(camaraActivityState)}`);

  const locationState = await page.evaluate(() => {
    const normalize = value => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase();
    const dept = document.querySelector('#digDepartamentoEmpresa');
    const city = document.querySelector('#digCiudadEmpresa');
    dept.value = '';
    dept.dispatchEvent(new Event('change', { bubbles: true }));
    const medellin = Array.from(city.options || []).find(option => normalize(option.value) === 'MEDELLIN');
    if (medellin) {
      city.value = medellin.value;
      city.dispatchEvent(new Event('change', { bubbles: true }));
    }
    return {
      foundMedellin: Boolean(medellin),
      departamento: dept.value,
      municipio: city.value,
    };
  });
  assert(locationState.foundMedellin, 'Municipio Medellin no aparece sin seleccionar departamento');
  assert(locationState.departamento === 'ANTIOQUIA', `Medellin no infiere Antioquia: ${JSON.stringify(locationState)}`);

  await page.click('[data-digitacion-tab="sedes"]');
  await page.waitForSelector('[data-digitacion-panel="sedes"].active', { timeout: 5000 });
  await page.fill('#digSedeActividad', '1131202');
  await page.waitForTimeout(150);
  const sedeRiskState = await page.evaluate(() => ({
    activity: document.querySelector('#digSedeActividad')?.value || '',
    risk: document.querySelector('#digSedeRiesgo')?.value || '',
  }));
  assert(sedeRiskState.risk === '1', `Riesgo sede no se lleno desde actividad economica: ${JSON.stringify(sedeRiskState)}`);
  await page.click('[data-digitacion-tab="afiliacion"]');
  await page.waitForSelector('[data-digitacion-panel="afiliacion"].active', { timeout: 5000 });

  const sampleValueFor = meta => {
    const key = meta.key || '';
    const type = String(meta.type || '').toLowerCase();
    if (type === 'date') return key.includes('fin') ? '2026-05-20' : '2026-05-12';
    if (type === 'email' || key.includes('correo')) return 'prueba@imagine.test';
    if (type === 'number') return key.includes('ibc') || key.includes('valor') ? '2000000' : '1';
    if (key.includes('codigo_actividad')) return '1131202';
    if (key === 'eps') return 'FAMISANAR';
    if (key === 'afp') return 'PORVENIR';
    if (key === 'cargo_actividad' || key.includes('cargo')) return 'GERENTE';
    if (key === 'genero') return 'F';
    if (key === 'tipo_cotizante') return '1';
    if (key === 'subtipo_cotizante') return '999';
    if (key.includes('telefono')) return '6012345';
    if (key.includes('celular')) return '3001234567';
    if (key.includes('extension')) return '123';
    if (key.includes('nit') || key.includes('documento') || key.includes('numero') || key.includes('codigo') || key.includes('dias') || key.includes('clase') || key.includes('grado') || key.includes('estado') || key.includes('tipo_localizacion') || key.includes('grupo') || key.includes('regimen') || key.includes('tamano') || key.includes('forma_pago') || key.includes('vinculador')) {
      return meta.maxLength && Number(meta.maxLength) <= 1 ? '1' : '1234567';
    }
    if (key.includes('zona')) return 'U';
    if (key.includes('pyme') || key.includes('olcsa') || key.includes('contratante') || key.includes('transporte') || key.includes('traslado') || key.includes('autoliquidacion')) return 'S';
    if (key.includes('direccion')) return 'CALLE 1 2 3';
    if (key.includes('observaciones') || meta.tag === 'TEXTAREA') return 'PRUEBA RPA';
    return 'PRUEBA';
  };

  const fieldFailures = [];
  const fieldStats = {};
  for (const panel of ['afiliacion', 'sedes', 'novedades']) {
    await page.click(`[data-digitacion-tab="${panel}"]`);
    await page.waitForSelector(`[data-digitacion-panel="${panel}"].active`, { timeout: 5000 });
    const fields = await page.$$eval(`[data-digitacion-panel="${panel}"] .digitacion-field`, elements => (
      elements
        .filter(element => element.offsetParent !== null && !element.disabled && element.id)
        .map(element => ({
          id: element.id,
          key: element.dataset.digKey || '',
          tag: element.tagName,
          type: element.getAttribute('type') || '',
          list: element.getAttribute('list') || '',
          maxLength: element.getAttribute('maxlength') || '',
          options: element.tagName === 'SELECT'
            ? Array.from(element.options || []).map(option => option.value).filter(Boolean)
            : [],
        }))
    ));
    fieldStats[panel] = fields.length;
    for (const meta of fields) {
      const selector = `#${meta.id}`;
      try {
        await page.locator(selector).click({ timeout: 4000 });
        await page.waitForTimeout(60);
        const activeId = await page.evaluate(() => document.activeElement?.id || '');
        if (activeId !== meta.id) {
          fieldFailures.push({ panel, key: meta.key, id: meta.id, problem: `perdio foco hacia ${activeId || 'ninguno'}` });
          continue;
        }
        if (meta.tag === 'SELECT') {
          const value = await page.$eval(selector, element => (
            Array.from(element.options || []).map(option => option.value).filter(Boolean)[0] || ''
          ));
          if (value) {
            await page.selectOption(selector, value);
            const actual = await page.$eval(selector, element => element.value);
            if (actual !== value) fieldFailures.push({ panel, key: meta.key, id: meta.id, problem: `select no aplico ${value}; actual ${actual}` });
          }
          continue;
        }
        const sample = sampleValueFor(meta);
        await page.locator(selector).fill(sample, { timeout: 4000 });
        await page.waitForTimeout(30);
        const state = await page.$eval(selector, element => ({ value: element.value, active: document.activeElement?.id || '' }));
        if (state.active !== meta.id) {
          fieldFailures.push({ panel, key: meta.key, id: meta.id, problem: `perdio foco al digitar hacia ${state.active || 'ninguno'}` });
        }
        if (!state.value) {
          fieldFailures.push({ panel, key: meta.key, id: meta.id, problem: 'no conserva valor digitado' });
        }
      } catch (error) {
        fieldFailures.push({ panel, key: meta.key, id: meta.id, problem: error.message });
      }
    }
  }
  assert(fieldFailures.length === 0, `Campos con problemas: ${JSON.stringify(fieldFailures.slice(0, 25), null, 2)}`);

  const validationResponse = await fetch(`${apiUrl}/api/cases/${sourceCase.id}/digitacion/validate-mdb?operation=colima`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      require_all: false,
      values: {
        fecha_radicacion: '2026-05-11',
        genero: 'X',
        eps: 'EPS INVENTADA',
        afp: 'AFP INVENTADA',
        ibc: '1000',
        cargo_actividad: 'Gerente',
        tipo_cotizante: '99',
        codigo_actividad_economica: '9999999',
        camara_codigo_actividad: '9999',
      },
    }),
  });
  assert(validationResponse.ok, `Validacion backend HTTP ${validationResponse.status}`);
  const validationPayload = await validationResponse.json();
  const errorKeys = (validationPayload?.validation?.errors || []).map(item => item.key);
  for (const key of ['genero', 'eps', 'afp', 'ibc', 'tipo_cotizante', 'codigo_actividad_economica', 'camara_codigo_actividad']) {
    assert(errorKeys.includes(key), `Backend no bloqueo ${key}`);
  }

  await page.screenshot({ path: '/tmp/afilega_digitacion_catalogs_rpa.png', fullPage: true });
  await browser.close();
  console.log(JSON.stringify({
    ok: true,
    caseId: sourceCase.id,
    flowState,
    uiState,
    fieldStats,
    backendErrorKeys: errorKeys,
    screenshot: '/tmp/afilega_digitacion_catalogs_rpa.png',
  }, null, 2));
})().catch(async error => {
  console.error(JSON.stringify({ ok: false, error: error.message, stack: error.stack }, null, 2));
  process.exit(1);
});
