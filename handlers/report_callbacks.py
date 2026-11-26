"""Обработка кнопок быстрых отчётов из вечерней сводки.

Кнопки приходят из `core/reminders.py` (_send_evening_summary).
Payload: rep:{kind}:{org_id}:{anchor_date}
  kind: day_pdf | week_xlsx | day_csv
"""
import logging
from datetime import datetime, timedelta

from core.messaging import send_to_client_raw, edit_message_for_client
from core.analytics_export import generate_and_send_analytics
from storage.db import get_admin_role

log = logging.getLogger(__name__)


async def handle(uid: int, payload: str, message_id: str | None = None) -> bool:
    if not payload.startswith("rep:"):
        return False

    parts = payload.split(":")
    if len(parts) != 4:
        return True

    kind = parts[1]
    try:
        org_id = int(parts[2])
    except ValueError:
        return True
    anchor = parts[3]

    try:
        anchor_date = datetime.strptime(anchor, "%Y-%m-%d").date()
    except ValueError:
        await send_to_client_raw(uid, "Неверная дата в запросе.")
        return True

    role, admin_org_id, _ = get_admin_role(uid)
    if role is None:
        await send_to_client_raw(uid, "Нет доступа.")
        return True
    if role != "superadmin" and admin_org_id != org_id:
        await send_to_client_raw(uid, "Нет доступа к этой организации.")
        return True

    if kind == "day_pdf":
        fmt = "pdf"
        date_from = anchor_date.isoformat()
        date_to = anchor_date.isoformat()
        caption_prefix = f"📊 **Аналитика · {date_from}**"
    elif kind == "week_xlsx":
        fmt = "xlsx"
        date_to = anchor_date.isoformat()
        date_from = (anchor_date - timedelta(days=6)).isoformat()
        caption_prefix = f"📊 **Аналитика · неделя {date_from} — {date_to}**"
    elif kind == "day_csv":
        fmt = "csv"
        date_from = anchor_date.isoformat()
        date_to = anchor_date.isoformat()
        caption_prefix = f"📄 **Сводка · {date_from}**"
    else:
        return True

    try:
        await send_to_client_raw(uid, "⏳ Готовлю файл…")
    except Exception:
        pass

    try:
        result = await generate_and_send_analytics(
            org_id=org_id, admin_uid=uid,
            date_from=date_from, date_to=date_to, fmt=fmt,
            caption_prefix=caption_prefix,
        )
    except Exception as e:
        log.error("report callback failed: %s", e)
        try:
            await send_to_client_raw(uid, f"❌ Не удалось сформировать файл: {e}")
        except Exception:
            pass
        return True

    if not result.get("sent_to_chat"):
        err = result.get("send_error") or "неизвестная ошибка"
        full_url = result.get("full_url") or "—"
        try:
            await send_to_client_raw(
                uid,
                f"⚠️ Не удалось отправить в чат ({err}).\nСкачать: {full_url}",
                fmt="markdown",
            )
        except Exception:
            pass

    log.info("report callback: kind=%s org=%s uid=%s sent=%s",
             kind, org_id, uid, result.get("sent_to_chat"))
    return True