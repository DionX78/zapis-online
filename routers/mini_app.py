"""Mini App endpoints (клиентская запись в MAX)."""
import json
import logging
from datetime import datetime

from fastapi import APIRouter, Request, HTTPException, Depends

from core.auth import require_user, get_uid_from_user
from core.booking import BookingContext, create_booking_unified
from handlers.booking import normalize_phone
from storage.db import (
    get_services, get_service,
    list_dates_with_slots, list_free_slots, get_slot,
    get_branch, get_doctor, get_client, upsert_client,
    list_orgs, get_org_settings,
    set_favorite_doctor,
    doctor_makes_service_batch,
    slots_needed_for_service,
    filter_slots_by_duration,
    now_for_org,
    is_user_blocked,
    list_doctors_by_org,
    get_uploaded_image_by_id,
    list_active_waitlist_for_user,
    create_waitlist_entry,
    cancel_waitlist_entry,
    get_waitlist_entry,
    log_audit,
    get_request,
)

log = logging.getLogger(__name__)

router = APIRouter()


@router.get("/max_booking/api/mini/me")
async def mini_me(user: dict = Depends(require_user)):
    uid = get_uid_from_user(user)
    user_info = user.get("user") or {}
    if isinstance(user_info, str):
        try:
            user_info = json.loads(user_info)
        except Exception:
            user_info = {}
    first_name = user_info.get("first_name") or ""
    last_name = user_info.get("last_name") or ""

    start_param = (user.get("start_param") or "").strip()
    start_org_id = None
    if start_param.startswith("org_"):
        try:
            start_org_id = int(start_param[4:])
        except ValueError:
            pass
    if not start_org_id:
        orgs = list_orgs()
        if len(orgs) == 1:
            start_org_id = orgs[0]["id"]

    client = get_client(uid)
    phone = ""
    middle_name = ""
    gender = ""
    birth_date = ""
    if client:
        first_name = client["first_name"] or first_name
        last_name = client["last_name"] or last_name
        middle_name = client["middle_name"] or ""
        phone = client["phone"] or ""
        gender = client["gender"] or ""
        birth_date = client["birth_date"] or ""
        if client["org_id"] is None and start_org_id:
            upsert_client(uid, org_id=start_org_id)
    else:
        if first_name or last_name:
            upsert_client(uid, org_id=start_org_id, first_name=first_name, last_name=last_name)

    return {
        "user_id": uid,
        "first_name": first_name,
        "last_name": last_name,
        "middle_name": middle_name,
        "phone": phone,
        "gender": gender,
        "birth_date": birth_date,
        "favorite_doctor_id": client["favorite_doctor_id"] if client else None,
        "consent_152fz": bool(client["consent_152fz"]) if client else False,
    }


@router.put("/max_booking/api/mini/favorite_doctor")
async def mini_set_favorite_doctor(request: Request, user: dict = Depends(require_user)):
    uid = get_uid_from_user(user)
    if not uid:
        raise HTTPException(status_code=401, detail="Invalid user")

    try:
        body = await request.json()
        if not isinstance(body, dict):
            body = {}
    except Exception:
        body = {}

    doctor_id_raw = body.get("doctor_id")
    if doctor_id_raw is None:
        set_favorite_doctor(uid, None)
        return {"ok": True, "favorite_doctor_id": None}

    try:
        doctor_id = int(doctor_id_raw)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid doctor_id")

    d = get_doctor(doctor_id)
    if not d:
        raise HTTPException(status_code=404, detail="Doctor not found")

    set_favorite_doctor(uid, doctor_id)
    return {"ok": True, "favorite_doctor_id": doctor_id}


@router.get("/max_booking/api/mini/services")
async def mini_services(user: dict = Depends(require_user)):
    start_param = (user.get("start_param") or "").strip()
    org_id = None
    if start_param.startswith("org_"):
        try:
            org_id = int(start_param[4:])
        except ValueError:
            pass
    if not org_id:
        orgs = list_orgs()
        if len(orgs) == 1:
            org_id = orgs[0]["id"]
    if not org_id:
        return {"services": []}
    rows = get_services(org_id)
    return {
        "services": [
            {"id": r["id"], "name": r["name"], "price": r["price"], "prep": r["prep"],
             "category_id": r["category_id"],
             "category_name": r["category_name"],
             "category_sort_order": r["category_sort_order"]}
            for r in rows
        ]
    }


@router.get("/max_booking/api/mini/dates")
async def mini_dates(service_id: str, user: dict = Depends(require_user)):
    svc = get_service(service_id)
    if not svc:
        raise HTTPException(status_code=404, detail="Service not found")
    org_id = svc["org_id"]
    dates = list_dates_with_slots(org_id, limit_days=14)
    return {"dates": dates}


