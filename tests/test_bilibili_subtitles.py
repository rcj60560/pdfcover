"""B站双语字幕工具纯逻辑测试（不触网、不要求安装 yt-dlp）。"""
from __future__ import annotations

import sys
import importlib.util
import threading
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest

BASE = Path(__file__).parents[1] / "tools" / "bilibili-subtitles"
sys.path.insert(0, str(BASE))

import subtitle_core as core  # noqa: E402
from extractor import ExtractionError, collect_tracks, extract_video  # noqa: E402
from xlsx_export import build_xlsx  # noqa: E402
from direct_generate import (  # noqa: E402
    DEFAULT_TRANSCRIBE_PROMPT,
    apply_translations,
    fill_missing_languages,
    join_parts,
    merge_captions,
    split_for_limit,
    split_methods,
    transcribe_audio,
    translate_texts,
)


def cue(start, end, text):
    return core.Caption(start, end, text)


def test_normalize_bilibili_url_accepts_video_short_and_bv():
    assert core.normalize_bilibili_url("BV1xx411c7mD").endswith("/BV1xx411c7mD")
    assert core.normalize_bilibili_url("https://www.bilibili.com/video/BV1xx411c7mD?p=2").endswith("?p=2")
    assert core.normalize_bilibili_url("b23.tv/abc123") == "https://b23.tv/abc123"
    with pytest.raises(ValueError):
        core.normalize_bilibili_url("https://example.com/video/BV1xx411c7mD")
    with pytest.raises(ValueError):
        core.normalize_bilibili_url("https://www.bilibili.com/read/cv123")


def test_parse_srt_and_vtt_cleans_markup():
    payload = """WEBVTT

1
00:00:01.250 --> 00:00:03.500 align:start
<b>Hello</b> world!

2
00:03.500 --> 00:05.000
你好，世界！
"""
    captions = core.parse_srt_or_vtt(payload)
    assert captions == [
        cue(1.25, 3.5, "Hello world!"),
        cue(3.5, 5.0, "你好，世界！"),
    ]


def test_parse_bilibili_json():
    payload = '{"body":[{"from":0.4,"to":1.8,"content":"Hi &amp; welcome"}]}'
    assert core.parse_subtitle_payload(payload, "json") == [cue(0.4, 1.8, "Hi & welcome")]


def test_detect_and_split_bilingual_track():
    captions = [cue(0, 2, "Hello everyone!\n大家好！"), cue(2, 4, "How are you? | 你好吗？")]
    assert core.detect_language_family("zh-CN", captions) == "bilingual"
    en, zh = core.split_bilingual_track(captions)
    assert [c.text for c in en] == ["Hello everyone!", "How are you?"]
    assert [c.text for c in zh] == ["大家好！", "你好吗？"]


def test_align_merges_repeated_translation_covering_two_english_cues():
    english = [cue(0, 1.8, "First sentence."), cue(1.8, 3.8, "Second sentence.")]
    chinese = [cue(0, 3.8, "第一句和第二句。")]
    rows = core.align_captions(english, chinese)
    assert len(rows) == 1
    assert rows[0].english == "First sentence. Second sentence."
    assert rows[0].chinese == "第一句和第二句。"
    assert (rows[0].start, rows[0].end) == (0, 3.8)


def test_align_keeps_unmatched_and_single_language():
    rows = core.align_captions([cue(10, 12, "Hello")], [cue(1, 2, "片头")])
    assert [(r.english, r.chinese) for r in rows] == [("", "片头"), ("Hello", "")]
    assert core.align_captions([], [cue(1, 2, "只有中文")])[0].chinese == "只有中文"


def test_whisper_captions_merge_for_reading_and_translation_apply():
    merged = merge_captions([
        cue(0, 2, "This is"), cue(2.2, 4, "one sentence."), cue(8, 10, "New part."),
    ])
    assert merged == [cue(0, 4, "This is one sentence."), cue(8, 10, "New part.")]
    rows = core.align_captions(merged, [])
    translated = apply_translations(rows, [0, 1], ["这是一个句子。", "新的部分。"], "chinese")
    assert [row.chinese for row in translated] == ["这是一个句子。", "新的部分。"]


