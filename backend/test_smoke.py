import hashlib
import hmac
import json

from fastapi.testclient import TestClient
from app.core.config import settings
from app.main import app


def test_health():
    assert TestClient(app).get("/health").status_code == 200


def test_webhook_queues_message():
    c = TestClient(app)
    payload = {"entry": [{"messaging": [{"sender": {"id": "123"}, "message": {"text": "hi", "mid": "m1"}}]}]}
    body = json.dumps(payload, separators=(",", ":")).encode()
    headers = {}
    if settings.meta_app_secret != "change-me":
        sig = "sha256=" + hmac.new(settings.meta_app_secret.encode(), body, hashlib.sha256).hexdigest()
        headers["X-Hub-Signature-256"] = sig
    assert c.post("/webhooks/instagram", content=body, headers={"Content-Type": "application/json", **headers}).json() == {"received": True}
