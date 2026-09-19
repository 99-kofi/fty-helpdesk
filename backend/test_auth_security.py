from fastapi.testclient import TestClient

from app.api.v1.auth import seed_admin
from app.core.config import settings
from app.main import app


def test_default_admin_bootstrap_is_disabled_without_explicit_setting():
    original = settings.allow_default_admin_bootstrap
    settings.allow_default_admin_bootstrap = False
    try:
        assert TestClient(app).post("/api/v1/auth/seed-admin").status_code == 404
    finally:
        settings.allow_default_admin_bootstrap = original
