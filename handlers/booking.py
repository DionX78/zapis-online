import re

from core.messaging import send_to_client_raw, edit_message_for_client
from core.notify import notify_admins
from storage.db import (
    get_service, get_services, add_history,
    get_history_upcoming, get_history_all,
    set_state, get_state, clear_state, get_admin_role,
    get_client, upsert_client,
    get_org, list_orgs,
)
import config

STATUS_LABELS = {
    "new": "новая",
    "pending": "ожидает подтверждения",
    "confirmed": "подтверждена",
    "done": "завершена",
    "cancelled": "отменена",
    "draft": "черновик",
}

STATUS_EMOJI = {
    "new": "🆕",
    "pending": "🟡",
    "confirmed": "✅",
    "done": "🏁",
    "cancelled": "❌",
    "draft": "📝",
}


def _row_get(row, key, default=None):
    """Безопасное чтение из sqlite3.Row — не падает, если ключа нет."""
    try:
        return row[key]
    except (IndexError, KeyError):
        return default


def _resolve_org_name(uid=None, org_id=None):
    """Имя организации для приветствия. Fallback: client.org_id → первая org → 'наша клиника'."""
    if not org_id and uid:
        try:
            client = get_client(uid)
            if client and client["org_id"]:
                org_id = client["org_id"]
        except Exception:
            pass
    if not org_id:
        try:
            orgs = list_orgs()
            if orgs:
                org_id = orgs[0]["id"]
        except Exception:
            pass
    if org_id:
        try:
            org = get_org(org_id)
            if org and org["name"]:
                return org["name"]
        except Exception:
            pass
    return "наша клиника"


# ---------- меню ----------

def main_menu_buttons(uid=None, platform=None):
    """Единая сборка главного меню для всех каналов.

    Платформа определяется по uid (vk:... → VK, иначе MAX) — это источник
    истины для любого пути вызова (/start, «Назад», фоллбэк ввода).
    """
    if uid is not None:
        platform = "vk" if str(uid).startswith("vk:") else "max"
    platform = platform or "max"

    bot_username = config.MINI_APP_BOT_USERNAME
    booking_btn = (
        {"type": "open_app", "text": "📅 Записаться", "web_app": bot_username}
        if (bot_username and platform == "max")
        else {"type": "callback", "text": "📅 Записаться", "payload": "start_booking_fallback"}
    )

    buttons = []
    if uid is not None:
        from storage.db import get_admin_role_by_platform
        role, _org_id, _org_name = get_admin_role_by_platform(platform, uid)
        if role in ("superadmin", "admin"):
            buttons.append([{"type": "callback", "text": "⚙️ Админ", "payload": "open_admin_panel"}])

    buttons.append([booking_btn])
    buttons.append([{"type": "callback", "text": "💼 Наши услуги", "payload": "show_services"}])
    buttons.append([{"type": "callback", "text": "📞 Заказать звонок", "payload": "call_admin"}])
    buttons.append([{"type": "callback", "text": "📋 Мои записи", "payload": "history"}])
    if platform == "max":
        if bot_username:
            buttons.append([{
                "type": "link",
                "text": "🔔 Лист ожидания",
                "url": f"https://max.ru/{bot_username}?startapp=waitlist",
            }])
    else:
        buttons.append([{
            "type": "callback",
            "text": "🔔 Лист ожидания",
            "payload": "waitlist_stub",
        }])
    return buttons

def back_to_menu_buttons(uid=None):
    return [[{"type": "callback", "text": "← Назад", "payload": "back:start"}]]


# ---------- валидация ----------

def normalize_phone(text: str):
    digits = re.sub(r"\D", "", text)
    if len(digits) == 10:
        return "+7" + digits
    if len(digits) == 11 and digits[0] in ("7", "8"):
        return "+7" + digits[1:]
    return None


# ---------- повторная запись ----------

def history_repeat_buttons(rows, max_buttons=3):
    bot_username = config.MINI_APP_BOT_USERNAME
    if not bot_username or not rows:
        return []

    seen_service_ids = set()
    buttons = []
    for r in rows:
        sid = _row_get(r, "service_id")
        if not sid or sid in seen_service_ids:
            continue
        seen_service_ids.add(sid)
        rid = _row_get(r, "id")
        sname = (_row_get(r, "service_name") or "")[:24]
        if not rid:
            continue
        buttons.append([{
            "type": "link",
            "text": f"↩ Повторить: {sname}",
            "url": f"https://max.ru/{bot_username}?startapp=repeat_{rid}",
        }])
        if len(buttons) >= max_buttons:
            break
    return buttons


