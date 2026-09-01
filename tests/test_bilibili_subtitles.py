"""B站双语字幕工具纯逻辑测试（不触网、不要求安装 yt-dlp）。"""
from __future__ import annotations

import sys
import importlib.util
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest

BASE = Path(__file__).parents[1] / "tools" / "bilibili-subtitles"
sys.path.insert(0, str(BASE))

import subtitle_core as core  # noqa: E402
from extractor import collect_tracks  # noqa: E402
from xlsx_export import build_xlsx  # noqa: E402
from direct_generate import apply_translations, merge_captions  # noqa: E402


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


def test_build_rows_from_same_bilingual_track():
    captions = (cue(0, 2, "Welcome home.\n欢迎回家。"),)
    track = core.SubtitleTrack("x", "zh-CN", "双语", "manual", "bilingual", captions)
    rows = core.build_bilingual_rows(track, track)
    assert rows == [core.BilingualRow(0, 2, "Welcome home.", "欢迎回家。")]


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
    text = core.render_markdown("标题", "https://www.bilibili.com/video/BV1x", rows, "English", "中文")
    assert text.startswith("# 标题\n")
    assert "`00:00:01 → 00:00:03`" in text
    assert "**Hello.**" in text and "你好。" in text


def test_xlsx_package_has_readable_sheet_freeze_filter_and_time_style():
    rows = [core.BilingualRow(1.25, 3.5, "Hello world", "你好，世界")]
    data = build_xlsx("视频标题", "https://www.bilibili.com/video/BV1x", rows)
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


def test_manifest_discovers_bilibili_subtitles():
    sys.path.insert(0, str(Path(__file__).parents[1]))
    from launcher.manifest import load_tools

    tools = {tool.slug: tool for tool in load_tools(Path(__file__).parents[1] / "tools")}
    tool = tools["bilibili-subtitles"]
    assert tool.name == "B站双语字幕"
    assert tool.port == 8600 and tool.status == "ready"
