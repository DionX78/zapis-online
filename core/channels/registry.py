"""Реестр каналов.

Сейчас реализован только MAX. В E4 добавим VK. В E3 — мультибот:
у клиента может быть несколько identity (MAX + VK), отправляем в канал
по настройке организации (channel_default) либо по приоритету
(is_primary → последняя активность).

Интерфейс:
  get_channel(platform) -> Channel
  get_channel_for_client(user_id, org_id=None) -> (Channel|None, platform_user_id, platform)
  get_channels_for_client(user_id, org_id=None) -> [(Channel, platform_user_id, platform), ...]

Регистр импортирует storage.db лениво (внутри функций), чтобы не ловить
циклический импорт при старте приложения.
"""
import logging

from core.channels.base import Channel
from core.channels.max import MaxChannel
from core.channels.vk import VkChannel

log = logging.getLogger(__name__)

_CHANNELS: dict[str, Channel] = {
    "max": MaxChannel(),
    "vk": VkChannel(),
}


def get_channel(platform: str) -> Channel:
    ch = _CHANNELS.get(platform)
    if not ch:
        raise ValueError(f"Unknown platform: {platform}")
    return ch


def _default_platform(org_id=None) -> str:
    """Канал по умолчанию из настроек организации (фоллбэк — max)."""
    if org_id is None:
        return "max"
    try:
        import storage.db as db

        settings = db.get_org_settings(int(org_id)) or {}
        platform = settings.get("channel_default") or "max"
        return platform if platform in _CHANNELS else "max"
    except Exception as e:  # настройки не прочитались — не роняем отправку
        log.warning("channel_default lookup failed for org %s: %s", org_id, e)
        return "max"


def _identity_platforms(user_id: str):
    """Паспорта клиента в порядке приоритета: [(platform, platform_uid), ...]."""
    try:
        import storage.db as db

        rows = db.get_client_identities(user_id) or []
    except Exception as e:
        log.warning("identities lookup failed for %s: %s", user_id, e)
        return []
    return [(r["platform"], str(r["platform_uid"])) for r in rows]


def get_channels_for_client(user_id, org_id=None):
    """Все доступные каналы клиента — в порядке приоритета отправки.

    Первым идёт канал по умолчанию организации (если у клиента он есть),
    дальше — остальные паспорта (is_primary, затем последняя активность).
    Пустой список — у клиента нет ни одного живого канала (напр. phone:...).
    """
    uid_str = str(user_id or "")
    if not uid_str or uid_str.startswith("phone:"):
        return []

    identities = [(p, u) for p, u in _identity_platforms(uid_str) if p in _CHANNELS]
    if not identities:
        # Составной id ('vk:123', 'phone:+7...') — не MAX-аккаунт: фоллбэк
        # на MAX невозможен, иначе сообщение уйдёт в никуда.
        if ":" in uid_str:
            return []
        # Легаси-клиент без паспорта: считаем, что он в MAX под своим user_id.
        return [(_CHANNELS["max"], uid_str, "max")]

    default = _default_platform(org_id)
    identities.sort(key=lambda item: 0 if item[0] == default else 1)
    return [(get_channel(platform), platform_uid, platform)
            for platform, platform_uid in identities]


def get_channel_for_client(user_id, org_id=None) -> tuple[Channel, str, str]:
    """Возвращает (channel, platform_user_id, platform) для основной отправки.

    channel is None — у клиента нет ни одного канала (phone-only клиент,
    записанный администратором по телефону). Вызывающий код обязан это учесть.
    """
    channels = get_channels_for_client(user_id, org_id)
    if not channels:
        return None, str(user_id or ""), ""
    return channels[0]