def _install_fake_whisper(monkeypatch):
    """注入假 faster_whisper：transcribe_audio 不加载真模型即可验证调用契约。"""
    import types

    calls = {}

    class FakeWhisperModel:
        def __init__(self, model_name, **kwargs):
            calls["model"] = model_name

        def transcribe(self, audio_path, **kwargs):
            calls["kwargs"] = kwargs
            segment = types.SimpleNamespace(start=0.0, end=2.4, text=" Hello there ")
            info = types.SimpleNamespace(language="en", language_probability=0.98)
            return [segment], info

    fake = types.ModuleType("faster_whisper")
    fake.WhisperModel = FakeWhisperModel
    monkeypatch.setitem(sys.modules, "faster_whisper", fake)
    return calls


def test_transcribe_audio_sends_generic_prompt_and_logs_progress(monkeypatch, tmp_path):
    calls = _install_fake_whisper(monkeypatch)
    logs = []
    captions = transcribe_audio(tmp_path / "a.m4a", "small.en", log=logs.append)

    assert calls["model"] == "small.en"
    assert calls["kwargs"]["language"] == "en"
    assert calls["kwargs"]["initial_prompt"] == DEFAULT_TRANSCRIBE_PROMPT
    assert "Vocabulary" not in DEFAULT_TRANSCRIBE_PROMPT and "Unit" not in DEFAULT_TRANSCRIBE_PROMPT
    assert captions == [cue(0.0, 2.4, "Hello there")]
    assert any("识别完成" in line for line in logs)


def test_transcribe_audio_accepts_custom_prompt(monkeypatch, tmp_path):
    calls = _install_fake_whisper(monkeypatch)
    transcribe_audio(tmp_path / "a.m4a", "base.en", initial_prompt="A physics lecture.")
    assert calls["kwargs"]["initial_prompt"] == "A physics lecture."


def test_generate_rows_from_audio_downloads_transcribes_and_returns_rows(monkeypatch, tmp_path):
    import direct_generate

    logs = []
    fake_audio = tmp_path / "fake.m4a"
    fake_audio.write_bytes(b"audio-bytes")
    monkeypatch.setattr(direct_generate, "download_audio", lambda url, temp_dir, browser: (
        fake_audio,
        {"title": "English Video", "webpage_url": "https://www.bilibili.com/video/BV1pgtn6NENb"},
    ))
    monkeypatch.setattr(direct_generate, "transcribe_audio",
                        lambda audio_path, model_name, **kwargs: [cue(0, 2, "Hello world.")])

    result = direct_generate.generate_rows_from_audio(
        "https://www.bilibili.com/video/BV1pgtn6NENb", "none", "small.en", log=logs.append)

    assert result.title == "English Video"
    assert result.source_url.endswith("BV1pgtn6NENb")
    assert result.rows == [core.BilingualRow(0, 2, "Hello world.", "")]
    assert result.methods == ["English：faster-whisper small.en 机器识别"]
    assert any("下载" in line for line in logs)


def test_generate_cli_writes_outputs_via_audio_pipeline(monkeypatch, tmp_path):
    import direct_generate

    monkeypatch.setattr(direct_generate, "rows_from_native_tracks", lambda url, browser: None)
    fake_audio = tmp_path / "a.m4a"
    fake_audio.write_bytes(b"audio-bytes")
    monkeypatch.setattr(direct_generate, "download_audio", lambda url, temp_dir, browser: (
        fake_audio,
        {"title": "CLI 标题", "webpage_url": "https://www.bilibili.com/video/BV1pgtn6NENb"},
    ))
    monkeypatch.setattr(direct_generate, "transcribe_audio",
                        lambda audio_path, model_name, **kwargs: [cue(0, 2, "Hello there.")])
    monkeypatch.setattr(direct_generate, "fill_missing_languages", lambda rows, backends=None: (
        [core.BilingualRow(0, 2, "Hello there.", "你好。")], ["中文：Fake 机器翻译"],
    ))

    md_path, xlsx_path = direct_generate.generate("BV1pgtn6NENb", tmp_path)

    assert md_path.exists() and xlsx_path.exists()
    content = md_path.read_text(encoding="utf-8")
    assert "Hello there." in content and "你好。" in content
    assert "faster-whisper" in content and "Fake" in content


def test_build_rows_from_same_bilingual_track():
    captions = (cue(0, 2, "Welcome home.\n欢迎回家。"),)
    track = core.SubtitleTrack("x", "zh-CN", "双语", "manual", "bilingual", captions)
    rows = core.build_bilingual_rows(track, track)
    assert rows == [core.BilingualRow(0, 2, "Welcome home.", "欢迎回家。")]


def test_split_for_limit_keeps_short_text_whole():
    assert split_for_limit("Short one.", 480) == ["Short one."]


