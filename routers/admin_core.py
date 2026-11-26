"""Админские ручки: me/orgs/timezones, dashboard, analytics, audit_log."""
import asyncio
import logging
import uuid as _uuid
from datetime import datetime
from io import BytesIO, StringIO
from pathlib import Path as _Path

from fastapi import APIRouter, Request, HTTPException, Depends

import config
from core import max_client as mx
from core.auth import AdminCtx, admin_ctx, superadmin_ctx, org_ctx
from core.analytics_export import generate_and_send_analytics
from storage.db import (
    list_orgs, get_org, update_org_name,
    get_branch, get_doctor,
    get_analytics_summary, get_analytics_doctor_summary,
    get_dashboard_today,
    log_audit, list_audit_log,
)

log = logging.getLogger(__name__)

router = APIRouter()


# ---------- Admin: me/orgs ----------

@router.get("/max_booking/api/admin/me")
async def admin_me(ctx: AdminCtx = Depends(admin_ctx)):
    org_name = None
    if ctx.org_id:
        org = get_org(ctx.org_id)
        if org:
            org_name = org["name"]
    return {"user_id": ctx.uid, "role": ctx.role, "org_id": ctx.org_id, "org_name": org_name}


@router.put("/max_booking/api/admin/org")
async def admin_update_org(request: Request, ctx: AdminCtx = Depends(org_ctx)):
    try:
        body = await request.json()
        if not isinstance(body, dict):
            body = {}
    except Exception:
        body = {}

    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Название не может быть пустым")
    if len(name) > 200:
        raise HTTPException(status_code=400, detail="Название не длиннее 200 символов")

    if not update_org_name(ctx.org_id, name):
        raise HTTPException(status_code=500, detail="Не удалось переименовать организацию")

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="org_renamed",
        entity_type="organization", entity_id=ctx.org_id,
        payload={"name": name},
    )

    return {"ok": True, "name": name}


@router.get("/max_booking/api/admin/orgs")
async def admin_orgs(ctx: AdminCtx = Depends(superadmin_ctx)):
    orgs = list_orgs()
    return {"orgs": [{"id": o["id"], "name": o["name"]} for o in orgs]}


@router.get("/max_booking/api/admin/timezones")
async def admin_timezones(ctx: AdminCtx = Depends(admin_ctx)):
    return {"timezones": [
        {"id": tz, "label": label}
        for tz, label in config.SUPPORTED_TIMEZONES
    ]}


# ---------- Admin: dashboard ----------

@router.get("/max_booking/api/admin/dashboard/today")
async def admin_dashboard_today(ctx: AdminCtx = Depends(org_ctx)):
    return get_dashboard_today(ctx.org_id)


# ---------- Admin: analytics ----------

