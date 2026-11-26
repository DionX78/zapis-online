import hashlib
import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, date as _date, timedelta
from zoneinfo import ZoneInfo

import config

log = logging.getLogger(__name__)

DB_PATH = config.DB_PATH


def db():
    """Соединение с БД: ждёт блокировку до 30 с, WAL, row_factory.

    Возвращает коннект, который нужно явно закрыть через conn.close().
    Для новых функций используйте db_ctx() — гарантирует закрытие
    даже при исключении.
    """
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def db_ctx():
    """Контекстный менеджер для соединения с БД.

    Гарантирует закрытие даже при исключении внутри блока.
    Не делает commit автоматически — коммит должен быть явным
    (в отличие от селектов, для insert/update/delete).

    Использование:
        with db_ctx() as conn:
            conn.execute("UPDATE ...")
            conn.commit()

        with db_ctx() as conn:
            row = conn.execute("SELECT ...").fetchone()
    """
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        try:
            conn.close()
        except Exception:
            pass


DEFAULT_ORG_SETTINGS = {
    "confirmation_mode": "manual",
    "client_confirm_delay_min": 60,
    "client_confirm_timeout_min": 120,
    "reminder_24h": True,
    "reminder_2h": True,
    "work_hours": {
        "mon_fri": {"start": "09:00", "end": "18:00"},
        "sat":     {"start": "09:00", "end": "14:00"},
        "sun":     None,
    },
    "slot_step_min": 30,
    "autocomplete_after_hours": 3,
    "pending_timeout_min": 0,
        "evening_summary_hour": config.EVENING_SUMMARY_DEFAULT_HOUR,
    "map_provider": "both",
    # E3: куда отправлять, если у клиента «паспорта» в нескольких каналах
    # (или канал не определён). Пока реально доступен только max.
    "channel_default": "max",
    # Дублировать ли уведомление во все каналы клиента (а не только в основной)
    "channel_duplicate": False,
    "max_bookings_per_day": 2,
    "schedule_horizon_days": 60,
    "auto_manual_no_show_threshold": 0,
    "client_at_risk_days": 30,
    "client_inactive_days": 90,
    # Тихие часы: не отправлять напоминания / client-подтверждение ночью.
    # «Последний шанс» (за час до приёма) работает всегда.
    "quiet_hours_start": 22,
    "quiet_hours_end": 9,
    # Лист ожидания / backfill (волна 2)
    "slot_backfill_enabled": True,
    "slot_backfill_delay_minutes": 30,          # от освобождения слота до первых уведомлений (лист)
    "slot_backfill_waitlist_wait_minutes": 30,  # сколько ждём реакции листа перед backfill
    "slot_backfill_batch_minutes": 15,          # сколько копить pending-офферы, чтобы отправить пачкой
    "slot_backfill_sent_ttl_hours": 24,         # сколько «живёт» неотвеченный sent-оффер, пока заявка не получит новые
    "slot_backfill_min_gap_hours": 24,          # мин. отрыв освободившегося слота от текущей записи
    "slot_backfill_max_candidates": 5,          # скольким клиентам отправить предложение
    "slot_backfill_cooldown_hours": 24,         # не дёргать одного клиента чаще
    # Отзывы
    "review_request_enabled": False,
    "review_request_delay_hours": 2,
    "review_positive_threshold": 4,
    "review_yandex_url": "",
    "review_2gis_url": "",
    # timezone хранится отдельной колонкой, но мержится сюда при чтении
}


# ==================== TZ helpers ====================

_tz_cache: dict[int, str] = {}
_tz_obj_cache: dict[str, ZoneInfo] = {}


def _tz_obj(tz_name: str) -> ZoneInfo:
    if tz_name in _tz_obj_cache:
        return _tz_obj_cache[tz_name]
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo(config.DEFAULT_TIMEZONE)
    _tz_obj_cache[tz_name] = tz
    return tz


def get_org_timezone(org_id: int) -> str:
    if org_id in _tz_cache:
        return _tz_cache[org_id]
    conn = db()
    row = conn.execute("SELECT timezone FROM organizations WHERE id=?", (org_id,)).fetchone()
    conn.close()
    tz = None
    if row and row["timezone"]:
        tz = row["timezone"]
    if not tz:
        tz = config.DEFAULT_TIMEZONE
    _tz_cache[org_id] = tz
    return tz


def set_org_timezone(org_id: int, tz_name: str):
    conn = db()
    conn.execute("UPDATE organizations SET timezone=? WHERE id=?", (tz_name, org_id))
    conn.commit()
    conn.close()
    _tz_cache.pop(org_id, None)


def now_for_org(org_id: int) -> datetime:
    """Наивный datetime в локальной таймзоне организации.
    Используется для всех сравнений с scheduled_at/date/time."""
    tz_name = get_org_timezone(org_id)
    return datetime.now(_tz_obj(tz_name)).replace(tzinfo=None)


def today_for_org(org_id: int) -> str:
    return now_for_org(org_id).strftime("%Y-%m-%d")


# ==================== schema ====================

