"""Воркер отправки рассылок (ручных и автоматических)."""
import asyncio
import json
import logging
import os
from datetime import datetime, timedelta

import config
from core.channels.base import UserBlocked, ChannelError
from core.channels.registry import get_channel_for_client
from core.messaging import send_to_client_raw
from core.reminders import _is_quiet_hours
from core import max_client as mx  # noqa: F401 (legacy: только upload_file для refresh токена)
from storage.db import (
    db,
    check_auto_log_birthday,
    check_auto_log_inactive, check_auto_log_after_visit, log_auto_broadcast,
    get_uploaded_image_by_id, update_uploaded_image_token,
    get_scheduled_broadcasts_due,
    get_client, get_request, get_branch, get_service,
    find_revisit_candidates, check_auto_log_revisit,
    now_for_org, get_org_settings,
)

log = logging.getLogger(__name__)

SEND_DELAY = 0.5
SCHEDULED_CHECK_INTERVAL = 60  # сек

UNSUB_BUTTONS = [[
    {"type": "callback", "text": "🚫 Больше не присылать", "payload": "unsub"},
]]


# ==================== refresh image token ====================

async def refresh_image_token(upload_id, channel=None, user_id=None):
    """Перезагружает файл с диска в канал, обновляет token в БД.
    Возвращает новый token для канала или None, если файла нет.

    channel=None — легаси-ветка с MAX (когда канал клиента неизвестен).
    token в uploaded_images хранится в паспорте MAX, поэтому для VK
    вернём свежий token, но в БД его не пишем."""
    img = get_uploaded_image_by_id(upload_id)
    if not img:
        return None
    file_path = img["file_path"]
    if not file_path:
        log.warning("refresh_image_token: file_path is NULL for upload_id=%s", upload_id)
        return None
    abs_path = os.path.join(config.UPLOADS_DIR, file_path)
    if not os.path.exists(abs_path):
        log.warning("refresh_image_token: file not found at %s", abs_path)
        return None
    try:
        with open(abs_path, "rb") as f:
            content = f.read()
    except Exception as e:
        log.error("refresh_image_token: read error %s", e)
        return None
    filename = img["original_filename"] or "image.jpg"
    mime = img["mime_type"] or "image/jpeg"
    if channel is not None:
        try:
            try:
                new_token = await channel.upload_file(
                    content, filename=filename, mime=mime, upload_type="image",
                    user_id=user_id,
                )
            except TypeError:
                new_token = await channel.upload_file(
                    content, filename=filename, mime=mime, upload_type="image",
                )
            if getattr(channel, "platform", "") == "max":
                update_uploaded_image_token(upload_id, new_token)
            log.info("refresh_image_token: upload_id=%s platform=%s token=%s",
                     upload_id, getattr(channel, "platform", "?"), new_token[:12])
            return new_token
        except Exception as e:
            log.error("refresh_image_token: upload to %s failed %s",
                      getattr(channel, "platform", "?"), e)
            return None
    try:
        new_token = await mx.upload_file(
            content,
            filename=filename,
            mime=mime,
            upload_type="image",
        )
        update_uploaded_image_token(upload_id, new_token)
        log.info("refresh_image_token: upload_id=%s (max) new_token=%s",
                 upload_id, new_token[:12])
        return new_token
    except Exception as e:
        log.error("refresh_image_token: upload failed %s", e)
        return None


async def _send_with_refresh(user_id, text, image_id, buttons=None, fmt="markdown",
                            org_id=None):
    """Отправляет сообщение с картинкой через канал клиента (не MAX напрямую).

    Токен в uploaded_images принадлежит MAX, поэтому:
    - канал MAX → пробуем сохранённый token, при ошибке перезаливаем и сохраняем;
    - другой канал → сразу перезаливаем в него (токен платформо-зависим).

    Бросает UserBlocked — клиент заблокировал бота.
    Бросает ChannelError — отправить не удалось (в т.ч. у клиента нет канала).
    """
    uid_str = str(user_id or "")
    channel, platform_uid, platform = get_channel_for_client(uid_str, org_id)
    if channel is None:
        raise ChannelError("no channel for user")

    img = get_uploaded_image_by_id(image_id) if image_id else None
    token = img["token"] if img else None

    if token and platform == "max":
        try:
            await channel.send_with_image(platform_uid, text, token,
                                          buttons=buttons, fmt=fmt)
            return
        except UserBlocked:
            raise
        except Exception as e:
            log.warning("send_with_image failed (upload_id=%s, err=%s), refreshing…",
                        image_id, e)

    new_token = (await refresh_image_token(image_id, channel, user_id=uid_str)
                 if image_id else None)
    if not new_token:
        raise ChannelError(f"Cannot send image: upload_id={image_id} refresh failed")

    await channel.send_with_image(platform_uid, text, new_token,
                                  buttons=buttons, fmt=fmt)


