from sqlalchemy import Integer, String, Boolean, Column, Table, DateTime, UUID, Text
from sqlalchemy.sql import func, bindparam
from typing import List, Optional, Dict, Any, Union
from app.data.dbinit import Base
from app.model.user_prompt_response import WeeklyPlanIdentifier, ActivityByDayIdentifier, ActivityDetail, ActivityDetailIdentifier
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import insert, select, update
from sqlalchemy.exc import SQLAlchemyError, MultipleResultsFound, NoResultFound, IntegrityError
from fastapi import HTTPException, status
import structlog

from app.common.exception import DatabaseConnectionException, RecordNotFoundException, IntegrityException, MissingDataException, GeneralDataException

logger = structlog.get_logger()

class UserPlanWeekDetail(Base):
    __tablename__ = "user_plan_week_detail"
    plan_id = Column(UUID, index=True)
    week_number = Column(Integer, nullable=False)
    week_objective = Column(String, nullable=False)
    week_text = Column(String, nullable=True)
    approved_by_user = Column(Integer, default=0)
    week_objective_sequence = Column(Integer)
    entity_id = Column(UUID(as_uuid=True), primary_key=True, server_default=str("gen_random_uuid()"))


class UserPlanDayDetail(Base):
    __tablename__ = "user_plan_day_detail"
    plan_id = Column(UUID, index=True)
    week_number = Column(Integer, nullable=False)
    day_text = Column(String, nullable=True)
    day_number= Column(Integer, nullable=False)
    day_objective = Column(String, nullable=False)
    approved_by_user = Column(Integer, default=0)
    day_objective_sequence = Column(Integer)
    week_objective_sequence = Column(Integer)
    suggest_time = Column(String, nullable=True)
    suggest_duration = Column(String, nullable=True)
    entity_id = Column(UUID(as_uuid=True), primary_key=True, server_default=str("gen_random_uuid()"))


class UserPlanActivityDetail(Base):
    __tablename__ = "user_plan_activity_detail"
    plan_id = Column(UUID, primary_key=True, index=True)
    week_number = Column(Integer, nullable=False)
    day_number= Column(Integer, nullable=False)
    activity_id = Column(UUID(as_uuid=True), primary_key=True, server_default=str("gen_random_uuid()"))
    activity = Column(String, nullable=False)
    activity_sequence = Column(Integer)
    day_objective_sequence = Column(Integer)
    week_objective_sequence = Column(Integer)
    suggest_time = Column(String, nullable=True)
    suggest_duration = Column(String, nullable=True)
    source_id = Column(Integer, default=0)
    approved_by_user = Column(Integer, default=0)


async def insert_weekly_header(obj_user_weekly_detail: WeeklyPlanIdentifier, db: AsyncSession) -> Optional[WeeklyPlanIdentifier] :
    try:
        # Create the user plan database object

        stmt = insert(UserPlanWeekDetail).values(
            plan_id=obj_user_weekly_detail.plan_id,
            week_text=obj_user_weekly_detail.week_text,
            week_number = obj_user_weekly_detail.week_number,
            week_objective=obj_user_weekly_detail.weekly_objective,
            week_objective_sequence = obj_user_weekly_detail.week_objective_sequence
        ).returning(UserPlanWeekDetail)

        result = await db.execute(stmt)
        user_week_object_db =  result.scalar_one()
        return user_week_object_db
    except IntegrityError as e:
        await db.rollback()
        logger.error(f"IntegrityError when inserting user plan: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This plan conflicts with an existing plan. Possible duplicate entry or foreign key constraint failure."
        )
    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(f"Database error when inserting user plan: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred while creating the user plan"
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"Unexpected error in insert_plan: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while creating the user plan"
        )

