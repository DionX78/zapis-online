"""Разбор событий Callback API VK в универсальный Update.

Поддерживается: message_new (входящее сообщение), message_event (нажатие
inline-кнопки), message_allow (клиент разрешил сообщения — считаем стартом).
Остальные типы (message_reply, photo_new, wall_post_new...) игнорируются.
"""
import json
import logging

from core.updates import Update

log = logging.getLogger(__name__)


def _payload_str(payload) -> str:
    """VK присылает payload строкой или объектом; нам нужен короткий код."""
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            return payload.strip()
    if isinstance(payload, dict):
        for key in ("p", "payload", "cmd", "command"):
            if payload.get(key):
                return str(payload[key])
        return ""
    return ""


def _parse_message_new(obj: dict):
    msg = obj.get("message") if isinstance(obj.get("message"), dict) else obj
    if not msg:
        return None
    if int(msg.get("out") or 0) == 1:
        return None   # эхо наших же сообщений
    from_id = msg.get("from_id")
    try:
        if int(from_id or 0) <= 0:
            return None   # сообщение от сообщества (from_id < 0)
    except (TypeError, ValueError):
        return None

    text = str(msg.get("text") or "").strip()
    payload = _payload_str(msg.get("payload"))
    # /start в VK приходит как обычный текст, поэтому чистим возможный deep link.
    return Update(
        platform="vk",
        type="message_created",
        user_id=str(from_id),
        text=text,
        payload=payload,
        message_id=str(msg.get("conversation_message_id") or msg.get("id") or ""),
        start_param=str((msg.get("ref") or "")),
        user_info={},
        raw={"type": "message_new", "object": obj, "message": msg},
    )


def _parse_message_event(obj: dict):
    user_id = obj.get("user_id")
    if not user_id:
        return None
    return Update(
        platform="vk",
        type="message_callback",
        user_id=str(user_id),
        payload=_payload_str(obj.get("payload")),
        message_id=str(obj.get("conversation_message_id") or ""),
        user_info={},
        raw={"type": "message_event", "object": obj},
    )


def parse_event(data: dict):
    """dict из тела POST → Update | None (None = событие нам не нужно)."""
    if not isinstance(data, dict):
        return None
    etype = str(data.get("type") or "")
    obj = data.get("object")
    if not isinstance(obj, dict):
        obj = {}

    if etype == "message_new":
        return _parse_message_new(obj)

    if etype == "message_event":
        return _parse_message_event(obj)

    if etype == "message_allow":
        uid = obj.get("user_id")
        if not uid:
            return None
        return Update(
            platform="vk",
            type="bot_started",
            user_id=str(uid),
            user_info={},
            raw={"type": "message_allow", "object": obj},
        )

    if etype in ("message_deny", "message_typing_state", "message_reply"):
        return None

    log.debug("VK: событие '%s' пропущено", etype)
    return None
