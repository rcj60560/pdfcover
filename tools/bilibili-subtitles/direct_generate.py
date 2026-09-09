"""链接进、产物出：B站字幕轨优先，无字幕时用 faster-whisper 识别。

用法：
    python direct_generate.py URL [-o 输出目录] [--browser edge]
"""
from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
import json
import tempfile
import time
from dataclasses import asdict, dataclass, replace
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


class PartialTranslationError(RuntimeError):
    """Incomplete work is still useful; callers can export it or resume later."""

    def __init__(self, message, translations=(), label='', rows=(), methods=()):
        super().__init__(message)
        self.translations = list(translations)
        self.label = label
        self.rows = list(rows)
        self.methods = list(methods)


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


_RATE_LIMIT_MARKERS = ("too many requests", "429", "rate limit", "throttl")


def _is_rate_limit_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in _RATE_LIMIT_MARKERS)


def _translate_with_retries(
    fn: Callable[[str], str],
    text: str,
    retries: int,
    retry_sleep: float,
    log: Callable[[str], None] | None = None,
) -> str:
    say = log or (lambda message: None)
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            value = fn(text)
            if not isinstance(value, str) or not value.strip():
                raise RuntimeError('翻译服务返回空译文')
            return value
        except Exception as exc:
            last_error = exc
            if not getattr(exc, 'retryable', True):
                raise
            if attempt + 1 < retries:
                if _is_rate_limit_error(exc):
                    # 限流按秒级恢复：短退避只会连撞，等 10s/20s 再试
                    wait = max(10.0 * (attempt + 1), retry_sleep * (attempt + 1))
                    say(f"      翻译触发限流，等待 {wait:.0f}s 后重试…")
                else:
                    wait = retry_sleep * (attempt + 1)
                time.sleep(wait)
    raise RuntimeError(f"机器翻译失败：{last_error}") from last_error


def _google_reachable(timeout: float = 3.0) -> bool:
    """3 秒 HEAD 探测，避免对被墙端点发起无超时请求而长时间挂起。"""
    try:
        import requests

        from translation_backends import GOOGLE_URL
        response = requests.head(GOOGLE_URL, timeout=timeout)
        try:
            return response.status_code < 400
        finally:
            response.close()
    except Exception:
        return False


def _build_backends(source: str, target: str, probe: bool = False) -> list[Backend]:
    """构造后端不触网；可选 probe 仅供诊断，实际请求由后端超时/冷却保护。"""
    try:
        import requests  # noqa: F401
        import bs4  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("缺少翻译依赖，请安装 requirements-whisper.txt") from exc

    from translation_backends import HttpTranslator
    from translation_store import default_store
    store = default_store()
    chain: list[Backend] = []
    if not probe or _google_reachable():
        google = HttpTranslator('Google Translate', source, target, store)
        chain.append(("Google Translate", google.translate, 4500))
    else:
        print("      Google 翻译不可达，直接使用 MyMemory（有代理时可设 HTTPS_PROXY）", flush=True)
    mymemory = HttpTranslator('MyMemory', source, target, store)
    chain.append(("MyMemory", mymemory.translate, 480))
    return chain


def translation_failure_hint(exc: Exception) -> str:
    """把翻译失败原因翻译成用户可执行的下一步操作（网页/命令行通用）。"""
    text = str(exc)
    if "额度" in text or "MYMEMORY WARNING" in text.upper():
        return ("MyMemory 免费额度已用尽：设置环境变量 MYMEMORY_EMAIL=你的邮箱 可提额"
                "（额度每天重置），恢复后重试翻译即可")
    if "Google" in text:
        return "Google 翻译失败：确认代理可用（HTTPS_PROXY 环境变量），或稍后重试翻译"
    return ("翻译服务暂时不可用（多为限流或网络波动）：稍等片刻重试翻译；"
            "如有代理可设置 HTTPS_PROXY 环境变量改走 Google")


