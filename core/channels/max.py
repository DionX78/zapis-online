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
            return await mx.upload_file(content, filename=filename, mime=mime, upload_type=upload_type)
        except Exception as e:
            raise ChannelError(str(e))

    async def set_commands(self, commands):
        try:
            await mx.set_commands(commands)
        except Exception as e:
            log.warning("MaxChannel.set_commands failed: %s", e)