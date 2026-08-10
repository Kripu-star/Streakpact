import requests
from app.config import settings

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


def _build_prompt(username: str, history: list[dict]) -> str:
    """
    history: list of dicts like
      {'activity_date': '2026-08-01', 'problems_solved': 2, 'easy_count': 1, 'medium_count': 1, 'hard_count': 0}
    """
    total_solved = sum(h["problems_solved"] for h in history)
    active_days = sum(1 for h in history if h["problems_solved"] > 0)
    easy = sum(h["easy_count"] for h in history)
    medium = sum(h["medium_count"] for h in history)
    hard = sum(h["hard_count"] for h in history)

    return f"""You are a blunt, encouraging coding-interview prep coach.
Given one user's last 7 days of LeetCode activity, write a 3-4 sentence summary for their
accountability group chat. Be specific and honest, not generic cheerleading.

Data for {username}:
- Active days this week: {active_days}/7
- Total problems solved: {total_solved}
- Difficulty split: Easy={easy}, Medium={medium}, Hard={hard}

Call out any imbalance (e.g. too many Easy, no Hard problems), any inactivity, and one
concrete, specific suggestion for next week. Do not use emojis. Keep it under 80 words."""


def generate_weekly_summary(username: str, history: list[dict]) -> str:
    if not settings.GROQ_API_KEY:
        return f"(Groq not configured) {username} solved {sum(h['problems_solved'] for h in history)} problems this week."

    prompt = _build_prompt(username, history)
    body = {
        "model": settings.GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.6,
        "max_tokens": 150,
    }
    headers = {
        "Authorization": f"Bearer {settings.GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    resp = requests.post(GROQ_URL, json=body, headers=headers, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError):
        return f"{username}'s weekly summary could not be generated right now."
