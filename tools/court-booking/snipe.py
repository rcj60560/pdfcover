"""球场秒抢 —— 微赛(wesais)场馆预订自动下单工具(个人自用)。

接口三件套(由 Fiddler 抓包逆向,见 README):
  /field/wxFieldBuyPlan/getDateList   探测放场:每天9点发布 今天+2天 的日期
  /field/wxFieldBuyPlan/getList       场地矩阵:12场 x 13槽,含 sku/价格/is_lock
  /shop/order/create                  下单(锁场约6分钟,超时不付自动取消)

用法:
  python snipe.py check                        体检:验token/对服务器时间/打印场地矩阵
  python snipe.py snipe                        正式抢:等到9点放场自动轮询下单
  python snipe.py test-order 2026-10-30 15 2   试验下单:指定日期/起始时/小时数(不付款,6分钟自动取消)
"""
import json
import sys
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows控制台中文/符号防乱码

TOOL_DIR = Path(__file__).resolve().parent
API = "https://api.wesais.com"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/144.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) "
      "NetType/WIFI MiniProgramEnv/Windows WindowsWechat/WMPF "
      "WindowsWechat(0x63090a13) UnifiedPCWindowsWechat(0xf2541f0d) "
      "XWEB/25799 miniProgram/wxd1be887d68ac1b15")


# ---------------------------------------------------------------- 客户端

class Wesais:
    def __init__(self, cfg):
        venue = cfg["venue"]
        self.business_id = str(venue["business_id"])
        self.stadium_id = str(venue["stadium_id"])
        self.ground_id = str(venue["ground_id"])
        self.s = requests.Session()
        self.s.trust_env = False  # 直连,不走系统代理(开着Fiddler/VPN时也不受影响)
        self.s.headers.update({
            "Authorization": cfg["token"],
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/x-www-form-urlencoded",
            "AuthRouter": "",
            "Origin": "https://xcx.wesais.com",
            "Referer": "https://xcx.wesais.com/",
        })

    def post(self, path, timeout=10, **params):
        params.setdefault("business_id", self.business_id)
        params.setdefault("stadium_id", self.stadium_id)
        params["request_id"] = uuid.uuid4().hex
        r = self.s.post(API + path, data={k: str(v) for k, v in params.items()},
                        timeout=timeout)
        r.raise_for_status()
        return r.json()

    # ---- 各业务接口 ----

    def server_time(self):
        """服务器时间(epoch秒) —— 用于对表,不依赖本机时钟。"""
        d = self.post("/field/businessBase/getNowTimeStamp")["data"]
        for v in d.values():
            if isinstance(v, (int, float)) and v > 1_600_000_000:
                return float(v)
        raise RuntimeError(f"getNowTimeStamp 响应不认识: {d}")

    def date_list(self):
        d = self.post("/field/wxFieldBuyPlan/getDateList")
        if d.get("code") != 200:
            raise RuntimeError(f"getDateList 失败: {d.get('message')} (code={d.get('code')})")
        return [x["date"] for x in d["data"]["list"]]

    def matrix(self, date):
        """场地矩阵 → {'fields': ['1#',...], 'slots': {(field, time_str): slot}}"""
        d = self.post("/field/wxFieldBuyPlan/getList", ground_id=self.ground_id,
                      time_date=date)
        if d.get("code") != 200:
            raise RuntimeError(f"getList 失败: {d.get('message')} (code={d.get('code')})")
        data = d["data"]
        fields = [f["name"] for f in data["fieldStr"]]
        slots = {}
        for g in data["skuList"]:
            for row in g:
                for slot in row:
                    # sku_name 形如 "多功能馆羽毛球--3#"
                    name = slot["sku_name"].rsplit("--", 1)[-1]
                    slots[(name, slot["time_str"])] = slot
        return {"fields": fields, "slots": slots}

    def create_order(self, skus):
        """下单。skus: sku字符串列表(连续多时段同场)。成功返回订单dict。"""
        d = self.post("/shop/order/create", timeout=6,
                      sys_id=13,
                      sku_slice=",".join(f"{sku}:1" for sku in skus),
                      business_type=1301,
                      order_from=2,
                      handle_info='{"date_str":""}',
                      sales_id=0)
        return d

    # ---- 判定辅助 ----

    @staticmethod
    def bookable(slot):
        return (not slot["is_lock"] and slot["lock_status"] == 0
                and not slot["is_overdue"])


# ---------------------------------------------------------------- 目标匹配

