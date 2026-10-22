"""LR(Language Reactor)导出 xlsx → 翻译/EPxx-zh.cues.txt。

xlsx 结构:Subtitles 表,3 列 = Time / Subtitle(英) / Machine Translation(中);
文件名(lln_excel_subs_日期_随机号.xlsx)与集号无关——按英文列内容指纹对集。

用法(在 tools/subtitle-viewer 下):
  python -m ytpodcast.lr_xlsx --xlsx-dir <xlsx目录> [--force]
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from ytpodcast.build import _MARKER_RE, episodes, clean_zh_line, parse_lr_time, parse_vtt

TOOL_DIR = Path(__file__).resolve().parent
MATCH_STRONG = 0.8                                      # 词 4-gram 绝对命中线
MATCH_THRESHOLD = 0.5                                   # 断层命中线:还需 ≥2 倍第二名
                                                        # (LR 与 vtt 词形差异会把真集拉到 ~0.78)


def norm_en(s: str) -> str:
    """英文指纹:小写、剔标点(撇号直接删,防 it's/its 风格差)、压空白。"""
    s = str(s).lower().replace("'", "").replace("’", "")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def clean_en_line(s: str) -> str:
    """LR 英文行:剥 >> 说话人符(行中任意位置)与 [music] 类标记,压空白。"""
    s = _MARKER_RE.sub("", str(s).replace(">>", " "))
    return re.sub(r"\s+", " ", s).strip()


def match_episode(rows_en: list[str], eps: dict[str, str]) -> str | None:
    """LR 英文行 → 内容指纹最像的集号。

    指纹 = 行文本中段(避开各集相同的开场白)的词 4-gram,看是否成串出现在
    某集文本里。命中规则:绝对分 ≥ MATCH_STRONG,或 ≥ MATCH_THRESHOLD 且
    断层领先第二名 2 倍。字符二元组不可用:通用英文的字母搭配对任何英文
    都有 ~0.7 召回(BBC 转写曾 0.79 误配)。
    """
    words = norm_en(" ".join(rows_en)).split()
    if len(words) < 12:
        return None
    mid = words[len(words) // 3: len(words) // 3 + 150]
    grams = [" ".join(mid[i:i + 4]) for i in range(len(mid) - 3)]
    scores = sorted((sum(1 for g in grams if g in t) / len(grams), ep)
                    for ep, t in eps.items())
    best_score, best = scores[-1]
    second = scores[-2][0] if len(scores) > 1 else 0.0
    if best_score >= MATCH_STRONG or (best_score >= MATCH_THRESHOLD
                                      and best_score >= 2 * second):
        return best
    return None


def read_xlsx_rows(path: Path) -> list[tuple[int | None, str, str]]:
    """xlsx → [(秒, 英文行, 中文行)];Time 列不识别/中文为空的行照样返回,由调用方筛。"""
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb["Subtitles"] if "Subtitles" in wb.sheetnames else wb[wb.sheetnames[0]]
    rows: list[tuple[int | None, str, str]] = []
    for r in ws.iter_rows(min_row=2, values_only=True):
        if not r or len(r) < 3:
            continue
        t = parse_lr_time(r[0]) if r[0] is not None else None
        rows.append((t, clean_en_line(r[1] or ""), clean_zh_line(r[2] or "")))
    wb.close()
    return rows


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="LR xlsx → EPxx-zh.cues.txt(按内容指纹对集)")
    ap.add_argument("--xlsx-dir", type=Path, required=True, help="LR 导出 xlsx 所在目录")
    ap.add_argument("--force", action="store_true", help="cues 已存在也覆盖")
    args = ap.parse_args(argv)

    import json
    config = json.loads((TOOL_DIR.parent / "config.json").read_text(encoding="utf-8"))
    src = Path(config["src_root"]) / "youtube-podcast"
    zh_dir = src / "翻译"

    eps_text: dict[str, str] = {}                       # 集号 → 全转写英文指纹
    for stem, vtt in episodes(src):
        cues = parse_vtt(vtt.read_text(encoding="utf-8", errors="replace"))
        eps_text[stem[:4]] = norm_en(" ".join(c[2] for c in cues))

    files = sorted(args.xlsx_dir.glob("*.xlsx"))
    if not files:
        raise SystemExit(f"目录里没有 xlsx:{args.xlsx_dir}")
    done = fail = 0
    claimed: dict[str, str] = {}                        # 集号 → xlsx 名,撞车时报
    for xlsx in files:
        rows = read_xlsx_rows(xlsx)
        zh_rows = [(t, zh) for t, _, zh in rows if t is not None and zh]
        if not zh_rows:
            print(f"{xlsx.name}: 无中文/无时间行,跳过")
            fail += 1
            continue
        ep = match_episode([en for _, en, _ in rows if en], eps_text)
        if ep is None:
            print(f"{xlsx.name}: ✗ 内容指纹未匹配到任何集")
            fail += 1
            continue
        out = zh_dir / f"{ep}-zh.cues.txt"
        if out.is_file() and not args.force:
            print(f"{xlsx.name}: {ep} cues 已存在,跳过(--force 覆盖)")
            continue
        if ep in claimed:
            print(f"⚠ {ep} 被两个 xlsx 认领:{claimed[ep]} 与 {xlsx.name},后者覆盖")
        claimed[ep] = xlsx.name
        out.write_text("\n".join(f"{t}|{zh}" for t, zh in zh_rows) + "\n", encoding="utf-8")
        print(f"{xlsx.name}: {ep} ✓ {len(zh_rows)} 行 → {out.name}")
        done += 1
    print(f"转换 {done},失败/跳过 {fail}")


if __name__ == "__main__":
    main()
