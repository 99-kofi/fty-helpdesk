"""Webhook Gateway: validate → queue → 200 OK. Heavy work happens async (spec §4)."""
import logging
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Query
from app.api.websocket import broadcast
from app.core.config import settings
from app.webhooks.verify import verify_meta_signature
from app.workers.queues import enqueue, redis_reachable

log = logging.getLogger("fty.webhooks")
webhook_router = APIRouter(tags=["webhooks"])


def _verify_hub(v_token: str, challenge: str):
    if settings.meta_verify_token == "change-me" or v_token != settings.meta_verify_token:
        raise HTTPException(403, "Invalid verify token")
    return int(challenge) if challenge.isdigit() else challenge


def _make_verifier(channel: str):
    async def _verify(
        hub_mode: str = Query(alias="hub.mode", default=""),
        hub_challenge: str = Query(alias="hub.challenge", default=""),
        hub_verify_token: str = Query(alias="hub.verify_token", default=""),
    ):
        return _verify_hub(hub_verify_token, hub_challenge)

    _verify.__name__ = f"verify_{channel}"
    return _verify


for _ch in ("instagram", "whatsapp", "facebook"):
    webhook_router.get(f"/{_ch}")(_make_verifier(_ch))


async def _ingest(channel: str, request: Request, background: BackgroundTasks, signed: bool = True):
    raw = await request.body()
    if signed:
        ok = verify_meta_signature(raw, request.headers.get("X-Hub-Signature-256"))
        if not ok:
            if settings.meta_app_secret != "change-me":
                raise HTTPException(403, "Invalid webhook signature")
            log.warning("accepting unsigned %s webhook (dev mode: set META_APP_SECRET)", channel)
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    enqueue("message", {"channel": channel, "payload": payload})
    if not redis_reachable():
        # No external worker in local dev — process inline so the inbox still updates.
        background.add_task(_process_inline, channel, payload)
    return {"received": True}


async def _process_inline(channel: str, payload: dict) -> None:
    from app.workers.tasks import handle_message_event
    try:
        stored = handle_message_event(channel, payload)
        if stored:
            await broadcast({"type": "message", "channel": channel, "sender": "customer"})
    except Exception:
        log.exception("inline webhook processing failed")


@webhook_router.post("/instagram")
async def ig_hook(request: Request, background: BackgroundTasks):
    return await _ingest("instagram", request, background)


@webhook_router.post("/whatsapp")
async def wa_hook(request: Request, background: BackgroundTasks):
    return await _ingest("whatsapp", request, background)


@webhook_router.post("/facebook")
async def fb_hook(request: Request, background: BackgroundTasks):
    return await _ingest("facebook", request, background)


@webhook_router.post("/email")
async def email_hook(request: Request, background: BackgroundTasks):
    """Generic inbound-email endpoint — point SendGrid/Mailgun inbound parse here."""
    return await _ingest("email", request, background, signed=False)
