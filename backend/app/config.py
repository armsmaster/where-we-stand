"""Пути и настройки окружения.

Всё, что может отличаться между локальным запуском и контейнером,
собрано здесь. Значения по умолчанию рассчитаны на запуск из корня
репозитория; в образе переопределяются переменными окружения.
"""

from __future__ import annotations

import os
import platform
from pathlib import Path

# backend/app/config.py -> backend/app -> backend -> корень репозитория
REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _path_from_env(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    return Path(value) if value else default


def _default_resvg() -> Path:
    if platform.system() == "Windows":
        return REPO_ROOT / "vendor" / "resvg" / "win64" / "resvg.exe"
    return REPO_ROOT / "vendor" / "resvg" / "linux-x86_64" / "resvg"


FONTS_DIR = _path_from_env("WDWS_FONTS_DIR", REPO_ROOT / "fonts")
PRESETS_DIR = _path_from_env("WDWS_PRESETS_DIR", REPO_ROOT / "presets")
STATIC_DIR = _path_from_env("WDWS_STATIC_DIR", REPO_ROOT / "frontend" / "dist")
RESVG_BIN = _path_from_env("WDWS_RESVG_BIN", _default_resvg())

# ТЗ 4.1 и 11.3: размер загружаемого файла и тела запроса.
MAX_UPLOAD_BYTES = 2 * 1024 * 1024

# ТЗ 12: одновременных растеризаций.
RENDER_CONCURRENCY = int(os.environ.get("WDWS_RENDER_CONCURRENCY", "4"))

# Таймаут одного вызова растеризатора, секунды.
RENDER_TIMEOUT = float(os.environ.get("WDWS_RENDER_TIMEOUT", "20"))

# Версия сборки — проставляется при сборке образа, см. Dockerfile.
BUILD_VERSION = os.environ.get("WDWS_BUILD_VERSION", "dev")

# Имя зарезервировано за палитрой и не показывается в списке пресетов (ТЗ 6.5).
PALETTE_FILENAME = "palette.json"
