"""vocab-review 构建纯逻辑测试。"""
import sys
from pathlib import Path

TOOL = Path(__file__).parents[1] / "tools" / "vocab-review"
sys.path.insert(0, str(TOOL))


def _mini_db(tmp_path):
    import sqlite3
    p = tmp_path / "mini.db"
    con = sqlite3.connect(p)
    con.execute(
        "CREATE TABLE stardict (word TEXT PRIMARY KEY, sw TEXT, phonetic TEXT,"
        " translation TEXT, tag TEXT, bnc TEXT, frq INTEGER, exchange TEXT)")
    con.executemany("INSERT INTO stardict (word, phonetic, translation, tag, frq, exchange) VALUES (?,?,?,?,?,?)", [
        ("run", "/rʌn/", "v. 跑", "zk gk", 100, "i:running/3:runs/d:ran"),
        ("running", "/ˈrʌnɪŋ/", "n. 跑步", "gk", 2000, "0:run/1:i"),
        ("reclaim", "/rɪˈkleɪm/", "vt. 开拓；回收利用", "cet6 ky ielts", 8000, "d:reclaimed"),
    ])
    con.commit(); con.close()
    return p


def test_load_for_tokens_resolves_lemma_and_fields(tmp_path):
    import ecdict
    entries, lemmas = ecdict.load_for_tokens(_mini_db(tmp_path), {"running", "ran", "reclaim", "zzz"})
    assert lemmas["running"] == "run"          # exchange 0:run → 原形
    assert lemmas["ran"] == "ran"              # 无独立词条 → 保持自身
    assert entries["reclaim"]["tag"] == "cet6 ky ielts"
    assert entries["reclaim"]["phon"] == "/rɪˈkleɪm/"     # phon 取自 phonetic 列
    assert entries["reclaim"]["translation"].startswith("vt.")
    assert "zzz" not in entries


MD = """# 测试书 Unit 1｜示例

> 来源: xxx

---

`0:00:01 → 0:00:05`

**Reclamation of old land takes years. And they Running fast!**

---

`0:00:05 → 0:00:08`

**Do you know the word reclaim?**
"""


def test_md_english_lines_and_title():
    import build
    lines = build.md_english_lines(MD)
    assert lines == ["Reclamation of old land takes years. And they Running fast!",
                     "Do you know the word reclaim?"]
    assert build.doc_title(MD) == "测试书 Unit 1｜示例"


def test_tokenize_keeps_alpha_words_only():
    import build
    assert build.tokenize("Reclamation of OLD land, takes 3 years--OK? A I") == \
        ["reclamation", "of", "old", "land", "takes", "years", "ok"]


def test_split_sentences_filters_by_word_count():
    import build
    sents = build.split_sentences(["Reclamation takes years. Yes! Do you know it?"])
    assert sents == ["Reclamation takes years.", "Do you know it?"]  # Yes! 仅1词被滤


def test_classify_by_tags_and_frequency():
    import build
    gk = {"tag": "zk gk", "frq": 300}
    cet6 = {"tag": "cet6 ky ielts", "frq": 8000}
    plain_high = {"tag": "", "frq": 1500}       # 无标签但词频前5000
    plain_low = {"tag": "", "frq": 0}           # 未收录语料 → 丢弃
    assert build.classify(gk) == "known"
    assert build.classify(cet6) == "candidate"
    assert build.classify(plain_high) == "known"
    assert build.classify(plain_low) == "drop"
    assert build.classify(None) == "drop"


def test_pick_sentences_shortest_first_with_source():
    import build
    sents = [("Reclamation of land takes years and costs money.", "书A Unit 1"),
             ("They reclaim it.", "书B Unit 2"),
             ("We can reclaim the plastics from old computers now.", "书B Unit 2")]
    picked = build.pick_sentences({"reclaim", "reclamation"}, sents)
    assert len(picked) == 2
    assert picked[0]["en"] == "We can reclaim the plastics from old computers now."
    assert picked[0]["from"] == "书B Unit 2"


def test_build_end_to_end_with_fixtures(tmp_path):
    import build, ecdict
    src = tmp_path / "docs"; src.mkdir()
    (src / "a.md").write_text(
        "# 书A Unit 1\n\n---\n\n`0:00:01 → 0:00:05`\n\n"
        "**They reclaim the land quickly. Running helps.**\n\n---\n", encoding="utf-8")
    result = build.build(src, _mini_db(tmp_path), level="gk")
    words = {w["w"]: w for w in result["words"]}
    assert "reclaim" in words and words["reclaim"]["def"].startswith("vt.")
    assert words["reclaim"]["sents"][0]["en"] == "They reclaim the land quickly."
    assert words["reclaim"]["tags"] == "cet6 ky ielts"
    assert "run" not in words                      # zk/gk → 已会,不进 words
    assert result["stats"]["total"] >= 4
