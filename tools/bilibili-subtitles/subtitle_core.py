"""字幕解析、语言识别、时间轴对齐与 Markdown 导出（纯逻辑）。"""
from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence
from urllib.parse import urlparse


_TIMECODE_RE = re.compile(
    r"(?P<start>(?:\d{1,3}:)?\d{1,2}:\d{2}[,.]\d{1,3})\s*-->\s*"
    r"(?P<end>(?:\d{1,3}:)?\d{1,2}:\d{2}[,.]\d{1,3})"
)
_TAG_RE = re.compile(r"<[^>]+>")
_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
_LATIN_RE = re.compile(r"[A-Za-z]")
_LATIN_WORD_RE = re.compile(r"[A-Za-z]+(?:['’-][A-Za-z]+)?")
_ILLEGAL_FILENAME_RE = re.compile(r"[\\/:*?\"<>|\x00-\x1f]")


@dataclass(frozen=True)
class Caption:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class SubtitleTrack:
    id: str
    lang: str
    label: str
    kind: str
    family: str
    captions: tuple[Caption, ...]

    def public_dict(self) -> dict:
        return {
            "id": self.id,
            "lang": self.lang,
            "label": self.label,
            "kind": self.kind,
            "family": self.family,
            "cue_count": len(self.captions),
            "sample": self.captions[0].text.replace("\n", " / ")[:100] if self.captions else "",
        }


@dataclass(frozen=True)
class BilingualRow:
    start: float
    end: float
    english: str = ""
    chinese: str = ""

    def public_dict(self) -> dict:
        return {
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "start_text": format_timestamp(self.start, milliseconds=False),
            "end_text": format_timestamp(self.end, milliseconds=False),
            "english": self.english,
            "chinese": self.chinese,
        }


class SubtitleParseError(ValueError):
    pass


def normalize_bilibili_url(value: str) -> str:
    """只接受 B 站视频地址、b23.tv 短链或 BV/av 号，避免任意 URL 抓取。"""
    raw = (value or "").strip()
    if re.fullmatch(r"(?i)BV[0-9A-Za-z]{8,14}", raw):
        return f"https://www.bilibili.com/video/{raw}"
    if re.fullmatch(r"(?i)av\d{1,15}", raw):
        return f"https://www.bilibili.com/video/{raw.lower()}"
    if not re.match(r"^[a-z][a-z0-9+.-]*://", raw, re.I):
        raw = "https://" + raw
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower().rstrip(".")
    allowed = {
        "bilibili.com", "www.bilibili.com", "m.bilibili.com",
        "b23.tv", "www.b23.tv",
    }
    if parsed.scheme not in {"http", "https"} or host not in allowed:
        raise ValueError("请输入 bilibili.com / b23.tv 视频链接，或直接输入 BV 号")
    if host.endswith("bilibili.com") and "/video/" not in parsed.path.lower():
        raise ValueError("当前只支持 B 站视频页链接（路径中应包含 /video/）")
    return raw


def _clean_text(value: str, *, keep_newlines: bool = True) -> str:
    value = html.unescape(_TAG_RE.sub("", value or ""))
    value = value.replace("\\N", "\n").replace("\u200b", "")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in value.splitlines()]
    lines = [line for line in lines if line]
    return ("\n" if keep_newlines else " ").join(lines)


def parse_timestamp(value: str) -> float:
    parts = value.strip().replace(",", ".").split(":")
    if len(parts) == 2:
        hours = 0
        minutes, seconds = parts
    elif len(parts) == 3:
        hours, minutes, seconds = parts
    else:
        raise SubtitleParseError(f"无法识别时间：{value}")
    try:
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    except ValueError as exc:
        raise SubtitleParseError(f"无法识别时间：{value}") from exc


