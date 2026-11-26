"""Админские ручки: slots, doctor schedule, branches, doctors, services, service categories."""
import asyncio
import logging
from datetime import datetime

from fastapi import APIRouter, Request, HTTPException, Depends, UploadFile, File

import config
from core.auth import AdminCtx, admin_ctx, org_ctx, require_branch, require_doctor
from core.uploads import _process_upload_image
from storage.db import (
    get_doctor_review_stats, get_doctors_review_stats_batch,
    list_slots_range, create_slot, delete_slot, generate_slots_range,
    get_slot, get_service, get_doctor, get_branch, get_org_settings,
    slots_needed_for_service, find_consecutive_slots,
    get_doctor_shifts, set_doctor_shifts,
    list_schedule_exceptions, create_schedule_exception, delete_schedule_exception,
    regenerate_doctor_slots, regenerate_all_slots_for_org,
    get_doctor_services, set_doctor_services, doctor_makes_service,
    list_branches, create_branch, update_branch, delete_branch, set_primary_branch,
    list_doctors, list_doctors_by_org, get_doctor_branches,
    create_doctor, update_doctor, delete_doctor,
    set_doctor_schedule_stop_date, set_doctor_photo,
    get_uploaded_image_by_id,
    list_services_admin, create_service, update_service, delete_service,
    list_service_categories, get_service_category,
    create_service_category, update_service_category, delete_service_category,
    save_uploaded_image_full, log_audit,
)

log = logging.getLogger(__name__)

router = APIRouter()


# ---------- Admin: slots ----------

@router.get("/max_booking/api/admin/slots")
async def admin_slots(
    date_from: str, date_to: str,
    branch_id: int | None = None, doctor_id: int | None = None,
    ctx: AdminCtx = Depends(org_ctx),
):
    rows = await asyncio.to_thread(
        list_slots_range, ctx.org_id, date_from, date_to, branch_id, doctor_id,
    )
    slots = []
    for r in rows:
        fio_parts = [r["last_name"], r["first_name"], r["middle_name"]]
        fio = " ".join(p for p in fio_parts if p).strip()
        slot_service_display = None
        if r["service_id"]:
            svc = get_service(r["service_id"])
            if svc:
                slot_service_display = svc["name"]
        slots.append({
            "id": r["id"], "date": r["date"], "time": r["time"],
            "is_booked": bool(r["is_booked"]), "request_id": r["request_id"],
            "branch_id": r["branch_id"], "branch_name": r["branch_name"],
            "doctor_id": r["doctor_id"], "doctor_name": r["doctor_name"],
            "service_name": r["service_name"], "phone": r["phone"],
            "status": r["status"], "client_fio": fio,
            "slot_service_id": r["service_id"],
            "slot_service_name": slot_service_display,
        })
    return {"slots": slots}


@router.get("/max_booking/api/admin/slots/available")
async def admin_slots_available(
    date_from: str, date_to: str,
    service_id: str | None = None,
    branch_id: int | None = None, doctor_id: int | None = None,
    slots_count: int | None = None,
    ctx: AdminCtx = Depends(org_ctx),
):
    """Свободные слоты для форм «Создать запись» и «Перенести запись».

    - Услуга указана → только слоты под эту услугу (или универсальные),
      с проверкой длительности.
    - Услуга НЕ указана, специалист указан → все свободные слоты этого
      специалиста, занимаем 1 слот (или slots_count).
    - Услуга и специалист НЕ указаны, есть branch_id → все свободные
      слоты филиала.
    - Ничего не указано → 400.
    - slots_count явно передан → используем его вместо вычисления по услуге.
    """
    if not service_id and not doctor_id and not branch_id:
        raise HTTPException(
            status_code=400,
            detail="Укажите услугу, специалиста или филиал",
        )

    settings = get_org_settings(ctx.org_id)
    step_min = int(settings.get("slot_step_min", 30) or 30)

    if service_id:
        svc = get_service(service_id)
        if not svc or (ctx.role != "superadmin" and svc["org_id"] != ctx.org_id):
            raise HTTPException(status_code=400, detail="Invalid service_id")
        slots_needed = slots_needed_for_service(service_id, step_min)
    else:
        service_id = None
        slots_needed = 1

    if slots_count is not None:
        try:
            slots_count = int(slots_count)
            if 1 <= slots_count <= 20:
                slots_needed = slots_count
        except (TypeError, ValueError):
            pass

    rows = await asyncio.to_thread(
        list_slots_range, ctx.org_id, date_from, date_to, branch_id, doctor_id,
    )
    result = []
    for r in rows:
        if r["is_booked"]:
            continue
        if service_id and r["service_id"] and r["service_id"] != service_id:
            continue

        consecutive = find_consecutive_slots(r["id"], slots_needed, step_min)
        if not consecutive:
            continue

        result.append({
            "id": r["id"], "date": r["date"], "time": r["time"],
            "branch_id": r["branch_id"], "branch_name": r["branch_name"],
            "doctor_id": r["doctor_id"], "doctor_name": r["doctor_name"],
            "slot_service_id": r["service_id"],
        })
    return {"slots": result, "slots_needed": slots_needed}


