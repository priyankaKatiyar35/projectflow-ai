# Testing Guide

Comprehensive pytest test suite for Timesheet AI.

## Running Tests

### Install test dependencies
```bash
pip install pytest pytest-cov pytest-asyncio
```

### Run all tests
```bash
pytest
```

### Run with coverage report
```bash
pytest --cov=app --cov-report=html
```

Then open `htmlcov/index.html` to see line-by-line coverage.

### Run a specific file
```bash
pytest tests/test_auth.py
```

### Run a specific test
```bash
pytest tests/test_auth.py::TestLogin::test_login_with_valid_credentials_succeeds
```

### Verbose mode
```bash
pytest -v
```

### Stop at first failure
```bash
pytest -x
```

## Test Structure

```
tests/
├── conftest.py          # Shared fixtures (admin_user, employee_user, sample_project, etc.)
├── test_auth.py         # Login, logout, session, password hashing
├── test_users.py        # User CRUD with permission enforcement
├── test_projects.py     # Project + ProjectTask CRUD + permissions
├── test_notifications.py # Notification creation, read state, admin notifs
├── test_audit.py        # Audit log: append-only, filters, permissions
├── test_attachments.py  # File uploads: security, permissions, cascade delete
├── test_search.py       # Global search across entities
└── test_okrs.py         # Objectives & Key Results
```

## Test Isolation

- Each test gets a **fresh in-memory SQLite database** via the `client` fixture
- No test affects another
- No cleanup needed between runs
- Fast: full suite runs in seconds

## Fixtures Available

| Fixture | What it provides |
|---------|------------------|
| `client` | TestClient with isolated DB |
| `db` | Direct SQLAlchemy session |
| `admin_user` | Admin User object in DB |
| `employee_user` | Employee User object in DB |
| `second_employee` | Another employee (for permission tests) |
| `admin_client` | TestClient already logged in as admin |
| `employee_client` | TestClient already logged in as employee |
| `sample_project` | A project created by admin |
| `sample_task` | A task assigned to employee_user |

## Writing New Tests

Example:
```python
def test_admin_can_do_something(admin_client, sample_project):
    r = admin_client.post(f"/api/projects/{sample_project['id']}/something", json={...})
    assert r.status_code == 200
    assert r.json()["expected"] == "value"
```

Use the `client` fixture and call `/login` manually if you need a different user.