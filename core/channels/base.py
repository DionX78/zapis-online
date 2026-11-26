"""Интерфейс канала (MAX, VK, виджет).

Любой канал реализации:
- send_message(user_id, text, buttons, fmt) -> dict (или бросает)
- send_with_image(user_id, text, image_token, buttons, fmt) -> dict
- send_with_file(user_id, text, file_token, buttons, fmt) -> dict
- edit_message(user_id, message_id, text, buttons, fmt) -> dict | None
- delete_message(user_id, message_id) -> dict | None
- upload_file(content, filename, mime, upload_type) -> str (token)
- set_commands(commands) -> None

Исключения:
- MaxUserBlocked / VkUserBlocked (по факту унифицированный UserBlocked)
- ChannelError для остальных случаев
"""
from abc import ABC, abstractmethod


class UserBlocked(Exception):
    """Клиент заблокировал бота в канале."""
    pass


class ChannelError(Exception):
    """Прочие ошибки канала (сеть, API, retry exhausted)."""
    pass


class Channel(ABC):
    platform: str = ""  # 'max' | 'vk' | 'widget'

    @abstractmethod
    async def send_message(self, user_id, text: str, buttons: list | None = None, fmt: str | None = None) -> dict:
        ...

    @abstractmethod
    async def send_with_image(self, user_id, text: str, image_token: str, buttons: list | None = None, fmt: str | None = None) -> dict:
        ...

    @abstractmethod
    async def send_with_file(self, user_id, text: str, file_token: str, buttons: list | None = None, fmt: str | None = None) -> dict:
        ...

    @abstractmethod
    async def edit_message(self, user_id, message_id, text: str, buttons: list | None = None, fmt: str | None = None) -> dict | None:
        ...

    @abstractmethod
    async def delete_message(self, user_id, message_id) -> dict | None:
        ...

    @abstractmethod
    async def upload_file(self, content, filename: str, mime: str = "text/calendar", upload_type: str = "file") -> str:
        ...

    @abstractmethod
    async def set_commands(self, commands: list) -> None:
        ...