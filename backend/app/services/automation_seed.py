"""Seed a small set of working automation examples.
Run once per fresh DB so the feature is self-explanatory.
"""
import json
from sqlalchemy.orm import Session
from app.models.automation import AutomationRule

PRESETS = [
    {
        "name": "VIP → urgent + manager",
        "trigger": "message_created",
        "conditions": {"contains": "vip"},
        "actions": {"set_priority": "urgent", "escalate": True},
    },
    {
        "name": "Instagram complaints → Customer Support",
        "trigger": "message_created",
        "conditions": {"channel": "instagram", "contains": "complaint"},
        "actions": {"set_team": "Customer Support", "set_priority": "high"},
    },
    {
        "name": "Return requests → triage + assign",
        "trigger": "message_created",
        "conditions": {"intent": "return_request", "min_confidence": 0.7},
        "actions": {"set_team": "Customer Support", "auto_assign": True},
    },
    {
        "name": "Uncategorized tickets → normal",
        "trigger": "ticket_created",
        "conditions": {"contains": "general"},
        "actions": {"set_priority": "normal"},
    },
]


def ensure_presets(db: Session) -> int:
    if db.query(AutomationRule).first():
        return 0
    for p in PRESETS:
        db.add(AutomationRule(
            name=p["name"], trigger=p["trigger"],
            conditions=json.dumps(p["conditions"]), actions=json.dumps(p["actions"]),
            enabled=True,
        ))
    db.commit()
    return len(PRESETS)
