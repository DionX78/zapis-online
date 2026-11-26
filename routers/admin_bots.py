"""API управления ботами организации.
Эндпоинты для добавления, редактирования, удаления ботов (MAX, VK и т.д.).
"""
import secrets
from typing import Optional

import logging

import httpx
import config

from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException

from core.auth import AdminCtx, admin_ctx, org_ctx
from storage.db import (
    delete_bot,
    get_bot,
    list_bots,
    set_bot_enabled,
    upsert_bot,
)

router = APIRouter(prefix="/max_booking/api/admin/bots", tags=["bots"])


# ==================== GET эндпоинты ====================

@router.get("")
async def list_org_bots(
    ctx: AdminCtx = Depends(org_ctx),
):
    """Список всех ботов организации."""
    if not ctx.org_id:
        raise HTTPException(status_code=400, detail="org_id required")
    
    bots = list_bots(org_id=ctx.org_id)
    return {
        "ok": True,
        "bots": [
            {
                "id": b["id"],
                "platform": b["platform"],
                "slug": b["slug"],
                "title": b["title"] or f"{b['platform'].upper()} Bot",
                "enabled": bool(b["enabled"]),
                "group_id": b["group_id"],
                "token": b["token"],  # полный токен для редактирования
                "confirmation_code": b["confirmation_code"],
                "created_at": b["created_at"],
                "updated_at": b["updated_at"],
            }
            for b in bots
        ],
    }


@router.get("/{bot_id}")
async def get_org_bot(bot_id: int, ctx: AdminCtx = Depends(org_ctx)):
    """Получить детали бота."""
    bot = get_bot(bot_id)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    
    # Проверить, принадлежит ли бот организации
    if ctx.role != "superadmin" and bot["org_id"] != ctx.org_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return {
        "ok": True,
        "bot": {
            "id": bot["id"],
            "platform": bot["platform"],
            "slug": bot["slug"],
            "title": bot["title"],
            "enabled": bool(bot["enabled"]),
            "group_id": bot["group_id"],
            "confirmation_code": bot["confirmation_code"],
            "token": "***" if bot["token"] else None,
            "webhook_secret": "***" if bot["webhook_secret"] else None,
            "created_at": bot["created_at"],
            "updated_at": bot["updated_at"],
        },
    }


# ==================== POST эндпоинты ====================

@router.post("/vk/init")
async def init_vk_bot(
    group_id: int,
    ctx: AdminCtx = Depends(org_ctx),
):
    """Инициализировать новый VK-бота.
    
    Возвращает:
    - slug: автогенерированный
    - confirmation_code: для вставки в ВК
    - инструкцию
    """
    if not ctx.org_id:
        raise HTTPException(status_code=400, detail="org_id required")
    
    # Генерировать slug и confirmation_code
    slug = f"vk_{group_id}_{secrets.token_hex(4)}"
    confirmation_code = secrets.token_hex(4)  # 8 символов
    
    # Создать бота в БД (disabled)
    bot_id = upsert_bot(
        org_id=ctx.org_id,
        platform="vk",
        slug=slug,
        group_id=group_id,
        confirmation_code=confirmation_code,
        enabled=0,  # включим после подтверждения токена
        title=f"VK Community {group_id}",
    )
    
    return {
        "ok": True,
        "bot_id": bot_id,
        "slug": slug,
        "confirmation_code": confirmation_code,
        "instructions": (
            f"1. Перейди в https://vk.com/club{group_id}/settings?act=callback\n"
            f"2. В поле 'Строка подтверждения' вставь: {confirmation_code}\n"
            f"3. Нажми 'Сохранить' и дождись подтверждения\n"
            f"4. Создай ключ доступа с правами: messages, manage\n"
            f"5. Отправь нам токен для активации"
        ),
    }


@router.post("/{bot_id}/token")
async def set_bot_token(
    bot_id: int,
    token: str,
    ctx: AdminCtx = Depends(org_ctx),
):
    """Обновить токен бота и включить его.
    
    Минимальная проверка: убедиться, что токен не пуст.
    Полная проверка (запрос в API) — на фронте или в отдельном эндпоинте.
    """
    if not ctx.org_id:
        raise HTTPException(status_code=400, detail="org_id required")
    
    bot = get_bot(bot_id)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    
    # Проверить доступ
    if ctx.role != "superadmin" and bot["org_id"] != ctx.org_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if not token or len(token) < 10:
        raise HTTPException(status_code=400, detail="Invalid token")
    
    # Обновить токен и включить бота
    upsert_bot(
        org_id=bot["org_id"],
        platform=bot["platform"],
        slug=bot["slug"],
        token=token,
        enabled=1,
    )
    
    return {
        "ok": True,
        "message": "Bot activated with new token",
        "bot_id": bot_id,
    }


