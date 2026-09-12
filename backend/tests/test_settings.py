"""Настройки, числа, палитра и шрифты (критерии приёмки 6, 18, 21–25)."""

from __future__ import annotations

import datetime as dt
import hashlib
import json

import pytest

from app import config, palette
from app.numbers import format_date, format_number
from app.settings_model import NumberFormat, default_settings
from app.validate_settings import validate

# --- числа ----------------------------------------------------------------


def fmt(**kwargs) -> NumberFormat:
    return NumberFormat(**kwargs)


def test_half_up_rounding():
    """ТЗ 7.2: банковское округление недопустимо — round(0.5) дало бы 0."""
    plain = fmt(thousandsSeparator="")
    assert format_number(0.5, 0, plain) == "1"
    assert format_number(1.5, 0, plain) == "2"
    assert format_number(2.5, 0, plain) == "3"
    assert format_number(13.25, 1, plain) == "13,3"


def test_trailing_zeros_are_kept():
    assert format_number(13.5, 2, fmt(thousandsSeparator="")) == "13,50"
    assert format_number(7, 1, fmt(thousandsSeparator="")) == "7,0"


def test_separators_and_minus():
    thousands = format_number(1234567, 0, fmt())
    assert thousands == "1 234 567"
    assert format_number(-12.3, 1, fmt(thousandsSeparator="")) == "−12,3"
    assert format_number(-0.04, 1, fmt(thousandsSeparator="")) == "0,0", "минус у нуля не печатаем"
    assert format_number(1234.5, 1, fmt(decimalSeparator=".", thousandsSeparator="")) == "1234.5"


def test_date_format():
    assert format_date(dt.date(2026, 3, 12)) == "12.03.2026"


# --- валидация настроек ---------------------------------------------------


def messages(issues):
    return " || ".join(item.message for item in issues)


def test_unknown_version_is_understandable(registry):
    """Критерий 18: понятное сообщение, а не ошибка сервера."""
    payload = default_settings().model_dump()
    payload["version"] = 99
    settings, issues = validate(payload, registry)
    assert settings is None
    assert "версии 99 не поддерживается" in messages(issues.errors)


def test_missing_version(registry):
    payload = default_settings().model_dump()
    del payload["version"]
    settings, issues = validate(payload, registry)
    assert settings is None
    assert "`version` обязательно" in messages(issues.errors)


def test_bad_color(registry):
    payload = default_settings().model_dump()
    payload["colors"]["current"] = "blue"
    settings, issues = validate(payload, registry)
    assert settings is None
    assert "не является цветом" in messages(issues.errors)
    assert "#RRGGBB" in messages(issues.errors)


def test_out_of_range_size(registry):
    payload = default_settings().model_dump()
    payload["typography"]["title"]["size"] = 0
    settings, issues = validate(payload, registry)
    assert settings is None
    text = messages(issues.errors)
    assert "typography.title.size" in text and "не меньше 8" in text


def test_unknown_font(registry):
    payload = default_settings().model_dump()
    payload["typography"]["family"] = "Helvetica Neue"
    settings, issues = validate(payload, registry)
    text = messages(issues.errors)
    assert "недоступен" in text and "Arimo" in text


def test_prev_radius_too_close(registry):
    payload = default_settings().model_dump()
    payload["geometry"]["prevRadius"] = payload["geometry"]["currentRadius"]
    settings, issues = validate(payload, registry)
    assert settings is None
    assert "не менее 1,5" in messages(issues.errors)


def test_unknown_placeholder(registry):
    payload = default_settings().model_dump()
    payload["texts"]["source"] = "Данные на {date}"
    settings, issues = validate(payload, registry)
    assert settings is None
    assert "{as_of}" in messages(issues.errors)


def test_unknown_field_is_a_warning(registry):
    payload = default_settings().model_dump()
    payload["canvas"]["shadow"] = True
    payload["somethingElse"] = 1
    settings, issues = validate(payload, registry)
    assert settings is not None
    text = messages(issues.warnings)
    assert "canvas.shadow" in text and "somethingElse" in text


def test_row_override_rejects_unknown_field(registry):
    payload = default_settings().model_dump()
    payload["rowOverrides"] = {"gold": {"glow": "#FFFFFF"}}
    settings, issues = validate(payload, registry)
    assert settings is None
    assert "не поддерживается" in messages(issues.errors)


def test_colors_are_normalized_to_upper_case(registry):
    """ТЗ 6.6: в файле формат строгий, регистр приводится к верхнему."""
    payload = default_settings().model_dump()
    payload["colors"]["current"] = "#c9a227"
    settings, issues = validate(payload, registry)
    assert settings is not None
    assert settings.colors.current == "#C9A227"


def test_indistinguishable_colors_warn(registry):
    """Критерий 25: совпадающие цвета точек предупреждают, но не блокируют."""
    payload = default_settings().model_dump()
    payload["colors"]["prev"] = payload["colors"]["current"]
    settings, issues = validate(payload, registry)
    assert settings is not None, "предупреждение не должно блокировать отрисовку"
    assert "слабо различимы" in messages(issues.warnings)


def test_settings_round_trip_is_stable(registry):
    """Файл настроек не должен меняться от сохранения к сохранению.

    Иначе одни и те же настройки дают разный текст и диффы пресетов
    шумят на пустом месте.
    """
    saved = json.dumps(default_settings().model_dump(), ensure_ascii=False, indent=2)
    restored, issues = validate(json.loads(saved), registry)
    assert issues.errors == []
    again = json.dumps(restored.model_dump(), ensure_ascii=False, indent=2)
    assert saved == again