@router.post("/max_booking/api/admin/slots")
async def admin_create_slot(request: Request, ctx: AdminCtx = Depends(org_ctx)):
    body = await request.json()
    date_str = body.get("date")
    time_str = body.get("time")
    if not date_str or not time_str:
        raise HTTPException(status_code=400, detail="date and time required")

    branch_id_val = body.get("branch_id")
    if not branch_id_val:
        raise HTTPException(status_code=400, detail="branch_id required — слоты без филиала запрещены")
    br = get_branch(branch_id_val)
    if not br or (ctx.role != "superadmin" and br["org_id"] != ctx.org_id):
        raise HTTPException(status_code=400, detail="Invalid branch_id")

    doctor_id_val = body.get("doctor_id")
    if doctor_id_val:
        doc = get_doctor(doctor_id_val)
        if not doc:
            raise HTTPException(status_code=400, detail="Invalid doctor_id")
        doc_br = get_branch(doc["branch_id"])
        if not doc_br or (ctx.role != "superadmin" and doc_br["org_id"] != ctx.org_id):
            raise HTTPException(status_code=400, detail="Invalid doctor_id")

    # Двухфазный режим: если специалист не делает услугу — сначала спрашиваем фронт.
    # Фронт показывает confirm, при «Да» отправляет confirm_skill_mismatch=true,
    # и мы создаём слот + автоматически привязываем услугу специалисту.
    svc_id_val = body.get("service_id")
    if doctor_id_val and svc_id_val and not doctor_makes_service(doctor_id_val, svc_id_val):
        if not bool(body.get("confirm_skill_mismatch")):
            return {
                "ok": False,
                "error_code": "skill_mismatch",
                "message": "За этим специалистом не числится эта услуга. Всё равно создать слот?",
            }
        # Подтверждено — привязываем услугу специалисту
        existing = get_doctor_services(doctor_id_val)
        if svc_id_val not in existing:
            existing.append(svc_id_val)
            set_doctor_services(doctor_id_val, existing)
            log_audit(
                org_id=ctx.org_id, user_id=ctx.uid, action="doctor_service_added",
                entity_type="doctor", entity_id=doctor_id_val,
                payload={"service_id": svc_id_val, "reason": "slot_creation_confirm"},
            )

    if body.get("service_id"):
        svc = get_service(body["service_id"])
        if not svc or (ctx.role != "superadmin" and svc["org_id"] != ctx.org_id):
            raise HTTPException(status_code=400, detail="Invalid service_id")
    slot_id = create_slot(ctx.org_id, body.get("branch_id"), body.get("doctor_id"),
                          date_str, time_str, body.get("service_id"))
    if not slot_id:
        if body.get("doctor_id"):
            return {
                "ok": False,
                "note": "У выбранного специалиста уже есть слот на это время — "
                        "в этом филиале или в другом. Один специалист не может вести "
                        "два приёма одновременно. Выберите другое время или "
                        "другого специалиста.",
            }
        return {
            "ok": False,
            "note": "На это время уже открыт универсальный слот (без специалиста). "
                    "Укажите специалиста — так можно создать параллельный слот "
                    "для другого специалиста.",
        }

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="slot_created",
        entity_type="slot", entity_id=slot_id,
        payload={"date": date_str, "time": time_str,
                 "doctor_id": body.get("doctor_id")},
    )

    return {"ok": True, "id": slot_id}


@router.delete("/max_booking/api/admin/slots/{slot_id}")
async def admin_delete_slot(slot_id: int, ctx: AdminCtx = Depends(admin_ctx)):
    slot = get_slot(slot_id)
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")
    if ctx.role != "superadmin" and slot["org_id"] != ctx.org_id:
        raise HTTPException(status_code=403, detail="Access denied")

    ok = delete_slot(slot_id)
    if not ok:
        return {"ok": False, "note": "slot is booked, cannot delete"}

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="slot_deleted",
        entity_type="slot", entity_id=slot_id,
        payload={"date": slot["date"], "time": slot["time"]},
    )

    return {"ok": True}


@router.post("/max_booking/api/admin/slots/generate")
async def admin_generate_slots(request: Request, ctx: AdminCtx = Depends(org_ctx)):
    body = await request.json()
    branch_id = body.get("branch_id")
    doctor_id = body.get("doctor_id")
    service_id = body.get("service_id")
    date_from = body.get("date_from")
    if not date_from:
        raise HTTPException(status_code=400, detail="date_from is required")
    if not branch_id:
        raise HTTPException(status_code=400, detail="branch_id required — слоты без филиала запрещены")

    br = get_branch(branch_id)
    if not br or (ctx.role != "superadmin" and br["org_id"] != ctx.org_id):
        raise HTTPException(status_code=400, detail="Invalid branch_id")
    if doctor_id:
        doc = get_doctor(doctor_id)
        if not doc:
            raise HTTPException(status_code=400, detail="Invalid doctor_id")
        doc_br = get_branch(doc["branch_id"])
        if not doc_br or (ctx.role != "superadmin" and doc_br["org_id"] != ctx.org_id):
            raise HTTPException(status_code=400, detail="Invalid doctor_id")
    if service_id:
        svc = get_service(service_id)
        if not svc or (ctx.role != "superadmin" and svc["org_id"] != ctx.org_id):
            raise HTTPException(status_code=400, detail="Invalid service_id")

    if doctor_id and service_id and not doctor_makes_service(doctor_id, service_id):
        if not bool(body.get("confirm_skill_mismatch")):
            return {
                "ok": False,
                "error_code": "skill_mismatch",
                "message": "За этим специалистом не числится эта услуга. Всё равно создать слоты?",
            }
        existing = get_doctor_services(doctor_id)
        if service_id not in existing:
            existing.append(service_id)
            set_doctor_services(doctor_id, existing)
            log_audit(
                org_id=ctx.org_id, user_id=ctx.uid, action="doctor_service_added",
                entity_type="doctor", entity_id=doctor_id,
                payload={"service_id": service_id, "reason": "slot_generation_confirm"},
            )

    created = generate_slots_range(
        ctx.org_id, body.get("branch_id"), body.get("doctor_id"),
        date_from, int(body.get("days", 7)),
        body.get("days_of_week", [0, 1, 2, 3, 4]),
        body.get("time_start", "09:00"), body.get("time_end", "18:00"),
        int(body.get("step_min", 30)), service_id=body.get("service_id"),
    )

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="slots_generated",
        entity_type="slot", entity_id=None,
        payload={"created": created, "date_from": date_from,
                 "doctor_id": doctor_id, "branch_id": branch_id},
    )

    return {"ok": True, "created": created}