# ==================== РУЧНЫЕ РАССЫЛКИ ====================

def get_clients_for_segment(org_id: int, segment: dict) -> list[str]:
    segment = segment or {}
    activity = segment.get("activity", "all")
    gender = segment.get("gender", "all")
    birthday_days = segment.get("birthday_within_days")

    service_ids = segment.get("service_ids")
    if not service_ids:
        single = segment.get("service_id")
        if single:
            service_ids = [single]
    service_ids = service_ids or []

    # Пороги «под риском / потерянные» — из настроек организации
    from storage.db import get_org_settings
    settings = get_org_settings(org_id)
    at_risk_days = int(settings.get("client_at_risk_days", 30) or 30)
    inactive_days = int(settings.get("client_inactive_days", 90) or 90)

    conn = db()
    cur = conn.cursor()

    base_q = (
        "SELECT DISTINCT c.user_id AS user_id FROM clients c "
        "LEFT JOIN history h ON h.user_id = c.user_id AND h.org_id = ? "
        "WHERE (c.org_id = ? OR h.id IS NOT NULL) "
        "  AND (c.marketing_opt_out IS NULL OR c.marketing_opt_out = 0) "
        # phone:... — клиент без канала (запись от админа по телефону).
        # Слать некуда, в рассылку не берём.
        "  AND c.user_id NOT LIKE 'phone:%' "
    )
    params = [org_id, org_id]

    now = datetime.now()
    if activity == "active_recent":
        cutoff = (now - timedelta(days=at_risk_days)).strftime("%Y-%m-%d %H:%M")
        base_q += "AND c.last_visit_at >= ? "
        params.append(cutoff)
    elif activity == "at_risk":
        cutoff_lost = (now - timedelta(days=inactive_days)).strftime("%Y-%m-%d %H:%M")
        cutoff_risk = (now - timedelta(days=at_risk_days)).strftime("%Y-%m-%d %H:%M")
        base_q += "AND c.last_visit_at >= ? AND c.last_visit_at < ? "
        params.append(cutoff_lost)
        params.append(cutoff_risk)
    elif activity == "lost":
        cutoff = (now - timedelta(days=inactive_days)).strftime("%Y-%m-%d %H:%M")
        base_q += "AND c.last_visit_at < ? "
        params.append(cutoff)
    elif activity == "never":
        base_q += "AND c.last_visit_at IS NULL "
    elif activity.startswith("active_"):
        days = int(activity.split("_")[1])
        cutoff = (now - timedelta(days=days)).strftime("%Y-%m-%d %H:%M")
        base_q += "AND c.last_visit_at >= ? "
        params.append(cutoff)
    elif activity.startswith("inactive_"):
        days = int(activity.split("_")[1])
        cutoff = (now - timedelta(days=days)).strftime("%Y-%m-%d %H:%M")
        base_q += "AND (c.last_visit_at IS NULL OR c.last_visit_at < ?) "
        params.append(cutoff)

    if gender in ("male", "female"):
        base_q += "AND c.gender = ? "
        params.append(gender)

    if service_ids:
        placeholders = ",".join("?" * len(service_ids))
        base_q += (
            f"AND EXISTS (SELECT 1 FROM history h2 "
            f"WHERE h2.user_id = c.user_id AND h2.org_id = ? "
            f"AND (h2.service_id IN ({placeholders}) "
            f"OR h2.service_name IN (SELECT name FROM services WHERE id IN ({placeholders})))) "
        )
        params.append(org_id)
        params.extend(service_ids)
        params.extend(service_ids)

    cur.execute(base_q, params)
    all_rows = cur.fetchall()
    conn.close()

    user_ids = [r["user_id"] for r in all_rows]

    if birthday_days:
        conn = db()
        placeholders = ",".join("?" * len(user_ids)) if user_ids else "''"
        rows = conn.execute(
            f"SELECT user_id, birth_date FROM clients WHERE user_id IN ({placeholders})",
            user_ids,
        ).fetchall()
        conn.close()

        today = datetime.now().date()
        result = []
        for r in rows:
            uid = r["user_id"]
            bd = r["birth_date"]
            if not bd:
                continue
            try:
                bd_date = datetime.strptime(bd, "%Y-%m-%d").date()
            except Exception:
                continue
            bd_this_year = bd_date.replace(year=today.year)
            if bd_this_year < today:
                bd_this_year = bd_date.replace(year=today.year + 1)
            days_until = (bd_this_year - today).days
            if 0 <= days_until <= birthday_days:
                result.append(uid)
        user_ids = result

    return user_ids


