# StreakPact

A peer accountability tool for a small group prepping for coding interviews together.
Not a "follow" feed — a closed group opts in together, a shared streak breaks if *anyone*
goes quiet, and a bot pushes that information to the group instead of waiting for someone
to check a dashboard.

## Why this isn't just "follow someone on LeetCode"

- **Opt-in, mutual, closed group** — not a public watchlist of a stranger's profile.
- **Push, not pull** — a daily Telegram digest is sent to the group automatically.
- **Shared consequence** — the group streak resets if *any* member misses a day, so the
  incentive is social, not just personal.
- **Cross-cutting context, not a raw count** — a weekly AI-generated summary calls out trends
  (e.g. "too many Easy problems, no Hard problems this week") that a solved-count alone
  doesn't surface.

## Stack

- **FastAPI** — REST API (users, groups, history, admin trigger endpoints)
- **SQLite** (via SQLAlchemy) — users, groups, memberships, daily submissions, streaks
- **LeetCode GraphQL** (unofficial public endpoint) — daily solved-problem data
- **Telegram Bot API** — pushes daily digests + weekly summaries to the group chat
- **Groq API** (Llama models) — generates the weekly trend summary per user
- **APScheduler** — runs the daily pull and weekly summary jobs in-process
- **AWS EC2** — deployment target (single instance, `uvicorn` behind a process manager)

## Project layout

```
app/
  main.py          FastAPI app + routes
  models.py         SQLAlchemy tables
  schemas.py        Pydantic request/response models
  crud.py            DB read/write + streak logic
  scheduler.py        APScheduler jobs (daily pull, weekly summary)
  services/
    leetcode.py       LeetCode GraphQL client
    telegram_bot.py    Telegram send + message formatting
    groq_summary.py    Groq prompt + call
```

## Running locally

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in TELEGRAM_BOT_TOKEN / GROQ_API_KEY
uvicorn app.main:app --reload
```

Docs at `http://localhost:8000/docs`.

## Typical flow

1. `POST /users` — each group member registers with their LeetCode username.
2. `POST /groups` — one member creates a group (gets back an `invite_code`).
3. `POST /groups/join` — others join with that code.
4. Link the group's Telegram chat ID (set `telegram_chat_id` on the group) so the bot can post there.
5. The scheduler pulls each member's LeetCode activity once a day, updates streaks, and posts
   a digest to the group chat. Once a week it also posts an AI-generated trend summary per user.
6. `POST /admin/run-daily-pull` and `/admin/run-weekly-summary` exist to trigger these manually
   for testing/demo instead of waiting for the cron time.

## Known limitations / things to talk through in an interview

- LeetCode's GraphQL endpoint is unofficial and public — no auth, so it can change or rate-limit
  without notice. Difficulty-per-problem is fetched with a small per-title lookup + a short
  sleep to avoid hammering it, which is a real bottleneck if a group is large.
- Streak logic is UTC-day based; a user solving right at midnight local time could get an
  inconsistent streak — a known tradeoff, would need per-user timezone handling to fix properly.
- Single SQLite file — fine for a handful of small groups, would need to move to Postgres if
  this ever had to handle concurrent writes at scale.
- Telegram is used for both individual bot setup and group posting — chat IDs currently have
  to be set manually rather than through a `/start` bot flow.
