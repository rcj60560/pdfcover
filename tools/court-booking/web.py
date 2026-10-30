"""court-booking 网页版 —— 纯抢场(极简)。

python web.py  →  http://127.0.0.1:8900
定位:只做小程序做不了的事——9 点放场瞬间的盲抢。看场/付款用小程序。
多 token 独立抢(各抢各的,互不干扰,期望各得一块场);滑窗匹配(9-12 实际
可中 11-13,0 元格若有窗口天然覆盖);等待期 token 复验;日志落盘 logs/;
放场后第一份矩阵快照存 evidence/(每战必留证)。
"""
import json
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask, jsonify, render_template, request

sys.path.insert(0, str(Path(__file__).resolve().parent))
import snipe  # noqa: E402

TOOL_DIR = Path(__file__).resolve().parent
LOG_DIR = TOOL_DIR / "logs"
EVID_DIR = TOOL_DIR / "evidence"
for d in (LOG_DIR, EVID_DIR):
    d.mkdir(exist_ok=True)

app = Flask(__name__)

STATE = {"phase": "idle", "log": [], "result": None, "trigger_at": None,
         "offset": 0.0, "alarm": None}
LOCK = threading.Lock()
STOP = threading.Event()
WORKER = None

RECHECK_S = 300  # 等待期间 token 复验间隔


def log(msg):
    with LOCK:
        STATE["log"].append({"t": datetime.now().strftime("%H:%M:%S"), "m": str(msg)})
        del STATE["log"][:-500]
        with (LOG_DIR / f"snipe-{datetime.now():%Y%m%d}.log").open(
                "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%H:%M:%S} {msg}\n")


def load_cfg():
    return json.loads((TOOL_DIR / "config.json").read_text(encoding="utf-8"))


def save_cfg(cfg):
    (TOOL_DIR / "config.json").write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def accounts_of(cfg):
    """配置 → 账号列表 [{name, token, hours, field}]。兼容旧单 token 配置。"""
    accs = cfg.get("accounts")
    if not accs:
        accs = [{"name": "账号1", "token": cfg.get("token", ""),
                 "hours": "09:00-12:00", "field": "any"}]
    return accs


def client_of(cfg, acc):
    return snipe.Wesais({"venue": cfg["venue"], "token": acc["token"]})


def server_now():
    return time.time() + STATE.get("offset", 0.0)


# ---------------------------------------------------------------- 页面

@app.route("/")
def index():
    return render_template("index.html")


# ---------------------------------------------------------------- API

@app.route("/api/health")
def health():
    """体检:各账号 token 活性 + 下一个周末放场目标 + 服务器时间偏差。"""
    cfg = load_cfg()
    out = {"phase": STATE["phase"], "accounts": []}
    for i, acc in enumerate(accounts_of(cfg)):
        st = {"idx": i, "name": acc["name"],
              "ok": False, "head": acc.get("token", "")[:14]}
        try:
            client_of(cfg, acc).date_list()
            if not out.get("server_now"):
                STATE["offset"] = client_of(cfg, acc).server_time() - time.time()
                out["server_now"] = server_now()
            st["ok"] = True
        except Exception as ex:
            st["err"] = str(ex)[:120]
        out["accounts"].append(st)
    day, target, week = snipe.next_snipe_day()
    out["target"] = target
    out["target_week"] = week
    out["target_day"] = day.strftime("%Y-%m-%d") if day else None
    # 未来 8 天可选目标(测试/临时抢非周末场用),附各自动场的放场时刻(=日期-2 的 9点)
    out["days"] = [
        {"date": (datetime.now() + timedelta(days=i)).strftime("%Y-%m-%d"),
         "week": snipe.WEEKS[(datetime.now() + timedelta(days=i)).weekday()]}
        for i in range(1, 9)]
    out["alarm"] = STATE["alarm"]
    return jsonify(out)


