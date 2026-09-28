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


KNOWN_TIERS = ["zk", "gk"]
CANDIDATE_TIERS = ["cet4", "cet6", "ky", "toefl", "ielts", "gre"]
FREQ_KNOWN_RANK = 5000      # 无标签但 COCA 排名前 5000 视为常用已会


def classify(entry: dict | None, level: str = "gk") -> str:
    """按 ECDICT 标签/词频划线;level 可上调(如 cet4)扩大已会范围。"""
    if not entry:
        return "drop"
    tags = set((entry["tag"] or "").split())
    known_tiers = KNOWN_TIERS[:KNOWN_TIERS.index(level) + 1] if level in KNOWN_TIERS else KNOWN_TIERS
    if tags & set(known_tiers):
        return "known"
    if tags & set(CANDIDATE_TIERS):
        return "candidate"
    if entry["frq"] <= 0:
        return "drop"
    if 0 < entry["frq"] <= FREQ_KNOWN_RANK:
        return "known"
    return "candidate"


def pick_sentences(variants: set[str], sentences: list[tuple[str, str]], limit: int = 2) -> list[dict]:
    """按词数降序取前 limit 条例句——取上下文更足的长句。"""
    hits = [(len(en.split()), en, src) for en, src in sentences
            if variants & set(tokenize(en))]
    hits.sort(key=lambda h: -h[0])
    return [{"en": en, "from": src} for _, en, src in hits[:limit]]
