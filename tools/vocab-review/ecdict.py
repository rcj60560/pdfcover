"""ECDICT sqlite(stardict.db)只读访问:为给定 token 集合取词条并解析词形原形。"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

_EX_LINK = re.compile(r"(?:^|/)([01]):([^/]+)")
_CHUNK = 400


def _lemma_of(exchange: str, word: str) -> str:
    """exchange 的 0:/1: 段指向原形;解析不到返回自身。"""
    for m in _EX_LINK.finditer(exchange or ""):
        return m.group(2)
    return word


def load_for_tokens(db_path: Path, tokens: set[str]) -> tuple[dict[str, dict], dict[str, str]]:
    wanted = sorted({t.lower() for t in tokens})
    entries: dict[str, dict] = {}
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        for start in range(0, len(wanted), _CHUNK):
            chunk = wanted[start:start + _CHUNK]
            marks = ",".join("?" * len(chunk))
            for word, phonetic, translation, exchange, frq, tag in con.execute(
                    f"SELECT word, phonetic, translation, exchange, frq, tag"
                    f" FROM stardict WHERE word IN ({marks})", chunk):
                entries[word.lower()] = {
                    "word": word,
                    "phon": (phonetic or "").strip(),
                    "translation": (translation or "").strip(),
                    "exchange": (exchange or "").strip(),
                    "frq": int(frq or 0),
                    "tag": (tag or "").strip(),
                }
    finally:
        con.close()
    lemmas = {t: _lemma_of(entries[t]["exchange"], t) if t in entries else t for t in wanted}
    return entries, lemmas
