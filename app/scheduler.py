from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.database import SessionLocal
from app import crud
from app.services import leetcode, telegram_bot, groq_summary
from app.config import settings


def run_daily_pull():
    """Pull each user's LeetCode activity, update submissions + streaks, push group digests
    and a personal DM to any user who has linked their own Telegram chat."""
    db = SessionLocal()
    try:
        users = crud.get_all_users(db)
        for user in users:
            try:
                activity = leetcode.get_todays_activity(user.leetcode_username)
            except Exception as e:
                print(f"[daily_pull] failed to fetch {user.username}: {e}")
                continue

            crud.upsert_submission(
                db,
                user_id=user.id,
                source="leetcode",
                problems_solved_today=activity["solved_today"],
                easy=activity["easy"],
                medium=activity["medium"],
                hard=activity["hard"],
                total_all_time=activity["total_all_time"],
            )
            crud.update_user_streak(db, user.id, was_active_today=activity["solved_today"] > 0)

            # Personal DM - fires regardless of whether the user's group(s) have a Telegram
            # chat configured, so linking your own Telegram is never a no-op.
            if user.telegram_chat_id:
                updated_streak = user.streak.current_streak if user.streak else 0
                personal_msg = telegram_bot.build_personal_daily_message(
                    user.username, activity["solved_today"], updated_streak
                )
                telegram_bot.send_message(user.telegram_chat_id, personal_msg)

        groups = crud.get_all_groups(db)
        for group in groups:
            members = crud.get_group_members(db, group.id)
            member_rows = []
            for m in members:
                today_rows = crud.get_user_history(db, m.id, days=1)
                solved_today = today_rows[0].problems_solved if today_rows else 0
                streak = m.streak.current_streak if m.streak else 0
                member_rows.append(
                    {"username": m.username, "solved_today": solved_today, "current_streak": streak}
                )

            gstreak = crud.recompute_group_streak(db, group.id)
            digest = telegram_bot.build_daily_digest(group.name, member_rows, gstreak.current_streak)
            if group.telegram_chat_id:
                telegram_bot.send_message(group.telegram_chat_id, digest)
            # else: group chat not linked yet - members without a personal Telegram link
            # simply get no notification for this group until either is set up.
    finally:
        db.close()


def run_weekly_summary():
    """Generate a Groq-written weekly trend summary per user and push it to their group(s)
    and to their personal chat if linked."""
    db = SessionLocal()
    try:
        users = crud.get_all_users(db)
        for user in users:
            history_rows = crud.get_user_history(db, user.id, days=7)
            history = [
                {
                    "activity_date": str(r.activity_date),
                    "problems_solved": r.problems_solved,
                    "easy_count": r.easy_count,
                    "medium_count": r.medium_count,
                    "hard_count": r.hard_count,
                }
                for r in history_rows
            ]
            if not history:
                continue

            summary_text = groq_summary.generate_weekly_summary(user.username, history)
            message = telegram_bot.build_weekly_summary_message(user.username, summary_text)

            if user.telegram_chat_id:
                telegram_bot.send_message(user.telegram_chat_id, message)

            for membership in user.memberships:
                group = membership.group
                if group.telegram_chat_id:
                    telegram_bot.send_message(group.telegram_chat_id, message)
    finally:
        db.close()


def start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        run_daily_pull,
        CronTrigger(hour=settings.DAILY_PULL_HOUR_UTC, minute=0),
        id="daily_pull",
        replace_existing=True,
    )
    scheduler.add_job(
        run_weekly_summary,
        CronTrigger(day_of_week=settings.WEEKLY_SUMMARY_DAY, hour=settings.DAILY_PULL_HOUR_UTC, minute=15),
        id="weekly_summary",
        replace_existing=True,
    )
    scheduler.start()
    return scheduler