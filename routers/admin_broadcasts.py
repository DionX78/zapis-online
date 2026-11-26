"""Админские ручки: broadcasts (Manual + Auto)."""
import asyncio
import logging

from fastapi import APIRouter, Request, HTTPException, Depends

from core.auth import AdminCtx, admin_ctx, org_ctx
from core.channels.base import UserBlocked
from core.messaging import send_to_client_raw
from core.broadcasts import (
    create_broadcast, get_broadcast, list_broadcasts,
    start_broadcast, cancel_broadcast, delete_broadcast,
    prepare_broadcast_sends, get_clients_for_segment,
    duplicate_broadcast, update_broadcast_draft,
)
from storage.db import (
    list_auto_broadcasts, get_auto_broadcast,
    create_auto_broadcast, update_auto_broadcast,
    delete_auto_broadcast, toggle_auto_broadcast,
    get_uploaded_image_by_id, log_audit,
    schedule_broadcast, unschedule_broadcast,
)

log = logging.getLogger(__name__)

router = APIRouter()


# ---------- Admin: broadcasts (Manual) ----------

def _check_image_id(ctx: AdminCtx, image_id):
    if image_id is None or image_id == "":
        return None
    try:
        uid_int = int(image_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid image_id")
    img = get_uploaded_image_by_id(uid_int)
    if not img or (ctx.role != "superadmin" and img["org_id"] != ctx.org_id):
        raise HTTPException(status_code=400, detail="Image not found")
    return uid_int


@router.get("/max_booking/api/admin/broadcasts")
async def admin_broadcasts(ctx: AdminCtx = Depends(admin_ctx)):
    if not ctx.org_id:
        return {"broadcasts": []}
    rows = list_broadcasts(ctx.org_id)

    image_previews = {}
    for r in rows:
        iid = r["image_id"]
        if iid and iid not in image_previews:
            img = get_uploaded_image_by_id(iid)
            if img and img["public_token"]:
                image_previews[iid] = f"/max_booking/api/upload/{img['public_token']}"
            else:
                image_previews[iid] = None

    return {"broadcasts": [
        {"id": r["id"], "text": r["text"], "status": r["status"],
         "total_recipients": r["total_recipients"], "sent_count": r["sent_count"],
         "failed_count": r["failed_count"], "created_at": r["created_at"],
         "started_at": r["started_at"], "finished_at": r["finished_at"],
         "scheduled_at": r["scheduled_at"],
         "image_id": r["image_id"],
         "has_image": bool(r["image_id"]),
         "preview_url": image_previews.get(r["image_id"]) if r["image_id"] else None}
        for r in rows
    ]}


@router.post("/max_booking/api/admin/broadcasts/preview")
async def admin_broadcast_preview(request: Request, ctx: AdminCtx = Depends(org_ctx)):
    body = await request.json()
    segment = body.get("segment", {})
    user_ids = await asyncio.to_thread(get_clients_for_segment, ctx.org_id, segment)
    return {"count": len(user_ids), "sample": user_ids[:5]}


@router.post("/max_booking/api/admin/broadcasts")
async def admin_broadcast_create(request: Request, ctx: AdminCtx = Depends(org_ctx)):
    body = await request.json()
    text = (body.get("text") or "").strip()
    segment = body.get("segment", {})
    image_id = _check_image_id(ctx, body.get("image_id"))
    start_now = bool(body.get("start_now", True))
    scheduled_at = (body.get("scheduled_at") or "").strip() or None

    if not text:
        raise HTTPException(status_code=400, detail="text required")

    status = "draft"
    if start_now:
        status = "draft"  # потом переведём в sending через start_draft_broadcast
    elif scheduled_at:
        status = "scheduled"

    bid = create_broadcast(
        ctx.org_id, text, segment, created_by=ctx.uid,
        image_id=image_id, scheduled_at=scheduled_at, status=status,
    )

    if start_now:
        user_ids = await asyncio.to_thread(get_clients_for_segment, ctx.org_id, segment)
        if not user_ids:
            return {"ok": False, "id": bid, "note": "Нет получателей в этом сегменте"}
        prepare_broadcast_sends(bid, user_ids)
        start_broadcast(bid, len(user_ids))

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="broadcast_created",
        entity_type="broadcast", entity_id=bid,
        payload={"start_now": start_now, "scheduled_at": scheduled_at,
                 "has_image": bool(image_id)},
    )

    return {"ok": True, "id": bid, "status": status if not start_now else "sending"}


