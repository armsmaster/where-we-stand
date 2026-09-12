"""Чтение и валидация файла данных (критерии приёмки 3, 4, 5, 19)."""

from __future__ import annotations

import io

from openpyxl import Workbook

from app import excel_reader, excel_template
from conftest import HEADERS, VALID_ROWS, make_workbook


def messages(issues):
    return " || ".join(item.message for item in issues)


def test_template_passes_validation():
    """Критерий 3: скачанный шаблон проходит валидацию без единой ошибки."""
    result = excel_reader.parse(excel_template.build(), "template.xlsx")
    assert result.issues.errors == []
    assert len(result.rows) == 5
    assert result.meta is not None


def test_all_four_defects_reported_in_one_pass():
    """Критерий 4: четыре дефекта разом, каждый с адресом ячейки."""
    headers = ["key", "label", "unit", "min", "max", "current", "previous", "decimals", "inverted"]
    rows = [
        # число как текст в C2 (min); current выше max в строке 3; дубль ключа gold
        ["imoex", "Индекс МосБиржи", "п.", "2512", 3521, 2890, 2845, 0, False],
        ["corp_spread", "Кредитный спред", "б.п.", 180, 520, 540, 355, 0, True],
        ["gold", "Золото", "$/унц.", 1980, 2790, 2620, 2585, 0, False],
        ["gold", "Золото ещё раз", "$/унц.", 1980, 2790, 2620, 2585, 0, False],
    ]
    result = excel_reader.parse(make_workbook(rows, headers=headers), "bad.xlsx")
    text = messages(result.issues.errors)

    assert "сохранено как текст" in text and "D2" in text
    assert "выше годового максимума" in text and "540" in text
    assert "Не найден обязательный столбец `prev`" in text and "previous" in text
    assert "встречается дважды" in text and "gold" in text


def test_formula_without_cached_value():
    """Критерий 5: формула без сохранённого результата, а не «ячейка пуста»."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "data"
    sheet.append(HEADERS)
    sheet.append(["imoex", "Индекс МосБиржи", "п.", 2512, 3521, "=B2*2", 2845, 0, False])
    meta = workbook.create_sheet("meta")
    meta.append(["as_of", "2026-03-12"])
    buffer = io.BytesIO()
    workbook.save(buffer)

    result = excel_reader.parse(buffer.getvalue(), "formulas.xlsx")
    text = messages(result.issues.errors)
    assert "содержит формулу" in text
    assert "=B2*2" in text
    assert "сохраните ещё раз" in text
    assert "пуста" not in text


def test_missing_meta_sheet_is_an_error():
    """Критерий 19: без листа meta — ошибка, а не подстановка сегодняшней даты."""
    result = excel_reader.parse(make_workbook(VALID_ROWS, meta_rows=[]), "nometa.xlsx")
    assert result.meta is None
    assert "as_of" in messages(result.issues.errors)


def test_bad_date_format():
    result = excel_reader.parse(
        make_workbook(VALID_ROWS, meta_rows=[["as_of", "12 марта"]]), "baddate.xlsx"
    )
    assert "не распознано как дата" in messages(result.issues.errors)


def test_data_below_empty_row_warns():
    rows = list(VALID_ROWS[:2]) + [[]] + [
        ["gold", "Золото", "$/унц.", 1980, 2790, 2620, 2585, 0, False]
    ]
    result = excel_reader.parse(make_workbook(rows), "gap.xlsx")
    assert len(result.rows) == 2
    assert "не попали в картинку" in messages(result.issues.warnings)


def test_russian_booleans_and_nbsp():
    rows = [
        ["ofz_10y", "Доходность ОФЗ", "%", 13.8, 17.2, 15.1, 15.4, 1, "ИСТИНА"],
        [" brent ", " Нефть  Brent ", "$", 62, 88, 71.4, 69.8, 1, "нет"],
    ]
    result = excel_reader.parse(make_workbook(rows), "bool.xlsx")
    assert result.issues.errors == []
    assert result.rows[0].inverted is True
    assert result.rows[1].inverted is False
    assert result.rows[1].key == "brent"
    assert result.rows[1].label == "Нефть Brent"


def test_unknown_column_is_only_a_warning():
    headers = HEADERS + ["комментарий"]
    rows = [row + ["что-то"] for row in VALID_ROWS]
    result = excel_reader.parse(make_workbook(rows, headers=headers), "extra.xlsx")
    assert result.issues.errors == []
    assert "не входит в спецификацию" in messages(result.issues.warnings)


def test_wrong_extension_rejected():
    result = excel_reader.parse(b"a,b,c", "data.csv")
    assert "не поддерживается" in messages(result.issues.errors)


def test_too_many_rows():
    rows = [
        [f"key{i}", f"Строка {i}", "", 0, 10, 5, 4, 0, False] for i in range(9)
    ]
    result = excel_reader.parse(make_workbook(rows), "many.xlsx")
    assert "Максимум — 8" in messages(result.issues.errors)


def test_decimals_out_of_range():
    rows = [["imoex", "Индекс", "п.", 1, 10, 5, 4, 9, False]]
    result = excel_reader.parse(make_workbook(rows), "dec.xlsx")
    assert "от 0 до 3" in messages(result.issues.errors)


def test_row_count_warning():
    rows = [["imoex", "Индекс", "п.", 1, 10, 5, 4, 0, False]]
    result = excel_reader.parse(make_workbook(rows), "one.xlsx")
    assert result.issues.errors == []
    assert "Штатная конфигурация" in messages(result.issues.warnings)
