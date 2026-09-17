"""Assignment engine: classify → team → load-aware routing → history → APIs."""
import uuid

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.main import app
from app.models.conversation import Conversation, Message
from app.models.customer import Customer
from app.models.team import Team, TeamMember
from app.models.user import User
from app.services.assignment import (
    active_count,
    classify,
    find_candidate,
    maybe_auto_assign,
)
from app.workers.tasks import handle_message_event

c = TestClient(app)


def _auth():
    c.post("/api/v1/auth/seed-admin")
    t = c.post("/api/v1/auth/login", data={"username": "admin@fty.local", "password": "admin123"}).json()
    return {"Authorization": f"Bearer {t['access_token']}"}


def _user(db, email, name, role="agent", availability="available", max_active=10):
    u = db.query(User).filter_by(email=email).first()
    if not u:
        u = User(name=name, email=email, password_hash=hash_password("x"), role=role,
                 availability=availability, max_active=max_active)
        db.add(u)
        db.commit()
        db.refresh(u)
    return u


def _team(db, name, members=()):
    t = db.query(Team).filter_by(name=name).first()
    if not t:
        t = Team(name=name)
        db.add(t)
        db.commit()
        db.refresh(t)
    for u in members:
        if not db.query(TeamMember).filter_by(team_id=t.id, user_id=u.id).first():
            db.add(TeamMember(team_id=t.id, user_id=u.id))
    db.commit()
    return t


def _conv(db, customer_id, channel="web"):
    conv = Conversation(customer_id=customer_id, channel=channel, status="open")
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


def test_classify_routes_intents():
    assert classify("How much is the hoodie?").team == "Sales"
    assert classify("My order hasn't arrived").team == "Orders"
    assert classify("My order hasn't arrived").priority == "high"
    assert classify("I want to return this").team == "Customer Support"
    assert classify("Payment failed twice!").priority == "urgent"
    low = classify("Hello there, just browsing")
    assert low.confidence < 0.75


def test_load_aware_routing_skips_offline_and_full():
    db = SessionLocal()
    try:
        tag = uuid.uuid4().hex[:6]
        a = _user(db, f"a-{tag}@t.co", "AgA", availability="available")
        b = _user(db, f"b-{tag}@t.co", "AgB", availability="offline")
        d = _user(db, f"d-{tag}@t.co", "AgD", availability="available", max_active=1)
        team = f"TS-{tag}"
        _team(db, team, (a, b, d))
        cust = Customer(name="Load C")
        db.add(cust)
        db.commit()
        # d is at capacity
        full = _conv(db, cust.id)
        full.assigned_agent_id = d.id
        db.commit()
        # a has 2 active, so give a load of 2
        for _ in range(2):
            busy = _conv(db, cust.id)
            busy.assigned_agent_id = a.id
        db.commit()
        assert active_count(db, a.id) == 2
        pick = find_candidate(db, team)
        assert pick is not None and pick.id == a.id  # b offline, d full
    finally:
        db.close()


def test_load_aware_routing_skips_away_workers():
    db = SessionLocal()
    try:
        tag = uuid.uuid4().hex[:6]
        a = _user(db, f"avail-{tag}@t.co", "AgAvail", availability="available")
        away_worker = _user(db, f"away-{tag}@t.co", "AgAway", availability="away")
        team = f"AwayTeam-{tag}"
        _team(db, team, (a, away_worker))

        pick = find_candidate(db, team)
        assert pick is not None and pick.id == a.id

        # If available worker goes away too, nothing is routed
        a.availability = "away"
        db.commit()
        pick_none = find_candidate(db, team)
        assert pick_none is None
    finally:
        db.close()


