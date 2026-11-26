"""Парсер MAX webhook → Update."""
import logging

from core.updates import Update

log = logging.getLogger(__name__)


def _user_info(d: dict) -> dict:
    if not isinstance(d, dict):
        return {}
    return {
        "user_id": d.get("user_id"),
        "first_name": d.get("first_name") or "",
        "last_name": d.get("last_name") or "",
        "username": d.get("username") or "",
    }


def parse(raw: dict) -> Update | None:
    if not isinstance(raw, dict):
        return None
    utype = raw.get("update_type") or raw.get("type")
    if not utype:
        return None

    if utype == "message_created":
        msg = raw.get("message") or {}
        sender = msg.get("sender") or {}
        uid = sender.get("user_id")
        if not uid:
            return None
        body = msg.get("body") or {}
        text = (body.get("text") or "").strip()
        return Update(
            platform="max",
            type="message_created",
            user_id=str(uid),
            user_info=_user_info(sender),
            text=text,
            raw=raw,
        )

    if utype == "message_callback":
        cb = raw.get("callback") or {}
        user = cb.get("user") or cb.get("sender") or {}
        uid = user.get("user_id")
        if not uid:
            return None
        payload = cb.get("payload", "") or ""
        message_id = (raw.get("message") or {}).get("body", {}).get("mid")
        return Update(
            platform="max",
            type="message_callback",
            user_id=str(uid),
            user_info=_user_info(user),
            payload=str(payload),
            message_id=message_id,
            raw=raw,
        )

    if utype == "bot_started":
        user = raw.get("user") or {}
        uid = user.get("user_id")
        if not uid:
            return None
        return Update(
            platform="max",
            type="bot_started",
            user_id=str(uid),
            user_info=_user_info(user),
            raw=raw,
        )

    return None