def _ensure_column(conn, table, column, ddl):
    cur = conn.execute(f"PRAGMA table_info({table})")
    cols = {row["name"] for row in cur.fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def init_db():
    conn = db()
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS organizations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        settings TEXT,
        timezone TEXT DEFAULT 'Europe/Moscow',
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS admins (
        user_id TEXT PRIMARY KEY,
        first_name TEXT,
        org_id INTEGER,
        added_by TEXT,
        added_at TEXT
    );

    CREATE TABLE IF NOT EXISTS pending_admins (
        user_id TEXT PRIMARY KEY,
        first_name TEXT,
        username TEXT,
        requested_at TEXT
    );

       CREATE TABLE IF NOT EXISTS service_categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        org_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        sort_order INTEGER DEFAULT 100,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS services (
        id TEXT PRIMARY KEY,
        org_id INTEGER,
        name TEXT NOT NULL,
        price INTEGER,
        prep TEXT,
        duration_min INTEGER DEFAULT 30,
        active INTEGER DEFAULT 1,
        category_id INTEGER
    );

    CREATE TABLE IF NOT EXISTS requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        org_id INTEGER,
        user_id TEXT,
        service_id TEXT,
        service_name TEXT,
        preferred_time TEXT,
        phone TEXT,
        status TEXT DEFAULT 'draft',
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS user_state (
        user_id TEXT PRIMARY KEY,
        state TEXT,
        context TEXT,
        updated_at TEXT
    );

    CREATE TABLE IF NOT EXISTS history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        org_id INTEGER,
        user_id TEXT,
        service_name TEXT,
        scheduled_at TEXT,
        phone TEXT,
        status TEXT DEFAULT 'pending',
        address TEXT,
        doctor TEXT,
        branch_id INTEGER,
        doctor_id INTEGER,
        slot_id INTEGER,
        service_id TEXT,
        confirmed_by TEXT,
        confirmed_at TEXT,
        reminder_24_sent_at TEXT,
        reminder_2_sent_at TEXT,
        reminder_24_attempts INTEGER DEFAULT 0,
        reminder_2_attempts INTEGER DEFAULT 0,
        client_asked_at TEXT,
        client_ask_attempts INTEGER DEFAULT 0,
        client_answer TEXT,
        actual_amount INTEGER,
        payment_method TEXT,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS branches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        org_id INTEGER NOT NULL,
        name TEXT,
        address TEXT,
        phone TEXT,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS doctors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        branch_id INTEGER NOT NULL,
        name TEXT,
        specialty TEXT,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS slots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        org_id INTEGER NOT NULL,
        branch_id INTEGER,
        doctor_id INTEGER,
        date TEXT NOT NULL,
        time TEXT NOT NULL,
        is_booked INTEGER DEFAULT 0,
        request_id INTEGER,
        service_id TEXT,
        UNIQUE(branch_id, doctor_id, date, time)
    );

    CREATE TABLE IF NOT EXISTS clients (
        user_id TEXT PRIMARY KEY,
        org_id INTEGER,
        first_name TEXT,
        last_name TEXT,
        middle_name TEXT,
        phone TEXT,
        gender TEXT,
        birth_date TEXT,
        last_visit_at TEXT,
        marketing_opt_out INTEGER DEFAULT 0,
        marketing_opt_out_at TEXT,
        created_at TEXT,
        updated_at TEXT
    );

    CREATE TABLE IF NOT EXISTS broadcasts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        org_id INTEGER NOT NULL,
        text TEXT NOT NULL,
        segment_json TEXT,
        status TEXT DEFAULT 'draft',
        total_recipients INTEGER DEFAULT 0,
        sent_count INTEGER DEFAULT 0,
        failed_count INTEGER DEFAULT 0,
        image_token TEXT,
        created_by TEXT,
        created_at TEXT,
        started_at TEXT,
        finished_at TEXT
    );

    CREATE TABLE IF NOT EXISTS broadcast_sends (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        broadcast_id INTEGER NOT NULL,
        user_id TEXT NOT NULL,
        status TEXT DEFAULT 'pending',
        error TEXT,
        sent_at TEXT,
        UNIQUE(broadcast_id, user_id)
    );

    CREATE TABLE IF NOT EXISTS uploaded_images (
        token TEXT PRIMARY KEY,
        org_id INTEGER NOT NULL,
        uploaded_by TEXT,
        uploaded_at TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_slots_org_date ON slots(org_id, date);
    CREATE INDEX IF NOT EXISTS idx_slots_booked ON slots(is_booked);
    CREATE INDEX IF NOT EXISTS idx_history_user ON history(user_id);
    CREATE INDEX IF NOT EXISTS idx_history_org_scheduled ON history(org_id, scheduled_at);
    CREATE INDEX IF NOT EXISTS idx_history_org_status ON history(org_id, status);
    CREATE INDEX IF NOT EXISTS idx_clients_org ON clients(org_id);

    CREATE TABLE IF NOT EXISTS auto_broadcasts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        org_id INTEGER NOT NULL,
        type TEXT NOT NULL,
        text TEXT NOT NULL,
        image_token TEXT,
        delay_value INTEGER NOT NULL,
        active INTEGER DEFAULT 1,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS auto_broadcast_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        auto_id INTEGER NOT NULL,
        user_id TEXT NOT NULL,
        event_ref TEXT,
        sent_at TEXT
    );

    CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        org_id INTEGER,
        user_id TEXT,
        action TEXT NOT NULL,
        entity_type TEXT,
        entity_id TEXT,
        payload TEXT,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS blocked_users (
        user_id TEXT PRIMARY KEY,
        org_id INTEGER,
        phone TEXT,
        reason TEXT,
        blocked_by TEXT,
        blocked_at TEXT
    );

    CREATE TABLE IF NOT EXISTS schedules (
        doctor_id INTEGER NOT NULL,
        weekday INTEGER NOT NULL,
        start_time TEXT NOT NULL,
        end_time TEXT NOT NULL,
        break_start TEXT,
        break_end TEXT,
        updated_at TEXT,
        PRIMARY KEY (doctor_id, weekday)
    );

    CREATE TABLE IF NOT EXISTS schedule_shifts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        doctor_id INTEGER NOT NULL,
        branch_id INTEGER NOT NULL,
        weekday INTEGER NOT NULL,
        start_time TEXT NOT NULL,
        end_time TEXT NOT NULL,
        break_start TEXT,
        break_end TEXT,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS schedule_exceptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        doctor_id INTEGER NOT NULL,
        date_from TEXT NOT NULL,
        date_to TEXT NOT NULL,
        reason TEXT,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS doctor_services (
        doctor_id INTEGER NOT NULL,
        service_id TEXT NOT NULL,
        PRIMARY KEY (doctor_id, service_id)
    );

    CREATE INDEX IF NOT EXISTS idx_doctor_services_doctor ON doctor_services(doctor_id);
    CREATE INDEX IF NOT EXISTS idx_doctor_services_service ON doctor_services(service_id);
    CREATE INDEX IF NOT EXISTS idx_schedules_doctor ON schedules(doctor_id);
    CREATE INDEX IF NOT EXISTS idx_schedule_shifts_doctor ON schedule_shifts(doctor_id);
    CREATE INDEX IF NOT EXISTS idx_schedule_shifts_doctor_day ON schedule_shifts(doctor_id, weekday);
    CREATE INDEX IF NOT EXISTS idx_schedule_exceptions_doctor ON schedule_exceptions(doctor_id);
    CREATE INDEX IF NOT EXISTS idx_audit_org_created ON audit_log(org_id, created_at);

    """)

    _ensure_column(conn, "history", "reminder_24_attempts", "INTEGER DEFAULT 0")
    _ensure_column(conn, "history", "reminder_2_attempts", "INTEGER DEFAULT 0")
    _ensure_column(conn, "history", "client_ask_attempts", "INTEGER DEFAULT 0")
    _ensure_column(conn, "history", "actual_amount", "INTEGER")
    _ensure_column(conn, "history", "payment_method", "TEXT")
    _ensure_column(conn, "clients", "marketing_opt_out", "INTEGER DEFAULT 0")
    _ensure_column(conn, "clients", "marketing_opt_out_at", "TEXT")
    _ensure_column(conn, "clients", "favorite_doctor_id", "INTEGER")
    _ensure_column(conn, "clients", "consent_152fz", "INTEGER DEFAULT 0")
    _ensure_column(conn, "clients", "consent_given_at", "TEXT")
    _ensure_column(conn, "organizations", "timezone", "TEXT DEFAULT 'Europe/Moscow'")
    _ensure_column(conn, "services", "category_id", "INTEGER")
    _ensure_column(conn, "slots", "auto_created", "INTEGER DEFAULT 0")
    _ensure_column(conn, "doctors", "schedule_paused", "INTEGER DEFAULT 0")
    _ensure_column(conn, "doctors", "schedule_stop_date", "TEXT")
    _ensure_column(conn, "branches", "is_primary", "INTEGER DEFAULT 0")
    _ensure_column(conn, "history", "done_auto", "INTEGER DEFAULT 0")
    _ensure_column(conn, "services", "buffer_min", "INTEGER DEFAULT 0")
    _ensure_column(conn, "services", "revisit_interval_days", "INTEGER DEFAULT 0")
    _ensure_column(conn, "history", "review_requested_at", "TEXT")

    conn.executescript("""
    CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        org_id INTEGER NOT NULL,
        user_id TEXT NOT NULL,
        request_id INTEGER NOT NULL,
        doctor_id INTEGER,
        service_id TEXT,
        rating INTEGER NOT NULL,
        comment TEXT,
        created_at TEXT NOT NULL,
        admin_notified_at TEXT,
        public_link_sent_at TEXT,
        UNIQUE(request_id)
    );
    CREATE INDEX IF NOT EXISTS idx_reviews_org_created
        ON reviews(org_id, created_at);
    CREATE INDEX IF NOT EXISTS idx_reviews_user
        ON reviews(user_id, org_id);
    """)
    _ensure_column(conn, "history", "slots_count", "INTEGER DEFAULT 1")
    _ensure_column(conn, "history", "slot_ids", "TEXT")
    _ensure_column(conn, "clients", "notes", "TEXT")
    _ensure_column(conn, "clients", "tags", "TEXT")
    _ensure_column(conn, "clients", "no_show_count", "INTEGER DEFAULT 0")
    _ensure_column(conn, "clients", "no_show_last_at", "TEXT")
    _ensure_column(conn, "clients", "photo_upload_id", "INTEGER")
    _ensure_column(conn, "doctors", "photo_upload_id", "INTEGER")
    _ensure_column(conn, "doctors", "education", "TEXT")
    _ensure_column(conn, "doctors", "courses", "TEXT")
    _ensure_column(conn, "doctors", "about", "TEXT")
    _ensure_column(conn, "broadcasts", "image_id", "INTEGER")
    _ensure_column(conn, "broadcasts", "scheduled_at", "TEXT")
    _ensure_column(conn, "auto_broadcasts", "image_id", "INTEGER")

    # Миграция uploaded_images: token PRIMARY KEY → id AUTOINCREMENT + file_path.
    cur_cols = conn.execute("PRAGMA table_info(uploaded_images)")
    img_cols = {row[1] for row in cur_cols.fetchall()}
    if "file_path" not in img_cols:
        conn.executescript("""
        CREATE TABLE uploaded_images_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token TEXT,
            public_token TEXT,
            file_path TEXT,
            mime_type TEXT,
            original_filename TEXT,
            file_size INTEGER,
            org_id INTEGER NOT NULL,
            uploaded_by TEXT,
            uploaded_at TEXT
        );
        INSERT INTO uploaded_images_new (token, org_id, uploaded_by, uploaded_at)
            SELECT token, org_id, uploaded_by, uploaded_at FROM uploaded_images;
        DROP TABLE uploaded_images;
        ALTER TABLE uploaded_images_new RENAME TO uploaded_images;
        """)

    # Для уже существующих записей: public_token генерируем из id
    _ensure_column(conn, "uploaded_images", "public_token", "TEXT")
    conn.execute(
        "UPDATE uploaded_images SET public_token = 'legacy_' || id "
        "WHERE public_token IS NULL"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_uploaded_images_public_token "
        "ON uploaded_images(public_token)"
    )

    # Перенос broadcasts.image_token → image_id (одноразовый, идемпотентный)
    conn.execute(
        "UPDATE broadcasts SET image_id = ("
        "  SELECT id FROM uploaded_images WHERE uploaded_images.token = broadcasts.image_token"
        ") WHERE image_id IS NULL AND image_token IS NOT NULL AND image_token != ''"
    )
    conn.execute(
        "UPDATE auto_broadcasts SET image_id = ("
        "  SELECT id FROM uploaded_images WHERE uploaded_images.token = auto_broadcasts.image_token"
        ") WHERE image_id IS NULL AND image_token IS NOT NULL AND image_token != ''"
    )

    # Перенос legacy-флага: если был schedule_paused=1, трактуем как «остановить с сегодня».
    # Условие schedule_stop_date IS NULL — чтобы не перезаписывать при каждом рестарте.
    conn.execute(
        "UPDATE doctors SET schedule_stop_date=date('now', 'localtime') "
        "WHERE schedule_paused=1 AND schedule_stop_date IS NULL"
    )

    # Заполнить timezone у существующих организаций, где NULL
    conn.execute(
        "UPDATE organizations SET timezone=? WHERE timezone IS NULL OR timezone=''",
        (config.DEFAULT_TIMEZONE,),
    )

    # Основной филиал: если ни один не помечен — ставим первый в каждой org
    conn.execute(
        "UPDATE branches SET is_primary=1 "
        "WHERE id IN (SELECT MIN(id) FROM branches GROUP BY org_id) "
        "AND org_id NOT IN (SELECT org_id FROM branches WHERE is_primary=1)"
    )

    # Слоты без филиала: свободные удаляем, забронированные привязываем
    conn.execute("DELETE FROM slots WHERE branch_id IS NULL AND is_booked = 0")
    conn.execute(
        "UPDATE slots SET branch_id = "
        "(SELECT d.branch_id FROM doctors d WHERE d.id = slots.doctor_id) "
        "WHERE branch_id IS NULL AND doctor_id IS NOT NULL"
    )
    conn.execute(
        "UPDATE slots SET branch_id = "
        "(SELECT b.id FROM branches b WHERE b.org_id = slots.org_id "
        " ORDER BY b.is_primary DESC, b.id LIMIT 1) "
        "WHERE branch_id IS NULL"
    )

    # Дедупликация слотов: один врач не может иметь два слота на одно время
    # в разных филиалах. Удаляем свободные auto-дубли, оставляя минимальный id.
    # Booked и manual-дубли не трогаем — админ сам разберётся через UI.
    conn.execute(
        "DELETE FROM slots "
        "WHERE id NOT IN ("
        "  SELECT MIN(id) FROM slots "
        "  WHERE doctor_id IS NOT NULL "
        "  GROUP BY doctor_id, date, time"
        ") "
        "AND doctor_id IS NOT NULL "
        "AND auto_created = 1 "
        "AND is_booked = 0"
    )

    # Одноразовый перенос старого графика в schedule_shifts (branch_id из doctors.branch_id).
    # Идемпотентно: повторный прогон не создаст дублей.
    conn.execute(
        "INSERT INTO schedule_shifts "
        "(doctor_id, branch_id, weekday, start_time, end_time, break_start, break_end, created_at) "
        "SELECT s.doctor_id, d.branch_id, s.weekday, s.start_time, s.end_time, "
        "       s.break_start, s.break_end, COALESCE(s.updated_at, datetime('now')) "
        "FROM schedules s "
        "JOIN doctors d ON d.id = s.doctor_id "
        "WHERE NOT EXISTS ("
        "  SELECT 1 FROM schedule_shifts ss "
        "  WHERE ss.doctor_id = s.doctor_id AND ss.branch_id = d.branch_id "
        "    AND ss.weekday = s.weekday"
        ")"
    )

    # --- Лист ожидания + backfill (волна 2) ---
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS waitlist (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        org_id INTEGER NOT NULL,
        user_id TEXT NOT NULL,
        service_id TEXT NOT NULL,
        doctor_id INTEGER,
        branch_id INTEGER,
        date_from TEXT NOT NULL,
        date_to TEXT NOT NULL,
        preferred_time TEXT,
        status TEXT NOT NULL DEFAULT 'active',
        notes TEXT,
        created_by TEXT,
        created_at TEXT NOT NULL,
        notified_at TEXT,
        notified_count INTEGER NOT NULL DEFAULT 0,
        last_notified_slot_id INTEGER,
        fulfilled_request_id INTEGER,
        fulfilled_at TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_waitlist_org_status
        ON waitlist (org_id, status, service_id);
    CREATE INDEX IF NOT EXISTS idx_waitlist_user_status
        ON waitlist (user_id, status);

    CREATE TABLE IF NOT EXISTS slot_offers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        org_id INTEGER NOT NULL,
        slot_id INTEGER NOT NULL,
        user_id TEXT NOT NULL,
        original_request_id INTEGER,
        kind TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'sent',
        sent_at TEXT NOT NULL,
        responded_at TEXT,
        error TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_slot_offers_slot
        ON slot_offers (slot_id, status);
    CREATE INDEX IF NOT EXISTS idx_slot_offers_user
        ON slot_offers (user_id, kind, sent_at);
    """)

    # waitlist.service_id → NULLABLE (поддержка «только специалист»)
    cur = conn.execute("PRAGMA table_info(waitlist)")
    wl_cols = {row["name"]: row for row in cur.fetchall()}
    if wl_cols.get("service_id") and wl_cols["service_id"]["notnull"]:
        conn.executescript("""
        CREATE TABLE waitlist_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id INTEGER NOT NULL,
            user_id TEXT NOT NULL,
            service_id TEXT,
            doctor_id INTEGER,
            branch_id INTEGER,
            date_from TEXT NOT NULL,
            date_to TEXT NOT NULL,
            preferred_time TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            notes TEXT,
            created_by TEXT,
            created_at TEXT NOT NULL,
            notified_at TEXT,
            notified_count INTEGER NOT NULL DEFAULT 0,
            last_notified_slot_id INTEGER,
            fulfilled_request_id INTEGER,
            fulfilled_at TEXT
        );
        INSERT INTO waitlist_new SELECT * FROM waitlist;
        DROP TABLE waitlist;
        ALTER TABLE waitlist_new RENAME TO waitlist;
        CREATE INDEX IF NOT EXISTS idx_waitlist_org_status
            ON waitlist (org_id, status, service_id);
        CREATE INDEX IF NOT EXISTS idx_waitlist_user_status
            ON waitlist (user_id, status);
        """)

    # slot_offers.waitlist_id — для обратной связи «оффер из какой заявки»
    try:
        conn.execute("ALTER TABLE slot_offers ADD COLUMN waitlist_id INTEGER")
    except sqlite3.OperationalError:
        pass

    # slots.released_at — для воркера backfill
    try:
        conn.execute("ALTER TABLE slots ADD COLUMN released_at TEXT")
    except sqlite3.OperationalError:
        pass  # колонка уже есть

    # Триггеры: released_at обновляется на уровне БД при любом UPDATE slots.request_id.
    # Не нужно править release_slot / book_slot / create_booking / cancel_stale_pending —
    # все они работают через одну и ту же колонку request_id.
    conn.executescript("""
    CREATE TRIGGER IF NOT EXISTS trg_slots_released
    AFTER UPDATE OF request_id ON slots
    WHEN NEW.request_id IS NULL AND OLD.request_id IS NOT NULL
    BEGIN
        UPDATE slots SET released_at = datetime('now') WHERE id = NEW.id;
    END;

    CREATE TRIGGER IF NOT EXISTS trg_slots_booked
    AFTER UPDATE OF request_id ON slots
    WHEN NEW.request_id IS NOT NULL
    BEGIN
        UPDATE slots SET released_at = NULL WHERE id = NEW.id;
    END;

    -- Слот, созданный вручную (админ открыл окно), тоже должен триггерить
    -- уведомление листа ожидания. auto_created=0 — это create_slot /
    -- generate_slots_range (ручное действие админа). auto_created=1 — это
    -- regenerate_doctor_slots (автогенерация из графика на 60 дней вперёд),
    -- её не триггерим, иначе первый запуск зальёт лист десятками уведомлений.
    CREATE TRIGGER IF NOT EXISTS trg_slots_created_manual
    AFTER INSERT ON slots
    WHEN NEW.request_id IS NULL AND NEW.auto_created = 0
    BEGIN
        UPDATE slots SET released_at = datetime('now') WHERE id = NEW.id;
    END;
    """)

    # ==================== E3: паспорта каналов + боты ====================
    # client_identities — «паспорт» клиента в конкретном канале.
    # Один клиент (ключ склейки — clients.user_id, обычно телефон) может иметь
    # 0..N паспортов: max:12345, vk:67890. PK (platform, platform_uid) —
    # один и тот же MAX-id не может принадлежать двум клиентам.
    # UNIQUE (user_id, platform) — у клиента не может быть двух MAX-паспортов.
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS client_identities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        platform TEXT NOT NULL,
        platform_uid TEXT NOT NULL,
        is_primary INTEGER NOT NULL DEFAULT 0,
        created_at TEXT,
        last_seen_at TEXT,
        UNIQUE (platform, platform_uid),
        UNIQUE (user_id, platform)
    );
    CREATE INDEX IF NOT EXISTS idx_client_identities_user
        ON client_identities (user_id);
    CREATE INDEX IF NOT EXISTS idx_client_identities_uid
        ON client_identities (platform, platform_uid);

    -- bots — боты организации. Сейчас один MAX-бот (из config.MAX_BOT_TOKEN),
    -- в E4 появится VK. slug — человекочитаемый ключ ('clinic-boroda-vk').
    CREATE TABLE IF NOT EXISTS bots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        org_id INTEGER NOT NULL,
        platform TEXT NOT NULL,
        slug TEXT NOT NULL UNIQUE,
        token TEXT,
        webhook_secret TEXT,
        title TEXT,
        enabled INTEGER NOT NULL DEFAULT 1,
        created_at TEXT,
        updated_at TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_bots_org_platform
        ON bots (org_id, platform, enabled);
    """)

    # Multi-bot: секрет вебхука у каждого бота свой (MAX и VK — разные схемы
    # подписи). confirmation_code — строка, которую VK требует вернуть на
    # type=confirmation; нужна и для авто-регистрации Callback-адреса.
    # bot_token — токен для MAX/VK (в MAX это app_token от Manifest, в VK — сам токен).
    for _col, _ddl in (
        ("group_id", "TEXT"),
        ("confirmation_code", "TEXT"),
        ("bot_token", "TEXT"),
    ):
        _ensure_column(conn, "bots", _col, _ddl)
    conn.commit()

    # ==================== E4.6: Суперадмины по платформам ====================
    # superadmins — глобальный реестр суперадминов (один человек может быть
    # суперадмином одновременно в MAX и VK с разными user_id). UNIQUE гарантирует,
    # что одна и та же пара (platform, platform_uid) не повторится дважды.
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS superadmins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        platform TEXT NOT NULL,
        platform_uid TEXT NOT NULL,
        name TEXT,
        created_at TEXT,
        UNIQUE (platform, platform_uid)
    );
    CREATE INDEX IF NOT EXISTS idx_superadmins_platform_uid
        ON superadmins (platform, platform_uid);
    """)
    conn.commit()

    # Разовая миграция clients.user_id (MAX-id или phone:...) → client_identities.
    # Идемпотентна: UNIQUE(platform, platform_uid) отсекает уже перенесённых,
    # UNIQUE(user_id, platform) — вторую попытку для того же клиента.
    conn.executescript("""
    INSERT OR IGNORE INTO client_identities
        (user_id, platform, platform_uid, is_primary, created_at, last_seen_at)
    SELECT
        c.user_id,
        'max',
        c.user_id,
        1,
        COALESCE(c.created_at, datetime('now')),
        datetime('now')
    FROM clients c
    WHERE c.user_id NOT LIKE 'phone:%'
      AND c.user_id != ''
      AND NOT EXISTS (
          SELECT 1 FROM client_identities ci WHERE ci.user_id = c.user_id
      );
    """)

    _ensure_column(conn, "client_identities", "is_primary",
                   "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "client_identities", "last_seen_at", "TEXT")

    conn.commit()
    conn.close()


# ---------- audit log ----------

def log_audit(org_id, user_id, action, entity_type=None, entity_id=None, payload=None):
    try:
        conn = db()
        conn.execute(
            "INSERT INTO audit_log (org_id, user_id, action, entity_type, entity_id, payload, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (org_id, str(user_id) if user_id else None, action,
             entity_type, str(entity_id) if entity_id is not None else None,
             json.dumps(payload or {}, ensure_ascii=False),
             datetime.now().isoformat()),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def list_audit_log(org_id, limit=100, offset=0, action=None, date_from=None, date_to=None):
    conn = db()
    where = ["org_id=?"]
    params = [org_id]
    if action:
        where.append("action=?")
        params.append(action)
    if date_from:
        where.append("date(created_at) >= date(?)")
        params.append(date_from)
    if date_to:
        where.append("date(created_at) <= date(?)")
        params.append(date_to)
    where_sql = " AND ".join(where)
    rows = conn.execute(
        f"SELECT id, user_id, action, entity_type, entity_id, payload, created_at "
        f"FROM audit_log WHERE {where_sql} "
        f"ORDER BY id DESC LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()
    conn.close()
    return rows


def get_orgs_with_evening_summary():
    """Возвращает организации в формате (org_id, hour_local)."""
    conn = db()
    rows = conn.execute(
        "SELECT id, settings FROM organizations WHERE settings IS NOT NULL"
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        try:
            s = json.loads(r["settings"] or "{}")
        except Exception:
            continue
        hour = s.get("evening_summary_hour", config.EVENING_SUMMARY_DEFAULT_HOUR)
        try:
            hour = int(hour)
        except (TypeError, ValueError):
            hour = config.EVENING_SUMMARY_DEFAULT_HOUR
        if 0 <= hour <= 23:
            result.append((r["id"], hour))
    return result


# ---------- dashboard ----------

def get_dashboard_today(org_id, today_str=None):
    """Сводка по сегодняшнему дню. today_str в локальной таймзоне организации."""
    today = today_str or today_for_org(org_id)
    conn = db()

    rows = conn.execute(
        "SELECT status, actual_amount, done_auto FROM history "
        "WHERE org_id=? AND date(scheduled_at)=date(?)",
        (org_id, today),
    ).fetchall()

    total = len(rows)
    pending = 0
    confirmed = 0
    done = 0
    no_show = 0
    cancelled = 0
    revenue = 0
    auto_done_count = 0
    for r in rows:
        st = r["status"]
        if st == "pending":
            pending += 1
        elif st == "confirmed":
            confirmed += 1
        elif st == "done":
            done += 1
            if r["actual_amount"]:
                revenue += int(r["actual_amount"])
            if r["done_auto"]:
                auto_done_count += 1
        elif st == "no_show":
            no_show += 1
        elif st == "cancelled":
            cancelled += 1

    pending_list = conn.execute(
        "SELECT id, service_name, scheduled_at, phone, doctor "
        "FROM history "
        "WHERE org_id=? AND date(scheduled_at)=date(?) AND status='pending' "
        "ORDER BY scheduled_at LIMIT 10",
        (org_id, today),
    ).fetchall()

    tomorrow = (_date.fromisoformat(today) + timedelta(days=1)).isoformat()
    tomorrow_count = conn.execute(
        "SELECT COUNT(*) AS n FROM history "
        "WHERE org_id=? AND date(scheduled_at)=date(?) "
        "AND status IN ('pending','confirmed')",
        (org_id, tomorrow),
    ).fetchone()["n"]

    conn.close()

    return {
        "date": today,
        "total": total,
        "pending": pending,
        "confirmed": confirmed,
        "done": done,
        "no_show": no_show,
        "cancelled": cancelled,
        "revenue": revenue,
        "auto_done_count": auto_done_count,
        "pending_list": [
            {"id": r["id"], "service_name": r["service_name"],
             "scheduled_at": r["scheduled_at"], "phone": r["phone"],
             "doctor": r["doctor"]}
            for r in pending_list
        ],
        "tomorrow_count": tomorrow_count,
    }


def get_today_requests_for_summary(org_id, today_str=None):
    today = today_str or today_for_org(org_id)
    conn = db()
    rows = conn.execute(
        "SELECT id, service_name, scheduled_at, phone, status, "
        "       actual_amount, payment_method, doctor "
        "FROM history "
        "WHERE org_id=? AND date(scheduled_at)=date(?) "
        "ORDER BY scheduled_at",
        (org_id, today),
    ).fetchall()
    conn.close()
    return rows


# ---------- uploaded images ----------

def save_uploaded_image_full(token, file_path, mime_type, original_filename,
                             file_size, org_id, uploaded_by):
    """Сохраняет запись о загруженном файле. Возвращает (id, public_token)."""
    import uuid as _uuid
    public_token = _uuid.uuid4().hex
    conn = db()
    try:
        cur = conn.execute(
            "INSERT INTO uploaded_images "
            "(token, public_token, file_path, mime_type, original_filename, file_size, "
            " org_id, uploaded_by, uploaded_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (token, public_token, file_path, mime_type, original_filename, file_size,
             org_id, str(uploaded_by) if uploaded_by else None,
             datetime.now().isoformat()),
        )
        uid = cur.lastrowid
        conn.commit()
        return uid, public_token
    finally:
        conn.close()


def get_uploaded_image_by_id(upload_id):
    conn = db()
    row = conn.execute(
        "SELECT id, token, public_token, file_path, mime_type, original_filename, "
        "       file_size, org_id, uploaded_by, uploaded_at "
        "FROM uploaded_images WHERE id=?",
        (upload_id,),
    ).fetchone()
    conn.close()
    return row


def list_temp_exports_older_than(minutes):
    """Возвращает id, file_path записей uploaded_images с mime csv/xlsx/pdf,
    старше указанного возраста. Используется фоновой очисткой."""
    from datetime import datetime as _dt, timedelta as _td
    cutoff = (_dt.now() - _td(minutes=minutes)).isoformat()
    conn = db()
    rows = conn.execute(
        "SELECT id, file_path, mime_type FROM uploaded_images "
        "WHERE mime_type IN ('text/csv', "
        "                    'application/pdf', "
        "                    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet') "
        "AND uploaded_at < ?",
        (cutoff,),
    ).fetchall()
    conn.close()
    return rows


def list_orphan_uploaded_files(org_id, extensions):
    """Возвращает список file_path на диске в uploads/{org_id}/ с расширением из extensions,
    для которых нет записи в uploaded_images."""
    import os as _os
    import config as _config
    from pathlib import Path as _Path

    ext_list = tuple("." + e.lower().lstrip(".") for e in extensions)
    folder = _Path(_config.UPLOADS_DIR) / str(org_id)
    if not folder.exists():
        return []

    try:
        on_disk = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in ext_list]
    except Exception:
        return []

    if not on_disk:
        return []

    conn = db()
    rows = conn.execute(
        "SELECT file_path FROM uploaded_images WHERE file_path IS NOT NULL"
    ).fetchall()
    conn.close()
    known = {r["file_path"] for r in rows}

    result = []
    for p in on_disk:
        rel = f"{org_id}/{p.name}"
        if rel not in known:
            result.append(rel)
    return result


def delete_uploaded_image_file(upload_id):
    """Удаляет файл с диска и запись из uploaded_images.
    Возвращает True, если запись была и файл удалён (или уже не было файла)."""
    import os as _os
    import config as _config
    if not upload_id:
        return False
    conn = db()
    row = conn.execute(
        "SELECT id, file_path FROM uploaded_images WHERE id=?", (upload_id,)
    ).fetchone()
    if not row:
        conn.close()
        return False
    if row["file_path"]:
        try:
            abs_path = _os.path.join(_config.UPLOADS_DIR, row["file_path"])
            if _os.path.exists(abs_path):
                _os.unlink(abs_path)
        except Exception:
            pass
    conn.execute("DELETE FROM uploaded_images WHERE id=?", (upload_id,))
    conn.commit()
    conn.close()
    return True


def get_uploaded_image_by_public_token(public_token):
    if not public_token:
        return None
    conn = db()
    row = conn.execute(
        "SELECT id, token, public_token, file_path, mime_type, original_filename, "
        "       file_size, org_id, uploaded_by, uploaded_at "
        "FROM uploaded_images WHERE public_token=?",
        (public_token,),
    ).fetchone()
    conn.close()
    return row


def update_uploaded_image_token(upload_id, token):
    conn = db()
    conn.execute(
        "UPDATE uploaded_images SET token=? WHERE id=?",
        (token, upload_id),
    )
    conn.commit()
    conn.close()


def get_uploaded_image(token: str):
    """Legacy-поиск по token. Возвращает Row или None."""
    if not token:
        return None
    conn = db()
    row = conn.execute(
        "SELECT id, token, file_path, mime_type, original_filename, "
        "       file_size, org_id, uploaded_by, uploaded_at "
        "FROM uploaded_images WHERE token=?",
        (token,),
    ).fetchone()
    conn.close()
    return row


# ---------- organizations ----------

def create_org(name: str) -> int:
    conn = db()
    cur = conn.execute(
        "INSERT INTO organizations (name, settings, timezone, created_at) VALUES (?, ?, ?, ?)",
        (name, json.dumps(DEFAULT_ORG_SETTINGS, ensure_ascii=False),
         config.DEFAULT_TIMEZONE, datetime.now().isoformat()),
    )
    oid = cur.lastrowid
    conn.commit()
    conn.close()
    return oid


def list_orgs():
    conn = db()
    rows = conn.execute("SELECT id, name FROM organizations ORDER BY id").fetchall()
    conn.close()
    return rows


def get_org(oid: int):
    conn = db()
    row = conn.execute("SELECT id, name, timezone FROM organizations WHERE id=?", (oid,)).fetchone()
    conn.close()
    return row


def get_org_settings(org_id: int) -> dict:
    conn = db()
    row = conn.execute(
        "SELECT settings, timezone FROM organizations WHERE id=?", (org_id,)
    ).fetchone()
    conn.close()
    if not row:
        return dict(DEFAULT_ORG_SETTINGS)
    tz = row["timezone"] or config.DEFAULT_TIMEZONE
    if not row["settings"]:
        merged = dict(DEFAULT_ORG_SETTINGS)
        merged["timezone"] = tz
        return merged
    try:
        stored = json.loads(row["settings"])
    except Exception:
        stored = {}
    merged = dict(DEFAULT_ORG_SETTINGS)
    merged.update(stored)
    merged["timezone"] = tz
    return merged


def set_org_settings(org_id: int, settings: dict):
    """Сохраняет настройки. timezone вынимается и пишется в отдельную колонку."""
    settings_copy = dict(settings or {})
    timezone_val = settings_copy.pop("timezone", None)
    conn = db()
    conn.execute(
        "UPDATE organizations SET settings=? WHERE id=?",
        (json.dumps(settings_copy, ensure_ascii=False), org_id),
    )
    if timezone_val:
        conn.execute("UPDATE organizations SET timezone=? WHERE id=?", (timezone_val, org_id))
    conn.commit()
    conn.close()
    if timezone_val:
        _tz_cache.pop(org_id, None)

def update_org_name(org_id: int, name: str) -> bool:
    """Переименование организации. Возвращает True при успехе."""
    name = (name or "").strip()
    if not name:
        return False
    conn = db()
    cur = conn.execute("UPDATE organizations SET name=? WHERE id=?", (name, org_id))
    conn.commit()
    changed = cur.rowcount > 0
    conn.close()
    return changed

# ---------- admins ----------

def is_superadmin_db(platform, platform_uid):
    """Проверка суперадмина по платформе и ID. Новая схема — против БД."""
    conn = db()
    row = conn.execute(
        "SELECT 1 FROM superadmins WHERE platform=? AND platform_uid=?",
        (platform, str(platform_uid)),
    ).fetchone()
    conn.close()
    return row is not None


def is_superadmin(uid):
    """Обратная совместимость: проверка MAX-суперадмина через конфиг (deprecated).
    Будет заменена на is_superadmin_db('max', uid) после миграции."""
    uid_str = str(uid)
    if not uid_str.isdigit():
        return False
    import config
    return config.SUPERADMIN_ID > 0 and int(uid_str) == config.SUPERADMIN_ID


def is_admin(uid):
    if is_superadmin(uid):
        return True
    conn = db()
    row = conn.execute("SELECT 1 FROM admins WHERE user_id=?", (str(uid),)).fetchone()
    conn.close()
    return row is not None


def upsert_superadmin(platform, platform_uid, name=None):
    """Добавить или обновить суперадмина. Идемпотентна."""
    conn = db()
    now = datetime.now().isoformat()
    row = conn.execute(
        "SELECT id FROM superadmins WHERE platform=? AND platform_uid=?",
        (platform, str(platform_uid)),
    ).fetchone()
    if row:
        if name is not None:
            conn.execute(
                "UPDATE superadmins SET name=? WHERE id=?",
                (name, row["id"]),
            )
    else:
        conn.execute(
            "INSERT INTO superadmins (platform, platform_uid, name, created_at) VALUES (?, ?, ?, ?)",
            (platform, str(platform_uid), name, now),
        )
    conn.commit()
    conn.close()


def list_superadmins():
    """Все суперадмины."""
    conn = db()
    rows = conn.execute(
        "SELECT id, platform, platform_uid, name, created_at FROM superadmins ORDER BY platform, platform_uid"
    ).fetchall()
    conn.close()
    return rows


def delete_superadmin(platform, platform_uid):
    """Удалить суперадмина."""
    conn = db()
    conn.execute(
        "DELETE FROM superadmins WHERE platform=? AND platform_uid=?",
        (platform, str(platform_uid)),
    )
    conn.commit()
    conn.close()


def get_admin_org(uid):
    conn = db()
    row = conn.execute("SELECT org_id FROM admins WHERE user_id=?", (str(uid),)).fetchone()
    conn.close()
    return row["org_id"] if row else None


def add_admin(uid, first_name, org_id, added_by):
    conn = db()
    conn.execute(
        "INSERT OR REPLACE INTO admins (user_id, first_name, org_id, added_by, added_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (str(uid), first_name, org_id, str(added_by), datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def remove_admin(uid):
    conn = db()
    conn.execute("DELETE FROM admins WHERE user_id=?", (str(uid),))
    conn.commit()
    conn.close()


def list_admins():
    conn = db()
    rows = conn.execute(
        "SELECT a.user_id, a.first_name, a.org_id, o.name "
        "FROM admins a LEFT JOIN organizations o ON o.id = a.org_id "
        "ORDER BY a.added_at DESC"
    ).fetchall()
    conn.close()
    return rows


def admins_of_org(org_id):
    conn = db()
    rows = conn.execute("SELECT user_id FROM admins WHERE org_id=?", (org_id,)).fetchall()
    conn.close()
    return [r["user_id"] for r in rows]


# ---------- pending admins ----------

def add_pending(uid, first_name, username=""):
    conn = db()
    conn.execute(
        "INSERT OR REPLACE INTO pending_admins (user_id, first_name, username, requested_at) "
        "VALUES (?, ?, ?, ?)",
        (str(uid), first_name, username, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def list_pending():
    conn = db()
    rows = conn.execute(
        "SELECT user_id, first_name, username, requested_at FROM pending_admins "
        "ORDER BY requested_at DESC"
    ).fetchall()
    conn.close()
    return rows


def remove_pending(uid):
    conn = db()
    conn.execute("DELETE FROM pending_admins WHERE user_id=?", (str(uid),))
    conn.commit()
    conn.close()


# ---------- services ----------

def get_services(org_id=None):
    conn = db()
    base = (
        "SELECT s.id, s.name, s.price, s.prep, s.category_id, "
        "       c.name AS category_name, c.sort_order AS category_sort_order "
        "FROM services s "
        "LEFT JOIN service_categories c ON c.id = s.category_id "
        "WHERE s.active=1"
    )
    if org_id is None:
        rows = conn.execute(
            base + " ORDER BY COALESCE(c.sort_order, 999999), c.name, s.name"
        ).fetchall()
    else:
        rows = conn.execute(
            base + " AND s.org_id=? ORDER BY COALESCE(c.sort_order, 999999), c.name, s.name",
            (org_id,),
        ).fetchall()
    conn.close()
    return rows


def get_service(sid):
    conn = db()
    row = conn.execute(
        "SELECT id, org_id, name, prep, active, duration_min, buffer_min, price, category_id, "
        "       revisit_interval_days "
        "FROM services WHERE id=?", (sid,)
    ).fetchone()
    conn.close()
    return row


def list_services_admin(org_id):
    conn = db()
    rows = conn.execute(
        "SELECT s.id, s.name, s.price, s.prep, s.duration_min, s.buffer_min, s.active, "
        "       s.category_id, c.name AS category_name, s.revisit_interval_days "
        "FROM services s "
        "LEFT JOIN service_categories c ON c.id = s.category_id "
        "WHERE s.org_id=? "
        "ORDER BY COALESCE(c.sort_order, 999999), c.name, s.name",
        (org_id,),
    ).fetchall()
    conn.close()
    return rows


def create_service(org_id, sid, name, price, prep, duration_min, category_id=None, buffer_min=0, revisit_interval_days=0):
    conn = db()
    try:
        conn.execute(
            "INSERT INTO services (id, org_id, name, price, prep, duration_min, buffer_min, "
            "active, category_id, revisit_interval_days) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
            (sid, org_id, name, price, prep, duration_min, buffer_min,
             category_id, revisit_interval_days),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def update_service(sid, name, price, prep, duration_min, active, category_id=None, buffer_min=0, revisit_interval_days=0):
    conn = db()
    conn.execute(
        "UPDATE services SET name=?, price=?, prep=?, duration_min=?, buffer_min=?, "
        "active=?, category_id=?, revisit_interval_days=? WHERE id=?",
        (name, price, prep, duration_min, buffer_min, active, category_id,
         revisit_interval_days, sid),
    )
    conn.commit()
    conn.close()


def delete_service(sid):
    conn = db()
    conn.execute("DELETE FROM doctor_services WHERE service_id=?", (sid,))
    conn.execute("DELETE FROM services WHERE id=?", (sid,))
    conn.commit()
    conn.close()


# ---------- service_categories ----------

def list_service_categories(org_id):
    """Список категорий организации с количеством услуг в каждой."""
    conn = db()
    rows = conn.execute(
        "SELECT c.id, c.name, c.sort_order, c.created_at, "
        "       (SELECT COUNT(*) FROM services s WHERE s.category_id=c.id) AS services_count "
        "FROM service_categories c "
        "WHERE c.org_id=? "
        "ORDER BY c.sort_order, c.name",
        (org_id,),
    ).fetchall()
    conn.close()
    return rows


def get_service_category(cat_id):
    conn = db()
    row = conn.execute(
        "SELECT id, org_id, name, sort_order FROM service_categories WHERE id=?",
        (cat_id,),
    ).fetchone()
    conn.close()
    return row


def create_service_category(org_id, name, sort_order=100):
    conn = db()
    cur = conn.execute(
        "INSERT INTO service_categories (org_id, name, sort_order, created_at) "
        "VALUES (?, ?, ?, ?)",
        (org_id, name, sort_order, datetime.now().isoformat()),
    )
    cid = cur.lastrowid
    conn.commit()
    conn.close()
    return cid


def update_service_category(cat_id, name, sort_order):
    conn = db()
    conn.execute(
        "UPDATE service_categories SET name=?, sort_order=? WHERE id=?",
        (name, sort_order, cat_id),
    )
    conn.commit()
    conn.close()


def delete_service_category(cat_id):
    """Удаляет категорию, только если в ней нет услуг.
    Возвращает (ok, services_count). Если ok=False — услуги привязаны,
    админ должен сначала переназначить их."""
    conn = db()
    n = conn.execute(
        "SELECT COUNT(*) AS n FROM services WHERE category_id=?", (cat_id,)
    ).fetchone()["n"]
    if n > 0:
        conn.close()
        return False, n
    conn.execute("DELETE FROM service_categories WHERE id=?", (cat_id,))
    conn.commit()
    conn.close()
    return True, 0


# ---------- user_state ----------

def set_state(user_id, state, context=None):
    conn = db()
    conn.execute(
        "INSERT OR REPLACE INTO user_state (user_id, state, context, updated_at) "
        "VALUES (?, ?, ?, ?)",
        (str(user_id), state, json.dumps(context or {}, ensure_ascii=False),
         datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def get_state(user_id):
    conn = db()
    row = conn.execute(
        "SELECT state, context FROM user_state WHERE user_id=?", (str(user_id),)
    ).fetchone()
    conn.close()
    if not row:
        return None, {}
    return row["state"], json.loads(row["context"] or "{}")


def clear_state(user_id):
    conn = db()
    conn.execute("DELETE FROM user_state WHERE user_id=?", (str(user_id),))
    conn.commit()
    conn.close()


# ---------- clients ----------

def search_clients(org_id: int, query: str, limit: int = 20):
    import re as _re
    conn = db()
    q = (query or "").strip()
    base_where = "(org_id=? OR org_id IS NULL)"
    base_params = [org_id]

    if not q:
        rows = conn.execute(
            "SELECT user_id, org_id, first_name, last_name, middle_name, phone, "
            "       last_visit_at, created_at, updated_at "
            f"FROM clients WHERE {base_where} "
            "ORDER BY CASE WHEN user_id LIKE 'phone:%' THEN 1 ELSE 0 END, "
            "         updated_at DESC LIMIT ?",
            base_params + [limit],
        ).fetchall()
        conn.close()
        return rows

    digits = _re.sub(r"\D", "", q)
    results = []
    seen_ids = set()

    if len(digits) >= 3:
        if len(digits) == 11 and digits[0] in ("7", "8"):
            canonical = digits[1:]
        else:
            canonical = digits
        pattern = f"%{canonical}%"
        phone_rows = conn.execute(
            "SELECT user_id, org_id, first_name, last_name, middle_name, phone, "
            "       last_visit_at, created_at, updated_at "
            f"FROM clients WHERE {base_where} AND phone LIKE ? "
            "ORDER BY CASE WHEN user_id LIKE 'phone:%' THEN 1 ELSE 0 END, "
            "         CASE WHEN org_id IS NULL THEN 1 ELSE 0 END, "
            "         updated_at DESC LIMIT ?",
            base_params + [pattern, limit],
        ).fetchall()
        for r in phone_rows:
            if r["user_id"] not in seen_ids:
                results.append(r)
                seen_ids.add(r["user_id"])

    if len(results) < limit:
        like = f"%{q}%"
        name_rows = conn.execute(
            "SELECT user_id, org_id, first_name, last_name, middle_name, phone, "
            "       last_visit_at, created_at, updated_at "
            f"FROM clients "
            f"WHERE {base_where} AND (first_name LIKE ? OR last_name LIKE ? "
            "       OR middle_name LIKE ?) "
            "ORDER BY CASE WHEN user_id LIKE 'phone:%' THEN 1 ELSE 0 END, "
            "         CASE WHEN org_id IS NULL THEN 1 ELSE 0 END, "
            "         updated_at DESC LIMIT ?",
            base_params + [like, like, like, limit],
        ).fetchall()
        for r in name_rows:
            if r["user_id"] not in seen_ids and len(results) < limit:
                results.append(r)
                seen_ids.add(r["user_id"])

    conn.close()
    return results[:limit]


def get_client_platforms(user_id):
    """Платформы клиента по client_identities: список ['max', 'vk']."""
    conn = db()
    rows = conn.execute(
        "SELECT platform FROM client_identities WHERE user_id=?",
        (str(user_id),),
    ).fetchall()
    conn.close()
    return sorted({r["platform"] for r in rows})


def get_client_platforms_batch(user_ids):
    """Каналы пачки клиентов: {user_id: ['max', 'vk']}."""
    out = {}
    ids = [str(u) for u in (user_ids or []) if u]
    if not ids:
        return out
    conn = db()
    ph = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"SELECT user_id, platform FROM client_identities "
        f"WHERE user_id IN ({ph})",
        ids,
    ).fetchall()
    conn.close()
    for r in rows:
        out.setdefault(r["user_id"], []).append(r["platform"])
    return out


def get_or_create_client_by_phone(org_id, first_name, last_name, middle_name, phone):
    import re as _re
    conn = db()
    digits = _re.sub(r"\D", "", phone or "")
    canonical = digits[-10:] if len(digits) >= 10 else digits
    rows = conn.execute(
        "SELECT user_id, org_id, phone FROM clients "
        "WHERE (org_id=? OR org_id IS NULL) AND phone IS NOT NULL AND phone != ''",
        (org_id,),
    ).fetchall()

    best_real = None
    best_real_orphan = None
    best_phone = None
    for r in rows:
        db_digits = _re.sub(r"\D", "", r["phone"] or "")
        if not db_digits:
            continue
        db_canon = db_digits[-10:] if len(db_digits) >= 10 else db_digits
        if db_canon != canonical:
            continue
        uid = r["user_id"]
        is_phone = str(uid).startswith("phone:")
        is_orphan = r["org_id"] is None
        if is_phone:
            if best_phone is None:
                best_phone = uid
        elif is_orphan:
            if best_real_orphan is None:
                best_real_orphan = uid
        else:
            if best_real is None:
                best_real = uid
    conn.close()

    if best_real:
        return best_real
    if best_real_orphan:
        upsert_client(best_real_orphan, org_id=org_id)
        return best_real_orphan
    if best_phone:
        return best_phone

    uid = f"phone:{phone}"
    upsert_client(
        uid, org_id=org_id, first_name=first_name or None,
        last_name=last_name or None, middle_name=middle_name or None, phone=phone,
    )
    return uid


def upsert_client(user_id, org_id=None, first_name=None, last_name=None,
                  middle_name=None, phone=None, gender=None, birth_date=None):
    conn = db()
    now = datetime.now().isoformat()
    row = conn.execute("SELECT user_id FROM clients WHERE user_id=?", (str(user_id),)).fetchone()
    if row:
        fields = []
        values = []
        if org_id is not None:
            fields.append("org_id=?"); values.append(org_id)
        if first_name is not None:
            fields.append("first_name=?"); values.append(first_name)
        if last_name is not None:
            fields.append("last_name=?"); values.append(last_name)
        if middle_name is not None:
            fields.append("middle_name=?"); values.append(middle_name)
        if phone is not None:
            fields.append("phone=?"); values.append(phone)
        if gender is not None:
            fields.append("gender=?"); values.append(gender)
        if birth_date is not None:
            fields.append("birth_date=?"); values.append(birth_date)
        fields.append("updated_at=?"); values.append(now); values.append(str(user_id))
        conn.execute(f"UPDATE clients SET {', '.join(fields)} WHERE user_id=?", values)
    else:
        conn.execute(
            "INSERT INTO clients (user_id, org_id, first_name, last_name, middle_name, phone, "
            "gender, birth_date, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (str(user_id), org_id, first_name or "", last_name or "", middle_name or "",
             phone or "", gender or "", birth_date or "", now, now),
        )
    _ensure_identity_for_user(conn, str(user_id))
    conn.commit()
    conn.close()


# ==================== E3: паспорта каналов (client_identities) ====================

def _ensure_identity_for_user(conn, user_id: str) -> None:
    """Создаёт MAX-паспорт для «настоящего» user_id (не phone:...).

    Вызывается из upsert_client, чтобы новые клиенты сразу получали identity,
    а не только те, кто прошёл разовую миграцию при старте.
    """
    uid = str(user_id or "")
    # 'phone:+7...', 'vk:123' — не MAX-аккаунт, паспорт заводит свой канал.
    if not uid or ":" in uid:
        return
    now = datetime.now().isoformat()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO client_identities "
            "(user_id, platform, platform_uid, is_primary, created_at, last_seen_at) "
            "VALUES (?, 'max', ?, 1, ?, ?)",
            (uid, uid, now, now),
        )
    except sqlite3.Error:
        # Таблицы ещё нет (старая БД без init_db) — не роняем запись клиента.
        pass


def get_client_identities(user_id):
    """Все «паспорта» клиента: список строк (platform, platform_uid, ...)."""
    conn = db()
    rows = conn.execute(
        "SELECT id, user_id, platform, platform_uid, is_primary, created_at, last_seen_at "
        "FROM client_identities WHERE user_id=? ORDER BY is_primary DESC, id ASC",
        (str(user_id),),
    ).fetchall()
    conn.close()
    return rows


def get_identity_by_platform_uid(platform, platform_uid):
    """Паспорт по id в канале: вернёт строку или None."""
    conn = db()
    row = conn.execute(
        "SELECT id, user_id, platform, platform_uid, is_primary, created_at, last_seen_at "
        "FROM client_identities WHERE platform=? AND platform_uid=?",
        (str(platform), str(platform_uid)),
    ).fetchone()
    conn.close()
    return row


def link_client_identity(user_id, platform, platform_uid, is_primary: int = 0):
    """Привязывает паспорт (platform, platform_uid) к клиенту user_id.

    Возвращает user_id — фактического владельца паспорта. Если паспорт уже
    привязан к другому клиенту, он НЕ перезахватывается: возвращается
    существующий владелец, а решение о склейке клиентов остаётся за
    вызывающим кодом (E4: склейка по телефону при первом VK-сообщении).
    """
    user_id = str(user_id)
    platform = str(platform)
    platform_uid = str(platform_uid)
    conn = db()
    now = datetime.now().isoformat()
    owner = conn.execute(
        "SELECT user_id FROM client_identities WHERE platform=? AND platform_uid=?",
        (platform, platform_uid),
    ).fetchone()
    if owner:
        conn.execute(
            "UPDATE client_identities SET last_seen_at=? WHERE platform=? AND platform_uid=?",
            (now, platform, platform_uid),
        )
        conn.commit()
        conn.close()
        return owner["user_id"]
    exist = conn.execute(
        "SELECT id FROM client_identities WHERE user_id=? AND platform=?",
        (user_id, platform),
    ).fetchone()
    if exist:
        conn.execute(
            "UPDATE client_identities SET platform_uid=?, last_seen_at=? WHERE id=?",
            (platform_uid, now, exist["id"]),
        )
    else:
        conn.execute(
            "INSERT INTO client_identities "
            "(user_id, platform, platform_uid, is_primary, created_at, last_seen_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, platform, platform_uid, 1 if is_primary else 0, now, now),
        )
    conn.commit()
    conn.close()
    return user_id


def touch_client_identity(user_id, platform):
    """Отмечает активность клиента в канале (для приоритета «последний активный»)."""
    conn = db()
    conn.execute(
        "UPDATE client_identities SET last_seen_at=? WHERE user_id=? AND platform=?",
        (datetime.now().isoformat(), str(user_id), str(platform)),
    )
    conn.commit()
    conn.close()


def unlink_client_identity(user_id, platform):
    """Удаляет паспорт — при отвязке канала или удалении данных по 152-ФЗ."""
    conn = db()
    conn.execute(
        "DELETE FROM client_identities WHERE user_id=? AND platform=?",
        (str(user_id), str(platform)),
    )
    conn.commit()
    conn.close()


# ==================== E3: боты организации ====================

def list_bots(org_id=None, platform=None, only_enabled: bool = False):
    """Список ботов, опционально по организации / платформе."""
    conn = db()
    where = []
    params = []
    if org_id is not None:
        where.append("org_id=?")
        params.append(org_id)
    if platform:
        where.append("platform=?")
        params.append(str(platform))
    if only_enabled:
        where.append("enabled=1")
    sql = "SELECT id, org_id, platform, slug, token, webhook_secret, title, enabled, " \
          "       group_id, confirmation_code, created_at, updated_at FROM bots"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY org_id ASC, platform ASC, id ASC"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return rows


def get_bot(bot_id):
    conn = db()
    row = conn.execute(
        "SELECT id, org_id, platform, slug, token, webhook_secret, title, enabled, "
        "       group_id, confirmation_code, created_at, updated_at FROM bots WHERE id=?",
        (bot_id,),
    ).fetchone()
    conn.close()
    return row


def get_bot_by_slug(slug):
    """Бот по slug — для маршрутизации /webhook/{bot_slug} (E4)."""
    conn = db()
    row = conn.execute(
        "SELECT id, org_id, platform, slug, token, webhook_secret, title, enabled, "
        "       group_id, confirmation_code, created_at, updated_at FROM bots WHERE slug=?",
        (str(slug),),
    ).fetchone()
    conn.close()
    return row


def get_bot_for_org(org_id, platform, only_enabled: bool = True):
    """Основной бот организации на платформе (сейчас MAX-бот из конфига)."""
    bots = list_bots(org_id=org_id, platform=platform, only_enabled=only_enabled)
    return bots[0] if bots else None


def upsert_bot(org_id, platform, slug, token=None, webhook_secret=None,
               title=None, enabled: int = 1, group_id=None,
               confirmation_code=None):
    """Создаёт или обновляет бота. Ключ — slug (он уникален глобально)."""
    conn = db()
    now = datetime.now().isoformat()
    row = conn.execute("SELECT id FROM bots WHERE slug=?", (str(slug),)).fetchone()
    if row:
        fields = ["org_id=?", "platform=?", "updated_at=?"]
        values = [org_id, str(platform), now]
        if token is not None:
            fields.append("token=?"); values.append(token)
        if webhook_secret is not None:
            fields.append("webhook_secret=?"); values.append(webhook_secret)
        if title is not None:
            fields.append("title=?"); values.append(title)
        if group_id is not None:
            fields.append("group_id=?"); values.append(str(group_id))
        if confirmation_code is not None:
            fields.append("confirmation_code=?"); values.append(confirmation_code)
        if enabled is not None:
            fields.append("enabled=?"); values.append(1 if enabled else 0)
        values.append(row["id"])
        conn.execute(f"UPDATE bots SET {', '.join(fields)} WHERE id=?", values)
        bot_id = row["id"]
    else:
        cur = conn.execute(
            "INSERT INTO bots (org_id, platform, slug, token, webhook_secret, title, "
            "group_id, confirmation_code, enabled, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (org_id, str(platform), str(slug), token, webhook_secret, title,
             str(group_id) if group_id is not None else None,
             confirmation_code, 1 if enabled else 0, now, now),
        )
        bot_id = cur.lastrowid
    conn.commit()
    conn.close()
    return bot_id


def set_bot_enabled(bot_id, enabled: bool):
    conn = db()
    conn.execute(
        "UPDATE bots SET enabled=?, updated_at=? WHERE id=?",
        (1 if enabled else 0, datetime.now().isoformat(), bot_id),
    )
    conn.commit()
    conn.close()


def delete_bot(bot_id):
    """Удалить бота."""
    conn = db()
    conn.execute("DELETE FROM bots WHERE id=?", (bot_id,))
    conn.commit()
    conn.close()


def get_client(user_id):
    conn = db()
    row = conn.execute(
        "SELECT user_id, org_id, first_name, last_name, middle_name, phone, "
        "       last_visit_at, gender, birth_date, "
        "       marketing_opt_out, marketing_opt_out_at, favorite_doctor_id, "
        "       consent_152fz, consent_given_at "
        "FROM clients WHERE user_id=?",
        (str(user_id),),
    ).fetchone()
    conn.close()
    return row


def set_marketing_opt_out(user_id, opt_out: bool = True):
    conn = db()
    conn.execute(
        "UPDATE clients SET marketing_opt_out=?, marketing_opt_out_at=?, updated_at=? "
        "WHERE user_id=?",
        (1 if opt_out else 0,
         datetime.now().isoformat() if opt_out else None,
         datetime.now().isoformat(),
         str(user_id)),
    )
    conn.commit()
    conn.close()


def get_marketing_opt_out(user_id):
    conn = db()
    row = conn.execute(
        "SELECT marketing_opt_out, marketing_opt_out_at FROM clients WHERE user_id=?",
        (str(user_id),),
    ).fetchone()
    conn.close()
    if not row:
        return None
    return {
        "opt_out": bool(row["marketing_opt_out"]),
        "opt_out_at": row["marketing_opt_out_at"],
    }


def get_marketing_opt_out_batch(user_ids):
    if not user_ids:
        return {}
    conn = db()
    placeholders = ",".join("?" * len(user_ids))
    rows = conn.execute(
        f"SELECT user_id, marketing_opt_out FROM clients WHERE user_id IN ({placeholders})",
        list(user_ids),
    ).fetchall()
    conn.close()
    return {r["user_id"]: bool(r["marketing_opt_out"]) for r in rows}


def set_favorite_doctor(user_id, doctor_id):
    """Ставит/снимает любимого врача. doctor_id=None или 0 — снять."""
    conn = db()
    conn.execute(
        "UPDATE clients SET favorite_doctor_id=?, updated_at=? WHERE user_id=?",
        (int(doctor_id) if doctor_id else None, datetime.now().isoformat(), str(user_id)),
    )
    conn.commit()
    conn.close()


def get_favorite_doctor(user_id):
    conn = db()
    row = conn.execute(
        "SELECT favorite_doctor_id FROM clients WHERE user_id=?",
        (str(user_id),),
    ).fetchone()
    conn.close()
    return row["favorite_doctor_id"] if row else None


def set_consent_152fz(user_id, consent=True):
    """Фиксирует согласие на обработку ПД (152-ФЗ). timestamp — серверное."""
    conn = db()
    now = datetime.now().isoformat()
    conn.execute(
        "UPDATE clients SET consent_152fz=?, consent_given_at=?, updated_at=? "
        "WHERE user_id=?",
        (1 if consent else 0, now if consent else None, now, str(user_id)),
    )
    conn.commit()
    conn.close()


def export_client_data(user_id, org_id):
    """Выгрузка всех данных клиента в JSON-совместимом виде (152-ФЗ)."""
    conn = db()
    uid_str = str(user_id)

    client_row = conn.execute(
        "SELECT user_id, org_id, first_name, last_name, middle_name, phone, "
        "       gender, birth_date, last_visit_at, favorite_doctor_id, "
        "       marketing_opt_out, marketing_opt_out_at, "
        "       consent_152fz, consent_given_at, created_at, updated_at "
        "FROM clients WHERE user_id=?",
        (uid_str,),
    ).fetchone()

    history_rows = conn.execute(
        "SELECT id, service_name, scheduled_at, phone, status, address, doctor, "
        "       actual_amount, payment_method, client_answer, created_at "
        "FROM history WHERE user_id=? AND org_id=? ORDER BY id DESC",
        (uid_str, org_id),
    ).fetchall()

    sends_rows = conn.execute(
        "SELECT broadcast_id, status, error, sent_at "
        "FROM broadcast_sends WHERE user_id=? ORDER BY id DESC",
        (uid_str,),
    ).fetchall()

    auto_rows = conn.execute(
        "SELECT auto_id, event_ref, sent_at "
        "FROM auto_broadcast_logs WHERE user_id=? ORDER BY id DESC",
        (uid_str,),
    ).fetchall()

    conn.close()

    return {
        "exported_at": datetime.now().isoformat(),
        "client": dict(client_row) if client_row else None,
        "requests": [dict(r) for r in history_rows],
        "broadcast_sends": [dict(r) for r in sends_rows],
        "auto_broadcast_logs": [dict(r) for r in auto_rows],
    }


def delete_client_data(user_id, org_id):
    """Удаление PII клиента по 152-ФЗ.

    Что удаляется полностью:
      - запись в clients (ФИО, телефон, пол, ДР, consent)
      - user_state (контекст диалогов с ботом)
      - broadcast_sends (лог маркетинговых касаний)
      - auto_broadcast_logs (лог автосценариев)

    Что обезличивается:
      - history: phone='', user_id='deleted:<hash>'. Записи остаются для
        финансовой отчётности, но идентифицировать клиента по ним нельзя.

    Что отменяется:
      - все активные записи (pending/confirmed), слоты освобождаются.

    Возвращает количество отменённых записей.
    """
    conn = db()
    uid_str = str(user_id)

    # 1. Отменить активные записи и освободить слоты
    active = conn.execute(
        "SELECT id, slot_id FROM history "
        "WHERE user_id=? AND org_id=? AND status IN ('pending', 'confirmed')",
        (uid_str, org_id),
    ).fetchall()
    cancelled = 0
    for row in active:
        rid = row["id"]
        slot_id = row["slot_id"]
        conn.execute("UPDATE history SET status='cancelled' WHERE id=?", (rid,))
        if slot_id:
            conn.execute(
                "UPDATE slots SET is_booked=0, request_id=NULL "
                "WHERE id=? AND request_id=?",
                (slot_id, rid),
            )
        cancelled += 1

    # 2. Удалить PII
    photo_row = conn.execute(
        "SELECT photo_upload_id FROM clients WHERE user_id=?", (uid_str,)
    ).fetchone()
    if photo_row and photo_row["photo_upload_id"]:
        conn.execute(
            "DELETE FROM uploaded_images WHERE id=?",
            (photo_row["photo_upload_id"],),
        )
    conn.execute("DELETE FROM clients WHERE user_id=?", (uid_str,))
    conn.execute("DELETE FROM user_state WHERE user_id=?", (uid_str,))
    conn.execute("DELETE FROM broadcast_sends WHERE user_id=?", (uid_str,))
    conn.execute("DELETE FROM auto_broadcast_logs WHERE user_id=?", (uid_str,))

    # 3. Обезличить историю (для финансовой отчётности)
    anon_uid = "deleted:" + hashlib.sha256(uid_str.encode()).hexdigest()[:12]
    conn.execute(
        "UPDATE history SET phone='', user_id=? WHERE user_id=? AND org_id=?",
        (anon_uid, uid_str, org_id),
    )

    conn.commit()
    conn.close()
    return cancelled


def recalculate_last_visit(user_id, org_id):
    conn = db()
    row = conn.execute(
        "SELECT MAX(scheduled_at) AS last FROM history "
        "WHERE org_id=? AND user_id=? AND status='done'",
        (org_id, str(user_id)),
    ).fetchone()
    last = row["last"] if row and row["last"] else None
    conn.execute(
        "UPDATE clients SET last_visit_at=?, updated_at=? WHERE org_id=? AND user_id=?",
        (last, datetime.now().isoformat(), org_id, str(user_id)),
    )
    conn.commit()
    conn.close()


def recalculate_all_last_visits(org_id=None):
    conn = db()
    q = (
        "UPDATE clients SET last_visit_at = ("
        "  SELECT MAX(h.scheduled_at) FROM history h"
        "  WHERE h.org_id = clients.org_id AND h.user_id = clients.user_id"
        "  AND h.status = 'done'"
        ")"
    )
    if org_id is None:
        conn.execute(q)
    else:
        conn.execute(q + " WHERE org_id=?", (org_id,))
    conn.commit()
    conn.close()


def autocomplete_past_visits(grace_hours=3, org_id=None):
    """Прошедшие confirmed → done с автозаполнением суммы по прайсу.
    Ставит done_auto=1, чтобы админ мог найти и перепроверить."""
    if org_id is not None:
        now_local = now_for_org(org_id)
    else:
        now_local = datetime.now()
    cutoff = (now_local - timedelta(hours=grace_hours)).strftime("%Y-%m-%d %H:%M")
    conn = db()

    # Найти подходящие записи, чтобы проставить сумму из услуги
    q_select = "SELECT id, service_id FROM history WHERE status='confirmed' AND scheduled_at < ?"
    params_select = [cutoff]
    if org_id is not None:
        q_select += " AND org_id=?"
        params_select.append(org_id)
    rows = conn.execute(q_select, params_select).fetchall()

    if not rows:
        conn.close()
        return 0

    service_prices = {}
    for r in rows:
        sid = r["service_id"]
        if sid and sid not in service_prices:
            row = conn.execute(
                "SELECT price FROM services WHERE id=?", (sid,)
            ).fetchone()
            service_prices[sid] = row["price"] if row and row["price"] else None

    n = 0
    for r in rows:
        rid = r["id"]
        sid = r["service_id"]
        price = service_prices.get(sid) if sid else None
        # actual_amount ставим только если он ещё не был установлен
        conn.execute(
            "UPDATE history SET status='done', done_auto=1, "
            "actual_amount = COALESCE(actual_amount, ?) "
            "WHERE id=?",
            (price, rid),
        )
        n += 1

    conn.commit()
    conn.close()
    if n:
        recalculate_all_last_visits(org_id)
    return n


def cancel_stale_pending(timeout_min, org_id=None):
    """Отменяет pending-заявки старше timeout_min и освобождает ВСЕ слоты записи."""
    if not timeout_min or timeout_min <= 0:
        return 0
    cutoff_server = (datetime.now() - timedelta(minutes=timeout_min)).isoformat()
    if org_id is not None:
        now_local = now_for_org(org_id)
    else:
        now_local = datetime.now()
    now_str = now_local.strftime("%Y-%m-%d %H:%M")
    conn = db()
    q = (
        "SELECT id, slot_id, slot_ids FROM history "
        "WHERE status='pending' AND created_at < ? AND scheduled_at >= ?"
    )
    params = [cutoff_server, now_str]
    if org_id is not None:
        q += " AND org_id=?"
        params.append(org_id)
    rows = conn.execute(q, params).fetchall()
    cancelled = 0
    for r in rows:
        rid = r["id"]
        slot_id = r["slot_id"]
        slot_ids_raw = r["slot_ids"]
        cur = conn.execute(
            "UPDATE history SET status='cancelled' WHERE id=? AND status='pending'",
            (rid,),
        )
        if cur.rowcount:
            cancelled += 1
            ids_to_release = []
            if slot_ids_raw:
                try:
                    ids_to_release = json.loads(slot_ids_raw)
                except Exception:
                    ids_to_release = []
            if not ids_to_release and slot_id:
                ids_to_release = [slot_id]
            if ids_to_release:
                placeholders = ",".join("?" * len(ids_to_release))
                conn.execute(
                    f"UPDATE slots SET is_booked=0, request_id=NULL "
                    f"WHERE id IN ({placeholders}) AND request_id=?",
                    ids_to_release + [rid],
                )
    conn.commit()
    conn.close()
    return cancelled


def list_visits_for_date(org_id, date_str):
    conn = db()
    rows = conn.execute(
        "SELECT id, user_id, service_name, scheduled_at, phone, status, doctor "
        "FROM history "
        "WHERE org_id=? AND date(scheduled_at)=date(?) "
        "AND status IN ('pending','confirmed','done','no_show') "
        "ORDER BY scheduled_at",
        (org_id, date_str),
    ).fetchall()
    conn.close()
    return rows


def touch_client_visit(user_id, when_iso):
    conn = db()
    conn.execute(
        "UPDATE clients SET last_visit_at=?, updated_at=? WHERE user_id=?",
        (when_iso, datetime.now().isoformat(), str(user_id)),
    )
    conn.commit()
    conn.close()


# ---------- history ----------

def add_history(org_id, user_id, service_name, scheduled_at, phone,
                address="", doctor="", branch_id=None, doctor_id=None,
                slot_id=None, status="pending", service_id=None):
    conn = db()
    cur = conn.execute(
        "INSERT INTO history (org_id, user_id, service_name, scheduled_at, phone, "
        "status, address, doctor, branch_id, doctor_id, slot_id, service_id, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (org_id, str(user_id), service_name, scheduled_at, phone,
         status, address, doctor, branch_id, doctor_id, slot_id, service_id,
         datetime.now().isoformat()),
    )
    rid = cur.lastrowid
    conn.commit()
    conn.close()
    return rid


def get_history(user_id):
    conn = db()
    rows = conn.execute(
        "SELECT id, service_name, scheduled_at, status, address, doctor FROM history "
        "WHERE user_id=? ORDER BY id DESC LIMIT 10",
        (str(user_id),),
    ).fetchall()
    conn.close()
    return rows


def get_history_upcoming(user_id):
    now_iso = datetime.now().strftime("%Y-%m-%d %H:%M")
    conn = db()
    rows = conn.execute(
        "SELECT id, service_id, service_name, scheduled_at, status, address, doctor "
        "FROM history "
        "WHERE user_id=? AND scheduled_at >= ? "
        "AND status IN ('pending', 'confirmed') "
        "ORDER BY CASE status WHEN 'confirmed' THEN 0 ELSE 1 END, scheduled_at",
        (str(user_id), now_iso),
    ).fetchall()
    conn.close()
    return rows


def get_history_all(user_id):
    now_iso = datetime.now().strftime("%Y-%m-%d %H:%M")
    conn = db()
    rows = conn.execute(
        "SELECT id, service_id, service_name, scheduled_at, status, address, doctor "
        "FROM history "
        "WHERE user_id=? "
        "ORDER BY "
        "  CASE "
        "    WHEN scheduled_at >= ? AND status='confirmed' THEN 0 "
        "    WHEN scheduled_at >= ? AND status='pending' THEN 1 "
        "    WHEN status='cancelled' THEN 2 "
        "    ELSE 3 "
        "  END, scheduled_at DESC",
        (str(user_id), now_iso, now_iso),
    ).fetchall()
    conn.close()
    return rows


def get_request(request_id):
    conn = db()
    row = conn.execute(
        "SELECT id, org_id, user_id, service_name, scheduled_at, phone, status, "
        "address, doctor, branch_id, doctor_id, slot_id, slots_count, slot_ids, "
        "service_id, actual_amount, payment_method, done_auto "
        "FROM history WHERE id=?",
        (request_id,),
    ).fetchone()
    conn.close()
    return row


def slots_needed_for_service(service_id, step_min):
    """Сколько подряд идущих слотов займёт услуга (с учётом буфера).
    Округление вверх до шага слота."""
    svc = get_service(service_id) if service_id else None
    duration = (svc["duration_min"] if svc else 30) or 30
    buffer_min = (svc["buffer_min"] if svc else 0) or 0
    step = step_min if step_min and step_min > 0 else 30
    total = duration + buffer_min
    import math
    n = math.ceil(total / step)
    return max(1, n)


def find_consecutive_slots(slot_id, slots_needed, step_min):
    """Проверяет, что от slot_id подряд идут slots_needed слотов
    (тот же врач, филиал, дата, шаг step_min), все свободны.
    Возвращает список slot_id или None."""
    if slots_needed <= 1:
        conn = db()
        row = conn.execute("SELECT is_booked FROM slots WHERE id=?", (slot_id,)).fetchone()
        conn.close()
        if not row or row["is_booked"]:
            return None
        return [slot_id]

    conn = db()
    slot = conn.execute(
        "SELECT id, branch_id, doctor_id, date, time, is_booked FROM slots WHERE id=?",
        (slot_id,),
    ).fetchone()
    if not slot or slot["is_booked"]:
        conn.close()
        return None

    h, m = map(int, slot["time"].split(":"))
    start_min = h * 60 + m
    date_str = slot["date"]
    doctor_id = slot["doctor_id"]
    branch_id = slot["branch_id"]

    needed_ids = [slot_id]
    for i in range(1, slots_needed):
        target_min = start_min + i * step_min
        if target_min >= 24 * 60:
            conn.close()
            return None
        target_time = f"{target_min // 60:02d}:{target_min % 60:02d}"
        row = conn.execute(
            "SELECT id, is_booked FROM slots "
            "WHERE date=? AND time=? AND doctor_id IS ? AND branch_id IS ?",
            (date_str, target_time, doctor_id, branch_id),
        ).fetchone()
        if not row or row["is_booked"]:
            conn.close()
            return None
        needed_ids.append(row["id"])
    conn.close()
    return needed_ids


def filter_slots_by_duration(org_id, date, base_slots, slots_needed, step_min):
    """Фильтрует свободные слоты: оставляет только те, для которых есть
    slots_needed-1 свободных слотов подряд (того же врача, филиала, дня).
    base_slots — список Row (id, time, branch_id, doctor_id, ...)."""
    if slots_needed <= 1:
        return base_slots

    conn = db()
    all_rows = conn.execute(
        "SELECT time, branch_id, doctor_id, is_booked FROM slots "
        "WHERE org_id=? AND date=?",
        (org_id, date),
    ).fetchall()
    conn.close()

    all_keys = set()
    occupied_keys = set()
    for r in all_rows:
        key = (r["doctor_id"], r["branch_id"], r["time"])
        all_keys.add(key)
        if r["is_booked"]:
            occupied_keys.add(key)

    result = []
    for s in base_slots:
        h, m = map(int, s["time"].split(":"))
        start_min = h * 60 + m
        ok = True
        for i in range(1, slots_needed):
            target_min = start_min + i * step_min
            if target_min >= 24 * 60:
                ok = False
                break
            target_time = f"{target_min // 60:02d}:{target_min % 60:02d}"
            key = (s["doctor_id"], s["branch_id"], target_time)
            if key not in all_keys or key in occupied_keys:
                ok = False
                break
        if ok:
            result.append(s)
    return result


_ALLOWED_FROM = {
    "confirmed": ("pending",),
    "done": ("pending", "confirmed", "no_show"),
    "no_show": ("pending", "confirmed", "done"),
    "cancelled": ("pending", "confirmed"),
}


def update_request_status(request_id, status, admin_id=None):
    conn = db()
    row = None
    prev_status = None
    if status in ("done", "no_show"):
        row = conn.execute(
            "SELECT user_id, org_id, status FROM history WHERE id=?", (request_id,)
        ).fetchone()
        if row:
            prev_status = row["status"]
    where = "id=?"
    params = [request_id]
    allowed = _ALLOWED_FROM.get(status)
    if allowed:
        where += " AND status IN (%s)" % ",".join("?" * len(allowed))
        params.extend(allowed)
    # done_auto сбрасывается в 0 при любой ручной отметке
    done_auto_clause = ", done_auto=0" if (status == "done" and admin_id is not None) else ""
    if admin_id is not None:
        cur = conn.execute(
            f"UPDATE history SET status=?, confirmed_by=?, confirmed_at=?{done_auto_clause} "
            f"WHERE {where}",
            [status, str(admin_id), datetime.now().isoformat()] + params,
        )
    else:
        cur = conn.execute(f"UPDATE history SET status=? WHERE {where}", [status] + params)
    changed = cur.rowcount > 0

    # Счётчик неявок: инкремент при переходе в no_show, декремент при выходе из no_show
    if changed and row:
        uid = row["user_id"]
        if status == "no_show" and prev_status != "no_show":
            conn.execute(
                "UPDATE clients SET no_show_count = COALESCE(no_show_count, 0) + 1, "
                "no_show_last_at = ? WHERE user_id = ?",
                (datetime.now().isoformat(), str(uid)),
            )
        elif prev_status == "no_show" and status != "no_show":
            conn.execute(
                "UPDATE clients SET no_show_count = MAX(COALESCE(no_show_count, 0) - 1, 0) "
                "WHERE user_id = ?",
                (str(uid),),
            )

    conn.commit()
    conn.close()
    if changed and status in ("done", "no_show") and row:
        recalculate_last_visit(row["user_id"], row["org_id"])
    return changed


def set_request_payment(request_id, actual_amount, payment_method):
    conn = db()
    cur = conn.execute(
        "UPDATE history SET actual_amount=?, payment_method=?, done_auto=0 "
        "WHERE id=? AND status IN ('done', 'no_show')",
        (actual_amount, payment_method, request_id),
    )
    changed = cur.rowcount > 0
    conn.commit()
    conn.close()
    return changed


def get_stats(org_id=None):
    conn = db()
    if org_id is None:
        total = conn.execute("SELECT COUNT(*) AS n FROM history").fetchone()["n"]
        by_service = conn.execute(
            "SELECT service_name, COUNT(*) AS n FROM history GROUP BY service_name"
        ).fetchall()
    else:
        total = conn.execute(
            "SELECT COUNT(*) AS n FROM history WHERE org_id=?", (org_id,)
        ).fetchone()["n"]
        by_service = conn.execute(
            "SELECT service_name, COUNT(*) AS n FROM history WHERE org_id=? GROUP BY service_name",
            (org_id,),
        ).fetchall()
    conn.close()
    return total, by_service


# ---------- branches ----------

def create_branch(org_id, name, address="", phone=""):
    conn = db()
    existing = conn.execute(
        "SELECT COUNT(*) AS n FROM branches WHERE org_id=?", (org_id,)
    ).fetchone()["n"]
    is_primary = 1 if existing == 0 else 0
    cur = conn.execute(
        "INSERT INTO branches (org_id, name, address, phone, is_primary, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (org_id, name, address, phone, is_primary, datetime.now().isoformat()),
    )
    bid = cur.lastrowid
    conn.commit()
    conn.close()
    return bid


def list_branches(org_id):
    conn = db()
    rows = conn.execute(
        "SELECT id, name, address, phone, is_primary FROM branches "
        "WHERE org_id=? ORDER BY is_primary DESC, id",
        (org_id,),
    ).fetchall()
    conn.close()
    return rows


def get_primary_branch(org_id):
    """Основной филиал org. Если ни одного не помечено — первый по id."""
    conn = db()
    row = conn.execute(
        "SELECT id, name, address, phone, is_primary FROM branches "
        "WHERE org_id=? ORDER BY is_primary DESC, id LIMIT 1",
        (org_id,),
    ).fetchone()
    conn.close()
    return row


def set_primary_branch(branch_id):
    """Помечает филиал основным, снимает флаг с других в его org.
    Возвращает True при успехе."""
    conn = db()
    try:
        br = conn.execute(
            "SELECT org_id FROM branches WHERE id=?", (branch_id,)
        ).fetchone()
        if not br:
            return False
        conn.execute(
            "UPDATE branches SET is_primary=0 WHERE org_id=?",
            (br["org_id"],),
        )
        conn.execute(
            "UPDATE branches SET is_primary=1 WHERE id=?",
            (branch_id,),
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_branch(bid):
    conn = db()
    row = conn.execute(
        "SELECT id, org_id, name, address, phone FROM branches WHERE id=?", (bid,)
    ).fetchone()
    conn.close()
    return row


def update_branch(bid, name, address, phone):
    conn = db()
    conn.execute(
        "UPDATE branches SET name=?, address=?, phone=? WHERE id=?",
        (name, address, phone, bid),
    )
    conn.commit()
    conn.close()


def delete_branch(bid):
    """Удаление филиала с проверками и чисткой.
    Возвращает (ok, reason)."""
    conn = db()
    try:
        active = conn.execute(
            "SELECT COUNT(*) AS n FROM history "
            "WHERE branch_id=? AND status IN ('pending', 'confirmed')",
            (bid,),
        ).fetchone()["n"]
        if active:
            return False, f"В филиале есть активные записи ({active}). Отмените или перенесите их сначала."

        booked = conn.execute(
            "SELECT COUNT(*) AS n FROM slots WHERE branch_id=? AND is_booked=1",
            (bid,),
        ).fetchone()["n"]
        if booked:
            return False, f"В филиале есть забронированные слоты ({booked}). Освободите их сначала."

        row = conn.execute(
            "SELECT org_id, is_primary FROM branches WHERE id=?", (bid,)
        ).fetchone()
        if not row:
            return False, "Филиал не найден"

        conn.execute("DELETE FROM slots WHERE branch_id=?", (bid,))
        conn.execute("DELETE FROM schedule_shifts WHERE branch_id=?", (bid,))
        conn.execute("DELETE FROM branches WHERE id=?", (bid,))

        if row["is_primary"]:
            new_primary = conn.execute(
                "SELECT MIN(id) AS nid FROM branches WHERE org_id=?", (row["org_id"],)
            ).fetchone()["nid"]
            if new_primary:
                conn.execute(
                    "UPDATE branches SET is_primary=1 WHERE id=?", (new_primary,)
                )

        conn.commit()
        return True, None
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------- doctors ----------

def create_doctor(branch_id, name, specialty="", education="", courses="", about=""):
    conn = db()
    cur = conn.execute(
        "INSERT INTO doctors (branch_id, name, specialty, education, courses, about, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (branch_id, name, specialty, education, courses, about, datetime.now().isoformat()),
    )
    did = cur.lastrowid
    conn.commit()
    conn.close()
    return did


def list_doctors(branch_id):
    """Врачи, работающие в филиале: либо основной филиал = branch_id,
    либо есть смена в этом филиале (schedule_shifts)."""
    conn = db()
    rows = conn.execute(
        "SELECT DISTINCT d.id, d.name, d.specialty "
        "FROM doctors d "
        "LEFT JOIN schedule_shifts ss ON ss.doctor_id = d.id "
        "WHERE d.branch_id=? OR ss.branch_id=? "
        "ORDER BY d.name",
        (branch_id, branch_id),
    ).fetchall()
    conn.close()
    return rows


def list_doctors_by_org(org_id):
    conn = db()
    rows = conn.execute(
        "SELECT d.id, d.name, d.specialty, d.branch_id, b.name AS branch_name, "
        "       d.photo_upload_id, d.education, d.courses, d.about, "
        "       (SELECT COUNT(*) FROM doctor_services ds WHERE ds.doctor_id = d.id) "
        "       AS services_count "
        "FROM doctors d JOIN branches b ON b.id = d.branch_id "
        "WHERE b.org_id=? ORDER BY d.name",
        (org_id,),
    ).fetchall()
    conn.close()
    return rows


def get_doctor_branches(doctor_id):
    """Список филиалов, где врач работает: основной (doctors.branch_id) +
    все уникальные филиалы из его смен (schedule_shifts)."""
    conn = db()
    rows = conn.execute(
        "SELECT DISTINCT b.id, b.name, b.address "
        "FROM branches b "
        "WHERE b.id = (SELECT branch_id FROM doctors WHERE id=?) "
        "   OR b.id IN (SELECT branch_id FROM schedule_shifts WHERE doctor_id=?) "
        "ORDER BY b.name",
        (doctor_id, doctor_id),
    ).fetchall()
    conn.close()
    return rows


# ---------- doctor_services ----------

def get_doctor_services(doctor_id):
    """Список service_id, привязанных к врачу.
    Пустой список = врач делает все услуги (legacy-режим)."""
    conn = db()
    rows = conn.execute(
        "SELECT service_id FROM doctor_services WHERE doctor_id=?",
        (doctor_id,),
    ).fetchall()
    conn.close()
    return [r["service_id"] for r in rows]


def set_doctor_services(doctor_id, service_ids):
    """Полная перезапись привязки. Пустой список = делает все услуги."""
    conn = db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM doctor_services WHERE doctor_id=?", (doctor_id,))
        if service_ids:
            conn.executemany(
                "INSERT OR IGNORE INTO doctor_services (doctor_id, service_id) VALUES (?, ?)",
                [(doctor_id, sid) for sid in service_ids],
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def doctor_makes_service(doctor_id, service_id):
    """True, если врач оказывает услугу.
    Пустой список привязок = делает все (legacy-режим)."""
    conn = db()
    rows = conn.execute(
        "SELECT service_id FROM doctor_services WHERE doctor_id=?",
        (doctor_id,),
    ).fetchall()
    conn.close()
    if not rows:
        return True
    return any(r["service_id"] == str(service_id) for r in rows)


def doctor_makes_service_batch(doctor_ids, service_id):
    """Батч-проверка: {doctor_id: True/False}. Пустой список привязок = делает все."""
    if not doctor_ids:
        return {}
    conn = db()
    placeholders = ",".join("?" * len(doctor_ids))
    rows = conn.execute(
        f"SELECT doctor_id, service_id FROM doctor_services "
        f"WHERE doctor_id IN ({placeholders})",
        list(doctor_ids),
    ).fetchall()
    conn.close()

    services_by_doctor = {}
    for r in rows:
        services_by_doctor.setdefault(r["doctor_id"], set()).add(r["service_id"])

    result = {}
    sid = str(service_id)
    for did in doctor_ids:
        if did not in services_by_doctor:
            result[did] = True  # пустой список = делает все
        else:
            result[did] = sid in services_by_doctor[did]
    return result


def list_doctors_for_service(org_id, service_id):
    """Все врачи org с флагом делает/не делает услугу.
    Возвращает Row: id, name, specialty, makes (1/0)."""
    conn = db()
    sid = str(service_id)
    rows = conn.execute(
        "SELECT d.id, d.name, d.specialty, "
        "       CASE "
        "         WHEN NOT EXISTS (SELECT 1 FROM doctor_services ds WHERE ds.doctor_id = d.id) "
        "           THEN 1 "
        "         WHEN EXISTS (SELECT 1 FROM doctor_services ds "
        "                      WHERE ds.doctor_id = d.id AND ds.service_id = ?) "
        "           THEN 1 "
        "         ELSE 0 "
        "       END AS makes "
        "FROM doctors d JOIN branches b ON b.id = d.branch_id "
        "WHERE b.org_id=? "
        "ORDER BY makes DESC, d.name",
        (sid, org_id),
    ).fetchall()
    conn.close()
    return rows


def get_doctor(did):
    conn = db()
    row = conn.execute(
        "SELECT id, branch_id, name, specialty, schedule_paused, schedule_stop_date, "
        "       photo_upload_id, education, courses, about "
        "FROM doctors WHERE id=?", (did,)
    ).fetchone()
    conn.close()
    return row


def set_doctor_photo(did, upload_id):
    """Привязывает/отвязывает фото специалиста. upload_id=None — убрать."""
    conn = db()
    conn.execute(
        "UPDATE doctors SET photo_upload_id=? WHERE id=?",
        (upload_id, did),
    )
    conn.commit()
    conn.close()


def set_doctor_schedule_stop_date(did, stop_date):
    """stop_date: 'YYYY-MM-DD' или None.
    Заодно синхронизируем legacy schedule_paused: он равен 1, если stop_date <= сегодня."""
    conn = db()
    paused = 1 if (stop_date and stop_date <= _date.today().isoformat()) else 0
    conn.execute(
        "UPDATE doctors SET schedule_stop_date=?, schedule_paused=? WHERE id=?",
        (stop_date, paused, did),
    )
    conn.commit()
    conn.close()


def update_doctor(did, name, specialty, branch_id, education=None, courses=None, about=None):
    conn = db()
    fields = ["name=?", "specialty=?", "branch_id=?"]
    params = [name, specialty, branch_id]
    if education is not None:
        fields.append("education=?")
        params.append(education)
    if courses is not None:
        fields.append("courses=?")
        params.append(courses)
    if about is not None:
        fields.append("about=?")
        params.append(about)
    params.append(did)
    conn.execute(f"UPDATE doctors SET {', '.join(fields)} WHERE id=?", params)
    conn.commit()
    conn.close()


def delete_doctor(did):
    """Удаление врача с проверками и чисткой.
    Возвращает (ok, reason)."""
    conn = db()
    try:
        active = conn.execute(
            "SELECT COUNT(*) AS n FROM history "
            "WHERE doctor_id=? AND status IN ('pending', 'confirmed')",
            (did,),
        ).fetchone()["n"]
        if active:
            return False, f"У врача есть активные записи ({active}). Отмените или перенесите их сначала."

        booked = conn.execute(
            "SELECT COUNT(*) AS n FROM slots WHERE doctor_id=? AND is_booked=1",
            (did,),
        ).fetchone()["n"]
        if booked:
            return False, f"У врача есть забронированные слоты ({booked}). Освободите их сначала."

        conn.execute("DELETE FROM slots WHERE doctor_id=?", (did,))
        conn.execute("DELETE FROM schedules WHERE doctor_id=?", (did,))
        conn.execute("DELETE FROM schedule_shifts WHERE doctor_id=?", (did,))
        conn.execute("DELETE FROM schedule_exceptions WHERE doctor_id=?", (did,))
        conn.execute("DELETE FROM doctor_services WHERE doctor_id=?", (did,))
        conn.execute("DELETE FROM doctors WHERE id=?", (did,))
        conn.commit()
        return True, None
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------- schedules ----------

def get_doctor_shifts(doctor_id):
    """Смены врача: список Row с полями
    id, branch_id, weekday, start_time, end_time, break_start, break_end."""
    conn = db()
    rows = conn.execute(
        "SELECT id, branch_id, weekday, start_time, end_time, break_start, break_end "
        "FROM schedule_shifts WHERE doctor_id=? ORDER BY weekday, start_time",
        (doctor_id,),
    ).fetchall()
    conn.close()
    return rows


def set_doctor_shifts(doctor_id, shifts):
    """Полная перезапись смен. shifts = список dict:
    {branch_id: int, weekday: 0..6, start_time: 'HH:MM', end_time: 'HH:MM',
     break_start: 'HH:MM'|None, break_end: 'HH:MM'|None}"""
    conn = db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM schedule_shifts WHERE doctor_id=?", (doctor_id,))
        now = datetime.now().isoformat()
        for s in shifts:
            conn.execute(
                "INSERT INTO schedule_shifts "
                "(doctor_id, branch_id, weekday, start_time, end_time, "
                " break_start, break_end, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (doctor_id, s["branch_id"], s["weekday"], s["start_time"], s["end_time"],
                 s.get("break_start"), s.get("break_end"), now),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# legacy-обёртки на случай, если остались вызовы (в app.py убраны, но пусть будут)
def get_doctor_schedule(doctor_id):
    return get_doctor_shifts(doctor_id)


def list_schedule_exceptions(doctor_id):
    conn = db()
    rows = conn.execute(
        "SELECT id, doctor_id, date_from, date_to, reason, created_at "
        "FROM schedule_exceptions WHERE doctor_id=? ORDER BY date_from",
        (doctor_id,),
    ).fetchall()
    conn.close()
    return rows


def get_schedule_exception(doctor_id, exc_id):
    conn = db()
    row = conn.execute(
        "SELECT id, doctor_id, date_from, date_to, reason, created_at "
        "FROM schedule_exceptions WHERE id=? AND doctor_id=?",
        (exc_id, doctor_id),
    ).fetchone()
    conn.close()
    return row


def create_schedule_exception(doctor_id, date_from, date_to, reason=""):
    conn = db()
    cur = conn.execute(
        "INSERT INTO schedule_exceptions (doctor_id, date_from, date_to, reason, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (doctor_id, date_from, date_to, reason, datetime.now().isoformat()),
    )
    eid = cur.lastrowid
    conn.commit()
    conn.close()
    return eid


def delete_schedule_exception(doctor_id, exc_id):
    conn = db()
    cur = conn.execute(
        "DELETE FROM schedule_exceptions WHERE id=? AND doctor_id=?",
        (exc_id, doctor_id),
    )
    changed = cur.rowcount > 0
    conn.commit()
    conn.close()
    return changed


# ---------- slots: автогенерация из графика ----------

def regenerate_doctor_slots(doctor_id, horizon_days=None):
    """Синхронизирует auto-слоты врача с его сменами на горизонте.

    Защита от дублей: если в какое-то время у врача уже есть booked-слот
    или ручной слот в ЛЮБОМ филиале — новый не создаётся. Это гарантирует,
    что врач не окажется в двух местах одновременно после смены графика.
    """
    conn = db()
    try:
        doc = conn.execute(
            "SELECT branch_id, schedule_stop_date FROM doctors WHERE id=?", (doctor_id,)
        ).fetchone()
        if not doc:
            return {"created": 0, "deleted": 0, "skipped_booked": 0,
                    "days_processed": 0, "days_skipped": 0, "error": "doctor_not_found"}

        shifts_rows = conn.execute(
            "SELECT branch_id, weekday, start_time, end_time, break_start, break_end "
            "FROM schedule_shifts WHERE doctor_id=?", (doctor_id,)
        ).fetchall()
        shifts_by_weekday = {}
        for r in shifts_rows:
            shifts_by_weekday.setdefault(r["weekday"], []).append({
                "branch_id": r["branch_id"],
                "start_time": r["start_time"],
                "end_time": r["end_time"],
                "break_start": r["break_start"],
                "break_end": r["break_end"],
            })

        org_id = None
        if shifts_rows:
            br = conn.execute(
                "SELECT org_id FROM branches WHERE id=?", (shifts_rows[0]["branch_id"],)
            ).fetchone()
            if br:
                org_id = br["org_id"]
        if org_id is None:
            br = conn.execute(
                "SELECT org_id FROM branches WHERE id=?", (doc["branch_id"],)
            ).fetchone()
            if br:
                org_id = br["org_id"]

        org_row = conn.execute(
            "SELECT settings FROM organizations WHERE id=?", (org_id,)
        ).fetchone() if org_id else None
        settings = {}
        if org_row and org_row["settings"]:
            try:
                settings = json.loads(org_row["settings"])
            except Exception:
                settings = {}
        step_min = int(settings.get("slot_step_min", 30) or 30)
        if horizon_days is None:
            horizon_days = int(settings.get("schedule_horizon_days", 60) or 60)
        if horizon_days < 1 or horizon_days > 365:
            horizon_days = 60

        today = _date.today()
        full_end = today + timedelta(days=horizon_days)

        stop_date_str = doc["schedule_stop_date"]
        stop_date_obj = None
        if stop_date_str:
            try:
                stop_date_obj = _date.fromisoformat(stop_date_str)
            except Exception:
                stop_date_obj = None

        generate_end = full_end
        if stop_date_obj and stop_date_obj < generate_end:
            generate_end = stop_date_obj

        to_delete_ids = []
        to_insert_rows = []
        skipped_booked = 0
        created = 0
        deleted = 0
        days_processed = 0
        days_skipped = 0

        # 1. Удалить auto+free слоты вне зоны генерации
        if generate_end < full_end and generate_end >= today - timedelta(days=1):
            cutoff_start = generate_end + timedelta(days=1)
            if cutoff_start < today:
                cutoff_start = today
            rows_beyond = conn.execute(
                "SELECT id FROM slots WHERE doctor_id=? AND auto_created=1 AND is_booked=0 "
                "AND date >= ? AND date <= ?",
                (doctor_id, cutoff_start.isoformat(), full_end.isoformat()),
            ).fetchall()
            to_delete_ids.extend(r["id"] for r in rows_beyond)
        elif generate_end < today:
            rows_beyond = conn.execute(
                "SELECT id FROM slots WHERE doctor_id=? AND auto_created=1 AND is_booked=0 "
                "AND date >= ? AND date <= ?",
                (doctor_id, today.isoformat(), full_end.isoformat()),
            ).fetchall()
            to_delete_ids.extend(r["id"] for r in rows_beyond)

        # 2. Работа внутри [today, generate_end]
        if generate_end >= today and shifts_by_weekday:
            all_slots = conn.execute(
                "SELECT id, date, time, branch_id, is_booked, auto_created FROM slots "
                "WHERE doctor_id=? AND date>=? AND date<=?",
                (doctor_id, today.isoformat(), generate_end.isoformat()),
            ).fetchall()
            slots_by_date = {}
            for r in all_slots:
                slots_by_date.setdefault(r["date"], []).append({
                    "id": r["id"], "time": r["time"], "branch_id": r["branch_id"],
                    "is_booked": r["is_booked"], "auto_created": r["auto_created"],
                })

            exceptions = conn.execute(
                "SELECT date_from, date_to FROM schedule_exceptions "
                "WHERE doctor_id=? AND date_to >= ?",
                (doctor_id, today.isoformat()),
            ).fetchall()

            def _is_exception(d):
                d_str = d.isoformat()
                for e in exceptions:
                    if e["date_from"] <= d_str <= e["date_to"]:
                        return True
                return False

            def _expected_pairs(shifts):
                result = []
                for sh in shifts:
                    try:
                        sh_h, sh_m = map(int, sh["start_time"].split(":"))
                        eh, em = map(int, sh["end_time"].split(":"))
                    except (ValueError, TypeError):
                        continue
                    start_min = sh_h * 60 + sh_m
                    end_min = eh * 60 + em
                    if end_min <= start_min:
                        continue
                    break_ranges = []
                    if sh.get("break_start") and sh.get("break_end"):
                        try:
                            bsh, bsm = map(int, sh["break_start"].split(":"))
                            beh, bem = map(int, sh["break_end"].split(":"))
                            break_ranges.append((bsh * 60 + bsm, beh * 60 + bem))
                        except (ValueError, TypeError):
                            pass
                    m = start_min
                    while m + step_min <= end_min:
                        if not any(bs <= m < be for bs, be in break_ranges):
                            hh, mm = m // 60, m % 60
                            result.append((sh["branch_id"], f"{hh:02d}:{mm:02d}"))
                        m += step_min
                return result

            num_days = (generate_end - today).days
            for offset in range(num_days + 1):
                d = today + timedelta(days=offset)
                if _is_exception(d):
                    continue
                day_shifts = shifts_by_weekday.get(d.weekday(), [])
                if not day_shifts:
                    continue

                expected = _expected_pairs(day_shifts)
                if not expected:
                    continue

                date_str = d.isoformat()
                existing = slots_by_date.get(date_str, [])
                existing_by_key = {}
                for s in existing:
                    existing_by_key[(s["branch_id"], s["time"])] = s

                # Дополнительная мапа для защиты от дубля «врач в двух местах»
                existing_by_time_any = {}
                for s in existing:
                    existing_by_time_any.setdefault(s["time"], []).append(s)

                def _locked_at(time_str):
                    for s in existing_by_time_any.get(time_str, []):
                        if s["is_booked"] or s["auto_created"] == 0:
                            return True
                    return False

                expected_set = set(expected)
                covered = all(k in existing_by_key for k in expected_set)
                no_stale = all(
                    (k in expected_set) or s["is_booked"] or (s["auto_created"] == 0)
                    for k, s in existing_by_key.items()
                )
                if covered and no_stale:
                    days_skipped += 1
                    continue

                days_processed += 1

                for k, s in existing_by_key.items():
                    if s["auto_created"] == 1 and not s["is_booked"] and k not in expected_set:
                        to_delete_ids.append(s["id"])

                for branch_id, time_str in expected:
                    k = (branch_id, time_str)
                    if k in existing_by_key:
                        if existing_by_key[k]["is_booked"]:
                            skipped_booked += 1
                        continue
                    if _locked_at(time_str):
                        # В это время у врача уже booked/manual в другом филиале —
                        # не создаём дубль. Врач не может быть в двух местах.
                        skipped_booked += 1
                        continue
                    to_insert_rows.append(
                        (org_id, branch_id, doctor_id, date_str, time_str)
                    )

        if to_delete_ids:
            placeholders = ",".join("?" * len(to_delete_ids))
            conn.execute(f"DELETE FROM slots WHERE id IN ({placeholders})", to_delete_ids)
            deleted = len(to_delete_ids)

        if to_insert_rows:
            conn.executemany(
                "INSERT OR IGNORE INTO slots "
                "(org_id, branch_id, doctor_id, date, time, auto_created) "
                "VALUES (?, ?, ?, ?, ?, 1)",
                to_insert_rows,
            )
            created = len(to_insert_rows)

        conn.commit()
        return {
            "created": created, "deleted": deleted,
            "skipped_booked": skipped_booked,
            "days_processed": days_processed, "days_skipped": days_skipped,
            "horizon_days": horizon_days,
            "stop_date": stop_date_str,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def regenerate_all_slots_for_org(org_id, horizon_days=None):
    """Пересоздаёт авто-слоты для всех врачей организации."""
    conn = db()
    doctors = conn.execute(
        "SELECT d.id FROM doctors d JOIN branches b ON b.id = d.branch_id "
        "WHERE b.org_id=?", (org_id,)
    ).fetchall()
    conn.close()

    result = {"doctors": 0, "created": 0, "deleted": 0, "skipped_booked": 0, "errors": []}
    for d in doctors:
        try:
            r = regenerate_doctor_slots(d["id"], horizon_days=horizon_days)
            if "error" in r:
                result["errors"].append({"doctor_id": d["id"], "error": r["error"]})
            else:
                result["doctors"] += 1
                result["created"] += r["created"]
                result["deleted"] += r["deleted"]
                result["skipped_booked"] += r["skipped_booked"]
        except Exception as e:
            result["errors"].append({"doctor_id": d["id"], "error": str(e)[:200]})
    return result


# ---------- slots ----------

def add_slot(org_id, branch_id, doctor_id, date, time, service_id=None):
    conn = db()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO slots (org_id, branch_id, doctor_id, date, time, service_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (org_id, branch_id, doctor_id, date, time, service_id),
        )
        conn.commit()
    finally:
        conn.close()


def list_dates_with_slots(org_id, limit_days=14):
    now_local = now_for_org(org_id)
    today = now_local.strftime("%Y-%m-%d")
    now_time = (now_local + timedelta(minutes=30)).strftime("%H:%M")
    conn = db()
    rows = conn.execute(
        "SELECT DISTINCT date FROM slots "
        "WHERE org_id=? AND is_booked=0 "
        "AND (date > ? OR (date = ? AND time >= ?)) "
        "ORDER BY date LIMIT ?",
        (org_id, today, today, now_time, limit_days),
    ).fetchall()
    conn.close()
    return [r["date"] for r in rows]


def list_free_slots(org_id, date, service_id=None):
    now_local = now_for_org(org_id)
    today = now_local.strftime("%Y-%m-%d")
    now_time = (now_local + timedelta(minutes=30)).strftime("%H:%M")
    conn = db()
    base_q = (
        "SELECT id, time, branch_id, doctor_id, service_id FROM slots "
        "WHERE org_id=? AND date=? AND is_booked=0 "
    )
    params = [org_id, date]
    if date == today:
        base_q += "AND time >= ? "; params.append(now_time)
    elif date < today:
        conn.close(); return []
    if service_id:
        base_q += "AND (service_id IS NULL OR service_id=?) "; params.append(service_id)
    base_q += "ORDER BY time"
    rows = conn.execute(base_q, params).fetchall()
    conn.close()
    return rows


def get_slot(slot_id):
    conn = db()
    row = conn.execute(
        "SELECT id, org_id, branch_id, doctor_id, date, time, is_booked, service_id "
        "FROM slots WHERE id=?", (slot_id,)
    ).fetchone()
    conn.close()
    return row


def book_slot(slot_id, request_id=None):
    conn = db()
    conn.execute(
        "UPDATE slots SET is_booked=1, request_id=? WHERE id=? AND is_booked=0",
        (request_id, slot_id),
    )
    changed = conn.total_changes
    conn.commit()
    conn.close()
    return changed > 0


def release_slot(slot_id, request_id=None):
    """Освобождает слот(ы) записи.
    Если request_id задан — освобождает все слоты из history.slot_ids
    (fallback на единственный slot_id для старых записей)."""
    conn = db()
    if request_id is None:
        conn.execute("UPDATE slots SET is_booked=0, request_id=NULL WHERE id=?", (slot_id,))
        conn.commit()
        conn.close()
        return

    hist = conn.execute(
        "SELECT slot_ids, slot_id FROM history WHERE id=?", (request_id,)
    ).fetchone()
    slot_ids_to_release = []
    if hist:
        if hist["slot_ids"]:
            try:
                slot_ids_to_release = json.loads(hist["slot_ids"])
            except Exception:
                slot_ids_to_release = []
        if not slot_ids_to_release and hist["slot_id"]:
            slot_ids_to_release = [hist["slot_id"]]
    if not slot_ids_to_release and slot_id:
        slot_ids_to_release = [slot_id]

    if slot_ids_to_release:
        placeholders = ",".join("?" * len(slot_ids_to_release))
        conn.execute(
            f"UPDATE slots SET is_booked=0, request_id=NULL "
            f"WHERE id IN ({placeholders}) AND request_id=?",
            slot_ids_to_release + [request_id],
        )
    conn.commit()
    conn.close()


def create_booking(org_id, user_id, service_name, scheduled_at, phone, address,
                   doctor, branch_id, doctor_id, slot_ids, status, service_id):
    """slot_ids — список id слотов (первый = основной). Всё занимается атомарно."""
    if not slot_ids:
        return None
    primary_slot_id = slot_ids[0]
    slots_count = len(slot_ids)
    slot_ids_json = json.dumps(slot_ids)

    conn = db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        placeholders = ",".join("?" * len(slot_ids))
        rows = conn.execute(
            f"SELECT id, is_booked FROM slots WHERE id IN ({placeholders})",
            slot_ids,
        ).fetchall()
        if len(rows) != slots_count:
            conn.rollback()
            return None
        for r in rows:
            if r["is_booked"]:
                conn.rollback()
                return None

        cur = conn.execute(
            "INSERT INTO history (org_id, user_id, service_name, scheduled_at, phone, "
            "status, address, doctor, branch_id, doctor_id, slot_id, slots_count, slot_ids, "
            "service_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (org_id, str(user_id), service_name, scheduled_at, phone,
             status, address, doctor, branch_id, doctor_id, primary_slot_id,
             slots_count, slot_ids_json, service_id,
             datetime.now().isoformat()),
        )
        rid = cur.lastrowid
        conn.execute(
            f"UPDATE slots SET is_booked=1, request_id=? WHERE id IN ({placeholders})",
            [rid] + list(slot_ids),
        )
        conn.commit()
        return rid
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def count_active_future_requests(user_id, org_id):
    now_iso = now_for_org(org_id).strftime("%Y-%m-%d %H:%M")
    conn = db()
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM history WHERE user_id=? AND org_id=? "
        "AND status IN ('pending','confirmed') AND scheduled_at >= ? AND slot_id IS NOT NULL",
        (str(user_id), org_id, now_iso),
    ).fetchone()
    conn.close()
    return row["n"] if row else 0


def count_slots_today(org_id):
    today = today_for_org(org_id)
    conn = db()
    total = conn.execute(
        "SELECT COUNT(*) AS n FROM slots WHERE org_id=? AND date=?", (org_id, today)
    ).fetchone()["n"]
    free = conn.execute(
        "SELECT COUNT(*) AS n FROM slots WHERE org_id=? AND date=? AND is_booked=0",
        (org_id, today),
    ).fetchone()["n"]
    conn.close()
    return total, free


def has_active_request_for_slot(user_id, slot_id, phone=None):
    conn = db()
    if phone:
        row = conn.execute(
            "SELECT id FROM history "
            "WHERE (user_id=? OR phone=?) AND slot_id=? "
            "AND status IN ('pending', 'confirmed')",
            (str(user_id), phone, slot_id),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT id FROM history "
            "WHERE user_id=? AND slot_id=? "
            "AND status IN ('pending', 'confirmed')",
            (str(user_id), slot_id),
        ).fetchone()
    conn.close()
    return row is not None


def has_active_request_at_time(user_id, org_id, scheduled_at, phone=None):
    """У клиента уже есть активная запись на это же время.
    Независимо от услуги, врача и слота."""
    conn = db()
    if phone:
        row = conn.execute(
            "SELECT id FROM history "
            "WHERE (user_id=? OR phone=?) AND org_id=? AND scheduled_at=? "
            "AND status IN ('pending', 'confirmed')",
            (str(user_id), phone, org_id, scheduled_at),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT id FROM history "
            "WHERE user_id=? AND org_id=? AND scheduled_at=? "
            "AND status IN ('pending', 'confirmed')",
            (str(user_id), org_id, scheduled_at),
        ).fetchone()
    conn.close()
    return row is not None


def count_active_bookings_on_date(user_id, org_id, date_str):
    """Сколько активных записей на конкретную дату (YYYY-MM-DD)."""
    conn = db()
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM history "
        "WHERE user_id=? AND org_id=? AND date(scheduled_at)=date(?) "
        "AND status IN ('pending', 'confirmed')",
        (str(user_id), org_id, date_str),
    ).fetchone()
    conn.close()
    return row["n"] if row else 0


def list_active_bookings_on_date(user_id, org_id, date_str):
    """Список активных записей клиента на дату: id, service_name, scheduled_at, doctor."""
    conn = db()
    rows = conn.execute(
        "SELECT id, service_name, scheduled_at, doctor, status "
        "FROM history "
        "WHERE user_id=? AND org_id=? AND date(scheduled_at)=date(?) "
        "AND status IN ('pending', 'confirmed') "
        "ORDER BY scheduled_at",
        (str(user_id), org_id, date_str),
    ).fetchall()
    conn.close()
    return rows


# ---------- blocked_users ----------

def block_user(user_id, org_id, phone, reason, blocked_by):
    conn = db()
    conn.execute(
        "INSERT OR REPLACE INTO blocked_users "
        "(user_id, org_id, phone, reason, blocked_by, blocked_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (str(user_id), org_id, phone or "", reason or "",
         str(blocked_by) if blocked_by else None, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def unblock_user(user_id):
    conn = db()
    conn.execute("DELETE FROM blocked_users WHERE user_id=?", (str(user_id),))
    conn.commit()
    conn.close()


def is_user_blocked(user_id):
    conn = db()
    row = conn.execute(
        "SELECT 1 FROM blocked_users WHERE user_id=?", (str(user_id),)
    ).fetchone()
    conn.close()
    return row is not None


def is_user_blocked_batch(user_ids):
    if not user_ids:
        return {}
    conn = db()
    placeholders = ",".join("?" * len(user_ids))
    rows = conn.execute(
        f"SELECT user_id FROM blocked_users WHERE user_id IN ({placeholders})",
        [str(u) for u in user_ids],
    ).fetchall()
    conn.close()
    return {r["user_id"]: True for r in rows}


def list_blocked_users(org_id=None):
    conn = db()
    if org_id is None:
        rows = conn.execute(
            "SELECT user_id, org_id, phone, reason, blocked_by, blocked_at "
            "FROM blocked_users ORDER BY blocked_at DESC"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT user_id, org_id, phone, reason, blocked_by, blocked_at "
            "FROM blocked_users WHERE org_id=? ORDER BY blocked_at DESC",
            (org_id,),
        ).fetchall()
    conn.close()
    return rows


# ---------- slots: admin panel ----------

def list_slots_range(org_id, date_from, date_to, branch_id=None, doctor_id=None):
    conn = db()
    q = (
        "SELECT s.id AS id, s.date AS date, s.time AS time, s.is_booked AS is_booked, "
        "       s.request_id AS request_id, s.branch_id AS branch_id, "
        "       s.doctor_id AS doctor_id, "
        "       h.service_name AS service_name, h.phone AS phone, h.status AS status, "
        "       c.first_name AS first_name, c.last_name AS last_name, "
        "       c.middle_name AS middle_name, "
        "       s.service_id AS service_id, "
        "       d.name AS doctor_name, "
        "       b.name AS branch_name "
        "FROM slots s "
        "LEFT JOIN history h ON h.id = s.request_id "
        "LEFT JOIN clients c ON c.user_id = h.user_id "
        "LEFT JOIN doctors d ON d.id = s.doctor_id "
        "LEFT JOIN branches b ON b.id = s.branch_id "
        "WHERE s.org_id=? AND s.date >= ? AND s.date <= ?"
    )
    params = [org_id, date_from, date_to]
    if branch_id:
        q += " AND s.branch_id=?"; params.append(branch_id)
    if doctor_id:
        q += " AND s.doctor_id=?"; params.append(doctor_id)
    q += " ORDER BY s.date, s.time"
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return rows


def create_slot(org_id, branch_id, doctor_id, date, time, service_id=None):
    if not branch_id:
        return None  # слоты без филиала запрещены
    conn = db()
    try:
        # Защита: один врач не может вести два приёма одновременно, даже
        # в разных филиалах. Проверяем по (doctor_id, date, time) без учёта филиала.
        if doctor_id:
            existing_any = conn.execute(
                "SELECT id FROM slots WHERE doctor_id=? AND date=? AND time=?",
                (doctor_id, date, time),
            ).fetchone()
            if existing_any:
                return None

        if doctor_id is None:
            existing = conn.execute(
                "SELECT id FROM slots WHERE org_id=? AND branch_id=? "
                "AND doctor_id IS NULL AND date=? AND time=?",
                (org_id, branch_id, date, time),
            ).fetchone()
            if existing:
                return None
        cur = conn.execute(
            "INSERT OR IGNORE INTO slots (org_id, branch_id, doctor_id, date, time, service_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (org_id, branch_id, doctor_id, date, time, service_id),
        )
        conn.commit()
        return cur.lastrowid if cur.rowcount else None
    finally:
        conn.close()


def delete_slot(slot_id):
    conn = db()
    row = conn.execute(
        "SELECT is_booked FROM slots WHERE id=?", (slot_id,)
    ).fetchone()
    if not row:
        conn.close(); return False
    if row["is_booked"]:
        conn.close(); return False
    conn.execute("DELETE FROM slots WHERE id=?", (slot_id,))
    conn.commit()
    conn.close()
    return True


def generate_slots_range(org_id, branch_id, doctor_id, date_from, days,
                         days_of_week, time_start, time_end, step_min,
                         service_id=None):
    if not branch_id:
        return 0  # слоты без филиала запрещены
    def _to_min(t):
        h, m = t.split(":")
        return int(h) * 60 + int(m)
    start_min = _to_min(time_start)
    end_min = _to_min(time_end)
    if end_min <= start_min or step_min <= 0:
        return 0
    try:
        d0 = _date.fromisoformat(date_from)
    except Exception:
        return 0
    created = 0
    for offset in range(days):
        d = d0 + timedelta(days=offset)
        if d.weekday() not in days_of_week:
            continue
        m = start_min
        while m + step_min <= end_min:
            hh = m // 60; mm = m % 60
            time_str = f"{hh:02d}:{mm:02d}"
            if create_slot(org_id, branch_id, doctor_id, d.isoformat(), time_str, service_id):
                created += 1
            m += step_min
    return created


# ---------- admin panel helpers ----------

def get_admin_role(uid):
    """Получить роль админа. Проверяет обе схемы: суперадмин (БД) и админ (таблица admins)."""
    # Сначала проверить суперадмина в MAX (платформа по умолчанию для ботов)
    if is_superadmin_db("max", uid):
        return ("superadmin", None, None)
    
    # Иначе проверить обычного админа
    conn = db()
    row = conn.execute(
        "SELECT a.org_id, o.name FROM admins a "
        "LEFT JOIN organizations o ON o.id = a.org_id "
        "WHERE a.user_id=?", (str(uid),)
    ).fetchone()
    conn.close()
    if not row:
        return (None, None, None)
    return ("admin", row["org_id"], row["name"])


def get_admin_role_by_platform(platform, uid):
    """Получить роль админа по платформе (max/vk).
    
    Проверяет:
    1. Суперадмин в таблице superadmins
    2. Обычный админ в таблице admins
    
    Возвращает: (role, org_id, org_name) или (None, None, None)
    """
    # Проверить суперадмина по платформе
    if is_superadmin_db(platform, uid):
        return ("superadmin", None, None)
    
    # Иначе проверить обычного админа (в таблице admins нет платформы, работает универсально)
    conn = db()
    row = conn.execute(
        "SELECT a.org_id, o.name FROM admins a "
        "LEFT JOIN organizations o ON o.id = a.org_id "
        "WHERE a.user_id=?", (str(uid),)
    ).fetchone()
    conn.close()
    if not row:
        return (None, None, None)
    return ("admin", row["org_id"], row["name"])


def list_requests_for_org(org_id, date_from=None, date_to=None,
                          status=None, page=1, per_page=20,
                          auto_done_only=False):
    conn = db()
    where = ["org_id=?"]
    params = [org_id]
    if date_from:
        where.append("date(scheduled_at) >= date(?)"); params.append(date_from)
    if date_to:
        where.append("date(scheduled_at) <= date(?)"); params.append(date_to)
    if status and status != "all":
        where.append("status=?"); params.append(status)
    if auto_done_only:
        where.append("done_auto=1")
    where_sql = " AND ".join(where)
    total = conn.execute(
        f"SELECT COUNT(*) AS n FROM history WHERE {where_sql}", params
    ).fetchone()["n"]
    offset = (page - 1) * per_page
    rows = conn.execute(
        f"SELECT id, user_id, service_id, service_name, scheduled_at, phone, status, "
        f"address, doctor, doctor_id, slot_id, created_at, actual_amount, payment_method, done_auto, "
        f"slots_count "
        f"FROM history WHERE {where_sql} "
        f"ORDER BY scheduled_at DESC LIMIT ? OFFSET ?",
        params + [per_page, offset],
    ).fetchall()
    conn.close()
    return rows, total


# ---------- reminders ----------

def get_upcoming_confirmed(org_id=None):
    conn = db()
    q = (
        "SELECT id, org_id, user_id, service_name, scheduled_at, "
        "       address, doctor, reminder_24_sent_at, reminder_2_sent_at, "
        "       reminder_24_attempts, reminder_2_attempts, "
        "       client_asked_at, client_answer "
        "FROM history WHERE status='confirmed'"
    )
    params = []
    if org_id is not None:
        q += " AND org_id=?"
        params.append(org_id)
    q += " ORDER BY scheduled_at"
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return rows


def mark_reminder_sent(request_id, kind):
    field = "reminder_24_sent_at" if kind == "24h" else "reminder_2_sent_at"
    conn = db()
    conn.execute(f"UPDATE history SET {field}=? WHERE id=?",
                 (datetime.now().isoformat(), request_id))
    conn.commit(); conn.close()


def increment_reminder_attempt(request_id, kind):
    field = "reminder_24_attempts" if kind == "24h" else "reminder_2_attempts"
    conn = db()
    conn.execute(f"UPDATE history SET {field} = COALESCE({field}, 0) + 1 WHERE id=?",
                 (request_id,))
    conn.commit(); conn.close()


# ---------- client confirm ----------

def get_pending_for_client_confirm():
    conn = db()
    rows = conn.execute(
        "SELECT id, org_id, user_id, service_name, scheduled_at, phone, "
        "       address, doctor, created_at, client_ask_attempts "
        "FROM history WHERE status='pending' AND client_asked_at IS NULL "
        "ORDER BY scheduled_at"
    ).fetchall()
    conn.close()
    return rows


def mark_client_asked(request_id):
    conn = db()
    conn.execute("UPDATE history SET client_asked_at=? WHERE id=?",
                 (datetime.now().isoformat(), request_id))
    conn.commit(); conn.close()


def increment_client_ask_attempt(request_id):
    conn = db()
    conn.execute(
        "UPDATE history SET client_ask_attempts = COALESCE(client_ask_attempts, 0) + 1 WHERE id=?",
        (request_id,),
    )
    conn.commit(); conn.close()


def set_client_answer(request_id, answer):
    conn = db()
    conn.execute("UPDATE history SET client_answer=? WHERE id=?", (answer, request_id))
    conn.commit(); conn.close()


def get_pending_timeout():
    conn = db()
    rows = conn.execute(
        "SELECT id, org_id, user_id, service_name, scheduled_at, phone, "
        "       address, doctor, client_asked_at "
        "FROM history WHERE status='pending' AND client_asked_at IS NOT NULL "
        "AND client_answer IS NULL"
    ).fetchall()
    conn.close()
    return rows


def set_broadcast_image(bid, image_id):
    conn = db()
    conn.execute(
        "UPDATE broadcasts SET image_id=? WHERE id=?",
        (image_id, bid),
    )
    conn.commit()
    conn.close()


# ---------- auto broadcasts ----------

def list_auto_broadcasts(org_id):
    conn = db()
    rows = conn.execute(
        "SELECT id, type, text, image_id, delay_value, active "
        "FROM auto_broadcasts WHERE org_id=? ORDER BY id DESC", (org_id,)
    ).fetchall()
    conn.close()
    return rows


def get_auto_broadcast(aid):
    conn = db()
    row = conn.execute(
        "SELECT id, org_id, type, text, image_id, delay_value, active "
        "FROM auto_broadcasts WHERE id=?", (aid,)
    ).fetchone()
    conn.close()
    return row


def create_auto_broadcast(org_id, atype, text, delay_value, image_id=None):
    conn = db()
    cur = conn.execute(
        "INSERT INTO auto_broadcasts (org_id, type, text, delay_value, image_id, active, created_at) "
        "VALUES (?, ?, ?, ?, ?, 1, ?)",
        (org_id, atype, text, delay_value, image_id, datetime.now().isoformat()),
    )
    aid = cur.lastrowid
    conn.commit(); conn.close()
    return aid


def update_auto_broadcast(aid, text, delay_value, image_id, active):
    conn = db()
    conn.execute(
        "UPDATE auto_broadcasts SET text=?, delay_value=?, image_id=?, active=? WHERE id=?",
        (text, delay_value, image_id, active, aid),
    )
    conn.commit(); conn.close()


def delete_auto_broadcast(aid):
    conn = db()
    conn.execute("DELETE FROM auto_broadcasts WHERE id=?", (aid,))
    conn.execute("DELETE FROM auto_broadcast_logs WHERE auto_id=?", (aid,))
    conn.commit(); conn.close()


def toggle_auto_broadcast(aid):
    conn = db()
    conn.execute("UPDATE auto_broadcasts SET active = 1 - active WHERE id=?", (aid,))
    conn.commit(); conn.close()


def log_auto_broadcast(auto_id, user_id, event_ref=None):
    conn = db()
    conn.execute(
        "INSERT INTO auto_broadcast_logs (auto_id, user_id, event_ref, sent_at) "
        "VALUES (?, ?, ?, ?)",
        (auto_id, str(user_id), event_ref, datetime.now().isoformat()),
    )
    conn.commit(); conn.close()


# ==================== Reviews ====================

def find_visits_for_review_request(org_id, delay_hours):
    """Находит done-визиты, по которым ещё не запрошен отзыв и прошло >= delay_hours.

    Один запрос на клиента: если у клиента несколько done-визитов без отзыва —
    берём самый свежий (один запрос). Остальные пропускаем (не спамим).
    """
    from datetime import datetime as _dt, timedelta as _td
    cutoff = (_dt.now() - _td(hours=delay_hours)).strftime("%Y-%m-%d %H:%M")
    lower_bound = (_dt.now() - _td(hours=delay_hours + 24 * 7)).strftime("%Y-%m-%d %H:%M")

    with db_ctx() as conn:
        rows = conn.execute(
            "SELECT h.id AS request_id, h.user_id, h.org_id, h.service_id, h.service_name, "
            "       h.doctor_id, h.scheduled_at, "
            "       c.first_name "
            "FROM history h "
            "JOIN clients c ON c.user_id = h.user_id AND c.org_id = h.org_id "
            "WHERE h.org_id=? AND h.status='done' "
            "  AND h.scheduled_at < ? AND h.scheduled_at >= ? "
            "  AND (c.marketing_opt_out IS NULL OR c.marketing_opt_out = 0) "
            "  AND h.review_requested_at IS NULL "
            "  AND NOT EXISTS (SELECT 1 FROM reviews r WHERE r.request_id = h.id) "
            "  AND NOT EXISTS ("
            "    SELECT 1 FROM history h2 "
            "    WHERE h2.user_id = h.user_id AND h2.org_id = h.org_id "
            "      AND h2.status = 'done' "
            "      AND h2.scheduled_at > h.scheduled_at "
            "      AND h2.scheduled_at < ?"
            "  ) "
            "ORDER BY h.scheduled_at DESC",
            (org_id, cutoff, lower_bound, cutoff),
        ).fetchall()
    return rows


def mark_review_requested(request_id):
    """Фиксирует, что по визиту уже отправили запрос на отзыв.
    Идемпотентно: повторный вызов не перезаписывает timestamp."""
    with db_ctx() as conn:
        conn.execute(
            "UPDATE history SET review_requested_at=? "
            "WHERE id=? AND review_requested_at IS NULL",
            (datetime.now().isoformat(), request_id),
        )
        conn.commit()


def save_review(org_id, user_id, request_id, rating, doctor_id=None, service_id=None, comment=None):
    """Сохраняет отзыв. UNIQUE(request_id) — повторный вызов ничего не сделает."""
    with db_ctx() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO reviews "
            "(org_id, user_id, request_id, doctor_id, service_id, rating, comment, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (org_id, str(user_id), request_id, doctor_id, service_id,
             int(rating), comment, datetime.now().isoformat()),
        )
        conn.commit()
        return cur.lastrowid if cur.rowcount else None


def get_review_by_request(request_id):
    conn = db()
    row = conn.execute(
        "SELECT id, org_id, user_id, request_id, doctor_id, service_id, "
        "       rating, comment, created_at, admin_notified_at, public_link_sent_at "
        "FROM reviews WHERE request_id=?",
        (request_id,),
    ).fetchone()
    conn.close()
    return row


def mark_review_admin_notified(review_id):
    with db_ctx() as conn:
        conn.execute(
            "UPDATE reviews SET admin_notified_at=? WHERE id=? AND admin_notified_at IS NULL",
            (datetime.now().isoformat(), review_id),
        )
        conn.commit()


def mark_review_public_link_sent(review_id):
    with db_ctx() as conn:
        conn.execute(
            "UPDATE reviews SET public_link_sent_at=? WHERE id=? AND public_link_sent_at IS NULL",
            (datetime.now().isoformat(), review_id),
        )
        conn.commit()


def get_client_review_stats(user_id, org_id):
    """Средний рейтинг, количество, распределение 1..5, последние 5 отзывов."""
    with db_ctx() as conn:
        agg = conn.execute(
            "SELECT COUNT(*) AS total, "
            "       AVG(rating) AS avg_rating, "
            "       SUM(CASE WHEN rating=5 THEN 1 ELSE 0 END) AS r5, "
            "       SUM(CASE WHEN rating=4 THEN 1 ELSE 0 END) AS r4, "
            "       SUM(CASE WHEN rating=3 THEN 1 ELSE 0 END) AS r3, "
            "       SUM(CASE WHEN rating=2 THEN 1 ELSE 0 END) AS r2, "
            "       SUM(CASE WHEN rating=1 THEN 1 ELSE 0 END) AS r1 "
            "FROM reviews WHERE user_id=? AND org_id=?",
            (str(user_id), org_id),
        ).fetchone()

        recent = conn.execute(
            "SELECT id, request_id, rating, comment, created_at "
            "FROM reviews WHERE user_id=? AND org_id=? "
            "ORDER BY created_at DESC LIMIT 5",
            (str(user_id), org_id),
        ).fetchall()

    total = (agg["total"] or 0) if agg else 0
    avg = (agg["avg_rating"] or 0) if agg else 0
    return {
        "total": total,
        "avg_rating": round(float(avg), 2) if avg else 0,
        "distribution": {
            "5": (agg["r5"] or 0) if agg else 0,
            "4": (agg["r4"] or 0) if agg else 0,
            "3": (agg["r3"] or 0) if agg else 0,
            "2": (agg["r2"] or 0) if agg else 0,
            "1": (agg["r1"] or 0) if agg else 0,
        },
        "recent": [
            {"id": r["id"], "request_id": r["request_id"],
             "rating": r["rating"], "comment": r["comment"] or "",
             "created_at": r["created_at"]}
            for r in recent
        ],
    }


def list_reviews(org_id, rating_filter=None, doctor_id=None, rating=None, limit=200, offset=0):
    """Список отзывов для админки.

    rating_filter: None | 'positive' (4-5) | 'negative' (1-3)
    doctor_id:     None | int — фильтр по специалисту
    rating:        None | 1..5 — точная оценка (перебивает rating_filter)
    """
    q = (
        "SELECT r.id, r.user_id, r.request_id, r.rating, r.comment, r.created_at, "
        "       c.first_name, c.last_name, c.middle_name, c.phone, "
        "       h.service_name, h.scheduled_at, h.doctor, r.doctor_id "
        "FROM reviews r "
        "LEFT JOIN clients c ON c.user_id = r.user_id AND c.org_id = r.org_id "
        "LEFT JOIN history h ON h.id = r.request_id "
        "WHERE r.org_id=? "
    )
    params = [org_id]

    if rating is not None:
        q += "AND r.rating = ? "
        params.append(int(rating))
    elif rating_filter == "positive":
        q += "AND r.rating >= 4 "
    elif rating_filter == "negative":
        q += "AND r.rating <= 3 "

    if doctor_id is not None:
        q += "AND r.doctor_id = ? "
        params.append(int(doctor_id))

    q += "ORDER BY r.created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    conn = db()
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return rows


def count_reviews(org_id):
    conn = db()
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM reviews WHERE org_id=?", (org_id,)
    ).fetchone()
    conn.close()
    return row["n"] if row else 0


