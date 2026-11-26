"""Канал VK — сообщения сообщества через Callback API.

Токен и group_id живут в таблице bots (у каждой организации свой бот),
поэтому канал не читает config.*. Отправка — messages.send, кнопки
конвертируются в inline-клавиатуру VK (label ≤ 40 символов,
payload ≤ 255 байт).
"""
import asyncio
import json
import logging
import random
import time

import httpx

from core.channels.base import Channel, UserBlocked, ChannelError

log = logging.getLogger(__name__)

from core.channels.vk_text import vk_text

VK_API = "https://api.vk.com/method/"
VK_VERSION = "5.199"

# Кэш активного бота: перечитывается раз в 60 с, чтобы смена токена
# подхватывалась без рестарта сервиса.
_BOT_TTL = 60
_bot_cache = {"at": 0.0, "bot": None}

# Клиент закрыл сообщения сообщества / запретил писать.
_BLOCKED_CODES = {7, 15, 901, 902}
# Временные: слишком много запросов в секунду, flood control, внутренняя ошибка.
_RETRY_CODES = {6, 9, 10}


def _load_bot():
    """Активный VK-бот (token, group_id) с кэшем на минуту."""
    now = time.time()
    bot = _bot_cache.get("bot")
    if bot and now - _bot_cache.get("at", 0.0) < _BOT_TTL:
        return bot
    try:
        import storage.db as db

        bots = db.list_bots(platform="vk", only_enabled=True) or []
    except Exception as e:
        log.warning("VK bot lookup failed: %s", e)
        bots = []
    if len(bots) > 1:
        log.debug("VK-ботов несколько (%s) — берём первого, выбор по org ещё не сделан",
                  len(bots))
    bot = bots[0] if bots else None
    _bot_cache.update({"at": now, "bot": bot})
    return bot


def reset_bot_cache():
    """Сбросить кэш бота (после смены токена в админке)."""
    _bot_cache.update({"at": 0.0, "bot": None})


async def api_call(method, params, token=None, retries: int = 3):
    """Вызов метода VK API. Возвращает поле response, бросает при ошибке."""
    if token is None:
        bot = _load_bot()
        if not bot or not bot["token"]:
            raise ChannelError("VK-бот не настроен: в bots нет token")
        token = bot["token"]
    payload = dict(params or {})
    payload["access_token"] = token
    payload["v"] = VK_VERSION

    last = ""
    for attempt in range(retries):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post(VK_API + method, data=payload)
            data = r.json()
        except Exception as e:
            last = f"{method}: {e}"
            await asyncio.sleep(1 + attempt)
            continue

        if "error" in data:
            err = data.get("error") or {}
            code = int(err.get("error_code") or 0)
            msg = err.get("error_msg") or ""
            if code in _RETRY_CODES:
                last = f"{code} {msg}"
                await asyncio.sleep(1 + attempt * 2)
                continue
            if code in _BLOCKED_CODES:
                raise UserBlocked(f"vk {code}: {msg}")
            raise ChannelError(f"vk {code}: {msg}")
        return data.get("response")

    raise ChannelError(f"{method} не удался после {retries} попыток: {last}")


def _button(b):
    """Кнопка MAX-формата → кнопка клавиатуры VK."""
    btype = str(b.get("type") or "callback").lower()
    text = str(b.get("text") or "")[:40]
    if btype in ("link", "open_link"):
        return {"action": {
            "type": "open_link",
            "link": b.get("url") or b.get("link") or "",
            "label": text,
        }}
    if btype in ("open_app", "web_app"):
        # Mini App MAX в VK пока не открывается (E4.4) — ведём в чат-поток.
        payload = "start_booking_fallback"
    else:
        payload = str(b.get("payload") or "")[:240]
    return {
        "action": {"type": "callback", "label": text,
                   "payload": json.dumps({"p": payload}, ensure_ascii=False)},
        "color": "secondary",
    }


def _keyboard(buttons):
    """Список рядов кнопок MAX → inline-клавиатура VK."""
    if not buttons:
        return None
    rows = []
    for row in buttons:
        items = [_button(b) for b in (row or []) if isinstance(b, dict)]
        if items:
            rows.append(items[:5])
        if len(rows) >= 6:
            break
    if not rows:
        return None
    return {"inline": True, "buttons": rows}


async def _send(peer_id, text, buttons=None, attachments=None):
    """Общая отправка: peer_id — id пользователя VK (диалог с сообществом)."""
    params = {
        "peer_id": int(peer_id),
        "random_id": random.getrandbits(31),
        "message": await vk_text(text) or "",
    }
    atts = [a for a in (attachments or []) if a]
    if atts:
        params["attachment"] = ",".join(atts)
    keyboard = _keyboard(buttons)
    if keyboard:
        params["keyboard"] = json.dumps(keyboard, ensure_ascii=False)
    try:
        return await api_call("messages.send", params)
    except ChannelError as e:
        # Клавиатура не понравилась VK (лимиты/формат) — сообщение важнее кнопок.
        if keyboard and "100" in str(e):
            log.warning("VK отклонил клавиатуру, повторяю без неё: %s", e)
            params.pop("keyboard", None)
            return await api_call("messages.send", params)
        raise


