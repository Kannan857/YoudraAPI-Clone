from app.model.user import UserCreate, UserUpdate
from app.model.user_prompt_response import UXGoalBuilder, GeneralRecommendationAndGuidelines, RoutineSummary
from sqlalchemy.exc import SQLAlchemyError, MultipleResultsFound, NoResultFound, IntegrityError
from sqlalchemy import select, update, insert, bindparam, ForeignKey, BigInteger, cast
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import Integer, String, Boolean, Column, Table, DateTime, UUID, Text, Float, or_, and_, func, text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.model.user_plan import UserPlan as UserPlanModel, UserPlanIdentifier as UserPlanIdentifierModel, UXUserPlanIdentifier, IExecutionPlanDetail, ICreatedPlan
from typing import List, Optional, Dict, Any, Union
from app.data.dbinit import Base, get_db
from app.data.common_table import ProgressUpdate
import structlog
from datetime import datetime, timedelta
from fastapi import HTTPException, status
from fastapi import APIRouter, Depends, HTTPException, status, Query
from app.common.exception import DatabaseConnectionException, RecordNotFoundException, IntegrityException, MissingDataException, GeneralDataException

# Set up logging
logger = structlog.get_logger()

class PlanGeneralGuideline(Base):
    __tablename__ = "plan_general_guideline"
    plan_id = Column(UUID(as_uuid=True), primary_key=True)
    guideline = Column(String, nullable=False)

class PlanRoutineSummary(Base):
    __tablename__ = "plan_routine_summary"
    plan_id = Column(UUID(as_uuid=True), primary_key=True)
    routine = Column(String, nullable=False)

class GoalBuilder(Base):
    __tablename__ = "goal_builder"
    plan_id = Column(UUID(as_uuid=True), primary_key=True)
    user_id = Column(UUID(as_uuid=True), primary_key = True, nullable=False)
    prev_plan_id = Column(UUID(as_uuid=True), nullable=True)
    root_id = Column(UUID(as_uuid=True), nullable=False)
    session_id = Column(UUID(as_uuid=True))
    plan_name = Column(String, nullable=False)
    prompt_text = Column(String, nullable=False)
    sequence_id = Column(BigInteger, nullable=False)
    revised_prompt_summary = Column(Text, nullable=True)
    concatenated_prompt = Column(Text, nullable=True)
    llm_source = Column(String, nullable=False)
    created_dt = Column(DateTime(timezone=True), server_default=func.now())

class UserPlan(Base):
    __tablename__ = "user_plan"
    plan_id = Column(UUID(as_uuid=True), primary_key=True, server_default=str("gen_random_uuid()"))
    user_id = Column(UUID, nullable=False)
    plan_name = Column(String, nullable=False)
    plan_start_date = Column(DateTime(timezone=True), nullable=True)
    plan_end_date = Column(DateTime(timezone=True), nullable=True)  
    plan_type = Column(String, nullable=False)
    plan_category = Column(String, nullable=True)
    plan_goal = Column(Text, nullable=False)
    goal_duration = Column(Text, nullable=True)
    approved_by_user = Column(Integer, default=0)
    private_flag = Column(Integer, default=1)
    follow_flag = Column(Integer, default=0)
    plan_status = Column(Integer, default=0)
    created_dt = Column(DateTime(timezone=True), server_default=func.now())

    activities = relationship("ExecutablePlan" ,back_populates="executable_plan")
    created_activities = relationship("CreatedPlan" ,back_populates="created_plan")

class CreatedPlan(Base):
    __tablename__ = "created_plan"
    plan_id = Column(UUID(as_uuid=True),ForeignKey('user_plan.plan_id'), primary_key=True )
    entity_id = Column(UUID(as_uuid=True), primary_key=True, server_default=str("gen_random_uuid()"))
    parent_id = Column(UUID(as_uuid=True), nullable=True )
    entity_type = Column(Integer, nullable=False)
    status_id = Column(Integer, nullable=False)
    source_id = Column(Integer, nullable=False)
    level_id = Column(Integer, nullable=False)
    sequence_id = Column(Integer, nullable=False)
    entity_desc = Column(String, nullable=False)
    suggested_duration = Column(String, nullable=False)
    suggested_start_time = Column(String, nullable=True)

    created_plan = relationship("UserPlan" ,back_populates="created_activities")

class ExecutablePlan(Base):
    __tablename__ = "executable_plan"
    plan_id = Column(UUID(as_uuid=True),ForeignKey('user_plan.plan_id'), primary_key=True )
    entity_id = Column(UUID(as_uuid=True), primary_key=True )
    parent_id = Column(UUID(as_uuid=True), nullable=True )
    entity_type = Column(Integer, nullable=False)
    status_id = Column(Integer, nullable=False)
    level_id = Column(Integer, nullable=False)
    sequence_id = Column(Integer, nullable=False)
    reminder_request = Column(Integer, nullable=False)
    progress_measure = Column(Float, nullable=False)
    activity_desc = Column(String, nullable=False)
    start_date = Column(DateTime(timezone=True), nullable=True)
    request_reminder_time = Column(String, nullable=True)
    objective_completion_dt = Column(DateTime(timezone=True), nullable=True)
    executable_plan = relationship("UserPlan", back_populates="activities")