@router.put("/max_booking/api/admin/broadcasts/{bid}")
async def admin_broadcast_update(request: Request, bid: int, ctx: AdminCtx = Depends(admin_ctx)):
    b = get_broadcast(bid)
    if not b:
        raise HTTPException(status_code=404, detail="Broadcast not found")
    if ctx.role != "superadmin" and b["org_id"] != ctx.org_id:
        raise HTTPException(status_code=403, detail="Access denied")
    if b["status"] not in ("draft", "scheduled"):
        raise HTTPException(status_code=400, detail="Only draft or scheduled can be edited")

    body = await request.json()
    text = (body.get("text") or "").strip()
    segment = body.get("segment", {})
    image_id = _check_image_id(ctx, body.get("image_id"))
    if not text:
        raise HTTPException(status_code=400, detail="text required")

    update_broadcast_draft(bid, text, segment, image_id=image_id)

    # Если была запланирована — позволяем обновить дату
    if "scheduled_at" in body and b["status"] == "scheduled":
        new_sched = (body.get("scheduled_at") or "").strip()
        if new_sched:
            from storage.db import db as _db
            conn = _db()
            conn.execute("UPDATE broadcasts SET scheduled_at=? WHERE id=?", (new_sched, bid))
            conn.commit()
            conn.close()

    return {"ok": True}


@router.post("/max_booking/api/admin/broadcasts/{bid}/start")
async def admin_broadcast_start(bid: int, ctx: AdminCtx = Depends(admin_ctx)):
    b = get_broadcast(bid)
    if not b:
        raise HTTPException(status_code=404, detail="Broadcast not found")
    if ctx.role != "superadmin" and b["org_id"] != ctx.org_id:
        raise HTTPException(status_code=403, detail="Access denied")

    from core.broadcasts import start_draft_broadcast
    ok, result = start_draft_broadcast(bid)
    if not ok:
        if result == "empty":
            return {"ok": False, "note": "Нет получателей в выбранном сегменте"}
        raise HTTPException(status_code=400, detail=result)

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="broadcast_started",
        entity_type="broadcast", entity_id=bid, payload={"count": result},
    )

    return {"ok": True, "count": result}


@router.post("/max_booking/api/admin/broadcasts/{bid}/schedule")
async def admin_broadcast_schedule(request: Request, bid: int, ctx: AdminCtx = Depends(admin_ctx)):
    b = get_broadcast(bid)
    if not b:
        raise HTTPException(status_code=404, detail="Broadcast not found")
    if ctx.role != "superadmin" and b["org_id"] != ctx.org_id:
        raise HTTPException(status_code=403, detail="Access denied")
    if b["status"] != "draft":
        raise HTTPException(status_code=400, detail="Only draft can be scheduled")

    body = await request.json()
    scheduled_at = (body.get("scheduled_at") or "").strip()
    if not scheduled_at:
        raise HTTPException(status_code=400, detail="scheduled_at required")

    if not schedule_broadcast(bid, scheduled_at):
        raise HTTPException(status_code=409, detail="Cannot schedule")

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="broadcast_scheduled",
        entity_type="broadcast", entity_id=bid, payload={"scheduled_at": scheduled_at},
    )
    return {"ok": True}


@router.post("/max_booking/api/admin/broadcasts/{bid}/unschedule")
async def admin_broadcast_unschedule(bid: int, ctx: AdminCtx = Depends(admin_ctx)):
    b = get_broadcast(bid)
    if not b:
        raise HTTPException(status_code=404, detail="Broadcast not found")
    if ctx.role != "superadmin" and b["org_id"] != ctx.org_id:
        raise HTTPException(status_code=403, detail="Access denied")
    if not unschedule_broadcast(bid):
        raise HTTPException(status_code=409, detail="Not scheduled")
    return {"ok": True}


@router.post("/max_booking/api/admin/broadcasts/{bid}/cancel")
async def admin_broadcast_cancel(bid: int, ctx: AdminCtx = Depends(admin_ctx)):
    b = get_broadcast(bid)
    if not b:
        raise HTTPException(status_code=404, detail="Broadcast not found")
    if ctx.role != "superadmin" and b["org_id"] != ctx.org_id:
        raise HTTPException(status_code=403, detail="Access denied")

    cancel_broadcast(bid)

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="broadcast_cancelled",
        entity_type="broadcast", entity_id=bid, payload={},
    )
    return {"ok": True}


@router.post("/max_booking/api/admin/broadcasts/{bid}/duplicate")
async def admin_broadcast_duplicate(bid: int, ctx: AdminCtx = Depends(admin_ctx)):
    b = get_broadcast(bid)
    if not b:
        raise HTTPException(status_code=404, detail="Broadcast not found")
    if ctx.role != "superadmin" and b["org_id"] != ctx.org_id:
        raise HTTPException(status_code=403, detail="Access denied")

    nid = duplicate_broadcast(bid, created_by=ctx.uid)
    if not nid:
        raise HTTPException(status_code=500, detail="Duplicate failed")

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="broadcast_duplicated",
        entity_type="broadcast", entity_id=nid, payload={"source_id": bid},
    )
    return {"ok": True, "id": nid}


