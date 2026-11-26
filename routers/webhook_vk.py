"""Вебхук VK Callback API: /max_booking/api/webhook/vk/{slug}.

Один эндпоинт на всех VK-ботов: slug определяет организацию, из bots
берутся token, group_id, confirmation_code и webhook_secret.
Секрет вебхука — свой у каждого бота (глобальный config.WEBHOOK_SECRET
один на приложение и здесь не используется).
"""
import json
import logging
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, PlainTextResponse

import storage.db as db
from core import dispatcher
from core import channels as _channels  # noqa: F401  (регистрирует каналы)
from core.channels import vk as vk_channel
from core.webhook_adapters import vk as vk_adapter

log = logging.getLogger(__name__)

router = APIRouter()

VK_WEBHOOK_PREFIX = "/max_booking/api/webhook/vk"


def _internal_user_id(vk_uid: str, org_id=None) -> str:
    """Внутренний user_id клиента по VK-id. Заводит «паспорт» при первом контакте.

    Новый клиент создаётся сразу с org_id бота: организация определяется
    по slug вебхука → строке в bots (каждый бот принадлежит одной организации).
    """
    vk_uid = str(vk_uid).removeprefix("vk:")
    try:
        row = db.get_identity_by_platform_uid("vk", vk_uid)
    except Exception as e:
        log.warning("VK identity lookup failed: %s", e)
        row = None
    if row:
        return str(row["user_id"])
    internal = f"vk:{vk_uid}"
    try:
        db.upsert_client(internal, org_id=org_id)
        return str(db.link_client_identity(internal, "vk", vk_uid, is_primary=1))
    except Exception as e:
        log.warning("VK identity link failed: %s", e)
        return internal


_VK_SEX = {1: "female", 2: "male"}


async def _autofill_vk_profile(vk_uid: str, bot) -> None:
    """Заполняет пустые поля профиля VK-клиента данными users.get.

    Запрос к VK идёт только пока имя/фамилия пусты — после первого
    успешного заполнения функция становится no-op (экономим лимиты API).
    Телефон VK API не отдаёт — он появится только из чата клиента или склейки.
    """
    internal = f"vk:{vk_uid}"
    try:
        client = db.get_client(internal)
        if not client:
            return
        if (client["first_name"] or "") and (client["last_name"] or ""):
            return
        token = bot["token"] if bot else None
        if not token:
            return
        users = await vk_channel.api_call(
            "users.get",
            {"user_ids": str(vk_uid), "fields": "sex,bdate"},
            token=token,
        )
        item = (users or [None])[0]
        if not isinstance(item, dict) or item.get("deactivated"):
            return
        updates = {}
        if not (client["first_name"] or "") and item.get("first_name"):
            updates["first_name"] = str(item["first_name"])
        if not (client["last_name"] or "") and item.get("last_name"):
            updates["last_name"] = str(item["last_name"])
        if not (client["gender"] or "") and item.get("sex") in _VK_SEX:
            updates["gender"] = _VK_SEX[item["sex"]]
        if not (client["birth_date"] or "") and item.get("bdate"):
            try:
                d = datetime.strptime(str(item["bdate"]), "%d.%m.%Y")
                updates["birth_date"] = d.strftime("%Y-%m-%d")
            except ValueError:
                pass  # VK отдал дату без года — не сохраняем
        if updates:
            db.upsert_client(internal, **updates)
            log.info("VK профиль %s дополнен: %s", internal, ", ".join(updates))
    except Exception as e:
        log.warning("VK autofill failed for %s: %s", vk_uid, e)


@router.post(VK_WEBHOOK_PREFIX + "/{slug}")
async def vk_webhook(slug: str, request: Request):
    bot = db.get_bot_by_slug(slug)
    if not bot or str(bot["platform"]) != "vk":
        log.warning("VK webhook: неизвестный бот '%s'", slug)
        return JSONResponse({"error": "unknown bot"}, status_code=404)

    raw_body = await request.body()
    try:
        data = json.loads(raw_body or b"{}")
    except Exception:
        return JSONResponse({"error": "bad json"}, status_code=400)
    if not isinstance(data, dict):
        return JSONResponse({"error": "bad payload"}, status_code=400)

    etype = str(data.get("type") or "")

    # Подтверждение адреса: ВК ждёт ровно строку кода, без кавычек и JSON.
    if etype == "confirmation":
        code = str(bot["confirmation_code"] or "")
        if not code:
            log.error("VK бот '%s': confirmation_code не задан в bots", slug)
            return PlainTextResponse("", status_code=500)
        return PlainTextResponse(code)

    secret = str(bot["webhook_secret"] or "")
    if secret and str(data.get("secret") or "") != secret:
        log.warning("VK webhook '%s': неверный secret", slug)
        return JSONResponse({"error": "forbidden"}, status_code=403)

    if not bot["enabled"]:
        log.debug("VK webhook '%s': бот выключен, событие '%s' пропущено", slug, etype)
        return PlainTextResponse("ok")

    org_id = bot["org_id"]

    update = vk_adapter.parse_event(data)
    if update is None:
        return PlainTextResponse("ok")

    # VK-id → внутренний user_id клиента (паспорт канала, org бота).
    update.user_id = _internal_user_id(update.user_id, org_id=org_id)

    # Автозаполнение пустых полей профиля из VK (ФИО, пол, ДР).
    try:
        await _autofill_vk_profile(str(update.user_id).removeprefix("vk:"), bot)
    except Exception as e:
        log.warning("VK autofill skipped: %s", e)
    try:
        update.bot_id = int(bot["id"])
    except (TypeError, ValueError):
        pass

    if update.type == "message_callback":
        # Гасим «крутилку» до обработки: ВК отвалится по таймауту иначе.
        await vk_channel.answer_event(data)

    try:
        await dispatcher.route(update)
    except Exception as e:
        log.exception("VK update failed (slug=%s, type=%s): %s", slug, etype, e)

    return PlainTextResponse("ok")


@router.get(VK_WEBHOOK_PREFIX + "/{slug}")
async def vk_webhook_ping(slug: str):
    """Проверка адреса из браузера: бот есть — 'ok'."""
    bot = db.get_bot_by_slug(slug)
    if not bot or str(bot["platform"]) != "vk":
        return PlainTextResponse("unknown bot", status_code=404)
    return PlainTextResponse("ok")
