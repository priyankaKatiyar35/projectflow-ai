"""
tests/conftest.py
Shared pytest fixtures used across all test files.

Key fixtures:
  - `client`        : FastAPI TestClient with isolated in-memory DB
  - `db`            : SQLAlchemy session for direct DB access
  - `admin_user`    : Pre-created admin User
  - `employee_user` : Pre-created employee User
  - `admin_client`  : TestClient already logged in as admin
  - `employee_client`: TestClient already logged in as employee
"""
import os
import sys
import types
import pytest
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Stub out google.generativeai so AI features don't try to call the real API in tests
_g = types.ModuleType("google")
_g.generativeai = types.ModuleType("google.generativeai")
sys.modules.setdefault("google", _g)
sys.modules.setdefault("google.generativeai", _g.generativeai)

# Ensure we're running from project root
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Use a temp upload directory for tests
os.environ["GEMINI_API_KEY"] = ""

from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.main import app
from app.routes.auth import hash_password
from app.models import User


# ============================================================
# Database fixture - fresh in-memory SQLite per test
# ============================================================

@pytest.fixture
def db_engine():
    """Create a fresh in-memory SQLite engine for each test."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db(db_engine):
    """SQLAlchemy session for direct DB access in tests."""
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_engine, tmp_path, monkeypatch):
    """
    FastAPI TestClient with isolated DB and isolated upload directory.
    Each test gets a brand-new in-memory database.
    """
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)

    def override_get_db():
        try:
            session = TestingSessionLocal()
            yield session
        finally:
            session.close()

    # Use temp directory for uploads in tests
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    try:
        from app.routes import attachments
        monkeypatch.setattr(attachments, "UPLOAD_DIR", upload_dir)
    except (ImportError, AttributeError):
        pass

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


# ============================================================
# User fixtures
# ============================================================

@pytest.fixture
def admin_user(db):
    """Create and return an admin user."""
    user = User(
        full_name="Test Admin",
        email="admin@test.com",
        password_hash=hash_password("adminpass123"),
        role="admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def employee_user(db):
    """Create and return an employee user."""
    user = User(
        full_name="Test Employee",
        email="employee@test.com",
        password_hash=hash_password("emppass123"),
        role="employee",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def second_employee(db):
    """A second employee, useful for permission tests."""
    user = User(
        full_name="Second Employee",
        email="emp2@test.com",
        password_hash=hash_password("emp2pass123"),
        role="employee",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ============================================================
# Pre-logged-in client fixtures
# ============================================================

@pytest.fixture
def admin_client(client, admin_user):
    """A TestClient already logged in as admin."""
    response = client.post("/login", data={
        "email": admin_user.email,
        "password": "adminpass123",
    })
    assert response.status_code in (200, 303), f"Login failed: {response.status_code}"
    return client


@pytest.fixture
def employee_client(client, employee_user):
    """A TestClient already logged in as employee."""
    from fastapi.testclient import TestClient as TC
    emp_client = TC(app)
    # Need a separate client instance with the same dep override
    response = emp_client.post("/login", data={
        "email": employee_user.email,
        "password": "emppass123",
    })
    assert response.status_code in (200, 303)
    return emp_client


# ============================================================
# Domain fixtures
# ============================================================

@pytest.fixture
def sample_project(admin_client):
    """A sample project created by admin."""
    r = admin_client.post("/api/projects", json={
        "name": "Sample Project",
        "description": "A test project",
    })
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def sample_task(admin_client, sample_project, employee_user):
    """A sample task assigned to the employee."""
    r = admin_client.post(f"/api/projects/{sample_project['id']}/tasks", json={
        "task_description": "Sample task to test",
        "category": "Development",
        "milestone_phase": "Phase 1",
        "status": "in_progress",
        "planned_effort": 4.0,
        "assignee_ids": [employee_user.id],
    })
    assert r.status_code == 200, r.text
    return r.json()