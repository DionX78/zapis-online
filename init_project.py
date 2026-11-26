# init_project.py
# Создаёт модульную структуру проекта MAX Booking Bot.
# Запуск: python3 init_project.py

from pathlib import Path

BASE = Path(__file__).parent
FILES = {}

# ---------- .env.example ----------
FILES[".env.example"] = """MAX_BOT_TOKEN=вставь_токен_сюда
SUPERADMIN_ID=0
WEBHOOK_SECRET=придумай_секрет
WEBHOOK_BASE_URL=https://boroda-bot.ru
"""

# ---------- requirements.txt ----------
FILES["requirements.txt"] = """fastapi
uvicorn[standard]
httpx
python-dotenv
"""

# ---------- config.py ----------
FILES["config.py"] = '''import os
from dotenv import load_dotenv

load_dotenv()

MAX_BOT_TOKEN = os.getenv("MAX_BOT_TOKEN", "")
SUPERADMIN_ID = int(os.getenv("SUPERADMIN_ID", "0"))
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", "https://boroda-bot.ru")

MAX_API = "https://platform-api2.max.ru"
WEBHOOK_PATH = "/max_booking/api/webhooks"
'''

# ---------- app.py ----------
FILES["app.py"] = '''import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import config
from core.dispatcher import route_update
from storage.db import init_db

logging.basicConfig(level=logging.INFO)

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

init_db()


@app.post(config.WEBHOOK_PATH)
async def webhook(request: Request):
    if config.WEBHOOK_SECRET:
        got = request.headers.get("X-Max-Bot-Api-Secret")
        if got and got != config.WEBHOOK_SECRET:
            return JSONResponse({"ok": False}, status_code=403)

    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"ok": False}, status_code=400)

    logging.info("IN: %s", data)
    await route_update(app.state.bot, data)
    return {"ok": True}
'''

# ---------- storage/__init__.py ----------
FILES["storage/__init__.py"] = ""

# ---------- storage/db.py ----------
FILES["storage/db.py"] = '''import sqlite3
from datetime import datetime

DB_PATH = "booking.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS services (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        price INTEGER,
        prep TEXT,
        active INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        service_id TEXT,
        service_name TEXT,
        preferred_time TEXT,
        phone TEXT,
        status TEXT DEFAULT 'draft',
        created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS admins (
        user_id TEXT PRIMARY KEY,
        added_by TEXT,
        added_at TEXT
    );
    """)
    conn.commit()
    conn.close()


# ---- services ----

def get_services():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT id, name, price, prep FROM services WHERE active=1"
    ).fetchall()
    conn.close()
    return rows


def get_service(sid):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT name, prep FROM services WHERE id=?", (sid,)
    ).fetchone()
    conn.close()
    return row


# ---- requests ----

def create_draft(user_id, sid, sname, tpref):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute(
        "INSERT INTO requests (user_id, service_id, service_name, preferred_time, status, created_at) "
        "VALUES (?, ?, ?, ?, 'draft', ?)",
        (str(user_id), sid, sname, tpref, datetime.now().isoformat()),
    )
    rid = cur.lastrowid
    conn.commit()
    conn.close()
    return rid


def attach_phone(user_id, phone):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT id, service_name, preferred_time FROM requests "
        "WHERE user_id=? AND status='draft' ORDER BY id DESC LIMIT 1",
        (str(user_id),),
    ).fetchone()
    if not row:
        conn.close()
        return None
    rid, sname, tpref = row
    conn.execute("UPDATE requests SET phone=?, status='new' WHERE id=?", (phone, rid))
    conn.commit()
    conn.close()
    return rid, sname, tpref


def get_stats():
    conn = sqlite3.connect(DB_PATH)
    total = conn.execute(
        "SELECT COUNT(*) FROM requests WHERE status!='draft'"
    ).fetchone()[0]
    by_service = conn.execute(
        "SELECT service_name, COUNT(*) FROM requests "
        "WHERE status!='draft' GROUP BY service_name"
    ).fetchall()
    conn.close()
    return total, by_service


# ---- admins ----

def is_superadmin(uid):
    import config
    return int(uid) == config.SUPERADMIN_ID


def is_admin(uid):
    if is_superadmin(uid):
        return True
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT 1 FROM admins WHERE user_id=?", (str(uid),)).fetchone()
    conn.close()
    return row is not None


def add_admin(uid, by):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT OR REPLACE INTO admins (user_id, added_by, added_at) VALUES (?, ?, ?)",
        (str(uid), str(by), datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def remove_admin(uid):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM admins WHERE user_id=?", (str(uid),))
    conn.commit()
    conn.close()


def all_admins():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT user_id FROM admins").fetchall()
    conn.close()
    return [x[0] for x in rows]
'''

