"""借用 text2mp3 的 tts_core 做「字幕 → MP3」。

模块互调只发生在核心逻辑层：import 兄弟目录的纯逻辑模块，
不依赖、不启动 text2mp3 的网页应用，两边 Flask 保持相互独立。
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Callable

import direct_generate
from subtitle_core import BilingualRow

TOOL_DIR = Path(__file__).resolve().parent
TEXT2MP3_DIR = (TOOL_DIR.parent / "text2mp3").resolve()

TTS_INSTALL_HINT = (
    "缺少文本转语音依赖：请确认 tools/text2mp3 存在，"
    "并运行 python -m pip install -r tools/text2mp3/requirements.txt"
)

# 单片合成上限：edge-tts 对超长单请求容易超时，按句界分片更稳
CHUNK_CHAR_LIMIT = 2500


def load_tts_core():
    """导入 text2mp3 的 tts_core（纯逻辑、无 Flask 依赖）。"""
    if str(TEXT2MP3_DIR) not in sys.path:
        sys.path.insert(0, str(TEXT2MP3_DIR))
    try:
        import tts_core
    except ImportError as exc:
        raise RuntimeError(TTS_INSTALL_HINT) from exc
    return tts_core


def missing_tts_dependency() -> str | None:
    """依赖检查：tts_core 或 edge-tts 缺失时返回安装提示。"""
    try:
        load_tts_core()
    except RuntimeError as exc:
        return str(exc)
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        return TTS_INSTALL_HINT
    return None


def format_rate(percent: int) -> str:
    """整数百分比 → edge-tts 语速串（如 -10 → "-10%"）；clamp 到 [-50, 100]。与 text2mp3 行为一致。"""
    value = max(-50, min(100, int(percent)))
    return f"{value:+d}%"


def rows_to_speech_text(rows: list[BilingualRow] | tuple[BilingualRow, ...], lang: str) -> str:
    """双语行 → 朗读文本：按语言取列、跳过空句、按时间轴顺序拼接。"""
    if lang not in {"english", "chinese"}:
        raise ValueError(f"未知朗读语言：{lang}")
    parts = [getattr(row, lang).strip() for row in rows]
    return " ".join(part for part in parts if part)


def synthesize_chunks(
    text: str,
    voice: str,
    rate: str = "+0%",
    pitch: str = "+0Hz",
    *,
    limit: int = CHUNK_CHAR_LIMIT,
    work_dir: Path,
    synthesize: Callable | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> bytes:
    """长文本按句界分片合成 MP3，返回拼接后的完整字节。

    work_dir 由调用方创建/清理；分片 MP3 写在里面，读走即用。
    """
    chunks = direct_generate.split_for_limit(text, limit)
    if synthesize is None:
        synthesize = load_tts_core().synthesize
    buffer = bytearray()
    for index, chunk in enumerate(chunks, start=1):
        part_path = work_dir / f"part-{index:03d}.mp3"
        asyncio.run(synthesize(chunk, voice, rate, pitch, part_path))
        buffer += part_path.read_bytes()
        if progress:
            progress(index, len(chunks))
    return bytes(buffer)
