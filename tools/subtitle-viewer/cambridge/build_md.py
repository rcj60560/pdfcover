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
) -> str:
    """Render aligned turns and their translations as subtitle Markdown."""
    header = (
        f"# 剑桥雅思核心词汇精讲精练 Recording {rec_id}—Unit {unit}\n\n"
        f"> 来源: 剑桥雅思核心词汇精讲精练 (Pauline Cullen)书后 Recording scripts · "
        f"音频 {track_name}\n"
        f"> 时间轴: `faster-whisper small.en 词级对齐` · 中文 `机翻` · 共 {len(turns)} 条\n\n"
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
    return f"Recording {rec_id}—Unit {unit}.md"
