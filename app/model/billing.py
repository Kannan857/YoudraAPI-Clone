from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, EmailStr, Field
from app.model.org_member import OrgMemberSummary


class BillingAccountSummary(BaseModel):
    account_id: UUID
    status: str
    stripe_customer_id: Optional[str] = None

    class Config:
        from_attributes = True


class PlanSummary(BaseModel):
    purchase_id: UUID
    plan_id: Optional[UUID] = None
    plan_code: Optional[str] = None
    plan_name: Optional[str] = None
    is_trial: bool
    status: str
    seat_limit: int
    unit_amount_cents: int
    currency: str
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    current_period_start: Optional[datetime] = None
    current_period_end: Optional[datetime] = None
    custom_seat_count: Optional[int] = None
    custom_unit_amount_cents: Optional[int] = None

    class Config:
        from_attributes = True


class OrganizationBase(BaseModel):
    name: str
    slug: Optional[str] = None
    primary_email: Optional[EmailStr] = None
    primary_phone: Optional[str] = None


class OrganizationAdminInvite(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None


class OrganizationCreate(OrganizationBase):
    owner_user_id: Optional[UUID] = None
    org_admins: Optional[List[OrganizationAdminInvite]] = None


class OrganizationUpdate(BaseModel):
    name: Optional[str] = None
    primary_email: Optional[EmailStr] = None
    primary_phone: Optional[str] = None
    status: Optional[str] = None  # e.g. active / suspended
    org_admins: Optional[List[OrganizationAdminInvite]] = None  # additional invites


class OrganizationDetail(BaseModel):
    org_id: UUID
    name: str
    slug: Optional[str] = None
    primary_email: Optional[EmailStr] = None
    primary_phone: Optional[str] = None
    status: str
    owner_user_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    billing_account: Optional[BillingAccountSummary] = None
    current_plan: Optional[PlanSummary] = None

    class Config:
        from_attributes = True


class OrganizationListItem(BaseModel):
    org_id: UUID
    name: str
    slug: Optional[str] = None
    status: str
    owner_user_id: Optional[UUID] = None
    created_at: datetime

    class Config:
        from_attributes = True


class OrganizationListOverview(BaseModel):
    org_id: UUID
    name: str
    slug: Optional[str] = None
    status: str
    owner_user_id: Optional[UUID] = None
    created_at: datetime
    plan_name: Optional[str] = None
    plan_type: Optional[str] = None
    billing_period: Optional[str] = None
    plan_status: Optional[str] = None
    seat_limit: Optional[int] = None
    seats_used: Optional[int] = None
    trial_ends_at: Optional[datetime] = None
    primary_contact_email: Optional[EmailStr] = None
    role_for_current_user: str

    class Config:
        from_attributes = True


class SeatUsageSummary(BaseModel):
    seat_limit: int
    seats_used: int
    seats_remaining: int
    plan_name: Optional[str] = None
    plan_status: Optional[str] = None
    plan_type: Optional[str] = None
    billing_period: Optional[str] = None
    trial_ends_at: Optional[datetime] = None


class TrialInfo(BaseModel):
    start_date: datetime
    end_date: datetime
    days_total: int
    days_remaining: int


class CurrentPeriodInfo(BaseModel):
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


class BillingSummary(BaseModel):
    org_id: UUID
    org_name: str

    billing_account: Optional["BillingAccountSummary"] = None
    plan: Optional["PlanSummary"] = None

    # Extra computed info to make the UI easy
    trial: Optional[TrialInfo] = None
    current_period: Optional[CurrentPeriodInfo] = None
    seat_summary: Optional[SeatUsageSummary] = None

    class Config:
        from_attributes = True

class BillingUpgradeRequest(BaseModel):
    plan_code: str
    success_url: AnyHttpUrl
    cancel_url: AnyHttpUrl
    seat_quantity: int = 1


class CustomPlanCheckoutRequest(BaseModel):
    seat_count: int = Field(..., ge=1, le=1000)
    success_url: AnyHttpUrl
    cancel_url: AnyHttpUrl


class CheckoutSessionResponse(BaseModel):
    checkout_url: str
    session_id: str


class OrganizationOverview(BaseModel):
    organization: OrganizationDetail
    billing: Optional[BillingSummary] = None
    members: List[OrgMemberSummary] = []
    seat_summary: Optional[SeatUsageSummary] = None
