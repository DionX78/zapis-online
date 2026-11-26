"""Фоновый воркер: напоминания + client-подтверждение + вечерняя сводка + рассылки + график."""
import asyncio
import logging
from datetime import datetime, date as _date, timedelta

import config
from core.channels.base import UserBlocked
from core.messaging import send_to_client_raw
from core.geo import route_lines
from core.notify import notify_admins
from storage.db import (
    autocomplete_past_visits, cancel_stale_pending,
    get_upcoming_confirmed, mark_reminder_sent, increment_reminder_attempt,
    get_org_settings, get_request,
    get_pending_for_client_confirm, mark_client_asked, increment_client_ask_attempt,
    get_pending_timeout, set_client_answer,
    list_orgs, get_org, get_orgs_with_evening_summary,
    get_today_requests_for_summary,
    now_for_org,
    regenerate_all_slots_for_org,
    find_visits_for_review_request, mark_review_requested,
    db as _db,
)

log = logging.getLogger(__name__)

CHECK_INTERVAL = 5 * 60
MIN_DELAY_AFTER_BOOKING_HOURS = 2
QUIET_HOURS_START = 22
QUIET_HOURS_END = 9
LAST_CHANCE_MINUTES = 60

_last_summary_sent = {}
_last_horizon_extend = {}


def _is_phone_only(user_id) -> bool:
    return str(user_id or "").startswith("phone:")


def _parse_sched(sched_str):
    try:
        return datetime.strptime(sched_str, "%Y-%m-%d %H:%M")
    except Exception:
        return None


def _is_quiet_hours(now_local, start_hour=None, end_hour=None):
    """Проверка «тихих часов». Границы можно передать явно
    (из настроек организации), иначе используются константы по умолчанию."""
    if start_hour is None:
        start_hour = QUIET_HOURS_START
    if end_hour is None:
        end_hour = QUIET_HOURS_END

    h = now_local.hour
    if start_hour == end_hour:
        return False  # вырожденный случай — тихих часов нет
    if start_hour > end_hour:
        # переход через полночь: 22 → 9
        return h >= start_hour or h < end_hour
    # обычный интервал: 1 → 6
    return start_hour <= h < end_hour


# ==================== напоминания ====================

async def _send_reminder(request_id, kind, attempts_used, now_local):
    req = get_request(request_id)
    if not req:
        return
    rid = req["id"]
    org_id = req["org_id"]
    client_uid = req["user_id"]
    service_name = req["service_name"]
    scheduled_at = req["scheduled_at"]
    address = req["address"]
    doctor = req["doctor"]

    if not client_uid:
        return
    if _is_phone_only(client_uid):
        mark_reminder_sent(request_id, "2h" if kind == "last_chance" else kind)
        log.info("Reminder %s for #%s skipped: phone-only client", kind, request_id)
        return
    if attempts_used >= config.MAX_SEND_ATTEMPTS:
        mark_reminder_sent(request_id, "2h" if kind == "last_chance" else kind)
        log.warning("Reminder %s for #%s gave up after %d attempts",
                    kind, request_id, attempts_used)
        return

    if kind == "24h":
        header = "🔔 **Напоминание о записи**\n\nЗавтра у вас приём."
    elif kind == "2h":
        header = "🔔 **Напоминание о записи**\n\nЧерез 2 часа у вас приём."
    elif kind == "last_chance":
        header = "🔔 **Скоро приём**\n\nНапоминаем — приём уже скоро."
    else:
        header = "🔔 **Напоминание о записи**"

    text = f"{header}\n\n**{service_name}**\n📅 {scheduled_at}\n"
    if address:
        text += route_lines(address, org_id=org_id)
    if doctor:
        text += f"👨‍⚕️ {doctor}\n"

    buttons = [[
        {"type": "callback", "text": "✅ Подтверждаю", "payload": f"rem:yes:{rid}"},
        {"type": "callback", "text": "❌ Отменить", "payload": f"rem:no:{rid}"},
    ]]

    try:
        await send_to_client_raw(client_uid, text, buttons, fmt="markdown")
        mark_reminder_sent(request_id, "2h" if kind == "last_chance" else kind)
        log.info("Reminder %s sent for #%s", kind, request_id)
    except UserBlocked:
        mark_reminder_sent(request_id, "2h" if kind == "last_chance" else kind)
        log.info("Reminder %s skipped for #%s: user blocked bot", kind, request_id)
    except Exception as e:
        increment_reminder_attempt(request_id, "2h" if kind == "last_chance" else kind)
        log.warning("Reminder %s failed for #%s (attempt %d/%d): %s",
                    kind, request_id, attempts_used + 1, config.MAX_SEND_ATTEMPTS, e)


