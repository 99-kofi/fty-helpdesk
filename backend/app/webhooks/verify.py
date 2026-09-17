"""Webhook signature helpers — never trust unverified payloads."""
import hashlib
import hmac
from app.core.config import settings


def verify_meta_signature(payload: bytes, signature: str | None) -> bool:
    if not settings.meta_app_secret or settings.meta_app_secret == "change-me":
        return True  # dev bypass; enforce in prod
    if not signature:
        return False
    expected = "sha256=" + hmac.new(settings.meta_app_secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
