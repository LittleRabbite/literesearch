"""认证：pbkdf2 密码哈希 + HttpOnly Cookie 会话令牌。

轻量多用户方案：用户名/密码登录，令牌落库（重启不失效），Cookie 自动随
fetch/EventSource 携带，无需前端手动附加。
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, Response

from . import storage

COOKIE_NAME = "litagent_auth"
TOKEN_TTL_DAYS = 30
_PBKDF2_ITER = 200_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), _PBKDF2_ITER).hex()
    return f"{salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, digest = stored.split("$", 1)
    except ValueError:
        return False
    cand = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), _PBKDF2_ITER).hex()
    return hmac.compare_digest(cand, digest)


def issue_token(resp: Response, username: str) -> None:
    """签发令牌并写入 HttpOnly Cookie（30 天有效）。"""
    token = secrets.token_hex(32)
    expires = datetime.now(timezone.utc) + timedelta(days=TOKEN_TTL_DAYS)
    storage.store.create_token(token, username, expires.isoformat())
    # localhost 为 http，故不强制 Secure；公网 HTTPS 部署时建议在
    # 反向代理层统一加 HSTS/Secure。
    resp.set_cookie(
        COOKIE_NAME, token,
        max_age=TOKEN_TTL_DAYS * 86400,
        httponly=True, samesite="lax",
    )


def clear_token(request: Request, resp: Response) -> None:
    token = request.cookies.get(COOKIE_NAME)
    if token:
        storage.store.delete_token(token)
    resp.delete_cookie(COOKIE_NAME)


def require_user(request: Request) -> str:
    """FastAPI 依赖：校验 Cookie 令牌，返回当前用户名。"""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(401, "未登录")
    row = storage.store.get_token(token)
    if not row:
        raise HTTPException(401, "登录已过期，请重新登录")
    return row["username"]