# ---------- Admin: doctor schedule ----------

def _valid_hhmm(t):
    if not t or not isinstance(t, str):
        return False
    try:
        h, m = map(int, t.split(":"))
        return 0 <= h <= 23 and 0 <= m <= 59
    except (ValueError, TypeError):
        return False


def _times_overlap(a_start, a_end, b_start, b_end):
    """Пересекаются ли интервалы 'HH:MM' (без учёта перерыва, только основное время)."""
    return not (a_end <= b_start or b_end <= a_start)


@router.get("/max_booking/api/admin/doctors/{doctor_id}/schedule")
async def admin_get_doctor_schedule(doctor_id: int, ctx: AdminCtx = Depends(admin_ctx)):
    require_doctor(ctx, doctor_id)
    rows = get_doctor_shifts(doctor_id)
    return {
        "doctor_id": doctor_id,
        "shifts": [
            {"id": r["id"], "branch_id": r["branch_id"], "weekday": r["weekday"],
             "start_time": r["start_time"], "end_time": r["end_time"],
             "break_start": r["break_start"], "break_end": r["break_end"]}
            for r in rows
        ],
    }


@router.put("/max_booking/api/admin/doctors/{doctor_id}/schedule")
async def admin_set_doctor_schedule(request: Request, doctor_id: int, ctx: AdminCtx = Depends(admin_ctx)):
    require_doctor(ctx, doctor_id)

    body = await request.json()
    shifts = body.get("shifts") or []
    if not isinstance(shifts, list):
        raise HTTPException(status_code=400, detail="shifts must be a list")

    normalized = []
    seen_sig = set()

    for idx, sh in enumerate(shifts):
        if not isinstance(sh, dict):
            raise HTTPException(status_code=400, detail="Each shift must be an object")

        try:
            bid = int(sh.get("branch_id"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"Invalid branch_id in shift #{idx}")
        br = get_branch(bid)
        if not br or (ctx.role != "superadmin" and br["org_id"] != ctx.org_id):
            raise HTTPException(status_code=400, detail=f"Invalid branch_id in shift #{idx}")

        try:
            wd = int(sh.get("weekday"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"Invalid weekday in shift #{idx}")
        if wd < 0 or wd > 6:
            raise HTTPException(status_code=400, detail="weekday must be 0..6")

        start = (sh.get("start_time") or "").strip()
        end = (sh.get("end_time") or "").strip()
        if not _valid_hhmm(start) or not _valid_hhmm(end):
            raise HTTPException(status_code=400, detail=f"Invalid time format in shift #{idx}")
        if start >= end:
            raise HTTPException(status_code=400, detail=f"start_time must be < end_time in shift #{idx}")

        bs = (sh.get("break_start") or "").strip() or None
        be = (sh.get("break_end") or "").strip() or None
        if (bs is None) != (be is None):
            raise HTTPException(status_code=400, detail=f"break_start and break_end must both be set or both empty in shift #{idx}")
        if bs and be:
            if not _valid_hhmm(bs) or not _valid_hhmm(be):
                raise HTTPException(status_code=400, detail=f"Invalid break time format in shift #{idx}")
            if bs >= be:
                raise HTTPException(status_code=400, detail=f"break_start must be < break_end in shift #{idx}")
            if bs < start or be > end:
                raise HTTPException(status_code=400, detail=f"Break must be inside working hours in shift #{idx}")

        sig = (bid, wd, start)
        if sig in seen_sig:
            raise HTTPException(status_code=400, detail=f"Duplicate shift: branch {bid}, weekday {wd}, start {start}")
        seen_sig.add(sig)

        normalized.append({
            "branch_id": bid,
            "weekday": wd,
            "start_time": start,
            "end_time": end,
            "break_start": bs,
            "break_end": be,
        })

    # Проверка пересечений смен в один день (у специалиста не может быть двух смен одновременно)
    by_day = {}
    for sh in normalized:
        by_day.setdefault(sh["weekday"], []).append(sh)
    for wd, day_shifts in by_day.items():
        day_shifts.sort(key=lambda x: x["start_time"])
        for i in range(len(day_shifts) - 1):
            a, b = day_shifts[i], day_shifts[i + 1]
            if _times_overlap(a["start_time"], a["end_time"], b["start_time"], b["end_time"]):
                raise HTTPException(
                    status_code=400,
                    detail=f"Смены специалиста в день {wd} пересекаются: "
                           f"{a['start_time']}–{a['end_time']} и {b['start_time']}–{b['end_time']}",
                )

    set_doctor_shifts(doctor_id, normalized)

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="doctor_schedule_updated",
        entity_type="doctor", entity_id=doctor_id,
        payload={"shifts_count": len(normalized)},
    )

    rows = get_doctor_shifts(doctor_id)
    return {
        "ok": True,
        "shifts": [
            {"id": r["id"], "branch_id": r["branch_id"], "weekday": r["weekday"],
             "start_time": r["start_time"], "end_time": r["end_time"],
             "break_start": r["break_start"], "break_end": r["break_end"]}
            for r in rows
        ],
    }


@router.get("/max_booking/api/admin/doctors/{doctor_id}/services")
async def admin_get_doctor_services(doctor_id: int, ctx: AdminCtx = Depends(admin_ctx)):
    require_doctor(ctx, doctor_id)
    service_ids = get_doctor_services(doctor_id)
    return {"doctor_id": doctor_id, "service_ids": service_ids}


@router.put("/max_booking/api/admin/doctors/{doctor_id}/services")
async def admin_set_doctor_services(request: Request, doctor_id: int, ctx: AdminCtx = Depends(admin_ctx)):
    require_doctor(ctx, doctor_id)

    body = await request.json()
    service_ids = body.get("service_ids")
    if not isinstance(service_ids, list):
        raise HTTPException(status_code=400, detail="service_ids must be a list")

    # Валидация: все услуги существуют и принадлежат этой org
    seen = set()
    clean_ids = []
    for sid in service_ids:
        sid_str = str(sid).strip()
        if not sid_str or sid_str in seen:
            continue
        seen.add(sid_str)
        svc = get_service(sid_str)
        if not svc:
            raise HTTPException(status_code=400, detail=f"Unknown service_id: {sid_str}")
        if ctx.role != "superadmin" and svc["org_id"] != ctx.org_id:
            raise HTTPException(status_code=400, detail=f"Service {sid_str} belongs to another organization")
        clean_ids.append(sid_str)

    set_doctor_services(doctor_id, clean_ids)

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="doctor_services_updated",
        entity_type="doctor", entity_id=doctor_id,
        payload={"services_count": len(clean_ids)},
    )

    return {"ok": True, "service_ids": clean_ids}


