#!/usr/bin/env bash
# Полная приёмка одной командой (ТЗ 13, 15).
#
#   bash scripts/acceptance.sh
#
# Переменные:
#   WDWS_PORT=8099    порт на хосте для шага «сервис отвечает» (по умолчанию 8080)
#   SKIP_BUILD=1      не пересобирать образ, использовать уже собранный
#
# Холодная сборка образа занимает несколько минут; повторная — секунды.
# Любая CI вызывает этот же скрипт, отдельной конфигурации не требуется.

set -euo pipefail

cd "$(dirname "$0")/.."

IMAGE="where-do-we-stand:1.0.0"
PORT="${WDWS_PORT:-8080}"
export WDWS_PORT="$PORT"
PYTHON="${PYTHON:-python}"

# Путь к репозиторию в виде, понятном docker: под Windows это C:/..., а не /c/...
# Тем же способом приводятся временные каталоги: curl и прочие нативные
# программы под Windows не понимают пути вида /tmp/xxx.
native_path() {
  if command -v cygpath >/dev/null 2>&1; then
    cygpath -m "$1"
  else
    printf '%s' "$1"
  fi
}

HOST_ROOT="$(native_path "$PWD")"

START_TS=$(date +%s)
STEP=0
TOTAL=6

log()  { printf '[%s +%4ds] %s\n' "$(date +%H:%M:%S)" "$(( $(date +%s) - START_TS ))" "$*"; }
step() { STEP=$((STEP + 1)); echo; log "=== $STEP/$TOTAL  $*"; }
ok()   { log "      ок — $*"; }
die()  { log "      ПРОВАЛ — $*"; exit 1; }

cleanup() {
  docker compose down --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

# Флаги docker и команда внутри контейнера разделяются «--»: иначе флаг
# со значением (--network none) съедает следующий аргумент и docker
# запускает образ с командой по умолчанию.
mounted_run() {
  local docker_flags=()
  while [[ $# -gt 0 && "$1" != "--" ]]; do
    docker_flags+=("$1")
    shift
  done
  [[ "${1:-}" == "--" ]] && shift

  # Git Bash переписал бы /src в C:/Program Files/Git/src. Подавление
  # ограничено вызовом docker: глобально оно ломает пути для curl.
  MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' \
  docker run --rm "${docker_flags[@]}" \
    -v "$HOST_ROOT:/src" -w /src \
    -e PYTHONPATH=/src/backend \
    -e PYTHONIOENCODING=utf-8 \
    -e WDWS_FONTS_DIR=/src/fonts \
    -e WDWS_PRESETS_DIR=/src/presets \
    -e WDWS_RESVG_BIN=/usr/local/bin/resvg \
    "$IMAGE" "$@"
}

# --- 1: окружение ------------------------------------------------------------

step "Окружение"

docker version --format '{{.Server.Version}}' >/dev/null 2>&1 \
  || die "Docker недоступен. Запустите Docker Desktop."
ok "docker $(docker version --format '{{.Server.Version}}')"

"$PYTHON" --version >/dev/null 2>&1 || die "python не найден в PATH"
ok "$("$PYTHON" --version)"

busy="$(docker ps --format '{{.Names}} {{.Ports}}' | grep ":${PORT}->" || true)"
if [[ -n "$busy" ]]; then
  log "      порт $PORT уже занят: $busy"
  die "Освободите порт или запустите с другим: WDWS_PORT=8099 bash scripts/acceptance.sh"
fi
ok "порт $PORT свободен"

# --- 2: тесты ----------------------------------------------------------------

step "Тесты на хосте"
(cd backend && "$PYTHON" -m pytest -q) || die "тесты не прошли"
ok "тесты прошли"

# --- 3: сборка ---------------------------------------------------------------

if [[ "${SKIP_BUILD:-}" == "1" ]]; then
  step "Сборка образа — пропущена (SKIP_BUILD=1)"
  docker image inspect "$IMAGE" >/dev/null 2>&1 || die "образ $IMAGE не собран"
  ok "используется собранный ранее образ"
else
  step "Сборка образа (холодная занимает несколько минут)"
  docker compose build || die "сборка образа не удалась"
  ok "образ собран, размер $(docker images "$IMAGE" --format '{{.Size}}')"
fi

# --- 4: эталоны --------------------------------------------------------------

step "Эталоны внутри контейнера"
mounted_run -- python scripts/update_golden.py --check || die "эталоны разошлись"
ok "SVG и хеши PNG совпали с эталонами"

# --- 5: без сети -------------------------------------------------------------

step "Работа без исходящей сети (критерий приёмки 2)"
mounted_run --network none -- python scripts/update_golden.py --check >/dev/null \
  || die "отрисовка без сети не работает"
ok "отрисовка не требует сети"

# --- 6: сервис ---------------------------------------------------------------

step "Сервис отвечает и отдаёт одинаковый PNG"

log "      поднимаю контейнер на порту $PORT"
docker compose up -d --wait || die "контейнер не поднялся"

base="http://127.0.0.1:${PORT}"
curl -fsS "$base/api/health" >/dev/null || die "/api/health не отвечает"
ok "/api/health отвечает"

tmp_dir="$(mktemp -d)"
tmp="$(native_path "$tmp_dir")"
curl -fsS "$base/api/template.xlsx" -o "$tmp/template.xlsx" || die "шаблон не отдаётся"
ok "шаблон получен ($(wc -c < "$tmp/template.xlsx") байт)"

parsed="$(curl -fsS -F "file=@$tmp/template.xlsx" "$base/api/data/parse")" \
  || die "шаблон не прошёл разбор"
settings="$("$PYTHON" -c "import urllib.request,sys; sys.stdout.write(urllib.request.urlopen('$base/api/settings/defaults').read().decode())")"

"$PYTHON" -c "
import json, sys
parsed = json.loads(sys.argv[1])
settings = json.loads(sys.argv[2])
assert parsed['ok'], parsed['errors']
json.dump({'rows': parsed['rows'], 'meta': parsed['meta'], 'settings': settings},
          open(sys.argv[3], 'w', encoding='utf-8'))
print(f\"      разобрано строк: {len(parsed['rows'])}, дата {parsed['meta']['as_of']}\")
" "$parsed" "$settings" "$tmp/body.json" || die "разбор шаблона вернул ошибки"

for name in a b; do
  curl -fsS -X POST "$base/api/render/png" \
    -H 'Content-Type: application/json' \
    --data-binary "@$tmp/body.json" -o "$tmp/$name.png" || die "отрисовка PNG не удалась"
done

if cmp -s "$tmp/a.png" "$tmp/b.png"; then
  ok "PNG побайтно совпадает между запросами ($(wc -c < "$tmp/a.png") байт)"
else
  die "PNG различается между запросами"
fi

rm -rf "$tmp_dir"

echo
log "Приёмка пройдена за $(( $(date +%s) - START_TS )) с."
