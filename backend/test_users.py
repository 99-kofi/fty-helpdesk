"""Worker logins: admin creates accounts, workers sign in, see only assigned customers."""
import uuid

from fastapi.testclient import TestClient
from app.main import app

c = TestClient(app)


def _admin():
    c.post("/api/v1/auth/seed-admin")
    t = c.post("/api/v1/auth/login", data={"username": "admin@fty.local", "password": "admin123"}).json()
    return {"Authorization": f"Bearer {t['access_token']}"}


def _login(email, password):
    t = c.post("/api/v1/auth/login", data={"username": email, "password": password}).json()
    return {"Authorization": f"Bearer {t['access_token']}"}


def test_admin_creates_worker_login():
    h = _admin()
    tag = uuid.uuid4().hex[:6]
    email = f"worker-{tag}@fty.local"
    u = c.post("/api/v1/users", json={
        "name": "New Worker", "email": email, "password": "secret123", "role": "agent",
    }, headers=h).json()
    assert u["email"] == email and u["role"] == "agent"
    # duplicate + weak password + bad role rejected
    assert c.post("/api/v1/users", json={"name": "x", "email": email, "password": "secret123"}, headers=h).status_code == 409
    assert c.post("/api/v1/users", json={"name": "x", "email": f"y-{tag}@fty.local", "password": "123"}, headers=h).status_code == 422
    assert c.post("/api/v1/users", json={"name": "x", "email": f"z-{tag}@fty.local", "password": "secret123", "role": "boss"}, headers=h).status_code == 422
    # the worker can log in on the same login endpoint
    w = _login(email, "secret123")
    me = c.get("/api/v1/auth/me", headers=w).json()
    assert me["email"] == email and me["role"] == "agent"
    # a non-admin cannot create logins
    assert c.post("/api/v1/users", json={"name": "x", "email": f"q-{tag}@fty.local", "password": "secret123"}, headers=w).status_code == 403


def test_worker_sees_only_assigned_customers():
    h = _admin()
    tag = uuid.uuid4().hex[:6]
    email = f"scoped-{tag}@fty.local"
    c.post("/api/v1/users", json={"name": "Scoped", "email": email, "password": "secret123"}, headers=h)
    w = _login(email, "secret123")
    me = c.get("/api/v1/auth/me", headers=w).json()

    assert c.get("/api/v1/customers", headers=w).json() == []
    assert c.get("/api/v1/conversations", headers=w).json() == []

    cust = c.post("/api/v1/customers", json={"name": f"C-{tag}"}, headers=h).json()
    conv = c.post("/api/v1/conversations", json={"customer_id": cust["id"], "channel": "web"}, headers=h).json()
    # before assignment: invisible to the worker
    assert all(x["id"] != cust["id"] for x in c.get("/api/v1/customers", headers=w).json())
    c.patch(f"/api/v1/conversations/{conv['id']}/assign", params={"agent_id": me["id"]}, headers=h)
    # after assignment: the customer (and thread) appear
    assert any(x["id"] == cust["id"] for x in c.get("/api/v1/customers", headers=w).json())
    assert any(x["id"] == conv["id"] for x in c.get("/api/v1/conversations", headers=w).json())


def test_admin_resets_password_and_role():
    h = _admin()
    tag = uuid.uuid4().hex[:6]
    email = f"reset-{tag}@fty.local"
    u = c.post("/api/v1/users", json={"name": "Reset", "email": email, "password": "oldpass1"}, headers=h).json()
    assert c.patch(f"/api/v1/users/{u['id']}", json={"password": "newpass2"}, headers=h).json()["id"] == u["id"]
    assert c.post("/api/v1/auth/login", data={"username": email, "password": "oldpass1"}).status_code == 401
    _login(email, "newpass2")  # new password works
    assert c.patch(f"/api/v1/users/{u['id']}", json={"role": "manager"}, headers=h).json()["role"] == "manager"
