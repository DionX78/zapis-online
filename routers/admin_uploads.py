"""Админские ручки: uploads (загрузка картинок, отдача файлов) + публичная отдача."""
import logging
import uuid as _uuid
from pathlib import Path as _Path

import httpx
from fastapi import APIRouter, Request, HTTPException, Depends, UploadFile, File
from fastapi.responses import FileResponse

import config
from core.auth import AdminCtx, admin_ctx, org_ctx
from core.uploads import _process_upload_image
from storage.db import (
    save_uploaded_image_full,
    get_uploaded_image_by_id,
    get_uploaded_image_by_public_token,
    log_audit,
)

log = logging.getLogger(__name__)

router = APIRouter()


# ---------- Admin: uploads ----------

@router.post("/max_booking/api/admin/upload")
async def admin_upload(
    file: UploadFile = File(...),
    ctx: AdminCtx = Depends(org_ctx),
):
    import uuid as _uuid
    from pathlib import Path as _Path

    if not config.MAX_BOT_TOKEN:
        raise HTTPException(status_code=500, detail="Bot token not configured")

    if not file.content_type or file.content_type not in config.ALLOWED_UPLOAD_MIME:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file.content_type}. "
                   f"Allowed: {', '.join(config.ALLOWED_UPLOAD_MIME)}",
        )

    raw_content = await file.read()
    if len(raw_content) > config.MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large: {len(raw_content)} bytes (max {config.MAX_UPLOAD_SIZE})",
        )
    if not raw_content:
        raise HTTPException(status_code=400, detail="Empty file")

    content, mime_type, ext = _process_upload_image(raw_content, file.content_type)

    filename = f"{_uuid.uuid4().hex}.{ext}"
    rel_dir = str(ctx.org_id)
    abs_dir = _Path(config.UPLOADS_DIR) / rel_dir
    abs_dir.mkdir(parents=True, exist_ok=True)
    abs_path = abs_dir / filename
    abs_path.write_bytes(content)
    rel_path = f"{rel_dir}/{filename}"

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                config.MAX_API + "/uploads",
                params={"type": "image"},
                headers={"Authorization": config.MAX_BOT_TOKEN},
            )
            if r.status_code != 200:
                raise Exception(f"MAX /uploads вернул {r.status_code}: {r.text}")
            data = r.json()
            if "url" not in data:
                raise Exception(f"Неожиданный ответ от MAX (нет url): {data}")
            upload_url = data["url"]

            files = {"data": (filename, content, mime_type)}
            r2 = await client.post(upload_url, files=files)
            if r2.status_code not in (200, 201):
                raise Exception(f"Загрузка в S3 вернула {r2.status_code}: {r2.text}")
            data2 = r2.json()
            photos = data2.get("photos", {})
            photo_key = next(iter(photos), None) if photos else None
            if not photo_key:
                raise Exception(f"В ответе нет объекта photos: {data2}")
            token = photos[photo_key].get("token")
            if not token:
                raise Exception(f"В ответе нет token: {data2}")

            uid, public_token = save_uploaded_image_full(
                token=token,
                file_path=rel_path,
                mime_type=mime_type,
                original_filename=file.filename or filename,
                file_size=len(content),
                org_id=ctx.org_id,
                uploaded_by=ctx.uid,
            )

            log_audit(
                org_id=ctx.org_id, user_id=ctx.uid, action="image_uploaded",
                entity_type="image", entity_id=str(uid),
                payload={"size": len(content), "mime": mime_type},
            )

            return {
                "upload_id": uid,
                "preview_url": f"/max_booking/api/upload/{public_token}",
            }

    except HTTPException:
        # Если MAX отверг — удаляем сохранённый файл, чтобы не мусорить
        try:
            abs_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise
    except Exception as e:
        try:
            abs_path.unlink(missing_ok=True)
        except Exception:
            pass
        log.error("Ошибка при загрузке картинки: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/max_booking/api/admin/upload/{upload_id}/file")
async def admin_upload_file(upload_id: int, request: Request, ctx: AdminCtx = Depends(admin_ctx)):
    from fastapi.responses import FileResponse
    from pathlib import Path as _Path

    img = get_uploaded_image_by_id(upload_id)
    if not img or (ctx.role != "superadmin" and img["org_id"] != ctx.org_id):
        raise HTTPException(status_code=404, detail="Not found")
    if not img["file_path"]:
        raise HTTPException(status_code=404, detail="File not stored")
    abs_path = _Path(config.UPLOADS_DIR) / img["file_path"]
    if not abs_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")
    return FileResponse(abs_path, media_type=img["mime_type"] or "image/jpeg")


@router.get("/max_booking/api/upload/{public_token}")
async def public_upload_file(public_token: str):
    """Публичная отдача картинки для <img src="...">.
    Без auth: токен неподбираемый (uuid4 hex), файлы и так идут в чаты клиентов.
    """
    from fastapi.responses import FileResponse
    from pathlib import Path as _Path

    if not public_token or len(public_token) < 8:
        raise HTTPException(status_code=404, detail="Not found")

    img = get_uploaded_image_by_public_token(public_token)
    if not img:
        raise HTTPException(status_code=404, detail="Not found")
    if not img["file_path"]:
        raise HTTPException(status_code=404, detail="File not stored")
    abs_path = _Path(config.UPLOADS_DIR) / img["file_path"]
    if not abs_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")
    return FileResponse(
        abs_path,
        media_type=img["mime_type"] or "image/jpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )

    