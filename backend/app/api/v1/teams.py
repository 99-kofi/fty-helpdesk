"""Teams & workers (spec §1, §6, §7): structure, availability, capacity."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.models.team import Team, TeamMember
from app.models.user import User
from app.services.assignment import active_count

router = APIRouter(tags=["teams"], dependencies=[Depends(get_current_user)])


class TeamIn(BaseModel):
    name: str
    description: str | None = None


class MemberIn(BaseModel):
    user_id: int


class MemberOut(BaseModel):
    user_id: int
    name: str
    availability: str
    active: int


class TeamOut(BaseModel):
    id: int
    name: str
    description: str | None = None
    members: list[MemberOut] = []


class AgentPatch(BaseModel):
    availability: str | None = None  # available|away|offline
    max_active: int | None = None
    team: str | None = None


def _team_out(db: Session, t: Team) -> TeamOut:
    members = (
        db.query(User).join(TeamMember, TeamMember.user_id == User.id)
        .filter(TeamMember.team_id == t.id).order_by(User.name).all()
    )
    return TeamOut(
        id=t.id, name=t.name, description=t.description,
        members=[MemberOut(user_id=u.id, name=u.name,
                           availability=u.availability or "available",
                           active=active_count(db, u.id)) for u in members],
    )


@router.get("/teams", response_model=list[TeamOut], dependencies=[Depends(require_role("admin"))])
def list_teams(db: Session = Depends(get_db)):
    return [_team_out(db, t) for t in db.query(Team).order_by(Team.name).all()]


@router.post("/teams", response_model=TeamOut, dependencies=[Depends(require_role("admin"))])
def create_team(data: TeamIn, db: Session = Depends(get_db)):
    if db.query(Team).filter_by(name=data.name).first():
        raise HTTPException(409, "Team already exists")
    t = Team(name=data.name, description=data.description)
    db.add(t)
    db.commit()
    db.refresh(t)
    return _team_out(db, t)


@router.post("/teams/{team_id}/members", dependencies=[Depends(require_role("admin"))])
def add_member(team_id: int, data: MemberIn, db: Session = Depends(get_db)):
    if not db.get(Team, team_id) or not db.get(User, data.user_id):
        raise HTTPException(404, "Team or user not found")
    if not db.query(TeamMember).filter_by(team_id=team_id, user_id=data.user_id).first():
        db.add(TeamMember(team_id=team_id, user_id=data.user_id))
        db.commit()
    return {"ok": True}


@router.delete("/teams/{team_id}/members/{user_id}", dependencies=[Depends(require_role("admin"))])
def remove_member(team_id: int, user_id: int, db: Session = Depends(get_db)):
    m = db.query(TeamMember).filter_by(team_id=team_id, user_id=user_id).first()
    if m:
        db.delete(m)
        db.commit()
    return {"ok": True}


@router.patch("/agents/{user_id}")
def update_agent(user_id: int, data: AgentPatch, db: Session = Depends(get_db),
                 me: User = Depends(get_current_user)):
    """Workers set their own availability; only the admin manages capacity & teams."""
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    is_self = me.id == user_id
    if not is_self and me.role != "admin":
        raise HTTPException(403, "Forbidden")
    if data.availability is not None:
        if data.availability not in ("available", "away", "offline"):
            raise HTTPException(422, "Bad availability")
        u.availability = data.availability
    if data.max_active is not None or data.team is not None:
        if me.role != "admin":
            raise HTTPException(403, "Only the admin changes capacity/teams")
        if data.max_active is not None:
            u.max_active = max(1, data.max_active)
        if data.team is not None:
            u.team = data.team
    db.commit()
    return {"ok": True}
