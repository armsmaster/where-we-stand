/**
 * Форма настроек, построенная из JSON Schema (ТЗ 6.1, 10).
 *
 * Описание полей — заголовки, диапазоны, допустимые значения — приходит
 * с бэкенда вместе со схемой. Здесь нет ни одного зашитого имени поля,
 * кроме двух особых случаев (шрифт и rowOverrides): иначе форма
 * и валидатор разойдутся при первой же правке модели.
 */

import { createColorField } from './colorfield.js';

const GROUP_ORDER = ['canvas', 'typography', 'geometry', 'colors', 'numberFormat', 'texts', 'toggles'];

/** Значения-разделители неразличимы на глаз, поэтому подписываются словами. */
const ENUM_LABELS = {
  '': 'без разделителя',
  ' ': 'обычный пробел',
  ' ': 'неразрывный пробел',
  ' ': 'узкий пробел',
  '−': '−  типографский минус',
  '-': '-  дефис',
  ',': ',  запятая',
  '.': '.  точка',
  400: '400 — обычное',
  500: '500 — среднее',
  600: '600 — полужирное',
};

const WIDE_FIELDS = new Set(['texts']);

function resolve(schema, node) {
  if (node && node.$ref) {
    const name = node.$ref.split('/').pop();
    return { ...schema.$defs[name], title: node.title || schema.$defs[name].title };
  }
  return node;
}

/** Для `HexColor | None` описание цвета спрятано внутрь anyOf. */
function unwrapNullable(node) {
  if (!node || !node.anyOf) return node;
  const real = node.anyOf.find((variant) => variant.type !== 'null');
  return real ? { ...real, title: node.title, default: node.default } : node;
}

function labelFor(value) {
  return Object.prototype.hasOwnProperty.call(ENUM_LABELS, value) ? ENUM_LABELS[value] : String(value);
}

