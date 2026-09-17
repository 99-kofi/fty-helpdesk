"""Encrypted token storage (Phase 2): Fernet vault for channel credentials.

Tokens are sealed before hitting the database and opened only in memory
at send time. Plaintext legacy rows still read (then re-seal on next save).
"""
import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

log = logging.getLogger("fty.vault")
PREFIX = "enc:"


def _fernet() -> Fernet:
    raw = settings.token_encryption_key or settings.jwt_secret
    key = base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest())
    return Fernet(key)


def seal(plaintext: str) -> str:
    return PREFIX + _fernet().encrypt(plaintext.encode()).decode()


def open_secret(stored: str | None) -> str:
    if not stored:
        return ""
    if not stored.startswith(PREFIX):
        return stored  # legacy plaintext row
    try:
        return _fernet().decrypt(stored[len(PREFIX):].encode()).decode()
    except InvalidToken:
        log.error("token vault: undecryptable value (wrong TOKEN_ENCRYPTION_KEY?)")
        return ""