def expand_hours(hours):
    """'19:00-21:00' → ['19:00--20:00', '20:00--21:00'](整点小时槽)"""
    a, b = hours.split("-")
    (ha, ma), (hb, mb) = a.split(":"), b.split(":")
    if ma != "00" or mb != "00" or not (0 <= int(ha) < int(hb) <= 24):
        raise ValueError(f"hours 只支持整点递增区间,如 19:00-21:00 : {hours}")
    return [f"{h:02d}:00--{h + 1:02d}:00" for h in range(int(ha), int(hb))]


def candidates(want, matrix):
    """按偏好顺序产出 (场地, [槽位...]) 生成器,只产出全部槽可订的。"""
    fields = want.get("fields") or ["any"]
    if "any" in fields:
        pool = [f for f in fields if f != "any"] + matrix["fields"]  # 指定场优先,any兜底
    else:
        pool = fields
    unknown = [f for f in pool if f != "any" and f not in matrix["fields"]]
    if unknown:
        print(f"  [warn] 配置里的场地 {unknown} 不在场地列表 {matrix['fields']},已忽略")
    pool = [f for f in dict.fromkeys(pool) if f in matrix["fields"]]
    for field in pool:
        slots = [matrix["slots"].get((field, t)) for t in expand_hours(want["hours"])]
        if all(s is not None and Wesais.bookable(s) for s in slots):
            yield field, slots


def match_all(wants, matrix):
    for want in wants:
        for field, slots in candidates(want, matrix):
            yield want, field, slots


# ---------------------------------------------------------------- 输出辅助

def print_matrix(matrix, date):
    fields = matrix["fields"]
    print(f"\n=== {date} 场地矩阵 ({len(fields)}场x{13}槽) ===")
    print("  [√36]=可订(价格)  x=已订/锁  .=未开放")
    head = "          " + "".join(f"{f:>7s}" for f in fields)
    print(head)
    times = sorted({t for (_, t) in matrix["slots"]})
    for t in times:
        cells = []
        for f in fields:
            slot = matrix["slots"].get((f, t))
            if slot is None:
                cells.append("      ?")
            elif Wesais.bookable(slot):
                p = slot["price"].rstrip("0").rstrip(".")
                cells.append(f"     √{p or '0'}")
            elif slot["is_overdue"]:
                cells.append("      过")
            elif slot["price"] == "0.00":
                cells.append("      .")
            else:
                cells.append("      x")
        print(f"  {t}  " + "".join(cells))


def announce_success(order_no, items, pay):
    print()
    print("=" * 62)
    print("  【抢到了!】快去小程序付款(6分钟内,超时自动取消)")
    print(f"  订单号: {order_no}   应付: ¥{pay}")
    for it in items:
        print(f"  · {it['sku_info']}  ¥{it['pay_price']}")
    print("=" * 62)
    try:
        import winsound
        for _ in range(12):
            winsound.Beep(1318, 220)
            time.sleep(0.06)
    except Exception:
        pass


def fail(msg):
    print(f"[FAIL] {msg}")
    sys.exit(1)


# ---------------------------------------------------------------- 三个命令

def load_config():
    cfg_path = TOOL_DIR / "config.json"
    if not cfg_path.exists():
        fail("没有 config.json —— 复制 config.example.json 为 config.json,"
             "把 Fiddler 抓的 Authorization 贴进 token 字段(见 README)")
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    if not cfg.get("token") and cfg.get("accounts"):  # 多账号配置 → CLI 用 A 账号
        cfg["token"] = cfg["accounts"][0]["token"]
    return cfg


def cmd_check(cfg):
    wx = Wesais(cfg)
    # 1. token 活性
    dates = wx.date_list()
    print(f"[OK] token 有效,可订日期: {dates}")
    # 2. 对时
    server = wx.server_time()
    offset = server - time.time()
    print(f"[OK] 服务器时间 {datetime.fromtimestamp(server):%H:%M:%S}"
          f" (本机偏差 {offset:+.2f}s)")
    # 3. 目标日期矩阵
    date = cfg["mission"]["date"]
    if date in dates:
        m = wx.matrix(date)
        print_matrix(m, date)
        got = list(match_all(cfg["mission"]["wants"], m))
        print(f"\n当前偏好下可立即下单的组合: {len(got)} 个")
        for want, field, slots in got[:5]:
            print(f"  · {want['hours']} {field} "
                  f"(¥{'/'.join(s['price'] for s in slots)})")
    else:
        print(f"[..] 目标日期 {date} 还未放场(放场后重跑可见矩阵)")


