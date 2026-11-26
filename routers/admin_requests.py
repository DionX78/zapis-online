"""Админские ручки: requests, clients, blocked, waitlist."""
import asyncio
import logging
import uuid as _uuid
from pathlib import Path as _Path

from fastapi import APIRouter, Request, HTTPException, Depends, UploadFile, File, Form

import config
from core.channels.base import UserBlocked
from core.messaging import (
    send_to_client_raw, send_to_client_with_image_raw,
    send_to_client_with_file_raw, upload_file_for_client,
)
from core.auth import AdminCtx, admin_ctx, org_ctx
from core.booking import (
    BookingContext,
    create_booking_unified,
    move_booking_unified,
)
from core.client_exports import (
    build_client_export_csv,
    build_client_export_xlsx,
    build_client_export_pdf,
)
from core.geo import route_lines
from core.messaging import send_to_client
from core.notify_ics import send_confirmation_with_ics
from core.uploads import _process_upload_image
from core.waitlist import notify_single_waitlist_entry as wl_notify_single
from handlers.booking import normalize_phone
from storage.db import (
    list_requests_for_org,
    get_marketing_opt_out_batch,
    is_user_blocked_batch,
    search_clients, get_client, upsert_client, get_or_create_client_by_phone,
    get_client_platforms, get_client_platforms_batch,
    set_marketing_opt_out, export_client_data, delete_client_data,
    get_client_full, update_client_notes_tags, reset_client_no_show,
    set_client_photo, block_user, unblock_user, is_user_blocked,
    list_blocked_users,
    get_request, get_slot, get_service, get_doctor, get_branch, get_org,
    get_org_settings, update_request_status, release_slot, set_request_payment,
    count_active_bookings_on_date, list_active_bookings_on_date,
    slots_needed_for_service, db_ctx, doctor_makes_service,
    update_booking_extended,
    save_uploaded_image_full, delete_uploaded_image_file,
    log_audit,
    create_waitlist_entry, get_waitlist_entry, list_waitlist,
    update_waitlist_entry, cancel_waitlist_entry, fulfill_waitlist_entry,
)

log = logging.getLogger(__name__)

router = APIRouter()


# ---------- Admin: requests ----------

@router.get("/max_booking/api/admin/requests")
async def admin_requests(
    date_from: str | None = None,
    date_to: str | None = None,
    status: str | None = None,
    auto_done: str | None = None,
    page: int = 1,
    per_page: int = 20,
    ctx: AdminCtx = Depends(org_ctx),
):
    rows, total = await asyncio.to_thread(
        list_requests_for_org,
        ctx.org_id, date_from=date_from, date_to=date_to,
        status=status, page=page, per_page=per_page,
        auto_done_only=(auto_done == "1"),
    )
    user_ids = list({r["user_id"] for r in rows if r["user_id"]})
    opt_out_map = get_marketing_opt_out_batch(user_ids)
    blocked_map = is_user_blocked_batch(user_ids)
    total_pages = max(1, (total + per_page - 1) // per_page)
    return {
        "requests": [
            {"id": r["id"], "user_id": r["user_id"], "service_id": r["service_id"],
             "service_name": r["service_name"],
             "scheduled_at": r["scheduled_at"], "phone": r["phone"], "status": r["status"],
             "address": r["address"], "doctor": r["doctor"],
             "doctor_id": r["doctor_id"], "slot_id": r["slot_id"],
             "created_at": r["created_at"],
             "actual_amount": r["actual_amount"], "payment_method": r["payment_method"],
             "done_auto": bool(r["done_auto"]),
             "slots_count": r["slots_count"] or 1,
             "marketing_opt_out": opt_out_map.get(r["user_id"], False),
             "blocked": bool(blocked_map.get(r["user_id"]))}
            for r in rows
        ],
        "total": total, "page": page, "per_page": per_page, "total_pages": total_pages,
    }


@router.get("/max_booking/api/admin/clients/search")
async def admin_clients_search(
    q: str = "",
    limit: int = 20,
    ctx: AdminCtx = Depends(org_ctx),
):
    rows = await asyncio.to_thread(search_clients, ctx.org_id, q, limit=limit)
    uid_list = [r["user_id"] for r in rows]
    platforms = get_client_platforms_batch(uid_list)
    return {"clients": [
        {"user_id": r["user_id"], "first_name": r["first_name"] or "",
         "last_name": r["last_name"] or "", "middle_name": r["middle_name"] or "",
         "phone": r["phone"] or "", "last_visit_at": r["last_visit_at"],
         "has_max": not str(r["user_id"]).startswith("phone:"),
         "channels": sorted(set(platforms.get(r["user_id"], [])))}
        for r in rows
    ]}


@router.put("/max_booking/api/admin/client/{user_id}/marketing")
async def admin_client_marketing(request: Request, user_id: str, ctx: AdminCtx = Depends(org_ctx)):
    body = await request.json()
    opt_out = bool(body.get("opt_out", True))

    client = get_client(user_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    if client["org_id"] is not None and ctx.role != "superadmin" and client["org_id"] != ctx.org_id:
        raise HTTPException(status_code=403, detail="Access denied")

    set_marketing_opt_out(user_id, opt_out)
    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid,
        action="marketing_opt_out_changed",
        entity_type="client", entity_id=user_id,
        payload={"opt_out": opt_out},
    )
    return {"ok": True, "opt_out": opt_out}


@router.get("/max_booking/api/admin/client/{user_id}/export-json")
async def admin_client_export_json(user_id: str, ctx: AdminCtx = Depends(org_ctx)):
    """Выгрузка всех данных клиента (152-ФЗ, право на доступ) в JSON."""
    client = get_client(user_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    if ctx.role != "superadmin" and client["org_id"] not in (None, ctx.org_id):
        raise HTTPException(status_code=403, detail="Access denied")

    data = export_client_data(user_id, ctx.org_id)

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="client_data_exported",
        entity_type="client", entity_id=user_id, payload={},
    )

    return data


@router.delete("/max_booking/api/admin/client/{user_id}")
async def admin_client_delete(user_id: str, ctx: AdminCtx = Depends(org_ctx)):
    """Удаление данных клиента (152-ФЗ, право на забвение).

    PII удаляется полностью. History обезличивается — остаётся для
    финансовой отчётности, но идентифицировать клиента по ней нельзя.
    Активные записи отменяются, слоты освобождаются.
    """
    client = get_client(user_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    if ctx.role != "superadmin" and client["org_id"] not in (None, ctx.org_id):
        raise HTTPException(status_code=403, detail="Access denied")

    cancelled = delete_client_data(user_id, ctx.org_id)

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="client_data_deleted",
        entity_type="client", entity_id=user_id,
        payload={"reason": "152-fz request", "cancelled_requests": cancelled},
    )

    return {"ok": True, "cancelled_requests": cancelled}


@router.post("/max_booking/api/admin/client/{user_id}/block")
async def admin_block_client(request: Request, user_id: str, ctx: AdminCtx = Depends(org_ctx)):
    try:
        body = await request.json()
        if not isinstance(body, dict):
            body = {}
    except Exception:
        body = {}

    reason = (body.get("reason") or "").strip()[:500]

    client = get_client(user_id)
    phone = client["phone"] if client else ""

    block_user(user_id, ctx.org_id, phone, reason, ctx.uid)

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="client_blocked",
        entity_type="client", entity_id=user_id,
        payload={"reason": reason, "phone": phone},
    )

    return {"ok": True}


