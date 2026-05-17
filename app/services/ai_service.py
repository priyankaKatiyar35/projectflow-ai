"""
app/services/ai_service.py
The brain of the app. Wraps Google Gemini for the 6 AI features.

If GEMINI_API_KEY is empty, all features fall back to deterministic
rule-based heuristics so the app still works offline.

Features
--------
1. chat_with_data(question, context)        -> answers questions about your tasks/people
2. generate_report(scope, data)              -> daily / weekly standup
3. parse_natural_task(text, users)           -> "Design login for Priya by Fri" -> structured task
4. detect_workload_issues(activity, tasks)   -> overload + suggestions
5. detect_burnout(daily_hours_per_user)      -> flags concerning patterns
6. predict_deadline_risk(task, efforts)      -> will-be-late probability
7. forecast_effort(new_task, history)        -> hours needed estimate
"""
from __future__ import annotations
import json
import re
import statistics
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Any

from app.config import settings


# ---------- Gemini client (lazy + optional) ----------
_genai_model = None


def _get_model():
    """Returns a Gemini model instance, or None if no key configured."""
    global _genai_model
    if _genai_model is not None:
        return _genai_model
    if not settings.gemini_api_key:
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=settings.gemini_api_key)
        _genai_model = genai.GenerativeModel(settings.gemini_model)
        return _genai_model
    except Exception as e:
        print(f"[ai_service] Gemini init failed: {e}")
        return None


def _ask_gemini(prompt: str, system: Optional[str] = None) -> Optional[str]:
    """Single-shot prompt to Gemini. Returns text or None on failure."""
    model = _get_model()
    if model is None:
        return None
    try:
        full = f"{system}\n\n---\n\n{prompt}" if system else prompt
        resp = model.generate_content(full)
        return (resp.text or "").strip()
    except Exception as e:
        print(f"[ai_service] Gemini call failed: {e}")
        return None


# ============================================================
# 1. AI chat with your data
# ============================================================

def chat_with_data(question: str, context: Dict[str, Any]) -> str:
    """Answers a free-form question using the live dashboard data as context."""
    if _get_model() is None:
        # Rule-based fallback - keyword matching
        q = question.lower()
        if "overdue" in q:
            return f"There are {context.get('overdue', 0)} overdue tasks right now."
        if "complete" in q:
            return f"{context.get('completed', 0)} tasks have been completed."
        if "who" in q and ("free" in q or "available" in q):
            activity = context.get("employee_activity", {})
            if activity:
                least_busy = min(activity, key=activity.get)
                return f"{least_busy} has logged the fewest hours ({activity[least_busy]}h) — likely most available."
        return "AI chat needs a Gemini API key. Add GEMINI_API_KEY to your .env file to enable smart answers."

    system = (
        "You are a helpful project management assistant. "
        "Answer the user's question using ONLY the JSON context provided. "
        "Be concise (2-4 sentences max). If the data doesn't contain the answer, say so honestly. "
        "Use specific names and numbers from the context."
    )
    prompt = f"CONTEXT:\n{json.dumps(context, default=str, indent=2)}\n\nQUESTION: {question}"
    reply = _ask_gemini(prompt, system)
    return reply or "I couldn't generate a response. Please try again."


# ============================================================
# 2. Auto reports / standups
# ============================================================

def generate_report(scope: str, data: Dict[str, Any]) -> str:
    """scope: 'daily_standup' | 'weekly_summary' | 'employee_review'"""
    if _get_model() is None:
        # Simple template fallback
        if scope == "daily_standup":
            return (
                f"Daily Standup ({date.today()})\n"
                f"- Completed: {data.get('completed', 0)} tasks\n"
                f"- In progress: {data.get('in_progress', 0)} tasks\n"
                f"- Pending: {data.get('pending', 0)} tasks\n"
                f"- Overdue: {data.get('overdue', 0)} tasks need attention\n"
            )
        return f"Report ({scope}):\n{json.dumps(data, default=str, indent=2)}"

    templates = {
        "daily_standup": (
            "Write a daily standup report in markdown. Sections: "
            "1) Progress yesterday, 2) Today's focus, 3) Blockers/risks. "
            "Use bullet points. Be punchy and practical — max 12 lines total."
        ),
        "weekly_summary": (
            "Write a weekly project summary in markdown. Sections: "
            "1) Headline numbers, 2) Wins, 3) Concerns, 4) Recommendations for next week. "
            "Use bullet points. Max 20 lines."
        ),
        "employee_review": (
            "Write a brief, balanced performance snapshot for this employee. "
            "Cover effort logged, completion rate, and one constructive suggestion. "
            "5-8 sentences."
        ),
    }
    system = templates.get(scope, "Write a clear project status report.")
    prompt = f"DATA:\n{json.dumps(data, default=str, indent=2)}"
    reply = _ask_gemini(prompt, system)
    return reply or "Report generation failed. Please try again."


