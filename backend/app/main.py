"""HTTP-слой (ТЗ 9, 11.3)."""

from __future__ import annotations

import base64
import json
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

from . import config, excel_reader, excel_template, palette, presets, raster, render
from .data_model import RenderRequest
from .fonts import get_registry
from .issues import Issue, Issues
from .settings_model import SETTINGS_VERSION, default_settings, json_schema
from .validate_settings import validate as validate_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("wdws")

@asynccontextmanager
async def lifespan(_: FastAPI):
    faces = get_registry(str(config.FONTS_DIR)).families()
    log.info(
        "шрифты: %s",
        ", ".join(
            f"{item['family']} ({', '.join(str(w) for w in item['weights'])})"
            for item in faces
        )
        or "не найдены",
    )
    log.info("растеризатор: %s (%s)", raster.binary_path(), raster.version())
    log.info("пресеты: %s", config.PRESETS_DIR)
    yield


app = FastAPI(
    title="Где мы находимся",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)


def registry():
    return get_registry(str(config.FONTS_DIR))


def envelope(issues: Issues, **extra) -> dict:
    return {
        "ok": issues.ok,
        "errors": [item.model_dump() for item in issues.errors],
        "warnings": [item.model_dump() for item in issues.warnings],
        **extra,
    }


def single_error(where: str, message: str, **extra) -> JSONResponse:
    body = {
        "ok": False,
        "errors": [Issue(level="error", where=where, message=message).model_dump()],
        "warnings": [],
        **extra,
    }
    return JSONResponse(body, status_code=422)


@app.middleware("http")
async def limit_and_log(request: Request, call_next):
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > config.MAX_UPLOAD_BYTES:
        # ТЗ 11.3: ограничение размера запроса.
        return JSONResponse(
            {
                "ok": False,
                "errors": [
                    {
                        "level": "error",
                        "where": "файл",
                        "message": f"Размер запроса превышает "
                        f"{config.MAX_UPLOAD_BYTES // (1024 * 1024)} МБ.",
                    }
                ],
                "warnings": [],
            },
            status_code=413,
        )

    started = time.perf_counter()
    response = await call_next(request)
    elapsed = (time.perf_counter() - started) * 1000
    if request.url.path.startswith("/api"):
        # Содержимое загруженных файлов и значения данных в лог не пишутся (ТЗ 12).
        log.info("%s %s -> %s за %.0f мс",
                 request.method, request.url.path, response.status_code, elapsed)
    return response


# --- служебные ------------------------------------------------------------


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/version")
async def version():
    faces = registry().families()
    return {
        "build": config.BUILD_VERSION,
        "settingsVersion": SETTINGS_VERSION,
        "rasterizer": raster.version(),
        "rasterizerAvailable": raster.available(),
        "fonts": faces,
    }


# --- данные ---------------------------------------------------------------


@app.get("/api/template.xlsx")
async def template():
    return Response(
        content=excel_template.build(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="gde-my-nahodimsya-template.xlsx"'},
    )


@app.post("/api/data/parse")
async def parse_data(file: UploadFile = File(...)):
    content = await file.read()
    if len(content) > config.MAX_UPLOAD_BYTES:
        return single_error(
            "файл",
            f"Файл больше {config.MAX_UPLOAD_BYTES // (1024 * 1024)} МБ. "
            "Удалите лишние листы и оформление.",
            rows=[],
            meta=None,
        )

    result = excel_reader.parse(content, file.filename or "")
    body = envelope(
        result.issues,
        rows=[row.model_dump() for row in result.rows],
        meta={"as_of": result.meta.as_of.isoformat()} if result.meta else None,
    )
    if result.meta is None and result.issues.ok:
        # Дата не прочиталась, но и ошибки не записалось — так быть не должно.
        body["ok"] = False
    return JSONResponse(body, status_code=200 if body["ok"] else 422)


# --- настройки ------------------------------------------------------------


@app.get("/api/settings/defaults")
async def settings_defaults():
    return default_settings().model_dump()


@app.get("/api/settings/schema")
async def settings_schema():
    return json_schema()


@app.post("/api/settings/validate")
async def settings_validate(request: Request):
    try:
        payload = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return single_error(
            "файл",
            f"Файл не является корректным JSON: {exc}. Откройте его в текстовом "
            "редакторе и проверьте запятые и кавычки.",
            settings=None,
        )
    settings, issues = validate_settings(payload, registry())
    body = envelope(issues, settings=settings.model_dump() if settings else None)
    return JSONResponse(body, status_code=200 if issues.ok else 422)


@app.get("/api/presets")
async def presets_list():
    return {"presets": presets.listing()}


@app.get("/api/presets/{name}")
async def preset_read(name: str):
    content, error = presets.read(name)
    if error:
        return single_error(f"пресет {name}", error)
    return content


@app.get("/api/palette")
async def palette_read():
    return palette.load()


@app.get("/api/fonts")
async def fonts_list():
    return {"families": registry().families()}


# --- отрисовка ------------------------------------------------------------


def _warnings_header(issues: Issues, required_height: float) -> dict[str, str]:
    """Предупреждения к бинарному ответу.

    Тело ответа — чистый PNG (ТЗ 3.1: скачивается ровно то, что показано
    в превью), поэтому сообщения уезжают заголовком в base64: кириллица
    в заголовке HTTP напрямую недопустима.
    """
    payload = json.dumps(
        [item.model_dump() for item in issues.warnings], ensure_ascii=False
    ).encode("utf-8")
    return {
        "X-Render-Warnings": base64.b64encode(payload).decode("ascii"),
        "X-Required-Height": f"{required_height:.0f}",
    }


@app.post("/api/render/png")
async def render_png(request: RenderRequest):
    started = time.perf_counter()
    svg, issues, required_height = render.render_svg(
        request.rows, request.meta, request.settings, registry()
    )
    if svg is None:
        return JSONResponse(envelope(issues), status_code=422)

    try:
        png = await raster.render_png_async(svg, request.settings.canvas.scale)
    except raster.RasterError as exc:
        log.error("растеризация не удалась: %s", exc)
        return single_error("растеризатор", str(exc))

    log.info(
        "png %dx%d scale=%d: %d КБ за %.0f мс",
        request.settings.canvas.width,
        request.settings.canvas.height,
        request.settings.canvas.scale,
        len(png) // 1024,
        (time.perf_counter() - started) * 1000,
    )
    return Response(
        content=png,
        media_type="image/png",
        headers=_warnings_header(issues, required_height),
    )


@app.post("/api/render/svg")
async def render_svg_file(request: RenderRequest):
    svg, issues, required_height = render.render_svg(
        request.rows, request.meta, request.settings, registry(), embed_fonts=True
    )
    if svg is None:
        return JSONResponse(envelope(issues), status_code=422)

    filename = f"gde-my-nahodimsya-{request.meta.as_of.isoformat()}.svg"
    headers = _warnings_header(issues, required_height)
    headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return Response(content=svg, media_type="image/svg+xml", headers=headers)


# --- статика --------------------------------------------------------------


if config.STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(config.STATIC_DIR), html=True), name="static")
else:
    @app.get("/")
    async def no_frontend():
        return PlainTextResponse(
            "Фронтенд не собран. Выполните `npm ci && npm run build` в каталоге frontend "
            f"либо укажите WDWS_STATIC_DIR. Ожидался каталог: {config.STATIC_DIR}",
            status_code=503,
        )
