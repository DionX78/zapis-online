"""E4.5: склейка профилей MAX и VK по общему телефону (вариант Б).

Два реальных клиента с одинаковым телефоном — могут быть и одним человеком,
и членами семьи. Объединяем только с подтверждением из обоих каналов.
Запрос создаётся, когда клиент указывает телефон при записи.
"""
import logging
import re as _re
from datetime import datetime, timedelta

from storage.db import db, log_audit

log = logging.getLogger(__name__)

MERGE_TTL_HOURS = 48
DECLINE_COOLDOWN_DAYS = 30


def _canon(phone):
    digits = _re.sub(r"\D", "", phone or "")
    return digits[-10:] if len(digits) >= 10 else digits


def _ensure_table(conn):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS pending_merges ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "org_id INTEGER, "
        "keep_user_id TEXT NOT NULL, "
        "gone_user_id TEXT NOT NULL, "
        "status TEXT DEFAULT 'pending', "
        "confirmed_keep INTEGER DEFAULT 0, "
        "confirmed_gone INTEGER DEFAULT 0, "
        "created_at TEXT, expires_at TEXT, updated_at TEXT)"
    )
    conn.commit()


def find_other_clients_by_phone(org_id, user_id, phone):
    """Реальные клиенты (не phone:...) с тем же телефоном, кроме самого себя."""
    canon = _canon(phone)
    if not canon:
        return []
    conn = db()
    rows = conn.execute(
        "SELECT user_id, phone FROM clients "
        "WHERE (org_id=? OR org_id IS NULL) AND phone IS NOT NULL AND phone != ''",
        (org_id,),
    ).fetchall()
    conn.close()
    me = str(user_id)
    out = []
    for r in rows:
        uid = str(r["user_id"])
        if uid == me or uid.startswith("phone:"):
            continue
        if _canon(r["phone"]) == canon:
            out.append(uid)
    return out


def create_pending_merges(org_id, user_id, phone):
    """Заявки на склейку с каждым реальным клиентом с тем же телефоном.

    keep — профиль с более ранней датой создания. Если по паре уже есть
    живая pending-заявка или свежий отказ — новую не создаём.
    Возвращает [(merge_id, keep_uid, gone_uid)].
    """
    others = find_other_clients_by_phone(org_id, user_id, phone)
    if not others:
        return []
    conn = db()
    _ensure_table(conn)
    now = datetime.now()
    now_iso = now.isoformat()
    created = {}
    for uid in [str(user_id)] + others:
        row = conn.execute(
            "SELECT created_at FROM clients WHERE user_id=?", (uid,)
        ).fetchone()
        created[uid] = (row["created_at"] if row and row["created_at"] else now_iso)
    result = []
    for other in others:
        keep, gone = (
            (str(user_id), other)
            if created[str(user_id)] <= created[other]
            else (other, str(user_id))
        )
        existing = conn.execute(
            "SELECT id, status, expires_at, updated_at FROM pending_merges WHERE org_id=? AND "
            "((keep_user_id=? AND gone_user_id=?) OR (keep_user_id=? AND gone_user_id=?))",
            (org_id, keep, gone, gone, keep),
        ).fetchone()
        if existing:
            if existing["status"] == "merged":
                continue
            if existing["status"] == "declined":
                try:
                    declined_at = datetime.fromisoformat(existing["updated_at"])
                except (TypeError, ValueError):
                    declined_at = None
                if declined_at and (now - declined_at).days < DECLINE_COOLDOWN_DAYS:
                    continue
                conn.execute(
                    "UPDATE pending_merges SET status='pending', confirmed_keep=0, "
                    "confirmed_gone=0, expires_at=?, updated_at=? WHERE id=?",
                    ((now + timedelta(hours=MERGE_TTL_HOURS)).isoformat(),
                     now_iso, existing["id"]),
                )
                result.append((existing["id"], keep, gone))
                continue
            if existing["status"] == "pending":
                exp = existing["expires_at"]
                live = False
                if exp:
                    try:
                        live = datetime.fromisoformat(exp) > now
                    except ValueError:
                        live = False
                if live:
                    continue
                conn.execute(
                    "UPDATE pending_merges SET confirmed_keep=0, confirmed_gone=0, "
                    "expires_at=?, updated_at=? WHERE id=?",
                    ((now + timedelta(hours=MERGE_TTL_HOURS)).isoformat(),
                     now_iso, existing["id"]),
                )
                result.append((existing["id"], keep, gone))
                continue
        cur = conn.execute(
            "INSERT INTO pending_merges (org_id, keep_user_id, gone_user_id, status, "
            "created_at, expires_at, updated_at) VALUES (?, ?, ?, 'pending', ?, ?, ?)",
            (org_id, keep, gone, now_iso,
             (now + timedelta(hours=MERGE_TTL_HOURS)).isoformat(), now_iso),
        )
        result.append((cur.lastrowid, keep, gone))
    conn.commit()
    conn.close()
    return result


def get_pending_merge(merge_id):
    conn = db()
    row = conn.execute("SELECT * FROM pending_merges WHERE id=?", (merge_id,)).fetchone()
    conn.close()
    return row


