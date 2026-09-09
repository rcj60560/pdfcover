"""Recovery contracts: real SQLite/files, fake external translation transport only."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import time

import pytest


@pytest.fixture(autouse=True)
def isolated_translation_cache(tmp_path, monkeypatch):
    monkeypatch.setenv('BILIBILI_CACHE_DIR', str(tmp_path / 'bilibili-cache'))

sys.path.insert(0, str(Path(__file__).parents[1] / 'tools' / 'bilibili-subtitles'))


def test_cache_survives_reopen_and_separates_namespaces(tmp_path):
    from translation_store import TranslationStore
    path = tmp_path / 'cache.db'
    TranslationStore(path).put('google:en:zh', 'hello', {'text': '你好'})
    reopened = TranslationStore(path)
    assert reopened.get('google:en:zh', 'hello') == {'text': '你好'}
    assert reopened.get('google:zh:en', 'hello') is None
    assert reopened.get('mymemory:en:zh', 'hello') is None
    reopened.put('transcript:small.en', 'video?p=2', {'rows': [[0, 2, 'hello']]})
    assert TranslationStore(path).get('transcript:small.en', 'video?p=2')['rows'] == [[0, 2, 'hello']]


def test_two_store_instances_share_request_spacing(tmp_path):
    from translation_store import TranslationStore
    path = tmp_path / 'cache.db'
    stores = [TranslationStore(path), TranslationStore(path)]
    def reserve(store):
        store.wait_turn('google', 0.12)
        return time.monotonic()
    with ThreadPoolExecutor(2) as pool:
        stamps = sorted(pool.map(reserve, stores))
    assert stamps[1] - stamps[0] >= 0.10


def test_provider_cooldown_shared_and_other_provider_available(tmp_path):
    from translation_store import TranslationStore, ProviderCoolingDown
    path = tmp_path / 'cache.db'
    first, second = TranslationStore(path), TranslationStore(path)
    first.cooldown('mymemory', 60, 'quota exhausted')
    with pytest.raises(ProviderCoolingDown, match='quota exhausted'):
        second.wait_turn('mymemory', 0)
    second.wait_turn('google', 0)


def test_duplicate_and_completed_chunks_not_requested_again(tmp_path, monkeypatch):
    import direct_generate as d
    from translation_store import TranslationStore
    store = TranslationStore(tmp_path / 'cache.db')
    monkeypatch.setattr(d.time, 'sleep', lambda seconds: None)
    requested = []
    failing = True
    def backend(text):
        requested.append(text)
        if text == 'B' and failing:
            raise RuntimeError('unavailable')
        return '译' + text
    with pytest.raises(RuntimeError):
        d.translate_texts(['A', 'A', 'B'], 'en', 'zh-CN', backends=[('fake', backend, 480)],
                          retries=1, cache=store, request_interval=0)
    failing = False
    values, label = d.translate_texts(['A', 'A', 'B'], 'en', 'zh-CN', backends=[('fake', backend, 480)],
                                     cache=store, request_interval=0)
    assert values == ['译A', '译A', '译B']
    assert label == 'fake'
    assert requested == ['A', 'B', 'B']


def test_partial_language_results_available_after_failure(monkeypatch):
    import direct_generate as d
    from subtitle_core import BilingualRow
    monkeypatch.setattr(d.time, 'sleep', lambda seconds: None)
    def backend(text):
        if text == 'B':
            raise RuntimeError('unavailable')
        return '译A'
    with pytest.raises(RuntimeError) as caught:
        d.fill_missing_languages([BilingualRow(0, 1, 'A'), BilingualRow(1, 2, 'B')],
                                 backends=[('fake', backend, 480)])
    assert [row.chinese for row in caught.value.rows] == ['译A', '']
    assert caught.value.methods == ['中文：fake 机器翻译']


def test_empty_translation_is_not_success():
    import direct_generate as d
    values, label = d.translate_texts(['hello'], 'en', 'zh-CN', retries=1, request_interval=0,
                                     backends=[('empty', lambda text: '  ', 480),
                                               ('backup', lambda text: '你好', 480)])
    assert values == ['你好'] and label == 'backup'


def test_mymemory_split_measures_utf8_bytes_and_keeps_text():
    from translation_backends import split_utf8
    text = '中文测试。' * 80
    chunks = split_utf8(text, 480)
    assert len(chunks) > 1
    assert ''.join(chunks) == text
    assert all(len(chunk.encode('utf-8')) <= 480 for chunk in chunks)


class Response:
    def __init__(self, status=200, data=None, text='', headers=None):
        self.status_code = status
        self.data = data
        self.text = text
        self.headers = headers or {}
    def json(self):
        return self.data
    def close(self):
        pass


def test_mymemory_passes_email_timeout_https_and_reads_translation(tmp_path, monkeypatch):
    from translation_backends import HttpTranslator
    from translation_store import TranslationStore
    monkeypatch.setenv('MYMEMORY_EMAIL', 'test@example.com')
    calls = []
    def get(url, **kwargs):
        calls.append((url, kwargs))
        return Response(data={'responseStatus': 200, 'responseData': {'translatedText': '你好'}, 'matches': []})
    translator = HttpTranslator('MyMemory', 'en', 'zh-CN', TranslationStore(tmp_path / 'db'), get=get)
    assert translator.translate('Hello') == '你好'
    url, kwargs = calls[0]
    assert url == 'https://api.mymemory.translated.net/get'
    assert kwargs['params'] == {'q': 'Hello', 'langpair': 'en|zh-CN', 'de': 'test@example.com'}
    assert kwargs['timeout'] == (5, 20)


@pytest.mark.parametrize('response', [
    Response(data={'responseStatus': 403, 'responseDetails': 'quota exceeded',
                   'responseData': {'translatedText': 'not a translation'}}),
    Response(data={'responseStatus': 200, 'responseData': {'translatedText': 'MYMEMORY WARNING: daily quota'}}),
    Response(data={'responseStatus': 200, 'responseData': {'translatedText': ' \n MYMEMORY WARNING: daily quota'}}),
])
def test_quota_response_never_becomes_translation_and_cools_backend(tmp_path, response):
    from translation_backends import HttpTranslator
    from translation_store import TranslationStore, ProviderCoolingDown
    calls = []
    def get(*args, **kwargs):
        calls.append(1)
        return response
    path = tmp_path / 'db'
    with pytest.raises(RuntimeError, match='额度'):
        HttpTranslator('MyMemory', 'en', 'zh-CN', TranslationStore(path), get=get).translate('one')
    with pytest.raises(ProviderCoolingDown):
        HttpTranslator('MyMemory', 'en', 'zh-CN', TranslationStore(path), get=get).translate('two')
    assert len(calls) == 1


def test_429_retry_after_shared_with_new_translator(tmp_path):
    from translation_backends import HttpTranslator
    from translation_store import TranslationStore, ProviderCoolingDown
    calls = []
    def get(*args, **kwargs):
        calls.append(1)
        return Response(429, headers={'Retry-After': '120'})
    path = tmp_path / 'db'
    with pytest.raises(RuntimeError, match='429'):
        HttpTranslator('Google Translate', 'en', 'zh-CN', TranslationStore(path), get=get).translate('one')
    with pytest.raises(ProviderCoolingDown, match='429'):
        HttpTranslator('Google Translate', 'en', 'zh-CN', TranslationStore(path), get=get).translate('two')
    assert calls == [1]


def test_google_uses_actual_html_endpoint(tmp_path):
    from translation_backends import HttpTranslator
    from translation_store import TranslationStore
    def get(url, **kwargs):
        assert url == 'https://translate.google.com/m'
        assert kwargs['params'] == {'q': 'hello', 'sl': 'en', 'tl': 'zh-CN'}
        assert kwargs['timeout'] == (5, 20)
        return Response(text='<div class="result-container">你好 &amp; 世界</div>')
    assert HttpTranslator('Google Translate', 'en', 'zh-CN', TranslationStore(tmp_path / 'db'), get=get).translate('hello') == '你好 & 世界'


def test_transcript_survives_pipeline_restart_and_model_key(tmp_path, monkeypatch):
    import direct_generate as d
    from subtitle_core import Caption
    downloads = []
    audio = tmp_path / 'fake.m4a'
    audio.write_bytes(b'audio')
    def download(url, temp, browser):
        downloads.append(url)
        return audio, {'title': 'Cached lesson', 'webpage_url': url}
    monkeypatch.setattr(d, 'download_audio', download)
    monkeypatch.setattr(d, 'transcribe_audio', lambda *a, **kw: [Caption(1, 3, 'Hello')])
    url = 'https://www.bilibili.com/video/BV1pgtn6NENb?p=2'
    first = d.generate_rows_from_audio(url)
    second = d.generate_rows_from_audio(url)
    assert first == second
    assert downloads == [url]
    d.generate_rows_from_audio(url, model_name='base.en')
    assert len(downloads) == 2
    d.generate_rows_from_audio(url.replace('p=2', 'p=3'))
    assert len(downloads) == 3


def test_web_partial_translations_export_and_retry_status(monkeypatch):
    from test_bilibili_subtitles import _load_web, _no_track_video
    import direct_generate as d
    from subtitle_core import BilingualRow
    web = _load_web()
    rows = [BilingualRow(0, 1, 'A'), BilingualRow(1, 2, 'B')]
    translated = [BilingualRow(0, 1, 'A', '译A'), rows[1]]
    job = web.Job(video=_no_track_video())
    key = web.jobs.put(job)
    monkeypatch.setattr(web, 'TRANSCRIBE_PIPELINE', lambda *a, **kw: d.AudioPipelineResult('t', 'url', rows, []))
    def partial(*args, **kwargs):
        raise d.PartialTranslationError('backend failed', rows=translated, methods=['中文：fake 机器翻译'])
    monkeypatch.setattr(web, 'TRANSLATE_ROWS', partial)
    web._run_transcribe(job, 'url', 'none', 'small.en')
    response = web.app.test_client().get(f'/api/jobs/{key}/transcribe/status').get_json()
    assert response['rows'][0]['chinese'] == '译A'
    assert response['translation_missing'] is True
    assert 'fake' in job.chinese_label
    srt = web.app.test_client().get(f'/api/jobs/{key}/download/srt').get_data(as_text=True)
    assert '译A' in srt and 'B' in srt


def test_cli_exports_partial_translation(monkeypatch, tmp_path):
    import direct_generate as d
    from subtitle_core import BilingualRow
    rows = [BilingualRow(0, 1, 'A'), BilingualRow(1, 2, 'B')]
    monkeypatch.setattr(d, 'rows_from_native_tracks', lambda *a: ('title', 'url', rows, 'English', '无'))
    def partial(*args, **kwargs):
        raise d.PartialTranslationError('failed', rows=[BilingualRow(0, 1, 'A', '译A'), rows[1]],
                                        methods=['中文：fake 机器翻译'])
    monkeypatch.setattr(d, 'fill_missing_languages', partial)
    path, _ = d.generate('BV1pgtn6NENb', tmp_path)
    content = path.read_text(encoding='utf-8')
    assert '译A' in content and 'fake' in content and 'B' in content


def test_default_chain_uses_cached_google_without_network(monkeypatch):
    import direct_generate as d
    from translation_store import default_store
    import requests
    d.translate_texts(['Hello'], 'en', 'zh-CN', backends=[('Google Translate', lambda text: '你好', 4500)],
                      cache=default_store())
    calls = []
    def unavailable(*args, **kwargs):
        calls.append(1)
        raise RuntimeError('network unavailable')
    monkeypatch.setattr(requests, 'head', unavailable)
    monkeypatch.setattr(requests, 'get', unavailable)
    monkeypatch.setattr(d, '_translate_with_retries', lambda fn, text, *a, **kw: fn(text))
    assert d.translate_texts(['Hello'], 'en', 'zh-CN') == (['你好'], 'Google Translate')
    assert calls == []


def test_default_chain_prefers_existing_fallback_cache(monkeypatch):
    import direct_generate as d
    from translation_store import default_store
    import requests
    d.translate_texts(['Hello'], 'en', 'zh-CN', backends=[('MyMemory', lambda text: '你好', 480)],
                      cache=default_store())
    calls = []
    def get(*args, **kwargs):
        calls.append(1)
        return Response(text='<div class="result-container">新译文</div>')
    monkeypatch.setattr(requests, 'head', lambda *a, **kw: Response())
    monkeypatch.setattr(requests, 'get', get)
    assert d.translate_texts(['Hello'], 'en', 'zh-CN') == (['你好'], 'MyMemory')
    assert calls == []


def test_retranslate_keeps_new_partial_success_and_provenance(monkeypatch):
    from test_bilibili_subtitles import _load_web, _no_track_video
    import direct_generate as d
    from subtitle_core import BilingualRow
    web = _load_web()
    original = [BilingualRow(0, 1, 'A', '译A'), BilingualRow(1, 2, 'B'), BilingualRow(2, 3, 'C')]
    partial_rows = [original[0], BilingualRow(1, 2, 'B', '译B'), original[2]]
    job = web.Job(video=_no_track_video(), rows=original, chinese_label='Google Translate 机器翻译')
    def partial(*args, **kwargs):
        raise d.PartialTranslationError('quota', rows=partial_rows, methods=['中文：MyMemory 机器翻译'])
    monkeypatch.setattr(web, 'TRANSLATE_ROWS', partial)
    web._run_retranslate(job)
    assert [row.chinese for row in job.rows] == ['译A', '译B', '']
    assert 'Google Translate' in job.chinese_label and 'MyMemory' in job.chinese_label
    assert '翻译失败' in job.chinese_label


def test_cached_chunks_survive_failure_in_same_long_row(tmp_path):
    import direct_generate as d
    from translation_store import TranslationStore
    cache = TranslationStore(tmp_path / 'db')
    calls = []
    failing = True
    def get(text):
        calls.append(text)
        if text == 'BBBB' and failing:
            raise RuntimeError('offline')
        return '译' + text
    with pytest.raises(RuntimeError):
        d.translate_texts(['AAAA BBBB'], 'en', 'zh-CN', backends=[('small', get, 4)],
                          retries=1, request_interval=0, cache=cache)
    failing = False
    values, _ = d.translate_texts(['AAAA BBBB'], 'en', 'zh-CN', backends=[('small', get, 4)],
                                  request_interval=0, cache=TranslationStore(tmp_path / 'db'))
    assert values == ['译AAAA 译BBBB']
    assert calls == ['AAAA', 'BBBB', 'BBBB']


def test_quota_activated_while_waiting_for_request_slot_is_respected(tmp_path, monkeypatch):
    from translation_backends import HttpTranslator
    from translation_store import TranslationStore, ProviderCoolingDown
    store = TranslationStore(tmp_path / 'db')
    calls = []
    client = HttpTranslator('MyMemory', 'en', 'zh-CN', store,
                            get=lambda *a, **kw: calls.append(1) or Response(data={
                                'responseStatus': 200, 'responseData': {'translatedText': '你好'}}))
    original_wait = store.wait_turn
    def wait(provider, interval):
        original_wait(provider, interval)
        if provider == 'MyMemory':
            TranslationStore(store.path).cooldown(client.quota_key, 60, 'quota exhausted')
    monkeypatch.setattr(store, 'wait_turn', wait)
    with pytest.raises(ProviderCoolingDown):
        client.translate('hello')
    assert calls == []


def test_health_shows_email_configured_without_exposing_address(monkeypatch):
    from test_bilibili_subtitles import _load_web
    web = _load_web()
    monkeypatch.setenv('MYMEMORY_EMAIL', 'private@example.com')
    response = web.app.test_client().get('/api/health')
    assert response.get_json()['translation_email_configured'] is True
    assert 'private@example.com' not in response.get_data(as_text=True)
    monkeypatch.delenv('MYMEMORY_EMAIL')
    assert web.app.test_client().get('/api/health').get_json()['translation_email_configured'] is False


def test_transcript_cache_write_failure_preserves_recognized_content(tmp_path, monkeypatch):
    import direct_generate as d
    from subtitle_core import Caption
    from translation_store import TranslationStore
    audio = tmp_path / 'fake.m4a'
    audio.write_bytes(b'audio')
    monkeypatch.setattr(d, 'download_audio', lambda url, *a: (audio, {'title': 't', 'webpage_url': url}))
    monkeypatch.setattr(d, 'transcribe_audio', lambda *a, **kw: [Caption(0, 2, 'Hello')])
    def unwritable(*args):
        raise OSError('disk full')
    monkeypatch.setattr(TranslationStore, 'put', unwritable)
    logs = []
    result = d.generate_rows_from_audio('BV1pgtn6NENb', log=logs.append)
    assert result.rows[0].english == 'Hello'
    assert any('disk full' in line for line in logs)


def test_whisper_dependencies_do_not_require_retired_translator(monkeypatch):
    import builtins
    from test_bilibili_subtitles import _load_web
    web = _load_web()
    original = builtins.__import__
    def import_module(name, *args, **kwargs):
        if name == 'deep_translator':
            raise ImportError('retired dependency')
        if name == 'faster_whisper':
            return object()
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', import_module)
    assert web._whisper_deps_missing() is None


@pytest.mark.parametrize('operation', ['get', 'put'])
def test_translation_cache_failure_does_not_block_translation(monkeypatch, operation):
    import direct_generate as d
    class BrokenCache:
        def get(self, *args):
            if operation == 'get':
                raise OSError('cache unavailable')
            return None
        def put(self, *args):
            if operation == 'put':
                raise OSError('cache unavailable')
    logs = []
    result = d.translate_texts(['Hello'], 'en', 'zh-CN',
                               backends=[('fake', lambda text: '你好', 480)],
                               cache=BrokenCache(), log=logs.append)
    assert result == (['你好'], 'fake')
    assert any('缓存' in line and 'cache unavailable' in line for line in logs)


def test_provider_state_store_failure_uses_local_pacing_and_still_translates():
    from translation_backends import HttpTranslator
    class BrokenStore:
        def wait_turn(self, *args):
            raise OSError('state unavailable')
        def cooldown(self, *args):
            raise OSError('state unavailable')
    calls = []
    def get(*args, **kwargs):
        calls.append(1)
        return Response(data={'responseStatus': 200, 'responseData': {'translatedText': '你好'}})
    client = HttpTranslator('MyMemory', 'en', 'zh-CN', BrokenStore(), get=get)
    assert client.translate('Hello') == '你好'
    assert calls == [1]


def test_provider_state_store_failure_does_not_hide_429():
    from translation_backends import HttpTranslator
    class BrokenStore:
        def wait_turn(self, *args):
            raise OSError('state unavailable')
        def cooldown(self, *args):
            raise OSError('state unavailable')
    client = HttpTranslator('Test Google', 'en', 'zh-CN', BrokenStore(),
                            get=lambda *a, **kw: Response(429, headers={'Retry-After': '3'}))
    with pytest.raises(RuntimeError, match='429'):
        client.translate('Hello')


def test_local_cooldown_is_kept_if_shared_store_recovers(tmp_path):
    from translation_backends import HttpTranslator
    from translation_store import TranslationStore
    class FailingCooldownStore(TranslationStore):
        def cooldown(self, *args):
            raise OSError('state unavailable')
    path = tmp_path / 'db'
    first = HttpTranslator('Recovered Google', 'en', 'zh-CN', FailingCooldownStore(path),
                           get=lambda *a, **kw: Response(429, headers={'Retry-After': '3'}))
    with pytest.raises(RuntimeError, match='429'):
        first.translate('one')
    calls = []
    second = HttpTranslator('Recovered Google', 'en', 'zh-CN', TranslationStore(path),
                            get=lambda *a, **kw: calls.append(1) or Response(text='ok'))
    with pytest.raises(RuntimeError, match='暂停'):
        second.translate('two')
    assert calls == []
