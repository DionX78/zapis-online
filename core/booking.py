"""Унифицированное создание записи.

Одна точка для всех источников: Mini App, админ, лист ожидания, API.
Все проверки и уведомления — здесь. Вызывающий код только:
1. Собирает BookingContext.
2. Зовёт create_booking_unified(ctx).
3. Превращает BookingResult в HTTP-ответ.

Возможности:
- Услуга опциональна (service_id=None) — запись «к специалисту без услуги»
  с предупреждением клиенту.
- slots_count_override — админ может занять больше/меньше слотов, чем
  по длительности услуги.
- confirm_over_daily_limit — админ может записать сверх лимита в день.
- skip_consent_check — для админа (клиент мог дать согласие вне бота).
- via — mini_app | admin | waitlist | api.
"""
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import asyncio

from core.channels.base import UserBlocked
from core.messaging import send_to_client_raw
from core.geo import route_lines
from core.notify import notify_admins
from core.notify_ics import send_confirmation_with_ics
from core.broadcasts import (
    _send_with_refresh, UNSUB_BUTTONS, format_auto_broadcast_text,
)
from storage.db import (
    get_slot, get_service, get_branch, get_doctor,
    get_client, upsert_client, set_consent_152fz,
    is_user_blocked,
    get_org_settings,
    count_active_future_requests, count_active_bookings_on_date,
    has_active_request_at_time,
    slots_needed_for_service, find_consecutive_slots,
    doctor_makes_service,
    get_client_no_show_count,
    create_booking,
    log_audit,
    get_request,
    move_booking, finalize_move_booking,
    count_bookings_for_client_before,
    get_active_auto_broadcast_by_type,
    check_auto_log_after_visit,
    log_auto_broadcast,
)

log = logging.getLogger(__name__)

MAX_ACTIVE_BOOKINGS = 10


@dataclass
class BookingContext:
    org_id: int
    user_id: str
    slot_id: int
    service_id: Optional[str] = None
    phone: str = ""
    first_name: str = ""
    last_name: str = ""
    middle_name: str = ""
    gender: Optional[str] = None
    birth_date: Optional[str] = None
    slots_count_override: Optional[int] = None
    via: str = "api"
    skip_consent_check: bool = False
    confirm_over_daily_limit: bool = False
    set_consent_152fz: bool = False


@dataclass
class BookingResult:
    ok: bool
    request_id: Optional[int] = None
    status: Optional[str] = None
    mode: Optional[str] = None
    notify_status: Optional[str] = None
    error_code: Optional[str] = None
    error_msg: Optional[str] = None
    slots_count: int = 1


def _valid_birth_date(value):
    if not value:
        return None
    try:
        d = datetime.strptime(str(value).strip(), "%Y-%m-%d")
    except ValueError:
        return None
    if d.year < 1900 or d > datetime.now():
        return None
    return d.strftime("%Y-%m-%d")


async def _try_send_welcome_first(ctx: BookingContext, request_id: int):
    """Если это первая запись клиента в org — отправить сценарий welcome_first.

    Никогда не бросает исключений — всё логируется.
    """
    try:
        if str(ctx.user_id).startswith("phone:"):
            return

        prior = count_bookings_for_client_before(ctx.user_id, ctx.org_id, request_id)
        if prior > 0:
            return

        scen = get_active_auto_broadcast_by_type(ctx.org_id, "welcome_first")
        if not scen:
            return

        event_ref = f"welcome:{request_id}"
        if check_auto_log_after_visit(scen["id"], event_ref):
            return

        client = get_client(ctx.user_id)
        if client and client["marketing_opt_out"]:
            log.info("welcome_first skipped for %s: marketing opt-out", ctx.user_id)
            return

        text = format_auto_broadcast_text(
            scen["text"], ctx.user_id, ctx.org_id, request_id=request_id,
        )
        image_id = scen["image_id"]

        try:
            if image_id:
                await _send_with_refresh(
                    ctx.user_id, text, image_id,
                    buttons=UNSUB_BUTTONS, fmt="markdown",
                )
            else:
                await send_to_client_raw(
                    ctx.user_id, text, buttons=UNSUB_BUTTONS, fmt="markdown",
                )
            log_auto_broadcast(scen["id"], ctx.user_id, event_ref=event_ref)
            log.info("welcome_first sent to %s (request #%s)", ctx.user_id, request_id)
        except UserBlocked:
            log_auto_broadcast(scen["id"], ctx.user_id, event_ref=event_ref)
            log.info("welcome_first skipped for %s: user blocked bot", ctx.user_id)
        except Exception as e:
            log.warning("welcome_first send failed for %s: %s", ctx.user_id, e)
    except Exception as e:
        log.warning("welcome_first outer error for #%s: %s", request_id, e)