def create_broadcast(org_id, text, segment, created_by=None,
                     image_id=None, scheduled_at=None, status="draft"):
    conn = db()
    cur = conn.execute(
        "INSERT INTO broadcasts "
        "(org_id, text, segment_json, status, image_id, scheduled_at, "
        " created_by, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (org_id, text, json.dumps(segment or {}, ensure_ascii=False),
         status, image_id, scheduled_at,
         str(created_by) if created_by else None,
         datetime.now().isoformat()),
    )
    bid = cur.lastrowid
    conn.commit()
    conn.close()
    return bid


def get_broadcast(bid):
    conn = db()
    row = conn.execute(
        "SELECT id, org_id, text, segment_json, status, total_recipients, "
        "       sent_count, failed_count, image_id, scheduled_at, created_by, "
        "       created_at, started_at, finished_at "
        "FROM broadcasts WHERE id=?",
        (bid,),
    ).fetchone()
    conn.close()
    return row


def list_broadcasts(org_id, limit=50):
    conn = db()
    rows = conn.execute(
        "SELECT id, text, status, total_recipients, sent_count, failed_count, "
        "       created_at, started_at, finished_at, image_id, scheduled_at "
        "FROM broadcasts WHERE org_id=? "
        "ORDER BY id DESC LIMIT ?",
        (org_id, limit),
    ).fetchall()
    conn.close()
    return rows


def start_broadcast(bid, total_recipients):
    conn = db()
    conn.execute(
        "UPDATE broadcasts SET status='sending', total_recipients=?, started_at=? "
        "WHERE id=? AND status IN ('draft', 'scheduled')",
        (total_recipients, datetime.now().isoformat(), bid),
    )
    conn.commit()
    conn.close()


def cancel_broadcast(bid):
    conn = db()
    conn.execute(
        "UPDATE broadcasts SET status='cancelled', finished_at=? "
        "WHERE id=? AND status IN ('draft', 'scheduled', 'sending')",
        (datetime.now().isoformat(), bid),
    )
    conn.commit()
    conn.close()


def delete_broadcast(bid):
    conn = db()
    conn.execute("DELETE FROM broadcast_sends WHERE broadcast_id=?", (bid,))
    conn.execute("DELETE FROM broadcasts WHERE id=?", (bid,))
    conn.commit()
    conn.close()


def get_pending_broadcasts():
    conn = db()
    rows = conn.execute(
        "SELECT id, org_id, text, segment_json, total_recipients, sent_count, "
        "       failed_count, image_id "
        "FROM broadcasts WHERE status='sending'"
    ).fetchall()
    conn.close()
    return rows


def get_next_pending_send(broadcast_id):
    conn = db()
    row = conn.execute(
        "SELECT id, user_id FROM broadcast_sends "
        "WHERE broadcast_id=? AND status='pending' "
        "ORDER BY id LIMIT 1",
        (broadcast_id,),
    ).fetchone()
    conn.close()
    return row


def mark_send(broadcast_id, user_id, status, error=None):
    conn = db()
    conn.execute(
        "UPDATE broadcast_sends SET status=?, error=?, sent_at=? "
        "WHERE broadcast_id=? AND user_id=?",
        (status, error, datetime.now().isoformat(), broadcast_id, user_id),
    )
    conn.commit()
    conn.close()

    conn = db()
    if status == "sent":
        conn.execute(
            "UPDATE broadcasts SET sent_count = sent_count + 1 WHERE id=?",
            (broadcast_id,),
        )
    elif status in ("failed", "skipped"):
        # skipped = у клиента нет живого канала. В прогресс он не идёт,
        # поэтому считаем его как недоставку — иначе полоса застынет на 99%.
        conn.execute(
            "UPDATE broadcasts SET failed_count = failed_count + 1 WHERE id=?",
            (broadcast_id,),
        )
    conn.commit()
    conn.close()


