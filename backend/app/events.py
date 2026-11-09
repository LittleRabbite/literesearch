"""会话管理：LangGraph 后台执行线程 + SSE 事件总线。

生命周期：create（仅注册）→ start（起线程跑图）→ SSE 订阅 →
interrupt 挂起（status=paused）→ feedback resume → … → finished。
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
import uuid
from collections import deque
from datetime import datetime, timezone

from langgraph.types import Command

from . import config, storage
from .graph import build_graph

graph = build_graph()

NODE_ORDER = ["planner", "retriever", "screening", "writer",
              "verifier", "bib_generator", "pdf_ingest", "human_review"]


def _jsonable(obj):
    try:
        json.dumps(obj, ensure_ascii=False)
        return obj
    except (TypeError, ValueError):
        return str(obj)


class Session:
    def __init__(self, session_id: str, payload: dict, user_id: str = ""):
        self.id = session_id
        self.user_id = user_id  # 归属用户；'' 为认证功能上线前的存量会话
        self.payload = payload
        self.topic = payload.get("topic", "")
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.status = "created"          # created/running/paused/finished/error
        self.error: str | None = None
        self.queue: asyncio.Queue | None = None
        self.loop: asyncio.AbstractEventLoop | None = None

    # ---- 供执行线程调用（线程安全） ----
    def bind_loop(self, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue):
        self.loop = loop
        self.queue = queue

    def push(self, event: dict):
        if self.loop and self.queue:
            self.loop.call_soon_threadsafe(self.queue.put_nowait, event)

    @property
    def config(self) -> dict:
        return {"configurable": {"thread_id": self.id}}


SESSIONS: dict[str, Session] = {}


def create_session(topic: str, year_from: int, year_to: int,
                   top_n: int, include_pdf: bool, user_id: str = "") -> Session:
    session_id = uuid.uuid4().hex[:12]
    payload = {
        "topic": topic, "year_from": year_from, "year_to": year_to,
        "top_n": top_n, "include_pdf": include_pdf,
        "sub_queries": [], "papers": [], "screened": [],
        "survey_draft": "", "verify_report": [], "bib_entries": [],
        "pdf_ingested": 0, "retry_count": 0, "human_feedback": None,
    }
    s = Session(session_id, payload, user_id)
    SESSIONS[session_id] = s
    storage.store.upsert(session_id, topic, payload, s.status, user_id=user_id)
    return s


def delete_session(session_id: str) -> None:
    """删除会话：内存 + 元数据库 + LangGraph 断点记录（尽力而为）。"""
    SESSIONS.pop(session_id, None)
    storage.store.delete(session_id)
    try:  # 清理 checkpointer 中该 thread_id 的状态，避免残留
        conn = sqlite3.connect(str(config.CHECKPOINT_DB))
        for table in ("checkpoints", "writes"):
            conn.execute(f"DELETE FROM {table} WHERE thread_id=?", (session_id,))
        conn.commit()
        conn.close()
    except sqlite3.Error:
        pass


def load_persisted() -> None:
    """后端重启后从元数据库恢复会话注册表。

    - paused/finished/error：完整恢复，快照与 resume 均可用（状态由 checkpointer 持有）；
    - created：保留待启动（payload 已落盘，可正常 start）；
    - running：执行线程已随进程消亡，标记为 error 并提示。
    """
    for row in storage.store.list(limit=10000, include_payload=True):
        sid = row["id"]
        if sid in SESSIONS:
            continue
        try:
            payload = json.loads(row["payload"])
        except (TypeError, ValueError):
            continue
        s = Session(sid, payload, row.get("user_id", "") or "")
        s.created_at = row["created_at"]
        s.status = row["status"]
        s.error = row["error"]
        if s.status == "running":
            s.status = "error"
            s.error = "后端重启，执行被中断，请重新发起调研"
            storage.store.update_status(sid, s.status, s.error)
        SESSIONS[sid] = s
    _migrate_checkpoints()


def _migrate_checkpoints() -> None:
    """一次性迁移：元数据库启用之前创建的旧会话（仅存在于 checkpointer 中），
    反向补录进历史列表，避免升级后旧调研失联。幂等，无旧数据时为空操作。"""
    try:
        conn = sqlite3.connect(str(config.CHECKPOINT_DB))
        rows = conn.execute(
            "SELECT DISTINCT thread_id FROM checkpoints"
        ).fetchall()
        conn.close()
    except sqlite3.Error:
        return
    for (tid,) in rows:
        if tid in SESSIONS or storage.store.get(tid):
            continue
        try:
            snap = graph.get_state({"configurable": {"thread_id": tid}})
            values = snap.values or {}
        except Exception:  # noqa: BLE001
            continue
        topic = str(values.get("topic") or "（未命名调研）")
        payload = {
            "topic": topic,
            "year_from": values.get("year_from", 2022),
            "year_to": values.get("year_to", 2026),
            "top_n": values.get("top_n", 15),
            "include_pdf": values.get("include_pdf", False),
            "sub_queries": [], "papers": [], "screened": [],
            "survey_draft": "", "verify_report": [], "bib_entries": [],
            "pdf_ingested": 0, "retry_count": 0, "human_feedback": None,
        }
        # 状态推断：挂在 human_review → paused；无筛选结果 → created；其余 → finished
        if snap.next:
            status = "paused"
        elif not values.get("screened"):
            status = "created"
        else:
            status = "finished"
        storage.store.upsert(tid, topic, payload, status)
        report = values.get("verify_report") or []
        storage.store.update_stats(tid, {
            "raw_count": len(values.get("papers") or []),
            "screened_count": len(values.get("screened") or []),
            "verify_pass": sum(1 for v in report if v.get("ok")),
            "verify_total": len(report),
            "retry_count": values.get("retry_count") or 0,
        })
        s = Session(tid, payload)
        s.status = status
        SESSIONS[tid] = s


# ------------------------------------------------------------ 执行
def _sync_stats(session: Session) -> None:
    """把漏斗统计（原始/入选/核验通过/轮次）写入元数据库，供历史列表展示。"""
    try:
        values = graph.get_state(session.config).values or {}
        report = values.get("verify_report") or []
        storage.store.update_stats(session.id, {
            "raw_count": len(values.get("papers") or []),
            "screened_count": len(values.get("screened") or []),
            "verify_pass": sum(1 for v in report if v.get("ok")),
            "verify_total": len(report),
            "retry_count": values.get("retry_count") or 0,
        })
    except Exception:  # noqa: BLE001 统计失败不影响主流程
        pass


def _run_graph(session: Session, payload) -> None:
    session.status = "running"
    storage.store.update_status(session.id, "running")
    try:
        for mode, chunk in graph.stream(payload, session.config,
                                        stream_mode=["updates", "custom"]):
            if mode == "custom":
                if isinstance(chunk, dict):
                    session.push(chunk)
                continue
            # updates 模式：{node: state_delta}
            for node, delta in chunk.items():
                if node == "__interrupt__":
                    continue
                session.push({"type": "node_end", "node": node})
                session.push({"type": "artifact", "node": node,
                              "data": _jsonable(delta)})
    except Exception as e:  # noqa: BLE001
        session.status = "error"
        session.error = str(e)
        session.push({"type": "error", "message": str(e)})
    else:
        snap = graph.get_state(session.config)
        if snap.next:                     # 挂起在 human_review
            session.status = "paused"
            session.push({"type": "interrupt", "node": "human_review"})
        else:
            session.status = "finished"
    finally:
        storage.store.update_status(session.id, session.status, session.error)
        _sync_stats(session)
        session.push({"type": "status", "status": session.status})
        session.push({"type": "done"})


def _spawn(session: Session, payload) -> None:
    threading.Thread(target=_run_graph, args=(session, payload), daemon=True).start()


def start_session(session: Session) -> None:
    _spawn(session, session.payload)


def resume_session(session: Session, feedback: dict) -> None:
    _spawn(session, Command(resume=feedback))


# ------------------------------------------------------------ 快照
def state_snapshot(session: Session) -> dict:
    """从 checkpointer 取完整状态，供刷新恢复。"""
    try:
        snap = graph.get_state(session.config)
        values = {k: _jsonable(v) for k, v in (snap.values or {}).items()}
    except Exception:
        values = {}
    # session.status 是权威来源：运行中 snap.next 也非空（下一个节点待执行），
    # 仅凭 snap.next 判 paused 会把「运行中」误报为「待审核」
    return {
        "session_id": session.id,
        "topic": session.topic,
        "status": session.status,
        "error": session.error,
        "created_at": session.created_at,
        "state": values,
    }


# ------------------------------------------------------------ SSE
async def sse_stream(session: Session):
    """先发快照（刷新恢复），再转发增量事件；心跳保活，连接常驻。"""
    session.loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    session.queue = queue

    yield f"data: {json.dumps({'type': 'snapshot', **state_snapshot(session)}, ensure_ascii=False)}\n\n"

    while True:
        try:
            event = await asyncio.wait_for(queue.get(), timeout=15)
        except asyncio.TimeoutError:
            yield ": ping\n\n"
            continue
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
