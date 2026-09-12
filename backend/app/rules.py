"""Правила по значениям строк (ТЗ 5.1, 5.2).

Общий код для парсера Excel и для рендер-эндпоинтов: фронтенд может
прислать произвольные `rows`, и без повторной проверки это даёт 500
вместо внятного 422 (ТЗ 9).
"""

from __future__ import annotations

from .data_model import EXPECTED_ROWS, MAX_ROWS, Row
from .issues import Issues

# ТЗ 5.2: диапазон уже этой доли от текущего значения — шкала вырождена.
NARROW_RANGE_RATIO = 0.01


def format_value(value: float) -> str:
    """Число для текста сообщения — не для картинки."""
    return f"{value:.10g}".replace(".", ",")


def check_range(
    low: float | None, high: float | None, current: float | None, prev: float | None,
    row_label: str, issues: Issues,
) -> bool:
    """Блокирующие проверки диапазона. Возвращает False, если были ошибки.

    Значения могут отсутствовать: если столбец переименован или ячейка
    пуста, остальные проверки всё равно должны выполниться (ТЗ 5.3).
    """
    if low is None or high is None:
        return False
    if low >= high:
        issues.error(
            row_label,
            f"{row_label}: минимум {format_value(low)} не меньше максимума "
            f"{format_value(high)}. Вероятно, значения перепутаны местами.",
        )
        return False

    ok = True
    for value, label in (
        (current, "текущее значение"),
        (prev, "значение недельной давности"),
    ):
        if value is None:
            continue
        if value > high:
            issues.error(
                row_label,
                f"{row_label}: {label} {format_value(value)} выше годового максимума "
                f"{format_value(high)}. Если это новый годовой максимум — укажите в `max` "
                f"значение {format_value(value)}. Если нет — проверьте, за какой период "
                "рассчитан максимум.",
            )
            ok = False
        elif value < low:
            issues.error(
                row_label,
                f"{row_label}: {label} {format_value(value)} ниже годового минимума "
                f"{format_value(low)}. Если это новый годовой минимум — укажите в `min` "
                f"значение {format_value(value)}. Если нет — проверьте, за какой период "
                "рассчитан минимум.",
            )
            ok = False
    return ok


def check_row_warnings(row: Row, row_label: str, issues: Issues) -> None:
    """Неблокирующие наблюдения по одной строке (ТЗ 5.2)."""
    if row.current == row.prev:
        issues.warning(
            row_label,
            f"{row_label}: за неделю значение не изменилось — проверьте, "
            "не скопирован ли столбец.",
        )

    span = row.max - row.min
    reference = abs(row.current) if row.current else abs(row.max)
    if reference and span < reference * NARROW_RANGE_RATIO:
        issues.warning(
            row_label,
            f"{row_label}: годовой диапазон ({format_value(span)}) уже одного процента "
            "от текущего значения — шкала будет визуально вырожденной.",
        )

    for value, name in ((row.current, "current"), (row.prev, "prev")):
        if value in (row.min, row.max):
            edge = "минимуму" if value == row.min else "максимуму"
            issues.warning(
                row_label,
                f"{row_label}: значение `{name}` равно годовому {edge} — точка встанет "
                "на край шкалы, подпись будет прижата к краю.",
            )


def check_rows(rows: list[Row], issues: Issues) -> None:
    """Полная проверка набора строк, пришедшего не из парсера."""
    if not rows:
        issues.error("rows", "Не передано ни одной строки данных.")
        return

    if len(rows) > MAX_ROWS:
        issues.error("rows", f"Передано {len(rows)} строк данных. Максимум — {MAX_ROWS}.")
        return

    seen: dict[str, int] = {}
    for index, row in enumerate(rows, start=1):
        row_label = f"Строка {index} (`{row.key}`)"
        if row.key in seen:
            issues.error(
                row_label,
                f"Ключ `{row.key}` встречается дважды: строки {seen[row.key]} и {index}. "
                "Ключи должны быть уникальны.",
            )
        else:
            seen[row.key] = index

        if check_range(row.min, row.max, row.current, row.prev, row_label, issues):
            check_row_warnings(row, row_label, issues)

    if len(rows) != EXPECTED_ROWS:
        issues.warning(
            "rows",
            f"Передано {len(rows)} строк данных. Штатная конфигурация — "
            f"{EXPECTED_ROWS} классов активов.",
        )
