from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "history.db"
    monkeypatch.setattr(settings, "history_db_path", str(path))
    return path


@pytest.fixture
def anyio_backend():
    """Run async tests on asyncio."""
    return "asyncio"
