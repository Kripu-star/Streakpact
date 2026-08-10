import requests
from app.config import settings

TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}"


def send_message(chat_id: str, text: str) -> None:
    if not settings.TELEGRAM_BOT_TOKEN or not chat_id:
        # No bot configured / no chat linked yet -> just skip silently in dev.
        print(f"[telegram:disabled] would send to {chat_id}: {text}")
        return

    url = f"{TELEGRAM_API_BASE.format(token=settings.TELEGRAM_BOT_TOKEN)}/sendMessage"
    resp = requests.post(
        url,
        json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
        timeout=10,
    )
    resp.raise_for_status()


def build_daily_digest(group_name: str, member_rows: list[dict], group_streak: int) -> str:
    """
    member_rows: [{'username': str, 'solved_today': int, 'current_streak': int}, ...]
    """
    lines = [f"*{group_name} — Daily Check-in* 🔥 Group streak: {group_streak} day(s)\n"]
    active = [m for m in member_rows if m["solved_today"] > 0]
    inactive = [m for m in member_rows if m["solved_today"] == 0]

    if active:
        lines.append("*Solved today:*")
        for m in active:
            lines.append(f"  • {m['username']} — {m['solved_today']} problem(s), streak {m['current_streak']}")

    if inactive:
        lines.append("\n*Gone quiet:*")
        for m in inactive:
            lines.append(f"  • {m['username']} — no submissions today. Nudge them!")

    return "\n".join(lines)


def build_weekly_summary_message(username: str, ai_summary: str) -> str:
    return f"*Weekly summary — {username}*\n{ai_summary}"


def build_personal_daily_message(username: str, solved_today: int, current_streak: int) -> str:
    if solved_today > 0:
        return (
            f"✅ *{username}* — solved {solved_today} problem(s) today. "
            f"Current streak: {current_streak} day(s)."
        )
    return (
        f"⚠️ *{username}* — no submissions yet today. Current streak: {current_streak} day(s). "
        f"Solve one to keep it alive!"
    )


def validate_chat_id(chat_id: str) -> bool:
    """
    Returns True if the bot can actually reach this chat/user.
    Note: Telegram only allows a bot to resolve a user's chat via getChat if that user has
    already started a conversation with the bot (sent /start) or shares a group with it.
    There is no way to validate an arbitrary Telegram user ID the bot has never seen.
    """
    if not settings.TELEGRAM_BOT_TOKEN:
        # Bot not configured at all - can't validate, so don't block user creation on it.
        return True

    url = f"{TELEGRAM_API_BASE.format(token=settings.TELEGRAM_BOT_TOKEN)}/getChat"
    try:
        resp = requests.get(url, params={"chat_id": chat_id}, timeout=10)
    except requests.RequestException:
        # Network failure - fail open so a Telegram outage doesn't block signups.
        return True

    return resp.status_code == 200 and resp.json().get("ok", False)


def get_updates() -> list[dict]:
    """Raw poll of the bot's pending updates (messages sent to it since the last poll)."""
    if not settings.TELEGRAM_BOT_TOKEN:
        return []
    url = f"{TELEGRAM_API_BASE.format(token=settings.TELEGRAM_BOT_TOKEN)}/getUpdates"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    return resp.json().get("result", [])


def find_chat_id_from_start_payload(payload: str) -> str | None:
    """
    Scans recent bot updates for a '/start <payload>' message (sent automatically when a user
    taps a https://t.me/<bot>?start=<payload> deep link) and returns the chat_id it came from.
    This is how we learn a user's chat_id without asking them to manually look up any IDs -
    the payload (their app user_id) tells us which app account the chat_id belongs to.
    """
    target_text = f"/start {payload}"
    for update in get_updates():
        message = update.get("message", {})
        if message.get("text") == target_text:
            chat = message.get("chat", {})
            chat_id = chat.get("id")
            if chat_id is not None:
                return str(chat_id)
    return None


def build_deep_link(payload: str) -> str:
    return f"https://t.me/{settings.TELEGRAM_BOT_USERNAME}?start={payload}"