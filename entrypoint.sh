#!/bin/sh
# entrypoint.sh

# Если HOST не задан, используем 0.0.0.0
HOST=${HOST:-0.0.0.0}
PORT=${PORT:-8000}

# Запускаем uvicorn с переданными параметрами
exec uvicorn src.app:app --host $HOST --port $PORT