# ==================== Reviews by doctor ====================

def get_doctor_review_stats(doctor_id, org_id):
    """Средний рейтинг, распределение, последние отзывы по специалисту."""
    with db_ctx() as conn:
        agg = conn.execute(
            "SELECT COUNT(*) AS total, "
            "       AVG(rating) AS avg_rating, "
            "       SUM(CASE WHEN rating=5 THEN 1 ELSE 0 END) AS r5, "
            "       SUM(CASE WHEN rating=4 THEN 1 ELSE 0 END) AS r4, "
            "       SUM(CASE WHEN rating=3 THEN 1 ELSE 0 END) AS r3, "
            "       SUM(CASE WHEN rating=2 THEN 1 ELSE 0 END) AS r2, "
            "       SUM(CASE WHEN rating=1 THEN 1 ELSE 0 END) AS r1 "
            "FROM reviews WHERE doctor_id=? AND org_id=?",
            (doctor_id, org_id),
        ).fetchone()

        recent = conn.execute(
            "SELECT r.id, r.request_id, r.rating, r.comment, r.created_at, "
            "       h.service_name, h.scheduled_at, "
            "       c.first_name, c.last_name, c.middle_name "
            "FROM reviews r "
            "LEFT JOIN history h ON h.id = r.request_id "
            "LEFT JOIN clients c ON c.user_id = r.user_id AND c.org_id = r.org_id "
            "WHERE r.doctor_id=? AND r.org_id=? "
            "ORDER BY r.created_at DESC LIMIT 10",
            (doctor_id, org_id),
        ).fetchall()

    total = (agg["total"] or 0) if agg else 0
    avg = (agg["avg_rating"] or 0) if agg else 0
    return {
        "total": total,
        "avg_rating": round(float(avg), 2) if avg else 0,
        "distribution": {
            "5": (agg["r5"] or 0) if agg else 0,
            "4": (agg["r4"] or 0) if agg else 0,
            "3": (agg["r3"] or 0) if agg else 0,
            "2": (agg["r2"] or 0) if agg else 0,
            "1": (agg["r1"] or 0) if agg else 0,
        },
        "recent": [
            {"id": r["id"], "request_id": r["request_id"],
             "rating": r["rating"], "comment": r["comment"] or "",
             "created_at": r["created_at"],
             "service_name": r["service_name"] or "",
             "scheduled_at": r["scheduled_at"] or "",
             "client_name": " ".join(p for p in [
                 r["last_name"], r["first_name"], r["middle_name"],
             ] if p).strip() or "—"}
            for r in recent
        ],
    }


