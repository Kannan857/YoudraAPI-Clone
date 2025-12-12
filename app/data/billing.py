from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    text,
    Boolean,
    Integer
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import relationship, selectinload
from sqlalchemy.sql import func

from app.data.dbinit import Base
from app.common.exception import GeneralDataException, IntegrityException


# ----------------------------------------------------------------------
# Organization
# ----------------------------------------------------------------------


class Organization(Base):
    """Represents a B2B organization/tenant that can later own billing accounts."""
    __tablename__ = "organization"

    org_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    # Core identity
    name = Column(String, nullable=False)
    slug = Column(String, nullable=True, unique=True)

    # Contact / ownership
    # links to dreav_user.user_id (or whatever your user table is called)
    owner_user_id = Column(UUID(as_uuid=True), nullable=True)
    primary_email = Column(String, nullable=True)
    primary_phone = Column(String, nullable=True)

    # Status lifecycle
    status = Column(String, nullable=False, default="active")

    # Extra metadata for arbitrary JSON payloads (billing notes, address, etc.)
    metadata_json = Column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


async def create_organization(
    db: AsyncSession,
    *,
    name: str,
    slug: Optional[str] = None,
    owner_user_id: Optional[uuid.UUID] = None,
    primary_email: Optional[str] = None,
    primary_phone: Optional[str] = None,
    status: str = "active",
    metadata_json: Optional[Dict[str, Any]] = None,
) -> Organization:
    """Insert a new organization row."""
    try:
        org = Organization(
            name=name,
            slug=slug,
            owner_user_id=owner_user_id,
            primary_email=primary_email,
            primary_phone=primary_phone,
            status=status,
            metadata_json=metadata_json or {},
        )
        db.add(org)
        await db.flush()
        await db.refresh(org)
        return org
    except IntegrityException as exc:
        await db.rollback()
        raise IntegrityException(
            "Integrity error when inserting organization",
            context={"detail": str(exc)},
        ) from exc
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        raise GeneralDataException(
            "Unexpected error when inserting organization",
            context={"detail": str(exc)},
        ) from exc


async def get_organization(
    db: AsyncSession,
    org_id: uuid.UUID,
) -> Optional[Organization]:
    """Fetch a single organization by primary key."""
    result = await db.execute(
        select(Organization).where(Organization.org_id == org_id)
    )
    return result.scalar_one_or_none()


async def get_organization_by_slug(
    db: AsyncSession,
    slug: str,
) -> Optional[Organization]:
    """Fetch a single organization by slug."""
    result = await db.execute(
        select(Organization).where(Organization.slug == slug)
    )
    return result.scalar_one_or_none()


async def list_organizations(
    db: AsyncSession,
    status: Optional[str] = None,
) -> List[Organization]:
    """Return all orgs, optionally filtered by status."""
    stmt = select(Organization).order_by(Organization.created_at.desc())
    if status:
        stmt = stmt.where(Organization.status == status)
    result = await db.execute(stmt)
    return result.scalars().all()


async def update_organization(
    db: AsyncSession,
    org_id: uuid.UUID,
    values: Dict[str, Any],
) -> Optional[Organization]:
    """Update fields on an organization and return the refreshed row."""
    org = await get_organization(db, org_id)
    if not org:
        return None

    for key, value in values.items():
        if hasattr(org, key) and value is not None:
            setattr(org, key, value)

    try:
        await db.flush()
        await db.refresh(org)
        return org
    except IntegrityException as exc:
        await db.rollback()
        raise IntegrityException(
            "Integrity error when updating organization",
            context={"detail": str(exc)},
        ) from exc
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        raise GeneralDataException(
            "Unexpected error when updating organization",
            context={"detail": str(exc)},
        ) from exc


# ----------------------------------------------------------------------
# BillingAccount
# ----------------------------------------------------------------------


