"""Hybrid assignment engine (spec): classify → team → load-aware routing → history.

Rules + suggestions first — no irreversible AI actions. High-confidence
inquiries auto-assign; low-confidence go to the Unassigned queue (§13).
"""
import logging
import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.assignment import AssignmentHistory
from app.models.conversation import Conversation
from app.models.team import Team, TeamMember
from app.models.user import User

log = logging.getLogger("fty.assign")

AUTO_ASSIGN_CONFIDENCE = 0.75
PRIORITY_RANK = {"low": 0, "normal": 1, "high": 2, "urgent": 3}
OPEN_STATES = {"new", "open", "assigned", "in_progress", "waiting_for_customer", "reopened"}

# intent, keywords, team, priority, confidence
INTENT_RULES: list[tuple[str, tuple[str, ...], str | None, str, float]] = [
    ("payment_issue", ("payment failed", "charged twice", "fraud", "scam", "stolen"), "Customer Support", "urgent", 0.90),
    ("complaint", ("complaint", "terrible", "awful", "worst", "angry", "disappointed", "rude"), "Customer Support", "high", 0.80),
    ("return_request", ("return", "refund", "exchange"), "Customer Support", "normal", 0.85),
    ("order_issue", ("order", "deliver", "shipping", "shipped", "tracking", "package", "arrived", "late"), "Orders", "high", 0.85),
    ("sales_inquiry", ("price", "pricing", "cost", "how much", "size", "sizes", "color", "colour",
                        "stock", "available", "discount", "wholesale",
                        "hoodie", "shirt", "shoe", "shoes", "sneaker", "dress", "jacket", "clothes"), "Sales", "normal", 0.80),
]


@dataclass
class Classification:
    intent: str
    confidence: float
    team: str | None
    priority: str


def classify(content: str) -> Classification:
    text = content.lower()
    for intent, keywords, team, priority, confidence in INTENT_RULES:
        if any(k in text for k in keywords):
            return Classification(intent, confidence, team, priority)
    if re.search(r"\b(hi|hey|hello|good morning|good afternoon)\b", text) or \
            any(k in text for k in ("please", "help", "question")):
        return Classification("general", 0.55, "Customer Support", "low")
    return Classification("general", 0.40, None, "normal")


def route_team(content: str) -> str:
    """Legacy helper kept for compatibility — prefer classify()."""
    return classify(content).team or "Support"


def active_count(db: Session, user_id: int) -> int:
    return (
        db.query(Conversation)
        .filter(
            Conversation.assigned_agent_id == user_id,
            Conversation.status.in_(OPEN_STATES),
        )
        .count()
    )


def team_pool(db: Session, team_name: str | None) -> list[User]:
    """Workers eligible for a team: members first, legacy team label as fallback."""
    named = _named_pool(db, team_name) if team_name else []
    return named or db.query(User).all()


def _named_pool(db: Session, team_name: str) -> list[User]:
    member_ids = [
        r[0] for r in db.query(TeamMember.user_id)
        .join(Team, Team.id == TeamMember.team_id)
        .filter(Team.name == team_name).all()
    ]
    users = db.query(User).filter(User.id.in_(member_ids)).all() if member_ids else []
    legacy = db.query(User).filter(User.team == team_name).all()
    seen = {u.id for u in users}
    return users + [u for u in legacy if u.id not in seen]


def find_candidate(db: Session, team_name: str | None, urgent_bypass: bool = False) -> User | None:
    """Load-aware routing: lowest active load, skipping offline/over-capacity workers.

    A named team with zero workers routes to the manager review queue (None) —
    never dumped on random staff — except urgent bypass, which must land somewhere.
    """
    if team_name and not _named_pool(db, team_name) and not urgent_bypass:
        return None
    pool = team_pool(db, team_name)
    if urgent_bypass:
        managers = [u for u in pool if u.role in ("admin", "manager")]
        if managers:
            pool = managers
    eligible = []
    for u in pool:
        if (u.availability or "available") in ("offline", "away"):
            continue
        load = active_count(db, u.id)
        capacity = u.max_active if u.max_active and u.max_active > 0 else 10
        if load >= capacity:
            continue
        eligible.append((load, u.id, u))
    if not eligible and urgent_bypass:
        # Urgent must land somewhere: any available worker with room.
        for u in db.query(User).all():
            if (u.availability or "available") in ("offline", "away"):
                continue
            load = active_count(db, u.id)
            capacity = u.max_active if u.max_active and u.max_active > 0 else 10
            if load < capacity:
                eligible.append((load, u.id, u))
    if not eligible:
        return None
    eligible.sort(key=lambda t: (t[0], t[1]))
    return eligible[0][2]


def record_history(
    db: Session,
    conv: Conversation,
    action: str,
    assigned_by: str = "auto",
    from_user_id: int | None = None,
    to_user_id: int | None = None,
    from_team: str | None = None,
    to_team: str | None = None,
    detail: str | None = None,
    reason: str | None = None,
) -> None:
    db.add(AssignmentHistory(
        conversation_id=conv.id, action=action, assigned_by=assigned_by,
        from_user_id=from_user_id if from_user_id is not None else conv.assigned_agent_id,
        to_user_id=to_user_id if to_user_id is not None else conv.assigned_agent_id,
        from_team=from_team if from_team is not None else conv.assigned_team,
        to_team=to_team if to_team is not None else conv.assigned_team,
        detail=detail, reason=reason,
    ))


def maybe_auto_assign(db: Session, conv: Conversation, content: str) -> Classification:
    """Route one incoming customer message. Returns its classification.

    - Unassigned conversation + high confidence → team + worker assigned.
    - Unassigned + low confidence → team suggestion only (manager review queue).
    - Already assigned → escalate priority upward only, never re-route silently.
    - Urgent → least-loaded manager/admin (bypass).
    """
    cls = classify(content)

    if PRIORITY_RANK.get(cls.priority, 1) > PRIORITY_RANK.get(conv.priority or "normal", 1):
        old = conv.priority
        conv.priority = cls.priority
        record_history(db, conv, "priority_changed", detail=f"{old} → {cls.priority}",
                       reason=f"auto: {cls.intent} ({cls.confidence:.0%})")

    if conv.assigned_agent_id is not None:
        db.commit()
        return cls

    if cls.team and conv.assigned_team != cls.team and cls.confidence >= 0.55:
        record_history(db, conv, "triaged", to_team=cls.team,
                       detail=f"intent={cls.intent} confidence={cls.confidence:.0%}")
        conv.assigned_team = cls.team

    if cls.confidence < AUTO_ASSIGN_CONFIDENCE:
        db.commit()  # stays in the Unassigned queue for manager review
        return cls

    urgent = cls.priority == "urgent"
    candidate = find_candidate(db, conv.assigned_team, urgent_bypass=urgent)
    if candidate is None:
        db.commit()
        return cls

    conv.assigned_agent_id = candidate.id
    if conv.status in ("new", "open"):
        conv.status = "assigned"
    record_history(
        db, conv, "assigned", to_user_id=candidate.id,
        detail=f"intent={cls.intent} confidence={cls.confidence:.0%} load={active_count(db, candidate.id)}",
        reason="urgent bypass → on-duty manager" if urgent and candidate.role in ("admin", "manager") else "auto: lowest active load",
    )
    db.commit()
    log.info("auto-assigned conversation %s → %s (%s)", conv.id, candidate.name, cls.intent)
    return cls
