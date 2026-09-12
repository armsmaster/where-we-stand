"""Единый конверт для ошибок и предупреждений (ТЗ 5, 6.4, 9).

Правило из ТЗ 5: сообщение должно позволять исправить файл, не обращаясь
к разработчику и не открывая спецификацию. Поэтому каждое сообщение —
законченная фраза: где, что найдено, что ожидалось, что сделать.

Правило из ТЗ 5.3: валидация обрабатывает весь вход целиком и возвращает
все проблемы сразу. Останавливаться на первой ошибке запрещено, поэтому
здесь нет исключений — только накопление в списке.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class Issue(BaseModel):
    level: Literal["error", "warning"]
    where: str
    """Адрес: ячейка «D4», «столбец prev», «строка 5 (brent)» или путь к полю настроек."""
    message: str


class Issues:
    """Накопитель проблем."""

    def __init__(self) -> None:
        self._items: list[Issue] = []

    def error(self, where: str, message: str) -> None:
        self._items.append(Issue(level="error", where=where, message=message))

    def warning(self, where: str, message: str) -> None:
        self._items.append(Issue(level="warning", where=where, message=message))

    def extend(self, other: "Issues") -> None:
        self._items.extend(other._items)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self._items if i.level == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self._items if i.level == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def __len__(self) -> int:
        return len(self._items)
