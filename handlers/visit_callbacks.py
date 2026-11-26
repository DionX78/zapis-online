"""«Закрытие дня» в чате: отметки «Пришёл / Не пришёл» без Mini App."""
import logging
from datetime import date as _date

from core.messaging import send_to_client_raw, edit_message_for_client
from storage.db import (
    is_admin, is_superadmin, get_admin_org, list_orgs,
    get_request, update_request_status, list_visits_for_date, get_org,
)

log = logging.getLogger(__name__)

STATUS_ICON = {
    "pending": "🟡",
    "confirmed": "✅",
    "done": "🏁",
    "no_show": "🚫",
    "cancelled": "❌",
}

STATUS_LABEL = {
    "pending": "ожидает",
    "confirmed": "подтверждена",
    "done": "пришёл",
    "no_show": "не пришёл",
    "cancelled": "отменена",
}


def _resolve_org(uid, requested_org=None):
    if is_superadmin(uid):
        if requested_org:
            return requested_org
        orgs = list_orgs()
        return orgs[0]["id"] if len(orgs) == 1 else None
    return get_admin_org(uid)


def _fmt_time(scheduled_at):
    return (scheduled_at or "")[11:16]


async def send_today(uid, requested_org=None):
    if not is_admin(uid):
        await send_to_client_raw(uid, "Нет доступа.")
        return
    org_id = _resolve_org(uid, requested_org)
    if not org_id:
        orgs = list_orgs()
        await send_to_client_raw(
            uid,
            "Выберите организацию:",
            buttons=[[{"type": "callback", "text": f"🏢 {o['name']}",
                       "payload": f"vis:today:{o['id']}"}] for o in orgs],
        )
        return

    today = _date.today().isoformat()
    rows = list_visits_for_date(org_id, today)
    org = get_org(org_id)
    org_name = org["name"] if org else ""

    head = f"📋 **{today} · {org_name}**\n"
    if not rows:
        await send_to_client_raw(uid, head + "\nНа сегодня записей нет.")
        return

    counters = {}
    for r in rows:
        st = r["status"]
        counters[st] = counters.get(st, 0) + 1
    total = len(rows)
    done = counters.get("done", 0)
    noshow = counters.get("no_show", 0)
    waiting = counters.get("pending", 0) + counters.get("confirmed", 0)

    text = head
    text += (
        f"\nВсего: {total} · пришли: {done} · не пришли: {noshow}"
        f" · без отметки: {waiting}\n"
    )
    if waiting:
        text += "\nОтметьте, кто пришёл — от этого зависят «Спасибо за визит» и сегменты клиентов.\n"

    for r in rows:
        rid = r["id"]
        sname = r["service_name"]
        sched = r["scheduled_at"]
        phone = r["phone"]
        status = r["status"]
        doctor = r["doctor"]
        icon = STATUS_ICON.get(status, "•")
        line = f"\n{icon} **{_fmt_time(sched)}** · {sname}"
        if doctor:
            line += f" · {doctor}"
        if phone:
            line += f"\n    {phone}"
        text += line

    await send_to_client_raw(uid, text, fmt="markdown")

    pending_rows = [r for r in rows if r["status"] in ("confirmed", "pending")]
    if not pending_rows:
        await send_to_client_raw(uid, "Все записи на сегодня отмечены 👍")
        return

    for r in pending_rows:
        rid = r["id"]
        sname = r["service_name"]
        sched = r["scheduled_at"]
        phone = r["phone"]
        status = r["status"]
        doctor = r["doctor"]

        caption = f"**{_fmt_time(sched)}** · {sname}"
        if doctor:
            caption += f" · {doctor}"
        if phone:
            caption += f"\n{phone}"
        caption += f"\nСтатус: {STATUS_LABEL.get(status, status)}"
        buttons = [[
            {"type": "callback", "text": "✅ Пришёл", "payload": f"vis:done:{rid}"},
            {"type": "callback", "text": "🚫 Не пришёл", "payload": f"vis:no:{rid}"},
        ]]
        try:
            await send_to_client_raw(uid, caption, buttons=buttons, fmt="markdown")
        except Exception as e:
            log.warning("send_today button for #%s failed: %s", rid, e)


async def handle(uid, payload, message_id=None):
    """vis:today | vis:done:<id> | vis:no:<id>"""
    if not payload.startswith("vis:"):
        return False

    parts = payload.split(":")
    if parts[1] == "today":
        requested_org = None
        if len(parts) == 3:
            try:
                requested_org = int(parts[2])
            except ValueError:
                requested_org = None
        await send_today(uid, requested_org)
        return True
    if len(parts) != 3 or parts[1] not in ("done", "no"):
        return True

    if not is_admin(uid):
        await send_to_client_raw(uid, "Нет доступа.")
        return True

    try:
        rid = int(parts[2])
    except ValueError:
        return True

    req = get_request(rid)
    if not req:
        await send_to_client_raw(uid, f"Заявка #{rid} не найдена.")
        return True

    org_id = req["org_id"]
    sname = req["service_name"]
    sched = req["scheduled_at"]
    phone = req["phone"]
    status = req["status"]

    my_org = _resolve_org(uid)
    if my_org is not None and org_id != my_org:
        await send_to_client_raw(uid, "Заявка другой организации.")
        return True

    new_status = "done" if parts[1] == "done" else "no_show"
    if not update_request_status(rid, new_status, admin_id=uid):
        await send_to_client_raw(
            uid,
            f"Заявка #{rid} в статусе «{STATUS_LABEL.get(status, status)}» — "
            f"отметить «{STATUS_LABEL[new_status]}» можно только для подтверждённой.",
        )
        return True

    msg = (
        f"{STATUS_ICON[new_status]} #{rid} — {STATUS_LABEL[new_status]}\n"
        f"{sname}\n🕐 {sched}"
    )
    if phone:
        msg += f"\n📞 {phone}"
    try:
        await send_to_client_raw(uid, msg)
    except Exception as e:
        log.warning("visit confirm to admin %s failed: %s", uid, e)
    return True