@router.get("/max_booking/api/admin/doctors/{doctor_id}/schedule_exceptions")
async def admin_list_schedule_exceptions(doctor_id: int, ctx: AdminCtx = Depends(admin_ctx)):
    require_doctor(ctx, doctor_id)
    rows = list_schedule_exceptions(doctor_id)
    return {"exceptions": [
        {"id": r["id"], "date_from": r["date_from"], "date_to": r["date_to"],
         "reason": r["reason"], "created_at": r["created_at"]}
        for r in rows
    ]}


@router.post("/max_booking/api/admin/doctors/{doctor_id}/schedule_exceptions")
async def admin_create_schedule_exception(request: Request, doctor_id: int, ctx: AdminCtx = Depends(admin_ctx)):
    require_doctor(ctx, doctor_id)

    body = await request.json()
    date_from = (body.get("date_from") or "").strip()
    date_to = (body.get("date_to") or "").strip() or date_from
    reason = (body.get("reason") or "").strip()[:200]

    if not date_from:
        raise HTTPException(status_code=400, detail="date_from is required")

    try:
        d_from = datetime.strptime(date_from, "%Y-%m-%d").date()
        d_to = datetime.strptime(date_to, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format (YYYY-MM-DD expected)")
    if d_from > d_to:
        raise HTTPException(status_code=400, detail="date_from must be <= date_to")

    eid = create_schedule_exception(doctor_id, date_from, date_to, reason)

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="schedule_exception_created",
        entity_type="doctor", entity_id=doctor_id,
        payload={"date_from": date_from, "date_to": date_to, "reason": reason},
    )

    return {"ok": True, "id": eid}


@router.delete("/max_booking/api/admin/doctors/{doctor_id}/schedule_exceptions/{exc_id}")
async def admin_delete_schedule_exception(doctor_id: int, exc_id: int, ctx: AdminCtx = Depends(admin_ctx)):
    require_doctor(ctx, doctor_id)
    if not delete_schedule_exception(doctor_id, exc_id):
        raise HTTPException(status_code=404, detail="Exception not found")

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="schedule_exception_deleted",
        entity_type="doctor", entity_id=doctor_id, payload={"exception_id": exc_id},
    )

    return {"ok": True}


@router.post("/max_booking/api/admin/doctors/{doctor_id}/schedule/regenerate")
async def admin_regenerate_doctor_slots(
    doctor_id: int,
    request: Request,
    ctx: AdminCtx = Depends(admin_ctx),
):
    require_doctor(ctx, doctor_id)

    try:
        body = await request.json()
        if not isinstance(body, dict):
            body = {}
    except Exception:
        body = {}

    horizon_raw = body.get("horizon_days")
    horizon_days = None
    if horizon_raw is not None:
        try:
            horizon_days = int(horizon_raw)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid horizon_days")
        if horizon_days < 1 or horizon_days > 365:
            raise HTTPException(status_code=400, detail="horizon_days must be in [1..365]")

    r = await asyncio.to_thread(regenerate_doctor_slots, doctor_id, horizon_days)
    if "error" in r:
        raise HTTPException(status_code=400, detail=r["error"])

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="slots_regenerated",
        entity_type="doctor", entity_id=doctor_id,
        payload={"created": r["created"], "deleted": r["deleted"],
                 "skipped_booked": r["skipped_booked"], "horizon_days": r["horizon_days"]},
    )
    return {"ok": True, **r}


