"""User accounts (admin): create worker logins, reset passwords, change roles.

Workers log in on the same Login page with the credentials the admin sets here.
Day-to-day availability stays self-service via PATCH /agents/{id}.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.core.security import hash_password
from app.models.user import User
from app.schemas import UserOut

router = APIRouter(tags=["users"], dependencies=[Depends(get_current_user)])
ADMIN = Depends(require_role("admin"))

ROLES = ("admin", "manager", "agent")


class UserCreate(BaseModel):
    name: str
    email: str  # plain str: internal domains like .local are valid here
    password: str
    role: str = "agent"
    team: str | None = None


class UserPatch(BaseModel):
    name: str | None = None
    role: str | None = None
    team: str | None = None
    availability: str | None = None
    max_active: int | None = None
    password: str | None = None


@router.post("/users", response_model=UserOut, dependencies=[ADMIN])
def create_user(data: UserCreate, db: Session = Depends(get_db)):
    if data.role not in ROLES:
        raise HTTPException(422, f"role must be one of {ROLES}")
    if len(data.password) < 6:
        raise HTTPException(422, "password must be at least 6 characters")
    if db.query(User).filter_by(email=data.email).first():
        raise HTTPException(409, "Email already in use")
    u = User(name=data.name.strip(), email=data.email, password_hash=hash_password(data.password),
             role=data.role, team=data.team)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@router.patch("/users/{user_id}", response_model=UserOut, dependencies=[ADMIN])
def patch_user(user_id: int, data: UserPatch, db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    if data.role is not None:
        if data.role not in ROLES:
            raise HTTPException(422, f"role must be one of {ROLES}")
        u.role = data.role
    if data.name is not None:
        u.name = data.name.strip()
    if data.team is not None:
        u.team = data.team
    if data.availability is not None:
        if data.availability not in ("available", "away", "offline"):
            raise HTTPException(422, "Bad availability")
        u.availability = data.availability
    if data.max_active is not None:
        u.max_active = max(1, data.max_active)
    if data.password is not None:
        if len(data.password) < 6:
            raise HTTPException(422, "password must be at least 6 characters")
        u.password_hash = hash_password(data.password)
    db.commit()
    db.refresh(u)
    return u
