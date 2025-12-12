from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, func, Float
from sqlalchemy.dialects.postgresql import UUID
from app.data.dbinit import Base
import uuid
from sqlalchemy.future import select
from sqlalchemy import update, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.model.progress_mgmt import ProgressUpdateCreate, ProgressUpdateOut, ProgressSummary, ProgressWeeklyDetail, ProgressDailyDetail
from app.data.user_plan import ExecutablePlan, UserPlan, update_plan, update_executable_plan, get_plan
from app.data.user import User as DreavUser
from app.common.site_enums import TaskStatus, PlanStatus
from sqlalchemy.exc import SQLAlchemyError, MultipleResultsFound, NoResultFound, IntegrityError
from app.common.exception import GeneralDataException, IntegrityException
from datetime import datetime, timezone, timedelta
from app.data.common_table import ProgressUpdate
from typing import List, Optional
from app.data.user import User
import structlog


class ProgressTracking(Base):
    __tablename__ = 'progress_tracking'

    entity_id = Column(UUID(as_uuid=True), primary_key=True)  # Same as executable_plan.entity_id
    plan_id = Column(UUID(as_uuid=True))
    cumulative_progress = Column(Float, default=0.0)
    notes = Column(Text, nullable=True)
    milestone_25 = Column(Integer, default=0)
    milestone_50 = Column(Integer, default=0)
    milestone_75 = Column(Integer, default=0)
    milestone_100 = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())


logger = structlog.get_logger()

async def create_progress_update(db: AsyncSession, update_data: ProgressUpdateCreate, current_user: User):
    try:
        stmt = select(ProgressUpdate).where(
            ProgressUpdate.entity_id == update_data.entity_id
        ).order_by(ProgressUpdate.created_at.desc())

        result = await db.execute(stmt)
        last_update = result.scalars().first()

        task_status = 0;

        if update_data.progress_percent == 100:
            task_status = TaskStatus.COMPLETE
        elif update_data.progress_percent > 0:
            task_status = TaskStatus.IN_PROGRESS
            
        else:
            task_status = TaskStatus.NOT_STARTED
        value_params = {}
        value_params["plan_id"] = update_data.plan_id

        if task_status.value == TaskStatus.COMPLETE.value:
            plan_res = await check_plan_completion(update_data.plan_id, db)
            if plan_res:
                if plan_res[0].total_tasks == plan_res[0].total_completed_tasks + 1:
                    value_params["plan_status"] = PlanStatus.COMPLETE.value
                    ret = await update_plan(update_data.plan_id,value_params, db)
        else:
            value_params["plan_status"] = PlanStatus.IN_PROGRESS.value
            ret = await update_plan(update_data.plan_id,value_params, db)        

        if last_update:
            last_update.entity_id=update_data.entity_id
            last_update.plan_id=update_data.plan_id
            last_update.progress_percent=update_data.progress_percent
            last_update.notes = (last_update.notes or "") + "\n" + (update_data.notes or "")
        else:
            new_update = ProgressUpdate(
                entity_id=update_data.entity_id,
                plan_id=update_data.plan_id,
                progress_percent=update_data.progress_percent,
                notes=update_data.notes
            )
            db.add(new_update)
        await db.flush()
        await update_progress_tracking(db, update_data.entity_id, 
                                       update_data.plan_id, 
                                       update_data.progress_percent,
                                       update_data.notes)
        await db.flush()
        plan_progress_res = await rollup_progress(db, update_data.plan_id, update_data.entity_id, current_user.user_id)

        ret = ProgressUpdateOut(entity_id=update_data.entity_id, 
                                progress_percent=update_data.progress_percent, 
                                notes=update_data.notes,
                                 plan_progress= plan_progress_res )
        filter_params = {}
        value_params = {}
        filter_params["plan_id"] = update_data.plan_id
        filter_params["entity_id"] = update_data.entity_id
        value_params["status_id"] = task_status.value
        if update_data.progress_percent == 100:
            value_params["objective_completion_dt"] = datetime.now(timezone.utc)
        ret_objective_status = await update_executable_plan(filter_params, value_params, db)
        return ret
    
    except IntegrityError as e:
        logger.error(f"IntegrityError when updating executable plan: {str(e)}")
        raise IntegrityException(
            "Integrity error when updating executable plan",
            context = {"detail": f"Issue with updating the executable plan {str(e)}"}
        )
    except SQLAlchemyError as e:
        logger.error(f"Database error when updating executable plan: {str(e)}")
        raise GeneralDataException(
            "Data base error occured while inserting the executable plan",
            context={"detail": f"Database error when updating executable plan: {str(e)}"}
        )
    except Exception as e:
        logger.error(f"Database error when updating executable plan: {str(e)}")
        raise GeneralDataException(
            "Unexpected error occured updating the executable plan",
            context={"detail" : f"Database error when updating executable plan: {str(e)}"}
        )

