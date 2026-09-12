"""Сборка статических начертаний из переменных шрифтов.

ТЗ 6.3: в образ поставляются статические файлы по одному на начертание.
Переменные шрифты не используются — их поддержка в растеризаторе неполна
и является лишним источником различий между сборками.

Скрипт детерминирован: из одних и тех же исходников получаются
побайтно одинаковые файлы. Хеши результата пишутся в fonts/MANIFEST.json
и проверяются тестом test_fonts.py.

Запуск:
    python scripts/build_fonts.py

Исходники берутся из кеша .fontsrc/, при отсутствии скачиваются
по закреплённым ссылкам с проверкой sha256.
"""

from __future__ import annotations

import hashlib
import json
import sys
import urllib.request
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / ".fontsrc"
OUT_DIR = ROOT / "fonts"

# Фиксированная метка времени в head: иначе fontTools проставит текущую
# и пересборка шрифтов даст другие байты.
FIXED_TIMESTAMP = 3786912000  # 2024-01-01 в шкале head (секунды от 1904-01-01)

WEIGHTS = {400: "Regular", 500: "Medium", 600: "SemiBold"}

SOURCES = {
    "Arimo": {
        "url": "https://github.com/google/fonts/raw/main/ofl/arimo/Arimo%5Bwght%5D.ttf",
        "file": "Arimo[wght].ttf",
        "sha256": "e43898b143ec826ac8cb4034816458a7047fbe0836558de2a1f8c6223ae3e0ca",
        # Кроме wght у Arimo осей нет.
        "pin": {},
        "license_url": "https://github.com/google/fonts/raw/main/ofl/arimo/OFL.txt",
        "license_file": "OFL-Arimo.txt",
    },
    "Inter": {
        "url": "https://github.com/google/fonts/raw/main/ofl/inter/Inter%5Bopsz,wght%5D.ttf",
        "file": "Inter[opsz,wght].ttf",
        "sha256": "29160a80ff49ddcab2c97711247e08b1fab27a484a329ce8b813d820dc559031",
        # opsz закрепляем на значении по умолчанию: статическое начертание
        # не может подстраивать оптический размер под кегль.
        "pin": {"opsz": 14},
        "license_url": "https://github.com/google/fonts/raw/main/ofl/inter/OFL.txt",
        "license_file": "OFL-Inter.txt",
    },
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch(url: str, dest: Path, expected: str | None = None) -> None:
    if dest.exists() and (expected is None or sha256(dest) == expected):
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  скачивание {url}")
    with urllib.request.urlopen(url) as response:
        dest.write_bytes(response.read())
    if expected is not None:
        actual = sha256(dest)
        if actual != expected:
            raise SystemExit(
                f"Хеш {dest.name} не совпал.\n"
                f"  ожидалось: {expected}\n"
                f"  получено:  {actual}\n"
                "Исходник изменился — проверьте источник, прежде чем обновлять константу."
            )


def set_names(font: TTFont, family: str, style: str) -> None:
    """Приводит таблицу имён к схеме, которую однозначно понимает fontdb resvg."""
    name = font["name"]
    legacy_family = family if style == "Regular" else f"{family} {style}"
    values = {
        1: legacy_family,
        2: "Regular",
        4: f"{family} {style}",
        6: f"{family}-{style}".replace(" ", ""),
        16: family,
        17: style,
    }
    for name_id, value in values.items():
        # Windows/Unicode BMP и Macintosh Roman — обе платформы, чтобы
        # не зависеть от того, какую читает конкретный загрузчик.
        name.setName(value, name_id, 3, 1, 0x409)
        name.setName(value, name_id, 1, 0, 0)


def build_family(family: str, spec: dict) -> list[dict]:
    source = SRC_DIR / spec["file"]
    fetch(spec["url"], source, spec["sha256"])

    license_dest = OUT_DIR / spec["license_file"]
    fetch(spec["license_url"], license_dest)

    produced = []
    for weight, style in WEIGHTS.items():
        out_path = OUT_DIR / f"{family}-{style}.ttf"
        font = TTFont(source)
        font = instancer.instantiateVariableFont(
            font, {"wght": weight, **spec["pin"]}, updateFontNames=False, inplace=True
        )
        set_names(font, family, style)
        font["OS/2"].usWeightClass = weight
        font["head"].created = FIXED_TIMESTAMP
        font["head"].modified = FIXED_TIMESTAMP
        font.save(out_path)
        font.close()
        digest = sha256(out_path)
        size = out_path.stat().st_size
        print(f"  {out_path.name:28} {size:>8} байт  {digest[:16]}…")
        produced.append(
            {
                "file": out_path.name,
                "family": family,
                "style": style,
                "weight": weight,
                "size": size,
                "sha256": digest,
            }
        )
    return produced


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {"faces": [], "sources": {}}
    for family, spec in SOURCES.items():
        print(f"{family}:")
        manifest["faces"].extend(build_family(family, spec))
        manifest["sources"][family] = {
            "url": spec["url"],
            "sha256": spec["sha256"],
            "license": spec["license_file"],
        }
    manifest["faces"].sort(key=lambda f: (f["family"], f["weight"]))
    (OUT_DIR / "MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"\nЗаписано {len(manifest['faces'])} начертаний в {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
