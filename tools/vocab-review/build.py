"""vocab-review 词池构建:字幕 md → 划线生词 + 例句 → vocab.json。用法:

    python build.py [--src 目录] [--ecdict csv] [--out web/vocab.json] [--level gk]
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parent
_BOLD_LINE = re.compile(r"^\*\*(.+)\*\*$")
_TOKEN = re.compile(r"[a-z]{2,}")
_SENT_SPLIT = re.compile(r"(?<=[.?!])\s+")


def md_english_lines(md_text: str) -> list[str]:
    out = []
    for line in md_text.splitlines():
        m = _BOLD_LINE.match(line.strip())
        if m:
            out.append(m.group(1).strip())
    return out


def doc_title(md_text: str) -> str:
    for line in md_text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return "未命名"


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def split_sentences(lines: list[str]) -> list[str]:
    out = []
    for line in lines:
        for sent in _SENT_SPLIT.split(line):
            sent = sent.strip()
            if 3 <= len(sent.split()) <= 30:
                out.append(sent)
    return out
