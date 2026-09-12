"""Реестр шрифтов и измерение текста (ТЗ 6.3, 7.1).

SVG не умеет ни переносить текст по словам, ни сообщать ширину строки,
а браузера на бэкенде нет. Поэтому ширина считается по метрикам шрифта
средствами fontTools: сумма горизонтальных ширин глифов, масштабированная
на кегль. Результат детерминирован и не зависит от окружения.

Точность. Растеризатор выполняет собственный шейпинг и может применить
кернинг из GPOS, которого здесь нет. Для Arimo и Inter расхождение
на латинице и кириллице не превышает долей процента, а измерение влияет
только на решения раскладки (прижать подпись к краю, где разорвать строку),
но не на итоговое положение текста — центрирование выполняет сам
растеризатор через text-anchor. Запас SAFETY_MARGIN закрывает расхождение.
"""

from __future__ import annotations

import base64
import functools
from dataclasses import dataclass
from pathlib import Path

from fontTools.ttLib import TTFont

# Запас при проверках «помещается ли»: измерение без GPOS-кернинга
# может слегка занижать ширину.
SAFETY_MARGIN = 1.015


@dataclass(frozen=True)
class Face:
    family: str
    weight: int
    path: Path
    units_per_em: int
    ascent: float
    """Доля em над базовой линией, положительная."""
    descent: float
    """Доля em под базовой линией, положительная."""
    cap_height: float
    """Доля em от базовой линии до верха прописных."""


class FontRegistry:
    def __init__(self, fonts_dir: Path) -> None:
        self.fonts_dir = fonts_dir
        self._faces: dict[tuple[str, int], Face] = {}
        self._advances: dict[tuple[str, int], dict[str, float]] = {}
        self._fallback_advance: dict[tuple[str, int], float] = {}
        self._load()

    def _load(self) -> None:
        if not self.fonts_dir.is_dir():
            return
        for path in sorted(self.fonts_dir.glob("*.ttf")):
            try:
                font = TTFont(path, lazy=True)
            except Exception:
                continue
            try:
                family = self._name(font, 16) or self._name(font, 1)
                if not family:
                    continue
                os2 = font["OS/2"]
                head = font["head"]
                upem = head.unitsPerEm
                ascent = getattr(os2, "sTypoAscender", None)
                descent = getattr(os2, "sTypoDescender", None)
                if ascent is None or descent is None:
                    hhea = font["hhea"]
                    ascent, descent = hhea.ascent, hhea.descent
                cap = getattr(os2, "sCapHeight", None) or int(0.7 * upem)
                face = Face(
                    family=family,
                    weight=int(os2.usWeightClass),
                    path=path,
                    units_per_em=upem,
                    ascent=ascent / upem,
                    descent=abs(descent) / upem,
                    cap_height=cap / upem,
                )
                self._faces[(face.family, face.weight)] = face
            finally:
                font.close()

    @staticmethod
    def _name(font: TTFont, name_id: int) -> str | None:
        record = font["name"].getDebugName(name_id)
        return record or None

    # --- публичный интерфейс ---------------------------------------------

    @property
    def is_empty(self) -> bool:
        return not self._faces

    def families(self) -> list[dict]:
        """Для `/api/fonts` и для валидации настроек."""
        grouped: dict[str, list[int]] = {}
        for family, weight in self._faces:
            grouped.setdefault(family, []).append(weight)
        return [
            {"family": family, "weights": sorted(weights)}
            for family, weights in sorted(grouped.items())
        ]

    def has_family(self, family: str) -> bool:
        return any(f == family for f, _ in self._faces)

    def weights_of(self, family: str) -> list[int]:
        return sorted(w for f, w in self._faces if f == family)

    def face(self, family: str, weight: int) -> Face:
        if (family, weight) in self._faces:
            return self._faces[(family, weight)]
        available = self.weights_of(family)
        if not available:
            raise KeyError(f"шрифт {family!r} не найден")
        # Ближайшее доступное начертание — чтобы отрисовка не падала,
        # если настройки прошли валидацию раньше подмены каталога шрифтов.
        nearest = min(available, key=lambda w: abs(w - weight))
        return self._faces[(family, nearest)]

    def _advance_table(self, family: str, weight: int) -> dict[str, float]:
        face = self.face(family, weight)
        cache_key = (face.family, face.weight)
        if cache_key in self._advances:
            return self._advances[cache_key]

        font = TTFont(face.path, lazy=True)
        try:
            cmap = font.getBestCmap()
            hmtx = font["hmtx"]
            upem = face.units_per_em
            table: dict[str, float] = {}
            for code, glyph_name in cmap.items():
                try:
                    table[chr(code)] = hmtx[glyph_name][0] / upem
                except KeyError:
                    continue
            try:
                fallback = hmtx[".notdef"][0] / upem
            except KeyError:
                fallback = 0.5
        finally:
            font.close()

        self._advances[cache_key] = table
        self._fallback_advance[cache_key] = fallback
        return table

    def measure(self, text: str, family: str, weight: int, size: float) -> float:
        """Ширина строки в пикселях при заданном кегле."""
        if not text:
            return 0.0
        face = self.face(family, weight)
        table = self._advance_table(family, weight)
        fallback = self._fallback_advance[(face.family, face.weight)]
        total = 0.0
        for char in text:
            total += table.get(char, fallback)
        return total * size

    def baseline_offset(self, family: str, weight: int, size: float) -> float:
        """Сдвиг базовой линии от вертикального центра строки.

        Центрируем по высоте прописных: для однострочных подписей рядом
        с тонкой полосой это выглядит правильнее, чем центрирование
        по полной высоте с учётом выносных элементов.
        """
        face = self.face(family, weight)
        return face.cap_height * size / 2

    def ascent_px(self, family: str, weight: int, size: float) -> float:
        return self.face(family, weight).ascent * size

    def descent_px(self, family: str, weight: int, size: float) -> float:
        return self.face(family, weight).descent * size

    def font_face_css(self, family: str) -> str:
        """`@font-face` с base64 — только для скачиваемого SVG (ТЗ 9).

        В SVG, который уходит растеризатору, шрифты не встраиваются:
        resvg берёт их из каталога, а base64 раздул бы каждый запрос.
        """
        blocks = []
        for weight in self.weights_of(family):
            face = self._faces[(family, weight)]
            payload = base64.b64encode(face.path.read_bytes()).decode("ascii")
            blocks.append(
                "@font-face{"
                f"font-family:'{family}';"
                f"font-style:normal;font-weight:{weight};"
                f"src:url(data:font/ttf;base64,{payload}) format('truetype');"
                "}"
            )
        return "".join(blocks)


@functools.lru_cache(maxsize=1)
def get_registry(fonts_dir: str) -> FontRegistry:
    return FontRegistry(Path(fonts_dir))