class PlanDetailChangeLog(Base):
    __tablename__ = "plan_detail_change_log"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=str("gen_random_uuid()") )
    plan_id = Column(UUID(as_uuid=True), nullable=False)
    entity_id = Column(UUID(as_uuid=True), nullable=False)
    old_start_date = Column(DateTime(timezone=True), nullable=False)
    new_start_date = Column(DateTime(timezone=True), nullable=False)
    changed_at = Column(DateTime(timezone=True), server_default=func.now())
    change_reason = Column(String, nullable=True)
    changed_by = Column(String, nullable=True)


class PlanChangeLog(Base):
    __tablename__ = "plan_change_log"

    id = Column(UUID(as_uuid=True), primary_key=True,server_default=str("gen_random_uuid()") )
    plan_id = Column(UUID(as_uuid=True), nullable=False)
    old_start_date = Column(DateTime(timezone=True), nullable=False)
    new_start_date = Column(DateTime(timezone=True), nullable=False)
    change_reason = Column(String, nullable=True)
    changed_at = Column(DateTime(timezone=True), server_default=func.now())
    changed_by = Column(String, nullable=True)


async def insert_plan(user_plan: UserPlanModel , db: AsyncSession) -> Optional[UXUserPlanIdentifier]:

    if not user_plan:
        logger.error("Attempted to insert None as user plan")
        raise MissingDataException(
            "User plan data is required",context = {"user_plan" :  "user plan not defined"}
        )
    
    # Validate required fields
    if not user_plan.user_id:
        logger.error("Missing required field: user_id")
        raise MissingDataException(
                "User ID is required",
                context= { "user_id" : "user id is missing in user plan"}
        )
    
    if not user_plan.plan_name or not user_plan.plan_name.strip():
        logger.error("Missing or empty required field: plan_name")
        raise MissingDataException(
                "plan nameis required",
                context= { "plan_name" : "plan name is missing in user plan"}
        )
    
    if not user_plan.plan_type or not user_plan.plan_type.strip():
        logger.error("Missing or empty required field: plan_type")
        raise MissingDataException(
                "plan type required",
                context= { "plan_type" : "plan type is missing in user plan"}
        )
    
    if not user_plan.plan_goal or not user_plan.plan_goal.strip():
        logger.error("Missing or empty required field: plan_goal")
        raise MissingDataException(
                "Plan goalis required",
                context= { "plan_goal" : "plan goal is missing in user plan"}
        )
    
    try:
        # Create the user plan database object

        stmt = insert(UserPlan).values(
            user_id = user_plan.user_id,
            plan_name = user_plan.plan_name,
            plan_type = user_plan.plan_type,
            plan_goal = user_plan.plan_goal,
            goal_duration = user_plan.goal_duration,
            plan_status = user_plan.plan_status,
            plan_category = user_plan.plan_category
        ).returning(UserPlan)

        result = await db.execute(stmt)
        user_plan_obj =  result.scalar_one()
        return user_plan_obj
        
        
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

    
async def get_plan(filter_params: Optional[Dict[str, Any]], db: AsyncSession) -> Optional[List[UserPlanIdentifierModel]]:
    try:

        stmt = select(UserPlan)
        if filter_params:
            if filter_params.get("plan_id") is not None:
                stmt = stmt.filter(UserPlan.plan_id == filter_params["plan_id"])
            if filter_params.get("approved_by_user") is not None:
                stmt = stmt.filter(UserPlan.approved_by_user == filter_params["approved_by_user"])
            if filter_params.get("user_id") is not None:
                stmt = stmt.filter(UserPlan.user_id == filter_params["user_id"])
        logger.info(f"The SQL statement is {stmt}")
        result = await db.execute(stmt)
        return result.scalars().all()
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


async def update_plan(
    plan_id: UUID,
    value_params: dict,
    db: AsyncSession
) -> Optional[UserPlan]:

    try:
        # Prepare update values
        update_values = {}

        # Build update_values and params at the same time
        params = {
            "plan_idx": plan_id
        }

        if "approved_by_user" in value_params:
            update_values["approved_by_user"] = bindparam("approved_by_user")
            params["approved_by_user"] = value_params["approved_by_user"]
        
        if "private_flag" in value_params:
            update_values["private_flag"] = bindparam("private_flag")
            params["private_flag"] = value_params["private_flag"]
        
        if "follow_flag" in value_params:
            update_values["follow_flag"] = bindparam("follow_flag")
            params["follow_flag"] = value_params["follow_flag"]
                                                        
        if "plan_start_date" in value_params :
            update_values["plan_start_date"] = bindparam("plan_start_date")
            params["plan_start_date"] = value_params["plan_start_date"]

        if "plan_end_date" in value_params :
            update_values["plan_end_date"] = bindparam("plan_end_date")
            params["plan_end_date"] = value_params["plan_end_date"]
        
        if "plan_status" in value_params :
            update_values["plan_status"] = bindparam("plan_status")
            params["plan_status"] = value_params["plan_status"]

        # Skip update if no values to update
        if not update_values:
            return None  # Or fetch and return the existing record

        stmt = (
            update(UserPlan)
            .where(
                UserPlan.plan_id == bindparam("plan_idx")
            )
            .values(**update_values)
            .returning(UserPlan)
        )
        
        result = await db.execute(stmt, params)
        
        # Return the updated plan
        updated_plan = result.scalar_one_or_none()
        return updated_plan
        
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



