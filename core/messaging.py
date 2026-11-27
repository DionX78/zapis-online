"""Единая точка отправки сообщений клиенту.

Сейчас работает через реестр core.channels (реализован только MAX).
После E4 будет работать и с VK — без изменений в вызывающем коде.

Два уровня API:
- send_to_client(user_id, ...) → (status, error) — не бросает, для «отправить и забыть».
  status: "sent" | "blocked" | "no_max" | "error".
  "no_max" исторически значит «у клиента нет канала» (phone-only клиент).
  Строку не меняем: на ней завязан фронт (CreateRequestModal, ClientMessageModal).

Дублирование: duplicate=True (или organizations.settings.channel_duplicate)
отправляет сообщение во ВСЕ каналы клиента, а не только в основной.

- send_to_client_raw(user_id, ...) → dict — бросает UserBlocked / ChannelError,
  для случаев, когда важен результат (рассылки, .ics, отчёты, retry).

Оба идут через get_channel_for_client — выбор канала по identity клиента.
"""
import logging

from core.channels.base import UserBlocked, ChannelError
from core.channels.registry import get_channel_for_client, get_channels_for_client

log = logging.getLogger(__name__)


def _should_duplicate(duplicate, org_id=None) -> bool:
    """Дублировать ли отправку во все каналы клиента.

    duplicate=None → берём organizations.settings.channel_duplicate.
    """
    if duplicate is not None:
        return bool(duplicate)
    if org_id is None:
        return False
    try:
        import storage.db as db

        return bool((db.get_org_settings(int(org_id)) or {}).get("channel_duplicate"))
    except Exception:
        return False


async def send_to_client(user_id, text, buttons=None, fmt="markdown",
                         org_id=None, duplicate=None):
    """Отправляет сообщение клиенту. Возвращает (status, error).

    status: "sent" | "blocked" | "no_max" | "error"
    Никогда не бросает.

    channel_duplicate=True (или настройка организации) — шлём во все каналы
    клиента. Статус "sent", если дошло хотя бы в один.
    """
    uid_str = str(user_id or "")
    if not uid_str or uid_str.startswith("phone:"):
        return "no_max", None

    if org_id is None:
        org_id = _client_org_id(uid_str)

    if _should_duplicate(duplicate, org_id):
        targets = get_channels_for_client(uid_str, org_id)
        if not targets:
            return "no_max", None
        last_status, last_err = "error", "all channels failed"
        sent_any = False
        for channel, platform_uid, platform in targets:
            try:
                await channel.send_message(platform_uid, text, buttons=buttons, fmt=fmt)
                sent_any = True
            except UserBlocked:
                last_status, last_err = "blocked", None
            except ChannelError as e:
                last_status, last_err = "error", str(e)[:200]
            except Exception as e:
                last_status, last_err = "error", str(e)[:200]
            else:
                last_status, last_err = "sent", None
            if not sent_any and last_status == "error":
                log.warning("send_to_client (%s) failed for %s: %s",
                            platform, uid_str, last_err)
        return ("sent", None) if sent_any else (last_status, last_err)

    channel, platform_uid, _platform = get_channel_for_client(uid_str, org_id)
    if channel is None:
        return "no_max", None
    try:
        await channel.send_message(platform_uid, text, buttons=buttons, fmt=fmt)
        return "sent", None
    except UserBlocked:
        return "blocked", None
    except ChannelError as e:
        log.warning("send_to_client failed for %s: %s", uid_str, e)
        return "error", str(e)[:200]
    except Exception as e:
        log.warning("send_to_client unexpected error for %s: %s", uid_str, e)
        return "error", str(e)[:200]


def _client_org_id(uid_str):
    # org клиента — чтобы работали настройки «канал по умолчанию» и «дублировать»
    # даже когда вызывающий код их не передал.
    try:
        import storage.db as _db
        c = _db.get_client(uid_str)
        return c["org_id"] if c else None
    except Exception:
        return None


async def _send_raw_multichannel(uid_str, org_id, duplicate, send_one, **kw):
    if org_id is None:
        org_id = _client_org_id(uid_str)
    if _should_duplicate(duplicate, org_id):
        targets = get_channels_for_client(uid_str, org_id)
        if not targets:
            raise ChannelError("no channel for user")
        result, last_exc, sent_any = None, None, False
        for channel, platform_uid, _platform in targets:
            try:
                result = await send_one(channel, platform_uid)
                sent_any = True
            except UserBlocked:
                raise
            except Exception as e:
                last_exc = e
                log.warning("raw send (%s) failed for %s: %s",
                            _platform, uid_str, str(e)[:200])
        if sent_any:
            return result
        raise ChannelError(str(last_exc or "all channels failed"))
    channel, platform_uid, _platform = get_channel_for_client(uid_str, org_id)
    if channel is None:
        raise ChannelError("no channel for user")
    return await send_one(channel, platform_uid)