async def insert_daily_header(obj_daily_header: ActivityByDayIdentifier, db: AsyncSession) -> Optional[ActivityByDayIdentifier] :
    try:
        # Create the user plan database object
        
        stmt = insert(UserPlanDayDetail).values(
            plan_id=obj_daily_header.plan_id,
            day_text=obj_daily_header.day_text,
            day_number = obj_daily_header.day_number,
            day_objective=obj_daily_header.daily_objective,
            week_number = obj_daily_header.week_number,
            week_objective_sequence = obj_daily_header.week_objective_sequence,
            day_objective_sequence = obj_daily_header.day_objective_sequence,
            suggest_time = obj_daily_header.suggested_time,
            suggest_duration = obj_daily_header.suggested_duration
        ).returning(UserPlanDayDetail)

        result = await db.execute(stmt)
        user_daily_header =  result.scalar_one()
        return user_daily_header
        
    except IntegrityError as e:
        await db.rollback()
        logger.error(f"IntegrityError when inserting user plan: {str(e)}")
        raise IntegrityException(
            "Integrity error when inserting a user plan",
            context = {"detail": "This plan conflicts with an existing plan. Possible duplicate entry or foreign key constraint failure."}
        )
    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(f"Database error when inserting user plan: {str(e)}")
        raise GeneralDataException(
            "Data base error occured while inserting the user plan",
            context={"detail": "Database error occurred while creating the user plan"}
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"Unexpected error in insert_plan: {str(e)}")
        raise GeneralDataException(
            "Unexpected error occured inserting plan",
            context={"detail" : "An unexpected error occurred while creating the user plan"}
        )

async def insert_activity_detail(obj_daily_header: ActivityDetail, db: AsyncSession) -> Optional[ActivityDetailIdentifier] :
    try:
        # Create the user plan database object
        stmt = insert(UserPlanActivityDetail).values(
            plan_id=obj_daily_header.plan_id,
            day_number = obj_daily_header.day_number,
            activity=obj_daily_header.activity,
            week_number = obj_daily_header.week_number,
            activity_sequence = obj_daily_header.activity_sequence,
            week_objective_sequence = obj_daily_header.week_objective_sequence,
            day_objective_sequence = obj_daily_header.day_objective_sequence,
            suggest_time = obj_daily_header.suggest_time,
            suggest_duration = obj_daily_header.suggest_duration
        ).returning(UserPlanActivityDetail)

        result = await db.execute(stmt)
        user_activity_db =  result.scalar_one()
        return user_activity_db
    except IntegrityError as e:
        await db.rollback()
        logger.error(f"IntegrityError when inserting user plan: {str(e)}")
        raise IntegrityException(
            "Integrity error when inserting a user plan",
            context = {"detail": "This plan conflicts with an existing plan. Possible duplicate entry or foreign key constraint failure."}
        )
    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(f"Database error when inserting user plan: {str(e)}")
        raise GeneralDataException(
            "Data base error occured while inserting the user plan",
            context={"detail": "Database error occurred while creating the user plan"}
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"Unexpected error in insert_plan: {str(e)}")
        raise GeneralDataException(
            "Unexpected error occured inserting plan",
            context={"detail" : "An unexpected error occurred while creating the user plan"}
        )

async def get_plan_weekly_detail(filter_params, db: AsyncSession) -> Optional[List[UserPlanWeekDetail]]:
    try:
        stmt = select(UserPlanWeekDetail)
        if filter_params:
            if filter_params.get("plan_id") is not None:
                stmt = stmt.filter(UserPlanWeekDetail.plan_id == filter_params["plan_id"])
            if filter_params.get("approved_by_user") is not None:
                stmt = stmt.filter(UserPlanWeekDetail.approved_by_user == filter_params["approved_by_user"])
        result = await db.execute(stmt)
        d = result.scalars().all()
        return d
    except IntegrityError as e:

        logger.error(f"IntegrityError when inserting user plan: {str(e)}")
        raise IntegrityException(
            "Integrity error when inserting a user plan",
            context = {"detail": "This plan conflicts with an existing plan. Possible duplicate entry or foreign key constraint failure."}
        )
    except SQLAlchemyError as e:

        logger.error(f"Database error when inserting user plan: {str(e)}")
        raise GeneralDataException(
            "Data base error occured while inserting the user plan",
            context={"detail": "Database error occurred while creating the user plan"}
        )
    except Exception as e:

        logger.error(f"Unexpected error in insert_plan: {str(e)}")
        raise GeneralDataException(
            "Unexpected error occured inserting plan",
            context={"detail" : "An unexpected error occurred while creating the user plan"}
        )

