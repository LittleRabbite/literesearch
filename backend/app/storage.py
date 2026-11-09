"""会话元数据持久层：SQLite（sessions.sqlite）。

与 LangGraph checkpointer（checkpoints.sqlite）分工：
- 这里只存轻量元数据（列表/搜索/删除的索引），含 payload 以支持重启后恢复/启动；
- 综述全文、文献等完整状态由 checkpointer 落盘，经 graph.get_state 读取。
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone

from .config import DATA_DIR

DB_PATH = DATA_DIR / "sessions.sqlite"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SessionStore:
    def __init__(self, path=DB_PATH):
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init()

    def _init(self):
        with self._lock:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    topic TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    raw_count INTEGER NOT NULL DEFAULT 0,
                    screened_count INTEGER NOT NULL DEFAULT 0,
                    verify_pass INTEGER NOT NULL DEFAULT 0,
                    verify_total INTEGER NOT NULL DEFAULT 0,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    user_id TEXT NOT NULL DEFAULT ''
                )
            """)
            # 旧库升级：补 user_id 列
            cols = {r["name"] for r in self._conn.execute(
                "PRAGMA table_info(sessions)").fetchall()}
            if "user_id" not in cols:
                self._conn.execute(
                    "ALTER TABLE sessions ADD COLUMN user_id TEXT NOT NULL DEFAULT ''")
            # 认证：用户表 + 会话令牌表
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS tokens (
                    token TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
            """)
            self._conn.commit()

    # ---- 写 ----
    def upsert(self, sid: str, topic: str, payload: dict, status: str,
               error: str | None = None, user_id: str | None = None,
               stats: dict | None = None) -> None:
        with self._lock:
            if user_id is None:
                self._conn.execute(
                    """INSERT INTO sessions (id, topic, payload, status, error,
                                              created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(id) DO UPDATE SET
                         topic=excluded.topic, payload=excluded.payload,
                         status=excluded.status, error=excluded.error,
                         updated_at=excluded.updated_at""",
                    (sid, topic, json.dumps(payload, ensure_ascii=False),
                     status, error, _now(), _now()),
                )
            else:
                self._conn.execute(
                    """INSERT INTO sessions (id, topic, payload, status, error,
                                              created_at, updated_at, user_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(id) DO UPDATE SET
                         topic=excluded.topic, payload=excluded.payload,
                         status=excluded.status, error=excluded.error,
                         updated_at=excluded.updated_at, user_id=excluded.user_id""",
                    (sid, topic, json.dumps(payload, ensure_ascii=False),
                     status, error, _now(), _now(), user_id),
                )
            if stats:
                self._write_stats(sid, stats)
            self._conn.commit()

    def update_status(self, sid: str, status: str,
                      error: str | None = None) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE sessions SET status=?, error=?, updated_at=? WHERE id=?",
                (status, error, _now(), sid),
            )
            self._conn.commit()

    def update_stats(self, sid: str, stats: dict) -> None:
        with self._lock:
            self._write_stats(sid, stats)
            self._conn.commit()

    def _write_stats(self, sid: str, stats: dict) -> None:  # 需持有锁调用
        cols = ("raw_count", "screened_count", "verify_pass",
                "verify_total", "retry_count")
        sets = ", ".join(f"{c}=?" for c in cols)
        vals = [int(stats.get(c) or 0) for c in cols]
        self._conn.execute(
            f"UPDATE sessions SET {sets}, updated_at=? WHERE id=?",
            (*vals, _now(), sid),
        )

    # ---- 读 ----
    def get(self, sid: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM sessions WHERE id=?", (sid,)
            ).fetchone()
        return dict(row) if row else None

    def list(self, q: str | None = None, limit: int = 200,
             include_payload: bool = False,
             user_id: str | None = None) -> list[dict]:
        cols = ("id, topic, status, error, created_at, updated_at, "
                "raw_count, screened_count, verify_pass, verify_total, retry_count")
        if include_payload:
            cols += ", payload"
        sql = f"SELECT {cols} FROM sessions"
        args: list = []
        conds = []
        if q:
            conds.append("topic LIKE ?")
            args.append(f"%{q}%")
        if user_id is not None:
            conds.append("user_id = ?")
            args.append(user_id)
        if conds:
            sql += " WHERE " + " AND ".join(conds)
        sql += " ORDER BY created_at DESC LIMIT ?"
        args.append(limit)
        with self._lock:
            rows = self._conn.execute(sql, args).fetchall()
        return [dict(r) for r in rows]

    def delete(self, sid: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM sessions WHERE id=?", (sid,))
            self._conn.commit()

    def delete_empty_user_sessions(self) -> None:
        """迁移收尾：删除 user_id 为空的历史记录（仅认证升级前残留）。"""
        with self._lock:
            self._conn.execute("DELETE FROM sessions WHERE user_id=''")
            self._conn.commit()

    # ---- 认证 ----
    def create_user(self, username: str, password_hash: str) -> bool:
        """创建用户；用户名已存在返回 False。"""
        with self._lock:
            try:
                self._conn.execute(
                    "INSERT INTO users (username, password_hash, created_at) "
                    "VALUES (?, ?, ?)", (username, password_hash, _now()))
                self._conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def get_user(self, username: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM users WHERE username=?", (username,)).fetchone()
        return dict(row) if row else None

    def count_users(self) -> int:
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    def assign_legacy_sessions(self, username: str) -> None:
        """首个注册用户继承认证功能上线前的存量会话。"""
        with self._lock:
            self._conn.execute(
                "UPDATE sessions SET user_id=? WHERE user_id=''", (username,))
            self._conn.commit()

    def create_token(self, token: str, username: str, expires_at: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO tokens (token, username, expires_at) VALUES (?, ?, ?)",
                (token, username, expires_at))
            self._conn.execute(
                "DELETE FROM tokens WHERE expires_at < ?", (_now(),))
            self._conn.commit()

    def get_token(self, token: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM tokens WHERE token=?", (token,)).fetchone()
        if not row or row["expires_at"] < _now():
            return None
        return dict(row)

    def delete_token(self, token: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM tokens WHERE token=?", (token,))
            self._conn.commit()


store = SessionStore()
