"""链接进、产物出：B站字幕轨优先，无字幕时用 faster-whisper 识别。

用法：
    python direct_generate.py URL [-o 输出目录] [--browser edge]
"""
from __future__ import annotations

import argparse
import os
import re
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


_SENTENCE_ENDERS = ".!?。！？；;"
_CJK_TAIL = re.compile(r"[一-鿿。！？；：、）】]$")
Backend = tuple[str, Callable[[str], str], int]


def _iter_sentences(text: str):
    buffer: list[str] = []
    for char in text:
        buffer.append(char)
        if char in _SENTENCE_ENDERS:
            yield "".join(buffer)
            buffer = []
    if buffer:
        yield "".join(buffer)


def _hard_split(piece: str, limit: int) -> list[str]:
    """单句仍超长时的兜底切分：先按空格词切，再不行按字符切。"""
    if len(piece) <= limit:
        return [piece]
    parts: list[str] = []
    current = ""
    for word in piece.split(" "):
        if len(word) > limit:
            if current:
                parts.append(current)
                current = ""
            parts.extend(word[start : start + limit] for start in range(0, len(word), limit))
        elif current and len(current) + 1 + len(word) > limit:
            parts.append(current)
            current = word
        else:
            current = f"{current} {word}" if current else word
    if current:
        parts.append(current)
    return parts


def split_for_limit(text: str, limit: int) -> list[str]:
    """按句子边界把长文本切成不超过 limit 的分片（"" 拼接可还原原文）。"""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current = ""
    for sentence in _iter_sentences(text):
        if len(sentence) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_hard_split(sentence, limit))
        elif current and len(current) + len(sentence) > limit:
            chunks.append(current)
            current = sentence
        else:
            current += sentence
    if current:
        chunks.append(current)
    return chunks


def join_parts(parts: Sequence[str]) -> str:
    """按目标语言拼接分片译文：中文直接连写，英文用空格。"""
    cleaned = [part.strip() for part in parts if part and part.strip()]
    if not cleaned:
        return ""
    if all(_CJK_TAIL.search(part) for part in cleaned):
        return "".join(cleaned)
    return " ".join(cleaned)


def split_methods(methods: Sequence[str]) -> tuple[str, str]:
    """把 "English：…/中文：…" 方法列表拆成 (英文标签, 中文标签)，去重。"""
    unique = list(dict.fromkeys(methods))
    english = "；".join(
        method.split("：", 1)[1] for method in unique if method.startswith("English：")
    )
    chinese = "；".join(
        method.split("：", 1)[1] for method in unique if method.startswith("中文：")
    )
    return english, chinese


def _translate_with_retries(
    fn: Callable[[str], str],
    text: str,
    retries: int,
    retry_sleep: float,
) -> str:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            return fn(text)
        except Exception as exc:  # 网络限流时线性退避
            last_error = exc
            if attempt + 1 < retries and retry_sleep:
                time.sleep(retry_sleep * (attempt + 1))
    raise RuntimeError(f"机器翻译失败：{last_error}") from last_error


def _google_reachable(timeout: float = 3.0) -> bool:
    """3 秒 HEAD 探测，避免对被墙端点发起无超时请求而长时间挂起。"""
    try:
        import requests

        response = requests.head("https://translate.googleapis.com", timeout=timeout)
        return response.status_code < 500
    except Exception:
        return False


def _build_backends(source: str, target: str, probe: bool = True) -> list[Backend]:
    """翻译后端链：Google 质量优先，不可达时自动退到 MyMemory（免 key）。"""
    try:
        from deep_translator import GoogleTranslator, MyMemoryTranslator
    except ImportError as exc:
        raise RuntimeError("缺少翻译依赖，请安装 requirements-whisper.txt") from exc

    names = {"en": "english", "zh-CN": "chinese simplified"}
    chain: list[Backend] = []
    if not probe or _google_reachable():
        google = GoogleTranslator(source=source, target=target)
        chain.append(("Google Translate", google.translate, 4500))
    else:
        print("      Google 翻译不可达，直接使用 MyMemory（有代理时可设 HTTPS_PROXY）", flush=True)
    # MyMemory 匿名额度有限；设置环境变量 MYMEMORY_EMAIL 可提额（可选）。
    email = os.environ.get("MYMEMORY_EMAIL") or None
    mymemory = MyMemoryTranslator(source=names[source], target=names[target], email=email)

    def mymemory_translate(text: str) -> str:
        result = mymemory.translate(text)
        # MyMemory 额度用尽时返回 HTTP 200，但译文是警告文本，必须识别为失败。
        if result and result.strip().upper().startswith("MYMEMORY WARNING"):
            raise RuntimeError(f"MyMemory 额度告警：{result.strip()[:120]}")
        return result

    chain.append(("MyMemory", mymemory_translate, 480))
    return chain


def translate_texts(
    texts: Sequence[str],
    source: str,
    target: str,
    progress: Callable[[int, int], None] | None = None,
    backends: Sequence[Backend] | None = None,
    retries: int = 3,
    retry_sleep: float = 1.5,
) -> tuple[list[str], str]:
    """多后端翻译：当前后端重试耗尽即永久切换下一个，返回 (译文, 实际后端名)。"""
    active = list(backends) if backends is not None else _build_backends(source, target)
    if not active:
        raise RuntimeError("没有可用的翻译后端")
    results: list[str] = []
    used: list[str] = []
    total = len(texts)
    for text in texts:
        translated: str | None = None
        while active:
            label, fn, limit = active[0]
            try:
                parts = [
                    _translate_with_retries(fn, chunk, retries, retry_sleep)
                    for chunk in split_for_limit(text, limit)
                ]
            except Exception:
                print(f"      翻译后端 {label} 不可用，切换下一个", flush=True)
                active.pop(0)
                continue
            translated = join_parts(parts)
            if label not in used:
                used.append(label)
            break
        if translated is None:
            raise RuntimeError("所有翻译后端均失败")
        results.append(translated)
        if progress:
            progress(len(results), total)
    return results, " / ".join(used)


def fill_missing_languages(
    rows: Sequence[core.BilingualRow],
    backends: Sequence[Backend] | None = None,
) -> tuple[list[core.BilingualRow], list[str]]:
    result = list(rows)
    methods: list[str] = []
    missing_zh = [index for index, row in enumerate(result) if row.english and not row.chinese]
    if missing_zh:
        print(f"[4/5] 翻译英文 → 中文：{len(missing_zh)} 条", flush=True)
        values, backend_label = translate_texts(
            [result[index].english for index in missing_zh], "en", "zh-CN",
            lambda done, total: print(f"      翻译进度 {done}/{total}", flush=True),
            backends=backends,
        )
        result = apply_translations(result, missing_zh, values, "chinese")
        methods.append(f"中文：{backend_label} 机器翻译")

    missing_en = [index for index, row in enumerate(result) if row.chinese and not row.english]
    if missing_en:
        print(f"[4/5] 翻译中文 → 英文：{len(missing_en)} 条", flush=True)
        values, backend_label = translate_texts(
            [result[index].chinese for index in missing_en], "zh-CN", "en",
            lambda done, total: print(f"      翻译进度 {done}/{total}", flush=True),
            backends=backends,
        )
        result = apply_translations(result, missing_en, values, "english")
        methods.append(f"English：{backend_label} 机器翻译")
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
    english_text, chinese_text = split_methods(methods)
    markdown = core.render_markdown(title, source_url, rows, english_text, chinese_text)
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