async def answer_event(raw):
    """Гасим «крутилку» на нажатой inline-кнопке (иначе клиент ждёт ответа)."""
    obj = (raw or {}).get("object") or {}
    if not obj.get("event_id"):
        return
    try:
        await api_call("messages.sendMessageEventAnswer", {
            "event_id": obj.get("event_id"),
            "user_id": obj.get("user_id"),
            "peer_id": obj.get("peer_id"),
        })
    except Exception as e:
        log.debug("sendMessageEventAnswer failed: %s", e)


class VkChannel(Channel):
    platform = "vk"

    async def send_message(self, user_id, text, buttons=None, fmt=None):
        return await _send(user_id, text, buttons=buttons)

    async def send_with_image(self, user_id, text, image_token, buttons=None, fmt=None):
        return await _send(user_id, text, buttons=buttons, attachments=[image_token])

    async def send_with_file(self, user_id, text, file_token, buttons=None, fmt=None):
        return await _send(user_id, text, buttons=buttons, attachments=[file_token])

    async def edit_message(self, user_id, message_id, text, buttons=None, fmt=None):
        try:
            params = {
                "peer_id": int(user_id),
                # VK ждёт именно conversation_message_id (id в диалоге),
                # а не глобальный message_id.
                "conversation_message_id": int(message_id),
                "message": await vk_text(text) or "",
            }
            keyboard = _keyboard(buttons)
            if keyboard:
                params["keyboard"] = json.dumps(keyboard, ensure_ascii=False)
            return await api_call("messages.edit", params)
        except Exception as e:
            log.warning("VkChannel.edit_message failed, fallback to send: %s", e)
        # Не смогли отредактировать (старое сообщение, лимит VK) — шлём новым.
        try:
            return await _send(user_id, text, buttons=buttons)
        except Exception as e:
            log.warning("VkChannel.send fallback failed: %s", e)
            return None

    async def delete_message(self, user_id, message_id):
        try:
            return await api_call("messages.delete", {
                "peer_id": int(user_id),
                "cmids": str(message_id),
                "delete_for_all": 1,
            })
        except Exception as e:
            log.warning("VkChannel.delete_message failed: %s", e)
            return None

    async def upload_file(self, content, filename, mime="text/calendar",
                          upload_type="file", user_id=None):
        """Загрузка в VK. Фото — через photos, остальное — через docs.

        Возвращает строку-вложение: 'photo{owner}_{id}_{key}' или 'doc{owner}_{id}'.
        """
        is_image = str(mime or "").startswith("image/")
        if isinstance(content, str):
            content = content.encode()
        try:
            if is_image:
                peer = int(str(user_id or "").replace("vk:", "")) or 0
                server = await api_call("photos.getMessagesUploadServer",
                                        {"peer_id": peer})
                url = (server or {}).get("upload_url")
                if not url:
                    raise ChannelError("photos.getMessagesUploadServer: нет upload_url")
                async with httpx.AsyncClient(timeout=60.0) as client:
                    r = await client.post(url, files={
                        "photo": (filename, content, mime or "image/jpeg"),
                    })
                up = r.json()
                saved = await api_call("photos.saveMessagesPhoto", {
                    "photo": up.get("photo"),
                    "server": up.get("server"),
                    "hash": up.get("hash"),
                })
                item = (saved or [{}])[0]
                return f"photo{item.get('owner_id')}_{item.get('id')}_{item.get('access_key')}"

            peer = int(str(user_id or "").replace("vk:", "")) or 0
            server = await api_call("docs.getMessagesUploadServer",
                                    {"type": "doc", "peer_id": peer})
            url = (server or {}).get("upload_url")
            if not url:
                raise ChannelError("docs.getMessagesUploadServer: нет upload_url")
            async with httpx.AsyncClient(timeout=60.0) as client:
                r = await client.post(url, files={
                    "file": (filename, content, mime or "application/octet-stream"),
                })
            up = r.json()
            saved = await api_call("docs.save", {
                "file": up.get("file"),
                "title": filename,
            })
            doc = (saved or {}).get("doc") or (saved or [{}])[0]
            return f"doc{doc.get('owner_id')}_{doc.get('id')}"
        except UserBlocked as e:
            # Ошибка загрузки — не блокировка клиента: blocked-коды VK
            # осмысленны только для messages.send, а не для загрузок.
            raise ChannelError(f"VK upload failed: {e}")
        except ChannelError:
            raise
        except Exception as e:
            raise ChannelError(f"VK upload failed: {e}")

    async def set_commands(self, commands):
        """VK не поддерживает список команд бота в интерфейсе — no-op."""
        log.debug("VkChannel.set_commands: пропуск (не поддерживается VK)")
        return None
