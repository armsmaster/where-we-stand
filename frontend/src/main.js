/** Сборка интерфейса и состояние вкладки (ТЗ 3, 10). */

import './styles.css';
import { api } from './api.js';
import { buildForm, writePath } from './form.js';

const DEBOUNCE_MS = 250;

const state = {
  schema: null,
  settings: null,
  palette: [],
  fonts: [],
  rows: [],
  meta: null,
  dataIssues: { errors: [], warnings: [] },
  settingsIssues: { errors: [], warnings: [] },
  renderIssues: { errors: [], warnings: [] },
  pngBlob: null,
  pngUrl: null,
  paletteNote: null,
};

const dom = {
  build: document.getElementById('build'),
  dataFile: document.getElementById('data-file'),
  dataName: document.getElementById('data-name'),
  issuesBlock: document.getElementById('issues-block'),
  issues: document.getElementById('issues'),
  tableBlock: document.getElementById('table-block'),
  table: document.getElementById('data-table'),
  asOf: document.getElementById('as-of'),
  form: document.getElementById('form'),
  presetSelect: document.getElementById('preset-select'),
  settingsFile: document.getElementById('settings-file'),
  saveSettings: document.getElementById('save-settings'),
  downloadPng: document.getElementById('download-png'),
  downloadSvg: document.getElementById('download-svg'),
  previewSize: document.getElementById('preview-size'),
  previewStatus: document.getElementById('preview-status'),
  image: document.getElementById('preview-image'),
  placeholder: document.getElementById('placeholder'),
};

// --- загрузка ------------------------------------------------------------

async function boot() {
  const [version, schema, defaults, palette, fonts, presets] = await Promise.all([
    api.version(),
    api.settingsSchema(),
    api.settingsDefaults(),
    api.palette(),
    api.fonts(),
    api.presets(),
  ]);

  dom.build.textContent = `сборка ${version.body.build} · ${version.body.rasterizer}`;
  if (!version.body.rasterizerAvailable) {
    pushIssue('error', 'растеризатор', 'Растеризатор недоступен — PNG собран не будет.');
  }

  state.schema = schema.body;
  state.settings = defaults.body;
  state.palette = palette.body.colors;
  state.paletteNote = palette.body.note;
  state.fonts = fonts.body.families.map((item) => item.family);

  if (state.paletteNote) pushIssue('warning', 'палитра', state.paletteNote);

  for (const preset of presets.body.presets) {
    const option = document.createElement('option');
    option.value = preset.name;
    option.textContent = preset.title ? `${preset.name} — ${preset.title}` : preset.name;
    dom.presetSelect.append(option);
  }

  renderForm();
  renderIssues();
}

// --- форма ---------------------------------------------------------------

function renderForm() {
  const scroll = dom.form.scrollTop;
  const openGroups = new Set(
    [...dom.form.querySelectorAll('details[open]')].map((node) => node.querySelector('summary').textContent)
  );

  dom.form.replaceChildren(
    buildForm({
      schema: state.schema,
      settings: state.settings,
      palette: state.palette,
      fonts: state.fonts,
      dataKeys: state.rows.map((row) => row.key),
      onChange: handleChange,
    })
  );

  if (openGroups.size) {
    for (const node of dom.form.querySelectorAll('details')) {
      node.open = openGroups.has(node.querySelector('summary').textContent);
    }
  }
  dom.form.scrollTop = scroll;
}

function handleChange(path, value) {
  state.settings = writePath(state.settings, path, value);
  // rowOverrides меняет состав формы, остальные поля — только значение.
  if (path[0] === 'rowOverrides') renderForm();
  scheduleRender();
}

// --- данные --------------------------------------------------------------

dom.dataFile.addEventListener('change', async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  dom.dataName.textContent = `Загружается ${file.name}…`;

  const response = await api.parseData(file);
  const body = response.body || { errors: [], warnings: [], rows: [], meta: null };

  state.dataIssues = { errors: body.errors || [], warnings: body.warnings || [] };
  state.rows = body.ok ? body.rows : [];
  state.meta = body.ok && body.meta ? body.meta : null;
  state.renderIssues = { errors: [], warnings: [] };

  dom.dataName.textContent = body.ok
    ? `${file.name} — ${state.rows.length} строк`
    : `${file.name} — файл не принят`;

  renderDataTable();
  renderForm();
  renderIssues();

  if (body.ok) {
    scheduleRender();
  } else {
    clearPreview();
  }

  event.target.value = '';
});

function renderDataTable() {
  if (!state.rows.length) {
    dom.tableBlock.hidden = true;
    return;
  }
  dom.tableBlock.hidden = false;
  dom.asOf.textContent = state.meta ? `Данные на ${formatDate(state.meta.as_of)}` : '';

  const columns = ['key', 'label', 'unit', 'min', 'max', 'current', 'prev', 'decimals', 'inverted'];
  const header = document.createElement('tr');
  for (const column of columns) {
    const cell = document.createElement('th');
    cell.textContent = column;
    header.append(cell);
  }

  const rows = state.rows.map((row) => {
    const tr = document.createElement('tr');
    for (const column of columns) {
      const cell = document.createElement('td');
      const value = row[column];
      cell.textContent = typeof value === 'boolean' ? (value ? 'да' : 'нет') : String(value ?? '');
      tr.append(cell);
    }
    return tr;
  });

  dom.table.replaceChildren(header, ...rows);
}

// --- настройки -----------------------------------------------------------

dom.presetSelect.addEventListener('change', async (event) => {
  const name = event.target.value;
  if (!name) return;
  const response = await api.preset(name);
  if (!response.ok) {
    state.settingsIssues = { errors: response.body?.errors || [], warnings: [] };
    renderIssues();
    return;
  }
  await applySettings(response.body);
});