def _get_created_at(request_id):
    conn = _db()
    row = conn.execute("SELECT created_at FROM history WHERE id=?", (request_id,)).fetchone()
    conn.close()
    return row["created_at"] if row else None


async def _check_reminders():
    rows = get_upcoming_confirmed()
    for r in rows:
        rid = r["id"]
        org_id = r["org_id"]
        scheduled_at = r["scheduled_at"]
        rem24 = r["reminder_24_sent_at"]
        rem2 = r["reminder_2_sent_at"]
        att24 = r["reminder_24_attempts"] or 0
        att2 = r["reminder_2_attempts"] or 0

        now_local = now_for_org(org_id)
        sched_dt = _parse_sched(scheduled_at)
        if not sched_dt:
            continue
        delta = sched_dt - now_local
        seconds = delta.total_seconds()
        if seconds <= 0:
            continue

        created_at = _get_created_at(rid)
        if created_at:
            try:
                created_dt = datetime.fromisoformat(created_at)
                if (datetime.now() - created_dt).total_seconds() < MIN_DELAY_AFTER_BOOKING_HOURS * 3600 \
                        and seconds > 2 * 3600:
                    continue
            except Exception:
                pass

        settings = get_org_settings(org_id)
        want_24h = settings.get("reminder_24h", True)
        want_2h = settings.get("reminder_2h", True)
        quiet_start = int(settings.get("quiet_hours_start", QUIET_HOURS_START) or 0)
        quiet_end = int(settings.get("quiet_hours_end", QUIET_HOURS_END) or 0)
        quiet = _is_quiet_hours(now_local, quiet_start, quiet_end)

        if seconds <= LAST_CHANCE_MINUTES * 60 and not rem2:
            await _send_reminder(rid, "last_chance", att2, now_local)
            continue
        if quiet:
            continue
        if 0 < seconds <= 2 * 3600 and want_2h and not rem2:
            await _send_reminder(rid, "2h", att2, now_local)
            continue
        # 24h reminder не нужен, если по записи уже был client-confirm
        # (клиент уже получил запрос «Придёте?» и ответил/думает).
        client_asked_at = r["client_asked_at"]
        if (20 * 3600 < seconds <= 24 * 3600 and want_24h and not rem24
                and not client_asked_at):
            await _send_reminder(rid, "24h", att24, now_local)
            continue


# ==================== client confirm ====================

