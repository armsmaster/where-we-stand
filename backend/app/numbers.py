"""Форматирование чисел и даты для картинки (ТЗ 7.2)."""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from .settings_model import NumberFormat


def format_number(value: float, decimals: int, fmt: NumberFormat) -> str:
    """Округление и запись числа по правилам ТЗ 7.2.

    Встроенный round() здесь применять нельзя: он реализует банковское
    округление, и round(0.5) даёт 0. Для публикуемых цифр это недопустимо.
    """
    quantum = Decimal(1).scaleb(-decimals)
    quantized = Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP)

    negative = quantized < 0
    digits = format(abs(quantized), "f")
    if "." in digits:
        integer_part, fraction_part = digits.split(".")
    else:
        integer_part, fraction_part = digits, ""

    if fmt.thousandsSeparator:
        grouped = []
        while len(integer_part) > 3:
            grouped.insert(0, integer_part[-3:])
            integer_part = integer_part[:-3]
        grouped.insert(0, integer_part)
        integer_part = fmt.thousandsSeparator.join(grouped)

    text = integer_part
    if decimals > 0:
        text = f"{text}{fmt.decimalSeparator}{fraction_part.ljust(decimals, '0')}"

    # Минус у нуля после округления не печатаем.
    if negative and quantized != 0:
        text = fmt.minusSign + text
    return text


def label_with_unit(label: str, unit: str) -> str:
    """ТЗ 7.3: единица измерения добавляется к подписи строки.

    Сами значения на шкале печатаются без единицы: она уже названа слева,
    а повтор у каждого числа зашумляет шкалу.
    """
    if not unit:
        return label
    return f"{label}, {unit}"


def format_date(value: date) -> str:
    """ТЗ 7.2: дата выводится как ДД.ММ.ГГГГ и настройке не подлежит."""
    return f"{value.day:02d}.{value.month:02d}.{value.year:04d}"
