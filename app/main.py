"""
app/main.py
FastAPI application entry point.
"""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.database import engine, Base
from app.routes import auth, pages, tasks, efforts, ai, users, projects, reports, notifications, comments, password_reset, search, okrs, audit, email_settings, attachments

Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.app_name)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)
app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(pages.router)
app.include_router(auth.router)
app.include_router(tasks.router)
app.include_router(efforts.router)
app.include_router(ai.router)
app.include_router(users.router)
app.include_router(projects.router)
app.include_router(reports.router)
app.include_router(notifications.router)
app.include_router(comments.router)
app.include_router(password_reset.router)
app.include_router(search.router)
app.include_router(okrs.router)
app.include_router(audit.router)
app.include_router(email_settings.router)
app.include_router(attachments.router)


@app.get("/health")
def health():
    return {"status": "ok", "ai_enabled": bool(settings.gemini_api_key)}