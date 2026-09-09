"""Durable local results and provider pacing shared by web/CLI processes."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time


class ProviderCoolingDown(RuntimeError):
    retryable = False


class TranslationStore:
    def __init__(self, path: Path):
        self.path = Path(path)

    @contextmanager
    def connection(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=15)
        try:
            db.execute('CREATE TABLE IF NOT EXISTS cache (namespace TEXT, key TEXT, value TEXT, '
                       'PRIMARY KEY(namespace, key))')
            db.execute('CREATE TABLE IF NOT EXISTS provider (name TEXT PRIMARY KEY, next_at REAL, '
                       'cool_until REAL, reason TEXT)')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def get(self, namespace: str, key: str):
        with self.connection() as db:
            row = db.execute('SELECT value FROM cache WHERE namespace=? AND key=?',
                             (namespace, self._key(key))).fetchone()
        if row is None:
            return None
        try:
            return json.loads(row[0])
        except (ValueError, TypeError):
            return None

    def put(self, namespace: str, key: str, value) -> None:
        with self.connection() as db:
            db.execute('INSERT OR REPLACE INTO cache VALUES (?, ?, ?)',
                       (namespace, self._key(key), json.dumps(value, ensure_ascii=False)))

    @staticmethod
    def _key(value: str) -> str:
        return hashlib.sha256(value.encode('utf-8')).hexdigest()

    def wait_turn(self, provider: str, interval: float) -> None:
        """Reserve a start time atomically; sleeping never holds the SQLite lock."""
        while True:
            with self.connection() as db:
                db.execute('BEGIN IMMEDIATE')
                now = time.time()
                row = db.execute('SELECT next_at, cool_until, reason FROM provider WHERE name=?',
                                 (provider,)).fetchone()
                next_at, cool_until, reason = row or (0, 0, '')
                if cool_until > now:
                    raise ProviderCoolingDown(f'{provider} 暂停请求：{reason}；约 {cool_until - now:.0f}s 后可重试')
                wait = next_at - now
                if wait <= 0:
                    db.execute('INSERT OR REPLACE INTO provider VALUES (?, ?, 0, ?)',
                               (provider, now + max(0, interval), ''))
                    return
            time.sleep(min(wait, 1.0))

    def cooldown(self, provider: str, seconds: float, reason: str) -> None:
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT INTO provider VALUES (?, 0, ?, ?) ON CONFLICT(name) DO UPDATE SET '
                       'cool_until=MAX(cool_until, excluded.cool_until), reason=excluded.reason',
                       (provider, time.time() + max(0, seconds), reason))


def default_store() -> TranslationStore:
    directory = Path(os.environ.get('BILIBILI_CACHE_DIR') or
                     Path(__file__).resolve().parent / 'outputs' / '.cache')
    return TranslationStore(directory / 'translation.sqlite3')
