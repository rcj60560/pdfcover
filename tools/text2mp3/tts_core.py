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