def test_split_for_limit_chunks_long_text_at_sentence_bounds():
    text = "First sentence here. Second one follows! Third, short. "
    chunks = split_for_limit(text, 25)
    assert all(len(chunk) <= 25 for chunk in chunks)
    assert len(chunks) > 1
    assert "".join(chunks) == text


def test_split_for_limit_hard_splits_unsplittable_text():
    text = "很" * 1200
    chunks = split_for_limit(text, 480)
    assert all(len(chunk) <= 480 for chunk in chunks)
    assert "".join(chunks) == text


def test_join_parts_is_cjk_aware():
    assert join_parts(["Hello.", "World."]) == "Hello. World."
    assert join_parts(["你好。", "世界。"]) == "你好。世界。"


def test_translate_texts_falls_back_when_first_backend_unreachable():
    def broken(_text):
        raise RuntimeError("no network")

    def working(text):
        return f"译[{text}]"

    translations, label = translate_texts(
        ["a", "b"], "en", "zh-CN",
        backends=[("Google", broken, 4500), ("MyMemory", working, 480)],
        retries=1, retry_sleep=0,
    )
    assert translations == ["译[a]", "译[b]"]
    assert label == "MyMemory"


def test_translate_texts_switches_backend_mid_run():
    calls = {"flaky": 0}

    def flaky(_text):
        calls["flaky"] += 1
        if calls["flaky"] > 1:
            raise RuntimeError("died mid-run")
        return "一"

    def working(_text):
        return "二"

    translations, label = translate_texts(
        ["a", "b", "c"], "en", "zh-CN",
        backends=[("G", flaky, 100), ("M", working, 100)],
        retries=1, retry_sleep=0,
    )
    assert translations == ["一", "二", "二"]
    assert label == "G / M"


def test_translate_texts_chunks_texts_over_backend_limit():
    calls = []

    def working(text):
        calls.append(text)
        return "句。"

    long_text = "Sentence one here. " * 30
    translations, _label = translate_texts(
        [long_text], "en", "zh-CN",
        backends=[("X", working, 100)],
        retries=1, retry_sleep=0,
    )
    assert len(calls) > 1 and all(len(call) <= 100 for call in calls)
    assert "".join(calls) == long_text
    assert translations == ["句。" * len(calls)]


def test_translate_texts_raises_when_all_backends_fail():
    def broken(_text):
        raise RuntimeError("down")

    with pytest.raises(RuntimeError, match="翻译后端"):
        translate_texts(
            ["a"], "en", "zh-CN",
            backends=[("G", broken, 100), ("M", broken, 100)],
            retries=1, retry_sleep=0,
        )


def test_fill_missing_languages_reports_backend_label():
    def working(text):
        return "你好。"

    rows = [core.BilingualRow(0, 2, "Hello.", "")]
    filled, methods = fill_missing_languages(rows, backends=[("MyMemory", working, 480)])
    assert filled[0].chinese == "你好。"
    assert methods and "MyMemory" in methods[0] and "机器翻译" in methods[0]


def test_fill_missing_languages_reports_progress_via_log():
    logs = []
    rows = [core.BilingualRow(0, 2, "Hello.", ""), core.BilingualRow(2, 4, "World.", "")]

    def working(_text):
        return "你好。"

    filled, _methods = fill_missing_languages(
        rows, backends=[("Fake", working, 480)], log=logs.append)

    assert [row.chinese for row in filled] == ["你好。", "你好。"]
    assert any("2/2" in line for line in logs)


def test_build_backends_skips_unreachable_google(monkeypatch):
    pytest.importorskip("deep_translator")
    import direct_generate

    monkeypatch.setattr(direct_generate, "_google_reachable", lambda timeout=3.0: False)
    backends = direct_generate._build_backends("en", "zh-CN")
    assert [backend[0] for backend in backends] == ["MyMemory"]

    monkeypatch.setattr(direct_generate, "_google_reachable", lambda timeout=3.0: True)
    backends = direct_generate._build_backends("en", "zh-CN")
    assert [backend[0] for backend in backends] == ["Google Translate", "MyMemory"]


def test_split_methods_separates_language_labels():
    methods = [
        "English：faster-whisper small.en 机器识别",
        "中文：MyMemory 机器翻译",
        "English：faster-whisper small.en 机器识别",  # 重复项应被去重
    ]
    assert split_methods(methods) == (
        "faster-whisper small.en 机器识别",
        "MyMemory 机器翻译",
    )
    assert split_methods([]) == ("", "")