# ==================== PATCH эндпоинты ====================

@router.patch("/{bot_id}")
async def update_bot(
    bot_id: int,
    enabled: Optional[bool] = None,
    title: Optional[str] = None,
    token: Optional[str] = None,
    group_id: Optional[str] = None,
    confirmation_code: Optional[str] = None,
    ctx: AdminCtx = Depends(org_ctx),
):
    """Обновить настройки бота (включить/выключить, изменить название, токен, confirmation_code)."""
    if not ctx.org_id:
        raise HTTPException(status_code=400, detail="org_id required")
    
    bot = get_bot(bot_id)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    
    # Проверить доступ
    if ctx.role != "superadmin" and bot["org_id"] != ctx.org_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if enabled is not None:
        set_bot_enabled(bot_id, enabled)
    
    # Собрать параметры для upsert
    update_kwargs = {
        "org_id": bot["org_id"],
        "platform": bot["platform"],
        "slug": bot["slug"],
    }
    
    if title is not None:
        update_kwargs["title"] = title
    if token is not None:
        update_kwargs["token"] = token
    if group_id is not None:
        update_kwargs["group_id"] = group_id
    if confirmation_code is not None:
        update_kwargs["confirmation_code"] = confirmation_code
    
    # Обновить, если есть что-то кроме базовых полей
    if len(update_kwargs) > 3:  # больше чем org_id, platform, slug
        upsert_bot(**update_kwargs)
    
    return {
        "ok": True,
        "message": "Bot updated",
        "bot_id": bot_id,
    }


# ==================== DELETE эндпоинты ====================

@router.delete("/{bot_id}")
async def remove_bot(bot_id: int, ctx: AdminCtx = Depends(org_ctx)):
    """Удалить бота."""
    if not ctx.org_id:
        raise HTTPException(status_code=400, detail="org_id required")
    
    bot = get_bot(bot_id)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    
    # Проверить доступ
    if ctx.role != "superadmin" and bot["org_id"] != ctx.org_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    delete_bot(bot_id)
    
    return {
        "ok": True,
        "message": "Bot deleted",
        "bot_id": bot_id,
    }


# ==================== UI API для админки ====================

@router.get("/ui/list")
async def ui_list_bots(ctx: AdminCtx = Depends(org_ctx)):
    """Получить список ботов для админки (UI)."""
    if not ctx.org_id:
        raise HTTPException(status_code=400, detail="org_id required")
    
    bots = list_bots(org_id=ctx.org_id)
    return {
        "bots": [
            {
                "id": b["id"],
                "platform": b["platform"],
                "slug": b["slug"],
                "title": b["title"] or f"{b['platform'].upper()} Bot",
                "enabled": bool(b["enabled"]),
                "group_id": b["group_id"],
                "token": b["token"],
                "confirmation_code": b["confirmation_code"],
                "webhook_secret": b["webhook_secret"],
                "org_id": b["org_id"],
                "created_at": b["created_at"],
            }
            for b in bots
        ]
    }


class CheckTokenBody(BaseModel):
    platform: str
    token: str
    group_id: Optional[str] = None


class CheckTokenBody(BaseModel):
    platform: str
    token: str
    group_id: Optional[str] = None


VK_API_BASE = "https://api.vk.com/method/"


async def vk_api(token, group_id, method, params=None):
    """Вызов VK API от имени конкретного бота (токен из bots)."""
    p = dict(params or {})
    p["access_token"] = token
    p["v"] = "5.199"
    if group_id:
        p["group_id"] = group_id
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(VK_API_BASE + method, data=p)
    data = r.json()
    if isinstance(data, dict) and data.get("error"):
        err = data["error"]
        logging.getLogger(__name__).error(
            "VK API %s failed: code=%s msg=%s params=%s",
            method,
            err.get("error_code"),
            err.get("error_msg"),
            {k: v for k, v in p.items() if k != "access_token"},
        )
        raise HTTPException(
            status_code=400,
            detail=f"VK API {err.get('error_code')}: {err.get('error_msg')}",
        )
    return data


