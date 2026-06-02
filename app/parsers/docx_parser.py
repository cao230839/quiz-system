from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.parsers.common import (
    _consume_segment,
    _strip_stem_number,
    detect_type,
    expand_line_segments,
    is_noise_line,
    is_question_number_line,
    is_valid_question,
    parse_lines,
    sort_questions_by_number,
    split_inline_options,
)
from app.schemas import ParseResult, QuestionCreate


def _is_heading_style(para: Paragraph) -> bool:
    name = (para.style.name if para.style else "") or ""
    lower = name.lower()
    if "heading" in lower or "title" in lower or "subtitle" in lower:
        return True
    if name in ("标题", "标题 1", "标题 2", "标题 3", "副标题"):
        return True
    return False


def _dedupe_adjacent(cells: list[str]) -> list[str]:
    out: list[str] = []
    prev = None
    for c in cells:
        if c and c != prev:
            out.append(c)
            prev = c
    return out


def _finalize_block(lines: list[str]) -> QuestionCreate | None:
    if not lines:
        return None
    stem_parts: list[str] = []
    options: list[str] = []
    answer = ""
    explanation = ""
    for line in lines:
        for seg in expand_line_segments(line):
            stem_parts, options, answer, explanation = _consume_segment(
                seg, stem_parts, options, answer, explanation
            )
    stem = _strip_stem_number(" ".join(stem_parts))
    if not is_valid_question(stem, options, answer):
        return None
    return QuestionCreate(
        type=detect_type(stem, options, answer),
        stem=stem,
        options=options or None,
        answer=answer,
        explanation=explanation or None,
        order_index=0,
    )


def _parse_table(table: Table) -> list[QuestionCreate]:
    rows_raw: list[list[str]] = []
    for row in table.rows:
        cells = _dedupe_adjacent([c.text.strip() for c in row.cells if c.text.strip()])
        if cells:
            rows_raw.append(cells)
    if not rows_raw:
        return []

    questions: list[QuestionCreate] = []
    start = 0
    if rows_raw and any(
        k in "".join(rows_raw[0]) for k in ("题干", "题目", "序号", "题号", "选项", "答案")
    ):
        start = 1

    buffer: list[str] = []

    def flush_buffer() -> None:
        nonlocal buffer
        q = _finalize_block(buffer)
        buffer = []
        if q:
            q.order_index = len(questions)
            questions.append(q)

    for cells in rows_raw[start:]:
        joined = " ".join(cells)
        if is_noise_line(joined):
            flush_buffer()
            continue

        if len(cells) >= 3:
            flush_buffer()
            stem = cells[1] if is_question_number_line(cells[0]) else cells[0]
            opts: list[str] = []
            ans = ""
            exp = ""
            for c in cells[2:]:
                inline, frag = split_inline_options(c)
                if inline:
                    opts.extend(inline)
                elif re.match(r"^答案", c):
                    ans = re.sub(r"^答案[：:]\s*", "", c).strip()
                elif re.match(r"^解析", c):
                    exp = re.sub(r"^解析[：:]\s*", "", c).strip()
                elif frag and not is_noise_line(frag):
                    stem = f"{stem} {frag}".strip()
            stem = _strip_stem_number(stem)
            if is_valid_question(stem, opts, ans):
                questions.append(
                    QuestionCreate(
                        type=detect_type(stem, opts, ans),
                        stem=stem,
                        options=opts or None,
                        answer=ans,
                        explanation=exp or None,
                        order_index=len(questions),
                    )
                )
            continue

        if len(cells) == 1 or (len(cells) == 2 and is_question_number_line(cells[0])):
            flush_buffer()
            buffer = list(cells)
            flush_buffer()
            continue

        buffer.extend(cells)

    flush_buffer()
    return questions


def _paragraph_lines(para: Paragraph) -> list[str]:
    text = para.text.strip()
    if not text:
        return []
    out: list[str] = []
    for sub in re.split(r"[\r\n]+", text):
        sub = sub.strip()
        if sub and not is_noise_line(sub):
            out.append(sub)
    return out


def parse_docx(path: Path) -> ParseResult:
    doc = Document(path)
    questions: list[QuestionCreate] = []
    pending_lines: list[str] = []

    def flush_paragraphs() -> None:
        nonlocal pending_lines
        if pending_lines:
            questions.extend(parse_lines(pending_lines, path.stem))
            pending_lines = []

    body = doc.element.body
    for child in body:
        tag = child.tag.split("}")[-1]
        if tag == "p":
            para = Paragraph(child, doc)
            if _is_heading_style(para):
                text = para.text.strip()
                if text:
                    # 章节标题行交给 parse_lines 识别题型，不作为独立题目
                    pending_lines.append(text)
                continue
            pending_lines.extend(_paragraph_lines(para))
        elif tag == "tbl":
            flush_paragraphs()
            table = Table(child, doc)
            table_qs = _parse_table(table)
            if table_qs:
                questions.extend(table_qs)
            else:
                for row in table.rows:
                    for cell in _dedupe_adjacent([c.text.strip() for c in row.cells]):
                        pending_lines.extend(_paragraph_lines_from_text(cell))
    flush_paragraphs()

    questions = sort_questions_by_number(questions)

    return ParseResult(title=path.stem, questions=questions)


def _paragraph_lines_from_text(text: str) -> list[str]:
    out: list[str] = []
    for sub in re.split(r"[\r\n\t]+", text.strip()):
        sub = sub.strip()
        if sub and not is_noise_line(sub):
            out.append(sub)
    return out
