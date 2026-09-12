"""Растеризация SVG в PNG (ТЗ 3.2, 12).

resvg вызывается как отдельный процесс через stdin/stdout — временные файлы
не создаются. Системные шрифты отключены явно: если растеризатор способен
подобрать шрифт из системы, воспроизводимость не гарантируется (ТЗ 3.2).
"""

from __future__ import annotations

import asyncio
import struct
import subprocess
from pathlib import Path

from . import config

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

# Критические чанки и прозрачность. Всё остальное — метаданные,
# среди которых бывают изменяющиеся поля (ТЗ 12).
KEEP_CHUNKS = {b"IHDR", b"PLTE", b"tRNS", b"IDAT", b"IEND"}

_semaphore: asyncio.Semaphore | None = None


class RasterError(RuntimeError):
    pass


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(config.RENDER_CONCURRENCY)
    return _semaphore


def binary_path() -> Path:
    return Path(config.RESVG_BIN)


def available() -> bool:
    return binary_path().is_file()


def version() -> str:
    if not available():
        return "недоступен"
    try:
        result = subprocess.run(
            [str(binary_path()), "--version"],
            capture_output=True,
            timeout=10,
            check=False,
        )
        return result.stdout.decode("utf-8", "replace").strip() or "неизвестно"
    except OSError:
        return "недоступен"


def strip_metadata(data: bytes) -> bytes:
    """Оставляет только те чанки, без которых PNG не картинка.

    Гарантия побайтного совпадения (ТЗ 12) не должна зависеть от того,
    что именно растеризатор решит записать в служебные поля.
    """
    if not data.startswith(PNG_SIGNATURE):
        raise RasterError("Растеризатор вернул данные, не похожие на PNG.")

    output = bytearray(PNG_SIGNATURE)
    offset = len(PNG_SIGNATURE)

    while offset + 8 <= len(data):
        (length,) = struct.unpack(">I", data[offset : offset + 4])
        chunk_type = data[offset + 4 : offset + 8]
        end = offset + 12 + length
        if end > len(data):
            raise RasterError("PNG оборван: длина чанка выходит за границы данных.")
        if chunk_type in KEEP_CHUNKS:
            output += data[offset:end]
        offset = end
        if chunk_type == b"IEND":
            break

    return bytes(output)


def render_png(svg: str, scale: int) -> bytes:
    if not available():
        raise RasterError(
            f"Растеризатор не найден по пути {binary_path()}. "
            "Проверьте, что бинарник resvg на месте, либо задайте WDWS_RESVG_BIN."
        )

    command = [
        str(binary_path()),
        "--skip-system-fonts",
        "--use-fonts-dir",
        str(config.FONTS_DIR),
        "--zoom",
        str(scale),
        "--quiet",
        "-",
        "-c",
    ]

    try:
        result = subprocess.run(
            command,
            input=svg.encode("utf-8"),
            capture_output=True,
            timeout=config.RENDER_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RasterError(
            f"Растеризация не уложилась в {config.RENDER_TIMEOUT:.0f} с."
        ) from exc
    except OSError as exc:
        raise RasterError(f"Не удалось запустить растеризатор: {exc}") from exc

    if result.returncode != 0:
        message = result.stderr.decode("utf-8", "replace").strip()
        raise RasterError(f"Растеризатор завершился с ошибкой: {message or 'без сообщения'}")

    return strip_metadata(result.stdout)


async def render_png_async(svg: str, scale: int) -> bytes:
    async with _get_semaphore():
        return await asyncio.to_thread(render_png, svg, scale)