@router.post("/ui/check_token")
async def ui_check_bot_token(
    body: CheckTokenBody,
    ctx: AdminCtx = Depends(org_ctx),
):
    """Проверить токен бота через API платформы."""
    if not ctx.org_id:
        raise HTTPException(status_code=400, detail="org_id required")

    if not body.token or len(body.token) < 10:
        raise HTTPException(status_code=400, detail="Invalid token format")

    async with httpx.AsyncClient(timeout=20) as client:
        if body.platform == "vk":
            if not body.group_id:
                raise HTTPException(status_code=400, detail="group_id required for VK")
            r = await client.get(VK_API_BASE + "groups.getById", params={
                "group_id": body.group_id,
                "fields": "name",
                "access_token": body.token,
                "v": "5.199",
            })
            data = r.json()
            if isinstance(data, dict) and data.get("error"):
                err = data["error"]
                raise HTTPException(
                    status_code=400,
                    detail=f"VK API {err.get('error_code')}: {err.get('error_msg')}",
                )
            resp = data.get("response") or {}
            groups = resp.get("groups") if isinstance(resp, dict) else resp
            if not groups:
                raise HTTPException(
                    status_code=400,
                    detail="VK: токен не привязан к сообществу",
                )
            g = groups[0]
            try:
                gid = int(str(body.group_id).lstrip("-"))
            except ValueError:
                gid = None
            if gid is not None and int(g.get("id") or 0) != gid:
                raise HTTPException(
                    status_code=400,
                    detail=(f"VK: токен относится к сообществу id={g.get('id')}, "
                            f"а не {body.group_id}"),
                )
            bot_name = g.get("name") or f"VK Community {body.group_id}"
        elif body.platform == "max":
            r = await client.get(
                "https://platform-api2.max.ru/me",
                params={"access_token": body.token},
            )
            data = r.json()
            if not data.get("is_bot"):
                raise HTTPException(
                    status_code=400,
                    detail="MAX: токен недействителен (is_bot=false)",
                )
            bot_name = data.get("name") or "MAX Bot"
        else:
            raise HTTPException(status_code=400, detail="Unknown platform")

    return {
        "message": f"Token valid for {body.platform}",
        "bot_name": bot_name,
    }


class AddBotBody(BaseModel):
    platform: str
    token: str
    title: Optional[str] = None
    group_id: Optional[str] = None


@router.post("/ui/add")
async def ui_add_bot(
    body: AddBotBody,
    ctx: AdminCtx = Depends(org_ctx),
):
    """Добавить новый бот (для админки)."""
    if not ctx.org_id:
        raise HTTPException(status_code=400, detail="org_id required")

    if not body.token or len(body.token) < 10:
        raise HTTPException(status_code=400, detail="Invalid token")

    webhook_secret = None
    if body.platform == "vk":
        if not body.group_id:
            raise HTTPException(status_code=400, detail="group_id required for VK")
        slug = f"vk_{body.group_id}_{secrets.token_hex(4)}"
        webhook_secret = secrets.token_hex(16)
    elif body.platform == "max":
        slug = f"max_{secrets.token_hex(8)}"
    else:
        raise HTTPException(status_code=400, detail="Unknown platform")

    bot_id = upsert_bot(
        org_id=ctx.org_id,
        platform=body.platform,
        slug=slug,
        token=body.token,
        webhook_secret=webhook_secret,
        title=body.title or f"{body.platform.upper()} Bot",
        group_id=body.group_id if body.platform == "vk" else None,
        enabled=1,
    )

    return {
        "bot_id": bot_id,
        "webhook_secret": webhook_secret,
        "message": "Bot added successfully",
    }


class UpdateBotBody(BaseModel):
    enabled: Optional[bool] = None
    title: Optional[str] = None
    token: Optional[str] = None
    group_id: Optional[str] = None
    confirmation_code: Optional[str] = None


