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

- **FastAPI** — REST API (auth, users, groups, history, admin trigger endpoints)
- **SQLite** (via SQLAlchemy + Alembic) — users, groups, memberships, daily submissions, streaks; schema changes go through migrations, not `create_all`
- **JWT + bcrypt** — signup/login flow; all group and profile endpoints require a valid Bearer token and act on the logged-in user, not a client-supplied ID
- **LeetCode GraphQL** (unofficial public endpoint) — daily solved-problem data
- **Telegram Bot API** — pushes daily digests + weekly summaries to the group chat
- **Groq API** (Llama models) — generates the weekly trend summary per user
- **APScheduler** — runs the daily pull and weekly summary jobs in-process
- **Frontend** — plain HTML/CSS/JS (no build step), served directly by FastAPI as static files. One deployable unit, one process.
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
cp .env.example .env   # fill in TELEGRAM_BOT_TOKEN / GROQ_API_KEY / JWT_SECRET_KEY
alembic upgrade head   # creates all tables via migration - do this before first run
uvicorn app.main:app --reload
```

Generate a `JWT_SECRET_KEY` with `openssl rand -hex 32` — do not leave it blank or reuse a
guessable value; login/token verification will fail without a real secret.

Docs at `http://localhost:8000/docs`. Frontend at `http://localhost:8000/` (same server, same port).

## Database migrations (Alembic)

The app no longer auto-creates tables on startup — schema changes go through Alembic instead
of deleting `streakpact.db` every time a model changes.

**First-time setup / fresh clone:**
```bash
alembic upgrade head
```

**After changing a model** (e.g. adding a column to `app/models.py`):
```bash
alembic revision --autogenerate -m "short description of the change"
alembic upgrade head
```
Always open the generated file in `alembic/versions/` and read it before running `upgrade` —
autogenerate is a good first draft, not something to trust blindly (it can miss some changes,
like renaming a column, which it sees as "drop one, add another" unless you edit the migration
by hand to make it a true rename).

**Undo the last migration** (useful while testing):
```bash
alembic downgrade -1
```

## Typical flow

1. `POST /users` — each group member registers with a username, password, and LeetCode username.
2. `POST /auth/login` (form data: `username`, `password`) — returns a JWT `access_token`.
3. All subsequent requests send `Authorization: Bearer <access_token>`.
4. `POST /groups` — creates a group, the logged-in user becomes the first member. Returns an `invite_code`.
5. `POST /groups/join` — other members join with that code, using their own token (no `user_id` needed in the body — it's taken from the token).
6. Link a personal Telegram chat (dashboard → "Open Telegram & tap Start" → "I've done that — check now")
   so you get direct notifications. Group chat IDs are still set manually at group creation
   (set `telegram_chat_id` when creating the group) so the bot can post digests there.
7. The scheduler pulls each member's LeetCode activity once a day, updates streaks, and posts
   a digest to the group chat. Once a week it also posts an AI-generated trend summary per user.
8. `POST /admin/run-daily-pull` and `/admin/run-weekly-summary` exist to trigger these manually
   for testing/demo instead of waiting for the cron time. (These are intentionally left open/unauthenticated for local demo convenience — see limitations below.)

## Known limitations / things to talk through in an interview

- No token refresh/revocation — a JWT is valid for its full lifetime (7 days by default) even
  if the user "logs out" client-side. A production version would add a refresh-token flow or
  a server-side denylist for revoked tokens.
- LeetCode's GraphQL endpoint is unofficial and public — no auth, so it can change or rate-limit
  without notice. Difficulty-per-problem is fetched with a small per-title lookup + a short
  sleep to avoid hammering it, which is a real bottleneck if a group is large.
- Streak logic is UTC-day based; a user solving right at midnight local time could get an
  inconsistent streak — a known tradeoff, would need per-user timezone handling to fix properly.
- Single SQLite file — fine for a handful of small groups, would need to move to Postgres if
  this ever had to handle concurrent writes at scale (schema is already relational and would
  port over with minimal changes via SQLAlchemy).
- A personal Telegram chat is linked via a deep link (`https://t.me/<bot>?start=<user_id>`) +
  a poll of `getUpdates` to match the resulting `/start` message back to the right app account
  — no manual chat-ID lookups. **Group** chat IDs are still set manually at group creation,
  since there's no equivalent deep-link flow for adding a bot to an existing group chat.
- The `/admin/run-*` trigger endpoints are deliberately left unauthenticated for local demo
  convenience. In a real deployment these would need an admin-only check, or be removed in
  favor of the actual cron schedule.
- Users without a linked Telegram cannot create or join a group — both require a personal
  Telegram link first, and creating a group additionally requires providing (and validating)
  a group Telegram chat ID up front. This makes Telegram delivery non-optional by design,
  rather than a feature people silently miss out on. The one place duplicate people ARE
  blocked: joining/linking is rejected if it would put two members of the *same group* on
  the same Telegram chat_id, since that would let one real person defeat the "each member is
  a distinct, accountable person" premise the group-streak mechanic depends on.
- Group members can see each other's LeetCode handle, current streak, and whether Telegram is
  linked — but never each other's raw numeric Telegram chat ID, which is private to the
  account holder (`GroupMemberOut` deliberately excludes it; only `/users/me` exposes your own).