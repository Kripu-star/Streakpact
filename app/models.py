import uuid
from datetime import datetime, date

from sqlalchemy import (
    Column, String, Integer, Date, DateTime, ForeignKey, UniqueConstraint, Boolean
)
from sqlalchemy.orm import relationship

from app.database import Base


def gen_id() -> str:
    return uuid.uuid4().hex[:12]


def gen_invite_code() -> str:
    return uuid.uuid4().hex[:8].upper()


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=gen_id)
    username = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    leetcode_username = Column(String, unique=True, nullable=False, index=True)
    codeforces_handle = Column(String, nullable=True)
    telegram_chat_id = Column(String, nullable=True)  # this user's own DM chat with the bot
    created_at = Column(DateTime, default=datetime.utcnow)

    memberships = relationship("GroupMembership", back_populates="user")
    submissions = relationship("DailySubmission", back_populates="user")
    streak = relationship("Streak", back_populates="user", uselist=False)


class Group(Base):
    __tablename__ = "groups"

    id = Column(String, primary_key=True, default=gen_id)
    name = Column(String, nullable=False)
    invite_code = Column(String, unique=True, default=gen_invite_code, index=True)
    telegram_chat_id = Column(String, unique=True, nullable=True)  # group chat the bot posts to
    creator_id = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    memberships = relationship("GroupMembership", back_populates="group")
    streak = relationship("GroupStreak", back_populates="group", uselist=False)


class GroupMembership(Base):
    __tablename__ = "group_memberships"
    __table_args__ = (UniqueConstraint("user_id", "group_id", name="uq_user_group"),)

    id = Column(String, primary_key=True, default=gen_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    group_id = Column(String, ForeignKey("groups.id"), nullable=False)
    joined_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="memberships")
    group = relationship("Group", back_populates="memberships")


class DailySubmission(Base):
    """One row per user per day per source, storing that day's activity summary."""
    __tablename__ = "daily_submissions"
    __table_args__ = (UniqueConstraint("user_id", "activity_date", "source", name="uq_user_date_source"),)

    id = Column(String, primary_key=True, default=gen_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    activity_date = Column(Date, default=date.today, nullable=False)
    source = Column(String, nullable=False, default="leetcode")  # "leetcode" | "codeforces"

    problems_solved = Column(Integer, default=0)
    easy_count = Column(Integer, default=0)
    medium_count = Column(Integer, default=0)
    hard_count = Column(Integer, default=0)
    total_solved_all_time = Column(Integer, default=0)  # cumulative count as of this pull

    fetched_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="submissions")


class Streak(Base):
    """Per-user streak, recomputed after each daily pull."""
    __tablename__ = "streaks"

    id = Column(String, primary_key=True, default=gen_id)
    user_id = Column(String, ForeignKey("users.id"), unique=True, nullable=False)
    current_streak = Column(Integer, default=0)
    longest_streak = Column(Integer, default=0)
    last_active_date = Column(Date, nullable=True)

    user = relationship("User", back_populates="streak")


class GroupStreak(Base):
    """Group streak resets to 0 if ANY member misses a day."""
    __tablename__ = "group_streaks"

    id = Column(String, primary_key=True, default=gen_id)
    group_id = Column(String, ForeignKey("groups.id"), unique=True, nullable=False)
    current_streak = Column(Integer, default=0)
    longest_streak = Column(Integer, default=0)
    last_all_active_date = Column(Date, nullable=True)

    group = relationship("Group", back_populates="streak")