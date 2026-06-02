from __future__ import annotations

import re
from typing import Optional

from app.models import QuestionType
from app.schemas import QuestionCreate

_FULLWIDTH_OPTIONS = str.maketrans(
    "ＡＢＣＤＥＦＧＨａｂｃｄｅｆｇｈ",
    "ABCDEFGHabcdefgh",
)

QUESTION_NUM_LINE = re.compile(r"^(\d{1,3})[\.、．]\s*(.+)$")
QUESTION_START = re.compile(
    r"^[\s]*(?:"
    r"第?\s*(\d{1,3})\s*[题题\.、\)]"
    r"|[\(\（](\d{1,3})[\)\）][\.、]?"
    r"|Q(\d{1,3})[\.:：]"
    r")",
    re.IGNORECASE,
)
OPTION_LINE = re.compile(r"^[\s]*([A-Ha-h])[\.、．\)\）:：]\s*(.+)$")
# 不要求选项前有空格，兼容 A.xxxB.yyy
INLINE_OPTIONS = re.compile(
    r"([A-Ha-h])[\.、．\)\）:：]\s*"
    r"(.+?)"
    r"(?=[A-Ha-h][\.、．\)\）:：]|$)"
)
ANSWER_LINE = re.compile(
    r"^[\s]*(?:答案|正确答案|参考答案|答)[：:]\s*(.+)$",
    re.IGNORECASE,
)
EXPLAIN_LINE = re.compile(
    r"^[\s]*(?:解析|说明|解答|详解)[：:]\s*(.+)$",
    re.IGNORECASE,
)
JUDGE_KEYWORDS = re.compile(r"^(正确|错误|对|错|√|×|T|F|true|false|是|否)$", re.I)

SECTION_HEADER = re.compile(
    r"^[（(]?[一二三四五六七八九十百千\d]+[)）]?[、．.\s]*"
    r"(单选题|多选题|判断题|填空题|简答题|选择题|名词解释|论述题|"
    r"单项选择|多项选择|不定项选择|是非判断)"
    r"[：:\s]*$",
    re.I,
)
SECTION_TYPE_IN_LINE = re.compile(
    r"(单选题|多选题|判断题|填空题|简答题|单项选择题|多项选择题|不定项选择题|是非题)",
    re.I,
)
NOISE_LINE = re.compile(
    r"^(?:"
    r"第[一二三四五六七八九十百千\d]+[章节部分篇卷].*"
    r"|[【\[]?参考答案[】\]]?|答案与解析|答题须知|注意事项"
    r"|姓名[：:]|班级[：:]|学号[：:]|得分[：:]|总分[：:]"
    r"|.+?(试卷|习题集|练习题|题库|测验|考试题|复习题|模拟卷|真题卷)$"
    r")$",
    re.I,
)
STEM_HAS_QUESTION = re.compile(r"[？?]|下列|以下|是否正确|对错|说法|说法中|哪项|哪个|哪些|填空")

TYPE_HINTS = {
    QuestionType.multiple: re.compile(r"多选|多项选择|不定项|（多选）|\(多选\)", re.I),
    QuestionType.judge: re.compile(r"判断题|判断对错|（判断）|\(判断\)|是否正确", re.I),
    QuestionType.short: re.compile(r"简答题|简述|论述|阐述|说明理由|为什么|如何理解|谈谈你的", re.I),
    QuestionType.fill: re.compile(r"填空题|填空|____+"),
}

SECTION_TO_TYPE = {
    "单选": QuestionType.single,
    "单项": QuestionType.single,
    "多选": QuestionType.multiple,
    "多项": QuestionType.multiple,
    "不定项": QuestionType.multiple,
    "判断": QuestionType.judge,
    "是非": QuestionType.judge,
    "填空": QuestionType.fill,
    "简答": QuestionType.short,
    "论述": QuestionType.short,
    "名词": QuestionType.short,
}


def _normalize_text(s: str) -> str:
    return s.translate(_FULLWIDTH_OPTIONS)


def _normalize_choice_answer(answer: str) -> str:
    return re.sub(r"[\s,，、/|；;]+", "", answer.strip().upper())


def _is_multi_choice_answer(answer: str) -> bool:
    compact = _normalize_choice_answer(answer)
    if len(compact) <= 1:
        return False
    return all(c in "ABCDEFGH" for c in compact)


def detect_section_type(line: str) -> Optional[QuestionType]:
    m = SECTION_TYPE_IN_LINE.search(line)
    if not m:
        return None
    label = m.group(1)
    for key, qtype in SECTION_TO_TYPE.items():
        if key in label:
            return qtype
    return None


