"""FTY HelpDesk API — modular monolith entrypoint."""
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.webhooks.router import webhook_router
from app.api.websocket import ws_router
from app.core.config import settings
from app.core.database import Base, engine
from app import models  # noqa: F401 — register tables

log = logging.getLogger("fty.sla")

Base.metadata.create_all(bind=engine)


def ensure_schema() -> None:
    """Backfill columns on pre-existing databases (no Alembic history yet)."""
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    if "users" not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns("users")}
    stmts = []
    if "availability" not in existing:
        stmts.append("ALTER TABLE users ADD COLUMN availability VARCHAR(20) DEFAULT 'available'")
    if "max_active" not in existing:
        stmts.append("ALTER TABLE users ADD COLUMN max_active INTEGER DEFAULT 10")
    if stmts:
        with engine.begin() as conn:
            for s in stmts:
                conn.execute(text(s))


ensure_schema()


def bootstrap_production_admin() -> None:
    """Create the first administrator from deployment secrets, never from a route."""
    if not (settings.bootstrap_admin_email and settings.bootstrap_admin_password):
        return
    from sqlalchemy.exc import IntegrityError
    from app.core.database import SessionLocal
    from app.core.security import hash_password
    from app.models.user import User

    db = SessionLocal()
    try:
        if db.query(User.id).first():
            return
        db.add(User(
            name=settings.bootstrap_admin_name,
            email=settings.bootstrap_admin_email,
            password_hash=hash_password(settings.bootstrap_admin_password),
            role="admin",
        ))
        db.commit()
        log.info("Created the initial administrator from deployment configuration")
    except IntegrityError:
        # Concurrent cold starts can race; the unique email constraint makes the
        # losing request harmless.
        db.rollback()
    finally:
        db.close()


bootstrap_production_admin()

_scheduler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """In-process SLA watchdog (dev/small deploys). Prod with replicas: disable
    and hit POST /api/v1/automation/sla-check from one external cron instead."""
    global _scheduler
    if os.getenv("VERCEL"):
        # Function instances are short-lived and may scale horizontally. Run SLA
        # checks from one external scheduler instead of starting one per instance.
        yield
        return
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from app.core.database import SessionLocal
        from app.services.sla import run_sla_check

        def _job():
            db = SessionLocal()
            try:
                run_sla_check(db)
            except Exception:
                log.exception("sla job failed")
            finally:
                db.close()

        _scheduler = AsyncIOScheduler()
        _scheduler.add_job(_job, "interval", minutes=settings.sla_check_minutes,
                           id="sla-watch", replace_existing=True)
        _scheduler.start()
        log.info("sla watchdog every %sm", settings.sla_check_minutes)
    except ImportError:
        log.warning("apscheduler not installed — SLA watchdog disabled")
    yield
    if _scheduler:
        _scheduler.shutdown()


app = FastAPI(title="FTY HelpDesk API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")
app.include_router(webhook_router, prefix="/webhooks")
# Vercel: top-level routes must also be reachable under /api (function at /api)
app.include_router(webhook_router, prefix="/api/webhooks")
app.include_router(ws_router)
app.include_router(ws_router, prefix="/api")


@app.get("/health")
@app.get("/api/health")
def health():
    return {"status": "ok", "service": "fty-helpdesk"}