def _install_fake_ytdlp(monkeypatch, info, warning=""):
    """注入假 yt_dlp：extract_video 不触网即可测各种 info/warning 组合。"""
    import types

    class FakeYoutubeDL:
        def __init__(self, options):
            self._logger = options.get("logger")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, url, download):
            if warning:
                self._logger.warning(warning)
            return info

    fake = types.ModuleType("yt_dlp")
    fake.YoutubeDL = FakeYoutubeDL
    monkeypatch.setitem(sys.modules, "yt_dlp", fake)


def test_extract_video_without_tracks_returns_video_for_transcription(monkeypatch):
    info = {
        "title": "English Talk",
        "webpage_url": "https://www.bilibili.com/video/BV1pgtn6NENb",
        "duration": 120,
        "subtitles": {},
        "automatic_captions": {},
    }
    _install_fake_ytdlp(monkeypatch, info)
    video = extract_video("BV1pgtn6NENb")
    assert video.tracks == ()
    assert video.title == "English Talk"
    assert any("语音识别" in warning or "Whisper" in warning for warning in video.warnings)


def test_extract_video_still_raises_when_login_required(monkeypatch):
    info = {"title": "t", "subtitles": {}, "automatic_captions": {}}
    _install_fake_ytdlp(monkeypatch, info, warning="Please login to view subtitles")
    with pytest.raises(ExtractionError, match="登录"):
        extract_video("BV1pgtn6NENb", "none")


def test_extract_video_returns_empty_tracks_when_logged_in(monkeypatch):
    info = {"title": "t", "subtitles": {}, "automatic_captions": {}}
    _install_fake_ytdlp(monkeypatch, info, warning="Please login to view subtitles")
    video = extract_video("BV1pgtn6NENb", "edge")
    assert video.tracks == ()


def test_friendly_error_maps_bilibili_412_to_retry_hint():
    from extractor import _friendly_error

    message = _friendly_error(RuntimeError("HTTP Error 412: Precondition Failed"), "none")
    assert "稍后再试" in message and "登录状态" in message


def test_collect_tracks_ignores_danmaku_and_deduplicates():
    srt = "1\n00:00:00,000 --> 00:00:01,000\nHello there\n"
    info = {
        "subtitles": {
            "danmaku": [{"data": "<i>xml</i>", "ext": "xml"}],
            "en-US": [{"data": srt, "ext": "srt"}],
        },
        "automatic_captions": {"en-US": [{"data": srt, "ext": "srt"}]},
    }
    tracks = collect_tracks(info)
    assert len(tracks) == 1
    assert tracks[0].family == "english" and tracks[0].captions[0].text == "Hello there"


def test_markdown_is_bilingual_subtitle_style():
    rows = [core.BilingualRow(1.2, 3.4, "Hello.", "你好。")]
    text = core.render_markdown("标题", "https://www.bilibili.com/video/BV1pgtn6NENb", rows, "English", "中文")
    assert text.startswith("# 标题\n")
    assert "`00:00:01 → 00:00:03`" in text
    assert "**Hello.**" in text and "你好。" in text


def test_render_srt_is_standard_bilingual_format():
    rows = [
        core.BilingualRow(1.2, 3.4, "Hello world.", "你好，世界"),
        core.BilingualRow(3.4, 5.0, "Second line.", ""),
    ]
    text = core.render_srt(rows)
    blocks = text.strip().split("\n\n")
    assert len(blocks) == 2
    assert blocks[0].splitlines() == [
        "1",
        "00:00:01,200 --> 00:00:03,400",
        "Hello world.",
        "你好，世界",
    ]
    assert blocks[1].splitlines() == [
        "2",
        "00:00:03,400 --> 00:00:05,000",
        "Second line.",
    ]
    assert text.endswith("\n")


def test_render_srt_pads_hours_and_holds_long_durations():
    rows = [core.BilingualRow(0, 3661.5, "Long video.", "长视频。")]
    lines = core.render_srt(rows).strip().splitlines()
    assert lines[1] == "00:00:00,000 --> 01:01:01,500"
    assert lines[2] == "Long video."


