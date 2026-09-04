"""通过 yt-dlp 读取 B 站视频元数据与字幕；不下载视频/音频。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.request import Request, urlopen

from subtitle_core import (
    SubtitleTrack,
    detect_language_family,
    language_label,
    normalize_bilibili_url,
    parse_subtitle_payload,
)


class ExtractionError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExtractedVideo:
    title: str
    source_url: str
    uploader: str
    duration: float
    tracks: tuple[SubtitleTrack, ...]
    warnings: tuple[str, ...] = ()


class _CaptureLogger:
    def __init__(self) -> None:
        self.warnings: list[str] = []

    def debug(self, message: str) -> None:
        pass

    def info(self, message: str) -> None:
        pass

    def warning(self, message: str) -> None:
        if message:
            self.warnings.append(str(message))

    def error(self, message: str) -> None:
        if message:
            self.warnings.append(str(message))


def _first_video(info: dict[str, Any]) -> dict[str, Any]:
    entries = info.get("entries")
    if entries:
        return next((entry for entry in entries if isinstance(entry, dict)), info)
    return info


def _download_subtitle(url: str, headers: dict[str, str] | None = None) -> str:
    if url.startswith("//"):
        url = "https:" + url
    request_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.bilibili.com/",
        **(headers or {}),
    }
    request = Request(url, headers=request_headers)
    with urlopen(request, timeout=20) as response:  # noqa: S310 - URL 来自 yt-dlp 的字幕元数据
        raw = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
    return raw.decode(charset, errors="replace")


def _entry_payload(entry: dict[str, Any], headers: dict[str, str]) -> tuple[str, str]:
    data = entry.get("data")
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace"), str(entry.get("ext") or "")
    if isinstance(data, str):
        return data, str(entry.get("ext") or "")
    url = entry.get("url")
    if isinstance(url, str) and url:
        return _download_subtitle(url, headers), str(entry.get("ext") or "")
    return "", str(entry.get("ext") or "")


def collect_tracks(info: dict[str, Any]) -> list[SubtitleTrack]:
    """把 yt-dlp info_dict 里的 manual/automatic 字幕统一成可消费轨道。"""
    headers = {str(k): str(v) for k, v in (info.get("http_headers") or {}).items()}
    tracks: list[SubtitleTrack] = []
    fingerprints: set[tuple] = set()
    for field, kind in (("subtitles", "manual"), ("automatic_captions", "automatic")):
        groups = info.get(field) or {}
        if not isinstance(groups, dict):
            continue
        for lang, entries in groups.items():
            if str(lang).lower() in {"danmaku", "live_chat", "comments"}:
                continue
            if not isinstance(entries, list):
                continue
            for entry_index, entry in enumerate(entries):
                if not isinstance(entry, dict):
                    continue
                try:
                    payload, ext = _entry_payload(entry, headers)
                except OSError:
                    continue
                captions = parse_subtitle_payload(payload, ext)
                if not captions:
                    continue
                fingerprint = tuple((c.start, c.end, c.text) for c in captions)
                if fingerprint in fingerprints:
                    continue
                fingerprints.add(fingerprint)
                family = detect_language_family(str(lang), captions)
                raw_name = str(entry.get("name") or "").strip()
                label = raw_name or language_label(str(lang), family, kind)
                tracks.append(SubtitleTrack(
                    id=f"{kind}:{lang}:{entry_index}",
                    lang=str(lang),
                    label=label,
                    kind=kind,
                    family=family,
                    captions=tuple(captions),
                ))
    family_order = {"bilingual": 0, "english": 1, "chinese": 2, "unknown": 3}
    return sorted(tracks, key=lambda track: (family_order.get(track.family, 9), track.kind, track.lang))


def _friendly_error(exc: Exception, browser: str) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    lower = message.lower()
    if "could not copy" in lower or "database is locked" in lower:
        return f"无法读取 {browser} 登录状态：请先完全关闭浏览器后重试"
    if "decrypt" in lower or "dpapi" in lower:
        return f"无法解密 {browser} Cookie；可先选择“不读取登录状态”重试"
    if "unsupported url" in lower:
        return "yt-dlp 无法识别这个链接，请确认它是有效的 B 站视频页"
    if "429" in lower or "rate limit" in lower or "352" in lower or "412" in lower or "precondition failed" in lower:
        return "B站请求过于频繁或被风控拦截，请稍后再试；也可以选择浏览器登录状态重试"
    return f"读取 B 站视频失败：{message}"


def extract_video(url: str, cookie_browser: str = "none") -> ExtractedVideo:
    normalized_url = normalize_bilibili_url(url)
    browser = (cookie_browser or "none").lower()
    if browser not in {"none", "chrome", "edge", "firefox"}:
        raise ExtractionError("不支持的浏览器登录状态")
    try:
        import yt_dlp
    except ImportError as exc:
        raise ExtractionError("缺少 yt-dlp，请先运行：pip install -r requirements.txt") from exc

    logger = _CaptureLogger()
    options: dict[str, Any] = {
        "skip_download": True,
        "quiet": True,
        "no_warnings": False,
        "logger": logger,
        "noplaylist": True,
        "playlistend": 1,
        "ignore_no_formats_error": True,
        "socket_timeout": 20,
        "retries": 2,
        "extractor_retries": 2,
        "cachedir": False,
    }
    if browser != "none":
        # yt-dlp 官方接口格式：(browser, profile, keyring, container)
        options["cookiesfrombrowser"] = (browser, None, None, None)

    try:
        with yt_dlp.YoutubeDL(options) as downloader:
            raw_info = downloader.extract_info(normalized_url, download=False)
    except Exception as exc:
        raise ExtractionError(_friendly_error(exc, browser)) from exc
    if not isinstance(raw_info, dict):
        raise ExtractionError("没有读到有效的视频信息")

    info = _first_video(raw_info)
    tracks = collect_tracks(info)
    if not tracks:
        needs_login = any("login" in warning.lower() or "登录" in warning for warning in logger.warnings)
        if needs_login and browser == "none":
            raise ExtractionError("B站要求登录后才能读取该视频字幕，请选择 Chrome / Edge / Firefox 登录状态后重试")
        # 无字幕轨不再是死路：返回空轨道视频，网页模式据此提供语音识别入口。
        logger.warnings.append(
            "视频没有可提取的字幕轨；画面烧录的文字不属于字幕轨，可用语音识别（Whisper）从音频生成。"
        )

    try:
        duration = float(info.get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0.0
    return ExtractedVideo(
        title=str(info.get("title") or "B站视频字幕"),
        source_url=str(info.get("webpage_url") or normalized_url),
        uploader=str(info.get("uploader") or ""),
        duration=duration,
        tracks=tuple(tracks),
        warnings=tuple(dict.fromkeys(logger.warnings)),
    )