def confirm_merge(merge_id, which):
    conn = db()
    conn.execute(
        "UPDATE pending_merges SET confirmed_" + which + "=1, updated_at=? WHERE id=?",
        (datetime.now().isoformat(), merge_id),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM pending_merges WHERE id=?", (merge_id,)).fetchone()
    conn.close()
    return row


def set_merge_status(merge_id, status):
    conn = db()
    conn.execute(
        "UPDATE pending_merges SET status=?, updated_at=? WHERE id=?",
        (status, datetime.now().isoformat(), merge_id),
    )
    conn.commit()
    conn.close()


def finalize_merge(keep_uid, gone_uid):
    """Склейка: сначала дозаполняем пустые поля keep данными gone,
    затем переносим историю и паспорта каналов через merge_client_into."""
    conn = db()
    k = conn.execute("SELECT * FROM clients WHERE user_id=?", (keep_uid,)).fetchone()
    g = conn.execute("SELECT * FROM clients WHERE user_id=?", (gone_uid,)).fetchone()
    if not k or not g:
        conn.close()
        return False
    fields, vals = [], []
    for col in ("first_name", "last_name", "middle_name", "phone", "gender", "birth_date"):
        if not (k[col] or "") and (g[col] or ""):
            fields.append(col + "=?")
            vals.append(g[col])
    if fields:
        fields.append("updated_at=?")
        vals.append(datetime.now().isoformat())
        vals.append(keep_uid)
        conn.execute("UPDATE clients SET " + ", ".join(fields) + " WHERE user_id=?", vals)
    conn.commit()
    conn.close()
    from storage.db import merge_client_into
    return merge_client_into(gone_uid, keep_uid)


def _merge_buttons(merge_id):
    return [[
        {"type": "callback", "text": "✅ Объединить", "payload": f"mg:yes:{merge_id}"},
        {"type": "callback", "text": "❌ Не объединять", "payload": f"mg:no:{merge_id}"},
    ]]


async def _send_merge_request(uid, text, merge_id):
    status, err = await send_to_client(uid, text, buttons=_merge_buttons(merge_id))
    if status == "sent":
        return
    if status == "blocked":
        log.info("merge request to %s: client blocked the bot", uid)
        return
    log.warning("merge buttons failed for %s: %s — отправляю без кнопок", uid, err)
    await send_to_client(
        uid,
        text + "\n\n⚠️ Кнопки не отобразились — если профили нужно объединить, "
        "ответьте в этот чат, администратор поможет.",
    )


async def _send_simple(uid, text):
    from core.messaging import send_to_client_raw
    await send_to_client_raw(uid, text)


async def maybe_queue_merge(org_id, user_id, phone):
    """Вызывается после успешной записи: ищет профили с тем же телефоном
    в других каналах и рассылает обоим запрос на объединение."""
    merges = create_pending_merges(org_id, user_id, phone)
    for merge_id, keep, gone in merges:
        text = (
            "🔗 **Объединение профилей**\n\n"
            f"Вы указали телефон {phone}. По этому номеру у нас уже есть "
            "ещё один профиль в другой системе (MAX или ВКонтакте).\n\n"
            "Это вы? Можем объединить записи в один профиль — история визитов, "
            "напоминания и уведомления будут приходить в оба мессенджера.\n\n"
            "Если это не вы (например, телефон общий в семье) — выберите «Нет», "
            "профили останутся раздельными."
        )
        for target in (keep, gone):
            try:
                await _send_merge_request(target, text, merge_id)
            except NotImplementedError:
                raise
            except Exception as e:
                log.warning("merge request send failed to %s: %s", target, e)
    return merges


async def handle_response(merge_id, uid, yes):
    row = get_pending_merge(merge_id)
    if not row:
        return "not_found"
    now = datetime.now()
    if row["status"] != "pending":
        if row["status"] == "merged":
            await _send_simple(uid, "ℹ️ Эти профили уже объединены.")
        return row["status"]
    try:
        exp = datetime.fromisoformat(row["expires_at"])
        if exp < now:
            set_merge_status(merge_id, "expired")
            await _send_simple(uid, "⏳ Время на подтверждение истекло. Запишитесь заново — запрос придёт снова.")
            return "expired"
    except (TypeError, ValueError):
        pass
    uid_s = str(uid)
    if uid_s not in (row["keep_user_id"], row["gone_user_id"]):
        return "wrong_user"
    which = "keep" if uid_s == row["keep_user_id"] else "gone"
    if not yes:
        set_merge_status(merge_id, "declined")
        await _send_simple(uid_s, "👍 Поняли, профили оставили раздельными. Если это ошибка — напишите администратору клиники.")
        return "declined"
    row2 = confirm_merge(merge_id, which)
    if row2["confirmed_keep"] and row2["confirmed_gone"]:
        set_merge_status(merge_id, "merged")
        ok = finalize_merge(row2["keep_user_id"], row2["gone_user_id"])
        if ok:
            await _send_simple(
                row2["keep_user_id"],
                "✅ **Профили объединены!** Все записи и история — в одном профиле, "
                "уведомления будут приходить во все подключённые мессенджеры.")
            try:
                log_audit(org_id=row2["org_id"], user_id=uid_s, action="clients_merged",
                          entity_type="client", entity_id=str(row2["keep_user_id"]),
                          payload={"gone": row2["gone_user_id"], "merge_id": merge_id})
            except Exception:
                pass
        return "merged"
    await _send_simple(uid_s, "✅ Принято! Как только подтвердите и во втором мессенджере — профили объединятся.")
    return "waited"