@router.delete("/max_booking/api/admin/client/{user_id}/block")
async def admin_unblock_client(user_id: str, ctx: AdminCtx = Depends(org_ctx)):
    unblock_user(user_id)

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="client_unblocked",
        entity_type="client", entity_id=user_id, payload={},
    )

    return {"ok": True}


@router.get("/max_booking/api/admin/blocked_users")
async def admin_blocked_users(ctx: AdminCtx = Depends(org_ctx)):
    rows = list_blocked_users(ctx.org_id)
    return {"users": [
        {"user_id": r["user_id"], "phone": r["phone"], "reason": r["reason"],
         "blocked_at": r["blocked_at"], "blocked_by": r["blocked_by"]}
        for r in rows
    ]}


@router.get("/max_booking/api/admin/client/{user_id}/card")
async def admin_client_card(user_id: str, ctx: AdminCtx = Depends(org_ctx)):
    """Полная карточка клиента: профиль, история, услуги, специалисты, предстоящие."""
    data = await asyncio.to_thread(get_client_full, user_id, ctx.org_id)
    if not data:
        raise HTTPException(status_code=404, detail="Client not found")
    data["channels"] = get_client_platforms(user_id)

    client = data["client"]
    if ctx.role != "superadmin" and client["org_id"] not in (None, ctx.org_id):
        raise HTTPException(status_code=403, detail="Access denied")

    tags_list = []
    if client["tags"]:
        try:
            import json as _json
            tags_list = _json.loads(client["tags"])
            if not isinstance(tags_list, list):
                tags_list = []
        except Exception:
            tags_list = []

    blocked = is_user_blocked(user_id)

    return {
        "user_id": client["user_id"],
        "org_id": client["org_id"],
        "first_name": client["first_name"] or "",
        "last_name": client["last_name"] or "",
        "middle_name": client["middle_name"] or "",
        "phone": client["phone"] or "",
        "gender": client["gender"] or "",
        "birth_date": client["birth_date"] or "",
        "last_visit_at": client["last_visit_at"],
        "favorite_doctor_id": client["favorite_doctor_id"],
        "favorite_doctor_name": data["favorite_doctor_name"],
        "marketing_opt_out": bool(client["marketing_opt_out"]),
        "consent_152fz": bool(client["consent_152fz"]),
        "consent_given_at": client["consent_given_at"],
        "notes": client["notes"] or "",
        "tags": tags_list,
        "no_show_count": client["no_show_count"] or 0,
        "no_show_last_at": client["no_show_last_at"],
        "blocked": blocked,
        "created_at": client["created_at"],
        "status_label": data["status_label"],
        "aggregates": {
            "visits_done": data["aggregates"]["visits_done"] or 0,
            "visits_no_show": data["aggregates"]["visits_no_show"] or 0,
            "total_revenue": data["aggregates"]["total_revenue"] or 0,
            "first_visit_at": data["aggregates"]["first_visit_at"],
            "last_done_at": data["aggregates"]["last_done_at"],
        },
        "photo_url": data.get("photo_url"),
        "services_list": data["services_list"],
        "specialists_list": data["specialists_list"],
        "upcoming": [
            {"id": r["id"], "service_name": r["service_name"],
             "scheduled_at": r["scheduled_at"], "status": r["status"],
             "doctor": r["doctor"], "slots_count": r["slots_count"] or 1}
            for r in data["upcoming"]
        ],
    }


@router.put("/max_booking/api/admin/client/{user_id}/card")
async def admin_client_card_update(request: Request, user_id: str, ctx: AdminCtx = Depends(org_ctx)):
    """Обновляет заметки и теги клиента."""
    client = get_client(user_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    if ctx.role != "superadmin" and client["org_id"] not in (None, ctx.org_id):
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        body = await request.json()
        if not isinstance(body, dict):
            body = {}
    except Exception:
        body = {}

    notes = (body.get("notes") or "").strip()[:5000]
    tags = body.get("tags") or []
    if not isinstance(tags, list):
        raise HTTPException(status_code=400, detail="tags must be a list")
    clean_tags = []
    for t in tags:
        if not isinstance(t, str):
            continue
        t = t.strip()[:50]
        if t and t not in clean_tags:
            clean_tags.append(t)
    if len(clean_tags) > 20:
        raise HTTPException(status_code=400, detail="Не больше 20 тегов")

    update_client_notes_tags(user_id, notes, clean_tags)

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="client_card_updated",
        entity_type="client", entity_id=user_id,
        payload={"tags_count": len(clean_tags), "notes_len": len(notes)},
    )

    return {"ok": True, "notes": notes, "tags": clean_tags}


@router.post("/max_booking/api/admin/client/{user_id}/reset_no_show")
async def admin_client_reset_no_show(user_id: str, ctx: AdminCtx = Depends(org_ctx)):
    """Сбрасывает счётчик неявок клиента."""
    client = get_client(user_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    if ctx.role != "superadmin" and client["org_id"] not in (None, ctx.org_id):
        raise HTTPException(status_code=403, detail="Access denied")

    reset_client_no_show(user_id)

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="client_no_show_reset",
        entity_type="client", entity_id=user_id, payload={},
    )

    return {"ok": True}


@router.post("/max_booking/api/admin/client/{user_id}/photo")
async def admin_client_upload_photo(
    user_id: str,
    file: UploadFile = File(...),
    ctx: AdminCtx = Depends(org_ctx),
):
    """Загружает фото клиента. Сжимает, хранит локально, отдаёт через public_token."""
    client = get_client(user_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    if ctx.role != "superadmin" and client["org_id"] not in (None, ctx.org_id):
        raise HTTPException(status_code=403, detail="Access denied")

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

    set_client_photo(user_id, upload_id)

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="client_photo_uploaded",
        entity_type="client", entity_id=user_id,
        payload={"upload_id": upload_id, "size": len(content), "mime": mime},
    )

    return {
        "ok": True,
        "photo_upload_id": upload_id,
        "photo_url": f"/max_booking/api/upload/{public_token}",
    }


