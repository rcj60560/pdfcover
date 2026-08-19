"""命令行版：UTF-8 文本文件 → MP3。用于自动化（如 Claude 生成口语回答后直接落音频）。

用法（在 tools/text2mp3/ 目录下）：
    python tts_cli.py 回答.txt -n 话题1-为什么我要学英语 [-v 语音ID] [-r -10] [--pitch -5] [-o 输出目录]

成功后打印 MP3 完整路径。不写 config.json（不动网页端记住的设置）。
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import tts_core as core


def main(argv: list[str] | None = None) -> None:
    cfg = core.load_config()
    ap = argparse.ArgumentParser(description="文本文件 → MP3（edge-tts）")
    ap.add_argument("file", help="UTF-8 文本文件")
    ap.add_argument("-n", "--name", default="", help="输出文件名（不含扩展名；默认取文本文件名）")
    ap.add_argument("-v", "--voice", default=core.DEFAULT_VOICE,
                    help=f"语音 ID，见 tts_core.VOICES（默认 {core.DEFAULT_VOICE}）")
    ap.add_argument("-r", "--rate", type=int, default=0, help="语速百分比，如 -10（默认 0）")
    ap.add_argument("--pitch", type=int, default=0, help="音调赫兹，如 -5（默认 0）")
    ap.add_argument("-o", "--out-dir", default=cfg["out_dir"], help="输出目录（默认读 config.json）")
    args = ap.parse_args(argv)

    text = Path(args.file).read_text(encoding="utf-8").strip()
    if not text:
        raise SystemExit("文本为空")
    if args.voice not in core.VOICES.values():
        raise SystemExit(f"未知语音：{args.voice}（可用列表见 tts_core.VOICES）")

    out = core.resolve_output_path(args.out_dir, args.name or Path(args.file).stem)
    import edge_tts  # 延迟导入，保持纯逻辑可单测

    asyncio.run(edge_tts.Communicate(
        text, args.voice,
        rate=core.format_rate(args.rate), pitch=core.format_pitch(args.pitch),
    ).save(str(out)))
    print(out)


if __name__ == "__main__":
    main()