@router.patch("/ui/{bot_id}")
async def ui_update_bot(
    bot_id: int,
    body: UpdateBotBody,
    ctx: AdminCtx = Depends(org_ctx),
):
    """Обновить бот (для админки)."""
    if not ctx.org_id:
        raise HTTPException(status_code=400, detail="org_id required")

    bot = get_bot(bot_id)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    if ctx.role != "superadmin" and bot["org_id"] != ctx.org_id:
        raise HTTPException(status_code=403, detail="Access denied")

    if body.enabled is not None:
        set_bot_enabled(bot_id, body.enabled)

    update_kwargs = {
        "org_id": bot["org_id"],
        "platform": bot["platform"],
        "slug": bot["slug"],
    }

    if body.title is not None:
        update_kwargs["title"] = body.title
    if body.token:
        update_kwargs["token"] = body.token
    if body.group_id:
        update_kwargs["group_id"] = body.group_id
    if body.confirmation_code is not None:
        update_kwargs["confirmation_code"] = body.confirmation_code

    if len(update_kwargs) > 3:
        upsert_bot(**update_kwargs)

    return {"message": "Bot updated"}


@router.post("/ui/{bot_id}/register_callback")
async def ui_register_callback(bot_id: int, ctx: AdminCtx = Depends(org_ctx)):
    """Зарегистрировать Callback-адрес бота в VK (setCallbackServer + события)."""
    if not ctx.org_id:
        raise HTTPException(status_code=400, detail="org_id required")

    bot = get_bot(bot_id)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    if ctx.role != "superadmin" and bot["org_id"] != ctx.org_id:
        raise HTTPException(status_code=403, detail="Access denied")

    if bot["platform"] == "max":
        return {
            "ok": True,
            "message": "MAX-вебхук регистрируется автоматически при старте сервиса",
        }
    if bot["platform"] != "vk":
        raise HTTPException(status_code=400, detail="Unsupported platform")

    token = bot["token"]
    group_id = bot["group_id"]
    if not token or not group_id:
        raise HTTPException(
            status_code=400,
            detail="Заполните токен и ID сообщества и сохраните их",
        )

    webhook_secret = bot["webhook_secret"]
    if not webhook_secret:
        webhook_secret = secrets.token_hex(16)
        upsert_bot(
            org_id=bot["org_id"],
            platform=bot["platform"],
            slug=bot["slug"],
            webhook_secret=webhook_secret,
            group_id=group_id,
        )

    vk_url = (config.WEBHOOK_BASE_URL + config.WEBHOOK_PATH).replace(
        "/api/webhooks", "/api/webhook/vk/" + bot["slug"]
    )

    servers = await vk_api(token, str(group_id), "groups.getCallbackServers")
    items = ((servers.get("response") or {}).get("items")) or []
    server_id = next((s["id"] for s in items if s.get("url") == vk_url), None)
    if server_id is None:
        created = await vk_api(token, str(group_id), "groups.setCallbackServer", {
            "url": vk_url,
            "title": "Booking Bot",
            "secret_key": webhook_secret,
        })
        server_id = created.get("response")
    else:
        # Сервер уже существует (адрес регистрировали вручную) — перезаписываем
        # его секрет, иначе VK продолжает слать старый секрет и вебхук отвечает 403.
        await vk_api(token, str(group_id), "groups.editCallbackServer", {
            "server_id": server_id,
            "url": vk_url,
            "title": "Booking Bot",
            "secret_key": webhook_secret,
        })

    await vk_api(token, str(group_id), "groups.setCallbackSettings", {
        "server_id": server_id,
        "api_version": "5.199",
        "message_new": 1,
        "message_reply": 1,
        "message_edit": 1,
        "message_allow": 1,
        "message_deny": 1,
        "message_event": 1,
        "wall_post_new": 0,
        "photo_new": 0,
        "video_new": 0,
        "audio_new": 0,
    })

    return {
        "ok": True,
        "message": "Callback зарегистрирован, события включены",
        "url": vk_url,
        "webhook_secret": webhook_secret,
    }


@router.delete("/ui/{bot_id}")
async def ui_delete_bot(bot_id: int, ctx: AdminCtx = Depends(org_ctx)):
    """Удалить бот (для админки)."""
    if not ctx.org_id:
        raise HTTPException(status_code=400, detail="org_id required")
    
    bot = get_bot(bot_id)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    
    if ctx.role != "superadmin" and bot["org_id"] != ctx.org_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    delete_bot(bot_id)
    
    return {"message": "Bot deleted"}
