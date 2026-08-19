"""text2mp3 核心逻辑（纯函数，可单测）：语音列表、文件名清洗、语速/音调格式、配置读写。

不依赖 Flask / edge-tts，方便 tests/ 直接导入。
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parent
CONFIG_PATH = TOOL_DIR / "config.json"

# 默认输出到 IELTS 笔记库的「口语回答/音频」目录
DEFAULT_OUT_DIR = r"D:\Users\luocj\Obsidian\IELTS\IELTS\学习记录\口语回答\音频"
# 新一代 Multilingual 语音（Ava/Emma/Andrew/Brian）韵律明显更自然，同为免费 edge-tts
DEFAULT_VOICE = "en-US-AvaMultilingualNeural"

# 页面下拉框顺序即此 dict 顺序：新一代在前（默认），其次经典英/美音、中文
VOICES: dict[str, str] = {
    "推荐 · Ava（美音女，最自然）": "en-US-AvaMultilingualNeural",
    "推荐 · Emma（美音女）": "en-US-EmmaMultilingualNeural",
    "推荐 · Andrew（美音男）": "en-US-AndrewMultilingualNeural",
    "推荐 · Brian（美音男）": "en-US-BrianMultilingualNeural",
    "英音 · Sonia（女）": "en-GB-SoniaNeural",
    "英音 · Libby（女）": "en-GB-LibbyNeural",
    "英音 · Ryan（男）": "en-GB-RyanNeural",
    "美音 · Aria（女）": "en-US-AriaNeural",
    "美音 · Jenny（女）": "en-US-JennyNeural",
    "美音 · Guy（男）": "en-US-GuyNeural",
    "中文 · 晓晓（女）": "zh-CN-XiaoxiaoNeural",
    "中文 · 云希（男）": "zh-CN-YunxiNeural",
}

_ILLEGAL = re.compile(r'[\\/:*?"<>|\r\n\t]+')


def sanitize_filename(name: str) -> str:
    """清洗文件名：非法字符换成空格、连续空白折叠为一个、去首尾空白和末尾的点；全空则时间戳默认名。"""
    cleaned = _ILLEGAL.sub(" ", name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().rstrip(".")
    return cleaned or f"tts-{datetime.now():%Y%m%d-%H%M%S}"


def format_rate(percent: int) -> str:
    """整数百分比 → edge-tts 语速串（如 -10 → "-10%"）；clamp 到 [-50, 100]。"""
    p = max(-50, min(100, int(percent)))
    return f"{p:+d}%"


def format_pitch(hz: int) -> str:
    """整数赫兹 → edge-tts 音调串（如 -5 → "-5Hz"）；clamp 到 [-50, 50]。音调发怪时可微调。"""
    h = max(-50, min(50, int(hz)))
    return f"{h:+d}Hz"


def load_config() -> dict:
    """读 config.json（记住上次的语音/语速/音调/输出目录）；缺失或损坏 → 全默认。"""
    default = {"voice": DEFAULT_VOICE, "rate": 0, "pitch": 0, "out_dir": DEFAULT_OUT_DIR}
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default
    return {**default, **{k: data[k] for k in default if k in data}}


def save_config(voice: str, rate: int, pitch: int, out_dir: str) -> dict:
    """把本次使用的设置写回 config.json。"""
    cfg = {"voice": voice, "rate": int(rate), "pitch": int(pitch), "out_dir": str(out_dir)}
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return cfg


def resolve_output_path(out_dir: str, filename: str) -> Path:
    """输出目录 + 原始文件名 → 完整 .mp3 路径（文件名自动清洗，目录自动创建）。"""
    path = Path(out_dir) / (sanitize_filename(filename) + ".mp3")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


# ---------- timeline（词级时间轴） ----------

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+")


def split_sentences_text(text: str) -> list[str]:
    """按句末标点（. ! ? …）切原文，保留标点；丢弃空白片段。"""
    return [p for p in _SENTENCE_SPLIT.split(text.strip()) if p.strip()]


def _tokens(s: str) -> list[str]:
    """仅保留字母数字撇号，小写——用于把事件词数对到原文句子上。"""
    return re.findall(r"[a-zA-Z0-9']+", s.lower())


def _derive_sentences(words: list[dict], text: str) -> list[dict]:
    n = len(words)
    if n == 0:
        return []
    whole = {"text": text.strip(), "i": 0, "j": n - 1,
             "start": words[0]["s"], "end": words[-1]["s"] + words[-1]["d"]}
    sent_texts = split_sentences_text(text)
    if not sent_texts:
        return [whole]
    out: list[dict] = []
    idx = 0
    for st in sent_texts:
        if idx >= n:
            break
        j = min(idx + max(len(_tokens(st)), 1), n) - 1
        out.append({"text": st, "i": idx, "j": j,
                    "start": words[idx]["s"], "end": words[j]["s"] + words[j]["d"]})
        idx = j + 1
    if idx < n and out:  # 尾部未覆盖的词并入最后一句
        out[-1]["j"] = n - 1
        out[-1]["end"] = words[-1]["s"] + words[-1]["d"]
    return out


def build_timeline(events: list[dict], text: str = "", voice: str = "",
                   rate: str = "+0%", pitch: str = "+0Hz", translation: str = "") -> dict:
    """edge-tts stream 事件（100ns 单位）→ timeline dict（毫秒单位）。纯函数。"""
    words = [{"t": ev["text"], "s": ev["offset"] // 10000, "d": ev["duration"] // 10000}
             for ev in events if ev.get("type") == "WordBoundary"]
    return {"voice": voice, "rate": rate, "pitch": pitch,
            "words": words, "sentences": _derive_sentences(words, text),
            "translation": translation}


def timeline_path(mp3_path: Path) -> Path:
    return mp3_path.with_suffix(".json")


def write_timeline(mp3_path: Path, timeline: dict) -> Path:
    p = timeline_path(mp3_path)
    p.write_text(json.dumps(timeline, ensure_ascii=False), encoding="utf-8")
    return p


class StreamSink:
    """消费 edge-tts stream() 事件流：音频块写文件、收 WordBoundary。纯同步可单测。"""

    def __init__(self, mp3_path: Path):
        self._f = open(mp3_path, "wb")
        self.events: list[dict] = []

    def feed(self, chunk: dict) -> None:
        if chunk.get("type") == "audio":
            self._f.write(chunk["data"])
        elif chunk.get("type") == "WordBoundary":
            self.events.append(chunk)

    def close(self) -> None:
        self._f.close()


async def synthesize(text: str, voice: str, rate: str, pitch: str,
                     mp3_path: Path, translation: str = "") -> Path:
    """edge-tts 合成：MP3 与同名 timeline json 一起落地，返回 json 路径。"""
    import edge_tts  # 延迟导入，保持纯逻辑可单测

    sink = StreamSink(mp3_path)
    try:
        try:
            # edge-tts 7.x 默认发 SentenceBoundary，必须显式要 WordBoundary 才有词级时间轴
            async for chunk in edge_tts.Communicate(
                    text, voice, rate=rate, pitch=pitch, boundary="WordBoundary").stream():
                sink.feed(chunk)
        finally:
            sink.close()   # 先关句柄再删文件（Windows 下删打开中的文件会 PermissionError）
    except BaseException:
        mp3_path.unlink(missing_ok=True)                 # 不留截断 mp3
        timeline_path(mp3_path).unlink(missing_ok=True)  # 不留旧 json 与新 mp3 错配
        raise
    return write_timeline(mp3_path, build_timeline(
        sink.events, text=text, voice=voice, rate=rate, pitch=pitch, translation=translation))
