from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import create_token, hash_password, verify_password
from app.models.user import User
from app.schemas import LoginIn, TokenOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/seed-admin")
def seed_admin(db: Session = Depends(get_db)):
    """Dev-only bootstrap: creates admin@fty.local / admin123 if missing."""
    if db.query(User).filter_by(email="admin@fty.local").first():
        return {"ok": True, "exists": True}
    u = User(name="Admin", email="admin@fty.local", password_hash=hash_password("admin123"), role="admin")
    db.add(u)
    db.commit()
    return {"ok": True, "email": "admin@fty.local", "password": "admin123"}


@router.post("/login", response_model=TokenOut)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter_by(email=form.username).first()
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    return TokenOut(access_token=create_token(str(user.id), user.role))


@router.get("/me", response_model=UserOut)
def me(db: Session = Depends(get_db), token_user: User = Depends(__import__("app.core.deps", fromlist=["get_current_user"]).get_current_user)):
    return token_user