def translate_texts(
    texts: Sequence[str],
    source: str,
    target: str,
    progress: Callable[[int, int], None] | None = None,
    backends: Sequence[Backend] | None = None,
    retries: int = 3,
    retry_sleep: float = 1.5,
    request_interval: float = 0.3,
    log: Callable[[str], None] | None = None,
    cache=None,
) -> tuple[list[str], str]:
    """多后端翻译：当前后端重试耗尽即永久切换下一个，返回 (译文, 实际后端名)。"""
    say = log or (lambda message: print(message, flush=True))
    active = list(backends) if backends is not None else _build_backends(source, target)
    if cache is None and backends is None:
        from translation_store import default_store
        cache = default_store()
    if not active:
        raise RuntimeError("没有可用的翻译后端")
    configured = tuple(active)
    results: list[str] = []
    used: list[str] = []
    total = len(texts)
    last_error: Exception | None = None
    paced = False  # 仅第一个请求前不等待
    memo = {}

    def read_cached(namespace, chunk):
        key = (namespace, chunk)
        value = memo.get(key)
        if value is None and cache is not None:
            try:
                value = cache.get(namespace, chunk)
            except (OSError, sqlite3.Error) as exc:
                say(f'      无法读取翻译缓存，本次继续请求后端：{exc}')
                value = None
        if isinstance(value, str) and value.strip():
            memo[key] = value
            return value
        return None

    def split_chunks(label, text, limit):
        from translation_backends import split_utf8
        return split_utf8(text, limit) if label == 'MyMemory' else split_for_limit(text, limit)

    for text in texts:
        translated: str | None = None
        # Cached results from any provider take precedence over new requests, even
        # if that provider is cooling down or was disabled earlier in this batch.
        for label, _, limit in configured:
            chunks = split_chunks(label, text, limit)
            saved_parts = [read_cached(f'translation-v2:{label}:{source}:{target}', chunk) for chunk in chunks]
            if saved_parts and all(part is not None for part in saved_parts):
                translated = join_parts(saved_parts)
                say(f'      复用已保存译文（{label}）')
                if label not in used:
                    used.append(label)
                break
        while translated is None and active:
            label, fn, limit = active[0]
            try:
                parts = []
                chunks = split_chunks(label, text, limit)
                for chunk in chunks:
                    namespace = f'translation-v2:{label}:{source}:{target}'
                    key = (namespace, chunk)
                    saved = read_cached(namespace, chunk)
                    if saved is not None:
                        parts.append(saved)
                        say('      复用已保存译文')
                        continue
                    if paced and backends is not None:
                        # Injectable/custom providers retain the local pacing API.
                        time.sleep(request_interval)
                    paced = True
                    value = _translate_with_retries(fn, chunk, retries, retry_sleep, log=say)
                    memo[key] = value
                    if cache is not None:
                        try:
                            cache.put(namespace, chunk, value)
                        except (OSError, sqlite3.Error) as exc:
                            say(f'      翻译缓存未能保存，本次译文仍会保留：{exc}')
                    parts.append(value)
            except Exception as exc:
                last_error = exc
                if backends is None and getattr(exc, 'retryable', True):
                    # Retry exhaustion should not restart a failing provider in
                    # every new job. The HTTP adapters share this store as well.
                    from translation_store import default_store
                    try:
                        default_store().cooldown(label, 60, str(exc))
                    except (OSError, sqlite3.Error) as cache_exc:
                        say(f'      无法保存后端冷却状态，本次仍会切换后端：{cache_exc}')
                say(f"      翻译后端 {label} 不可用（{exc}），切换下一个")
                active.pop(0)
                continue
            translated = join_parts(parts)
            if label not in used:
                used.append(label)
            break
        if translated is None:
            raise PartialTranslationError(f"所有翻译后端均失败：{last_error}", results, ' / '.join(used))
        results.append(translated)
        if progress:
            progress(len(results), total)
    return results, " / ".join(used)


def fill_missing_languages(
    rows: Sequence[core.BilingualRow],
    backends: Sequence[Backend] | None = None,
    log: Callable[[str], None] | None = None,
) -> tuple[list[core.BilingualRow], list[str]]:
    say = log or (lambda message: print(message, flush=True))
    result = list(rows)
    methods: list[str] = []
    missing_zh = [index for index, row in enumerate(result) if row.english and not row.chinese]
    if missing_zh:
        say(f"[4/5] 翻译英文 → 中文：{len(missing_zh)} 条")
        try:
            values, backend_label = translate_texts(
                [result[index].english for index in missing_zh], "en", "zh-CN",
                lambda done, total: say(f"      翻译进度 {done}/{total}"),
                backends=backends, log=say,
            )
        except PartialTranslationError as exc:
            exc.rows = apply_translations(result, missing_zh[:len(exc.translations)], exc.translations, 'chinese')
            exc.methods = methods + ([f'中文：{exc.label} 机器翻译'] if exc.label else [])
            raise
        result = apply_translations(result, missing_zh, values, "chinese")
        methods.append(f"中文：{backend_label} 机器翻译")

    missing_en = [index for index, row in enumerate(result) if row.chinese and not row.english]
    if missing_en:
        say(f"[4/5] 翻译中文 → 英文：{len(missing_en)} 条")
        try:
            values, backend_label = translate_texts(
                [result[index].chinese for index in missing_en], "zh-CN", "en",
                lambda done, total: say(f"      翻译进度 {done}/{total}"),
                backends=backends, log=say,
            )
        except PartialTranslationError as exc:
            exc.rows = apply_translations(result, missing_en[:len(exc.translations)], exc.translations, 'english')
            exc.methods = methods + ([f'English：{exc.label} 机器翻译'] if exc.label else [])
            raise
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
        # 转写只需要音频：优先最低码率纯音频（B 站通常为 64k m4a，Whisper 内部会重采样，
        # 高码率毫无收益）；万一被迫落到含画面的合成流，也选 worst，避免拉高清视频。
        "format": "worstaudio[acodec!=none]/worstaudio/bestaudio[acodec!=none]/worst[acodec!=none]/best",
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