def is_noise_line(line: str) -> bool:
    s = _normalize_text(line.strip())
    if not s or len(s) <= 1:
        return True
    if SECTION_HEADER.match(s):
        return True
    if NOISE_LINE.match(s):
        return True
    if re.match(r"^[单多判填简]选题\s*$", s):
        return True
    # 纯章节名、试卷大标题（短且无问号）
    if len(s) <= 25 and not STEM_HAS_QUESTION.search(s) and not OPTION_LINE.match(s):
        if re.match(r"^[一二三四五六七八九十]+、", s):
            return True
        if not re.search(r"\d", s) and "题" in s and len(s) < 20:
            return True
    return False


def is_question_number_line(line: str) -> bool:
    s = _normalize_text(line.strip())
    m = QUESTION_NUM_LINE.match(s)
    if not m:
        return False
    num = int(m.group(1))
    rest = m.group(2).strip()
    # 排除年份被当成题号
    if 1900 <= num <= 2100 and len(rest) < 40 and not STEM_HAS_QUESTION.search(rest):
        return False
    if len(rest) < 2:
        return False
    return True


def _hint_type_from_stem(stem: str) -> QuestionType | None:
    for qtype, pattern in TYPE_HINTS.items():
        if pattern.search(stem):
            return qtype
    if re.search(r"判断", stem) and "单选" not in stem and "多选" not in stem:
        return QuestionType.judge
    return None


def detect_type(
    stem: str,
    options: list[str],
    answer: str,
    section_type: Optional[QuestionType] = None,
) -> QuestionType:
    ans = answer.strip()

    # 有多个选项时一律按选择题处理（题干中 ( ) 仅为选题空格，不是填空题）
    if options and len(options) >= 2:
        if _is_multi_choice_answer(ans):
            return QuestionType.multiple
        if section_type == QuestionType.multiple:
            return QuestionType.multiple
        if re.search(r"多选|不定项", stem, re.I):
            return QuestionType.multiple
        return QuestionType.single

    hinted = _hint_type_from_stem(stem)
    if hinted:
        return hinted

    if not options:
        if ans and JUDGE_KEYWORDS.match(ans):
            return QuestionType.judge
        if re.search(r"填空|____", stem):
            return QuestionType.fill
        if TYPE_HINTS[QuestionType.short].search(stem) or (
            ans and (len(ans) > 40 or "。" in ans)
        ):
            return QuestionType.short
        if section_type in (QuestionType.judge, QuestionType.short, QuestionType.fill):
            return section_type
        return QuestionType.fill if ans else QuestionType.short

    if _is_multi_choice_answer(ans):
        return QuestionType.multiple
    return QuestionType.single


def split_inline_options(text: str) -> tuple[list[str], str]:
    text = _normalize_text(text.strip())
    if not text:
        return [], ""

    matches = list(INLINE_OPTIONS.finditer(text))
    if len(matches) >= 2:
        options = [m.group(2).strip() for m in matches]
        prefix = text[: matches[0].start()].strip()
        return options, prefix

    line_m = OPTION_LINE.match(text)
    if line_m:
        return [line_m.group(2).strip()], ""

    return [], text


def expand_line_segments(line: str) -> list[str]:
    segments: list[str] = []
    for part in re.split(r"[\t\r\n]+", line):
        part = part.strip()
        if part:
            segments.append(part)
    return segments or [line.strip()]


def split_blocks(lines: list[str]) -> list[str]:
    """按题号切分；忽略噪声行。"""
    blocks: list[list[str]] = []
    current: list[str] = []

    def flush():
        nonlocal current
        if current:
            blocks.append(current)
            current = []

    for line in lines:
        s = line.strip()
        if not s or is_noise_line(s):
            flush()
            continue
        if is_question_number_line(s) or QUESTION_START.match(_normalize_text(s)):
            flush()
            current = [line]
        else:
            if not current:
                # 题目前的无编号题干行：仅在有选项/答案线索时并入下一题
                current = [line]
            else:
                current.append(line)

    flush()
    return ["\n".join(b) for b in blocks if b]