async def send_to_client_raw(user_id, text, buttons=None, fmt="markdown",
                             org_id=None, duplicate=None):
    """Текст. Бросает UserBlocked/ChannelError. duplicate — во все каналы клиента."""
    uid_str = str(user_id or "")
    if not uid_str or uid_str.startswith("phone:"):
        raise ChannelError("no channel for user")

    async def _one(channel, platform_uid):
        return await channel.send_message(platform_uid, text, buttons=buttons, fmt=fmt)

    return await _send_raw_multichannel(uid_str, org_id, duplicate, _one)


def _stored_image_bytes(token):
    """Байты картинки по токену: blob в БД или файл на диске."""
    import os as _os
    import sqlite3 as _sq
    try:
        conn = _sq.connect("booking.db")
        conn.row_factory = _sq.Row
        cols = [r[1] for r in conn.execute("PRAGMA table_info(uploaded_images)").fetchall()]
        row = None
        for c in cols:
            if c == "id":
                continue
            try:
                row = conn.execute(
                    "SELECT * FROM uploaded_images WHERE " + c + "=? LIMIT 1", (token,)
                ).fetchone()
            except Exception:
                row = None
            if row:
                break
        if row is None:
            conn.close()
            return None, None
        mime = row["mime"] if "mime" in cols and row["mime"] else "image/jpeg"
        for c in cols:
            if c in ("id", "created_at"):
                continue
            try:
                v = row[c]
            except Exception:
                continue
            if isinstance(v, (bytes, bytearray)) and len(v) > 100:
                conn.close()
                return bytes(v), mime
        path = None
        for c in ("path", "file_path", "filepath", "local_path", "stored_name",
                  "filename", "name"):
            if c in cols and row[c]:
                path = row[c]
                break
        conn.close()
        if not path:
            return None, None
        for cand in (path, _os.path.join(_os.getcwd(), path),
                     _os.path.join(_os.getcwd(), "uploads", path),
                     _os.path.join(_os.getcwd(), "static", path)):
            if _os.path.exists(cand) and _os.path.isfile(cand):
                with open(cand, "rb") as f:
                    return f.read(), mime
        log.warning("stored image path not found on disk: %s", path)
        return None, None
    except Exception as e:
        log.warning("stored image lookup failed: %s", e)
        return None, None


def _vk_token():
    import config as _cfg
    for n in sorted(dir(_cfg)):
        if "VK" in n.upper() and "TOKEN" in n.upper():
            v = getattr(_cfg, n)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return None


def _vk_api():
    import config as _cfg
    for n in sorted(dir(_cfg)):
        if "VK" in n.upper() and ("API" in n.upper() or "URL" in n.upper()):
            v = getattr(_cfg, n)
            if isinstance(v, str) and v.startswith("http"):
                return v.rstrip("/") + "/"
    return "https://api.vk.com/method/"


def _vk_version():
    import config as _cfg
    return getattr(_cfg, "VK_API_VERSION", "5.199")


async def _vk_upload_photo(content, mime):
    """Загружает картинку в VK, возвращает attachment 'photo{id}_{id}'."""
    import httpx
    token = _vk_token()
    if not token:
        raise ChannelError("VK token not found in config")
    api = _vk_api()
    params = {"access_token": token, "v": _vk_version()}
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.get(api + "photos.getMessagesUploadServer", params=params)
        d = r.json()
        if d.get("error"):
            raise ChannelError("VK getUploadServer: " + str(d["error"])[:200])
        upload_url = d["response"]["upload_url"]
        r2 = await c.post(upload_url,
                          files={"photo": ("image.jpg", content, mime or "image/jpeg")})
        up = r2.json()
        if not up.get("photo"):
            raise ChannelError("VK upload: " + str(up)[:200])
        r3 = await c.get(api + "photos.saveMessagesPhoto", params={
            **params, "server": up["server"], "photo": up["photo"], "hash": up["hash"]})
        sd = r3.json()
        if sd.get("error"):
            raise ChannelError("VK savePhoto: " + str(sd["error"])[:200])
        ph = sd["response"][0]
        return "photo" + str(ph["owner_id"]) + "_" + str(ph["id"])


