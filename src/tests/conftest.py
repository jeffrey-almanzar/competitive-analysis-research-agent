import pytest

from app import db


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    """A fresh SQLite database wired into app.db for the duration of a test."""
    import app.models  # noqa: F401  (register tables)

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    db.engine.cache_clear()
    db._sessionmaker.cache_clear()
    db.Base.metadata.create_all(db.engine())
    yield
    db.engine().dispose()
    db.engine.cache_clear()
    db._sessionmaker.cache_clear()


@pytest.fixture(autouse=True)
def _no_external_services(monkeypatch):
    """Keep tests off the real page cache and Langfuse even when .env configures them."""
    from app.research import cache, telemetry

    monkeypatch.setenv("PAGE_CACHE_TTL_S", "0")
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    cache._client.cache_clear()
    telemetry._langfuse.cache_clear()
    yield
    for fn in (cache._client, telemetry._langfuse):
        if hasattr(fn, "cache_clear"):  # a test may have replaced it
            fn.cache_clear()
