"""
app/check.py
Diagnostic script - checks every required file is in place and all
routes load correctly. Helps spot mistakes during setup.

Run with:
    python -m app.check
"""
import os
import sys
from pathlib import Path


ROOT = Path(__file__).parent.parent


REQUIRED_FILES = [
    "app/__init__.py",
    "app/main.py",
    "app/config.py",
    "app/database.py",
    "app/seed.py",
    "app/setup.py",
    "app/check.py",
    "app/migrate.py",
    "app/models/__init__.py",
    "app/models/user.py",
    "app/models/task.py",
    "app/models/effort.py",
    "app/models/project.py",
    "app/models/project_task.py",
    "app/routes/__init__.py",
    "app/routes/auth.py",
    "app/routes/pages.py",
    "app/routes/tasks.py",
    "app/routes/efforts.py",
    "app/routes/ai.py",
    "app/routes/users.py",
    "app/routes/projects.py",
    "app/routes/reports.py",
    "app/routes/notifications.py",
    "app/models/notification.py",
    "app/services/__init__.py",
    "app/services/analytics.py",
    "app/services/ai_service.py",
    "app/schemas/__init__.py",
    "app/schemas/schemas.py",
    "templates/base.html",
    "templates/login.html",
    "templates/dashboard.html",
    "templates/tasks.html",
    "templates/admin_users.html",
    "templates/projects.html",
    "templates/project_detail.html",
    "templates/reports.html",
    "static/css/style.css",
    "requirements.txt",
]


def run():
    print()
    print("=" * 60)
    print("  TIMESHEET AI — Diagnostic check")
    print("=" * 60)
    print()

    # 1) File check
    print("Step 1: Checking required files...")
    missing = []
    for rel in REQUIRED_FILES:
        full = ROOT / rel
        if not full.exists():
            missing.append(rel)
            print(f"  ✗ MISSING: {rel}")
        else:
            print(f"  ✓ {rel}")

    if missing:
        print()
        print(f"  ❌ {len(missing)} file(s) missing. Place them before continuing.")
        sys.exit(1)
    print()
    print("  ✓ All files present")
    print()

    # 2) Import check
    print("Step 2: Loading the application...")
    try:
        from app.main import app
        print("  ✓ App loaded successfully")
    except Exception as e:
        print(f"  ✗ Failed to load app: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    print()

    # 3) Route check
    print("Step 3: Checking routes are registered...")
    expected_routes = [
        "/login", "/", "/tasks", "/admin/users",
        "/projects", "/reports",
        "/api/tasks", "/api/users", "/api/efforts",
        "/api/projects",
        "/api/notifications", "/api/notifications/unread_count",
        "/api/reports/cmmi/preview", "/api/reports/cmmi/csv",
        "/api/reports/cmmi/xlsx", "/api/reports/cmmi/pdf",
        "/api/ai/chat", "/api/ai/workload", "/api/ai/burnout",
        "/health",
    ]
    registered = [r.path for r in app.routes if hasattr(r, "path")]
    missing_routes = []
    for r in expected_routes:
        if r in registered:
            print(f"  ✓ {r}")
        else:
            print(f"  ✗ MISSING: {r}")
            missing_routes.append(r)

    if missing_routes:
        print()
        print(f"  ❌ {len(missing_routes)} route(s) missing. Check main.py and the route files.")
        sys.exit(1)
    print()

    # 4) Database check
    print("Step 4: Checking database...")
    try:
        from app.database import SessionLocal
        from app.models import User, Task, Effort
        db = SessionLocal()
        users = db.query(User).count()
        tasks = db.query(Task).count()
        efforts = db.query(Effort).count()
        admins = db.query(User).filter(User.role == "admin").count()
        db.close()
        print(f"  ✓ Database accessible")
        print(f"    - Users:   {users} (admins: {admins})")
        print(f"    - Tasks:   {tasks}")
        print(f"    - Efforts: {efforts}")
        if users == 0:
            print()
            print("  ⚠️  No users yet. Run:  python -m app.setup")
        elif admins == 0:
            print()
            print("  ⚠️  No admin user! Run:  python -m app.setup")
    except Exception as e:
        print(f"  ✗ Database error: {e}")
        print()
        print("  ⚠️  Run:  python -m app.setup")

    print()
    print("=" * 60)
    print("  ✓ Everything looks good!")
    print("=" * 60)
    print()
    print("  Start the server with:")
    print("    uvicorn app.main:app --reload")
    print()


if __name__ == "__main__":
    run()