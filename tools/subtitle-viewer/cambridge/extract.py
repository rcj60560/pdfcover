"""OCR PDF → Recording 结构化 JSON。文本处理纯函数可单测。"""
from __future__ import annotations

import re

from pypdf import PdfReader

# 无字母后缀的单元唯一录音(Unit 16/18/21 的 Recording 16/18/21)编号同样合法。
# 大小写敏感:正文小写 “recording” 后跟换行/页码(如 “in the recording\n3.3”)
# 不得误判为标题;后缀字母允许大写,parse_scripts 里统一 lower()。
REC_RE = re.compile(r"Recording\s+(\d{1,2}[A-Za-z]?)\b")
TURN_RE = re.compile(r"(?:^|\n)\s*([A-Z][A-Za-z0-9 .'-]{0,30}):\s")
# 无冒号说话人(如 22b 的 A–J 枚举行):行首单字母 + 空格 + 至少一个词
NOCOLON_RE = re.compile(r"(?:^|\n)([A-Z]) (?=\S)")
# 答案 Key / 版权页标签:命中即截断该录音后续内容
CREDITS_LABELS = {
    "Key",
    "Picture research",
    "Text design and page make-up",
    "Concept design",
    "Illustrations",
}
# OCR 文本层漏检的标题(书页视觉上有):正文被并入上一条录音。
# (rec_id, 正文起点标志) —— 标志必须在全文恰好出现一次,否则换书时抛错,
# 防止静默错切。
MISSING_HEADINGS = [
    # 6a 必须用含撇号全串:截短的 "French teacher, but" 会把 “I'm a ” 残留在
    # 5c 词表 turn 尾部、6a 首 turn 缺开头。底本撇号为 ASCII '(U+2019 计 0 次)。
    ("6a", "I'm a French teacher, but"),
    ("8b", "Welcome once again to"),
]
# 无字母后缀的录音标题:OCR 文本层可能粘在上一条词表行中,REC_RE 按行
# 切不开(如 20c 词表行中的「Recording 21」),预处理在其前强制换行。
# 标志全文出现次数必须恰好 1,否则换书时抛错。
MIDLINE_HEADINGS = ["Recording 16", "Recording 18", "Recording 21"]
# OCR 噪声定点覆盖:(rec_id, 原样噪声串, 替换串, 期望出现次数)。原样串取自
# 底本 OCR 原文(含换行),只作用于对应录音的正文范围;出现次数必须与期望
# 完全一致,否则换书时抛 ValueError,绝不静默放过或误伤其他录音。
# 词表/独白尾部的乱码串是页脚页码区的误读,整串删除;6a 尾部页脚残迹
# 「160 P\E\ 18」同理(旧版尾部页码剥除恰好削掉 “ 18”,收窄规则后完整
# 暴露,索性整段清除);CO» 是 CO₂(下标 2)的 OCR 误读。
TEXT_OVERRIDES = [
    ("15b", " :\neo onronorh@®bhb =\nwack", "", 1),
    ("22a", "\neo onoaoh@Q hb =\noh\n166\nP\\e\\ 18", "", 1),
    ("6a", "\n160\nP\\E\\ 18", "", 1),
    ("16", "CO»", "CO₂", 3),
]


def _normalize_chars(s: str) -> str:
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = re.sub(r"(?<![A-Za-z])[|!](?![A-Za-z])", "I", s)   # 独立 | / ! → I
    return re.sub(r"\s+", " ", s).strip()


def clean_label(s: str) -> str:
    """说话人标签清理:保留「Speaker 1」等数字,不做页码/页眉剥离。"""
    return _normalize_chars(s)


def clean_line(s: str) -> str:
    """正文清理:在标签清理之上,剥页边界混入的页眉与裸页码残迹。"""
    s = _normalize_chars(s)
    s = re.sub(r"\b\d{1,3}\s+Recording scripts\b", " ", s)  # 页眉「157 Recording scripts」
    s = re.sub(r"\bRecording scripts\b", " ", s)  # 页码被 OCR 误读(如「eg」)的裸页眉
    s = re.sub(r"\s+", " ", s)
    # 首尾裸页码 token:仅当剩余非空才剥(纯页码行保持原样,由空文本判断丢弃);
    # (?!\d)/(?<!\d) 防止把 2010 这类四位数拦腰截断
    lead = re.sub(r"^\d{1,3}(?!\d)\s*", "", s)
    if lead:
        s = lead
    # 尾部裸页码还要求数字前紧邻句末标点或逗号(句子/词表结尾跨页粘页码的语境),
    # 否则 “Statement 1” 这类词+空格+数字组合(15a 题号)会被误吃
    tail = re.sub(r"(?<=[.,;:!?])\s*(?<!\d)\d{1,3}$", "", s)
    if tail:
        s = tail
    return s.strip()


