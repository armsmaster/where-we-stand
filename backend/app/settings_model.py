"""Схема настроек оформления — единственный источник правды (ТЗ 6.1).

Из этой модели выводятся: значения по умолчанию (`/api/settings/defaults`),
валидация (`/api/settings/validate`) и JSON Schema (`/api/settings/schema`),
по которой фронтенд строит форму. Дублировать описание полей в коде
фронтенда запрещено — иначе форма и валидатор расходятся при первой же правке.
"""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from .colors import normalize_hex

SETTINGS_VERSION = 1

HexColor = Annotated[
    str,
    Field(
        pattern=r"^#[0-9A-Fa-f]{6}$",
        description="Цвет в формате #RRGGBB",
        json_schema_extra={"format": "color"},
    ),
    AfterValidator(normalize_hex),
]

Weight = Literal[400, 500, 600]

# ТЗ 6.2: в текстах поддерживается единственная подстановка.
PLACEHOLDER_RE = re.compile(r"\{([^}]*)\}")
ALLOWED_PLACEHOLDERS = {"as_of"}


class Strict(BaseModel):
    """База для блоков схемы: неизвестные поля отбрасываются.

    Предупреждение о них собирается отдельно, до разбора (см. unknown_paths):
    pydantic о выброшенных ключах не сообщает.

    validate_default нужен, чтобы значения по умолчанию проходили приведение
    типов. Без него Field(92) у поля float остаётся целым, и файл настроек,
    сохранённый до загрузки, текстуально расходится с сохранённым после неё:
    92 против 92.0 при одинаковой картинке.
    """

    model_config = ConfigDict(extra="ignore", validate_default=True)


class Padding(Strict):
    top: int = Field(32, ge=0, le=400, title="Сверху")
    right: int = Field(40, ge=0, le=400, title="Справа")
    bottom: int = Field(32, ge=0, le=400, title="Снизу")
    left: int = Field(40, ge=0, le=400, title="Слева")


class Canvas(Strict):
    width: int = Field(1200, ge=400, le=4000, title="Ширина, px")
    height: int = Field(690, ge=200, le=4000, title="Высота, px")
    scale: int = Field(2, ge=1, le=4, title="Множитель растра")
    background: HexColor = Field("#FFFFFF", title="Фон")
    transparent: bool = Field(False, title="Прозрачный фон")
    padding: Padding = Field(default_factory=Padding, title="Поля")


class TextStyle(Strict):
    size: float = Field(..., ge=8, le=72, title="Кегль")
    weight: Weight = Field(..., title="Начертание")
    color: HexColor = Field(..., title="Цвет")


class Typography(Strict):
    family: str = Field("Arimo", min_length=1, max_length=64, title="Семейство")
    title: TextStyle = Field(
        default_factory=lambda: TextStyle(size=28, weight=600, color="#111111"),
        title="Заголовок",
    )
    rowLabel: TextStyle = Field(
        default_factory=lambda: TextStyle(size=16, weight=500, color="#111111"),
        title="Подпись строки",
    )
    value: TextStyle = Field(
        default_factory=lambda: TextStyle(size=15, weight=500, color="#111111"),
        title="Значение",
    )
    scaleEnds: TextStyle = Field(
        default_factory=lambda: TextStyle(size=13, weight=400, color="#777777"),
        title="Концы шкалы",
    )
    legend: TextStyle = Field(
        default_factory=lambda: TextStyle(size=13, weight=400, color="#777777"),
        title="Легенда",
    )
    footnote: TextStyle = Field(
        default_factory=lambda: TextStyle(size=12, weight=400, color="#777777"),
        title="Сноска",
    )


class Geometry(Strict):
    rowHeight: float = Field(92, ge=24, le=300, title="Высота строки")
    labelColumnWidth: float = Field(240, ge=0, le=1200, title="Ширина колонки подписей")
    labelGap: float = Field(16, ge=0, le=200, title="Зазор до шкалы")
    trackHeight: float = Field(6, ge=1, le=60, title="Толщина полосы")
    trackRadius: float = Field(3, ge=0, le=30, title="Скругление полосы")
    currentRadius: float = Field(6, ge=1, le=40, title="Радиус точки «сейчас»")
    prevRadius: float = Field(4.5, ge=1, le=40, title="Радиус кольца «неделю назад»")
    prevStrokeWidth: float = Field(1.5, ge=0.5, le=10, title="Толщина кольца")
    connectorWidth: float = Field(1.5, ge=0.5, le=10, title="Толщина связки")
    valueOffset: float = Field(11, ge=0, le=100, title="Отступ подписи значения")
    scaleEndsOffset: float = Field(16, ge=0, le=100, title="Отступ подписей концов")
    titleGap: float = Field(28, ge=0, le=300, title="После заголовка")
    legendGap: float = Field(24, ge=0, le=300, title="До легенды")
    legendItemGap: float = Field(20, ge=0, le=200, title="Между элементами легенды")
    footnoteGap: float = Field(12, ge=0, le=200, title="До сноски и источника")
    lineHeight: float = Field(1.35, ge=1.0, le=3.0, title="Межстрочный интервал")

    @model_validator(mode="after")
    def _points_distinguishable(self) -> "Geometry":
        # ТЗ 6.4: кольцо «неделю назад» рисуется поверх текущей точки,
        # и при близких радиусах сливается с её краем.
        if abs(self.prevRadius - self.currentRadius) < 1.5:
            raise ValueError(
                f"значение {self.prevRadius:g} слишком близко к currentRadius "
                f"{self.currentRadius:g}. Разница должна быть не менее 1,5 px, иначе "
                "кольцо «неделю назад» сливается с краем текущей точки"
            )
        return self