@router.get("/max_booking/api/mini/slots")
async def mini_slots(service_id: str, date: str, user: dict = Depends(require_user)):
    svc = get_service(service_id)
    if not svc:
        raise HTTPException(status_code=404, detail="Service not found")
    org_id = svc["org_id"]

    settings = get_org_settings(org_id)
    step_min = int(settings.get("slot_step_min", 30) or 30)
    slots_needed = slots_needed_for_service(service_id, step_min)

    rows = list_free_slots(org_id, date, service_id=service_id)

    doctor_ids = list({r["doctor_id"] for r in rows if r["doctor_id"]})
    makes_map = doctor_makes_service_batch(doctor_ids, service_id) if doctor_ids else {}

    if slots_needed > 1:
        rows = filter_slots_by_duration(org_id, date, rows, slots_needed, step_min)

    branch_cache = {}
    doctor_cache = {}
    result = []
    for r in rows:
        doctor_id = r["doctor_id"]

        if doctor_id and not makes_map.get(doctor_id, True):
            continue

        doctor_name = None
        if doctor_id:
            if doctor_id in doctor_cache:
                d = doctor_cache[doctor_id]
            else:
                d = get_doctor(doctor_id)
                doctor_cache[doctor_id] = d
            if d:
                doctor_name = d["name"]

        branch_id = r["branch_id"]
        branch_name = None
        branch_address = None
        if branch_id:
            if branch_id in branch_cache:
                br = branch_cache[branch_id]
            else:
                br = get_branch(branch_id)
                branch_cache[branch_id] = br
            if br:
                branch_name = br["name"]
                branch_address = br["address"]

        result.append({
            "id": r["id"],
            "time": r["time"],
            "branch_id": branch_id,
            "branch_name": branch_name,
            "branch_address": branch_address,
            "doctor_id": doctor_id,
            "service_id": r["service_id"],
            "doctor_name": doctor_name,
        })
    return {
        "slots": result,
        "slots_needed": slots_needed,
        "duration_min": (svc["duration_min"] or 30),
        "buffer_min": (svc["buffer_min"] or 0),
    }


@router.get("/max_booking/api/mini/doctors")
async def mini_doctors(user: dict = Depends(require_user)):
    """Список специалистов организации для клиентского Mini App."""
    start_param = (user.get("start_param") or "").strip()
    org_id = None
    if start_param.startswith("org_"):
        try:
            org_id = int(start_param[4:])
        except ValueError:
            pass
    if not org_id:
        orgs = list_orgs()
        if len(orgs) == 1:
            org_id = orgs[0]["id"]
    if not org_id:
        return {"doctors": []}

    rows = list_doctors_by_org(org_id)
    result = []
    for r in rows:
        photo_url = None
        pid = r["photo_upload_id"] if "photo_upload_id" in r.keys() else None
        if pid:
            img = get_uploaded_image_by_id(pid)
            if img and img["public_token"]:
                photo_url = f"/max_booking/api/upload/{img['public_token']}"
        result.append({
            "id": r["id"],
            "name": r["name"],
            "specialty": r["specialty"] or "",
            "photo_url": photo_url,
        })
    return {"doctors": result}