@router.delete("/max_booking/api/admin/client/{user_id}/photo")
async def admin_client_delete_photo(user_id: str, ctx: AdminCtx = Depends(org_ctx)):
    """Отвязывает фото клиента. Файл на диске остаётся, но ссылка перестаёт быть активной."""
    client = get_client(user_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    if ctx.role != "superadmin" and client["org_id"] not in (None, ctx.org_id):
        raise HTTPException(status_code=403, detail="Access denied")

    set_client_photo(user_id, None)

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="client_photo_deleted",
        entity_type="client", entity_id=user_id, payload={},
    )

    return {"ok": True}


@router.post("/max_booking/api/admin/client/{user_id}/message-with-file")
async def admin_client_send_message_with_file(
    user_id: str,
    file: UploadFile = File(None),
    text: str = Form(""),
    ctx: AdminCtx = Depends(org_ctx),
):
    """Отправляет клиенту сообщение с файлом. Фото сжимаются.
    При ошибке отправки возвращает ссылку для скачивания."""
    client = get_client(user_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    if ctx.role != "superadmin" and client["org_id"] not in (None, ctx.org_id):
        raise HTTPException(status_code=403, detail="Access denied")

    clean_text = (text or "").strip()
    if len(clean_text) > 4000:
        raise HTTPException(status_code=400, detail="Текст не длиннее 4000 символов")
    if not clean_text and not file:
        raise HTTPException(status_code=400, detail="Введите текст или прикрепите файл")

    if not file:
        status, err = await send_to_client(user_id, clean_text, fmt="markdown")
        log_audit(
            org_id=ctx.org_id, user_id=ctx.uid, action="client_message_sent",
            entity_type="client", entity_id=user_id,
            payload={"status": status, "text_len": len(clean_text), "has_file": False},
        )
        return {"ok": status == "sent", "status": status, "error": err, "url": None}

    allowed_mimes = (
        "image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif",
        "application/pdf", "text/plain", "text/csv",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    if file.content_type not in allowed_mimes:
        raise HTTPException(
            status_code=400,
            detail=f"Формат {file.content_type} не поддерживается. "
                   f"Разрешены: изображения, PDF, TXT, CSV, DOC/DOCX, XLS/XLSX.",
        )

    raw = await file.read()
    if len(raw) > config.MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"Файл больше {config.MAX_UPLOAD_SIZE // (1024 * 1024)} МБ",
        )
    if not raw:
        raise HTTPException(status_code=400, detail="Пустой файл")

    is_image = file.content_type in ("image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif")
    if is_image:
        content, mime, ext = _process_upload_image(raw, file.content_type)
    else:
        content = raw
        mime = file.content_type
        ext = "bin"
        if mime == "application/pdf": ext = "pdf"
        elif mime == "text/plain": ext = "txt"
        elif mime == "text/csv": ext = "csv"
        elif mime == "application/msword": ext = "doc"
        elif "wordprocessingml" in mime: ext = "docx"
        elif mime == "application/vnd.ms-excel": ext = "xls"
        elif "spreadsheetml" in mime: ext = "xlsx"

    orig_name = file.filename or f"attachment.{ext}"
    safe_name = "".join(c for c in orig_name if c.isalnum() or c in "._- ").strip() or f"attachment.{ext}"
    caption = clean_text or "📎 Файл"

    status = "error"
    err = None
    try:
        token = await upload_file_for_client(
            user_id, content, filename=safe_name, mime=mime,
            upload_type="image" if is_image else "file",
        )
        if is_image:
            await send_to_client_with_image_raw(user_id, caption, token, fmt="markdown")
        else:
            await send_to_client_with_file_raw(user_id, caption, token, fmt="markdown")
        status = "sent"
    except UserBlocked:
        status = "blocked"
    except Exception as e:
        log.warning("send file to client %s failed: %s", user_id, e)
        err = str(e)[:200]

    public_url = None
    full_url = None
    if status != "sent":
        rel_dir = str(ctx.org_id)
        abs_dir = _Path(config.UPLOADS_DIR) / rel_dir
        abs_dir.mkdir(parents=True, exist_ok=True)
        local_name = f"{_uuid.uuid4().hex}.{ext}"
        abs_path = abs_dir / local_name
        abs_path.write_bytes(content)
        rel_path = f"{rel_dir}/{local_name}"
        uid_img, public_token = save_uploaded_image_full(
            token=None, file_path=rel_path, mime_type=mime,
            original_filename=safe_name, file_size=len(content),
            org_id=ctx.org_id, uploaded_by=ctx.uid,
        )
        public_url = f"/max_booking/api/upload/{public_token}"
        full_url = config.WEBHOOK_BASE_URL.rstrip("/") + public_url

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="client_message_sent",
        entity_type="client", entity_id=user_id,
        payload={"status": status, "text_len": len(clean_text),
                 "has_file": True, "mime": mime, "size": len(content)},
    )

    return {
        "ok": status == "sent",
        "status": status,
        "error": err,
        "url": public_url,
        "full_url": full_url,
        "filename": safe_name,
    }


@router.post("/max_booking/api/admin/client/{user_id}/message")
async def admin_client_send_message(request: Request, user_id: str, ctx: AdminCtx = Depends(org_ctx)):
    """Отправить произвольное сообщение клиенту (пока только через MAX)."""
    client = get_client(user_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    if ctx.role != "superadmin" and client["org_id"] not in (None, ctx.org_id):
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        body = await request.json()
        if not isinstance(body, dict):
            body = {}
    except Exception:
        body = {}

    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Текст сообщения обязателен")
    if len(text) > 4000:
        raise HTTPException(status_code=400, detail="Текст не длиннее 4000 символов")

    status, err = await send_to_client(user_id, text, fmt="markdown")

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="client_message_sent",
        entity_type="client", entity_id=user_id,
        payload={"status": status, "text_len": len(text)},
    )

    return {"ok": status == "sent", "status": status, "error": err}


