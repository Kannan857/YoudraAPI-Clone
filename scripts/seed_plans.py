# scripts/seed_plans.py
import asyncio
from dotenv import load_dotenv

load_dotenv()  # make sure POSTGRES_* etc. are in the environment

from app.data.dbinit import SessionLocal
from app.data.billing import create_subscription_plan


async def seed_plans():
    async with SessionLocal() as db:
        await create_subscription_plan(
            db,
            code="TRIAL_14D_10_SEATS",
            name="Free Trial (14 days)",
            description="Try Performance 360 with up to 10 employees.",
            plan_type="trial",
            billing_cycle="trial",
            amount_cents=0,
            currency="usd",
            seat_limit=10,
            extra_seat_price_cents=None,
            max_cycles_per_year=1,
            max_active_reviews=10,
            includes_external_reviewers=True,
            is_trial=True,
            trial_days=14,
            stripe_price_id=None,
        )

        await create_subscription_plan(
            db,
            code="STARTER_25_MONTHLY",
            name="Starter (25 seats)",
            description="Up to 25 employees, billed monthly.",
            plan_type="recurring",
            billing_cycle="month",
            amount_cents=19900,
            currency="usd",
            seat_limit=25,
            extra_seat_price_cents=None,
            max_cycles_per_year=2,
            max_active_reviews=25,
            includes_external_reviewers=True,
            is_trial=False,
            trial_days=None,
            stripe_price_id="price_1SanPkLf2ieGpqi2gRNroTIM",
        )

        await create_subscription_plan(
            db,
            code="GROWTH_50_MONTHLY",
            name="Growth (50 seats)",
            description="Up to 50 employees, billed monthly.",
            plan_type="recurring",
            billing_cycle="month",
            amount_cents=34900,
            currency="usd",
            seat_limit=50,
            extra_seat_price_cents=None,
            max_cycles_per_year=3,
            max_active_reviews=50,
            includes_external_reviewers=True,
            is_trial=False,
            trial_days=None,
            stripe_price_id="price_1SanV9Lf2ieGpqi2NkJuqlbU",
        )

        await db.commit()


if __name__ == "__main__":
    asyncio.run(seed_plans())
