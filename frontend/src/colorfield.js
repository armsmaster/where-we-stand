/**
 * Цветовое поле (ТЗ 6.6, 10).
 *
 * Три равноправных способа задать цвет: образец утверждённой палитры,
 * ввод hex и системный выбор. Все три пишут в одно и то же поле настроек —
 * сохранённый JSON не отличает цвет, взятый из палитры, от введённого руками.
 *
 * Послабления при вводе живут только здесь: наружу всегда уходит
 * строгий `#RRGGBB` в верхнем регистре.
 */

const STRICT = /^#[0-9A-Fa-f]{6}$/;
const SHORT = /^#?([0-9A-Fa-f]{3})$/;
const LONG = /^#?([0-9A-Fa-f]{6})$/;

/** Приводит принимаемые формы записи к `#RRGGBB`; null — если форма не распознана. */
export function normalizeHex(input) {
  const text = String(input || '').trim();
  if (!text) return null;

  const short = SHORT.exec(text);
  if (short) {
    const [r, g, b] = short[1];
    return `#${r}${r}${g}${g}${b}${b}`.toUpperCase();
  }

  const long = LONG.exec(text);
  if (long) return `#${long[1]}`.toUpperCase();

  return null;
}

export function isStrictHex(value) {
  return STRICT.test(String(value || ''));
}

let openPopover = null;

function closeOpen() {
  if (openPopover) {
    openPopover.remove();
    openPopover = null;
  }
}

document.addEventListener('click', (event) => {
  if (openPopover && !openPopover.closest('.color-field').contains(event.target)) {
    closeOpen();
  }
});
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') closeOpen();
});

export function createColorField({ value, palette, onChange }) {
  let current = normalizeHex(value) || '#000000';

  const element = document.createElement('div');
  element.className = 'color-field';

  const swatch = document.createElement('button');
  swatch.type = 'button';
  swatch.className = 'color-swatch';
  swatch.title = 'Выбрать цвет';

  const text = document.createElement('input');
  text.type = 'text';
  text.className = 'color-value';
  text.spellcheck = false;
  text.setAttribute('aria-label', 'Цвет в формате #RRGGBB');

  element.append(swatch, text);

  function paint() {
    swatch.style.background = current;
    if (document.activeElement !== text) text.value = current;
    text.classList.remove('invalid');
  }

  function apply(next, { silent = false } = {}) {
    const normalized = normalizeHex(next);
    if (!normalized) return false;
    current = normalized;
    paint();
    if (!silent) onChange(current);
    return true;
  }

  text.addEventListener('input', () => {
    // Пустое поле — незавершённый ввод, а не сброс.
    if (!text.value.trim()) {
      text.classList.remove('invalid');
      return;
    }
    const normalized = normalizeHex(text.value);
    if (normalized) {
      text.classList.remove('invalid');
      current = normalized;
      swatch.style.background = current;
      onChange(current);
    } else {
      // Некорректный ввод не применяется: в настройках остаётся прежнее
      // значение, запрос на отрисовку не уходит.
      text.classList.add('invalid');
    }
  });

  text.addEventListener('blur', () => paint());

  swatch.addEventListener('click', (event) => {
    event.stopPropagation();
    if (openPopover && element.contains(openPopover)) {
      closeOpen();
      return;
    }
    closeOpen();
    openPopover = buildPopover();
    element.append(openPopover);
  });

  function buildPopover() {
    const popover = document.createElement('div');
    popover.className = 'color-popover';

    const heading = document.createElement('h5');
    heading.textContent = 'Палитра редакции';
    popover.append(heading);

    const grid = document.createElement('div');
    grid.className = 'palette-grid';
    for (const item of palette) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'palette-swatch';
      button.style.background = item.hex;
      button.title = `${item.name} · ${item.hex}`;
      if (item.hex.toUpperCase() === current) button.classList.add('chosen');
      button.addEventListener('click', () => {
        apply(item.hex);
        closeOpen();
      });
      grid.append(button);
    }
    popover.append(grid);

    const row = document.createElement('div');
    row.className = 'popover-row';

    const native = document.createElement('input');
    native.type = 'color';
    native.value = current;
    native.addEventListener('input', () => apply(native.value));

    const manual = document.createElement('input');
    manual.type = 'text';
    manual.className = 'color-value';
    manual.value = current;
    manual.spellcheck = false;
    manual.placeholder = '#RRGGBB';
    manual.addEventListener('input', () => {
      const normalized = normalizeHex(manual.value);
      if (normalized) {
        manual.classList.remove('invalid');
        apply(normalized);
        native.value = normalized;
      } else if (manual.value.trim()) {
        manual.classList.add('invalid');
      }
    });

    row.append(native, manual);
    popover.append(row);

    const note = document.createElement('p');
    note.className = 'popover-note';
    note.textContent = 'Принимается #RRGGBB, RRGGBB и краткое #RGB. Сохраняется всегда как #RRGGBB.';
    popover.append(note);

    popover.addEventListener('click', (event) => event.stopPropagation());
    return popover;
  }

  paint();

  return {
    element,
    setValue(next) {
      apply(next, { silent: true });
    },
  };
}
