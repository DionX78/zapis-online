"""Генерация .ics-файлов для добавления записи в календарь (RFC 5545)."""
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from storage.db import get_org_timezone


def _escape(value: str) -> str:
    """Экранирование строк по RFC 5545."""
    if not value:
        return ""
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace("\r", "\\n")
    )


def _to_utc(date_str: str, time_str: str, tz_name: str):
    """local (naive) -> aware UTC."""
    try:
        local_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    except Exception:
        return None
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = timezone.utc
    return local_dt.replace(tzinfo=tz).astimezone(timezone.utc)


def _fmt_dt(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%SZ")


def build_ics(
    request_id: int,
    org_id: int,
    service_name: str,
    scheduled_at: str,
    duration_min: int,
    address: str = "",
    doctor: str = "",
    prep: str = "",
    uid_domain: str = "boroda-bot.ru",
) -> str:
    """Возвращает текст .ics-файла для заявки.

    scheduled_at — в локальном времени организации, формат "YYYY-MM-DD HH:MM".
    duration_min — длительность услуги в минутах (минимум 30).
    """
    if not scheduled_at or len(scheduled_at) < 16:
        raise ValueError("Некорректный scheduled_at")

    date_str = scheduled_at[:10]
    time_str = scheduled_at[11:16]

    tz_name = get_org_timezone(org_id)
    start_utc = _to_utc(date_str, time_str, tz_name)
    if start_utc is None:
        raise ValueError("Некорректная дата/время")

    if not duration_min or duration_min < 5:
        duration_min = 30
    end_utc = start_utc + timedelta(minutes=duration_min)

    dtstamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    summary = service_name or "Приём"
    description_parts = []
    if doctor:
        description_parts.append(f"Специалист: {doctor}")
    if prep:
        description_parts.append(f"Подготовка: {prep}")
    description = "\n".join(description_parts)

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//MAX Booking Bot//RU",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:booking-{request_id}@{uid_domain}",
        f"DTSTAMP:{dtstamp}",
        f"DTSTART:{_fmt_dt(start_utc)}",
        f"DTEND:{_fmt_dt(end_utc)}",
        f"SUMMARY:{_escape(summary)}",
    ]
    if address:
        lines.append(f"LOCATION:{_escape(address)}")
    if description:
        lines.append(f"DESCRIPTION:{_escape(description)}")
    lines.append("STATUS:CONFIRMED")
    lines.append("BEGIN:VALARM")
    lines.append("TRIGGER:-PT1H")
    lines.append("ACTION:DISPLAY")
    lines.append(f"DESCRIPTION:{_escape(summary)}")
    lines.append("END:VALARM")
    lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")

    return "\r\n".join(lines) + "\r\n"