async def get_progress_by_user_entity(db: AsyncSession, user_id:UUID, entity_id: UUID = None):
    try:

        # Step 2: Find all plans for the user
        stmt = select(UserPlan)
        stmt = stmt.filter(UserPlan.user_id == user_id)
        if entity_id:
            stmt = stmt.filter(UserPlan.plan_id == entity_id)
        result = await db.execute(stmt)
        user_plans = result.scalars().all()
        if not user_plans:
            return []  # No plans, return empty list

        plan_ids = [plan.plan_id for plan in user_plans]
        entity_type_arr = [1,2,1000]
        # Step 3: Find top-level weeks for each plan (entity_type = 2)
        stmt = select(ExecutablePlan)
        stmt = stmt.filter(ExecutablePlan.plan_id.in_(plan_ids))
        stmt = stmt.filter(ExecutablePlan.entity_type.in_(entity_type_arr))
        stmt = stmt.order_by(ExecutablePlan.sequence_id)
        logger.info(f"The sql statement is {stmt}")
        result = await db.execute(stmt)
        objectives = result.scalars().all()

        # Step 4: Collect entity_ids of weeks and plan_ids
        entity_ids = list(dict.fromkeys(week.entity_id for week in objectives))

        # Step 5: Now get progress_tracking for:
        # - Each weekly entity_id
        # - Each plan_id (even though no node exists for plan, progress_tracking has entity_id = plan_id)

        progress_entity_ids = entity_ids + plan_ids

        if not progress_entity_ids:
            return []

        result = await db.execute(
            select(ProgressTracking)
            .where(ProgressTracking.entity_id.in_(progress_entity_ids))
        )
        tracking_data = result.scalars().all()

        progress_map = {str(track.entity_id): track for track in tracking_data}

        # Step 6: Structure the response
        response = []
        for plan in user_plans:
            plan_progress = progress_map.get(str(plan.plan_id))
            # Find weeks under the plan
            plan_detail = [row for row in objectives if row.plan_id == plan.plan_id]
            week_progress_list = []
            day_progress_list = []
            for row in plan_detail:               
                progress = progress_map.get(str(row.entity_id))
                if row.entity_type == 2:
                    obj = ProgressWeeklyDetail(
                        entity_id=row.entity_id,
                        activity_desc=row.activity_desc,
                        sequence_id=row.sequence_id,
                        progress_percent=progress.cumulative_progress if progress else 0,
                        milestone_100=progress.milestone_100 if progress else 0,
                        milestone_25=progress.milestone_25 if progress else 0,
                        milestone_50=progress.milestone_50 if progress else 0,
                        milestone_75=progress.milestone_75 if progress else 0
                    )
                    week_progress_list.append(obj)
                else:
                    obj = ProgressDailyDetail(entity_id=row.entity_id, 
                                              activity_desc=row.activity_desc,
                                              progress_percent=progress.cumulative_progress if progress else 0,
                                              parent_id=row.parent_id,
                                              sequence_id=row.sequence_id)
                    day_progress_list.append(obj)

            progress_summary_obj = ProgressSummary(
                plan_id= plan.plan_id,
                plan_name= plan.plan_name,
                plan_type=plan.plan_type,
                plan_progress_percent=plan_progress.cumulative_progress if plan_progress else 0,
                plan_milestone_100=plan_progress.milestone_100 if plan_progress else 0,
                plan_milestone_25=plan_progress.milestone_25 if plan_progress else 0,
                plan_milestone_50=plan_progress.milestone_50 if plan_progress else 0,
                plan_milestone_75=plan_progress.milestone_75 if plan_progress else 0,
                week_detail=week_progress_list,
                day_detail=day_progress_list
            )

        return progress_summary_obj

    except IntegrityError as e:
        logger.error(f"IntegrityError when updating executable plan: {str(e)}")
        raise IntegrityException(
            "Integrity error when updating executable plan",
            context = {"detail": f"Issue with updating the executable plan {str(e)}"}
        )
    except SQLAlchemyError as e:
        logger.error(f"Database error when updating executable plan: {str(e)}")
        raise GeneralDataException(
            "Data base error occured while inserting the executable plan",
            context={"detail": f"Database error when updating executable plan: {str(e)}"}
        )
    except Exception as e:
        logger.error(f"Database error when updating executable plan: {str(e)}")
        raise GeneralDataException(
            "Unexpected error occured updating the executable plan",
            context={"detail" : f"Database error when updating executable plan: {str(e)}"}
        )


