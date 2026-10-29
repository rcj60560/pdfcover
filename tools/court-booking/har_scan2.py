# 深挖:order/create 的完整请求结构 + 检查所有请求体是否缺失
import json, sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

HAR = r"C:\Users\luocj\Documents\booking.har"
with open(HAR, 'r', encoding='utf-8-sig') as f:
    har = json.load(f)

entries = har['log']['entries']

# 1. 哪些请求有 postData?
has_body = [(i, e['request']['method'], e['request']['url'].split('?')[0])
            for i, e in enumerate(entries)
            if e['request'].get('postData')]
print(f"entries with postData: {len(has_body)}")
for i, m, u in has_body:
    print(f"  [{i:02d}] {m} {u}")

# 2. order/create 完整请求 JSON
for i, e in enumerate(entries):
    if '/shop/order/create' in e['request']['url'] and e['request']['method'] == 'POST':
        print(f"\n=== entry [{i}] order/create REQUEST RAW ===")
        print(json.dumps(e['request'], indent=1, ensure_ascii=False)[:4000])
        break

# 3. 完整 Authorization
for e in entries:
    for h in e['request']['headers']:
        if h['name'].lower() == 'authorization':
            print(f"\n=== FULL Authorization ({len(h['value'])} chars) ===")
            print(h['value'])
            break
    else:
        continue
    break
