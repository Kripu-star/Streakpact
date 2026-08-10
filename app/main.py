from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.database import engine, get_db
from app import crud, schemas, models, auth
from app.services import leetcode, telegram_bot
from app.scheduler import start_scheduler, run_daily_pull, run_weekly_summary
from app.config import settings

# NOTE: table creation is now handled by Alembic migrations (see alembic/ and README),
# not by Base.metadata.create_all(). Run `alembic upgrade head` before starting the app.

app = FastAPI(title="StreakPact", description="Peer accountability tracker for CP/DSA prep")

# Dev-friendly CORS. If you ever split frontend/backend onto different origins, restrict
# allow_origins to that exact origin instead of "*". Since the frontend is served by this
# same FastAPI app below, CORS mostly matters for local dev (e.g. opening index.html directly).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

scheduler = None


@app.on_event("startup")
def on_startup():
    global scheduler
    scheduler = start_scheduler()


# ---------- Auth ----------

@app.post("/users", response_model=schemas.UserOut)
def create_user(payload: schemas.UserCreate, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.username == payload.username).first()
    if existing:
        raise HTTPException(400, "Username already taken")

    existing_lc = (
        db.query(models.User)
        .filter(models.User.leetcode_username == payload.leetcode_username)
        .first()
    )
    if existing_lc:
        raise HTTPException(
            400,
            f"LeetCode handle '{payload.leetcode_username}' is already linked to another account",
        )

    try:
        lc_valid = leetcode.validate_username(payload.leetcode_username)
    except Exception:
        raise HTTPException(502, "Could not verify LeetCode username right now — try again shortly")
    if not lc_valid:
        raise HTTPException(400, f"LeetCode username '{payload.leetcode_username}' does not exist")

    if payload.telegram_chat_id:
        if not telegram_bot.validate_chat_id(payload.telegram_chat_id):
            raise HTTPException(
                400,
                "Could not reach that Telegram user_id — make sure you've sent /start to the bot first",
            )

    hashed = auth.hash_password(payload.password)
    return crud.create_user(db, payload, hashed_password=hashed)


@app.post("/auth/login", response_model=schemas.TokenOut)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(401, "Incorrect username or password")
    token = auth.create_access_token(user.id)
    return schemas.TokenOut(access_token=token)


@app.get("/users/me", response_model=schemas.UserOut)
def read_own_profile(current_user: models.User = Depends(auth.get_current_user)):
    return current_user


@app.get("/users/me/history", response_model=schemas.UserHistoryOut)
def read_own_history(
    days: int = 14,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    history = crud.get_user_history(db, current_user.id, days=days)
    return schemas.UserHistoryOut(
        user=schemas.UserOut.model_validate(current_user),
        streak=schemas.StreakOut.model_validate(current_user.streak) if current_user.streak else None,
        history=[schemas.SubmissionOut.model_validate(row) for row in history],
    )


@app.get("/users/me/groups", response_model=list[schemas.GroupOut])
def read_own_groups(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    return crud.get_user_groups(db, current_user.id)


@app.get("/users/me/telegram-link")
def get_telegram_link(current_user: models.User = Depends(auth.get_current_user)):
    if not settings.TELEGRAM_BOT_USERNAME:
        raise HTTPException(500, "Telegram bot username not configured on the server")
    return {"link": telegram_bot.build_deep_link(current_user.id)}


@app.post("/users/me/link-telegram")
def link_telegram(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    chat_id = telegram_bot.find_chat_id_from_start_payload(current_user.id)
    if not chat_id:
        raise HTTPException(
            404,
            "Haven't seen a message from you yet — tap the Telegram link and press Start, then try again",
        )

    # Guard the same "distinct people" assumption here too, since linking can happen after
    # a user has already joined groups, not just at signup.
    for group in crud.get_user_groups(db, current_user.id):
        dupe = crud.find_group_member_with_telegram_chat_id(db, group.id, chat_id)
        if dupe and dupe.id != current_user.id:
            raise HTTPException(
                400,
                f"This Telegram account is already linked to '{dupe.username}' in your group "
                f"'{group.name}' — each group member should be a distinct person",
            )

    current_user.telegram_chat_id = chat_id
    db.commit()
    return {"telegram_chat_id": chat_id}


# ---------- Groups (all require a valid Bearer token; acts on the logged-in user) ----------

@app.post("/groups", response_model=schemas.GroupOut)
def create_group(
    payload: schemas.GroupCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    return crud.create_group(db, payload, creator_user_id=current_user.id)


@app.post("/groups/join", response_model=schemas.GroupOut)
def join_group(
    payload: schemas.GroupJoin,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    group = db.query(models.Group).filter(models.Group.invite_code == payload.invite_code).first()
    if not group:
        raise HTTPException(404, "Invalid invite code")

    if current_user.telegram_chat_id:
        dupe = crud.find_group_member_with_telegram_chat_id(db, group.id, current_user.telegram_chat_id)
        if dupe and dupe.id != current_user.id:
            raise HTTPException(
                400,
                f"'{dupe.username}' in this group is already linked to your Telegram account — "
                "each group member should be a distinct person for the streak to mean anything",
            )

    joined = crud.join_group(db, payload.invite_code, user_id=current_user.id)
    return joined


@app.get("/groups/{group_id}/members", response_model=list[schemas.UserOut])
def group_members(
    group_id: str,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    member_ids = {m.id for m in crud.get_group_members(db, group_id)}
    if current_user.id not in member_ids:
        raise HTTPException(403, "You're not a member of this group")
    return crud.get_group_members(db, group_id)


@app.get("/groups/{group_id}/streak", response_model=schemas.GroupStreakOut)
def group_streak(
    group_id: str,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    member_ids = {m.id for m in crud.get_group_members(db, group_id)}
    if current_user.id not in member_ids:
        raise HTTPException(403, "You're not a member of this group")
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group or not group.streak:
        raise HTTPException(404, "Group or streak not found")
    return group.streak


@app.patch("/groups/{group_id}/telegram-chat-id", response_model=schemas.GroupOut)
def update_group_telegram_chat_id(
    group_id: str,
    payload: schemas.GroupTelegramUpdate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    member_ids = {m.id for m in crud.get_group_members(db, group_id)}
    if current_user.id not in member_ids:
        raise HTTPException(403, "You're not a member of this group")
    group = crud.set_group_telegram_chat_id(db, group_id, payload.telegram_chat_id)
    if not group:
        raise HTTPException(404, "Group not found")
    return group


# ---------- Manual trigger endpoints (useful for demoing / testing without waiting for cron) ----------
# NOTE: left unauthenticated deliberately for local demo convenience. Do not expose these
# publicly without adding an admin check - see README "known limitations".

@app.post("/admin/run-daily-pull")
def trigger_daily_pull():
    run_daily_pull()
    return {"status": "daily pull executed"}


@app.post("/admin/run-weekly-summary")
def trigger_weekly_summary():
    run_weekly_summary()
    return {"status": "weekly summary executed"}


@app.get("/health")
def health():
    return {"status": "ok"}


# Serve the frontend last, as a catch-all - must come after every API route above,
# otherwise it would shadow them.
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")