def get_doctors_review_stats_batch(doctor_ids, org_id):
    """Батч-версия: {doctor_id: {total, avg_rating}}. Для бейджей и списков."""
    if not doctor_ids:
        return {}
    placeholders = ",".join("?" * len(doctor_ids))
    with db_ctx() as conn:
        rows = conn.execute(
            f"SELECT doctor_id, COUNT(*) AS total, AVG(rating) AS avg_rating "
            f"FROM reviews WHERE org_id=? AND doctor_id IN ({placeholders}) "
            f"GROUP BY doctor_id",
            [org_id] + list(doctor_ids),
        ).fetchall()
    out = {}
    for r in rows:
        out[r["doctor_id"]] = {
            "total": r["total"] or 0,
            "avg_rating": round(float(r["avg_rating"]), 2) if r["avg_rating"] else 0,
        }
    return out


def find_revisit_candidates(org_id):
    """Находит пары (клиент, услуга), которым пора напомнить о повторе.

    Условия:
    - у услуги revisit_interval_days > 0
    - последний done-визит клиента по этой услуге был >= revisit_interval_days дней назад
    - нет более свежего визита по этой услуге
    - нет активной записи на будущее (pending/confirmed) — клиент уже записан куда-то
    - клиент не отписан от маркетинга

    Сортировка — от самой «просроченной» к менее (по разнице дней).
    """
    from datetime import datetime as _dt
    now_str = _dt.now().strftime("%Y-%m-%d %H:%M")

    with db_ctx() as conn:
        rows = conn.execute(
            "SELECT h.user_id, h.service_id, h.id AS last_request_id, "
            "       h.scheduled_at AS last_visit, "
            "       s.name AS service_name, s.prep AS prep, "
            "       s.revisit_interval_days, "
            "       CAST(julianday('now', 'localtime') - julianday(h.scheduled_at) AS INTEGER) AS days_since "
            "FROM history h "
            "JOIN services s ON s.id = h.service_id AND s.revisit_interval_days > 0 "
            "JOIN clients c ON c.user_id = h.user_id AND c.org_id = h.org_id "
            "WHERE h.org_id = ? "
            "  AND h.status = 'done' "
            "  AND h.scheduled_at = ("
            "    SELECT MAX(h2.scheduled_at) FROM history h2 "
            "    WHERE h2.user_id = h.user_id AND h2.service_id = h.service_id "
            "      AND h2.org_id = h.org_id AND h2.status = 'done'"
            "  ) "
            "  AND CAST(julianday('now', 'localtime') - julianday(h.scheduled_at) AS INTEGER) >= s.revisit_interval_days "
            "  AND (c.marketing_opt_out IS NULL OR c.marketing_opt_out = 0) "
            "  AND NOT EXISTS ("
            "    SELECT 1 FROM history h3 "
            "    WHERE h3.user_id = h.user_id AND h3.org_id = h.org_id "
            "      AND h3.status IN ('pending','confirmed') "
            "      AND h3.scheduled_at >= ?"
            "  ) "
            "ORDER BY h.user_id, "
            "  (julianday('now', 'localtime') - julianday(h.scheduled_at) - s.revisit_interval_days) DESC",
            (org_id, now_str),
        ).fetchall()
    return rows


