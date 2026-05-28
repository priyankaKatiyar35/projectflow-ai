"""
seed_demo.py
Populate the database with realistic demo data for screenshots / demos.

USAGE (from project root, with venv active):
    python seed_demo.py

This will:
  - Create 4 employees (with believable names)
  - Create 3 projects with descriptions
  - Create ~14 tasks spread across statuses, dates, and assignees
  - Create 2 OKRs with key results
  - Generate audit-log entries + notifications as a side effect

SAFE: it only ADDS data. It won't delete your existing admin or data.
Run it once. If you run it twice you'll get duplicates (fine for screenshots).

NOTE: This assumes you've already run `python -m app.setup` and have an admin.
"""
import sys
from datetime import date, timedelta, datetime

# Make sure we can import the app
sys.path.insert(0, ".")

from app.database import SessionLocal
from app.models import User, Project, ProjectTask, Objective, KeyResult
from app.routes.auth import hash_password


# ----------------------------------------------------------------------
# Sample data definitions
# ----------------------------------------------------------------------

EMPLOYEES = [
    ("Rahul Sharma",  "rahul.sharma@demo.com"),
    ("Anjali Verma",  "anjali.verma@demo.com"),
    ("Vikram Singh",  "vikram.singh@demo.com"),
    ("Priya Nair",    "priya.nair@demo.com"),
]

PROJECTS = [
    {
        "name": "Mobile App Redesign",
        "description": "Complete UX overhaul of the customer-facing mobile app, including new onboarding flow and dark mode.",
        "status": "in_progress",
    },
    {
        "name": "Q2 Infrastructure Migration",
        "description": "Migrate production workloads to the new cloud environment with zero downtime and improved monitoring.",
        "status": "in_progress",
    },
    {
        "name": "Customer Portal v2",
        "description": "Next-generation self-service portal with real-time support chat and billing management.",
        "status": "not_started",
    },
]

# Tasks per project: (description, category, phase, status, planned_offset_start, duration_days, effort, assignee_index)
# planned_offset_start is days from "today" (negative = past)
TASKS = {
    "Mobile App Redesign": [
        ("Design new onboarding screens",        "Design",       "Phase 1: Design",      "completed",   -25, 7,  16, 1),
        ("Implement dark mode across app",        "Development",  "Phase 2: Build",       "completed",   -18, 10, 24, 0),
        ("Build new navigation component",        "Development",  "Phase 2: Build",       "in_progress", -8,  12, 20, 0),
        ("Usability testing with 5 users",        "Testing",      "Phase 3: Validate",    "in_progress", -3,  8,  12, 3),
        ("Accessibility audit (WCAG 2.1)",         "Testing",      "Phase 3: Validate",    "not_started", 5,   6,  10, 3),
        ("Final design sign-off",                  "Design",       "Phase 3: Validate",    "not_started", 12,  3,  6,  1),
    ],
    "Q2 Infrastructure Migration": [
        ("Audit current infrastructure",          "Planning",     "Discovery",            "completed",   -30, 5,  12, 2),
        ("Set up new cloud environment",          "DevOps",       "Setup",                "completed",   -22, 8,  20, 2),
        ("Migrate database with zero downtime",   "DevOps",       "Migration",            "in_progress", -6,  10, 28, 2),
        ("Configure monitoring & alerting",        "DevOps",       "Migration",            "in_progress", -4,  7,  14, 0),
        ("Load testing on new environment",        "Testing",      "Validation",           "not_started", 6,   5,  16, 3),
        ("Cutover to production",                  "DevOps",       "Go-Live",              "not_started", 14,  2,  8,  2),
    ],
    "Customer Portal v2": [
        ("Gather requirements from stakeholders", "Planning",     "Discovery",            "not_started", 3,   6,  14, 1),
        ("Design portal information architecture", "Design",       "Discovery",            "not_started", 10,  8,  18, 1),
    ],
}

OKRS = [
    {
        "title": "Deliver a best-in-class mobile experience",
        "description": "Make the mobile app the primary channel our customers love to use.",
        "category": "Product",
        "period_label": "2026-Q2",
        "visibility": "company",
        "key_results": [
            ("Increase mobile app store rating", "numeric", "stars", 3.8, 4.6, 4.2),
            ("Reduce onboarding drop-off rate",  "percent", "%",     40,  15,  28),
            ("Ship dark mode to all users",      "boolean", None,    0,   1,   1),
        ],
    },
    {
        "title": "Achieve reliable, scalable infrastructure",
        "description": "Build infrastructure that scales smoothly and never wakes anyone at 3am.",
        "category": "Engineering",
        "period_label": "2026-Q2",
        "visibility": "company",
        "key_results": [
            ("Reach 99.9% uptime",                  "percent", "%",        99.2, 99.9, 99.6),
            ("Cut average API latency",             "numeric", "ms",       320,  150,  210),
            ("Complete production migration",        "milestone", None,     0,    4,    3),
        ],
    },
]


