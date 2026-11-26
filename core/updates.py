"""Универсальный объект Update — то, что приходит от платформы.

Dispatcher не знает, MAX это, VK или виджет. Платформенная специфика —
в .raw. Всё, что нужно handlers — в явных полях.
"""
from dataclasses import dataclass, field


@dataclass
class Update:
    platform: str            # 'max' | 'vk' | 'widget'
    type: str                # 'message_created' | 'message_callback' | 'bot_started'
    user_id: str             # платформенный uid (строка; VK может быть > 2^31)
    bot_id: int | None = None
    user_info: dict = field(default_factory=dict)   # first_name, last_name, username
    text: str = ""           # для message_created
    payload: str = ""        # для message_callback
    message_id: str | None = None   # для message_callback (edit_message)
    start_param: str = ""    # из deep link (если канал поддерживает)
    raw: dict = field(default_factory=dict)