"""Сборка SVG по готовой раскладке (ТЗ 7, 8.4).

Модуль не принимает решений о геометрии — все координаты уже посчитаны
в layout.py. Здесь только разметка.

Запрещённые элементы (ТЗ 8.4): foreignObject, внешние ссылки, script,
анимации, фильтры. Перенос текста выполнен заранее отдельными строками.
"""

from __future__ import annotations

from xml.sax.saxutils import escape

from .fonts import FontRegistry
from .layout import Layout, TextBlock
from .settings_model import Settings, TextStyle

SVG_NS = "http://www.w3.org/2000/svg"


def num(value: float) -> str:
    """Координата с фиксированной точностью.

    Округление до сотых выполняется всегда и одинаково: без него
    представление float просачивалось бы в разметку и ломало
    побайтное совпадение (ТЗ 1.1).
    """
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-", "-0") else text


def _text_element(content: str, x: float, y: float, style: TextStyle, family: str,
                  anchor: str = "start") -> str:
    anchor_attr = f' text-anchor="{anchor}"' if anchor != "start" else ""
    return (
        f'<text x="{num(x)}" y="{num(y)}" font-family="{escape(family)}" '
        f'font-size="{num(style.size)}" font-weight="{style.weight}" '
        f'fill="{style.color}"{anchor_attr}>{escape(content)}</text>'
    )


def _block(block: TextBlock | None, family: str) -> list[str]:
    if block is None:
        return []
    return [
        _text_element(line, block.x, baseline, block.style, family, block.anchor)
        for line, baseline in zip(block.lines, block.baselines)
    ]


def build(layout: Layout, settings: Settings, registry: FontRegistry,
          embed_fonts: bool = False) -> str:
    geom = settings.geometry
    typo = settings.typography
    family = typo.family
    parts: list[str] = []

    parts.append(
        f'<svg xmlns="{SVG_NS}" width="{num(layout.width)}" height="{num(layout.height)}" '
        f'viewBox="0 0 {num(layout.width)} {num(layout.height)}">'
    )

    if embed_fonts:
        # Только для скачиваемого SVG: чтобы он открывался одинаково вне сервиса.
        # В разметку для растеризатора шрифты не встраиваются — resvg берёт их
        # из каталога, а base64 раздул бы каждый запрос превью.
        parts.append(f"<style>{registry.font_face_css(family)}</style>")

    if not settings.canvas.transparent:
        parts.append(
            f'<rect x="0" y="0" width="{num(layout.width)}" height="{num(layout.height)}" '
            f'fill="{settings.canvas.background}"/>'
        )

    parts.extend(_block(layout.title, family))

    track_width = layout.track_end - layout.track_start

    for row in layout.rows:
        track_top = row.track_y - geom.trackHeight / 2
        parts.append(
            f'<rect x="{num(layout.track_start)}" y="{num(track_top)}" '
            f'width="{num(track_width)}" height="{num(geom.trackHeight)}" '
            f'rx="{num(geom.trackRadius)}" fill="{row.track_color}"/>'
        )

        if row.draw_connector:
            parts.append(
                f'<line x1="{num(row.prev_x)}" y1="{num(row.track_y)}" '
                f'x2="{num(row.current_x)}" y2="{num(row.track_y)}" '
                f'stroke="{row.connector_color}" '
                f'stroke-width="{num(geom.connectorWidth)}" stroke-linecap="round"/>'
            )

        parts.append(
            f'<circle cx="{num(row.current_x)}" cy="{num(row.track_y)}" '
            f'r="{num(geom.currentRadius)}" fill="{row.current_color}"/>'
        )

        # ТЗ 7.4: кольцо «неделю назад» рисуется ПОВЕРХ текущей точки.
        # Обратный порядок при prevRadius < currentRadius делает его невидимым,
        # а при совпадении значений оно должно читаться как контур внутри точки.
        parts.append(
            f'<circle cx="{num(row.prev_x)}" cy="{num(row.track_y)}" '
            f'r="{num(geom.prevRadius)}" fill="none" stroke="{row.prev_color}" '
            f'stroke-width="{num(geom.prevStrokeWidth)}"/>'
        )

        parts.append(_text_element(row.label, settings.canvas.padding.left,
                                   row.label_baseline, typo.rowLabel, family))
        parts.append(_text_element(row.value_text, row.value_x, row.value_baseline,
                                   typo.value, family, row.value_anchor))
        parts.append(_text_element(row.min_text, layout.track_start, row.ends_baseline,
                                   typo.scaleEnds, family))
        parts.append(_text_element(row.max_text, layout.track_end, row.ends_baseline,
                                   typo.scaleEnds, family, "end"))

    for item in layout.legend_items:
        if item.kind == "dot":
            parts.append(
                f'<circle cx="{num(item.x)}" cy="{num(layout.legend_center_y)}" '
                f'r="{num(geom.currentRadius)}" fill="{settings.colors.current}"/>'
            )
        elif item.kind == "ring":
            parts.append(
                f'<circle cx="{num(item.x)}" cy="{num(layout.legend_center_y)}" '
                f'r="{num(geom.prevRadius)}" fill="none" stroke="{settings.colors.prev}" '
                f'stroke-width="{num(geom.prevStrokeWidth)}"/>'
            )
        if item.text:
            parts.append(
                _text_element(item.text, item.text_x, layout.legend_baseline,
                              typo.legend, family)
            )

    parts.extend(_block(layout.footnote, family))
    parts.extend(_block(layout.source, family))

    parts.append("</svg>")
    return "".join(parts)