@router.get("/max_booking/api/admin/analytics/summary")
async def admin_analytics_summary(
    date_from: str,
    date_to: str,
    branch_id: int | None = None,
    doctor_id: int | None = None,
    ctx: AdminCtx = Depends(org_ctx),
):
    try:
        d_from = datetime.strptime(date_from, "%Y-%m-%d").date()
        d_to = datetime.strptime(date_to, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format (YYYY-MM-DD expected)")

    if d_to < d_from:
        raise HTTPException(status_code=400, detail="date_to must be >= date_from")
    if (d_to - d_from).days > 730:
        raise HTTPException(status_code=400, detail="Период не должен превышать 2 года")

    if branch_id is not None:
        br = get_branch(branch_id)
        if not br or (ctx.role != "superadmin" and br["org_id"] != ctx.org_id):
            raise HTTPException(status_code=400, detail="Invalid branch_id")

    if doctor_id is not None:
        d = get_doctor(doctor_id)
        if not d:
            raise HTTPException(status_code=400, detail="Invalid doctor_id")

    result = await asyncio.to_thread(
        get_analytics_summary,
        ctx.org_id, date_from, date_to, branch_id, doctor_id,
    )
    return result


@router.get("/max_booking/api/admin/analytics/doctor/{doctor_id}")
async def admin_analytics_doctor(
    doctor_id: int,
    date_from: str,
    date_to: str,
    ctx: AdminCtx = Depends(org_ctx),
):
    """Сводка по одному специалисту за период. Для модалки в аналитике."""
    try:
        d_from = datetime.strptime(date_from, "%Y-%m-%d").date()
        d_to = datetime.strptime(date_to, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format")

    if d_to < d_from:
        raise HTTPException(status_code=400, detail="date_to must be >= date_from")
    if (d_to - d_from).days > 730:
        raise HTTPException(status_code=400, detail="Период не должен превышать 2 года")

    doc = get_doctor(doctor_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Doctor not found")

    br = get_branch(doc["branch_id"]) if doc["branch_id"] else None
    if ctx.role != "superadmin" and (not br or br["org_id"] != ctx.org_id):
        raise HTTPException(status_code=403, detail="Access denied")

    data = await asyncio.to_thread(
        get_analytics_doctor_summary, ctx.org_id, doctor_id, date_from, date_to,
    )
    data["doctor"] = {
        "id": doc["id"], "name": doc["name"], "specialty": doc["specialty"] or "",
    }

    # Рейтинг специалиста (все отзывы, не за период)
    try:
        from storage.db import get_doctor_review_stats
        review_stats = await asyncio.to_thread(
            get_doctor_review_stats, doctor_id, ctx.org_id,
        )
        data["review_stats"] = review_stats
    except Exception as e:
        log.warning("doctor review stats failed for #%s: %s", doctor_id, e)
        data["review_stats"] = {"total": 0, "avg_rating": 0,
                                "distribution": {}, "recent": []}

    return data


@router.get("/max_booking/api/admin/analytics/export")
async def admin_analytics_export(
    date_from: str,
    date_to: str,
    format: str = "xlsx",
    branch_id: int | None = None,
    doctor_id: int | None = None,
    ctx: AdminCtx = Depends(org_ctx),
):
    """Экспорт аналитики в CSV/XLSX/PDF. Отправляет файл в чат админу."""
    try:
        d_from = datetime.strptime(date_from, "%Y-%m-%d").date()
        d_to = datetime.strptime(date_to, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format")

    if d_to < d_from:
        raise HTTPException(status_code=400, detail="date_to must be >= date_from")
    if (d_to - d_from).days > 730:
        raise HTTPException(status_code=400, detail="Период не должен превышать 2 года")

    if branch_id is not None:
        br = get_branch(branch_id)
        if not br or (ctx.role != "superadmin" and br["org_id"] != ctx.org_id):
            raise HTTPException(status_code=400, detail="Invalid branch_id")
    if doctor_id is not None:
        d = get_doctor(doctor_id)
        if not d:
            raise HTTPException(status_code=400, detail="Invalid doctor_id")

    fmt = (format or "xlsx").lower().strip()
    if fmt not in ("csv", "xlsx", "pdf"):
        raise HTTPException(status_code=400, detail="format must be csv, xlsx or pdf")

    try:
        return await generate_and_send_analytics(
            org_id=ctx.org_id, admin_uid=ctx.uid,
            date_from=date_from, date_to=date_to, fmt=fmt,
            branch_id=branch_id, doctor_id=doctor_id,
        )
    except Exception as e:
        log.error("analytics export failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Ошибка формирования файла: {e}")


# ---------- Admin: audit log ----------

@router.get("/max_booking/api/admin/audit_log")
async def admin_audit_log(
    limit: int = 100,
    offset: int = 0,
    action: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    ctx: AdminCtx = Depends(org_ctx),
):
    if limit > 500:
        limit = 500
    rows = list_audit_log(
        ctx.org_id, limit=limit, offset=offset,
        action=action, date_from=date_from, date_to=date_to,
    )
    return {"entries": [
        {"id": r["id"], "user_id": r["user_id"], "action": r["action"],
         "entity_type": r["entity_type"], "entity_id": r["entity_id"],
         "payload": r["payload"], "created_at": r["created_at"]}
        for r in rows
    ]}
