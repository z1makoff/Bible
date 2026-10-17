#!/bin/sh
# Запуск читалки на Linux: сервер работает в фоне, браузер открывается сам.
# Если читалка уже запущена, просто открывается браузер. Журнал — user/server.log.
cd "$(dirname "$0")/.." || exit 1
PY=$(command -v python3 || command -v python)
if [ -z "$PY" ]; then
    echo "Для читалки нужен Python 3: sudo apt install python3" >&2
    exit 1
fi
mkdir -p user
nohup "$PY" app/server.py >> user/server.log 2>&1 &
