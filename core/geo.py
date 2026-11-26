"""Утилиты геолокации: ссылки на Яндекс.Карты и 2ГИС."""
from urllib.parse import quote

from config import MAP_PROVIDERS


_VALID_PROVIDERS = {p[0] for p in MAP_PROVIDERS}
DEFAULT_PROVIDER = "both"


def yandex_maps_link(address: str) -> str:
    """Ссылка на Яндекс.Карты по текстовому адресу."""
    if not address or not address.strip():
        return ""
    return "https://yandex.ru/maps/?text=" + quote(address.strip(), safe="")


def gis_maps_link(address: str) -> str:
    """Ссылка на 2ГИС по текстовому адресу."""
    if not address or not address.strip():
        return ""
    return "https://2gis.ru/search/" + quote(address.strip(), safe="")


def _resolve_provider(org_id, provider):
    if provider and provider in _VALID_PROVIDERS:
        return provider
    if org_id is not None:
        try:
            from storage.db import get_org_settings
            settings = get_org_settings(org_id)
            p = settings.get("map_provider", DEFAULT_PROVIDER)
            if p in _VALID_PROVIDERS:
                return p
        except Exception:
            pass
    return DEFAULT_PROVIDER


def route_lines(address: str, org_id=None, provider: str | None = None) -> str:
    """Markdown-фрагмент для сообщения бота:
       📍 <адрес>
       🗺 [Яндекс.Карты](<link>)        (если provider=yandex или both)
       🗺 [2ГИС](<link>)                (если provider=2gis или both)

    provider: явно переданный идентификатор ("yandex"/"2gis"/"both").
    Если не передан — берём из настроек организации по org_id.
    Если ничего не известно — "both".
    Пустой адрес → пустая строка.
    """
    if not address or not address.strip():
        return ""
    addr = address.strip()
    p = _resolve_provider(org_id, provider)

    lines = [f"📍 {addr}"]
    if p in ("yandex", "both"):
        link = yandex_maps_link(addr)
        if link:
            lines.append(f"🗺 [Яндекс.Карты]({link})")
    if p in ("2gis", "both"):
        link = gis_maps_link(addr)
        if link:
            lines.append(f"🗺 [2ГИС]({link})")
    return "\n".join(lines) + "\n"