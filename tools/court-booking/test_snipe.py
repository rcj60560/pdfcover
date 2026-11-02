"""snipe.py 纯函数单测:python test_snipe.py(无需pytest)

锁住的三个关键行为:
  next_snipe_day  周四/周五才有周末场可抢;错过当天9点顺延到下一个放场日
  windows         滑窗匹配:最早开始优先、场地按序、同起点长段优先、尾段可延1小时
  expand_hours    整点区间解析(原有)
"""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import snipe  # noqa: E402


def mk_slot(field, t, price="36.00", lock=False):
    return {"sku": f"S-{field}-{t}", "sku_name": f"多功能馆羽毛球--{field}",
            "time_str": t, "is_lock": lock, "lock_status": 206 if lock else 0,
            "is_overdue": False, "price": price}


def mk_matrix(locked, fields=("1#", "2#")):
    """locked: {(field, time)} 不可订集合;其余 9-14 点槽全部可订"""
    slots = {}
    for f in fields:
        for h in range(9, 14):
            t = f"{h:02d}:00--{h + 1:02d}:00"
            slots[(f, t)] = mk_slot(f, t, lock=((f, t) in locked))
    return {"fields": list(fields), "slots": slots}


def hours_of(slots):
    return f"{slots[0]['time_str'][:5]}-{int(slots[-1]['time_str'][:2]) + 1:02d}:00"


# ---------------------------------------------------------------- next_snipe_day

def test_next_snipe_day():
    cases = [
        # (now,                        expect_snipe_day, expect_target, target_week)
        ("2026-10-29 08:00", "2026-10-29", "2026-10-31", "周六"),  # 周四早 → 抢周六
        ("2026-10-29 10:00", "2026-10-30", "2026-11-01", "周日"),  # 周四9点已过 → 明天抢周日
        ("2026-10-30 08:00", "2026-10-30", "2026-11-01", "周日"),  # 周五早 → 抢周日
        ("2026-10-30 10:00", "2026-11-05", "2026-11-07", "周六"),  # 周五9点已过 → 下周四
        ("2026-10-31 08:00", "2026-11-05", "2026-11-07", "周六"),  # 周六 → 下周四
        ("2026-11-01 08:00", "2026-11-05", "2026-11-07", "周六"),  # 周日 → 下周四
        ("2026-11-04 20:00", "2026-11-05", "2026-11-07", "周六"),  # 周三晚 → 明早周四
    ]
    for now_s, day_s, target_s, week in cases:
        now = datetime.strptime(now_s, "%Y-%m-%d %H:%M")
        day, target, wk = snipe.next_snipe_day(now)
        assert day and day.strftime("%Y-%m-%d") == day_s, \
            f"{now_s}: 期望抢场日 {day_s}, 实际 {day}"
        assert target == target_s, f"{now_s}: 期望目标 {target_s}, 实际 {target}"
        assert wk == week, f"{now_s}: 期望 {week}, 实际 {wk}"
    print("[OK] next_snipe_day: 7 个场景全过")


# ---------------------------------------------------------------- windows 滑窗

def test_windows_normal_day():
    """常态:9-11锁死(0元格),11-12/12-13可订 → 最优=1# 11:00-13:00"""
    locked = {(f, t) for f in ("1#", "2#") for t in
              ("09:00--10:00", "10:00--11:00")}
    m = mk_matrix(locked)
    got = list(snipe.windows("09:00-12:00", m))
    first = got[0]
    assert first[0] == "1#" and hours_of(first[1]) == "11:00-13:00", \
        f"常态最优应为 1# 11:00-13:00, 实际 {first[0]} {hours_of(first[1])}"
    assert ("2#", "11:00-13:00") in [(f, hours_of(s)) for f, s, _ in got], \
        "2# 11:00-13:00 也应是候选"
    print("[OK] windows: 常态(9-11锁)→ 1# 11:00-13:00 优先")


def test_windows_earliest_start_wins():
    """最早开始优先:1# 只剩 12-13,2# 有 11-13 → 选 2# 11-13 而非 1# 12-13"""
    locked = {("1#", "09:00--10:00"), ("1#", "10:00--11:00"), ("1#", "11:00--12:00"),
              ("2#", "09:00--10:00"), ("2#", "10:00--11:00")}
    m = mk_matrix(locked)
    field, slots, _ = next(snipe.windows("09:00-12:00", m))
    assert field == "2#" and hours_of(slots) == "11:00-13:00", \
        f"应为 2# 11:00-13:00, 实际 {field} {hours_of(slots)}"
    print("[OK] windows: 最早开始优先于场地序")