@router.get("/max_booking/api/admin/client/{user_id}/export")
async def admin_client_export_file(
    user_id: str,
    format: str = "csv",
    target: str = "admin",
    ctx: AdminCtx = Depends(org_ctx),
):
    """Генерирует CSV/XLSX/PDF и отправляет файл:
    - target=admin (по умолчанию): в чат админу, который запросил.
    - target=client: в чат клиенту через MAX, если у него есть MAX и он не заблокировал бота.
    """
    from datetime import datetime as _dt

    data = await asyncio.to_thread(get_client_full, user_id, ctx.org_id)
    if not data:
        raise HTTPException(status_code=404, detail="Client not found")
    client = data["client"]
    if ctx.role != "superadmin" and client["org_id"] not in (None, ctx.org_id):
        raise HTTPException(status_code=403, detail="Access denied")

    org = get_org(ctx.org_id)
    data["org_name"] = org["name"] if org else ""

    fmt = (format or "csv").lower().strip()
    tgt = (target or "admin").lower().strip()
    if tgt not in ("admin", "client"):
        raise HTTPException(status_code=400, detail="target must be admin or client")

    if tgt == "client":
        if fmt == "csv":
            raise HTTPException(
                status_code=400,
                detail="Клиенту доступны только PDF и XLSX",
            )
        if str(user_id).startswith("phone:"):
            raise HTTPException(
                status_code=400,
                detail="У клиента нет MAX-профиля — отправить файл невозможно",
            )
        if is_user_blocked(user_id):
            raise HTTPException(
                status_code=400,
                detail="Клиент заблокирован",
            )

    ts = _dt.now().strftime("%Y-%m-%d")
    fio = " ".join(p for p in [client["last_name"], client["first_name"], client["middle_name"]] if p).strip() or user_id
    for_client = (tgt == "client")

    try:
        if fmt == "csv":
            content = build_client_export_csv(data, client)
            filename = f"client_{user_id}_{ts}.csv"
            mime = "text/csv"
            ext = "csv"
        elif fmt == "xlsx":
            content = await asyncio.to_thread(
                build_client_export_xlsx, data, client, for_client,
            )
            prefix = "my_visits" if for_client else "client"
            filename = f"{prefix}_{user_id}_{ts}.xlsx"
            mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ext = "xlsx"
        elif fmt == "pdf":
            content = await asyncio.to_thread(
                build_client_export_pdf, data, client, for_client,
            )
            prefix = "my_visits" if for_client else "client"
            filename = f"{prefix}_{user_id}_{ts}.pdf"
            mime = "application/pdf"
            ext = "pdf"
        else:
            raise HTTPException(status_code=400, detail="format must be csv, xlsx or pdf")
    except HTTPException:
        raise
    except Exception as e:
        log.error("export build error: %s", e)
        raise HTTPException(status_code=500, detail=f"Ошибка формирования файла: {e}")

    rel_dir = str(ctx.org_id)
    abs_dir = _Path(config.UPLOADS_DIR) / rel_dir
    abs_dir.mkdir(parents=True, exist_ok=True)
    local_name = f"{_uuid.uuid4().hex}.{ext}"
    abs_path = abs_dir / local_name
    abs_path.write_bytes(content)
    rel_path = f"{rel_dir}/{local_name}"

    uid_int, public_token = save_uploaded_image_full(
        token=None, file_path=rel_path, mime_type=mime,
        original_filename=filename, file_size=len(content),
        org_id=ctx.org_id, uploaded_by=ctx.uid,
    )
    public_url = f"/max_booking/api/upload/{public_token}"
    full_url = config.WEBHOOK_BASE_URL.rstrip("/") + public_url

    if tgt == "client":
        send_caption = (
            f"📄 **Ваши визиты**\n\n"
            f"Файл: {filename}\n"
            f"Если нужно сохранить на телефон — откройте файл и нажмите «Скачать»."
        )
        recipient_id = int(user_id)
    else:
        send_caption = (
            f"📥 **Экспорт данных клиента**\n\n"
            f"👤 {fio}\n"
            f"📄 {filename} ({len(content) // 1024} KB)"
        )
        recipient_id = int(ctx.uid)

    sent_ok = False
    send_err = None
    try:
        token = await upload_file_for_client(
            recipient_id, content, filename=filename, mime=mime, upload_type="file",
        )
        await send_to_client_with_file_raw(recipient_id, send_caption, token, fmt="markdown")
        sent_ok = True
    except UserBlocked:
        send_err = "blocked"
    except Exception as e:
        log.error("export send to %s failed: %s", recipient_id, e)
        send_err = str(e)[:200]

    if sent_ok:
        try:
            delete_uploaded_image_file(uid_int)
            public_url = None
            full_url = None
        except Exception as e:
            log.warning("export cleanup failed for upload_id=%s: %s", uid_int, e)

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid,
        action=f"client_export_{fmt}_to_{tgt}",
        entity_type="client", entity_id=user_id,
        payload={"filename": filename, "size": len(content), "sent_to_chat": sent_ok},
    )

    return {
        "ok": True,
        "filename": filename,
        "format": fmt,
        "target": tgt,
        "url": public_url,
        "full_url": full_url,
        "sent_to_chat": sent_ok,
        "send_error": send_err,
    }