export function buildForm({ schema, settings, palette, fonts, dataKeys, onChange }) {
  const root = document.createElement('div');

  for (const groupName of GROUP_ORDER) {
    const node = resolve(schema, schema.properties[groupName]);
    if (!node || !node.properties) continue;

    const group = document.createElement('details');
    group.className = 'group';
    if (groupName === 'colors' || groupName === 'texts') group.open = true;

    const summary = document.createElement('summary');
    summary.textContent = schema.properties[groupName].title || groupName;
    group.append(summary);

    const body = document.createElement('div');
    body.className = 'group-body';
    renderObject(body, node, [groupName]);
    group.append(body);
    root.append(group);
  }

  root.append(buildOverrides());

  function renderObject(container, node, path) {
    for (const [name, rawChild] of Object.entries(node.properties)) {
      const child = resolve(schema, unwrapNullable(rawChild));
      const childPath = [...path, name];

      if (child.properties) {
        const subgroup = document.createElement('div');
        subgroup.className = 'subgroup';
        const heading = document.createElement('h4');
        heading.textContent = rawChild.title || name;
        subgroup.append(heading);
        renderObject(subgroup, child, childPath);
        container.append(subgroup);
        continue;
      }

      container.append(renderField(child, childPath, rawChild.title || name, path[0]));
    }
  }

  function renderField(node, path, title, groupName) {
    const field = document.createElement('div');
    field.className = 'field';

    const label = document.createElement('label');
    label.textContent = title;

    const value = readPath(settings, path);

    if (node.type === 'boolean') {
      field.className = 'field toggle';
      const input = document.createElement('input');
      input.type = 'checkbox';
      input.checked = Boolean(value);
      input.addEventListener('change', () => onChange(path, input.checked));
      field.append(input, label);
      return field;
    }

    if (path.join('.') === 'typography.family') {
      const select = document.createElement('select');
      for (const family of fonts) {
        const option = document.createElement('option');
        option.value = family;
        option.textContent = family;
        option.selected = family === value;
        select.append(option);
      }
      select.addEventListener('change', () => onChange(path, select.value));
      field.append(label, select);
      return field;
    }

    if (node.enum) {
      const select = document.createElement('select');
      for (const option of node.enum) {
        const element = document.createElement('option');
        element.value = String(option);
        element.textContent = labelFor(option);
        element.selected = String(option) === String(value);
        select.append(element);
      }
      select.addEventListener('change', () => {
        const picked = node.enum.find((item) => String(item) === select.value);
        onChange(path, picked);
      });
      field.append(label, select);
      return field;
    }

    if (node.format === 'color') {
      const control = createColorField({
        value: value || node.default || '#000000',
        palette,
        onChange: (next) => onChange(path, next),
      });
      field.append(label, control.element);
      return field;
    }

    if (node.type === 'number' || node.type === 'integer') {
      const input = document.createElement('input');
      input.type = 'number';
      if (node.minimum !== undefined) input.min = node.minimum;
      if (node.maximum !== undefined) input.max = node.maximum;
      input.step = node.type === 'integer' ? 1 : 'any';
      input.value = value ?? node.default ?? '';
      input.title = rangeHint(node);
      input.addEventListener('input', () => {
        const parsed = Number(input.value);
        const outOfRange =
          input.value === '' ||
          Number.isNaN(parsed) ||
          (node.minimum !== undefined && parsed < node.minimum) ||
          (node.maximum !== undefined && parsed > node.maximum);
        input.classList.toggle('invalid', outOfRange);
        // Значение вне диапазона не применяется: превью остаётся прежним.
        if (!outOfRange) onChange(path, parsed);
      });
      field.append(label, input);
      return field;
    }

    const input = document.createElement('input');
    input.type = 'text';
    input.value = value ?? node.default ?? '';
    if (node.description) input.title = node.description;
    input.addEventListener('input', () => onChange(path, input.value));
    if (WIDE_FIELDS.has(groupName)) {
      field.className = 'field wide';
      field.append(label, input);
    } else {
      field.append(label, input);
    }
    return field;
  }

  function buildOverrides() {
    const group = document.createElement('details');
    group.className = 'group';
    const summary = document.createElement('summary');
    summary.textContent = 'Оформление отдельных строк';
    group.append(summary);

    const body = document.createElement('div');
    body.className = 'group-body';
    group.append(body);

    const overrideSchema = schema.$defs.RowOverride;
    const overrides = settings.rowOverrides || {};

    for (const [key, override] of Object.entries(overrides)) {
      const block = document.createElement('div');
      block.className = 'subgroup';

      const heading = document.createElement('h4');
      heading.textContent = key;
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.textContent = 'Убрать';
      remove.style.marginLeft = '8px';
      remove.addEventListener('click', () => {
        const next = { ...settings.rowOverrides };
        delete next[key];
        onChange(['rowOverrides'], next);
      });
      heading.append(remove);
      block.append(heading);

      for (const [name, rawChild] of Object.entries(overrideSchema.properties)) {
        const child = unwrapNullable(rawChild);
        if (child.format !== 'color') continue;

        const field = document.createElement('div');
        field.className = 'field';
        const label = document.createElement('label');
        label.textContent = rawChild.title || name;

        const control = createColorField({
          value: override[name] || readPath(settings, ['colors', name]) || '#000000',
          palette,
          onChange: (next) => {
            const updated = { ...settings.rowOverrides };
            updated[key] = { ...updated[key], [name]: next };
            onChange(['rowOverrides'], updated);
          },
        });
        field.append(label, control.element);
        block.append(field);
      }

      body.append(block);
    }

    const add = document.createElement('div');
    add.className = 'row-controls';
    const select = document.createElement('select');
    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = dataKeys.length ? '— ключ строки —' : 'сначала загрузите данные';
    select.append(placeholder);
    for (const key of dataKeys) {
      if (overrides[key]) continue;
      const option = document.createElement('option');
      option.value = key;
      option.textContent = key;
      select.append(option);
    }

    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = 'Добавить';
    button.addEventListener('click', () => {
      if (!select.value) return;
      onChange(['rowOverrides'], {
        ...settings.rowOverrides,
        [select.value]: { current: settings.colors.current },
      });
    });

    add.append(select, button);
    body.append(add);
    return group;
  }

  return root;
}

function rangeHint(node) {
  if (node.minimum !== undefined && node.maximum !== undefined) {
    return `от ${node.minimum} до ${node.maximum}`;
  }
  return '';
}

export function readPath(object, path) {
  return path.reduce((acc, key) => (acc == null ? acc : acc[key]), object);
}

export function writePath(object, path, value) {
  const copy = structuredClone(object);
  let node = copy;
  for (const key of path.slice(0, -1)) node = node[key];
  node[path[path.length - 1]] = value;
  return copy;
}
