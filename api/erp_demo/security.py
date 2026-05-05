# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from api.erp_demo.odoo_auth import is_admin_login

_bearer = HTTPBearer(auto_error=False)


class TokenPayload(BaseModel):
    sub: str
    uid: int
    db: str
    name: str = ""
    company: str = ""
    role: str = "user"


def _env_flag(name: str) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _secret() -> str:
    s = (os.getenv("JWT_SECRET") or "").strip()
    if s:
        return s
    if _env_flag("ERP_DEMO_ALLOW_WEAK_JWT"):
        return "weak-dev-only-change-me"
    raise RuntimeError("Thiếu JWT_SECRET (hoặc bật ERP_DEMO_ALLOW_WEAK_JWT chỉ cho dev).")


def create_access_token(payload: TokenPayload, expires_hours: int = 24) -> str:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(hours=expires_hours)
    data: dict[str, Any] = {
        "sub": payload.sub,
        "uid": payload.uid,
        "db": payload.db,
        "name": payload.name,
        "company": payload.company,
        "role": payload.role,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(data, _secret(), algorithm="HS256")


def decode_token(token: str) -> TokenPayload:
    try:
        raw = jwt.decode(token, _secret(), algorithms=["HS256"])
        return TokenPayload(
            sub=str(raw["sub"]),
            uid=int(raw["uid"]),
            db=str(raw["db"]),
            name=str(raw.get("name") or ""),
            company=str(raw.get("company") or ""),
            role=str(raw.get("role") or "user"),
        )
    except Exception as e:
        raise HTTPException(status_code=401, detail="Phiên đăng nhập không hợp lệ.") from e


async def get_current_user(
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> TokenPayload:
    if cred is None or (cred.scheme or "").lower() != "bearer":
        raise HTTPException(status_code=401, detail="Thiếu Bearer token.")
    return decode_token(cred.credentials)


def build_payload_after_login(login: str, uid: int, db: str, display_name: str, company_name: str) -> TokenPayload:
    role = "admin" if is_admin_login(login) else "user"
    return TokenPayload(
        sub=login,
        uid=uid,
        db=db,
        name=display_name,
        company=company_name or "",
        role=role,
    )
