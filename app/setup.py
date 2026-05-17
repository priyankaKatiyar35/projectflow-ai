"""
app/setup.py
First-time setup for production use.

Wipes any demo data and creates ONE admin account from real credentials
you enter in the terminal. After this you log in and add real employees
through the Users page.

Run with:
    python -m app.setup
"""
import os
import sys
import getpass

from app.database import engine, SessionLocal, Base
from app.models import User
from app.routes.auth import hash_password


def prompt_non_empty(label: str) -> str:
    """Ask until the user types something non-blank."""
    while True:
        value = input(label).strip()
        if value:
            return value
        print("  → Cannot be empty, please try again.")


def prompt_email() -> str:
    while True:
        email = input("Admin email (e.g. you@company.com): ").strip().lower()
        if "@" in email and "." in email.split("@")[-1]:
            return email
        print("  → That doesn't look like a valid email. Try again.")


def prompt_password() -> str:
    while True:
        # getpass hides the password while typing
        pw = getpass.getpass("Admin password (min 6 chars, hidden as you type): ")
        if len(pw) < 6:
            print("  → Too short — needs at least 6 characters.")
            continue
        pw2 = getpass.getpass("Confirm password: ")
        if pw != pw2:
            print("  → Passwords don't match. Try again.")
            continue
        return pw


def run():
    print()
    print("=" * 60)
    print("  TIMESHEET AI — First-time setup")
    print("=" * 60)
    print()
    print("  This will:")
    print("    1. Reset the database (deletes any existing data)")
    print("    2. Create one admin account with your real credentials")
    print()
    print("  After this, log in and add your team via the Users page.")
    print()

    confirm = input("Continue? (yes/no): ").strip().lower()
    if confirm not in ("yes", "y"):
        print("Cancelled.")
        sys.exit(0)

    print()
    print("--- Admin account details ---")
    full_name = prompt_non_empty("Your full name: ")
    email     = prompt_email()
    password  = prompt_password()
    company   = input("Company name (optional, just for display): ").strip() or "My Company"

    print()
    print("Creating database...")

    # Wipe and recreate all tables
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        admin = User(
            full_name=full_name,
            email=email,
            password_hash=hash_password(password),
            role="admin",
        )
        db.add(admin)
        db.commit()
    finally:
        db.close()

    print()
    print("=" * 60)
    print("  ✓ Setup complete!")
    print("=" * 60)
    print(f"  Company:  {company}")
    print(f"  Admin:    {full_name}")
    print(f"  Email:    {email}")
    print()
    print("  Next steps:")
    print("    1. Start the server:   uvicorn app.main:app --reload")
    print("    2. Open browser:       http://localhost:8000")
    print("    3. Log in with the email and password you just set")
    print("    4. Click 'Users' in the sidebar to add your team members")
    print()


if __name__ == "__main__":
    run()
