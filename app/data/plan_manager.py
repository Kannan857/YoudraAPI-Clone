# crud/fmp_subscriber.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from typing import List, Optional, Dict, Any
from sqlalchemy import Column, DateTime, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.data.dbinit import Base
import uuid
from app.data.user_plan import UserPlan
from app.model.user import User

from app.common.exception import (
    DatabaseConnectionException,
    RecordNotFoundException,
    IntegrityException,
    GeneralDataException,
)

from app.model.plan_manager import FmpSubscriberCreate, FmpSubscriberUpdate

import structlog

from datetime import datetime

logger = structlog.get_logger()

class DBFmpSubscriber(Base):
    __tablename__ = "fmp_subscriber"

    plan_id = Column(UUID(as_uuid=True), primary_key=True)
    user_id = Column(UUID(as_uuid=True), primary_key=True)
    subscribed_dt = Column(DateTime(timezone=True), server_default=func.now())
    is_active = Column(Integer, nullable=False)
    inserted_dt = Column(DateTime(timezone=True), server_default=func.now())
    updated_dt = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


async def add_subscriber(
    db: AsyncSession,
    fmp: FmpSubscriberCreate
) -> DBFmpSubscriber:
    try:
        subscriber = DBFmpSubscriber(
            plan_id=fmp.plan_id,
            user_id=fmp.user_id,
            is_active=fmp.is_active
        )
        db.add(subscriber)
        await db.commit()
        await db.refresh(subscriber)
        return subscriber
    except IntegrityError as e:
        logger.error(f"Integrity error adding subscriber: {str(e)}")
        raise IntegrityException("Duplicate or conflicting entry")
    except SQLAlchemyError as e:
        logger.error(f"Database error adding subscriber: {str(e)}")
        raise GeneralDataException("Database error while adding subscriber")

    except Exception as e:
        logger.error(f"Database error adding subscriber: {str(e)}")
        raise GeneralDataException("Database error while adding subscriber")
    
async def update_subscriber_status(
    db: AsyncSession,
    plan_id: uuid.UUID,
    user_id: uuid.UUID,
    is_active: int
) -> bool:
    try:
        stmt = (
            update(DBFmpSubscriber)
            .where(DBFmpSubscriber.plan_id == plan_id, DBFmpSubscriber.user_id == user_id)
            .values(
                is_active=is_active,
                updated_dt=datetime.utcnow()
            )
        )
        result = await db.execute(stmt)
        await db.commit()
        return result.rowcount > 0
    except SQLAlchemyError as e:
        logger.error(f"Database error updating subscriber: {str(e)}")
        raise GeneralDataException("Database error while updating subscriber")


