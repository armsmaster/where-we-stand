# Сервис генерации шапки «Где мы находимся».
#
# Базовые образы закреплены по digest, а не по тегу: тег переезжает,
# digest — нет, а от него зависит побайтная воспроизводимость PNG (ТЗ 1.1, 11.4).
#
# Сборка через внутренние зеркала (Nexus и подобные) настраивается
# аргументами ниже — править Dockerfile для этого не нужно. Значения удобно
# держать в файле .env рядом с docker-compose.yml, см. .env.example.
#
# Требуется BuildKit (включён по умолчанию в docker compose v2) — из-за
# кеш-монтирований, см. ниже.
#
# Корпоративный центр сертификации. Если зеркала отдаются с сертификатом
# внутреннего ЦС, положите всю цепочку одним файлом в certs/ca.pem — npm и pip
# будут проверять TLS по ней. Файл монтируется только на время команды и не
# попадает ни в слои образа, ни в git. Отключать проверку сертификатов
# (strict-ssl=false, PIP_TRUSTED_HOST) вместо этого не нужно. Без файла
# сборка ведёт себя как раньше.

# Префикс реестра для базовых образов. Пусто — Docker Hub напрямую.
# Не требуется, если Nexus подключён как registry-mirror: тогда имена
# образов остаются прежними и digest проверяется как обычно.
ARG REGISTRY=

# --- этап 1: сборка фронтенда ------------------------------------------------
FROM ${REGISTRY}node:22-alpine@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32 AS frontend

# Адрес npm-репозитория. Пусто — registry.npmjs.org: npm читает переменную
# сам и при пустом значении берёт умолчание, поэтому условий здесь нет.
ARG NPM_CONFIG_REGISTRY=

WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./

# Кеш загрузок npm живёт в кеше BuildKit, а не в слое образа: правка соседних
# строк Dockerfile сбрасывает слой, но не заставляет качать пакеты заново.
# NODE_EXTRA_CA_CERTS дополняет встроенный список ЦС, а не заменяет его.
RUN --mount=type=cache,target=/root/.npm \
    --mount=type=bind,source=certs,target=/certs \
    if [ -f /certs/ca.pem ]; then export NODE_EXTRA_CA_CERTS=/certs/ca.pem; fi; \
    npm ci --no-audit --no-fund

COPY frontend/ ./
RUN npm run build

# --- этап 2: итоговый образ --------------------------------------------------
FROM ${REGISTRY}python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea

ARG BUILD_VERSION=dev

# Адрес индекса пакетов. Пусто — pypi.org: pip читает переменные сам
# и при пустом значении берёт умолчание.
ARG PIP_INDEX_URL=
ARG PIP_TRUSTED_HOST=

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    WDWS_FONTS_DIR=/app/fonts \
    WDWS_PRESETS_DIR=/presets \
    WDWS_STATIC_DIR=/app/static \
    WDWS_RESVG_BIN=/usr/local/bin/resvg \
    WDWS_BUILD_VERSION=${BUILD_VERSION}

# Пакеты через apt не ставятся сознательно. Единственным кандидатом был curl
# для healthcheck'а, но его заменяет Python, который в образе уже есть.
# Так при сборке в изолированном контуре нужны ровно три канала — docker, pip
# и npm, — а репозитории Debian, которые закрывают отдельно от PyPI и npm,
# не требуются вовсе.

WORKDIR /app

# Зависимости ставятся одним проходом прямо в итоговый образ. Отдельный этап
# со сборкой колёс был бы уместен, если бы что-то компилировалось из исходников,
# но у всех зависимостей есть готовые manylinux-колёса. Зато промежуточный
# `COPY /wheels` оставлял в истории образа 10,5 МБ, удаляемых следующей строкой.
#
# Кеш pip — в кеше BuildKit: в слой он не попадает, поэтому `--no-cache-dir`
# не нужен, а повторная сборка не качает пакеты заново.
#
# PIP_CERT, в отличие от NODE_EXTRA_CA_CERTS, заменяет встроенный список ЦС.
# Это корректно, пока все запросы pip идут в зеркало, подписанное тем же ЦС, —
# а certs/ca.pem и нужен только там, где зеркало есть.
COPY backend/requirements.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=bind,source=certs,target=/certs \
    if [ -f /certs/ca.pem ]; then export PIP_CERT=/certs/ca.pem; fi; \
    pip install -r requirements.txt \
    && rm requirements.txt

# Растеризатор вендорится в репозиторий (ТЗ 3.2): отдельного канала
# скачивания при сборке не требуется.
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