async def update_progress_tracking(
    db: AsyncSession, 
    entity_id: UUID, 
    plan_id: UUID,
    new_percent: int, 
    notes: Optional[str] = None
):
    """
    Update or create a ProgressTracking record for a given entity (daily, weekly, plan).
    If notes are provided, append them to existing notes.
    """
    try:
        stmt = select(ProgressTracking).where(ProgressTracking.entity_id == entity_id)
        result = await db.execute(stmt)
        tracking = result.scalars().first()

        '''
        if new_percent == 100:
            task_status = TaskStatus.COMPLETE
        elif new_percent > 0:
            task_status = TaskStatus.IN_PROGRESS
            plan_status = PlanStatus.IN_PROGRESS
        else:
            task_status = TaskStatus.NOT_STARTED
        value_params = {}
        value_params["plan_id"] = plan_id
        value_params["plan_status"] = plan_status.value
        if task_status.value == TaskStatus.COMPLETE:
            plan_res = await check_plan_completion(plan_id)
            if plan_res:
                if plan_res[0].total_tasks == plan_res[0].total_completed_tasks:
                    ret = await update_plan(plan_id,value_params, db)
        else:
            task_status = PlanStatus.IN_PROGRESS
            value_params["plan_status"] = task_status.value
            ret = await update_plan(plan_id,value_params, db) 
        '''

        if not tracking:
            # No tracking yet — create new
            tracking = ProgressTracking(
                entity_id=entity_id,
                plan_id = plan_id,
                cumulative_progress=new_percent,
                notes=notes if notes else "",
                milestone_25=1 if new_percent >= 25 else 0,
                milestone_50=1 if new_percent >= 50 else 0,
                milestone_75=1 if new_percent >= 75 else 0,
                milestone_100=1 if new_percent == 100 else 0
            )
            db.add(tracking)
        else:
            # Update existing
            new_cumulative_progress = new_percent
            tracking.cumulative_progress = new_cumulative_progress
            tracking.milestone_25 = 1 if new_cumulative_progress >= 25 else 0
            tracking.milestone_50 = 1 if new_cumulative_progress >= 50 else 0
            tracking.milestone_75 = 1 if new_cumulative_progress >= 75 else 0
            tracking.milestone_100 = 1 if new_cumulative_progress == 100 else 0

            if notes:
                if tracking.notes:
                    tracking.notes = tracking.notes.strip() + "\n" + notes.strip()
                else:
                    tracking.notes = notes.strip()
        '''
        filter_params = {}
        value_params = {}
        filter_params["plan_id"] = plan_id
        filter_params["entity_id"] = entity_id
        value_params["status_id"] = task_status.value
        if new_percent == 100:
            value_params["objective_completion_dt"] = datetime.now(timezone.utc)
        ret_objective_status = await update_executable_plan(filter_params, value_params, db)
        '''
        await db.flush()
    except IntegrityError as e:
        logger.error(f"IntegrityError when updating progress tracking : {str(e)}")
        raise IntegrityException(
            "Integrity error when updating executable plan",
            context = {"detail": f"Issue with updating the executable plan {str(e)}"}
        )
    except SQLAlchemyError as e:
        logger.error(f"Database error when updating executable plan: {str(e)}")
        raise GeneralDataException(
            "Data base error occured while inserting the executable plan",
            context={"detail": f"Database error when updating executable plan: {str(e)}"}
        )
    except Exception as e:
        logger.error(f"Database error when updating executable plan: {str(e)}")
        raise GeneralDataException(
            "Unexpected error occured updating the executable plan",
            context={"detail" : f"Database error when updating executable plan: {str(e)}"}
        )

