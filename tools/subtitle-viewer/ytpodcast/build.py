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
import html
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
_MARKER_RE = re.compile(
    r"\[(music|laughter|applause|applauding|silence|foreign|inaudible"
    r"|笑声|掌声|音乐|静音|沉默|旁白|翻译|不可闻)[^\]]*\]", re.IGNORECASE)
_SPEAK_RE = re.compile(r"^>>\s*")
_SUB_SUFFIX_RE = re.compile(r"\.en(-orig|-US)?\.vtt$", re.IGNORECASE)
_SENT_END_RE = re.compile(r"[.?!][\"')\]]?$")
_SENT_SPLIT_RE = re.compile(r"(?<=[.?!])\s+(?=[\"'A-Z])")   # 行内多句:句末标点后接大写/引号处切


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


def build_window_blocks(cues: list[tuple], rows: list[tuple[int, str]]) -> list[dict]:
    """以 LR 行(=YouTube 显示窗口,2 行英文一组)为块:窗口内 cue 拼接,中文=整行。

    块切换节奏与 YouTube 播放器字幕完全一致;每块必带中文(窗口级 1:1)。
    """
    if not rows:
        return []
    blocks: list[dict] = []
    for i, (t, zh) in enumerate(rows):
        hi = rows[i + 1][0] if i + 1 < len(rows) else float("inf")
        win = [c for c in cues if t <= c[0] < hi]
        if not win:
            continue
        blocks.append({"start": win[0][0], "end": win[0][0],
                       "text": " ".join(c[2] for c in win), "zh": zh})
    for i in range(len(blocks) - 1):                     # end = 下一块 start
        blocks[i]["end"] = blocks[i + 1]["start"]
    if blocks:
        blocks[-1]["end"] = max(cues[-1][1], blocks[-1]["start"] + 0.5)
    return blocks


def merge_cues(cues: list[tuple], max_words: int = 40) -> list[dict]:
    """一句一块:cue 内多句按词数比例拆时间戳,跨 cue 句子拼接;≤2 词语气碎句并给下一句。

    cues 元素为 (start, end, text) 或 (start, end, text, zh);块携带 zh(各行中文拼接)。
    end 为下一块 start(段内拆分即拆分点);末块 end 由 build_md 兜底 +5s。
    """
    norm = [(c[0], c[1], c[2], c[3] if len(c) > 3 else "") for c in cues]
    # 1) 展开:cue → 句子碎片,行内多句按词数比例分配 [start,end] 窗口
    pieces: list[tuple[float, str, str]] = []
    for s, e, text, zh in norm:
        sents = [x for x in _SENT_SPLIT_RE.split(text) if x.strip()]
        if not sents:
            continue
        if len(sents) == 1:
            pieces.append((s, sents[0], zh))
            continue
        words = [len(x.split()) for x in sents]
        total = sum(words) or 1
        dur = max(e - s, 0.5)
        t = s
        for k, (sent, w) in enumerate(zip(sents, words)):
            pieces.append((round(t, 2), sent, zh if k == 0 else ""))  # 行级中文归首句
            t += dur * w / total
    # 2) 碎片 → 句块:句末标点收口(≤2 词语气句不收,并给下一句);无标点超长强断
    blocks: list[dict] = []
    buf, zh_buf, start = [], [], 0.0
    for t, sent, zh in pieces:
        if not buf:
            start = t
        buf.append(sent)
        if zh:
            zh_buf.append(zh)
        joined = " ".join(buf)
        done = (_SENT_END_RE.search(sent) and len(joined.split()) >= 3) \
            or len(joined.split()) >= max_words
        if done:
            blocks.append({"start": start, "end": t, "text": joined,
                           "zh": "".join(zh_buf)})
            buf, zh_buf = [], []
    if buf:
        blocks.append({"start": start, "end": blocks[-1]["start"] if blocks else 0.0,
                       "text": " ".join(buf), "zh": "".join(zh_buf)})
    # 3) end 统一取下一块 start(= 拆分点),末块留给 build_md 兜底
    for i in range(len(blocks) - 1):
        blocks[i]["end"] = blocks[i + 1]["start"]
    return blocks


