# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from typing import Any

import httpx


def _env_flag(name: str) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def odoo_jsonrpc(url: str, service: str, method: str, args: list[Any]) -> Any:
    payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {"service": service, "method": method, "args": args},
        "id": 1,
    }
    timeout = float(os.getenv("ODOO_RPC_TIMEOUT", "30"))
    with httpx.Client(timeout=timeout) as client:
        r = client.post(url.rstrip("/") + "/jsonrpc", json=payload)
        r.raise_for_status()
        body = r.json()
    if body.get("error"):
        err = body["error"]
        msg = err.get("data", {}).get("message") or err.get("message") or str(err)
        raise RuntimeError(msg)
    return body.get("result")


def odoo_authenticate(base_url: str, db: str, login: str, password: str) -> int:
    uid = odoo_jsonrpc(
        base_url,
        "common",
        "authenticate",
        [db, login, password, {}],
    )
    if not uid or not isinstance(uid, int):
        raise ValueError("Sai tài khoản hoặc cơ sở dữ liệu Odoo.")
    return uid


def odoo_user_context(base_url: str, db: str, uid: int, password: str) -> dict[str, Any]:
    rows = odoo_jsonrpc(
        base_url,
        "object",
        "execute_kw",
        [db, uid, password, "res.users", "read", [[uid]], {"fields": ["name", "login", "company_id"]}],
    )
    if not rows:
        return {"name": "", "login": "", "company_id": None, "company_name": ""}
    row = rows[0]
    name = str(row.get("name") or "")
    login = str(row.get("login") or "")
    company_name = ""
    cid = row.get("company_id")
    if isinstance(cid, (list, tuple)) and len(cid) >= 2:
        company_name = str(cid[1])
    elif isinstance(cid, int):
        crows = odoo_jsonrpc(
            base_url,
            "object",
            "execute_kw",
            [db, uid, password, "res.company", "read", [[cid]], {"fields": ["name"]}],
        )
        if crows and isinstance(crows, list):
            company_name = str(crows[0].get("name") or "")
    return {"name": name, "login": login, "company_id": cid, "company_name": company_name}


def try_login(
    login: str,
    password: str,
) -> tuple[int, str, str, str]:
    """
    Trả về (odoo_uid, display_name, company_name, db).
    """
    if _env_flag("ERP_DEMO_AUTH_BYPASS"):
        exp_login = (os.getenv("ERP_DEMO_BYPASS_LOGIN") or "demo").strip()
        exp_pass = (os.getenv("ERP_DEMO_BYPASS_PASSWORD") or "demo").strip()
        if login == exp_login and password == exp_pass:
            return (
                int(os.getenv("ERP_DEMO_BYPASS_UID") or "2"),
                os.getenv("ERP_DEMO_BYPASS_NAME") or "Demo (bypass)",
                os.getenv("ERP_DEMO_BYPASS_COMPANY") or "Luật Mai Trang",
                (os.getenv("ODOO_DB") or "bypass").strip() or "bypass",
            )
        raise ValueError("Bypass bật nhưng sai tài khoản demo.")

    base = (os.getenv("ODOO_BASE_URL") or "http://localhost:8069").strip().rstrip("/")
    db = (os.getenv("ODOO_DB") or "").strip()
    if not db:
        raise ValueError("Thiếu ODOO_DB trong .env (tên database Odoo).")

    uid = odoo_authenticate(base, db, login, password)
    ctx = odoo_user_context(base, db, uid, password)
    display = ctx.get("name") or ctx.get("login") or login
    company = ctx.get("company_name") or ""
    return uid, str(display), str(company), db


def is_admin_login(login: str) -> bool:
    raw = (os.getenv("ERP_DEMO_ADMIN_LOGINS") or "admin").strip()
    allowed = {x.strip().lower() for x in raw.split(",") if x.strip()}
    return login.strip().lower() in allowed
