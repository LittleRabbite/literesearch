"""多用户认证与隔离测试：.venv\\Scripts\\python.exe backend\\tests\\test_auth.py

覆盖：未授权 401 / 注册登录 / 密码校验 / 双用户会话隔离 / 首用户继承存量 / 登出。
TestClient 隔离：临时元数据库 + 跳过 checkpoint 迁移，不污染真实数据。
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

from backend.app import events, storage  # noqa: E402

PASS = 0


def check(name: str, cond: bool):
    global PASS
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        sys.exit(1)
    PASS += 1


def main():
    # 隔离：临时元数据库 + 跳过 checkpoint 迁移
    storage.store = storage.SessionStore(
        Path(tempfile.mkdtemp()) / "sessions.sqlite")
    events.storage.store = storage.store
    events.SESSIONS.clear()
    events._migrate_checkpoints = lambda: None  # startup 时不再触碰真实库

    from backend.app.main import app
    client = TestClient(app)

    # 1. 未登录一律 401
    check("未登录访问列表 401", client.get("/api/sessions").status_code == 401)
    check("未登录创建会话 401",
          client.post("/api/sessions", json={"topic": "x"}).status_code == 401)

    # 2. 注册：密码过短 / 成功 / 重复
    check("密码过短 400",
          client.post("/api/auth/register",
                      json={"username": "alice", "password": "123"}).status_code == 400)
    # 首用户继承前提：注册前已存在 user_id='' 的存量记录
    storage.store.upsert("legacyrow01", "升级前的旧调研", {}, "finished")
    r = client.post("/api/auth/register",
                    json={"username": "alice", "password": "secret6"})
    check("注册成功并登录", r.status_code == 200 and r.json()["username"] == "alice")
    check("注册后 me 生效", client.get("/api/auth/me").json()["username"] == "alice")
    check("首用户 alice 继承存量会话",
          any(x["id"] == "legacyrow01" for x in client.get("/api/sessions").json()))
    check("重复用户名 409",
          client.post("/api/auth/register",
                      json={"username": "alice", "password": "secret6"}).status_code == 409)

    # 3. alice 创建会话
    sid = client.post("/api/sessions", json={"topic": "Alice 的调研"}).json()["session_id"]
    check("alice 列表含自己的会话",
          any(x["id"] == sid for x in client.get("/api/sessions").json()))

    # 4. bob 注册（非首用户，不触发继承）→ 看不到 alice 的会话
    check("bob 注册成功",
          client.post("/api/auth/register",
                      json={"username": "bob", "password": "secret7"}).status_code == 200)
    check("bob 列表为空（隔离）", client.get("/api/sessions").json() == [])
    check("bob 访问 alice 会话快照 404",
          client.get(f"/api/sessions/{sid}").status_code == 404)
    check("bob 删除 alice 会话 404",
          client.delete(f"/api/sessions/{sid}").status_code == 404)
    check("bob 导出 alice 会话 404",
          client.get(f"/api/sessions/{sid}/export?format=md").status_code == 404)
    check("bob 推送 alice 会话 Zotero 404",
          client.post(f"/api/sessions/{sid}/zotero", json={}).status_code == 404)

    # 5. 登出 / 错误密码
    client.post("/api/auth/logout")
    check("登出后 me 401", client.get("/api/auth/me").status_code == 401)
    check("错误密码登录 401",
          client.post("/api/auth/login",
                      json={"username": "alice", "password": "wrong!!"}).status_code == 401)
    check("正确密码登录成功",
          client.post("/api/auth/login",
                      json={"username": "alice", "password": "secret6"}).status_code == 200)

    # 6. 非首用户不触发继承（carol 注册前用户数 > 1）
    storage.store.upsert("legacyrow02", "无主记录不应被后来者继承", {}, "finished")
    r = client.post("/api/auth/register", json={"username": "carol", "password": "secret8"})
    check("carol 注册成功", r.status_code == 200)
    check("非首用户不继承新存量",
          all(x["id"] != "legacyrow02" for x in client.get("/api/sessions").json()))

    print(f"\nALL {PASS} CHECKS PASSED")


if __name__ == "__main__":
    main()