async def rollup_progress(session: AsyncSession, plan_id: UUID, updated_daily_entity_id: UUID, user_id: UUID):
    try:
        # 0. Get the plan information
        result = await session.execute(select(UserPlan).where(UserPlan.plan_id == plan_id))
        user_plan = result.scalars().first()
        if not user_plan:
            return []  # No plans, return empty list
        # 1. Find the parent weekly entity for the daily task
        if user_plan.plan_type != 'Daily': 
            result = await session.execute(
                text("""
                    SELECT parent_id
                    FROM executable_plan
                    WHERE entity_id = :entity_id 
                """),
                {"entity_id": str(updated_daily_entity_id)}
            )
            parent_id = result.scalar()
            if not parent_id:
                raise ValueError(f"No parent objective found for entity_id {updated_daily_entity_id}")

            # 2. Recalculate Weekly Progress by averaging its daily children's progress
            result = await session.execute(
                text("""
                    SELECT 
                        COALESCE(SUM(p.cumulative_progress), 0) AS total_progress,
                        COUNT(e.entity_id) AS total_tasks
                    FROM executable_plan e
                    LEFT JOIN progress_tracking p ON e.entity_id = p.entity_id
                    WHERE e.parent_id = :weekly_id AND ( e.entity_type = 3 or e.entity_type = 1001)
                """),
                {"weekly_id": str(parent_id)}
            )
            row = result.fetchone()
            total_progress, total_tasks = row
            weekly_cumulative = (total_progress / total_tasks) if total_tasks > 0 else 0

            # 3. Update the weekly tracking progress
            await session.execute(
                text("""
                    INSERT INTO progress_tracking (plan_id, entity_id, cumulative_progress, updated_at)
                    VALUES (:plan_id, :entity_id, :progress, now())
                    ON CONFLICT (entity_id) DO UPDATE 
                    SET cumulative_progress = :progress, updated_at = now()
                """),
                {"plan_id": str(plan_id), "entity_id": str(parent_id), "progress": weekly_cumulative}
            )
        # 4. Recalculate plan progress based on the plan type
        if user_plan.plan_type == "Weekly":
            result = await session.execute(
                text("""
                    SELECT 
                        COALESCE(SUM(p.cumulative_progress), 0) AS total_progress,
                        COUNT(e.entity_id) AS total_weeks
                    FROM executable_plan e
                    LEFT JOIN progress_tracking p ON e.entity_id = p.entity_id
                    WHERE e.plan_id = :plan_id AND e.entity_type = 2
                """),
                {"plan_id": str(plan_id)}
            )
        elif user_plan.plan_type == "Daily":
            result = await session.execute(
                text("""
                    SELECT 
                        COALESCE(SUM(p.cumulative_progress), 0) AS total_progress,
                        COUNT(e.entity_id) AS total_weeks
                    FROM executable_plan e
                    LEFT JOIN progress_tracking p ON e.entity_id = p.entity_id
                    WHERE e.plan_id = :plan_id AND e.entity_type = 3
                """),
                {"plan_id": str(plan_id)}
            )
        else: # This is a milestone levely plan
                result = await session.execute(
                text("""
                    SELECT 
                        COALESCE(SUM(p.cumulative_progress), 0) AS total_progress,
                        COUNT(e.entity_id) AS total_weeks
                    FROM executable_plan e
                    LEFT JOIN progress_tracking p ON e.entity_id = p.entity_id
                    WHERE e.plan_id = :plan_id AND e.entity_type = 1000
                """),
                {"plan_id": str(plan_id)}
            )
        row = result.fetchone()
        total_progress, total_weeks = row
        plan_progress = (total_progress / total_weeks) if total_weeks > 0 else 0

        # 5 Update the plan tracking progress
        await session.execute(
            text("""
                INSERT INTO progress_tracking (plan_id, entity_id, cumulative_progress, updated_at)
                VALUES (:plan_id, :entity_id, :progress, now())
                ON CONFLICT (entity_id) DO UPDATE 
                SET cumulative_progress = :progress, updated_at = now()
            """),
            {"plan_id": str(plan_id), "entity_id": str(plan_id), "progress": plan_progress}
        )
        
        return plan_progress

    except IntegrityError as e:
        logger.error(f"IntegrityError when updating executable plan: {str(e)}")
        raise IntegrityException(
            "Integrity error when updating executable plan",
            context = {"detail": f"Issue with updating the executable plan {str(e)}"}
        )
    except SQLAlchemyError as e:
        logger.error(f"Database error when updating executable plan: {str(e)}")
        raise GeneralDataException(
            "Data base error occured while inserting the executable plan",
            context={"detail": f"Database error when updating executable plan: {str(e)}"}
        )
    except Exception as e:
        logger.error(f"Database error when updating executable plan: {str(e)}")
        raise GeneralDataException(
            "Unexpected error occured updating the executable plan",
            context={"detail" : f"Database error when updating executable plan: {str(e)}"}
        )

