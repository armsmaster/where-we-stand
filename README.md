# Где мы находимся

Внутренний сервис редакции: собирает еженедельную шапку — шкалы положения классов
активов в годовом диапазоне. Спецификация — [SPEC.md](SPEC.md).

Сервис умеет одну картинку и не должен уметь другие.

---

## Быстрый старт

```bash
docker compose up -d
```

Откроется на `http://<хост>:8080`.

Если порт занят чем-то другим, `docker compose` откажется стартовать
с `port is already allocated`. Задайте свободный:

```bash
WDWS_PORT=8099 docker compose up -d
```

Дальше: скачать шаблон Excel → заполнить → загрузить → скачать PNG.

---

## Как это устроено

**Превью и итоговый файл — один и тот же PNG.** Кнопка «Скачать PNG» сохраняет
байты, уже полученные для превью; повторного запроса к бэкенду нет. Поэтому
совпадение превью и результата не проверяется, а обеспечивается конструкцией.

**Всё, что попадает в картинку, приходит во входных данных.** В рендерере нет
обращений к системным часам, локали, переменным окружения и системным шрифтам.
Одинаковые файлы плюс один и тот же образ дают побайтно одинаковый PNG.

Отсюда следует практика: шрифты и бинарник растеризатора лежат в репозитории,
базовые образы закреплены по digest, зависимости — по версиям.

```
данные (.xlsx) ─┐
                ├─► проверка ─► раскладка ─► SVG ─► resvg ─► PNG
настройки (.json)┘
```

---

## Разработка

