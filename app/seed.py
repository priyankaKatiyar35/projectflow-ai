"""
app/seed.py
Creates the SQLite DB and fills it with realistic demo data so you can
test every feature immediately. Run with:

    python -m app.seed
"""
import random
from datetime import datetime, date, timedelta

from app.database import engine, SessionLocal, Base
from app.models import User, Task, Effort
from app.routes.auth import hash_password


def run():
    print("Creating tables...")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()

    # ---- Users ----
    admin = User(
        full_name="Admin User",
        email="admin@demo.com",
        password_hash=hash_password("admin123"),
        role="admin",
        last_online=datetime.utcnow(),
    )
    employees = [
        User(full_name="Rahul Sharma",  email="rahul@demo.com",  password_hash=hash_password("employee123"), role="employee", last_online=datetime.utcnow() - timedelta(minutes=3)),
        User(full_name="Priya Patel",   email="priya@demo.com",  password_hash=hash_password("employee123"), role="employee", last_online=datetime.utcnow() - timedelta(hours=1)),
        User(full_name="Ankit Verma",   email="ankit@demo.com",  password_hash=hash_password("employee123"), role="employee", last_online=datetime.utcnow() - timedelta(hours=4)),
        User(full_name="Sneha Reddy",   email="sneha@demo.com",  password_hash=hash_password("employee123"), role="employee", last_online=datetime.utcnow() - timedelta(days=1)),
        User(full_name="Vikram Singh",  email="vikram@demo.com", password_hash=hash_password("employee123"), role="employee", last_online=datetime.utcnow() - timedelta(minutes=12)),
    ]
    db.add(admin)
    db.add_all(employees)
    db.commit()

    # ---- Tasks ----
    categories_subtasks = [
        ("Frontend", ["Build login page", "Dashboard redesign", "Profile settings UI", "Mobile responsive fixes"]),
        ("Backend",  ["Auth API", "Reports export endpoint", "Database optimisation", "Webhook integration"]),
        ("Design",   ["Logo refresh", "Style guide v2", "Email templates"]),
        ("QA",       ["Regression suite", "Load testing"]),
        ("DevOps",   ["CI pipeline", "Production deploy script"]),
    ]
    statuses    = ["pending", "in_progress", "completed"]
    priorities  = ["low", "medium", "high", "urgent"]

    tasks_created = []
    for emp in employees:
        n = random.randint(4, 8)
        for _ in range(n):
            cat, subs = random.choice(categories_subtasks)
            sub = random.choice(subs)
            status = random.choices(statuses, weights=[2, 3, 2])[0]
            # Spread deadlines: some past, some future, some none
            roll = random.random()
            if roll < 0.15:
                deadline = None
            elif roll < 0.35:
                deadline = datetime.utcnow() - timedelta(days=random.randint(1, 5))  # overdue
            else:
                deadline = datetime.utcnow() + timedelta(days=random.randint(1, 14))
            t = Task(
                task=cat,
                sub_task=sub,
                description=f"Auto-generated demo task for {cat}",
                status=status,
                priority=random.choice(priorities),
                deadline=deadline,
                estimated_hours=random.choice([2, 4, 6, 8, 12, 16]),
                assignee_id=emp.id,
            )
            db.add(t)
            tasks_created.append(t)
    db.commit()

    # ---- Efforts (random hours over last 10 days) ----
    for t in tasks_created:
        n_logs = random.randint(0, 5)
        for _ in range(n_logs):
            day_offset = random.randint(0, 9)
            mins = random.choice([30, 45, 60, 90, 120, 150, 180])
            db.add(Effort(
                task_id=t.id,
                user_id=t.assignee_id,
                minutes=mins,
                log_date=date.today() - timedelta(days=day_offset),
                notes=random.choice([None, "Made progress", "Blocked on review", "Pair session"]),
            ))
    db.commit()

    # Print summary
    print(f"✓ Seeded {db.query(User).count()} users (1 admin + {len(employees)} employees)")
    print(f"✓ Seeded {db.query(Task).count()} tasks")
    print(f"✓ Seeded {db.query(Effort).count()} effort logs")
    print()
    print("Login credentials:")
    print("  Admin:    admin@demo.com  /  admin123")
    print("  Employee: rahul@demo.com  /  employee123")
    print()
    db.close()


if __name__ == "__main__":
    run()
