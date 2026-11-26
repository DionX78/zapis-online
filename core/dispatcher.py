"""Маршрутизация входящих Update → handlers.

Платформонезависимо: приходит Update (см. core/updates.py),
дальше просто матчинг по .type и вызовы handlers. Специфика
канала — в webhook_adapters/<platform>.py.
"""
import logging

from core.messaging import send_to_client_raw
from core.updates import Update
from core.webhook_adapters import max as max_adapter
from handlers import start, booking, admin
from handlers import superadmin_callbacks as sa_cb
from handlers import request_callbacks as req_cb
from handlers import reminder_callbacks as rem_cb
from handlers import client_confirm_callbacks as cc_cb
from handlers import visit_callbacks as vis_cb
from handlers import unsub_callbacks as unsub_cb
from handlers import report_callbacks as rep_cb
from handlers import review_callbacks as rv_cb
from core import waitlist as wl_core
import config

log = logging.getLogger(__name__)


async def route(update: Update):
    """Маршрутизация одного Update. Не зависит от платформы."""
    try:
        uid = int(update.user_id) if update.user_id.isdigit() else update.user_id
    except (AttributeError, ValueError):
        log.warning("Update without valid user_id, skip: %r", update.user_id)
        return

    if update.type == "message_created":
        text = update.text or ""
        if not text:
            return
        await _handle_message(uid, text, update.platform)
        return

    if update.type == "message_callback":
        payload = update.payload or ""
        if not payload:
            return
        await _handle_callback(uid, payload, update.message_id, update.platform)
        return

    if update.type == "bot_started":
        if uid:
            await start.cmd_start(uid, platform=update.platform)
        return


async def _handle_message(uid, text, platform="max"):
    low = text.lower()

    if await sa_cb.handle_text(uid, text):
        return

    if await admin.try_handle(uid, text):
        return

    if low in ("/start", "start", "начать", "привет"):
        await start.cmd_start(uid, platform=platform)
        return

    if low == "/myid":
        await send_to_client_raw(uid, f"Ваш ID: {uid}")
        return

    if low == "/help":
        await send_to_client_raw(
            uid,
            "Доступные команды:\n"
            "/start — начать запись\n"
            "/myid — узнать свой ID\n"
            "/iam — подать заявку на роль администратора\n"
            "/help — справка",
        )
        return

    if low in ("/today", "/сегодня"):
        await vis_cb.send_today(uid)
        return

    if low == "/cancel":
        await start.cmd_start(uid)
        return

    if not text.startswith("/"):
        await booking.handle_input(uid, text)


async def _handle_callback(uid, payload, message_id, platform="max"):
    if await unsub_cb.handle(uid, payload, message_id):
        return
    if await wl_core.handle_callback(uid, payload, message_id):
        return
    if await sa_cb.handle(uid, payload, message_id):
        return
    if await req_cb.handle(uid, payload, message_id):
        return
    if await rem_cb.handle(uid, payload, message_id):
        return
    if await cc_cb.handle(uid, payload, message_id):
        return
    if await vis_cb.handle(uid, payload, message_id):
        return
    if await rep_cb.handle(uid, payload, message_id):
        return
    if await rv_cb.handle(uid, payload, message_id):
        return
    await booking.handle_callback(uid, payload, message_id)


async def route_update(data: dict):
    """Совместимая обёртка: сырой dict → parse → route.

    Оставлена для случаев, если где-то ещё зовут route_update(data).
    В routers/webhook.py переключаемся на parse+route напрямую.
    """
    update = max_adapter.parse(data)
    if not update:
        log.debug("Unparseable update: %r", (data or {}).get("update_type"))
        return
    await route(update)