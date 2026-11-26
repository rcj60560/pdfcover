"""句级等比对齐器 —— 英文句 ↔ 中文句按序号比例映射,再把中文句挂回 EN 块。

用法: python sent_align.py <align_latest.json> <out.txt>
原理: 欧路整段翻译基本一句对一句。把 EN 全文和中文全文各按句末标点切成句,
按 i/n 等比映射得到每句英文对应的中文句区间;再把每个 EN 块覆盖的英文句的中文拼起来。
"""
from __future__ import annotations

import json
import re
import sys


STOP_EN = set("""Okay Alright Well This That Then They There What When Where Which Have Like Good Great Right
Sure Here Some Maybe Let Look Just Very Also Both Each Most Other Another Because Before After About
Could Would Should Think Know Want Little Things People Animals Plants Water Earth Boys Girls Teacher
Unit Lesson Part Say Give Can Did Does Was Were Been Do Not Don't You Your We Our He She It His Her
Their Them Us Me My Mine All Any And But Or If In On At To For Of With From By As So Than Then Now
Today Next Last First Second Third New Old Big Small Many Much More Most Less Few Going Making Really
Something Together Through Around Under Over Always Never Every Anything Someone Everyone These Those
Again Back Down Out Off Up Chinese English Chinese National Geographic Farmer Michael Sahara Desert
Canada Canadian Toronto Middle East Walnut Disney World Circus Legos Lego""".split())


def split_en(text: str) -> list[str]:
    # 英文句末: . ? ! 后跟空格+大写/引号/数字,或行尾;缩写(Mr. Dr. U.S.)粗略保护
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\"'$\d])", text)
    return [p.strip() for p in parts if p.strip()]


def split_zh(text: str) -> list[str]:
    # 切得比句末更细:逗号/顿号也切,让比例映射粒度匹配英文的短句块;先去掉段落空行
    text = re.sub(r"\s+", "", text)
    parts = re.split(r"(?<=[。！？；，、])", text)
    return [p.strip() for p in parts if p.strip()]


def main(src: str, dst: str) -> None:
    d = json.load(open(src, encoding="utf-8"))
    rows = d["rows"]
    # 块偏移表:全文拼接后每个块覆盖的字符区间
    full = ""; spans = []
    for r in rows:
        s = len(full); full += r["english"] + " "; spans.append((s, len(full)))
    en_sents = split_en(full)
    zh_sents = split_zh(d["raw_chinese"])
    ne, nz = len(en_sents), len(zh_sents)
    # 每个英文句的字符起点 → 序号比例 → 中文句区间 [j0, j1]
    def zh_range_for_char(c0: float, c1: float) -> tuple[int, int]:
        j0 = min(nz - 1, int(c0 / len(full) * nz))
        j1 = min(nz - 1, max(j0, int(round(c1 / len(full) * nz)) - 1))
        return j0, j1
    # 非重叠分配:每个块的中文起点 = 上一块的终点,终点 = 按比例算出的位置
    # 锚点校正: 块内若有"该块特有的关键词"(英文原词/数字/大写专名),在比例终点附近±8个子句内找它,
    # 找到则把终点吸附到该关键词所在子句之前(关键词属于本块,不应分给下一块)
    def block_key(r) -> str | None:
        t = r["english"]
        for n in re.findall(r"\d[\d,.]*", t):
            return n.replace(",", "")
        for w in re.findall(r"[A-Za-z][A-Za-z-]{4,}", t):
            if w[0].isupper() and w.lower() not in STOP_EN:
                return w
        return None
    zh_pos = []  # 每个子句在拼接串中的起点
    acc = 0
    for s_ in zh_sents:
        zh_pos.append(acc); acc += len(s_)
    zh_full = "".join(zh_sents)
    # 按字符长度比例(而非子句序号):吸收中英长度系统性差异
    zh_total = len(zh_full); en_total = len(full)
    def zh_char(c: float) -> int:
        return min(zh_total - 1, int(c / en_total * zh_total))
    def clause_at(pos: int) -> int:
        return max(i for i, p in enumerate(zh_pos) if p <= pos)
    out = []; prev_j = 0
    for (s, e), r in zip(spans, rows):
        j1 = clause_at(zh_char(e))
        j1 = max(prev_j, j1)
        key = block_key(r)
        if key:
            # 在 [prev_j, j1+8] 子句范围内找关键词,找到则把终点钉到关键词所在子句(双向吸附)
            lo_c = zh_pos[prev_j] if prev_j < len(zh_pos) else 0
            hi_c = zh_pos[min(j1 + 12, len(zh_pos) - 1)] + 120
            m = re.search(re.escape(key), zh_full[lo_c:hi_c], re.I)
            if m:
                kc = lo_c + m.start()
                k = max(i for i, p in enumerate(zh_pos) if p <= kc)
                if prev_j <= k <= j1 + 12:
                    j1 = k
        out.append("".join(zh_sents[prev_j:j1 + 1]))
        prev_j = j1 + 1
    # 收尾:把剩余子句并入最后一块
    if prev_j < nz:
        out[-1] += "".join(zh_sents[prev_j:])
    # 修正: 保证每个块至少有内容(否则从前/后借一句)——这里只报告,不自动改
    empty = [i + 1 for i, o in enumerate(out) if not o]
    open(dst, "w", encoding="utf-8").write("\n\n".join(out))
    total = sum(map(len, out))
    print(f"EN {ne} 句 / {len(rows)} 块 | ZH {nz} 句 | 空块 {len(empty)} {empty[:10]} | 中文字 {total} (原文 {len(d['raw_chinese'])})")
    for k in (0, 1, len(rows) // 4, len(rows) // 2, 3 * len(rows) // 4, len(rows) - 1):
        print(f"--- 块{k+1}: E:{rows[k]['english'][:70]}")
        print(f"          Z:{out[k][:60]}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