DEFAULT_TRANSCRIBE_PROMPT = "Spoken English with clear pronunciation and complete sentences."


def transcribe_audio(
    audio_path: Path,
    model_name: str,
    *,
    initial_prompt: str | None = None,
    log: Callable[[str], None] | None = None,
) -> list[core.Caption]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("缺少 faster-whisper，请安装 requirements-whisper.txt") from exc

    say = log or (lambda message: print(message, flush=True))
    threads = min(8, max(2, os.cpu_count() or 4))
    say(f"[3/5] 加载 Whisper {model_name}（首次运行会下载模型）")
    model = WhisperModel(model_name, device="cpu", compute_type="int8", cpu_threads=threads)
    segments, info = model.transcribe(
        str(audio_path), language="en", task="transcribe", beam_size=5,
        vad_filter=True, condition_on_previous_text=True, word_timestamps=False,
        log_progress=True,
        initial_prompt=initial_prompt if initial_prompt is not None else DEFAULT_TRANSCRIBE_PROMPT,
    )
    say(f"      检测语言：{info.language}（{info.language_probability:.1%}）")
    captions: list[core.Caption] = []
    for segment in segments:
        text = " ".join(str(segment.text).split())
        if text:
            captions.append(core.Caption(float(segment.start), float(segment.end), text))
    if not captions:
        raise RuntimeError("Whisper 没有识别出语音内容")
    merged = merge_captions(captions)
    say(f"      识别完成：{len(captions)} 个片段 → {len(merged)} 条阅读字幕")
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


@dataclass(frozen=True)
class AudioPipelineResult:
    title: str
    source_url: str
    rows: list[core.BilingualRow]
    methods: list[str]


def generate_rows_from_audio(
    url: str,
    browser: str = "none",
    model_name: str = "small.en",
    log: Callable[[str], None] | None = None,
) -> AudioPipelineResult:
    """复用本地转写，或下载临时音频识别并保存结果；网页模式与 CLI 共用。"""
    say = log or (lambda message: print(message, flush=True))
    from translation_store import default_store
    store = default_store()
    normalized_url = core.normalize_bilibili_url(url)
    namespace = 'audio-transcript-v1'
    key = json.dumps([normalized_url, model_name, DEFAULT_TRANSCRIBE_PROMPT], ensure_ascii=False)
    try:
        cached = store.get(namespace, key)
    except (OSError, sqlite3.Error) as exc:
        say(f'      无法读取转写缓存，将重新识别：{exc}')
        cached = None
    if cached:
        try:
            result = AudioPipelineResult(
                title=cached['title'], source_url=cached['source_url'],
                rows=[core.BilingualRow(**row) for row in cached['rows']], methods=cached['methods'],
            )
            if result.rows:
                say(f'[3/5] 复用本地转写：{len(result.rows)} 条，无需重新下载或识别')
                return result
        except (KeyError, TypeError, ValueError):
            say('      转写缓存格式无效，将重新识别')
    say("[2/5] 下载临时音频（最终不会保留）")
    with tempfile.TemporaryDirectory(prefix="bili-subtitle-") as temp:
        audio_path, info = download_audio(url, Path(temp), browser)
        size_mb = audio_path.stat().st_size / 1024 / 1024
        say(f"      音频：{audio_path.suffix} · {size_mb:.1f} MB")
        captions = transcribe_audio(audio_path, model_name, log=say)
    result = AudioPipelineResult(
        title=str(info.get("title") or "B站视频"),
        source_url=str(info.get("webpage_url") or url),
        rows=core.align_captions(captions, []),
        methods=[f"English：faster-whisper {model_name} 机器识别"],
    )
    try:
        store.put(namespace, key, asdict(result))
    except (OSError, sqlite3.Error) as exc:
        say(f'      转写缓存未能保存，本次内容仍可导出，重启后不能复用：{exc}')
    return result


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
        audio = generate_rows_from_audio(normalized_url, browser, model_name)
        title, source_url, rows = audio.title, audio.source_url, audio.rows
        methods.extend(audio.methods)

    if translate:
        try:
            rows, translation_methods = fill_missing_languages(rows)
            methods.extend(translation_methods)
        except Exception as exc:
            if isinstance(exc, PartialTranslationError):
                rows = exc.rows or rows
                methods.extend(exc.methods)
            # 转写（耗时大头）已完成：翻译失败只降级为缺中文，仍写出结果文件。
            print("警告：机器翻译失败，已保留现有内容继续导出", flush=True)
            print(f"  原因：{exc}", flush=True)
            print(f"  处理：{translation_failure_hint(exc)}", flush=True)
            if any(row.english and not row.chinese for row in rows):
                methods.append("中文：机器翻译失败（内容已保留）")
            if any(row.chinese and not row.english for row in rows):
                methods.append("English：机器翻译失败（内容已保留）")
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
