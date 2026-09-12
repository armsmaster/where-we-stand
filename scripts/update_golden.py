"""Пересборка эталонов (ТЗ 13).

Эталоны — это зафиксированный результат отрисовки. Их обновление
допустимо только отдельным коммитом с явным указанием причины
и визуальной проверкой дифа.

SVG собирается на любой платформе. Хеши PNG зависят от образа целиком,
поэтому снимаются только под Linux — то есть внутри контейнера.

    пересборка:  python scripts/update_golden.py
    проверка:    python scripts/update_golden.py --check

Режим --check ничего не пишет и годится для приёмки в контейнере,
где тестовых пакетов нет.
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "backend" / "tests"))

from app import config, raster, render  # noqa: E402
from app.fonts import get_registry  # noqa: E402
from app.settings_model import default_settings  # noqa: E402
from scenarios import GOLDEN_DIR, META, patched, scenarios  # noqa: E402


def main(check: bool = False) -> int:
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    registry = get_registry(str(config.FONTS_DIR))
    base = default_settings()

    png_hashes: dict[str, str] = {}
    png_path = GOLDEN_DIR / "png-linux.json"
    if png_path.exists():
        png_hashes = json.loads(png_path.read_text(encoding="utf-8"))

    on_linux = platform.system() == "Linux" and raster.available()
    failures = 0

    for name, (rows, patch) in scenarios().items():
        settings = patched(base, patch)
        svg, issues, _ = render.render_svg(rows, META, settings, registry)
        if svg is None:
            print(f"  {name}: пропущен, ошибки отрисовки:")
            for item in issues.errors:
                print(f"    {item.where}: {item.message}")
            return 1

        svg_path = GOLDEN_DIR / f"{name}.svg"
        line = f"  {name:10} svg {len(svg):>6} байт"

        if check:
            if not svg_path.exists():
                print(f"  {name}: нет эталона {svg_path.name}")
                failures += 1
                continue
            if svg != svg_path.read_text(encoding="utf-8"):
                print(f"  {name}: SVG разошёлся с эталоном")
                failures += 1
                continue
            line += "  ✓"
        else:
            svg_path.write_text(svg, encoding="utf-8")

        if on_linux:
            png = raster.render_png(svg, settings.canvas.scale)
            digest = hashlib.sha256(png).hexdigest()
            if check:
                if png_hashes.get(name) != digest:
                    print(f"  {name}: PNG разошёлся с эталоном")
                    print(f"    ожидалось: {png_hashes.get(name)}")
                    print(f"    получено:  {digest}")
                    failures += 1
                    continue
                line += " png ✓"
            else:
                png_hashes[name] = digest
                line += f"  png {len(png):>7} байт  {digest[:16]}…"
        print(line)

    if check:
        if failures:
            print(f"\nЭталоны разошлись: {failures}. Если изменение намеренное — "
                  "обновите их отдельным коммитом с указанием причины.")
            return 1
        if not on_linux:
            print("\nХеши PNG не проверялись: снимаются только в контейнере под Linux.")
        print("\nЭталоны совпали.")
        return 0

    if on_linux:
        png_path.write_text(
            json.dumps(png_hashes, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"\nХеши PNG записаны в {png_path.name}")
    else:
        print("\nХеши PNG не обновлены: снимаются только в контейнере под Linux.")

    return 0


if __name__ == "__main__":
    sys.exit(main(check="--check" in sys.argv))
