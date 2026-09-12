# Сервис генерации шапки «Где мы находимся».
#
# Базовые образы закреплены по digest, а не по тегу: тег переезжает,
# digest — нет, а от него зависит побайтная воспроизводимость PNG (ТЗ 1.1, 11.4).

# --- этап 1: сборка фронтенда ------------------------------------------------
FROM node:22-alpine@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32 AS frontend

WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- этап 2: зависимости Python ----------------------------------------------
FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea AS deps

WORKDIR /wheels
COPY backend/requirements.txt ./
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

# --- этап 3: итоговый образ --------------------------------------------------
FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea

ARG BUILD_VERSION=dev

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    WDWS_FONTS_DIR=/app/fonts \
    WDWS_PRESETS_DIR=/presets \
    WDWS_STATIC_DIR=/app/static \
    WDWS_RESVG_BIN=/usr/local/bin/resvg \
    WDWS_BUILD_VERSION=${BUILD_VERSION}

# curl нужен только healthcheck'у из docker-compose.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=deps /wheels /wheels
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels requirements.txt

# Растеризатор вендорится в репозиторий (ТЗ 3.2): отдельного канала
# скачивания при сборке не требуется, изолированному контуру хватит
# прокси для pip, npm и docker.
COPY vendor/resvg/linux-x86_64/resvg /usr/local/bin/resvg
RUN chmod +x /usr/local/bin/resvg && resvg --version

# Шрифты — внутри образа. Системные при отрисовке отключены явно,
# поэтому этот каталог является единственным их источником (ТЗ 3.2, 6.3).
COPY fonts/ /app/fonts/

COPY backend/app/ /app/app/
COPY --from=frontend /build/dist/ /app/static/

# Пресеты монтируются томом; копия внутри образа — запасной вариант
# на случай запуска без тома.
COPY presets/ /presets/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]
