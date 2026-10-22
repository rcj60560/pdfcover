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


def test_merge_cues_一句一块与段内拆分():
    from ytpodcast.build import merge_cues
    cues = [
        (0.0, 5.0, "Hello everyone"),                    # 无句尾,跨行
        (5.0, 10.0, "and welcome. Today we talk."),       # 行内两句→按词比例拆时
        (10.0, 15.0, "It is fun."),                       # 单句
    ]
    blocks = merge_cues(cues)
    assert [b["text"] for b in blocks] == [
        "Hello everyone and welcome.",
        "Today we talk.",
        "It is fun.",
    ]
    # 段内拆分:welcome.(2词) vs Today we talk.(3词) → 5.0+5*(2/5)=7.0
    assert abs(blocks[0]["end"] - 7.0) < 0.01
    assert blocks[1]["start"] == 7.0 and abs(blocks[1]["end"] - 10.0) < 0.01
    assert blocks[2]["start"] == 10.0


def test_build_md_反转义HTML实体():
    from ytpodcast.build import build_md
    blocks = [{"start": 1.0, "end": 2.0, "text": "&gt;&gt; hello &amp; welcome"}]
    md = build_md("EP01 - T", "EP01 - T.mp3", blocks)
    assert "**>> hello & welcome**" in md          # 显示层反转义(解析层不动,块数与对齐锁死)


def test_parse_lr_xlsx_无需openpyxl的纯逻辑():
    from ytpodcast.build import clean_zh_line, parse_lr_time
    assert clean_zh_line(">> 是的，欢迎。") == "是的，欢迎。"
    assert clean_zh_line("这里 [笑声] 很好") == "这里 很好"
    assert clean_zh_line("  保持 原样  ") == "保持 原样"
    assert parse_lr_time("0s") == 0
    assert parse_lr_time("1:01") == 61
    assert parse_lr_time("1:01:05") == 3665
    assert parse_lr_time("abc") is None


def test_build_window_blocks_窗口即块():
    from ytpodcast.build import build_window_blocks
    cues = [
        (0.0, 3.0, "Hello everyone"), (3.0, 5.0, "out there."),
        (5.0, 8.0, "Welcome back."), (8.0, 10.0, "Sit down."),
    ]
    rows = [(0, "大家好。"), (5, "欢迎回来。")]
    blocks = build_window_blocks(cues, rows)
    assert [b["text"] for b in blocks] == ["Hello everyone out there.", "Welcome back. Sit down."]
    assert [b["zh"] for b in blocks] == ["大家好。", "欢迎回来。"]
    assert blocks[0]["start"] == 0.0 and blocks[0]["end"] == 5.0    # end=下一窗口起点
    assert blocks[1]["end"] == 10.0                                  # 末块用 cue 末端


def test_merge_cues_中文继承与语气碎句():
    from ytpodcast.build import merge_cues
    cues = [
        (0.0, 2.0, "Yeah."),                          # 语气碎句并给下一句
        (2.0, 8.0, "It works.", "管用。"),
        (8.0, 12.0, "Hello there my friend.", "你好,朋友。"),
    ]
    blocks = merge_cues(cues)
    assert [b["text"] for b in blocks] == ["Yeah. It works.", "Hello there my friend."]
    assert [b["zh"] for b in blocks] == ["管用。", "你好,朋友。"]


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


def test_merge_cues_超长强制断():
    """滚动去重已在 parse_vtt 完成;merge 只管无标点超长强断。"""
    from ytpodcast.build import merge_cues
    cues = [(i * 5.0, i * 5.0 + 5, t)
            for i, t in enumerate(["w0 w1 w2 w3", "w4", "w5", "w6 w7", "w8", "w9"])]
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


def test_split_align_blocks_空行切分容忍多空行():
    from ytpodcast.align_zh import split_align_blocks
    assert split_align_blocks("甲\n\n乙\n\n\n\n丙\n") == ["甲", "乙", "丙"]
    assert split_align_blocks("") == []


def test_parse_numbered_segments_编号对齐与缺号():
    from ytpodcast.align_zh import parse_numbered_segments
    out = "[001] 甲\n\n[002] 乙\n\n[004] 丁\n\n[005] 多行\n第二行\n"
    assert parse_numbered_segments(out) == {
        1: "甲", 2: "乙", 4: "丁", 5: "多行\n第二行"}


def test_build_md_注入中文():
    from ytpodcast.build import build_md
    blocks = [
        {"start": 4.0, "end": 5.0, "text": "Hello world."},
        {"start": 6.0, "end": 7.0, "text": "Good night."},
    ]
    md = build_md("EP01 - T", "EP01 - T.mp3", blocks, zh=["你好,世界。", "晚安。"])
    assert "**Hello world.**\n\n你好,世界。" in md
    assert "**Good night.**\n\n晚安。" in md
    assert "欧路精翻" in md


