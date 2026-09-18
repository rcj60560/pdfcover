"""Build timestamped Cambridge subtitle Markdown from aligned turns."""
from __future__ import annotations


STYLE = (
    "<style>\n"
    "  p { font-size: 18px; }\n"
    "  p > strong:only-child { font-size: 28px; }\n"
    "  p > code:only-child { font-size: 16px; }\n"
    "  blockquote p { font-size: inherit; }\n"
    "</style>"
)


def fmt_ts(sec: float) -> str:
    """Format seconds as ``M:SS`` or ``H:MM:SS``."""
    whole = max(0, int(sec))
    minutes, seconds = divmod(whole, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def build_md(
    rec_id: str,
    unit: str,
    turns: list[dict],
    track_name: str,
    zh: dict[int, str],
    zh_source: str = "精翻",
) -> str:
    """Render aligned turns and their translations as subtitle Markdown."""
    header = (
        f"# 剑桥雅思核心词汇精讲精练 Recording {rec_id}｜Unit {unit}\n\n"
        f"> 来源: 剑桥雅思核心词汇精讲精练 (Pauline Cullen)书后 Recording scripts · "
        f"音频 {track_name}\n"
        f"> 时间轴: `faster-whisper small.en 词级对齐` · 中文 `{zh_source}` · 共 {len(turns)} 条\n\n"
        f"{STYLE}\n"
    )

    blocks: list[str] = []
    for index, turn in enumerate(turns):
        start = float(turn.get("start", 0.0) or 0.0)
        if index + 1 < len(turns):
            end = float(turns[index + 1].get("start", start) or start)
        else:
            raw_end = turn.get("end")
            end = float(raw_end if raw_end is not None else start + 5.0)
        end = max(end, start + 0.5)

        label = turn.get("label", "")
        text = turn.get("text", "")
        english = f"{label}: {text}" if label else text
        block = f"`{fmt_ts(start)} → {fmt_ts(end)}`\n\n**{english}**"
        translation = zh.get(index, "")
        if translation:
            block += f"\n\n{translation}"
        blocks.append(f"---\n\n{block}")

    return header + "\n".join(blocks) + ("\n" if blocks else "")


def md_filename(rec_id: str, unit: str) -> str:
    """Return the standard output filename for a recording and unit."""
    return f"Recording {rec_id}｜Unit {unit}.md"


def build_unit_md(
    unit: str,
    recordings: list[dict],
) -> str:
    """一个 Unit 合并为一个字幕 md(时间戳跨录音累加,保单调)。

    recordings: [{id, track, turns:[{label,text,start,end}], zh:{i:中文}, zh_source}]
    每个录音的首块英文带「Recording Na ·」前缀,便于分段定位;
    切换音频时点该段首个时间戳锚定。
    """
    total = sum(len(r["turns"]) for r in recordings)
    tracks = "、".join(r["track"] for r in recordings)
    sources = "、".join(sorted({r["zh_source"] for r in recordings}))
    header = (
        f"# 剑桥雅思核心词汇精讲精练 Unit {unit}\n\n"
        f"> 来源: 剑桥雅思核心词汇精讲精练 (Pauline Cullen)书后 Recording scripts\n"
        f"> 音频: {tracks}(各录音对应一条 Track,换音频时点该段首个时间戳定位)\n"
        f"> 时间轴: `faster-whisper small.en 词级对齐` · 中文 `{sources}` · 共 {total} 条\n\n"
        f"{STYLE}\n"
    )
    blocks: list[str] = []
    offset = 0.0                                  # 跨录音累加,保证时间戳单调
    for r in recordings:
        turns = r["turns"]
        zh = r["zh"]
        for index, turn in enumerate(turns):
            start = float(turn.get("start", 0.0) or 0.0) + offset
            if index + 1 < len(turns):
                end = float(turns[index + 1].get("start", 0.0) or 0.0) + offset
            else:
                raw_end = turn.get("end")
                end = float(raw_end if raw_end is not None else 0.0) + offset
                if end <= start:
                    end = start + 5.0
            end = max(end, start + 0.5)
            label = turn.get("label", "")
            text = turn.get("text", "")
            english = f"{label}: {text}" if label else text
            if index == 0:                        # 分段边界标记
                english = f"Recording {r['id']} · {english}" if english else f"Recording {r['id']}"
            block = f"`{fmt_ts(start)} → {fmt_ts(end)}`\n\n**{english}**"
            translation = zh.get(index, "")
            if translation:
                block += f"\n\n{translation}"
            blocks.append(f"---\n\n{block}")
        last_end = float(turns[-1].get("end", 0.0) or 0.0) if turns else 0.0
        offset += max(last_end, 5.0) + 5.0                       # 段间留 ≥5s 间隙
    return header + "\n".join(blocks) + ("\n" if blocks else "")


def unit_filename(unit: str) -> str:
    """Return the merged per-unit output filename."""
    return f"Unit {unit}.md"