def finalize_broadcast_if_done(broadcast_id):
    conn = db()
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM broadcast_sends "
        "WHERE broadcast_id=? AND status='pending'",
        (broadcast_id,),
    ).fetchone()
    if row and row["n"] == 0:
        conn.execute(
            "UPDATE broadcasts SET status='sent', finished_at=? WHERE id=?",
            (datetime.now().isoformat(), broadcast_id),
        )
        conn.commit()
        log.info("Broadcast #%s finished", broadcast_id)
    conn.close()


def prepare_broadcast_sends(bid, user_ids):
    conn = db()
    for uid in user_ids:
        conn.execute(
            "INSERT OR IGNORE INTO broadcast_sends (broadcast_id, user_id, status) "
            "VALUES (?, ?, 'pending')",
            (bid, str(uid)),
        )
    conn.commit()
    conn.close()


def get_broadcast_sends(bid, limit=200):
    conn = db()
    rows = conn.execute(
        "SELECT user_id, status, error, sent_at FROM broadcast_sends "
        "WHERE broadcast_id=? ORDER BY id LIMIT ?",
        (bid, limit),
    ).fetchall()
    conn.close()
    return rows


def update_broadcast_draft(bid, text, segment, image_id=None):
    conn = db()
    conn.execute(
        "UPDATE broadcasts SET text=?, segment_json=?, image_id=? "
        "WHERE id=? AND status IN ('draft', 'scheduled')",
        (text, json.dumps(segment or {}, ensure_ascii=False), image_id, bid),
    )
    conn.commit()
    conn.close()


def start_draft_broadcast(bid):
    b = get_broadcast(bid)
    if not b:
        return False, "not_found"
    if b["status"] not in ("draft", "scheduled"):
        return False, "not_a_draft"

    segment = json.loads(b["segment_json"] or "{}")
    user_ids = get_clients_for_segment(b["org_id"], segment)
    if not user_ids:
        return False, "empty"

    prepare_broadcast_sends(bid, user_ids)
    start_broadcast(bid, len(user_ids))
    return True, len(user_ids)


def duplicate_broadcast(bid, created_by=None):
    """Создаёт новый draft — копию с тем же текстом, сегментом, картинкой."""
    src = get_broadcast(bid)
    if not src:
        return None
    conn = db()
    cur = conn.execute(
        "INSERT INTO broadcasts "
        "(org_id, text, segment_json, status, image_id, created_by, created_at) "
        "VALUES (?, ?, ?, 'draft', ?, ?, ?)",
        (src["org_id"], src["text"], src["segment_json"], src["image_id"],
         str(created_by) if created_by else None, datetime.now().isoformat()),
    )
    nid = cur.lastrowid
    conn.commit()
    conn.close()
    return nid


# ==================== отправка ====================

async def _check_manual_broadcasts():
    pending = get_pending_broadcasts()
    for b in pending:
        bid = b["id"]
        text = b["text"]
        image_id = b["image_id"]

        while True:
            current = get_broadcast(bid)
            if not current or current["status"] != "sending":
                log.info("Broadcast #%s stopped (status changed)", bid)
                break

            row = get_next_pending_send(bid)
            if not row:
                finalize_broadcast_if_done(bid)
                break

            uid = str(row["user_id"])
            try:
                if image_id:
                    await _send_with_refresh(uid, text, image_id,
                                             buttons=UNSUB_BUTTONS, fmt="markdown",
                                             org_id=b["org_id"])
                else:
                    await send_to_client_raw(uid, text,
                                          buttons=UNSUB_BUTTONS, fmt="markdown")
                mark_send(bid, uid, "sent")
            except UserBlocked:
                mark_send(bid, uid, "sent", error="blocked")
                log.info("Broadcast #%s: user %s blocked bot", bid, uid)
            except ChannelError as e:
                # У клиента нет живого канала (phone-only, запись от админа):
                # это не сбой рассылки — помечаем пропуск, чтобы не копить pending.
                mark_send(bid, uid, "skipped", f"no channel: {str(e)[:150]}")
                log.info("Broadcast #%s: user %s has no channel, skipped", bid, uid)
            except Exception as e:
                mark_send(bid, uid, "failed", str(e)[:200])
                log.warning("Broadcast #%s send to %s failed: %s", bid, uid, e)

            await asyncio.sleep(SEND_DELAY)