class BillingAccount(Base):
    """
    Represents the billing identity for an organization.
    Maps (for now) 1:1 to a Stripe Customer (stripe_customer_id).
    """
    __tablename__ = "billing_account"
    __table_args__ = (
        UniqueConstraint("org_id", name="uq_billing_account_org_id"),
    )

    account_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    # Link back to Organization
    org_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organization.org_id"),
        nullable=False,
        index=True,
    )

    # Denormalized copy of org name for convenience/reporting
    org_name = Column(String, nullable=False)

    primary_contact_name = Column(String, nullable=True)
    primary_contact_email = Column(String, nullable=True)

    # Stripe customer this billing account maps to (cus_...)
    stripe_customer_id = Column(String, nullable=True, unique=True)

    # Billing lifecycle status for this account
    status = Column(String, nullable=False, default="active")  # active/trial/suspended/etc.

    metadata_json = Column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # ORM relationship back to org (optional but handy)
    organization = relationship(
        "Organization",
        backref="billing_account",
        uselist=False,
    )


# ----------------------------------------------------------------------
# BillingAccount helpers
# ----------------------------------------------------------------------


async def get_billing_account(
    db: AsyncSession,
    account_id: uuid.UUID,
) -> Optional[BillingAccount]:
    """Fetch a billing account by its primary key."""
    result = await db.execute(
        select(BillingAccount).where(BillingAccount.account_id == account_id)
    )
    return result.scalar_one_or_none()


async def get_billing_account_by_org_id(
    db: AsyncSession,
    org_id: uuid.UUID,
) -> Optional[BillingAccount]:
    """Fetch the billing account for a given organization (1:1 mapping)."""
    result = await db.execute(
        select(BillingAccount).where(BillingAccount.org_id == org_id)
    )
    return result.scalar_one_or_none()


async def create_billing_account(
    db: AsyncSession,
    *,
    organization: Organization,
    primary_contact_name: Optional[str] = None,
    primary_contact_email: Optional[str] = None,
    status: str = "active",
    metadata_json: Optional[Dict[str, Any]] = None,
) -> BillingAccount:
    """
    Create a billing account row for an organization.

    NOTE: This does NOT call Stripe – it only creates a row in your DB.
    Creating the Stripe Customer and populating `stripe_customer_id` should
    be done in a separate Stripe service layer.
    """
    try:
        billing = BillingAccount(
            org_id=organization.org_id,
            org_name=organization.name,
            primary_contact_name=primary_contact_name,
            primary_contact_email=primary_contact_email or organization.primary_email,
            status=status,
            metadata_json=metadata_json or {},
        )
        db.add(billing)
        await db.flush()
        await db.refresh(billing)
        return billing
    except IntegrityException as exc:
        await db.rollback()
        raise IntegrityException(
            "Integrity error when inserting billing account",
            context={"detail": str(exc)},
        ) from exc
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        raise GeneralDataException(
            "Unexpected error when inserting billing account",
            context={"detail": str(exc)},
        ) from exc


async def ensure_billing_account_for_org(
    db: AsyncSession,
    organization: Organization,
) -> BillingAccount:
    """
    Get the billing account for an org, or create one if it doesn't exist.

    This is typically called from your Billing/Upgrade flows:
    - Resolve org from auth
    - Call ensure_billing_account_for_org(...)
    - Then, in a separate Stripe service, ensure a Stripe customer exists
      and fill in `stripe_customer_id`.
    """
    billing = await get_billing_account_by_org_id(db, organization.org_id)
    if billing:
        return billing

    return await create_billing_account(
        db,
        organization=organization,
        primary_contact_name=None,
        primary_contact_email=organization.primary_email,
    )


async def update_billing_account(
    db: AsyncSession,
    account_id: uuid.UUID,
    values: Dict[str, Any],
) -> Optional[BillingAccount]:
    """Update fields on a billing account and return the refreshed row."""
    billing = await get_billing_account(db, account_id)
    if not billing:
        return None

    for key, value in values.items():
        if hasattr(billing, key) and value is not None:
            setattr(billing, key, value)

    try:
        await db.flush()
        await db.refresh(billing)
        return billing
    except IntegrityException as exc:
        await db.rollback()
        raise IntegrityException(
            "Integrity error when updating billing account",
            context={"detail": str(exc)},
        ) from exc
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        raise GeneralDataException(
            "Unexpected error when updating billing account",
            context={"detail": str(exc)},
        ) from exc


