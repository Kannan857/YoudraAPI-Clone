from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.data.billing import (
    BillingAccount,
    Organization,
    PlanPurchase,
    SubscriptionPlan,
    WebhookEvent,
    Invoice,
    PaymentTransaction,
    upsert_invoice_from_stripe,
    create_payment_transaction,
    get_payment_transaction_by_pi,
)
from app.data.org_member import OrgMember

from app.data.user import User
from app.model.billing import (
    BillingAccountSummary,
    BillingSummary,
    CurrentPeriodInfo,
    PlanSummary,
    TrialInfo,
    OrganizationDetail,
)


def normalize_slug(raw: str) -> str:
    """
    Simple slugify helper. Lowercases the input, replaces non-alphanumeric
    sequences with '-', and trims leading/trailing dashes.
    """
    slug = raw.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug


def ensure_platform_admin(current_user: User) -> None:
    """
    Raise 403 if the current user is not marked as a platform admin.
    """
    if not getattr(current_user, "is_platform_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only platform admins can perform this action.",
        )


async def load_org_with_authorization(
    db: AsyncSession,
    org_id: UUID,
    current_user: User,
    allow_platform_admin: bool = True,
    allow_owner: bool = True,
    allow_org_admin: bool = False,
) -> Organization:
    """
    Fetch an organization and ensure the caller may access it.
    Platform admins always pass if allow_platform_admin=True.
    The org owner passes when allow_owner=True.
    """
    result = await db.execute(select(Organization).where(Organization.org_id == org_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    is_platform_admin = getattr(current_user, "is_platform_admin", False)
    is_owner = bool(org.owner_user_id and org.owner_user_id == current_user.user_id)
    is_org_admin = False
    if allow_org_admin and not (is_platform_admin or is_owner):
        member = await db.scalar(
            select(OrgMember).where(
                OrgMember.org_id == org_id,
                OrgMember.user_id == current_user.user_id,
                OrgMember.status == "active",
                OrgMember.role.in_(["ORG_ADMIN"]),
            )
        )
        is_org_admin = member is not None

    if not (
        (allow_platform_admin and is_platform_admin)
        or (allow_owner and is_owner)
        or (allow_org_admin and is_org_admin)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not allowed to access this organization.",
        )

    return org


async def get_billing_account_for_org(
    db: AsyncSession,
    org_id: UUID,
) -> Optional[BillingAccount]:
    result = await db.execute(
        select(BillingAccount).where(BillingAccount.org_id == org_id)
    )
    return result.scalar_one_or_none()


async def get_active_plan_for_account(db: AsyncSession, account_id: UUID) -> Optional[PlanPurchase]:
    result = await db.execute(
        select(PlanPurchase)
        .options(joinedload(PlanPurchase.plan))  # eager load subscription plan
        .where(PlanPurchase.account_id == account_id)
        .where(PlanPurchase.status.in_(["trial_active", "active", "past_due"]))
        .order_by(PlanPurchase.created_at.desc())
    )
    return result.scalar_one_or_none()


async def build_org_detail(
    db: AsyncSession,
    org: Organization,
) -> OrganizationDetail:
    """
    Compose the OrganizationDetail response, including billing account and
    currently-active plan summary if present.
    """
    billing_account = await get_billing_account_for_org(db, org.org_id)

    billing_summary: Optional[BillingAccountSummary] = None
    plan_summary: Optional[PlanSummary] = None

    if billing_account:
        billing_summary = BillingAccountSummary.from_orm(billing_account)

        current_purchase = await get_active_plan_for_account(db, billing_account.account_id)

        if current_purchase:
            plan_obj = current_purchase.plan
            custom_label = None
            custom_code = None
            if not plan_obj and current_purchase.custom_seat_count:
                custom_label = f"Custom ({current_purchase.custom_seat_count} seats)"
                custom_code = "CUSTOM"
            plan_summary = PlanSummary(
                purchase_id=current_purchase.purchase_id,
                plan_id=plan_obj.plan_id if plan_obj else None,
                plan_code=plan_obj.code if plan_obj else custom_code,
                plan_name=plan_obj.name if plan_obj else custom_label,
                is_trial=current_purchase.is_trial,
                status=current_purchase.status,
                seat_limit=current_purchase.seat_limit,
                unit_amount_cents=current_purchase.unit_amount_cents,
                currency=current_purchase.currency,
                start_date=current_purchase.start_date,
                end_date=current_purchase.end_date,
                current_period_start=current_purchase.current_period_start,
                current_period_end=current_purchase.current_period_end,
                custom_seat_count=current_purchase.custom_seat_count,
                custom_unit_amount_cents=current_purchase.custom_unit_amount_cents,
            )

    return OrganizationDetail(
        org_id=org.org_id,
        name=org.name,
        slug=org.slug,
        primary_email=org.primary_email,
        primary_phone=org.primary_phone,
        status=org.status,
        owner_user_id=org.owner_user_id,
        created_at=org.created_at,
        updated_at=org.updated_at,
        billing_account=billing_summary,
        current_plan=plan_summary,
    )


async def get_billing_summary_for_org(
    db: AsyncSession,
    org: Organization,
) -> BillingSummary:
    """
    Build a billing summary for the given organization:
    - BillingAccount
    - Current plan (trial or paid)
    - Trial / current period info
    """
    billing_account = await get_billing_account_for_org(db, org.org_id)

    if not billing_account:
        return BillingSummary(
            org_id=org.org_id,
            org_name=org.name,
            billing_account=None,
            plan=None,
            trial=None,
            current_period=None,
        )

    billing_summary = BillingAccountSummary.model_validate(
        billing_account,
        from_attributes=True,
    )

    current_purchase = await get_active_plan_for_account(
        db, billing_account.account_id
    )
    if not current_purchase:
        return BillingSummary(
            org_id=org.org_id,
            org_name=org.name,
            billing_account=billing_summary,
            plan=None,
            trial=None,
            current_period=None,
        )

    plan_obj = current_purchase.plan
    custom_label = None
    custom_code = None
    if not plan_obj and current_purchase.custom_seat_count:
        custom_label = f"Custom ({current_purchase.custom_seat_count} seats)"
        custom_code = "CUSTOM"
    plan_summary = PlanSummary(
        purchase_id=current_purchase.purchase_id,
        plan_id=plan_obj.plan_id if plan_obj else None,
        plan_code=plan_obj.code if plan_obj else custom_code,
        plan_name=plan_obj.name if plan_obj else custom_label,
        is_trial=current_purchase.is_trial,
        status=current_purchase.status,
        seat_limit=current_purchase.seat_limit,
        unit_amount_cents=current_purchase.unit_amount_cents,
        currency=current_purchase.currency,
        start_date=current_purchase.start_date,
        end_date=current_purchase.end_date,
        current_period_start=current_purchase.current_period_start,
        current_period_end=current_purchase.current_period_end,
        custom_seat_count=current_purchase.custom_seat_count,
        custom_unit_amount_cents=current_purchase.custom_unit_amount_cents,
    )

    trial_info: Optional[TrialInfo] = None
    current_period_info: Optional[CurrentPeriodInfo] = None

    now = datetime.now(timezone.utc)

    if current_purchase.is_trial:
        if current_purchase.start_date and current_purchase.end_date:
            total_days = (
                current_purchase.end_date - current_purchase.start_date
            ).days
            remaining_days = max(
                0,
                (current_purchase.end_date - now).days
                if current_purchase.end_date.tzinfo
                else (current_purchase.end_date.replace(tzinfo=timezone.utc) - now).days,
            )
            trial_info = TrialInfo(
                start_date=current_purchase.start_date,
                end_date=current_purchase.end_date,
                days_total=total_days,
                days_remaining=remaining_days,
            )
    else:
        if (
            current_purchase.current_period_start
            and current_purchase.current_period_end
        ):
            current_period_info = CurrentPeriodInfo(
                start_date=current_purchase.current_period_start,
                end_date=current_purchase.current_period_end,
            )

    return BillingSummary(
        org_id=org.org_id,
        org_name=org.name,
        billing_account=billing_summary,
        plan=plan_summary,
        trial=trial_info,
        current_period=current_period_info,
    )


async def mark_webhook_processed(
    db: AsyncSession,
    webhook: WebhookEvent,
    *,
    success: bool,
    error_message: Optional[str] = None,
) -> None:
    webhook.processed = success
    webhook.error_message = error_message[:500] if error_message else None
    webhook.processed_at = datetime.now(timezone.utc)
    await db.flush()


# -------------------------------------------------------------------------
# Stripe subscription -> PlanPurchase
# -------------------------------------------------------------------------


def _map_stripe_subscription_status(status: str) -> str:
    """
    Map Stripe subscription status to our internal PlanPurchase.status.
    Stripe statuses: 'active', 'trialing', 'past_due', 'canceled',
                     'unpaid', 'incomplete', 'incomplete_expired'
    """
    # For now, just reuse most statuses
    if status == "trialing":
        return "active"  # we track trial via is_trial flag
    if status in {"active", "past_due", "canceled"}:
        return status
    return "incomplete"  # catchall


async def handle_subscription_event(
    db: AsyncSession,
    event: dict,
) -> None:
    """
    Handle Stripe customer.subscription.created / updated / deleted events.
    Creates or updates a non-trial PlanPurchase row.
    """
    obj = event["data"]["object"]

    subscription_id = obj["id"]
    customer_id = obj["customer"]
    stripe_status = obj["status"]

    # Protect against weird events
    if not customer_id:
        return

    # 1) Find billing account by stripe_customer_id
    billing_account = await db.scalar(
        select(BillingAccount).where(BillingAccount.stripe_customer_id == customer_id)
    )
    if not billing_account:
        # No matching billing account, nothing we can do
        return

    # 2) Determine which price/plan this subscription is for (first item)
    items = (obj.get("items") or {}).get("data") or []
    if not items:
        return

    first_item = items[0] or {}
    price = first_item.get("price") or {}
    if not price:
        return

    price_id = price["id"]  # Stripe price ID

    # 3) Find our SubscriptionPlan by stripe_price_id
    plan = await db.scalar(
        select(SubscriptionPlan).where(SubscriptionPlan.stripe_price_id == price_id)
    )

    metadata = obj.get("metadata") or {}
    custom_seat_count = metadata.get("custom_seat_count")
    custom_unit_amount = metadata.get("custom_unit_amount_cents")
    try:
        custom_seat_count = int(custom_seat_count) if custom_seat_count is not None else None
    except (ValueError, TypeError):
        custom_seat_count = None
    try:
        custom_unit_amount = int(custom_unit_amount) if custom_unit_amount is not None else None
    except (ValueError, TypeError):
        custom_unit_amount = None

    currency = price.get("currency") or (plan.currency if plan else "usd")
    seat_limit_value = plan.seat_limit if plan else None
    unit_amount_value = plan.amount_cents if plan else None

    if custom_seat_count and custom_unit_amount:
        seat_limit_value = custom_seat_count
        unit_amount_value = custom_seat_count * custom_unit_amount
    elif seat_limit_value is None or unit_amount_value is None:
        # Without either a catalog plan or custom metadata, we can't proceed
        return

    # 4) Convert timestamps to datetimes, with fallback to item-level period
    def _dt(ts: Optional[int]) -> Optional[datetime]:
        if ts is None:
            return None
        return datetime.fromtimestamp(ts, tz=timezone.utc)

    item_cp_start = first_item.get("current_period_start")
    item_cp_end = first_item.get("current_period_end")

    raw_cp_start = obj.get("current_period_start") or item_cp_start
    raw_cp_end = obj.get("current_period_end") or item_cp_end

    cp_start_dt = _dt(raw_cp_start)
    cp_end_dt = _dt(raw_cp_end)
    start_dt = _dt(obj.get("start_date"))

    internal_status = _map_stripe_subscription_status(stripe_status)

    # 5) Check if we already have a PlanPurchase with this subscription_id
    purchase = await db.scalar(
        select(PlanPurchase).where(
            PlanPurchase.stripe_subscription_id == subscription_id
        )
    )

    if not purchase:
        # Create a new non-trial PlanPurchase
        purchase = PlanPurchase(
            account_id=billing_account.account_id,
            plan_id=plan.plan_id if plan else None,
            stripe_subscription_id=subscription_id,
            stripe_latest_invoice_id=obj.get("latest_invoice"),
            stripe_price_id=price_id,
            seat_limit=seat_limit_value,
            unit_amount_cents=unit_amount_value,
            currency=currency,
            status=internal_status,
            is_trial=False,
            start_date=start_dt,
            end_date=None,
            current_period_start=cp_start_dt,
            current_period_end=cp_end_dt,
            cancel_at=None,
            cancel_at_period_end=False,
            metadata_json=metadata or {},
        )
        purchase.custom_seat_count = custom_seat_count
        purchase.custom_unit_amount_cents = custom_unit_amount
        db.add(purchase)
        await db.flush()

        # Mark any active trial for this account as converted/expired
        trial_purchase = await db.scalar(
            select(PlanPurchase).where(
                PlanPurchase.account_id == billing_account.account_id,
                PlanPurchase.is_trial.is_(True),
                PlanPurchase.status.in_(["trial_active", "active"]),
            )
        )
        if trial_purchase:
            trial_purchase.status = "trial_converted"
            await db.flush()
    else:
        # Update existing purchase
        purchase.status = internal_status
        purchase.current_period_start = cp_start_dt
        purchase.current_period_end = cp_end_dt
        purchase.seat_limit = seat_limit_value
        purchase.unit_amount_cents = unit_amount_value
        purchase.custom_seat_count = custom_seat_count
        purchase.custom_unit_amount_cents = custom_unit_amount
        purchase.currency = currency
        purchase.stripe_price_id = price_id
        latest_invoice = obj.get("latest_invoice")
        if latest_invoice:
            purchase.stripe_latest_invoice_id = latest_invoice
        if metadata:
            purchase.metadata_json = metadata

        # If stripe says canceled, set end_date
        if stripe_status == "canceled" and cp_end_dt:
            purchase.end_date = cp_end_dt

        await db.flush()

    await _backfill_purchase_links(
        db,
        account_id=billing_account.account_id,
        subscription_id=subscription_id,
    )


async def _backfill_purchase_links(
    db: AsyncSession,
    *,
    account_id: UUID,
    subscription_id: Optional[str],
) -> None:
    """
    When invoices/payment transactions arrive before the subscription event,
    attach them retroactively once the PlanPurchase exists.
    """
    if not subscription_id:
        return

    purchase = await db.scalar(
        select(PlanPurchase).where(
            PlanPurchase.account_id == account_id,
            PlanPurchase.stripe_subscription_id == subscription_id,
        )
    )
    if not purchase:
        return

    invoices_result = await db.execute(
        select(Invoice).where(
            Invoice.account_id == purchase.account_id,
            Invoice.stripe_subscription_id == subscription_id,
            Invoice.purchase_id.is_(None),
        )
    )
    invoices = invoices_result.scalars().all()
    if not invoices:
        return

    stripe_invoice_ids: list[str] = []
    payment_intent_ids: list[str] = []

    for invoice in invoices:
        invoice.purchase_id = purchase.purchase_id
        if invoice.stripe_invoice_id:
            stripe_invoice_ids.append(invoice.stripe_invoice_id)
        payload = invoice.raw_payload_json or {}
        pi_id = payload.get("payment_intent")
        if pi_id:
            payment_intent_ids.append(pi_id)

    await db.flush()

    if stripe_invoice_ids:
        await db.execute(
            update(PaymentTransaction)
            .where(
                PaymentTransaction.purchase_id.is_(None),
                PaymentTransaction.stripe_invoice_id.in_(stripe_invoice_ids),
            )
            .values(purchase_id=purchase.purchase_id)
        )

    if payment_intent_ids:
        await db.execute(
            update(PaymentTransaction)
            .where(
                PaymentTransaction.purchase_id.is_(None),
                PaymentTransaction.stripe_payment_intent_id.in_(payment_intent_ids),
            )
            .values(purchase_id=purchase.purchase_id)
        )

    await db.flush()


# -------------------------------------------------------------------------
# Stripe invoice/payment -> Invoice + PaymentTransaction
# -------------------------------------------------------------------------


async def handle_invoice_payment_succeeded(
    db: AsyncSession,
    event: dict,
) -> None:
    """
    Handle invoice.payment_succeeded.
    - Upserts Invoice row
    - Creates PaymentTransaction row
    - Updates PlanPurchase.current_period_* for the paid plan
    """
    invoice_obj = event["data"]["object"]

    stripe_invoice_id = invoice_obj["id"]
    customer_id = invoice_obj.get("customer")
    amount_due = invoice_obj.get("amount_due", 0)
    amount_paid = invoice_obj.get("amount_paid", 0)
    currency = invoice_obj.get("currency", "usd")
    period_start = invoice_obj.get("period_start")
    period_end = invoice_obj.get("period_end")
    status = invoice_obj.get("status", "paid")

    # ---- 1. Find or derive subscription_id ----
    subscription_id: Optional[str] = invoice_obj.get("subscription")

    if not subscription_id:
        try:
            lines = (invoice_obj.get("lines") or {}).get("data") or []
            for line in lines:
                parent = (line or {}).get("parent") or {}
                sub_details = parent.get("subscription_item_details") or {}
                sid = sub_details.get("subscription")
                if sid:
                    subscription_id = sid
                    break
        except Exception:
            subscription_id = None

    # ---- 2. Dates ----
    def _dt(ts: Optional[int]) -> Optional[datetime]:
        if ts is None:
            return None
        return datetime.fromtimestamp(ts, tz=timezone.utc)

    period_start_dt = _dt(period_start)
    period_end_dt = _dt(period_end)

    # ---- 3. Find BillingAccount ----
    billing_account = await db.scalar(
        select(BillingAccount).where(BillingAccount.stripe_customer_id == customer_id)
    )
    if not billing_account:
        # Nothing to attach this to
        return

    # ---- 4. Find PlanPurchase by subscription id ----
    purchase: Optional[PlanPurchase] = None
    if subscription_id:
        purchase = await db.scalar(
            select(PlanPurchase).where(
                PlanPurchase.stripe_subscription_id == subscription_id,
                PlanPurchase.account_id == billing_account.account_id,
            )
        )

    # ---- 5. Upsert Invoice ----
    invoice = await upsert_invoice_from_stripe(
        db,
        account=billing_account,
        purchase=purchase,
        stripe_invoice_id=stripe_invoice_id,
        stripe_subscription_id=subscription_id,
        amount_due_cents=amount_due,
        amount_paid_cents=amount_paid,
        currency=currency,
        status=status,
        period_start=period_start_dt,
        period_end=period_end_dt,
        hosted_invoice_url=invoice_obj.get("hosted_invoice_url"),
        invoice_pdf_url=invoice_obj.get("invoice_pdf"),
        raw_payload_json=invoice_obj,
    )

    # ---- 6. Always create a PaymentTransaction (fallback id if no PI) ----
    payment_intent_id = invoice_obj.get("payment_intent")
    tx_payment_id = payment_intent_id or f"invoice_{stripe_invoice_id}"

    existing_tx: Optional[PaymentTransaction] = None
    if payment_intent_id:
        existing_tx = await get_payment_transaction_by_pi(db, payment_intent_id)

    occurred_at = datetime.now(timezone.utc)

    if existing_tx:
        existing_tx.account_id = billing_account.account_id
        existing_tx.purchase_id = purchase.purchase_id if purchase else existing_tx.purchase_id
        existing_tx.stripe_invoice_id = stripe_invoice_id
        existing_tx.kind = "initial"
        existing_tx.status = "succeeded"
        existing_tx.amount_cents = amount_paid
        existing_tx.currency = currency
        existing_tx.occurred_at = existing_tx.occurred_at or occurred_at
        existing_tx.raw_payload_json = invoice_obj
        await db.flush()
    else:
        await create_payment_transaction(
            db,
            account=billing_account,
            purchase=purchase,
            stripe_payment_intent_id=tx_payment_id,
            stripe_charge_id=None,
            stripe_invoice_id=stripe_invoice_id,
            kind="initial",
            status="succeeded",
            amount_cents=amount_paid,
            currency=currency,
            occurred_at=occurred_at,
            raw_payload_json=invoice_obj,
        )

    # ---- 7. Update PlanPurchase current period from the invoice ----
    if purchase:
        purchase.stripe_latest_invoice_id = stripe_invoice_id
        if period_start_dt and period_end_dt:
            purchase.current_period_start = period_start_dt
            purchase.current_period_end = period_end_dt
            if purchase.start_date is None:
                purchase.start_date = period_start_dt

        # Ensure it's marked active
        if purchase.status in {"incomplete", "past_due", "trial_converted"}:
            purchase.status = "active"

        await db.flush()

    await _backfill_purchase_links(
        db,
        account_id=billing_account.account_id,
        subscription_id=subscription_id,
    )


async def handle_invoice_payment_failed(
    db: AsyncSession,
    event: dict,
) -> None:
    """
    Handle invoice.payment_failed.
    Upserts Invoice and records a failed PaymentTransaction.
    Marks the PlanPurchase as past_due.
    """
    invoice_obj = event["data"]["object"]

    stripe_invoice_id = invoice_obj["id"]
    customer_id = invoice_obj.get("customer")
    amount_due = invoice_obj.get("amount_due", 0)
    amount_paid = invoice_obj.get("amount_paid", 0)
    currency = invoice_obj.get("currency", "usd")
    period_start = invoice_obj.get("period_start")
    period_end = invoice_obj.get("period_end")
    status = invoice_obj.get("status", "open")

    # ---- 1. Find or derive subscription_id (same pattern as 'succeeded') ----
    subscription_id: Optional[str] = invoice_obj.get("subscription")

    if not subscription_id:
        try:
            lines = (invoice_obj.get("lines") or {}).get("data") or []
            for line in lines:
                parent = (line or {}).get("parent") or {}
                sub_details = parent.get("subscription_item_details") or {}
                sid = sub_details.get("subscription")
                if sid:
                    subscription_id = sid
                    break
        except Exception:
            subscription_id = None

    # ---- 2. Dates ----
    def _dt(ts: Optional[int]) -> Optional[datetime]:
        if ts is None:
            return None
        return datetime.fromtimestamp(ts, tz=timezone.utc)

    period_start_dt = _dt(period_start)
    period_end_dt = _dt(period_end)

    # ---- 3. Find BillingAccount ----
    billing_account = await db.scalar(
        select(BillingAccount).where(BillingAccount.stripe_customer_id == customer_id)
    )
    if not billing_account:
        return

    # ---- 4. Find PlanPurchase by subscription ----
    purchase: Optional[PlanPurchase] = None
    if subscription_id:
        purchase = await db.scalar(
            select(PlanPurchase).where(
                PlanPurchase.stripe_subscription_id == subscription_id,
                PlanPurchase.account_id == billing_account.account_id,
            )
        )

    # ---- 5. Upsert Invoice ----
    invoice = await upsert_invoice_from_stripe(
        db,
        account=billing_account,
        purchase=purchase,
        stripe_invoice_id=stripe_invoice_id,
        stripe_subscription_id=subscription_id,
        amount_due_cents=amount_due,
        amount_paid_cents=amount_paid,
        currency=currency,
        status=status,
        period_start=period_start_dt,
        period_end=period_end_dt,
        hosted_invoice_url=invoice_obj.get("hosted_invoice_url"),
        invoice_pdf_url=invoice_obj.get("invoice_pdf"),
        raw_payload_json=invoice_obj,
    )

    # ---- 6. Log a failed transaction even if there's no real PaymentIntent id ----
    payment_intent_id = invoice_obj.get("payment_intent")
    tx_payment_id = payment_intent_id or f"invoice_{stripe_invoice_id}"

    await create_payment_transaction(
        db,
        account=billing_account,
        purchase=purchase,
        stripe_payment_intent_id=tx_payment_id,
        stripe_charge_id=None,
        stripe_invoice_id=stripe_invoice_id,
        kind="initial",
        status="failed",
        amount_cents=amount_due,
        currency=currency,
        occurred_at=datetime.now(timezone.utc),
        raw_payload_json=invoice_obj,
    )

    # ---- 7. Mark purchase as past_due ----
    if purchase:
        purchase.status = "past_due"
        purchase.stripe_latest_invoice_id = stripe_invoice_id
        await db.flush()

    await _backfill_purchase_links(
        db,
        account_id=billing_account.account_id,
        subscription_id=subscription_id,
    )


async def handle_charge_succeeded(
    db: AsyncSession,
    event: dict,
) -> None:
    """
    Tie Stripe charge.succeeded events back to our payment transactions.
    If the related PaymentIntent transaction already exists (from the invoice
    webhook), update it with the charge id. Otherwise create a new transaction
    placeholder so later invoice webhooks can enrich it.
    """
    charge_obj = event["data"]["object"]

    charge_id = charge_obj.get("id")
    payment_intent_id = charge_obj.get("payment_intent")
    customer_id = charge_obj.get("customer")
    invoice_id = charge_obj.get("invoice")
    amount = charge_obj.get("amount", 0)
    currency = charge_obj.get("currency", "usd")
    status = charge_obj.get("status", "succeeded")
    created_ts = charge_obj.get("created")

    occurred_at = (
        datetime.fromtimestamp(created_ts, tz=timezone.utc)
        if isinstance(created_ts, (int, float))
        else datetime.now(timezone.utc)
    )

    tx: Optional[PaymentTransaction] = None
    if payment_intent_id:
        tx = await get_payment_transaction_by_pi(db, payment_intent_id)

    if tx:
        if charge_id:
            tx.stripe_charge_id = charge_id
        tx.status = status
        tx.occurred_at = occurred_at
        tx.raw_payload_json = charge_obj
        if invoice_id and not tx.stripe_invoice_id:
            tx.stripe_invoice_id = invoice_id
        await db.flush()
        return

    billing_account: Optional[BillingAccount] = None
    purchase: Optional[PlanPurchase] = None

    if invoice_id:
        invoice_row = await db.execute(
            select(Invoice)
            .options(
                joinedload(Invoice.account),
                joinedload(Invoice.purchase),
            )
            .where(Invoice.stripe_invoice_id == invoice_id)
        )
        invoice_obj_db: Optional[Invoice] = invoice_row.scalar_one_or_none()
        if invoice_obj_db:
            billing_account = invoice_obj_db.account
            purchase = invoice_obj_db.purchase

    if billing_account is None and customer_id:
        billing_account = await db.scalar(
            select(BillingAccount).where(BillingAccount.stripe_customer_id == customer_id)
        )

    if billing_account is None:
        # Without an account we cannot persist this charge.
        return

    await create_payment_transaction(
        db,
        account=billing_account,
        purchase=purchase,
        stripe_payment_intent_id=payment_intent_id or f"charge_{charge_id}",
        stripe_charge_id=charge_id,
        stripe_invoice_id=invoice_id,
        kind="initial",
        status=status,
        amount_cents=amount,
        currency=currency,
        occurred_at=occurred_at,
        raw_payload_json=charge_obj,
    )
