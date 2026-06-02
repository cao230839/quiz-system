import re
from pathlib import Path

from app.parsers.txt_parser import parse_txt
from app.parsers.xlsx_parser import parse_xlsx
from app.parsers.docx_parser import parse_docx
from app.parsers.pdf_parser import parse_pdf
from app.schemas import ParseResult


def parse_file(path: Path, filename: str) -> ParseResult:
    ext = Path(filename).suffix.lower()
    if ext == ".txt":
        return parse_txt(path)
    if ext in (".xlsx", ".xls"):
        return parse_xlsx(path)
    if ext == ".docx":
        return parse_docx(path)
    if ext == ".pdf":
        return parse_pdf(path)
    raise ValueError(f"不支持的文件格式: {ext}")