@app.route("/api/token", methods=["POST"])
def set_token():
    body = request.get_json()
    idx, token = body.get("idx", 0), (body.get("token") or "").strip()
    if not token.startswith("eyJ"):
        return jsonify(error="token 应该是 eyJ 开头的整串"), 400
    cfg = load_cfg()
    accs = accounts_of(cfg)
    if idx >= len(accs):
        accs.append({"name": f"账号{idx + 1}", "token": "", "hours": "09:00-12:00",
                     "field": "any"})
    accs[idx]["token"] = token
    cfg["accounts"] = accs
    if idx == 0:
        cfg["token"] = token  # 兼容 CLI(snipe.py 用 accounts[0])
    save_cfg(cfg)
    try:
        client_of(cfg, accs[idx]).date_list()
        return jsonify(ok=True)
    except Exception as ex:
        return jsonify(error=f"保存了但校验失败: {str(ex)[:150]}"), 200


@app.route("/api/order", methods=["POST"])
def order_api():
    """手动下单:日期+场地号+整点起止+账号,直接真实下单(不付款6分钟自动取消)。"""
    body = request.get_json()
    date, field = body.get("date"), body.get("field")
    start, end, idx = body.get("start"), body.get("end"), body.get("acc", 0)
    try:
        sh, eh = int(start[:2]), int(end[:2])
    except (TypeError, ValueError):
        return jsonify(error="起止时间应为整点,如 12:00 / 13:00"), 400
    if not (9 <= sh < eh <= 22) or not field:
        return jsonify(error="参数:日期 + 场地(如4#) + 起止整点(9-22)"), 400
    cfg = load_cfg()
    accs = accounts_of(cfg)
    if idx >= len(accs) or not accs[idx].get("token"):
        return jsonify(error=f"账号{idx + 1} 没有可用 token"), 400
    wx = client_of(cfg, accs[idx])
    try:
        if date not in wx.date_list():
            return jsonify(error=f"{date} 不在可订日期里(放场规则:当天+2)"), 200
        m = wx.matrix(date)
        ts = [f"{h:02d}:00--{h + 1:02d}:00" for h in range(sh, eh)]
        slots = [m["slots"].get((field, t)) for t in ts]
        if not all(slots):
            return jsonify(error=f"{field} {start}-{end} 槽位不在矩阵里"), 200
        bad = [t for s, t in zip(slots, ts) if not snipe.Wesais.bookable(s)]
        if bad:
            return jsonify(error=f"{field} 以下时段已不可订: "
                                 f"{','.join(t[:5] for t in bad)}"), 200
        resp = snipe.with_retry(lambda: wx.create_order(
            [s["sku"] for s in slots]), tries=2, what="下单")
    except Exception as ex:
        return jsonify(error=f"请求异常: {str(ex)[:150]}"), 200
    if resp.get("code") == 200:
        try:
            lst = resp["data"]["list"]
            order = {"account": accs[idx]["name"],
                     "order_no": lst["order"]["order_no"],
                     "pay": lst["order"]["pay_price"],
                     "items": [i["sku_info"] for i in lst["item"]]}
            log(f"[手动下单] {date} {field} {start}-{end} "
                f"订单{order['order_no']} ¥{order['pay']}")
            return jsonify(ok=True, result={"orders": [order]})
        except (KeyError, TypeError):
            return jsonify(error=f"响应结构异常: {str(resp)[:200]}"), 200
    return jsonify(error=f"下单失败: {resp.get('message')} (code={resp.get('code')})"), 200