async def insert_approved_plan(user_plan: IExecutionPlanDetail , db: AsyncSession) -> Optional[IExecutionPlanDetail]:
    """
    Insert a new user plan into the database.
    
    Args:
        db: Database session
        user_plan: User plan data to insert
        
    Returns:
        UserPlanIdentifierModel with the new plan ID or None if an error occurs
        
    Raises:
        HTTPException: For database errors or validation issues
    """
    if not user_plan:
        logger.error("Attempted to insert None as user plan")
        raise GeneralDataException(
            f"Not all required inputs are in the approved plan",
            context={"detail": f"Some inputs are missingin the executable plan input"}
        )
    
    try:
        # Create the user plan database object

        stmt = insert(ExecutablePlan).values(
            plan_id = user_plan.plan_id,
            entity_id = user_plan.entity_id,
            parent_id = user_plan.parent_id,
            entity_type = user_plan.entity_type,
            status_id = user_plan.status_id,
            reminder_request = user_plan.reminder_request,
            progress_measure = user_plan.progress_measure,
            activity_desc = user_plan.activity_desc,
            start_date = user_plan.start_date,
            sequence_id = user_plan.sequence_id,
            level_id = user_plan.level_id,
            request_reminder_time = user_plan.request_reminder_time
        ).returning(ExecutablePlan)

        result = await db.execute(stmt)
        user_plan_obj =  result.scalar_one()
        return user_plan_obj
        
        
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


async def insert_created_plan(user_plan: ICreatedPlan , db: AsyncSession) -> Optional[CreatedPlan]:
    """
    Insert a new user plan into the database.
    
    Args:
        db: Database session
        user_plan: User plan data to insert
        
    Returns:
        UserPlanIdentifierModel with the new plan ID or None if an error occurs
        
    Raises:
        HTTPException: For database errors or validation issues
    """
    if not user_plan:
        logger.error("Attempted to insert None as user plan")
        raise GeneralDataException(
            f"Not all required inputs are in the approved plan",
            context={"detail": f"Some inputs are missingin the executable plan input"}
        )
    
    try:
        # Create the user plan database object

        stmt = insert(CreatedPlan).values(
            plan_id = user_plan.plan_id,
            parent_id = user_plan.parent_id,
            entity_type = user_plan.entity_type,
            status_id = user_plan.status_id,
            entity_desc = user_plan.entity_desc,
            sequence_id = user_plan.sequence_id,
            level_id = user_plan.level_id,
            suggested_duration = user_plan.suggested_duration,
            suggested_start_time = user_plan.suggested_start_time,
            source_id = user_plan.source_id
        ).returning(CreatedPlan)

        result = await db.execute(stmt)
        user_plan_obj =  result.scalar_one()
        return user_plan_obj
        
        
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

async def get_executable_plan(filter_params: Optional[Dict[str, Any]], db: AsyncSession) -> Optional[List[IExecutionPlanDetail]]:
    try:

        stmt = select(ExecutablePlan)
        stmt = stmt.join(UserPlan, ExecutablePlan.plan_id == UserPlan.plan_id)
        if filter_params:
            if filter_params.get("plan_id") is not None:
                stmt = stmt.filter(UserPlan.plan_id == filter_params["plan_id"])
            if filter_params.get("user_id") is not None:
                stmt = stmt.filter(UserPlan.user_id == filter_params["user_id"])     
            if filter_params.get("sequence_id") is not None:
                stmt = stmt.filter(ExecutablePlan.sequence_id >= filter_params["sequence_id"])
            if filter_params.get("entity_id") is not None:
                stmt = stmt.filter(ExecutablePlan.entity_id == filter_params["entity_id"])
            if filter_params.get("parent_id") is not None:
                stmt = stmt.filter(ExecutablePlan.parent_id == filter_params["parent_id"])

            stmt = stmt.order_by(ExecutablePlan.sequence_id.asc())
        logger.info(f"The SQL statement is {stmt}")
        result = await db.execute(stmt)
        return result.scalars().all()
    except IntegrityError as e:

        logger.error(f"Error in selecting from the executable plan: {str(e)}")
        raise IntegrityException(
            "rror in selecting from the executable plan",
            context = {"detail": "Check if you have given the right values for the parameters. Error in selecting from executable plan."}
        )
    except SQLAlchemyError as e:

        logger.error(f"Database Error in selecting from the executable pla: {str(e)}")
        raise GeneralDataException(
            "Data base eError in selecting from the executable pla",
            context={"detail": "Database error Error in selecting from the executable pla"}
        )
    except Exception as e:

        logger.error(f"Unexpected Error in selecting from the executable pla: {str(e)}")
        raise GeneralDataException(
            "Unexpected Error in selecting from the executable pla",
            context={"detail" : "An unexpected Error in selecting from the executable pla"}
        )


