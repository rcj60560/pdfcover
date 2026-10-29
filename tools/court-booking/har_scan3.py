# booking1.har 分析:重点 wxFieldBuyPlan 列表接口 + order/create 下单内容
import json, sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

HAR = r"D:\Users\luocj\pyProject\ky\tools\tools\court-booking\booking1.har"
with open(HAR, 'r', encoding='utf-8-sig') as f:
    har = json.load(f)

entries = har['log']['entries']
print(f"total entries: {len(entries)}")


def form_of(e):
    """把 postData(params或text)转成 dict"""
    pd = e['request'].get('postData', {})
    if pd.get('params'):
        return {p['name']: p['value'] for p in pd['params']}
    if pd.get('text'):
        try:
            return json.loads(pd['text'])
        except Exception:
            return pd['text'][:200]
    return {}


def resp_text(e):
    return e['response'].get('content', {}).get('text', '')


print("\n=== API 调用序列 ===")
for i, e in enumerate(entries):
    u = e['request']['url']
    if 'api.wesais.com' not in u or e['request']['method'] == 'OPTIONS' or e['response']['status'] == 204:
        continue
    print(f"[{i:02d}] {e['request']['method']} {u.split('api.wesais.com')[1]} -> {e['response']['status']} ({len(resp_text(e))}B)")

print("\n=== wxFieldBuyPlan 请求详情 ===")
for i, e in enumerate(entries):
    u = e['request']['url']
    if 'wxFieldBuyPlan' not in u or e['request']['method'] != 'POST':
        continue
    print(f"\n--- [{i:02d}] POST {u}")
    print(f"  PARAMS: {json.dumps(form_of(e), ensure_ascii=False)}")
    body = resp_text(e)
    print(f"  RESP({len(body)}B): {body[:2600]}")

print("\n=== order/create 下单详情(回答:订了哪天哪块场) ===")
for i, e in enumerate(entries):
    u = e['request']['url']
    if '/shop/order/create' not in u or e['request']['method'] != 'POST':
        continue
    print(f"\n--- [{i:02d}] POST {u}")
    print(f"  PARAMS: {json.dumps(form_of(e), ensure_ascii=False)}")
    body = resp_text(e)
    try:
        d = json.loads(body)
        item = d['data']['list']['item'][0]
        order = d['data']['list']['order']
        print(f"  >>> 场次: {item['sku_info']}")
        print(f"  >>> sku : {item['sku']}  价格: {item['pay_price']}  order_no: {order.get('order_no')}")
    except Exception as ex:
        print(f"  RESP RAW: {body[:1200]} (parse err: {ex})")

print("\n=== order/price 详情(浏览器下单前的预检) ===")
for i, e in enumerate(entries):
    u = e['request']['url']
    if '/shop/order/price' not in u or e['request']['method'] != 'POST':
        continue
    print(f"\n--- [{i:02d}] PARAMS: {json.dumps(form_of(e), ensure_ascii=False)}")
    body = resp_text(e)
    print(f"  RESP({len(body)}B): {body[:1000]}")
