"""链接进、产物出：B站字幕轨优先，无字幕时用 faster-whisper 识别。

用法：
    python direct_generate.py URL [-o 输出目录] [--browser edge]
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path
from typing import Callable, Sequence

import subtitle_core as core
from extractor import ExtractionError, extract_video
from xlsx_export import build_xlsx


TOOL_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = TOOL_DIR / "outputs"


def merge_captions(
    captions: Sequence[core.Caption],
    max_duration: float = 11.0,
    max_chars: int = 170,
    max_gap: float = 1.2,
) -> list[core.Caption]:
    """把 Whisper 的碎片合成适合电脑阅读/翻译的字幕块。"""
    result: list[core.Caption] = []
    for cue in captions:
        text = " ".join(cue.text.split())
        if not text:
            continue
        current = core.Caption(cue.start, cue.end, text)
        if not result:
            result.append(current)
            continue
        previous = result[-1]
        combined_text = f"{previous.text} {current.text}".strip()
        can_merge = (
            current.start - previous.end <= max_gap
            and current.end - previous.start <= max_duration
            and len(combined_text) <= max_chars
        )
        if can_merge:
            result[-1] = core.Caption(previous.start, current.end, combined_text)
        else:
            result.append(current)
    return result


def apply_translations(
    rows: Sequence[core.BilingualRow],
    indices: Sequence[int],
    translations: Sequence[str],
    target: str,
) -> list[core.BilingualRow]:
    if len(indices) != len(translations):
        raise ValueError("翻译结果数量与字幕数量不一致")
    result = list(rows)
    for index, translated in zip(indices, translations, strict=True):
        value = " ".join((translated or "").split())
        if target == "chinese":
            result[index] = replace(result[index], chinese=value)
        elif target == "english":
            result[index] = replace(result[index], english=value)
        else:
            raise ValueError(f"未知翻译目标：{target}")
    return result


def translate_texts(
    texts: Sequence[str],
    source: str,
    target: str,
    progress: Callable[[int, int], None] | None = None,
) -> list[str]:
    try:
        from deep_translator import GoogleTranslator
    except ImportError as exc:
        raise RuntimeError("缺少翻译依赖，请安装 requirements-whisper.txt") from exc

    translator = GoogleTranslator(source=source, target=target)
    translated: list[str] = []
    total = len(texts)
    # translate_batch 内部会维护同一个 translator，减少反复初始化；小批次便于失败重试。
    for start in range(0, total, 20):
        batch = list(texts[start : start + 20])
        try:
            values = translator.translate_batch(batch)
            if len(values) != len(batch):
                raise RuntimeError("翻译服务返回数量不一致")
        except Exception:
            values = []
            for text in batch:
                last_error: Exception | None = None
                for attempt in range(3):
                    try:
                        values.append(translator.translate(text))
                        last_error = None
                        break
                    except Exception as exc:  # 网络限流时指数退避
                        last_error = exc
                        time.sleep(1.5 * (attempt + 1))
                if last_error is not None:
                    raise RuntimeError(f"机器翻译失败：{last_error}") from last_error
        translated.extend(str(value or "") for value in values)
        if progress:
            progress(len(translated), total)
    return translated


def fill_missing_languages(rows: Sequence[core.BilingualRow]) -> tuple[list[core.BilingualRow], list[str]]:
    result = list(rows)
    methods: list[str] = []
    missing_zh = [index for index, row in enumerate(result) if row.english and not row.chinese]
    if missing_zh:
        print(f"[4/5] 翻译英文 → 中文：{len(missing_zh)} 条", flush=True)
        values = translate_texts(
            [result[index].english for index in missing_zh], "en", "zh-CN",
            lambda done, total: print(f"      翻译进度 {done}/{total}", flush=True),
        )
        result = apply_translations(result, missing_zh, values, "chinese")
        methods.append("中文：Google Translate 机器翻译")

    missing_en = [index for index, row in enumerate(result) if row.chinese and not row.english]
    if missing_en:
        print(f"[4/5] 翻译中文 → 英文：{len(missing_en)} 条", flush=True)
        values = translate_texts(
            [result[index].chinese for index in missing_en], "zh-CN", "en",
            lambda done, total: print(f"      翻译进度 {done}/{total}", flush=True),
        )
        result = apply_translations(result, missing_en, values, "english")
        methods.append("English：Google Translate 机器翻译")
    return result, methods


def _yt_dlp_options(browser: str) -> dict:
    options = {
        "noplaylist": True,
        "playlistend": 1,
        "socket_timeout": 30,
        "retries": 5,
        "fragment_retries": 5,
    }
    if browser != "none":
        options["cookiesfrombrowser"] = (browser, None, None, None)
    return options


def download_audio(url: str, temp_dir: Path, browser: str) -> tuple[Path, dict]:
    try:
        import yt_dlp
    except ImportError as exc:
        raise RuntimeError("缺少 yt-dlp，请安装 requirements.txt") from exc

    options = {
        **_yt_dlp_options(browser),
        "format": "bestaudio[acodec!=none]/bestaudio/best",
        "outtmpl": str(temp_dir / "source.%(ext)s"),
        "quiet": False,
        "no_warnings": False,
        "overwrites": True,
    }
    with yt_dlp.YoutubeDL(options) as downloader:
        info = downloader.extract_info(core.normalize_bilibili_url(url), download=True)
    if not isinstance(info, dict):
        raise RuntimeError("没有读到有效的视频信息")
    candidates = [
        path for path in temp_dir.glob("source.*")
        if path.is_file() and path.suffix.lower() not in {".part", ".ytdl", ".json"}
    ]
    if not candidates:
        raise RuntimeError("音频下载完成，但没有找到音频文件")
    return max(candidates, key=lambda path: path.stat().st_size), info


def transcribe_audio(audio_path: Path, model_name: str) -> list[core.Caption]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("缺少 faster-whisper，请安装 requirements-whisper.txt") from exc

    threads = min(8, max(2, os.cpu_count() or 4))
    print(f"[3/5] 加载 Whisper {model_name}（首次运行会下载模型）", flush=True)
    model = WhisperModel(model_name, device="cpu", compute_type="int8", cpu_threads=threads)
    segments, info = model.transcribe(
        str(audio_path), language="en", task="transcribe", beam_size=5,
        vad_filter=True, condition_on_previous_text=True, word_timestamps=False,
        log_progress=True,
        initial_prompt="English vocabulary lesson. Vocabulary in Use Advanced, Unit 14.",
    )
    print(f"      检测语言：{info.language}（{info.language_probability:.1%}）", flush=True)
    captions: list[core.Caption] = []
    for segment in segments:
        text = " ".join(str(segment.text).split())
        if text:
            captions.append(core.Caption(float(segment.start), float(segment.end), text))
    if not captions:
        raise RuntimeError("Whisper 没有识别出语音内容")
    merged = merge_captions(captions)
    print(f"      识别完成：{len(captions)} 个片段 → {len(merged)} 条阅读字幕", flush=True)
    return merged


def rows_from_native_tracks(url: str, browser: str) -> tuple[str, str, list[core.BilingualRow], str, str] | None:
    try:
        video = extract_video(url, browser)
    except ExtractionError as exc:
        print(f"[1/5] 原生字幕不可用：{exc}", flush=True)
        return None
    suggested = core.suggested_track_ids(video.tracks)
    by_id = {track.id: track for track in video.tracks}
    english = by_id.get(suggested["english"])
    chinese = by_id.get(suggested["chinese"])
    if english is None and chinese is None:
        return None
    rows = core.build_bilingual_rows(english, chinese)
    print(f"[1/5] 使用视频字幕轨：{len(rows)} 条", flush=True)
    return (
        video.title, video.source_url, rows,
        english.label if english else "无",
        chinese.label if chinese else "无",
    )


def generate(
    url: str,
    output_dir: Path,
    browser: str = "none",
    model_name: str = "small.en",
    translate: bool = True,
) -> tuple[Path, Path]:
    normalized_url = core.normalize_bilibili_url(url)
    native = rows_from_native_tracks(normalized_url, browser)
    methods: list[str] = []
    if native:
        title, source_url, rows, english_label, chinese_label = native
        methods.extend([f"English：{english_label}", f"中文：{chinese_label}"])
    else:
        print("[2/5] 下载临时音频（最终不会保留）", flush=True)
        with tempfile.TemporaryDirectory(prefix="bili-subtitle-") as temp:
            audio_path, info = download_audio(normalized_url, Path(temp), browser)
            size_mb = audio_path.stat().st_size / 1024 / 1024
            print(f"      音频：{audio_path.suffix} · {size_mb:.1f} MB", flush=True)
            captions = transcribe_audio(audio_path, model_name)
        title = str(info.get("title") or "B站视频")
        source_url = str(info.get("webpage_url") or normalized_url)
        rows = core.align_captions(captions, [])
        methods.append(f"English：faster-whisper {model_name} 机器识别")

    if translate:
        rows, translation_methods = fill_missing_languages(rows)
        methods.extend(translation_methods)
    print("[5/5] 写入 Markdown / Excel", flush=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    basename = core.sanitize_filename(title) + "-双语字幕"
    md_path = output_dir / f"{basename}.md"
    xlsx_path = output_dir / f"{basename}.xlsx"
    method_text = "；".join(dict.fromkeys(methods))
    markdown = core.render_markdown(title, source_url, rows, method_text, method_text)
    markdown += f"\n> 生成说明：{method_text}\n"
    md_path.write_text(markdown, encoding="utf-8")
    xlsx_path.write_bytes(build_xlsx(title, source_url, rows))
    print(f"完成：\n  {md_path}\n  {xlsx_path}", flush=True)
    return md_path, xlsx_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="B站链接直接生成中英对照 MD / XLSX")
    parser.add_argument("url", help="B站视频链接、b23.tv 短链或 BV 号")
    parser.add_argument("-o", "--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--browser", choices=("none", "edge", "chrome", "firefox"), default="none")
    parser.add_argument("--whisper-model", default="small.en", help="默认 small.en；速度优先可用 base.en")
    parser.add_argument("--no-translate", action="store_true", help="不自动补齐缺失语言")
    args = parser.parse_args(argv)
    try:
        generate(args.url, args.output_dir, args.browser, args.whisper_model, not args.no_translate)
    except Exception as exc:
        print(f"失败：{exc}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
