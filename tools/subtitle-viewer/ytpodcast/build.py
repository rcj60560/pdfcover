"""English Leap Podcast:YouTube vtt → 字幕跟读 md(纯英文,中文后续可补)。

源数据:素材目录(默认 src_root/youtube-podcast)下 yt-dlp 下载的
`EPxx - 标题.mp3` + `EPxx - 标题.en-orig.vtt`(或 .en.vtt)。

用法:
  python -m ytpodcast.build                # 全量 → md 落素材目录同名 .md
  python -m ytpodcast.build --limit 2     # 样张前 2 集
  python -m ytpodcast.build --src DIR --out DIR

块格式与 nce2/cambridge 一致:块 end = 下一块 start,末块用自身 end(≥start+5s),最短 0.5s。
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parent

STYLE = (
    "<style>\n"
    "  p { font-size: 18px; }\n"
    "  p > strong:only-child { font-size: 28px; }\n"
    "  p > code:only-child { font-size: 16px; }\n"
    "  blockquote p { font-size: inherit; }\n"
    "</style>"
)

_TAG_RE = re.compile(r"<[^>]+>")
_MARKER_RE = re.compile(r"\[(music|laughter|applause|applauding|silence|foreign|inaudible)[^\]]*\]",
                        re.IGNORECASE)
_SPEAK_RE = re.compile(r"^>>\s*")
_SUB_SUFFIX_RE = re.compile(r"\.en(-orig|-US)?\.vtt$", re.IGNORECASE)
_SENT_END_RE = re.compile(r"[.?!][\"')\]]?$")


def _ts(s: str) -> float:
    """`HH:MM:SS.mmm` / `MM:SS.mmm` → 秒。"""
    s = s.strip().split(" ")[0].replace(",", ".")   # 去掉行内 cue 设置
    parts = [float(p) for p in s.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0.0)
    h, m, sec = parts
    return round(h * 3600 + m * 60 + sec, 2)


def parse_vtt(content: str) -> list[tuple[float, float, str]]:
    """WEBVTT 文本 → [(start, end, text)]。

    YouTube 自动字幕是滚动窗口:真 cue 两行(旧行+带词级时间戳的新行),
    后跟 ~10ms 桥接 cue 复读旧行。只取每个 cue 的最后一个非空行,
    与上一条相同即弃,并剥内联时间戳/样式标签/[music] 标记/>> 说话人符。
    """
    lines = content.splitlines()
    cues: list[tuple[float, float, str]] = []
    prev_text: str | None = None
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if "-->" not in line or i + 1 >= len(lines):
            i += 1
            continue
        try:
            a, b = line.split("-->", 1)
            start, end = _ts(a), _ts(b)
        except ValueError:
            i += 1
            continue
        j = i + 1
        while j < len(lines) and not lines[j].strip():      # 跳过时间行后的占位空行
            j += 1
        texts: list[str] = []
        while j < len(lines) and lines[j].strip() and "-->" not in lines[j]:
            texts.append(lines[j])
            j += 1
        if not texts:
            i = j
            continue
        text = re.sub(r"\s+", " ", _TAG_RE.sub("", texts[-1])).strip()
        text = _SPEAK_RE.sub("", _MARKER_RE.sub("", text)).strip()
        if text and text != prev_text:
            prev_text = text
            cues.append((start, end, text))
        i = j
    return cues


def merge_cues(cues: list[tuple[float, float, str]],
               max_words: int = 40) -> list[dict]:
    """短语 cue 按句末标点合并成句块;滚动重复行去重;超长强制断。"""
    blocks: list[dict] = []
    buf: list[str] = []
    start = last_end = 0.0
    prev_text: str | None = None
    for s, e, text in cues:
        if text == prev_text:                       # 自动字幕滚动窗口重复
            last_end = max(last_end, e)
            continue
        prev_text = text
        if not buf:
            start = s
        buf.append(text)
        last_end = e
        joined = " ".join(buf)
        if _SENT_END_RE.search(text) or len(joined.split()) >= max_words:
            blocks.append({"start": start, "end": last_end, "text": joined})
            buf = []
    if buf:
        blocks.append({"start": start, "end": last_end, "text": " ".join(buf)})
    return blocks


def fmt_ts(sec: float) -> str:
    whole = max(0, int(sec))
    minutes, seconds = divmod(whole, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"


def split_align_blocks(text: str) -> list[str]:
    """排版产物(空行分隔的中文块)→ 列表;容忍多空行。"""
    return [b.strip() for b in re.split(r"\n\s*\n", text.strip()) if b.strip()]


def en_only(ep_title: str, blocks: list[dict]) -> str:
    """整段英文(不硬换行,欧路词典整段翻译用),nce2 --en-only 同款。"""
    return f"# {ep_title} · 英文(待精翻)\n\n" + " ".join(b["text"] for b in blocks)


def build_md(ep_title: str, audio_name: str, blocks: list[dict],
             zh: list[str] | None = None) -> str:
    zh = list(zh or []) + [None] * len(blocks)
    zh = zh[: len(blocks)]                            # 部分对齐:短于块数时尾部补 None
    covered = sum(1 for z in zh if z and z.strip() != "·")   # · = 无译文占位,不计数
    zh_label = ("欧路精翻" if covered == len(blocks)
                else f"欧路精翻(部分 {covered}/{len(blocks)})") if covered else "暂无(后续可补)"
    head = (
        f"# {ep_title}\n\n"
        f"> 来源: English Leap Podcast(Speak English with Class)· 音频 书库「youtube-podcast」{audio_name}\n"
        f"> 时间轴: `YouTube 原生字幕 句级合并` · 中文 `{zh_label}` · 共 {len(blocks)} 条\n\n"
        f"{STYLE}"
    )
    parts = []
    for i, b in enumerate(blocks):
        end = blocks[i + 1]["start"] if i + 1 < len(blocks) else max(b["end"], b["start"] + 5)
        end = max(end, b["start"] + 0.5)
        block = f"---\n\n`{fmt_ts(b['start'])} → {fmt_ts(end)}`\n\n**{b['text']}**"
        if zh[i] and zh[i].strip() != "·":
            block += f"\n\n{zh[i]}"
        parts.append(block)
    return head + "\n" + "\n\n".join(parts) + "\n"


def episodes(src: Path) -> list[tuple[str, Path]]:
    """素材目录 → [(EP 基名, vtt 路径)],en-orig 优先于 en,按 EP 序号排序。"""
    by_stem: dict[str, Path] = {}
    for vtt in sorted(src.glob("*.vtt")):
        stem = _SUB_SUFFIX_RE.sub("", vtt.name)
        if stem not in by_stem or ".en-orig." in vtt.name:
            by_stem[stem] = vtt
    return sorted(by_stem.items(), key=lambda kv: kv[0])


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="English Leap Podcast vtt → 字幕跟读 md")
    ap.add_argument("--src", type=Path, default=None, help="素材目录(默认 src_root/youtube-podcast)")
    ap.add_argument("--out", type=Path, default=None, help="md 输出目录(默认与素材同目录)")
    ap.add_argument("--limit", type=int, default=None, help="只处理前 N 集")
    ap.add_argument("--en-only", action="store_true",
                    help="只导出每集整段英文 txt 到 翻译/ 子目录(欧路精翻用)")
    args = ap.parse_args(argv)

    import json
    config = json.loads((TOOL_DIR.parent / "config.json").read_text(encoding="utf-8"))
    src = args.src or (Path(config["src_root"]) / "youtube-podcast")
    out = args.out or src

    eps = episodes(src)
    if args.limit:
        eps = eps[: args.limit]
    if not eps:
        raise SystemExit(f"素材目录没有 vtt:{src}")

    if args.en_only:
        zh_dir = src / "翻译"
        zh_dir.mkdir(parents=True, exist_ok=True)
        for stem, vtt in eps:
            blocks = merge_cues(parse_vtt(vtt.read_text(encoding="utf-8", errors="replace")))
            out = zh_dir / f"{stem[:4]}-英文.txt"
            out.write_text(en_only(stem, blocks), encoding="utf-8")
            print(f"{out.name}: {len(blocks)} 句")
        return

    for stem, vtt in eps:
        cues = parse_vtt(vtt.read_text(encoding="utf-8", errors="replace"))
        blocks = merge_cues(cues)
        audio = f"{stem}.mp3"
        align_file = src / "翻译" / f"{stem[:4]}-align.txt"
        zh = (split_align_blocks(align_file.read_text(encoding="utf-8"))
              if align_file.is_file() else [])
        if len(zh) > len(blocks):
            print(f"{stem}: ⚠ 对齐块数超出({len(zh)}/{len(blocks)}),本集先出纯英文")
            zh = []
        md_path = out / f"{stem}.md"
        md_path.write_text(build_md(stem, audio, blocks, zh=zh or None), encoding="utf-8")
        has_audio = (src / audio).is_file()
        print(f"{stem}: {len(cues)} cues → {len(blocks)} 句块"
              f"{' +中文' if zh else ''}"
              f"{' (音频在)' if has_audio else ' ⚠ 缺音频 ' + audio}")
    print(f"{len(eps)} 集 → {out}")


if __name__ == "__main__":
    main()
