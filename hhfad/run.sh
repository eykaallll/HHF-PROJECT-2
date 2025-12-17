#!/usr/bin/env bash
set -euo pipefail

cmd="${1:-run}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$ROOT_DIR/.flask.pid"
LOG_FILE="$ROOT_DIR/logs/server.log"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8001}"
FLASK_APP_PATH="${FLASK_APP:-app.py}"

mkdir -p "$ROOT_DIR/logs"
touch "$LOG_FILE"

is_running() {
    [[ -f "$PID_FILE" ]] && ps -p "$(cat "$PID_FILE")" >/dev/null 2>&1
}

start_server() {
    if is_running; then
        echo "Server already running (PID $(cat "$PID_FILE"))."
        exit 0
    fi

    echo "Starting Flask app on ${HOST}:${PORT} (logs -> ${LOG_FILE})."
    (
        cd "$ROOT_DIR"
        FLASK_APP="$FLASK_APP_PATH" FLASK_RUN_HOST="$HOST" FLASK_RUN_PORT="$PORT" \
            nohup flask run --host "$HOST" --port "$PORT" \
            >>"$LOG_FILE" 2>&1 &
        echo $! >"$PID_FILE"
    )
}

stop_server() {
    if ! is_running; then
        echo "Server is not running."
        [[ "$cmd" == stop ]] && exit 0 || return
    else
        local pid
        pid="$(cat "$PID_FILE")"
        echo "Stopping Flask app (PID ${pid})."
        kill "$pid"
        rm -f "$PID_FILE"
    fi
}

case "$cmd" in
    run|start)
        start_server
        ;;
    stop)
        stop_server
        ;;
    restart)
        stop_server
        start_server
        ;;
    status)
        if is_running; then
            echo "Server running (PID $(cat "$PID_FILE"))."
        else
            echo "Server not running."
        fi
        ;;
    *)
        echo "Usage: $0 {run|start|stop|restart|status}"
        exit 1
        ;;
esac