@app.route("/api/snipe", methods=["POST"])
def snipe_api():
    """开抢。body: {date: "auto"|"2026-11-02", fields: ["4#","any",...]}(按账号序)。"""
    global WORKER
    if WORKER and WORKER.is_alive():
        return jsonify(error="已经在抢了,先停止再重来"), 400
    body = request.get_json(silent=True) or {}
    cfg = load_cfg()
    all_accs = accounts_of(cfg)
    fields = body.get("fields") or []
    for i, f in enumerate(fields[:len(all_accs)]):
        all_accs[i]["field"] = f if f in [f"{n}#" for n in range(1, 13)] or f == "any" \
            else "any"
    accs = [a for a in all_accs if a.get("token")]
    if not accs:
        return jsonify(error="一个有效 token 都没有,先贴 token 检测"), 400
    hours = "09:00-12:00"
    # 目标日期:auto=自动推导下一个周末场;指定日期(测试/临时)直接用
    date = body.get("date") or "auto"
    if date == "auto":
        day, date, week = snipe.next_snipe_day()
        if not date:
            return jsonify(error="8 天内没有周末场放场日(周四放周六、周五放周日),"
                                 "页面上选个具体日期再抢"), 400
    else:
        try:
            d = datetime.strptime(date, "%Y-%m-%d")
            day = d - timedelta(days=2)
            week = snipe.WEEKS[d.weekday()]
        except ValueError:
            return jsonify(error=f"日期格式应为 YYYY-MM-DD: {date}"), 400
        if d <= datetime.now():
            return jsonify(error="目标日期须是未来日期(放场=目标日-2 的 9 点)"), 400
    cfg["accounts"] = all_accs
    cfg["mission"] = {"date": date, "wants": [{"hours": hours, "fields": ["any"]}]}
    save_cfg(cfg)
    STOP.clear()
    STATE.update(phase="waiting", log=[], result=None, trigger_at=None, alarm=None)
    log(f"目标: {week} {date}({day:%m-%d} 9点放场) {hours} 滑窗,{len(accs)} 号各抢各的:"
        + ", ".join(f"{a['name']}→{a.get('field', 'any')}" for a in accs))
    WORKER = threading.Thread(target=worker, args=(cfg, date, accs, hours),
                              daemon=True)
    WORKER.start()
    return jsonify(ok=True, date=date, week=week)


@app.route("/api/observe", methods=["POST"])
def observe_api():
    """取证观察:只探测不下单,放场瞬间快照矩阵,回答 9-11 是否放场即锁。"""
    global WORKER
    if WORKER and WORKER.is_alive():
        return jsonify(error="有任务在跑,先停止"), 400
    cfg = load_cfg()
    acc = next((a for a in accounts_of(cfg) if a.get("token")), None)
    if not acc:
        return jsonify(error="没有可用 token"), 400
    STOP.clear()
    STATE.update(phase="observing", log=[], result=None, trigger_at=None, alarm=None)

    def run():
        try:
            snipe.observe(cfg, log=log)
            STATE["result"] = {"observe_done": True}
            STATE["phase"] = "success"
        except SystemExit:
            STATE["phase"] = "failed"
        except Exception as ex:
            log(f"[FAIL] 取证异常: {ex!r}")
            STATE["phase"] = "failed"

    WORKER = threading.Thread(target=run, daemon=True)
    WORKER.start()
    return jsonify(ok=True)


@app.route("/api/stop", methods=["POST"])
def stop_api():
    STOP.set()
    log("[手动停止]")
    return jsonify(ok=True)


@app.route("/api/state")
def state_api():
    """前端 1s 轮询:阶段/日志/结果/倒计时/报警。"""
    return jsonify(phase=STATE["phase"], log=STATE["log"][-80:],
                   result=STATE["result"], trigger_at=STATE["trigger_at"],
                   server_now=server_now(), alarm=STATE["alarm"])


# ---------------------------------------------------------------- 抢场线程

