#!/usr/bin/env bash
set -euo pipefail

APP_USER="${APP_USER:-appuser}"
APP_HOME="/home/${APP_USER}"
CTF_USER="${CTF_USER:-ctf}"
AUTHORIZED_SRC="${AUTHORIZED_KEYS_SRC:-/authorized_key.pem}"
AUTHORIZED_TARGET="${APP_HOME}/.ssh/authorized_keys"
SSH_DIR="$(dirname "$AUTHORIZED_TARGET")"
SSH_PORT="${SSH_PORT:-2222}"
SSH_PASSWORD="${SSH_PASSWORD:-helperpass123}"
FLASK_APP_PATH="${FLASK_APP:-app.py}"
FLASK_HOST="${HOST:-0.0.0.0}"
FLASK_PORT="${PORT:-8001}"
FLAG_PATH="${FLAG_PATH:-/flag.txt}"
FLAG_SEED_SRC="${FLAG_SEED_SRC:-/app/flag.txt}"
LOG_DIR="/app/logs"
ROTATOR_LOG="${FLAG_ROTATOR_LOG:-${LOG_DIR}/flag_rotator.log}"
FLASK_PID_FILE="/app/.flask.pid"
TAIL_PID=""
FLAG_ROTATOR_PID=""

prepare_authorized_keys() {
    if [[ -f "$AUTHORIZED_SRC" ]]; then
        mkdir -p "$SSH_DIR"
        cp "$AUTHORIZED_SRC" "$AUTHORIZED_TARGET"
        chown -R "$APP_USER:$APP_USER" "$SSH_DIR"
        chmod 700 "$SSH_DIR"
        chmod 600 "$AUTHORIZED_TARGET"
        echo "Loaded authorized keys from $AUTHORIZED_SRC"
    fi
}

configure_password_auth() {
    echo "${APP_USER}:${SSH_PASSWORD}" | chpasswd
}

prepare_flag_file() {
    local flag_dir
    flag_dir="$(dirname "$FLAG_PATH")"
    mkdir -p "$flag_dir"

    if [[ ! -f "$FLAG_PATH" ]]; then
        if [[ -f "$FLAG_SEED_SRC" ]]; then
            cp "$FLAG_SEED_SRC" "$FLAG_PATH"
        else
            touch "$FLAG_PATH"
        fi
    fi

    chown "$CTF_USER:$APP_USER" "$FLAG_PATH"
    chmod 640 "$FLAG_PATH"
    echo "Flag initialized at ${FLAG_PATH} (owned by ${CTF_USER})"
}

start_flag_rotator() {
    local disabled="${FLAG_ROTATOR_DISABLED:-0}"
    disabled="$(echo "$disabled" | tr '[:upper:]' '[:lower:]')"
    if [[ "$disabled" == "1" || "$disabled" == "true" || "$disabled" == "yes" ]]; then
        echo "Flag rotator disabled via FLAG_ROTATOR_DISABLED=${disabled}"
        return
    fi

    mkdir -p "$LOG_DIR"

    local args=(/app/rotate.py --output "$FLAG_PATH")
    [[ -n "${FLAG_ROTATOR_BASE_URL:-}" ]] && args+=(--base-url "$FLAG_ROTATOR_BASE_URL")
    [[ -n "${FLAG_ROTATOR_TOKEN:-}" ]] && args+=(--token "$FLAG_ROTATOR_TOKEN")
    [[ -n "${FLAG_ROTATOR_INTERVAL:-}" ]] && args+=(--interval "$FLAG_ROTATOR_INTERVAL")
    [[ -n "${FLAG_ROTATOR_OFFSET:-}" ]] && args+=(--offset "$FLAG_ROTATOR_OFFSET")

    : >"$ROTATOR_LOG"
    chown "$CTF_USER:$APP_USER" "$ROTATOR_LOG"
    echo "Starting flag rotator as ${CTF_USER} (log -> ${ROTATOR_LOG})"
    gosu "$CTF_USER" python "${args[@]}" >>"$ROTATOR_LOG" 2>&1 &
    FLAG_ROTATOR_PID=$!
}

start_sshd() {
    ssh-keygen -A >/dev/null 2>&1
    mkdir -p /var/run/sshd
    configure_password_auth
    /usr/sbin/sshd \
        -p "$SSH_PORT" \
        -o PermitRootLogin=no \
        -o PasswordAuthentication=yes \
        -o GatewayPorts=no \
        -o UsePAM=no \
        -o AllowUsers="$APP_USER"
}

start_flask() {
    echo "Launching Flask helper via run.sh (PID file -> ${FLASK_PID_FILE})."
    gosu "$APP_USER" /app/run.sh start
}

stop_flask() {
    echo "Stopping Flask helper via run.sh."
    gosu "$APP_USER" /app/run.sh stop >/dev/null 2>&1 || true
}

stop_flag_rotator() {
    if [[ -n "$FLAG_ROTATOR_PID" ]] && kill -0 "$FLAG_ROTATOR_PID" >/dev/null 2>&1; then
        echo "Stopping flag rotator (PID ${FLAG_ROTATOR_PID})."
        kill "$FLAG_ROTATOR_PID"
    fi
}

cleanup() {
    echo "Received shutdown signal; cleaning up."
    stop_flask || true
    stop_flag_rotator || true
    if [[ -n "$TAIL_PID" ]]; then
        kill "$TAIL_PID" >/dev/null 2>&1 || true
    fi
    exit 0
}

trap cleanup SIGINT SIGTERM

prepare_authorized_keys
prepare_flag_file
start_sshd
start_flag_rotator
start_flask

mkdir -p "$LOG_DIR"
touch "$LOG_DIR/server.log"
echo "Tailing logs/server.log to keep the container alive."
tail -n0 -F "$LOG_DIR/server.log" &
TAIL_PID=$!
wait "$TAIL_PID"
