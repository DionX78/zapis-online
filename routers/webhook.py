"""Webhook-эндпоинт и регистрация webhook/команд бота в MAX."""
import hmac
import logging

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

import config
from core import max_client as mx
from core.dispatcher import route
from core.webhook_adapters.max import parse as parse_max_update

log = logging.getLogger(__name__)

router = APIRouter()


async def ensure_webhook_subscribed():
    if not config.MAX_BOT_TOKEN:
        log.warning("MAX_BOT_TOKEN не задан")
        return
    url = config.WEBHOOK_BASE_URL + config.WEBHOOK_PATH
    headers = {"Authorization": config.MAX_BOT_TOKEN}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(config.MAX_API + "/subscriptions", headers=headers)
            subs = []
            if r.status_code == 200:
                data = r.json()
                subs = data.get("subscriptions", []) if isinstance(data, dict) else data
            urls = [s.get("url") for s in subs if isinstance(s, dict)]
            if url in urls:
                log.info("Webhook уже зарегистрирован: %s", url)
                return
            body = {
                "url": url,
                "update_types": ["message_created", "message_callback", "bot_started"],
            }
            if config.WEBHOOK_SECRET:
                body["secret"] = config.WEBHOOK_SECRET
            r2 = await client.post(
                config.MAX_API + "/subscriptions",
                headers={**headers, "Content-Type": "application/json"},
                json=body,
            )
            log.info("Регистрация webhook: %s %s", r2.status_code, r2.text[:300])
    except Exception as e:
        log.error("Ошибка регистрации webhook: %s", e)


async def register_bot_commands():
    if not config.MAX_BOT_TOKEN:
        return
    try:
        await mx.set_commands([
            {"name": "start", "description": "Начать запись"},
            {"name": "myid",  "description": "Показать мой ID"},
            {"name": "iam",   "description": "Подать заявку на роль администратора"},
            {"name": "today", "description": "Записи на сегодня (для админа)"},
            {"name": "help",  "description": "Справка"},
        ])
        log.info("Команды бота зарегистрированы")
    except Exception as e:
        log.error("Ошибка регистрации команд: %s", e)


async def startup():
    """Вызывается из lifespan приложения после init_db()."""
    if not config.WEBHOOK_SECRET:
        log.error(
            "⚠ WEBHOOK_SECRET не задан — вебхук НЕ ЗАЩИЩЁН! "
            "Любой может слать поддельные апдейты. Установите секрет в .env."
        )
    log.info("DB_PATH = %s", config.DB_PATH)
    await ensure_webhook_subscribed()
    await register_bot_commands()


@router.post(config.WEBHOOK_PATH)
async def webhook(request: Request):
    if config.WEBHOOK_SECRET:
        got = request.headers.get("X-Max-Bot-Api-Secret", "")
        if not hmac.compare_digest(got, config.WEBHOOK_SECRET):
            log.warning("Webhook 403: secret mismatch (got len=%s, expected len=%s)",
                        len(got or ""), len(config.WEBHOOK_SECRET or ""))
            return JSONResponse({"ok": False}, status_code=403)
    try:
        data = await request.json()
    except Exception:
        log.warning("Webhook: invalid JSON")
        return JSONResponse({"ok": False}, status_code=400)
    log.info("Webhook IN: type=%s", data.get("type") or data.get("update_type"))
    try:
        update = parse_max_update(data)
        if update:
            await route(update)
    except Exception:
        log.exception("route failed")
    return {"ok": True}