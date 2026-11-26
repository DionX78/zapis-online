"""Лист ожидания + backfill (горящие окна).

Логика:
- Слот освободился → триггер БД ставит slots.released_at.
- Воркер раз в минуту сканирует освободившиеся слоты:
  * сначала уведомляет подходящих из листа ожидания;
  * если лист пуст (или никто не откликнулся за slot_backfill_delay_minutes) —
    запускает backfill (предлагает перенос клиентам с более поздней записью
    на ту же услугу).
- Уведомления уходят с кнопками. Клиент отвечает через callback (wl:*).
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

import config
from core.channels.base import UserBlocked
from core.messaging import send_to_client_raw, edit_message_for_client
from core.booking import BookingContext, create_booking_unified
from core.geo import route_lines
from core.notify import notify_admins
from core.notify_ics import send_confirmation_with_ics
from storage.db import (
    db, db_ctx,
    find_waitlist_matches_for_slot, mark_waitlist_notified,
    find_backfill_candidates, create_slot_offer,
    list_slot_offers_for_slot, update_slot_offer_status,
    mark_other_offers_taken, count_user_offers_since, get_slot_offer,
    get_org_settings,
    get_request, has_active_request_at_time,
    get_branch, get_doctor,
    get_service,
    slots_needed_for_service, find_consecutive_slots,
    doctor_makes_service,
    move_booking, finalize_move_booking,
    create_booking,
    get_client, is_user_blocked,
    count_active_bookings_on_date, count_active_future_requests,
    get_client_no_show_count,
    get_waitlist_entry,
    cancel_waitlist_entry,
)

log = logging.getLogger(__name__)

CHECK_INTERVAL = 60


def _fmt_slot(slot_date, slot_time):
    """'2026-11-08', '15:30' -> '08 ноя, 15:30'."""
    try:
        dt = datetime.strptime(f"{slot_date} {slot_time}", "%Y-%m-%d %H:%M")
    except Exception:
        return f"{slot_date} {slot_time}"
    months = ["янв", "фев", "мар", "апр", "мая", "июн",
              "июл", "авг", "сен", "окт", "ноя", "дек"]
    return f"{dt.day:02d} {months[dt.month - 1]}, {slot_time}"


def _get_slot(slot_id):
    conn = db()
    row = conn.execute(
        "SELECT s.id, s.org_id, s.date, s.time, s.doctor_id, "
        "       s.branch_id, s.service_id, s.request_id, "
        "       d.name AS doctor_name, "
        "       b.name AS branch_name, "
        "       sv.name AS service_name, sv.duration_min "
        "FROM slots s "
        "LEFT JOIN doctors d ON d.id = s.doctor_id "
        "LEFT JOIN branches b ON b.id = s.branch_id "
        "LEFT JOIN services sv ON sv.id = s.service_id "
        "WHERE s.id=?",
        (slot_id,),
    ).fetchone()
    conn.close()
    return row


def _bot_username():
    try:
        return config.MINI_APP_BOT_USERNAME or ""
    except Exception:
        return ""


def _clear_released_at(slot_id):
    """Сбрасывает released_at, чтобы воркер больше не сканировал слот."""
    with db_ctx() as conn:
        conn.execute("UPDATE slots SET released_at = NULL WHERE id = ?", (slot_id,))
        conn.commit()


# ==================== Уведомление листа ====================

async def notify_waitlist_for_slot(slot_id):
    """Создаёт pending-офферы для подходящих заявок листа.

    Реальная отправка — в _flush_pending_offers() в конце итерации воркера:
    это позволяет собрать все освободившиеся слоты в одно сообщение на
    каждую пару (user_id, waitlist_id).

    Rate-limit реализован через find_waitlist_matches_for_slot: заявки с
    «живым» оффером (pending или свежий sent) не получают новые pending,
    пока не ответят или не истечёт TTL.

    Возвращает число созданных pending-офферов.
    """
    slot = _get_slot(slot_id)
    if not slot or slot["request_id"] is not None:
        return 0

    org_id = slot["org_id"]
    matches = find_waitlist_matches_for_slot(org_id, slot_id)
    created = 0

    for wl in matches:
        uid = wl["user_id"]

        # Защита от дублей: если по (slot_id, waitlist_id) уже есть
        # pending или sent — не создаём новый.
        with db_ctx() as conn:
            exists = conn.execute(
                "SELECT 1 FROM slot_offers "
                "WHERE slot_id=? AND waitlist_id=? "
                "  AND status IN ('pending','sent') LIMIT 1",
                (slot_id, wl["id"]),
            ).fetchone()
        if exists:
            continue

        offer_id = create_slot_offer(
            org_id, slot_id, uid, kind="waitlist",
            original_request_id=None, waitlist_id=wl["id"],
            status="pending",
        )

        if str(uid).startswith("phone:"):
            update_slot_offer_status(offer_id, "expired", error="phone_only")
            continue

        created += 1

    return created


# ==================== Backfill ====================

async def run_backfill_for_slot(slot_id):
    """Возвращает число отправленных предложений переноса."""
    slot = _get_slot(slot_id)
    if not slot or slot["request_id"] is not None:
        return 0
    if not slot["service_id"]:
        return 0

    org_id = slot["org_id"]
    settings = get_org_settings(org_id) or {}

    if not settings.get("slot_backfill_enabled", True):
        return 0

    # Не предлагаем слот в прошлом — клиент всё равно получит отказ.
    from storage.db import now_for_org
    try:
        slot_dt = datetime.strptime(
            f"{slot['date']} {slot['time']}", "%Y-%m-%d %H:%M"
        )
    except ValueError:
        slot_dt = None
    if slot_dt is not None and slot_dt < now_for_org(org_id):
        log.info("backfill: slot %s is in the past, skip", slot_id)
        return 0

    step_min = int(settings.get("slot_step_min", 30) or 30)
    min_gap = int(settings.get("slot_backfill_min_gap_hours", 24) or 24)
    max_candidates = int(settings.get("slot_backfill_max_candidates", 5) or 5)
    cooldown_hours = int(settings.get("slot_backfill_cooldown_hours", 24) or 24)

    candidates = find_backfill_candidates(org_id, slot_id, min_gap, max_candidates)
    sent = 0
    cooldown_since = (datetime.now() - timedelta(hours=cooldown_hours)).isoformat()

    for cand in candidates:
        uid = cand["user_id"]
        if not uid or str(uid).startswith("phone:"):
            continue
        if count_user_offers_since(uid, "backfill", cooldown_since) > 0:
            continue

        # Проверка: под длительность записи клиента должно хватать подряд.
        cand_slots_count = int(cand["slots_count"] or 1)
        if not find_consecutive_slots(slot_id, cand_slots_count, step_min):
            log.info(
                "backfill: slot %s has no %d consecutive slots for #%s (uid=%s), skip",
                slot_id, cand_slots_count, cand["history_id"], uid,
            )
            continue

        offer_id = create_slot_offer(
            org_id, slot_id, uid, kind="backfill",
            original_request_id=cand["history_id"],
        )

        date_human = _fmt_slot(slot["date"], slot["time"])
        old_dt = cand["scheduled_at"] or ""
        try:
            old_human = _fmt_slot(old_dt[:10], old_dt[11:16])
        except Exception:
            old_human = old_dt

        text = (
            f"🔥 **Освободилось более раннее время**\n\n"
            f"**{slot['service_name'] or 'Услуга'}**\n"
            f"📅 {date_human}\n"
        )
        if slot["doctor_name"]:
            text += f"👤 {slot['doctor_name']}\n"
        text += (
            f"\nВаша текущая запись — {old_human}.\n"
            f"Перенести на более раннее время?"
        )

        buttons = [[
            {"type": "callback", "text": "✅ Перенести", "payload": f"wl:move:{offer_id}"},
            {"type": "callback", "text": "❌ Оставить как есть", "payload": f"wl:keep:{offer_id}"},
        ]]

        try:
            await send_to_client_raw(uid, text, buttons, fmt="markdown")
            sent += 1
        except UserBlocked:
            update_slot_offer_status(offer_id, "taken", error="blocked")
        except Exception as e:
            log.warning("backfill notify failed for %s: %s", uid, e)
            update_slot_offer_status(offer_id, "expired", error=str(e)[:200])

    return sent

# ==================== Запись из листа «в один клик» ====================

MAX_ACTIVE_BOOKINGS = 10


async def _book_slot_for_waitlist_client(user_id, slot, service_id_override=None):
    """Обёртка над create_booking_unified для листа ожидания.

    Вся бизнес-логика (проверки, уведомления, no_service-сценарий,
    slots_count_override) — в core/booking.py. Здесь только:
    1. Собираем BookingContext.
    2. Зовём create_booking_unified.
    3. Мапим error_code → строковый статус для handle_callback.

    Возвращает:
      "booked" | "no_consent" | "blocked" | "slot_taken"
      | "no_slots_for_duration" | "already_at_time" | "limit_exceeded"
      | "too_many_active" | "doctor_skill" | "error"
    """
    org_id = slot["org_id"]
    effective_service_id = service_id_override or slot["service_id"]

    ctx = BookingContext(
        org_id=org_id,
        user_id=str(user_id),
        slot_id=slot["id"],
        service_id=effective_service_id,
        via="waitlist",
    )
    result = await create_booking_unified(ctx)

    if result.ok:
        _fulfill_waitlists_for_booking(
            user_id, org_id, effective_service_id, slot["date"], result.request_id,
        )
        log.info(
            "waitlist booking ok: uid=%s slot=%s rid=%s status=%s",
            user_id, slot["id"], result.request_id, result.status,
        )
        return "booked"

    code = result.error_code or "error"
    mapping = {
        "blocked": "blocked",
        "slot_taken": "slot_taken",
        "slot_not_found": "slot_taken",
        "slot_org_mismatch": "slot_taken",
        "no_consent": "no_consent",
        "no_slots_for_duration": "no_slots_for_duration",
        "already_at_time": "already_at_time",
        "daily_limit_exceeded": "limit_exceeded",
        "too_many_active": "too_many_active",
        "doctor_skill": "doctor_skill",
    }
    mapped = mapping.get(code, "error")
    log.info(
        "waitlist booking fail: uid=%s slot=%s code=%s mapped=%s msg=%s",
        user_id, slot["id"], code, mapped, (result.error_msg or "")[:120],
    )
    return mapped


def _fulfill_waitlists_for_booking(user_id, org_id, service_id, slot_date, request_id):
    """Помечает fulfilled все активные заявки листа, подходящие под созданную запись.

    Заявка без услуги (service_id IS NULL) тоже считается выполненной — клиент
    записался, искать ему больше нечего.

    Заодно отзывает все sent/pending офферы этих заявок — чтобы клиент
    не тапал на устаревшие кнопки из старых сообщений.
    """
    with db_ctx() as conn:
        rows = conn.execute(
            "SELECT id FROM waitlist "
            "WHERE org_id=? AND user_id=? AND status='active' "
            "  AND (service_id IS NULL OR service_id=?) "
            "  AND date_from <= ? AND date_to >= ?",
            (org_id, str(user_id), service_id, slot_date, slot_date),
        ).fetchall()
        wl_ids = [r["id"] for r in rows]
        if wl_ids:
            placeholders = ",".join("?" * len(wl_ids))
            conn.execute(
                f"UPDATE waitlist SET status='fulfilled', fulfilled_request_id=?, fulfilled_at=? "
                f"WHERE id IN ({placeholders})",
                [request_id, datetime.now().isoformat()] + wl_ids,
            )
            conn.execute(
                f"UPDATE slot_offers SET status='expired', responded_at=?, error='waitlist_fulfilled' "
                f"WHERE waitlist_id IN ({placeholders}) AND status IN ('sent','pending')",
                [datetime.now().isoformat()] + wl_ids,
            )
        conn.commit()

# ==================== Подбор свободных слотов для новой заявки ====================

async def _notify_waitlist_entry_for_free_slots(waitlist_id):
    """При создании заявки: ищем уже свободные слоты, подходящие под неё,
    и создаём для них pending-офферы. Дальше обычный flush отправит их пачкой.

    Полезно, когда слот был свободен ещё до появления заявки — воркер
    его уже не обрабатывает (released_at сброшен или не проставлен).
    """
    entry = get_waitlist_entry(waitlist_id)
    if not entry or entry["status"] != "active":
        return 0

    if str(entry["user_id"]).startswith("phone:"):
        return 0

    org_id = entry["org_id"]

    conds = [
        "s.org_id = ?",
        "s.request_id IS NULL",
        "s.date >= ?",
        "s.date <= ?",
    ]
    params = [org_id, entry["date_from"], entry["date_to"]]
    if entry["service_id"]:
        conds.append("(s.service_id IS NULL OR s.service_id = ?)")
        params.append(entry["service_id"])
    if entry["doctor_id"]:
        conds.append("s.doctor_id = ?")
        params.append(entry["doctor_id"])
    if entry["branch_id"]:
        conds.append("s.branch_id = ?")
        params.append(entry["branch_id"])

    with db_ctx() as conn:
        slots = conn.execute(
            "SELECT s.id FROM slots s WHERE " + " AND ".join(conds) +
            " ORDER BY s.date, s.time LIMIT 10",
            params,
        ).fetchall()

    if not slots:
        return 0

    created = 0
    for s in slots:
        # Дубль-защита
        with db_ctx() as conn:
            exists = conn.execute(
                "SELECT 1 FROM slot_offers "
                "WHERE slot_id=? AND waitlist_id=? "
                "  AND status IN ('pending','sent') LIMIT 1",
                (s["id"], waitlist_id),
            ).fetchone()
        if exists:
            continue
        create_slot_offer(
            org_id, s["id"], entry["user_id"], kind="waitlist",
            original_request_id=None, waitlist_id=waitlist_id,
            status="pending",
        )
        created += 1

    if created:
        log.info(
            "Waitlist entry %s matched %d free slots, pending offers created",
            waitlist_id, created,
        )
    return created


# ==================== Отправка офферов (группировка) ====================

async def _send_single_offer(user_id, waitlist_id, offer):
    """Отправляет уведомление по одному офферу. Старый формат (1 кнопка ✅ + ❌)."""
    slot = _get_slot(offer["slot_id"])
    if not slot or slot["request_id"] is not None:
        update_slot_offer_status(offer["id"], "taken")
        return

    date_human = _fmt_slot(slot["date"], slot["time"])
    text = (
        f"🔔 **Освободилось время**\n\n"
        f"**{slot['service_name'] or 'Услуга'}**\n"
        f"📅 {date_human}\n"
    )
    if slot["doctor_name"]:
        text += f"👤 {slot['doctor_name']}\n"
    if slot["branch_name"]:
        text += f"🏢 {slot['branch_name']}\n"

    buttons = [
        [
            {"type": "callback", "text": "✅ Записаться", "payload": f"wl:accept:{offer['id']}"},
            {"type": "callback", "text": "❌ Не нужно", "payload": f"wl:decline:{offer['id']}"},
        ],
        [
            {"type": "callback", "text": "🚫 Больше не присылать", "payload": f"wl:removeask:{offer['id']}"},
        ],
    ]

    try:
        await send_to_client_raw(user_id, text, buttons, fmt="markdown")
        update_slot_offer_status(offer["id"], "sent")
        if waitlist_id:
            mark_waitlist_notified(waitlist_id, offer["slot_id"])
    except UserBlocked:
        update_slot_offer_status(offer["id"], "taken", error="blocked")
    except Exception as e:
        log.warning("send_single_offer failed for %s: %s", user_id, e)
        update_slot_offer_status(offer["id"], "expired", error=str(e)[:200])


async def _send_grouped_offers(user_id, waitlist_id, offers):
    """Отправляет одно сообщение с несколькими слотами и выбором (кнопки по слотам)."""
    # Слоты, которые уже заняли — сразу помечаем taken, в сообщение не включаем
    live = []
    for o in offers:
        slot = _get_slot(o["slot_id"])
        if not slot or slot["request_id"] is not None:
            update_slot_offer_status(o["id"], "taken")
            continue
        live.append((o, slot))

    if not live:
        return
    if len(live) == 1:
        await _send_single_offer(user_id, waitlist_id, live[0][0])
        return

    first_slot = live[0][1]
    service_name = first_slot["service_name"] or "Услуга"
    doctor_name = first_slot["doctor_name"]
    branch_name = first_slot["branch_name"]

    lines = [f"🔔 **Освободилось {len(live)} слота**\n", f"**{service_name}**"]
    if doctor_name:
        lines.append(f"👤 {doctor_name}")
    if branch_name:
        lines.append(f"🏢 {branch_name}")
    lines.append("")
    lines.append("Выберите удобное время:")

    buttons = []
    for o, slot in live:
        date_human = _fmt_slot(slot["date"], slot["time"])
        buttons.append([{
            "type": "callback",
            "text": f"📅 {date_human}",
            "payload": f"wl:accept:{o['id']}",
        }])
    buttons.append([{
        "type": "callback",
        "text": "❌ Не нужно",
        "payload": f"wl:declineb:{live[0][0]['id']}",
    }])
    buttons.append([{
        "type": "callback",
        "text": "🚫 Больше не присылать",
        "payload": f"wl:removeask:{live[0][0]['id']}",
    }])

    text = "\n".join(lines)

    try:
        await send_to_client_raw(user_id, text, buttons, fmt="markdown")
        for o, _slot in live:
            update_slot_offer_status(o["id"], "sent")
        if waitlist_id:
            mark_waitlist_notified(waitlist_id, live[0][0]["slot_id"])
    except UserBlocked:
        for o, _slot in live:
            update_slot_offer_status(o["id"], "taken", error="blocked")
    except Exception as e:
        log.warning("send_grouped_offers failed for %s: %s", user_id, e)
        for o, _slot in live:
            update_slot_offer_status(o["id"], "expired", error=str(e)[:200])


async def _flush_pending_offers():
    """Отправляет pending-офферы группами, но только когда самая старая группа
    достигла возраста slot_backfill_batch_minutes. Так несколько освободившихся
    слотов за короткий промежуток попадают в одно сообщение.
    """
    settings_cache = {}

    def _batch_minutes(org_id):
        if org_id not in settings_cache:
            s = get_org_settings(org_id) or {}
            settings_cache[org_id] = int(s.get("slot_backfill_batch_minutes", 15) or 15)
        return settings_cache[org_id]

    with db_ctx() as conn:
        rows = conn.execute(
            "SELECT id, org_id, slot_id, user_id, waitlist_id, kind, status, sent_at "
            "FROM slot_offers "
            "WHERE status='pending' "
            "ORDER BY user_id, waitlist_id, id"
        ).fetchall()

    if not rows:
        return

    groups = {}
    for r in rows:
        key = (str(r["user_id"]), r["waitlist_id"])
        groups.setdefault(key, []).append(dict(r))

    now = datetime.now()
    for (user_id, waitlist_id), offers in groups.items():
        # Готовы к отправке, если самый старый оффер в группе достиг возраста batch_minutes
        oldest = min(o["sent_at"] for o in offers)
        try:
            oldest_dt = datetime.fromisoformat(oldest)
        except Exception:
            oldest_dt = now - timedelta(hours=1)
        org_id = offers[0]["org_id"]
        if (now - oldest_dt) < timedelta(minutes=_batch_minutes(org_id)):
            continue

        try:
            await _send_grouped_offers(user_id, waitlist_id, offers)
        except Exception as e:
            log.warning("flush group failed for %s/%s: %s", user_id, waitlist_id, e)


# ==================== Переотправка оставшихся слотов ====================

async def _resend_remaining_offers_for_group(user_id, waitlist_id, exclude_offer_ids=None):
    """После неудачной попытки (слот занят) или после отмены — переотправляет
    оставшиеся свободные слоты этой же заявки. Если все заняты — сообщает.

    Заявку НЕ отменяет — она остаётся active, sweep продолжит следить.
    """
    exclude_offer_ids = set(exclude_offer_ids or [])

    with db_ctx() as conn:
        rows = conn.execute(
            "SELECT id, slot_id FROM slot_offers "
            "WHERE waitlist_id=? AND status IN ('sent','pending') "
            "ORDER BY id",
            (waitlist_id,),
        ).fetchall()

    live = []
    for r in rows:
        if r["id"] in exclude_offer_ids:
            continue
        slot = _get_slot(r["slot_id"])
        if not slot or slot["request_id"] is not None:
            update_slot_offer_status(r["id"], "taken")
            continue
        live.append({"id": r["id"], "slot_id": r["slot_id"]})

    if not live:
        try:
            await send_to_client_raw(
                user_id,
                "⚠️ К сожалению, все предложенные слоты уже заняты.\n\n"
                "Мы сообщим, если появятся новые — заявка остаётся активной.",
                fmt="markdown",
            )
        except Exception as e:
            log.warning("resend remaining: send failed for %s: %s", user_id, e)
        return

    try:
        await _send_grouped_offers(user_id, waitlist_id, live)
    except Exception as e:
        log.warning("resend remaining: send group failed for %s: %s", user_id, e)


# ==================== Callback'и ====================

async def handle_callback(uid, payload, message_id=None):
    if not payload.startswith("wl:"):
        return False
    log.info("wl callback RAW: uid=%s payload=%r msg_id=%r",
             uid, payload, message_id)
    parts = payload.split(":")
    if len(parts) != 3:
        return True

    action = parts[1]
    try:
        offer_id = int(parts[2])
    except ValueError:
        return True

    offer = get_slot_offer(offer_id)
    if not offer:
        await _edit_or_send(uid, message_id, "Предложение больше неактивно.")
        return True
    if str(offer["user_id"]) != str(uid):
        await _edit_or_send(uid, message_id, "Нет доступа.")
        return True
    if offer["status"] != "sent":
        await _edit_or_send(uid, message_id, "Предложение уже обработано.")
        return True

    slot = _get_slot(offer["slot_id"])

    # --- принять из листа ожидания: бронируем сразу ---
    if action == "accept":
        if not slot or slot["request_id"] is not None:
            update_slot_offer_status(offer_id, "taken")
            wl_id = offer["waitlist_id"]
            await _edit_or_send(
                uid, message_id,
                "⚠️ Это время только что заняли.",
                buttons=[],
            )
            if wl_id:
                wl_entry = get_waitlist_entry(wl_id)
                if wl_entry and wl_entry["status"] == "active":
                    await _resend_remaining_offers_for_group(
                        uid, wl_id, exclude_offer_ids={offer_id},
                    )
                else:
                    try:
                        await send_to_client_raw(
                            int(uid),
                            "Ваша заявка в листе ожидания уже закрыта "
                            "(вы записаны или отменили её). "
                            "Записаться на другое время можно через Mini App.",
                        )
                    except Exception as e:
                        log.warning("early slot_taken notify failed: %s", e)
            return True

        # Если оффер пришёл из конкретной заявки — берём её услугу как override
        # (важно для универсальных слотов и для заявок «к специалисту без услуги»).
        service_id_override = None
        if offer["waitlist_id"]:
            wl_entry = get_waitlist_entry(offer["waitlist_id"])
            if wl_entry:
                service_id_override = wl_entry["service_id"]

        result = await _book_slot_for_waitlist_client(
            uid, slot, service_id_override=service_id_override,
        )

        if result == "booked":
            update_slot_offer_status(offer_id, "accepted")
            mark_other_offers_taken(slot["id"], offer_id)
            date_human = _fmt_slot(slot["date"], slot["time"])
            # Основное сообщение (подтверждение / .ics / «ожидает») уже отправлено
            # внутри _book_slot_for_waitlist_client. Здесь — короткое «готово».
            await _edit_or_send(
                uid, message_id,
                f"✅ Записали вас на **{date_human}**. "
                f"Подробности — в сообщении выше.",
            )
            return True

        if result == "no_consent":
            # Единственный fallback на Mini App — согласие 152-ФЗ
            bot = _bot_username()
            if bot and slot["service_id"]:
                url = f"https://max.ru/{bot}?startapp=slot_{slot['id']}"
                text = (
                    "✅ Освободилось время!\n\n"
                    "Чтобы записаться, нужно согласие на обработку персональных данных. "
                    "Нажмите кнопку ниже — откроется Mini App с уже выбранным слотом."
                )
                buttons = [[{"type": "link", "text": "📅 Открыть и записаться", "url": url}]]
                await _edit_or_send(uid, message_id, text, buttons)
            else:
                await _edit_or_send(
                    uid, message_id,
                    "Не удалось записать автоматически. Откройте Mini App в боте "
                    "и запишитесь на это время.",
                )
            return True

        if result == "no_service":
            update_slot_offer_status(offer_id, "expired", error="no_service")
            date_human = _fmt_slot(slot["date"], slot["time"])
            await _edit_or_send(
                uid, message_id,
                f"Освободилось время ({date_human}), но без конкретной услуги "
                f"записать автоматически нельзя. Администратор свяжется с вами, "
                f"чтобы оформить запись.",
            )
            try:
                fio = "—"
                cl = get_client(uid)
                if cl:
                    fio = " ".join(p for p in [
                        cl["last_name"], cl["first_name"], cl["middle_name"]
                    ] if p).strip() or cl["phone"] or "—"
                admin_text = (
                    f"🔔 **Клиент из листа ожидания хочет записаться**\n\n"
                    f"Время: {date_human}\n"
                )
                if slot["doctor_name"]:
                    admin_text += f"👤 {slot['doctor_name']}\n"
                if slot["branch_name"]:
                    admin_text += f"🏢 {slot['branch_name']}\n"
                admin_text += (
                    f"\nКлиент: {fio}\n"
                    f"Свяжитесь с ним — услуга не была указана в заявке."
                )
                await notify_admins(admin_text, org_id=slot["org_id"], buttons=None)
            except Exception as e:
                log.warning("no_service notify_admins failed: %s", e)
            return True

        if result == "blocked":
            update_slot_offer_status(offer_id, "taken", error="blocked")
            await _edit_or_send(
                uid, message_id,
                "Не удалось записаться. Свяжитесь с администратором.",
            )
            return True

        if result == "slot_taken":
            update_slot_offer_status(offer_id, "taken")
            wl_id = offer["waitlist_id"]
            await _edit_or_send(
                uid, message_id,
                "⚠️ Это время только что заняли. Смотрите новое предложение ниже.",
                buttons=[],
            )
            if wl_id:
                await _resend_remaining_offers_for_group(
                    uid, wl_id, exclude_offer_ids={offer_id},
                )
            return True

        if result == "no_slots_for_duration":
            update_slot_offer_status(offer_id, "expired", error="no_slots_for_duration")
            await _edit_or_send(
                uid, message_id,
                "Слот освободился, но для этой услуги нужно больше времени подряд. "
                "Свяжитесь с администратором — подберём вариант.",
            )
            return True

        if result == "already_at_time":
            update_slot_offer_status(offer_id, "expired", error="already_at_time")
            await _edit_or_send(
                uid, message_id,
                "У вас уже есть активная запись на это время. "
                "Отмените её, если хотите переписаться.",
            )
            return True

        if result in ("limit_exceeded", "too_many_active"):
            update_slot_offer_status(offer_id, "expired", error=result)
            await _edit_or_send(
                uid, message_id,
                "У вас уже слишком много активных записей. "
                "Отмените одну, чтобы записаться на новое время.",
            )
            return True

        if result == "doctor_skill":
            update_slot_offer_status(offer_id, "expired", error="doctor_skill")
            await _edit_or_send(
                uid, message_id,
                "Этот специалист не оказывает выбранную услугу. "
                "Свяжитесь с администратором.",
            )
            return True

        # прочие ошибки
        update_slot_offer_status(offer_id, "expired", error=result)
        await _edit_or_send(
            uid, message_id,
            "Не удалось записаться. Свяжитесь с администратором.",
        )
        return True

    # --- отклонить из листа ожидания (одиночный слот) ---
    if action == "decline":
        update_slot_offer_status(offer_id, "declined")
        await _edit_or_send(uid, message_id, "Ок, больше не будем предлагать это время.")
        return True

    # --- отклонить группу слотов (кнопка «Не нужно» в групповом сообщении) ---
    if action == "declineb":
        wl_id = offer["waitlist_id"]
        if wl_id:
            with db_ctx() as conn:
                conn.execute(
                    "UPDATE slot_offers SET status='declined', responded_at=? "
                    "WHERE user_id=? AND waitlist_id=? "
                    "  AND status IN ('sent', 'pending')",
                    (datetime.now().isoformat(), str(uid), wl_id),
                )
                conn.commit()
        else:
            update_slot_offer_status(offer_id, "declined")
        await _edit_or_send(uid, message_id, "Ок, больше не будем предлагать эти слоты.")
        return True

    # --- двухфазное удаление: первый тап — подтверждение ---
    if action == "removeask":
        await _edit_or_send(
            uid, message_id,
            "🚫 **Отменить заявку в листе ожидания?**\n\n"
            "Вы больше не получите предложений по этой услуге. "
            "Вернуться в лист можно через Mini App.\n\n"
            "Вы уверены?",
            [
                [{"type": "callback", "text": "🗑 Да, отменить заявку",
                  "payload": f"wl:remove:{offer_id}"}],
                [{"type": "callback", "text": "↩ Нет, оставить",
                  "payload": f"wl:keep_offer:{offer_id}"}],
            ],
        )
        return True

    # --- отмена двухфазного удаления ---
    if action == "keep_offer":
        await _edit_or_send(
            uid, message_id,
            "✅ Хорошо, заявка остаётся активной.",
            buttons=[],
        )
        wl_id = offer["waitlist_id"]
        if wl_id:
            await _resend_remaining_offers_for_group(
                uid, wl_id, exclude_offer_ids=set(),
            )
        return True

    # --- подтверждено: удаляем заявку ---
    if action == "remove":
        wl_id = offer["waitlist_id"]
        if wl_id:
            cancel_waitlist_entry(wl_id)
            with db_ctx() as conn:
                conn.execute(
                    "UPDATE slot_offers SET status='declined', responded_at=? "
                    "WHERE waitlist_id=? AND status IN ('sent', 'pending')",
                    (datetime.now().isoformat(), wl_id),
                )
                conn.commit()
        else:
            update_slot_offer_status(offer_id, "declined")
        await _edit_or_send(
            uid, message_id,
            "🚫 Заявка удалена из листа ожидания. Больше предложений по этой услуге не будет.\n\n"
            "Если захотите снова — встаньте в лист через Mini App.",
            buttons=[],
        )
        return True

    # --- перенос (backfill) ---
    if action == "move":
        if not slot or slot["request_id"] is not None:
            update_slot_offer_status(offer_id, "taken")
            await _edit_or_send(uid, message_id, "К сожалению, время уже занято.")
            return True

        req_id = offer["original_request_id"]
        if not req_id:
            update_slot_offer_status(offer_id, "expired", error="no_original_request")
            await _edit_or_send(uid, message_id, "Не удалось найти вашу запись.")
            return True

        from core.booking import move_booking_unified
        mv = await move_booking_unified(req_id, slot["id"], via="waitlist")

        if not mv.ok:
            update_slot_offer_status(offer_id, "expired", error=mv.error_code or "move_failed")
            user_messages = {
                "request_not_found": "Не удалось найти вашу запись.",
                "request_not_active": "Ваша запись уже неактивна.",
                "slot_taken": "Время только что заняли. Не удалось перенести.",
                "slot_in_past": "Время уже в прошлом.",
                "already_at_time": "У вас уже есть другая запись на это время.",
                "no_slots_for_duration": "Для переноса не хватает свободного времени подряд.",
                "doctor_skill": "Специалист не оказывает эту услугу.",
                "move_failed": "Не удалось перенести — попробуйте через администратора.",
            }
            await _edit_or_send(
                uid, message_id,
                user_messages.get(mv.error_code, "Не удалось перенести запись."),
            )
            return True

        update_slot_offer_status(offer_id, "accepted")
        mark_other_offers_taken(slot["id"], offer_id)

        date_human = _fmt_slot(slot["date"], slot["time"])
        await _edit_or_send(
            uid, message_id,
            f"✅ Готово, вы перенесены на **{date_human}**.\n\n"
            f"Детали — в сообщении «🔄 Запись перенесена».",
        )
        return True

    # --- оставить (backfill) ---
    if action == "keep":
        update_slot_offer_status(offer_id, "declined")
        await _edit_or_send(uid, message_id, "Хорошо, оставляем вашу запись как есть.")
        return True

    return True


async def _edit_or_send(uid, message_id, text, buttons=None):
    if message_id:
        await edit_message_for_client(uid, message_id, text, buttons=buttons, fmt="markdown")
    else:
        await send_to_client_raw(uid, text, buttons=buttons, fmt="markdown")


# ==================== Воркер ====================

async def _scan_released_slots():
    conn = db()
    rows = conn.execute(
        "SELECT s.id AS slot_id, s.org_id, s.released_at "
        "FROM slots s "
        "WHERE s.request_id IS NULL AND s.released_at IS NOT NULL "
        "ORDER BY s.released_at ASC LIMIT 50"
    ).fetchall()
    conn.close()
    return rows


async def _process_released_slot(slot_row):
    slot_id = slot_row["slot_id"]
    org_id = slot_row["org_id"]
    settings = get_org_settings(org_id) or {}

    delay_min = int(settings.get("slot_backfill_delay_minutes", 30) or 30)
    wait_min = int(settings.get("slot_backfill_waitlist_wait_minutes", 30) or 30)

    try:
        # released_at пишется триггером через datetime('now') — это UTC.
        # Помечаем naive-datetime как UTC и сравниваем с текущим UTC,
        # чтобы не получать смещение на TZ сервера.
        released_dt = datetime.fromisoformat(
            slot_row["released_at"].replace(" ", "T")
        ).replace(tzinfo=timezone.utc)
    except Exception:
        _clear_released_at(slot_id)
        return

    # 1. Первые delay_min — слот просто висит в обычном потоке
    if (datetime.now(timezone.utc) - released_dt) < timedelta(minutes=delay_min):
        return

    offers = list_slot_offers_for_slot(slot_id)

    # 2. Есть backfill-офферы в статусе sent — ждём ответа клиента, не трогаем.
    if any(o["kind"] == "backfill" and o["status"] == "sent" for o in offers):
        return

    # 3. Backfill уже был, все его офферы resolved — попытка полностью
    #    завершена, сбрасываем released_at, чтобы не сканировать слот вечно.
    backfill_offers = [o for o in offers if o["kind"] == "backfill"]
    if backfill_offers and all(
        o["status"] in ("declined", "expired", "taken", "accepted")
        for o in backfill_offers
    ):
        _clear_released_at(slot_id)
        return

    waitlist_offers = [o for o in offers if o["kind"] == "waitlist"]

    # 4. Pending — ждём flush
    if any(o["status"] == "pending" for o in waitlist_offers):
        return

    # 5. Кто-то из листа уже записался — слот занят триггером booked,
    #    released_at уже NULL, но на случай гонки — просто выходим.
    if any(o["status"] == "accepted" for o in waitlist_offers):
        return

    # 6. Есть sent-офферы листа — проверяем таймаут ответа
    sent_offers = [o for o in waitlist_offers if o["status"] == "sent"]
    if sent_offers:
        try:
            oldest_sent = min(
                datetime.fromisoformat(o["sent_at"]) for o in sent_offers
            )
        except Exception:
            _clear_released_at(slot_id)
            return
        if (datetime.now() - oldest_sent) < timedelta(minutes=wait_min):
            return  # ещё ждём реакции
        log.info(
            "Waitlist did not respond for slot %s within %d min, running backfill",
            slot_id, wait_min,
        )
    elif waitlist_offers:
        # Все waitlist-офферы resolved (declined/expired) — сразу backfill
        log.info("All waitlist offers resolved for slot %s, running backfill", slot_id)
    else:
        # Офферов листа не было — пробуем уведомить сейчас
        sent = await notify_waitlist_for_slot(slot_id)
        if sent > 0:
            log.info("Waitlist notified for slot %s: %d", slot_id, sent)
            return
        log.info("No waitlist matches for slot %s, running backfill", slot_id)

    # 7. Запускаем backfill. Если 0 офферов создано — попытка завершена,
    #    сбрасываем released_at, чтобы не спамить в лог каждую минуту.
    created = await run_backfill_for_slot(slot_id)
    if created == 0:
        _clear_released_at(slot_id)


def _fulfill_waitlist_on_bookings_sync():
    """Sync-версия: выполняется в отдельном потоке (asyncio.to_thread).

    Возвращает число заявок, помеченных fulfilled.
    После fulfilled отзывает все sent/pending офферы этих заявок,
    чтобы клиент не тапал на устаревшие кнопки.

    ВАЖНО: закрываем заявку только если у клиента появилась активная
    запись, созданная ПОСЛЕ создания заявки. Иначе старая бронь в том же
    периоде закрывала бы каждую новую заявку клиента (баг 2026-11-10).
    """
    with db_ctx() as conn:
        active = conn.execute(
            "SELECT * FROM waitlist WHERE status='active'"
        ).fetchall()

    if not active:
        return 0

    fulfilled = 0
    for wl in active:
        wl_created = wl["created_at"]

        if wl["service_id"] is None:
            conds = ["h.org_id=?", "h.user_id=?",
                     "h.status IN ('pending','confirmed')",
                     "date(h.scheduled_at) >= ?", "date(h.scheduled_at) <= ?",
                     "h.created_at > ?"]
            params = [wl["org_id"], wl["user_id"],
                      wl["date_from"], wl["date_to"], wl_created]
        else:
            conds = ["h.org_id=?", "h.user_id=?", "h.service_id=?",
                     "h.status IN ('pending','confirmed')",
                     "date(h.scheduled_at) >= ?", "date(h.scheduled_at) <= ?",
                     "h.created_at > ?"]
            params = [wl["org_id"], wl["user_id"], wl["service_id"],
                      wl["date_from"], wl["date_to"], wl_created]
        if wl["doctor_id"]:
            conds.append("h.doctor_id=?")
            params.append(wl["doctor_id"])

        with db_ctx() as conn:
            row = conn.execute(
                "SELECT h.id FROM history h WHERE " + " AND ".join(conds) + " LIMIT 1",
                params,
            ).fetchone()
        if row:
            now_iso = datetime.now().isoformat()
            with db_ctx() as conn:
                conn.execute(
                    "UPDATE waitlist SET status='fulfilled', fulfilled_request_id=?, fulfilled_at=? "
                    "WHERE id=? AND status='active'",
                    (row["id"], now_iso, wl["id"]),
                )
                conn.execute(
                    "UPDATE slot_offers SET status='expired', responded_at=?, error='waitlist_fulfilled' "
                    "WHERE waitlist_id=? AND status IN ('sent','pending')",
                    (now_iso, wl["id"]),
                )
                conn.commit()
            fulfilled += 1
    return fulfilled


async def _sweep_stale_waitlists():
    """Проходит по активным заявкам, у которых нет pending/sent офферов,
    и пробует подобрать свободные слоты. Нужно, чтобы заявки, созданные
    до появления свободных слотов, тоже получали предложения.
    """
    with db_ctx() as conn:
        rows = conn.execute(
            "SELECT w.id AS waitlist_id "
            "FROM waitlist w "
            "WHERE w.status='active' "
            "  AND w.user_id NOT LIKE 'phone:%' "
            "  AND NOT EXISTS ("
            "    SELECT 1 FROM slot_offers o "
            "    WHERE o.waitlist_id = w.id "
            "      AND o.status IN ('pending','sent') "
            "  ) "
            "ORDER BY w.created_at ASC LIMIT 50"
        ).fetchall()

    if not rows:
        return

    total_matched = 0
    for r in rows:
        try:
            n = await _notify_waitlist_entry_for_free_slots(r["waitlist_id"])
            total_matched += n
        except Exception as e:
            log.warning(
                "sweep_stale_waitlists: entry %s failed: %s",
                r["waitlist_id"], e,
            )

    if total_matched:
        log.info(
            "sweep_stale_waitlists: matched %d free slots across %d entries",
            total_matched, len(rows),
        )


async def _fulfill_waitlist_on_bookings():
    """Помечает waitlist-заявки fulfilled, если у клиента появилась подходящая запись.

    Выполняется в отдельном потоке, чтобы не блокировать event loop
    при большом количестве активных заявок.
    """
    try:
        n = await asyncio.to_thread(_fulfill_waitlist_on_bookings_sync)
        if n:
            log.info("Auto-fulfilled %d waitlist entries", n)
    except Exception as e:
        log.error("Fulfill waitlist failed: %s", e)


_last_expire_date = None
_last_sweep_ts = None  # None = «ещё не запускали» → sweep сработает в первой итерации
SWEEP_INTERVAL_SEC = 600  # 10 минут между пересмотрами


async def _expire_daily():
    global _last_expire_date
    from storage.db import list_orgs, today_for_org

    for org in list_orgs():
        oid = org["id"]
        try:
            today = today_for_org(oid)
        except Exception as e:
            log.warning("expire: today_for_org failed for org %s: %s", oid, e)
            continue
        with db_ctx() as conn:
            cur = conn.execute(
                "UPDATE waitlist SET status='expired' "
                "WHERE status='active' AND date_to < ? AND org_id = ?",
                (today, oid),
            )
            n = cur.rowcount
            conn.commit()
        if n:
            log.info("Waitlist: expired %d entries for org %s", n, oid)
    _last_expire_date = datetime.now().strftime("%Y-%m-%d")


async def run_waitlist_worker():
    global _last_sweep_ts
    log.info("Waitlist worker started")
    await asyncio.sleep(45)

    while True:
        try:
            rows = await _scan_released_slots()
            for row in rows:
                try:
                    await _process_released_slot(row)
                except Exception as e:
                    log.error("process_released_slot %s failed: %s", row["slot_id"], e)
        except Exception as e:
            log.error("Waitlist scan failed: %s", e)

        try:
            await _flush_pending_offers()
        except Exception as e:
            log.error("Flush pending offers failed: %s", e)

        # Раз в 10 минут — пересмотр заявок, которые не получали офферов
        now_ts = asyncio.get_event_loop().time()
        if _last_sweep_ts is None or now_ts - _last_sweep_ts >= SWEEP_INTERVAL_SEC:
            try:
                await _sweep_stale_waitlists()
                _last_sweep_ts = now_ts
            except Exception as e:
                log.error("Sweep stale waitlists failed: %s", e)

        try:
            await _fulfill_waitlist_on_bookings()
        except Exception as e:
            log.error("Fulfill waitlist failed: %s", e)

        today = datetime.now().date()
        if _last_expire_date != today:
            try:
                await _expire_daily()
            except Exception as e:
                log.error("Waitlist expire failed: %s", e)

        await asyncio.sleep(CHECK_INTERVAL)


# ==================== Ручной notify (из админки) ====================

async def notify_single_waitlist_entry(waitlist_id):
    """Ручной пинок одной заявки из админки: ищем ближайший свободный слот,
    подходящий под заявку, отправляем уведомление только этой заявке.

    Возвращает (result, info):
      ("sent", slot_id)
      ("no_slot", None)             — нет свободных подходящих слотов
      ("blocked", None)             — клиент заблокировал бота
      ("error", "текст")            — прочие ошибки / заявка неактивна
    """
    entry = get_waitlist_entry(waitlist_id)
    if not entry:
        return ("error", "not_found")
    if entry["status"] != "active":
        return ("error", "not_active")
    if str(entry["user_id"]).startswith("phone:"):
        return ("error", "phone_only")

    conn = db()
    conds = [
        "s.org_id = ?",
        "s.request_id IS NULL",
        "s.date >= ?",
        "s.date <= ?",
    ]
    params = [entry["org_id"], entry["date_from"], entry["date_to"]]
    if entry["service_id"]:
        conds.append("(s.service_id IS NULL OR s.service_id = ?)")
        params.append(entry["service_id"])
    if entry["doctor_id"]:
        conds.append("s.doctor_id = ?")
        params.append(entry["doctor_id"])
    if entry["branch_id"]:
        conds.append("s.branch_id = ?")
        params.append(entry["branch_id"])

    slot = conn.execute(
        "SELECT s.id, s.date, s.time, s.doctor_id, s.branch_id, s.service_id, "
        "       d.name AS doctor_name, b.name AS branch_name, "
        "       sv.name AS service_name "
        "FROM slots s "
        "LEFT JOIN doctors d ON d.id = s.doctor_id "
        "LEFT JOIN branches b ON b.id = s.branch_id "
        "LEFT JOIN services sv ON sv.id = s.service_id "
        "WHERE " + " AND ".join(conds) + " "
        "ORDER BY s.date, s.time LIMIT 1",
        params,
    ).fetchone()
    conn.close()

    if not slot:
        return ("no_slot", None)

    offer_id = create_slot_offer(
        entry["org_id"], slot["id"], entry["user_id"],
        kind="waitlist", original_request_id=None,
        waitlist_id=entry["id"],
    )

    date_human = _fmt_slot(slot["date"], slot["time"])
    text = (
        f"🔔 **Освободилось время**\n\n"
        f"**{slot['service_name'] or 'Услуга'}**\n"
        f"📅 {date_human}\n"
    )
    if slot["doctor_name"]:
        text += f"👤 {slot['doctor_name']}\n"
    if slot["branch_name"]:
        text += f"🏢 {slot['branch_name']}\n"

    buttons = [[
        {"type": "callback", "text": "✅ Записаться", "payload": f"wl:accept:{offer_id}"},
        {"type": "callback", "text": "❌ Не нужно", "payload": f"wl:decline:{offer_id}"},
    ]]

    try:
        await send_to_client_raw(entry["user_id"], text, buttons, fmt="markdown")
        mark_waitlist_notified(entry["id"], slot["id"])
        return ("sent", slot["id"])
    except UserBlocked:
        update_slot_offer_status(offer_id, "taken", error="blocked")
        return ("blocked", None)
    except Exception as e:
        log.warning("notify_single_waitlist_entry failed: %s", e)
        update_slot_offer_status(offer_id, "expired", error=str(e)[:200])
        return ("error", str(e)[:200])