def parse_srt_or_vtt(payload: str) -> list[Caption]:
    """解析 SRT/WebVTT；忽略序号、样式行及 cue settings。"""
    text = (payload or "").lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    captions: list[Caption] = []
    for block in re.split(r"\n\s*\n", text):
        lines = [line for line in block.split("\n") if line.strip()]
        time_index = next((i for i, line in enumerate(lines) if _TIMECODE_RE.search(line)), None)
        if time_index is None:
            continue
        match = _TIMECODE_RE.search(lines[time_index])
        assert match is not None
        cue_text = _clean_text("\n".join(lines[time_index + 1 :]))
        if not cue_text:
            continue
        start = parse_timestamp(match.group("start"))
        end = parse_timestamp(match.group("end"))
        if end < start:
            start, end = end, start
        captions.append(Caption(start, end, cue_text))
    return _normalize_captions(captions)


def parse_bilibili_json(payload: str | dict) -> list[Caption]:
    data = json.loads(payload) if isinstance(payload, str) else payload
    body = data.get("body") if isinstance(data, dict) else None
    if not isinstance(body, list):
        return []
    captions = []
    for item in body:
        if not isinstance(item, dict):
            continue
        cue_text = _clean_text(str(item.get("content") or ""))
        if not cue_text:
            continue
        try:
            start = float(item.get("from", 0))
            end = float(item.get("to", start))
        except (TypeError, ValueError):
            continue
        captions.append(Caption(start, max(start, end), cue_text))
    return _normalize_captions(captions)


def parse_subtitle_payload(payload: str, ext: str = "") -> list[Caption]:
    raw = (payload or "").strip()
    if not raw:
        return []
    if ext.lower() in {"json", "json3"} or raw.startswith("{"):
        try:
            parsed = parse_bilibili_json(raw)
            if parsed:
                return parsed
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    return parse_srt_or_vtt(raw)


def _normalize_captions(captions: Iterable[Caption]) -> list[Caption]:
    ordered = sorted(captions, key=lambda cue: (cue.start, cue.end, cue.text))
    result: list[Caption] = []
    for cue in ordered:
        text = _clean_text(cue.text)
        if not text:
            continue
        normalized = Caption(max(0.0, cue.start), max(cue.start, cue.end), text)
        if result and normalized == result[-1]:
            continue
        result.append(normalized)
    return result


def detect_language_family(lang: str, captions: Sequence[Caption]) -> str:
    """返回 english/chinese/bilingual/unknown，优先参考内容而非不稳定的语言标签。"""
    sample = " ".join(c.text for c in captions[:80])
    cjk_count = len(_CJK_RE.findall(sample))
    latin_count = len(_LATIN_RE.findall(sample))
    code = (lang or "").lower().replace("_", "-")
    code_zh = code.startswith("zh") or code in {"ai-zh", "cn", "chs", "cht"}
    code_en = code.startswith("en") or code == "ai-en"

    total_letters = cjk_count + latin_count
    # 数量阈值覆盖短字幕；占比阈值避免中文正文里偶尔出现 Python/AI 就误判双语。
    if (
        cjk_count >= 4 and latin_count >= 8 and total_letters
        and cjk_count / total_letters >= 0.12
        and latin_count / total_letters >= 0.12
    ):
        return "bilingual"
    if code_zh:
        return "chinese"
    if code_en:
        return "english"
    if cjk_count >= max(4, latin_count / 2):
        return "chinese"
    if latin_count >= max(8, cjk_count * 2):
        return "english"
    return "unknown"


def language_label(lang: str, family: str, kind: str) -> str:
    labels = {
        "zh-cn": "中文（简体）", "zh-hans": "中文（简体）", "zh-hant": "中文（繁体）",
        "ai-zh": "中文（AI）", "en": "English", "en-us": "English (US)",
        "en-gb": "English (UK)", "ai-en": "English（AI）",
    }
    base = labels.get((lang or "").lower(), lang or {
        "english": "English", "chinese": "中文", "bilingual": "中英双语",
    }.get(family, "未知语言"))
    suffix = " · 自动字幕" if kind == "automatic" and "AI" not in base else ""
    return base + suffix


def suggested_track_ids(tracks: Sequence[SubtitleTrack]) -> dict[str, str]:
    bilingual = next((track for track in tracks if track.family == "bilingual"), None)
    if bilingual:
        return {"english": bilingual.id, "chinese": bilingual.id}
    english = next((track for track in tracks if track.family == "english"), None)
    chinese = next((track for track in tracks if track.family == "chinese"), None)
    return {
        "english": english.id if english else "",
        "chinese": chinese.id if chinese else "",
    }


