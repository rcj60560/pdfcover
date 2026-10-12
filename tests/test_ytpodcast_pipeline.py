"""English Leap Podcast:vtt → 滚动字幕 md 管线纯逻辑测试。"""
import sys
from pathlib import Path

TOOL = Path(__file__).parents[1] / "tools" / "subtitle-viewer"
sys.path.insert(0, str(TOOL))

VTT = """WEBVTT
Kind: captions
Language: en

00:00:04.000 --> 00:00:09.000
Welcome back to the

00:00:09.000 --> 00:00:15.240
English Leap Podcast.

00:00:15.480 --> 00:00:19.100
Hey English learners,
"""


def test_parse_vtt():
    from ytpodcast.build import parse_vtt
    cues = parse_vtt(VTT)
    assert cues == [
        (4.0, 9.0, "Welcome back to the"),
        (9.0, 15.24, "English Leap Podcast."),
        (15.48, 19.1, "Hey English learners,"),
    ]


def test_parse_vtt_strips_tags_and_inline_ts():
    from ytpodcast.build import parse_vtt
    vtt = ("WEBVTT\n\n00:00:01.000 --> 00:00:02.000\n"
           "welcome <00:00:01.500><c>back</c>.\n")
    assert parse_vtt(vtt) == [(1.0, 2.0, "welcome back.")]


ROLLING = """WEBVTT
Kind: captions
Language: en

00:00:00.560 --> 00:00:03.430 align:start position:0%

English<00:00:00.920><c> Leap</c>

00:00:03.430 --> 00:00:03.440 align:start position:0%
English Leap


00:00:03.440 --> 00:00:05.590 align:start position:0%
English Leap
with<00:00:03.800><c> Class.</c><00:00:03.929><c> [music]</c>

00:00:05.590 --> 00:00:05.600 align:start position:0%
with Class. [music]


00:00:05.600 --> 00:00:07.950 align:start position:0%
with Class. [music]
Hey<00:00:05.960><c> learners.</c>
"""


def test_parse_vtt_滚动字幕去重():
    """YouTube 自动字幕滚动窗口:每 cue 只取新增行,桥接复读丢弃,[music] 剥离。"""
    from ytpodcast.build import parse_vtt
    cues = parse_vtt(ROLLING)
    assert cues == [
        (0.56, 3.43, "English Leap"),
        (3.44, 5.59, "with Class."),
        (5.6, 7.95, "Hey learners."),
    ]


def test_merge_cues_句末断句():
    from ytpodcast.build import merge_cues
    cues = [
        (4.0, 9.0, "Welcome back to the"),
        (9.0, 15.24, "English Leap Podcast."),
        (15.48, 19.1, "Hey English learners,"),
        (19.1, 23.0, "welcome back."),
    ]
    blocks = merge_cues(cues)
    assert len(blocks) == 2
    assert blocks[0]["text"] == "Welcome back to the English Leap Podcast."
    assert blocks[0]["start"] == 4.0
    assert blocks[1]["text"] == "Hey English learners, welcome back."
    assert blocks[1]["start"] == 15.48


def test_merge_cues_超长强制断与滚动去重():
    from ytpodcast.build import merge_cues
    cues = [(i * 5.0, i * 5.0 + 5, t)
            for i, t in enumerate(["w0 w1 w2 w3", "w0 w1 w2 w3", "w4", "w5", "w6 w7", "w8", "w9"])]
    blocks = merge_cues(cues, max_words=4)
    assert [b["text"] for b in blocks] == ["w0 w1 w2 w3", "w4 w5 w6 w7", "w8 w9"]


def test_fmt_ts():
    from ytpodcast.build import fmt_ts
    assert fmt_ts(83.4) == "1:23"
    assert fmt_ts(3723) == "1:02:03"


def test_build_md_块格式():
    from subtitle_lib import has_timestamps
    from ytpodcast.build import build_md
    blocks = [
        {"start": 4.0, "end": 15.24, "text": "Welcome back to the English Leap Podcast."},
        {"start": 15.48, "end": 23.0, "text": "Hey English learners, welcome back."},
    ]
    md = build_md("EP01 - Test Episode", "EP01 - Test Episode.mp3", blocks)
    assert has_timestamps(md)
    assert "`0:04 → 0:15`" in md          # 块 end = 下一块 start
    assert "`0:15 → 0:23`" in md          # 末块用自身 end(≥start+5)
    assert "**Welcome back to the English Leap Podcast.**" in md
    assert "EP01 - Test Episode.mp3" in md
    assert "<style>" in md


def test_en_only_整段不换行():
    from ytpodcast.build import en_only
    blocks = [
        {"start": 1.0, "end": 2.0, "text": "First sentence."},
        {"start": 3.0, "end": 4.0, "text": "Second one."},
    ]
    out = en_only("EP01 - Test", blocks)
    assert out.startswith("# EP01 - Test")
    body = out.split("\n", 2)[-1]
    assert body.strip() == "First sentence. Second one."   # 单段,无硬换行(欧路整段翻译用)
