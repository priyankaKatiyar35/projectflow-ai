"""
app/routes/initial_setup.py
ONE-TIME ADMIN SETUP via web URL.
Visit /setup-first-admin?token=SETUP_NOW_PRIYANKA_2026 ONCE to create your admin.
Delete this file after using it for security.
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from fastapi import Depends

from app.database import get_db, engine, Base
from app.models import User
from app.routes.auth import hash_password


router = APIRouter()

# Change this token to anything secret — must match in the URL
SETUP_TOKEN = "SETUP_NOW_PRIYANKA_2026"


@router.get("/setup-first-admin", response_class=HTMLResponse)
def setup_first_admin(token: str = "", email: str = "", password: str = "", name: str = "", db: Session = Depends(get_db)):
    # Make sure tables exist
    Base.metadata.create_all(bind=engine)

    if token != SETUP_TOKEN:
        return HTMLResponse(
            """
            <html><body style="font-family: sans-serif; padding: 40px; max-width: 600px; margin: auto;">
            <h2>🔐 First Admin Setup</h2>
            <p>This page creates your first admin account. Use only once.</p>
            <form>
              <p><label>Token:<br><input name="token" required style="width:100%;padding:8px;"></label></p>
              <p><label>Full Name:<br><input name="name" required style="width:100%;padding:8px;"></label></p>
              <p><label>Email:<br><input name="email" type="email" required style="width:100%;padding:8px;"></label></p>
              <p><label>Password (min 6 chars):<br><input name="password" type="password" required minlength="6" style="width:100%;padding:8px;"></label></p>
              <button type="submit" style="padding:10px 20px;background:#667eea;color:white;border:none;border-radius:6px;cursor:pointer;">Create Admin</button>
            </form>
            </body></html>
            """
        )

    if not email or not password or not name:
        return HTMLResponse("<p>Missing fields. <a href='/setup-first-admin'>Go back</a></p>", status_code=400)

    if len(password) < 6:
        return HTMLResponse("<p>Password too short (min 6 chars). <a href='/setup-first-admin'>Go back</a></p>", status_code=400)

    # Check if any admin already exists
    existing_admin = db.query(User).filter(User.role == "admin").first()
    if existing_admin:
        return HTMLResponse(
            f"<p>❌ An admin already exists ({existing_admin.email}). For security, this setup link only works ONCE. <br>If you forgot your password, contact the developer.</p>",
            status_code=403,
        )

    user = User(
        full_name=name,
        email=email.lower().strip(),
        password_hash=hash_password(password),
        role="admin",
    )
    db.add(user)
    db.commit()

    return HTMLResponse(
        f"""
        <html><body style="font-family: sans-serif; padding: 40px; max-width: 600px; margin: auto; text-align:center;">
        <h2>✅ Admin created successfully!</h2>
        <p><b>Name:</b> {name}<br><b>Email:</b> {email}</p>
        <p><a href='/login' style="display:inline-block;padding:10px 24px;background:#667eea;color:white;text-decoration:none;border-radius:6px;">Login now →</a></p>
        <p style="color:#999;font-size:13px;margin-top:30px;">⚠️ For security, you should delete app/routes/initial_setup.py from GitHub now.</p>
        </body></html>
        """
    )