def test_picture_survives_settings_round_trip(registry, rows, meta):
    """Критерий 6: после сохранения и повторной загрузки картинка та же."""
    from app import render

    original = default_settings()
    before, _, _ = render.render_svg(rows, meta, original, registry)

    saved = json.dumps(original.model_dump(), ensure_ascii=False, indent=2)
    restored, _ = validate(json.loads(saved), registry)
    after, _, _ = render.render_svg(rows, meta, restored, registry)

    assert before == after
    assert hashlib.sha256(before.encode()).hexdigest() == hashlib.sha256(after.encode()).hexdigest()


def test_prev_point_cannot_be_hidden(registry):
    """Критерий 15 и ТЗ 8.1: точка «неделю назад» не отключается.

    Ни в переключателях, ни где-либо ещё в схеме не должно появиться способа
    её скрыть — это главный смысловой элемент картинки.
    """
    from app.settings_model import json_schema

    schema = json.dumps(json_schema(), ensure_ascii=False).lower()
    assert "showprev" not in schema

    payload = default_settings().model_dump()
    payload["toggles"]["showPrev"] = False
    settings, issues = validate(payload, registry)

    assert settings is not None
    assert "toggles.showPrev" in messages(issues.warnings), "поле должно быть отброшено"
    assert not hasattr(settings.toggles, "showPrev")


def test_overrides_against_missing_key(registry, rows):
    from app.validate_settings import check_overrides_against_rows
    from app.issues import Issues

    payload = default_settings().model_dump()
    payload["rowOverrides"] = {"silver": {"current": "#C9A227"}}
    settings, _ = validate(payload, registry)

    issues = Issues()
    check_overrides_against_rows(settings, rows, issues)
    assert "которого нет в файле данных" in messages(issues.warnings)


# --- палитра --------------------------------------------------------------


def test_palette_file_is_read():
    loaded = palette.load()
    assert loaded["note"] is None
    assert loaded["source"] == config.PALETTE_FILENAME
    assert all(item["hex"].startswith("#") and item["name"] for item in loaded["colors"])


def test_palette_falls_back_when_missing(tmp_path, monkeypatch):
    """Критерий 23: без файла сервис поднимается на встроенной палитре."""
    monkeypatch.setattr(config, "PRESETS_DIR", tmp_path)
    loaded = palette.load()
    assert loaded["source"] == "builtin"
    assert "не найден" in loaded["note"]
    assert loaded["colors"] == palette.BUILTIN


def test_palette_falls_back_when_broken(tmp_path, monkeypatch):
    (tmp_path / config.PALETTE_FILENAME).write_text("{ не json", encoding="utf-8")
    monkeypatch.setattr(config, "PRESETS_DIR", tmp_path)
    loaded = palette.load()
    assert loaded["source"] == "builtin"
    assert "не читается" in loaded["note"]


def test_palette_rejects_bad_colors(tmp_path, monkeypatch):
    (tmp_path / config.PALETTE_FILENAME).write_text(
        json.dumps({"version": 1, "colors": [{"hex": "blue", "name": "Синий"}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "PRESETS_DIR", tmp_path)
    loaded = palette.load()
    assert loaded["source"] == "builtin"
    assert "не является цветом" in loaded["note"]


def test_palette_is_not_listed_as_preset(tmp_path, monkeypatch):
    """ТЗ 6.5: имя зарезервировано, пресетом файл не считается."""
    from app import presets

    monkeypatch.setattr(config, "PRESETS_DIR", tmp_path)
    (tmp_path / config.PALETTE_FILENAME).write_text('{"version":1,"colors":[]}', encoding="utf-8")
    (tmp_path / "editorial.json").write_text('{"version":1}', encoding="utf-8")

    names = [item["name"] for item in presets.listing()]
    assert names == ["editorial"]
    assert presets.read("palette")[0] is None


def test_palette_does_not_affect_rendering(tmp_path, monkeypatch, rows, meta, registry):
    """Критерий 24: подмена палитры не меняет картинку."""
    from app import render

    settings = default_settings()
    before, _, _ = render.render_svg(rows, meta, settings, registry)

    (tmp_path / config.PALETTE_FILENAME).write_text(
        json.dumps({"version": 1, "colors": [{"hex": "#00FF00", "name": "Кислотный"}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "PRESETS_DIR", tmp_path)
    after, _, _ = render.render_svg(rows, meta, settings, registry)
    assert before == after


# --- шрифты ---------------------------------------------------------------


def test_font_manifest_matches_files():
    """ТЗ 6.3 и 11.4: файлы шрифтов зафиксированы хешами."""
    manifest = json.loads((config.FONTS_DIR / "MANIFEST.json").read_text(encoding="utf-8"))
    for face in manifest["faces"]:
        path = config.FONTS_DIR / face["file"]
        assert path.is_file(), f"нет файла {face['file']}"
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == face["sha256"], f"{face['file']} изменился"


def test_all_weights_are_present(registry):
    for family in ("Arimo", "Inter"):
        assert registry.weights_of(family) == [400, 500, 600]


def test_measurement_is_positive_and_scales(registry):
    narrow = registry.measure("Индекс МосБиржи", "Arimo", 400, 16)
    wide = registry.measure("Индекс МосБиржи", "Arimo", 400, 32)
    assert narrow > 0
    assert wide == pytest.approx(narrow * 2)
