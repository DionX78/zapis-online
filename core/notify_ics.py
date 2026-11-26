"""Отправка подтверждений записи с .ics-вложением (файл для календаря)."""
import logging

from core.channels.base import UserBlocked
from core.messaging import (
    send_to_client_with_file_raw, send_to_client_raw, upload_file_for_client,
)
from core.ics import build_ics
from storage.db import get_service

log = logging.getLogger(__name__)


async def send_confirmation_with_ics(
    user_id, text, request_id, org_id, service_id,
    service_name, scheduled_at, address="", doctor="", prep="",
):
    """Отправляет сообщение с .ics-вложением.
    Возвращает (status, error), где status: "sent" | "blocked" | "error" | "no_max".
    При ошибке .ics — fallback на обычный текст.
    """
    if not user_id or str(user_id).startswith("phone:"):
        return "no_max", None

    try:
        duration_min = 30
        svc = get_service(service_id) if service_id else None
        if svc:
            try:
                duration_min = svc["duration_min"] or 30
            except (IndexError, KeyError):
                duration_min = 30
            try:
                if not prep:
                    prep = svc["prep"] or ""
            except (IndexError, KeyError):
                pass

        ics_text = build_ics(
            request_id=request_id, org_id=org_id, service_name=service_name,
            scheduled_at=scheduled_at, duration_min=duration_min,
            address=address or "", doctor=doctor or "", prep=prep or "",
        )
        log.info("Sending ics for #%s to %s", request_id, user_id)
        file_token = await upload_file_for_client(
            user_id, ics_text, filename=f"booking-{request_id}.ics",
            mime="text/calendar",
        )
        await send_to_client_with_file_raw(user_id, text, file_token, fmt="markdown")
        log.info("ICS sent for #%s", request_id)
        return "sent", None
    except UserBlocked:
        log.info("User %s blocked bot (#%s)", user_id, request_id)
        return "blocked", None
    except Exception as e:
        log.warning("Не удалось отправить .ics для #%s: %s, fallback на текст", request_id, e)

    try:
        await send_to_client_raw(user_id, text, fmt="markdown")
        return "sent", None
    except UserBlocked:
        return "blocked", None
    except Exception as e2:
        return "error", str(e2)[:200]