class SubscriptionPlan(Base):
    __tablename__ = "subscription_plan"

    plan_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    code = Column(String, nullable=False, unique=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)

    plan_type = Column(String, nullable=False, default="recurring")
    billing_cycle = Column(String, nullable=False)

    amount_cents = Column(Integer, nullable=False)
    currency = Column(String, nullable=False, default="usd")

    seat_limit = Column(Integer, nullable=False)
    extra_seat_price_cents = Column(Integer, nullable=True)

    max_cycles_per_year = Column(Integer, nullable=True)
    max_active_reviews = Column(Integer, nullable=True)
    includes_external_reviewers = Column(Boolean, nullable=False, default=True)

    # NEW – trial flags
    is_trial = Column(Boolean, nullable=False, default=False)
    trial_days = Column(Integer, nullable=True)

    # Stripe linkage – can be NULL for free trial / internal plans
    stripe_price_id = Column(String, nullable=True, unique=True)

    is_active = Column(Boolean, nullable=False, default=True)

    metadata_json = Column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

# ----------------------------------------------------------------------
# SubscriptionPlan helpers
# ----------------------------------------------------------------------


async def get_subscription_plan(
    db: AsyncSession,
    plan_id: uuid.UUID,
) -> Optional[SubscriptionPlan]:
    """Fetch a subscription plan by its primary key."""
    result = await db.execute(
        select(SubscriptionPlan).where(SubscriptionPlan.plan_id == plan_id)
    )
    return result.scalar_one_or_none()


async def get_subscription_plan_by_code(
    db: AsyncSession,
    code: str,
) -> Optional[SubscriptionPlan]:
    """Fetch a subscription plan using its code (e.g. 'STARTER_25_MONTHLY')."""
    result = await db.execute(
        select(SubscriptionPlan).where(SubscriptionPlan.code == code)
    )
    return result.scalar_one_or_none()


async def list_subscription_plans(
    db: AsyncSession,
    *,
    only_active: bool = True,
    include_trials: bool = True,
) -> List[SubscriptionPlan]:
    """
    List plans, optionally:
    - only_active: filter to plans that are currently active
    - include_trials: include/exclude trial plans (is_trial = True)
    """
    stmt = select(SubscriptionPlan).order_by(SubscriptionPlan.amount_cents.asc())

    if only_active:
        stmt = stmt.where(SubscriptionPlan.is_active.is_(True))
    if not include_trials:
        stmt = stmt.where(SubscriptionPlan.is_trial.is_(False))

    result = await db.execute(stmt)
    return result.scalars().all()


async def get_default_trial_plan(
    db: AsyncSession,
) -> Optional[SubscriptionPlan]:
    """
    Convenience helper: fetch a default trial plan.
    If you ever have more than one trial plan, you can refine this (e.g. by code).
    """
    result = await db.execute(
        select(SubscriptionPlan)
        .where(SubscriptionPlan.is_trial.is_(True))
        .where(SubscriptionPlan.is_active.is_(True))
        .order_by(SubscriptionPlan.created_at.asc())
    )
    return result.scalar_one_or_none()


async def create_subscription_plan(
    db: AsyncSession,
    *,
    code: str,
    name: str,
    description: Optional[str],
    plan_type: str,
    billing_cycle: str,
    amount_cents: int,
    currency: str,
    seat_limit: int,
    extra_seat_price_cents: Optional[int],
    max_cycles_per_year: Optional[int],
    max_active_reviews: Optional[int],
    includes_external_reviewers: bool,
    # trial-related
    is_trial: bool = False,
    trial_days: Optional[int] = None,
    # Stripe linkage (can be None for free/trial/internal plans)
    stripe_price_id: Optional[str],
    metadata_json: Optional[Dict[str, Any]] = None,
    is_active: bool = True,
) -> SubscriptionPlan:
    """
    Insert a new subscription plan row.

    For a free trial plan:
    - set is_trial=True
    - set trial_days (e.g. 14)
    - set amount_cents=0
    - set stripe_price_id=None

    For a paid Stripe-backed plan:
    - set is_trial=False
    - set trial_days=None
    - set stripe_price_id to the 'price_...' from Stripe
    """
    # Basic sanity: if it's a trial, amount should typically be 0
    if is_trial and amount_cents != 0:
        raise GeneralDataException(
            "Trial plans should have amount_cents = 0",
            context={"code": code, "amount_cents": amount_cents},
        )

    # If not a trial but trial_days is provided, we can allow it (e.g. paid plan with Stripe trial),
    # or you can choose to enforce trial_days is None for non-trial plans.

    try:
        plan = SubscriptionPlan(
            code=code,
            name=name,
            description=description,
            plan_type=plan_type,
            billing_cycle=billing_cycle,
            amount_cents=amount_cents,
            currency=currency,
            seat_limit=seat_limit,
            extra_seat_price_cents=extra_seat_price_cents,
            max_cycles_per_year=max_cycles_per_year,
            max_active_reviews=max_active_reviews,
            includes_external_reviewers=includes_external_reviewers,
            is_trial=is_trial,
            trial_days=trial_days,
            stripe_price_id=stripe_price_id,
            is_active=is_active,
            metadata_json=metadata_json or {},
        )
        db.add(plan)
        await db.flush()
        await db.refresh(plan)
        return plan
    except IntegrityException as exc:
        await db.rollback()
        raise IntegrityException(
            "Integrity error when inserting subscription plan",
            context={"detail": str(exc)},
        ) from exc
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        raise GeneralDataException(
            "Unexpected error when inserting subscription plan",
            context={"detail": str(exc)},
        ) from exc