dom.settingsFile.addEventListener('change', async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  let parsed;
  try {
    parsed = JSON.parse(await file.text());
  } catch (error) {
    state.settingsIssues = {
      errors: [{ level: 'error', where: 'файл', message: `Файл не является корректным JSON: ${error.message}` }],
      warnings: [],
    };
    renderIssues();
    event.target.value = '';
    return;
  }
  await applySettings(parsed);
  dom.presetSelect.value = '';
  event.target.value = '';
});

async function applySettings(payload) {
  const response = await api.settingsValidate(payload);
  const body = response.body || { errors: [], warnings: [] };
  state.settingsIssues = { errors: body.errors || [], warnings: body.warnings || [] };

  if (body.ok && body.settings) {
    state.settings = body.settings;
    renderForm();
    scheduleRender();
  }
  renderIssues();
}

dom.saveSettings.addEventListener('click', () => {
  const payload = JSON.stringify(state.settings, null, 2) + '\n';
  saveFile(new Blob([payload], { type: 'application/json' }), 'gde-my-nahodimsya-settings.json');
});

// --- превью и выгрузка ---------------------------------------------------

let renderTimer = null;
let renderToken = 0;

function scheduleRender() {
  clearTimeout(renderTimer);
  renderTimer = setTimeout(runRender, DEBOUNCE_MS);
}

async function runRender() {
  if (!state.rows.length || !state.meta || !state.settings) return;
  if (state.dataIssues.errors.length || state.settingsIssues.errors.length) return;

  const token = ++renderToken;
  setStatus('обновление…', 'busy');
  dom.image.classList.add('busy');

  let response;
  try {
    response = await api.renderPng({
      rows: state.rows,
      meta: state.meta,
      settings: state.settings,
    });
  } catch (error) {
    if (token !== renderToken) return;
    state.renderIssues = {
      errors: [{ level: 'error', where: 'сеть', message: String(error.message || error) }],
      warnings: [],
    };
    setStatus('ошибка сети', 'stale');
    dom.image.classList.remove('busy');
    renderIssues();
    return;
  }

  // Опоздавший ответ не должен затирать более свежий.
  if (token !== renderToken) return;
  dom.image.classList.remove('busy');

  if (!response.ok) {
    state.renderIssues = {
      errors: response.body?.errors || [],
      warnings: response.body?.warnings || [],
    };
    // Предыдущее превью остаётся видимым (ТЗ 10).
    setStatus('картинка устарела', 'stale');
    renderIssues();
    return;
  }

  state.renderIssues = { errors: [], warnings: response.warnings || [] };
  showPng(response.blob);
  setStatus('', '');
  renderIssues();
}

function showPng(blob) {
  const previous = state.pngUrl;
  state.pngBlob = blob;
  state.pngUrl = URL.createObjectURL(blob);
  dom.image.src = state.pngUrl;
  dom.image.hidden = false;
  dom.placeholder.hidden = true;
  if (previous) URL.revokeObjectURL(previous);

  const { width, height, scale } = state.settings.canvas;
  dom.previewSize.textContent =
    `${width} × ${height} px · растр ${width * scale} × ${height * scale} · ${Math.round(blob.size / 1024)} КБ`;

  dom.downloadPng.disabled = false;
  dom.downloadSvg.disabled = false;
}

function clearPreview() {
  dom.downloadPng.disabled = true;
  dom.downloadSvg.disabled = true;
  setStatus('картинка устарела', 'stale');
}

// ТЗ 3.1 и 10: скачивается ровно тот массив байтов, который показан
// в превью. Повторного запроса к бэкенду здесь нет.
dom.downloadPng.addEventListener('click', () => {
  if (!state.pngBlob) return;
  saveFile(state.pngBlob, `gde-my-nahodimsya-${state.meta.as_of}.png`);
});

dom.downloadSvg.addEventListener('click', async () => {
  const response = await api.renderSvg({
    rows: state.rows,
    meta: state.meta,
    settings: state.settings,
  });
  if (!response.ok) {
    state.renderIssues = { errors: response.body?.errors || [], warnings: [] };
    renderIssues();
    return;
  }
  saveFile(response.blob, `gde-my-nahodimsya-${state.meta.as_of}.svg`);
});

function saveFile(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// --- сообщения -----------------------------------------------------------

const extraIssues = [];

function pushIssue(level, where, message) {
  extraIssues.push({ level, where, message });
}

function renderIssues() {
  const all = [
    ...extraIssues,
    ...state.dataIssues.errors,
    ...state.settingsIssues.errors,
    ...state.renderIssues.errors,
    ...state.dataIssues.warnings,
    ...state.settingsIssues.warnings,
    ...state.renderIssues.warnings,
  ];

  // Ошибки первыми (ТЗ 5.3).
  all.sort((a, b) => (a.level === b.level ? 0 : a.level === 'error' ? -1 : 1));

  if (!all.length) {
    dom.issuesBlock.hidden = true;
    dom.issues.replaceChildren();
    return;
  }

  dom.issuesBlock.hidden = false;
  dom.issues.replaceChildren(
    ...all.map((issue) => {
      const item = document.createElement('li');
      item.className = issue.level;
      const where = document.createElement('span');
      where.className = 'where';
      where.textContent = issue.where;
      item.append(where, document.createTextNode(issue.message));
      return item;
    })
  );
}

function setStatus(text, className) {
  dom.previewStatus.textContent = text;
  dom.previewStatus.className = `status ${className}`.trim();
}

function formatDate(iso) {
  const [year, month, day] = iso.split('-');
  return `${day}.${month}.${year}`;
}

boot().catch((error) => {
  pushIssue('error', 'запуск', `Не удалось загрузить сервис: ${error.message}`);
  renderIssues();
});
