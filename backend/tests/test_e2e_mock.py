"""端到端验证：真实检索工具冒烟 + MOCK_LLM 全流程 + 反馈回路 + 导出。

运行：.venv/Scripts/python backend/tests/test_e2e_mock.py
"""
import json
import os
import sys
import threading
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ["EMBED_MODEL"] = "sentence-transformers/all-MiniLM-L6-v2"  # 小模型快速验证嵌入路径
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

import requests  # noqa: E402
import uvicorn   # noqa: E402

from app import tools  # noqa: E402


def banner(msg: str):
    print(f"\n{'=' * 60}\n{msg}\n{'=' * 60}", flush=True)


# ------------------------------------------------- 0. 启动真实服务
BANNER_PORT = 8765
server_cfg = uvicorn.Config("app.main:app", host="127.0.0.1", port=BANNER_PORT,
                            log_level="error", lifespan="off")
server = uvicorn.Server(server_cfg)
threading.Thread(target=server.run, daemon=True).start()
for _ in range(100):
    if server.started:
        break
    time.sleep(0.2)
BASE = f"http://127.0.0.1:{BANNER_PORT}"
print(f"uvicorn started at {BASE}", flush=True)

# ------------------------------------------------- 0.5 注册 e2e 专用用户（多用户鉴权）
http = requests.Session()
for attempt in ("register", "login"):
    r = http.post(f"{BASE}/api/auth/{attempt}",
                  json={"username": "e2e_bot", "password": "e2e-pass-6"},
                  timeout=30)
    if r.ok:
        break
print(f"auth: e2e_bot ({'ok' if r.ok else r.text})", flush=True)

# ------------------------------------------------- 1. 工具冒烟（真实网络）
banner("1. 检索工具冒烟测试（真实 API）")
r = tools.search_arxiv("LLM agent survey", year_from=2023, max_results=3)
print(f"arXiv: {len(r)} 篇  例: {r[0]['title'][:60] if r else '无'}")

r2 = tools.search_semantic_scholar("LLM agent", year_from=2023, limit=3)
print(f"S2:    {len(r2)} 篇  例: {r2[0]['title'][:60] if r2 else '无（可能限流）'}")

v = tools.verify_reference("Attention Is All You Need", "Vaswani", 2017)
print(f"CrossRef 核验: ok={v['ok']}  {v.get('detail', '')}")

b = tools.fetch_bibtex(arxiv_id="1706.03762")
print(f"BibTeX: {'OK ' + b.splitlines()[0] if b else 'None'}")

# ------------------------------------------------- 2. 全流程（MOCK LLM）
banner("2. LangGraph 全流程（MOCK_LLM=1）")
body = {"topic": "LLM agents for software engineering",
        "year_from": 2023, "year_to": 2026, "top_n": 8, "include_pdf": False}
sid = http.post(f"{BASE}/api/sessions", json=body, timeout=30).json()["session_id"]
print(f"session: {sid}")


def consume(out: list, label: str):
    try:
        with http.get(f"{BASE}/api/sessions/{sid}/events",
                          stream=True, timeout=600) as resp:
            for raw in resp.iter_lines(decode_unicode=True):
                if not raw or not raw.startswith("data: "):
                    continue
                ev = json.loads(raw[6:])
                out.append(ev)
                t = ev["type"]
                if t == "node_end":
                    print(f"  [{label} node_end] {ev['node']}", flush=True)
                elif t == "progress":
                    print(f"  [{label}] {ev.get('node')}: {ev.get('message', '')[:70]}",
                          flush=True)
                elif t == "interrupt":
                    print(f"  [{label} interrupt] 挂起等待审核", flush=True)
                elif t == "status":
                    print(f"  [{label} status] {ev.get('status')}", flush=True)
                elif t == "error":
                    print(f"  [{label} ERROR] {ev.get('message')}", flush=True)
                elif t == "done":
                    break
    except Exception as e:  # noqa: BLE001
        out.append({"type": "__thread_error", "message": repr(e)})
        print(f"  [{label} THREAD_ERROR] {e!r}", flush=True)


def run_phase(trigger: dict, label: str) -> list[dict]:
    out: list[dict] = []
    th = threading.Thread(target=consume, args=(out, label), daemon=True)
    th.start()
    time.sleep(0.6)                       # 等 SSE 连接建立
    url = (f"{BASE}/api/sessions/{sid}/start" if trigger["action"] == "start"
           else f"{BASE}/api/sessions/{sid}/feedback")
    payload = {} if trigger["action"] == "start" else {
        "action": trigger["action"],
        "comment": trigger.get("comment", ""),
        "drop": trigger.get("drop", [])}
    resp = http.post(url, json=payload if payload else None, timeout=30)
    print(f"  POST {url.split('/')[-1]} -> {resp.json()}", flush=True)
    th.join(timeout=420)
    return out


ev1 = run_phase({"action": "start"}, "run1")
assert not any(e["type"] == "__thread_error" for e in ev1), "SSE 线程异常"
assert any(e["type"] == "interrupt" for e in ev1), "应挂起等待审核"
assert any(e["type"] == "token" for e in ev1), "writer 应有 token 流"

# 刷新恢复快照
snap = http.get(f"{BASE}/api/sessions/{sid}", timeout=30).json()
print(f"刷新恢复: status={snap['status']}  "
      f"screened={len(snap['state'].get('screened', []))}  "
      f"draft长度={len(snap['state'].get('survey_draft', ''))}")
assert snap["status"] == "paused", f"期望 paused，实际 {snap['status']}"
assert snap["state"]["screened"], "screened 不应为空"
assert "[0]" in snap["state"]["survey_draft"], "综述应含引用编号"
n_screened = len(snap["state"]["screened"])

# ------------------------------------- 3. 反馈回路：drop [0] → 重写 → 挂起
banner("3. 反馈回路：drop [0] → writer 重跑 → 再次挂起")
ev2 = run_phase({"action": "drop", "drop": [0]}, "run2")
assert not any(e["type"] == "__thread_error" for e in ev2)
snap = http.get(f"{BASE}/api/sessions/{sid}", timeout=30).json()
assert snap["status"] == "paused"
n_after_drop = len(snap["state"]["screened"])
print(f"drop 后 screened: {n_after_drop}（之前 {n_screened}）")
assert n_after_drop == n_screened - 1

# ------------------------------------------------- 4. approved → END
banner("4. approved → 流程结束")
ev3 = run_phase({"action": "approved"}, "run3")
snap = http.get(f"{BASE}/api/sessions/{sid}", timeout=30).json()
print(f"最终状态: {snap['status']}（应为 finished）")
assert snap["status"] == "finished", f"期望 finished，实际 {snap['status']}"

# ------------------------------------------------- 5. 导出
banner("5. 三种导出")
for fmt in ("md", "bib", "xlsx"):
    resp = http.get(f"{BASE}/api/sessions/{sid}/export?format={fmt}", timeout=60)
    print(f"{fmt}: status={resp.status_code}  bytes={len(resp.content)}")
    assert resp.status_code == 200

print("\nALL PASSED ✔")