async def update_subscription_plan(
    db: AsyncSession,
    plan_id: uuid.UUID,
    values: Dict[str, Any],
) -> Optional[SubscriptionPlan]:
    """Update fields on a subscription plan and return the refreshed row."""
    plan = await get_subscription_plan(db, plan_id)
    if not plan:
        return None

    for key, value in values.items():
        if hasattr(plan, key) and value is not None:
            setattr(plan, key, value)

    try:
        await db.flush()
        await db.refresh(plan)
        return plan
    except IntegrityException as exc:
        await db.rollback()
        raise IntegrityException(
            "Integrity error when updating subscription plan",
            context={"detail": str(exc)},
        ) from exc
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        raise GeneralDataException(
            "Unexpected error when updating subscription plan",
            context={"detail": str(exc)},
        ) from exc


# ----------------------------------------------------------------------
# PlanPurchase – an organization's actual subscription/trial
# ----------------------------------------------------------------------


class PlanPurchase(Base):
    """
    Represents an organization (via BillingAccount) being on a given SubscriptionPlan.

    Examples:
    - Org's free trial: maps to TRIAL_14D_10_SEATS plan, no Stripe subscription.
    - Org's paid subscription: maps to STARTER_25_MONTHLY plan with a Stripe subscription.
    """

    __tablename__ = "plan_purchase"

    purchase_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    # Who is buying? (B2B account)
    account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("billing_account.account_id"),
        nullable=False,
        index=True,
    )

    # Which catalog plan did they buy?
    plan_id = Column(
        UUID(as_uuid=True),
        ForeignKey("subscription_plan.plan_id"),
        nullable=True,
        index=True,
    )

    # Stripe subscription linkage (for recurring paid plans)
    stripe_subscription_id = Column(String, nullable=True, unique=True)  # "sub_..."

    # Optional: last Stripe invoice id for quick lookup
    stripe_latest_invoice_id = Column(String, nullable=True)
    stripe_price_id = Column(String, nullable=True)

    # Snapshot of key plan values at the time of purchase,
    # so future price changes don't retroactively affect history.
    seat_limit = Column(Integer, nullable=False)          # copied from SubscriptionPlan.seat_limit
    unit_amount_cents = Column(Integer, nullable=False)   # copied from SubscriptionPlan.amount_cents
    currency = Column(String, nullable=False, default="usd")

    # High-level status of this purchase
    # Examples: 'trial_active','trial_expired','active','canceled','past_due','incomplete'
    status = Column(String, nullable=False)

    # Is this purchase a trial?
    is_trial = Column(Boolean, nullable=False, default=False)

    # Period information:
    # - For trial: start_date + end_date = trial window
    # - For paid: current_period_start/end = Stripe subscription billing period
    start_date = Column(DateTime(timezone=True), nullable=True)
    end_date = Column(DateTime(timezone=True), nullable=True)

    current_period_start = Column(DateTime(timezone=True), nullable=True)
    current_period_end = Column(DateTime(timezone=True), nullable=True)

    cancel_at = Column(DateTime(timezone=True), nullable=True)
    cancel_at_period_end = Column(Boolean, nullable=False, default=False)
    custom_seat_count = Column(Integer, nullable=True)
    custom_unit_amount_cents = Column(Integer, nullable=True)

    metadata_json = Column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships (optional but helpful)
    account = relationship("BillingAccount", backref="plan_purchases")
    plan = relationship("SubscriptionPlan", backref="purchases")


