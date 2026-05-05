# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    login: str = Field(..., min_length=1, max_length=128)
    password: str = Field(..., min_length=1, max_length=256)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    name: str
    company: str


class CustomerCreate(BaseModel):
    name: str
    tax_id: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    status: str = "active"


class CustomerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    tax_id: str | None
    email: str | None
    phone: str | None
    address: str | None
    status: str
    owner_odoo_uid: int
    created_at: datetime


class ContractCreate(BaseModel):
    customer_id: UUID
    title: str
    contract_type: str = "soan_thao"
    status: str = "nhap"
    start_date: date | None = None
    end_date: date | None = None
    amount: Decimal | None = None
    notes: str | None = None


class ContractOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    customer_id: UUID
    title: str
    contract_type: str
    status: str
    start_date: date | None
    end_date: date | None
    amount: Decimal | None
    notes: str | None
    owner_odoo_uid: int
    created_at: datetime


class DocumentCreate(BaseModel):
    title: str
    doc_type: str = "tai_lieu"
    external_url: str | None = None
    notes: str | None = None
    customer_id: UUID | None = None
    contract_id: UUID | None = None


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    doc_type: str
    external_url: str | None
    notes: str | None
    customer_id: UUID | None
    contract_id: UUID | None
    owner_odoo_uid: int
    created_at: datetime


class NotificationCreate(BaseModel):
    title: str
    body: str | None = None
    due_at: datetime | None = None
    priority: str = "normal"


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    body: str | None
    due_at: datetime | None
    priority: str
    is_read: bool
    owner_odoo_uid: int
    created_at: datetime


class DashboardOut(BaseModel):
    counts: dict[str, int]
    recent_customers: list[CustomerOut]
    recent_contracts: list[ContractOut]
    unread_notifications: int


class ErpChatRequest(BaseModel):
    question: str
    top_k: int | None = None
    business_groups: list[str] | None = None
