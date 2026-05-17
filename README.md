# Timesheet AI — Modern Project Planning & Time Tracking

A Python rebuild of your PHP timesheet system, with AI-powered features companies actually demand in 2026.

## Stack
- **Backend:** FastAPI (Python 3.10+) + SQLAlchemy + SQLite
- **Frontend:** Jinja2 templates + Tailwind CSS (CDN) + Alpine.js + Chart.js
- **AI:** Google Gemini (free tier — get a key at https://aistudio.google.com/app/apikey)
- **Auth:** Session-based, password hashing with bcrypt

## Features

### Core (rebuilt from your PHP app)
- Admin & employee dashboards with role-based views
- Task & sub-task management with status, deadline, priority
- Effort/time logging per task
- Employee progress & activity charts
- Online presence tracking

### AI Features
1. **AI Chat** — ask questions about your data in plain English ("who's overloaded this week?")
2. **Auto reports** — one-click daily standup or weekly status summaries
3. **Natural language task entry** — type "Design login page for Priya by Friday" → structured task
4. **Workload balancer** — detects overload, suggests redistribution
5. **Burnout detector** — flags unusual hour patterns
6. **Smart deadline predictor** — estimates if a task will be late, based on past effort
7. **Effort forecasting** — predicts hours needed based on similar tasks

## Quick start

```bash
# 1. Create a virtual env
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Get a free Gemini API key
#    https://aistudio.google.com/app/apikey

# 4. Create a .env file (copy from .env.example)
cp .env.example .env
#    Then edit .env and paste your GEMINI_API_KEY

# 5. Seed the database with demo data (creates admin + sample employees + tasks)
python -m app.seed

# 6. Run the app
uvicorn app.main:app --reload

# 7. Open http://localhost:8000
#    Login as admin:    admin@demo.com  / admin123
#    Login as employee: rahul@demo.com  / employee123
```

## Project structure

```
timesheet_ai/
├── app/
│   ├── main.py              # FastAPI entry point
│   ├── config.py            # Settings & env vars
│   ├── database.py          # DB connection & session
│   ├── seed.py              # Demo data seeder
│   ├── models/              # SQLAlchemy models (User, Task, Effort)
│   ├── schemas/             # Pydantic request/response schemas
│   ├── routes/              # API + page routes
│   │   ├── pages.py         # HTML pages (dashboard, login, tasks)
│   │   ├── auth.py          # Login / logout
│   │   ├── tasks.py         # Task CRUD
│   │   ├── efforts.py       # Time-log CRUD
│   │   └── ai.py            # All AI endpoints
│   └── services/
│       ├── analytics.py     # Charts data & stat aggregations
│       └── ai_service.py    # Gemini wrapper + prompt templates
├── templates/               # Jinja2 HTML
│   ├── base.html
│   ├── dashboard.html       # The redesigned dashboard
│   ├── tasks.html
│   ├── login.html
│   └── partials/
├── static/
│   ├── css/style.css        # Glassmorphism / modern theme
│   └── js/app.js            # Frontend logic (Alpine + Chart.js)
├── data/                    # SQLite DB lives here
├── .env.example
├── requirements.txt
└── README.md
```

## How AI features work without an API key
If `GEMINI_API_KEY` is empty, the app falls back to rule-based heuristics for:
- Workload balancing (statistical detection of overload)
- Burnout detection (hour thresholds)
- Deadline prediction (linear extrapolation from effort)

AI chat & report generation require the key.