# ----------------------------------------------------------------------
# PlanPurchase helpers
# ----------------------------------------------------------------------


async def get_plan_purchase(
    db: AsyncSession,
    purchase_id: uuid.UUID,
) -> Optional[PlanPurchase]:
    """Fetch a plan purchase by its primary key."""
    result = await db.execute(
        select(PlanPurchase).where(PlanPurchase.purchase_id == purchase_id)
    )
    return result.scalar_one_or_none()


async def get_active_plan_purchase_for_account(
    db: AsyncSession,
    account_id: uuid.UUID,
) -> Optional[PlanPurchase]:
    """
    Fetch the current active plan purchase for a billing account.

    You can tweak statuses to what you treat as 'active'.
    """
    result = await db.execute(
        select(PlanPurchase)
        .options(selectinload(PlanPurchase.plan))
        .where(PlanPurchase.account_id == account_id)
        .where(PlanPurchase.status.in_(["trial_active", "active", "past_due"]))
        .order_by(PlanPurchase.created_at.desc())
    )
    return result.scalar_one_or_none()


async def list_plan_purchases_for_account(
    db: AsyncSession,
    account_id: uuid.UUID,
) -> List[PlanPurchase]:
    """List all purchases (history) for a billing account."""
    result = await db.execute(
        select(PlanPurchase)
        .where(PlanPurchase.account_id == account_id)
        .order_by(PlanPurchase.created_at.desc())
    )
    return result.scalars().all()


async def create_plan_purchase(
    db: AsyncSession,
    *,
    account: BillingAccount,
    plan: SubscriptionPlan,
    status: str,
    is_trial: bool,
    start_date: Optional[DateTime] = None,
    end_date: Optional[DateTime] = None,
    current_period_start: Optional[DateTime] = None,
    current_period_end: Optional[DateTime] = None,
    stripe_subscription_id: Optional[str] = None,
    stripe_latest_invoice_id: Optional[str] = None,
    cancel_at: Optional[DateTime] = None,
    cancel_at_period_end: bool = False,
    metadata_json: Optional[Dict[str, Any]] = None,
) -> PlanPurchase:
    """
    Create a new PlanPurchase for a billing account.

    For a free trial:
      - is_trial=True
      - status='trial_active'
      - stripe_subscription_id=None
      - start_date/end_date = trial window

    For a paid Stripe subscription:
      - is_trial=False
      - status='active' (or 'incomplete' until first payment succeeds)
      - stripe_subscription_id='sub_...'
      - current_period_start/end from Stripe subscription
    """
    try:
        purchase = PlanPurchase(
            account_id=account.account_id,
            plan_id=plan.plan_id,
            stripe_subscription_id=stripe_subscription_id,
            stripe_latest_invoice_id=stripe_latest_invoice_id,
            seat_limit=plan.seat_limit,
            unit_amount_cents=plan.amount_cents,
            currency=plan.currency,
            status=status,
            is_trial=is_trial,
            start_date=start_date,
            end_date=end_date,
            current_period_start=current_period_start,
            current_period_end=current_period_end,
            cancel_at=cancel_at,
            cancel_at_period_end=cancel_at_period_end,
            metadata_json=metadata_json or {},
        )
        db.add(purchase)
        await db.flush()
        await db.refresh(purchase)
        return purchase
    except IntegrityException as exc:
        await db.rollback()
        raise IntegrityException(
            "Integrity error when inserting plan purchase",
            context={"detail": str(exc)},
        ) from exc
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        raise GeneralDataException(
            "Unexpected error when inserting plan purchase",
            context={"detail": str(exc)},
        ) from exc


