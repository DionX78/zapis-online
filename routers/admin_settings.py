"""Админские ручки: settings (настройки организации) + валидация whitelist."""
import logging

from fastapi import APIRouter, Request, HTTPException, Depends

from core.auth import AdminCtx, org_ctx
from storage.db import (
    get_org, get_org_settings, set_org_settings, set_org_timezone,
    update_org_name, log_audit,
)

log = logging.getLogger(__name__)

router = APIRouter()


# ---------- валидация настроек ----------

_ALLOWED_SETTING_RULES = {
    "confirmation_mode": "enum:manual,auto,client",
    "review_request_enabled": "bool",
    "review_request_delay_hours": "int:1:168",
    "review_positive_threshold": "int:1:5",
    "review_yandex_url": "str_url",
    "review_2gis_url": "str_url",
    "client_confirm_delay_min": "int:5:1440",
    "client_confirm_timeout_min": "int:5:1440",
    "reminder_24h": "bool",
    "reminder_2h": "bool",
    "slot_step_min": "int:5:240",
    "autocomplete_after_hours": "int:0:48",
    "pending_timeout_min": "int:0:10080",
    "work_hours": "dict",
    "evening_summary_hour": "int:0:23",
    "map_provider": "enum:yandex,2gis,both",
    # E3: канал по умолчанию и дублирование уведомлений
    "channel_default": "enum:max,vk",
    "channel_duplicate": "bool",
    "max_bookings_per_day": "int:0:50",
    "schedule_horizon_days": "int:1:365",
    "auto_manual_no_show_threshold": "int:0:100",
    "client_at_risk_days": "int:1:365",
    "client_inactive_days": "int:1:3650",
    "quiet_hours_start": "int:0:23",
    "quiet_hours_end": "int:0:23",
    # Лист ожидания / backfill
    "slot_backfill_enabled": "bool",
    "slot_backfill_delay_minutes": "int:0:1440",
    "slot_backfill_waitlist_wait_minutes": "int:0:1440",
    "slot_backfill_batch_minutes": "int:0:1440",
    "slot_backfill_sent_ttl_hours": "int:1:720",
    "slot_backfill_min_gap_hours": "int:1:720",
    "slot_backfill_max_candidates": "int:1:20",
    "slot_backfill_cooldown_hours": "int:1:168",
}


def _validate_settings(new_settings: dict) -> tuple[bool, str]:
    for key, value in new_settings.items():
        rule = _ALLOWED_SETTING_RULES.get(key)
        if rule is None:
            return False, f"Unknown setting: {key}"

        if rule == "bool":
            if not isinstance(value, bool):
                return False, f"{key} must be boolean"
        elif rule == "dict":
            if not isinstance(value, dict):
                return False, f"{key} must be object"
        elif rule.startswith("enum:"):
            allowed = rule.split(":", 1)[1].split(",")
            if value not in allowed:
                return False, f"{key} must be one of: {', '.join(allowed)}"
        elif rule.startswith("int:"):
            _, lo, hi = rule.split(":")
            lo_i, hi_i = int(lo), int(hi)
            if isinstance(value, bool) or not isinstance(value, int):
                return False, f"{key} must be integer"
            if value < lo_i or value > hi_i:
                return False, f"{key} must be in range [{lo_i}..{hi_i}]"
        elif rule == "str_url":
            if not isinstance(value, str):
                return False, f"{key} must be string"
            v = value.strip()
            if v and not (v.startswith("http://") or v.startswith("https://")):
                return False, f"{key} must be URL (http:// or https://) or empty"
            if len(v) > 500:
                return False, f"{key} too long (max 500)"
        else:
            return False, f"Invalid rule for {key}"

    return True, ""


# ---------- Admin: settings ----------

@router.get("/max_booking/api/admin/settings")
async def admin_get_settings(ctx: AdminCtx = Depends(org_ctx)):
    org = get_org(ctx.org_id)
    return {
        "settings": get_org_settings(ctx.org_id),
        "name": org["name"] if org else "",
    }


@router.post("/max_booking/api/admin/settings")
async def admin_set_settings(request: Request, ctx: AdminCtx = Depends(org_ctx)):
    body = await request.json()
    new_settings = body.get("settings")
    if not isinstance(new_settings, dict):
        raise HTTPException(status_code=400, detail="settings must be an object")

    # name и timezone живут в отдельных колонках, не в JSON settings
    name_in_body = new_settings.pop("name", None)
    timezone_in_body = new_settings.pop("timezone", None)

    if name_in_body is not None:
        if not isinstance(name_in_body, str):
            raise HTTPException(status_code=400, detail="name must be a string")
        name_in_body = name_in_body.strip()
        if not name_in_body:
            raise HTTPException(status_code=400, detail="Название организации не может быть пустым")
        if len(name_in_body) > 200:
            raise HTTPException(status_code=400, detail="Название организации — не длиннее 200 символов")

    if timezone_in_body is not None:
        if not isinstance(timezone_in_body, str) or not timezone_in_body.strip():
            raise HTTPException(status_code=400, detail="timezone must be a non-empty string")
        try:
            from zoneinfo import ZoneInfo
            ZoneInfo(timezone_in_body)
        except Exception:
            raise HTTPException(status_code=400, detail=f"Unknown timezone: {timezone_in_body}")

    ok, err = _validate_settings(new_settings)
    if not ok:
        raise HTTPException(status_code=400, detail=err)

    current = get_org_settings(ctx.org_id)
    current.update(new_settings)
    set_org_settings(ctx.org_id, current)
    if timezone_in_body:
        set_org_timezone(ctx.org_id, timezone_in_body)
        current["timezone"] = timezone_in_body

    if name_in_body:
        update_org_name(ctx.org_id, name_in_body)

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="settings_updated",
        entity_type="organization", entity_id=ctx.org_id,
        payload={"changed_keys": list(new_settings.keys()) +
                 (["timezone"] if timezone_in_body else []) +
                 (["name"] if name_in_body else [])},
    )

    org = get_org(ctx.org_id)
    return {"ok": True, "settings": current, "name": org["name"] if org else ""}


