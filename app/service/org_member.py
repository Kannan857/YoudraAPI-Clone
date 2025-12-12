from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.billing import BillingAccount, PlanPurchase, Organization
from app.data.org_member import (
    OrgMember,
    count_active_seat_members,
    get_member_by_id,
    get_member_by_token,
    list_members,
)


INVITE_TTL_DAYS = 7


async def _get_billing_account(db: AsyncSession, org_id: UUID) -> BillingAccount:
    account = await db.scalar(select(BillingAccount).where(BillingAccount.org_id == org_id))
    if not account:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Organization is missing a billing account.",
        )
    return account


async def get_active_plan_purchase(db: AsyncSession, org_id: UUID) -> PlanPurchase:
    account = await _get_billing_account(db, org_id)
    purchase = await db.scalar(
        select(PlanPurchase)
        .options(selectinload(PlanPurchase.plan))
        .where(
            PlanPurchase.account_id == account.account_id,
            PlanPurchase.status.in_(["trial_active", "active", "past_due"]),
        )
        .order_by(PlanPurchase.created_at.desc())
    )
    if not purchase:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Organization does not have an active subscription plan.",
        )
    return purchase


async def ensure_seat_capacity(
    db: AsyncSession,
    org_id: UUID,
    *,
    consumes_seat: bool,
    ignore_member_id: Optional[UUID] = None,
) -> None:
    if not consumes_seat:
        return
    purchase = await get_active_plan_purchase(db, org_id)
    seat_limit = purchase.seat_limit or 0
    if seat_limit == 0:
        return
    used = await count_active_seat_members(db, org_id)
    if ignore_member_id:
        current_member = await get_member_by_id(db, org_id, ignore_member_id)
        if current_member and current_member.status == "active" and current_member.consumes_seat:
            used -= 1
    if used >= seat_limit:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Seat limit reached ({seat_limit}). Upgrade your plan to add more employees.",
        )


async def list_org_members(db: AsyncSession, org_id: UUID) -> List[OrgMember]:
    return await list_members(db, org_id)


async def get_org_member_for_user(
    db: AsyncSession,
    org_id: UUID,
    user_id: UUID,
) -> Optional[OrgMember]:
    result = await db.execute(
        select(OrgMember).where(
            OrgMember.org_id == org_id,
            OrgMember.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def create_member_invite(
    db: AsyncSession,
    *,
    org_id: UUID,
    email: str,
    full_name: Optional[str],
    role: str,
    consumes_seat: bool,
    invited_by_user_id: Optional[UUID],
) -> OrgMember:
    await ensure_seat_capacity(db, org_id, consumes_seat=consumes_seat)
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=INVITE_TTL_DAYS)

    member = OrgMember(
        org_id=org_id,
        email=email,
        full_name=full_name,
        role=role,
        status="invited",
        consumes_seat=consumes_seat,
        invite_token=token,
        invite_expires_at=expires_at,
        invited_by_user_id=invited_by_user_id,
    )
    db.add(member)
    await db.flush()
    return member


async def ensure_owner_member(
    db: AsyncSession,
    *,
    org_id: UUID,
    user_id: UUID,
    email: str,
    full_name: Optional[str],
) -> OrgMember:
    existing = await db.scalar(
        select(OrgMember).where(
            OrgMember.org_id == org_id,
            OrgMember.user_id == user_id,
        )
    )
    if existing:
        if existing.status != "active":
            existing.status = "active"
        existing.role = "ORG_ADMIN"
        existing.consumes_seat = True
        existing.email = email
        if full_name:
            existing.full_name = full_name
        await db.flush()
        return existing

    member = OrgMember(
        org_id=org_id,
        user_id=user_id,
        email=email,
        full_name=full_name,
        role="ORG_ADMIN",
        status="active",
        consumes_seat=True,
    )
    db.add(member)
    await db.flush()
    return member


async def accept_invite(
    db: AsyncSession,
    *,
    token: str,
    user_id: UUID,
    full_name: Optional[str],
) -> OrgMember:
    member = await get_member_by_token(db, token)
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite token not found")
    if member.status == "active":
        return member
    if member.invite_expires_at and member.invite_expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invite token has expired")
    await ensure_seat_capacity(
        db,
        member.org_id,
        consumes_seat=member.consumes_seat,
        ignore_member_id=member.member_id,
    )
    member.user_id = user_id
    if full_name:
        member.full_name = full_name
    member.status = "active"
    member.invite_token = None
    member.invite_expires_at = None
    await db.flush()
    return member


async def update_member_status(
    db: AsyncSession,
    *,
    org_id: UUID,
    member_id: UUID,
    status_value: str,
) -> OrgMember:
    member = await get_member_by_id(db, org_id, member_id)
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    if status_value == member.status:
        return member
    if status_value == "active":
        await ensure_seat_capacity(
            db,
            org_id,
            consumes_seat=member.consumes_seat,
            ignore_member_id=member.member_id,
        )
    member.status = status_value
    await db.flush()
    return member


async def get_seat_summary(db: AsyncSession, org_id: UUID) -> dict:
    purchase = await get_active_plan_purchase(db, org_id)
    seat_limit = purchase.seat_limit or 0
    used = await count_active_seat_members(db, org_id)
    plan_obj = purchase.plan
    plan_name = plan_obj.name if plan_obj else None
    plan_status = purchase.status
    plan_type = "trial" if purchase.is_trial else "subscription"
    billing_period = plan_obj.billing_cycle if plan_obj else None
    if purchase.custom_seat_count:
        plan_type = "custom"
        if not plan_name:
            plan_name = f"Custom ({purchase.custom_seat_count} seats)"
        if not billing_period:
            billing_period = "month"
    trial_ends_at = purchase.end_date if purchase.is_trial else None
    return {
        "seat_limit": seat_limit,
        "seats_used": used,
        "seats_remaining": max(seat_limit - used, 0),
        "plan_name": plan_name,
        "plan_status": plan_status,
        "plan_type": plan_type,
        "billing_period": billing_period,
        "trial_ends_at": trial_ends_at,
    }


async def get_org_member_or_404(db: AsyncSession, org_id: UUID, member_id: UUID) -> OrgMember:
    member = await get_member_by_id(db, org_id, member_id)
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    return member


async def list_admin_orgs_for_user(db: AsyncSession, user_id: UUID) -> List[Organization]:
    result = await db.execute(
        select(Organization)
        .join(OrgMember, OrgMember.org_id == Organization.org_id)
        .where(
            OrgMember.user_id == user_id,
            OrgMember.status == "active",
            OrgMember.role == "ORG_ADMIN",
        )
        .order_by(Organization.created_at.asc())
    )
    return result.scalars().all()
