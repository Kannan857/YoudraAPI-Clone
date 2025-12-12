# app/api/routes/organizations.py
from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.service.user import get_current_user
from app.data.dbinit import get_db
from app.data.user import User
from app.data.billing import (
    Organization,
    BillingAccount,
    PlanPurchase,
    SubscriptionPlan,
    get_default_trial_plan,
)
from app.model.billing import (
    BillingAccountSummary,
    OrganizationCreate,
    OrganizationDetail,
    OrganizationListItem,
    OrganizationListOverview,
    OrganizationUpdate,
    PlanSummary,
    OrganizationAdminInvite,
    OrganizationOverview,
    SeatUsageSummary,
)
from app.model.org_member import (
    OrgMemberInviteAccept,
    OrgMemberInviteRequest,
    OrgMemberStatusUpdate,
    OrgMemberSummary,
    SeatSummary,
)
from app.service.billing import (
    build_org_detail,
    get_billing_summary_for_org,
    ensure_platform_admin,
    load_org_with_authorization,
    normalize_slug,
)
from app.service import org_member as member_service

router = APIRouter()


async def _get_billing_account_for_org(db: AsyncSession, org_id: UUID) -> Optional[BillingAccount]:
    result = await db.execute(select(BillingAccount).where(BillingAccount.org_id == org_id))
    return result.scalar_one_or_none()


async def _get_active_plan_for_account(db: AsyncSession, account_id: UUID) -> Optional[PlanPurchase]:
    result = await db.execute(
        select(PlanPurchase)
        .where(PlanPurchase.account_id == account_id)
        .where(PlanPurchase.status.in_(["trial_active", "active", "past_due"]))
        .order_by(PlanPurchase.created_at.desc())
    )
    return result.scalar_one_or_none()


@router.post(
    "/admin/organizations",
    response_model=OrganizationDetail,
    status_code=status.HTTP_201_CREATED,
)
async def create_organization_admin(
    payload: OrganizationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ensure_platform_admin(current_user)

    owner_user_id: UUID
    if payload.owner_user_id:
        owner = await db.scalar(select(User).where(User.user_id == payload.owner_user_id))
        if not owner:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="owner_user_id does not refer to a valid user.",
            )
        if not owner.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="owner_user_id refers to an inactive user.",
            )
        owner_user_id = owner.user_id
        owner_email = owner.email
        owner_full_name = " ".join(filter(None, [owner.first_name, owner.last_name])).strip()
        if not owner_full_name:
            owner_full_name = owner.first_name or owner.email
    else:
        owner_user_id = current_user.user_id
        owner_email = current_user.email
        owner_full_name = " ".join(filter(None, [current_user.first_name, current_user.last_name])).strip()
        if not owner_full_name:
            owner_full_name = current_user.first_name or current_user.email

    slug = normalize_slug(payload.slug or payload.name)

    existing = await db.scalar(select(Organization).where(Organization.slug == slug))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An organization with this slug already exists.",
        )

    primary_email = payload.primary_email or owner_email
    primary_phone = payload.primary_phone
    now = datetime.utcnow()

    try:
        org = Organization(
            name=payload.name,
            slug=slug,
            owner_user_id=owner_user_id,
            primary_email=primary_email,
            primary_phone=primary_phone,
            status="active",
            metadata_json={},
        )
        db.add(org)
        await db.flush()

        billing_account = BillingAccount(
            org_id=org.org_id,
            org_name=org.name,
            primary_contact_name=None,
            primary_contact_email=primary_email,
            status="active",
            stripe_customer_id=None,
            metadata_json={},
        )
        db.add(billing_account)
        await db.flush()

        trial_plan: Optional[SubscriptionPlan] = await get_default_trial_plan(db)
        if trial_plan:
            trial_days = trial_plan.trial_days or 14
            trial_start = now
            trial_end = trial_start + timedelta(days=trial_days)

            trial_purchase = PlanPurchase(
                account_id=billing_account.account_id,
                plan_id=trial_plan.plan_id,
                stripe_subscription_id=None,
                stripe_latest_invoice_id=None,
                seat_limit=trial_plan.seat_limit,
                unit_amount_cents=trial_plan.amount_cents,
                currency=trial_plan.currency,
                status="trial_active",
                is_trial=True,
                start_date=trial_start,
                end_date=trial_end,
                current_period_start=trial_start,
                current_period_end=trial_end,
                cancel_at=None,
                cancel_at_period_end=False,
                metadata_json={},
            )
            db.add(trial_purchase)

        await member_service.ensure_owner_member(
            db,
            org_id=org.org_id,
            user_id=owner_user_id,
            email=primary_email,
            full_name=owner_full_name,
        )

        extra_admins = payload.org_admins or []
        for admin in extra_admins:
            admin_email = admin.email.lower()
            if admin_email == primary_email.lower():
                continue
            await member_service.create_member_invite(
                db,
                org_id=org.org_id,
                email=admin.email,
                full_name=admin.full_name,
                role="ORG_ADMIN",
                consumes_seat=True,
                invited_by_user_id=current_user.user_id,
            )

        await db.commit()
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating organization: {exc}",
        )

    org = await db.scalar(select(Organization).where(Organization.org_id == org.org_id))
    return await build_org_detail(db, org)


