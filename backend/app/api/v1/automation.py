"""Automation rules CRUD + manual SLA run (Phase 3)."""
import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.models.automation import AutomationRule

router = APIRouter(tags=["automation"], dependencies=[Depends(require_role("admin"))])

TRIGGERS = ("message_created", "ticket_created")


class RuleIn(BaseModel):
    name: str
    trigger: str
    conditions: dict = {}
    actions: dict = {}
    enabled: bool = True


class RulePatch(BaseModel):
    name: str | None = None
    conditions: dict | None = None
    actions: dict | None = None
    enabled: bool | None = None


def _out(r: AutomationRule) -> dict:
    return {"id": r.id, "name": r.name, "trigger": r.trigger,
            "conditions": json.loads(r.conditions or "{}"),
            "actions": json.loads(r.actions or "{}"), "enabled": r.enabled}


@router.get("/automation")
def list_rules(db: Session = Depends(get_db)):
    return [_out(r) for r in db.query(AutomationRule).order_by(AutomationRule.id).all()]


@router.post("/automation", dependencies=[Depends(require_role("admin", "manager"))])
def create_rule(data: RuleIn, db: Session = Depends(get_db)):
    if data.trigger not in TRIGGERS:
        raise HTTPException(422, f"trigger must be one of {TRIGGERS}")
    r = AutomationRule(name=data.name, trigger=data.trigger,
                       conditions=json.dumps(data.conditions), actions=json.dumps(data.actions),
                       enabled=data.enabled)
    db.add(r)
    db.commit()
    db.refresh(r)
    return _out(r)


@router.patch("/automation/{rule_id}", dependencies=[Depends(require_role("admin", "manager"))])
def patch_rule(rule_id: int, data: RulePatch, db: Session = Depends(get_db)):
    r = db.get(AutomationRule, rule_id)
    if not r:
        raise HTTPException(404, "Rule not found")
    if data.name is not None:
        r.name = data.name
    if data.conditions is not None:
        r.conditions = json.dumps(data.conditions)
    if data.actions is not None:
        r.actions = json.dumps(data.actions)
    if data.enabled is not None:
        r.enabled = data.enabled
    db.commit()
    return _out(r)


@router.delete("/automation/{rule_id}", dependencies=[Depends(require_role("admin", "manager"))])
def delete_rule(rule_id: int, db: Session = Depends(get_db)):
    r = db.get(AutomationRule, rule_id)
    if r:
        db.delete(r)
        db.commit()
    return {"ok": True}


@router.post("/automation/sla-check", dependencies=[Depends(require_role("admin", "manager"))])
def run_sla_now(db: Session = Depends(get_db)):
    """Trigger the SLA watchdog on demand (the scheduler also runs it)."""
    from app.services.sla import run_sla_check
    return run_sla_check(db)