@router.post("/max_booking/api/admin/schedule/regenerate_all")
async def admin_regenerate_all_slots(request: Request, ctx: AdminCtx = Depends(org_ctx)):
    try:
        body = await request.json()
        if not isinstance(body, dict):
            body = {}
    except Exception:
        body = {}

    horizon_raw = body.get("horizon_days")
    horizon_days = None
    if horizon_raw is not None:
        try:
            horizon_days = int(horizon_raw)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid horizon_days")
        if horizon_days < 1 or horizon_days > 365:
            raise HTTPException(status_code=400, detail="horizon_days must be in [1..365]")

    r = await asyncio.to_thread(regenerate_all_slots_for_org, ctx.org_id, horizon_days)

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="slots_regenerated_all",
        entity_type="organization", entity_id=ctx.org_id,
        payload=r,
    )
    return {"ok": True, **r}


# ---------- Admin: branches ----------

@router.get("/max_booking/api/admin/branches")
async def admin_branches(ctx: AdminCtx = Depends(admin_ctx)):
    if not ctx.org_id:
        return {"branches": []}
    rows = list_branches(ctx.org_id)
    return {"branches": [
        {"id": r["id"], "name": r["name"], "address": r["address"],
         "phone": r["phone"], "is_primary": bool(r["is_primary"])}
        for r in rows
    ]}


@router.post("/max_booking/api/admin/branches")
async def admin_create_branch(request: Request, ctx: AdminCtx = Depends(org_ctx)):
    body = await request.json()
    bid = create_branch(ctx.org_id, body.get("name", ""), body.get("address", ""), body.get("phone", ""))

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="branch_created",
        entity_type="branch", entity_id=bid,
        payload={"name": body.get("name", "")},
    )

    return {"ok": True, "id": bid}


@router.put("/max_booking/api/admin/branches/{branch_id}")
async def admin_update_branch(request: Request, branch_id: int, ctx: AdminCtx = Depends(admin_ctx)):
    require_branch(ctx, branch_id)
    body = await request.json()
    update_branch(branch_id, body.get("name", ""), body.get("address", ""), body.get("phone", ""))

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="branch_updated",
        entity_type="branch", entity_id=branch_id,
        payload={"name": body.get("name", "")},
    )

    return {"ok": True}


@router.delete("/max_booking/api/admin/branches/{branch_id}")
async def admin_delete_branch(branch_id: int, ctx: AdminCtx = Depends(admin_ctx)):
    br = require_branch(ctx, branch_id)
    ok, reason = delete_branch(branch_id)
    if not ok:
        raise HTTPException(status_code=409, detail=reason)

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="branch_deleted",
        entity_type="branch", entity_id=branch_id,
        payload={"name": br["name"] if br else None},
    )

    return {"ok": True}


@router.put("/max_booking/api/admin/branches/{branch_id}/primary")
async def admin_set_primary_branch(branch_id: int, ctx: AdminCtx = Depends(admin_ctx)):
    br = require_branch(ctx, branch_id)
    ok = set_primary_branch(branch_id)
    if not ok:
        log.warning("set_primary_branch failed: branch_id=%s org_id=%s", branch_id, ctx.org_id)
        raise HTTPException(status_code=500, detail="Не удалось установить основной филиал")

    log.info("Primary branch changed: branch_id=%s org_id=%s", branch_id, ctx.org_id)
    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="branch_primary_changed",
        entity_type="branch", entity_id=branch_id,
        payload={"name": br["name"] if br else None},
    )

    rows = list_branches(ctx.org_id)
    return {"ok": True, "branches": [
        {"id": r["id"], "name": r["name"], "address": r["address"],
         "phone": r["phone"], "is_primary": bool(r["is_primary"])}
        for r in rows
    ]}


# ---------- Admin: doctors ----------

def _doctor_photo_url(photo_upload_id):
    if not photo_upload_id:
        return None
    img = get_uploaded_image_by_id(photo_upload_id)
    if img and img["public_token"]:
        return f"/max_booking/api/upload/{img['public_token']}"
    return None


