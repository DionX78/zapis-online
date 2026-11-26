import truststore
truststore.inject_into_ssl()

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

import config  # noqa: F401
from routers import (
    webhook as webhook_router,
    webhook_vk as webhook_vk_router,
    mini_app as mini_app_router,
    admin_core as admin_core_router,
    admin_requests as admin_requests_router,
    admin_directories as admin_directories_router,
    admin_broadcasts as admin_broadcasts_router,
    admin_settings as admin_settings_router,
    admin_uploads as admin_uploads_router,
    admin_reviews as admin_reviews_router,
    admin_bots as admin_bots_router,
)
from storage.db import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    await webhook_router.startup()

    from core.reminders import run_reminder_worker, run_supervised
    from core.broadcasts import run_broadcast_worker
    from core.waitlist import run_waitlist_worker

    worker_tasks = [
        asyncio.create_task(run_supervised("reminder", run_reminder_worker)),
        asyncio.create_task(run_supervised("broadcast", run_broadcast_worker)),
        asyncio.create_task(run_supervised("waitlist", run_waitlist_worker)),
    ]
    log.info("Workers started (reminder, broadcast, waitlist) via supervisor")

    yield

    for t in worker_tasks:
        t.cancel()
    for t in worker_tasks:
        try:
            await t
        except asyncio.CancelledError:
            pass


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(webhook_router.router)
app.include_router(webhook_vk_router.router)
app.include_router(mini_app_router.router)
app.include_router(admin_core_router.router)
app.include_router(admin_requests_router.router)
app.include_router(admin_directories_router.router)
app.include_router(admin_broadcasts_router.router)
app.include_router(admin_settings_router.router)
app.include_router(admin_uploads_router.router)
app.include_router(admin_reviews_router.router)
app.include_router(admin_bots_router.router)
