from __future__ import annotations

import random
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Question, QuestionBank, QuestionType, User, WrongAnswer
from app.schemas import AnswerResult, AnswerSubmit, QuizStart, QuestionOut

router = APIRouter(prefix="/api/quiz", tags=["quiz"])

_sessions: dict[str, dict] = {}


_FULLWIDTH_CHOICES = str.maketrans(
    "ＡＢＣＤＥＦＧＨａｂｃｄｅｆｇｈ",
    "ABCDEFGHabcdefgh",
)

_CHOICE_LETTERS = re.compile(r"[A-H]")


def normalize_answer(s: str) -> str:
    return (
        s.strip()
        .translate(_FULLWIDTH_CHOICES)
        .upper()
        .replace("，", ",")
        .replace("、", ",")
        .replace(" ", "")
        .replace("正确", "T")
        .replace("错误", "F")
        .replace("对", "T")
        .replace("错", "F")
    )


def extract_choice_letters(s: str) -> str:
    """只提取 A-H 选项字母，忽略 D. / D、 等标点。"""
    return "".join(sorted(set(_CHOICE_LETTERS.findall(normalize_answer(s)))))


def primary_choice_letter(s: str) -> str | None:
    letters = extract_choice_letters(s)
    if len(letters) == 1:
        return letters
    compact = normalize_answer(s)
    m = re.match(r"^[\(（]?([A-H])[\.．、\)\）:：]?", compact)
    return m.group(1) if m else None


def _match_by_options(q: Question, user_answer: str, correct_answer: str) -> bool:
    if not q.options:
        return False
    ua_letter = primary_choice_letter(user_answer)
    ca_letter = primary_choice_letter(correct_answer)
    ua_text = user_answer.strip()
    ca_text = correct_answer.strip()
    for i, opt in enumerate(q.options):
        letter = "ABCDEFGH"[i]
        opt_s = opt.strip()
        ca_hit = ca_text == opt_s or ca_text == letter or ca_letter == letter
        ua_hit = ua_text == opt_s or ua_text == letter or ua_letter == letter
        if ca_hit and ua_hit:
            return True
    return False


def _match_single_or_fill(q: Question, user_answer: str, correct_answer: str) -> bool:
    ua = normalize_answer(user_answer)
    ca = normalize_answer(correct_answer)
    if ua == ca:
        return True
    ua_l = primary_choice_letter(user_answer)
    ca_l = primary_choice_letter(correct_answer)
    if ua_l and ca_l and ua_l == ca_l:
        return True
    return _match_by_options(q, user_answer, correct_answer)


def check_answer(q: Question, user_answer: str, self_assessed: bool | None) -> AnswerResult:
    if q.type == QuestionType.short:
        return AnswerResult(
            correct=self_assessed or False,
            correct_answer=q.answer,
            explanation=q.explanation,
            show_self_assess=True,
        )
    ua = normalize_answer(user_answer)
    ca = normalize_answer(q.answer)
    if q.type == QuestionType.multiple:
        ua_letters = extract_choice_letters(user_answer)
        ca_letters = extract_choice_letters(q.answer)
        correct = ua_letters == ca_letters and len(ca_letters) > 0
    elif q.type == QuestionType.judge:
        true_set = {"T", "TRUE", "1", "YES", "Y"}
        false_set = {"F", "FALSE", "0", "NO", "N"}

        def as_bool(v: str) -> str | None:
            if v in true_set:
                return "T"
            if v in false_set:
                return "F"
            return None

        ua_b, ca_b = as_bool(ua), as_bool(ca)
        correct = (
            ua_b is not None and ca_b is not None and ua_b == ca_b
        ) or ua == ca
        if not correct and q.options:
            correct = _match_single_or_fill(q, user_answer, q.answer)
    else:
        correct = _match_single_or_fill(q, user_answer, q.answer)
    return AnswerResult(
        correct=correct,
        correct_answer=q.answer,
        explanation=q.explanation,
        show_self_assess=False,
    )


