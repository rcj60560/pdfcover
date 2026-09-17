"""剑桥词汇管线纯逻辑测试。"""
import sys
from pathlib import Path

TOOL = Path(__file__).parents[1] / "tools" / "subtitle-viewer"
sys.path.insert(0, str(TOOL))

PAGES = [
    "Recording 1a\n"
    "Speaker A: On Mondays | often talk about movies.\n"
    "Speaker B: My parents are both teachers.\n",
    "Recording 1b\n"
    "Teacher: Tell me about your family.\n"
    "Student: Well, my immediate family is small!\n"
    "Recording 1c\n"           # 无说话人 → 整段 narration
    "You will hear two people talking about family.\n",
]

def test_clean_line():
    from cambridge.extract import clean_line
    assert clean_line("| often can’t stop") == "I often can't stop"
    assert clean_line("small! and fun") == "small! and fun"   # 紧贴单词的 ! 不是 I
    assert clean_line("abie   able") == "abie able"


def test_clean_line_strips_page_header_residue():
    from cambridge.extract import clean_line
    # 1c turn22 场景:页边界把「157 Recording scripts」粘进 turn 文本
    assert clean_line("Yes, that does make more sense! 157 Recording scripts") == \
        "Yes, that does make more sense!"
    assert clean_line("Yes, that does make more sense!\n157\n\nRecording scripts\n") == \
        "Yes, that does make more sense!"
    # 页码被 OCR 误读(如「eg」)时只剩裸页眉,也要剥掉
    assert clean_line("studies. eg Recording scripts") == "studies. eg"
    # 首尾裸页码 token 剥除;四位数年份不受牵连
    assert clean_line("157 turn text 158") == "turn text"
    assert clean_line("2010 was a year") == "2010 was a year"
    # 纯页码保持原样(剩余为空不剥),由上层空文本判断丢弃
    assert clean_line("157") == "157"

def test_parse_scripts():
    from cambridge.extract import parse_scripts
    recs = parse_scripts(PAGES)
    assert [r["id"] for r in recs] == ["1a", "1b", "1c"]
    assert recs[0]["turns"][0] == {"label": "Speaker A",
        "text": "On Mondays I often talk about movies."}
    assert recs[1]["turns"] == [
        {"label": "Teacher", "text": "Tell me about your family."},
        {"label": "Student", "text": "Well, my immediate family is small!"},
    ]
    assert recs[2]["turns"] == [{"label": "",
        "text": "You will hear two people talking about family."}]

NOCOLON_PAGES = [
    "Recording 7a\n"            # 无冒号 A–J 枚举;run 后附录/Key 全部丢弃
    "A Leading environmentalists are concerned about warming.\n"
    "B Scientists have shown that fish may be beneficial.\n"
    "C Satellites have recently sent back new data from Mars.\n"
    "\n"
    "APPENDIX\n"
    "adolescence /x/\n"
    "Key: | = left, c = centre.\n",
    "Recording 8a\n"            # 带数字的说话人标签不残留
    "Speaker 1: Not really, | think so.\n"
    "Speaker 2: For me there is only one choice.\n",
    "Recording 9a\n"            # credits 标签出现即截断
    "Speaker A: Hello there.\n"
    "Key: | = left, c = centre, r = right.\n"
    "Picture research: Hilary Luckcock\n",
    "Recording 10a\n"           # 保守门:孤立 “A …” 行不切 turn
    "A man and a woman are talking about weather.\n"
    "They will discuss the family.\n",
]