@router.get("/max_booking/api/admin/doctors")
async def admin_doctors(branch_id: int | None = None, ctx: AdminCtx = Depends(admin_ctx)):
    if branch_id:
        require_branch(ctx, branch_id)
        rows = list_doctors(branch_id)
        result = []
        for r in rows:
            d = get_doctor(r["id"])
            branches_list = get_doctor_branches(r["id"])
            services_list = get_doctor_services(r["id"])
            result.append({
                "id": r["id"], "name": r["name"], "specialty": r["specialty"],
                "branch_id": d["branch_id"] if d else None,
                "branch_name": "",
                "branch_ids": [b["id"] for b in branches_list],
                "schedule_stop_date": d["schedule_stop_date"] if d else None,
                "services_count": len(services_list),
                "photo_url": _doctor_photo_url(d["photo_upload_id"]) if d else None,
                "education": (d["education"] if d else None) or "",
                "courses": (d["courses"] if d else None) or "",
                "about": (d["about"] if d else None) or "",
            })
        _attach_review_stats(result, ctx.org_id)
        return {"doctors": result}
    if not ctx.org_id:
        return {"doctors": []}
    rows = list_doctors_by_org(ctx.org_id)
    result = []
    for r in rows:
        d = get_doctor(r["id"])
        branches_list = get_doctor_branches(r["id"])
        result.append({
            "id": r["id"], "name": r["name"], "specialty": r["specialty"],
            "branch_id": r["branch_id"], "branch_name": r["branch_name"],
            "branch_ids": [b["id"] for b in branches_list],
            "schedule_stop_date": d["schedule_stop_date"] if d else None,
            "services_count": r["services_count"],
            "photo_url": _doctor_photo_url(d["photo_upload_id"]) if d else None,
            "education": (d["education"] if d else None) or "",
            "courses": (d["courses"] if d else None) or "",
            "about": (d["about"] if d else None) or "",
        })
    _attach_review_stats(result, ctx.org_id)
    return {"doctors": result}


def _attach_review_stats(doctors: list, org_id: int):
    """Батч-добавление avg_rating и reviews_count в каждый dict."""
    if not doctors or not org_id:
        return
    ids = [d["id"] for d in doctors if d.get("id")]
    stats = get_doctors_review_stats_batch(ids, org_id)
    for d in doctors:
        s = stats.get(d["id"]) or {}
        d["avg_rating"] = s.get("avg_rating", 0)
        d["reviews_count"] = s.get("total", 0)


@router.post("/max_booking/api/admin/doctors")
async def admin_create_doctor(request: Request, ctx: AdminCtx = Depends(admin_ctx)):
    body = await request.json()
    branch_id = body.get("branch_id")
    if not branch_id:
        raise HTTPException(status_code=400, detail="branch_id required")

    require_branch(ctx, int(branch_id))

    did = create_doctor(
        int(branch_id),
        (body.get("name") or "").strip(),
        (body.get("specialty") or "").strip(),
        (body.get("education") or "").strip(),
        (body.get("courses") or "").strip(),
        (body.get("about") or "").strip(),
    )

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="doctor_created",
        entity_type="doctor", entity_id=did,
        payload={"name": body.get("name", "")},
    )

    return {"ok": True, "id": did}


@router.put("/max_booking/api/admin/doctors/{doctor_id}")
async def admin_update_doctor(request: Request, doctor_id: int, ctx: AdminCtx = Depends(admin_ctx)):
    d = get_doctor(doctor_id)
    if not d:
        raise HTTPException(status_code=404, detail="Doctor not found")
    br_old = get_branch(d["branch_id"])
    if br_old and ctx.role != "superadmin" and br_old["org_id"] != ctx.org_id:
        raise HTTPException(status_code=403, detail="Access denied")

    body = await request.json()
    new_branch_id = int(body.get("branch_id") or d["branch_id"])
    if new_branch_id != d["branch_id"]:
        require_branch(ctx, new_branch_id)

    update_doctor(
        doctor_id,
        (body.get("name") or "").strip(),
        (body.get("specialty") or "").strip(),
        new_branch_id,
        education=(body.get("education") or "").strip(),
        courses=(body.get("courses") or "").strip(),
        about=(body.get("about") or "").strip(),
    )

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="doctor_updated",
        entity_type="doctor", entity_id=doctor_id,
        payload={"name": body.get("name", "")},
    )

    return {"ok": True}


@router.delete("/max_booking/api/admin/doctors/{doctor_id}")
async def admin_delete_doctor(doctor_id: int, ctx: AdminCtx = Depends(admin_ctx)):
    d = get_doctor(doctor_id)
    if d:
        br = get_branch(d["branch_id"])
        if br and ctx.role != "superadmin" and br["org_id"] != ctx.org_id:
            raise HTTPException(status_code=403, detail="Access denied")

    ok, reason = delete_doctor(doctor_id)
    if not ok:
        raise HTTPException(status_code=409, detail=reason)

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="doctor_deleted",
        entity_type="doctor", entity_id=doctor_id,
        payload={"name": d["name"] if d else None},
    )

    return {"ok": True}


@router.post("/max_booking/api/admin/doctors/{doctor_id}/photo")
async def admin_doctor_upload_photo(
    doctor_id: int,
    file: UploadFile = File(...),
    ctx: AdminCtx = Depends(admin_ctx),
):
    """Загружает фото специалиста. Сжимает, хранит локально."""
    import uuid as _uuid
    from pathlib import Path as _Path

    require_doctor(ctx, doctor_id)

    if not file.content_type or file.content_type not in (
        "image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif",
    ):
        raise HTTPException(status_code=400, detail="Только JPEG/PNG/WebP/GIF")

    raw = await file.read()
    if len(raw) > config.MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"Файл больше {config.MAX_UPLOAD_SIZE // (1024 * 1024)} МБ",
        )
    if not raw:
        raise HTTPException(status_code=400, detail="Пустой файл")

    content, mime, ext = _process_upload_image(raw, file.content_type)

    filename = f"{_uuid.uuid4().hex}.{ext}"
    rel_dir = str(ctx.org_id)
    abs_dir = _Path(config.UPLOADS_DIR) / rel_dir
    abs_dir.mkdir(parents=True, exist_ok=True)
    abs_path = abs_dir / filename
    abs_path.write_bytes(content)
    rel_path = f"{rel_dir}/{filename}"

    upload_id, public_token = save_uploaded_image_full(
        token=None,
        file_path=rel_path,
        mime_type=mime,
        original_filename=file.filename or filename,
        file_size=len(content),
        org_id=ctx.org_id,
        uploaded_by=ctx.uid,
    )

    set_doctor_photo(doctor_id, upload_id)

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="doctor_photo_uploaded",
        entity_type="doctor", entity_id=doctor_id,
        payload={"upload_id": upload_id, "size": len(content), "mime": mime},
    )

    return {
        "ok": True,
        "photo_upload_id": upload_id,
        "photo_url": f"/max_booking/api/upload/{public_token}",
    }


