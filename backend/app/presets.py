"""Каталог пресетов оформления (ТЗ 6.5)."""

from __future__ import annotations

import json
import re

from . import config

SAFE_NAME = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def listing() -> list[dict]:
    directory = config.PRESETS_DIR
    if not directory.is_dir():
        return []

    items = []
    for path in sorted(directory.glob("*.json")):
        if path.name == config.PALETTE_FILENAME:
            # Имя зарезервировано за палитрой, пресетом файл не считается.
            continue
        title = path.stem
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            title = str(raw.get("texts", {}).get("title", "") or path.stem)
        except (OSError, json.JSONDecodeError, AttributeError):
            # Битый пресет не должен ломать список остальных — он просто
            # показывается под именем файла и отвалится при загрузке.
            pass
        items.append({"name": path.stem, "title": title})
    return items


def read(name: str) -> tuple[dict | None, str | None]:
    if not SAFE_NAME.match(name):
        return None, (
            f"Недопустимое имя пресета «{name}». Допустимы латиница, цифры, "
            "дефис и подчёркивание."
        )

    path = config.PRESETS_DIR / f"{name}.json"
    if path.name == config.PALETTE_FILENAME or not path.is_file():
        return None, f"Пресет «{name}» не найден."

    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"Пресет «{name}» не читается: {exc}"