# ---------- core/__init__.py ----------
FILES["core/__init__.py"] = ""

# ---------- core/max_client.py ----------
FILES["core/max_client.py"] = '''import httpx
import config

API = config.MAX_API + "/messages"


async def send_message(user_id: int, text: str, buttons: list | None = None):
    if not config.MAX_BOT_TOKEN:
        print("MAX_BOT_TOKEN не задан")
        return
    headers = {
        "Authorization": config.MAX_BOT_TOKEN,
        "Content-Type": "application/json",
    }
    payload = {"text": text}
    if buttons:
        payload["attachments"] = [{
            "type": "inline_keyboard",
            "payload": {"buttons": buttons},
        }]
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            r = await client.post(
                API,
                params={"user_id": user_id},
                json=payload,
                headers=headers,
            )
            print("MAX ->", r.status_code, r.text[:200])
        except Exception as e:
            print("MAX error:", e)


async def get_me():
    headers = {"Authorization": config.MAX_BOT_TOKEN}
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(config.MAX_API + "/me", headers=headers)
        return r.json()
'''

# ---------- core/dispatcher.py ----------
FILES["core/dispatcher.py"] = '''import logging
from core import max_client as mx
from handlers import start, booking, admin
from storage.db import all_admins
import config

log = logging.getLogger(__name__)


async def route_update(bot, data: dict):
    utype = data.get("update_type") or data.get("type")

    if utype == "message_created":
        msg = data.get("message") or {}
        sender = msg.get("sender") or {}
        uid = sender.get("user_id")
        body = msg.get("body") or {}
        text = (body.get("text") or "").strip()
        if not uid:
            return

        low = text.lower()

        # админские команды — в порядке приоритета
        if await admin.try_handle(uid, text):
            return

        if low in ("/start", "start", "начать", "привет"):
            await start.welcome(uid)
            return

        if low == "/myid":
            await mx.send_message(uid, f"Ваш ID: {uid}")
            return

        # если это не команда — возможно, телефон
        if not text.startswith("/"):
            await booking.handle_input(uid, text)
        return

    if utype == "message_callback":
        cb = data.get("callback") or {}
        uid = (cb.get("sender") or {}).get("user_id")
        payload = cb.get("payload", "")
        if not uid or not payload:
            return
        await booking.handle_callback(uid, payload)
        return

    if utype == "bot_started":
        user = data.get("user") or {}
        uid = user.get("user_id")
        if uid:
            await start.welcome(uid)


async def notify_admins(text: str):
    recipients = set(all_admins())
    if config.SUPERADMIN_ID:
        recipients.add(str(config.SUPERADMIN_ID))
    for r in recipients:
        try:
            await mx.send_message(int(r), text)
        except Exception as e:
            log.warning("notify failed for %s: %s", r, e)
'''

# ---------- handlers/__init__.py ----------
FILES["handlers/__init__.py"] = ""

# ---------- handlers/start.py ----------
FILES["handlers/start.py"] = '''from core import max_client as mx
from storage.db import get_services

WELCOME = "Здравствуйте! Это центр «Диагноз».\\nВыберите услугу:"


def services_buttons():
    rows = []
    for sid, name, price, _prep in get_services():
        rows.append([{
            "type": "callback",
            "text": f"{name} — {price} ₽",
            "payload": f"svc:{sid}",
        }])
    return rows


async def welcome(uid: int):
    buttons = services_buttons()
    if not buttons:
        await mx.send_message(uid, "Услуги пока не настроены.")
        return
    await mx.send_message(uid, WELCOME, buttons)
'''