def check_auto_log_revisit(auto_id, user_id, service_id, cooldown_days=60):
    """True — уже отправляли по этой (услуге, клиенту) недавно, блокируем.

    Использует event_ref вида 'revisit:<service_id>:<request_id>' в auto_broadcast_logs.
    """
    with db_ctx() as conn:
        row = conn.execute(
            "SELECT MAX(sent_at) AS ts FROM auto_broadcast_logs "
            "WHERE auto_id=? AND user_id=? AND event_ref LIKE ?",
            (auto_id, str(user_id), f"revisit:{service_id}:%"),
        ).fetchone()
    if not row or not row["ts"]:
        return False
    try:
        from datetime import datetime as _dt
        sent_dt = _dt.fromisoformat(row["ts"])
        return (_dt.now() - sent_dt).days < cooldown_days
    except Exception:
        return True


def count_bookings_for_client_before(user_id, org_id, exclude_request_id):
    """Сколько активных/завершённых записей было у клиента в этой org
    ДО указанной записи. Cancelled не считаем."""
    conn = db()
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM history "
        "WHERE user_id=? AND org_id=? AND id != ? "
        "AND status IN ('pending', 'confirmed', 'done', 'no_show')",
        (str(user_id), org_id, exclude_request_id),
    ).fetchone()
    conn.close()
    return row["n"] if row else 0


