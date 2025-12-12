from __future__ import annotations

from typing import Optional
from uuid import UUID

from datetime import datetime, timezone
import stripe

import stripe
from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.config import settings
from app.data.billing import Organization, SubscriptionPlan
from app.data.billing import create_webhook_event, WebhookEvent
from app.data.dbinit import get_db
from app.data.user import User
from app.model.billing import (
    BillingSummary,
    BillingUpgradeRequest,
    CheckoutSessionResponse,
    CustomPlanCheckoutRequest,
)
from app.service.billing import (
    get_billing_summary_for_org,
    load_org_with_authorization,
    get_billing_account_for_org,    
    mark_webhook_processed,
    handle_subscription_event,
    handle_invoice_payment_succeeded,
    handle_invoice_payment_failed,
    handle_charge_succeeded,
)
from app.service.user import get_current_user

from app.data.dbinit import get_db
from app.data.user import User
from app.data.billing import Organization
from app.model.billing import BillingSummary


router = APIRouter(prefix="/billing", tags=["billing"])

stripe.api_key = settings.STRIPE_SECRET_KEY
CUSTOM_SEAT_UNIT_AMOUNT_CENTS = 200


async def _resolve_org(
    db: AsyncSession,
    current_user: User,
    org_id: Optional[UUID],
) -> Organization:
    if org_id:
        return await load_org_with_authorization(
            db,
            org_id=org_id,
            current_user=current_user,
            allow_platform_admin=True,
            allow_owner=True,
            allow_org_admin=True,
        )
    org = await db.scalar(
        select(Organization)
        .where(Organization.owner_user_id == current_user.user_id)
        .order_by(Organization.created_at.asc())
    )
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No organization found for this user.",
        )
    return org


@router.get(
    "/summary",
    response_model=BillingSummary,
)
async def get_billing_summary(
    org_id: Optional[UUID] = Query(
        default=None,
        description="Optional org_id. If omitted, uses first org where user is owner.",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Return billing summary for an organization.

    Access:
    - Platform admin can request any org by org_id.
    - Org owner can request their own org (by id or "current").
    """
    org = await _resolve_org(db, current_user, org_id)

    summary = await get_billing_summary_for_org(db, org)
    return summary


@router.post(
    "/upgrade",
    response_model=CheckoutSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upgrade_billing_plan(
    payload: BillingUpgradeRequest,
    org_id: Optional[UUID] = Query(
        default=None,
        description="Optional org_id. If omitted, uses first org where user is owner.",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Start a Stripe Checkout Session to upgrade the current organization
    to a paid subscription plan. Actual plan activation happens via webhooks
    after Stripe confirms payment.
    """
    if org_id:
        org = await load_org_with_authorization(
            db,
            org_id=org_id,
            current_user=current_user,
            allow_platform_admin=True,
            allow_owner=True,
        )
    else:
        org = await db.scalar(
            select(Organization)
            .where(Organization.owner_user_id == current_user.user_id)
            .order_by(Organization.created_at.asc())
        )
        if not org:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No organization found for this user.",
            )

    billing_account = await get_billing_account_for_org(db, org.org_id)
    if not billing_account:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No billing account configured for this organization.",
        )

    result = await db.execute(
        select(SubscriptionPlan).where(SubscriptionPlan.code == payload.plan_code)
    )
    plan: Optional[SubscriptionPlan] = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown plan_code '{payload.plan_code}'.",
        )
    if not plan.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Requested plan is not active.",
        )
    if plan.plan_type != "recurring":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Requested plan is not a recurring subscription plan.",
        )
    if not plan.stripe_price_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Requested plan is not configured with a Stripe price.",
        )

    try:
        if not billing_account.stripe_customer_id:
            customer = stripe.Customer.create(
                email=billing_account.primary_contact_email,
                name=org.name,
                metadata={
                    "org_id": str(org.org_id),
                    "billing_account_id": str(billing_account.account_id),
                },
            )
            billing_account.stripe_customer_id = customer.id
            await db.flush()
            await db.commit()
    except stripe.error.StripeError as exc:  # pragma: no cover
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error creating Stripe customer: {exc.user_message or str(exc)}",
        )

    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            customer=billing_account.stripe_customer_id,
            line_items=[
                {
                    "price": plan.stripe_price_id,
                    "quantity": payload.seat_quantity,
                }
            ],
            success_url=str(payload.success_url),
            cancel_url=str(payload.cancel_url),
            allow_promotion_codes=True,
            client_reference_id=str(org.org_id),
            metadata={
                "org_id": str(org.org_id),
                "billing_account_id": str(billing_account.account_id),
                "plan_id": str(plan.plan_id),
                "plan_code": plan.code,
            },
        )
    except stripe.error.StripeError as exc:  # pragma: no cover
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error creating Stripe Checkout Session: {exc.user_message or str(exc)}",
        )

    return CheckoutSessionResponse(
        checkout_url=session.url,
        session_id=session.id,
    )


