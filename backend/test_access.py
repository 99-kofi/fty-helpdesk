"""Access control: admin has full access; everyone else sees only assigned work."""
import uuid

from fastapi.testclient import TestClient
from app.main import app

c = TestClient(app)

ADMIN_PAGES = [
    "/api/v1/channels",
    "/api/v1/teams",
    "/api/v1/automation",
    "/api/v1/analytics/overview",
    "/api/v1/analytics/summary",
]
# Knowledge is readable by all authenticated users (for AI suggestions + inbox)
READABLE_KB = ["/api/v1/knowledge", "/api/v1/knowledge/categories"]


def _admin():
    c.post("/api/v1/auth/seed-admin")
    t = c.post("/api/v1/auth/login", data={"username": "admin@fty.local", "password": "admin123"}).json()
    return {"Authorization": f"Bearer {t['access_token']}"}


def _worker(tag):
    h = _admin()
    email = f"locked-{tag}@fty.local"
    c.post("/api/v1/users", json={"name": "Locked", "email": email, "password": "secret123"}, headers=h)
    t = c.post("/api/v1/auth/login", data={"username": email, "password": "secret123"}).json()
    me = c.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {t['access_token']}"}).json()
    return {"Authorization": f"Bearer {t['access_token']}"}, me


def test_admin_pages_forbidden_for_workers():
    h = _admin()
    tag = uuid.uuid4().hex[:6]
    w, _ = _worker(tag)
    for path in ADMIN_PAGES:
        assert c.get(path, headers=w).status_code == 403, path
    for path in ADMIN_PAGES:
        assert c.get(path, headers=h).status_code == 200, path
    # KB is readable by workers (for AI) — writes still admin-only
    for path in READABLE_KB:
        assert c.get(path, headers=w).status_code == 200, path
        assert c.post("/api/v1/knowledge", json={"category": "Test", "title": "t", "body": "b"}, headers=w).status_code == 403


def test_worker_mutations_restricted():
    h = _admin()
    tag = uuid.uuid4().hex[:6]
    w, me = _worker(tag)
    cust = c.post("/api/v1/customers", json={"name": f"L-{tag}"}, headers=h).json()
    conv = c.post("/api/v1/conversations", json={"customer_id": cust["id"], "channel": "web"}, headers=h).json()
    cid = conv["id"]

    # read others' work → 403; write anything structural → 403
    assert c.get(f"/api/v1/conversations/{cid}/messages", headers=w).status_code == 403
    assert c.get(f"/api/v1/conversations/{cid}/history", headers=w).status_code == 403
    assert c.post(f"/api/v1/conversations/{cid}/messages",
                  json={"sender_type": "agent", "content": "hi"}, headers=w).status_code == 403
    assert c.patch(f"/api/v1/conversations/{cid}/assign",
                   params={"agent_id": me["id"]}, headers=w).status_code == 403
    assert c.patch(f"/api/v1/conversations/{cid}/status",
                   params={"status": "in_progress"}, headers=w).status_code == 403
    assert c.post("/api/v1/tickets", json={"conversation_id": cid, "category": "x"}, headers=w).status_code == 403
    assert c.post("/api/v1/customers", json={"name": "x"}, headers=w).status_code == 403
    assert c.post("/api/v1/conversations", json={"customer_id": cust["id"], "channel": "web"}, headers=w).status_code == 403
    # invisible in scoped lists
    assert all(x["id"] != cid for x in c.get("/api/v1/conversations", headers=w).json())
    assert all(x["id"] != cust["id"] for x in c.get("/api/v1/customers", headers=w).json())


def test_worker_can_work_assigned_tasks():
    h = _admin()
    tag = uuid.uuid4().hex[:6]
    w, me = _worker(tag)
    cust = c.post("/api/v1/customers", json={"name": f"W-{tag}"}, headers=h).json()
    conv = c.post("/api/v1/conversations", json={"customer_id": cust["id"], "channel": "web"}, headers=h).json()
    cid = conv["id"]
    c.patch(f"/api/v1/conversations/{cid}/assign", params={"agent_id": me["id"]}, headers=h)

    assert any(x["id"] == cid for x in c.get("/api/v1/conversations", headers=w).json())
    assert any(x["id"] == cust["id"] for x in c.get("/api/v1/customers", headers=w).json())
    assert c.get(f"/api/v1/conversations/{cid}/messages", headers=w).status_code == 200
    assert c.post(f"/api/v1/conversations/{cid}/messages",
                  json={"sender_type": "agent", "content": "on it"}, headers=w).status_code == 200
    assert c.patch(f"/api/v1/conversations/{cid}/status",
                   params={"status": "in_progress"}, headers=w).json()["ok"] is True
    t = c.post("/api/v1/tickets", json={"conversation_id": cid, "category": "general"}, headers=w).json()
    assert t["conversation_id"] == cid
    assert c.patch(f"/api/v1/tickets/{t['id']}", params={"status": "resolved"}, headers=w).json()["ok"] is True
    # but cannot reassign tickets (even to self) — admin only
    assert c.patch(f"/api/v1/tickets/{t['id']}", params={"assigned_to": me["id"]}, headers=w).status_code == 403
    hist = c.get(f"/api/v1/conversations/{cid}/history", headers=w).json()
    assert isinstance(hist, list)
