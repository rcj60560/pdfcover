# 一次性分析脚本:解析 booking.har,列出会话概览 + api.wesais.com 详情
import json, sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

HAR = r"C:\Users\luocj\Documents\booking.har"

with open(HAR, 'r', encoding='utf-8-sig') as f:
    har = json.load(f)

entries = har['log']['entries']
print(f"total entries: {len(entries)}\n")

print("=== OVERVIEW ===")
for i, e in enumerate(entries):
    req = e['request']
    resp = e['response']
    url = req['url']
    # strip query for overview
    path = url.split('?')[0]
    if len(path) > 78:
        path = path[:75] + '...'
    rb = req.get('postData', {}).get('text', '')
    sb = resp.get('content', {}).get('size', 0)
    print(f"[{i:02d}] {req['method']:7s} {resp['status']:3d} req={len(rb):5d}B resp={sb:6d}B  {path}")

print("\n=== API DETAIL (api.wesais.com, non-OPTIONS) ===")
header_dumped = False
for i, e in enumerate(entries):
    req = e['request']
    resp = e['response']
    url = req['url']
    if 'api.wesais.com' not in url:
        continue
    if req['method'] == 'OPTIONS' or resp['status'] == 204:
        continue
    print(f"\n--- [{i:02d}] {req['method']} {url} -> {resp['status']}")
    if not header_dumped:
        print("  FULL REQUEST HEADERS:")
        for h in req['headers']:
            print(f"    {h['name']}: {h['value'][:180]}")
        header_dumped = True
    else:
        # just auth-ish headers
        for h in req['headers']:
            n = h['name'].lower()
            if any(k in n for k in ('token', 'auth', 'cookie', 'session', 'user', 'wx')):
                print(f"    H {h['name']}: {h['value'][:180]}")
    body = req.get('postData', {}).get('text', '')
    if body:
        print(f"  REQ BODY: {body[:600]}")
    rbody = resp.get('content', {}).get('text', '')
    if rbody:
        print(f"  RESP BODY: {rbody[:600]}")
