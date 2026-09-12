"""Работа с цветом: разбор hex и мера различимости (ТЗ 6.4, 6.6)."""

from __future__ import annotations

import re

HEX_STRICT = re.compile(r"^#[0-9A-Fa-f]{6}$")

# ТЗ 6.4: порог различимости. Константа задана в коде и настройке не подлежит —
# эвристика сознательно грубая, её задача поймать случайную вставку не того hex.
DELTA_E_THRESHOLD = 25.0


def is_valid_hex(value: str) -> bool:
    return bool(HEX_STRICT.match(value))


def normalize_hex(value: str) -> str:
    """Приводит корректный `#RRGGBB` к верхнему регистру.

    Послабления при вводе (краткая форма, запись без решётки) живут только
    в интерфейсе — см. ТЗ 6.6. Здесь формат строгий.
    """
    return "#" + value[1:].upper()


def to_rgb(value: str) -> tuple[int, int, int]:
    v = value.lstrip("#")
    return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)


def _to_linear(channel: float) -> float:
    if channel <= 0.04045:
        return channel / 12.92
    return ((channel + 0.055) / 1.055) ** 2.4


def to_lab(value: str) -> tuple[float, float, float]:
    """sRGB -> CIE Lab (D65). Нужен только для меры различимости."""
    r, g, b = (c / 255.0 for c in to_rgb(value))
    r, g, b = _to_linear(r), _to_linear(g), _to_linear(b)

    x = r * 0.4124564 + g * 0.3575761 + b * 0.1804375
    y = r * 0.2126729 + g * 0.7151522 + b * 0.0721750
    z = r * 0.0193339 + g * 0.1191920 + b * 0.9503041

    # Белая точка D65
    x, y, z = x / 0.95047, y / 1.00000, z / 1.08883

    def f(t: float) -> float:
        if t > 216 / 24389:
            return t ** (1 / 3)
        return (24389 / 27 * t + 16) / 116

    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def delta_e(first: str, second: str) -> float:
    """ΔE по CIE76 — разница двух цветов в Lab."""
    l1, a1, b1 = to_lab(first)
    l2, a2, b2 = to_lab(second)
    return ((l1 - l2) ** 2 + (a1 - a2) ** 2 + (b1 - b2) ** 2) ** 0.5


def indistinguishable(first: str, second: str) -> bool:
    return delta_e(first, second) < DELTA_E_THRESHOLD