# ---------- handlers/booking.py ----------
FILES["handlers/booking.py"] = '''from core import max_client as mx
from core.dispatcher import notify_admins
from storage.db import get_service, create_draft, attach_phone


def time_buttons(sid):
    return [
        [{"type": "callback", "text": "Сегодня", "payload": f"time:{sid}:today"}],
        [{"type": "callback", "text": "Завтра", "payload": f"time:{sid}:tomorrow"}],
    ]


async def handle_callback(uid: int, payload: str):
    if payload.startswith("svc:"):
        sid = payload.split(":", 1)[1]
        svc = get_service(sid)
        if not svc:
            await mx.send_message(uid, "Услуга не найдена")
            return
        name, prep = svc
        await mx.send_message(
            uid,
            f"{name}\\nПодготовка: {prep}\\n\\nКогда удобно?",
            time_buttons(sid),
        )
        return

    if payload.startswith("time:"):
        parts = payload.split(":")
        if len(parts) != 3:
            return
        _, sid, tpref = parts
        svc = get_service(sid)
        sname = svc[0] if svc else sid
        create_draft(uid, sid, sname, tpref)
        await mx.send_message(
            uid,
            f"Вы выбрали: {sname}, {tpref}.\\n"
            f"Отправьте номер телефона для подтверждения:",
        )
        return


async def handle_input(uid: int, text: str):
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) < 10:
        return
    res = attach_phone(uid, text)
    if not res:
        return
    rid, sname, tpref = res
    await mx.send_message(uid, "Спасибо! Заявка принята, администратор свяжется с вами.")
    await notify_admins(
        f"Новая заявка #{rid}\\n"
        f"Услуга: {sname}\\n"
        f"Время: {tpref}\\n"
        f"Телефон: {text}"
    )
'''

# ---------- handlers/admin.py ----------
FILES["handlers/admin.py"] = '''from core import max_client as mx
from storage.db import (
    is_superadmin, is_admin,
    add_admin, remove_admin, all_admins, get_stats,
)


async def try_handle(uid: int, text: str) -> bool:
    low = text.lower()

    if low.startswith("/setadmin"):
        if not is_superadmin(uid):
            await mx.send_message(uid, "Нет доступа. Только суперадмин может назначать.")
            return True
        parts = text.split()
        if len(parts) == 2 and parts[1].lstrip("-").isdigit():
            target = int(parts[1])
            add_admin(target, uid)
            await mx.send_message(uid, f"{target} назначен администратором")
            try:
                await mx.send_message(
                    target,
                    "Вы назначены администратором. Заявки будут приходить сюда.",
                )
            except Exception:
                pass
        else:
            await mx.send_message(uid, "Использование: /setadmin <user_id>")
        return True

    if low.startswith("/deladmin"):
        if not is_superadmin(uid):
            await mx.send_message(uid, "Нет доступа.")
            return True
        parts = text.split()
        if len(parts) == 2 and parts[1].lstrip("-").isdigit():
            remove_admin(int(parts[1]))
            await mx.send_message(uid, f"{parts[1]} снят с роли администратора")
        else:
            await mx.send_message(uid, "Использование: /deladmin <user_id>")
        return True

    if low == "/admins":
        if not is_superadmin(uid):
            await mx.send_message(uid, "Нет доступа.")
            return True
        rows = all_admins()
        if not rows:
            await mx.send_message(uid, "Админов пока нет.")
        else:
            await mx.send_message(uid, "Админы:\\n" + "\\n".join(rows))
        return True

    if low == "/stats":
        if not is_admin(uid):
            await mx.send_message(uid, "Нет доступа.")
            return True
        total, by_service = get_stats()
        lines = [f"Всего заявок: {total}", ""]
        for name, count in by_service:
            lines.append(f"{name}: {count}")
        await mx.send_message(uid, "\\n".join(lines))
        return True

    return False
'''

# ---------- seed.py ----------
FILES["seed.py"] = '''"""Наполняет базу тестовыми услугами.
Перед демо другому клиенту — поменяй SERVICES.
"""
import sqlite3
from storage.db import init_db, DB_PATH

init_db()

SERVICES = [
    ("eeg",  "ЭЭГ",     1200, "Чистая голова, без лака/геля"),
    ("uzi",  "УЗИ",     1000, "Натощак"),
    ("echo", "ЭХО-КГ",  1500, "Подготовка не требуется"),
]

conn = sqlite3.connect(DB_PATH)
conn.execute("DELETE FROM services")
conn.executemany(
    "INSERT INTO services (id, name, price, prep) VALUES (?, ?, ?, ?)",
    SERVICES,
)
conn.commit()
conn.close()
print("OK, услуги добавлены:", len(SERVICES))
'''

# ---------- register_webhook.py ----------
FILES["register_webhook.py"] = '''"""Регистрация webhook в MAX.
Запуск: python3 register_webhook.py [url]
"""
import sys
import httpx
import config

DEFAULT_URL = config.WEBHOOK_BASE_URL + config.WEBHOOK_PATH
URL = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
ENDPOINT = config.MAX_API + "/subscriptions"

headers = {
    "Authorization": config.MAX_BOT_TOKEN,
    "Content-Type": "application/json",
}
body = {
    "url": URL,
    "update_types": ["message_created", "message_callback", "bot_started"],
}
if config.WEBHOOK_SECRET:
    body["secret"] = config.WEBHOOK_SECRET

print("POST", ENDPOINT)
r = httpx.post(ENDPOINT, json=body, headers=headers, timeout=20)
print("Status:", r.status_code)
print("Body:", r.text)

print()
print("GET", ENDPOINT)
r2 = httpx.get(ENDPOINT, headers=headers, timeout=20)
print("Status:", r2.status_code)
print("Body:", r2.text)
'''