async def delete_subscriber(db: AsyncSession, plan_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    try:
        stmt = delete(DBFmpSubscriber).where(
            DBFmpSubscriber.plan_id == plan_id,
            DBFmpSubscriber.user_id == user_id
        )
        result = await db.execute(stmt)
        await db.commit()
        return result.rowcount > 0
    except SQLAlchemyError as e:
        logger.error(f"Database error deleting subscriber: {str(e)}")
        raise GeneralDataException("Database error while deleting subscriber")

async def get_users_by_plan_id(db: AsyncSession, plan_id: UUID) -> List["DBFmpSubscriber"]:
    try:
        stmt = select(DBFmpSubscriber).where(DBFmpSubscriber.plan_id == plan_id)
        result = await db.execute(stmt)
        subscribers = result.scalars().all()
        return subscribers
    except Exception as e:
        logger.error(f"Error fetching subscribers by plan_id: {e}")
        raise GeneralDataException(
            message="Failed to fetch subscribers by plan ID",
            context={"plan_id": str(plan_id), "error": str(e)}
            )

async def get_subscriber_db(db: AsyncSession, filter_params: dict) -> List[Dict[str, Any]]:
        try:
            stmt = (
            select(
                UserPlan.plan_id,
                UserPlan.plan_name,
                func.count(DBFmpSubscriber.user_id).label("subscriber_count")
            )
            .join(DBFmpSubscriber, UserPlan.plan_id == DBFmpSubscriber.plan_id)
            .where(UserPlan.user_id == filter_params["user_id"])
            .where(DBFmpSubscriber.is_active == 1)
        )

            # Add optional plan_id filter
            if "plan_id" in filter_params and filter_params["plan_id"]:
                stmt = stmt.where(UserPlan.plan_id == filter_params["plan_id"])

            stmt = stmt.group_by(UserPlan.plan_id, UserPlan.plan_name)
            result = await db.execute(stmt)
            data = [
                {
                    "plan_id": row.plan_id,
                    "plan_name": row.plan_name,
                    "subscriber_count": row.subscriber_count
                }
                for row in result
            ]
            return data

        except Exception as e:
            logger.error(f"Failed to get subscriber count by plan for user {user_id}: {e}")
            raise GeneralDataException(
                message="Error fetching subscriber count",
                context={"user_id": str(filter_params["user_id"]), "error": str(e)}
            )
        
async def get_subscription_db(db: AsyncSession, filter_params: dict) -> List[Dict[str, Any]]:
    try:
        stmt = (
            select(UserPlan.plan_id, UserPlan.plan_name)
            .join(DBFmpSubscriber, UserPlan.plan_id == DBFmpSubscriber.plan_id)
            .where(DBFmpSubscriber.user_id == filter_params["user_id"])
            .where(DBFmpSubscriber.is_active == 1)
        )
        if "plan_id" in filter_params and filter_params["plan_id"]:
            stmt = stmt.where(DBFmpSubscriber.plan_id == filter_params["plan_id"])
        result = await db.execute(stmt)
        plans = result.fetchall()

        return [{"plan_id": row.plan_id, "plan_name": row.plan_name} for row in plans]
    
    except Exception as e:
        logger.error(f"Error fetching subscribed plans for user {filter_params['user_id']}: {e}")
        raise GeneralDataException(
            message="Failed to fetch user subscriptions",
            context={"user_id": str(filter_params["user_id"]), "error": str(e)}
        )

async def get_fmp_by_count(
    db: AsyncSession, user_id: UUID, limit: int = 10, offset: int = 0
) -> Optional[List[dict]]:
    try:
        query = """
            SELECT DISTINCT 
                up.plan_id,
                up.plan_name,
                coalesce(followers,0),
                up.user_id,
                first_name,
                last_name
            FROM 
                user_plan up
            LEFT JOIN (
                SELECT count(user_id) as followers, plan_id
                FROM fmp_subscriber
                WHERE user_id != :user_id
                GROUP BY plan_id
            ) fmp ON up.plan_id = fmp.plan_id,
            dreav_user du
            WHERE 
                up.user_id != :user_id
                and up.private_flag = 0
                AND du.user_id = up.user_id
            LIMIT :limit OFFSET :offset
        """

        params = {
            "user_id": str(user_id),
            "limit": limit,
            "offset": offset
        }

        result = await db.execute(text(query), params)
        res = result.mappings().all()
        return res


    except IntegrityError as e:
        logger.error(f"IntegrityError when updating executable plan: {str(e)}")
        raise IntegrityException(
            "Integrity error when updating executable plan",
            context={"detail": f"Issue with updating the executable plan {str(e)}"}
        )
    except SQLAlchemyError as e:
        logger.error(f"Database error when updating executable plan: {str(e)}")
        raise GeneralDataException(
            "Database error occurred while inserting the executable plan",
            context={"detail": f"Database error when updating executable plan: {str(e)}"}
        )
    except Exception as e:
        logger.error(f"Unexpected error when updating executable plan: {str(e)}")
        raise GeneralDataException(
            "Unexpected error occurred updating the executable plan",
            context={"detail": f"Database error when updating executable plan: {str(e)}"}
        )