def _line_family(line: str) -> str:
    cjk = len(_CJK_RE.findall(line))
    latin = len(_LATIN_RE.findall(line))
    if cjk and latin:
        return "mixed"
    if cjk:
        return "chinese"
    if latin:
        return "english"
    return "unknown"


def split_bilingual_text(text: str) -> tuple[str, str]:
    """把常见的“英文换行中文”或“英文 | 中文”拆为 (英文, 中文)。"""
    raw_lines: list[str] = []
    for line in _clean_text(text).splitlines():
        pieces = [p.strip() for p in re.split(r"\s{2,}|[|｜]", line) if p.strip()]
        raw_lines.extend(pieces or [line])

    english: list[str] = []
    chinese: list[str] = []
    unknown: list[str] = []
    for line in raw_lines:
        family = _line_family(line)
        if family == "english":
            english.append(line)
        elif family == "chinese":
            chinese.append(line)
        elif family == "mixed":
            # 无显式分隔符时，仅在两侧都像完整文本时按首次语言切换拆分。
            first_cjk = _CJK_RE.search(line)
            first_latin = _LATIN_RE.search(line)
            assert first_cjk and first_latin
            if first_latin.start() < first_cjk.start():
                left, right = line[: first_cjk.start()].strip(), line[first_cjk.start() :].strip()
            else:
                tail = re.search(r"[A-Za-z][A-Za-z\s'’.,!?-]*$", line)
                left, right = (line[: tail.start()].strip(), line[tail.start() :].strip()) if tail else (line, "")
            first, second = (_line_family(left), _line_family(right))
            if first == "english" and second == "chinese" and len(_LATIN_WORD_RE.findall(left)) >= 2:
                english.append(left); chinese.append(right)
            elif first == "chinese" and second == "english" and len(_LATIN_WORD_RE.findall(right)) >= 2:
                chinese.append(left); english.append(right)
            else:
                unknown.append(line)
        else:
            unknown.append(line)

    if unknown:
        target = english if english and not chinese else chinese if chinese and not english else english
        target.extend(unknown)
    return " ".join(english).strip(), " ".join(chinese).strip()


def split_bilingual_track(captions: Sequence[Caption]) -> tuple[list[Caption], list[Caption]]:
    english: list[Caption] = []
    chinese: list[Caption] = []
    for cue in captions:
        en, zh = split_bilingual_text(cue.text)
        if en:
            english.append(Caption(cue.start, cue.end, en))
        if zh:
            chinese.append(Caption(cue.start, cue.end, zh))
    return english, chinese


def _overlap(a: Caption, b: Caption) -> float:
    return max(0.0, min(a.end, b.end) - max(a.start, b.start))


def _join_unique_text(captions: Iterable[Caption]) -> str:
    result: list[str] = []
    seen: set[str] = set()
    for cue in captions:
        text = cue.text.replace("\n", " ").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return " ".join(result)