def get_active_auto_broadcast_by_type(org_id, atype):
    """Первый активный сценарий указанного типа для организации (или None)."""
    conn = db()
    row = conn.execute(
        "SELECT id, org_id, type, text, image_id, delay_value, active "
        "FROM auto_broadcasts WHERE org_id=? AND type=? AND active=1 "
        "ORDER BY id LIMIT 1",
        (org_id, atype),
    ).fetchone()
    conn.close()
    return row


def check_auto_log_birthday(auto_id, user_id):
    current_year = datetime.now().strftime("%Y")
    conn = db()
    row = conn.execute(
        "SELECT id FROM auto_broadcast_logs "
        "WHERE auto_id=? AND user_id=? AND sent_at LIKE ?",
        (auto_id, str(user_id), f"{current_year}-%"),
    ).fetchone()
    conn.close()
    return row is not None


def check_auto_log_inactive(auto_id, user_id, last_visit_at, cooldown_days=90):
    """True — уже отправляли недавно, блокируем.

    Логика:
    - last_visit_at NULL (никогда не был): один раз за всё время.
    - last_visit_at есть:
      * отправка ДО последнего визита — клиент вернулся, шлём снова;
      * отправка ПОСЛЕ визита и с неё < cooldown_days — блокируем;
      * отправка ПОСЛЕ визита и с неё >= cooldown_days — шлём снова
        (клиент всё ещё inactive, пора напомнить).
    """
    conn = db()
    try:
        if not last_visit_at:
            row = conn.execute(
                "SELECT id FROM auto_broadcast_logs WHERE auto_id=? AND user_id=?",
                (auto_id, str(user_id)),
            ).fetchone()
            return row is not None

        last_send = conn.execute(
            "SELECT MAX(sent_at) AS ts FROM auto_broadcast_logs "
            "WHERE auto_id=? AND user_id=?",
            (auto_id, str(user_id)),
        ).fetchone()
        last_sent_at = last_send["ts"] if last_send else None

        if not last_sent_at:
            return False

        if last_sent_at <= last_visit_at:
            return False

        try:
            from datetime import datetime as _dt
            sent_dt = _dt.fromisoformat(last_sent_at)
            days_since = (_dt.now() - sent_dt).days
            return days_since < cooldown_days
        except Exception:
            return True
    finally:
        conn.close()


