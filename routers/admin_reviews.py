"""Админские ручки: отзывы (список, карточка клиента)."""
import logging

from fastapi import APIRouter, HTTPException, Depends

from core.auth import AdminCtx, org_ctx
from storage.db import (
    list_reviews, count_reviews, get_client_review_stats, get_client,
    get_doctor, log_audit,
)

log = logging.getLogger(__name__)

router = APIRouter()


@router.get("/max_booking/api/admin/reviews")
async def admin_reviews_list(
    filter: str | None = None,
    doctor_id: int | None = None,
    rating: int | None = None,
    limit: int = 200,
    offset: int = 0,
    ctx: AdminCtx = Depends(org_ctx),
):
    if limit > 500:
        limit = 500
    if filter not in (None, "positive", "negative", "all"):
        raise HTTPException(status_code=400, detail="filter must be positive, negative or empty")
    if rating is not None and (rating < 1 or rating > 5):
        raise HTTPException(status_code=400, detail="rating must be 1..5")
    if doctor_id is not None:
        doc = get_doctor(doctor_id)
        if not doc:
            raise HTTPException(status_code=400, detail="Invalid doctor_id")

    rows = list_reviews(
        ctx.org_id,
        rating_filter=filter if filter != "all" else None,
        doctor_id=doctor_id,
        rating=rating,
        limit=limit,
        offset=offset,
    )

    # Список специалистов, у которых хотя бы один отзыв — для фильтра
    from storage.db import db as _db, db_ctx as _db_ctx
    with _db_ctx() as conn:
        doc_rows = conn.execute(
            "SELECT DISTINCT r.doctor_id, d.name AS doctor_name "
            "FROM reviews r "
            "LEFT JOIN doctors d ON d.id = r.doctor_id "
            "WHERE r.org_id=? AND r.doctor_id IS NOT NULL "
            "ORDER BY d.name",
            (ctx.org_id,),
        ).fetchall()

    return {
        "total": count_reviews(ctx.org_id),
        "doctors": [
            {"id": r["doctor_id"], "name": r["doctor_name"] or "—"}
            for r in doc_rows
        ],
        "reviews": [
            {"id": r["id"], "user_id": r["user_id"], "request_id": r["request_id"],
             "rating": r["rating"], "comment": r["comment"] or "",
             "created_at": r["created_at"],
             "client_last_name": r["last_name"] or "",
             "client_first_name": r["first_name"] or "",
             "client_middle_name": r["middle_name"] or "",
             "client_phone": r["phone"] or "",
             "service_name": r["service_name"] or "",
             "scheduled_at": r["scheduled_at"] or "",
             "doctor": r["doctor"] or "",
             "doctor_id": r["doctor_id"]}
            for r in rows
        ],
    }


@router.get("/max_booking/api/admin/client/{user_id}/reviews")
async def admin_client_reviews(user_id: str, ctx: AdminCtx = Depends(org_ctx)):
    client = get_client(user_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    if ctx.role != "superadmin" and client["org_id"] not in (None, ctx.org_id):
        raise HTTPException(status_code=403, detail="Access denied")

    return get_client_review_stats(user_id, ctx.org_id)