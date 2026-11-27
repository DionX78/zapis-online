"""Реализация канала MAX. Делегирует в core.max_client."""
import logging

from core import max_client as mx
from core.channels.base import Channel, UserBlocked, ChannelError

log = logging.getLogger(__name__)


class MaxChannel(Channel):
    platform = "max"

    async def send_message(self, user_id, text, buttons=None, fmt=None):
        try:
            return await mx.send_message(int(user_id), text, buttons=buttons, fmt=fmt)
        except mx.MaxUserBlocked as e:
            raise UserBlocked(str(e))
        except Exception as e:
            raise ChannelError(str(e))

    async def send_with_image(self, user_id, text, image_token, buttons=None, fmt=None):
        try:
            return await mx.send_message_with_image(
                int(user_id), text, image_token, buttons=buttons, fmt=fmt,
            )
        except mx.MaxUserBlocked as e:
            raise UserBlocked(str(e))
        except Exception as e:
            raise ChannelError(str(e))

    async def send_with_file(self, user_id, text, file_token, buttons=None, fmt=None):
        try:
            return await mx.send_message_with_file(
                int(user_id), text, file_token, buttons=buttons, fmt=fmt,
            )
        except mx.MaxUserBlocked as e:
            raise UserBlocked(str(e))
        except Exception as e:
            raise ChannelError(str(e))

    async def edit_message(self, user_id, message_id, text, buttons=None, fmt=None):
        try:
            return await mx.edit_message(message_id, text, buttons=buttons, fmt=fmt)
        except Exception as e:
            log.warning("MaxChannel.edit_message failed: %s", e)
            return None

    async def delete_message(self, user_id, message_id):
        try:
            return await mx.delete_message(message_id)
        except Exception as e:
            log.warning("MaxChannel.delete_message failed: %s", e)
            return None

    async def upload_file(self, content, filename, mime="text/calendar", upload_type="file"):
        try:
            result = await mx.upload_file(content, filename=filename, mime=mime, upload_type=upload_type)
            try:
                _cache_max_upload(result, content, mime)
            except Exception:
                pass
            return result
        except Exception as e:
            raise ChannelError(str(e))

    async def set_commands(self, commands):
        try:
            await mx.set_commands(commands)
        except Exception as e:
            log.warning("MaxChannel.set_commands failed: %s", e)

# --- E4.5: кэш байтов загруженных картинок (нужен для перезалива в VK) ---
def _cache_max_upload(result, content, mime):
    import hashlib
    import json
    import os

    if content is None:
        return
    if hasattr(content, "read"):
        content = content.read()
    if not content:
        return

    def _find(res):
        if isinstance(res, dict):
            for k, v in res.items():
                if isinstance(v, str) and "token" in k.lower() and len(v) > 4:
                    return v
                t = _find(v)
                if t:
                    return t
        elif isinstance(res, list):
            for v in res:
                t = _find(v)
                if t:
                    return t
        return None

    token = _find(result)
    if not token:
        return
    d = os.path.join(os.getcwd(), "vk_photo_cache")
    os.makedirs(d, exist_ok=True)
    h = hashlib.sha1(str(token).encode("utf-8")).hexdigest()
    path = os.path.join(d, h + ".bin")
    with open(path, "wb") as f:
        f.write(bytes(content))
    idx = os.path.join(d, "index.json")
    m = {}
    if os.path.exists(idx):
        try:
            with open(idx, "r", encoding="utf-8") as f:
                m = json.load(f)
        except Exception:
            m = {}
    m[str(token)] = {"path": path, "mime": mime or "image/jpeg"}
    with open(idx, "w", encoding="utf-8") as f:
        json.dump(m, f)
