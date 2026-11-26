"""Обработка кнопок подтверждения/отклонения заявок админом."""
import logging

from core.messaging import send_to_client_raw, edit_message_for_client
from storage.db import (
    get_request, update_request_status, release_slot,
    is_admin, get_admin_org,
)
import config

log = logging.getLogger(__name__)


async def handle(uid: int, payload: str, message_id: str | None = None) -> bool:
    if not payload.startswith("req:"):
        return False

    if not is_admin(uid):
        await send_to_client_raw(uid, "Нет доступа.")
        return True

    parts = payload.split(":")
    if len(parts) < 3:
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
    status = req["status"]
    address = req["address"]
    doctor = req["doctor"]
    slot_id = req["slot_id"]

    admin_org = get_admin_org(uid)
    if not config.is_superadmin(uid) and admin_org != r_org_id:
        await send_to_client_raw(uid, "Нет доступа к этой заявке.")
        return True

    if status == "confirmed":
        await _edit_or_send(uid, message_id, f"Заявка #{request_id} уже подтверждена.")
        return True
    if status == "cancelled":
        await _edit_or_send(uid, message_id, f"Заявка #{request_id} уже отклонена.")
        return True

    if action == "confirm":
        update_request_status(request_id, "confirmed", admin_id=uid)

        text = f"✅ **Ваша запись подтверждена!**\n\n"
        text += f"**{service_name}**\n"
        text += f"📅 {scheduled_at}\n"
        if address:
            text += f"📍 {address}\n"
        if doctor:
            text += f"👨‍⚕️ {doctor}\n"
        text += f"\nЖдём вас! Если планы изменятся — напишите боту /start."

        try:
            await send_to_client_raw(client_uid, text, fmt="markdown")
        except Exception as e:
            log.warning("Не удалось уведомить клиента %s: %s", client_uid, e)

        await _edit_or_send(
            uid, message_id,
            f"✅ Заявка #{request_id} подтверждена.\nКлиент уведомлён.",
        )
        return True

    if action == "reject":
        update_request_status(request_id, "cancelled", admin_id=uid)

        if slot_id:
            release_slot(slot_id, request_id)

        text = (
            f"❌ **К сожалению, ваша заявка #{request_id} отклонена.**\n\n"
            f"**{service_name}**\n"
            f"📅 {scheduled_at}\n\n"
            f"Администратор свяжется с вами для уточнения деталей "
            f"или предложит другое время."
        )
        try:
            await send_to_client_raw(client_uid, text, fmt="markdown")
        except Exception as e:
            log.warning("Не удалось уведомить клиента %s: %s", client_uid, e)

        await _edit_or_send(
            uid, message_id,
            f"❌ Заявка #{request_id} отклонена. Слот освобождён. Клиент уведомлён.",
        )
        return True

    return True


async def _edit_or_send(uid, message_id, text):
    if message_id:
        await edit_message_for_client(uid, message_id, text)
    else:
        await send_to_client_raw(uid, text)