# ============================================================
# 3. Natural-language task entry
# ============================================================

def parse_natural_task(text: str, users: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Parses 'Design login page for Priya by Friday, high priority, ~6h' into structured fields."""
    result: Dict[str, Any] = {
        "task": "General",
        "sub_task": text,
        "priority": "medium",
        "estimated_hours": 0.0,
        "deadline": None,
        "assignee_name": None,
        "raw_input": text,
    }

    # Always try to match a known user name (works without AI too)
    lowered = text.lower()
    for u in users:
        if u["full_name"].split()[0].lower() in lowered or u["full_name"].lower() in lowered:
            result["assignee_name"] = u["full_name"]
            break

    if _get_model() is None:
        # Rule-based fallback
        if any(w in lowered for w in ["urgent", "asap", "critical"]):
            result["priority"] = "urgent"
        elif "high" in lowered:
            result["priority"] = "high"
        elif "low" in lowered:
            result["priority"] = "low"

        # Hours: "6h", "~6 hours", "6 hrs"
        m = re.search(r"~?\s*(\d+(?:\.\d+)?)\s*(?:h|hr|hrs|hour|hours)", lowered)
        if m:
            result["estimated_hours"] = float(m.group(1))

        # Cheap deadline: today/tomorrow/friday etc.
        weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        for i, w in enumerate(weekdays):
            if w in lowered:
                today = date.today()
                days_ahead = (i - today.weekday()) % 7 or 7
                result["deadline"] = datetime.combine(today + timedelta(days=days_ahead), datetime.min.time())
                break
        if "tomorrow" in lowered:
            result["deadline"] = datetime.combine(date.today() + timedelta(days=1), datetime.min.time())
        if "today" in lowered:
            result["deadline"] = datetime.combine(date.today(), datetime.max.time())
        return result

    # AI path - structured JSON extraction
    user_names = [u["full_name"] for u in users]
    system = (
        "Extract structured task data from natural language. "
        f"Return ONLY a JSON object with these keys: "
        f'{{"task": str, "sub_task": str, "priority": "low"|"medium"|"high"|"urgent", '
        f'"estimated_hours": float, "deadline": "YYYY-MM-DD" or null, "assignee_name": str or null}}. '
        f"Today is {date.today().isoformat()}. "
        f"Valid assignee names: {user_names}. "
        f"`task` is a short category (e.g. 'Frontend', 'Backend', 'Design'). "
        f"`sub_task` is the specific work item. "
        "No markdown, no commentary — just the JSON."
    )
    reply = _ask_gemini(text, system)
    if reply:
        # Strip markdown code fences if present
        clean = re.sub(r"```(?:json)?", "", reply).strip().strip("`")
        try:
            parsed = json.loads(clean)
            for k in ("task", "sub_task", "priority", "estimated_hours", "assignee_name"):
                if k in parsed and parsed[k] is not None:
                    result[k] = parsed[k]
            if parsed.get("deadline"):
                try:
                    result["deadline"] = datetime.fromisoformat(parsed["deadline"])
                except ValueError:
                    pass
        except json.JSONDecodeError:
            pass
    return result


# ============================================================
# 4. Workload balancer
# ============================================================

def detect_workload_issues(employee_activity: Dict[str, float]) -> List[Dict[str, str]]:
    """Returns a list of insight dicts: {type, title, body}."""
    insights: List[Dict[str, str]] = []
    if not employee_activity:
        return insights

    values = list(employee_activity.values())
    avg = statistics.mean(values) if values else 0
    if avg == 0:
        return insights

    overloaded, underused = [], []
    for name, hours in employee_activity.items():
        if hours > avg * settings.overload_threshold:
            overloaded.append((name, hours))
        elif hours < avg * 0.5 and hours >= 0:
            underused.append((name, hours))

    for name, hours in overloaded:
        body = f"{name} has logged {hours:.1f}h vs team average {avg:.1f}h. Consider redistributing work."
        if underused:
            free_name = underused[0][0]
            body += f" {free_name} has capacity ({underused[0][1]:.1f}h logged)."
        insights.append({"type": "warning", "title": "Overload detected", "body": body})

    if not overloaded and not underused:
        insights.append({
            "type": "success",
            "title": "Workload is balanced",
            "body": f"Team is averaging {avg:.1f}h per person — distribution looks healthy."
        })
    return insights


# ============================================================
# 5. Burnout detector
# ============================================================

def detect_burnout(daily_hours_per_user: Dict[str, List[float]]) -> List[Dict[str, str]]:
    """daily_hours_per_user: {name: [hrs_day1, hrs_day2, ...]} for recent days."""
    insights = []
    for name, hours in daily_hours_per_user.items():
        if not hours:
            continue
        days_over = sum(1 for h in hours if h > settings.burnout_daily_hours)
        avg = statistics.mean(hours)
        if days_over >= 3:
            insights.append({
                "type": "danger",
                "title": f"Burnout risk: {name}",
                "body": f"{name} has logged >{settings.burnout_daily_hours:.0f}h on {days_over} of the last {len(hours)} days. Recommend a check-in."
            })
        elif avg > settings.burnout_daily_hours * 0.9:
            insights.append({
                "type": "warning",
                "title": f"Watch: {name}",
                "body": f"Averaging {avg:.1f}h/day — close to burnout threshold."
            })
    return insights


# ============================================================
# 6. Deadline risk predictor
# ============================================================

def predict_deadline_risk(task: Dict[str, Any], total_minutes_logged: int) -> Dict[str, Any]:
    """Returns {risk: 'low'|'medium'|'high', reason: str}."""
    if not task.get("deadline") or task.get("status") == "completed":
        return {"risk": "low", "reason": "No deadline or already complete."}

    deadline = task["deadline"]
    if isinstance(deadline, str):
        deadline = datetime.fromisoformat(deadline)

    days_left = (deadline - datetime.utcnow()).days
    estimated = task.get("estimated_hours") or 0
    logged = total_minutes_logged / 60.0

    if days_left < 0:
        return {"risk": "high", "reason": f"Already {abs(days_left)} day(s) past deadline."}

    if estimated <= 0:
        # Without an estimate we can only flag the time crunch
        if days_left <= 1:
            return {"risk": "high", "reason": "Deadline within 24 hours and no effort estimate."}
        return {"risk": "medium", "reason": "No effort estimate set — risk unknown."}

    remaining = max(estimated - logged, 0)
    # Assume 6 productive hours/day
    needed_days = remaining / 6.0
    if needed_days > days_left:
        return {
            "risk": "high",
            "reason": f"Needs ~{remaining:.1f}h more work but only {days_left} day(s) until deadline."
        }
    if needed_days > days_left * 0.7:
        return {
            "risk": "medium",
            "reason": f"Tight — {remaining:.1f}h work, {days_left} day(s) left."
        }
    return {"risk": "low", "reason": f"On track — {remaining:.1f}h work, {days_left} day(s) left."}


# ============================================================
# 7. Effort forecast for a new task
# ============================================================

def forecast_effort(new_task_text: str, history: List[Dict[str, Any]]) -> Dict[str, Any]:
    """history: list of {sub_task, hours_logged}. Returns {hours: float, basis: str}."""
    if not history:
        return {"hours": 4.0, "basis": "No history — default estimate."}

    # Cheap similarity: token overlap
    text_tokens = set(re.findall(r"\w+", new_task_text.lower()))
    best, best_score = None, 0
    for h in history:
        h_tokens = set(re.findall(r"\w+", h["sub_task"].lower()))
        score = len(text_tokens & h_tokens)
        if score > best_score:
            best, best_score = h, score

    if best and best_score >= 2:
        return {
            "hours": round(best["hours_logged"], 1),
            "basis": f"Similar to past task: \"{best['sub_task']}\" ({best['hours_logged']:.1f}h)"
        }

    avg = statistics.mean([h["hours_logged"] for h in history if h["hours_logged"] > 0] or [4.0])
    return {"hours": round(avg, 1), "basis": f"Team average across {len(history)} past tasks."}