async def _check_scheduled_broadcasts():
    """Раз в 60 сек проверяет запланированные рассылки (лёгкий SELECT)."""
    now_iso = datetime.now().isoformat()
    due = get_scheduled_broadcasts_due(now_iso)
    for b in due:
        bid = b["id"]
        ok, result = start_draft_broadcast(bid)
        if ok:
            log.info("Scheduled broadcast #%s started, %d recipients", bid, result)
        else:
            log.warning("Scheduled broadcast #%s failed: %s", bid, result)


# ==================== АВТОМАТИЧЕСКИЕ РАССЫЛКИ ====================

def format_auto_broadcast_text(template, user_id, org_id, request_id=None):
    """Подставляет переменные в текст сценария.

    Переменные:
      {name}         — имя клиента (clients.first_name, или «друг»)
      {service}      — название услуги (из указанной записи или последней done)
      {scheduled_at} — дата и время записи «YYYY-MM-DD HH:MM»
      {address}      — адрес филиала услуги
      {prep}         — подготовка к услуге (services.prep)
    """
    name = "друг"
    service = ""
    scheduled_at = ""
    address = ""
    prep = ""

    client = get_client(user_id)
    if client and client["first_name"]:
        first = (client["first_name"] or "").strip()
        if first:
            name = first

    req = None
    if request_id:
        req = get_request(request_id)
    else:
        conn = db()
        req = conn.execute(
            "SELECT id, service_id, service_name, scheduled_at, branch_id "
            "FROM history WHERE user_id=? AND org_id=? AND status='done' "
            "ORDER BY scheduled_at DESC LIMIT 1",
            (str(user_id), org_id),
        ).fetchone()
        conn.close()

    if req:
        service = req["service_name"] or ""
        scheduled_at = req["scheduled_at"] or ""
        if req["branch_id"]:
            br = get_branch(req["branch_id"])
            if br:
                address = br["address"] or ""
        if req["service_id"]:
            svc = get_service(req["service_id"])
            if svc:
                prep = svc["prep"] or ""

    # {last_visit} и {days_inactive} — из clients.last_visit_at,
    # fallback на дату последнего done-визита.
    last_visit = ""
    if client and client["last_visit_at"]:
        last_visit = client["last_visit_at"]
    elif req:
        last_visit = req["scheduled_at"] or ""

    days_inactive = "—"
    days_since_visit = "—"
    if last_visit:
        try:
            from datetime import datetime as _dt
            lv_date = _dt.strptime(last_visit[:10], "%Y-%m-%d")
            days = (_dt.now() - lv_date).days
            days_inactive = str(days)
            days_since_visit = str(days)
        except Exception:
            pass
    else:
        last_visit = "—"

    replacements = {
        "{name}": name,
        "{service}": service,
        "{scheduled_at}": scheduled_at,
        "{address}": address,
        "{prep}": prep,
        "{last_visit}": last_visit,
        "{days_inactive}": days_inactive,
        "{days_since_visit}": days_since_visit,
    }
    text = template or ""
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text