# ---------- static/demo.html ----------
FILES["static/demo.html"] = '''<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>Записаться — Диагноз</title>
<style>
  body { font-family: system-ui, sans-serif; padding: 40px; max-width: 600px; margin: auto; }
  h1 { color: #222; }
  .btn {
    display: inline-block; padding: 16px 32px; background: #2AABEE;
    color: #fff; border-radius: 50px; text-decoration: none; font-size: 18px;
    margin-top: 20px;
  }
  .hint { color: #666; font-size: 14px; margin-top: 40px; }
</style>
</head>
<body>
  <h1>Центр «Диагноз»</h1>
  <p>Запись на приём — онлайн, без звонков.</p>
  <a class="btn" href="https://max.ru/ВАШ_БОТ" target="_blank">Записаться онлайн</a>
  <p class="hint">Это демонстрация кнопки, которая встанет на сайт mcdiagnoz.ru</p>
</body>
</html>
'''

# ---------- nginx.conf.snippet ----------
FILES["nginx.conf.snippet"] = '''# Добавить в существующий server { } для boroda-bot.ru

location /max_booking/api/webhooks {
    proxy_pass http://127.0.0.1:8080/max_booking/api/webhooks;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Max-Bot-Api-Secret $http_x_max_bot_api_secret;
    proxy_read_timeout 60s;
}

location /static/ {
    alias /var/www/max_booking_bot/static/;
}
'''

# ---------- max-bot.service ----------
FILES["max-bot.service"] = '''[Unit]
Description=MAX Booking Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/var/www/max_booking_bot
EnvironmentFile=/var/www/max_booking_bot/.env
ExecStart=/usr/local/bin/uvicorn app:app --host 127.0.0.1 --port 8080
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
'''

# ---------- README.md ----------
FILES["README.md"] = '''# MAX Booking Bot

Модульный бот для записи клиентов в MAX.

## Структура

    app.py                  — FastAPI-приложение, приём webhook
    config.py               — переменные окружения
    core/
        dispatcher.py       — маршрутизация update -> handler
        max_client.py       — отправка сообщений в MAX API
    handlers/
        start.py            — /start, приветствие
        booking.py          — выбор услуги, время, телефон
        admin.py            — команды суперадмина и админов
    storage/
        db.py               — SQLite: services, requests, admins
    seed.py                 — наполнение тестовыми услугами
    register_webhook.py     — POST /subscriptions в MAX

## Установка

1. pip install -r requirements.txt
2. cp .env.example .env && nano .env
3. python3 seed.py
4. python3 register_webhook.py
5. uvicorn app:app --host 127.0.0.1 --port 8080
6. Nginx: добавить nginx.conf.snippet
7. Systemd: cp max-bot.service /etc/systemd/system/

## Роли

- Суперадмин — только ты (SUPERADMIN_ID в .env).
  Может назначать и снимать админов: /setadmin, /deladmin, /admins.
- Админ — назначен суперадмином. Получает заявки.
  Может смотреть /stats.

## Путь webhook

/max_booking/api/webhooks
'''

# ---------- .gitignore ----------
FILES[".gitignore"] = """venv/
__pycache__/
*.pyc
.env
booking.db
"""


def write(rel, content):
    path = BASE / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        print("skip", rel)
        return
    path.write_text(content, encoding="utf-8")
    print("ok  ", rel)


def main():
    print("Creating in:", BASE)
    for rel, content in FILES.items():
        write(rel, content)
    print()
    print("Done. Структура:")
    for p in sorted(BASE.rglob("*")):
        rel = p.relative_to(BASE)
        if str(rel).startswith("."):
            continue
        if p.is_dir():
            print("  " + str(rel) + "/")
        elif p.name != "init_project.py":
            print("  " + str(rel))
    print()
    print("Next:")
    print("  1. cp .env.example .env && nano .env")
    print("  2. pip install -r requirements.txt")
    print("  3. python3 seed.py")
    print("  4. python3 register_webhook.py")
    print("  5. uvicorn app:app --host 127.0.0.1 --port 8080")


if __name__ == "__main__":
    main()