@router.get("/max_booking/api/admin/request/{request_id}/slot_options")
async def admin_request_slot_options(request_id: int, ctx: AdminCtx = Depends(org_ctx)):
    """Сколько подряд идущих слотов доступно для этой записи.

    Идём по РЕАЛЬНОМУ списку слотов специалиста/филиала/даты (ORDER BY time),
    а не по вычисленному времени с шагом step_min. Так не ломаемся,
    если шаг сетки в настройках не совпадает с шагом реальных слотов.

    «Наши» слоты (is_booked=1, request_id=current) считаем доступными —
    их можно как оставить, так и уменьшить.
    """
    req = get_request(request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if ctx.role != "superadmin" and req["org_id"] != ctx.org_id:
        raise HTTPException(status_code=403, detail="Access denied")

    first_slot_id = req["slot_id"]
    if not first_slot_id:
        raise HTTPException(status_code=409, detail="У записи нет первого слота")

    slot = get_slot(first_slot_id)
    if not slot:
        raise HTTPException(status_code=409, detail="Первый слот не найден")

    settings = get_org_settings(ctx.org_id)
    step_min = int(settings.get("slot_step_min", 30) or 30)

    with db_ctx() as conn:
        all_slots = conn.execute(
            "SELECT id, time, is_booked, request_id FROM slots "
            "WHERE date=? AND doctor_id IS ? AND branch_id IS ? "
            "ORDER BY time",
            (slot["date"], slot["doctor_id"], slot["branch_id"]),
        ).fetchall()

    first_idx = None
    for i, s in enumerate(all_slots):
        if s["id"] == first_slot_id:
            first_idx = i
            break
    if first_idx is None:
        raise HTTPException(status_code=409, detail="Первый слот не найден в списке")

    max_consecutive = 0
    slots_list = []
    limit_reason = None
    break_from = None
    break_until = None
    conflict_at = None
    prev_min = None

    for i in range(first_idx, len(all_slots)):
        s = all_slots[i]

        if prev_min is not None:
            expected_min = prev_min + step_min
            if expected_min >= 24 * 60:
                limit_reason = "end_of_day"
                break
            expected_time = f"{expected_min // 60:02d}:{expected_min % 60:02d}"

            try:
                ch, cm = map(int, s["time"].split(":"))
                cur_min = ch * 60 + cm
            except Exception:
                limit_reason = "bad_time"
                break

            if cur_min != expected_min:
                if cur_min > expected_min:
                    limit_reason = "break"
                    break_from = expected_time
                    break_until = s["time"]
                else:
                    limit_reason = "out_of_order"
                break

        is_ours = (s["request_id"] == request_id)
        is_free = (s["is_booked"] == 0)

        if not (is_ours or is_free):
            if prev_min is None:
                limit_reason = "first_not_ours"
            else:
                limit_reason = "busy"
                conflict_at = s["time"]
            break

        max_consecutive += 1
        slots_list.append({
            "slot_id": s["id"], "time": s["time"],
            "is_current": is_ours, "is_free": is_free,
        })
        h, m = map(int, s["time"].split(":"))
        prev_min = h * 60 + m
    else:
        if prev_min is not None and limit_reason is None:
            limit_reason = "end_of_slots"

    suggested = (
        slots_needed_for_service(req["service_id"], step_min)
        if req["service_id"] else 1
    )

    return {
        "request_id": request_id,
        "max_consecutive": max_consecutive,
        "current_slots_count": req["slots_count"] or 1,
        "suggested_by_service": suggested,
        "step_min": step_min,
        "limit_reason": limit_reason,
        "break_from": break_from,
        "break_until": break_until,
        "conflict_at": conflict_at,
        "first_slot": {
            "date": slot["date"], "time": slot["time"],
            "doctor_id": slot["doctor_id"], "branch_id": slot["branch_id"],
        },
        "slots": slots_list,
    }


@router.put("/max_booking/api/admin/request/{request_id}/edit")
async def admin_request_edit(request: Request, request_id: int, ctx: AdminCtx = Depends(org_ctx)):
    """Редактирование услуги и/или количества слотов существующей записи."""
    req = get_request(request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if ctx.role != "superadmin" and req["org_id"] != ctx.org_id:
        raise HTTPException(status_code=403, detail="Access denied")
    if req["status"] not in ("pending", "confirmed"):
        raise HTTPException(status_code=409, detail="Можно редактировать только активную запись")

    try:
        body = await request.json()
        if not isinstance(body, dict):
            body = {}
    except Exception:
        body = {}

    if "service_id" in body:
        raw_sid = body.get("service_id")
        if raw_sid in (None, "", 0):
            new_service_id = None
            new_service_name = "Приём (услуга не указана)"
        else:
            new_service_id = str(raw_sid).strip()
            svc = get_service(new_service_id)
            if not svc or svc["org_id"] != ctx.org_id:
                raise HTTPException(status_code=404, detail="Услуга не найдена")
            new_service_name = svc["name"]
            if req["doctor_id"] and not doctor_makes_service(req["doctor_id"], new_service_id):
                raise HTTPException(status_code=400, detail="Специалист не оказывает эту услугу")
    else:
        new_service_id = req["service_id"]
        new_service_name = req["service_name"]

    settings = get_org_settings(ctx.org_id)
    step_min = int(settings.get("slot_step_min", 30) or 30)

    if "slots_count" in body:
        try:
            new_slots_count = int(body["slots_count"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid slots_count")
        if new_slots_count < 1 or new_slots_count > 20:
            raise HTTPException(status_code=400, detail="slots_count must be 1..20")
    else:
        new_slots_count = req["slots_count"] or 1

    ok, err, msg, _payload = update_booking_extended(
        request_id, new_service_id, new_service_name, new_slots_count, step_min,
    )
    if not ok:
        raise HTTPException(status_code=409, detail=msg or err or "Не удалось обновить")

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="request_edited",
        entity_type="request", entity_id=request_id,
        payload={"service_id": new_service_id, "service_name": new_service_name,
                 "slots_count": new_slots_count},
    )

    if (req["service_id"] != new_service_id) or ((req["slots_count"] or 1) != new_slots_count):
        if not str(req["user_id"]).startswith("phone:"):
            try:
                svc = get_service(new_service_id) if new_service_id else None
                service_duration = (svc["duration_min"] if svc else None) or None
                booked_min = new_slots_count * step_min
                default_slots = (
                    slots_needed_for_service(new_service_id, step_min)
                    if new_service_id else 1
                )
                overridden = new_slots_count != default_slots

                text = (
                    f"🔄 **Ваша запись обновлена**\n\n"
                    f"**{new_service_name}**\n"
                    f"📅 {req['scheduled_at']}\n"
                )
                if service_duration:
                    text += f"⏱ Услуга: {service_duration} мин\n"
                if overridden:
                    text += f"🗓 Забронировано: {new_slots_count} слота ({booked_min} мин)\n"
                if new_service_id is None:
                    text += "\n⚠️ Услуга не указана. Свяжитесь с администратором для уточнения."
                await send_to_client(req["user_id"], text, fmt="markdown")
            except Exception as e:
                log.warning("edit request notify failed: %s", e)

    return {
        "ok": True,
        "id": request_id,
        "service_id": new_service_id,
        "service_name": new_service_name,
        "slots_count": new_slots_count,
    }


@router.post("/max_booking/api/admin/request/{request_id}/move")
async def admin_request_move(request: Request, request_id: int, ctx: AdminCtx = Depends(org_ctx)):
    """Перенос записи на новый слот. Освобождает старые, занимает новые."""
    req = get_request(request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if ctx.role != "superadmin" and req["org_id"] != ctx.org_id:
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        body = await request.json()
        if not isinstance(body, dict):
            body = {}
    except Exception:
        body = {}

    try:
        new_slot_id = int(body.get("new_slot_id"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="new_slot_id обязателен")

    result = await move_booking_unified(request_id, new_slot_id, via="admin")

    if not result.ok:
        status_map = {
            "request_not_found": 404,
            "request_not_active": 409,
            "slot_not_found": 404,
            "slot_org_mismatch": 403,
            "slot_taken": 409,
            "slot_in_past": 400,
            "already_at_time": 409,
            "no_slots_for_duration": 409,
            "doctor_skill": 400,
            "move_failed": 409,
        }
        code = status_map.get(result.error_code, 400)
        raise HTTPException(status_code=code, detail=result.error_msg or "Не удалось перенести")

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="request_moved",
        entity_type="request", entity_id=request_id,
        payload={"from": req["scheduled_at"], "to": result.scheduled_at},
    )

    return {"ok": True, "id": request_id, "scheduled_at": result.scheduled_at}


@router.post("/max_booking/api/admin/request/create")
async def admin_request_create(request: Request, ctx: AdminCtx = Depends(org_ctx)):
    body = await request.json()
    service_id = str(body.get("service_id") or "").strip() or None
    slot_id_raw = body.get("slot_id")
    phone = str(body.get("phone") or "").strip()
    first_name = str(body.get("first_name") or "").strip()[:100]
    last_name = str(body.get("last_name") or "").strip()[:100]
    middle_name = str(body.get("middle_name") or "").strip()[:100]
    user_id_hint = (body.get("user_id") or "").strip()

    if not slot_id_raw or not phone:
        raise HTTPException(status_code=400, detail="slot_id и phone обязательны")

    phone = normalize_phone(phone)
    if not phone:
        raise HTTPException(status_code=400, detail="Некорректный телефон")

    try:
        slot_id = int(slot_id_raw)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid slot_id")

    slot = get_slot(slot_id)
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")
    if slot["org_id"] != ctx.org_id:
        raise HTTPException(status_code=403, detail="Slot belongs to another organization")

    if slot["is_booked"]:
        raise HTTPException(status_code=409, detail="Slot already booked")

    if user_id_hint:
        user_id = user_id_hint
        existing = get_client(user_id)
        if existing and existing["org_id"] not in (None, ctx.org_id):
            raise HTTPException(status_code=400, detail="Client belongs to another organization")
        if existing and existing["org_id"] is None:
            upsert_client(user_id, org_id=ctx.org_id)
        # Телефон из формы сохраняем выбранному клиенту: пустое поле
        # телефона не должно «терять» выбор и плодить phone-дублей.
        if existing and (existing["phone"] or "") != phone:
            upsert_client(user_id, phone=phone)
    else:
        user_id = get_or_create_client_by_phone(
            ctx.org_id, first_name, last_name, middle_name, phone,
        )

    ctx_b = BookingContext(
        org_id=ctx.org_id,
        user_id=str(user_id),
        slot_id=slot_id,
        service_id=service_id,
        phone=phone,
        first_name=first_name,
        last_name=last_name,
        middle_name=middle_name,
        slots_count_override=body.get("slots_count_override") if body.get("slots_count_override") is not None else None,
        via="admin",
        skip_consent_check=True,
        confirm_over_daily_limit=bool(body.get("confirm_over_daily_limit")),
    )

    result = await create_booking_unified(ctx_b)

    if not result.ok:
        if result.error_code == "daily_limit_exceeded":
            booking_settings = get_org_settings(ctx.org_id)
            max_per_day = int(booking_settings.get("max_bookings_per_day", 2) or 0)
            date_str = slot["date"]
            day_count = count_active_bookings_on_date(user_id, ctx.org_id, date_str)
            existing = list_active_bookings_on_date(user_id, ctx.org_id, date_str)
            return {
                "ok": False,
                "error_code": "daily_limit_exceeded",
                "message": (
                    f"У клиента уже {day_count} активных записей на этот день "
                    f"(лимит {max_per_day}). Всё равно создать новую?"
                ),
                "existing_count": day_count,
                "max_per_day": max_per_day,
                "existing_bookings": [
                    {
                        "id": r["id"],
                        "service_name": r["service_name"],
                        "scheduled_at": r["scheduled_at"],
                        "doctor": r["doctor"],
                    }
                    for r in existing
                ],
            }
        status_map = {
            "slot_not_found": 404,
            "slot_org_mismatch": 403,
            "slot_taken": 409,
            "slot_service_mismatch": 400,
            "service_inactive": 404,
            "service_org_mismatch": 400,
            "no_phone": 400,
            "invalid_slots_count": 400,
            "no_slots_for_duration": 409,
            "already_at_time": 409,
            "too_many_active": 409,
            "doctor_skill": 400,
            "blocked": 403,
            "slot_in_past": 400,
        }
        code = status_map.get(result.error_code, 400)
        raise HTTPException(status_code=code, detail=result.error_msg or "Не удалось создать запись")

    return {
        "ok": True,
        "id": result.request_id,
        "status": result.status,
        "user_id": user_id,
        "notified": result.notify_status == "sent",
        "notify_status": result.notify_status,
        "notify_error": None,
        "slots_count": result.slots_count,
    }


@router.post("/max_booking/api/admin/request/{request_id}/done")
async def admin_mark_done(request: Request, request_id: int, ctx: AdminCtx = Depends(admin_ctx)):
    try:
        body = await request.json()
        if not isinstance(body, dict):
            body = {}
    except Exception:
        body = {}
    return await _mark_visit(ctx, request_id, "done", body)


@router.post("/max_booking/api/admin/request/{request_id}/no_show")
async def admin_mark_no_show(request_id: int, ctx: AdminCtx = Depends(admin_ctx)):
    return await _mark_visit(ctx, request_id, "no_show", {})


async def _mark_visit(ctx: AdminCtx, request_id: int, new_status: str, body: dict | None = None):
    body = body or {}
    req = get_request(request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    r_org_id = req["org_id"]
    status = req["status"]

    if ctx.role != "superadmin" and r_org_id != ctx.org_id:
        raise HTTPException(status_code=403, detail="Access denied")

    actual_amount = None
    payment_method = None
    if new_status == "done":
        raw_amount = body.get("actual_amount")
        if raw_amount is not None and raw_amount != "":
            try:
                actual_amount = int(raw_amount)
                if actual_amount < 0:
                    raise ValueError
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="actual_amount must be non-negative integer")
        pm = body.get("payment_method")
        if pm:
            pm = str(pm).strip()
            if pm not in ("cash", "card", "transfer", "other"):
                raise HTTPException(status_code=400, detail="Invalid payment_method")
            payment_method = pm

    if status == new_status:
        if new_status == "done" and (actual_amount is not None or payment_method is not None):
            set_request_payment(request_id, actual_amount, payment_method)
            log_audit(
                org_id=ctx.org_id, user_id=ctx.uid, action="payment_updated",
                entity_type="request", entity_id=request_id,
                payload={"actual_amount": actual_amount, "payment_method": payment_method},
            )
            return {
                "ok": True,
                "status": new_status,
                "note": "already marked, payment updated",
                "actual_amount": actual_amount,
                "payment_method": payment_method,
            }
        return {"ok": True, "status": new_status, "note": "already marked"}

    if not update_request_status(request_id, new_status, admin_id=ctx.uid):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Нельзя отметить заявку #{request_id} как «{new_status}»: "
                f"текущий статус «{status}»."
            ),
        )

    if new_status == "done" and (actual_amount is not None or payment_method is not None):
        set_request_payment(request_id, actual_amount, payment_method)

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid,
        action=f"status_changed_to_{new_status}",
        entity_type="request", entity_id=request_id,
        payload={"from": status, "to": new_status,
                 "actual_amount": actual_amount, "payment_method": payment_method},
    )

    return {
        "ok": True,
        "status": new_status,
        "actual_amount": actual_amount,
        "payment_method": payment_method,
    }


@router.put("/max_booking/api/admin/request/{request_id}/payment")
async def admin_update_payment(request: Request, request_id: int, ctx: AdminCtx = Depends(admin_ctx)):
    req = get_request(request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    r_org_id = req["org_id"]
    if ctx.role != "superadmin" and r_org_id != ctx.org_id:
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        body = await request.json()
        if not isinstance(body, dict):
            body = {}
    except Exception:
        body = {}

    raw_amount = body.get("actual_amount")
    actual_amount = None
    if raw_amount is not None and raw_amount != "":
        try:
            actual_amount = int(raw_amount)
            if actual_amount < 0:
                raise ValueError
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="actual_amount must be non-negative integer")

    pm = body.get("payment_method")
    payment_method = None
    if pm:
        pm = str(pm).strip()
        if pm not in ("cash", "card", "transfer", "other"):
            raise HTTPException(status_code=400, detail="Invalid payment_method")
        payment_method = pm

    if not set_request_payment(request_id, actual_amount, payment_method):
        raise HTTPException(status_code=409, detail="Payment can be edited only for done/no_show requests")

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="payment_updated",
        entity_type="request", entity_id=request_id,
        payload={"actual_amount": actual_amount, "payment_method": payment_method},
    )

    return {"ok": True, "actual_amount": actual_amount, "payment_method": payment_method}