@router.get("/organizations/current", response_model=OrganizationDetail)
async def get_current_organization(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Organization)
        .where(Organization.owner_user_id == current_user.user_id)
        .order_by(Organization.created_at.asc())
    )
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No organization found for this user.",
        )
    return await build_org_detail(db, org)


@router.get("/organizations/my", response_model=List[OrganizationListOverview])
async def list_organizations_for_current_user(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    is_platform_admin = getattr(current_user, "is_platform_admin", False)
    if is_platform_admin:
        result = await db.execute(select(Organization).order_by(Organization.created_at.asc()))
        orgs = result.scalars().all()
    else:
        orgs = await member_service.list_admin_orgs_for_user(db, current_user.user_id)

    entries: List[OrganizationListOverview] = []
    for org in orgs:
        seat_summary = await member_service.get_seat_summary(db, org.org_id)
        if is_platform_admin:
            role = "PLATFORM_ADMIN"
        elif org.owner_user_id and org.owner_user_id == current_user.user_id:
            role = "OWNER"
        else:
            member = await member_service.get_org_member_for_user(db, org.org_id, current_user.user_id)
            role = member.role if member else "MEMBER"

        entries.append(
            OrganizationListOverview(
                org_id=org.org_id,
                name=org.name,
                slug=org.slug,
                status=org.status,
                owner_user_id=org.owner_user_id,
                created_at=org.created_at,
                plan_name=seat_summary.get("plan_name"),
                plan_type=seat_summary.get("plan_type"),
                billing_period=seat_summary.get("billing_period"),
                plan_status=seat_summary.get("plan_status"),
                seat_limit=seat_summary.get("seat_limit"),
                seats_used=seat_summary.get("seats_used"),
                trial_ends_at=seat_summary.get("trial_ends_at"),
                primary_contact_email=org.primary_email,
                role_for_current_user=role,
            )
        )

    return entries



@router.get("/organizations/{org_id}", response_model=OrganizationDetail)
async def get_organization_by_id(
    org_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org = await load_org_with_authorization(
        db,
        org_id=org_id,
        current_user=current_user,
        allow_platform_admin=True,
        allow_owner=True,
    )
    return await build_org_detail(db, org)


@router.get("/organizations/{org_id}/overview", response_model=OrganizationOverview)
async def get_organization_overview(
    org_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org = await load_org_with_authorization(
        db,
        org_id=org_id,
        current_user=current_user,
        allow_platform_admin=True,
        allow_owner=True,
        allow_org_admin=True,
    )
    org_detail = await build_org_detail(db, org)
    billing_summary = await get_billing_summary_for_org(db, org)
    members = await member_service.list_org_members(db, org_id)
    seat_usage_data = await member_service.get_seat_summary(db, org_id)
    seat_usage_model = SeatUsageSummary(**seat_usage_data)
    if billing_summary:
        billing_summary = billing_summary.model_copy(update={"seat_summary": seat_usage_model})
    return OrganizationOverview(
        organization=org_detail,
        billing=billing_summary,
        members=members,
        seat_summary=seat_usage_model,
    )





@router.get("/admin/organizations", response_model=List[OrganizationListItem])
async def list_organizations_admin(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ensure_platform_admin(current_user)
    result = await db.execute(select(Organization).order_by(Organization.created_at.desc()))
    orgs = result.scalars().all()
    return [
        OrganizationListItem(
            org_id=o.org_id,
            name=o.name,
            slug=o.slug,
            status=o.status,
            owner_user_id=o.owner_user_id,
            created_at=o.created_at,
        )
        for o in orgs
    ]




@router.patch("/organizations/{org_id}", response_model=OrganizationDetail)
async def update_organization(
    org_id: UUID,
    payload: OrganizationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org = await load_org_with_authorization(
        db,
        org_id=org_id,
        current_user=current_user,
        allow_platform_admin=True,
        allow_owner=True,
    )
    is_platform_admin = getattr(current_user, "is_platform_admin", False)

    if payload.name is not None:
        org.name = payload.name
    if payload.primary_email is not None:
        org.primary_email = payload.primary_email
    if payload.primary_phone is not None:
        org.primary_phone = payload.primary_phone
    if payload.status is not None:
        if not is_platform_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only platform admins can change organization status.",
            )
        org.status = payload.status

    try:
        extra_admins = payload.org_admins or []
        primary_email_lower = (org.primary_email or "").lower()
        for admin in extra_admins:
            admin_email_lower = admin.email.lower()
            if primary_email_lower and admin_email_lower == primary_email_lower:
                continue
            await member_service.create_member_invite(
                db,
                org_id=org.org_id,
                email=admin.email,
                full_name=admin.full_name,
                role="ORG_ADMIN",
                consumes_seat=True,
                invited_by_user_id=current_user.user_id,
            )
        await db.flush()
        await db.commit()
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating organization: {exc}",
        )

    org = await db.scalar(select(Organization).where(Organization.org_id == org.org_id))
    return await build_org_detail(db, org)


@router.get(
    "/organizations/{org_id}/members",
    response_model=List[OrgMemberSummary],
)
async def list_org_members_endpoint(
    org_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await load_org_with_authorization(
        db,
        org_id=org_id,
        current_user=current_user,
        allow_platform_admin=True,
        allow_owner=True,
        allow_org_admin=True,
    )
    members = await member_service.list_org_members(db, org_id)
    return members


@router.post(
    "/organizations/{org_id}/members",
    response_model=OrgMemberSummary,
    status_code=status.HTTP_201_CREATED,
)
async def invite_org_member(
    org_id: UUID,
    payload: OrgMemberInviteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await load_org_with_authorization(
        db,
        org_id=org_id,
        current_user=current_user,
        allow_platform_admin=True,
        allow_owner=True,
        allow_org_admin=True,
    )
    member = await member_service.create_member_invite(
        db,
        org_id=org_id,
        email=payload.email,
        full_name=payload.full_name,
        role=payload.role,
        consumes_seat=payload.consumes_seat,
        invited_by_user_id=current_user.user_id,
    )
    return member


@router.get(
    "/organizations/{org_id}/seat-summary",
    response_model=SeatSummary,
)
async def get_seat_summary(
    org_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await load_org_with_authorization(
        db,
        org_id=org_id,
        current_user=current_user,
        allow_platform_admin=True,
        allow_owner=True,
        allow_org_admin=True,
    )
    summary = await member_service.get_seat_summary(db, org_id)
    return SeatSummary(**summary)


@router.patch(
    "/organizations/{org_id}/members/{member_id}",
    response_model=OrgMemberSummary,
)
async def update_org_member_status(
    org_id: UUID,
    member_id: UUID,
    payload: OrgMemberStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await load_org_with_authorization(
        db,
        org_id=org_id,
        current_user=current_user,
        allow_platform_admin=True,
        allow_owner=True,
        allow_org_admin=True,
    )
    new_status = payload.status
    if new_status not in {"active", "disabled"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status.")
    member = await member_service.update_member_status(
        db,
        org_id=org_id,
        member_id=member_id,
        status_value=new_status,
    )
    return member


@router.post(
    "/organizations/members/accept",
    response_model=OrgMemberSummary,
)
async def accept_org_invite(
    payload: OrgMemberInviteAccept,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    member = await member_service.accept_invite(
        db,
        token=payload.token,
        user_id=current_user.user_id,
        full_name=payload.full_name,
    )
    return member
