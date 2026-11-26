from datetime import date as _date, timedelta

from core.messaging import send_to_client_raw, edit_message_for_client
from storage.db import (
    is_superadmin, is_admin, get_admin_org,
    add_admin, remove_admin, list_admins,
    add_pending, list_pending, remove_pending,
    create_org, list_orgs, get_org,
    get_stats, add_slot, create_branch, create_doctor,
    list_branches, count_slots_today,
)


async def try_handle(uid: int, text: str) -> bool:
    low = text.lower()

    if low == "/sadmin":
        if not is_superadmin(uid):
            await send_to_client_raw(uid, "Нет доступа.")
            return True
        await show_superadmin_panel(uid)
        return True

    if low == "/iam":
        if is_admin(uid):
            await send_to_client_raw(uid, "Вы уже администратор.")
            return True
        add_pending(uid, first_name="", username="")
        await send_to_client_raw(
            uid,
            "✅ Заявка на роль администратора принята.\n"
            "Ожидайте подтверждения от суперадмина.",
        )
        return True

    if low.startswith("/genslots"):
        if not (is_superadmin(uid) or is_admin(uid)):
            await send_to_client_raw(uid, "Нет доступа.")
            return True
        parts = text.split()
        if len(parts) != 4 or not all(p.isdigit() for p in parts[1:]):
            await send_to_client_raw(
                uid,
                "Использование: /genslots <org_id> <branch_id> <doctor_id>\n"
                "Создаст слоты на 14 дней вперёд:\n"
                "Пн–Пт 9:00–18:00, Сб 9:00–14:00, шаг 30 мин.",
            )
            return True
        org_id = int(parts[1])
        branch_id = int(parts[2])
        doctor_id = int(parts[3])
        created = _gen_slots(org_id, branch_id, doctor_id)
        await send_to_client_raw(
            uid,
            f"✅ Создано {created} слотов на 14 дней вперёд.",
        )
        return True

    if low.startswith("/setadmin"):
        if not is_superadmin(uid):
            await send_to_client_raw(uid, "Нет доступа.")
            return True
        parts = text.split()
        if len(parts) == 3 and parts[1].lstrip("-").isdigit() and parts[2].isdigit():
            target_id = int(parts[1])
            org_id = int(parts[2])
            org = get_org(org_id)
            if not org:
                await send_to_client_raw(uid, "Организация не найдена.")
                return True
            add_admin(target_id, "", org_id, uid)
            remove_pending(target_id)
            await send_to_client_raw(uid, f"✅ {target_id} назначен админом «{org['name']}».")
            try:
                await send_to_client_raw(target_id, f"Вы назначены администратором «{org['name']}».")
            except Exception:
                pass
        else:
            await send_to_client_raw(uid, "Использование: /setadmin <user_id> <org_id>")
        return True

    return False


def _gen_slots(org_id, branch_id, doctor_id):
    today = _date.today()
    created = 0
    for offset in range(14):
        d = today + timedelta(days=offset)
        wd = d.weekday()
        if wd == 6:
            continue
        if wd == 5:
            start, end = 9, 14
        else:
            start, end = 9, 18
        h = start
        m = 0
        while h < end or (h == end and m == 0):
            if h == end:
                break
            date_str = d.isoformat()
            time_str = f"{h:02d}:{m:02d}"
            add_slot(org_id, branch_id, doctor_id, date_str, time_str)
            created += 1
            m += 30
            if m == 60:
                m = 0
                h += 1
    return created


async def show_superadmin_panel(uid: int, message_id: str | None = None):
    text = "🔧 Панель суперадмина\n\nВыберите действие:"
    buttons = [
        [{"type": "callback", "text": "👤 Назначить админа", "payload": "sa:assign"}],
        [{"type": "callback", "text": "📋 Список админов", "payload": "sa:list_admins"}],
        [{"type": "callback", "text": "🏢 Создать организацию", "payload": "sa:create_org"}],
        [{"type": "callback", "text": "📋 Список организаций", "payload": "sa:list_orgs"}],
        [{"type": "callback", "text": "📊 Статистика", "payload": "sa:stats"}],
        [{"type": "callback", "text": "📱 Mini App", "payload": "sa:mini_app"}],
        [{"type": "callback", "text": "🚪 Выйти", "payload": "sa:exit"}],
    ]
    if message_id:
        await edit_message_for_client(uid, message_id, text, buttons=buttons)
    else:
        await send_to_client_raw(uid, text, buttons)