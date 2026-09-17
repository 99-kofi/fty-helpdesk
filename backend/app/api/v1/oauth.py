"""Meta OAuth connect (Phase 2): FTY Admin → Meta Login → backend → encrypted storage.

Covers Instagram (via its linked Facebook Page) and Facebook Messenger.
WhatsApp Cloud API and Email keep manual token setup in Settings.
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from jose import jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.core.vault import seal
from app.models.channel import ChannelConnection
from app.models.user import User

log = logging.getLogger("fty.oauth")
router = APIRouter(prefix="/channels", tags=["channel-oauth"])

SCOPES = {
    "instagram": "instagram_basic,instagram_manage_messages,pages_messaging,pages_show_list,pages_read_engagement",
    "facebook": "pages_messaging,pages_show_list,pages_read_engagement",
}


def _redirect_uri(channel: str) -> str:
    return f"{settings.meta_oauth_redirect_base}/api/v1/channels/{channel}/oauth/callback"


def _require_app() -> None:
    if not settings.meta_app_id:
        raise HTTPException(400, "META_APP_ID is not configured on the backend")


def _issue_state(channel: str, user_id: int) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=10)
    return jwt.encode(
        {"ch": channel, "u": str(user_id), "exp": exp},
        settings.jwt_secret, algorithm=settings.jwt_algorithm,
    )


def _read_state(state: str, channel: str) -> str:
    try:
        payload = jwt.decode(state, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except Exception:
        raise HTTPException(400, "Invalid OAuth state")
    if payload.get("ch") != channel:
        raise HTTPException(400, "OAuth state mismatch")
    return str(payload.get("u", ""))


async def exchange_code_for_token(code: str, redirect_uri: str) -> str:
    """Code → short-lived user token."""
    url = f"https://graph.facebook.com/{settings.meta_api_version}/oauth/access_token"
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(url, params={
            "client_id": settings.meta_app_id,
            "client_secret": settings.meta_app_secret,
            "redirect_uri": redirect_uri,
            "code": code,
        })
    data = r.json()
    if r.status_code >= 400 or "access_token" not in data:
        raise RuntimeError(f"token exchange failed: {str(data)[:200]}")
    return data["access_token"]


async def to_long_lived_token(short_token: str) -> str:
    url = f"https://graph.facebook.com/{settings.meta_api_version}/oauth/access_token"
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(url, params={
            "grant_type": "fb_exchange_token",
            "client_id": settings.meta_app_id,
            "client_secret": settings.meta_app_secret,
            "fb_exchange_token": short_token,
        })
    data = r.json()
    if r.status_code >= 400 or "access_token" not in data:
        raise RuntimeError(f"long-lived exchange failed: {str(data)[:200]}")
    return data["access_token"]


async def fetch_managed_pages(long_token: str) -> list[dict]:
    """Pages the admin granted, with linked Instagram business accounts."""
    url = f"https://graph.facebook.com/{settings.meta_api_version}/me/accounts"
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(url, params={
            "fields": "id,name,access_token,instagram_business_account{id,username}",
            "access_token": long_token,
        })
    data = r.json()
    if r.status_code >= 400:
        raise RuntimeError(f"page lookup failed: {str(data)[:200]}")
    return data.get("data", [])


def _pick_credential(channel: str, pages: list[dict]) -> tuple[str, dict]:
    if not pages:
        log.error("oauth: Meta returned zero pages (wrong login account? dev-mode roles? declined permissions?)")
        raise RuntimeError("NO_PAGES_AT_ALL")
    if channel == "instagram":
        for p in pages:
            ig = p.get("instagram_business_account") or {}
            if ig.get("id") and p.get("access_token"):
                return p["access_token"], {
                    "page_id": p["id"], "page_name": p.get("name"),
                    "ig_id": ig["id"], "ig_username": ig.get("username"),
                }
        log.error("oauth pages without linked IG: %s",
                  [{"page": p.get("id"), "name": p.get("name"),
                    "ig_field": bool(p.get("instagram_business_account"))} for p in pages])
        raise RuntimeError("No Facebook Page with a linked Instagram business account found")
    if not pages or not pages[0].get("access_token"):
        raise RuntimeError("No Facebook Pages returned for this login")
    return pages[0]["access_token"], {"page_id": pages[0]["id"], "page_name": pages[0].get("name")}


def _store(channel: str, page_token: str, config: dict) -> None:
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        row = db.query(ChannelConnection).filter_by(channel=channel).first()
        if not row:
            row = ChannelConnection(channel=channel)
            db.add(row)
        row.access_token = seal(page_token)
        row.config = json.dumps(config)
        db.commit()
    finally:
        db.close()


def _done(channel: str, error: str | None = None) -> RedirectResponse:
    base = f"{settings.frontend_url}/settings"
    qs = urlencode({"oauth_error": error} if error else {"connected": channel})
    return RedirectResponse(f"{base}?{qs}")


@router.get("/{channel}/oauth/start", dependencies=[Depends(require_role("admin"))])
def oauth_start(channel: str, user: User = Depends(get_current_user)):
    """Step 1–2: build the Meta Login URL the admin clicks through."""
    if channel not in SCOPES:
        raise HTTPException(400, "OAuth is available for instagram and facebook")
    _require_app()
    dialog = f"https://www.facebook.com/{settings.meta_api_version}/dialog/oauth?" + urlencode({
        "client_id": settings.meta_app_id,
        "redirect_uri": _redirect_uri(channel),
        "state": _issue_state(channel, user.id),
        "scope": SCOPES[channel],
        "response_type": "code",
    })
    return {"url": dialog}


@router.get("/{channel}/oauth/callback")
async def oauth_callback(
    channel: str,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
):
    """Steps 3–6: Meta returns the credential → exchange → seal → store → Instagram API ready."""
    if channel not in SCOPES:
        return _done(channel, "unsupported_channel")
    if error:
        return _done(channel, f"meta_{error}")
    if not code or not state:
        return _done(channel, "missing_code_or_state")
    try:
        _require_app()
        if not settings.meta_app_secret or settings.meta_app_secret == "change-me":
            log.error("oauth callback: META_APP_SECRET not configured")
            return _done(channel, "app_secret_missing")
        _read_state(state, channel)
        try:
            short = await exchange_code_for_token(code, _redirect_uri(channel))
        except Exception as e:
            log.error("oauth token exchange failed: %s", str(e)[:300])
            return _done(channel, "token_exchange_failed")
        try:
            long_token = await to_long_lived_token(short)
        except Exception as e:
            log.error("oauth long-lived exchange failed: %s", str(e)[:300])
            return _done(channel, "long_lived_failed")
        try:
            pages = await fetch_managed_pages(long_token)
        except Exception as e:
            log.error("oauth page lookup failed: %s", str(e)[:300])
            return _done(channel, "page_lookup_failed")
        try:
            page_token, config = _pick_credential(channel, pages)
        except RuntimeError as e:
            log.error("oauth credential pick failed: %s", e)
            if str(e) == "NO_PAGES_AT_ALL":
                return _done(channel, "no_pages_returned")
            if "Instagram" in str(e):
                return _done(channel, "no_linked_instagram")
            return _done(channel, "no_pages")
        _store(channel, page_token, config)
    except HTTPException as e:
        return _done(channel, e.detail if isinstance(e.detail, str) else "bad_request")
    except Exception:
        log.exception("meta oauth callback failed")
        return _done(channel, "exchange_failed")
    return _done(channel)