@router.post("/max_booking/api/admin/request/{request_id}/confirm")
async def admin_confirm(request_id: int, ctx: AdminCtx = Depends(admin_ctx)):
    req = get_request(request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    r_org_id = req["org_id"]
    client_uid = req["user_id"]
    service_name = req["service_name"]
    scheduled_at = req["scheduled_at"]
    status = req["status"]
    address = req["address"]
    doctor = req["doctor"]

    if ctx.role != "superadmin" and r_org_id != ctx.org_id:
        raise HTTPException(status_code=403, detail="Access denied")
    if status == "confirmed":
        return {"ok": True, "status": "confirmed", "note": "already confirmed"}

    if not update_request_status(request_id, "confirmed", admin_id=ctx.uid):
        raise HTTPException(status_code=409, detail="Request is not pending (already cancelled?)")
    text = (
        f"✅ **Ваша запись подтверждена!**\n\n"
        f"**{service_name}**\n📅 {scheduled_at}\n"
    )
    if address:
        text += route_lines(address, org_id=r_org_id)
    if doctor:
        text += f"👨‍⚕️ {doctor}\n"
    text += "\nЖдём вас!"
    if not str(client_uid).startswith("phone:"):
        status_ics, err = await send_confirmation_with_ics(
            client_uid, text, request_id, r_org_id, req["service_id"],
            service_name, scheduled_at, address or "", doctor or "",
        )
        if status_ics == "error":
            log.warning("notify failed for #%s: %s", request_id, err)

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="request_confirmed",
        entity_type="request", entity_id=request_id,
        payload={"service": service_name, "scheduled_at": scheduled_at},
    )

    return {"ok": True, "status": "confirmed"}


