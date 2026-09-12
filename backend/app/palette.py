"""Утверждённая палитра (ТЗ 6.6).

Палитра — удобство, а не условие работы: при отсутствующем или повреждённом
файле сервис поднимается на встроенном наборе и сообщает причину. Падать
он при этом не имеет права.

На результат отрисовки палитра не влияет никак: в настройках всегда лежит
конкретный #RRGGBB, а подмена файла не меняет уже собранные картинки.
"""

from __future__ import annotations

import json

from . import config
from .colors import is_valid_hex, normalize_hex

BUILTIN = [
    {"hex": "#378ADD", "name": "Синий — «сейчас»"},
    {"hex": "#888780", "name": "Серый — «неделю назад»"},
    {"hex": "#F1EFE8", "name": "Песочный — полоса шкалы"},
    {"hex": "#C9A227", "name": "Золото"},
    {"hex": "#111111", "name": "Основной текст"},
    {"hex": "#777777", "name": "Вторичный текст"},
    {"hex": "#FFFFFF", "name": "Белый фон"},
]


def load() -> dict:
    """Возвращает `{colors, source, note}`; note заполняется только при проблеме."""
    path = config.PRESETS_DIR / config.PALETTE_FILENAME

    if not path.is_file():
        return {
            "colors": BUILTIN,
            "source": "builtin",
            "note": f"Файл {config.PALETTE_FILENAME} не найден — показана встроенная палитра.",
        }

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "colors": BUILTIN,
            "source": "builtin",
            "note": f"Файл {config.PALETTE_FILENAME} не читается ({exc}) — "
                    "показана встроенная палитра.",
        }

    problem = _problem(raw)
    if problem:
        return {
            "colors": BUILTIN,
            "source": "builtin",
            "note": f"Файл {config.PALETTE_FILENAME} не прошёл проверку: {problem}. "
                    "Показана встроенная палитра.",
        }

    colors = [
        {"hex": normalize_hex(item["hex"]), "name": item["name"].strip()}
        for item in raw["colors"]
    ]
    return {"colors": colors, "source": config.PALETTE_FILENAME, "note": None}


def _problem(raw: object) -> str | None:
    if not isinstance(raw, dict):
        return "ожидался объект JSON"
    if not isinstance(raw.get("version"), int):
        return "отсутствует целочисленное поле `version`"
    colors = raw.get("colors")
    if not isinstance(colors, list) or not colors:
        return "поле `colors` должно быть непустым списком"
    for index, item in enumerate(colors):
        where = f"colors[{index}]"
        if not isinstance(item, dict):
            return f"{where}: ожидался объект"
        hex_value = item.get("hex")
        if not isinstance(hex_value, str) or not is_valid_hex(hex_value):
            return f"{where}.hex: значение «{hex_value}» не является цветом формата #RRGGBB"
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            return f"{where}.name: название обязательно"
    return None