def test_xlsx_package_has_readable_sheet_freeze_filter_and_time_style():
    rows = [core.BilingualRow(1.25, 3.5, "Hello world", "你好，世界")]
    data = build_xlsx("视频标题", "https://www.bilibili.com/video/BV1pgtn6NENb", rows)
    with ZipFile(BytesIO(data)) as archive:
        assert archive.testzip() is None
        names = set(archive.namelist())
        assert {"xl/workbook.xml", "xl/styles.xml", "xl/worksheets/sheet1.xml"} <= names
        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        assert sheet.find(".//m:pane", ns).attrib["ySplit"] == "3"
        assert sheet.find(".//m:autoFilter", ns).attrib["ref"] == "A3:E4"
        cells = {cell.attrib["r"]: cell for cell in sheet.findall(".//m:c", ns)}
        assert cells["B4"].attrib["s"] == "5"
        assert float(cells["B4"].find("m:v", ns).text) == pytest.approx(1.25 / 86400)


def test_xlsx_uses_shared_strings_and_theme_for_viewer_compatibility():
    rows = [core.BilingualRow(1.0, 2.5, "Hello world", "你好，世界")]
    data = build_xlsx("视频标题", "https://www.bilibili.com/video/BV1pgtn6NENb", rows)
    with ZipFile(BytesIO(data)) as archive:
        names = set(archive.namelist())
        assert "xl/sharedStrings.xml" in names
        assert "xl/theme/theme1.xml" in names
        content_types = archive.read("[Content_Types].xml").decode("utf-8")
        assert "spreadsheetml.sharedStrings+xml" in content_types
        assert "theme+xml" in content_types
        rels = archive.read("xl/_rels/workbook.xml.rels").decode("utf-8")
        assert "sharedStrings.xml" in rels and "theme1.xml" in rels
        sheet = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
        assert 't="inlineStr"' not in sheet, "轻量查看器不支持 inlineStr，应全部走 sharedStrings"
        shared = archive.read("xl/sharedStrings.xml").decode("utf-8")
        for value in ("视频标题", "序号", "English", "Hello world", "你好，世界"):
            assert value in shared


def test_web_generate_and_download_endpoints():
    from extractor import ExtractedVideo

    spec = importlib.util.spec_from_file_location("bilibili_subtitles_web", BASE / "app.py")
    assert spec and spec.loader
    web = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = web
    spec.loader.exec_module(web)

    track = core.SubtitleTrack(
        "bilingual:1", "zh-CN", "中英双语", "manual", "bilingual",
        (cue(0, 2, "Hello there.\n你好。"),),
    )
    video = ExtractedVideo(
        "接口测试视频", "https://www.bilibili.com/video/BV1xx411c7mD",
        "tester", 2.0, (track,),
    )
    job_id = web.jobs.put(web.Job(video))
    client = web.app.test_client()

    generated = client.post("/api/generate", json={
        "job_id": job_id,
        "english_track": track.id,
        "chinese_track": track.id,
    })
    assert generated.status_code == 200
    body = generated.get_json()
    assert body["count"] == 1 and body["has_english"] and body["has_chinese"]

    markdown = client.get(f"/api/jobs/{job_id}/download/md")
    assert markdown.status_code == 200
    assert "Hello there." in markdown.get_data(as_text=True)
    workbook = client.get(f"/api/jobs/{job_id}/download/xlsx")
    assert workbook.status_code == 200
    with ZipFile(BytesIO(workbook.data)) as archive:
        assert archive.testzip() is None


def _load_web():
    spec = importlib.util.spec_from_file_location("bilibili_subtitles_web", BASE / "app.py")
    assert spec and spec.loader
    web = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = web
    spec.loader.exec_module(web)
    return web


def _no_track_video(title="无字幕英文视频"):
    from extractor import ExtractedVideo

    return ExtractedVideo(title, "https://www.bilibili.com/video/BV1pgtn6NENb", "tester", 10.0, ())


def test_rows_to_speech_text_picks_column_and_skips_empty():
    import tts_bridge

    rows = [
        core.BilingualRow(0, 2, "Hello there.", "你好。"),
        core.BilingualRow(2, 4, "", "只有中文"),
    ]
    assert tts_bridge.rows_to_speech_text(rows, "english") == "Hello there."
    assert tts_bridge.rows_to_speech_text(rows, "chinese") == "你好。 只有中文"
    assert tts_bridge.rows_to_speech_text([], "english") == ""
    with pytest.raises(ValueError):
        tts_bridge.rows_to_speech_text(rows, "japanese")


def test_missing_tts_dependency_reports_hint_when_core_absent(monkeypatch):
    import tts_bridge

    def broken():
        raise RuntimeError("缺模块")

    monkeypatch.setattr(tts_bridge, "load_tts_core", broken)
    assert tts_bridge.missing_tts_dependency() == "缺模块"
    assert tts_bridge.missing_tts_dependency() is not None


