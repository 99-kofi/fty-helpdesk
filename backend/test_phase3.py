"""Phase 3: automation rules, SLA watchdog, knowledge base, analytics."""
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import SessionLocal
from app.main import app
from app.models.conversation import Conversation, Message
from app.models.customer import Customer
from app.models.ticket import Ticket
from app.services.sla import run_sla_check
from app.workers.tasks import handle_message_event

c = TestClient(app)


def _auth():
    c.post("/api/v1/auth/seed-admin")
    t = c.post("/api/v1/auth/login", data={"username": "admin@fty.local", "password": "admin123"}).json()
    return {"Authorization": f"Bearer {t['access_token']}"}


def _rule(trigger, conditions, actions):
    h = _auth()
    return c.post("/api/v1/automation", json={
        "name": f"R-{conditions}-{actions}", "trigger": trigger,
        "conditions": conditions, "actions": actions}, headers=h).json()


def test_rules_crud_and_permissions():
    h = _auth()
    r = _rule("message_created", {"contains": "placeholder-xyz"}, {"set_priority": "high"})
    assert r["enabled"] is True
    rules = c.get("/api/v1/automation", headers=h).json()
    assert any(x["id"] == r["id"] for x in rules)
    assert c.patch(f"/api/v1/automation/{r['id']}", json={"enabled": False}, headers=h).json()["enabled"] is False
    assert c.delete(f"/api/v1/automation/{r['id']}", headers=h).json()["ok"] is True
    # unauthenticated writes are rejected
    assert c.post("/api/v1/automation", json={"name": "x", "trigger": "message_created"}).status_code in (401, 403)


def test_keyword_rule_fires_on_inbound():
    import uuid
    tag = uuid.uuid4().hex[:8]
    rule = _rule("message_created", {"contains": f"vip-{tag}"}, {"set_priority": "urgent"})
    try:
        stored = handle_message_event("web", {"guest": f"ignored-{tag}", "messages": []})  # unknown shape → 0
        assert stored == 0
        # web adapter needs session flow; use email adapter shape instead
        stored = handle_message_event("email", {"from": f"vip-{tag}@x.co", "body": f"I am a VIP-{tag} customer, help"})
        assert stored == 1
        db = SessionLocal()
        try:
            msg = db.query(Message).filter(Message.content.like(f"%VIP-{tag}%")).first()
            assert msg is not None
            conv = db.get(Conversation, msg.conversation_id)
            assert conv.priority == "urgent"
        finally:
            db.close()
    finally:
        c.delete(f"/api/v1/automation/{rule['id']}", headers=_auth())


def test_escalate_action_routes_to_manager():
    import uuid
    tag = uuid.uuid4().hex[:8]
    rule = _rule("message_created", {"contains": f"lawsuit-{tag}"}, {"escalate": True})
    try:
        handle_message_event("email", {"from": f"e-{tag}@x.co", "body": f"This is lawsuit-{tag} territory"})
        db = SessionLocal()
        try:
            msg = db.query(Message).filter(Message.content.like(f"%lawsuit-{tag}%")).first()
            conv = db.get(Conversation, msg.conversation_id)
            assert conv.priority == "urgent"
            from app.models.user import User
            u = db.get(User, conv.assigned_agent_id)
            assert u is not None and u.role in ("admin", "manager")
        finally:
            db.close()
    finally:
        c.delete(f"/api/v1/automation/{rule['id']}", headers=_auth())


def test_disabled_rule_does_nothing():
    import uuid
    tag = uuid.uuid4().hex[:8]
    rule = _rule("message_created", {"contains": f"zzz-{tag}"}, {"set_priority": "urgent"})
    c.patch(f"/api/v1/automation/{rule['id']}", json={"enabled": False}, headers=_auth())
    try:
        handle_message_event("email", {"from": f"z-{tag}@x.co", "body": f"nothing special zzz-{tag} here"})
        db = SessionLocal()
        try:
            msg = db.query(Message).filter(Message.content.like(f"%zzz-{tag}%")).first()
            conv = db.get(Conversation, msg.conversation_id)
            assert conv.priority != "urgent"
        finally:
            db.close()
    finally:
        c.delete(f"/api/v1/automation/{rule['id']}", headers=_auth())


def test_sla_escalates_unanswered_conversation():
    db = SessionLocal()
    try:
        cust = Customer(name="SLA C")
        db.add(cust)
        db.commit()
        conv = Conversation(customer_id=cust.id, channel="web", status="open")
        db.add(conv)
        db.commit()
        old = datetime.now(timezone.utc) - timedelta(minutes=settings.sla_first_response_minutes + 15)
        db.add(Message(conversation_id=conv.id, sender_type="customer", sender_id="g", content="waiting…", created_at=old))
        db.commit()
        cid = conv.id
    finally:
        db.close()
    out = run_sla_check(SessionLocal())
    assert out["conversations_escalated"] >= 1
    db = SessionLocal()
    try:
        conv = db.get(Conversation, cid)
        assert conv.priority == "urgent"
        assert conv.assigned_agent_id is not None
        n1 = len([h for h in conv_history(db, cid) if h == "escalated"])
        out2 = run_sla_check(db)
        n2 = len([h for h in conv_history(db, cid) if h == "escalated"])
        assert n1 == n2 == 1  # idempotent — no double escalation
    finally:
        db.close()


def conv_history(db, cid):
    from app.models.assignment import AssignmentHistory
    return [h.action for h in db.query(AssignmentHistory).filter_by(conversation_id=cid).all()]


def test_sla_escalates_stale_ticket():
    h = _auth()
    cust = c.post("/api/v1/customers", json={"name": "SLA T"}, headers=h).json()
    conv = c.post("/api/v1/conversations", json={"customer_id": cust["id"], "channel": "web"}, headers=h).json()
    t = c.post("/api/v1/tickets", json={"conversation_id": conv["id"], "category": "general"}, headers=h).json()
    db = SessionLocal()
    try:
        row = db.get(Ticket, t["id"])
        row.created_at = datetime.now(timezone.utc) - timedelta(hours=settings.sla_resolution_hours + 1)
        db.commit()
    finally:
        db.close()
    out = run_sla_check(SessionLocal())
    assert out["tickets_escalated"] >= 1
    got = c.get("/api/v1/tickets", headers=h).json()
    row = next(x for x in got if x["id"] == t["id"])
    assert row["priority"] == "urgent"


def test_knowledge_crud_search():
    h = _auth()
    a = c.post("/api/v1/knowledge", json={"category": "Returns", "title": "Return window?",
                                          "body": "30 days with receipt."}, headers=h).json()
    assert a["id"]
    assert any(x["id"] == a["id"] for x in c.get("/api/v1/knowledge", params={"q": "receipt"}, headers=h).json())
    assert "Returns" in c.get("/api/v1/knowledge/categories", headers=h).json()
    assert c.patch(f"/api/v1/knowledge/{a['id']}", json={"title": "Return window (updated)"}, headers=h).json()["title"].endswith("(updated)")
    assert c.delete(f"/api/v1/knowledge/{a['id']}", headers=h).json()["ok"] is True


def test_analytics_overview_shape():
    h = _auth()
    ov = c.get("/api/v1/analytics/overview", headers=h).json()
    assert set(ov["totals"]) >= {"conversations", "messages", "tickets", "open_conversations", "unassigned", "urgent"}
    assert len(ov["volume_14d"]) == 14
    assert isinstance(ov["by_channel"], dict)
    assert isinstance(ov["agents"], list)