def dump_first_matrix(cfg, date):
    """放场后第一份矩阵快照落盘(每战必留证,顺带回答9-11有无窗口)。"""
    try:
        wx = client_of(cfg, next(a for a in accounts_of(cfg) if a.get("token")))
        m = wx.matrix(date)
        snap = {f"{f}|{t}": {"ok": snipe.Wesais.bookable(s), "p": s["price"]}
                for (f, t), s in m["slots"].items()}
        fp = EVID_DIR / f"{date}-first-matrix.json"
        fp.write_text(json.dumps({"date": date, "ts": time.time(),
                                  "slots": snap}, ensure_ascii=False),
                      encoding="utf-8")
        morning = [k for k in snap if k.split("|")[1].startswith(("09:00", "10:00"))]
        opened = [k for k in morning if snap[k]["ok"]]
        log(f"[取证] 放场首帧矩阵已存 {fp.name};9-11格曾可订 {len(opened)}/{len(morning)}"
            f"{'(有窗口!)' if opened else '(放场即锁)'}")
    except Exception as ex:
        log(f"[取证] 首帧矩阵落盘失败({ex})——不影响抢场")


def worker(cfg, date, accs, hours):
    try:
        clients = {}
        for acc in accs:
            try:
                client_of(cfg, acc).date_list()
                clients[acc["name"]] = client_of(cfg, acc)
                log(f"{acc['name']}: token OK")
            except Exception as ex:
                log(f"{acc['name']}: token 失效({str(ex)[:80]}),该号下场")
        if not clients:
            STATE["alarm"] = "所有 token 失效,换 token 后重新开抢"
            log(f"[FAIL] {STATE['alarm']}")
            return finish("failed")
        wx0 = next(iter(clients.values()))
        sc = cfg.get("snipe", {})
        server = snipe.with_retry(wx0.server_time, what="对时")
        STATE["offset"] = server - time.time()

        if date in wx0.date_list():
            log(f"{date} 已在放场列表,直接进入匹配")
            STATE["phase"] = "matching"
        else:
            STATE["phase"] = "waiting"
            now = datetime.fromtimestamp(server)
            pub_h = sc.get("publish_hour", 9)
            # 放场日 = 目标日期 - 2 天(目标可能是未来的周四放的,不能默认今天)
            pub_day = datetime.strptime(date, "%Y-%m-%d") - timedelta(days=2)
            trig = pub_day.replace(hour=pub_h, minute=0, second=0, microsecond=0)
            if now >= trig:
                fail_msg = f"目标 {date} 未放场且今天 {pub_h}:00 已过——目标推导异常,停止"
                log(f"[FAIL] {fail_msg}")
                return finish("failed")
            STATE["trigger_at"] = server + (trig - now).total_seconds() - 5
            log(f"等到 {trig:%m-%d %H:%M:%S}(服务器时间)开抢,"
                f"约{(STATE['trigger_at'] - server) / 60:.0f}分钟,期间别关页面")
            last_check = time.time()
            while True:  # 到点必退(不用 STOP.wait(0) 当出口,防死循环——今天的教训)
                remain = STATE["trigger_at"] - server_now()
                if remain <= 0:
                    break
                if STOP.wait(min(remain, 30)):
                    return finish("stopped")
                if time.time() - last_check > RECHECK_S:  # 等待期 token 复验
                    last_check = time.time()
                    fresh = accounts_of(load_cfg())  # 重读config:换过token自动生效
                    fails = []
                    for acc in list(accs):
                        name = acc["name"]
                        fa = next((a for a in fresh if a["name"] == name), None)
                        if not fa or not fa.get("token"):
                            continue
                        try:
                            c = client_of({"venue": cfg["venue"]}, fa)
                            c.date_list()
                            clients[name] = c  # 采纳(可能是刚换的新token)
                        except Exception as ex:
                            fails.append(f"{name}({str(ex)[:50]})")
                    if fails:
                        STATE["alarm"] = "token 失效: " + ",".join(fails) \
                                         + " ——贴新token点检测,自动生效"
                        log(f"[ALARM] {STATE['alarm']}")
                    elif STATE["alarm"]:
                        STATE["alarm"] = None
                        log("[OK] token 全部恢复有效")
            if STOP.is_set():
                return finish("stopped")
            STATE["phase"] = "polling"
            log(f"轮询 getDateList 等待 {date} 出现...")
            t0 = server_now()
            n = 0
            while not STOP.is_set():
                n += 1
                try:
                    if date in wx0.date_list():
                        log(f"[!!] {date} 放场!第{n}次探测,"
                            f"耗时{server_now() - t0:.1f}s")
                        break
                except Exception as ex:
                    log(f"探测异常({ex}),继续")
                if server_now() - t0 > sc.get("max_minutes", 5) * 60:
                    log(f"[FAIL] {sc.get('max_minutes', 5)}分钟内未见放场,"
                        f"放弃(放场时间可能变了)")
                    return finish("failed")
                interval = sc.get("fast_interval_ms", 350) / 1000 \
                    if server_now() - t0 < sc.get("fast_seconds", 30) \
                    else sc.get("slow_interval_ms", 1000) / 1000
                STOP.wait(interval)
            if STOP.is_set():
                return finish("stopped")
            STATE["phase"] = "matching"
            dump_first_matrix(cfg, date)

        # 滑窗盲抢:每号独立取最早连续可订段;被拒/被秒换下一个,120s 上限
        t0, done, tried = time.time(), {}, set()
        pending = [a for a in accs if a["name"] in clients]
        while time.time() - t0 < 120 and pending and not STOP.is_set():
            try:
                m = wx0.matrix(date)
            except Exception as ex:
                log(f"矩阵未就绪({ex}),1s后重试")
                STOP.wait(1)
                continue
            for acc in list(pending):
                # 一号一场地:绑定场地只扫该场,"any"=全场地扫最早可订
                pool = [acc["field"]] if acc.get("field", "any") != "any" else None
                for field, slots, hs in snipe.windows(hours, m, fields=pool):
                    skus = tuple(s["sku"] for s in slots)
                    key = (acc["name"], skus)
                    if key in tried:
                        continue
                    tried.add(key)
                    try:
                        resp = snipe.with_retry(
                            lambda: clients[acc["name"]].create_order(list(skus)),
                            tries=2, what="下单")
                    except Exception as ex:
                        log(f"{acc['name']} 请求异常({hs} {field}): {ex}")
                        continue
                    if resp.get("code") == 200:
                        try:
                            lst = resp["data"]["list"]
                            done[acc["name"]] = {
                                "account": acc["name"],
                                "order_no": lst["order"]["order_no"],
                                "pay": lst["order"]["pay_price"],
                                "items": [i["sku_info"] for i in lst["item"]]}
                            log(f"[OK] {acc['name']}: {field} {hs} "
                                f"订单{done[acc['name']]['order_no']} "
                                f"应付¥{done[acc['name']]['pay']}")
                            pending.remove(acc)
                            break
                        except (KeyError, TypeError):
                            log(f"{acc['name']} code=200但结构异常: {str(resp)[:120]}")
                    else:
                        log(f"{acc['name']} 下单失败({hs} {field}): "
                            f"{resp.get('message')},换下一个")
            if pending:
                log("本轮未全成,0.8s后重拉矩阵")
                STOP.wait(0.8)
        if STOP.is_set():
            return finish("stopped" if not done else "success")
        STATE["result"] = {"orders": list(done.values())}
        if done:
            log(f"[OK] 完成:{len(done)}/{len(accs)} 个号抢到,"
                f"{'另一个号没抢到' if pending else '全部得手'}")
            return finish("success")
        log("[FAIL] 2分钟内未抢到(全被占或未开放),日志已存 logs/")
        finish("failed")
    except Exception as ex:
        log(f"[FAIL] 异常: {ex!r}")
        finish("failed")


def finish(phase):
    STATE["phase"] = phase


if __name__ == "__main__":
    print("订场秒抢网页版: http://127.0.0.1:8900")
    app.run(host="127.0.0.1", port=8900, threaded=True)
