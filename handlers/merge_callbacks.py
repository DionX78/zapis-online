"""E4.5: колбэки склейки профилей (mg:yes / mg:no)."""
import logging

from core import merge as merge_core

log = logging.getLogger(__name__)


async def handle(uid, payload, message_id):
    if not payload.startswith("mg:"):
        return False
    parts = payload.split(":")
    if len(parts) != 3 or parts[1] not in ("yes", "no"):
        return False
    action, mid = parts[1], parts[2]
    try:
        merge_id = int(mid)
    except ValueError:
        return False
    try:
        await merge_core.handle_response(merge_id, str(uid), action == "yes")
    except NotImplementedError:
        log.warning("merge: кнопочная отправка ещё не подключена")
    except Exception as e:
        log.warning("merge callback failed: %s", e)
    return True
