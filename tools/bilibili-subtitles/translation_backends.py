"""Explicit, bounded HTTP adapters for the two existing free providers."""
from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import math
import os
import sqlite3
from threading import Lock
import time

from translation_store import ProviderCoolingDown, TranslationStore

GOOGLE_URL = 'https://translate.google.com/m'
MYMEMORY_URL = 'https://api.mymemory.translated.net/get'
REQUEST_TIMEOUT = (5, 20)
GOOGLE_HEADERS = {'User-Agent': 'Mozilla/5.0'}
_LOCAL_LOCK = Lock()
_LOCAL_NEXT: dict[str, float] = {}
_LOCAL_COOLDOWN: dict[str, tuple[float, str]] = {}


def _local_wait_turn(provider: str, interval: float) -> None:
    """Process-local fallback when the shared SQLite scheduler is unavailable."""
    while True:
        with _LOCAL_LOCK:
            now = time.monotonic()
            cool_until, reason = _LOCAL_COOLDOWN.get(provider, (0, ''))
            if cool_until > now:
                raise ProviderCoolingDown(
                    f'{provider} 暂停请求：{reason}；约 {cool_until - now:.0f}s 后可重试')
            wait = _LOCAL_NEXT.get(provider, 0) - now
            if wait <= 0:
                _LOCAL_NEXT[provider] = now + max(0, interval)
                return
        time.sleep(min(wait, 1.0))


def _local_cooldown(provider: str, seconds: float, reason: str) -> None:
    with _LOCAL_LOCK:
        until = time.monotonic() + max(0, seconds)
        previous = _LOCAL_COOLDOWN.get(provider, (0, ''))
        _LOCAL_COOLDOWN[provider] = (max(previous[0], until), reason)


class TranslationServiceError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


def split_utf8(text: str, limit: int = 480) -> list[str]:
    """Preserve all input, favor sentence/word boundaries, never split a codepoint."""
    if limit < 4:
        raise ValueError('UTF-8 分片上限至少为 4 字节')
    result = []
    while text:
        size = 0
        end = 0
        boundary = 0
        for index, char in enumerate(text):
            size += len(char.encode('utf-8'))
            if size > limit:
                break
            end = index + 1
            if char.isspace() or char in '.!?。！？；;':
                boundary = end
        if end == len(text):
            result.append(text)
            break
        end = boundary or end
        result.append(text[:end])
        text = text[end:]
    return result


def retry_after_seconds(value: str | None) -> float:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        try:
            date = parsedate_to_datetime(value)
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
            seconds = (date - datetime.now(timezone.utc)).total_seconds()
        except (TypeError, ValueError, OverflowError):
            seconds = 60
    return max(1, seconds) if math.isfinite(seconds) else 60


class HttpTranslator:
    def __init__(self, label: str, source: str, target: str, store: TranslationStore, *, get=None):
        self.label, self.source, self.target, self.store = label, source, target, store
        self.email = os.environ.get('MYMEMORY_EMAIL', '').strip()
        self.quota_key = 'MyMemory-account:' + hashlib.sha256(self.email.encode()).hexdigest()[:16]
        if get is None:
            import requests
            get = requests.get
        self.get = get

    def _cooldown(self, key, seconds, message):
        try:
            self.store.cooldown(key, seconds, message)
        except (OSError, sqlite3.Error):
            _local_cooldown(key, seconds, message)
        raise TranslationServiceError(message)

    def _wait_turn(self, key: str, interval: float) -> None:
        # Always honor a cooldown recorded while the shared store was down.
        _local_wait_turn(key, 0)
        try:
            self.store.wait_turn(key, interval)
        except (OSError, sqlite3.Error):
            _local_wait_turn(key, interval)

    def translate(self, text: str) -> str:
        is_mymemory = self.label == 'MyMemory'
        if is_mymemory:
            if len(text.encode('utf-8')) > 500:
                raise TranslationServiceError('MyMemory 单次文本超过 500 UTF-8 字节')
            self._wait_turn(self.quota_key, 0)
        self._wait_turn(self.label, 0.5 if is_mymemory else 1.0)
        if is_mymemory:
            # Quota may have been exhausted by another process while pacing waited.
            self._wait_turn(self.quota_key, 0)
        params = ({'q': text, 'langpair': f'{self.source}|{self.target}'} if is_mymemory
                  else {'q': text, 'sl': self.source, 'tl': self.target})
        if is_mymemory and self.email:
            params['de'] = self.email
        try:
            response = self.get(MYMEMORY_URL if is_mymemory else GOOGLE_URL,
                                params=params, timeout=REQUEST_TIMEOUT,
                                **({} if is_mymemory else {'headers': GOOGLE_HEADERS}))
        except Exception as exc:
            # Requests exceptions can embed the URL, including text/email: don't log it.
            raise TranslationServiceError(f'{self.label} 网络请求失败（{type(exc).__name__}）', retryable=True) from exc
        try:
            if response.status_code == 429:
                self._cooldown(self.label, retry_after_seconds(response.headers.get('Retry-After')),
                               f'{self.label} HTTP 429 限流，已暂停该后端')
            if response.status_code >= 500:
                raise TranslationServiceError(f'{self.label} HTTP {response.status_code}', retryable=True)
            if response.status_code != 200:
                raise TranslationServiceError(f'{self.label} HTTP {response.status_code}')
            if is_mymemory:
                try:
                    data = response.json()
                    status = int(data.get('responseStatus', 200))
                    value = data.get('responseData', {}).get('translatedText', '')
                    details = str(data.get('responseDetails', ''))
                except (AttributeError, TypeError, ValueError) as exc:
                    raise TranslationServiceError('MyMemory 返回无效 JSON 响应') from exc
                quota = (str(value).strip().upper().startswith('MYMEMORY WARNING') or
                         any(word in details.lower() for word in ('quota', 'daily limit', 'used all', 'next available')))
                if quota:
                    self._cooldown(self.quota_key, 3600, 'MyMemory 额度不足，已暂停一小时；恢复后重试翻译')
                if status == 429:
                    self._cooldown(self.label, retry_after_seconds(response.headers.get('Retry-After')),
                                   'MyMemory HTTP 429 限流，已暂停该后端')
                if status != 200:
                    raise TranslationServiceError(f'MyMemory 响应错误 {status}', retryable=status >= 500)
            else:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(response.text, 'html.parser')
                element = soup.find('div', class_='t0') or soup.find('div', class_='result-container')
                value = element.get_text(' ', strip=True) if element else ''
            if not isinstance(value, str) or not value.strip():
                raise TranslationServiceError(f'{self.label} 没有返回有效译文')
            return value.strip()
        finally:
            response.close()