async def get_created_plan(filter_params: Optional[Dict[str, Any]], db: AsyncSession) -> Optional[List[CreatedPlan]]:
    try:

        stmt = select(CreatedPlan)
        stmt = stmt.join(UserPlan, CreatedPlan.plan_id == UserPlan.plan_id)
        if filter_params:
            if filter_params.get("plan_id") is not None:
                stmt = stmt.filter(CreatedPlan.plan_id == filter_params["plan_id"])
            if filter_params.get("user_id") is not None:
                stmt = stmt.filter(UserPlan.user_id == filter_params["user_id"])     
            if filter_params.get("sequence_id") is not None:
                stmt = stmt.filter(CreatedPlan.sequence_id >= filter_params["sequence_id"])
            if filter_params.get("entity_id") is not None:
                stmt = stmt.filter(CreatedPlan.entity_id == filter_params["entity_id"])
            if filter_params.get("start_date") is not None:
                '''
                use this filter for upcoming tasks
                '''
                stmt = stmt.filter(CreatedPlan.start_date >= filter_params["start_date"])
                end_date = filter_params["start_date"] + timedelta(days=filter_params["days_to_add"])
                stmt = stmt.filter(CreatedPlan.start_date <= end_date)

            stmt.order_by(CreatedPlan.sequence_id)

        logger.info(f"The SQL statement is {stmt}")
        result = await db.execute(stmt)
        return result.scalars().all()
    except IntegrityError as e:

        logger.error(f"Error in selecting from the executable plan: {str(e)}")
        raise IntegrityException(
            "rror in selecting from the executable plan",
            context = {"detail": "Check if you have given the right values for the parameters. Error in selecting from executable plan."}
        )
    except SQLAlchemyError as e:

        logger.error(f"Database Error in selecting from the executable pla: {str(e)}")
        raise GeneralDataException(
            "Data base eError in selecting from the executable pla",
            context={"detail": "Database error Error in selecting from the executable pla"}
        )
    except Exception as e:

        logger.error(f"Unexpected Error in selecting from the executable pla: {str(e)}")
        raise GeneralDataException(
            "Unexpected Error in selecting from the executable pla",
            context={"detail" : "An unexpected Error in selecting from the executable pla"}
        )

'''
SELECT *
FROM executable_plan
WHERE 
    status_id = 99
    OR (
        status_id IS NULL 
        AND (
            start_date <= CURRENT_TIMESTAMP 
            OR 
            start_date BETWEEN CURRENT_TIMESTAMP 
              AND CURRENT_TIMESTAMP + make_interval(days => :days_ahead)
        )
    )

SELECT *,
  CASE
    WHEN status_id IS NULL AND start_date < NOW() THEN 'should_have_begun'
    WHEN status_id = 99 THEN 'in_progress'
    WHEN status_id IS NULL AND start_date BETWEEN NOW() AND NOW() + INTERVAL '3 days' THEN 'starting_soon'
    ELSE 'other'
  END AS status_category
FROM executable_plan
WHERE
  (status_id IS NULL AND start_date < NOW()) OR
  (status_id = 99) OR
  (status_id IS NULL AND start_date BETWEEN NOW() AND NOW() + INTERVAL '3 days')
ORDER BY start_date;
'''



