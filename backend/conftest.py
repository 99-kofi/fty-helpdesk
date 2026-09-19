import pytest

from app.core.config import settings


@pytest.fixture(scope="session", autouse=True)
def enable_local_admin_bootstrap_for_tests():
    """Keep predictable credentials confined to the test process."""
    original = settings.allow_default_admin_bootstrap
    settings.allow_default_admin_bootstrap = True
    yield
    settings.allow_default_admin_bootstrap = original