def test_build_md_部分中文与占位符():
    from ytpodcast.build import build_md
    blocks = [
        {"start": 4.0, "end": 5.0, "text": "Hello world."},
        {"start": 6.0, "end": 7.0, "text": "Good night."},
    ]
    md = build_md("EP01 - T", "EP01 - T.mp3", blocks, zh=["你好,世界。", "·"])  # · = 无译文占位
    assert "**Hello world.**\n\n你好,世界。" in md
    assert "**Good night.**\n\n·" not in md          # 占位符不渲染
    assert "欧路精翻(部分 1/2)" in md


# ---- lr_xlsx:LR(Language Reactor)导出 xlsx → 翻译/EPxx-zh.cues.txt ----

def test_norm_en_小写去标点压空白():
    from ytpodcast.lr_xlsx import norm_en
    assert norm_en("Hello, World! It's fine.") == "hello world its fine"


def test_match_episode_按内容指纹命中():
    from ytpodcast.lr_xlsx import match_episode
    eps = {
        "EP11": "welcome back to the english leap podcast hey learners "
                "today we talk about daily life in english",
        "EP12": "the power of not reacting keep your calm",
    }
    rows_en = ["Welcome back to the English Leap Podcast.",
               "Hey learners, today we talk about daily life in english."]
    assert match_episode(rows_en, eps) == "EP11"


def test_match_episode_无关内容返回None():
    from ytpodcast.lr_xlsx import match_episode
    eps = {"EP11": "welcome back to the english leap podcast hey learners"}
    rows_en = ["Cooking pasta with olive oil and garlic tonight for dinner.",
               "The recipe needs basil and parmesan cheese too."]
    assert match_episode(rows_en, eps) is None


def test_match_episode_通用英文不误报集():
    """真实失效模式:字符二元组对任何英文都有 ~0.7 召回——BBC 等无关转写被误配。
    词 4-gram 中段指纹:通用英文对本系列任何集都应接近 0 分。"""
    from ytpodcast.lr_xlsx import match_episode
    boiler = ("welcome back to the english leap podcast from speak english with class "
              "hey english learners welcome back to your cozy place to learn easy english ")
    eps = {
        "EP11": boiler + ("today we talk about daily life routines in english "
                          "my morning starts with coffee and a short walk outside " * 12).strip(),
        "EP12": boiler + ("the power of not reacting keeps your mind calm and steady "
                          "when people push your buttons just breathe and let it go " * 12).strip(),
    }
    rows_en = [("this bbc podcast is supported by ads outside the uk we have lots more "
                "to help you make sense of the news download the app"),
               ("our story begins in a small village where the old baker wakes before dawn "
                "to light the oven and knead the dough for the morning bread")]
    assert match_episode(rows_en, eps) is None


def test_match_episode_中段内容区分同开头集():
    """各集开场白相同:指纹取中段词 4-gram,命中正确集而非同开头的邻居。"""
    from ytpodcast.lr_xlsx import match_episode
    boiler = ("welcome back to the english leap podcast hey english learners "
              "this is your cozy place to learn easy english through real conversations ")
    eps = {
        "EP11": boiler + "today we talk about daily life routines in english " * 8,
        "EP12": boiler + "the power of not reacting keeps your mind calm and steady " * 8,
    }
    rows_en = [boiler, "Today we talk about daily life routines in English."]
    assert match_episode(rows_en, eps) == "EP11"


def test_match_episode_词序打乱不算同一集():
    """字符二元组只看字母搭配不看词序——同词表乱序的"通用英文"照样高分(真实事故:
    BBC 转写 0.79 误配 EP18);词 4-gram 指纹必须看语序,乱序不认。"""
    from ytpodcast.lr_xlsx import match_episode
    text = ("today we talk about daily life routines in english and how to describe "
            "your morning with simple words that people really use in conversation")
    shuffled = " ".join(reversed(text.split()))
    assert match_episode([shuffled], {"EP11": text}) is None


def test_clean_en_line_LR标记剥离():
    """LR 英文列保留 >> / [music] 原始标记(vtt 解析层会剥,LR 不会),指纹前先剥掉。"""
    from ytpodcast.lr_xlsx import clean_en_line
    assert clean_en_line("Podcast >> from Speak English with Claus. [music]") \
        == "Podcast from Speak English with Claus."
    assert clean_en_line("  keep  inner  spaces  ") == "keep inner spaces"


def test_match_episode_绝对分不高但断层领先也命中():
    """真实事故:389969→EP06 绝对分仅 0.78(LR 与 vtt 词形差异),阈值 0.8 差一步;
    但对邻集断层领先(第二名 0.04)——够高且 ≥2 倍第二名也应命中。"""
    from ytpodcast.lr_xlsx import match_episode
    hit = " ".join(f"morning routine step {i} of my day" for i in range(15))   # 全在 EP11
    noise = " ".join(f"xylophone quizz v{i}" for i in range(8))                # 谁都不在
    eps = {"EP11": hit, "EP12": "the power of not reacting keeps your mind calm"}
    assert match_episode([hit + " " + noise], eps) == "EP11"
