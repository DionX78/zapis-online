"""Аутентификация и авторизация для Mini App и админки.
Зависимости FastAPI + хелперы проверки принадлежности организации."""
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from urllib.parse import parse_qsl

from fastapi import Depends, HTTPException, Request

import config
from storage.db import (
    get_admin_role,
    get_branch,
    get_doctor,
    get_service,
    is_superadmin_db,
)


@dataclass
class AdminCtx:
    uid: int
    role: str
    org_id: Optional[int]
    platform: str = "max"  # платформа (max/vk)


# ==================== Парсинг WebAppData ====================

def validate_webapp_data(init_data: str, max_age_seconds: int = 86400):
    if not init_data or not config.MAX_BOT_TOKEN:
        return None
    try:
        params = dict(parse_qsl(init_data, keep_blank_values=True))
    except Exception:
        return None
    if "hash" not in params:
        return None
    received_hash = params.pop("hash")

    auth_date_str = params.get("auth_date")
    if auth_date_str:
        try:
            auth_date = int(auth_date_str)
            now = int(datetime.now().timestamp())
            if now - auth_date > max_age_seconds:
                return None
        except ValueError:
            return None

    items = sorted(params.items())
    launch_params = "\n".join(f"{k}={v}" for k, v in items)
    secret_key = hmac.new(b"WebAppData", config.MAX_BOT_TOKEN.encode(), hashlib.sha256).digest()
    calc_hash = hmac.new(secret_key, launch_params.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc_hash, received_hash):
        return None

    if "user" in params:
        try:
            params["user"] = json.loads(params["user"])
        except Exception:
            pass
    return params


def get_user_from_request(request: Request):
    init_data = request.headers.get("X-Max-Init-Data", "")
    return validate_webapp_data(init_data)


def get_uid_from_user(user):
    user_info = user.get("user") or {}
    if isinstance(user_info, str):
        try:
            user_info = json.loads(user_info)
        except Exception:
            user_info = {}
    return user_info.get("id") or user_info.get("user_id") or 0


# ==================== Зависимости FastAPI ====================

async def require_user(request: Request) -> dict:
    user = get_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid initData")
    return user


async def admin_ctx(request: Request) -> AdminCtx:
    # Тестовый режим: test_uid в query-параметре (только для локального тестирования)
    test_uid = request.query_params.get("test_uid")
    if test_uid and test_uid.isdigit():
        test_uid = int(test_uid)
        platform = "max"
        if is_superadmin_db(platform, test_uid):
            q_org = request.query_params.get("org_id")
            if q_org and q_org.isdigit():
                return AdminCtx(uid=test_uid, role="superadmin", org_id=int(q_org), platform=platform)
            return AdminCtx(uid=test_uid, role="superadmin", org_id=None, platform=platform)
        conn_row = get_admin_role(test_uid)
        role, org_id_from_db, _name = conn_row
        if role is None:
            raise HTTPException(status_code=403, detail="Not an admin")
        return AdminCtx(uid=test_uid, role=role, org_id=org_id_from_db, platform=platform)
    
    # Обычный режим: проверка WebAppData
    user = get_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid initData")
    uid = get_uid_from_user(user)
    if not uid:
        raise HTTPException(status_code=401, detail="Invalid user")

    # Платформа всегда MAX для WebAppData
    platform = "max"
    
    # Проверить суперадмина через новую схему БД
    if is_superadmin_db(platform, uid):
        q_org = request.query_params.get("org_id")
        if q_org and q_org.isdigit():
            return AdminCtx(uid=uid, role="superadmin", org_id=int(q_org), platform=platform)
        return AdminCtx(uid=uid, role="superadmin", org_id=None, platform=platform)
    
    # Иначе проверить обычного админа
    conn_row = get_admin_role(uid)
    role, org_id_from_db, _name = conn_row
    if role is None:
        raise HTTPException(status_code=403, detail="Not an admin")

    return AdminCtx(uid=uid, role=role, org_id=org_id_from_db, platform=platform)


async def superadmin_ctx(ctx: AdminCtx = Depends(admin_ctx)) -> AdminCtx:
    if ctx.role != "superadmin":
        raise HTTPException(status_code=403, detail="Only superadmin")
    return ctx


async def org_ctx(ctx: AdminCtx = Depends(admin_ctx)) -> AdminCtx:
    if not ctx.org_id:
        raise HTTPException(status_code=400, detail="org_id is required")
    return ctx


# ==================== Проверки принадлежности ====================

def require_branch(ctx: AdminCtx, branch_id: int):
    br = get_branch(branch_id)
    if not br:
        raise HTTPException(status_code=404, detail="Branch not found")
    if ctx.role != "superadmin" and br["org_id"] != ctx.org_id:
        raise HTTPException(status_code=403, detail="Access denied")
    return br


def require_doctor(ctx: AdminCtx, doctor_id: int):
    d = get_doctor(doctor_id)
    if not d:
        raise HTTPException(status_code=404, detail="Doctor not found")
    br = get_branch(d["branch_id"])
    if ctx.role != "superadmin" and (not br or br["org_id"] != ctx.org_id):
        raise HTTPException(status_code=403, detail="Access denied")
    return d


def require_service(ctx: AdminCtx, service_id: str):
    svc = get_service(service_id)
    if not svc:
        raise HTTPException(status_code=404, detail="Service not found")
    if ctx.role != "superadmin" and svc["org_id"] != ctx.org_id:
        raise HTTPException(status_code=403, detail="Access denied")
    return svc