async def send_to_client_with_image_raw(user_id, text, image_token=None, buttons=None,
                                        fmt="markdown", org_id=None, duplicate=None):
    """Сообщение с картинкой. МАХ получает свой токен, ВК — своё вложение.

    Если байты картинки не нашлись, ВК получает текст без фото (лог: no attachment for vk).
    """
    uid_str = str(user_id or "")
    if not uid_str or uid_str.startswith("phone:"):
        raise ChannelError("no channel for user")

    if org_id is None:
        org_id = _client_org_id(uid_str)

    bytes_ = None
    mime = "image/jpeg"
    if image_token:
        bytes_, mime = _stored_image_bytes(image_token)
        if not bytes_:
            log.warning("with_image: байты не найдены для токена — VK получит текст без фото")

    if _should_duplicate(duplicate, org_id):
        targets = get_channels_for_client(uid_str, org_id)
    else:
        one = get_channel_for_client(uid_str, org_id)
        targets = [one] if one and one[0] else []
    if not targets:
        raise ChannelError("no channel for user")

    result, last_exc, sent_any = None, None, False
    for channel, platform_uid, platform in targets:
        try:
            if platform == "vk":
                if bytes_:
                    att = await _vk_upload_photo(bytes_, mime)
                    result = await channel.send_with_image(
                        platform_uid, text, att, buttons=buttons, fmt=fmt)
                else:
                    log.warning("with_image: no attachment for vk, %s", uid_str)
                    result = await channel.send_message(
                        platform_uid, text, buttons=buttons, fmt=fmt)
            else:
                result = await channel.send_with_image(
                    platform_uid, text, image_token, buttons=buttons, fmt=fmt)
            sent_any = True
        except UserBlocked:
            raise
        except Exception as e:
            last_exc = e
            log.warning("with_image (%s) failed for %s: %s",
                        platform, uid_str, str(e)[:200])
    if sent_any:
        return result
    raise ChannelError(str(last_exc or "all channels failed"))


async def send_to_client_with_file_raw(user_id, text, file_token, buttons=None,
                                       fmt="markdown", org_id=None, duplicate=None):
    """Сообщение с файлом (.ics и т.п.). duplicate/org_id — как выше."""
    uid_str = str(user_id or "")
    if not uid_str or uid_str.startswith("phone:"):
        raise ChannelError("no channel for user")

    async def _one(channel, platform_uid):
        return await channel.send_with_file(platform_uid, text, file_token,
                                            buttons=buttons, fmt=fmt)

    return await _send_raw_multichannel(uid_str, org_id, duplicate, _one)


async def edit_message_for_client(user_id, message_id, text, buttons=None, fmt="markdown"):
    """Редактирует сообщение. Возвращает dict | None. Не бросает."""
    uid_str = str(user_id or "")
    if not uid_str:
        return None
    channel, platform_uid, _platform = get_channel_for_client(uid_str)
    if channel is None:
        return None
    try:
        return await channel.edit_message(platform_uid, message_id, text, buttons=buttons, fmt=fmt)
    except Exception as e:
        log.warning("edit_message_for_client failed for %s/%s: %s", uid_str, message_id, e)
        return None


async def delete_message_for_client(user_id, message_id):
    """Удаляет сообщение. Возвращает dict | None. Не бросает."""
    uid_str = str(user_id or "")
    if not uid_str:
        return None
    channel, platform_uid, _platform = get_channel_for_client(uid_str)
    if channel is None:
        return None
    try:
        return await channel.delete_message(platform_uid, message_id)
    except Exception as e:
        log.warning("delete_message_for_client failed for %s/%s: %s", uid_str, message_id, e)
        return None


async def upload_file_for_client(user_id, content, filename: str,
                                 mime: str = "text/calendar",
                                 upload_type: str = "file") -> str:
    """Загружает файл в канал клиента. Возвращает token или бросает ChannelError.

    Используется для .ics, экспортов, вложений. Канал выбирается по identity
    клиента — после E4 автоматически уйдёт в VK, если клиент там.
    """
    uid_str = str(user_id or "")
    if not uid_str or uid_str.startswith("phone:"):
        raise ChannelError("no channel for user")
    channel, _platform_uid, _platform = get_channel_for_client(uid_str)
    if channel is None:
        raise ChannelError("no channel for user")
    try:
        return await channel.upload_file(
            content, filename=filename, mime=mime, upload_type=upload_type,
            user_id=user_id,
        )
    except TypeError:
        # Каналы, где upload_file ещё без user_id (MAX), — вызов по-старому.
        return await channel.upload_file(
            content, filename=filename, mime=mime, upload_type=upload_type,
        )