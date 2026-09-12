"""Валидация файла настроек (ТЗ 6.4).

Сообщения строятся по тому же принципу, что и для Excel: путь к полю,
что получено, что ожидалось. Проверяется весь файл целиком.
"""

from __future__ import annotations

from typing import Any, get_args, get_origin

from pydantic import BaseModel, ValidationError

from .colors import DELTA_E_THRESHOLD, delta_e
from .data_model import Row
from .fonts import FontRegistry
from .issues import Issues
from .settings_model import SETTINGS_VERSION, RowOverride, Settings


def validate(raw: Any, registry: FontRegistry) -> tuple[Settings | None, Issues]:
    issues = Issues()

    if not isinstance(raw, dict):
        issues.error("файл", "Ожидался объект JSON с настройками оформления.")
        return None, issues

    version = raw.get("version")
    if version is None:
        issues.error(
            "version",
            f"Поле `version` обязательно. Укажите `\"version\": {SETTINGS_VERSION}`.",
        )
        return None, issues
    if not isinstance(version, int) or isinstance(version, bool):
        issues.error(
            "version",
            f"Поле `version`: ожидалось целое число, получено «{version}».",
        )
        return None, issues
    if version != SETTINGS_VERSION:
        issues.error(
            "version",
            f"Файл настроек версии {version} не поддерживается. Сервис работает "
            f"с версией {SETTINGS_VERSION}. Сохраните настройки заново из интерфейса "
            "или возьмите пресет.",
        )
        return None, issues

    for path in _unknown_paths(raw, Settings):
        issues.warning(path, f"Поле `{path}` не входит в схему и проигнорировано.")

    try:
        settings = Settings.model_validate(raw)
    except ValidationError as exc:
        for error in exc.errors():
            path, message = _translate(error)
            issues.error(path, message)
        return None, issues

    _check_font(settings, registry, issues)
    _check_contrast(settings, issues)
    return settings, issues


def check_overrides_against_rows(settings: Settings, rows: list[Row], issues: Issues) -> None:
    """ТЗ 5.2: `rowOverrides` ссылается на ключ, которого нет в данных."""
    known = {row.key for row in rows}
    for key in settings.rowOverrides:
        if key not in known:
            issues.warning(
                f"rowOverrides.{key}",
                f"В настройках задано индивидуальное оформление для ключа `{key}`, "
                "которого нет в файле данных. Проверьте, не переименован ли он.",
            )


def _check_font(settings: Settings, registry: FontRegistry, issues: Issues) -> None:
    family = settings.typography.family
    if not registry.has_family(family):
        available = ", ".join(item["family"] for item in registry.families()) or "нет ни одного"
        issues.error(
            "typography.family",
            f"Шрифт «{family}» недоступен. Доступны: {available}.",
        )
        return

    weights = set(registry.weights_of(family))
    typo = settings.typography
    for name in ("title", "rowLabel", "value", "scaleEnds", "legend", "footnote"):
        style = getattr(typo, name)
        if style.weight not in weights:
            issues.warning(
                f"typography.{name}.weight",
                f"У шрифта «{family}» нет начертания {style.weight}. "
                f"Доступны: {', '.join(str(w) for w in sorted(weights))}. "
                "Будет использовано ближайшее.",
            )


def _check_contrast(settings: Settings, issues: Issues) -> None:
    """ТЗ 6.4: предупреждения о неразличимых цветах."""
    colors = settings.colors

    def compare(first: str, second: str, path: str, message: str) -> None:
        distance = delta_e(first, second)
        if distance < DELTA_E_THRESHOLD:
            issues.warning(path, f"{message} ΔE {distance:.0f} при пороге {DELTA_E_THRESHOLD:.0f}.")

    compare(
        colors.current, colors.prev, "colors.prev",
        "Цвета точки «сейчас» и кольца «неделю назад» слабо различимы — "
        "две точки остаются единственным носителем смысла картинки.",
    )
    compare(
        colors.current, colors.track, "colors.current",
        "Цвет точки «сейчас» слабо отличается от полосы шкалы — точка потеряется.",
    )
    compare(
        colors.prev, colors.track, "colors.prev",
        "Цвет кольца «неделю назад» слабо отличается от полосы шкалы — кольцо потеряется.",
    )

    for key, override in settings.rowOverrides.items():
        current = override.current or colors.current
        prev = override.prev or colors.prev
        track = override.track or colors.track
        compare(
            current, prev, f"rowOverrides.{key}",
            f"В строке `{key}` цвета точки и кольца слабо различимы.",
        )
        compare(
            current, track, f"rowOverrides.{key}",
            f"В строке `{key}` точка «сейчас» слабо отличается от полосы шкалы.",
        )


