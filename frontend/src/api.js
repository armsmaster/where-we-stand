/** Обращения к бэкенду. Единый конверт ошибок описан в ТЗ 9. */

async function asJson(response) {
  const text = await response.text();
  try {
    return text ? JSON.parse(text) : null;
  } catch {
    return null;
  }
}

/** Возвращает `{ok, body, status}` — 422 с конвертом не считается сбоем. */
async function call(url, options = {}) {
  const response = await fetch(url, options);
  const body = await asJson(response);
  if (!response.ok && body === null) {
    throw new Error(`${options.method || 'GET'} ${url}: HTTP ${response.status}`);
  }
  return { ok: response.ok, status: response.status, body };
}

export const api = {
  version: () => call('/api/version'),
  fonts: () => call('/api/fonts'),
  palette: () => call('/api/palette'),
  presets: () => call('/api/presets'),
  preset: (name) => call(`/api/presets/${encodeURIComponent(name)}`),
  settingsDefaults: () => call('/api/settings/defaults'),
  settingsSchema: () => call('/api/settings/schema'),

  settingsValidate: (payload) =>
    call('/api/settings/validate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),

  parseData(file) {
    const form = new FormData();
    form.append('file', file);
    return call('/api/data/parse', { method: 'POST', body: form });
  },

  /** PNG отдаётся как есть: этот же массив байтов потом сохраняется по кнопке. */
  async renderPng(payload) {
    const response = await fetch('/api/render/png', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      return { ok: false, status: response.status, body: await asJson(response) };
    }

    return {
      ok: true,
      status: response.status,
      blob: await response.blob(),
      warnings: decodeWarnings(response.headers.get('X-Render-Warnings')),
      requiredHeight: Number(response.headers.get('X-Required-Height') || 0),
    };
  },

  async renderSvg(payload) {
    const response = await fetch('/api/render/svg', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      return { ok: false, status: response.status, body: await asJson(response) };
    }
    return { ok: true, blob: await response.blob() };
  },
};

/** Кириллица в заголовке HTTP напрямую недопустима, поэтому base64 (ТЗ 9). */
function decodeWarnings(header) {
  if (!header) return [];
  try {
    const binary = atob(header);
    const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
    return JSON.parse(new TextDecoder().decode(bytes));
  } catch {
    return [];
  }
}
