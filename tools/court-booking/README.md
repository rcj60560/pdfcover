# 订场秒抢（court-booking）

球馆订场小程序（微赛 wesais SaaS）自动抢场工具。每天 9 点场馆放"今天+2天"的场地，
本工具在放场瞬间自动查场 + 下单锁场，人在 6 分钟内去小程序付款即可。
**纯本地工具，不部署线上服务器。**

## 入口（两个，随便用）

| 入口 | 说明 |
|---|---|
| **双击 `run_web.bat`** | 网页版（推荐）：自动开浏览器 → 配偏好/看矩阵/点"开始抢" |
| 工具箱面板 | 刷新面板自动出现（tool.toml 已挂 8900 端口） |
| `run_snipe.bat` / `python snipe.py snipe` | 命令行版，网页版的备份通道 |

## 快速使用（网页版）

```bash
pip install requests flask    # 依赖
双击 run_web.bat              # → http://127.0.0.1:8900
```

页面流程：①贴 token 点检测 → ②填日期+偏好(时段+场地优先级,可多条排序) →
③刷新矩阵预演 → ④点"开始抢"（自动等到 9 点） → 全屏变绿+响铃 → 6 分钟内小程序付款。

首次使用：复制 `config.example.json` 为 `config.json`（场馆 ID 已配好，贴 token 即可）。

## token 更新（每次实战前做一次，2分钟）

1. PC 微信打开球馆小程序，Fiddler 抓包
2. 随便点一条 `api.wesais.com` 请求 → Request Headers → 复制 `Authorization` 整串
3. 粘贴到 `config.json` 的 `token` 字段
4. `python snipe.py check` 确认 token 有效

> token 有效期未测出（JWT 无 exp 字段），保险起见每次抢之前换新的。
> config.json 已 gitignore，不会误提交。

## mission 配置说明

```json
"mission": {
  "date": "2026-11-01",        // 要抢的日期(它会在某个早上9点被放出来)
  "wants": [                    // 偏好从上到下,第一个抢到的生效
    {"hours": "09:00-12:00", "fields": ["any"]},   // 3小时连续,任意场地
    {"hours": "19:00-21:00", "fields": ["3#", "any"]}  // 2小时,3#优先
  ]
}
```

- `hours` 只支持整点区间，连续多小时要求**同一块场地**连续时段
- `fields` 按顺序偏好；`"any"` = 任意场地兜底；界面只显示 1#-5#，
  数据里共 12 块场（6#-12# 大概率不对外，脚本只认"可订"标记，不影响）
- 日期关系：**周日的场 = 周五早上9点放**，以此类推（今天+2天）

## 接口原理（抓包逆向自 booking1.har）

| 接口 | 作用 |
|---|---|
| `POST /field/wxFieldBuyPlan/getDateList` | 探测放场：新日期出现=9点放场了 |
| `POST /field/wxFieldBuyPlan/getList` | 12场×13槽矩阵，含 sku/价格/is_lock |
| `POST /shop/order/create` | 下单锁场（表单POST，无签名无风控头） |
| `POST /field/businessBase/getNowTimeStamp` | 服务器时间，用于对表 |

可订判定：`is_lock==false && lock_status==0 && is_overdue==false`（价格 0 的槽
也算可订，0 元单的支付流程抢到后自然揭晓）。鉴权：`Authorization` 头带 JWT。

轮询克制：放场前 5 秒起 0.35s/次×30s，之后降为 1s/次，总时长最多 5 分钟，
抢到即停。个人自用工具，别改参数去轰服务器。

## 试验下单（验证连续多时段格式用）

```bash
python snipe.py test-order 2026-10-31 19 2 4#,5#,any   # 周六19点起2小时,4#/5#优先
```

真实下一单（6 分钟不付款自动取消，零成本）。**连场格式已实证**（2026-10-29
小号测试：`sku_slice` 逗号拼接两个 sku → 一单两小时 ¥120），此命令留作
以后验证新场景用。

## 目录内其他文件

- `har_scan*.py` —— 抓包分析脚本（逆向接口时用的，留作参考）
- `booking*.har` —— 原始抓包（已 gitignore，含 token 勿外传）
