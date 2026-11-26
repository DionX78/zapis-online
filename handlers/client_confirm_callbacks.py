"""Обработка кнопок из запроса клиентского подтверждения."""
import logging

from core.messaging import send_to_client_raw, edit_message_for_client
from core.geo import route_lines
from core.notify import notify_admins
from core.notify_ics import send_confirmation_with_ics
from storage.db import (
    get_request, update_request_status, release_slot,
    set_client_answer,
)

log = logging.getLogger(__name__)


async def handle(uid: int, payload: str, message_id: str | None = None) -> bool:
    if not payload.startswith("cc:"):
        return False

    parts = payload.split(":")
    if len(parts) != 3:
        return True

    action = parts[1]
    try:
        request_id = int(parts[2])
    except ValueError:
        return True

    req = get_request(request_id)
    if not req:
        await _edit_or_send(uid, message_id, f"Заявка #{request_id} не найдена.")
        return True

    r_org_id = req["org_id"]
    client_uid = req["user_id"]
    service_name = req["service_name"]
    scheduled_at = req["scheduled_at"]
    phone = req["phone"]
    status = req["status"]
    slot_id = req["slot_id"]
    address = req["address"]
    doctor = req["doctor"]
    service_id = req["service_id"]

    if str(client_uid) != str(uid):
        await _edit_or_send(uid, message_id, "Нет доступа к этой заявке.")
        return True

    if status != "pending":
        await _edit_or_send(uid, message_id, "Заявка уже неактивна.")
        return True

    if action == "yes":
        set_client_answer(request_id, "yes")
        update_request_status(request_id, "confirmed", admin_id=None)

        text = (
            f"✅ Спасибо! Запись подтверждена.\n\n"
            f"**{service_name}**\n"
            f"📅 {scheduled_at}\n"
        )
        if address:
            text += route_lines(address, org_id=r_org_id)
        if doctor:
            text += f"👨‍⚕️ {doctor}\n"
        text += "\nЖдём вас!"

        await _edit_or_send(uid, message_id, text)

        # Отдельным сообщением — .ics, чтобы можно было добавить в календарь
        await send_confirmation_with_ics(
            uid,
            "📅 Добавьте приём в календарь — нажмите на файл ниже:",
            request_id, r_org_id, service_id,
            service_name, scheduled_at, address or "", doctor or "",
        )

        await notify_admins(
            f"✅ **Клиент подтвердил запись #{request_id}**\n\n"
            f"**{service_name}**\n"
            f"📅 {scheduled_at}\n"
            f"Телефон: {phone or '—'}\n\n"
            f"Клиент сам подтвердил, можно не перезванивать.",
            org_id=r_org_id,
        )
        return True

    if action == "no":
        buttons = [
            [
                {"type": "callback", "text": "❌ Да, отменить", "payload": f"cc:confirm_no:{request_id}"},
                {"type": "callback", "text": "↩ Нет, оставить", "payload": f"cc:keep:{request_id}"},
            ],
        ]
        await _edit_or_send(
            uid, message_id,
            f"❓ **Вы уверены, что хотите отменить запись?**\n\n"
            f"**{service_name}**\n"
            f"📅 {scheduled_at}\n\n"
            f"Слот будет освобождён, и другой клиент сможет на него записаться.",
            buttons,
        )
        return True

    if action == "confirm_no":
        set_client_answer(request_id, "no")
        update_request_status(request_id, "cancelled", admin_id=None)
        if slot_id:
            release_slot(slot_id, request_id)

        await _edit_or_send(
            uid, message_id,
            f"❌ Запись #{request_id} отменена.\n\n"
            f"**{service_name}**\n"
            f"📅 {scheduled_at}\n\n"
            f"Слот освобождён. Если захотите записаться снова — /start.",
        )

        await notify_admins(
            f"❌ **Клиент отменил запись #{request_id}**\n\n"
            f"**{service_name}**\n"
            f"📅 {scheduled_at}\n"
            f"Телефон: {phone or '—'}\n\n"
            f"Слот освобождён.",
            org_id=r_org_id,
        )
        return True

    if action == "keep":
        buttons = [
            [
                {"type": "callback", "text": "✅ Приду", "payload": f"cc:yes:{request_id}"},
                {"type": "callback", "text": "❌ Не смогу", "payload": f"cc:no:{request_id}"},
            ],
        ]
        await _edit_or_send(
            uid, message_id,
            f"✅ Хорошо, запись остаётся в силе.\n\n"
            f"**{service_name}**\n"
            f"📅 {scheduled_at}\n\n"
            f"Вы придёте?",
            buttons,
        )
        return True

    return True


async def _edit_or_send(uid, message_id, text, buttons=None):
    if message_id:
        await edit_message_for_client(uid, message_id, text, buttons=buttons, fmt="markdown")
    else:
        await send_to_client_raw(uid, text, buttons, fmt="markdown")