def check_auto_log_after_visit(auto_id, event_ref):
    conn = db()
    row = conn.execute(
        "SELECT id FROM auto_broadcast_logs WHERE auto_id=? AND event_ref=?",
        (auto_id, str(event_ref)),
    ).fetchone()
    conn.close()
    return row is not None

# ---------- broadcasts: планирование ----------

def schedule_broadcast(bid, scheduled_at):
    """Переводит draft → scheduled с датой."""
    conn = db()
    cur = conn.execute(
        "UPDATE broadcasts SET status='scheduled', scheduled_at=? "
        "WHERE id=? AND status='draft'",
        (scheduled_at, bid),
    )
    changed = cur.rowcount > 0
    conn.commit()
    conn.close()
    return changed


def unschedule_broadcast(bid):
    """Возвращает scheduled → draft (отмена планирования)."""
    conn = db()
    cur = conn.execute(
        "UPDATE broadcasts SET status='draft', scheduled_at=NULL "
        "WHERE id=? AND status='scheduled'",
        (bid,),
    )
    changed = cur.rowcount > 0
    conn.commit()
    conn.close()
    return changed


def get_scheduled_broadcasts_due(now_iso):
    """Запланированные, чьё время уже наступило."""
    conn = db()
    rows = conn.execute(
        "SELECT id, org_id, text, segment_json, image_id "
        "FROM broadcasts WHERE status='scheduled' AND scheduled_at <= ?",
        (now_iso,),
    ).fetchall()
    conn.close()
    return rows

# ---------- clients: карточка ----------

def get_client_full(user_id, org_id):
    """Полная карточка клиента + история визитов + агрегаты + услуги/специалисты/предстоящие."""
    conn = db()
    uid_str = str(user_id)

    client_row = conn.execute(
        "SELECT user_id, org_id, first_name, last_name, middle_name, phone, "
        "       gender, birth_date, last_visit_at, favorite_doctor_id, "
        "       marketing_opt_out, marketing_opt_out_at, "
        "       consent_152fz, consent_given_at, "
        "       notes, tags, no_show_count, no_show_last_at, "
        "       photo_upload_id, created_at, updated_at "
        "FROM clients WHERE user_id=?",
        (uid_str,),
    ).fetchone()

    if not client_row:
        conn.close()
        return None

    history_rows = conn.execute(
        "SELECT id, service_name, scheduled_at, status, doctor, branch_id, "
        "       actual_amount, payment_method, done_auto, slots_count "
        "FROM history WHERE user_id=? AND org_id=? "
        "ORDER BY scheduled_at DESC LIMIT 1000",
        (uid_str, org_id),
    ).fetchall()

    upcoming_rows = conn.execute(
        "SELECT id, service_name, scheduled_at, status, doctor, branch_id, "
        "       slot_id, slots_count "
        "FROM history WHERE user_id=? AND org_id=? "
        "AND status IN ('pending','confirmed') "
        "AND scheduled_at >= datetime('now') "
        "ORDER BY scheduled_at",
        (uid_str, org_id),
    ).fetchall()

    agg = conn.execute(
        "SELECT "
        "  COUNT(*) FILTER (WHERE status='done') AS visits_done, "
        "  COUNT(*) FILTER (WHERE status='no_show') AS visits_no_show, "
        "  SUM(CASE WHEN status='done' THEN COALESCE(actual_amount, 0) ELSE 0 END) AS total_revenue, "
        "  MIN(CASE WHEN status='done' THEN scheduled_at END) AS first_visit_at, "
        "  MAX(CASE WHEN status='done' THEN scheduled_at END) AS last_done_at "
        "FROM history WHERE user_id=? AND org_id=?",
        (uid_str, org_id),
    ).fetchone()

    favorite_doctor_name = None
    if client_row["favorite_doctor_id"]:
        d = conn.execute(
            "SELECT name FROM doctors WHERE id=?", (client_row["favorite_doctor_id"],)
        ).fetchone()
        if d:
            favorite_doctor_name = d["name"]

    # Группировка истории по услугам
    services_map = {}
    for r in history_rows:
        sname = r["service_name"] or "—"
        entry = services_map.get(sname)
        if not entry:
            entry = {
                "service_name": sname,
                "visits_total": 0,
                "visits_done": 0,
                "visits_no_show": 0,
                "total_amount": 0,
                "last_visit_at": None,
                "visits": [],
            }
            services_map[sname] = entry
        entry["visits_total"] += 1
        if r["status"] == "done":
            entry["visits_done"] += 1
            entry["total_amount"] += r["actual_amount"] or 0
            if not entry["last_visit_at"] or r["scheduled_at"] > entry["last_visit_at"]:
                entry["last_visit_at"] = r["scheduled_at"]
        elif r["status"] == "no_show":
            entry["visits_no_show"] += 1
        entry["visits"].append({
            "id": r["id"], "scheduled_at": r["scheduled_at"],
            "status": r["status"], "doctor": r["doctor"] or "",
            "actual_amount": r["actual_amount"],
            "payment_method": r["payment_method"] or "",
            "done_auto": bool(r["done_auto"]),
            "slots_count": r["slots_count"] or 1,
        })
    services_list = sorted(
        services_map.values(),
        key=lambda x: (x["last_visit_at"] or ""),
        reverse=True,
    )

    # Уникальные специалисты (по истории)
    specialists_map = {}
    for r in history_rows:
        doc = (r["doctor"] or "").strip()
        if not doc:
            continue
        specialists_map[doc] = specialists_map.get(doc, 0) + 1
    specialists_list = sorted(
        [{"name": k, "visits": v} for k, v in specialists_map.items()],
        key=lambda x: -x["visits"],
    )

    # Статус клиента (по настройкам org)
    settings = get_org_settings(org_id)
    at_risk_days = int(settings.get("client_at_risk_days", 30) or 30)
    inactive_days = int(settings.get("client_inactive_days", 90) or 90)
    last_done = agg["last_done_at"] if agg else None
    status_label = "never"
    if last_done:
        try:
            last_dt = datetime.fromisoformat(last_done.replace(" ", "T"))
        except Exception:
            try:
                last_dt = datetime.strptime(last_done, "%Y-%m-%d %H:%M")
            except Exception:
                last_dt = None
        if last_dt:
            days_ago = (datetime.now() - last_dt).days
            if days_ago <= at_risk_days:
                status_label = "active"
            elif days_ago <= inactive_days:
                status_label = "at_risk"
            else:
                status_label = "lost"

    photo_url = None
    if client_row["photo_upload_id"]:
        try:
            _p = conn.execute(
                "SELECT public_token FROM uploaded_images WHERE id=?",
                (client_row["photo_upload_id"],),
            ).fetchone()
            if _p and _p["public_token"]:
                photo_url = f"/max_booking/api/upload/{_p['public_token']}"
        except Exception:
            pass

    conn.close()

    return {
        "client": client_row,
        "history": history_rows,
        "upcoming": upcoming_rows,
        "aggregates": agg,
        "favorite_doctor_name": favorite_doctor_name,
        "services_list": services_list,
        "specialists_list": specialists_list,
        "status_label": status_label,
        "photo_url": photo_url,
    }


def set_client_photo(user_id, upload_id):
    """Привязывает/отвязывает фото клиента. upload_id=None — убрать фото."""
    conn = db()
    conn.execute(
        "UPDATE clients SET photo_upload_id=?, updated_at=? WHERE user_id=?",
        (upload_id, datetime.now().isoformat(), str(user_id)),
    )
    conn.commit()
    conn.close()


def update_client_notes_tags(user_id, notes, tags):
    """Обновляет заметки и теги. tags — список строк (сохраняется как JSON)."""
    import json as _json
    conn = db()
    tags_json = _json.dumps(tags or [], ensure_ascii=False)
    conn.execute(
        "UPDATE clients SET notes=?, tags=?, updated_at=? WHERE user_id=?",
        (notes or "", tags_json, datetime.now().isoformat(), str(user_id)),
    )
    conn.commit()
    conn.close()


def reset_client_no_show(user_id):
    conn = db()
    conn.execute(
        "UPDATE clients SET no_show_count=0, no_show_last_at=NULL, updated_at=? "
        "WHERE user_id=?",
        (datetime.now().isoformat(), str(user_id)),
    )
    conn.commit()
    conn.close()


def get_client_no_show_count(user_id):
    conn = db()
    row = conn.execute(
        "SELECT COALESCE(no_show_count, 0) AS n FROM clients WHERE user_id=?",
        (str(user_id),),
    ).fetchone()
    conn.close()
    return row["n"] if row else 0

def update_booking_extended(request_id, new_service_id, new_service_name,
                            new_slots_count, step_min):
    """Изменяет услугу и/или количество слотов для существующей записи.

    Атомарно: освобождает лишние старые слоты, занимает новые подряд
    от того же первого слота (doctor_id, branch_id, date, time — не меняются).

    Возвращает (ok: bool, error_code: str|None, msg: str|None, payload: dict|None).
    """
    import json as _json
    conn = db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        req = conn.execute(
            "SELECT id, org_id, user_id, service_id, slot_id, slot_ids, slots_count, "
            "       branch_id, doctor_id, scheduled_at, status "
            "FROM history WHERE id=?",
            (request_id,),
        ).fetchone()
        if not req:
            conn.rollback()
            return False, "request_not_found", None, None
        if req["status"] not in ("pending", "confirmed"):
            conn.rollback()
            return False, "request_not_active", "Редактировать можно только активную запись", None

        own_rows = conn.execute(
            "SELECT id FROM slots WHERE request_id=? ORDER BY date, time",
            (request_id,),
        ).fetchall()
        old_slot_ids = [r["id"] for r in own_rows]

        if not old_slot_ids:
            # fallback для записей, которые не имеют ни одного слота с нашим request_id
            if req["slot_ids"]:
                try:
                    old_slot_ids = _json.loads(req["slot_ids"])
                except Exception:
                    old_slot_ids = []
            if not old_slot_ids and req["slot_id"]:
                old_slot_ids = [req["slot_id"]]

        first_slot_id = old_slot_ids[0] if old_slot_ids else req["slot_id"]
        if not first_slot_id:
            conn.rollback()
            return False, "no_first_slot", "У записи нет слота", None

        slot = conn.execute(
            "SELECT id, date, time, doctor_id, branch_id FROM slots WHERE id=?",
            (first_slot_id,),
        ).fetchone()
        if not slot:
            conn.rollback()
            return False, "first_slot_missing", "Первый слот не найден", None

        h, m = map(int, slot["time"].split(":"))
        start_min = h * 60 + m
        date_str = slot["date"]

        log.info(
            "update_booking_extended: request=%s requested_slots=%s step_min=%s first=%s %s",
            request_id, new_slots_count, step_min, date_str, slot["time"],
        )
        new_slot_ids = [first_slot_id]
        for i in range(1, new_slots_count):
            target_min = start_min + i * step_min
            if target_min >= 24 * 60:
                conn.rollback()
                log.info("update_booking_extended: stop at %02d:%02d (past midnight)", target_min // 60, target_min % 60)
                return (
                    False,
                    "slots_exceed_day",
                    f"Слоты выходят за границу дня. Максимум {i} слотов подряд.",
                    None,
                )
            target_time = f"{target_min // 60:02d}:{target_min % 60:02d}"
            r = conn.execute(
                "SELECT id, is_booked, request_id FROM slots "
                "WHERE date=? AND time=? AND doctor_id IS ? AND branch_id IS ?",
                (date_str, target_time, slot["doctor_id"], slot["branch_id"]),
            ).fetchone()
            if not r:
                later = conn.execute(
                    "SELECT id FROM slots "
                    "WHERE date=? AND doctor_id IS ? AND branch_id IS ? AND time > ? "
                    "ORDER BY time LIMIT 1",
                    (date_str, slot["doctor_id"], slot["branch_id"], target_time),
                ).fetchone()
                conn.rollback()
                if later:
                    log.info("update_booking_extended: break at %s (next exists)", target_time)
                    return (
                        False,
                        "slot_break",
                        (
                            f"Перерыв в расписании: слота на {target_time} нет. "
                            f"Максимум {i} слотов подряд. Для приёма после перерыва "
                            f"создайте отдельную запись."
                        ),
                        None,
                    )
                log.info("update_booking_extended: slot %s missing (end of day)", target_time)
                return (
                    False,
                    "slot_missing",
                    f"Слот на {target_time} отсутствует. Максимум {i} слотов подряд.",
                    None,
                )
            if r["is_booked"] and r["request_id"] != request_id:
                conn.rollback()
                log.info("update_booking_extended: slot %s busy (req=%s)", target_time, r["request_id"])
                return (
                    False,
                    "slot_busy",
                    f"Слот на {target_time} занят другой записью. Максимум {i} слотов подряд.",
                    None,
                )
            new_slot_ids.append(r["id"])
        log.info("update_booking_extended: occupied slots %s", len(new_slot_ids))

        to_release = [sid for sid in old_slot_ids if sid not in new_slot_ids]
        if to_release:
            ph = ",".join("?" * len(to_release))
            conn.execute(
                f"UPDATE slots SET is_booked=0, request_id=NULL "
                f"WHERE id IN ({ph}) AND request_id=?",
                to_release + [request_id],
            )

        to_book = [sid for sid in new_slot_ids if sid not in old_slot_ids]
        if to_book:
            ph = ",".join("?" * len(to_book))
            conn.execute(
                f"UPDATE slots SET is_booked=1, request_id=? WHERE id IN ({ph})",
                [request_id] + to_book,
            )

        conn.execute(
            "UPDATE history SET service_id=?, service_name=?, "
            "slot_id=?, slot_ids=?, slots_count=? WHERE id=?",
            (new_service_id, new_service_name, new_slot_ids[0],
             _json.dumps(new_slot_ids), len(new_slot_ids), request_id),
        )

        conn.commit()
        return True, None, None, {
            "request_id": request_id,
            "slot_ids": new_slot_ids,
            "slots_count": len(new_slot_ids),
            "service_id": new_service_id,
            "service_name": new_service_name,
        }
    except Exception as e:
        conn.rollback()
        return False, "exception", str(e)[:200], None
    finally:
        conn.close()


def move_booking(request_id, new_slot_id):
    """Переносит заявку на новый слот. Атомарно: освобождает старые слоты,
    занимает новые, обновляет историю. Возвращает (ok, error, payload)."""
    import json as _json
    conn = db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        req = conn.execute(
            "SELECT id, org_id, user_id, service_id, slot_id, slot_ids, slots_count, "
            "       scheduled_at, branch_id, doctor_id, status "
            "FROM history WHERE id=?",
            (request_id,),
        ).fetchone()
        if not req:
            conn.rollback()
            return False, "request_not_found", None
        if req["status"] not in ("pending", "confirmed"):
            conn.rollback()
            return False, "request_not_active", None

        new_slot = conn.execute(
            "SELECT id, org_id, branch_id, doctor_id, date, time, is_booked, service_id "
            "FROM slots WHERE id=?",
            (new_slot_id,),
        ).fetchone()
        if not new_slot:
            conn.rollback()
            return False, "slot_not_found", None
        if new_slot["org_id"] != req["org_id"]:
            conn.rollback()
            return False, "slot_other_org", None
        if new_slot["is_booked"]:
            conn.rollback()
            return False, "slot_booked", None
        if new_slot["service_id"] and new_slot["service_id"] != req["service_id"]:
            conn.rollback()
            return False, "slot_other_service", None

        # Освободить старые слоты
        old_ids = []
        if req["slot_ids"]:
            try:
                old_ids = _json.loads(req["slot_ids"])
            except Exception:
                old_ids = []
        if not old_ids and req["slot_id"]:
            old_ids = [req["slot_id"]]
        if old_ids:
            ph = ",".join("?" * len(old_ids))
            conn.execute(
                f"UPDATE slots SET is_booked=0, request_id=NULL "
                f"WHERE id IN ({ph}) AND request_id=?",
                old_ids + [request_id],
            )

        conn.commit()
        return True, None, {
            "old_slot_ids": old_ids,
            "new_slot": dict(new_slot),
        }
    except Exception as e:
        conn.rollback()
        return False, f"exception: {e}", None
    finally:
        conn.close()


def finalize_move_booking(request_id, new_slot_ids, new_scheduled_at,
                          new_branch_id, new_doctor_id, new_address, new_doctor):
    """Обновляет history после move_booking и занимает новые слоты."""
    import json as _json
    conn = db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        ids_json = _json.dumps(new_slot_ids)
        primary = new_slot_ids[0] if new_slot_ids else None
        conn.execute(
            "UPDATE history SET scheduled_at=?, slot_id=?, slot_ids=?, slots_count=?, "
            "branch_id=?, doctor_id=?, address=?, doctor=? WHERE id=?",
            (new_scheduled_at, primary, ids_json, len(new_slot_ids),
             new_branch_id, new_doctor_id, new_address, new_doctor, request_id),
        )
        ph = ",".join("?" * len(new_slot_ids))
        conn.execute(
            f"UPDATE slots SET is_booked=1, request_id=? WHERE id IN ({ph})",
            [request_id] + list(new_slot_ids),
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

# ==================== Лист ожидания ====================

def create_waitlist_entry(org_id, user_id, service_id, date_from, date_to,
                          doctor_id=None, branch_id=None,
                          preferred_time=None, notes=None, created_by=None):
    with db_ctx() as conn:
        cur = conn.execute(
            "INSERT INTO waitlist "
            "(org_id, user_id, service_id, doctor_id, branch_id, "
            " date_from, date_to, preferred_time, status, notes, created_by, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)",
            (org_id, str(user_id), service_id, doctor_id, branch_id,
             date_from, date_to, preferred_time, notes,
             str(created_by) if created_by else None,
             datetime.now().isoformat()),
        )
        wid = cur.lastrowid
        conn.commit()
        return wid


def get_waitlist_entry(wid):
    conn = db()
    row = conn.execute(
        "SELECT w.*, s.name AS service_name, d.name AS doctor_name, "
        "       b.name AS branch_name "
        "FROM waitlist w "
        "LEFT JOIN services s ON s.id = w.service_id "
        "LEFT JOIN doctors d ON d.id = w.doctor_id "
        "LEFT JOIN branches b ON b.id = w.branch_id "
        "WHERE w.id=?",
        (wid,),
    ).fetchone()
    conn.close()
    return row


def list_waitlist(org_id, status=None, service_id=None, doctor_id=None,
                  branch_id=None, limit=200, offset=0):
    q = (
        "SELECT w.*, s.name AS service_name, d.name AS doctor_name, "
        "       b.name AS branch_name, "
        "       c.last_name, c.first_name, c.middle_name, c.phone "
        "FROM waitlist w "
        "LEFT JOIN services s ON s.id = w.service_id "
        "LEFT JOIN doctors d ON d.id = w.doctor_id "
        "LEFT JOIN branches b ON b.id = w.branch_id "
        "LEFT JOIN clients c ON c.user_id = w.user_id AND c.org_id = w.org_id "
        "WHERE w.org_id=? "
    )
    params = [org_id]
    if status:
        q += "AND w.status=? "
        params.append(status)
    if service_id:
        q += "AND w.service_id=? "
        params.append(service_id)
    if doctor_id:
        q += "AND w.doctor_id=? "
        params.append(doctor_id)
    if branch_id:
        q += "AND w.branch_id=? "
        params.append(branch_id)
    q += "ORDER BY w.created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    conn = db()
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return rows


def list_active_waitlist_for_user(org_id, user_id):
    conn = db()
    rows = conn.execute(
        "SELECT w.*, s.name AS service_name, d.name AS doctor_name, "
        "       b.name AS branch_name "
        "FROM waitlist w "
        "LEFT JOIN services s ON s.id = w.service_id "
        "LEFT JOIN doctors d ON d.id = w.doctor_id "
        "LEFT JOIN branches b ON b.id = w.branch_id "
        "WHERE w.org_id=? AND w.user_id=? AND w.status='active' "
        "ORDER BY w.created_at DESC",
        (org_id, str(user_id)),
    ).fetchall()
    conn.close()
    return rows


def update_waitlist_entry(wid, **fields):
    allowed = {"service_id", "doctor_id", "branch_id", "date_from",
               "date_to", "preferred_time", "notes", "status"}
    sets = []
    params = []
    for k, v in fields.items():
        if k in allowed:
            sets.append(f"{k}=?")
            params.append(v)
    if not sets:
        return
    params.append(wid)
    with db_ctx() as conn:
        conn.execute(f"UPDATE waitlist SET {', '.join(sets)} WHERE id=?", params)
        conn.commit()


def cancel_waitlist_entry(wid):
    log.info("cancel_waitlist_entry: wid=%s", wid)
    with db_ctx() as conn:
        conn.execute(
            "UPDATE waitlist SET status='cancelled' WHERE id=? AND status='active'",
            (wid,),
        )
        conn.commit()


def fulfill_waitlist_entry(wid, request_id):
    with db_ctx() as conn:
        conn.execute(
            "UPDATE waitlist SET status='fulfilled', fulfilled_request_id=?, fulfilled_at=? "
            "WHERE id=? AND status='active'",
            (request_id, datetime.now().isoformat(), wid),
        )
        conn.commit()


def find_waitlist_matches_for_slot(org_id, slot_id):
    """Находит активные заявки листа ожидания, подходящие под слот.

    Матчинг:
    - слот с конкретной услугой подходит заявке, если у неё:
      * та же услуга, или
      * услуга не указана (клиент ищет любого специалиста / «к специалисту»)
    - универсальный слот (service_id IS NULL) подходит ЛЮБОЙ заявке
      (клиент выберет услугу при записи).
    - doctor_id: заявка без врача → любой слот; с врачом → только его слоты.
    - branch_id: аналогично.

    Не возвращает заявки, по которым уже есть отправленный (sent) оффер
    моложе slot_backfill_sent_ttl_hours — то есть клиент получил предложение,
    но ещё не ответил.

    Pending-офферы не блокируют: это значит, что если несколько слотов
    освободились в пределах окна batch_minutes, все они попадут в один batch
    и клиент получит одно сообщение со списком.
    """
    conn = db()
    slot = conn.execute(
        "SELECT s.id, s.org_id, s.date, s.time, s.doctor_id, "
        "       s.service_id AS service_id, "
        "       s.branch_id AS branch_id "
        "FROM slots s "
        "WHERE s.id=? AND s.org_id=?",
        (slot_id, org_id),
    ).fetchone()
    conn.close()
    if not slot:
        return []

    settings = get_org_settings(org_id) or {}
    sent_ttl = int(settings.get("slot_backfill_sent_ttl_hours", 24) or 24)

    # Блокируем только «свежий sent» (клиент уже получил предложение и не ответил).
    # Pending не блокирует — иначе близкие по времени слоты попадут в разные батчи.
    conn = db()
    rows = conn.execute(
        "SELECT w.* "
        "FROM waitlist w "
        "WHERE w.org_id = ? "
        "  AND w.status = 'active' "
        "  AND (w.service_id IS NULL OR ? IS NULL OR w.service_id = ?) "
        "  AND w.date_from <= ? "
        "  AND w.date_to >= ? "
        "  AND (w.doctor_id IS NULL OR w.doctor_id = ?) "
        "  AND (w.branch_id IS NULL OR w.branch_id = ?) "
        "  AND NOT EXISTS ("
        "    SELECT 1 FROM slot_offers o "
        "    WHERE o.waitlist_id = w.id "
        "      AND o.status = 'sent' "
        "      AND datetime(o.sent_at) > datetime('now', 'localtime', ?) "
        "  ) "
        "ORDER BY w.created_at ASC",
        (org_id, slot["service_id"], slot["service_id"],
         slot["date"], slot["date"],
         slot["doctor_id"], slot["branch_id"],
         f"-{sent_ttl} hours"),
    ).fetchall()
    conn.close()
    return rows


def mark_waitlist_notified(wid, slot_id):
    with db_ctx() as conn:
        conn.execute(
            "UPDATE waitlist SET "
            "  notified_at=?, "
            "  notified_count = notified_count + 1, "
            "  last_notified_slot_id=? "
            "WHERE id=?",
            (datetime.now().isoformat(), slot_id, wid),
        )
        conn.commit()


def expire_old_waitlist_entries(org_id=None):
    """Помечает expired все активные заявки, у которых date_to < сегодня."""
    today = datetime.now().strftime("%Y-%m-%d")
    with db_ctx() as conn:
        if org_id:
            cur = conn.execute(
                "UPDATE waitlist SET status='expired' "
                "WHERE status='active' AND date_to < ? AND org_id=?",
                (today, org_id),
            )
        else:
            cur = conn.execute(
                "UPDATE waitlist SET status='expired' "
                "WHERE status='active' AND date_to < ?",
                (today,),
            )
        n = cur.rowcount
        conn.commit()
        return n


# ==================== Slot offers (backfill) ====================

def create_slot_offer(org_id, slot_id, user_id, kind,
                      original_request_id=None, waitlist_id=None,
                      status="sent"):
    with db_ctx() as conn:
        cur = conn.execute(
            "INSERT INTO slot_offers "
            "(org_id, slot_id, user_id, original_request_id, kind, "
            " waitlist_id, status, sent_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (org_id, slot_id, str(user_id), original_request_id, kind,
             waitlist_id, status, datetime.now().isoformat()),
        )
        oid = cur.lastrowid
        conn.commit()
        return oid


def get_slot_offer(oid):
    conn = db()
    row = conn.execute("SELECT * FROM slot_offers WHERE id=?", (oid,)).fetchone()
    conn.close()
    return row


def list_slot_offers_for_slot(slot_id, status=None):
    q = "SELECT * FROM slot_offers WHERE slot_id=?"
    params = [slot_id]
    if status:
        q += " AND status=?"
        params.append(status)
    conn = db()
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return rows


def count_user_offers_since(user_id, kind, since_iso):
    conn = db()
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM slot_offers "
        "WHERE user_id=? AND kind=? AND sent_at >= ?",
        (str(user_id), kind, since_iso),
    ).fetchone()
    conn.close()
    return row["n"] if row else 0


