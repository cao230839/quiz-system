from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field

from app.models import QuestionType


class UserCreate(BaseModel):
    email: EmailStr
    username: str = Field(min_length=2, max_length=50)
    password: str = Field(min_length=6)


class UserLogin(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    username: str

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class QuestionCreate(BaseModel):
    type: QuestionType
    stem: str
    options: list[str] | None = None
    answer: str
    explanation: str | None = None
    order_index: int = 0


class QuestionUpdate(BaseModel):
    type: QuestionType | None = None
    stem: str | None = None
    options: list[str] | None = None
    answer: str | None = None
    explanation: str | None = None
    order_index: int | None = None


class QuestionOut(BaseModel):
    id: int
    bank_id: int
    type: QuestionType
    stem: str
    options: list[str] | None
    answer: str
    explanation: str | None
    order_index: int

    class Config:
        from_attributes = True


class BankCreate(BaseModel):
    title: str
    questions: list[QuestionCreate] = []


class BankOut(BaseModel):
    id: int
    title: str
    created_at: datetime
    question_count: int = 0

    class Config:
        from_attributes = True


class BankDetail(BankOut):
    questions: list[QuestionOut] = []


class ParseResult(BaseModel):
    title: str
    questions: list[QuestionCreate]


class QuizStart(BaseModel):
    bank_id: int
    count: int | None = None
    shuffle: bool = False
    wrong_only: bool = False


class QuizSession(BaseModel):
    session_id: str
    question_ids: list[int]
    current_index: int = 0


class AnswerSubmit(BaseModel):
    session_id: str
    question_id: int
    user_answer: str
    self_assessed_correct: bool | None = None


class AnswerResult(BaseModel):
    correct: bool
    correct_answer: str
    explanation: str | None
    show_self_assess: bool = False


class WrongAnswerOut(BaseModel):
    id: int
    question: QuestionOut
    mastered: bool
    created_at: datetime

    class Config:
        from_attributes = True