# ---------- форматирование истории ----------

def format_history(rows, show_all=False):
    if not rows:
        if show_all:
            return "У вас пока нет записей.", None
        return "У вас нет предстоящих записей.", None

    header = "**📋 Все ваши записи**" if show_all else "**📋 Ваши ближайшие записи**"
    lines = [header, ""]

    for i, r in enumerate(rows):
        hid = _row_get(r, "id")
        sname = _row_get(r, "service_name")
        sched = _row_get(r, "scheduled_at")
        status = _row_get(r, "status")
        addr = _row_get(r, "address")
        doc = _row_get(r, "doctor")

        emoji = STATUS_EMOJI.get(status, "•")
        label = STATUS_LABELS.get(status, status)
        lines.append(f"{emoji} **Заявка #{hid}** — {label}")
        lines.append("")
        lines.append(f"**{sname}**")
        lines.append(f"📅 {sched}")
        if doc:
            lines.append(f"👨‍⚕️ {doc}")
        if addr:
            lines.append(f"📍 {addr}")
        if i < len(rows) - 1:
            lines.append("")
            lines.append("━━━━━━━━━━━━━━━━")
            lines.append("")

    return "\n".join(lines), "markdown"


# ---------- вход ----------

async def welcome(uid, org_id=None, message_id=None, platform="max"):
    try:
        existing = get_client(uid)
        if not existing:
            upsert_client(uid, org_id=org_id)
        elif existing["org_id"] is None and org_id:
            upsert_client(uid, org_id=org_id)
        elif existing["org_id"] and not org_id:
            org_id = existing["org_id"]
    except Exception:
        pass

    clear_state(uid)
    set_state(uid, "START", {"org_id": org_id})

    org_name = _resolve_org_name(uid=uid, org_id=org_id)
    text = (
        f"Здравствуйте! Это {org_name}.\n\n"
        "Через этого бота вы можете записаться на приём, "
        "посмотреть наши услуги и свои записи."
    )
    buttons = main_menu_buttons(uid, platform=platform)
    if message_id:
        await edit_message_for_client(uid, message_id, text, buttons=buttons)
    else:
        await send_to_client_raw(uid, text, buttons)


# ---------- callback ----------