def test_hybrid_auto_assign_and_unassigned_queue():
    db = SessionLocal()
    try:
        tag = uuid.uuid4().hex[:6]
        w = _user(db, f"w-{tag}@t.co", "WorkerW")
        _team(db, "Sales", (w,))  # real Sales pool → engine routes here
        cust = Customer(name="Hybrid C")
        db.add(cust)
        db.commit()

        # High confidence → assigned within the Sales pool
        conv = _conv(db, cust.id)
        cls = maybe_auto_assign(db, conv, "What is the price of the hoodie in XL?")
        assert cls.confidence >= 0.75
        assert conv.assigned_agent_id is not None
        assert conv.assigned_team == "Sales"
        assert conv.status == "assigned"
        assignee = db.get(User, conv.assigned_agent_id)
        assert assignee is not None

        # Low confidence → unassigned queue, no worker
        conv2 = _conv(db, cust.id)
        cls2 = maybe_auto_assign(db, conv2, "Hmm interesting, tell me things")
        assert cls2.confidence < 0.75
        assert conv2.assigned_agent_id is None
    finally:
        db.close()


def test_urgent_bypasses_to_manager():
    db = SessionLocal()
    try:
        tag = uuid.uuid4().hex[:6]
        ag = _user(db, f"ag-{tag}@t.co", "AgU")
        mg = _user(db, f"mg-{tag}@t.co", "MgrU", role="manager")
        _team(db, "Customer Support", (ag, mg))
        cust = Customer(name="Urgent C")
        db.add(cust)
        db.commit()
        conv = _conv(db, cust.id)
        maybe_auto_assign(db, conv, "I was charged twice, this is fraud!")
        assert conv.priority == "urgent"
        bypassed = db.get(User, conv.assigned_agent_id)
        assert bypassed is not None and bypassed.role in ("admin", "manager")
    finally:
        db.close()


def test_assign_status_history_api():
    h = _auth()
    cust = c.post("/api/v1/customers", json={"name": "Audit C"}, headers=h).json()
    conv = c.post("/api/v1/conversations", json={"customer_id": cust["id"], "channel": "web"}, headers=h).json()
    agents = c.get("/api/v1/agents", headers=h).json()
    ag = agents[0]

    r = c.patch(f"/api/v1/conversations/{conv['id']}/assign",
                params={"agent_id": ag["id"], "team": "Sales", "priority": "high", "reason": "looks like pricing"},
                headers=h)
    assert r.json()["ok"] is True
    r = c.patch(f"/api/v1/conversations/{conv['id']}/status", params={"status": "in_progress"}, headers=h)
    assert r.json()["status"] == "in_progress"
    hist = c.get(f"/api/v1/conversations/{conv['id']}/history", headers=h).json()
    actions = [e["action"] for e in hist]
    assert "assigned" in actions and "priority_changed" in actions and "status_changed" in actions
    assert any(e["reason"] == "looks like pricing" for e in hist)


def test_teams_api_and_availability():
    h = _auth()
    name = f"Team-{uuid.uuid4().hex[:6]}"
    t = c.post("/api/v1/teams", json={"name": name}, headers=h).json()
    assert t["name"] == name
    agents = c.get("/api/v1/agents", headers=h).json()
    ag = agents[0]
    assert c.post(f"/api/v1/teams/{t['id']}/members", json={"user_id": ag["id"]}, headers=h).json()["ok"] is True
    assert c.patch(f"/api/v1/agents/{ag['id']}", json={"availability": "away"}, headers=h).json()["ok"] is True
    teams = c.get("/api/v1/teams", headers=h).json()
    row = next(x for x in teams if x["id"] == t["id"])
    assert any(m["user_id"] == ag["id"] and m["availability"] == "away" for m in row["members"])
    # restore
    c.patch(f"/api/v1/agents/{ag['id']}", json={"availability": "available"}, headers=h)


def test_pipeline_auto_assigns_inbound():
    tag = uuid.uuid4().hex[:8]
    stored = handle_message_event("instagram", {"entry": [{"messaging": [{
        "sender": {"id": f"ig-{tag}"}, "message": {"text": "Do you have the black hoodie in XL?", "mid": f"m-{tag}"}}]}]})
    assert stored == 1
    db = SessionLocal()
    try:
        msg = db.query(Message).filter_by(external_message_id=f"m-{tag}").first()
        assert msg is not None
        conv = db.get(Conversation, msg.conversation_id)
        assert conv.assigned_team == "Sales"  # intent routed even before a worker is picked
    finally:
        db.close()
