from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel


class UserCreate(BaseModel):
    username: str
    password: str
    leetcode_username: str
    codeforces_handle: Optional[str] = None
    telegram_chat_id: Optional[str] = None


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: str
    username: str
    leetcode_username: str
    codeforces_handle: Optional[str]
    telegram_chat_id: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class GroupCreate(BaseModel):
    name: str
    telegram_chat_id: Optional[str] = None


class GroupJoin(BaseModel):
    invite_code: str


class GroupTelegramUpdate(BaseModel):
    telegram_chat_id: str


class GroupOut(BaseModel):
    id: str
    name: str
    invite_code: str
    telegram_chat_id: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class StreakOut(BaseModel):
    current_streak: int
    longest_streak: int
    last_active_date: Optional[date]

    class Config:
        from_attributes = True


class SubmissionOut(BaseModel):
    activity_date: date
    source: str
    problems_solved: int
    easy_count: int
    medium_count: int
    hard_count: int

    class Config:
        from_attributes = True


class UserHistoryOut(BaseModel):
    user: UserOut
    streak: Optional[StreakOut]
    history: List[SubmissionOut]


class GroupStreakOut(BaseModel):
    current_streak: int
    longest_streak: int
    last_all_active_date: Optional[date]

    class Config:
        from_attributes = True