def test_missing_tts_dependency_none_when_available():
    import tts_bridge

    if tts_bridge.missing_tts_dependency() is None:
        return  # 依赖齐全
    pytest.skip("edge-tts 未安装，跳过可用分支")


def test_synthesize_chunks_splits_concatenates_and_reports_progress(tmp_path):
    import tts_bridge
    from direct_generate import split_for_limit

    synthesized = []

    async def fake_synth(text, voice, rate, pitch, mp3_path, translation=""):
        synthesized.append(text)
        mp3_path.write_bytes(f"[{text}]".encode("utf-8"))
        return mp3_path.with_suffix(".json")

    text = "Sentence one here. Sentence two follows! Third one? "
    progress_calls = []
    data = tts_bridge.synthesize_chunks(
        text, "en-US-AvaMultilingualNeural", "+0%", "+0Hz",
        limit=25, work_dir=tmp_path, synthesize=fake_synth,
        progress=lambda done, total: progress_calls.append((done, total)),
    )

    chunks = split_for_limit(text, 25)
    assert len(chunks) >= 2
    assert synthesized == chunks
    expected = "".join(f"[{chunk}]" for chunk in chunks).encode("utf-8")
    assert data == expected
    assert progress_calls == [(index, len(chunks)) for index in range(1, len(chunks) + 1)]
    # 临时分片不留在工作目录之外，工作目录内合成完只剩分片文件（由调用方清理）
    assert sorted(p.name for p in tmp_path.glob("part-*.mp3")) == [
        f"part-{index:03d}.mp3" for index in range(1, len(chunks) + 1)
    ]


def test_transcribe_job_lifecycle_and_srt_download(monkeypatch):
    from direct_generate import AudioPipelineResult

    web = _load_web()
    job_id = web.jobs.put(web.Job(video=_no_track_video()))
    monkeypatch.setattr(web, "_whisper_deps_missing", lambda: None)

    def fake_pipeline(url, browser, model_name, log=None):
        if log:
            log("[2/5] 下载临时音频（测试）")
        return AudioPipelineResult(
            title="无字幕英文视频",
            source_url="https://www.bilibili.com/video/BV1pgtn6NENb",
            rows=[core.BilingualRow(0, 2, "Hello there.", "")],
            methods=["English：faster-whisper small.en 机器识别"],
        )

    monkeypatch.setattr(web, "TRANSCRIBE_PIPELINE", fake_pipeline)
    monkeypatch.setattr(web, "TRANSLATE_ROWS", lambda rows, log=None: (
        [core.BilingualRow(0, 2, "Hello there.", "你好。")], ["中文：Fake 机器翻译"],
    ))

    client = web.app.test_client()
    started = client.post(f"/api/jobs/{job_id}/transcribe", json={"browser": "none"})
    assert started.status_code == 200 and started.get_json()["ok"]

    web.jobs.get(job_id).transcribe_thread.join(timeout=5)

    body = client.get(f"/api/jobs/{job_id}/transcribe/status").get_json()
    assert body["phase"] == "done" and body["error"] == ""
    assert body["count"] == 1 and body["has_english"] and body["has_chinese"]
    assert any("下载临时音频" in line for line in body["log"])
    assert body["stage"]["step"] == 4

    srt = client.get(f"/api/jobs/{job_id}/download/srt")
    assert srt.status_code == 200
    text = srt.get_data(as_text=True)
    assert "00:00:00,000 --> 00:00:02,000" in text
    assert "Hello there." in text and "你好。" in text

    markdown = client.get(f"/api/jobs/{job_id}/download/md")
    assert markdown.status_code == 200
    assert "faster-whisper" in markdown.get_data(as_text=True)


def test_transcribe_job_reports_pipeline_error(monkeypatch):
    web = _load_web()
    job_id = web.jobs.put(web.Job(video=_no_track_video()))
    monkeypatch.setattr(web, "_whisper_deps_missing", lambda: None)

    def broken(url, browser, model_name, log=None):
        raise RuntimeError("下载音频失败（测试）")

    monkeypatch.setattr(web, "TRANSCRIBE_PIPELINE", broken)
    client = web.app.test_client()
    assert client.post(f"/api/jobs/{job_id}/transcribe", json={}).status_code == 200
    web.jobs.get(job_id).transcribe_thread.join(timeout=5)

    body = client.get(f"/api/jobs/{job_id}/transcribe/status").get_json()
    assert body["phase"] == "error"
    assert "下载音频失败（测试）" in body["error"]


