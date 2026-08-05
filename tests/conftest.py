"""
Shared pytest fixtures.

Two rules this suite holds itself to:

1. No network, no API key. Every test runs on the offline engines, so CI is
   free, deterministic and works on a train. The LLM seam is tested by
   substituting a fake provider, not by calling a real one.
2. No shared state. Each test session gets its own SQLite file and its own
   storage directory in tmp, both thrown away afterwards - a test suite that
   writes into the developer's real database is a test suite people stop
   running.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# These must be set BEFORE backend.app.config is imported, because Settings is
# cached with lru_cache on first use.
_TMP = Path(tempfile.mkdtemp(prefix="interviewace-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["STORAGE_DIR"] = str(_TMP / "storage")
os.environ["SECRET_KEY"] = "test-secret-key-not-used-anywhere-real"
os.environ["LLM_PROVIDER"] = "offline"
os.environ["STT_PROVIDER"] = "none"
os.environ["ADMIN_EMAIL"] = "admin@interviewace.ai"

from fastapi.testclient import TestClient  # noqa: E402

from backend.app.database import Base, engine  # noqa: E402
from backend.app.main import app  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session", autouse=True)
def _create_schema():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def sample_resume_bytes() -> bytes:
    return (FIXTURES / "sample_resume.txt").read_bytes()


@pytest.fixture
def sample_resume_text() -> str:
    return (FIXTURES / "sample_resume.txt").read_text(encoding="utf-8")


_email_counter = iter(range(1, 100_000))


@pytest.fixture
def auth(client: TestClient):
    """Register a fresh user and return (headers, user_dict).

    A new email per test keeps tests independent of execution order.
    """
    email = f"candidate{next(_email_counter)}@example.com"
    response = client.post("/register", json={
        "email": email,
        "password": "TestPass123",
        "full_name": "Test Candidate",
        "target_role": "full-stack-developer",
        "experience_level": "fresher",
    })
    assert response.status_code == 201, response.text
    body = response.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body["user"]