def cmd_snipe(cfg):
    wx = Wesais(cfg)
    date = cfg["mission"]["date"]
    sc = cfg.get("snipe", {})
    publish_h = sc.get("publish_hour", 9)
    fast_ms = sc.get("fast_interval_ms", 350)
    fast_s = sc.get("fast_seconds", 30)
    slow_ms = sc.get("slow_interval_ms", 1000)
    max_min = sc.get("max_minutes", 5)

    print(f"[1/3] 验 token...", end=" ")
    wx.date_list()
    print("OK")

    if date in wx.date_list():
        print(f"[!] {date} 已在放场列表里(可能已放场),直接进入匹配")
    else:
        # 等到 8:59:55(按服务器时间)再开始密集轮询;过了放场点就直接开轮
        server = wx.server_time()
        offset = server - time.time()
        now = datetime.fromtimestamp(server)
        trig = now.replace(hour=publish_h, minute=0, second=0, microsecond=0)
        if now < trig:
            target_epoch = server + (trig - now).total_seconds() - 5
            print(f"[2/3] 服务器时间 {now:%H:%M:%S},等到 {publish_h - 1}:59:55 开始轮询"
                  f"(约{(trig - now).total_seconds() / 60:.0f}分钟,期间别关窗口)")
            while True:
                remain = target_epoch - (time.time() + offset)
                if remain <= 0:
                    break
                time.sleep(min(remain, 30))
        # 密集轮询等放场
        t0 = time.time() + offset
        print(f"[2/3] 轮询 getDateList 等待 {date} 出现...", flush=True)
        n = 0
        while True:
            n += 1
            if date in wx.date_list():
                print(f"\n[!!] {date} 放场了!第{n}次探测,耗时{time.time()+offset-t0:.1f}s")
                break
            el = time.time() + offset - t0
            if el > fast_s:
                if el > max_min * 60:
                    fail(f"{max_min}分钟内未见 {date} 放场,放弃(确认放场时间是否变了)")
                time.sleep(slow_ms / 1000)
            else:
                time.sleep(fast_ms / 1000)
                print(".", end="", flush=True)

    # 放场后:拉矩阵按偏好下单(矩阵未就绪/全被抢则重拉,最多2分钟)
    print("[3/3] 拉取场地矩阵并下单...", flush=True)
    t0 = time.time()
    tried = set()
    while time.time() - t0 < 120:
        try:
            m = wx.matrix(date)
        except Exception as ex:
            print(f"  矩阵未就绪({ex}),1s后重试")
            time.sleep(1)
            continue
        for want, field, slots in match_all(cfg["mission"]["wants"], m):
            skus = tuple(s["sku"] for s in slots)
            if skus in tried:
                continue
            tried.add(skus)
            resp = wx.create_order(list(skus))
            if resp.get("code") == 200:
                try:
                    lst = resp["data"]["list"]
                    announce_success(lst["order"]["order_no"], lst["item"],
                                     lst["order"]["pay_price"])
                    return
                except (KeyError, TypeError):
                    print(f"  code=200但结构异常,按失败处理: {str(resp)[:200]}")
            else:
                print(f"  下单失败({want['hours']} {field}): "
                      f"{resp.get('message')} (code={resp.get('code')}),换下一个")
        print("  本轮无可订组合,0.8s后重拉矩阵...", flush=True)
        time.sleep(0.8)
    fail("2分钟内未抢到(时段全被占或未开放),明早再战或调低偏好")


def cmd_test_order(cfg, date, start_hour, n_hours, fields="any"):
    """试验性下单:验证连续多时段的下单格式。不付款,6分钟自动取消。"""
    wx = Wesais(cfg)
    dates = wx.date_list()
    if date not in dates:
        fail(f"{date} 不在可订日期 {dates} 里")
    m = wx.matrix(date)
    hours = f"{start_hour:02d}:00-{start_hour + n_hours:02d}:00"
    for field, slots in candidates({"hours": hours, "fields": fields.split(",")}, m):
        skus = [s["sku"] for s in slots]
        print(f"选定: {date} {field} {hours} sku={skus}")
        resp = wx.create_order(skus)
        print(f"响应: {json.dumps(resp, ensure_ascii=False)[:800]}")
        if resp.get("code") == 200:
            lst = resp["data"]["list"]
            announce_success(lst["order"]["order_no"], lst["item"],
                             lst["order"]["pay_price"])
            print(">>> 这是试验单!去小程序取消它(或等6分钟自动取消)")
        return
    fail("没找到连续可订的场地做试验")


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return
    cmd = sys.argv[1]
    if cmd == "test-order":
        if len(sys.argv) not in (5, 6):
            fail("用法: python snipe.py test-order <日期> <起始时> <小时数> [场地偏好]\n"
                 "例:   python snipe.py test-order 2026-10-31 19 2 4#,5#,any")
        fields = sys.argv[5] if len(sys.argv) == 6 else "any"
        cmd_test_order(load_config(), sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), fields)
        return
    cfg = load_config()
    {"check": cmd_check, "snipe": cmd_snipe}[cmd](cfg)


if __name__ == "__main__":
    main()
