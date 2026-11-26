"""Обработка отписки от маркетинговых рассылок.

Двухфазная отписка:
  unsub         — тап на «🚫 Больше не присылать»; показываем подтверждение
  unsub:confirm — подтвердил; отписываем + редактируем сообщение
  unsub:cancel  — отменил; редактируем сообщение

Все кнопки «Больше не присылать» во всех рассылках (ручные, авто:
birthday, inactive, after_visit, welcome_first, revisit_cycle) используют
один и тот же payload 'unsub' — попадают сюда. Унифицировано.
"""
import logging

from core.messaging import send_to_client_raw, edit_message_for_client
from storage.db import set_marketing_opt_out, get_marketing_opt_out

log = logging.getLogger(__name__)


TEXT_CONFIRM = (
    "🚫 **Отписаться от всех рассылок?**\n\n"
    "Если отписаться, вы больше не получите акции, скидки, "
    "напоминания о повторных визитах и другую полезную информацию "
    "о наших услугах и событиях.\n\n"
    "❗️ Это **не отменит** уведомления о ваших записях — подтверждения, "
    "напоминания за 24ч/2ч и изменения приёма продолжат приходить."
)

TEXT_DONE = (
    "✅ Готово. Больше не будем присылать рекламные рассылки.\n\n"
    "Уведомления о ваших записях продолжат приходить — это часть услуги.\n\n"
    "Если захотите вернуть рассылки — обратитесь в клинику."
)

TEXT_CANCEL = (
    "👍 Хорошо, оставляем. Рассылки продолжат приходить.\n\n"
    "Если передумаете — нажмите «🚫 Больше не присылать» "
    "в любой следующей рассылке."
)

TEXT_ALREADY = (
    "Вы уже отписаны от рекламных рассылок.\n\n"
    "Уведомления о ваших записях продолжат приходить. "
    "Если хотите вернуть рассылки — обратитесь в клинику."
)

CONFIRM_BUTTONS = [[
    {"type": "callback", "text": "🗑 Да, отписаться", "payload": "unsub:confirm"},
    {"type": "callback", "text": "↩ Нет, оставить", "payload": "unsub:cancel"},
]]


async def _edit_or_send(uid, message_id, text, buttons=None):
    """Пытаемся отредактировать сообщение; при неудаче — отправляем новое.

    edit_message_for_client возвращает None при ошибке. Проверяем.
    """
    if message_id:
        try:
            r = await edit_message_for_client(uid, message_id, text, buttons=buttons, fmt="markdown")
            if r:
                return
            log.info("unsub: edit returned empty, fallback to send (uid=%s)", uid)
        except Exception as e:
            log.warning("unsub: edit_message failed, fallback to send: %s", e)
    try:
        await send_to_client_raw(uid, text, buttons=buttons, fmt="markdown")
    except Exception as e:
        log.warning("unsub: send_message failed: %s", e)


async def handle(uid: int, payload: str, message_id: str | None = None) -> bool:
    if payload not in ("unsub", "unsub:confirm", "unsub:cancel"):
        return False

    state = get_marketing_opt_out(uid)
    already_opted_out = bool(state and state["opt_out"])

    if payload == "unsub":
        if already_opted_out:
            await _edit_or_send(uid, message_id, TEXT_ALREADY)
            return True
        await _edit_or_send(uid, message_id, TEXT_CONFIRM, CONFIRM_BUTTONS)
        return True

    if payload == "unsub:confirm":
        if already_opted_out:
            await _edit_or_send(uid, message_id, TEXT_ALREADY)
            return True
        set_marketing_opt_out(uid, True)
        log.info("User %s unsubscribed from marketing (confirmed)", uid)
        await _edit_or_send(uid, message_id, TEXT_DONE)
        return True

    if payload == "unsub:cancel":
        await _edit_or_send(uid, message_id, TEXT_CANCEL)
        return True

    return True