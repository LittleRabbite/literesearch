"""FastAPI 入口：薄封装 LangGraph，SSE 透传 + 导出 + Zotero + 多用户鉴权。

启动：uvicorn backend.app.main:app --port 8000（在项目根目录执行）
"""
from __future__ import annotations

import json
from urllib.parse import quote

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from . import auth, events, exports, zotero_client

app = FastAPI(title="Literature Research Agent", version="0.1.0")


@app.on_event("startup")
def _restore_sessions():
    """后端重启后从元数据库恢复会话注册表（历史列表/快照恢复可用）。"""
    events.load_persisted()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"], allow_headers=["*"], allow_credentials=True,
)


class CreateBody(BaseModel):
    topic: str
    year_from: int = 2022
    year_to: int = 2026
    top_n: int = 15
    include_pdf: bool = False


class FeedbackBody(BaseModel):
    action: str                     # approved / rewrite / refetch / drop
    comment: str = ""
    drop: list[int] = []


class ZoteroBody(BaseModel):
    indices: list[int] | None = None   # 缺省推送全部 screened


class AuthBody(BaseModel):
    username: str
    password: str


def _own_session(session_id: str, user: str) -> events.Session:
    """取当前用户名下的会话；他人或不存在一律 404（不暴露存在性）。"""
    s = events.SESSIONS.get(session_id)
    if not s or s.user_id != user:
        raise HTTPException(404, "session 不存在")
    return s


def _attachment(safe_topic: str, ext: str) -> str:
    """下载头：中文文件名按 RFC 5987 编码（header 只允许 latin-1），附 ASCII 回退名。"""
    return (f"attachment; filename=\"export{ext}\"; "
            f"filename*=UTF-8''{quote(safe_topic)}{ext}")


# ------------------------------------------------------------- 认证
@app.post("/api/auth/register")
def register(body: AuthBody, resp: Response):
    username = body.username.strip()
    if not (2 <= len(username) <= 32):
        raise HTTPException(400, "用户名需 2–32 个字符")
    if len(body.password) < 6:
        raise HTTPException(400, "密码至少 6 位")
    if not events.storage.store.create_user(username, auth.hash_password(body.password)):
        raise HTTPException(409, "用户名已存在")
    # 首个注册用户继承认证上线前的存量会话
    if events.storage.store.count_users() == 1:
        events.storage.store.assign_legacy_sessions(username)
    auth.issue_token(resp, username)
    return {"username": username}


@app.post("/api/auth/login")
def login(body: AuthBody, resp: Response):
    row = events.storage.store.get_user(body.username.strip())
    if not row or not auth.verify_password(body.password, row["password_hash"]):
        raise HTTPException(401, "用户名或密码错误")
    auth.issue_token(resp, body.username.strip())
    return {"username": body.username.strip()}


@app.post("/api/auth/logout")
def logout(request: Request, resp: Response):
    auth.clear_token(request, resp)
    return {"ok": True}


@app.get("/api/auth/me")
def me(user: str = Depends(auth.require_user)):
    return {"username": user}


# ------------------------------------------------------------- 会话
@app.get("/api/sessions")
def list_sessions(q: str | None = None, user: str = Depends(auth.require_user)):
    """历史调研列表：仅返回当前用户名下的会话。"""
    return events.storage.store.list(q=q, user_id=user)


@app.delete("/api/sessions/{session_id}")
def remove_session(session_id: str, user: str = Depends(auth.require_user)):
    _own_session(session_id, user)
    events.delete_session(session_id)
    return {"ok": True}


@app.post("/api/sessions")
def create_session(body: CreateBody, user: str = Depends(auth.require_user)):
    if not body.topic.strip():
        raise HTTPException(400, "topic 不能为空")
    s = events.create_session(body.topic.strip(), body.year_from,
                              body.year_to, body.top_n, body.include_pdf,
                              user_id=user)
    return {"session_id": s.id, "status": s.status}


@app.post("/api/sessions/{session_id}/start")
def start_session(session_id: str, user: str = Depends(auth.require_user)):
    s = _own_session(session_id, user)
    if s.status != "created":
        raise HTTPException(409, f"会话状态为 {s.status}，不能重复启动")
    events.start_session(s)
    return {"ok": True}


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str, user: str = Depends(auth.require_user)):
    return events.state_snapshot(_own_session(session_id, user))


@app.get("/api/sessions/{session_id}/events")
async def stream_events(session_id: str, user: str = Depends(auth.require_user)):
    s = _own_session(session_id, user)
    return StreamingResponse(
        events.sse_stream(s),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                 "Connection": "keep-alive"},
    )


@app.post("/api/sessions/{session_id}/feedback")
def feedback(session_id: str, body: FeedbackBody,
             user: str = Depends(auth.require_user)):
    s = _own_session(session_id, user)
    if s.status != "paused":
        raise HTTPException(409, f"会话未处于待审核状态（当前 {s.status}）")
    if body.action not in ("approved", "rewrite", "refetch", "drop"):
        raise HTTPException(400, "action 取值非法")
    events.resume_session(s, {"action": body.action,
                              "comment": body.comment, "drop": body.drop})
    return {"ok": True}


# ------------------------------------------------------------- 导出
@app.get("/api/sessions/{session_id}/export")
def export(session_id: str, format: str = "md",
           user: str = Depends(auth.require_user)):
    s = _own_session(session_id, user)
    snap = events.graph.get_state(s.config)
    state = snap.values or {}
    if not state.get("screened"):
        raise HTTPException(400, "暂无可导出的结果")
    safe_topic = "".join(c for c in s.topic if c.isalnum() or c in "_- ")[:40] or "survey"

    if format == "md":
        content = exports.to_markdown(state)
        return Response(content, media_type="text/markdown; charset=utf-8",
                        headers={"Content-Disposition": _attachment(safe_topic, ".md")})
    if format == "bib":
        content = exports.to_bibtex(state)
        return Response(content, media_type="application/x-bibtex",
                        headers={"Content-Disposition": _attachment(safe_topic, ".bib")})
    if format == "xlsx":
        return Response(exports.to_xlsx(state),
                        media_type="application/vnd.openxmlformats-officedocument"
                                   ".spreadsheetml.sheet",
                        headers={"Content-Disposition": _attachment(safe_topic, ".xlsx")})
    raise HTTPException(400, "format 仅支持 md | bib | xlsx")


# ------------------------------------------------------------ Zotero
@app.post("/api/sessions/{session_id}/zotero")
def push_zotero(session_id: str, body: ZoteroBody,
                user: str = Depends(auth.require_user)):
    s = _own_session(session_id, user)
    state = events.graph.get_state(s.config).values or {}
    screened = state.get("screened", [])
    if not screened:
        raise HTTPException(400, "暂无可推送的文献")
    if body.indices is None:
        targets = screened
    else:
        targets = [screened[i] for i in body.indices if 0 <= i < len(screened)]
    try:
        return zotero_client.push_papers(targets)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Zotero 推送失败: {e}")


# ------------------------------------------------------------- 健康检查
@app.get("/api/health")
def health():
    return {"ok": True, "sessions": len(events.SESSIONS)}
