# -*- coding: utf-8 -*-
"""01 · 第一段代码：调用大模型，让它回你一句话。

目标：亲手让 LLM 说话。跑通这一步，后面的概念就都"活"了。

准备：
  1. 装依赖（在 PyCharm 终端里运行）：
        pip install requests
  2. 申请 API Key（任选一家，国内推荐硅基流动，有免费额度）：
        硅基流动  https://siliconflow.cn
        智谱      https://open.bigmodel.cn
        OpenRouter https://openrouter.ai  （可接 Claude/GPT 等，需科学上网）
  3. 把拿到的 key 填进下面的 API_KEY。

运行：
        python 01-hello-llm.py
"""

import requests

# ============ 在这里填你的配置 ============
API_KEY = "sk-在这里填你的key"          # ← 改成你的 API Key
BASE_URL = "https://api.siliconflow.cn"  # ← 硅基流动；用智谱就换 https://open.bigmodel.cn/paas/v4
MODEL = "Qwen/Qwen2.5-7B-Instruct"       # ← 硅基流动的免费模型；智谱用 "glm-4-flash"
# =========================================


def chat(user_msg: str) -> str:
    """发一句话给模型，拿回它的回复。"""
    url = f"{BASE_URL}/v1/chat/completions"
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    body = {
        "model": MODEL,
        "messages": [                # messages 是一个"对话列表"
            {"role": "user", "content": user_msg},
        ],
    }
    resp = requests.post(url, headers=headers, json=body, timeout=60)
    if resp.status_code != 200:
        # 出错就把服务器返回的信息打印出来，方便排查（记得记进 cheatsheet/常见报错.md）
        raise RuntimeError(f"请求失败 {resp.status_code}: {resp.text}")
    data = resp.json()
    return data["choices"][0]["message"]["content"]   # 从返回结构里抠出回复文本


if __name__ == "__main__":
    if "在这里填" in API_KEY:
        print("⚠️  还没填 API_KEY！打开这个文件，把 API_KEY 改成你申请到的 key。")
    else:
        answer = chat("用一句话介绍什么是 AI Agent，要通俗。")
        print("模型回复：")
        print(answer)