def _unknown_paths(raw: dict, model: type[BaseModel], prefix: str = "") -> list[str]:
    """Ключи входного JSON, которых нет в схеме.

    pydantic при extra="ignore" о выброшенных ключах не сообщает,
    а ТЗ 6.4 требует предупреждения.
    """
    found: list[str] = []
    fields = model.model_fields

    for key, value in raw.items():
        path = f"{prefix}{key}"
        if key not in fields:
            found.append(path)
            continue

        annotation = fields[key].annotation
        nested = _model_of(annotation)

        if nested is not None and isinstance(value, dict):
            found.extend(_unknown_paths(value, nested, prefix=f"{path}."))
        elif key == "rowOverrides" and isinstance(value, dict):
            for row_key, override in value.items():
                if isinstance(override, dict):
                    found.extend(
                        _unknown_paths(override, RowOverride, prefix=f"{path}.{row_key}.")
                    )
    return found


def _model_of(annotation: Any) -> type[BaseModel] | None:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    for argument in get_args(annotation):
        if isinstance(argument, type) and issubclass(argument, BaseModel):
            return argument
    if get_origin(annotation) is dict:
        return None
    return None


def _translate(error: dict) -> tuple[str, str]:
    path = ".".join(str(part) for part in error["loc"]) or "настройки"
    kind = error["type"]
    ctx = error.get("ctx") or {}
    value = error.get("input")

    if kind == "string_pattern_mismatch" and ctx.get("pattern", "").startswith("^#"):
        return path, (
            f"Поле `{path}`: значение «{value}» не является цветом. "
            "Ожидается формат #RRGGBB."
        )

    if kind in ("greater_than_equal", "less_than_equal", "greater_than", "less_than"):
        bound = ctx.get("ge", ctx.get("le", ctx.get("gt", ctx.get("lt"))))
        relation = {
            "greater_than_equal": f"не меньше {bound}",
            "less_than_equal": f"не больше {bound}",
            "greater_than": f"больше {bound}",
            "less_than": f"меньше {bound}",
        }[kind]
        return path, f"Поле `{path}`: ожидалось число {relation}, получено {value}."

    if kind == "literal_error":
        allowed = ctx.get("expected", "")
        return path, f"Поле `{path}`: получено «{value}», допустимо {allowed}."

    if kind == "missing":
        return path, f"Поле `{path}` обязательно и отсутствует."

    if kind == "extra_forbidden":
        return path, (
            f"Поле `{path}` не поддерживается. В индивидуальном оформлении строки "
            "допустимы только current, prev, connector и track."
        )

    if kind in ("string_too_long", "string_too_short"):
        limit = ctx.get("max_length", ctx.get("min_length"))
        word = "длиннее" if kind == "string_too_long" else "короче"
        return path, f"Поле `{path}`: строка {word} допустимого ({limit} символов)."

    if kind in ("int_parsing", "float_parsing", "int_type", "float_type"):
        return path, f"Поле `{path}`: ожидалось число, получено «{value}»."

    if kind == "bool_type" or kind == "bool_parsing":
        return path, f"Поле `{path}`: ожидалось true или false, получено «{value}»."

    if kind == "value_error":
        message = str(error.get("msg", "")).removeprefix("Value error, ")
        return path, f"Поле `{path}`: {message}."

    return path, f"Поле `{path}`: {error.get('msg', 'значение не принято')}."
