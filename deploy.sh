#!/bin/bash
# deploy.sh — развёртывание MAX Booking Bot.
#
# Использование:
#   ./deploy.sh              # пользователь maxbot, hardening (боевой сервер)
#   ./deploy.sh --root       # root, без hardening (тест/отладка)
#
# Что делает:
#   1. Ставит Python 3.12 в /opt/python3.12 (если ещё нет).
#      На Ubuntu 24.04 берёт системный python3.12 — сборка не нужна.
#   2. Создаёт venv, ставит зависимости.
#   3. Создаёт пользователя maxbot (если не --root), даёт права.
#   4. Пишет systemd-unit, запускает сервис.
#
# Запускать от root: sudo ./deploy.sh

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_VERSION="3.12.9"
PYTHON_PREFIX="/opt/python3.12"
SERVICE_USER="maxbot"
SERVICE_NAME="max-bot"

RUN_AS_ROOT=false
for arg in "$@"; do
    case "$arg" in
        --root) RUN_AS_ROOT=true ;;
        -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    esac
done

log() { echo ">>> $*"; }
fail() { echo "!!! $*" >&2; exit 1; }

[ "$EUID" -eq 0 ] || fail "Запускать от root: sudo ./deploy.sh"
[ -f "$PROJECT_DIR/.env" ] || fail "Нет .env — сначала: cp .env.example .env && nano .env"
[ -f "$PROJECT_DIR/requirements.txt" ] || fail "Нет requirements.txt"

# ---------- 1. Python 3.12 ----------
if [ -x "$PYTHON_PREFIX/bin/python3.12" ]; then
    log "Python уже есть: $($PYTHON_PREFIX/bin/python3.12 --version)"
elif [ -x /usr/bin/python3.12 ]; then
    log "Используем системный /usr/bin/python3.12"
    PYTHON_PREFIX=""
else
    log "Устанавливаем зависимости для сборки..."
    apt update -q
    apt install -y -q build-essential wget \
        libssl-dev zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev \
        libffi-dev liblzma-dev libncurses5-dev libgdbm-dev libnss3-dev \
        uuid-dev tk-dev

    log "Собираем Python $PYTHON_VERSION в $PYTHON_PREFIX..."
    cd /tmp
    [ -f "Python-$PYTHON_VERSION.tgz" ] || \
        wget -q "https://www.python.org/ftp/python/$PYTHON_VERSION/Python-$PYTHON_VERSION.tgz"
    tar -xzf "Python-$PYTHON_VERSION.tgz"
    cd "Python-$PYTHON_VERSION"
    ./configure --prefix="$PYTHON_PREFIX" --enable-optimizations --with-ensurepip=install
    make -j"$(nproc)"
    make install
    cd "$PROJECT_DIR"
fi

if [ -n "$PYTHON_PREFIX" ]; then
    PYTHON_BIN="$PYTHON_PREFIX/bin/python3.12"
else
    PYTHON_BIN="/usr/bin/python3.12"
fi
log "Python: $($PYTHON_BIN --version)"

# ---------- 2. venv ----------
log "Создаём venv..."
rm -rf "$PROJECT_DIR/venv"
"$PYTHON_BIN" -m venv "$PROJECT_DIR/venv"
"$PROJECT_DIR/venv/bin/pip" install -q --upgrade pip
"$PROJECT_DIR/venv/bin/pip" install -q -r "$PROJECT_DIR/requirements.txt"

# ---------- 3. Пользователь и права ----------
if ! $RUN_AS_ROOT; then
    log "Создаём пользователя $SERVICE_USER..."
    id "$SERVICE_USER" >/dev/null 2>&1 || \
        useradd -r -s /usr/sbin/nologin -d "$PROJECT_DIR" -M "$SERVICE_USER"

    log "Даём права на проект..."
    chown -R "$SERVICE_USER:$SERVICE_USER" "$PROJECT_DIR"
    chmod 750 "$PROJECT_DIR"
    chmod 600 "$PROJECT_DIR/.env"
    find "$PROJECT_DIR" -name "*.py" -exec chmod 644 {} \;
    find "$PROJECT_DIR" -name "*.db" -exec chmod 660 {} \;
    [ -d "$PROJECT_DIR/static" ] && {
        find "$PROJECT_DIR/static" -type f -exec chmod 644 {} \;
        find "$PROJECT_DIR/static" -type d -exec chmod 755 {} \;
    }
fi

# ---------- 4. Systemd unit ----------
log "Пишем unit..."
if $RUN_AS_ROOT; then
    USER_BLOCK=""
    HARDENING=""
else
    USER_BLOCK="User=$SERVICE_USER
Group=$SERVICE_USER"
    HARDENING="
# Hardening
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
ReadWritePaths=$PROJECT_DIR
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictSUIDSGID=yes
LockPersonality=yes"
fi

cat > "/etc/systemd/system/$SERVICE_NAME.service" <<EOF
[Unit]
Description=MAX Booking Bot
After=network.target

[Service]
Type=simple
${USER_BLOCK}
WorkingDirectory=$PROJECT_DIR
EnvironmentFile=$PROJECT_DIR/.env
ExecStart=$PROJECT_DIR/venv/bin/uvicorn app:app --host 127.0.0.1 --port 8080
Restart=always
RestartSec=5
${HARDENING}

[Install]
WantedBy=multi-user.target
EOF

# ---------- 5. Запуск ----------
log "Запускаем $SERVICE_NAME..."
systemctl daemon-reload
systemctl enable "$SERVICE_NAME" >/dev/null
systemctl restart "$SERVICE_NAME"
sleep 2
systemctl status "$SERVICE_NAME" --no-pager || true

echo
log "Готово. Полезное:"
echo "  systemctl status $SERVICE_NAME"
echo "  journalctl -u $SERVICE_NAME -f"
echo "  curl -s http://127.0.0.1:8080/max_booking/api/admin/me   # ожидаем {\"detail\":\"Invalid initData\"}"