class Colors(Strict):
    track: HexColor = Field("#F1EFE8", title="Полоса шкалы")
    current: HexColor = Field("#378ADD", title="Точка «сейчас»")
    prev: HexColor = Field("#888780", title="Кольцо «неделю назад»")
    connector: HexColor = Field("#888780", title="Связка")


NBSP = " "
THIN_SPACE = " "
MINUS_SIGN = "−"


class NumberFormat(Strict):
    decimalSeparator: Literal[",", "."] = Field(",", title="Разделитель дробной части")
    thousandsSeparator: Literal["", NBSP, THIN_SPACE] = Field(
        NBSP, title="Разделитель разрядов"
    )
    minusSign: Literal[MINUS_SIGN, "-"] = Field(MINUS_SIGN, title="Знак минуса")
    unitSeparator: Literal[NBSP, " ", ""] = Field(
        NBSP, title="Отбивка единицы измерения"
    )


class RowOverride(BaseModel):
    """Индивидуальное оформление строки. ТЗ 6.2: иные поля отклоняются."""

    model_config = ConfigDict(extra="forbid")

    current: HexColor | None = Field(None, title="Точка «сейчас»")
    prev: HexColor | None = Field(None, title="Кольцо «неделю назад»")
    connector: HexColor | None = Field(None, title="Связка")
    track: HexColor | None = Field(None, title="Полоса шкалы")


class Texts(Strict):
    title: str = Field("Где мы находимся", max_length=120, title="Заголовок")
    legendCurrent: str = Field("сейчас", max_length=60, title="Легенда: «сейчас»")
    legendPrev: str = Field("неделю назад", max_length=60, title="Легенда: «неделю назад»")
    legendScale: str = Field(
        "шкала — диапазон за 12 месяцев", max_length=120, title="Легенда: шкала"
    )
    footnote: str = Field(
        "У доходностей и премий выше по шкале — ниже цена бумаги.",
        max_length=400,
        title="Сноска",
    )
    source: str = Field(
        "Источник: Мосбиржа, расчёты редакции. Данные на {as_of}",
        max_length=400,
        title="Источник",
        description="Шаблон. Подстановка {as_of} заменяется датой с листа meta",
    )

    @model_validator(mode="after")
    def _check_placeholders(self) -> "Texts":
        for field_name in ("title", "legendCurrent", "legendPrev", "legendScale", "footnote", "source"):
            value = getattr(self, field_name)
            for found in PLACEHOLDER_RE.findall(value):
                if found not in ALLOWED_PLACEHOLDERS:
                    raise ValueError(
                        f"неизвестная подстановка {{{found}}} в поле {field_name}. "
                        "Поддерживается только {as_of}"
                    )
        return self


class Toggles(Strict):
    showTitle: bool = Field(True, title="Заголовок")
    showLegend: bool = Field(True, title="Легенда")
    showFootnote: bool = Field(True, title="Сноска")
    showSource: bool = Field(True, title="Источник")


class Settings(Strict):
    version: int = Field(SETTINGS_VERSION, title="Версия схемы")
    canvas: Canvas = Field(default_factory=Canvas, title="Холст")
    typography: Typography = Field(default_factory=Typography, title="Типографика")
    geometry: Geometry = Field(default_factory=Geometry, title="Геометрия")
    colors: Colors = Field(default_factory=Colors, title="Цвета")
    numberFormat: NumberFormat = Field(default_factory=NumberFormat, title="Формат чисел")
    rowOverrides: dict[str, RowOverride] = Field(
        default_factory=dict, title="Оформление отдельных строк"
    )
    texts: Texts = Field(default_factory=Texts, title="Тексты")
    toggles: Toggles = Field(default_factory=Toggles, title="Переключатели")


def default_settings() -> Settings:
    return Settings()


def json_schema() -> dict:
    return Settings.model_json_schema()