@router.delete("/max_booking/api/admin/broadcasts/{bid}")
async def admin_broadcast_delete(bid: int, ctx: AdminCtx = Depends(admin_ctx)):
    b = get_broadcast(bid)
    if not b:
        raise HTTPException(status_code=404, detail="Broadcast not found")
    if ctx.role != "superadmin" and b["org_id"] != ctx.org_id:
        raise HTTPException(status_code=403, detail="Access denied")

    delete_broadcast(bid)

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="broadcast_deleted",
        entity_type="broadcast", entity_id=bid, payload={},
    )
    return {"ok": True}


@router.get("/max_booking/api/admin/broadcasts/{bid}")
async def admin_broadcast_details(bid: int, ctx: AdminCtx = Depends(admin_ctx)):
    b = get_broadcast(bid)
    if not b:
        raise HTTPException(status_code=404, detail="Broadcast not found")
    if ctx.role != "superadmin" and b["org_id"] != ctx.org_id:
        raise HTTPException(status_code=403, detail="Access denied")

    preview_url = None
    if b["image_id"]:
        _img = get_uploaded_image_by_id(b["image_id"])
        if _img and _img["public_token"]:
            preview_url = f"/max_booking/api/upload/{_img['public_token']}"
    return {"broadcast": {
        "id": b["id"], "org_id": b["org_id"], "text": b["text"],
        "segment": b["segment_json"], "status": b["status"],
        "total": b["total_recipients"], "sent": b["sent_count"],
        "failed": b["failed_count"], "image_id": b["image_id"],
        "preview_url": preview_url,
        "scheduled_at": b["scheduled_at"],
        "created_by": b["created_by"], "created_at": b["created_at"],
        "started_at": b["started_at"], "finished_at": b["finished_at"],
    }}


@router.get("/max_booking/api/admin/broadcasts/{bid}/sends")
async def admin_broadcast_sends(bid: int, ctx: AdminCtx = Depends(admin_ctx)):
    b = get_broadcast(bid)
    if not b:
        raise HTTPException(status_code=404, detail="Broadcast not found")
    if ctx.role != "superadmin" and b["org_id"] != ctx.org_id:
        raise HTTPException(status_code=403, detail="Access denied")

    from core.broadcasts import get_broadcast_sends as _get_sends
    rows = _get_sends(bid, limit=500)
    return {"sends": [
        {"user_id": r["user_id"], "status": r["status"],
         "error": r["error"], "sent_at": r["sent_at"]}
        for r in rows
    ]}


# ---------- Admin: broadcasts (Auto) ----------

@router.get("/max_booking/api/admin/auto_broadcasts")
async def admin_auto_broadcasts(ctx: AdminCtx = Depends(admin_ctx)):
    if not ctx.org_id:
        return {"auto_broadcasts": []}
    rows = list_auto_broadcasts(ctx.org_id)

    # Кэш картинок, чтобы не дёргать БД на каждую строку
    image_previews = {}
    for r in rows:
        iid = r["image_id"]
        if iid and iid not in image_previews:
            img = get_uploaded_image_by_id(iid)
            if img and img["public_token"]:
                image_previews[iid] = f"/max_booking/api/upload/{img['public_token']}"
            else:
                image_previews[iid] = None

    return {"auto_broadcasts": [
        {"id": r["id"], "type": r["type"], "text": r["text"],
         "image_id": r["image_id"], "has_image": bool(r["image_id"]),
         "preview_url": image_previews.get(r["image_id"]) if r["image_id"] else None,
         "delay_value": r["delay_value"], "active": bool(r["active"])}
        for r in rows
    ]}


@router.post("/max_booking/api/admin/auto_broadcasts")
async def admin_auto_broadcast_create(request: Request, ctx: AdminCtx = Depends(org_ctx)):
    body = await request.json()
    atype = body.get("type")
    text = (body.get("text") or "").strip()
    delay_value = int(body.get("delay_value") or 0)
    image_id = _check_image_id(ctx, body.get("image_id"))

    if atype not in ("birthday", "inactive", "after_visit", "welcome_first", "revisit_cycle") or not text:
        raise HTTPException(status_code=400, detail="Invalid data")
    if atype not in ("welcome_first", "revisit_cycle") and delay_value <= 0:
        raise HTTPException(status_code=400, detail="Invalid data")

    aid = create_auto_broadcast(ctx.org_id, atype, text, delay_value, image_id)

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="auto_broadcast_created",
        entity_type="auto_broadcast", entity_id=aid,
        payload={"type": atype, "delay_value": delay_value},
    )
    return {"ok": True, "id": aid}


