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