async def _ask_client_confirm(request_id, attempts_used):
    req = get_request(request_id)
    if not req:
        return
    rid = req["id"]
    org_id = req["org_id"]
    client_uid = req["user_id"]
    service_name = req["service_name"]
    scheduled_at = req["scheduled_at"]
    address = req["address"]
    doctor = req["doctor"]

    if not client_uid:
        return
    if _is_phone_only(client_uid):
        mark_client_asked(rid)
        log.info("Client confirm for #%s skipped: phone-only client", request_id)
        return
    if attempts_used >= config.MAX_SEND_ATTEMPTS:
        mark_client_asked(rid)
        log.warning("Client confirm for #%s gave up after %d attempts",
                    request_id, attempts_used)
        return

    text = (
        f"❓ **Подтверждение записи**\n\n"
        f"Вы записаны на **{service_name}**\n"
        f"📅 {scheduled_at}\n"
    )
    if address:
        text += route_lines(address, org_id=org_id)
    if doctor:
        text += f"👨‍⚕️ {doctor}\n"
    text += "\nПридёте?"

    buttons = [[
        {"type": "callback", "text": "✅ Приду", "payload": f"cc:yes:{rid}"},
        {"type": "callback", "text": "❌ Не смогу", "payload": f"cc:no:{rid}"},
    ]]

    try:
        await send_to_client_raw(client_uid, text, buttons, fmt="markdown")
        mark_client_asked(rid)
        log.info("Client confirm asked for #%s", request_id)
    except UserBlocked:
        mark_client_asked(rid)
        log.info("Client confirm skipped for #%s: user blocked bot", request_id)
    except Exception as e:
        increment_client_ask_attempt(rid)
        log.warning("Failed to ask client for #%s (attempt %d/%d): %s",
                    request_id, attempts_used + 1, config.MAX_SEND_ATTEMPTS, e)


async def _check_client_confirm():
    rows = get_pending_for_client_confirm()
    for r in rows:
        rid = r["id"]
        org_id = r["org_id"]
        scheduled_at = r["scheduled_at"]
        created_at = r["created_at"]
        attempts = r["client_ask_attempts"] or 0

        settings = get_org_settings(org_id)
        if settings.get("confirmation_mode") != "client":
            continue
        delay_min = int(settings.get("client_confirm_delay_min", 60))

        now_local = now_for_org(org_id)
        try:
            created_dt = datetime.fromisoformat(created_at)
            sched_dt = _parse_sched(scheduled_at)
        except Exception:
            continue
        if not sched_dt:
            continue

        # Тихие часы: не дёргаем клиента ночью, КРОМЕ случая,
        # когда приём наступит раньше, чем закончатся тихие часы
        # (иначе клиент вообще не получит запрос на подтверждение).
        quiet_start = int(settings.get("quiet_hours_start", QUIET_HOURS_START) or 0)
        quiet_end = int(settings.get("quiet_hours_end", QUIET_HOURS_END) or 0)
        if _is_quiet_hours(now_local, quiet_start, quiet_end):
            quiet_end_dt = now_local.replace(
                hour=quiet_end, minute=0, second=0, microsecond=0
            )
            if quiet_end_dt <= now_local:
                quiet_end_dt += timedelta(days=1)
            if sched_dt > quiet_end_dt:
                continue

        minutes_to_appt = (sched_dt - now_local).total_seconds() / 60
        if minutes_to_appt <= 0:
            continue

        effective_delay = delay_min
        if minutes_to_appt < delay_min:
            effective_delay = min(2, max(1, minutes_to_appt - 1))

        delta_since_created_min = (datetime.now() - created_dt).total_seconds() / 60
        if delta_since_created_min < effective_delay:
            continue
        await _ask_client_confirm(rid, attempts)


async def _check_client_timeout():
    rows = get_pending_timeout()
    for r in rows:
        rid = r["id"]
        org_id = r["org_id"]
        service_name = r["service_name"]
        scheduled_at = r["scheduled_at"]
        phone = r["phone"]
        client_asked_at = r["client_asked_at"]
        settings = get_org_settings(org_id)
        if settings.get("confirmation_mode") != "client":
            continue
        timeout_min = int(settings.get("client_confirm_timeout_min", 120))
        try:
            asked_dt = datetime.fromisoformat(client_asked_at)
        except Exception:
            continue
        delta_since_asked_min = (datetime.now() - asked_dt).total_seconds() / 60
        if delta_since_asked_min < timeout_min:
            continue
        set_client_answer(rid, "timeout")
        await notify_admins(
            f"⏰ **Клиент не ответил на подтверждение**\n\n"
            f"**{service_name}**\n📅 {scheduled_at}\n"
            f"Телефон: {phone or '—'}\n\n"
            f"Заявка остаётся в статусе «ожидает». Подтвердите вручную или позвоните клиенту.",
            org_id=org_id,
        )
        log.info("Client timeout for #%s, admin notified", rid)