@router.post(
    "/custom-plan",
    response_model=CheckoutSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_custom_plan_checkout(
    payload: CustomPlanCheckoutRequest,
    org_id: Optional[UUID] = Query(
        default=None,
        description="Optional org_id. Defaults to caller's first org.",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.seat_count <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="seat_count must be greater than zero.",
        )
    if not settings.STRIPE_CUSTOM_SEAT_PRICE_ID:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Custom seat price is not configured. Please contact support.",
        )

    org = await _resolve_org(db, current_user, org_id)

    billing_account = await get_billing_account_for_org(db, org.org_id)
    if not billing_account:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No billing account configured for this organization.",
        )

    try:
        if not billing_account.stripe_customer_id:
            customer = stripe.Customer.create(
                email=billing_account.primary_contact_email,
                name=org.name,
                metadata={
                    "org_id": str(org.org_id),
                    "billing_account_id": str(billing_account.account_id),
                },
            )
            billing_account.stripe_customer_id = customer.id
            await db.flush()
            await db.commit()
    except stripe.error.StripeError as exc:  # pragma: no cover
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error creating Stripe customer: {exc.user_message or str(exc)}",
        )

    metadata = {
        "org_id": str(org.org_id),
        "billing_account_id": str(billing_account.account_id),
        "plan_type": "custom",
        "custom_seat_count": str(payload.seat_count),
        "custom_unit_amount_cents": str(CUSTOM_SEAT_UNIT_AMOUNT_CENTS),
    }

    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            customer=billing_account.stripe_customer_id,
            line_items=[
                {
                    "price": settings.STRIPE_CUSTOM_SEAT_PRICE_ID,
                    "quantity": payload.seat_count,
                }
            ],
            subscription_data={
                "metadata": metadata,
            },
            success_url=str(payload.success_url),
            cancel_url=str(payload.cancel_url),
            allow_promotion_codes=True,
            client_reference_id=str(org.org_id),
            metadata=metadata,
        )
    except stripe.error.StripeError as exc:  # pragma: no cover
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error creating Stripe Checkout Session: {exc.user_message or str(exc)}",
        )

    return CheckoutSessionResponse(
        checkout_url=session.url,
        session_id=session.id,
    )

@router.post("/webhooks/stripe", status_code=status.HTTP_200_OK)
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Stripe webhook endpoint.

    This receives events from Stripe (via Stripe CLI or dashboard),
    verifies the signature, logs the event in webhook_event, and
    dispatches to business logic handlers.
    """
    payload = await request.body()
    sig_header = request.headers.get("Stripe-Signature", "")

    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=sig_header,
            secret=settings.STRIPE_WEBHOOK_SECRET,
        )
    except ValueError:
        # Invalid JSON
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid payload",
        )
    except stripe.error.SignatureVerificationError:
        # Invalid signature
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Stripe signature",
        )

    stripe_event_id = event["id"]
    event_type = event["type"]

    # 1) Log webhook_event with idempotency
    webhook_row = await create_webhook_event(
    db,
    stripe_event_id=stripe_event_id,
    event_type=event_type,
    payload_json=event,
)

    if webhook_row is None:
        # event already logged before, just ack
        return {"received": True, "duplicate": True}

    # 2) Dispatch to handlers
    error_message: Optional[str] = None
    success = True

    try:
        if event_type.startswith("customer.subscription."):
            await handle_subscription_event(db, event)
        elif event_type == "invoice.payment_succeeded":
            await handle_invoice_payment_succeeded(db, event)
        elif event_type == "invoice.payment_failed":
            await handle_invoice_payment_failed(db, event)
        elif event_type == "charge.succeeded":
            await handle_charge_succeeded(db, event)
        else:
            # For now, we ignore other events but still mark as processed.
            pass

        await mark_webhook_processed(db, webhook_row, success=True, error_message=None)
        await db.commit()
    except Exception as exc:  # noqa: BLE001
        success = False
        error_message = str(exc)
        await mark_webhook_processed(db, webhook_row, success=False, error_message=error_message)
        await db.commit()
        # You can choose to re-raise or just swallow. For now we just log and ack.
        # raise HTTPException(status_code=500, detail="Error processing webhook")

    return {"received": True, "processed": success}