async def get_upcoming_activities_db(filter_params: Optional[Dict[str, Any]], db: AsyncSession):
    try:
        stmt = select(
            UserPlan.plan_id.label("user_plan_id"), 
            UserPlan.plan_name.label("plan_name"),
            ExecutablePlan.entity_id.label("entity_id"),
            ExecutablePlan.activity_desc.label("activity_desc"),
            func.to_char(ExecutablePlan.start_date, "YYYY-MM-DD HH24:MI:SS").label("start_date"),
            ExecutablePlan.reminder_request.label("reminder_request"),
            ExecutablePlan.request_reminder_time.label("request_reminder_time"),
            ExecutablePlan.entity_type.label("entity_type"),
            ExecutablePlan.status_id.label("status_id"),
            ExecutablePlan.progress_measure,
            func.coalesce(ProgressUpdate.progress_percent,0.0).label("progress_percent")  # <-- new field
        ).join(
            UserPlan, 
            ExecutablePlan.plan_id == UserPlan.plan_id
        ).outerjoin(
            ProgressUpdate, 
            and_(
                ExecutablePlan.plan_id == ProgressUpdate.plan_id,
                ExecutablePlan.entity_id == ProgressUpdate.entity_id
            )
        )

        if "start_date" in filter_params:
            end_date = filter_params["start_date"] + timedelta(
            days=filter_params.get("days_to_add", 7)
            )
        
        # Core filtering logic for task status and timeline
        stmt = stmt.where(
            or_(
                ExecutablePlan.status_id == 1,  # In-progress tasks
                and_(
                    ExecutablePlan.status_id == 0,  # Not started
                    or_(
                        ExecutablePlan.start_date <= func.now(),  # Overdue
                        ExecutablePlan.start_date.between(  # Upcoming
                            filter_params["start_date"],
                            end_date
                        )
                    )
                )
            )
        )
        stmt = stmt.filter(ExecutablePlan.entity_type != 999)
        # Apply additional filters
        if filter_params:
            if "plan_id" in filter_params:
                stmt = stmt.filter(UserPlan.plan_id == filter_params["plan_id"])
            if "user_id" in filter_params:
                stmt = stmt.filter(UserPlan.user_id == filter_params["user_id"])
            if "sequence_id" in filter_params:
                stmt = stmt.filter(
                    ExecutablePlan.sequence_id >= filter_params["sequence_id"]
                )
            if "entity_id" in filter_params:
                stmt = stmt.filter(
                    ExecutablePlan.entity_id == filter_params["entity_id"]
                )


        # Consistent ordering
        stmt = stmt.order_by(ExecutablePlan.sequence_id)

        logger.info(f"Generated SQL: {stmt}")
        result = await db.execute(stmt)
        ret =  result.mappings().all()
        return ret

    except IntegrityError as e:
        logger.error(f"Data integrity error: {str(e)}")
        raise IntegrityException(
            "Data consistency violation in plan query",
            context={"detail": "Verify input parameters and system state"}
        )
    except SQLAlchemyError as e:
        logger.error(f"Database operation failed: {str(e)}")
        raise GeneralDataException(
            "Database access error",
            context={"detail": "Failed to retrieve execution plan"}
        )
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise GeneralDataException(
            "System error retrieving plan",
            context={"detail": "Please contact technical support"}
        )

    
async def update_executable_plan(
    filter_params: Optional[Dict[str, Any]],
    value_params: Optional[Dict[str, Any]],
    db: AsyncSession
) -> Optional[ExecutablePlan]:  # Adjust return type if needed
    try:
        update_values = {}
        if value_params:
            if "start_date" in value_params:
                update_values["start_date"] = bindparam("start_date")
            if "status_id" in value_params:
                update_values["status_id"] = bindparam("status_id")
            if "reminder_request" in value_params:
                update_values["reminder_request"] = bindparam("reminder_request")
            if "request_reminder_time" in value_params:
                update_values["request_reminder_time"] = bindparam("request_reminder_time")
            if "objective_completion_dt" in value_params:
                update_values["objective_completion_dt"] = bindparam("objective_completion_dt")

        params = {}
        if filter_params:
            if "plan_id" in filter_params:
                params["b_plan_id"] = filter_params["plan_id"]
            if "entity_id" in filter_params:
                params["b_entity_id"] = filter_params["entity_id"]
            if "sequence_id" in filter_params:
                params["b_sequence_id"] = filter_params["sequence_id"]  
           

        if not update_values or not params:
            raise ValueError("Missing required filter or update values.")
        
        where_clauses = [
                ExecutablePlan.plan_id == bindparam("b_plan_id"),
                ExecutablePlan.entity_id == bindparam("b_entity_id")
                        ]

        if "sequence_id" in filter_params:
            where_clauses.append(ExecutablePlan.sequence_id == bindparam("b_sequence_id"))

        stmt = (
            update(ExecutablePlan)
            .where(*where_clauses)
            .values(**update_values)
            .returning(ExecutablePlan)  # or UserPlan if that’s what you want
        )

        result = await db.execute(stmt, {**params, **value_params})


        return result.scalars().all()

    except IntegrityError as e:
        await db.rollback()
        logger.error(f"IntegrityError when updating executable plan: {str(e)}")
        raise IntegrityException("Integrity error when updating executable plan", context={"detail": str(e)})

    except SQLAlchemyError as e:

        logger.error(f"Database error: {str(e)}")
        raise GeneralDataException("Database error updating executable plan", context={"detail": str(e)})

    except Exception as e:

        logger.error(f"Unexpected error: {str(e)}")
        raise GeneralDataException("Unexpected error updating executable plan", context={"detail": str(e)})


