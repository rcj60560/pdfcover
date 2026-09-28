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


def build(src_root: Path, ecdict_path: Path, level: str = "gk") -> dict:
    import datetime
    import ecdict as ecdict_mod

    docs = sorted(p for p in src_root.rglob("*.md") if "`" in p.read_text(encoding="utf-8")[:400])
    sentences: list[tuple[str, str]] = []      # (句子, 来源)
    token_case: dict[str, list[bool]] = {}     # token -> 是否首字母大写(专名判定)
    counts: dict[str, int] = {}
    for path in docs:
        text = path.read_text(encoding="utf-8")
        title = doc_title(text)
        lines = md_english_lines(text)
        sentences.extend((s, title) for s in split_sentences(lines))
        for line in lines:
            for raw in re.findall(r"[A-Za-z]{2,}", line):
                low = raw.lower()
                counts[low] = counts.get(low, 0) + 1
                token_case.setdefault(low, []).append(raw[0].isupper())

    entries, lemmas = ecdict_mod.load_for_tokens(ecdict_path, set(counts))

    stats = {"total": 0, "known": 0, "candidate": 0, "dropped": 0}
    lemma_counts: dict[str, int] = {}
    lemma_variants: dict[str, set[str]] = {}
    for token, n in counts.items():
        always_cap = all(token_case[token]) and counts[token] >= 2
        stats["total"] += 1 if lemmas[token] not in lemma_counts else 0
        lemma_counts[lemmas[token]] = lemma_counts.get(lemmas[token], 0) + n
        lemma_variants.setdefault(lemmas[token], set()).add(token)

    words = []
    for lemma in sorted(lemma_counts, key=lambda w: -lemma_counts[w]):
        entry = entries.get(lemma) or entries.get(next(iter(lemma_variants[lemma])))
        kind = classify(entry, level)
        if kind == "drop" or (entry is None and lemma_counts[lemma] < 2):
            stats["dropped"] += 1
            continue
        stats[kind] += 1
        if kind == "candidate":
            words.append({
                "w": lemma,
                "phon": entry.get("phon", "") if entry else "",
                "def": (entry.get("translation", "") if entry else "").replace("\n", "; "),
                "tags": entry.get("tag", "") if entry else "",
                "sents": pick_sentences(lemma_variants[lemma] | {lemma}, sentences),
            })
    stats["total"] = len(lemma_counts)
    return {
        "version": 1,
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "words": words, "stats": stats,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="字幕库 → vocab.json 词池")
    ap.add_argument("--src", type=Path, default=None)
    ap.add_argument("--ecdict", type=Path, default=TOOL_DIR.parents[1] / "tmp" / "ecdict" / "stardict.db")
    ap.add_argument("--out", type=Path, default=TOOL_DIR / "web" / "vocab.json")
    ap.add_argument("--level", default="gk", choices=["zk", "gk", "cet4"])
    args = ap.parse_args()
    src = args.src
    if src is None:
        cfg = json.loads((TOOL_DIR.parent / "subtitle-viewer" / "config.json").read_text(encoding="utf-8"))
        src = Path(cfg["src_root"])
    if not args.ecdict.is_file():
        raise SystemExit(f"找不到 ECDICT sqlite:{args.ecdict}\n"
                         "从 https://github.com/skywind3000/ecdict releases 下载 ecdict-sqlite-28.zip,"
                         "解压出 stardict.db 放到 tmp/ecdict/(或用 --ecdict 指路)")
    result = build(src, args.ecdict, args.level)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    s = result["stats"]
    print(f"词池 {s['total']}(已会 {s['known']} · 生词候选 {s['candidate']} · 丢弃 {s['dropped']})"
          f" → {args.out}({args.out.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