# ==================== запросы на отзыв ====================

async def _check_review_requests():
    """Отправляет запрос на отзыв клиентам через N часов после done-визита.

    Один запрос на клиента: если у клиента несколько done-визитов без отзыва —
    берём самый свежий (find_visits_for_review_request уже это делает).
    """
    for org in list_orgs():
        oid = org["id"]
        try:
            settings = get_org_settings(oid)
        except Exception:
            continue
        if not settings.get("review_request_enabled"):
            continue
        delay_h = int(settings.get("review_request_delay_hours", 2) or 2)

        try:
            visits = find_visits_for_review_request(oid, delay_h)
        except Exception as e:
            log.error("review_request: query failed for org %s: %s", oid, e)
            continue

        for v in visits:
            rid = v["request_id"]
            uid = v["user_id"]
            if not uid or str(uid).startswith("phone:"):
                continue

            name = (v["first_name"] or "").strip() or "друг"
            service_name = v["service_name"] or ""
            text = (
                f"🙏 **{name}**, спасибо, что были у нас!\n\n"
            )
            if service_name:
                text += f"**{service_name}**\n\n"
            text += "Оцените, пожалуйста, визит от 1 до 5 звёзд — это займёт 1 секунду и очень поможет нам стать лучше."

            buttons = [[
                {"type": "callback", "text": "1 ⭐", "payload": f"rv:rate:{rid}:1"},
                {"type": "callback", "text": "2 ⭐", "payload": f"rv:rate:{rid}:2"},
                {"type": "callback", "text": "3 ⭐", "payload": f"rv:rate:{rid}:3"},
                {"type": "callback", "text": "4 ⭐", "payload": f"rv:rate:{rid}:4"},
                {"type": "callback", "text": "5 ⭐", "payload": f"rv:rate:{rid}:5"},
            ]]

            try:
                await send_to_client_raw(uid, text, buttons, fmt="markdown")
                mark_review_requested(rid)
                log.info("review_request sent: org=%s uid=%s req=%s", oid, uid, rid)
                await asyncio.sleep(0.5)
            except UserBlocked:
                mark_review_requested(rid)
                log.info("review_request skipped: uid=%s blocked bot (marked)", uid)
            except Exception as e:
                log.warning("review_request send failed uid=%s: %s", uid, e)


# ==================== вечерняя сводка ====================

def _evening_summary_buttons(org_id, today_str):
    return [
        [
            {"type": "callback", "text": "📊 День (PDF)",
             "payload": f"rep:day_pdf:{org_id}:{today_str}"},
            {"type": "callback", "text": "📊 Неделя (XLSX)",
             "payload": f"rep:week_xlsx:{org_id}:{today_str}"},
        ],
        [
            {"type": "callback", "text": "📄 Сводка (CSV)",
             "payload": f"rep:day_csv:{org_id}:{today_str}"},
        ],
    ]


