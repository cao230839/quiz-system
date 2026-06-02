from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User, WrongAnswer
from app.schemas import QuestionOut, WrongAnswerOut

router = APIRouter(prefix="/api/wrong", tags=["wrong"])


@router.get("", response_model=List[WrongAnswerOut])
def list_wrong(
    include_mastered: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(WrongAnswer).filter(WrongAnswer.user_id == user.id)
    if not include_mastered:
        q = q.filter(WrongAnswer.mastered == False)
    items = q.order_by(WrongAnswer.created_at.desc()).all()
    return [
        WrongAnswerOut(
            id=w.id,
            question=QuestionOut.model_validate(w.question),
            mastered=w.mastered,
            created_at=w.created_at,
        )
        for w in items
    ]


@router.post("/{wrong_id}/master")
def mark_mastered(
    wrong_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    w = (
        db.query(WrongAnswer)
        .filter(WrongAnswer.id == wrong_id, WrongAnswer.user_id == user.id)
        .first()
    )
    if not w:
        raise HTTPException(status_code=404, detail="记录不存在")
    w.mastered = True
    db.commit()
    return {"ok": True}


@router.delete("/{wrong_id}")
def remove_wrong(
    wrong_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    w = (
        db.query(WrongAnswer)
        .filter(WrongAnswer.id == wrong_id, WrongAnswer.user_id == user.id)
        .first()
    )
    if not w:
        raise HTTPException(status_code=404, detail="记录不存在")
    db.delete(w)
    db.commit()
    return {"ok": True}