def test_windows_free_slots_open():
    """若 9-10 真有窗口(取证发现):最早可订段从 9 点起;10-11锁 → 只抢 9-10"""
    locked = {("1#", "10:00--11:00"), ("2#", "10:00--11:00"),
              ("2#", "09:00--10:00")}
    m = mk_matrix(locked)
    field, slots, _ = next(snipe.windows("09:00-12:00", m))
    assert field == "1#" and hours_of(slots) == "09:00-10:00", \
        f"应为 1# 09:00-10:00, 实际 {field} {hours_of(slots)}"
    print("[OK] windows: 0元格若有窗口,最早段生效")


def test_windows_all_locked():
    m = mk_matrix({(f, t) for f in ("1#", "2#") for t in
                   [f"{h:02d}:00--{h + 1:02d}:00" for h in range(9, 14)]})
    assert list(snipe.windows("09:00-12:00", m)) == [], "全锁应无候选"
    print("[OK] windows: 全锁返回空")


# ---------------------------------------------------------------- 0元格=内部圈场
# 2026-11-02 周三实战实锤:工作日白天9-14也是0元格(15点起36元);放场首帧 is_lock=false
# 是假窗口,下单28连拒(服务端message为空),数分钟后转锁。bookable 必须排除0元格,
# 否则滑窗在必败格上锚定,耗尽时间窗(当日事故根因)。

def test_bookable_zero_price_fake_window():
    """0元格即使 is_lock=false/lock_status=0(假窗口)也不可订"""
    s = mk_slot("1#", "09:00--10:00", price="0.00", lock=False)
    assert snipe.Wesais.bookable(s) is False, "0元假窗口必须判不可订"
    assert snipe.Wesais.bookable(mk_slot("1#", "15:00--16:00")) is True
    print("[OK] bookable: 0元假窗口拒,有价格可订")


def test_windows_zero_fake_window_anchors_paid():
    """9点格是0元假窗、11点起有价 → 绝不在9点锚定,首选 11:00-13:00(当日事故场景)"""
    slots = {}
    for f in ("1#", "2#"):
        for h in range(9, 14):
            t = f"{h:02d}:00--{h + 1:02d}:00"
            fake = h <= 10  # 9-10点 = 0元假窗(未锁但0元);11点起有价可订
            slots[(f, t)] = mk_slot(f, t, price="0.00" if fake else "36.00")
    m = {"fields": ["1#", "2#"], "slots": slots}
    got = list(snipe.windows("09:00-12:00", m))
    assert got, "11点起有价,应有候选"
    first_f, first_slots, _ = got[0]
    assert hours_of(first_slots) == "11:00-13:00", \
        f"应锚定11点,实际 {first_f} {hours_of(first_slots)}"
    print("[OK] windows: 0元假窗跳过,锚定首个有价段")


def test_windows_weekday_morning_all_free_price():
    """工作日白天全0元(9-14圈场)→ 9-12 窗口内无任何候选(想抢得改15点后窗口)"""
    slots = {}
    for f in ("1#", "2#"):
        for h in range(9, 14):
            t = f"{h:02d}:00--{h + 1:02d}:00"
            slots[(f, t)] = mk_slot(f, t, price="0.00")
    m = {"fields": ["1#", "2#"], "slots": slots}
    assert list(snipe.windows("09:00-12:00", m)) == [], "全0元应无候选"
    print("[OK] windows: 工作日白天全0元 → 9-12窗口为空")


def test_windows_field_pref():
    """指定场地偏好:只扫 2#"""
    locked = {("1#", "09:00--10:00"), ("1#", "10:00--11:00"),
              ("2#", "09:00--10:00"), ("2#", "10:00--11:00")}
    m = mk_matrix(locked)
    field, slots, _ = next(snipe.windows("09:00-12:00", m, fields=["2#"]))
    assert field == "2#", "指定 fields 只扫 2#"
    print("[OK] windows: 场地偏好生效")


# ---------------------------------------------------------------- expand_hours

def test_expand_hours():
    assert snipe.expand_hours("19:00-21:00") == ["19:00--20:00", "20:00--21:00"]
    try:
        snipe.expand_hours("19:30-21:00")
        raise AssertionError("非整点应抛 ValueError")
    except ValueError:
        pass
    print("[OK] expand_hours: 原有行为不变")


if __name__ == "__main__":
    test_next_snipe_day()
    test_windows_normal_day()
    test_windows_earliest_start_wins()
    test_windows_free_slots_open()
    test_windows_all_locked()
    test_windows_field_pref()
    test_bookable_zero_price_fake_window()
    test_windows_zero_fake_window_anchors_paid()
    test_windows_weekday_morning_all_free_price()
    test_expand_hours()
    print("\n全部通过 ✓")
