from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest
from openpyxl import Workbook

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config  # noqa: E402
from app.fonts import get_registry  # noqa: E402
from app.settings_model import default_settings  # noqa: E402
from scenarios import GOLDEN_DIR, META, VALID_ROWS, sample_rows  # noqa: E402,F401

HEADERS = ["key", "label", "unit", "min", "max", "current", "prev", "decimals", "inverted"]


@pytest.fixture(scope="session")
def registry():
    return get_registry(str(config.FONTS_DIR))


@pytest.fixture
def settings():
    return default_settings()


@pytest.fixture
def meta():
    return META


def make_workbook(rows, as_of="2026-03-12", headers=HEADERS, meta_rows=None) -> bytes:
    """Книга из списка списков — для проверки конкретных дефектов."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "data"
    sheet.append(headers)
    for row in rows:
        sheet.append(row)

    meta_sheet = workbook.create_sheet("meta")
    if meta_rows is None:
        meta_rows = [["as_of", as_of]] if as_of is not None else []
    for row in meta_rows:
        meta_sheet.append(row)

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


@pytest.fixture
def rows():
    return sample_rows()