def validate_booking(ctx: BookingContext):
    """Все проверки. Возвращает (ok, error_code, error_msg, info).

    info — dict с подготовленными данными (slot, svc, slots_needed, slot_ids,
    settings, step_min, effective_service_id, service_name, phone, mode,
    initial_status, human_sched). Используется в create_booking_unified,
    чтобы не перезагружать данные.
    """
    if is_user_blocked(ctx.user_id):
        return False, "blocked", "Аккаунт заблокирован", None

    slot = get_slot(ctx.slot_id)
    if not slot:
        return False, "slot_not_found", "Слот не найден", None
    if slot["org_id"] != ctx.org_id:
        return False, "slot_org_mismatch", "Слот другой организации", None
    if slot["is_booked"]:
        return False, "slot_taken", "Слот уже занят", None

    effective_service_id = ctx.service_id or slot["service_id"]
    svc = None
    if effective_service_id:
        svc = get_service(effective_service_id)
        if not svc or not svc["active"]:
            return False, "service_inactive", "Услуга удалена или скрыта", None
        if svc["org_id"] != ctx.org_id:
            return False, "service_org_mismatch", "Услуга другой организации", None
        if slot["service_id"] and slot["service_id"] != effective_service_id:
            return (
                False,
                "slot_service_mismatch",
                "Слот зарезервирован под другую услугу",
                None,
            )

    client = get_client(ctx.user_id)
    if not ctx.skip_consent_check:
        has_consent = bool(client and client["consent_152fz"]) or ctx.set_consent_152fz
        if not has_consent:
            return (
                False,
                "no_consent",
                "Требуется согласие на обработку персональных данных",
                None,
            )

    if not ctx.phone:
        if client and client["phone"]:
            phone = client["phone"]
        else:
            return False, "no_phone", "Не указан телефон", None
    else:
        phone = ctx.phone

    # Запись в прошлое невозможна ни в одном канале (Mini App, админ,
    # лист ожидания, API). Граница — 30 минут от текущего времени
    # по часовому поясу организации (чтобы не записывать на «сейчас»
    # и «5 минут назад»).
    try:
        slot_dt = datetime.strptime(
            f"{slot['date']} {slot['time']}", "%Y-%m-%d %H:%M"
        )
    except ValueError:
        slot_dt = None
    if slot_dt is not None:
        from storage.db import now_for_org
        now_local = now_for_org(ctx.org_id)
        if slot_dt < now_local:
            return (
                False,
                "slot_in_past",
                "Слот уже в прошлом. Выберите другое время.",
                None,
            )

    settings = get_org_settings(ctx.org_id)
    step_min = int(settings.get("slot_step_min", 30) or 30)

    if ctx.slots_count_override is not None:
        if ctx.slots_count_override < 1 or ctx.slots_count_override > 20:
            return (
                False,
                "invalid_slots_count",
                "Количество слотов должно быть от 1 до 20",
                None,
            )
        slots_needed = ctx.slots_count_override
    elif effective_service_id:
        slots_needed = slots_needed_for_service(effective_service_id, step_min)
    else:
        slots_needed = 1

    slot_ids = find_consecutive_slots(ctx.slot_id, slots_needed, step_min)
    if not slot_ids:
        return (
            False,
            "no_slots_for_duration",
            f"Недостаточно свободного времени подряд (нужно {slots_needed} слотов)",
            None,
        )

    human_sched = f"{slot['date']} {slot['time']}"

    if has_active_request_at_time(ctx.user_id, ctx.org_id, human_sched, phone=phone):
        return (
            False,
            "already_at_time",
            "У вас уже есть активная запись на это время",
            None,
        )

    max_per_day = int(settings.get("max_bookings_per_day", 2) or 0)
    if max_per_day > 0 and not ctx.confirm_over_daily_limit:
        day_count = count_active_bookings_on_date(ctx.user_id, ctx.org_id, slot["date"])
        if day_count >= max_per_day:
            return (
                False,
                "daily_limit_exceeded",
                (
                    f"Не более {max_per_day} активных записей на один день. "
                    f"Отмените существующую запись, чтобы создать новую."
                ),
                None,
            )

    if count_active_future_requests(ctx.user_id, ctx.org_id) >= MAX_ACTIVE_BOOKINGS:
        return False, "too_many_active", "Слишком много активных записей", None

    if effective_service_id and slot["doctor_id"]:
        if not doctor_makes_service(slot["doctor_id"], effective_service_id):
            return False, "doctor_skill", "Специалист не оказывает эту услугу", None

    mode = settings.get("confirmation_mode", "manual")
    initial_status = "confirmed" if mode == "auto" else "pending"

    no_show_threshold = int(settings.get("auto_manual_no_show_threshold", 0) or 0)
    if no_show_threshold > 0 and initial_status == "confirmed":
        if get_client_no_show_count(ctx.user_id) >= no_show_threshold:
            initial_status = "pending"
            mode = "manual"

    service_name = svc["name"] if svc else "Приём (услуга не указана)"

    info = {
        "slot": slot,
        "svc": svc,
        "slots_needed": slots_needed,
        "slot_ids": slot_ids,
        "settings": settings,
        "step_min": step_min,
        "effective_service_id": effective_service_id,
        "service_name": service_name,
        "phone": phone,
        "mode": mode,
        "initial_status": initial_status,
        "human_sched": human_sched,
    }
    return True, None, None, info