def _consume_segment(
    segment: str,
    stem_parts: list[str],
    options: list[str],
    answer: str,
    explanation: str,
) -> tuple[list[str], list[str], str, str]:
    stripped = _normalize_text(segment.strip())
    if not stripped or is_noise_line(stripped):
        return stem_parts, options, answer, explanation

    exp_m = EXPLAIN_LINE.match(stripped)
    if exp_m:
        return stem_parts, options, answer, exp_m.group(1).strip()

    ans_m = ANSWER_LINE.match(stripped)
    if ans_m:
        return stem_parts, options, ans_m.group(1).strip(), explanation

    inline_opts, stem_frag = split_inline_options(stripped)
    if inline_opts:
        options.extend(inline_opts)
        if stem_frag and not is_noise_line(stem_frag):
            stem_parts.append(stem_frag)
        return stem_parts, options, answer, explanation

    if is_noise_line(stripped):
        return stem_parts, options, answer, explanation

    if not stem_parts and QUESTION_START.match(stripped):
        stem_parts.append(re.sub(QUESTION_START, "", stripped).strip() or stripped)
    elif not stem_parts and is_question_number_line(stripped):
        m = QUESTION_NUM_LINE.match(stripped)
        stem_parts.append(m.group(2).strip() if m else stripped)
    else:
        stem_parts.append(stripped)

    return stem_parts, options, answer, explanation


def _strip_stem_number(stem: str) -> str:
    stem = QUESTION_START.sub("", stem).strip()
    m = QUESTION_NUM_LINE.match(stem)
    if m:
        stem = m.group(2).strip()
    return re.sub(r"\s+", " ", stem).strip()


def is_valid_question(
    stem: str,
    options: list[str],
    answer: str,
) -> bool:
    stem = _strip_stem_number(stem)
    if not stem or is_noise_line(stem):
        return False
    if SECTION_HEADER.match(stem):
        return False
    # 试卷大标题：很短、无选项、无答案、不像题干
    if (
        len(stem) <= 30
        and not options
        and not answer
        and not STEM_HAS_QUESTION.search(stem)
    ):
        return False
    if len(stem) < 4 and not options:
        return False
    # 选择题至少 2 个选项或已有答案
    if options and len(options) < 2 and not answer:
        return False
    return True


def parse_block(
    block: str,
    index: int,
    section_type: Optional[QuestionType] = None,
) -> QuestionCreate | None:
    block = _normalize_text(block)
    lines = [l for l in block.split("\n") if l.strip() and not is_noise_line(l)]
    if not lines:
        return None

    stem_parts: list[str] = []
    options: list[str] = []
    answer = ""
    explanation = ""

    for line in lines:
        for segment in expand_line_segments(line):
            stem_parts, options, answer, explanation = _consume_segment(
                segment, stem_parts, options, answer, explanation
            )

    stem = _strip_stem_number(" ".join(stem_parts))
    if not is_valid_question(stem, options, answer):
        return None

    qtype = detect_type(stem, options, answer, section_type)
    return QuestionCreate(
        type=qtype,
        stem=stem,
        options=options or None,
        answer=answer,
        explanation=explanation or None,
        order_index=index,
    )


_QUESTION_NUM_PATTERNS = (
    re.compile(r"^(\d{1,4})[\.、．]\s*"),
    re.compile(r"^第\s*(\d{1,4})\s*题"),
    re.compile(r"^[Qq](\d{1,4})[\.:：]"),
    re.compile(r"^[\(（](\d{1,4})[\)）]"),
)


def extract_question_number(stem: str, fallback: int) -> int:
    """从题干提取题号，用于 1、2、3… 排序。"""
    s = _normalize_text(stem.strip())
    for pat in _QUESTION_NUM_PATTERNS:
        m = pat.match(s)
        if m:
            num = int(m.group(1))
            if 1 <= num <= 9999:
                return num
    return fallback


def sort_questions_by_number(questions: list[QuestionCreate]) -> list[QuestionCreate]:
    if len(questions) <= 1:
        return questions
    indexed = list(enumerate(questions))
    indexed.sort(
        key=lambda item: (
            extract_question_number(item[1].stem, 1_000_000 + item[0]),
            item[0],
        )
    )
    for i, (_, q) in enumerate(indexed):
        q.order_index = i
    return [q for _, q in indexed]


def parse_lines(
    lines: list[str],
    title: str = "导入题库",
) -> list[QuestionCreate]:
    """解析行列表；自动跳过标题/章节，并按章节推断题型。"""
    cleaned: list[str] = []
    section_type: Optional[QuestionType] = None

    for line in lines:
        s = line.strip()
        if not s:
            continue
        st = detect_section_type(s)
        if st is not None:
            section_type = st
            continue
        if is_noise_line(s):
            continue
        cleaned.append(s)

    blocks = split_blocks(cleaned)
    questions: list[QuestionCreate] = []
    for i, block in enumerate(blocks):
        q = parse_block(block, len(questions), section_type)
        if q:
            questions.append(q)
            q.order_index = len(questions) - 1

    return sort_questions_by_number(questions)


def parse_text_content(text: str, title: str = "导入题库") -> list[QuestionCreate]:
    lines = [l for l in text.replace("\r\n", "\n").split("\n") if l.strip()]
    return parse_lines(lines, title=title)
