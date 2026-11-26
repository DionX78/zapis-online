from core.messaging import send_to_client_raw, edit_message_for_client
from storage.db import (
    is_superadmin, list_pending, remove_pending,
    list_orgs, create_org, get_org,
    add_admin, remove_admin, list_admins,
    get_stats, set_state, get_state, clear_state,
)
import config

STATE_CREATE_ORG = "SA_CREATE_ORG"
STATE_ASSIGN_ORG = "SA_ASSIGN_ORG"


async def handle(uid: int, payload: str, message_id: str | None = None) -> bool:
    if not payload.startswith("sa:"):
        return False

    if not is_superadmin(uid):
        await _edit_or_send(uid, message_id, "Нет доступа.")
        return True

    action = payload.split(":", 1)[1]

    if action == "exit":
        clear_state(uid)
        await _edit_or_send(uid, message_id, "Панель закрыта. Напишите /sadmin для возврата.")
        return True

    if action == "assign":
        await _show_pending(uid, message_id)
        return True

    if action == "create_org":
        set_state(uid, STATE_CREATE_ORG)
        await _edit_or_send(
            uid, message_id,
            "🏢 Введите название новой организации одним сообщением:",
            [[{"type": "callback", "text": "← Назад", "payload": "sa:panel"}]],
        )
        return True

    if action == "list_orgs":
        orgs = list_orgs()
        if not orgs:
            text = "Организаций пока нет."
        else:
            text = "🏢 Организации:\n" + "\n".join(f"#{o['id']} — {o['name']}" for o in orgs)
        await _edit_or_send(uid, message_id, text,
                            [[{"type": "callback", "text": "← Назад", "payload": "sa:panel"}]])
        return True

    if action == "list_admins":
        rows = list_admins()
        if not rows:
            text = "Админов пока нет."
        else:
            lines = ["📋 Администраторы:\n"]
            for r in rows:
                lines.append(f"— {r['user_id']} {r['first_name'] or ''} → «{r['name'] or '—'}»")
            text = "\n".join(lines)
        await _edit_or_send(uid, message_id, text,
                            [[{"type": "callback", "text": "← Назад", "payload": "sa:panel"}]])
        return True

    if action == "stats":
        total, by_service = get_stats()
        lines = [f"📊 Всего записей: {total}", ""]
        for r in by_service:
            lines.append(f"{r['service_name']}: {r['n']}")
        await _edit_or_send(uid, message_id, "\n".join(lines),
                            [[{"type": "callback", "text": "← Назад", "payload": "sa:panel"}]])
        return True

    if action == "mini_app":
        bot_username = config.MINI_APP_BOT_USERNAME
        if not bot_username:
            await _edit_or_send(
                uid, message_id,
                "❌ Не задан MINI_APP_BOT_USERNAME в .env.\n"
                "Узнать username можно из ответа /me (поле username).",
                [[{"type": "callback", "text": "← Назад", "payload": "sa:panel"}]],
            )
            return True
        mini_url = f"https://max.ru/{bot_username}?startapp="
        await _edit_or_send(
            uid, message_id,
            "📱 Mini App для клиента.\n\n"
            "Нажми кнопку — откроется календарь записи прямо в MAX:",
            [
                [{"type": "link", "text": "📅 Открыть Mini App", "url": mini_url}],
                [{"type": "callback", "text": "← Назад", "payload": "sa:panel"}],
            ],
        )
        return True

    if action == "panel":
        clear_state(uid)
        from handlers.admin import show_superadmin_panel
        await show_superadmin_panel(uid, message_id)
        return True

    if action.startswith("pick_pending:"):
        target_id = action.split(":", 1)[1]
        orgs = list_orgs()
        if not orgs:
            await _edit_or_send(
                uid, message_id,
                "Сначала создайте хотя бы одну организацию (🏢 Создать организацию).",
                [[{"type": "callback", "text": "← Назад", "payload": "sa:panel"}]],
            )
            return True
        set_state(uid, STATE_ASSIGN_ORG, {"target_id": target_id})
        buttons = [[{"type": "callback", "text": f"🏢 {o['name']}", "payload": f"sa:pick_org:{o['id']}"}]
                   for o in orgs]
        buttons.append([{"type": "callback", "text": "← Назад", "payload": "sa:assign"}])
        await _edit_or_send(uid, message_id, "Выберите организацию для этого админа:", buttons)
        return True

    if action.startswith("pick_org:"):
        org_id = int(action.split(":", 1)[1])
        state, ctx = get_state(uid)
        target_id = ctx.get("target_id")
        if not target_id:
            await _edit_or_send(uid, message_id, "Ошибка: не выбран пользователь.")
            return True
        org = get_org(org_id)
        add_admin(int(target_id), "", org_id, uid)
        remove_pending(target_id)
        clear_state(uid)
        await _edit_or_send(uid, message_id,
                            f"✅ {target_id} назначен админом «{org['name']}».",
                            [[{"type": "callback", "text": "← В панель", "payload": "sa:panel"}]])
        try:
            await send_to_client_raw(int(target_id), f"Вы назначены администратором «{org['name']}».")
        except Exception:
            pass
        return True

    if action.startswith("del_admin:"):
        target_id = action.split(":", 1)[1]
        remove_admin(target_id)
        await _edit_or_send(uid, message_id, f"Пользователь {target_id} снят с роли админа.",
                            [[{"type": "callback", "text": "← Назад", "payload": "sa:list_admins"}]])
        return True

    return True


async def _show_pending(uid, message_id):
    rows = list_pending()
    if not rows:
        await _edit_or_send(
            uid, message_id,
            "Ожидающих назначения нет.\n\n"
            "Попросите владельца написать боту /iam.",
            [[{"type": "callback", "text": "← Назад", "payload": "sa:panel"}]],
        )
        return
    buttons = []
    for r in rows:
        uid_str = r["user_id"]
        fn = r["first_name"]
        label = f"👤 {uid_str} {fn or ''}".strip()
        buttons.append([{"type": "callback", "text": label, "payload": f"sa:pick_pending:{uid_str}"}])
    buttons.append([{"type": "callback", "text": "← Назад", "payload": "sa:panel"}])
    await _edit_or_send(uid, message_id, "Выберите пользователя для назначения админом:", buttons)


async def _edit_or_send(uid, message_id, text, buttons=None):
    if message_id:
        await edit_message_for_client(uid, message_id, text, buttons=buttons)
    else:
        await send_to_client_raw(uid, text, buttons)


async def handle_text(uid: int, text: str) -> bool:
    state, ctx = get_state(uid)
    if not is_superadmin(uid):
        return False

    if state == STATE_CREATE_ORG:
        name = text.strip()
        if not name:
            await send_to_client_raw(uid, "Название не может быть пустым.")
            return True
        oid = create_org(name)
        clear_state(uid)
        await send_to_client_raw(uid, f"✅ Организация «{name}» создана (id={oid}).")
        from handlers.admin import show_superadmin_panel
        await show_superadmin_panel(uid)
        return True

    return False