def test_transcribe_rejects_duplicate_start(monkeypatch):
    from direct_generate import AudioPipelineResult

    web = _load_web()
    job_id = web.jobs.put(web.Job(video=_no_track_video()))
    monkeypatch.setattr(web, "_whisper_deps_missing", lambda: None)
    release = threading.Event()
    pipeline_started = threading.Event()

    def slow_pipeline(url, browser, model_name, log=None):
        pipeline_started.set()
        release.wait(5)
        return AudioPipelineResult(
            "t", "https://www.bilibili.com/video/BV1pgtn6NENb",
            [core.BilingualRow(0, 1, "Hi", "")], [],
        )

    monkeypatch.setattr(web, "TRANSCRIBE_PIPELINE", slow_pipeline)
    client = web.app.test_client()
    assert client.post(f"/api/jobs/{job_id}/transcribe", json={}).status_code == 200
    assert pipeline_started.wait(5)
    duplicate = client.post(f"/api/jobs/{job_id}/transcribe", json={})
    assert duplicate.status_code == 409
    release.set()
    web.jobs.get(job_id).transcribe_thread.join(timeout=5)


def test_transcribe_rejects_when_dependencies_missing(monkeypatch):
    web = _load_web()
    job_id = web.jobs.put(web.Job(video=_no_track_video()))
    monkeypatch.setattr(web, "_whisper_deps_missing", lambda: "缺少 faster-whisper（测试）")
    client = web.app.test_client()
    response = client.post(f"/api/jobs/{job_id}/transcribe", json={})
    assert response.status_code == 400
    assert "faster-whisper" in response.get_json()["error"]


def test_transcribe_unknown_job_returns_404():
    web = _load_web()
    client = web.app.test_client()
    assert client.post("/api/jobs/nope/transcribe", json={}).status_code == 404
    assert client.get("/api/jobs/nope/transcribe/status").status_code == 404


def test_inspect_returns_transcribable_video_without_tracks(monkeypatch):
    web = _load_web()
    monkeypatch.setattr(web, "extract_video", lambda url, browser: _no_track_video("纯英文口播"))
    client = web.app.test_client()
    response = client.post("/api/inspect", json={
        "url": "https://www.bilibili.com/video/BV1pgtn6NENb", "browser": "none",
    })
    assert response.status_code == 200
    body = response.get_json()
    assert body["ok"] and body["tracks"] == []
    assert body["can_transcribe"] is True


def test_derive_transcribe_stage_steps_and_translation_detail():
    web = _load_web()
    assert web.derive_transcribe_stage(["[2/5] 下载临时音频（最终不会保留）"])["step"] == 1
    assert web.derive_transcribe_stage(["[3/5] 加载 Whisper small.en"])["step"] == 2
    stage = web.derive_transcribe_stage([
        "[2/5] 下载临时音频",
        "      识别完成：120 个片段 → 40 条阅读字幕",
        "[4/5] 翻译英文 → 中文：40 条",
        "      翻译进度 12/40",
    ])
    assert stage["step"] == 3
    assert stage["detail"] == "翻译 12/40"
    assert web.derive_transcribe_stage([]) == {"step": 0, "detail": ""}


def test_tts_job_lifecycle_and_mp3_download(monkeypatch):
    web = _load_web()
    job_id = web.jobs.put(web.Job(video=_no_track_video("TTS 视频")))
    web.jobs.get(job_id).rows = [core.BilingualRow(0, 2, "Hello there.", "你好。")]
    monkeypatch.setattr(web, "_tts_deps_missing", lambda: None)

    calls = {}

    def fake_synthesize(text, voice, rate, pitch, work_dir, progress=None):
        calls.update(text=text, voice=voice, rate=rate, pitch=pitch)
        if progress:
            progress(1, 2)
            progress(2, 2)
        return b"ID3-fake-mp3-bytes"

    monkeypatch.setattr(web, "TTS_SYNTHESIZE", fake_synthesize)

    client = web.app.test_client()
    started = client.post(f"/api/jobs/{job_id}/tts", json={
        "lang": "english", "voice": "en-US-AvaMultilingualNeural", "rate": -10,
    })
    assert started.status_code == 200 and started.get_json()["ok"]
    web.jobs.get(job_id).tts_thread.join(timeout=5)

    body = client.get(f"/api/jobs/{job_id}/tts/status").get_json()
    assert body["phase"] == "done" and body["error"] == ""
    assert body["done"] == 2 and body["total"] == 2
    assert calls["text"] == "Hello there."
    assert calls["rate"] == "-10%" and calls["pitch"] == "+0Hz"

    mp3 = client.get(f"/api/jobs/{job_id}/download/mp3")
    assert mp3.status_code == 200
    assert mp3.data == b"ID3-fake-mp3-bytes"
    assert mp3.mimetype == "audio/mpeg"
    assert ".mp3" in mp3.headers.get("Content-Disposition", "")