@router.get("/max_booking/api/mini/history/{request_id}")
async def mini_history(request_id: int, user: dict = Depends(require_user)):
    """Данные прошлой заявки — для кнопки «Повторить» в Mini App."""
    uid = get_uid_from_user(user)
    req = get_request(request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if str(req["user_id"]) != str(uid):
        raise HTTPException(status_code=403, detail="Access denied")
    return {
        "id": req["id"],
        "service_id": req["service_id"],
        "service_name": req["service_name"],
        "scheduled_at": req["scheduled_at"],
        "doctor_id": req["doctor_id"],
        "status": req["status"],
    }


@router.post("/max_booking/api/mini/book")
async def mini_book(request: Request, user: dict = Depends(require_user)):
    uid = get_uid_from_user(user)
    if not uid:
        raise HTTPException(status_code=401, detail="Invalid user")

    try:
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    service_id = body.get("service_id")
    slot_id_raw = body.get("slot_id")
    phone = str(body.get("phone") or "").strip()
    first_name = str(body.get("first_name") or "").strip()[:100]
    last_name = str(body.get("last_name") or "").strip()[:100]
    middle_name = str(body.get("middle_name") or "").strip()[:100]
    gender = str(body.get("gender") or "").strip()
    birth_date = body.get("birth_date")
    consent_in_body = bool(body.get("consent_152fz"))

    if not service_id or not slot_id_raw or not phone:
        raise HTTPException(status_code=400, detail="Missing required fields")

    phone = normalize_phone(phone)
    if not phone:
        raise HTTPException(status_code=400, detail="Invalid phone")
    if not first_name or not last_name:
        raise HTTPException(status_code=400, detail="First and last name are required")
    if gender not in ("male", "female"):
        gender = None
    service_id = str(service_id)
    try:
        slot_id = int(slot_id_raw)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid slot_id")

    slot_pre = get_slot(slot_id)
    if not slot_pre:
        raise HTTPException(status_code=404, detail="Slot not found")
    org_id = slot_pre["org_id"]

    ctx_b = BookingContext(
        org_id=org_id,
        user_id=str(uid),
        slot_id=slot_id,
        service_id=service_id,
        phone=phone,
        first_name=first_name,
        last_name=last_name,
        middle_name=middle_name,
        gender=gender,
        birth_date=birth_date,
        via="mini_app",
        skip_consent_check=False,
        set_consent_152fz=consent_in_body,
    )

    result = await create_booking_unified(ctx_b)

    if not result.ok:
        status_map = {
            "blocked": (403, "Ваш аккаунт заблокирован. Обратитесь в клинику по телефону."),
            "slot_not_found": (404, "Slot not found"),
            "slot_org_mismatch": (400, "Slot belongs to another organization"),
            "slot_taken": (409, "Slot already booked"),
            "service_inactive": (404, "Service not found"),
            "service_org_mismatch": (400, "Service does not belong to this slot"),
            "slot_service_mismatch": (400, "Slot is reserved for another service"),
            "no_consent": (400, "Требуется согласие на обработку персональных данных"),
            "no_phone": (400, "Invalid phone"),
            "no_slots_for_duration": (409, "Недостаточно свободного времени подряд для этой услуги. Выберите другое время."),
            "slot_in_past": (400, "Slot is in the past"),
            "already_at_time": (409, "У вас уже есть активная запись на это время. Отмените её или выберите другое."),
            "daily_limit_exceeded": (409, result.error_msg or "Превышен лимит активных записей на день."),
            "too_many_active": (409, "Too many active bookings"),
            "doctor_skill": (400, "Специалист не оказывает эту услугу. Выберите другого специалиста."),
            "invalid_slots_count": (400, "Invalid slots_count"),
        }
        code, msg = status_map.get(
            result.error_code, (400, result.error_msg or "Не удалось создать запись")
        )
        raise HTTPException(status_code=code, detail=msg)

    try:
        import asyncio as _asyncio
        from core import merge as merge_core
        _asyncio.create_task(merge_core.maybe_queue_merge(org_id, str(uid), phone))
    except Exception:
        log.debug("merge hook skipped", exc_info=True)

    return {"ok": True, "id": result.request_id, "status": result.status}


@router.get("/max_booking/api/mini/slot/{slot_id}")
async def mini_slot_details(slot_id: int, user: dict = Depends(require_user)):
    uid = get_uid_from_user(user)
    if not uid:
        raise HTTPException(status_code=401, detail="Invalid user")

    slot = get_slot(slot_id)
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")
    if slot["is_booked"]:
        raise HTTPException(status_code=409, detail="Slot already booked")

    if not slot["service_id"]:
        raise HTTPException(status_code=400, detail="Slot is universal")

    svc = get_service(slot["service_id"])
    if not svc or not svc["active"]:
        raise HTTPException(status_code=404, detail="Service not found")

    doctor_name = None
    if slot["doctor_id"]:
        d = get_doctor(slot["doctor_id"])
        if d:
            doctor_name = d["name"]

    branch_name = None
    branch_address = None
    if slot["branch_id"]:
        br = get_branch(slot["branch_id"])
        if br:
            branch_name = br["name"]
            branch_address = br["address"]

    return {
        "service": {
            "id": svc["id"], "name": svc["name"], "price": svc["price"],
            "duration_min": svc["duration_min"], "buffer_min": svc["buffer_min"],
            "prep": svc["prep"],
        },
        "slot": {
            "id": slot["id"], "date": slot["date"], "time": slot["time"],
            "doctor_id": slot["doctor_id"], "doctor_name": doctor_name,
            "branch_id": slot["branch_id"], "branch_name": branch_name,
            "branch_address": branch_address, "service_id": slot["service_id"],
        },
    }


@router.post("/max_booking/api/mini/waitlist")
async def mini_waitlist_create(request: Request, user: dict = Depends(require_user)):
    uid = get_uid_from_user(user)
    if not uid:
        raise HTTPException(status_code=401, detail="Invalid user")

    start_param = (user.get("start_param") or "").strip()
    org_id = None
    if start_param.startswith("org_"):
        try:
            org_id = int(start_param[4:])
        except ValueError:
            pass
    if not org_id:
        client = get_client(uid)
        if client and client["org_id"]:
            org_id = client["org_id"]
    if not org_id:
        orgs = list_orgs()
        if len(orgs) == 1:
            org_id = orgs[0]["id"]
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization not determined")

    if is_user_blocked(uid):
        raise HTTPException(status_code=403, detail="Аккаунт заблокирован")

    try:
        body = await request.json()
        if not isinstance(body, dict):
            body = {}
    except Exception:
        body = {}

    service_id = str(body.get("service_id") or "").strip()
    date_from = str(body.get("date_from") or "").strip()
    date_to = str(body.get("date_to") or "").strip()
    preferred_time = (body.get("preferred_time") or "").strip() or None
    doctor_id_raw = body.get("doctor_id")
    branch_id_raw = body.get("branch_id")

    if not date_from or not date_to:
        raise HTTPException(status_code=400, detail="date_from, date_to обязательны")

    svc = None
    if service_id:
        svc = get_service(service_id)
        if not svc or not svc["active"] or svc["org_id"] != org_id:
            raise HTTPException(status_code=404, detail="Услуга не найдена")
    else:
        service_id = None

    try:
        d_from = datetime.strptime(date_from, "%Y-%m-%d").date()
        d_to = datetime.strptime(date_to, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный формат даты (YYYY-MM-DD)")

    today = now_for_org(org_id).date()
    if d_to < d_from:
        raise HTTPException(status_code=400, detail="date_from должен быть ≤ date_to")
    if d_to < today:
        raise HTTPException(status_code=400, detail="Период уже в прошлом")
    if (d_to - d_from).days > 90:
        raise HTTPException(status_code=400, detail="Слишком длинный период (макс. 90 дней)")

    doctor_id = None
    if doctor_id_raw not in (None, "", 0):
        try:
            doctor_id = int(doctor_id_raw)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid doctor_id")
        d = get_doctor(doctor_id)
        if not d:
            raise HTTPException(status_code=404, detail="Специалист не найден")

    branch_id = None
    if branch_id_raw not in (None, "", 0):
        try:
            branch_id = int(branch_id_raw)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid branch_id")
        br = get_branch(branch_id)
        if not br or br["org_id"] != org_id:
            raise HTTPException(status_code=400, detail="Invalid branch_id")

    if preferred_time not in (None, "morning", "afternoon", "evening", "any"):
        preferred_time = None

    if not service_id and not doctor_id:
        raise HTTPException(
            status_code=400,
            detail="Укажите услугу и/или специалиста",
        )

    wid = create_waitlist_entry(
        org_id, uid, service_id, date_from, date_to,
        doctor_id=doctor_id, branch_id=branch_id,
        preferred_time=preferred_time, created_by=None,
    )

    try:
        from core.waitlist import _notify_waitlist_entry_for_free_slots
        n = await _notify_waitlist_entry_for_free_slots(wid)
        if n:
            log.info("mini_waitlist_create: %d free slots matched for entry %s", n, wid)
    except Exception as e:
        log.warning("mini_waitlist_create: notify-on-create failed: %s", e)

    log_audit(
        org_id=org_id, user_id=uid, action="waitlist_created",
        entity_type="waitlist", entity_id=wid,
        payload={"service_id": service_id, "date_from": date_from,
                 "date_to": date_to, "via": "mini_app"},
    )

    return {"ok": True, "id": wid}


@router.get("/max_booking/api/mini/waitlist")
async def mini_waitlist_list(user: dict = Depends(require_user)):
    uid = get_uid_from_user(user)
    if not uid:
        raise HTTPException(status_code=401, detail="Invalid user")

    client = get_client(uid)
    org_id = client["org_id"] if client else None
    if not org_id:
        orgs = list_orgs()
        if len(orgs) == 1:
            org_id = orgs[0]["id"]
    if not org_id:
        return {"entries": []}

    rows = list_active_waitlist_for_user(org_id, uid)
    return {"entries": [
        {"id": r["id"], "service_id": r["service_id"],
         "service_name": r["service_name"],
         "doctor_id": r["doctor_id"], "doctor_name": r["doctor_name"],
         "branch_id": r["branch_id"], "branch_name": r["branch_name"],
         "date_from": r["date_from"], "date_to": r["date_to"],
         "preferred_time": r["preferred_time"],
         "created_at": r["created_at"]}
        for r in rows
    ]}


@router.delete("/max_booking/api/mini/waitlist/{wid}")
async def mini_waitlist_cancel(wid: int, user: dict = Depends(require_user)):
    uid = get_uid_from_user(user)
    if not uid:
        raise HTTPException(status_code=401, detail="Invalid user")

    entry = get_waitlist_entry(wid)
    if not entry:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    if str(entry["user_id"]) != str(uid):
        raise HTTPException(status_code=403, detail="Нет доступа")
    if entry["status"] != "active":
        return {"ok": True, "note": "already not active"}

    cancel_waitlist_entry(wid)

    log_audit(
        org_id=entry["org_id"], user_id=uid, action="waitlist_cancelled",
        entity_type="waitlist", entity_id=wid, payload={"via": "mini_app"},
    )

    return {"ok": True}