async def set_reminder_executable_plan(
    filter_params: Optional[Dict[str, Any]],
    value_params: Optional[Dict[str, Any]],
    db: AsyncSession
) -> Optional[ExecutablePlan]:  # Adjust return type if needed
    try:
        update_values = {}
        if value_params:
            if "reminder_request" in value_params:
                update_values["reminder_request"] = bindparam("reminder_request")
            if "request_reminder_time" in value_params:
                update_values["request_reminder_time"] = bindparam("request_reminder_time")

        params = {}
        if filter_params:
            if "plan_id" in filter_params:
                params["b_plan_id"] = filter_params["plan_id"]
            if "entity_id" in filter_params:
                params["b_entity_id"] = filter_params["entity_id"]

        if not update_values or not params:
            raise ValueError("Missing required filter or update values.")

        stmt = (
            update(ExecutablePlan)
            .where(
                ExecutablePlan.plan_id == bindparam("b_plan_id"),
                ExecutablePlan.entity_id == bindparam("b_entity_id")
            )
            .values(**update_values)
            .returning(ExecutablePlan)  # or UserPlan if that’s what you want
        )

        result = await db.execute(stmt, {**params, **value_params})


        return result.scalar_one_or_none()

    except IntegrityError as e:
        await db.rollback()
        logger.error(f"IntegrityError when updating executable plan: {str(e)}")
        raise IntegrityException("Integrity error when updating executable plan", context={"detail": str(e)})

    except SQLAlchemyError as e:

        logger.error(f"Database error: {str(e)}")
        raise GeneralDataException("Database error updating executable plan", context={"detail": str(e)})

    except Exception as e:

        logger.error(f"Unexpected error: {str(e)}")
        raise GeneralDataException("Unexpected error updating executable plan", context={"detail": str(e)})


"""
APIs for 
- Upcoming tasks - current day + 2
- Incomplete tasks - This should be applicable only for executed plan
"""


async def insert_goal_builder(user_plan: UXGoalBuilder , db: AsyncSession) -> Optional[UXGoalBuilder]:
    """
    Insert a new user plan into the database.
    
    Args:
        db: Database session
        user_plan: User plan data to insert
        
    Returns:
        UserPlanIdentifierModel with the new plan ID or None if an error occurs
        
    Raises:
        HTTPException: For database errors or validation issues
    """
    if not user_plan:
        logger.error("Attempted to insert None as user plan")
        raise MissingDataException(
            "User plan data is required",context = {"user_plan" :  "user plan not defined"}
        )
    
    
    try:
        # Create the user plan database object

        stmt = insert(GoalBuilder).values(
            plan_id = user_plan.plan_id,
            prev_plan_id = user_plan.prev_plan_id,
            prompt_text = user_plan.prompt_text,
            plan_name = user_plan.plan_name,
            session_id = user_plan.session_id,
            root_id = user_plan.root_id,
            llm_source = user_plan.llm_source,
            revised_prompt_summary = user_plan.revised_prompt_summary,
            user_id = user_plan.user_id,
            concatenated_prompt = user_plan.concatenated_prompt
        ).returning(GoalBuilder)

        result = await db.execute(stmt)
        user_plan_obj =  result.scalar_one()
        return user_plan_obj
        
        
    except IntegrityError as e:

        logger.error(f"IntegrityError when inserting into goal builder: {str(e)}")
        raise IntegrityException(
            f"Integrity error when inserting a record in goal builder {str(e)}",
            context = {"detail": f"Integrity error when inserting a record in goal builder"}
        )
    except SQLAlchemyError as e:

        logger.error(f"Database error when inserting goal: {str(e)}")
        raise GeneralDataException(
            f"Data error when inserting a record in goal builder {str(e)}",
            context = {"detail": f"Data error when inserting a record in goal builder"}
        )
    except Exception as e:

        logger.error(f"Unexpected error in goal: {str(e)}")
        raise GeneralDataException(
            f"Exception  when inserting a record in goal builder {str(e)}",
            context = {"detail": f"Exception  when inserting a record in goal builder"}
        )
async def get_goal_builder(filter_params: Optional[Dict[str, Any]], db: AsyncSession) -> Optional[List[GoalBuilder]]:
    try:
        

        if filter_params:
            stmt = select(GoalBuilder)
            if filter_params["intent"] == "calc":

                stmt = stmt.order_by(GoalBuilder.sequence_id)
            else:
                stmt = stmt.order_by(GoalBuilder.created_dt.asc())
            if filter_params.get("plan_id") is not None:
                stmt = stmt.filter(GoalBuilder.plan_id == filter_params["plan_id"])
            if filter_params.get("prev_plan_id") is not None:
                stmt = stmt.filter(GoalBuilder.prev_plan_id == filter_params["prev_plan_id"])
            if filter_params.get("root_id") is not None:
                stmt = stmt.filter(GoalBuilder.root_id == filter_params["root_id"])
            if filter_params.get("user_id") is not None:
                stmt = stmt.filter(GoalBuilder.user_id == filter_params["user_id"])
            result = await db.execute(stmt)
            return result.scalars().all()
        return 0
    
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