async def create_booking_unified(ctx: BookingContext) -> BookingResult:
    ok, err_code, err_msg, info = validate_booking(ctx)
    if not ok:
        return BookingResult(ok=False, error_code=err_code, error_msg=err_msg)

    slot = info["slot"]
    svc = info["svc"]
    effective_service_id = info["effective_service_id"]
    service_name = info["service_name"]
    slot_ids = info["slot_ids"]
    human_sched = info["human_sched"]
    phone = info["phone"]
    mode = info["mode"]
    initial_status = info["initial_status"]
    slots_needed = info["slots_needed"]
    step_min = info["step_min"]

    if ctx.via == "mini_app":
        birth_date = _valid_birth_date(ctx.birth_date)
        upsert_client(
            ctx.user_id,
            org_id=ctx.org_id,
            first_name=ctx.first_name or None,
            last_name=ctx.last_name or None,
            middle_name=ctx.middle_name or None,
            phone=phone,
            gender=ctx.gender if ctx.gender in ("male", "female") else None,
            birth_date=birth_date,
        )
        if ctx.set_consent_152fz:
            set_consent_152fz(ctx.user_id, True)

    addr = ""
    if slot["branch_id"]:
        br = get_branch(slot["branch_id"])
        if br:
            addr = br["address"] or ""
    doc = ""
    if slot["doctor_id"]:
        d = get_doctor(slot["doctor_id"])
        if d:
            doc = d["name"] or ""

    rid = create_booking(
        ctx.org_id, ctx.user_id, service_name, human_sched, phone, addr, doc,
        slot["branch_id"], slot["doctor_id"], slot_ids, initial_status,
        effective_service_id,
    )
    if rid is None:
        return BookingResult(
            ok=False,
            error_code="slot_taken",
            error_msg="Слот уже занят",
        )

    fio_parts = [ctx.last_name, ctx.first_name, ctx.middle_name]
    fio = " ".join(p for p in fio_parts if p).strip() or "—"

    notify_status = "no_max"
    if not str(ctx.user_id).startswith("phone:"):
        if initial_status == "confirmed":
            client_text = (
                f"✅ **Ваша запись подтверждена!**\n\n"
                f"**{service_name}**\n"
                f"📅 {human_sched}\n"
            )
            if addr:
                client_text += route_lines(addr, org_id=ctx.org_id)
            if doc:
                client_text += f"👤 {doc}\n"
            if svc and svc["prep"]:
                client_text += f"\n_{svc['prep']}_\n"
            if svc:
                client_text += "\nЖдём вас!"
            else:
                client_text += (
                    f"\n\n⚠️ Услуга не указана — записали вас на стандартные "
                    f"{slots_needed * step_min} минут. Пожалуйста, свяжитесь "
                    f"с администратором для уточнения услуги и длительности."
                )

            if svc:
                try:
                    status_ics, _ = await send_confirmation_with_ics(
                        ctx.user_id, client_text, rid, ctx.org_id,
                        effective_service_id, service_name, human_sched,
                        addr, doc, svc["prep"] or "",
                    )
                    notify_status = status_ics
                except Exception as e:
                    log.warning("create_booking: ics failed for #%s: %s", rid, e)
                    notify_status = "error"
            else:
                try:
                    await send_to_client_raw(ctx.user_id, client_text, fmt="markdown")
                    notify_status = "sent"
                except UserBlocked:
                    notify_status = "blocked"
                except Exception as e:
                    log.warning("create_booking: notify failed for #%s: %s", rid, e)
                    notify_status = "error"
        elif mode == "client":
            client_text = (
                f"✅ Заявка #{rid} принята!\n\n"
                f"**{service_name}**\n"
                f"📅 {human_sched}\n"
            )
            if addr:
                client_text += f"📍 {addr}\n"
            if doc:
                client_text += f"👤 {doc}\n"
            if not svc:
                client_text += (
                    f"\n⚠️ Услуга не указана — записали на стандартные "
                    f"{slots_needed * step_min} мин. Свяжитесь с администратором."
                )
            client_text += "\nДля подтверждения записи позже пришлём вам запрос, ожидайте."
            try:
                await send_to_client_raw(ctx.user_id, client_text, fmt="markdown")
                notify_status = "sent"
            except UserBlocked:
                notify_status = "blocked"
            except Exception as e:
                log.warning("create_booking: notify failed for #%s: %s", rid, e)
                notify_status = "error"
        else:
            client_text = (
                f"✅ Заявка #{rid} принята!\n\n"
                f"**{service_name}**\n"
                f"📅 {human_sched}\n"
            )
            if addr:
                client_text += f"📍 {addr}\n"
            if doc:
                client_text += f"👤 {doc}\n"
            if svc and svc["prep"]:
                client_text += f"\n_{svc['prep']}_\n"
            if not svc:
                client_text += (
                    f"\n⚠️ Услуга не указана — записали на стандартные "
                    f"{slots_needed * step_min} мин. Свяжитесь с администратором."
                )
            client_text += "\nСтатус: ожидает подтверждения администратором."
            try:
                await send_to_client_raw(ctx.user_id, client_text, fmt="markdown")
                notify_status = "sent"
            except UserBlocked:
                notify_status = "blocked"
            except Exception as e:
                log.warning("create_booking: notify failed for #%s: %s", rid, e)
                notify_status = "error"

    # welcome_first — fire-and-forget, не блокирует основной поток
    try:
        asyncio.create_task(_try_send_welcome_first(ctx, rid))
    except Exception as e:
        log.warning("welcome_first task schedule failed for #%s: %s", rid, e)

    no_service_note = (
        (
            f"\n\n⚠️ _Услуга не указана — уточните у клиента и при необходимости "
            f"скорректируйте длительность (сейчас {slots_needed * step_min} мин)._"
        )
        if not svc else ""
    )

    via_labels = {
        "mini_app": "Mini App",
        "admin": "администратором",
        "waitlist": "из листа ожидания",
        "api": "API",
    }
    via_label = via_labels.get(ctx.via, ctx.via)

    if mode == "manual":
        admin_text = (
            f"🆕 **Новая заявка #{rid}** ({via_label}, ожидает подтверждения)\n\n"
            f"**{service_name}**\n📅 {human_sched}\n"
            f"Клиент: {fio}\nТелефон: {phone}\n"
        )
        if addr:
            admin_text += f"📍 {addr}\n"
        if doc:
            admin_text += f"👤 {doc}\n"
        admin_text += no_service_note
        admin_buttons = [[
            {"type": "callback", "text": "✅ Подтвердить", "payload": f"req:confirm:{rid}"},
            {"type": "callback", "text": "❌ Отклонить", "payload": f"req:reject:{rid}"},
        ]]
        await notify_admins(admin_text, org_id=ctx.org_id, buttons=admin_buttons)
    elif mode == "client":
        admin_text = (
            f"🆕 **Новая заявка #{rid}** ({via_label}, клиент подтверждает сам)\n\n"
            f"**{service_name}**\n📅 {human_sched}\n"
            f"Клиент: {fio}\nТелефон: {phone}\n"
        )
        admin_text += no_service_note
        await notify_admins(admin_text, org_id=ctx.org_id, buttons=None)
    else:
        admin_text = (
            f"🆕 **Новая заявка #{rid}** ({via_label}, авто-подтверждена)\n\n"
            f"**{service_name}**\n📅 {human_sched}\n"
            f"Клиент: {fio}\nТелефон: {phone}\n"
        )
        admin_text += no_service_note
        await notify_admins(admin_text, org_id=ctx.org_id, buttons=None)

    log_audit(
        org_id=ctx.org_id, user_id=ctx.user_id, action="booking_created",
        entity_type="request", entity_id=rid,
        payload={
            "service": service_name,
            "scheduled_at": human_sched,
            "via": ctx.via,
            "slots_count": len(slot_ids),
        },
    )

    return BookingResult(
        ok=True,
        request_id=rid,
        status=initial_status,
        mode=mode,
        notify_status=notify_status,
        slots_count=len(slot_ids),
    )