@router.post("/max_booking/api/admin/request/{request_id}/reject")
async def admin_reject(request_id: int, ctx: AdminCtx = Depends(admin_ctx)):
    req = get_request(request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    r_org_id = req["org_id"]
    client_uid = req["user_id"]
    service_name = req["service_name"]
    scheduled_at = req["scheduled_at"]
    status = req["status"]
    slot_id = req["slot_id"]

    if ctx.role != "superadmin" and r_org_id != ctx.org_id:
        raise HTTPException(status_code=403, detail="Access denied")
    if status == "cancelled":
        return {"ok": True, "status": "cancelled", "note": "already cancelled"}

    was_confirmed = (status == "confirmed")
    if not update_request_status(request_id, "cancelled", admin_id=ctx.uid):
        return {"ok": True, "status": "cancelled", "note": "already cancelled"}
    if slot_id:
        release_slot(slot_id, request_id)

    text = (
        f"❌ **Запись #{request_id} {'отменена администратором' if was_confirmed else 'отклонена'}.**\n\n"
        f"**{service_name}**\n📅 {scheduled_at}\n\n"
        f"Администратор свяжется с вами для уточнения деталей."
    )
    if not str(client_uid).startswith("phone:"):
        try:
            await send_to_client_raw(client_uid, text, fmt="markdown")
        except Exception as e:
            log.warning("notify failed: %s", e)

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid,
        action="request_cancelled_by_admin" if was_confirmed else "request_rejected",
        entity_type="request", entity_id=request_id,
        payload={"service": service_name, "scheduled_at": scheduled_at},
    )

    return {"ok": True, "status": "cancelled", "was_confirmed": was_confirmed}


# ---------- Admin: waitlist ----------

@router.get("/max_booking/api/admin/waitlist")
async def admin_waitlist_list(
    status: str | None = None,
    service_id: str | None = None,
    doctor_id: int | None = None,
    branch_id: int | None = None,
    limit: int = 200,
    offset: int = 0,
    ctx: AdminCtx = Depends(org_ctx),
):
    if limit > 500:
        limit = 500
    rows = list_waitlist(
        ctx.org_id, status=status, service_id=service_id,
        doctor_id=doctor_id, branch_id=branch_id,
        limit=limit, offset=offset,
    )
    return {"entries": [
        {"id": r["id"], "user_id": r["user_id"],
         "service_id": r["service_id"], "service_name": r["service_name"],
         "doctor_id": r["doctor_id"], "doctor_name": r["doctor_name"],
         "branch_id": r["branch_id"], "branch_name": r["branch_name"],
         "date_from": r["date_from"], "date_to": r["date_to"],
         "preferred_time": r["preferred_time"],
         "status": r["status"],
         "notes": r["notes"] or "",
         "created_at": r["created_at"],
         "notified_at": r["notified_at"],
         "notified_count": r["notified_count"] or 0,
         "fulfilled_request_id": r["fulfilled_request_id"],
         "fulfilled_at": r["fulfilled_at"],
         "client_last_name": r["last_name"] or "",
         "client_first_name": r["first_name"] or "",
         "client_middle_name": r["middle_name"] or "",
         "client_phone": r["phone"] or "",
         "has_max": not str(r["user_id"]).startswith("phone:")}
        for r in rows
    ]}