async def insert_general_guideline(plan_id_x: str, general_description: str , db: AsyncSession) -> Optional[List[PlanGeneralGuideline]]:

    
    try:
        # Create the user plan database object

        stmt = insert(PlanGeneralGuideline).values(
                plan_id = plan_id_x,
                guideline = general_description
            ).returning(PlanGeneralGuideline)

        result = await db.execute(stmt)
        user_plan_obj =  result.scalar_one()
        return user_plan_obj
        
        
    except IntegrityError as e:

        logger.error(f"IntegrityError when inserting general guideline: {str(e)}")
        raise IntegrityException(
            f"Integrity error when inserting general guideline{str(e)}",
            context = {"detail": f"Issue inserting into the general guideline"}
        )
    except SQLAlchemyError as e:

        logger.error(f"Database error when inserting general guideline: {str(e)}")
        raise GeneralDataException(
            "Data base error occured while inserting general guideline",
            context={"detail": "Database error occurred while general guideline"}
        )
    except Exception as e:

        logger.error(f"Unexpected error in general guideline: {str(e)}")
        raise GeneralDataException(
            "Unexpected error occured inserting general guideline",
            context={"detail" : "An unexpected error occurred while general guideline"}
        )


async def insert_plan_routine_summary(plan_id_x: str, summary_item: str , db: AsyncSession) -> Optional[List[PlanRoutineSummary]]:
    try:
        # Create the user plan database object

        stmt = insert(PlanRoutineSummary).values(
                plan_id = plan_id_x,
                routine = summary_item
            ).returning(PlanRoutineSummary)

        result = await db.execute(stmt)
        user_plan_obj =  result.scalar_one()
        return user_plan_obj
        
        
    except IntegrityError as e:

        logger.error(f"IntegrityError when inserting routine summary: {str(e)}")
        raise IntegrityException(
            f"Integrity error when inserting routine summary{str(e)}",
            context = {"detail": f"Issue inserting into the routine summary"}
        )
    except SQLAlchemyError as e:

        logger.error(f"Database error when inserting routine summary: {str(e)}")
        raise GeneralDataException(
            "Data base error occured while inserting routine summary",
            context={"detail": "Database error occurred while routine summary"}
        )
    except Exception as e:

        logger.error(f"Unexpected error in routine summary: {str(e)}")
        raise GeneralDataException(
            "Unexpected error occured inserting routine summary",
            context={"detail" : "An unexpected error occurred while routine summary"}
        )


async def get_general_guidelines(filter_params: Optional[Dict[str, Any]], db: AsyncSession) -> Optional[List[PlanGeneralGuideline]]:
    try:

        stmt = select(PlanGeneralGuideline.plan_id, PlanGeneralGuideline.guideline)
       
        if filter_params:
            if filter_params.get("plan_id") is not None:
                stmt = stmt.filter(PlanGeneralGuideline.plan_id == filter_params["plan_id"])
        result = await db.execute(stmt)
        return result.all()
    except IntegrityError as e:

        logger.error(f"Error in selecting from general guideline: {str(e)}")
        raise IntegrityException(
            "rror in selecting from the general guideline",
            context = {"detail": "Check if you have given the right values for the parameters. Error in selecting from general guideline."}
        )
    except SQLAlchemyError as e:

        logger.error(f"Database Error in selecting from general guideline: {str(e)}")
        raise GeneralDataException(
            "Data base eError in selecting from general guideline",
            context={"detail": "Database error Error in selecting from general guideline"}
        )
    except Exception as e:

        logger.error(f"Unexpected Error in selecting from general guideline: {str(e)}")
        raise GeneralDataException(
            "Unexpected Error in selecting from general guideline",
            context={"detail" : "An unexpected Error in selecting from general guideline"}
        )

async def get_plan_routine_summary(filter_params: Optional[Dict[str, Any]], db: AsyncSession) -> Optional[List[PlanRoutineSummary]]:
    try:

        stmt = select(PlanRoutineSummary.plan_id, PlanRoutineSummary.routine)
       
        if filter_params:
            if filter_params.get("plan_id") is not None:
                stmt = stmt.filter(PlanRoutineSummary.plan_id == filter_params["plan_id"])
        result = await db.execute(stmt)
        return result.all()
    except IntegrityError as e:

        logger.error(f"Error in selecting from routine summary: {str(e)}")
        raise IntegrityException(
            "rror in selecting from the routine summary",
            context = {"detail": "Check if you have given the right values for the parameters. Error in selecting from routine summary."}
        )
    except SQLAlchemyError as e:

        logger.error(f"Database Error in selecting from routine summary: {str(e)}")
        raise GeneralDataException(
            "Data base eError in selecting from routine summary",
            context={"detail": "Database error Error in selecting from routine summary"}
        )
    except Exception as e:

        logger.error(f"Unexpected Error in selecting from routine summary: {str(e)}")
        raise GeneralDataException(
            "Unexpected Error in selecting from routine summary",
            context={"detail" : "An unexpected Error in selecting from routine summary"}
        )
    


