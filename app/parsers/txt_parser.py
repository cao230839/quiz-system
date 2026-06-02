from pathlib import Path

from app.parsers.common import parse_text_content
from app.schemas import ParseResult


def parse_txt(path: Path) -> ParseResult:
    text = path.read_text(encoding="utf-8", errors="ignore")
    questions = parse_text_content(text, path.stem)
    return ParseResult(title=path.stem, questions=questions)