def align_captions(english: Sequence[Caption], chinese: Sequence[Caption]) -> list[BilingualRow]:
    """按时间重叠对齐；同一翻译覆盖多条英文时自动合并，避免中文重复刷屏。"""
    en = _normalize_captions(english)
    zh = _normalize_captions(chinese)
    if not en:
        return [BilingualRow(c.start, c.end, chinese=c.text.replace("\n", " ")) for c in zh]
    if not zh:
        return [BilingualRow(c.start, c.end, english=c.text.replace("\n", " ")) for c in en]

    rows: list[BilingualRow] = []
    used_zh: set[int] = set()
    left = 0
    for en_cue in en:
        while left < len(zh) and zh[left].end < en_cue.start - 1.2:
            left += 1
        matches: list[tuple[int, Caption]] = []
        cursor = max(0, left - 1)
        while cursor < len(zh) and zh[cursor].start <= en_cue.end + 1.2:
            zh_cue = zh[cursor]
            overlap = _overlap(en_cue, zh_cue)
            shorter = max(0.05, min(en_cue.end - en_cue.start, zh_cue.end - zh_cue.start))
            if overlap >= 0.05 and overlap / shorter >= 0.12:
                matches.append((cursor, zh_cue))
            cursor += 1
        if not matches:
            en_mid = (en_cue.start + en_cue.end) / 2
            nearby = [
                (abs((cue.start + cue.end) / 2 - en_mid), idx, cue)
                for idx, cue in enumerate(zh[max(0, left - 1) : min(len(zh), left + 3)], max(0, left - 1))
            ]
            nearest = min(nearby, default=None)
            if nearest and nearest[0] <= 1.2:
                _, idx, cue = nearest
                matches = [(idx, cue)]

        used_zh.update(idx for idx, _ in matches)
        match_cues = [cue for _, cue in matches]
        start = min([en_cue.start, *[cue.start for cue in match_cues]])
        end = max([en_cue.end, *[cue.end for cue in match_cues]])
        row = BilingualRow(
            start, end,
            english=en_cue.text.replace("\n", " "),
            chinese=_join_unique_text(match_cues),
        )
        # 同一条中文跨越多条英文：合成一行，阅读时不重复显示翻译。
        if rows and row.chinese and row.chinese == rows[-1].chinese and row.start <= rows[-1].end + 0.5:
            previous = rows[-1]
            rows[-1] = BilingualRow(
                min(previous.start, row.start), max(previous.end, row.end),
                english=" ".join(x for x in (previous.english, row.english) if x),
                chinese=row.chinese,
            )
        else:
            rows.append(row)

    for idx, cue in enumerate(zh):
        if idx not in used_zh:
            rows.append(BilingualRow(cue.start, cue.end, chinese=cue.text.replace("\n", " ")))
    return _dedupe_rows(sorted(rows, key=lambda row: (row.start, row.end)))


def _dedupe_rows(rows: Sequence[BilingualRow]) -> list[BilingualRow]:
    result: list[BilingualRow] = []
    for row in rows:
        if result and row.english == result[-1].english and row.chinese == result[-1].chinese:
            previous = result[-1]
            result[-1] = BilingualRow(previous.start, max(previous.end, row.end), row.english, row.chinese)
        else:
            result.append(row)
    return result


def build_bilingual_rows(
    english_track: SubtitleTrack | None,
    chinese_track: SubtitleTrack | None,
) -> list[BilingualRow]:
    if english_track is None and chinese_track is None:
        raise ValueError("请至少选择一条字幕轨")
    if english_track is not None and english_track is chinese_track:
        en, zh = split_bilingual_track(english_track.captions)
        if en and zh:
            return align_captions(en, zh)
        if english_track.family == "chinese":
            return align_captions([], english_track.captions)
        return align_captions(english_track.captions, [])

    en_captions = english_track.captions if english_track else ()
    zh_captions = chinese_track.captions if chinese_track else ()
    return align_captions(en_captions, zh_captions)


def format_timestamp(seconds: float, *, milliseconds: bool = True) -> str:
    total_ms = max(0, round(float(seconds) * 1000))
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    if milliseconds:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def sanitize_filename(value: str, fallback: str = "bilibili-subtitles") -> str:
    cleaned = _ILLEGAL_FILENAME_RE.sub(" ", value or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return (cleaned or fallback)[:100].rstrip(" .")


def render_markdown(
    title: str,
    source_url: str,
    rows: Sequence[BilingualRow],
    english_label: str = "",
    chinese_label: str = "",
) -> str:
    lines = [
        f"# {title}", "",
        f"> 来源：{source_url}",
        f"> 字幕：English `{english_label or '无'}` · 中文 `{chinese_label or '无'}` · 共 {len(rows)} 条",
        "", "---", "",
    ]
    for row in rows:
        lines.append(f"`{format_timestamp(row.start, milliseconds=False)} → {format_timestamp(row.end, milliseconds=False)}`")
        lines.append("")
        if row.english:
            lines.extend([f"**{row.english}**", ""])
        if row.chinese:
            lines.extend([row.chinese, ""])
        lines.extend(["---", ""])
    return "\n".join(lines).rstrip() + "\n"


def write_markdown(path: Path, *args, **kwargs) -> Path:
    path.write_text(render_markdown(*args, **kwargs), encoding="utf-8")
    return path