def test_parse_scripts_no_colon_and_credits():
    from cambridge.extract import parse_scripts
    recs = parse_scripts(NOCOLON_PAGES)
    assert [r["id"] for r in recs] == ["7a", "8a", "9a", "10a"]
    assert recs[0]["turns"] == [
        {"label": "A", "text": "Leading environmentalists are concerned about warming."},
        {"label": "B", "text": "Scientists have shown that fish may be beneficial."},
        {"label": "C", "text": "Satellites have recently sent back new data from Mars."},
    ]
    assert recs[1]["turns"] == [
        {"label": "Speaker 1", "text": "Not really, I think so."},
        {"label": "Speaker 2", "text": "For me there is only one choice."},
    ]
    assert recs[2]["turns"] == [{"label": "Speaker A", "text": "Hello there."}]
    assert recs[3]["turns"] == [{"label": "",
        "text": "A man and a woman are talking about weather. They will discuss the family."}]


def test_words_of_normalizes_unicode_punctuation():
    from cambridge.align import words_of
    assert words_of("I can't – STOP!") == ["i", "can't", "stop"]


def test_align_turns_matches_and_interpolates_unmatched_run():
    from cambridge.align import align_turns

    turns = [
        {"label": "A", "text": "alpha"},
        {"label": "B", "text": "bravo charlie"},
        {"label": "C", "text": "delta echo foxtrot"},
        {"label": "D", "text": "omega"},
    ]
    words = [
        {"w": "alpha", "s": 1.0, "e": 2.0},
        {"w": "omega", "s": 10.0, "e": 11.0},
    ]

    out = align_turns(turns, words)
    assert (out[0]["start"], out[0]["end"], out[0]["conf"]) == (1.0, 2.0, 1.0)
    assert (out[1]["start"], out[1]["end"], out[1]["conf"]) == (2.0, 5.2, 0.0)
    assert (out[2]["start"], out[2]["end"], out[2]["conf"]) == (5.2, 10.0, 0.0)
    assert (out[3]["start"], out[3]["end"], out[3]["conf"]) == (10.0, 11.0, 1.0)


def test_align_turns_whole_track_interpolation_and_empty_audio():
    from cambridge.align import align_turns

    turns = [
        {"label": "A", "text": "one"},
        {"label": "B", "text": "two three"},
    ]
    out = align_turns(turns, [
        {"w": "unrelated", "s": 2.0, "e": 5.0},
    ])
    assert (out[0]["start"], out[0]["end"]) == (0.0, 5 / 3)
    assert (out[1]["start"], out[1]["end"]) == (5 / 3, 5.0)
    assert all(item["conf"] == 0.0 for item in out)

    empty = align_turns(turns, [])
    assert all(item["start"] == item["end"] == 0.0 for item in empty)


MERGED_HEADING_PAGES = [
    # p166:5c 词表结尾连排 6a 独白(OCR 文本层漏了 “Recording 6a” 标题)
    "Recording 5c\n"
    "academic, assignment, controversy, research (n), thesis, theory, theoretical\n"
    "I'm a French teacher, but I remember when I first started to learn\n"
    "the language I really struggled with it.\n",
    "Recording 6b\n"
    "Speaker A: Now listen again and answer questions one to five.\n",
    # p167:8a 说话人段落连排 8b 讲座(漏了 “Recording 8b” 标题)
    "Recording 8a\n"
    "Speaker 3: I own about 12 watches and clocks, but none of them show the\n"
    "right time. Welcome once again to 'Introduction to dentistry' and in\n"
    "today's lecture we'll be looking at the history of dentistry.\n",
    "Recording 9a\n"
    "Speaker A: Hello there.\n",
]


def test_inject_missing_headings_splits_merged_recordings():
    from cambridge.extract import inject_missing_headings, parse_scripts

    recs = parse_scripts(inject_missing_headings(MERGED_HEADING_PAGES))
    assert [r["id"] for r in recs] == ["5c", "6a", "6b", "8a", "8b", "9a"]
    # 5c 词表独立成条,不再吸入 6a 独白
    assert recs[0]["turns"] == [{"label": "",
        "text": "academic, assignment, controversy, research (n), thesis, "
                "theory, theoretical I'm a"}]
    # 6a 独白内容完整
    assert recs[1]["turns"] == [{"label": "",
        "text": "French teacher, but I remember when I first started to learn "
                "the language I really struggled with it."}]
    # 8a 说话人段落止于原句末
    assert recs[3]["turns"] == [{"label": "Speaker 3",
        "text": "I own about 12 watches and clocks, but none of them show the right time."}]
    # 8b 讲座独立成条、内容完整
    assert recs[4]["turns"] == [{"label": "",
        "text": "Welcome once again to 'Introduction to dentistry' and in today's "
                "lecture we'll be looking at the history of dentistry."}]