def fmt_ts(sec: float) -> str:
    whole = max(0, int(sec))
    minutes, seconds = divmod(whole, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"


def parse_lr_time(s: str) -> int | None:
    """LR 时间列:'0s' / '1:01' / '1:01:05' → 秒;不识别返回 None。"""
    s = str(s).strip()
    m = re.fullmatch(r"(\d+)\s*s", s, re.IGNORECASE)
    if m:
        return int(m.group(1))
    if re.fullmatch(r"(?:\d{1,2}:)?\d{1,2}:\d{2}", s):
        p = [int(x) for x in s.split(":")]
        while len(p) < 3:
            p.insert(0, 0)
        return p[0] * 3600 + p[1] * 60 + p[2]
    return None


def clean_zh_line(s: str) -> str:
    """中文机翻行:剥 >> 说话人符与 [笑声] 类标记,压空白。"""
    s = _SPEAK_RE.sub("", _MARKER_RE.sub("", str(s)))
    return re.sub(r"\s+", " ", s).strip()


def load_zh_cues(path: Path) -> list[tuple[int, str]]:
    """`翻译/EPxx-zh.cues.txt`,每行 `秒|中文`(由 LR xlsx 转换而来)。"""
    cues: list[tuple[int, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        t, _, zh = line.partition("|")
        zh = clean_zh_line(zh)
        if zh and t.strip().isdigit():
            cues.append((int(t), zh))
    return cues


def split_align_blocks(text: str) -> list[str]:
    """排版产物(空行分隔的中文块)→ 列表;容忍多空行。"""
    return [b.strip() for b in re.split(r"\n\s*\n", text.strip()) if b.strip()]


def en_only(ep_title: str, blocks: list[dict]) -> str:
    """整段英文(不硬换行,欧路词典整段翻译用),nce2 --en-only 同款。"""
    return f"# {ep_title} · 英文(待精翻)\n\n" + " ".join(b["text"] for b in blocks)


def build_md(ep_title: str, audio_name: str, blocks: list[dict],
             zh: list[str] | None = None, zh_source: str | None = None) -> str:
    zh = list(zh or []) + [None] * len(blocks)
    zh = zh[: len(blocks)]                            # 部分对齐:短于块数时尾部补 None
    covered = sum(1 for z in zh if z and z.strip() != "·")   # · = 无译文占位,不计数
    if zh_source:
        zh_label = (zh_source if covered == len(blocks)
                    else f"{zh_source}(部分 {covered}/{len(blocks)})")
    else:
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
        en = html.unescape(b["text"])                  # 显示层反转义,不动分段(块数与对齐文件锁死)
        block = f"---\n\n`{fmt_ts(b['start'])} → {fmt_ts(end)}`\n\n**{en}**"
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
        audio = f"{stem}.mp3"
        zh, zh_source = [], None
        cues_file = src / "翻译" / f"{stem[:4]}-zh.cues.txt"
        if cues_file.is_file():                       # LR 机翻:显示窗口即块,中文 1:1
            blocks = build_window_blocks(cues, load_zh_cues(cues_file))
            zh = [b.get("zh", "") for b in blocks]
            zh_source = "LR 机翻·窗口直配"
        else:
            blocks = merge_cues(cues)
            align_file = src / "翻译" / f"{stem[:4]}-align.txt"
            if align_file.is_file():
                zh = split_align_blocks(align_file.read_text(encoding="utf-8"))
                if len(zh) > len(blocks):
                    print(f"{stem}: ⚠ 对齐块数超出({len(zh)}/{len(blocks)}),本集先出纯英文")
                    zh = []
        md_path = out / f"{stem}.md"
        md_path.write_text(build_md(stem, audio, blocks, zh=zh or None, zh_source=zh_source),
                           encoding="utf-8")
        has_audio = (src / audio).is_file()
        print(f"{stem}: {len(cues)} cues → {len(blocks)} 句块"
              f"{' +中文' if any(zh) else ''}"
              f"{' (音频在)' if has_audio else ' ⚠ 缺音频 ' + audio}")
    print(f"{len(eps)} 集 → {out}")


if __name__ == "__main__":
    main()