async def insert_into_plan_detail_change_log(
    db: AsyncSession,
    plan_id: UUID,
    entity_id: UUID,
    old_start_date: datetime,
    new_start_date: datetime,
    reason: str = None
):
    try:
        changed_by = f"system"
        change = PlanDetailChangeLog(
            plan_id=plan_id,
            entity_id=entity_id,
            old_start_date=old_start_date,
            new_start_date=new_start_date,
            changed_by=changed_by
        )
        res = db.add(change)
        return res
    except IntegrityError as e:

        logger.error(f"Error in selecting from routine summary: {str(e)}")
        raise IntegrityException(
            "rror in selecting from the routine summary",
            context = {"detail": "Check if you have given the right values for the parameters. Error in selecting from routine summary."}
        )
    except SQLAlchemyError as e:

        logger.error(f"Database Error in selecting from routine summary: {str(e)}")
        raise GeneralDataException(
            "Data base eError in selecting from routine summary",
            context={"detail": "Database error Error in selecting from routine summary"}
        )
    except Exception as e:

        logger.error(f"Unexpected Error in selecting from routine summary: {str(e)}")
        raise GeneralDataException(
            "Unexpected Error in selecting from routine summary",
            context={"detail" : "An unexpected Error in selecting from routine summary"}
        )
    


async def insert_into_plan_change_log(
    db: AsyncSession,
    plan_id: UUID,
    old_start_date: datetime,
    new_start_date: datetime,
    reason: str = None
):
    try:
        changed_by = f"system"
        change = PlanChangeLog(
            plan_id=plan_id,
            old_start_date=old_start_date,
            new_start_date=new_start_date,
            changed_by=changed_by,
            change_reason=reason,
        )
        res = db.add(change)
        return res
    except IntegrityError as e:

        logger.error(f"Error in selecting from routine summary: {str(e)}")
        raise IntegrityException(
            "rror in selecting from the routine summary",
            context = {"detail": "Check if you have given the right values for the parameters. Error in selecting from routine summary."}
        )
    except SQLAlchemyError as e:

        logger.error(f"Database Error in selecting from routine summary: {str(e)}")
        raise GeneralDataException(
            "Data base eError in selecting from routine summary",
            context={"detail": "Database error Error in selecting from routine summary"}
        )
    except Exception as e:

        logger.error(f"Unexpected Error in selecting from routine summary: {str(e)}")
        raise GeneralDataException(
            "Unexpected Error in selecting from routine summary",
            context={"detail" : "An unexpected Error in selecting from routine summary"}
        )
    
async def get_task_change_history(db: AsyncSession, plan_id: UUID):
    try:
        # Construct the select statement properly
        stmt = select(
            PlanDetailChangeLog.entity_id,
            func.count().label("change_count"),
            func.array_agg(text("change_reason::text")).label("reasons"),
            func.array_agg(text("changed_at::timestamp")).label("timestamps"),
            func.array_agg(PlanDetailChangeLog.new_start_date).label("dates")
        ).select_from(
            PlanDetailChangeLog
        ).filter(
            PlanDetailChangeLog.plan_id == plan_id
        ).group_by(
            PlanDetailChangeLog.entity_id
        )
        # Execute the statement
        result = await db.execute(stmt)
        results = result.all()
        
        return results
    except IntegrityError as e:
        logger.error(f"Error in selecting from routine summary: {str(e)}")
        raise IntegrityException(
            "Error in selecting from the routine summary",
            context={"detail": "Check if you have given the right values for the parameters. Error in selecting from routine summary."}
        )
    except SQLAlchemyError as e:
        logger.error(f"Database Error in selecting from routine summary: {str(e)}")
        raise GeneralDataException(            "Database Error in selecting from routine summary",
            context={"detail": "Database error Error in selecting from routine summary"}
        )
    except Exception as e:
        logger.error(f"Unexpected Error in selecting from routine summary: {str(e)}")
        raise GeneralDataException(
            "Unexpected Error in selecting from routine summary",
            context={"detail": "An unexpected Error in selecting from routine summary"}
        )

async def get_plan_change_history(db: AsyncSession, plan_id: UUID):
    try:
        # Construct the select statement properly
        stmt = select(
            PlanChangeLog.plan_id,
            func.count().label("change_count"),
            func.array_agg(cast(PlanChangeLog.change_reason, String)).label("reasons"),
            func.array_agg(cast(PlanChangeLog.changed_at, DateTime)).label("timestamps"),
            func.array_agg(cast(PlanChangeLog.new_start_date, DateTime)).label("dates")
        ).filter(
            PlanChangeLog.plan_id == plan_id
        ).group_by(
            PlanChangeLog.plan_id
        )
        # Execute the statement
        result = await db.execute(stmt)
        results = result.all()
        
        return results
    except IntegrityError as e:
        logger.error(f"Error in selecting from routine summary: {str(e)}")
        raise IntegrityException(
            "Error in selecting from the routine summary",
            context={"detail": "Check if you have given the right values for the parameters. Error in selecting from routine summary."}
        )
    except SQLAlchemyError as e:
        logger.error(f"Database Error in selecting from routine summary: {str(e)}")
        raise GeneralDataException(            "Database Error in selecting from routine summary",
            context={"detail": "Database error Error in selecting from routine summary"}
        )
    except Exception as e:
        logger.error(f"Unexpected Error in selecting from routine summary: {str(e)}")
        raise GeneralDataException(
            "Unexpected Error in selecting from routine summary",
            context={"detail": "An unexpected Error in selecting from routine summary"}
        )