async def get_progress_tracking_by_plan(db: AsyncSession, plan_id: UUID, user_id: UUID)-> Optional[dict]:
    try:
        stmt = select(ProgressTracking).where(
            ProgressTracking.plan_id == plan_id
        )
        result = await db.execute(stmt)
        progress_map = {f"str(entity_row.entity_id)-str(entity_row.plan_id)": entity_row for entity_row in result}
        return progress_map
    
    except IntegrityError as e:
        logger.error(f"IntegrityError when updating executable plan: {str(e)}")
        raise IntegrityException(
            "Integrity error when updating executable plan",
            context = {"detail": f"Issue with updating the executable plan {str(e)}"}
        )
    except SQLAlchemyError as e:
        logger.error(f"Database error when updating executable plan: {str(e)}")
        raise GeneralDataException(
            "Data base error occured while inserting the executable plan",
            context={"detail": f"Database error when updating executable plan: {str(e)}"}
        )
    except Exception as e:
        logger.error(f"Database error when updating executable plan: {str(e)}")
        raise GeneralDataException(
            "Unexpected error occured updating the executable plan",
            context={"detail" : f"Database error when updating executable plan: {str(e)}"}
        )



async def get_dashboard_summary_sql(db: AsyncSession, user_id: UUID, plan_id: Optional[UUID] = None) -> Optional[dict]:
    try:
        # Base query string
        query = """
            WITH user_plans AS (
                SELECT plan_id, plan_type, approved_by_user, plan_start_date, plan_end_date, plan_goal, plan_status, user_id
                FROM user_plan
                WHERE user_id = :user_id
                """ + (" AND plan_id = :plan_id" if plan_id else "") + """
            ),
        progress_per_plan AS (
            SELECT 
                pt.entity_id AS plan_id,
                MAX(pt.cumulative_progress) AS plan_progress
            FROM progress_tracking pt
            INNER JOIN user_plans up ON up.plan_id = pt.entity_id
            GROUP BY pt.entity_id
        ),
        task_changes_per_plan AS (
            SELECT 
                pdc.plan_id,
                COUNT(DISTINCT pdc.id) AS task_change_count
            FROM plan_detail_change_log pdc
            INNER JOIN user_plans up ON up.plan_id = pdc.plan_id
            GROUP BY pdc.plan_id
        ),
        plan_changes_per_plan AS (
            SELECT 
                pc.plan_id,
                COUNT(DISTINCT pc.id) AS plan_change_count
            FROM plan_change_log pc
            INNER JOIN user_plans up ON up.plan_id = pc.plan_id
            GROUP BY pc.plan_id
        )
        SELECT
            COALESCE(pp.plan_progress, NULL) AS plan_progress,  
            COALESCE(tc.task_change_count, 0) AS task_change_count,
            COALESCE(pc.plan_change_count, 0) AS plan_change_count,
            
            COUNT(DISTINCT up.plan_id) AS total_plans,
            COUNT(DISTINCT CASE WHEN up.plan_status = 1 THEN up.plan_id END) 
                 AS total_active_plans,
            up.plan_id,
            up.plan_type,
            up.approved_by_user,
            up.plan_start_date,
            up.plan_end_date,
            up.plan_goal
        FROM user_plans up
        LEFT JOIN progress_per_plan pp 
            ON pp.plan_id = up.plan_id
        LEFT JOIN task_changes_per_plan tc
            ON tc.plan_id = up.plan_id
        LEFT JOIN plan_changes_per_plan pc
            ON pc.plan_id = up.plan_id
        GROUP BY 
            up.plan_id,
            up.plan_type,
            up.approved_by_user,
            up.plan_start_date,
            up.plan_end_date,
            up.plan_goal,
            pp.plan_progress,
            tc.task_change_count,
            pc.plan_change_count
        """


        # Add optional plan_id filter

        params = {"user_id": str(user_id)}

        if plan_id:
            params["plan_id"] = str(plan_id)
        
        '''
        query = """
            SELECT 
                MAX(CASE 
                    WHEN pt_plan.entity_id = up.plan_id THEN pt_plan.cumulative_progress 
                    ELSE 0 
                END) AS plan_progress,
                COUNT(DISTINCT pdc.id) AS task_change_count,
                COUNT(DISTINCT pc.id) AS plan_change_count,
                coalesce(count(distinct up.plan_id),0) as total_plans,
                coalesce(count(distinct case when up.plan_status = 1 then up.plan_id else null end),0) as total_active_plans,
                up.plan_id,
                up.plan_type,
                up.approved_by_user,
                up.plan_start_date,
                up.plan_end_date,
                up.plan_goal
            FROM 
                user_plan up
            LEFT JOIN progress_tracking pt_plan ON pt_plan.entity_id = up.plan_id
            LEFT JOIN plan_detail_change_log pdc ON pdc.plan_id = up.plan_id
            LEFT JOIN plan_change_log pc ON pc.plan_id = up.plan_id
            WHERE 
                up.user_id = :user_id
        """

        # Parameters dictionary
        params = {"user_id": str(user_id)}

        # Add conditionally if plan_id is provided
        if plan_id:
            query += " AND up.plan_id = :plan_id"
            params["plan_id"] = str(plan_id)

        # Add GROUP BY clause
        query += """
            GROUP BY 
                up.plan_id,
                up.plan_type,
                up.approved_by_user,
                up.plan_start_date,
                up.plan_end_date,
                up.plan_goal
        """
        '''

        # Execute the query
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