async def handle_callback(uid, payload, message_id=None):
    state, ctx = get_state(uid)

    if payload in ("back:start", "cancel"):
        await welcome(uid, ctx.get("org_id"), message_id)
        return

    if payload == "open_admin_panel":
        role, org_id, org_name = get_admin_role(uid)
        bot_username = config.MINI_APP_BOT_USERNAME
        if not bot_username:
            await _edit_or_send(uid, message_id, "Mini App не настроен.", back_to_menu_buttons(uid))
            return

        if role == "superadmin":
            orgs = list_orgs()
            if not orgs:
                await _edit_or_send(uid, message_id, "Организаций пока нет. Создайте через /sadmin.",
                                    back_to_menu_buttons(uid))
                return
            buttons = [
                [{
                    "type": "link",
                    "text": f"🏢 {o['name']}",
                    "url": f"https://max.ru/{bot_username}?startapp=admin_{o['id']}",
                }]
                for o in orgs
            ]
            buttons.append([{"type": "callback", "text": "← Назад", "payload": "back:start"}])
            await _edit_or_send(uid, message_id, "Выберите организацию для открытия админки:", buttons)
            return

        if role == "admin":
            admin_url = f"https://max.ru/{bot_username}?startapp=admin_{org_id}"
            await _edit_or_send(
                uid, message_id,
                f"Админка «{org_name}». Нажмите кнопку ниже:",
                [
                    [{"type": "link", "text": "⚙️ Открыть админку", "url": admin_url}],
                    [{"type": "callback", "text": "← Назад", "payload": "back:start"}],
                ],
            )
            return

        await welcome(uid, ctx.get("org_id"), message_id)
        return

    if payload == "start_booking_fallback":
        await _edit_or_send(
            uid, message_id,
            "Запись онлайн здесь пока не открыта. Напишите нам сообщение — "
            "администратор оформит запись.",
            back_to_menu_buttons(uid),
        )
        return

    if payload == "waitlist_stub":
        await _edit_or_send(
            uid, message_id,
            "🔔 Лист ожидания пока доступен только в MAX (мини-приложение).\n"
            "В ВК эта функция скоро появится. Если нужно — напишите нам, "
            "администратор добавит вас в лист вручную.",
            back_to_menu_buttons(uid),
        )
        return

    if payload == "show_services":
        services = get_services(ctx.get("org_id"))
        if not services:
            await _edit_or_send(uid, message_id, "Услуги пока не настроены.", back_to_menu_buttons(uid))
            return

        has_categories = any(s["category_id"] for s in services)
        lines = ["**💼 Наши услуги**\n"]

        if has_categories:
            groups = {}
            for s in services:
                key = s["category_id"] if s["category_id"] else "__none__"
                if key not in groups:
                    groups[key] = {
                        "name": s["category_name"] or "Прочие услуги",
                        "sort_order": s["category_sort_order"] if s["category_sort_order"] is not None else 999999,
                        "items": [],
                    }
                groups[key]["items"].append(s)

            ordered = sorted(groups.values(), key=lambda g: (g["sort_order"], g["name"]))
            for g in ordered:
                lines.append(f"**📂 {g['name']}**")
                lines.append("")
                for s in g["items"]:
                    lines.append(f"• {s['name']} — {s['price']} ₽")
                    if s["prep"]:
                        lines.append(f"  _{s['prep']}_")
                lines.append("")
        else:
            for s in services:
                lines.append(f"**{s['name']}** — {s['price']} ₽")
                if s["prep"]:
                    lines.append(f"_{s['prep']}_")
                lines.append("")

        text = "\n".join(lines).strip()
        await _edit_or_send(uid, message_id, text, back_to_menu_buttons(uid), fmt="markdown")
        return

    if payload == "call_admin":
        set_state(uid, "CALL_ADMIN", ctx)
        text = (
            "📞 **Заказ звонка администратора**\n\n"
            "Напишите, пожалуйста, ваш вопрос и номер телефона для связи."
        )
        await _edit_or_send(uid, message_id, text, back_to_menu_buttons(uid), fmt="markdown")
        return

    if payload == "history":
        rows = get_history_upcoming(uid)
        text, fmt = format_history(rows, show_all=False)

        buttons = []
        buttons.extend(history_repeat_buttons(rows))
        if rows:
            buttons.append([{"type": "callback", "text": "📜 Показать все записи", "payload": "history_all"}])
        buttons.extend(back_to_menu_buttons(uid))

        set_state(uid, "HISTORY", ctx)
        await _edit_or_send(uid, message_id, text, buttons, fmt=fmt)
        return

    if payload == "history_all":
        rows = get_history_all(uid)
        text, fmt = format_history(rows, show_all=True)

        repeatable = [r for r in rows if _row_get(r, "status") in ("done", "confirmed", "pending")]
        buttons = []
        buttons.extend(history_repeat_buttons(repeatable))
        if rows:
            buttons.append([{"type": "callback", "text": "📋 Только предстоящие", "payload": "history"}])
        buttons.extend(back_to_menu_buttons(uid))

        set_state(uid, "HISTORY_ALL", ctx)
        await _edit_or_send(uid, message_id, text, buttons, fmt=fmt)
        return


# ---------- текстовые сообщения ----------

async def handle_input(uid, text):
    state, ctx = get_state(uid)

    if state == "CALL_ADMIN":
        rid = add_history(ctx.get("org_id"), uid, "Звонок администратора", "—", "—")
        set_state(uid, "DONE", {"rid": rid, "org_id": ctx.get("org_id")})
        await send_to_client_raw(
            uid,
            "✅ Запрос на звонок принят. Администратор свяжется с вами.",
            back_to_menu_buttons(uid),
        )
        await notify_admins(
            f"📞 Запрос звонка #{rid}\nСообщение: {text}",
            org_id=ctx.get("org_id"),
        )
        return

    await send_to_client_raw(
        uid,
        "Выберите нужный пункт в меню ниже.\n"
        "Если хотите, чтобы мы перезвонили — нажмите «📞 Заказать звонок».",
        main_menu_buttons(uid),
    )


# ---------- helpers ----------

async def _edit_or_send(uid, message_id, text, buttons=None, fmt=None):
    if message_id:
        await edit_message_for_client(uid, message_id, text, buttons=buttons, fmt=fmt)
    else:
        await send_to_client_raw(uid, text, buttons, fmt=fmt)