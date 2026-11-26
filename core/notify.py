"""Отправка уведомлений администраторам организации или суперадмину.

Идёт через core.messaging.send_to_client — единую точку отправки.
После E4 будет работать и с VK, если админ там.
"""
import logging

from core.messaging import send_to_client
from storage.db import list_admins, admins_of_org
import config

log = logging.getLogger(__name__)


async def notify_admins(text: str, org_id=None, buttons=None):
    """Если org_id задан — шлём админам этой организации.
    Если нет — всем админам + суперадмину.
    buttons — inline-кнопки (список рядов), прикрепляются к сообщению.
    """
    recipients = set()
    if org_id is not None:
        recipients.update(admins_of_org(org_id))
    else:
        for r in list_admins():
            recipients.add(r["user_id"])
    if config.SUPERADMIN_ID:
        recipients.add(str(config.SUPERADMIN_ID))

    for r in recipients:
        status, err = await send_to_client(r, text, buttons=buttons, fmt=None)
        if status not in ("sent", "no_max"):
            log.warning("notify_admins failed for %s: status=%s err=%s", r, status, err)