"""
app/main.py
FastAPI application entry point. Wires up middleware, static files,
templates, and every router.

Run with:
    uvicorn app.main:app --reload
"""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.database import engine, Base
<<<<<<< HEAD
from app.routes import auth, pages, tasks, efforts, ai, users, projects, reports, notifications
=======
from app.routes import auth, pages, tasks, efforts, ai, users, initial_setup, projects, reports
>>>>>>> 0fdb0a36ec5ef364063bbd6f34b05c7466c9ef49

# Create tables on first run (safe / idempotent)
Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.app_name)

# Session middleware - signs cookies with SECRET_KEY
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)

# Static files (css/js/images)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Routers
app.include_router(pages.router)
app.include_router(auth.router)
app.include_router(tasks.router)
app.include_router(efforts.router)
app.include_router(ai.router)
app.include_router(users.router)
app.include_router(projects.router)
app.include_router(reports.router)
<<<<<<< HEAD
app.include_router(notifications.router)
=======
app.include_router(initial_setup.router)
>>>>>>> 0fdb0a36ec5ef364063bbd6f34b05c7466c9ef49


@app.get("/health")
def health():
    return {"status": "ok", "ai_enabled": bool(settings.gemini_api_key)}