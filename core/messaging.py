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


async def send_to_client_raw(user_id, text, buttons=None, fmt="markdown"):
    """Отправляет сообщение клиенту. Возвращает dict (ответ API) или бросает.

    Бросает UserBlocked — клиент заблокировал бота.
    Бросает ChannelError — прочие ошибки.
    Используется там, где нужен результат / retry (рассылки, .ics, отчёты).
    """
    uid_str = str(user_id or "")
    if not uid_str or uid_str.startswith("phone:"):
        raise ChannelError("no channel for user")

    channel, platform_uid, _platform = get_channel_for_client(uid_str)
    if channel is None:
        raise ChannelError("no channel for user")
    return await channel.send_message(platform_uid, text, buttons=buttons, fmt=fmt)


async def send_to_client_with_image_raw(user_id, text, image_token, buttons=None, fmt="markdown"):
    """Сообщение с картинкой. Возвращает dict или бросает. Для рассылок."""
    uid_str = str(user_id or "")
    if not uid_str or uid_str.startswith("phone:"):
        raise ChannelError("no channel for user")
    channel, platform_uid, _platform = get_channel_for_client(uid_str)
    if channel is None:
        raise ChannelError("no channel for user")
    return await channel.send_with_image(platform_uid, text, image_token, buttons=buttons, fmt=fmt)


async def send_to_client_with_file_raw(user_id, text, file_token, buttons=None, fmt="markdown"):
    """Сообщение с файлом. Возвращает dict или бросает. Для .ics/экспортов."""
    uid_str = str(user_id or "")
    if not uid_str or uid_str.startswith("phone:"):
        raise ChannelError("no channel for user")
    channel, platform_uid, _platform = get_channel_for_client(uid_str)
    if channel is None:
        raise ChannelError("no channel for user")
    return await channel.send_with_file(platform_uid, text, file_token, buttons=buttons, fmt=fmt)


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