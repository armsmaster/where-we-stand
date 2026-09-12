"""Раскладка картинки (ТЗ 7.3–7.7).

Здесь считается вся геометрия: где какой блок, где базовые линии,
где разорвать строку. Собственно SVG строится отдельно и уже
не принимает решений — так раскладку можно проверять без разбора разметки.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .data_model import Meta, Row
from .fonts import SAFETY_MARGIN, FontRegistry
from .issues import Issues
from .numbers import format_date, format_number, label_with_unit
from .settings_model import Settings, TextStyle


@dataclass
class TextBlock:
    lines: list[str]
    baselines: list[float]
    x: float
    anchor: str
    style: TextStyle


@dataclass
class RowLayout:
    row: Row
    label: str
    label_baseline: float
    track_y: float
    current_x: float
    prev_x: float
    draw_connector: bool
    value_text: str
    value_x: float
    value_anchor: str
    value_baseline: float
    min_text: str
    max_text: str
    ends_baseline: float
    track_color: str
    current_color: str
    prev_color: str
    connector_color: str


@dataclass
class LegendItem:
    kind: str
    """dot | ring | text"""
    x: float
    text: str
    text_x: float


@dataclass
class Layout:
    width: float
    height: float
    required_height: float
    track_start: float
    track_end: float
    title: TextBlock | None
    rows: list[RowLayout] = field(default_factory=list)
    legend_items: list[LegendItem] = field(default_factory=list)
    legend_baseline: float = 0.0
    legend_center_y: float = 0.0
    footnote: TextBlock | None = None
    source: TextBlock | None = None


def _baseline_in_line(top: float, style: TextStyle, line_height: float, registry: FontRegistry,
                      family: str) -> float:
    """Базовая линия внутри строки высотой size × lineHeight (полулидинг)."""
    ascent = registry.ascent_px(family, style.weight, style.size)
    descent = registry.descent_px(family, style.weight, style.size)
    line = style.size * line_height
    return top + (line - (ascent + descent)) / 2 + ascent


def wrap_lines(text: str, max_width: float, measure) -> tuple[list[str], bool]:
    """Перенос по словам. Внутри слова не переносим (ТЗ 7.6)."""
    if not text:
        return [], False
    words = text.split(" ")
    lines: list[str] = []
    current = ""
    overflow = False

    for word in words:
        candidate = f"{current} {word}".strip()
        if not current or measure(candidate) <= max_width:
            current = candidate
            continue
        lines.append(current)
        current = word

    if current:
        lines.append(current)

    for line in lines:
        if measure(line) > max_width:
            overflow = True
            break

    return lines, overflow


def build(rows: list[Row], meta: Meta, settings: Settings, registry: FontRegistry,
          issues: Issues) -> Layout:
    canvas = settings.canvas
    geom = settings.geometry
    typo = settings.typography
    family = typo.family
    pad = canvas.padding

    def measure(text: str, style: TextStyle) -> float:
        return registry.measure(text, family, style.weight, style.size)

    content_left = pad.left
    content_right = canvas.width - pad.right
    content_width = content_right - content_left

    track_start = pad.left + geom.labelColumnWidth
    track_end = content_right
    track_width = track_end - track_start

    if track_width <= 0:
        issues.error(
            "geometry.labelColumnWidth",
            f"Поле `geometry.labelColumnWidth`: при ширине холста {canvas.width} и полях "
            f"{pad.left}/{pad.right} на шкалу не остаётся места. Уменьшите ширину колонки "
            "подписей или увеличьте ширину холста.",
        )
        track_width = 1.0
        track_end = track_start + track_width

    cursor = float(pad.top)

    title_block: TextBlock | None = None
    if settings.toggles.showTitle and settings.texts.title:
        style = typo.title
        baseline = _baseline_in_line(cursor, style, geom.lineHeight, registry, family)
        title_block = TextBlock(
            lines=[settings.texts.title],
            baselines=[baseline],
            x=content_left,
            anchor="start",
            style=style,
        )
        cursor += style.size * geom.lineHeight + geom.titleGap

    label_budget = geom.labelColumnWidth - geom.labelGap
    row_layouts: list[RowLayout] = []

    for row in rows:
        track_y = cursor + geom.rowHeight / 2
        override = settings.rowOverrides.get(row.key)

        def pick(name: str, override=override) -> str:
            base = getattr(settings.colors, name)
            if override is None:
                return base
            return getattr(override, name) or base

        label = label_with_unit(row.label, row.unit)
        label_width = measure(label, typo.rowLabel) * SAFETY_MARGIN
        if label_width > label_budget:
            issues.warning(
                f"строка {row.key}",
                f"Подпись строки `{row.key}` шире колонки подписей "
                f"({label_width:.0f} px при доступных {label_budget:.0f} px) и наедет "
                "на шкалу. Сократите подпись или увеличьте `geometry.labelColumnWidth`.",
            )

        span = row.max - row.min
        current_x = track_start + (row.current - row.min) / span * track_width
        prev_x = track_start + (row.prev - row.min) / span * track_width

        value_text = format_number(row.current, row.decimals, settings.numberFormat)
        value_width = measure(value_text, typo.value) * SAFETY_MARGIN
        value_x, value_anchor = _clamp_label(current_x, value_width, track_start, track_end)

        row_layouts.append(
            RowLayout(
                row=row,
                label=label,
                label_baseline=track_y + registry.baseline_offset(
                    family, typo.rowLabel.weight, typo.rowLabel.size
                ),
                track_y=track_y,
                current_x=current_x,
                prev_x=prev_x,
                draw_connector=abs(current_x - prev_x) >= geom.currentRadius + geom.prevRadius,
                value_text=value_text,
                value_x=value_x,
                value_anchor=value_anchor,
                value_baseline=track_y - geom.valueOffset,
                min_text=format_number(row.min, row.decimals, settings.numberFormat),
                max_text=format_number(row.max, row.decimals, settings.numberFormat),
                ends_baseline=track_y + geom.scaleEndsOffset,
                track_color=pick("track"),
                current_color=pick("current"),
                prev_color=pick("prev"),
                connector_color=pick("connector"),
            )
        )
        cursor += geom.rowHeight

    layout = Layout(
        width=canvas.width,
        height=canvas.height,
        required_height=0.0,
        track_start=track_start,
        track_end=track_end,
        title=title_block,
        rows=row_layouts,
    )

    tail_first = True

    if settings.toggles.showLegend:
        cursor += geom.legendGap if tail_first else geom.footnoteGap
        tail_first = False
        style = typo.legend
        line = style.size * geom.lineHeight
        layout.legend_center_y = cursor + line / 2
        layout.legend_baseline = _baseline_in_line(cursor, style, geom.lineHeight, registry, family)
        layout.legend_items = _legend_items(settings, measure, content_left)
        cursor += line

    if settings.toggles.showFootnote and settings.texts.footnote:
        cursor += geom.legendGap if tail_first else geom.footnoteGap
        tail_first = False
        layout.footnote, cursor = _paragraph(
            settings.texts.footnote, typo.footnote, cursor, content_left, content_width,
            geom.lineHeight, registry, family, measure, issues, "texts.footnote"
        )

    if settings.toggles.showSource and settings.texts.source:
        cursor += geom.legendGap if tail_first else geom.footnoteGap
        tail_first = False
        source_text = settings.texts.source.replace("{as_of}", format_date(meta.as_of))
        layout.source, cursor = _paragraph(
            source_text, typo.footnote, cursor, content_left, content_width,
            geom.lineHeight, registry, family, measure, issues, "texts.source"
        )

    layout.required_height = cursor + pad.bottom

    if layout.required_height > canvas.height + 0.5:
        issues.warning(
            "canvas.height",
            f"Заданной высоты холста ({canvas.height} px) не хватает: для размещения всех "
            f"элементов нужно {layout.required_height:.0f} px. Автоматическое сжатие "
            "запрещено — увеличьте `canvas.height` или сократите тексты.",
        )

    return layout


def _clamp_label(center: float, width: float, left: float, right: float) -> tuple[float, str]:
    """ТЗ 7.5: подпись прижимается к границе, обрезка не допускается."""
    half = width / 2
    if center - half < left:
        return left, "start"
    if center + half > right:
        return right, "end"
    return center, "middle"


def _legend_items(settings: Settings, measure, left: float) -> list[LegendItem]:
    geom = settings.geometry
    style = settings.typography.legend
    texts = settings.texts
    gap_after_sample = 7.0

    items: list[LegendItem] = []
    x = left

    items.append(
        LegendItem(kind="dot", x=x + geom.currentRadius, text=texts.legendCurrent,
                   text_x=x + 2 * geom.currentRadius + gap_after_sample)
    )
    x += 2 * geom.currentRadius + gap_after_sample + measure(texts.legendCurrent, style)
    x += geom.legendItemGap

    items.append(
        LegendItem(kind="ring", x=x + geom.prevRadius, text=texts.legendPrev,
                   text_x=x + 2 * geom.prevRadius + gap_after_sample)
    )
    x += 2 * geom.prevRadius + gap_after_sample + measure(texts.legendPrev, style)
    x += geom.legendItemGap

    if texts.legendScale:
        items.append(LegendItem(kind="text", x=x, text=texts.legendScale, text_x=x))

    return items


def _paragraph(text: str, style: TextStyle, top: float, left: float, width: float,
               line_height: float, registry: FontRegistry, family: str, measure,
               issues: Issues, field_path: str) -> tuple[TextBlock, float]:
    lines, overflow = wrap_lines(
        text, width / SAFETY_MARGIN, lambda t: measure(t, style)
    )
    if overflow:
        issues.warning(
            field_path,
            f"Поле `{field_path}`: в тексте есть слово, которое не помещается в ширину "
            "области отрисовки целиком, и оно выступит за границу. Сократите слово "
            "или увеличьте ширину холста.",
        )
    baselines = []
    cursor = top
    for _ in lines:
        baselines.append(_baseline_in_line(cursor, style, line_height, registry, family))
        cursor += style.size * line_height
    return TextBlock(lines=lines, baselines=baselines, x=left, anchor="start", style=style), cursor
