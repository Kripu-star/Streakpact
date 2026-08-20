from datetime import date, timedelta
from sqlalchemy.orm import Session

from app import models, schemas


def create_user(db: Session, payload: schemas.UserCreate, hashed_password: str) -> models.User:
    user = models.User(
        username=payload.username,
        hashed_password=hashed_password,
        leetcode_username=payload.leetcode_username,
        codeforces_handle=payload.codeforces_handle,
        telegram_chat_id=payload.telegram_chat_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.add(models.Streak(user_id=user.id))
    db.commit()
    return user


def get_user(db: Session, user_id: str) -> models.User | None:
    return db.query(models.User).filter(models.User.id == user_id).first()


def create_group(db: Session, payload: schemas.GroupCreate, creator_user_id: str) -> models.Group:
    group = models.Group(
        name=payload.name,
        telegram_chat_id=payload.telegram_chat_id,
        creator_id=creator_user_id,
    )
    db.add(group)
    db.commit()
    db.refresh(group)

    db.add(models.GroupMembership(user_id=creator_user_id, group_id=group.id))
    db.add(models.GroupStreak(group_id=group.id))
    db.commit()
    return group


def join_group(db: Session, invite_code: str, user_id: str) -> models.Group | None:
    group = db.query(models.Group).filter(models.Group.invite_code == invite_code).first()
    if not group:
        return None
    existing = (
        db.query(models.GroupMembership)
        .filter_by(user_id=user_id, group_id=group.id)
        .first()
    )
    if not existing:
        db.add(models.GroupMembership(user_id=user_id, group_id=group.id))
        db.commit()
    return group


def get_group_members(db: Session, group_id: str) -> list[models.User]:
    return (
        db.query(models.User)
        .join(models.GroupMembership, models.GroupMembership.user_id == models.User.id)
        .filter(models.GroupMembership.group_id == group_id)
        .all()
    )


def delete_group(db: Session, group_id: str) -> bool:
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        return False
    db.query(models.GroupMembership).filter_by(group_id=group_id).delete()
    db.query(models.GroupStreak).filter_by(group_id=group_id).delete()
    db.delete(group)
    db.commit()
    return True


def find_group_member_with_telegram_chat_id(
    db: Session, group_id: str, telegram_chat_id: str
) -> models.User | None:
    """Used to block a group from having two members who are provably the same real person
    (same linked Telegram chat) - which would let one person defeat the group-streak mechanic."""
    return (
        db.query(models.User)
        .join(models.GroupMembership, models.GroupMembership.user_id == models.User.id)
        .filter(
            models.GroupMembership.group_id == group_id,
            models.User.telegram_chat_id == telegram_chat_id,
        )
        .first()
    )


def get_group_members_with_status(db: Session, group_id: str) -> list[dict]:
    """Member info for display to groupmates - deliberately excludes the raw telegram_chat_id
    (just a linked/not-linked boolean) so members can't see each other's actual Telegram IDs."""
    members = get_group_members(db, group_id)
    result = []
    for m in members:
        result.append(
            {
                "username": m.username,
                "leetcode_username": m.leetcode_username,
                "telegram_linked": m.telegram_chat_id is not None,
                "current_streak": m.streak.current_streak if m.streak else 0,
            }
        )
    return result


def get_user_groups(db: Session, user_id: str) -> list[models.Group]:
    return (
        db.query(models.Group)
        .join(models.GroupMembership, models.GroupMembership.group_id == models.Group.id)
        .filter(models.GroupMembership.user_id == user_id)
        .all()
    )


def set_group_telegram_chat_id(db: Session, group_id: str, chat_id: str) -> models.Group | None:
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        return None
    group.telegram_chat_id = chat_id
    db.commit()
    db.refresh(group)
    return group


def leave_group(db: Session, group_id: str, user_id: str) -> bool:
    """Removes a single member's own membership. Returns True if a row was actually deleted."""
    membership = (
        db.query(models.GroupMembership)
        .filter_by(group_id=group_id, user_id=user_id)
        .first()
    )
    if not membership:
        return False
    db.delete(membership)
    db.commit()
    return True


def delete_group(db: Session, group_id: str) -> bool:
    """Deletes a group and everything that references it. SQLite doesn't enforce FK cascade
    by default, so we clean up dependent rows explicitly rather than relying on the DB."""
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        return False

    db.query(models.GroupMembership).filter_by(group_id=group_id).delete()
    db.query(models.GroupStreak).filter_by(group_id=group_id).delete()
    db.delete(group)
    db.commit()
    return True


def delete_user_account(db: Session, user_id: str) -> None:
    """Fully removes a user and everything that references them. Caller is responsible for
    having already checked that the user isn't the creator of any group with other members
    (see main.py) - this function assumes that check already passed."""
    db.query(models.DailySubmission).filter_by(user_id=user_id).delete()
    db.query(models.Streak).filter_by(user_id=user_id).delete()

    # Any group this user created must, by this point, have no other members (checked by
    # caller) - so delete those groups outright rather than leaving them ownerless.
    owned_groups = db.query(models.Group).filter_by(creator_id=user_id).all()
    for group in owned_groups:
        db.query(models.GroupMembership).filter_by(group_id=group.id).delete()
        db.query(models.GroupStreak).filter_by(group_id=group.id).delete()
        db.delete(group)

    # Remove membership in any group this user just belongs to (didn't create).
    db.query(models.GroupMembership).filter_by(user_id=user_id).delete()

    user = db.query(models.User).filter_by(id=user_id).first()
    if user:
        db.delete(user)
    db.commit()


def get_groups_created_by(db: Session, user_id: str) -> list[models.Group]:
    return db.query(models.Group).filter(models.Group.creator_id == user_id).all()


def delete_user_account(db: Session, user_id: str) -> None:
    """Permanently deletes a user and everything that only makes sense in relation to them.
    Caller (the endpoint) must have already confirmed the user isn't the creator of any group -
    this function does not check that, to keep the two concerns (ownership vs. deletion)
    separately testable."""
    db.query(models.DailySubmission).filter_by(user_id=user_id).delete()
    db.query(models.Streak).filter_by(user_id=user_id).delete()
    db.query(models.GroupMembership).filter_by(user_id=user_id).delete()
    db.query(models.User).filter_by(id=user_id).delete()
    db.commit()


def get_all_users(db: Session) -> list[models.User]:
    return db.query(models.User).all()


def get_all_groups(db: Session) -> list[models.Group]:
    return db.query(models.Group).all()


def upsert_submission(
    db: Session,
    user_id: str,
    source: str,
    problems_solved_today: int,
    easy: int,
    medium: int,
    hard: int,
    total_all_time: int,
    for_date: date | None = None,
) -> models.DailySubmission:
    for_date = for_date or date.today()
    row = (
        db.query(models.DailySubmission)
        .filter_by(user_id=user_id, activity_date=for_date, source=source)
        .first()
    )
    if row is None:
        row = models.DailySubmission(user_id=user_id, activity_date=for_date, source=source)
        db.add(row)

    row.problems_solved = problems_solved_today
    row.easy_count = easy
    row.medium_count = medium
    row.hard_count = hard
    row.total_solved_all_time = total_all_time
    db.commit()
    db.refresh(row)
    return row


def update_user_streak(db: Session, user_id: str, was_active_today: bool) -> models.Streak:
    streak = db.query(models.Streak).filter_by(user_id=user_id).first()
    if streak is None:
        streak = models.Streak(user_id=user_id)
        db.add(streak)

    today = date.today()
    yesterday = today - timedelta(days=1)

    if was_active_today:
        if streak.last_active_date == yesterday:
            streak.current_streak += 1
        elif streak.last_active_date == today:
            pass  # already counted today
        else:
            streak.current_streak = 1
        streak.last_active_date = today
        streak.longest_streak = max(streak.longest_streak, streak.current_streak)
    else:
        streak.current_streak = 0

    db.commit()
    db.refresh(streak)
    return streak


def recompute_group_streak(db: Session, group_id: str) -> models.GroupStreak:
    """Group streak only continues if EVERY member was active today."""
    members = get_group_members(db, group_id)
    today = date.today()

    all_active_today = True
    for member in members:
        streak = db.query(models.Streak).filter_by(user_id=member.id).first()
        if not streak or streak.last_active_date != today:
            all_active_today = False
            break

    gstreak = db.query(models.GroupStreak).filter_by(group_id=group_id).first()
    if gstreak is None:
        gstreak = models.GroupStreak(group_id=group_id)
        db.add(gstreak)

    yesterday = today - timedelta(days=1)
    if all_active_today and members:
        if gstreak.last_all_active_date == yesterday:
            gstreak.current_streak += 1
        else:
            gstreak.current_streak = 1
        gstreak.last_all_active_date = today
        gstreak.longest_streak = max(gstreak.longest_streak, gstreak.current_streak)
    else:
        gstreak.current_streak = 0

    db.commit()
    db.refresh(gstreak)
    return gstreak


def get_user_history(db: Session, user_id: str, days: int = 14) -> list[models.DailySubmission]:
    since = date.today() - timedelta(days=days)
    return (
        db.query(models.DailySubmission)
        .filter(models.DailySubmission.user_id == user_id, models.DailySubmission.activity_date >= since)
        .order_by(models.DailySubmission.activity_date.desc())
        .all()
    )