async def get_plan_day_detail(filter_params: Optional[Dict[str, Any]], db: AsyncSession) -> Optional[List[UserPlanDayDetail]]:
    try:
        stmt = select(UserPlanDayDetail)
        if filter_params:
            if filter_params.get("plan_id") is not None:
                stmt = stmt.filter(UserPlanDayDetail.plan_id == filter_params["plan_id"])
            if filter_params.get("approved_by_user") is not None:
                stmt = stmt.filter(UserPlanDayDetail.approved_by_user == filter_params["approved_by_user"])
            if filter_params.get("entity_id") is not None:
                stmt = stmt.filter(UserPlanDayDetail.entity_id == filter_params["entity_id"])
        result = await db.execute(stmt)
        return result.scalars().all()
    except IntegrityError as e:

        logger.error(f"IntegrityError when inserting user plan: {str(e)}")
        raise IntegrityException(
            "Integrity error when inserting a user plan",
            context = {"detail": "This plan conflicts with an existing plan. Possible duplicate entry or foreign key constraint failure."}
        )
    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(f"Database error when inserting user plan: {str(e)}")
        raise GeneralDataException(
            "Data base error occured while inserting the user plan",
            context={"detail": "Database error occurred while creating the user plan"}
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"Unexpected error in insert_plan: {str(e)}")
        raise GeneralDataException(
            "Unexpected error occured inserting plan",
            context={"detail" : "An unexpected error occurred while creating the user plan"}
        )
async def get_plan_activity_detail(filter_params: Optional[Dict[str, Any]], db: AsyncSession) -> Optional[List[UserPlanActivityDetail]]:
    try:

        stmt = select(UserPlanActivityDetail)
        if filter_params:
            if filter_params.get("plan_id") is not None:
                stmt = stmt.filter(UserPlanActivityDetail.plan_id == filter_params["plan_id"])
            if filter_params.get("approved_by_user") is not None:
                stmt = stmt.filter(UserPlanActivityDetail.approved_by_user == filter_params["approved_by_user"])
            if filter_params.get("activity_id") is not None:
                stmt = stmt.filter(UserPlanActivityDetail.activity_id == filter_params["activity_id"])
        result = await db.execute(stmt)
        return result.scalars().all()
    except IntegrityError as e:
        await db.rollback()
        logger.error(f"IntegrityError when inserting user plan: {str(e)}")
        raise IntegrityException(
            "Integrity error when inserting a user plan",
            context = {"detail": "This plan conflicts with an existing plan. Possible duplicate entry or foreign key constraint failure."}
        )
    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(f"Database error when inserting user plan: {str(e)}")
        raise GeneralDataException(
            "Data base error occured while inserting the user plan",
            context={"detail": "Database error occurred while creating the user plan"}
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"Unexpected error in insert_plan: {str(e)}")
        raise GeneralDataException(
            "Unexpected error occured inserting plan",
            context={"detail" : "An unexpected error occurred while creating the user plan"}
        )

async def update_plan_weekly_detail(
    plan_id: UUID,
    user_approval: int,
    db: AsyncSession
) -> Optional[UserPlanWeekDetail]:
 
    try:
        if str(plan_id) is None:
            raise NoResultFound
        # Prepare update values
        update_values = {}
        if user_approval is not None:
            update_values["approved_by_user"] = bindparam("user_approval")
        params = {
            "plan_id": plan_id,
            "user_approval": user_approval
        }
        stmt = (
            update(UserPlanWeekDetail)
            .where(
                UserPlanWeekDetail.plan_id == bindparam("plan_id")
            )
            .values(**update_values)
            .returning(UserPlanWeekDetail)
        )
        
        result = await db.execute(stmt, params)
        await db.commit()
        
        # Return the updated plan
        updated_plan = result.scalar_one_or_none()
        return updated_plan
        
    except IntegrityError as e:
        await db.rollback()
        logger.error(f"IntegrityError when inserting user plan: {str(e)}")
        raise IntegrityException(
            "Integrity error when inserting a user plan",
            context = {"detail": "This plan conflicts with an existing plan. Possible duplicate entry or foreign key constraint failure."}
        )
    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(f"Database error when inserting user plan: {str(e)}")
        raise GeneralDataException(
            "Data base error occured while inserting the user plan",
            context={"detail": "Database error occurred while creating the user plan"}
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"Unexpected error in insert_plan: {str(e)}")
        raise GeneralDataException(
            "Unexpected error occured inserting plan",
            context={"detail" : "An unexpected error occurred while creating the user plan"}
        )