def test_tts_rejects_when_no_rows(monkeypatch):
    web = _load_web()
    job_id = web.jobs.put(web.Job(video=_no_track_video()))
    monkeypatch.setattr(web, "_tts_deps_missing", lambda: None)
    client = web.app.test_client()
    response = client.post(f"/api/jobs/{job_id}/tts", json={"lang": "english"})
    assert response.status_code == 400
    assert "字幕" in response.get_json()["error"]


def test_tts_rejects_invalid_language_and_voice(monkeypatch):
    web = _load_web()
    job_id = web.jobs.put(web.Job(video=_no_track_video()))
    web.jobs.get(job_id).rows = [core.BilingualRow(0, 2, "Hi", "你好")]
    monkeypatch.setattr(web, "_tts_deps_missing", lambda: None)
    client = web.app.test_client()
    bad_lang = client.post(f"/api/jobs/{job_id}/tts", json={"lang": "japanese"})
    assert bad_lang.status_code == 400
    bad_voice = client.post(f"/api/jobs/{job_id}/tts", json={"lang": "english", "voice": "voice-not-exist"})
    assert bad_voice.status_code == 400


def test_tts_rejects_when_dependencies_missing(monkeypatch):
    web = _load_web()
    job_id = web.jobs.put(web.Job(video=_no_track_video()))
    web.jobs.get(job_id).rows = [core.BilingualRow(0, 2, "Hi", "你好")]
    monkeypatch.setattr(web, "_tts_deps_missing", lambda: "缺少 edge-tts（测试）")
    client = web.app.test_client()
    response = client.post(f"/api/jobs/{job_id}/tts", json={"lang": "english"})
    assert response.status_code == 400
    assert "edge-tts" in response.get_json()["error"]


def test_tts_rejects_duplicate_start(monkeypatch):
    web = _load_web()
    job_id = web.jobs.put(web.Job(video=_no_track_video()))
    web.jobs.get(job_id).rows = [core.BilingualRow(0, 2, "Hi", "你好")]
    monkeypatch.setattr(web, "_tts_deps_missing", lambda: None)
    release = threading.Event()
    started = threading.Event()

    def slow_synthesize(text, voice, rate, pitch, work_dir, progress=None):
        started.set()
        release.wait(5)
        return b"mp3"

    monkeypatch.setattr(web, "TTS_SYNTHESIZE", slow_synthesize)
    client = web.app.test_client()
    assert client.post(f"/api/jobs/{job_id}/tts", json={"lang": "english"}).status_code == 200
    assert started.wait(5)
    assert client.post(f"/api/jobs/{job_id}/tts", json={"lang": "english"}).status_code == 409
    release.set()
    web.jobs.get(job_id).tts_thread.join(timeout=5)


def test_tts_unknown_job_returns_404():
    web = _load_web()
    client = web.app.test_client()
    assert client.post("/api/jobs/nope/tts", json={}).status_code == 404
    assert client.get("/api/jobs/nope/tts/status").status_code == 404


def test_tts_voices_endpoint_lists_text2mp3_voices():
    web = _load_web()
    client = web.app.test_client()
    response = client.get("/api/tts/voices")
    assert response.status_code == 200
    body = response.get_json()
    assert body["ok"] and len(body["voices"]) >= 10
    assert any("Ava" in voice["id"] for voice in body["voices"])
    assert all(set(voice) == {"label", "id"} for voice in body["voices"])


def test_manifest_discovers_bilibili_subtitles():
    sys.path.insert(0, str(Path(__file__).parents[1]))
    from launcher.manifest import load_tools

    tools = {tool.slug: tool for tool in load_tools(Path(__file__).parents[1] / "tools")}
    tool = tools["bilibili-subtitles"]
    assert tool.name == "B站双语字幕"
    assert tool.port == 8600 and tool.status == "ready"
