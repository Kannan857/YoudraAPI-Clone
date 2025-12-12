from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr


class OrgMemberSummary(BaseModel):
    member_id: UUID
    org_id: UUID
    email: EmailStr
    full_name: Optional[str] = None
    role: str
    status: str
    consumes_seat: bool
    user_id: Optional[UUID] = None
    invited_by_user_id: Optional[UUID] = None
    invite_token: Optional[str] = None
    invite_expires_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class OrgMemberInviteRequest(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None
    role: Literal["ORG_ADMIN", "EMPLOYEE"] = "EMPLOYEE"
    consumes_seat: bool = True


class OrgMemberStatusUpdate(BaseModel):
    status: Literal["active", "disabled"]


class OrgMemberInviteAccept(BaseModel):
    token: str
    full_name: Optional[str] = None


class SeatSummary(BaseModel):
    seat_limit: int
    seats_used: int
    seats_remaining: int
    plan_name: Optional[str] = None
    plan_status: Optional[str] = None
    plan_type: Optional[str] = None
    billing_period: Optional[str] = None
    trial_ends_at: Optional[datetime] = None
