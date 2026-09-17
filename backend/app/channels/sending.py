"""Outbound delivery (Phase 2): agent reply → channel API.

Best-effort by design: returns the provider message id on success,
None when unconfigured or failed. Never raises — the reply is always
stored locally first, delivery is a bonus.
"""
import asyncio
import logging
import smtplib
from email.message import EmailMessage

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.vault import open_secret
from app.models.channel import ChannelConnection
from app.models.conversation import Conversation
from app.models.customer import CustomerIdentity

log = logging.getLogger("fty.outbound")


def _is_real(value: str | None) -> bool:
    return bool(value and value != "change-me")


def channel_token(db: Session | None, channel: str, fallback: str = "") -> str:
    if db is not None:
        row = db.query(ChannelConnection).filter_by(channel=channel).first()
        if row and _is_real(open_secret(row.access_token)):
            return open_secret(row.access_token) or ""
    return fallback if _is_real(fallback) else ""


def recipient(db: Session, conv: Conversation) -> str | None:
    ident = (
        db.query(CustomerIdentity)
        .filter_by(customer_id=conv.customer_id, channel=conv.channel)
        .order_by(CustomerIdentity.id.desc())
        .first()
    )
    return ident.external_user_id if ident else None


async def _send_meta(to_id: str, text: str, token: str) -> str | None:
    url = f"https://graph.facebook.com/{settings.meta_api_version}/me/messages"
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(url, params={"access_token": token}, json={
            "recipient": {"id": to_id},
            "messaging_type": "RESPONSE",
            "message": {"text": text},
        })
    if r.status_code >= 400:
        log.warning("meta send failed: %s %s", r.status_code, r.text[:300])
        return None
    return r.json().get("message_id")


async def _send_whatsapp(to: str, text: str, token: str) -> str | None:
    if not settings.whatsapp_phone_number_id:
        return None
    url = f"https://graph.facebook.com/{settings.meta_api_version}/{settings.whatsapp_phone_number_id}/messages"
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(url, headers={"Authorization": f"Bearer {token}"}, json={
            "messaging_product": "whatsapp", "to": to,
            "type": "text", "text": {"body": text},
        })
    if r.status_code >= 400:
        log.warning("whatsapp send failed: %s %s", r.status_code, r.text[:300])
        return None
    msgs = r.json().get("messages") or []
    return msgs[0].get("id") if msgs else "sent"


def _send_smtp_sync(to_addr: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body)
    if settings.smtp_use_tls:
        smtp: smtplib.SMTP = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15)
        smtp.starttls()
    else:
        smtp = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15)
    try:
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)
    finally:
        smtp.quit()


async def deliver(db: Session, conv: Conversation, text: str) -> str | None:
    """Route an agent reply to the customer's channel. Returns provider id or None."""
    to = recipient(db, conv)
    if not to:
        return None
    try:
        if conv.channel in ("instagram", "facebook"):
            token = channel_token(db, conv.channel, settings.meta_page_token)
            if not token:
                return None
            return await _send_meta(to, text, token)
        if conv.channel == "whatsapp":
            token = channel_token(db, "whatsapp", settings.whatsapp_token)
            if not token:
                return None
            return await _send_whatsapp(to, text, token)
        if conv.channel == "email":
            if not settings.smtp_host:
                return None
            await asyncio.to_thread(_send_smtp_sync, to, "Re: your FTY support request", text)
            return "smtp-sent"
        if conv.channel == "web":
            return "web:stored"  # widget polls; no push needed
    except Exception:
        log.exception("outbound delivery failed (%s)", conv.channel)
    return None