@router.delete("/max_booking/api/admin/doctors/{doctor_id}/photo")
async def admin_doctor_delete_photo(doctor_id: int, ctx: AdminCtx = Depends(admin_ctx)):
    """Отвязывает фото специалиста."""
    require_doctor(ctx, doctor_id)

    set_doctor_photo(doctor_id, None)

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="doctor_photo_deleted",
        entity_type="doctor", entity_id=doctor_id, payload={},
    )

    return {"ok": True}


@router.get("/max_booking/api/admin/doctors/{doctor_id}/reviews")
async def admin_doctor_reviews(doctor_id: int, ctx: AdminCtx = Depends(admin_ctx)):
    """Все отзывы по специалисту + агрегат. Для модалки «Эффективность»."""
    require_doctor(ctx, doctor_id)
    return get_doctor_review_stats(doctor_id, ctx.org_id)


@router.put("/max_booking/api/admin/doctors/{doctor_id}/schedule_stop")
async def admin_set_doctor_schedule_stop(
    doctor_id: int, request: Request, ctx: AdminCtx = Depends(admin_ctx)
):
    """Устанавливает дату, до которой генерируются слоты из графика.
    stop_date=null — бессрочно. stop_date=сегодня — слоты на будущее удаляются.
    Сразу после сохранения вызывается regenerate, чтобы применить ограничение немедленно."""
    require_doctor(ctx, doctor_id)

    try:
        body = await request.json()
        if not isinstance(body, dict):
            body = {}
    except Exception:
        body = {}

    stop_date_raw = body.get("stop_date")
    stop_date = None
    if stop_date_raw is not None and str(stop_date_raw).strip() != "":
        try:
            stop_date = datetime.strptime(str(stop_date_raw).strip(), "%Y-%m-%d").date().isoformat()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid stop_date (YYYY-MM-DD expected)")

    set_doctor_schedule_stop_date(doctor_id, stop_date)

    r = await asyncio.to_thread(regenerate_doctor_slots, doctor_id)
    if "error" in r:
        raise HTTPException(status_code=400, detail=r["error"])

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid,
        action="doctor_schedule_stop_set" if stop_date else "doctor_schedule_stop_cleared",
        entity_type="doctor", entity_id=doctor_id,
        payload={"stop_date": stop_date,
                 "created": r.get("created"), "deleted": r.get("deleted")},
    )

    return {"ok": True, "stop_date": stop_date, "regenerate": r}


# ---------- Admin: services ----------

@router.get("/max_booking/api/admin/services")
async def admin_services(ctx: AdminCtx = Depends(admin_ctx)):
    if not ctx.org_id:
        return {"services": []}
    rows = list_services_admin(ctx.org_id)
    return {"services": [
        {"id": r["id"], "name": r["name"], "price": r["price"], "prep": r["prep"],
         "duration_min": r["duration_min"], "active": bool(r["active"]),
         "category_id": r["category_id"], "category_name": r["category_name"]}
        for r in rows
    ]}


@router.post("/max_booking/api/admin/services")
async def admin_create_service(request: Request, ctx: AdminCtx = Depends(org_ctx)):
    import secrets

    body = await request.json()
    sid = (body.get("id") or "").strip()
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Название услуги обязательно")

    # ID генерируется автоматически, если не передан (UI его не передаёт).
    # Старые услуги с осмысленными ID (uzi, eeg) продолжают работать.
    if not sid:
        for _ in range(20):
            candidate = "svc-" + secrets.token_hex(4)
            if not get_service(candidate):
                sid = candidate
                break
        if not sid:
            raise HTTPException(status_code=500, detail="Не удалось сгенерировать ID услуги")

    category_id = body.get("category_id")
    if category_id is not None and category_id != "":
        try:
            category_id = int(category_id)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid category_id")
        cat = get_service_category(category_id)
        if not cat or (ctx.role != "superadmin" and cat["org_id"] != ctx.org_id):
            raise HTTPException(status_code=400, detail="Invalid category_id")
    else:
        category_id = None

    buffer_min = int(body.get("buffer_min") or 0)
    if buffer_min < 0 or buffer_min > 240:
        raise HTTPException(status_code=400, detail="buffer_min must be in [0..240]")

    revisit = int(body.get("revisit_interval_days") or 0)
    if revisit < 0 or revisit > 3650:
        raise HTTPException(status_code=400, detail="revisit_interval_days must be in [0..3650]")

    ok = create_service(ctx.org_id, sid, name, int(body.get("price") or 0),
                        body.get("prep") or "", int(body.get("duration_min") or 30),
                        category_id=category_id, buffer_min=buffer_min,
                        revisit_interval_days=revisit)
    if not ok:
        raise HTTPException(status_code=409, detail="Услуга с таким ID уже существует")

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="service_created",
        entity_type="service", entity_id=sid, payload={"name": name},
    )

    return {"ok": True, "id": sid}