@router.put("/max_booking/api/admin/auto_broadcasts/{aid}")
async def admin_auto_broadcast_update(request: Request, aid: int, ctx: AdminCtx = Depends(admin_ctx)):
    a = get_auto_broadcast(aid)
    if not a:
        raise HTTPException(status_code=404, detail="Auto broadcast not found")
    if ctx.role != "superadmin" and a["org_id"] != ctx.org_id:
        raise HTTPException(status_code=403, detail="Access denied")

    body = await request.json()
    text = (body.get("text") or "").strip()
    delay_value = int(body.get("delay_value") or 0)
    image_id = _check_image_id(ctx, body.get("image_id"))
    active = int(body.get("active", 1))

    if not text:
        raise HTTPException(status_code=400, detail="Invalid data")
    if a["type"] not in ("welcome_first", "revisit_cycle") and delay_value <= 0:
        raise HTTPException(status_code=400, detail="Invalid data")

    update_auto_broadcast(aid, text, delay_value, image_id, active)

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="auto_broadcast_updated",
        entity_type="auto_broadcast", entity_id=aid,
        payload={"type": a["type"], "active": active},
    )
    return {"ok": True}


@router.delete("/max_booking/api/admin/auto_broadcasts/{aid}")
async def admin_auto_broadcast_delete(aid: int, ctx: AdminCtx = Depends(admin_ctx)):
    a = get_auto_broadcast(aid)
    if not a:
        raise HTTPException(status_code=404, detail="Auto broadcast not found")
    if ctx.role != "superadmin" and a["org_id"] != ctx.org_id:
        raise HTTPException(status_code=403, detail="Access denied")

    delete_auto_broadcast(aid)

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="auto_broadcast_deleted",
        entity_type="auto_broadcast", entity_id=aid,
        payload={"type": a["type"]},
    )
    return {"ok": True}


@router.post("/max_booking/api/admin/auto_broadcasts/{aid}/toggle")
async def admin_auto_broadcast_toggle(aid: int, ctx: AdminCtx = Depends(admin_ctx)):
    a = get_auto_broadcast(aid)
    if not a:
        raise HTTPException(status_code=404, detail="Auto broadcast not found")
    if ctx.role != "superadmin" and a["org_id"] != ctx.org_id:
        raise HTTPException(status_code=403, detail="Access denied")

    toggle_auto_broadcast(aid)

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="auto_broadcast_toggled",
        entity_type="auto_broadcast", entity_id=aid,
        payload={"new_active": 0 if a["active"] else 1},
    )
    return {"ok": True}


@router.post("/max_booking/api/admin/auto_broadcasts/{aid}/test")
async def admin_auto_broadcast_test(aid: int, ctx: AdminCtx = Depends(admin_ctx)):
    """Отправляет админу тестовое сообщение с подставленными фиктивными данными."""
    from core.broadcasts import _send_with_refresh, UNSUB_BUTTONS

    a = get_auto_broadcast(aid)
    if not a:
        raise HTTPException(status_code=404, detail="Auto broadcast not found")
    if ctx.role != "superadmin" and a["org_id"] != ctx.org_id:
        raise HTTPException(status_code=403, detail="Access denied")

    text = a["text"] or ""
    text = text.replace("{name}", "Иван")
    text = text.replace("{service}", "Тестовая услуга")
    text = text.replace("{scheduled_at}", "2026-11-15 15:00")
    text = text.replace("{address}", "ул. Ленина, 1")
    text = text.replace("{prep}", "Натощак, не есть 6 часов")
    text = text.replace("{last_visit}", "2026-08-15")
    text = text.replace("{days_inactive}", "92")
    text = text.replace("{days_since_visit}", "92")

    header = "🧪 **ТЕСТ** · данные для примера\n\n"
    full_text = header + text

    image_id = a["image_id"]
    try:
        if image_id:
            await _send_with_refresh(
                int(ctx.uid), full_text, image_id,
                buttons=UNSUB_BUTTONS, fmt="markdown",
            )
        else:
            await send_to_client_raw(
                int(ctx.uid), full_text, buttons=UNSUB_BUTTONS, fmt="markdown",
            )
    except UserBlocked:
        raise HTTPException(status_code=409, detail="Вы заблокировали бота — тест не отправится")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка отправки: {e}")

    return {"ok": True}