async def _check_auto_broadcasts():
    conn = db()
    autos = conn.execute(
        "SELECT id, org_id, type, text, image_id, delay_value "
        "FROM auto_broadcasts WHERE active=1"
    ).fetchall()
    conn.close()

    _org_settings_cache = {}

    def _is_quiet(oid):
        if oid not in _org_settings_cache:
            s = get_org_settings(oid) or {}
            _org_settings_cache[oid] = (
                int(s.get('quiet_hours_start', 22) or 0),
                int(s.get('quiet_hours_end', 9) or 0),
            )
        start_h, end_h = _org_settings_cache[oid]
        return _is_quiet_hours(now_for_org(oid), start_h, end_h)

    for a in autos:
        aid = a["id"]
        org_id = a["org_id"]
        atype = a["type"]
        text = a["text"]
        image_id = a["image_id"]
        delay_value = a["delay_value"]

        if _is_quiet(org_id):
            log.debug("Auto broadcast %s skipped: quiet hours (org=%s)", atype, org_id)
            continue

        now = now_for_org(org_id)
        today_date = now.date()

        if atype == "birthday":
            target_date = today_date + timedelta(days=delay_value)
            target_md = target_date.strftime("-%m-%d")

            conn = db()
            clients = conn.execute(
                "SELECT user_id, first_name FROM clients "
                "WHERE org_id=? AND birth_date LIKE ? "
                "  AND (marketing_opt_out IS NULL OR marketing_opt_out = 0)",
                (org_id, f"%{target_md}")
            ).fetchall()
            conn.close()

            for c in clients:
                uid = str(c["user_id"])
                fname = c["first_name"]
                if not uid or uid.startswith("phone:"):
                    continue
                if check_auto_log_birthday(aid, uid):
                    continue

                msg = text.replace("{name}", fname or "друг")
                try:
                    if image_id:
                        await _send_with_refresh(uid, msg, image_id,
                                                 buttons=UNSUB_BUTTONS, fmt="markdown",
                                                 org_id=org_id)
                    else:
                        await send_to_client_raw(uid, msg,
                                              buttons=UNSUB_BUTTONS, fmt="markdown")
                    log_auto_broadcast(aid, uid)
                    log.info("Auto birthday sent to %s", uid)
                    await asyncio.sleep(SEND_DELAY)
                except UserBlocked:
                    log.info("Auto birthday: user %s blocked bot", uid)
                except ChannelError as e:
                    log.info("Auto birthday: user %s has no channel (%s)", uid, e)
                except Exception as e:
                    log.warning("Auto birthday failed for %s: %s", uid, e)

        elif atype == "inactive":
            cutoff = (today_date - timedelta(days=delay_value)).strftime("%Y-%m-%d")
            now_str = now.strftime("%Y-%m-%d %H:%M")
            conn = db()
            clients = conn.execute(
                "SELECT c.user_id AS user_id, c.first_name AS first_name, "
                "       c.last_visit_at AS last_visit_at "
                "FROM clients c "
                "WHERE c.org_id=? AND (c.last_visit_at IS NULL OR c.last_visit_at < ?) "
                "AND (c.marketing_opt_out IS NULL OR c.marketing_opt_out = 0) "
                "AND NOT EXISTS ("
                "  SELECT 1 FROM history h "
                "  WHERE h.user_id = c.user_id AND h.org_id = ? "
                "  AND h.status IN ('pending', 'confirmed') "
                "  AND h.scheduled_at >= ?"
                ")",
                (org_id, cutoff, org_id, now_str)
            ).fetchall()
            conn.close()

            for c in clients:
                uid = str(c["user_id"])
                fname = c["first_name"]
                lvisit = c["last_visit_at"]
                if not uid or uid.startswith("phone:"):
                    continue
                if check_auto_log_inactive(aid, uid, lvisit):
                    continue

                msg = format_auto_broadcast_text(text, uid, org_id)
                try:
                    if image_id:
                        await _send_with_refresh(uid, msg, image_id,
                                                 buttons=UNSUB_BUTTONS, fmt="markdown",
                                                 org_id=org_id)
                    else:
                        await send_to_client_raw(uid, msg,
                                              buttons=UNSUB_BUTTONS, fmt="markdown")
                    log_auto_broadcast(aid, uid)
                    log.info("Auto inactive sent to %s", uid)
                    await asyncio.sleep(SEND_DELAY)
                except UserBlocked:
                    log.info("Auto inactive: user %s blocked bot", uid)
                except ChannelError as e:
                    log.info("Auto inactive: user %s has no channel (%s)", uid, e)
                except Exception as e:
                    log.warning("Auto inactive failed for %s: %s", uid, e)

        elif atype == "revisit_cycle":
            from datetime import datetime as _dt
            candidates = find_revisit_candidates(org_id)
            bot_username = (config.MINI_APP_BOT_USERNAME or "").strip()

            # Один клиент = максимум одно сообщение. Фильтруем cooldown,
            # берём самую просроченную услугу без недавней отправки.
            by_user = {}
            for c in candidates:
                uid = c["user_id"]
                if not uid or str(uid).startswith("phone:"):
                    continue
                if uid in by_user:
                    continue
                if check_auto_log_revisit(aid, uid, c["service_id"]):
                    continue
                by_user[uid] = c

            for uid, c in by_user.items():
                last_visit_str = (c["last_visit"] or "")[:16].replace("T", " ")
                days_since = c["days_since"] or 0
                svc_id = c["service_id"]
                req_id = c["last_request_id"]

                msg = format_auto_broadcast_text(
                    text, uid, org_id, request_id=req_id,
                )

                buttons = []
                if bot_username:
                    repeat_url = f"https://max.ru/{bot_username}?startapp=repeat_{req_id}"
                    buttons.append([{
                        "type": "link",
                        "text": "↩ Записаться снова",
                        "url": repeat_url,
                    }])
                buttons.extend(UNSUB_BUTTONS)

                try:
                    if image_id:
                        await _send_with_refresh(uid, msg, image_id,
                                                 buttons=buttons, fmt="markdown",
                                                 org_id=org_id)
                    else:
                        await send_to_client_raw(uid, msg,
                                              buttons=buttons, fmt="markdown")
                    log_auto_broadcast(aid, uid,
                                       event_ref=f"revisit:{svc_id}:{req_id}")
                    log.info(
                        "Auto revisit sent: uid=%s service=%s days=%s",
                        uid, svc_id, days_since,
                    )
                    await asyncio.sleep(SEND_DELAY)
                except UserBlocked:
                    log.info("Auto revisit: user %s blocked bot", uid)
                except ChannelError as e:
                    log.info("Auto revisit: user %s has no channel (%s)", uid, e)
                except Exception as e:
                    log.warning("Auto revisit failed for %s: %s", uid, e)

        elif atype == "after_visit":
            cutoff_time = (now - timedelta(hours=delay_value)).strftime("%Y-%m-%d %H:%M")
            lower_bound = (now - timedelta(hours=delay_value + 72)).strftime("%Y-%m-%d %H:%M")
            conn = db()
            visits = conn.execute(
                "SELECT h.id AS id, h.user_id AS user_id "
                "FROM history h "
                "LEFT JOIN clients c ON c.user_id = h.user_id AND c.org_id = h.org_id "
                "WHERE h.org_id=? AND h.status='done' "
                "AND h.scheduled_at < ? AND h.scheduled_at >= ? "
                "AND (c.marketing_opt_out IS NULL OR c.marketing_opt_out = 0)",
                (org_id, cutoff_time, lower_bound)
            ).fetchall()
            conn.close()

            bot_username = (config.MINI_APP_BOT_USERNAME or "").strip()

            for v in visits:
                v_id = v["id"]
                uid = str(v["user_id"])
                if not uid or uid.startswith("phone:"):
                    continue
                if check_auto_log_after_visit(aid, v_id):
                    continue

                msg = format_auto_broadcast_text(text, uid, org_id, request_id=v_id)

                buttons = []
                if bot_username:
                    repeat_url = f"https://max.ru/{bot_username}?startapp=repeat_{v_id}"
                    buttons.append([{
                        "type": "link",
                        "text": "↩ Записаться снова",
                        "url": repeat_url,
                    }])
                buttons.extend(UNSUB_BUTTONS)

                try:
                    if image_id:
                        await _send_with_refresh(uid, msg, image_id,
                                                 buttons=buttons, fmt="markdown",
                                                 org_id=org_id)
                    else:
                        await send_to_client_raw(uid, msg,
                                              buttons=buttons, fmt="markdown")
                    log_auto_broadcast(aid, uid, event_ref=str(v_id))
                    log.info("Auto after_visit sent to %s", uid)
                    await asyncio.sleep(SEND_DELAY)
                except UserBlocked:
                    log.info("Auto after_visit: user %s blocked bot", uid)
                except ChannelError as e:
                    log.info("Auto after_visit: user %s has no channel (%s)", uid, e)
                except Exception as e:
                    log.warning("Auto after_visit failed for %s: %s", uid, e)


async def run_broadcast_worker():
    log.info("Broadcast worker started")
    await asyncio.sleep(60)
    last_scheduled_check = 0.0
    last_auto_check_ts = 0.0
    AUTO_CHECK_INTERVAL = 300  # 5 минут

    while True:
        try:
            await _check_manual_broadcasts()
        except Exception as e:
            log.error("Manual broadcast cycle error: %s", e)

        # Раз в 60 секунд проверяем запланированные
        now_ts = asyncio.get_event_loop().time()
        if now_ts - last_scheduled_check >= SCHEDULED_CHECK_INTERVAL:
            try:
                await _check_scheduled_broadcasts()
            except Exception as e:
                log.error("Scheduled broadcast cycle error: %s", e)
            last_scheduled_check = now_ts

        now_ts2 = asyncio.get_event_loop().time()
        if now_ts2 - last_auto_check_ts >= AUTO_CHECK_INTERVAL:
            try:
                await _check_auto_broadcasts()
            except Exception as e:
                log.error("Auto broadcast cycle error: %s", e)
            last_auto_check_ts = now_ts2

        await asyncio.sleep(10)