@router.post("/max_booking/api/admin/waitlist")
async def admin_waitlist_create(request: Request, ctx: AdminCtx = Depends(org_ctx)):
    try:
        body = await request.json()
        if not isinstance(body, dict):
            body = {}
    except Exception:
        body = {}

    user_id = str(body.get("user_id") or "").strip()
    phone = str(body.get("phone") or "").strip()
    first_name = str(body.get("first_name") or "").strip()[:100]
    last_name = str(body.get("last_name") or "").strip()[:100]
    middle_name = str(body.get("middle_name") or "").strip()[:100]
    service_id = str(body.get("service_id") or "").strip()
    date_from = str(body.get("date_from") or "").strip()
    date_to = str(body.get("date_to") or "").strip()
    preferred_time = (body.get("preferred_time") or "").strip() or None
    notes = (body.get("notes") or "").strip()[:500]
    doctor_id_raw = body.get("doctor_id")
    branch_id_raw = body.get("branch_id")

    if not date_from or not date_to:
        raise HTTPException(status_code=400, detail="date_from, date_to обязательны")
    if not user_id and not phone:
        raise HTTPException(status_code=400, detail="Нужен user_id или phone")

    svc = None
    if service_id:
        svc = get_service(service_id)
        if not svc or svc["org_id"] != ctx.org_id:
            raise HTTPException(status_code=404, detail="Услуга не найдена")
    else:
        service_id = None

    try:
        from datetime import datetime as _dt
        d_from = _dt.strptime(date_from, "%Y-%m-%d").date()
        d_to = _dt.strptime(date_to, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный формат даты")
    if d_to < d_from:
        raise HTTPException(status_code=400, detail="date_from должен быть ≤ date_to")

    if not user_id:
        phone_norm = normalize_phone(phone)
        if not phone_norm:
            raise HTTPException(status_code=400, detail="Invalid phone")
        user_id = get_or_create_client_by_phone(
            ctx.org_id, first_name, last_name, middle_name, phone_norm,
        )

    doctor_id = None
    if doctor_id_raw not in (None, "", 0):
        try:
            doctor_id = int(doctor_id_raw)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid doctor_id")
        d = get_doctor(doctor_id)
        if not d:
            raise HTTPException(status_code=404, detail="Специалист не найден")

    if not service_id and not doctor_id:
        raise HTTPException(
            status_code=400,
            detail="Укажите услугу и/или специалиста",
        )

    branch_id = None
    if branch_id_raw not in (None, "", 0):
        try:
            branch_id = int(branch_id_raw)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid branch_id")

    if preferred_time not in (None, "morning", "afternoon", "evening", "any"):
        preferred_time = None

    wid = create_waitlist_entry(
        ctx.org_id, user_id, service_id, date_from, date_to,
        doctor_id=doctor_id, branch_id=branch_id,
        preferred_time=preferred_time, notes=notes,
        created_by=ctx.uid,
    )

    try:
        from core.waitlist import _notify_waitlist_entry_for_free_slots
        n = await _notify_waitlist_entry_for_free_slots(wid)
        if n:
            log.info("admin_waitlist_create: %d free slots matched for entry %s", n, wid)
    except Exception as e:
        log.warning("admin_waitlist_create: notify-on-create failed: %s", e)

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="waitlist_created",
        entity_type="waitlist", entity_id=wid,
        payload={"service_id": service_id, "date_from": date_from,
                 "date_to": date_to, "via": "admin"},
    )

    return {"ok": True, "id": wid, "user_id": user_id}


@router.put("/max_booking/api/admin/waitlist/{wid}")
async def admin_waitlist_update(wid: int, request: Request, ctx: AdminCtx = Depends(org_ctx)):
    entry = get_waitlist_entry(wid)
    if not entry:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    if entry["org_id"] != ctx.org_id:
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        body = await request.json()
        if not isinstance(body, dict):
            body = {}
    except Exception:
        body = {}

    fields = {}
    if "service_id" in body:
        raw_sid = body["service_id"]
        if raw_sid in (None, "", 0):
            fields["service_id"] = None
        else:
            sid = str(raw_sid).strip()
            svc = get_service(sid)
            if not svc or svc["org_id"] != ctx.org_id:
                raise HTTPException(status_code=400, detail="Invalid service_id")
            fields["service_id"] = sid
    if "date_from" in body:
        fields["date_from"] = str(body["date_from"]).strip()
    if "date_to" in body:
        fields["date_to"] = str(body["date_to"]).strip()
    if "doctor_id" in body:
        d = body["doctor_id"]
        fields["doctor_id"] = int(d) if d not in (None, "", 0) else None
    if "branch_id" in body:
        b = body["branch_id"]
        fields["branch_id"] = int(b) if b not in (None, "", 0) else None
    if "preferred_time" in body:
        pt = (body["preferred_time"] or "").strip() or None
        if pt not in (None, "morning", "afternoon", "evening", "any"):
            pt = None
        fields["preferred_time"] = pt
    if "notes" in body:
        fields["notes"] = (body["notes"] or "").strip()[:500]

    try:
        from datetime import datetime as _dt
        new_from = fields.get("date_from", entry["date_from"])
        new_to = fields.get("date_to", entry["date_to"])
        _dt.strptime(new_from, "%Y-%m-%d")
        _dt.strptime(new_to, "%Y-%m-%d")
        if new_to < new_from:
            raise HTTPException(status_code=400, detail="date_from должен быть ≤ date_to")
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный формат даты")

    if fields:
        update_waitlist_entry(wid, **fields)

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="waitlist_updated",
        entity_type="waitlist", entity_id=wid,
        payload={"fields": list(fields.keys())},
    )

    return {"ok": True}


@router.delete("/max_booking/api/admin/waitlist/{wid}")
async def admin_waitlist_cancel(wid: int, ctx: AdminCtx = Depends(org_ctx)):
    entry = get_waitlist_entry(wid)
    if not entry:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    if entry["org_id"] != ctx.org_id:
        raise HTTPException(status_code=403, detail="Access denied")
    if entry["status"] != "active":
        return {"ok": True, "note": "already not active"}

    cancel_waitlist_entry(wid)

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="waitlist_cancelled",
        entity_type="waitlist", entity_id=wid, payload={"via": "admin"},
    )

    return {"ok": True}


@router.post("/max_booking/api/admin/waitlist/{wid}/notify")
async def admin_waitlist_notify(wid: int, ctx: AdminCtx = Depends(org_ctx)):
    entry = get_waitlist_entry(wid)
    if not entry:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    if entry["org_id"] != ctx.org_id:
        raise HTTPException(status_code=403, detail="Access denied")

    result, info = await wl_notify_single(wid)
    if result == "sent":
        log_audit(
            org_id=ctx.org_id, user_id=ctx.uid, action="waitlist_notified",
            entity_type="waitlist", entity_id=wid,
            payload={"slot_id": info, "via": "admin"},
        )
        return {"ok": True, "slot_id": info}
    if result == "no_slot":
        raise HTTPException(status_code=409, detail="Нет свободных слотов по этой заявке")
    if result == "blocked":
        raise HTTPException(status_code=409, detail="Клиент заблокировал бота")
    if result == "error":
        raise HTTPException(status_code=400, detail=info or "Не удалось отправить")
    raise HTTPException(status_code=500, detail="Unknown result")


@router.post("/max_booking/api/admin/waitlist/{wid}/fulfill")
async def admin_waitlist_fulfill(
    wid: int, request: Request, ctx: AdminCtx = Depends(org_ctx),
):
    entry = get_waitlist_entry(wid)
    if not entry:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    if entry["org_id"] != ctx.org_id:
        raise HTTPException(status_code=403, detail="Access denied")
    if entry["status"] != "active":
        return {"ok": True, "note": "already not active"}

    try:
        body = await request.json()
        if not isinstance(body, dict):
            body = {}
    except Exception:
        body = {}

    request_id = body.get("request_id")
    if request_id is not None:
        try:
            request_id = int(request_id)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid request_id")
        req = get_request(request_id)
        if not req or req["org_id"] != ctx.org_id:
            raise HTTPException(status_code=400, detail="Request not found")
    else:
        request_id = None

    fulfill_waitlist_entry(wid, request_id)

    log_audit(
        org_id=ctx.org_id, user_id=ctx.uid, action="waitlist_fulfilled",
        entity_type="waitlist", entity_id=wid,
        payload={"request_id": request_id},
    )

    return {"ok": True}