# 确认可订状态语义:用户订到的 sku(3# 12:00) vs 其他槽位的状态组合
import json, sys
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

HAR = r"D:\Users\luocj\pyProject\ky\tools\tools\court-booking\booking1.har"
with open(HAR, 'r', encoding='utf-8-sig') as f:
    har = json.load(f)

TARGET_SKU = "131325600100324120261031"  # 3# 12:00-13:00 10-31

for e in har['log']['entries']:
    u = e['request']['url']
    if 'wxFieldBuyPlan/getList' not in u or e['request']['method'] != 'POST':
        continue
    # 找 10-31 那次
    pd = e['request'].get('postData', {})
    params = {p['name']: p['value'] for p in pd.get('params', [])}
    if params.get('time_date') != '2026-10-31':
        continue
    d = json.loads(e['response']['content']['text'])['data']
    print(f"skuList 维度: {len(d['skuList'])} ground x {len(d['skuList'][0])} x ...")

    target = None
    combo = Counter()
    for g_list in d['skuList']:
        for t_list in g_list:
            for slot in t_list:
                key = (slot.get('is_lock'), slot.get('lock_status'), slot.get('is_overdue'), slot.get('price') == '0.00')
                combo[key] += 1
                if slot['sku'] == TARGET_SKU:
                    target = slot
    print("\n状态组合统计 (is_lock, lock_status, is_overdue, price==0):")
    for k, v in combo.most_common():
        print(f"  {k}: {v} 个槽位")
    print(f"\n>>> 用户订到的 3# 12:00-13:00 槽位完整数据:")
    print(json.dumps(target, ensure_ascii=False, indent=2))
    break
