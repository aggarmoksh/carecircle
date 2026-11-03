import pytest


@pytest.fixture(autouse=True)
def _no_real_urls(monkeypatch):
    """Tests never use the real public address from .env (it would show up in failure output and in rendered links)."""
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.invalid")


@pytest.fixture(autouse=True)
def _no_real_model_calls(monkeypatch, request):
    """Unit tests never reach the model API: a test that needs a model answer must stub llm.spark_json itself. (Live evals live in tests/eval_*.py, which are scripts, not tests.)"""
    from app import llm
    if "live" in request.keywords:
        return
    monkeypatch.setattr(llm, "key", lambda: (_ for _ in ()).throw(AssertionError("a unit test tried to call the model API; stub llm.spark_json")))
