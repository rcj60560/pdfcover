"""OCR PDF → Recording 结构化 JSON。文本处理纯函数可单测。"""
from __future__ import annotations

import re
from pathlib import Path

from pypdf import PdfReader

REC_RE = re.compile(r"Recording\s+(\d{1,2}[a-z])\b", re.I)
TURN_RE = re.compile(r"(?:^|\n)\s*([A-Z][A-Za-z .'-]{0,30}):\s")


def clean_line(s: str) -> str:
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = re.sub(r"(?<![A-Za-z])[|!](?![A-Za-z])", "I", s)   # 独立 | / ! → I
    s = re.sub(r"\s+", " ", s)
    return s.strip()


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
        if tm:
            turns = []
            for j, t in enumerate(tm):
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
