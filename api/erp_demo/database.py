# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def _database_url() -> str | None:
    u = (os.getenv("DATABASE_URL") or "").strip()
    return u or None


_engine = None
_SessionLocal = None


def get_engine():
    global _engine, _SessionLocal
    url = _database_url()
    if not url:
        return None
    if _engine is None:
        connect_args: dict = {}
        if url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        _engine = create_engine(url, pool_pre_ping=not url.startswith("sqlite"), connect_args=connect_args)
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
    return _engine


def session_factory():
    if _SessionLocal is None:
        get_engine()
    return _SessionLocal


def get_db() -> Generator:
    factory = session_factory()
    if factory is None:
        raise RuntimeError("DATABASE_URL chưa cấu hình.")
    db = factory()
    try:
        yield db
    finally:
        db.close()


def init_db() -> bool:
    """Tạo bảng nếu có DATABASE_URL."""
    from api.erp_demo import models  # noqa: F401

    eng = get_engine()
    if eng is None:
        return False
    Base.metadata.create_all(bind=eng)
    return True
