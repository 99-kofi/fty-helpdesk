"""Real analytics (Phase 3): response/resolution times, volumes, scorecards."""
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.models.assignment import AssignmentHistory
from app.models.conversation import Conversation, Message
from app.models.ticket import Ticket
from app.models.user import User
from app.services.assignment import OPEN_STATES

router = APIRouter(tags=["analytics"], dependencies=[Depends(require_role("admin"))])


def _as_utc(dt):
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _minutes(a, b) -> float | None:
    a, b = _as_utc(a), _as_utc(b)
    if not a or not b:
        return None
    return (b - a).total_seconds() / 60.0


def _avg(xs: list[float]) -> float | None:
    xs = [x for x in xs if x is not None and x >= 0]
    return round(sum(xs) / len(xs), 1) if xs else None


@router.get("/analytics/overview")
def overview(db: Session = Depends(get_db)):
    convs = db.query(Conversation).order_by(Conversation.id.desc()).limit(2000).all()
    conv_ids = [c.id for c in convs]
    msgs: list[Message] = (
        db.query(Message).filter(Message.conversation_id.in_(conv_ids)).order_by(Message.id).all()
        if conv_ids else []
    )
    by_conv: dict[int, list[Message]] = defaultdict(list)
    for m in msgs:
        by_conv[m.conversation_id].append(m)
    tickets = db.query(Ticket).order_by(Ticket.id.desc()).limit(2000).all()
    users = {u.id: u for u in db.query(User).all()}
    hist = db.query(AssignmentHistory).filter(
        AssignmentHistory.conversation_id.in_(conv_ids),
        AssignmentHistory.action == "status_changed").all() if conv_ids else []
    resolved_at: dict[int, object] = {}
    for h in hist:
        if h.detail and h.detail.endswith("→ resolved") or (h.detail or "").endswith("→ closed"):
            resolved_at[h.conversation_id] = h.created_at

    first_resp, resolution = [], []
    for c in convs:
        ms = by_conv.get(c.id, [])
        cust = [m for m in ms if m.sender_type == "customer"]
        ag = [m for m in ms if m.sender_type in ("agent", "ai")]
        if cust and ag:
            first_ag = next((m for m in ag if m.created_at and cust[0].created_at and
                             _as_utc(m.created_at) >= _as_utc(cust[0].created_at)), None)
            if first_ag:
                first_resp.append(_minutes(cust[0].created_at, first_ag.created_at))
        if c.status in ("resolved", "closed"):
            end = resolved_at.get(c.id, c.updated_at)
            resolution.append(_minutes(c.created_at, end))

    # 14-day volume
    days, day_conv, day_msg = [], Counter(), Counter()
    today = datetime.now(timezone.utc).date()
    for i in range(13, -1, -1):
        days.append((today - timedelta(days=i)).isoformat())
    for c in convs:
        d = _as_utc(c.created_at)
        if d and (today - d.date()).days < 14:
            day_conv[d.date().isoformat()] += 1
    for m in msgs:
        d = _as_utc(m.created_at)
        if d and (today - d.date()).days < 14:
            day_msg[d.date().isoformat()] += 1

    per_agent: dict[int, dict] = {}
    for c in convs:
        if c.assigned_agent_id:
            per_agent.setdefault(c.assigned_agent_id, {"active": 0, "resp": []})
            if c.status in OPEN_STATES:
                per_agent[c.assigned_agent_id]["active"] += 1
            ms = by_conv.get(c.id, [])
            cust = [m for m in ms if m.sender_type == "customer"]
            ag = [m for m in ms if m.sender_type in ("agent", "ai")]
            if cust and ag:
                r = _minutes(cust[0].created_at, ag[-1].created_at)
                if r is not None and r >= 0:
                    per_agent[c.assigned_agent_id]["resp"].append(r)
    resolved_tickets: Counter = Counter()
    for t in tickets:
        if t.status in ("resolved", "closed") and t.assigned_to:
            resolved_tickets[t.assigned_to] += 1

    return {
        "totals": {
            "conversations": db.query(Conversation).count(),
            "messages": db.query(Message).count(),
            "tickets": db.query(Ticket).count(),
            "open_conversations": sum(1 for c in convs if c.status in OPEN_STATES),
            "unassigned": sum(1 for c in convs if not c.assigned_agent_id and c.status in OPEN_STATES),
            "urgent": sum(1 for c in convs if c.priority == "urgent" and c.status in OPEN_STATES),
        },
        "avg_first_response_min": _avg(first_resp),
        "avg_resolution_hours": round(_avg(resolution) / 60, 1) if _avg(resolution) is not None else None,
        "volume_14d": [{"day": d, "conversations": day_conv.get(d, 0), "messages": day_msg.get(d, 0)} for d in days],
        "by_channel": dict(Counter(c.channel for c in convs)),
        "by_team": dict(Counter(c.assigned_team or "unassigned" for c in convs if c.status in OPEN_STATES)),
        "tickets_by_category": dict(Counter(t.category or "uncategorized" for t in tickets)),
        "agents": [{
            "id": uid, "name": (users.get(uid).name if users.get(uid) else f"#{uid}"),
            "active": v["active"], "resolved_tickets": resolved_tickets.get(uid, 0),
            "avg_response_min": _avg(v["resp"]),
        } for uid, v in sorted(per_agent.items())],
    }