async def update_plan_purchase(
    db: AsyncSession,
    purchase_id: uuid.UUID,
    values: Dict[str, Any],
) -> Optional[PlanPurchase]:
    """Update fields on a plan purchase and return the refreshed row."""
    purchase = await get_plan_purchase(db, purchase_id)
    if not purchase:
        return None

    for key, value in values.items():
        if hasattr(purchase, key) and value is not None:
            setattr(purchase, key, value)

    try:
        await db.flush()
        await db.refresh(purchase)
        return purchase
    except IntegrityException as exc:
        await db.rollback()
        raise IntegrityException(
            "Integrity error when updating plan purchase",
            context={"detail": str(exc)},
        ) from exc
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        raise GeneralDataException(
            "Unexpected error when updating plan purchase",
            context={"detail": str(exc)},
        ) from exc


# ----------------------------------------------------------------------
# PaymentTransaction – Stripe payment / charge events
# ----------------------------------------------------------------------


class PaymentTransaction(Base):
    """
    Represents a Stripe payment-related event (PaymentIntent / Charge),
    optionally tied to a PlanPurchase.
    """

    __tablename__ = "payment_transaction"

    transaction_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("billing_account.account_id"),
        nullable=False,
        index=True,
    )

    purchase_id = Column(
        UUID(as_uuid=True),
        ForeignKey("plan_purchase.purchase_id"),
        nullable=True,
        index=True,
    )

    stripe_payment_intent_id = Column(String, nullable=False)  # "pi_..."
    stripe_charge_id = Column(String, nullable=True)           # "ch_..."
    stripe_invoice_id = Column(String, nullable=True)          # "in_..."

    # 'initial','recurring','one_time','refund'
    kind = Column(String, nullable=False)

    # Stripe PaymentIntent status, e.g. 'succeeded','processing','requires_payment_method'
    status = Column(String, nullable=False)

    amount_cents = Column(Integer, nullable=False)
    currency = Column(String, nullable=False)

    occurred_at = Column(DateTime(timezone=True), nullable=True)

    raw_payload_json = Column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    account = relationship("BillingAccount", backref="payment_transactions")
    purchase = relationship("PlanPurchase", backref="payment_transactions")

# ----------------------------------------------------------------------
# PaymentTransaction helpers
# ----------------------------------------------------------------------


async def create_payment_transaction(
    db: AsyncSession,
    *,
    account: BillingAccount,
    purchase: Optional[PlanPurchase],
    stripe_payment_intent_id: str,
    stripe_charge_id: Optional[str],
    stripe_invoice_id: Optional[str],
    kind: str,
    status: str,
    amount_cents: int,
    currency: str,
    occurred_at,
    raw_payload_json: Dict[str, Any],
) -> PaymentTransaction:
    """Insert a new payment transaction row."""
    try:
        tx = PaymentTransaction(
            account_id=account.account_id,
            purchase_id=purchase.purchase_id if purchase else None,
            stripe_payment_intent_id=stripe_payment_intent_id,
            stripe_charge_id=stripe_charge_id,
            stripe_invoice_id=stripe_invoice_id,
            kind=kind,
            status=status,
            amount_cents=amount_cents,
            currency=currency,
            occurred_at=occurred_at,
            raw_payload_json=raw_payload_json or {},
        )
        db.add(tx)
        await db.flush()
        await db.refresh(tx)
        return tx
    except IntegrityException as exc:
        await db.rollback()
        raise IntegrityException(
            "Integrity error when inserting payment transaction",
            context={"detail": str(exc)},
        ) from exc
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        raise GeneralDataException(
            "Unexpected error when inserting payment transaction",
            context={"detail": str(exc)},
        ) from exc


async def get_payment_transaction_by_pi(
    db: AsyncSession,
    stripe_payment_intent_id: str,
) -> Optional[PaymentTransaction]:
    """Fetch a transaction by its Stripe PaymentIntent id."""
    result = await db.execute(
        select(PaymentTransaction).where(
            PaymentTransaction.stripe_payment_intent_id == stripe_payment_intent_id
        )
    )
    return result.scalar_one_or_none()


# ----------------------------------------------------------------------
# Invoice – mirror of Stripe invoices
# ----------------------------------------------------------------------