def test_inject_missing_headings_raises_when_marker_count_differs():
    import pytest
    from cambridge.extract import inject_missing_headings

    duplicated = ["Recording 5c\n"
                  "The French teacher, but meets another French teacher, but here.\n"]
    with pytest.raises(ValueError):
        inject_missing_headings(duplicated)

    absent = ["Recording 1a\nSpeaker A: Nothing to see.\n"]  # 换书:标志缺失
    with pytest.raises(ValueError):
        inject_missing_headings(absent)


MIDLINE_HEADING_PAGES = [
    # 15b 词表行中粘着无字母标题「Recording 16」(REC_RE 切不开)
    "Recording 15b\n"
    "recycle, reusable, rubbish, solar, warmer Recording 16\n"
    "Let's find out just how environmentally aware you are.\n",
    # 17b 词表行中粘着「Recording 18」
    "Recording 17b\n"
    "bird, earn, first, nurse, perk, purse, work Recording 18\n"
    "In spite of the large number of prisons we have, crime figures have risen.\n",
    # 20c 词表行中粘着「Recording 21」,21 词表接在标题同一行
    "Recording 20c\n"
    "atmosphere, classical, edition, festival, fundamental, imagination,\n"
    "literary, monotonous, musical Recording 21 put, these, in, some, ball,\n"
    "choose, word, about, guest, what, attack, hard\n",
    "Recording 22a\n"
    "Speaker A: Hello.\n",
]


def test_split_midline_headings_separates_letterless_recording():
    from cambridge.extract import parse_scripts, split_midline_headings

    recs = parse_scripts(split_midline_headings(MIDLINE_HEADING_PAGES))
    assert [r["id"] for r in recs] == ["15b", "16", "17b", "18", "20c", "21", "22a"]
    # 15b 词表止于行中标题前,不再吸入 16 全文
    assert recs[0]["turns"] == [{"label": "",
        "text": "recycle, reusable, rubbish, solar, warmer"}]
    assert recs[1]["turns"] == [{"label": "",
        "text": "Let's find out just how environmentally aware you are."}]
    assert recs[3]["turns"] == [{"label": "",
        "text": "In spite of the large number of prisons we have, crime figures "
                "have risen."}]
    # 20c 词表止于行中标题前,不再吸入 21 全文
    assert recs[4]["turns"] == [{"label": "",
        "text": "atmosphere, classical, edition, festival, fundamental, imagination, "
                "literary, monotonous, musical"}]
    # 21 独立成条、词表完整
    assert recs[5]["turns"] == [{"label": "",
        "text": "put, these, in, some, ball, choose, word, about, guest, what, "
                "attack, hard"}]
    assert recs[6]["turns"] == [{"label": "Speaker A", "text": "Hello."}]


def test_split_midline_headings_raises_when_marker_count_differs():
    import pytest
    from cambridge.extract import split_midline_headings

    duplicated = ["Recording 21 once and Recording 21 twice.\n"]  # 重复
    with pytest.raises(ValueError):
        split_midline_headings(duplicated)

    absent = ["Recording 1a\nSpeaker A: Nothing to see.\n"]  # 换书:标志缺失
    with pytest.raises(ValueError):
        split_midline_headings(absent)


