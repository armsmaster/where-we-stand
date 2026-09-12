"""Наборы данных для эталонных тестов (ТЗ 13).

Модуль не зависит от pytest: его же импортирует scripts/update_golden.py,
который запускается внутри контейнера, где тестовых пакетов нет.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from app.data_model import Meta, Row
from app.settings_model import Settings

GOLDEN_DIR = Path(__file__).parent / "golden"

META = Meta(as_of=dt.date(2026, 3, 12))

VALID_ROWS = [
    ["imoex", "Индекс МосБиржи", "п.", 2512, 3521, 2890, 2845, 0, False],
    ["ofz_10y", "Доходность ОФЗ 10 лет", "%", 13.8, 17.2, 15.1, 15.4, 1, True],
    ["corp_spread", "Кредитный спред", "б.п.", 180, 520, 340, 355, 0, True],
    ["brent", "Нефть Brent", "$/барр.", 62, 88, 71.4, 69.8, 1, False],
    ["gold", "Золото", "$/унц.", 1980, 2790, 2620, 2585, 0, False],
]

LONG_FOOTNOTE = (
    "Очень длинная сноска, которая заведомо не помещается в одну строку "
    "и обязана быть перенесена по словам без обрезки и без выхода за пределы "
    "области отрисовки. Для того, чтобы проверка была настоящей, текст заведомо "
    "длиннее той ширины, которая остаётся под него на холсте шириной 1200 точек "
    "при полях сорок точек с каждой стороны."
)


def sample_rows() -> list[Row]:
    return [
        Row(
            key=row[0], label=row[1], unit=row[2], min=row[3], max=row[4],
            current=row[5], prev=row[6], decimals=row[7], inverted=row[8],
        )
        for row in VALID_ROWS
    ]


def scenarios() -> dict[str, tuple[list[Row], dict]]:
    """Имя сценария -> (строки, правка настроек поверх значений по умолчанию)."""
    return {
        "base": (sample_rows(), {}),
        "edges": (
            [
                Row(key="at_min", label="На минимуме", unit="п.", min=100, max=200,
                    current=100, prev=150, decimals=0),
                Row(key="at_max", label="На максимуме", unit="п.", min=100, max=200,
                    current=200, prev=150, decimals=0),
            ],
            {},
        ),
        "same": (
            [Row(key="frozen", label="Без изменений", unit="%", min=1, max=9,
                 current=5, prev=5, decimals=1)],
            {},
        ),
        "near": (
            [Row(key="near", label="Почти совпали", unit="%", min=0, max=100,
                 current=50, prev=50.4, decimals=1)],
            {},
        ),
        "long": (
            [Row(key="long_one", label="Индекс МосБиржи полной доходности брутто",
                 unit="пунктов", min=1000, max=9000, current=5000, prev=4800, decimals=0)],
            {"texts": {"footnote": LONG_FOOTNOTE}},
        ),
        "eight": (
            [
                Row(key=f"row_{i}", label=f"Строка {i}", unit="п.",
                    min=0, max=100, current=10 * i, prev=10 * i - 5, decimals=0)
                for i in range(1, 9)
            ],
            {"canvas": {"height": 1130}},
        ),
        "no_chrome": (
            sample_rows(),
            {"toggles": {"showTitle": False, "showLegend": False,
                         "showFootnote": False, "showSource": False}},
        ),
    }


def patched(settings: Settings, patch: dict) -> Settings:
    data = settings.model_dump()
    for group, values in patch.items():
        data[group].update(values)
    return Settings.model_validate(data)
