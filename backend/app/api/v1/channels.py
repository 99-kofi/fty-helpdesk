"""Channel connections (Phase 2): which channels are live. Tokens never leave the backend."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.core.vault import seal
from app.models.channel import ChannelConnection

router = APIRouter(tags=["channels"], dependencies=[Depends(get_current_user)])

CHANNELS = ("instagram", "whatsapp", "facebook", "email", "web")


class ChannelStatus(BaseModel):
    channel: str
    connected: bool
    has_token: bool
    oauth_ready: bool = False  # Meta Login available (META_APP_ID set)


class ChannelUpsert(BaseModel):
    access_token: str | None = None
    config: str | None = None  # JSON string, e.g. {"phone_number_id": "..."}


@router.get("/channels", response_model=list[ChannelStatus],
              dependencies=[Depends(require_role("admin"))])
def list_channels(db: Session = Depends(get_db)):
    rows = {r.channel: r for r in db.query(ChannelConnection).all()}
    meta_ready = bool(settings.meta_app_id)
    return [
        ChannelStatus(
            channel=c,
            connected=c in rows,
            has_token=bool(rows[c].access_token) if c in rows else False,
            oauth_ready=meta_ready if c in ("instagram", "facebook") else True,
        )
        for c in CHANNELS
    ]


@router.put("/channels/{channel}", dependencies=[Depends(require_role("admin"))])
def upsert_channel(channel: str, data: ChannelUpsert, db: Session = Depends(get_db)):
    if channel not in CHANNELS:
        return {"ok": False, "error": "unknown channel"}
    row = db.query(ChannelConnection).filter_by(channel=channel).first()
    if not row:
        row = ChannelConnection(channel=channel)
        db.add(row)
    if data.access_token is not None:
        row.access_token = seal(data.access_token) if data.access_token else None
    if data.config is not None:
        row.config = data.config
    db.commit()
    return {"ok": True, "channel": channel, "connected": True}
