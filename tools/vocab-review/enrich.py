"""雅思词书增强层:vocab.json + 有道/新东方雅思词书(JSONL)→ vocab-beta.json。

词池每个词若在词书命中(headWord 小写对齐),追加可选字段——绝不改动已有字段:
  enDef    英英释义:全部命中词书的 tranOther 去重后 " ; " 连接
  phrases  短语前 3:跨词书合并,按短语原文去重
  ydSents  词书例句前 2:多本命中时排前的词书(默认有道 IELTSluan_2)优先
  phon     词池音标为空时用词书 ukphone 补齐
字段无内容就不落键——前端 app.js 对缺失字段不渲染,主站 vocab.json 不经本脚本,
两层完全向后兼容。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parent
DEFAULT_BOOKS = [
    TOOL_DIR.parent.parent / "tmp" / "kajweb" / "IELTSluan_2.json",   # 有道,排前 → 例句优先
    TOOL_DIR.parent.parent / "tmp" / "kajweb" / "IELTS_3.json",       # 新东方
]


def _parse_book(path: Path) -> list[dict]:
    """解析一本 JSONL 词书:一行一个 JSON 对象,空行跳过。"""
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        head = str(rec.get("headWord") or "").strip()
        if not head:
            continue
        c = ((rec.get("content") or {}).get("word") or {}).get("content") or {}
        entries.append({
            "head": head.lower(),
            "ukphone": str(c.get("ukphone") or "").strip(),
            "tranOthers": [
                str(t.get("tranOther") or "").strip()
                for t in (c.get("trans") or [])
                if str(t.get("tranOther") or "").strip()
            ],
            "sentences": [
                (str(s.get("sContent") or "").strip(), str(s.get("sCn") or "").strip())
                for s in ((c.get("sentence") or {}).get("sentences") or [])
                if str(s.get("sContent") or "").strip()
            ],
            "phrases": [
                (str(p.get("pContent") or "").strip(), str(p.get("pCn") or "").strip())
                for p in ((c.get("phrase") or {}).get("phrases") or [])
                if str(p.get("pContent") or "").strip()
            ],
        })
    return entries


def enrich(vocab: dict, book_paths: list[Path]) -> tuple[dict, int]:
    """纯函数:返回 (增强后的新 vocab, 命中增强的词数);不修改入参。"""
    by_head: dict[str, list[dict]] = {}
    for path in book_paths:
        for e in _parse_book(path):
            by_head.setdefault(e["head"], []).append(e)   # 同词跨书按词书顺序排,前者优先

    new_words = []
    enriched = 0
    for item in vocab.get("words", []):
        hits = by_head.get(str(item.get("w") or "").lower())
        if not hits:
            new_words.append(item)                        # 词书没命中:原样保留
            continue
        winner = hits[0]
        out = dict(item)
        changed = False
        en_defs: list[str] = []                           # 英英:跨书 tranOther 去重连接
        for e in hits:
            for t in e["tranOthers"]:
                if t not in en_defs:
                    en_defs.append(t)
        if en_defs:
            out["enDef"] = " ; ".join(en_defs)
            changed = True
        phrases: list[dict] = []                          # 短语:跨书合并,按原文去重,前 3
        seen_phrases: set[str] = set()
        for e in hits:
            for pc, pcn in e["phrases"]:
                if pc not in seen_phrases:
                    seen_phrases.add(pc)
                    phrases.append({"en": pc, "cn": pcn})
        if phrases:
            out["phrases"] = phrases[:3]
            changed = True
        if winner["sentences"]:                           # 例句:排前词书(有道)优先,前 2
            out["ydSents"] = [{"en": en, "cn": cn} for en, cn in winner["sentences"][:2]]
            changed = True
        if not str(out.get("phon") or "").strip() and winner["ukphone"]:
            out["phon"] = winner["ukphone"]               # 音标:词池为空才补
            changed = True
        if changed:
            enriched += 1
        new_words.append(out)

    new_vocab = dict(vocab)
    new_vocab["words"] = new_words
    return new_vocab, enriched


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="雅思词书增强:vocab.json → vocab-beta.json")
    ap.add_argument("--vocab", type=Path, default=TOOL_DIR / "web" / "vocab.json",
                    help="输入词库(默认 web/vocab.json)")
    ap.add_argument("--books", type=Path, nargs="*", default=DEFAULT_BOOKS,
                    help="JSONL 词书,可多本;排前者例句优先(默认:有道 IELTSluan_2、新东方 IELTS_3)")
    ap.add_argument("--out", type=Path, default=TOOL_DIR / "web" / "vocab-beta.json",
                    help="输出词库(默认 web/vocab-beta.json)")
    args = ap.parse_args(argv)

    vocab = json.loads(args.vocab.read_text(encoding="utf-8"))
    result, n = enrich(vocab, args.books)
    args.out.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    print(f"enriched {n}/{len(result['words'])} words → {args.out}")


if __name__ == "__main__":
    main()
