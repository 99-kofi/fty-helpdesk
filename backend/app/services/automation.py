"""Automation rules engine (spec §10: WHEN something happens → IF condition → DO something).

Rules live in the AutomationRule table and are evaluated on events:
  message_created — a customer message arrives (after the assignment engine)
  ticket_created  — a support ticket is filed

Conditions (all must match; empty = always):
  channel: exact channel name
  contains: substring (case-insensitive) in the message/category text
  intent: classified intent id (message_created only)
  min_confidence: minimum classification confidence 0..1
  priority: current conversation/ticket priority

Actions (applied in a fixed safe order):
  set_priority, set_team, auto_assign (route now), escalate (urgent + manager)
"""
import json
import logging

from sqlalchemy.orm import Session

from app.models.automation import AutomationRule
from app.models.conversation import Conversation
from app.models.ticket import Ticket
from app.services.assignment import PRIORITY_RANK, find_candidate, record_history

log = logging.getLogger("fty.automation")

TRIGGERS = ("message_created", "ticket_created")


def _load(rule: AutomationRule, field: str) -> dict:
    try:
        return json.loads(getattr(rule, field) or "{}")
    except Exception:
        return {}


def _matches(conditions: dict, ctx: dict) -> bool:
    if not conditions:
        return True
    if "channel" in conditions and ctx.get("channel") != conditions["channel"]:
        return False
    if "contains" in conditions and conditions["contains"].lower() not in (ctx.get("text") or "").lower():
        return False
    if "intent" in conditions and ctx.get("intent") != conditions["intent"]:
        return False
    if "min_confidence" in conditions and (ctx.get("confidence") or 0) < conditions["min_confidence"]:
        return False
    if "priority" in conditions and ctx.get("priority") != conditions["priority"]:
        return False
    return True


def _apply_to_conversation(db: Session, conv: Conversation, actions: dict, rule_name: str) -> list[str]:
    applied: list[str] = []
    by = f"automation: {rule_name}"

    if "set_priority" in actions and actions["set_priority"] in PRIORITY_RANK:
        new = actions["set_priority"]
        if PRIORITY_RANK[new] > PRIORITY_RANK.get(conv.priority or "normal", 1):
            record_history(db, conv, "priority_changed", assigned_by=by,
                           detail=f"{conv.priority} → {new}")
            conv.priority = new
            applied.append(f"priority→{new}")

    if "set_team" in actions and actions["set_team"] and conv.assigned_team != actions["set_team"]:
        record_history(db, conv, "triaged", assigned_by=by, to_team=actions["set_team"])
        conv.assigned_team = actions["set_team"]
        applied.append(f"team→{actions['set_team']}")

    if actions.get("escalate"):
        if conv.priority != "urgent":
            record_history(db, conv, "priority_changed", assigned_by=by,
                           detail=f"{conv.priority} → urgent", reason="escalation rule")
            conv.priority = "urgent"
        mgr = find_candidate(db, conv.assigned_team, urgent_bypass=True)
        if mgr and conv.assigned_agent_id != mgr.id:
            record_history(db, conv, "escalated", assigned_by=by, to_user_id=mgr.id,
                           reason="escalation rule → on-duty manager")
            conv.assigned_agent_id = mgr.id
            if conv.status in ("new", "open"):
                conv.status = "assigned"
        applied.append("escalated")

    if actions.get("auto_assign") and conv.assigned_agent_id is None:
        cand = find_candidate(db, conv.assigned_team)
        if cand:
            conv.assigned_agent_id = cand.id
            if conv.status in ("new", "open"):
                conv.status = "assigned"
            record_history(db, conv, "assigned", assigned_by=by, to_user_id=cand.id,
                           reason="automation rule")
            applied.append(f"assigned→{cand.name}")

    return applied


def evaluate_event_rules(db: Session, trigger: str, ctx: dict) -> list[str]:
    """Evaluate enabled rules for an event. Returns human-readable applied actions."""
    if trigger not in TRIGGERS:
        return []
    done: list[str] = []
    rules = db.query(AutomationRule).filter_by(trigger=trigger, enabled=True).order_by(AutomationRule.id).all()
    for rule in rules:
        if not _matches(_load(rule, "conditions"), ctx):
            continue
        actions = _load(rule, "actions")
        if not actions:
            continue
        conv = ctx.get("conversation")
        if isinstance(conv, Conversation):
            applied = _apply_to_conversation(db, conv, actions, rule.name)
            if applied:
                log.info("rule '%s' fired on conversation %s: %s", rule.name, conv.id, applied)
                done.append(f"{rule.name}: {', '.join(applied)}")
        elif isinstance(ctx.get("ticket"), Ticket) and "set_priority" in actions:
            t = ctx["ticket"]
            new = actions["set_priority"]
            if new in PRIORITY_RANK and PRIORITY_RANK[new] > PRIORITY_RANK.get(t.priority or "normal", 1):
                t.priority = new
                done.append(f"{rule.name}: ticket priority→{new}")
    if done:
        db.commit()
    return done