@router.put("/max_booking/api/admin/services/{service_id}")
async def admin_update_service(request: Request, service_id: str, ctx: AdminCtx = Depends(admin_ctx)):
    svc = get_service(service_id)
    if not svc:
        raise HTTPException(status_code=404, detail="Service not found")
    if ctx.role != "superadmin" and svc["org_id"] != ctx.org_id:
        raise HTTPException(status_code=403, detail="Access denied")

    body = await request.json()

    category_id = body.get("category_id")
    if category_id is not None and category_id != "":
        try:
            category_id = int(category_id)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid category_id")
        cat = get_service_category(category_id)
        if not cat or (ctx.role != "superadmin" and cat["org_id"] != ctx.org_id):
            raise HTTPException(status_code=400, detail="Invalid category_id")
    else:
        category_id = None

    buffer_min = int(body.get("buffer_min") or 0)
    if buffer_min < 0 or buffer_min > 240:
        raise HTTPException(status_code=400, detail="buffer_min must be in [0..240]")

    revisit = int(body.get("revisit_interval_days") or 0)
    if revisit < 0 or revisit > 3650:
        raise HTTPException(status_code=400, detail="revisit_interval_days must be in [0..3650]")

    update_service(service_id, body.get("name", svc["name"]),
                   int(body.get("price") or 0), body.get("prep") or "",
                   int(body.get("duration_min") or 30), int(body.get("active", 1)),
                   category_id=category_id, buffer_min=buffer_min,
                   revisit_interval_days=revisit)

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="service_updated",
        entity_type="service", entity_id=service_id,
        payload={"name": body.get("name", svc["name"])},
    )

    return {"ok": True}


@router.delete("/max_booking/api/admin/services/{service_id}")
async def admin_delete_service(service_id: str, ctx: AdminCtx = Depends(admin_ctx)):
    svc = get_service(service_id)
    if not svc:
        raise HTTPException(status_code=404, detail="Service not found")
    if ctx.role != "superadmin" and svc["org_id"] != ctx.org_id:
        raise HTTPException(status_code=403, detail="Access denied")
    delete_service(service_id)

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="service_deleted",
        entity_type="service", entity_id=service_id,
        payload={"name": svc["name"]},
    )

    return {"ok": True}


# ---------- Admin: service categories ----------

@router.get("/max_booking/api/admin/service_categories")
async def admin_service_categories(ctx: AdminCtx = Depends(org_ctx)):
    rows = list_service_categories(ctx.org_id)
    return {"categories": [
        {"id": r["id"], "name": r["name"], "sort_order": r["sort_order"],
         "services_count": r["services_count"]}
        for r in rows
    ]}


@router.post("/max_booking/api/admin/service_categories")
async def admin_create_service_category(request: Request, ctx: AdminCtx = Depends(org_ctx)):
    body = await request.json()
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Название категории обязательно")
    if len(name) > 100:
        raise HTTPException(status_code=400, detail="Название не длиннее 100 символов")

    try:
        sort_order = int(body.get("sort_order") or 100)
    except (TypeError, ValueError):
        sort_order = 100

    cid = create_service_category(ctx.org_id, name, sort_order)

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="service_category_created",
        entity_type="service_category", entity_id=cid, payload={"name": name},
    )

    return {"ok": True, "id": cid}


@router.put("/max_booking/api/admin/service_categories/{cat_id}")
async def admin_update_service_category(request: Request, cat_id: int, ctx: AdminCtx = Depends(admin_ctx)):
    cat = get_service_category(cat_id)
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    if ctx.role != "superadmin" and cat["org_id"] != ctx.org_id:
        raise HTTPException(status_code=403, detail="Access denied")

    body = await request.json()
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Название категории обязательно")
    if len(name) > 100:
        raise HTTPException(status_code=400, detail="Название не длиннее 100 символов")

    try:
        sort_order = int(body.get("sort_order") or 100)
    except (TypeError, ValueError):
        sort_order = 100

    update_service_category(cat_id, name, sort_order)

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="service_category_updated",
        entity_type="service_category", entity_id=cat_id, payload={"name": name},
    )

    return {"ok": True}


@router.delete("/max_booking/api/admin/service_categories/{cat_id}")
async def admin_delete_service_category(cat_id: int, ctx: AdminCtx = Depends(admin_ctx)):
    cat = get_service_category(cat_id)
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    if ctx.role != "superadmin" and cat["org_id"] != ctx.org_id:
        raise HTTPException(status_code=403, detail="Access denied")

    ok, count = delete_service_category(cat_id)
    if not ok:
        raise HTTPException(
            status_code=409,
            detail=f"В категории {count} услуг. Сначала переназначьте их в другие категории.",
        )

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="service_category_deleted",
        entity_type="service_category", entity_id=cat_id, payload={"name": cat["name"]},
    )

    return {"ok": True}