Нужны Python 3.12+ и Node 20+.

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r backend/requirements-dev.txt
cd frontend && npm ci && npm run build && cd ..
```

Бэкенд:

```bash
cd backend && python -m uvicorn app.main:app --reload --port 8000
```

Фронтенд с горячей перезагрузкой (запросы к `/api` проксируются на порт 8000):

```bash
cd frontend && npm run dev
```

Тесты:

```bash
cd backend && python -m pytest
```

Полная приёмка — тесты, сборка образа, сверка эталонов в контейнере, проверка
работы без сети и совпадения PNG между запросами:

```bash
bash scripts/acceptance.sh
```

Каждый шаг пишет в лог время и результат. С прогретым кешем сборки прогон
занимает около полутора минут, холодная сборка образа добавляет несколько минут.

| Переменная | Что делает |
|---|---|
| `WDWS_PORT=8099` | Порт для шага «сервис отвечает». Скрипт заранее проверяет, что порт свободен, и объясняет, если нет |
| `SKIP_BUILD=1` | Не пересобирать образ, взять собранный ранее |

---

## Каталоги

| Путь | Что внутри |
|---|---|
| `backend/app/` | Сервис: чтение Excel, проверки, раскладка, SVG, растеризация, HTTP |
| `backend/tests/` | Тесты, включая эталоны в `tests/golden/` |
| `frontend/` | SPA на ванильном JS, форма строится из JSON Schema |
| `fonts/` | Статические начертания Arimo и Inter, лицензии, `MANIFEST.json` с хешами |
| `vendor/resvg/` | Бинарники растеризатора под Linux и Windows, версия 0.47.0 |
| `presets/` | Утверждённое оформление и `palette.json`; монтируется в контейнер только на чтение |
| `scripts/` | Сборка шрифтов, пересборка и сверка эталонов, приёмка |

---

## Эталоны

Единственный механизм, который удерживает картинку от дрейфа на горизонте лет.

- `backend/tests/golden/*.svg` — разметка, сравнивается посимвольно. Платформы
  не различает, проверяется где угодно.
- `backend/tests/golden/png-linux.json` — хеши PNG. **Снимаются только внутри
  контейнера**: байты зависят от образа целиком, и на Windows они другие.

Сверка:

```bash
python scripts/update_golden.py --check
```

Пересборка после намеренного изменения отрисовки:

```bash
python scripts/update_golden.py            # SVG
docker run --rm -v "$PWD:/src" -w /src \
  -e PYTHONPATH=/src/backend -e WDWS_FONTS_DIR=/src/fonts \
  -e WDWS_PRESETS_DIR=/src/presets -e WDWS_RESVG_BIN=/usr/local/bin/resvg \
  where-do-we-stand:1.0.0 python scripts/update_golden.py   # + хеши PNG
```

Обновлять эталоны допустимо **только отдельным коммитом** с причиной в сообщении
и визуальной проверкой дифа.

---

## Шрифты

В образ вшиты **Arimo** (основной) и **Inter**, начертания 400/500/600, лицензия
SIL OFL 1.1 — файлы лицензий лежат рядом в `fonts/`.

Arial поставлять нельзя: шрифт принадлежит Monotype, прав на распространение
внутри контейнера у редакции нет. Arimo метрически совместима с Arial —
это и есть его вид с открытой лицензией. Liberation Sans не подошла: в ней
только 400 и 700, а схема типографики использует 400/500/600.

Начертания собираются из переменных шрифтов детерминированно:

```bash
python scripts/build_fonts.py
```

Хеши результата пишутся в `fonts/MANIFEST.json` и проверяются тестом.

---

## Переменные окружения

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `WDWS_PORT` | `8080` | Порт на хосте (только `docker-compose.yml`) |
| `WDWS_FONTS_DIR` | `/app/fonts` | Каталог шрифтов |
| `WDWS_PRESETS_DIR` | `/presets` | Каталог пресетов и палитры |
| `WDWS_STATIC_DIR` | `/app/static` | Собранный фронтенд |
| `WDWS_RESVG_BIN` | `/usr/local/bin/resvg` | Путь к растеризатору |
| `WDWS_RENDER_CONCURRENCY` | `4` | Одновременных растеризаций |
| `WDWS_RENDER_TIMEOUT` | `20` | Таймаут растеризации, секунды |
| `WDWS_BUILD_VERSION` | `dev` | Версия сборки, видна в `/api/version` |

---

## Развёртывание в изолированном контуре

Сеть нужна **только при сборке образа**. Работающий сервис в интернет не ходит —
шрифты, растеризатор и зависимости зафиксированы на этапе сборки. Проверяется
шагом 5 приёмки: отрисовка выполняется в контейнере с `--network none`.

### Три канала, а не один

Настройка только демона Docker — самая частая ошибка: базовые образы скачаются,
а `npm ci` внутри сборки повиснет на таймауте.

| Что ходит в сеть | Кто ходит | Зеркала (Nexus) | HTTP-прокси |
|---|---|---|---|
| `docker pull` базовых образов | демон Docker | `registry-mirrors` в настройках демона | настройки демона |
| `npm ci` и `pip wheel` | процессы внутри сборки | `.env` рядом с `docker-compose.yml` | `~/.docker/config.json` |
| работа сервиса | никто | ничего не нужно | ничего не нужно |

Пакеты через `apt` не ставятся: healthcheck работает на Python, который в образе
уже есть. Поэтому репозитории Debian — которые в контурах закрывают отдельно
от PyPI и npm — для сборки не требуются.

### Через внутренние зеркала (Nexus)

Основной путь, если npm, pip и Docker Hub проксируются через Nexus.

**npm и pip — через `.env`.** Скопируйте образец и подставьте адреса:

```bash
cp .env.example .env
```

```
WDWS_NPM_REGISTRY=https://nexus.corp/repository/npm-proxy/
WDWS_PIP_INDEX_URL=https://nexus.corp/repository/pypi-proxy/simple
```

`docker compose build` подхватит их автоматически. Dockerfile править не нужно:
адреса приходят аргументами сборки, npm и pip читают их сами и при пустом
значении берут умолчания. В итоговый образ аргументы не попадают.

Обратите внимание на `/simple` в конце адреса pip — без него индекс не найдётся.

**Docker Hub — двумя способами.** Предпочтительный: подключить Nexus
как registry-mirror в настройках демона.

Docker Desktop → Settings → Docker Engine:

```json
{ "registry-mirrors": ["https://nexus.corp:8082"] }
```

Linux: то же в `/etc/docker/daemon.json`, затем `sudo systemctl restart docker`.

Имена базовых образов при этом не меняются, digest проверяется как обычно,
`WDWS_REGISTRY` остаётся пустым.

Запасной способ, если зеркало приходится указывать именем образа, — префикс
в `.env` (со слэшем на конце; возможно, потребуется добавить `library/`):

```
WDWS_REGISTRY=nexus.corp:8082/
```

### Закрепление по digest и Nexus

Снимать закрепление не нужно — вопреки распространённому ожиданию, оно
с зеркалом совместимо.

Nexus в роли **proxy repository** отдаёт манифест байт-в-байт, поэтому digest
сохраняется, и закрепление работает при обоих способах выше. Digest изменится
только если образы **перезалиты** в hosted-репозиторий через
`docker pull` → `docker tag` → `docker push`: эта последовательность
пересобирает манифест. `skopeo copy` и `crane copy` копируют digest как есть.

Если digest всё же не совпал, сборка упадёт с `manifest unknown` — это
правильное поведение, а не помеха. Реакция: узнать digest внутреннего образа
и зафиксировать его в `FROM`, а не убирать `@sha256:`.

```bash
docker manifest inspect nexus.corp:8082/library/python:3.12-slim | grep -m1 digest
```

### Внутренний центр сертификации

Если зеркала отдаются с сертификатом внутреннего ЦС, сборка падает так:

```
npm error code UNABLE_TO_VERIFY_LEAF_SIGNATURE
npm error request to https://nexus.corp/... failed, reason: unable to verify the first certificate
```

Браузер на рабочей машине при этом зеркалу доверяет — ЦС установлен
в хранилище Windows. Но Node и pip его не видят: у каждого свой список ЦС.

Решение — положить цепочку сертификатов в **`certs/ca.pem`**. Сборка сама
передаст её npm (`NODE_EXTRA_CA_CERTS`) и pip (`PIP_CERT`). Файл игнорируется
git и монтируется только на время установки пакетов — в образ не попадает.
Как выгрузить цепочку из хранилища Windows и проверить её до сборки —
в [certs/README.md](certs/README.md).

Отключать проверку сертификатов вместо этого не нужно. Если pip сейчас
работает только благодаря `WDWS_PIP_TRUSTED_HOST` — это она и есть,
отключённая: после появления `certs/ca.pem` переменную можно очистить.

### Через HTTP-прокси

Если вместо зеркал обычный прокси, `.env` не нужен — настраиваются два места.

Демон, для базовых образов. Docker Desktop: Settings → Resources → Proxies →
Manual proxy configuration, внутренние адреса в Bypass. Linux с systemd:

```bash
sudo mkdir -p /etc/systemd/system/docker.service.d
sudo tee /etc/systemd/system/docker.service.d/http-proxy.conf <<'EOF'
[Service]
Environment="HTTP_PROXY=http://proxy.corp:3128"
Environment="HTTPS_PROXY=http://proxy.corp:3128"
Environment="NO_PROXY=localhost,127.0.0.1,.corp.local"
EOF
sudo systemctl daemon-reload && sudo systemctl restart docker
```

Сборка, для npm и pip. В `~/.docker/config.json` (на Windows —
`C:\Users\<вы>\.docker\config.json`) рядом с существующими ключами:

```json
"proxies": {
  "default": {
    "httpProxy": "http://proxy.corp:3128",
    "httpsProxy": "http://proxy.corp:3128",
    "noProxy": "localhost,127.0.0.1,.corp.local"
  }
}
```

BuildKit прокинет это в каждый `RUN` как `HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY`
и их строчные варианты. Это предопределённые build-аргументы, в образ они
не попадают.

### Проверка

```bash
docker compose build --progress=plain 2>&1 | grep -iE "Looking in indexes|nexus|manifest unknown|timed out|Could not resolve"
```

Строка `Looking in indexes: ...` от pip показывает фактически использованный
индекс — по ней видно, подхватилось зеркало или сборка ушла на pypi.org.

### Хранение образа

Собранный образ сохраняйте во внутренний реестр или архивом:

```bash
docker save where-do-we-stand:1.0.0 | gzip > where-do-we-stand-1.0.0.tar.gz
```

Рассчитывать на успешную пересборку из npm и pip через три года нельзя —
это не гипотеза, а норма.

---

## Регламент публикации

Картинку отправлять в Telegram **файлом, а не фотографией**. Фотографии
пережимаются и уменьшаются по длинной стороне — вся работа по детерминированному
рендерингу теряет смысл на последнем шаге.
