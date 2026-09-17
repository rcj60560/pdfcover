"""OCR PDF → Recording 结构化 JSON。文本处理纯函数可单测。"""
from __future__ import annotations

import re

from pypdf import PdfReader

REC_RE = re.compile(r"Recording\s+(\d{1,2}[a-z])\b", re.I)
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


def clean_line(s: str) -> str:
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = re.sub(r"(?<![A-Za-z])[|!](?![A-Za-z])", "I", s)   # 独立 | / ! → I
    s = re.sub(r"\s+", " ", s)
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
                if clean_line(t.group(1)) in CREDITS_LABELS:
                    break   # 答案 Key / 版权页起,该 turn 及其后全部丢弃
                seg_end = tm[j + 1].start() if j + 1 < len(tm) else len(body)
                txt = clean_line(body[t.end():seg_end])
                if txt:
                    turns.append({"label": clean_line(t.group(1)), "text": txt})
        else:
            turns = [{"label": "", "text": clean_line(body)}] if clean_line(body) else []
        if turns:
            recs.append({"id": rid, "turns": turns})
    return recs


def extract_from_pdf(pdf_path: str) -> list[dict]:
    reader = PdfReader(str(pdf_path), strict=False)
    return parse_scripts([(p.extract_text() or "") for p in reader.pages])