def update_slot_offer_status(oid, status, error=None):
    with db_ctx() as conn:
        conn.execute(
            "UPDATE slot_offers SET status=?, responded_at=?, error=? WHERE id=?",
            (status, datetime.now().isoformat(), error, oid),
        )
        conn.commit()


def mark_other_offers_taken(slot_id, exclude_offer_id):
    """Все остальные 'sent' по этому слоту → 'taken' (слот уже занят)."""
    with db_ctx() as conn:
        conn.execute(
            "UPDATE slot_offers SET status='taken', responded_at=? "
            "WHERE slot_id=? AND status='sent' AND id != ?",
            (datetime.now().isoformat(), slot_id, exclude_offer_id),
        )
        conn.commit()


# ==================== Аналитика ====================

def _period_bounds(d_from, d_to):
    """Возвращает (start_str, end_str) для WHERE scheduled_at BETWEEN."""
    return (f"{d_from.isoformat()} 00:00", f"{d_to.isoformat()} 23:59")


def _compute_period_metrics(org_id, d_from, d_to, branch_id=None, doctor_id=None):
    start_str, end_str = _period_bounds(d_from, d_to)

    where = ["org_id=?", "scheduled_at >= ?", "scheduled_at <= ?"]
    params = [org_id, start_str, end_str]
    if branch_id:
        where.append("branch_id=?")
        params.append(branch_id)
    if doctor_id:
        where.append("doctor_id=?")
        params.append(doctor_id)
    where_sql = " AND ".join(where)

    with db_ctx() as conn:
        agg = conn.execute(
            f"SELECT "
            f"  COUNT(*) AS total, "
            f"  SUM(CASE WHEN status='done' THEN 1 ELSE 0 END) AS done, "
            f"  SUM(CASE WHEN status='no_show' THEN 1 ELSE 0 END) AS no_show, "
            f"  SUM(CASE WHEN status='cancelled' THEN 1 ELSE 0 END) AS cancelled, "
            f"  SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) AS pending, "
            f"  SUM(CASE WHEN status='confirmed' THEN 1 ELSE 0 END) AS confirmed, "
            f"  SUM(CASE WHEN status='done' THEN COALESCE(actual_amount, 0) ELSE 0 END) AS revenue "
            f"FROM history WHERE {where_sql}",
            params,
        ).fetchone()

        unique = conn.execute(
            f"SELECT COUNT(DISTINCT user_id) AS n "
            f"FROM history WHERE {where_sql}",
            params,
        ).fetchone()["n"] or 0

        new_clients = conn.execute(
            f"SELECT COUNT(DISTINCT user_id) AS n FROM history "
            f"WHERE {where_sql} AND status='done' "
            f"AND user_id NOT IN ("
            f"  SELECT DISTINCT user_id FROM history "
            f"  WHERE org_id=? AND status='done' AND scheduled_at < ?"
            f")",
            params + [org_id, start_str],
        ).fetchone()["n"] or 0

    slot_where = ["org_id=?", "date >= ?", "date <= ?"]
    slot_params = [org_id, d_from.isoformat(), d_to.isoformat()]
    if branch_id:
        slot_where.append("branch_id=?")
        slot_params.append(branch_id)
    if doctor_id:
        slot_where.append("doctor_id=?")
        slot_params.append(doctor_id)
    slot_where_sql = " AND ".join(slot_where)

    with db_ctx() as conn:
        slots_info = conn.execute(
            f"SELECT "
            f"  COUNT(*) AS total_slots, "
            f"  SUM(CASE WHEN is_booked=1 THEN 1 ELSE 0 END) AS booked_slots "
            f"FROM slots WHERE {slot_where_sql}",
            slot_params,
        ).fetchone()

    total = agg["total"] or 0
    done = agg["done"] or 0
    no_show = agg["no_show"] or 0
    revenue = agg["revenue"] or 0
    total_slots = slots_info["total_slots"] or 0
    booked_slots = slots_info["booked_slots"] or 0

    avg_check_per_visit = round(revenue / done, 2) if done > 0 else 0
    avg_revenue_per_client = round(revenue / unique, 2) if unique > 0 else 0
    avg_service_price = round(revenue / done, 2) if done > 0 else 0  # см. ниже про сервисную цену
    no_show_pct = round(no_show / total * 100, 1) if total > 0 else 0
    load_pct = round(booked_slots / total_slots * 100, 1) if total_slots > 0 else 0
    returning = max(0, unique - new_clients)
    returning_rate_pct = round(returning / unique * 100, 1) if unique > 0 else 0

    return {
        "total": total,
        "done": done,
        "no_show": no_show,
        "cancelled": agg["cancelled"] or 0,
        "pending": agg["pending"] or 0,
        "confirmed": agg["confirmed"] or 0,
        "revenue": revenue,
        "avg_check": avg_check_per_visit,  # legacy-поле, оставляем для совместимости
        "avg_check_per_visit": avg_check_per_visit,
        "avg_revenue_per_client": avg_revenue_per_client,
        "avg_service_price": avg_service_price,
        "no_show_pct": no_show_pct,
        "load_pct": load_pct,
        "total_slots": total_slots,
        "booked_slots": booked_slots,
        "unique_clients": unique,
        "new_clients": new_clients,
        "returning_clients": returning,
        "returning_rate_pct": returning_rate_pct,
    }


def _top_services(org_id, d_from, d_to, branch_id=None, doctor_id=None, limit=10):
    start_str, end_str = _period_bounds(d_from, d_to)

    where = ["org_id=?", "scheduled_at >= ?", "scheduled_at <= ?", "status='done'"]
    params = [org_id, start_str, end_str]
    if branch_id:
        where.append("branch_id=?")
        params.append(branch_id)
    if doctor_id:
        where.append("doctor_id=?")
        params.append(doctor_id)
    where_sql = " AND ".join(where)

    with db_ctx() as conn:
        rows = conn.execute(
            f"SELECT service_id, service_name, "
            f"       COUNT(*) AS cnt, "
            f"       SUM(COALESCE(actual_amount, 0)) AS revenue "
            f"FROM history WHERE {where_sql} "
            f"GROUP BY service_id, service_name "
            f"ORDER BY cnt DESC LIMIT ?",
            params + [limit],
        ).fetchall()

    return [
        {"service_id": r["service_id"],
         "name": r["service_name"] or "—",
         "count": r["cnt"],
         "revenue": r["revenue"] or 0}
        for r in rows
    ]


def _top_doctors(org_id, d_from, d_to, branch_id=None, doctor_id=None, limit=10):
    start_str, end_str = _period_bounds(d_from, d_to)

    where = ["org_id=?", "scheduled_at >= ?", "scheduled_at <= ?",
             "status='done'", "doctor IS NOT NULL", "doctor != ''"]
    params = [org_id, start_str, end_str]
    if branch_id:
        where.append("branch_id=?")
        params.append(branch_id)
    if doctor_id:
        where.append("doctor_id=?")
        params.append(doctor_id)
    where_sql = " AND ".join(where)

    with db_ctx() as conn:
        rows = conn.execute(
            f"SELECT doctor_id, doctor, "
            f"       COUNT(*) AS cnt, "
            f"       SUM(COALESCE(actual_amount, 0)) AS revenue "
            f"FROM history WHERE {where_sql} "
            f"GROUP BY doctor_id, doctor "
            f"ORDER BY cnt DESC LIMIT ?",
            params + [limit],
        ).fetchall()

    result = [
        {"doctor_id": r["doctor_id"],
         "name": r["doctor"] or "—",
         "count": r["cnt"],
         "revenue": r["revenue"] or 0,
         "avg_rating": 0,
         "reviews_count": 0}
        for r in rows
    ]
    doc_ids = [it["doctor_id"] for it in result if it["doctor_id"]]
    if doc_ids:
        stats = get_doctors_review_stats_batch(doc_ids, org_id)
        for it in result:
            s = stats.get(it["doctor_id"]) or {}
            it["avg_rating"] = s.get("avg_rating", 0)
            it["reviews_count"] = s.get("total", 0)
    return result


def get_analytics_daily_series(org_id, date_from, date_to, branch_id=None, doctor_id=None):
    """Дневная серия: по каждому дню периода — визиты, выручка, неявки.

    Используется только для графика в XLSX-экспорте (в Mini App не выводим).
    """
    d_from = _date.fromisoformat(date_from)
    d_to = _date.fromisoformat(date_to)

    where = ["org_id=?", "scheduled_at >= ?", "scheduled_at <= ?"]
    params = [org_id, f"{date_from} 00:00", f"{date_to} 23:59"]
    if branch_id:
        where.append("branch_id=?")
        params.append(branch_id)
    if doctor_id:
        where.append("doctor_id=?")
        params.append(doctor_id)
    where_sql = " AND ".join(where)

    with db_ctx() as conn:
        rows = conn.execute(
            f"SELECT date(scheduled_at) AS d, "
            f"       SUM(CASE WHEN status='done' THEN 1 ELSE 0 END) AS done, "
            f"       SUM(CASE WHEN status='no_show' THEN 1 ELSE 0 END) AS no_show, "
            f"       SUM(CASE WHEN status='done' THEN COALESCE(actual_amount, 0) ELSE 0 END) AS revenue "
            f"FROM history WHERE {where_sql} "
            f"GROUP BY date(scheduled_at)",
            params,
        ).fetchall()

    by_day = {r["d"]: r for r in rows}
    series = []
    cur = d_from
    while cur <= d_to:
        key = cur.isoformat()
        r = by_day.get(key)
        series.append({
            "date": key,
            "done": r["done"] if r else 0,
            "no_show": r["no_show"] if r else 0,
            "revenue": r["revenue"] if r else 0,
        })
        cur += timedelta(days=1)
    return series


def get_analytics_summary(org_id, date_from, date_to, branch_id=None, doctor_id=None):
    """Сводка по метрикам за период + сравнение с предыдущим периодом той же длины.

    date_from, date_to — 'YYYY-MM-DD' (включительно).
    Возвращает dict с current / previous / delta / top_services / top_doctors.
    """
    d_from = _date.fromisoformat(date_from)
    d_to = _date.fromisoformat(date_to)
    days = (d_to - d_from).days + 1

    prev_to = d_from - timedelta(days=1)
    prev_from = prev_to - timedelta(days=days - 1)

    current = _compute_period_metrics(org_id, d_from, d_to, branch_id, doctor_id)
    previous = _compute_period_metrics(org_id, prev_from, prev_to, branch_id, doctor_id)

    def pct(cur, prev):
        if not prev:
            return None
        return round((cur - prev) / prev * 100, 1)

    def pp(cur, prev):
        # percentage points — для процентных метрик
        if prev is None:
            return None
        return round(cur - prev, 1)

    delta = {
        "total_pct": pct(current["total"], previous["total"]),
        "done_pct": pct(current["done"], previous["done"]),
        "revenue_pct": pct(current["revenue"], previous["revenue"]),
        "avg_check_pct": pct(current["avg_check"], previous["avg_check"]),
        "no_show_pct_pp": pp(current["no_show_pct"], previous["no_show_pct"]) if previous["total"] else None,
        "load_pct_pp": pp(current["load_pct"], previous["load_pct"]) if previous["total_slots"] else None,
        "new_clients_pct": pct(current["new_clients"], previous["new_clients"]),
    }

    return {
        "period": {
            "date_from": date_from,
            "date_to": date_to,
            "days": days,
        },
        "previous_period": {
            "date_from": prev_from.isoformat(),
            "date_to": prev_to.isoformat(),
        },
        "filters": {
            "branch_id": branch_id,
            "doctor_id": doctor_id,
        },
        "current": current,
        "previous": previous,
        "delta": delta,
        "top_services": _top_services(org_id, d_from, d_to, branch_id, doctor_id, limit=10),
        "top_doctors": _top_doctors(org_id, d_from, d_to, branch_id, doctor_id, limit=10),
    }


def get_analytics_doctor_summary(org_id, doctor_id, date_from, date_to):
    """Сводка по одному специалисту за период (для модалки в аналитике).

    Возвращает: period, current (метрики), top_services.
    - new_clients: у кого первый done-визит К ЭТОМУ СПЕЦИАЛИСТУ попал в период.
    - load_pct: booked_slots / total_slots за период.
    """
    d_from = _date.fromisoformat(date_from)
    d_to = _date.fromisoformat(date_to)
    days = (d_to - d_from).days + 1

    start_str = f"{date_from} 00:00"
    end_str = f"{date_to} 23:59"

    with db_ctx() as conn:
        agg = conn.execute(
            "SELECT "
            "  COUNT(*) AS total, "
            "  SUM(CASE WHEN status='done' THEN 1 ELSE 0 END) AS done, "
            "  SUM(CASE WHEN status='no_show' THEN 1 ELSE 0 END) AS no_show, "
            "  SUM(CASE WHEN status='cancelled' THEN 1 ELSE 0 END) AS cancelled, "
            "  SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) AS pending, "
            "  SUM(CASE WHEN status='confirmed' THEN 1 ELSE 0 END) AS confirmed, "
            "  SUM(CASE WHEN status='done' THEN COALESCE(actual_amount, 0) ELSE 0 END) AS revenue "
            "FROM history "
            "WHERE org_id=? AND doctor_id=? AND scheduled_at >= ? AND scheduled_at <= ?",
            (org_id, doctor_id, start_str, end_str),
        ).fetchone()

        unique = conn.execute(
            "SELECT COUNT(DISTINCT user_id) AS n FROM history "
            "WHERE org_id=? AND doctor_id=? AND scheduled_at >= ? AND scheduled_at <= ?",
            (org_id, doctor_id, start_str, end_str),
        ).fetchone()["n"] or 0

        new_clients = conn.execute(
            "SELECT COUNT(*) AS n FROM ("
            "  SELECT user_id, MIN(scheduled_at) AS first_visit "
            "  FROM history "
            "  WHERE org_id=? AND doctor_id=? AND status='done' "
            "  GROUP BY user_id"
            ") WHERE date(first_visit) BETWEEN date(?) AND date(?)",
            (org_id, doctor_id, date_from, date_to),
        ).fetchone()["n"] or 0

        slots_info = conn.execute(
            "SELECT "
            "  COUNT(*) AS total_slots, "
            "  SUM(CASE WHEN is_booked=1 THEN 1 ELSE 0 END) AS booked_slots "
            "FROM slots "
            "WHERE org_id=? AND doctor_id=? AND date >= ? AND date <= ?",
            (org_id, doctor_id, date_from, date_to),
        ).fetchone()

        top_services_rows = conn.execute(
            "SELECT service_id, service_name, COUNT(*) AS cnt, "
            "       SUM(COALESCE(actual_amount, 0)) AS revenue "
            "FROM history "
            "WHERE org_id=? AND doctor_id=? AND status='done' "
            "  AND scheduled_at >= ? AND scheduled_at <= ? "
            "GROUP BY service_id, service_name "
            "ORDER BY cnt DESC LIMIT 10",
            (org_id, doctor_id, start_str, end_str),
        ).fetchall()

    total = agg["total"] or 0
    done = agg["done"] or 0
    no_show = agg["no_show"] or 0
    revenue = agg["revenue"] or 0
    total_slots = slots_info["total_slots"] or 0
    booked_slots = slots_info["booked_slots"] or 0

    avg_check = round(revenue / done, 2) if done > 0 else 0
    no_show_pct = round(no_show / total * 100, 1) if total > 0 else 0
    load_pct = round(booked_slots / total_slots * 100, 1) if total_slots > 0 else 0
    returning = max(0, unique - new_clients)

    return {
        "period": {"date_from": date_from, "date_to": date_to, "days": days},
        "current": {
            "total": total,
            "done": done,
            "no_show": no_show,
            "cancelled": agg["cancelled"] or 0,
            "pending": agg["pending"] or 0,
            "confirmed": agg["confirmed"] or 0,
            "revenue": revenue,
            "avg_check": avg_check,
            "no_show_pct": no_show_pct,
            "load_pct": load_pct,
            "total_slots": total_slots,
            "booked_slots": booked_slots,
            "unique_clients": unique,
            "new_clients": new_clients,
            "returning_clients": returning,
        },
        "top_services": [
            {"service_id": r["service_id"], "name": r["service_name"] or "—",
             "count": r["cnt"], "revenue": r["revenue"] or 0}
            for r in top_services_rows
        ],
    }


def find_backfill_candidates(org_id, slot_id, min_gap_hours, limit):
    """Кандидаты для backfill.

    Условия:
    - у клиента есть активная запись (pending/confirmed) на ту же услугу;
    - эта запись >= slot_time + min_gap_hours;
    - у клиента НЕТ другой записи на это же время / этот слот;
    - берём для каждого клиента одну запись — самую близкую к освободившемуся слоту
      среди подходящих;
    - сортируем клиентов по этой ближайшей записи, топ-limit.
    """
    conn = db()
    slot = conn.execute(
        "SELECT s.id, s.date, s.time, s.service_id, s.doctor_id, "
        "       s.branch_id AS branch_id "
        "FROM slots s "
        "WHERE s.id=? AND s.org_id=?",
        (slot_id, org_id),
    ).fetchone()
    if not slot or not slot["service_id"]:
        conn.close()
        return []

    slot_dt_str = f"{slot['date']} {slot['time']}"
    slot_dt = datetime.strptime(slot_dt_str, "%Y-%m-%d %H:%M")
    threshold_dt = slot_dt + timedelta(hours=min_gap_hours)
    threshold_str = threshold_dt.strftime("%Y-%m-%d %H:%M")

    # Кандидаты: активная запись на ту же услугу, позже порога,
    # в той же организации, у клиента нет этого слота в его записи.
    rows = conn.execute(
        "SELECT h.id AS history_id, h.user_id, h.scheduled_at, "
        "       h.slot_id, h.slot_ids, h.slots_count, h.service_id, h.org_id "
        "FROM history h "
        "WHERE h.org_id = ? "
        "  AND h.service_id = ? "
        "  AND h.status IN ('pending','confirmed') "
        "  AND h.scheduled_at >= ?",
        (org_id, slot["service_id"], threshold_str),
    ).fetchall()
    conn.close()

    by_user = {}
    for r in rows:
        uid = r["user_id"]
        if not uid or str(uid).startswith("phone:"):
            continue
        if r["slot_id"] == slot_id:
            continue
        cur = by_user.get(uid)
        if cur is None or r["scheduled_at"] < cur["scheduled_at"]:
            by_user[uid] = r

    ordered = sorted(by_user.values(), key=lambda x: x["scheduled_at"])
    return ordered[:limit]