@dataclass
class MoveResult:
    ok: bool
    request_id: Optional[int] = None
    scheduled_at: Optional[str] = None
    notify_status: Optional[str] = None
    error_code: Optional[str] = None
    error_msg: Optional[str] = None


async def move_booking_unified(request_id: int, new_slot_id: int, via: str = "admin") -> MoveResult:
    """Атомарный перенос активной записи на новый слот.

    Проверки:
    - запись существует и активна (pending/confirmed);
    - новый слот существует, свободен, в той же org;
    - новый слот не в прошлом;
    - у клиента нет другой активной записи на новое время;
    - под длительность услуги хватает подряд идущих слотов;
    - специалист оказывает услугу (если применимо).

    После переноса клиенту уходит уведомление «Запись перенесена».
    """
    req = get_request(request_id)
    if not req:
        return MoveResult(ok=False, error_code="request_not_found",
                          error_msg="Заявка не найдена")
    if req["status"] not in ("pending", "confirmed"):
        return MoveResult(ok=False, error_code="request_not_active",
                          error_msg="Можно перенести только активную запись")

    new_slot = get_slot(new_slot_id)
    if not new_slot:
        return MoveResult(ok=False, error_code="slot_not_found",
                          error_msg="Слот не найден")
    if new_slot["org_id"] != req["org_id"]:
        return MoveResult(ok=False, error_code="slot_org_mismatch",
                          error_msg="Слот принадлежит другой организации")
    if new_slot["is_booked"]:
        return MoveResult(ok=False, error_code="slot_taken",
                          error_msg="Слот уже занят")

    try:
        slot_dt = datetime.strptime(
            f"{new_slot['date']} {new_slot['time']}", "%Y-%m-%d %H:%M"
        )
    except ValueError:
        slot_dt = None
    if slot_dt is not None:
        from storage.db import now_for_org
        if slot_dt < now_for_org(req["org_id"]):
            return MoveResult(ok=False, error_code="slot_in_past",
                              error_msg="Слот уже в прошлом")

    human_sched = f"{new_slot['date']} {new_slot['time']}"
    user_id = req["user_id"]

    if has_active_request_at_time(user_id, req["org_id"], human_sched, phone=req["phone"]):
        return MoveResult(ok=False, error_code="already_at_time",
                          error_msg="У клиента уже есть другая активная запись на это время")

    settings = get_org_settings(req["org_id"])
    step_min = int(settings.get("slot_step_min", 30) or 30)

    # При переносе сохраняем текущее количество слотов записи — длительность
    # приёма не меняется. Для записей без услуги (service_id=NULL) это
    # критично: slots_needed_for_service(None)=1, а запись могла занимать N
    # слотов (override админа).
    current_slots_count = int(req["slots_count"] or 0)
    if current_slots_count > 0:
        slots_needed = current_slots_count
    else:
        slots_needed = slots_needed_for_service(req["service_id"], step_min)

    slot_ids_list = find_consecutive_slots(new_slot_id, slots_needed, step_min)
    if not slot_ids_list:
        return MoveResult(ok=False, error_code="no_slots_for_duration",
                          error_msg="Недостаточно свободного времени подряд для этой услуги")

    doctor_id = new_slot["doctor_id"]
    if doctor_id and req["service_id"] and not doctor_makes_service(doctor_id, req["service_id"]):
        return MoveResult(ok=False, error_code="doctor_skill",
                          error_msg="Специалист не оказывает эту услугу")

    ok, err, _payload = move_booking(request_id, new_slot_id)
    if not ok:
        return MoveResult(ok=False, error_code="move_failed",
                          error_msg=err or "Не удалось перенести")

    branch_id = new_slot["branch_id"]
    addr = ""
    if branch_id:
        br = get_branch(branch_id)
        if br:
            addr = br["address"] or ""
    doc_name = ""
    if doctor_id:
        d = get_doctor(doctor_id)
        if d:
            doc_name = d["name"] or ""

    finalize_move_booking(
        request_id, slot_ids_list, human_sched,
        branch_id, doctor_id, addr, doc_name,
    )

    notify_status = "no_max"
    if user_id and not str(user_id).startswith("phone:"):
        notify_text = (
            f"🔄 **Запись перенесена**\n\n"
            f"**{req['service_name']}**\n"
            f"Было: {req['scheduled_at']}\n"
            f"Стало: {human_sched}\n"
        )
        if addr:
            notify_text += route_lines(addr, org_id=req["org_id"])
        if doc_name:
            notify_text += f"👤 {doc_name}\n"
        notify_text += "\n📅 Добавьте новое время в календарь — файл ниже."

        prep = ""
        if req["service_id"]:
            svc_obj = get_service(req["service_id"])
            if svc_obj and svc_obj["prep"]:
                prep = svc_obj["prep"]

        notify_status, _err = await send_confirmation_with_ics(
            user_id, notify_text, request_id, req["org_id"], req["service_id"],
            req["service_name"], human_sched, addr, doc_name, prep,
        )

    log.info(
        "move_booking_unified: #%s %s -> %s (via=%s, notify=%s)",
        request_id, req["scheduled_at"], human_sched, via, notify_status,
    )

    return MoveResult(
        ok=True,
        request_id=request_id,
        scheduled_at=human_sched,
        notify_status=notify_status,
    )