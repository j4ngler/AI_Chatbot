# -*- coding: utf-8 -*-
from __future__ import annotations

from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from api.erp_demo.database import session_factory


def get_db_session() -> Generator[Session, None, None]:
    factory = session_factory()
    if factory is None:
        raise HTTPException(
            status_code=503,
            detail="Chưa cấu hình DATABASE_URL (PostgreSQL cho demo ERP).",
        )
    db = factory()
    try:
        yield db
    finally:
        db.close()


DbSession = Annotated[Session, Depends(get_db_session)]
