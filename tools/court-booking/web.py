"""court-booking 网页版 —— 多账号配偏好/看矩阵/一键抢场。

python web.py  →  http://127.0.0.1:8900
复用 snipe.py 的客户端与匹配逻辑,抢场在后台线程跑,页面轮询日志。
多账号:公益时段每手机号每日限2小时,双号分工(如 A抢9-11 / B抢11-12),
B 自动跟进 A 抢到的场地,合成同场连续时段。
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
app = Flask(__name__)

STATE = {"phase": "idle", "log": [], "result": None, "trigger_at": None, "offset": 0.0}
LOCK = threading.Lock()
STOP = threading.Event()
WORKER = None


def log(msg):
    with LOCK:
        STATE["log"].append({"t": datetime.now().strftime("%H:%M:%S"), "m": str(msg)})
        del STATE["log"][:-500]


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
                 "hours": "09:00-11:00", "field": "any"}]
    return accs


def client_of(cfg, acc):
    return snipe.Wesais({"venue": cfg["venue"], "token": acc["token"]})


def server_now():
    return time.time() + STATE.get("offset", 0.0)


def next_target(dates):
    """目标 = 下一个 9 点放场新出现的日期(当前最远日期+1)。"""
    latest = max(dates)
    t = datetime.strptime(latest, "%Y-%m-%d") + timedelta(days=1)
    weeks = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    return latest, t.strftime("%Y-%m-%d"), weeks[t.weekday()]


# ---------------------------------------------------------------- 页面

@app.route("/")
def index():
    return render_template("index.html")


# ---------------------------------------------------------------- API

@app.route("/api/health")
def health():
    """体检:各账号 token 活性 + 可订日期 + 自动目标 + 服务器时间偏差。"""
    cfg = load_cfg()
    out = {"phase": STATE["phase"], "accounts": []}
    dates = None
    for i, acc in enumerate(accounts_of(cfg)):
        st = {"idx": i, "name": acc["name"],
              "ok": False, "head": acc.get("token", "")[:14]}
        try:
            wx = client_of(cfg, acc)
            ds = wx.date_list()
            if dates is None:
                dates = ds
                STATE["offset"] = wx.server_time() - time.time()
            st["ok"] = True
        except Exception as ex:
            st["err"] = str(ex)[:120]
        out["accounts"].append(st)
    if dates:
        server = server_now()
        latest, target, week = next_target(dates)
        published = datetime.fromtimestamp(server).hour >= \
            cfg.get("snipe", {}).get("publish_hour", 9)
        out.update(ok=True, dates=dates, latest=latest, target=target,
                   target_week=week, published=published,
                   server_now=server, hours=[a["hours"] for a in accounts_of(cfg)])
    else:
        out.update(ok=False)
    return jsonify(out)


@app.route("/api/token", methods=["POST"])
def set_token():
    body = request.get_json()
    idx, token = body.get("idx", 0), (body.get("token") or "").strip()
    if not token.startswith("eyJ"):
        return jsonify(error="token 应该是 eyJ 开头的整串"), 400
    cfg = load_cfg()
    accs = accounts_of(cfg)
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


@app.route("/api/matrix", methods=["POST"])
def matrix_api():
    """拉矩阵 + 按 UI 当前偏好预演(参考用)。"""
    body = request.get_json()
    date, wants = body["date"], body["wants"]
    cfg = load_cfg()
    wx = None
    for acc in accounts_of(cfg):
        if acc.get("token"):
            wx = client_of(cfg, acc)
            break
    if wx is None:
        return jsonify(error="没有可用 token"), 400
    m = wx.matrix(date)
    times = sorted({t for (_, t) in m["slots"]})
    cells = {}
    for (f, t), slot in m["slots"].items():
        if snipe.Wesais.bookable(slot):
            st = "ok"
        elif slot["is_overdue"]:
            st = "over"
        elif slot["price"] == "0.00":
            st = "na"
        else:
            st = "lock"
        cells[f"{f}|{t}"] = {"s": st, "p": slot["price"].rstrip("0").rstrip(".") or "0",
                             "sku": slot["sku"]}
    preview = []
    for want, field, slots in snipe.match_all(wants, m):
        preview.append({"hours": want["hours"], "field": field,
                        "prices": [s["price"] for s in slots],
                        "times": [s["time_str"] for s in slots]})
        if len(preview) >= 5:
            break
    return jsonify(fields=m["fields"], times=times, cells=cells, preview=preview)


@app.route("/api/order", methods=["POST"])
def order_api():
    """手动下单:矩阵里选中的场次,立即真实下单(不付款6分钟自动取消)。"""
    body = request.get_json()
    date, skus = body.get("date"), body.get("skus") or []
    if not skus:
        return jsonify(error="没选场次"), 400
    cfg = load_cfg()
    acc = next((a for a in accounts_of(cfg) if a.get("token")), None)
    if not acc:
        return jsonify(error="没有可用 token"), 400
    try:
        resp = client_of(cfg, acc).create_order(skus)
    except Exception as ex:
        return jsonify(error=f"请求异常: {str(ex)[:150]}"), 200
    if resp.get("code") == 200:
        try:
            lst = resp["data"]["list"]
            result = {"orders": [{"account": acc["name"],
                                  "order_no": lst["order"]["order_no"],
                                  "pay": lst["order"]["pay_price"],
                                  "items": [i["sku_info"] for i in lst["item"]]}]}
            log(f"[手动下单] {date} {len(skus)}个时段 订单"
                f"{result['orders'][0]['order_no']} ¥{result['orders'][0]['pay']}")
            return jsonify(ok=True, result=result)
        except (KeyError, TypeError):
            return jsonify(error=f"响应结构异常: {str(resp)[:200]}"), 200
    return jsonify(error=f"下单失败: {resp.get('message')} (code={resp.get('code')})"), 200


@app.route("/api/snipe", methods=["POST"])
def snipe_api():
    global WORKER
    if WORKER and WORKER.is_alive():
        return jsonify(error="已经在抢了,先停止再重来"), 400
    body = request.get_json()
    acc0 = (body.get("accounts") or [{}])[0]
    cfg = load_cfg()
    accs = accounts_of(cfg)
    accs[0]["hours"] = acc0.get("hours", accs[0]["hours"])
    accs[0]["field"] = acc0.get("field", "any")
    run_accs = [accs[0]]  # UI 单账号;其余账号留在配置里备用(2块场玩法)
    try:
        for a in run_accs:
            snipe.expand_hours(a["hours"])
    except ValueError as ex:
        return jsonify(error=str(ex)), 400
    if not any(a.get("token") for a in run_accs):
        return jsonify(error="一个有效 token 都没有"), 400
    # 目标日期自动推导:下一个 9 点放场新出现的日期
    try:
        probe = client_of(cfg, next(a for a in run_accs if a.get("token")))
        _, date, _ = next_target(probe.date_list())
    except Exception as ex:
        return jsonify(error=f"推导目标日期失败(token?): {str(ex)[:150]}"), 400
    cfg["accounts"] = accs
    cfg["mission"] = {"date": date,
                      "wants": [{"hours": accs[0]["hours"],
                                 "fields": [accs[0]["field"], "any"]
                                 if accs[0]["field"] != "any" else ["any"]}]}
    save_cfg(cfg)
    STOP.clear()
    STATE.update(phase="waiting", log=[], result=None, trigger_at=None)
    WORKER = threading.Thread(target=worker, args=(cfg, date, run_accs), daemon=True)
    WORKER.start()
    return jsonify(ok=True, date=date)


@app.route("/api/stop", methods=["POST"])
def stop_api():
    STOP.set()
    log("[手动停止]")
    return jsonify(ok=True)


@app.route("/api/state")
def state_api():
    """前端 1s 轮询:阶段/日志/结果/倒计时。"""
    return jsonify(phase=STATE["phase"], log=STATE["log"][-80:],
                   result=STATE["result"], trigger_at=STATE["trigger_at"],
                   server_now=server_now())


# ---------------------------------------------------------------- 抢场线程

def worker(cfg, date, accs):
    try:
        clients = {}
        for acc in accs:
            if not acc.get("token"):
                log(f"{acc['name']}: 无 token,跳过")
                continue
            try:
                client_of(cfg, acc).date_list()
                clients[acc["name"]] = client_of(cfg, acc)
                log(f"{acc['name']}: token OK")
            except Exception as ex:
                log(f"{acc['name']}: token 失效({str(ex)[:80]})")
        if not clients:
            log("[FAIL] 没有可用账号")
            return finish("failed")
        wx0 = next(iter(clients.values()))
        sc = cfg.get("snipe", {})
        server = wx0.server_time()
        STATE["offset"] = server - time.time()

        if date in wx0.date_list():
            log(f"{date} 已在放场列表,直接进入匹配")
            STATE["phase"] = "matching"
        else:
            STATE["phase"] = "waiting"
            now = datetime.fromtimestamp(server)
            pub_h = sc.get("publish_hour", 9)
            trig = now.replace(hour=pub_h, minute=0, second=0, microsecond=0)
            if now >= trig:  # 今天放场点已过 → 目标是明天 9 点才出现
                trig += timedelta(days=1)
            STATE["trigger_at"] = server + (trig - now).total_seconds() - 5
            log(f"目标 {date},等到 {trig:%m-%d %H:%M:%S}(服务器时间)开抢,"
                f"约{(STATE['trigger_at'] - server) / 60:.0f}分钟,期间别关页面")
            while not STOP.wait(min(max(STATE["trigger_at"] - server_now(), 0), 30)):
                pass
            if STOP.is_set():
                return finish("stopped")
            STATE["phase"] = "polling"
            log(f"轮询 getDateList 等待 {date} 出现...")
            t0 = server_now()
            n = 0
            while not STOP.is_set():
                n += 1
                if date in wx0.date_list():
                    log(f"[!!] {date} 放场!第{n}次探测,耗时{server_now() - t0:.1f}s")
                    break
                el = server_now() - t0
                if el > sc.get("max_minutes", 5) * 60:
                    log(f"[FAIL] {sc.get('max_minutes', 5)}分钟内未见放场,放弃")
                    return finish("failed")
                interval = sc.get("fast_interval_ms", 350) / 1000 \
                    if el < sc.get("fast_seconds", 30) \
                    else sc.get("slow_interval_ms", 1000) / 1000
                STOP.wait(interval)
            if STOP.is_set():
                return finish("stopped")
            STATE["phase"] = "matching"

        # 匹配下单:逐账号;先成功的场地作为后续账号跟进偏好;
        # 单账号整段被拒时按公益2h规则自动降级只抢前2小时
        t0, done, base_court, covered, tried = time.time(), {}, None, [], set()
        pending = [a for a in accs if a["name"] in clients]

        def parse_h(h):
            a, b = h.split("-")
            return int(a[:2]), int(b[:2])

        while time.time() - t0 < 120 and pending and not STOP.is_set():
            try:
                m = wx0.matrix(date)
            except Exception as ex:
                log(f"矩阵未就绪({ex}),1s后重试")
                STOP.wait(1)
                continue
            for acc in list(pending):
                ha0, hb0 = parse_h(acc["hours"])
                chain = [acc["hours"]]
                if hb0 - ha0 > 2:  # 跨超2小时 → 追加"前2小时"兜底(免费时段上限)
                    chain.append(f"{acc['hours'].split('-')[0]}-{ha0 + 2:02d}:00")
                got = False
                for hours_try in chain:
                    ha, hb = parse_h(hours_try)
                    if any(s <= ha and hb <= e for s, e in covered):
                        log(f"{acc['name']}: {hours_try} 已被前面订单覆盖,跳过")
                        pending.remove(acc)
                        got = True
                        break
                    want = {"hours": hours_try}
                    # 场地偏好:指定场→该场优先;随机→跟进前面的场地(保证同场连打)
                    want["fields"] = [acc["field"], "any"] if acc["field"] != "any" \
                        else ([base_court, "any"] if base_court else ["any"])
                    for _, field, slots in snipe.match_all([want], m):
                        skus = tuple(s["sku"] for s in slots)
                        if (acc["name"], skus) in tried:
                            continue
                        tried.add((acc["name"], skus))
                        try:
                            resp = clients[acc["name"]].create_order(list(skus))
                        except Exception as ex:
                            log(f"{acc['name']} 请求异常({hours_try} {field}): {ex}")
                            continue
                        if resp.get("code") == 200:
                            try:
                                lst = resp["data"]["list"]
                                done[acc["name"]] = {
                                    "account": acc["name"],
                                    "order_no": lst["order"]["order_no"],
                                    "pay": lst["order"]["pay_price"],
                                    "items": [i["sku_info"] for i in lst["item"]],
                                }
                                log(f"[OK] {acc['name']}: {hours_try} {field} "
                                    f"订单{done[acc['name']]['order_no']} "
                                    f"应付¥{done[acc['name']]['pay']}")
                                covered.append((ha, hb))
                                if base_court is None:
                                    base_court = field
                                pending.remove(acc)
                                got = True
                                break
                            except (KeyError, TypeError):
                                log(f"{acc['name']} code=200但结构异常: {str(resp)[:120]}")
                        else:
                            log(f"{acc['name']} 下单失败({hours_try} {field}): "
                                f"{resp.get('message')},换下一个")
                    if got:
                        break
                    if len(chain) > 1 and hours_try == chain[0]:
                        log(f"{acc['name']}: 整段 {chain[0]} 全被拒,"
                            f"按公益2h规则降级试 {chain[1]}")
            if pending:
                log("本轮未全成,0.8s后重拉矩阵")
                STOP.wait(0.8)
        if STOP.is_set():
            return finish("stopped" if not done else "success")
        STATE["result"] = {"orders": list(done.values())}
        if done:
            log(f"[OK] 完成:{len(done)}/{len(pending) + len(done)} 个账号抢到")
            return finish("success")
        log("[FAIL] 2分钟内未抢到(全被占或未开放)")
        finish("failed")
    except Exception as ex:
        log(f"[FAIL] 异常: {ex!r}")
        finish("failed")


def finish(phase):
    STATE["phase"] = phase


if __name__ == "__main__":
    print("订场秒抢网页版: http://127.0.0.1:8900")
    app.run(host="127.0.0.1", port=8900, threaded=True)