class Invoice(Base):
    __tablename__ = "invoice"

    invoice_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("billing_account.account_id"),
        nullable=False,
        index=True,
    )

    purchase_id = Column(
        UUID(as_uuid=True),
        ForeignKey("plan_purchase.purchase_id"),
        nullable=True,
        index=True,
    )

    stripe_invoice_id = Column(String, nullable=False, unique=True)  # "in_..."
    stripe_subscription_id = Column(String, nullable=True)           # "sub_..."

    amount_due_cents = Column(Integer, nullable=False)
    amount_paid_cents = Column(Integer, nullable=False)
    currency = Column(String, nullable=False)

    status = Column(String, nullable=False)  # 'draft','open','paid','void','uncollectible'

    period_start = Column(DateTime(timezone=True), nullable=True)
    period_end = Column(DateTime(timezone=True), nullable=True)

    hosted_invoice_url = Column(String, nullable=True)
    invoice_pdf_url = Column(String, nullable=True)

    raw_payload_json = Column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    account = relationship("BillingAccount", backref="invoices")
    purchase = relationship("PlanPurchase", backref="invoices")

# ----------------------------------------------------------------------
# Invoice helpers
# ----------------------------------------------------------------------


async def upsert_invoice_from_stripe(
    db: AsyncSession,
    *,
    account: BillingAccount,
    purchase: Optional[PlanPurchase],
    stripe_invoice_id: str,
    stripe_subscription_id: Optional[str],
    amount_due_cents: int,
    amount_paid_cents: int,
    currency: str,
    status: str,
    period_start,
    period_end,
    hosted_invoice_url: Optional[str],
    invoice_pdf_url: Optional[str],
    raw_payload_json: Dict[str, Any],
) -> Invoice:
    """
    Create or update an invoice row based on Stripe invoice webhook payload.
    Idempotent on stripe_invoice_id.
    """
    result = await db.execute(
        select(Invoice).where(Invoice.stripe_invoice_id == stripe_invoice_id)
    )
    invoice = result.scalar_one_or_none()

    if invoice is None:
        invoice = Invoice(
            account_id=account.account_id,
            purchase_id=purchase.purchase_id if purchase else None,
            stripe_invoice_id=stripe_invoice_id,
            stripe_subscription_id=stripe_subscription_id,
            amount_due_cents=amount_due_cents,
            amount_paid_cents=amount_paid_cents,
            currency=currency,
            status=status,
            period_start=period_start,
            period_end=period_end,
            hosted_invoice_url=hosted_invoice_url,
            invoice_pdf_url=invoice_pdf_url,
            raw_payload_json=raw_payload_json or {},
        )
        db.add(invoice)
    else:
        invoice.stripe_subscription_id = stripe_subscription_id
        invoice.amount_due_cents = amount_due_cents
        invoice.amount_paid_cents = amount_paid_cents
        invoice.currency = currency
        invoice.status = status
        invoice.period_start = period_start
        invoice.period_end = period_end
        invoice.hosted_invoice_url = hosted_invoice_url
        invoice.invoice_pdf_url = invoice_pdf_url
        invoice.raw_payload_json = raw_payload_json or {}

    await db.flush()
    await db.refresh(invoice)
    return invoice

# ----------------------------------------------------------------------
# WebhookEvent – log + idempotency for Stripe webhooks
# ----------------------------------------------------------------------


class WebhookEvent(Base):
    __tablename__ = "webhook_event"

    event_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    stripe_event_id = Column(String, nullable=False, unique=True)  # "evt_..."
    type = Column(String, nullable=False)                          # "invoice.payment_succeeded", etc.

    processed = Column(Boolean, nullable=False, default=False)
    payload_json = Column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    received_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    processed_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(String, nullable=True)

# ----------------------------------------------------------------------
# WebhookEvent helpers
# ----------------------------------------------------------------------


async def create_webhook_event(
    db: AsyncSession,
    *,
    stripe_event_id: str,
    event_type: str,
    payload_json: Dict[str, Any],
) -> Optional[WebhookEvent]:
    """
    Insert a new webhook event if not already present.
    Returns None if an event with this stripe_event_id already exists.
    """
    existing = await db.execute(
        select(WebhookEvent).where(WebhookEvent.stripe_event_id == stripe_event_id)
    )
    if existing.scalar_one_or_none():
        return None

    evt = WebhookEvent(
        stripe_event_id=stripe_event_id,
        type=event_type,
        payload_json=payload_json or {},
    )
    db.add(evt)
    await db.flush()
    await db.refresh(evt)
    return evt