async def _send_evening_summary(org_id, today_str):
    try:
        org = get_org(org_id)
        if not org:
            log.warning("Evening summary: org %s not found", org_id)
            return
        org_name = org["name"]
        rows = get_today_requests_for_summary(org_id, today_str)

        if not rows:
            text = (
                f"🌙 **Итоги дня · {today_str}**\n\n"
                f"🏢 {org_name}\n\n"
                f"📭 Записей на сегодня не было."
            )
            buttons = _evening_summary_buttons(org_id, today_str)
            await notify_admins(text, org_id=org_id, buttons=buttons)
            log.info("Evening summary (empty day) sent for org %s (%s)",
                     org_id, today_str)
            return

        total = len(rows)
        done = 0
        no_show = 0
        pending = 0
        confirmed = 0
        cancelled = 0
        revenue = 0
        for r in rows:
            st = r["status"]
            if st == "done":
                done += 1
                if r["actual_amount"]:
                    revenue += int(r["actual_amount"])
            elif st == "no_show":
                no_show += 1
            elif st == "pending":
                pending += 1
            elif st == "confirmed":
                confirmed += 1
            elif st == "cancelled":
                cancelled += 1

        from datetime import date as _d, timedelta as _td
        tomorrow = (_d.fromisoformat(today_str) + _td(days=1)).isoformat()
        conn = _db()
        tomorrow_count = conn.execute(
            "SELECT COUNT(*) AS n FROM history "
            "WHERE org_id=? AND date(scheduled_at)=date(?) "
            "AND status IN ('pending','confirmed')",
            (org_id, tomorrow),
        ).fetchone()["n"]
        conn.close()

        text = (
            f"🌙 **Итоги дня · {today_str}**\n\n"
            f"🏢 {org_name}\n"
            f"Всего записей: {total}\n"
            f"✅ Пришли: {done}\n"
            f"🚫 Не пришли: {no_show}\n"
            f"🟡 Ожидают: {pending}\n"
            f"🔵 Подтверждены: {confirmed}\n"
            f"❌ Отменены: {cancelled}\n"
        )
        if revenue > 0:
            text += f"\n💰 Выручка: **{revenue} ₽**\n"
        text += f"\n📅 На завтра записано: {tomorrow_count}"

        buttons = _evening_summary_buttons(org_id, today_str)
        await notify_admins(text, org_id=org_id, buttons=buttons)
        log.info("Evening summary sent for org %s (%s)", org_id, today_str)
    except Exception as e:
        log.error("Evening summary failed for org %s: %s", org_id, e)


async def _check_evening_summaries():
    for org_id, summary_hour in get_orgs_with_evening_summary():
        now_local = now_for_org(org_id)
        if now_local.hour != summary_hour:
            continue
        today_str = now_local.strftime("%Y-%m-%d")
        if _last_summary_sent.get(org_id) == today_str:
            continue
        log.info("Evening summary due for org %s (hour=%d, date=%s)",
                 org_id, summary_hour, today_str)
        await _send_evening_summary(org_id, today_str)
        _last_summary_sent[org_id] = today_str


# ==================== автопродление горизонта графиков ====================

async def _extend_schedules_horizon():
    """Раз в сутки продлевает горизонт автогенерированных слотов для всех организаций.
    Тяжёлая синхронная работа вынесена в отдельный поток через asyncio.to_thread,
    чтобы не блокировать event loop (иначе бот перестаёт отвечать на webhook).
    """
    today_local = _date.today()
    for org in list_orgs():
        oid = org["id"]
        if _last_horizon_extend.get(oid) == today_local:
            continue
        try:
            r = await asyncio.to_thread(regenerate_all_slots_for_org, oid)
            if r["doctors"] > 0:
                log.info(
                    "Schedule horizon extended for org %s: doctors=%d created=%d deleted=%d skipped_booked=%d",
                    oid, r["doctors"], r["created"], r["deleted"], r["skipped_booked"],
                )
            _last_horizon_extend[oid] = today_local
        except Exception as e:
            log.error("Schedule horizon extend failed for org %s: %s", oid, e)


# ==================== housekeeping ====================

async def _cleanup_temp_exports():
    """Удаляет временные файлы экспорта (csv/xlsx/pdf):
    1) старше 1 часа — независимо от того, что в БД;
    2) файлы на диске без записи в uploaded_images (orphans).
    Не трогает изображения (картинки рассылок, фото клиентов/специалистов).
    """
    import os as _os
    import config as _config
    from storage.db import (
        list_temp_exports_older_than, list_orphan_uploaded_files,
        delete_uploaded_image_file, list_orgs,
    )
    from pathlib import Path as _Path

    deleted = 0

    # 1. Временные экспорты старше 1 часа
    try:
        stale = list_temp_exports_older_than(60)
        for row in stale:
            try:
                delete_uploaded_image_file(row["id"])
                deleted += 1
            except Exception as e:
                log.warning("Cleanup temp export id=%s failed: %s", row["id"], e)
    except Exception as e:
        log.error("Cleanup temp exports error: %s", e)

    # 2. Orphan-файлы на диске (нет записи в БД)
    try:
        for org in list_orgs():
            oid = org["id"]
            orphans = list_orphan_uploaded_files(oid, ["csv", "xlsx", "pdf"])
            for rel_path in orphans:
                try:
                    abs_path = _Path(_config.UPLOADS_DIR) / rel_path
                    if abs_path.exists():
                        abs_path.unlink()
                        deleted += 1
                except Exception as e:
                    log.warning("Cleanup orphan file %s failed: %s", rel_path, e)
    except Exception as e:
        log.error("Cleanup orphan files error: %s", e)

    if deleted:
        log.info("Cleanup temp exports: deleted %d file(s)", deleted)