@router.post("/start")
def start_quiz(
    data: QuizStart,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    bank = (
        db.query(QuestionBank)
        .filter(QuestionBank.id == data.bank_id, QuestionBank.user_id == user.id)
        .first()
    )
    if not bank:
        raise HTTPException(status_code=404, detail="题库不存在")

    ids = [q.id for q in sorted(bank.questions, key=lambda x: x.order_index)]

    if data.wrong_only:
        wrong_ids = {
            w.question_id
            for w in db.query(WrongAnswer)
            .filter(WrongAnswer.user_id == user.id, WrongAnswer.mastered == False)
            .all()
        }
        ids = [i for i in ids if i in wrong_ids]
        if not ids:
            raise HTTPException(status_code=400, detail="错题本为空")

    if data.shuffle:
        random.shuffle(ids)
    elif not data.wrong_only:
        pass

    if data.count and data.count < len(ids):
        ids = ids[: data.count]

    if not ids:
        raise HTTPException(status_code=400, detail="题库无题目")

    session_id = str(uuid.uuid4())
    _sessions[session_id] = {
        "user_id": user.id,
        "question_ids": ids,
        "current_index": 0,
    }
    return {
        "session_id": session_id,
        "question_ids": ids,
        "total": len(ids),
    }


@router.get("/session/{session_id}/current")
def current_question(
    session_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sess = _sessions.get(session_id)
    if not sess or sess["user_id"] != user.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    idx = sess["current_index"]
    ids = sess["question_ids"]
    if idx >= len(ids):
        return {"finished": True, "index": idx, "total": len(ids)}
    q = db.query(Question).filter(Question.id == ids[idx]).first()
    out = QuestionOut.model_validate(q)
    safe = out.model_dump()
    safe.pop("answer")
    return {
        "finished": False,
        "index": idx,
        "total": len(ids),
        "question": safe,
    }


@router.post("/answer", response_model=AnswerResult)
def submit_answer(
    data: AnswerSubmit,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sess = _sessions.get(data.session_id)
    if not sess or sess["user_id"] != user.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    q = db.query(Question).filter(Question.id == data.question_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="题目不存在")

    result = check_answer(q, data.user_answer, data.self_assessed_correct)

    if not result.correct:
        existing = (
            db.query(WrongAnswer)
            .filter(
                WrongAnswer.user_id == user.id,
                WrongAnswer.question_id == q.id,
            )
            .first()
        )
        if existing:
            existing.mastered = False
        else:
            db.add(WrongAnswer(user_id=user.id, question_id=q.id))
        db.commit()

    return result


@router.get("/session/{session_id}/reveal/{question_id}")
def reveal_answer(
    session_id: str,
    question_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sess = _sessions.get(session_id)
    if not sess or sess["user_id"] != user.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    q = db.query(Question).filter(Question.id == question_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="题目不存在")
    if q.type != QuestionType.short:
        raise HTTPException(status_code=400, detail="仅简答题支持查看答案")
    return {"correct_answer": q.answer, "explanation": q.explanation}


@router.post("/session/{session_id}/navigate")
def navigate(
    session_id: str,
    direction: str,
    user: User = Depends(get_current_user),
):
    sess = _sessions.get(session_id)
    if not sess or sess["user_id"] != user.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    if direction == "prev" and sess["current_index"] > 0:
        sess["current_index"] -= 1
    elif direction == "next" and sess["current_index"] < len(sess["question_ids"]) - 1:
        sess["current_index"] += 1
    return {"index": sess["current_index"], "total": len(sess["question_ids"])}


@router.post("/session/{session_id}/goto/{index}")
def goto_index(
    session_id: str,
    index: int,
    user: User = Depends(get_current_user),
):
    sess = _sessions.get(session_id)
    if not sess or sess["user_id"] != user.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    if 0 <= index < len(sess["question_ids"]):
        sess["current_index"] = index
    return {"index": sess["current_index"], "total": len(sess["question_ids"])}