async def update_plan_daily_detail(
    plan_id: UUID,
    user_approval: int,
    day_objective_sequence: int,
    db: AsyncSession
) -> Optional[UserPlanDayDetail]:
 
    try:
        if str(plan_id) is None:
            raise NoResultFound
        # Prepare update values
        update_values = {}
        if user_approval is not None:
            update_values["approved_by_user"] = bindparam("user_approval")
            update_values["day_objective_sequence"] = bindparam("day_objective_sequence")
        params = {
            "plan_id": plan_id,
            "day_objective_sequence": day_objective_sequence,
            "user_approval": user_approval
        }
        stmt = (
            update(UserPlanDayDetail)
            .where(
                UserPlanDayDetail.plan_id == bindparam("plan_id")
            )
            .values(**update_values)
            .returning(UserPlanDayDetail)
        )
        
        result = await db.execute(stmt, params)
        await db.commit()
        
        # Return the updated plan
        updated_plan = result.scalar_one_or_none()
        return updated_plan
        
    except IntegrityError as e:
        await db.rollback()
        logger.error(f"IntegrityError when updating executable plan: {str(e)}")
        raise IntegrityException(
            "Integrity error when updating executable plan",
            context = {"detail": f"Issue with updating the executable plan {str(e)}"}
        )
    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(f"Database error when updating executable plan: {str(e)}")
        raise GeneralDataException(
            "Data base error occured while inserting the executable plan",
            context={"detail": f"Database error when updating executable plan: {str(e)}"}
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"Database error when updating executable plan: {str(e)}")
        raise GeneralDataException(
            "Unexpected error occured updating the executable plan",
            context={"detail" : f"Database error when updating executable plan: {str(e)}"}
        )


async def update_plan_activity_detail(
    plan_id: str,
    user_approval: int,
    activity_id: str,
    db: AsyncSession
) -> Optional[UserPlanActivityDetail]:
 
    try:
        if str(plan_id) is None:
            raise NoResultFound
        # Prepare update values
        update_values = {}
        if user_approval is not None:
            update_values["approved_by_user"] = bindparam("user_approval")
        params = {
            "plan_id": str(plan_id),
            "activity_id": str(activity_id),
            "user_approval" : user_approval
        }
        stmt = (
            update(UserPlanActivityDetail)
            .where(
                UserPlanActivityDetail.plan_id == bindparam("plan_id"),
                UserPlanActivityDetail.activity_id == bindparam("activity_id")
            )
            .values(**update_values)
            .returning(UserPlanActivityDetail)
        )
        
        result = await db.execute(stmt, params)
        await db.commit()
        
        # Return the updated plan
        updated_plan = result.scalar_one_or_none()
        return updated_plan
        
    except IntegrityError as e:
        await db.rollback()
        logger.error(f"IntegrityError when updating executable plan: {str(e)}")
        raise IntegrityException(
            "Integrity error when updating executable plan",
            context = {"detail": f"Issue with updating the executable plan {str(e)}"}
        )
    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(f"Database error when updating executable plan: {str(e)}")
        raise GeneralDataException(
            "Data base error occured while inserting the executable plan",
            context={"detail": f"Database error when updating executable plan: {str(e)}"}
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"Database error when updating executable plan: {str(e)}")
        raise GeneralDataException(
            "Unexpected error occured updating the executable plan",
            context={"detail" : f"Database error when updating executable plan: {str(e)}"}
        )

