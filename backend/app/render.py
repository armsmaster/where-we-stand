"""Сборка картинки из данных и настроек (ТЗ 3.1, 9)."""

from __future__ import annotations

from . import layout as layout_module
from . import svg_builder
from .data_model import Meta, Row
from .fonts import FontRegistry
from .issues import Issues
from .rules import check_rows
from .settings_model import Settings
from .validate_settings import check_overrides_against_rows


def render_svg(
    rows: list[Row],
    meta: Meta,
    settings: Settings,
    registry: FontRegistry,
    embed_fonts: bool = False,
) -> tuple[str | None, Issues, float]:
    """Возвращает `(svg, issues, required_height)`.

    svg равен None, если были блокирующие ошибки: отрисовка при ошибках
    не выполняется (ТЗ 5.3).
    """
    issues = Issues()

    check_rows(rows, issues)
    check_overrides_against_rows(settings, rows, issues)
    if not issues.ok:
        return None, issues, 0.0

    layout = layout_module.build(rows, meta, settings, registry, issues)
    if not issues.ok:
        return None, issues, layout.required_height

    svg = svg_builder.build(layout, settings, registry, embed_fonts=embed_fonts)
    return svg, issues, layout.required_height
