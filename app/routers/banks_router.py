from __future__ import annotations

import shutil
import tempfile
import uuid
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Question, QuestionBank, User
from app.parsers import parse_file
from app.schemas import (
    BankCreate,
    BankDetail,
    BankOut,
    ParseResult,
    QuestionCreate,
    QuestionOut,
    QuestionUpdate,
)

router = APIRouter(prefix="/api/banks", tags=["banks"])


def bank_to_out(bank: QuestionBank) -> BankOut:
    return BankOut(
        id=bank.id,
        title=bank.title,
        created_at=bank.created_at,
        question_count=len(bank.questions),
    )


@router.get("", response_model=List[BankOut])
def list_banks(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    banks = db.query(QuestionBank).filter(QuestionBank.user_id == user.id).all()
    return [bank_to_out(b) for b in banks]


@router.get("/{bank_id}", response_model=BankDetail)
def get_bank(
    bank_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    bank = (
        db.query(QuestionBank)
        .filter(QuestionBank.id == bank_id, QuestionBank.user_id == user.id)
        .first()
    )
    if not bank:
        raise HTTPException(status_code=404, detail="题库不存在")
    return BankDetail(
        **bank_to_out(bank).model_dump(),
        questions=[
            QuestionOut.model_validate(q)
            for q in sorted(bank.questions, key=lambda x: x.order_index)
        ],
    )


@router.post("", response_model=BankDetail)
def create_bank(
    data: BankCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    bank = QuestionBank(user_id=user.id, title=data.title)
    db.add(bank)
    db.flush()
    for i, q in enumerate(sorted(data.questions, key=lambda x: x.order_index)):
        db.add(
            Question(
                bank_id=bank.id,
                type=q.type,
                stem=q.stem,
                options=q.options,
                answer=q.answer,
                explanation=q.explanation,
                order_index=i,
            )
        )
    db.commit()
    db.refresh(bank)
    return get_bank(bank.id, user, db)


@router.post("/parse", response_model=ParseResult)
async def parse_upload(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    allowed = {".txt", ".xlsx", ".xls", ".docx", ".pdf"}
    ext = Path(file.filename or "").suffix.lower()
    if ext not in allowed:
        raise HTTPException(status_code=400, detail=f"不支持格式: {ext}")
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)
    try:
        return parse_file(tmp_path, file.filename or "upload")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"解析失败: {e}")
    finally:
        tmp_path.unlink(missing_ok=True)


@router.put("/{bank_id}/questions/{question_id}", response_model=QuestionOut)
def update_question(
    bank_id: int,
    question_id: int,
    data: QuestionUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    bank = (
        db.query(QuestionBank)
        .filter(QuestionBank.id == bank_id, QuestionBank.user_id == user.id)
        .first()
    )
    if not bank:
        raise HTTPException(status_code=404, detail="题库不存在")
    q = (
        db.query(Question)
        .filter(Question.id == question_id, Question.bank_id == bank_id)
        .first()
    )
    if not q:
        raise HTTPException(status_code=404, detail="题目不存在")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(q, field, value)
    db.commit()
    db.refresh(q)
    return q


@router.delete("/{bank_id}")
def delete_bank(
    bank_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    bank = (
        db.query(QuestionBank)
        .filter(QuestionBank.id == bank_id, QuestionBank.user_id == user.id)
        .first()
    )
    if not bank:
        raise HTTPException(status_code=404, detail="题库不存在")
    db.delete(bank)
    db.commit()
    return {"ok": True}