async def _daily_housekeeping():
    """Ежедневные задачи по каждой организации:
    - автозавершение прошедших confirmed → done (с суммой по прайсу, done_auto=1)
    - отмена зависших pending (pending_timeout_min) с освобождением слотов

    Раньше функция вызывалась в воркере, но потерялась при рефакторинге —
    при этом импорты autocomplete_past_visits/cancel_stale_pending остались.
    Восстанавливаем.
    """
    for org in list_orgs():
        oid = org["id"]
        try:
            settings = get_org_settings(oid)
        except Exception as e:
            log.warning("Housekeeping: get_org_settings failed for org %s: %s", oid, e)
            continue

        autocomplete_hours = int(settings.get("autocomplete_after_hours", 3) or 0)
        pending_timeout = int(settings.get("pending_timeout_min", 0) or 0)

        if autocomplete_hours > 0:
            try:
                n = await asyncio.to_thread(
                    autocomplete_past_visits, autocomplete_hours, oid,
                )
                if n:
                    log.info("Autocompleted %d visits for org %s", n, oid)
            except Exception as e:
                log.error("Autocomplete failed for org %s: %s", oid, e)

        if pending_timeout > 0:
            try:
                n = await asyncio.to_thread(
                    cancel_stale_pending, pending_timeout, oid,
                )
                if n:
                    log.info("Cancelled %d stale pending for org %s", n, oid)
            except Exception as e:
                log.error("Cancel stale pending failed for org %s: %s", oid, e)


async def run_reminder_worker():
    log.info("Reminder worker started")

    await asyncio.sleep(60)
    while True:
        try:
            await _daily_housekeeping()
        except Exception as e:
            log.error("Housekeeping cycle error: %s", e)

        try:
            await _cleanup_temp_exports()
        except Exception as e:
            log.error("Cleanup temp exports cycle error: %s", e)

        try:
            await _extend_schedules_horizon()
        except Exception as e:
            log.error("Schedule horizon cycle error: %s", e)

        try:
            await _check_reminders()
        except Exception as e:
            log.error("Reminders cycle error: %s", e)

        try:
            await _check_client_confirm()
        except Exception as e:
            log.error("Client confirm cycle error: %s", e)

        try:
            await _check_client_timeout()
        except Exception as e:
            log.error("Client timeout cycle error: %s", e)

        try:
            await _check_review_requests()
        except Exception as e:
            log.error("Review requests cycle error: %s", e)

        try:
            await _check_evening_summaries()
        except Exception as e:
            log.error("Evening summary cycle error: %s", e)

        await asyncio.sleep(CHECK_INTERVAL)


# ==================== Супервизор воркеров ====================

async def run_supervised(name: str, worker_fn):
    """Обёртка для фоновых воркеров: перезапускает при падении.

    Если воркер бросил исключение (кроме CancelledError) — логируем
    и перезапускаем через 30 секунд. Так один упавший воркер не убивает
    остальные и сам восстанавливается до рестарта бота.
    """
    while True:
        try:
            await worker_fn()
        except asyncio.CancelledError:
            log.info("%s worker cancelled", name)
            raise
        except Exception as e:
            log.exception("%s worker crashed: %s. Restart in 30s", name, e)
            await asyncio.sleep(30)