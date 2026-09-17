"""Phase 2: channels, webhooks, webchat, outbound, notifications feed."""
import asyncio
import hashlib
import hmac

from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import SessionLocal
from app.channels import ADAPTERS
from app.channels.sending import deliver
from app.main import app
from app.models.conversation import Conversation

c = TestClient(app)


def test_adapters_normalize():
    ig = ADAPTERS["instagram"].normalize(
        {"entry": [{"messaging": [{"sender": {"id": "IG1"}, "message": {"text": "hi ig", "mid": "ig-m1"}}]}]}
    )
    assert ig[0].channel == "instagram" and ig[0].content == "hi ig"

    wa = ADAPTERS["whatsapp"].normalize(
        {"entry": [{"changes": [{"value": {"messages": [
            {"from": "233500000001", "id": "wa-m1", "type": "text", "text": {"body": "hi wa"}}]}}]}]}
    )
    assert wa[0].external_user_id == "233500000001" and wa[0].content == "hi wa"

    em = ADAPTERS["email"].normalize({"from": "a@b.com", "body": "help please"})
    assert em[0].channel == "email" and em[0].content == "help please"


def test_hub_verify_rejects_bad_token():
    r = c.get("/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.challenge": "42", "hub.verify_token": "nope"})
    assert r.status_code == 403


def test_hub_verify_accepts_good_token():
    old = settings.meta_verify_token
    settings.meta_verify_token = "test-token"
    try:
        r = c.get("/webhooks/facebook", params={"hub.mode": "subscribe", "hub.challenge": "42", "hub.verify_token": "test-token"})
        assert r.status_code == 200
    finally:
        settings.meta_verify_token = old


def test_signature_enforced_when_configured():
    old = settings.meta_app_secret
    settings.meta_app_secret = "s3cret"
    try:
        body = b'{"entry":[]}'
        r = c.post("/webhooks/instagram", content=body)  # unsigned
        assert r.status_code == 403
        sig = "sha256=" + hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()
        r = c.post("/webhooks/instagram", content=body, headers={"X-Hub-Signature-256": sig})
        assert r.json() == {"received": True}
    finally:
        settings.meta_app_secret = old


def test_webchat_roundtrip():
    s = c.post("/api/v1/web/sessions", json={"name": "Web Guest"}).json()
    assert s["guest_id"].startswith("web-")
    assert c.post(f"/api/v1/web/sessions/{s['guest_id']}/messages", json={"content": "hello from site"}).json()["ok"]
    msgs = c.get(f"/api/v1/web/sessions/{s['guest_id']}/messages").json()
    assert any(m["from"] == "customer" and "hello from site" in m["text"] for m in msgs["messages"])


def _auth():
    c.post("/api/v1/auth/seed-admin")
    t = c.post("/api/v1/auth/login", data={"username": "admin@fty.local", "password": "admin123"}).json()
    return {"Authorization": f"Bearer {t['access_token']}"}


def test_channels_api_and_updates_feed():
    h = _auth()
    rows = c.get("/api/v1/channels", headers=h).json()
    assert {r["channel"] for r in rows} >= {"instagram", "whatsapp", "web"}
    assert c.put("/api/v1/channels/web", json={}, headers=h).json()["connected"] is True
    feed = c.get("/api/v1/conversations/updates?since=0", headers=h).json()
    assert "latest" in feed and "messages" in feed


def test_outbound_no_config_returns_none():
    db = SessionLocal()
    try:
        conv = db.query(Conversation).filter_by(channel="instagram").order_by(Conversation.id.desc()).first()
        if conv is None:
            s = c.post("/api/v1/web/sessions", json={}).json()
            conv = db.get(Conversation, s["conversation_id"])
            conv.channel = "web"  # has identity → web short-circuits
            assert asyncio.run(deliver(db, conv, "hi")) == "web:stored"
            return
        assert asyncio.run(deliver(db, conv, "hi")) is None  # no tokens configured
    finally:
        db.close()


def test_widget_js_served():
    r = c.get("/api/v1/web/widget.js")
    assert r.status_code == 200 and "fty_guest" in r.text