def _no_colon_turns(body: str, nm: list, first_colon: int) -> list[dict]:
    """A–J 枚举格式:只保留枚举段,其后内容(词汇附录/来源/版权页)整体丢弃。

    枚举段终点取「首个空行」与「首个冒号匹配」中较早者,避免最后一条把
    书末附录整段吸进 text(22b 场景)。
    """
    run_end = len(body)
    blank = body.find("\n\n", nm[-1].end())
    if blank != -1:
        run_end = min(run_end, blank)
    if first_colon != -1:
        run_end = min(run_end, first_colon)
    turns = []
    for j, m in enumerate(nm):
        seg_end = nm[j + 1].start() if j + 1 < len(nm) else run_end
        txt = clean_line(body[m.end():seg_end])
        if txt:
            turns.append({"label": m.group(1), "text": txt})
    return turns


def parse_scripts(pages_text: list[str]) -> list[dict]:
    text = "\n".join(pages_text)
    marks = [(m.start(), m.group(1).lower()) for m in REC_RE.finditer(text)]
    recs = []
    for i, (pos, rid) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        body = text[pos:end]
        nl = body.find("\n")
        body = body[nl + 1:] if nl != -1 else ""
        tm = list(TURN_RE.finditer(body))
        # 保守门:无冒号行仅在「首个冒号匹配之前」(或全无冒号)且成组出现
        # (>=2 行)才视为说话人,避免误伤正文里偶发的行首 “A …”。
        first_colon = tm[0].start() if tm else -1
        gate_end = first_colon if first_colon != -1 else len(body)
        nm = [m for m in NOCOLON_RE.finditer(body) if m.start() < gate_end]
        if len(nm) >= 2:
            turns = _no_colon_turns(body, nm, first_colon)
        elif tm:
            turns = []
            for j, t in enumerate(tm):
                if clean_label(t.group(1)) in CREDITS_LABELS:
                    break   # 答案 Key / 版权页起,该 turn 及其后全部丢弃
                seg_end = tm[j + 1].start() if j + 1 < len(tm) else len(body)
                txt = clean_line(body[t.end():seg_end])
                if txt:
                    turns.append({"label": clean_label(t.group(1)), "text": txt})
        else:
            turns = [{"label": "", "text": clean_line(body)}] if clean_line(body) else []
        if turns:
            recs.append({"id": rid, "turns": turns})
    return recs


def inject_missing_headings(pages_text: list[str]) -> list[str]:
    """在漏检标题对应正文起点前插入 ``Recording {id}`` 行,返回新页文本。

    每个标志在全文必须恰好出现一次(0 次或多次都说明底本变了),否则
    ValueError,绝不静默错切。
    """
    text = "\n".join(pages_text)
    for recording_id, marker in MISSING_HEADINGS:
        count = text.count(marker)
        if count != 1:
            raise ValueError(
                f"missing-heading marker {marker!r} for Recording {recording_id} "
                f"appears {count} times (expected exactly 1)"
            )
    for recording_id, marker in MISSING_HEADINGS:
        text = text.replace(marker, f"Recording {recording_id}\n{marker}", 1)
    return text.split("\n")


def split_midline_headings(pages_text: list[str]) -> list[str]:
    """把粘在上一条词表行中的无字母标题前后插入换行,返回新行列表。

    标题前换行把它与上一条词表切开;标题后换行保住与标题同行、原本会
    被 parse_scripts 丢弃的正文。每个标志在全文必须恰好出现一次
    (0 次或多次都说明底本变了),否则 ValueError,绝不静默错切。
    """
    text = "\n".join(pages_text)
    for marker in MIDLINE_HEADINGS:
        count = text.count(marker)
        if count != 1:
            raise ValueError(
                f"midline heading {marker!r} appears {count} times "
                f"(expected exactly 1)"
            )
    for marker in MIDLINE_HEADINGS:
        text = text.replace(marker, "\n" + marker + "\n", 1)
    return text.split("\n")


def _recording_body_span(text: str, recording_id: str) -> tuple[int, int] | None:
    """Return the (start, end) char span of one recording's body, or None."""
    marks = [(m.start(), m.group(1).lower()) for m in REC_RE.finditer(text)]
    for i, (pos, rid) in enumerate(marks):
        if rid != recording_id:
            continue
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        nl = text.find("\n", pos, end)
        return (nl + 1 if nl != -1 else end, end)
    return None


def apply_text_overrides(pages_text: list[str]) -> list[str]:
    """按 TEXT_OVERRIDES 对指定录音正文做定点噪声清理,返回新页文本。

    每条覆盖的噪声串必须在其录音正文范围内恰好出现 ``expected`` 次
    (0 次或次数变动都说明底本变了),否则 ValueError,绝不静默放过。
    """
    text = "\n".join(pages_text)
    for recording_id, old, new, expected in TEXT_OVERRIDES:
        span = _recording_body_span(text, recording_id)
        if span is None:
            raise ValueError(
                f"text override for Recording {recording_id}: recording not found"
            )
        start, end = span
        found = text.count(old, start, end)
        if found != expected:
            raise ValueError(
                f"text override {old!r} for Recording {recording_id} appears "
                f"{found} times (expected exactly {expected})"
            )
        text = text[:start] + text[start:end].replace(old, new) + text[end:]
    return text.split("\n")


def extract_from_pdf(pdf_path: str) -> list[dict]:
    reader = PdfReader(str(pdf_path), strict=False)
    pages = [(p.extract_text() or "") for p in reader.pages]
    return parse_scripts(apply_text_overrides(
        split_midline_headings(inject_missing_headings(pages))))
