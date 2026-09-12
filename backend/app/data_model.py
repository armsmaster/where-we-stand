"""Модель данных строки и запроса на отрисовку (ТЗ 4.2, 9)."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from .settings_model import Settings

KEY_PATTERN = r"^[A-Za-z0-9_]{1,32}$"

MIN_ROWS = 1
MAX_ROWS = 8
EXPECTED_ROWS = 5


class Row(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: Annotated[str, Field(pattern=KEY_PATTERN)]
    label: Annotated[str, Field(min_length=1, max_length=40)]
    unit: Annotated[str, Field(max_length=16)] = ""
    min: float
    max: float
    current: float
    prev: float
    decimals: Annotated[int, Field(ge=0, le=3)] = 0
    inverted: bool = False


class Meta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of: date


class RenderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[Row]
    meta: Meta
    settings: Settings
