from __future__ import annotations

from pathlib import Path

import pdfplumber

from app.parsers.common import parse_text_content
from app.schemas import ParseResult


def parse_pdf(path: Path) -> ParseResult:
    parts: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                parts.append(t)
    text = "\n\n".join(parts)
    questions = parse_text_content(text, path.stem)
    return ParseResult(title=path.stem, questions=questions)
