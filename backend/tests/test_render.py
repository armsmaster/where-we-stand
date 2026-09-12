"""Отрисовка и эталонные тесты (ТЗ 13, критерии приёмки 7–17)."""

from __future__ import annotations

import hashlib
import json
import platform

import pytest

from app import layout as layout_module
from app import raster, render
from app.issues import Issues
from scenarios import GOLDEN_DIR, patched, scenarios

PNG_GOLDEN = GOLDEN_DIR / "png-linux.json"


# --- детерминированность --------------------------------------------------


def test_svg_is_stable(rows, meta, settings, registry):
    first, _, _ = render.render_svg(rows, meta, settings, registry)
    second, _, _ = render.render_svg(rows, meta, settings, registry)
    assert first == second


@pytest.mark.skipif(not raster.available(), reason="растеризатор недоступен")
def test_png_is_byte_identical(rows, meta, settings, registry):
    """Критерий 7: два прогона подряд дают побайтно одинаковый PNG."""
    svg, _, _ = render.render_svg(rows, meta, settings, registry)
    assert raster.render_png(svg, 2) == raster.render_png(svg, 2)


@pytest.mark.skipif(not raster.available(), reason="растеризатор недоступен")
def test_png_has_no_metadata_chunks(rows, meta, settings, registry):
    """ТЗ 12: изменяющиеся служебные поля в PNG подавлены."""
    svg, _, _ = render.render_svg(rows, meta, settings, registry)
    png = raster.render_png(svg, 1)
    for marker in (b"tEXt", b"iTXt", b"tIME", b"pHYs", b"zTXt"):
        assert marker not in png


# --- структура картинки ---------------------------------------------------


def test_no_forbidden_elements(rows, meta, settings, registry):
    """Критерий 17 и ТЗ 8.4."""
    svg, _, _ = render.render_svg(rows, meta, settings, registry)
    for forbidden in ("<foreignObject", "<script", "<animate", "<filter", "xlink:href"):
        assert forbidden not in svg


def test_value_label_fits_at_both_edges(meta, settings, registry):
    """Критерий 10: подписи на границах помещаются на холсте целиком."""
    rows = scenarios()["edges"][0]
    issues = Issues()
    layout = layout_module.build(rows, meta, settings, registry, issues)

    at_min, at_max = layout.rows
    assert at_min.value_anchor == "start"
    assert at_min.value_x == pytest.approx(layout.track_start)
    assert at_max.value_anchor == "end"
    assert at_max.value_x == pytest.approx(layout.track_end)

    width_min = registry.measure(
        at_min.value_text, settings.typography.family,
        settings.typography.value.weight, settings.typography.value.size,
    )
    assert layout.track_start + width_min <= settings.canvas.width - settings.canvas.padding.right
    assert layout.track_end - width_min >= settings.canvas.padding.left


def test_no_connector_when_points_are_close(meta, settings, registry):
    """Критерий 11: связка не рисуется, когда точки ближе суммы радиусов."""
    rows = scenarios()["near"][0]
    issues = Issues()
    layout = layout_module.build(rows, meta, settings, registry, issues)
    assert layout.rows[0].draw_connector is False

    svg, _, _ = render.render_svg(rows, meta, settings, registry)
    assert "<line" not in svg


def test_ring_is_drawn_over_the_current_point(meta, settings, registry):
    """Критерий 12: при current == prev кольцо видно поверх заполненной точки."""
    rows = scenarios()["same"][0]
    svg, _, _ = render.render_svg(rows, meta, settings, registry)

    filled = svg.index(f'r="{settings.geometry.currentRadius:g}" fill="{settings.colors.current}"')
    ring = svg.index('fill="none" stroke=')
    assert ring > filled, "кольцо должно идти после заполненной точки"


def test_long_label_warns(meta, settings, registry):
    """Критерий 13: длинная подпись предупреждает, а не молча наезжает на шкалу."""
    rows = scenarios()["long"][0]
    _, issues, _ = render.render_svg(rows, meta, settings, registry)
    assert any("шире колонки подписей" in item.message for item in issues.warnings)


def test_footnote_wraps(meta, settings, registry):
    """Критерий 14: длинная сноска переносится по словам."""
    rows, patch = scenarios()["long"]
    svg, _, _ = render.render_svg(rows, meta, patched(settings, patch), registry)
    issues = Issues()
    layout = layout_module.build(rows, meta, patched(settings, patch), registry, issues)
    assert len(layout.footnote.lines) > 1
    assert svg.count("<text") >= len(layout.footnote.lines)


def test_track_has_no_gradient(rows, meta, settings, registry):
    """Критерий 16: полоса шкалы без градиентов и цветового кодирования."""
    svg, _, _ = render.render_svg(rows, meta, settings, registry)
    for forbidden in ("Gradient", "<defs", "stop-color"):
        assert forbidden not in svg


def test_rows_keep_file_order(rows, meta, settings, registry):
    """ТЗ 8.7: порядок строк не меняется."""
    issues = Issues()
    layout = layout_module.build(rows, meta, settings, registry, issues)
    assert [item.row.key for item in layout.rows] == [row.key for row in rows]


def test_height_warning(rows, meta, settings, registry):
    """ТЗ 7.7: не хватило высоты — предупреждение с требуемым значением."""
    tight = patched(settings, {"canvas": {"height": 300}})
    _, issues, required = render.render_svg(rows, meta, tight, registry)
    assert required > 300
    assert any("не хватает" in item.message for item in issues.warnings)


# --- эталоны --------------------------------------------------------------


@pytest.mark.parametrize("name", list(scenarios()))
def test_golden_svg(name, meta, settings, registry):
    """ТЗ 13: эталонный SVG сравнивается посимвольно."""
    rows, patch = scenarios()[name]
    svg, _, _ = render.render_svg(rows, meta, patched(settings, patch), registry)
    path = GOLDEN_DIR / f"{name}.svg"

    if not path.exists():
        pytest.fail(f"Нет эталона {path.name}. Соберите: python scripts/update_golden.py")

    assert svg == path.read_text(encoding="utf-8"), (
        f"Отрисовка разошлась с эталоном {path.name}. Если изменение намеренное — "
        "обновите эталоны отдельным коммитом: python scripts/update_golden.py"
    )


@pytest.mark.skipif(
    platform.system() != "Linux" or not raster.available(),
    reason="эталонные хеши PNG снимаются в контейнере (ТЗ 1.1: байты зависят от образа)",
)
@pytest.mark.parametrize("name", list(scenarios()))
def test_golden_png(name, meta, settings, registry):
    """Критерий 20: хеш PNG совпадает с эталоном, снятым в образе."""
    if not PNG_GOLDEN.exists():
        pytest.fail(f"Нет {PNG_GOLDEN.name}. Соберите: python scripts/update_golden.py")

    expected = json.loads(PNG_GOLDEN.read_text(encoding="utf-8"))
    rows, patch = scenarios()[name]
    applied = patched(settings, patch)
    svg, _, _ = render.render_svg(rows, meta, applied, registry)
    digest = hashlib.sha256(raster.render_png(svg, applied.canvas.scale)).hexdigest()

    assert digest == expected.get(name), (
        f"PNG сценария {name} разошёлся с эталоном. Если изменение намеренное — "
        "обновите эталоны отдельным коммитом."
    )