def test_match_tracks_accepts_similarity_at_threshold():
    from cambridge.align import match_tracks

    recordings = [{"id": "r", "turns": [{"label": "", "text": "one two"}]}]
    tracks = {"Track.mp3": [{"w": word, "s": i, "e": i + 1}
                            for i, word in enumerate("one three".split())]}
    mapping, no_recording, no_track = match_tracks(recordings, tracks)
    assert mapping == {"r": "Track.mp3"}
    assert no_recording == []
    assert no_track == []


def test_match_tracks_skips_unspoken_leading_instructions():
    """4b 场景:脚本开头 26 词指令音频里未朗读,需前缀偏移后才能对上。"""
    from cambridge.align import match_tracks

    instructions = ("You will hear a woman talking on radio about spare activities "
                    "occupying younger minds during vacation time before beginning "
                    "listen carefully now very good luck everyone").split()
    real = "The school holidays are fast approaching and I'm sure all of you".split()
    assert len(instructions) == 26 and len(real) == 12
    recordings = [{"id": "4b", "turns": [
        {"label": "Narrator", "text": " ".join(instructions + real)}]}]
    tracks = {"Track12.mp3": [{"w": word, "s": i, "e": i + 1}
                              for i, word in enumerate(real)]}
    mapping, no_recording, no_track = match_tracks(recordings, tracks)
    assert mapping == {"4b": "Track12.mp3"}
    assert no_recording == []
    assert no_track == []


def test_match_tracks_truncates_track_head_to_script_head_length():
    """10c 场景:脚本前 2 turn 仅 18 词,Track 头 60 词;等长截断后才配得上。

    不截断时最佳相似度 2*18/78 ≈ 0.46 < 0.5,系统性吃亏。
    """
    from cambridge.align import match_tracks

    head = ("you will hear a man and a woman talking about how to use "
            "the big online school library").split()
    assert len(head) == 18
    tail = [f"later{i}" for i in range(42)]           # Track 头后续 42 词
    recordings = [{"id": "10c", "turns": [
        {"label": "Narrator", "text": " ".join(head[:8])},
        {"label": "Tutor", "text": " ".join(head[8:])},
    ]}]
    tracks = {
        "Track26.mp3": [{"w": w, "s": i, "e": i + 1} for i, w in enumerate(head + tail)],
        "Track99.mp3": [{"w": w, "s": i, "e": i + 1} for i, w in enumerate(tail)],
    }
    mapping, no_recording, no_track = match_tracks(recordings, tracks)
    assert mapping == {"10c": "Track26.mp3"}
    assert no_recording == []
    assert no_track == ["Track99.mp3"]


def test_fmt_ts():
    from cambridge.build_md import fmt_ts

    assert fmt_ts(83.4) == "1:23"
    assert fmt_ts(3723) == "1:02:03"


def test_build_md_formats_turns_with_timestamps_and_translation():
    from cambridge.build_md import build_md
    from subtitle_lib import has_timestamps

    turns = [
        {"label": "Speaker A", "text": "Hello world.", "start": 0.0, "end": 2.0, "conf": 1.0},
        {"label": "Speaker B", "text": "Good night.", "start": 5.0, "end": 6.0, "conf": 1.0},
    ]
    md = build_md("1a", "1 Family", turns, "Track01.mp3", {0: "你好,世界。", 1: "晚安。"})

    assert has_timestamps(md)
    assert "`0:00 → 0:05`" in md
    assert "`0:05 → 0:06`" in md
    assert "# 剑桥雅思核心词汇精讲精练 Recording 1a｜Unit 1 Family" in md
    assert "中文 `精翻`" in md
    assert "**Speaker A: Hello world.**" in md
    assert "你好,世界。" in md
    assert "Track01.mp3" in md


def test_md_filename_uses_fullwidth_separator():
    from cambridge.build_md import md_filename

    assert md_filename("1a", "1 Family") == "Recording 1a｜Unit 1 Family.md"
    assert "—" not in md_filename("22b", "22 Colour")  # 半角破折号不再用作分隔