# ----------------------------------------------------------------------
# Seeding logic
# ----------------------------------------------------------------------

def run():
    db = SessionLocal()
    try:
        # Find the admin (creator of everything)
        admin = db.query(User).filter(User.role == "admin").first()
        if not admin:
            print("❌ No admin found. Run `python -m app.setup` first.")
            return

        print(f"✓ Using admin: {admin.full_name} ({admin.email})")

        # --- Create employees ---
        employees = []
        for name, email in EMPLOYEES:
            existing = db.query(User).filter(User.email == email).first()
            if existing:
                employees.append(existing)
                print(f"  - employee exists: {name}")
                continue
            u = User(
                full_name=name,
                email=email,
                password_hash=hash_password("demo1234"),
                role="employee",
            )
            db.add(u)
            db.flush()
            employees.append(u)
            print(f"  ✓ created employee: {name}")
        db.commit()

        # --- Create projects + tasks ---
        today = date.today()
        for proj_spec in PROJECTS:
            existing = db.query(Project).filter(Project.name == proj_spec["name"]).first()
            if existing:
                print(f"  - project exists: {proj_spec['name']}")
                project = existing
            else:
                project = Project(
                    name=proj_spec["name"],
                    description=proj_spec["description"],
                    status=proj_spec["status"],
                    created_by=admin.id,
                )
                db.add(project)
                db.flush()
                print(f"  ✓ created project: {proj_spec['name']}")

            # Tasks for this project
            for (desc, cat, phase, status, off_start, dur, effort, assignee_idx) in TASKS.get(proj_spec["name"], []):
                # Skip if a task with same description already exists in this project
                dupe = db.query(ProjectTask).filter(
                    ProjectTask.project_id == project.id,
                    ProjectTask.task_description == desc,
                ).first()
                if dupe:
                    continue

                p_start = today + timedelta(days=off_start)
                p_end = p_start + timedelta(days=dur)

                task = ProjectTask(
                    project_id=project.id,
                    task_description=desc,
                    category=cat,
                    milestone_phase=phase,
                    status=status,
                    planned_start_date=p_start,
                    planned_end_date=p_end,
                    planned_effort=effort,
                )

                # Fill actuals for completed / in-progress tasks (so Gantt shows two bars)
                if status == "completed":
                    task.actual_start_date = p_start + timedelta(days=1)
                    task.actual_end_date = p_end + timedelta(days=1)
                    task.actual_effort = round(effort * 1.1, 1)
                elif status == "in_progress":
                    task.actual_start_date = p_start + timedelta(days=1)
                    task.actual_effort = round(effort * 0.5, 1)

                db.add(task)
                db.flush()

                # Assign to an employee
                if 0 <= assignee_idx < len(employees):
                    task.assignees.append(employees[assignee_idx])

            db.commit()
            print(f"    ✓ tasks added to {proj_spec['name']}")

        # --- Create OKRs ---
        for okr_spec in OKRS:
            existing = db.query(Objective).filter(Objective.title == okr_spec["title"]).first()
            if existing:
                print(f"  - OKR exists: {okr_spec['title']}")
                continue

            obj = Objective(
                title=okr_spec["title"],
                description=okr_spec["description"],
                category=okr_spec["category"],
                period_label=okr_spec["period_label"],
                visibility=okr_spec["visibility"],
                owner_id=admin.id,
            )
            db.add(obj)
            db.flush()

            for sort_i, (kr_title, kr_type, unit, start_v, target_v, current_v) in enumerate(okr_spec["key_results"]):
                kr = KeyResult(
                    objective_id=obj.id,
                    title=kr_title,
                    kr_type=kr_type,
                    unit=unit,
                    start_value=start_v,
                    target_value=target_v,
                    current_value=current_v,
                    owner_id=admin.id,
                    sort_order=sort_i,
                )
                db.add(kr)
            db.commit()
            print(f"  ✓ created OKR: {okr_spec['title']}")

        # --- Summary ---
        print()
        print("=" * 55)
        print("  ✓ Demo data seeded successfully!")
        print("=" * 55)
        print(f"  Employees: {db.query(User).filter(User.role == 'employee').count()}")
        print(f"  Projects:  {db.query(Project).count()}")
        print(f"  Tasks:     {db.query(ProjectTask).count()}")
        print(f"  OKRs:      {db.query(Objective).count()}")
        print()
        print("  All demo employee passwords: demo1234")
        print()
        print("  Now refresh your browser and take screenshots of:")
        print("    /          (dashboard)")
        print("    /kanban    (drag-drop board)")
        print("    /gantt     (timeline)")
        print("    /calendar  (monthly view)")
        print("    /okrs      (goals)")
        print("    /audit     (audit log)")
        print("=" * 55)

    finally:
        db.close()


if __name__ == "__main__":
    run()