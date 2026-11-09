"""持久化层测试：python backend/tests/test_persistence.py（项目根目录执行）

覆盖：写通落盘 / 重启恢复（load_persisted）/ running 中断标记 / 删除清理。
不跑真实图执行，checkpoints.sqlite 不受影响。
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app import events, storage  # noqa: E402

PASS = 0


def check(name: str, cond: bool):
    global PASS
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}")
    if cond:
        PASS += 1
    else:
        sys.exit(1)


def main():
    # 隔离：元数据写入临时库，不污染真实 sessions.sqlite
    tmp = Path(tempfile.mkdtemp()) / "sessions.sqlite"
    storage.store = storage.SessionStore(tmp)
    events.storage.store = storage.store

    # 1. 创建即落盘
    s = events.create_session("测试主题A", 2022, 2026, 15, False)
    check("创建会话后元数据落盘", storage.store.get(s.id) is not None)
    check("列表返回该会话", storage.store.list()[0]["topic"] == "测试主题A")

    # 2. 状态与统计写通（含非空值，验证 SQL 绑定正确）
    events._sync_stats(s)  # 空状态也应安全
    row = storage.store.get(s.id)
    check("统计写通（空状态安全）",
          row["raw_count"] == 0 and row["verify_total"] == 0)
    storage.store.update_stats(s.id, {
        "raw_count": 63, "screened_count": 15,
        "verify_pass": 6, "verify_total": 15, "retry_count": 1})
    row = storage.store.get(s.id)
    check("统计写通（非空值逐列落盘）",
          (row["raw_count"], row["screened_count"], row["verify_pass"],
           row["verify_total"], row["retry_count"]) == (63, 15, 6, 15, 1))

    # 3. 模拟重启恢复：内存清空后从库恢复
    events.SESSIONS.clear()
    events.load_persisted()
    restored = events.SESSIONS.get(s.id)
    check("重启后会话恢复", restored is not None)
    check("恢复后 topic/status 一致",
          restored.topic == "测试主题A" and restored.status == "created")
    check("恢复后 payload 可启动",
          restored.payload["topic"] == "测试主题A"
          and restored.payload["top_n"] == 15)

    # 4. running 会话重启后标记为 error
    sid2 = "deadrun001"
    storage.store.upsert(sid2, "中断主题B", {}, "running")
    events.SESSIONS.clear()
    events.load_persisted()
    s2 = events.SESSIONS.get(sid2)
    check("running 会话标记为 error",
          s2 is not None and s2.status == "error" and "中断" in (s2.error or ""))

    # 5. paused 会话重启后保持 paused（可 resume）
    sid3 = "pausedrow1"
    storage.store.upsert(sid3, "待审核主题C", {}, "paused")
    events.SESSIONS.clear()
    events.load_persisted()
    check("paused 会话保持 paused",
          events.SESSIONS.get(sid3).status == "paused")

    # 6. 删除：内存 + 元数据同时清理
    events.delete_session(sid3)
    check("删除后元数据移除", storage.store.get(sid3) is None)
    check("删除后内存移除", sid3 not in events.SESSIONS)

    # 7. 关键词搜索
    hits = storage.store.list(q="测试主题")
    check("按主题搜索", len(hits) >= 1 and all("测试主题" in h["topic"] for h in hits))

    print(f"\nALL {PASS} CHECKS PASSED")


if __name__ == "__main__":
    main()
