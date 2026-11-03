import pytest


@pytest.fixture(autouse=True)
def _no_real_urls(monkeypatch):
    """Tests never use the real public address from .env (it would show up in failure output and in rendered links)."""
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.invalid")
