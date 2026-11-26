"""Обработка кнопок отзыва 1-5 звёзд.

Payload: rv:rate:{request_id}:{1..5}

Логика:
- 4-5 (>= positive_threshold) → сохраняем, отправляем ссылки на Яндекс/2ГИС
- 1-3 → сохраняем, уведомляем админа приватно
"""
import logging

from core.messaging import send_to_client_raw, edit_message_for_client
from core.notify import notify_admins
from storage.db import (
    get_request, get_org_settings, get_client,
    save_review, get_review_by_request,
    mark_review_admin_notified, mark_review_public_link_sent,
)

log = logging.getLogger(__name__)


def _edit_or_send(uid, message_id, text, buttons=None):
    if message_id:
        return edit_message_for_client(uid, message_id, text, buttons=buttons, fmt="markdown")
    return send_to_client_raw(uid, text, buttons=buttons, fmt="markdown")


def _build_public_links(settings):
    """Возвращает список [(label, url), ...] для публичных площадок."""
    links = []
    yandex = (settings.get("review_yandex_url") or "").strip()
    gis = (settings.get("review_2gis_url") or "").strip()
    if yandex:
        links.append(("🗺 Яндекс.Карты", yandex))
    if gis:
        links.append(("🗺 2ГИС", gis))
    return links


async def handle(uid: int, payload: str, message_id: str | None = None) -> bool:
    if not payload.startswith("rv:rate:"):
        return False

    parts = payload.split(":")
    if len(parts) != 4:
        return True

    try:
        request_id = int(parts[2])
        rating = int(parts[3])
    except ValueError:
        return True

    if rating < 1 or rating > 5:
        return True

    req = get_request(request_id)
    if not req:
        try:
            await _edit_or_send(uid, message_id, "Заявка не найдена.")
        except Exception:
            pass
        return True

    if str(req["user_id"]) != str(uid):
        try:
            await _edit_or_send(uid, message_id, "Нет доступа к этой заявке.")
        except Exception:
            pass
        return True

    existing = get_review_by_request(request_id)
    if existing:
        try:
            await _edit_or_send(
                uid, message_id,
                "Спасибо! Вы уже оценили этот визит — повторно отзыв отправить нельзя.",
            )
        except Exception:
            pass
        return True

    org_id = req["org_id"]
    settings = get_org_settings(org_id)
    threshold = int(settings.get("review_positive_threshold", 4) or 4)

    rid_new = save_review(
        org_id=org_id, user_id=uid, request_id=request_id,
        rating=rating, doctor_id=req["doctor_id"], service_id=req["service_id"],
    )

    stars = "⭐" * rating

    if rating >= threshold:
        # Позитивно. Если есть ссылки — отправим их.
        links = _build_public_links(settings)
        text = (
            f"🌟 **Спасибо большое!** {stars}\n\n"
            f"Нам очень приятно, что визит прошёл хорошо."
        )
        buttons = []
        if links:
            text += (
                "\n\nБудем очень благодарны, если оставите отзыв — "
                "это помогает другим людям найти нас и помогает нам становиться лучше."
            )
            for label, url in links:
                buttons.append([{"type": "link", "text": label, "url": url}])

        try:
            if message_id:
                await edit_message_for_client(uid, message_id, text, buttons=buttons, fmt="markdown")
            else:
                await send_to_client_raw(uid, text, buttons=buttons, fmt="markdown")
            if links and rid_new:
                mark_review_public_link_sent(rid_new)
        except Exception as e:
            log.warning("review: edit/send positive failed: %s", e)
        return True

    # Негатив. Не показываем ссылки, уведомляем админа.
    text = (
        f"😔 **Спасибо за честную оценку.** {stars}\n\n"
        f"Нам важно разобраться, что пошло не так. "
        f"Администратор свяжется с вами в ближайшее время."
    )
    try:
        await _edit_or_send(uid, message_id, text)
    except Exception as e:
        log.warning("review: edit/send negative failed: %s", e)

    if rid_new:
        client = get_client(uid)
        fio = "—"
        if client:
            fio = " ".join(p for p in [
                client["last_name"], client["first_name"], client["middle_name"],
            ] if p).strip() or client["phone"] or uid

        admin_text = (
            f"⚠️ **Низкая оценка визита: {rating}/5**\n\n"
            f"👤 {fio}\n"
            f"📞 {client['phone'] if client else '—'}\n"
            f"**{req['service_name'] or '—'}**\n"
            f"📅 {req['scheduled_at']}\n"
        )
        if req["doctor"]:
            admin_text += f"👤 Специалист: {req['doctor']}\n"
        admin_text += f"\nЗаявка #{request_id}."
        admin_text += "\n\nСвяжитесь с клиентом, чтобы узнать подробности."

        try:
            await notify_admins(admin_text, org_id=org_id, buttons=None)
            mark_review_admin_notified(rid_new)
        except Exception as e:
            log.warning("review: notify_admins failed: %s", e)

    return True