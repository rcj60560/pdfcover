"""新概念(2/3):LRC 同步字幕 → 字幕跟读 md。

源数据:书库音频自带的 .lrc(句级时间戳 + 中英对照,露珠同步字幕版),
缓存于仓库 tmp/nce2_lrc/(96 个)、tmp/nce3_lrc/(60 个),与 /script/books/新概念N/*.mp3 同名。

用法:
  python build.py                          # 全量 --book 册 → src_root/新概念N/
  python build.py --book 3 --out DIR       # 指定册/指定目录
  python build.py --limit 3 --out DIR      # 样张:前 3 课
  python build.py --en-only 10 --out DIR   # 第 1-N 课英文合辑(欧路精翻用,英文不硬换行)

时间轴规则与 cambridge/build_md.py 一致:块 end = 下一块 start,末块 +5s,最短 0.5s。
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parent
REPO_TMP = TOOL_DIR.parents[2] / "tmp"
# --book 预设:书名(库目录名=书库音频名) / 文档标题前缀 / LRC 缓存子目录
BOOKS = {
    2: ("新概念2", "新概念英语2", "nce2_lrc"),
    3: ("新概念3", "新概念英语3", "nce3_lrc"),
}

STYLE = (
    "<style>\n"
    "  p { font-size: 18px; }\n"
    "  p > strong:only-child { font-size: 28px; }\n"
    "  p > code:only-child { font-size: 16px; }\n"
    "  blockquote p { font-size: inherit; }\n"
    "</style>"
)

_TS_LINE = re.compile(r"^((?:\[\d+:\d+(?:[.:]\d{1,3})?\])+)(.*)$")
_TS_ONE = re.compile(r"\[(\d+):(\d+)(?:[.:](\d{1,3}))?\]")


def _ts_ms(m: re.Match) -> int:
    frac = (m.group(3) or "0").ljust(3, "0")
    return ((int(m.group(1)) * 60) + int(m.group(2))) * 1000 + int(frac)


def parse_lrc(path: Path) -> tuple[dict[str, str], list[tuple[int, str, str]]]:
    """LRC → (元数据 tags, [(ms, en, zh)] 按时间升序)。无 zh 的行 zh 为空串。"""
    meta: dict[str, str] = {}
    rows: list[tuple[int, str, str]] = []
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        m = _TS_LINE.match(raw.strip())
        if not m:                                            # [al:] [ti:] 等标签行
            tag = re.match(r"^\[(\w+):(.*)\]$", raw.strip())
            if tag:
                meta[tag.group(1)] = tag.group(2)
            continue
        first = _TS_ONE.search(m.group(1))
        if not first:
            continue
        rest = m.group(2).strip()
        en, _, zh = rest.partition("|")
        rows.append((_ts_ms(first), en.strip(), zh.strip()))
    rows.sort(key=lambda r: r[0])
    return meta, rows


def fmt_ts(ms: int) -> str:
    whole = max(0, ms // 1000)
    minutes, seconds = divmod(whole, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"


def lesson_meta(stem: str, meta: dict[str, str]) -> tuple[str, str]:
    """文件名 01－Title → (课号 '01', 课名)。"""
    num, _, title = stem.partition("－")                    # 全角连字符,与音频同名
    return num, (meta.get("ti") or title or stem).strip()


def build_lesson_md(stem: str, rows: list[tuple[int, str, str]], zh_source: str,
                    book: tuple[str, str]) -> str:
    name, prefix = book
    num, title = lesson_meta(stem, {})
    parts = [
        f"# {prefix} · Lesson {num} {title}\n\n"
        f"> 来源: {prefix} 美音版同步字幕(露珠) · 音频 书库「{name}」{stem}.mp3\n"
        f"> 时间轴: `LRC 句级同步` · 中文 `{zh_source}` · 共 {len(rows)} 条\n\n"
        f"{STYLE}",
    ]
    for i, (ms, en, zh) in enumerate(rows):
        end = rows[i + 1][0] if i + 1 < len(rows) else ms + 5000
        block = f"---\n\n`{fmt_ts(ms)} → {fmt_ts(max(end, ms + 500))}`\n\n**{en}**"
        if zh:
            block += f"\n\n{zh}"
        parts.append(block)
    return "\n\n".join(parts) + "\n"


def build_en_only(stems: list[str], rows_by: dict[str, list], book: tuple[str, str]) -> str:
    """第 1-N 课英文合辑:每课一段,整段不硬换行(欧路整段翻译用)。"""
    name, prefix = book
    parts = [f"# {prefix} · 第 1-{len(stems)} 课英文(待精翻)"]
    for stem in stems:
        num, title = lesson_meta(stem, {})
        parts.append(f"---\n\n## Lesson {num} {title}\n\n" + " ".join(en for _, en, _ in rows_by[stem]))
    return "\n\n".join(parts) + "\n"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="新概念 LRC → 字幕跟读 md")
    ap.add_argument("--book", type=int, default=2, choices=sorted(BOOKS), help="册号(默认 2)")
    ap.add_argument("--lrc", type=Path, default=None, help="LRC 目录(默认 tmp/nce{N}_lrc)")
    ap.add_argument("--out", type=Path, default=None, help="输出目录(默认 src_root/新概念N/)")
    ap.add_argument("--limit", type=int, default=None, help="只处理前 N 课(样张)")
    ap.add_argument("--en-only", type=int, default=None, help="输出第 1-N 课英文合辑 md 而非双语")
    ap.add_argument("--zh-source", default="LRC 内置", help="中文来源标注")
    args = ap.parse_args(argv)

    name, prefix, lrc_dir = BOOKS[args.book]
    book = (name, prefix)
    lrc_dir = args.lrc or (REPO_TMP / lrc_dir)
    stems = sorted(p.stem for p in lrc_dir.glob("*.lrc"))
    if not stems:
        raise SystemExit(f"没有 LRC 文件:{lrc_dir}")
    if args.limit:
        stems = stems[: args.limit]
    rows_by = {s: parse_lrc(lrc_dir / f"{s}.lrc")[1] for s in stems}

    if args.en_only is not None:
        picked = stems[: args.en_only]
        out = (args.out or Path.cwd()) / f"{name} 第1-{len(picked)}课-英文.md"
        out.write_text(build_en_only(picked, rows_by, book), encoding="utf-8")
        print(f"英文合辑 → {out}({len(picked)} 课)")
        return

    config = json.loads((TOOL_DIR.parent / "config.json").read_text(encoding="utf-8"))
    out_dir = args.out or (Path(config["src_root"]) / name)
    out_dir.mkdir(parents=True, exist_ok=True)
    for s in stems:
        (out_dir / f"{s}.md").write_text(build_lesson_md(s, rows_by[s], args.zh_source, book), encoding="utf-8")
    print(f"{len(stems)} 课 → {out_dir}")


if __name__ == "__main__":
    main()