async def calculate_task_delay(user_id: UUID, db: AsyncSession):

    try:
        params ={"user_id": str(user_id)}
        sql = """
                SELECT 
                    coalesce(sum(distinct case when  
                        ep.start_date < current_timestamp then current_date - ep.start_date::date else null end),0) as objectives_delayed_time ,
                    coalesce(count(ep.entity_id),0) as total_objectives,
                    coalesce(count(case when ep.start_date::date = current_date then ep.entity_id else null end),0) as total_current_tasks,
                    coalesce(count(case when  status_id = 100 then ep.entity_id else null end),0) as total_completed_tasks,
                    coalesce(count(case when  status_id = 100 and objective_completion_dt::date = current_date::date then ep.entity_id else null end),0) as total_completed_tasks_today,
                    coalesce(count(case when status_id = 99 then ep.entity_id else null end),0) as total_in_progress_tasks,
                    coalesce(count(case when status_id = 0 then ep.entity_id else null end),0) as total_not_started_tasks,
                    coalesce(count(case when start_date::date < current_date and status_id not in (99,100) then ep.entity_id else null end), 0) as total_delayed_tasks,
                    up.plan_id,
                    up.plan_start_date
                FROM 
                    user_plan up
                JOIN executable_plan ep ON ep.plan_id = up.plan_id
                WHERE 
                    up.user_id = :user_id and 
                    approved_by_user != 0 and 
                    entity_type not in ( 2, 1000, 999) and 
                    ep.status_id = 0 
                            GROUP BY 
                    up.plan_id,
                    up.plan_start_date

            """
        result = await db.execute(text(sql), params)
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


async def check_plan_completion(plan_id: UUID, db: AsyncSession):

    try:
        filter_params = {}
        filter_params["plan_id"] = plan_id
        params = {"plan_id": str(plan_id)}
        sql = """
            select
                count(ep.entity_id ) as total_tasks,
                count(case when  status_id = 100 then ep.entity_id else null end) as total_completed_tasks,
                count(case when status_id = 99 then ep.entity_id else null end) as total_in_progress_tasks,
                count(case when status_id = 0 then ep.entity_id else null end) as total_not_started_tasks,
                count(case when start_date::date < current_date and status_id not in (99,100) then ep.entity_id else null end) as total_delayed_tasks
            from 
                executable_plan ep
            where
                plan_id = :plan_id and
                ep.entity_type not in (2, 1000, 999)
            """
        result = await db.execute(text(sql), params)
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