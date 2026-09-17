"""Meta OAuth connect: vault, start URL, callback, encrypted storage."""
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

import app.api.v1.oauth as oauth_mod
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.vault import open_secret, seal
from app.main import app
from app.models.channel import ChannelConnection

c = TestClient(app, follow_redirects=False)


def _auth():
    c.post("/api/v1/auth/seed-admin")
    t = c.post("/api/v1/auth/login", data={"username": "admin@fty.local", "password": "admin123"}).json()
    return {"Authorization": f"Bearer {t['access_token']}"}


def test_vault_roundtrip_and_legacy():
    s = seal("page-token-123")
    assert s.startswith("enc:") and "page-token-123" not in s
    assert open_secret(s) == "page-token-123"
    assert open_secret("plain-legacy") == "plain-legacy"
    assert open_secret(None) == ""


def test_vault_wrong_key_fails_closed():
    s = seal("abc")
    old = settings.token_encryption_key
    settings.token_encryption_key = "something-else"
    try:
        assert open_secret(s) == ""
    finally:
        settings.token_encryption_key = old


def test_oauth_start_needs_app_id():
    old = settings.meta_app_id
    settings.meta_app_id = ""
    try:
        assert c.get("/api/v1/channels/instagram/oauth/start", headers=_auth()).status_code == 400
    finally:
        settings.meta_app_id = old


def test_oauth_start_builds_meta_url():
    old = settings.meta_app_id
    settings.meta_app_id = "12345"
    try:
        url = c.get("/api/v1/channels/instagram/oauth/start", headers=_auth()).json()["url"]
        assert "facebook.com" in url and "client_id=12345" in url
        assert "instagram_manage_messages" in url.replace("%2C", ",").replace(",", ",")
        assert "instagram_basic" in url
        assert "state=" in url
    finally:
        settings.meta_app_id = old


def test_oauth_callback_rejects_bad_state():
    r = c.get("/api/v1/channels/instagram/oauth/callback", params={"code": "x", "state": "bogus"})
    assert r.status_code in (302, 303, 307)
    assert "oauth_error" in r.headers["location"]


async def _fake_short(code: str, redirect_uri: str) -> str:
    assert code == "auth-code-1"
    return "short-token"


async def _fake_long(short: str) -> str:
    assert short == "short-token"
    return "long-token"


async def _fake_pages(long_token: str) -> list[dict]:
    assert long_token == "long-token"
    return [{"id": "page-1", "name": "FTY", "access_token": "PAGE_TOKEN_SECURE",
             "instagram_business_account": {"id": "ig-9", "username": "fty"}}]


def test_oauth_callback_full_flow(monkeypatch):
    monkeypatch.setattr(oauth_mod, "exchange_code_for_token", _fake_short)
    monkeypatch.setattr(oauth_mod, "to_long_lived_token", _fake_long)
    monkeypatch.setattr(oauth_mod, "fetch_managed_pages", _fake_pages)
    old_app, old_front = settings.meta_app_id, settings.frontend_url
    old_secret = settings.meta_app_secret
    settings.meta_app_id = "12345"
    settings.meta_app_secret = "test-secret"
    settings.frontend_url = "http://test-front"
    try:
        url = c.get("/api/v1/channels/instagram/oauth/start", headers=_auth()).json()["url"]
        state = parse_qs(urlparse(url).query)["state"][0]
        r = c.get("/api/v1/channels/instagram/oauth/callback", params={"code": "auth-code-1", "state": state})
        assert r.status_code in (302, 303, 307)
        assert "connected=instagram" in r.headers["location"]

        db = SessionLocal()
        try:
            row = db.query(ChannelConnection).filter_by(channel="instagram").first()
            assert row is not None
            assert row.access_token.startswith("enc:")
            assert "PAGE_TOKEN_SECURE" not in row.access_token
            assert open_secret(row.access_token) == "PAGE_TOKEN_SECURE"
            assert '"ig-9"' in (row.config or "")
        finally:
            db.close()
    finally:
        settings.meta_app_id = old_app
        settings.meta_app_secret = old_secret
        settings.frontend_url = old_front


def test_oauth_callback_empty_pages_slug(monkeypatch):
    async def _empty(long_token: str) -> list[dict]:
        return []

    monkeypatch.setattr(oauth_mod, "exchange_code_for_token", _fake_short)
    monkeypatch.setattr(oauth_mod, "to_long_lived_token", _fake_long)
    monkeypatch.setattr(oauth_mod, "fetch_managed_pages", _empty)
    old_app, old_secret = settings.meta_app_id, settings.meta_app_secret
    settings.meta_app_id = "12345"
    settings.meta_app_secret = "test-secret"
    try:
        url = c.get("/api/v1/channels/instagram/oauth/start", headers=_auth()).json()["url"]
        state = parse_qs(urlparse(url).query)["state"][0]
        r = c.get("/api/v1/channels/instagram/oauth/callback", params={"code": "auth-code-1", "state": state})
        assert "no_pages_returned" in r.headers["location"]
    finally:
        settings.meta_app_id = old_app
        settings.meta_app_secret = old_secret


def test_oauth_callback_flags_missing_secret():
    old_app, old_secret = settings.meta_app_id, settings.meta_app_secret
    settings.meta_app_id = "12345"
    try:
        url = c.get("/api/v1/channels/instagram/oauth/start", headers=_auth()).json()["url"]
        state = parse_qs(urlparse(url).query)["state"][0]
        settings.meta_app_secret = "change-me"
        r = c.get("/api/v1/channels/instagram/oauth/callback", params={"code": "x", "state": state})
        assert "app_secret_missing" in r.headers["location"]
    finally:
        settings.meta_app_id = old_app
        settings.meta_app_secret = old_secret


def test_oauth_callback_names_failed_step(monkeypatch):
    async def _boom(code: str, redirect_uri: str) -> str:
        raise RuntimeError("invalid code")

    monkeypatch.setattr(oauth_mod, "exchange_code_for_token", _boom)
    old_app, old_secret = settings.meta_app_id, settings.meta_app_secret
    settings.meta_app_id = "12345"
    settings.meta_app_secret = "test-secret"
    try:
        url = c.get("/api/v1/channels/instagram/oauth/start", headers=_auth()).json()["url"]
        state = parse_qs(urlparse(url).query)["state"][0]
        r = c.get("/api/v1/channels/instagram/oauth/callback", params={"code": "bad", "state": state})
        assert "token_exchange_failed" in r.headers["location"]
    finally:
        settings.meta_app_id = old_app
        settings.meta_app_secret = old_secret
