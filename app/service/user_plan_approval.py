from fastapi import HTTPException, status, Request
from app.model.user_plan import UXPlanApprovalPL, IExecutionPlanDetail, UXApprovedPlanDetail, UXUpdateApprovedPlan, UXUserPlanIdentifier, UXUpcomingActivitiesRequest, UXUpcomingActivitiesResponse, UXUpcomingActivitiesResponseRS, UXUserPlanIdentifierRS, IUXCreatedPlan, UXUserPlanUpdate
from app.model.user_prompt_response import WeeklyPlanIdentifier, ActivityByDayIdentifier, ActivityDetail, ActivityDetailIdentifier, PlanDetailForUserManagement
from app.model.common import RoutineSummary, GeneralRecommendationAndGuidelines
from app.model.plan_manager import FmpSubscriberGet
from app.data.user import User
from app.data.user_plan_detail import get_plan_weekly_detail, get_plan_day_detail, get_plan_activity_detail
from app.data.user_plan import (insert_approved_plan, 
                                get_executable_plan, 
                                update_plan, 
                                update_executable_plan, 
                                get_plan, 
                                get_general_guidelines, 
                                get_plan_routine_summary, 
                                get_upcoming_activities_db, 
                                get_created_plan,
                                insert_into_plan_detail_change_log,
                                insert_into_plan_change_log,
                                get_task_change_history,
                                get_goal_builder)
from app.common.date_functions import convert_to_user_timezone, convert_user_time_to_utc, format_date_time
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from enum import Enum
import structlog
import pytz
from app.common.date_functions import convert_to_user_timezone, convert_user_time_to_utc, format_date_time
from app.common.exception import DatabaseConnectionException, IntegrityException, TimeZoneException, GeneralDataException, UserNotFound, PlanAlreadyApproved
from app.common.site_enums import Level, EntityType, PlanStatus
from app.common.utility_functions import extract_number
from app.service.rewards import RewardsService
from uuid import UUID
from typing import Optional
logger = structlog.get_logger()

async def build_approved_plan(obj_plan: UXPlanApprovalPL,  db: AsyncSession,current_user: User, request_metadata: Request, rewards_service: RewardsService):
#async def build_approved_plan(obj_plan: UXPlanApprovalPL,  db: AsyncSession,current_user: User, request_metadata: Request):
    try:
        if obj_plan.plan_start_date is None:
            raise GeneralDataException(
                message="Plan Start Date is missing",
                context={"detail": "Required plan start date is missing"}
            ) 
        current_utc = datetime.now(timezone.utc)
        format_user_time = format_date_time(str(obj_plan.plan_start_date))
        user_time_in_otc = convert_user_time_to_utc(format_user_time, "America/Los_Angeles")

        if user_time_in_otc < current_utc:
            logger.error("The plan cannot start in the past")
            raise GeneralDataException(
            message= "Plan cannot be approved with the given date",
            context= {"detail": f" Plan cannot be updated with past date {obj_plan.plan_start_date}"}
            )
        filter_params = {}
        filter_params["plan_id"] = obj_plan.plan_id
        filter_params["user_id"] = current_user.user_id
        plan_resultset = []
        plan_resultset =  await get_plan(filter_params,db)

        if len(plan_resultset) == 0:
            raise GeneralDataException(
                message= f"Plan is not owned by the user {filter_params['plan_id']}",
                context={"detail": f"Plan is not owned by the user {filter_params['plan_id']}" }
            ) 

        del filter_params["user_id"] 

        obj_created_plan = await get_created_plan(filter_params, db)

        b_approved_plan = await get_executable_plan(filter_params, db)

        if b_approved_plan:
            raise PlanAlreadyApproved(
                reason= "Plan Exists",
                plan_id= {"detail": f"Plan Exists {str(obj_plan.plan_id)}"}
                )

        week_obj_hash = {}
        day_obj_hash = {}
        dt_start_date = None
        if plan_resultset[0].plan_type == "Weekly":
            if len(obj_created_plan) < 1:
                logger.error("The plan is a weekly plan, but no data in the  table {str(plan_resultset.plan_id)}")
                raise GeneralDataException(
                message= "The plan is a weekly plan, but no data in the  table",
                context= {"detail": f"The plan is a weekly plan, but no data in the  table {str(plan_resultset.plan_id)}"}
                )
            day_counter = 0
            for i in range(len(obj_created_plan)):
                logger.info ( f"The value is {obj_created_plan[i].entity_type}")

                if EntityType(obj_created_plan[i].entity_type) == EntityType.WEEK:
                    if i == 0 :
                        dt_start_date = user_time_in_otc
                        #dt_start_date = obj_plan.plan_start_date
                    else:
                        dt_start_date = user_time_in_otc + timedelta(days=7)
                        #dt_start_date = obj_plan.plan_start_date + timedelta(days=7)
                elif EntityType(obj_created_plan[i].entity_type) == EntityType.DAY:
                    #dt_start_date = obj_plan.plan_start_date + timedelta(days=day_counter) 
                    dt_start_date = user_time_in_otc + timedelta(days=day_counter)
                    day_counter += 1
                elif EntityType(obj_created_plan[i].entity_type) == EntityType.ACTIVITY:
                    dt_start_date = dt_start_date
                else:
                    pass
                
                obj_execution_plan = IExecutionPlanDetail(plan_id = obj_created_plan[i].plan_id,
                                        sequence_id= obj_created_plan[i].sequence_id,
                                        level_id=obj_created_plan[i].level_id,
                                        entity_type = obj_created_plan[i].entity_type,
                                        parent_id=obj_created_plan[i].parent_id,
                                        entity_id = obj_created_plan[i].entity_id,
                                        start_date = dt_start_date,
                                        status_id= PlanStatus.TO_BE_STARTED,
                                        reminder_request = None,
                                        progress_measure= 0.0,
                                        activity_desc= obj_created_plan[i].entity_desc,
                                        request_reminder_time= None
                                        )
                obj_execution_plan_db = await insert_approved_plan(obj_execution_plan, db)
        elif plan_resultset[0].plan_type == "Daily":
            for i in range(len(obj_created_plan)):
                logger.info ( f"The value is {obj_created_plan[i].entity_type}")
                if EntityType(obj_created_plan[i].entity_type) == EntityType.DAY:
                    dt_start_date = user_time_in_otc + timedelta(days=i) 
                    #dt_start_date = obj_plan.plan_start_date + timedelta(days=i)
                elif EntityType(obj_created_plan[i].entity_type) == EntityType.ACTIVITY:
                    dt_start_date = dt_start_date
                else:
                    pass
                
                obj_execution_plan = IExecutionPlanDetail(plan_id = obj_created_plan[i].plan_id,
                                        sequence_id= obj_created_plan[i].sequence_id,
                                        level_id=obj_created_plan[i].level_id,
                                        entity_type = obj_created_plan[i].entity_type,
                                        parent_id=obj_created_plan[i].parent_id,
                                        entity_id = obj_created_plan[i].entity_id,
                                        start_date = dt_start_date,
                                        status_id= PlanStatus.TO_BE_STARTED,
                                        reminder_request = None,
                                        progress_measure= 0.0,
                                        activity_desc= obj_created_plan[i].entity_desc,
                                        request_reminder_time= None
                                        )
                obj_execution_plan_db = await insert_approved_plan(obj_execution_plan, db)
        else:
            count_of_milestones = sum(1 for item in obj_created_plan if item.entity_type == EntityType.MILESTONE.value)

            days = await extract_number(plan_resultset[0].goal_duration)
            if days == 0:
                if plan_resultset[0].plan_type == "Monthly" or plan_resultset[0].plan_type == "Yearly":
                    days_to_increment = 30
                else:
                    days_to_increment = 10
            else:
                days_to_increment = int(days/count_of_milestones)
            milestone_counter = 0
            for i in range(len(obj_created_plan)):
                logger.info ( f"The value is {obj_created_plan[i].entity_type}")
                if EntityType(obj_created_plan[i].entity_type) == EntityType.MILESTONE:
                    dt_start_date = user_time_in_otc + timedelta(days=milestone_counter*days_to_increment) 
                    milestone_counter += 1
                    #dt_start_date = obj_plan.plan_start_date + timedelta(days=i*days_to_increment) 
                elif EntityType(obj_created_plan[i].entity_type) == EntityType.ACTIVITY:
                    dt_start_date = dt_start_date
                elif EntityType(obj_created_plan[i].entity_type) == EntityType.TASK:
                    dt_start_date = dt_start_date
                else:
                    pass
                
                obj_execution_plan = IExecutionPlanDetail(plan_id = obj_created_plan[i].plan_id,
                                        sequence_id= obj_created_plan[i].sequence_id,
                                        level_id=obj_created_plan[i].level_id,
                                        entity_type = obj_created_plan[i].entity_type,
                                        parent_id=obj_created_plan[i].parent_id,
                                        entity_id = obj_created_plan[i].entity_id,
                                        start_date = dt_start_date,
                                        status_id= PlanStatus.TO_BE_STARTED,
                                        reminder_request = None,
                                        progress_measure= 0.0,
                                        activity_desc= obj_created_plan[i].entity_desc,
                                        request_reminder_time= None
                                        )
                obj_execution_plan_db = await insert_approved_plan(obj_execution_plan, db)

        value_params = {}
        value_params["plan_start_date"] = user_time_in_otc
        value_params["plan_end_date"] = dt_start_date
        value_params["approved_by_user"] =  PlanStatus.APPROVED_BY_USER.value
        value_params["plan_status"] = PlanStatus.IN_PROGRESS.value
        obj_update_plan = await update_plan(obj_plan.plan_id,value_params=value_params, db=db )
        
        #reward_response = await rewards_service.process_plan_creation_rewards(
        #current_user.user_id, obj_plan.plan_id
        #    )
        
        obj_approved_plan = await get_executable_plan(filter_params=filter_params, db=db)
        obj_approved_plan_for_ux = []
        
        for i in range(len(obj_approved_plan)):
            '''
            x = IExecutionPlanDetail(
                plan_id = obj_approved_plan[i].plan_id,
                sequence_id= obj_approved_plan[i].sequence_id,
                level_id = obj_approved_plan[i].level_id,
                entity_id= obj_approved_plan[i].entity_id,
                entity_type= obj_approved_plan[i].entity_type,
                parent_id= obj_approved_plan[i].parent_id,
                start_date=obj_approved_plan[i].start_date,
                status_id=obj_approved_plan[i].status_id,
                reminder_request=obj_approved_plan[i].reminder_request,
                progress_measure=obj_approved_plan[i].progress_measure,
                activity_desc=obj_approved_plan[i].activity_desc,
                request_reminder_time= obj_approved_plan[i].request_reminder_time
            )
            
            obj_approved_plan_for_ux.append(x)   
            '''
            obj_approved_plan[i].start_date = convert_to_user_timezone(obj_approved_plan[i].start_date, request_metadata["timezone"])
            obj_approved_plan_for_ux.append(IExecutionPlanDetail.model_validate(obj_approved_plan[i])) 

        

        
        obj_routine_summary = await get_plan_routine_summary(filter_params=filter_params, db=db)
        obj_x = []
        if obj_routine_summary is not None and len(obj_routine_summary) > 0:
            for i in range(len(obj_routine_summary )):
                obj_x.append(obj_routine_summary[i].routine)
        obj_routine = RoutineSummary(summary_item=obj_x)
        obj_x = []
        obj_general_guidelines = await get_general_guidelines(filter_params=filter_params,db=db)
        if obj_general_guidelines is not None and len(obj_general_guidelines) > 0 :
            for i in range(len(obj_general_guidelines)):
                obj_x.append(obj_general_guidelines[i].guideline)
        obj_gg = GeneralRecommendationAndGuidelines(general_descripton=obj_x)

        return UXApprovedPlanDetail(plan_detail=obj_approved_plan_for_ux,
                                    routine_summary=obj_routine,
                                    general_guidelines=obj_gg)
    except PlanAlreadyApproved:
        raise 
    except IntegrityException as e:

        logger.error(f"IntegrityError when inserting user plan: {str(e)}")
        raise IntegrityException(
            "Integrity error when inserting a user plan",
            context = {"detail": "This plan conflicts with an existing plan. Possible duplicate entry or foreign key constraint failure."}
        )
    except GeneralDataException as e:

        logger.error(f"Database error when inserting user plan: {str(e)}")
        raise GeneralDataException(
            "Data base error occured while inserting the executed plan",
            context={"detail": "Database error occurred while creating the user plan"}
        )
    except TimeZoneException as e:
        logger.error(f"Time manipulation error when inserting executed plan: {str(e)}")
        raise GeneralDataException(
            f"Time manipulation error when inserting executed plan: {str(e)}",
            context={"detail": f"Time manipulation error when inserting executed plan: {str(e)}"}
        )
    except Exception as e:
        logger.error(f"Unexpected error in executing the approved plan: {str(e)}")
        raise GeneralDataException(
            "Unexpected error occured formatting date",
            context={"detail" : "An unexpected error occurred while formatting the date"}
        )
        
async def update_approved_plan_dates(obj_plan: UXUpdateApprovedPlan, db: AsyncSession, current_user: User, request_metadata: Request):
    """
    - Check if the task to be moved is in the past and allow only if the plan hasn't started or no activity has been completed
    - Check if the task that need to be moved is already done
    """
    try:

        filter_params = {}
        current_utc = datetime.now(timezone.utc)
        filter_params["plan_id"] = obj_plan.plan_id
        #filter_params["user_id"] = current_user.user_id
        plan_start_date = plan_start_date = None
        ret = await get_plan(filter_params, db)
        if len(ret) <= 0:
            raise GeneralDataException(f"THere is no plan with id: {filter_params['plan_id']}",
                                    context= "Plan id is missing in the context of updating the plan")
        format_user_time = format_date_time(str(ret[0].plan_start_date))
        user_time_in_otc = convert_user_time_to_utc(format_user_time, request_metadata["timezone"] )
        

        if (user_time_in_otc + timedelta(days=obj_plan.days_to_move) ) < current_utc:
            logger.error("The plan cannot update a task in the past")
            raise GeneralDataException(
            message= "Past activity cannot be updated",
            context= {"detail": f" Activity in the past cannot be updated {obj_plan.entity_id}"}
            )
        filter_params["change_reason"] = obj_plan.change_reason
        if obj_plan.sequence_id is not None:  
            if obj_plan.sequence_id == 0: # This means it is a plan level update
                new_plan_start_date = ret[0].plan_start_date + timedelta(days=obj_plan.days_to_move)
                plan_end_date = None
                if ret[0].plan_end_date is not None:
                    plan_end_date = ret[0].plan_end_date + timedelta(days=obj_plan.days_to_move)
                else:
                    plan_end_date = new_plan_start_date + timedelta(days=90) # This should not happen. If this condition is met, we should revisit the logic
                res = await insert_into_plan_change_log(db, 
                                                        filter_params["plan_id"],
                                                        ret[0].plan_start_date, 
                                                        new_plan_start_date,
                                                        obj_plan.change_reason
                                                        )
                value_params = {}
                value_params["plan_start_date"] = new_plan_start_date
                value_params["plan_end_date"] = plan_end_date
                update_user_plan = await update_plan(obj_plan.plan_id,value_params, db)

            obj_executable_plan_detail = await get_executable_plan(filter_params=filter_params, db=db)
            for i in range(len(obj_executable_plan_detail)):
                #print(type(obj_plan.sequence_id), type(obj_executable_plan_detail[i].sequence_id))
                #print(type(obj_plan.entity_id), type(obj_executable_plan_detail[i].entity_id))
                print(f"{obj_plan.sequence_id} -- {obj_plan.entity_id} db: {obj_executable_plan_detail[i].sequence_id} -- {obj_executable_plan_detail[i].entity_id}")
                if obj_plan.sequence_id != 0 and obj_plan.sequence_id > obj_executable_plan_detail[i].sequence_id:
                    continue
                if (obj_plan.sequence_id == obj_executable_plan_detail[i].sequence_id) and (obj_plan.entity_id == str(obj_executable_plan_detail[i].entity_id)):
                    filter_params["change_reason"] = obj_plan.change_reason
                else:
                    filter_params["change_reason"] = "system"
                new_date = obj_executable_plan_detail[i].start_date + timedelta(days=obj_plan.days_to_move)
                if obj_plan.sequence_id == 10000 and i == 0:
                    plan_start_date = new_date
                if i == len(obj_executable_plan_detail) -1:
                        plan_end_date = new_date
                if (obj_plan.sequence_id == obj_executable_plan_detail[i].sequence_id) and (obj_plan.entity_id == str(obj_executable_plan_detail[i].entity_id)):
                    ret = await insert_into_plan_detail_change_log(db,
                                                    obj_plan.plan_id,
                                                    obj_executable_plan_detail[i].entity_id,
                                                    obj_executable_plan_detail[i].start_date,
                                                    new_date,
                                                    filter_params["change_reason"]
                                                    )
                update_filter = {}
                value_params = {}
                update_filter["plan_id"] = str(obj_executable_plan_detail[i].plan_id)
                update_filter["entity_id"] = str(obj_executable_plan_detail[i].entity_id)
                value_params["start_date"] = new_date
                obj_task_update = await update_executable_plan(update_filter,value_params, db)
            if obj_plan.sequence_id == 10000:
                value_params["plan_start_date"] = plan_start_date
                value_params["plan_end_date"] = plan_end_date
                update_user_plan = await update_plan(obj_plan.plan_id,value_params, db)
            else:
                value_params["plan_end_date"] = plan_end_date
                update_user_plan = await update_plan(obj_plan.plan_id,value_params, db)
        return 1;
    except SQLAlchemyError as e:
        logger.error(f"Database error when updating the approved user plan: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred while creating user plan"
        )
    except IntegrityException as e:

        logger.error(f"IntegrityError when updating the executable plan: {str(e)}")
        raise IntegrityException(
            "Integrity error when updating the executable plan",
            context = {"detail": "Error when updating the executable plan."}
        )
    except GeneralDataException as e:

        logger.error(f"Database error when updating the executable plan: {str(e)}")
        raise GeneralDataException(
            "Data base error when updating the executable plan",
            context={"detail": "Database error when updating the executable plan"}
        )
    except TimeZoneException as e:
        logger.error(f"Some error with Date Manipulation while updating the executable plan: {str(e)}")
        raise GeneralDataException(
            "Some error with Date Manipulation while updating the executable plan",
            context={"detail": f"Some error with Date Manipulation while updating the executable plan {str(e)}"}
        )
    except Exception as e:
        logger.error(f"Some general error when updating the executable plan: {str(e)}")
        raise GeneralDataException(
            message="Database error when updating the executable plan",
            context={"detail": "Database error when updating the executable plan"})


async def set_reminder_svc(obj_plan: UXUpdateApprovedPlan, db: AsyncSession, current_user: User, request_metadata: Request):
    """
    - Check if the task to be moved is in the past and allow only if the plan hasn't started or no activity has been completed
    - Check if the task that need to be moved is already done
    """
    try:

        update_filter = {}
        value_params = {}
        update_filter["plan_id"] = obj_plan.plan_id
        update_filter["entity_id"] = obj_plan.entity_id
        update_filter["sequence_id"] = obj_plan.sequence_id
        value_params["reminder_request"] = obj_plan.reminder_request
        value_params["request_reminder_time"] = obj_plan.request_reminder_time
        obj_task_update = await update_executable_plan(update_filter,value_params, db)
        return 1
    
    except SQLAlchemyError as e:
        logger.error(f"Database error when setting the reminder: {str(e)}")
        raise HTTPException(
            f"Database error when setting the reminder: {str(e)}",
            detail="Database error occurred when setting the reminder:"
        )
    except IntegrityException as e:

        logger.error(f"IntegrityError  when setting the reminder:: {str(e)}")
        raise IntegrityException(
            f"Integrity error when setting the reminder: {str(e)}",
            context = {"detail": "Error when setting the reminder:."}
        )
    except GeneralDataException as e:

        logger.error(f"Database error when setting the reminder: {str(e)}")
        raise GeneralDataException(
            f"Data base error when setting the reminder: {str(e)}",
            context={"detail": f"Data base error when setting the reminder: {str(e)}"}
        )
    except TimeZoneException as e:
        logger.error(f"Some error with Date Manipulation when setting the reminder: {str(e)}")
        raise GeneralDataException(
            "Some error with Date Manipulation when setting the reminder",
            context={"detail": f"Some error with Date Manipulation {str(e)}"}
        )
    except Exception as e:
        logger.error(f"Some general error when updating the executable plan: {str(e)}")
        raise GeneralDataException(
            message=f"Some error with Date Manipulation when setting the reminder: {str(e)}",
            context={"detail": f"Some error with Date Manipulation when setting the reminder: {str(e)}"})



async def update_objective_status_svc(obj_plan: UXUpdateApprovedPlan, db: AsyncSession, current_user: User, request_metadata: Request):
    """
    - Check if the task to be moved is in the past and allow only if the plan hasn't started or no activity has been completed
    - Check if the task that need to be moved is already done
    """
    try:

        update_filter = {}
        value_params = {}
        update_filter["plan_id"] = obj_plan.plan_id
        update_filter["entity_id"] = obj_plan.entity_id
        update_filter["sequence_id"] = obj_plan.sequence_id
        value_params["status_id"] = obj_plan.reminder_request
        obj_task_update = await update_executable_plan(update_filter,value_params, db)
        return 1
    
    except SQLAlchemyError as e:
        logger.error(f"Database error when updating the objective status: {str(e)}")
        raise HTTPException(
            f"Database error when updating the objective status: {str(e)}",
            detail=f"Database error when updating the objective status: {str(e)}"
        )
    except IntegrityException as e:

        logger.error(f"IntegrityError when updating the objective status: {str(e)}")
        raise IntegrityException(
            f"IntegrityError when updating the objective status: {str(e)}",
            context = {"detail": f"IntegrityError when updating the objective status: {str(e)}"}
        )
    except GeneralDataException as e:

        logger.error(f"Database error when updating the objective status: {str(e)}")
        raise GeneralDataException(
            f"Database error when updating the objective status: {str(e)}",
            context={"detail": f"Database error when updating the objective status: {str(e)}"}
        )
    except TimeZoneException as e:
        logger.error(f"Some error with Date Manipulation when updating the objective status: {str(e)}")
        raise GeneralDataException(
            f"Some error with Date Manipulation when updating the objective status: {str(e)}",
            context={"detail": f"Some error with Date Manipulation when updating the objective status: {str(e)}"}
        )
    except Exception as e:
        logger.error(f"Some general error when updating the objective status: {str(e)}")
        raise GeneralDataException(
            message=f"Some general error when updating the objective status: {str(e)}",
            context={"detail": f"Some general error when updating the objective status: {str(e)}"})



async def redo_plan():
    """
    - Ensure the plan to be copied is successful
    - Ensure the plan is from the same user (Note: This could be a great feature)

    """

async def get_all_plans(db: AsyncSession, current_user: User, request_metadata: Request):
    """
    - get all plans by user

    """
    try:

        filter_params = {}
        filter_params["user_id"] = current_user.user_id
        obj_user_plan_db = await get_plan(filter_params=filter_params, db=db)
        obj_x = []
        if not obj_user_plan_db:
            return UXUserPlanIdentifierRS(content=[])
        user_start_dt = None
        user_end_dt = None  
        for i in range(len(obj_user_plan_db)) :
            if obj_user_plan_db[i].plan_start_date is not None:
                logger.info(f"The start date is {obj_user_plan_db[i].plan_start_date}")
                user_start_dt = format_date_time(str(obj_user_plan_db[i].plan_start_date))
                dt = convert_user_time_to_utc(user_start_dt, request_metadata["timezone"] )
                user_start_dt = convert_to_user_timezone(dt, request_metadata["timezone"]).strftime("%Y-%m-%d %H:%M:%S")
            if obj_user_plan_db[i].plan_end_date is not None:
                logger.info(f"The start date is {obj_user_plan_db[i].plan_end_date}")
                user_end_dt = format_date_time(str(obj_user_plan_db[i].plan_end_date))
                dt = convert_user_time_to_utc(user_end_dt, request_metadata["timezone"] )
                user_end_dt = convert_to_user_timezone(dt, request_metadata["timezone"]).strftime("%Y-%m-%d %H:%M:%S")

            obj_user_plan_ux = UXUserPlanIdentifier(user_id = str(obj_user_plan_db[i].user_id),
                                                plan_id = str(obj_user_plan_db[i].plan_id),
                                                plan_name = obj_user_plan_db[i].plan_name,
                                                plan_type = obj_user_plan_db[i].plan_type,
                                                plan_goal = obj_user_plan_db[i].plan_goal,
                                                plan_end_date= user_end_dt,
                                                plan_start_date= user_start_dt,
                                                plan_status= obj_user_plan_db[i].plan_status,
                                                approved_by_user= obj_user_plan_db[i].approved_by_user,
                                                follow_flag=obj_user_plan_db[i].follow_flag,
                                                private_flag=obj_user_plan_db[i].private_flag)
            
            obj_x.append(obj_user_plan_ux)

        rs = UXUserPlanIdentifierRS(content=obj_x)
        return rs
    except IntegrityException as e:
        await db.rollback()
        logger.error(f"IntegrityError when retrieving all plans: {str(e)}")
        raise IntegrityException(
            f"IntegrityError when retrieving all plans: {str(e)}",
            context = {"detail": f"IntegrityError when retrieving all plans: {str(e)}"}
        )
    except GeneralDataException as e:
        await db.rollback()
        logger.error(f"Database error when retrieving all plans: {str(e)}")
        raise GeneralDataException(
            f"Database error when retrieving all plans: {str(e)}",
            context={"detail": f"Database error when retrieving all plans: {str(e)}"}
        )
    except Exception as e:
        logger.error(f"Some general error occured when retrieving all plans: {str(e)}")
        raise GeneralDataException(
            f"Some general error occured when retrieving all plans: {str(e)}",
            context = {"detail": f"Some general error occured when retrieving all plans: {str(e)}"})


'''
async def get_plan_impersonate(db: AsyncSession, fmp: FmpSubscriberGet, current_user: User, request_metadata: Request):
    """
    - get all plans by user

    """
    try:

        filter_params = {}
        if fmp.plan_id is None:
            raise GeneralDataException(
            f"Plan id is null: {str(e)}",
            context={"detail": f"Plan id is null: {str(e)}"}
        )
        filter_params["plan_id"] = fmp.plan_id
        obj_user_plan_db = await get_plan(filter_params=filter_params, db=db)
        obj_x = []
        if not obj_user_plan_db:
            raise GeneralDataException(
            f"Plan with this id does not exist: {str(e)}",
            context={"detail": f"Plan with this id does not exist: {str(e)}"}
        )
        user_start_dt = None
        user_end_dt = None  
        for i in range(len(obj_user_plan_db)) :
            if obj_user_plan_db[i].plan_start_date is not None:
                logger.info(f"The start date is {obj_user_plan_db[i].plan_start_date}")
                user_start_dt = format_date_time(str(obj_user_plan_db[i].plan_start_date))
                dt = convert_user_time_to_utc(user_start_dt, request_metadata["timezone"] )
                user_start_dt = convert_to_user_timezone(dt, request_metadata["timezone"]).strftime("%Y-%m-%d %H:%M:%S")
            if obj_user_plan_db[i].plan_end_date is not None:
                logger.info(f"The start date is {obj_user_plan_db[i].plan_end_date}")
                user_end_dt = format_date_time(str(obj_user_plan_db[i].plan_end_date))
                dt = convert_user_time_to_utc(user_end_dt, request_metadata["timezone"] )
                user_end_dt = convert_to_user_timezone(dt, request_metadata["timezone"]).strftime("%Y-%m-%d %H:%M:%S")

            obj_user_plan_ux = UXUserPlanIdentifier(user_id = str(obj_user_plan_db[i].user_id),
                                                plan_id = str(obj_user_plan_db[i].plan_id),
                                                plan_name = obj_user_plan_db[i].plan_name,
                                                plan_type = obj_user_plan_db[i].plan_type,
                                                plan_goal = obj_user_plan_db[i].plan_goal,
                                                plan_end_date= user_end_dt,
                                                plan_start_date= user_start_dt,
                                                plan_status= obj_user_plan_db[i].plan_status,
                                                approved_by_user= obj_user_plan_db[i].approved_by_user,
                                                follow_flag=obj_user_plan_db[i].follow_flag,
                                                private_flag=obj_user_plan_db[i].private_flag)
            
            obj_x.append(obj_user_plan_ux)

        rs = UXUserPlanIdentifierRS(content=obj_x)
        return rs
    except UserNotFound as e:
        raise e
    except IntegrityException as e:
        await db.rollback()
        logger.error(f"IntegrityError when retrieving all plans: {str(e)}")
        raise IntegrityException(
            f"IntegrityError when retrieving all plans: {str(e)}",
            context = {"detail": f"IntegrityError when retrieving all plans: {str(e)}"}
        )
    except GeneralDataException as e:
        await db.rollback()
        logger.error(f"Database error when retrieving all plans: {str(e)}")
        raise GeneralDataException(
            f"Database error when retrieving all plans: {str(e)}",
            context={"detail": f"Database error when retrieving all plans: {str(e)}"}
        )
    except Exception as e:
        logger.error(f"Some general error occured when retrieving all plans: {str(e)}")
        raise GeneralDataException(
            f"Some general error occured when retrieving all plans: {str(e)}",
            context = {"detail": f"Some general error occured when retrieving all plans: {str(e)}"})

'''
async def get_upcoming_activities_svc(obj: UXUpcomingActivitiesRequest, db: AsyncSession, current_user: User, request_metadata: Request ):
    try:

        current_utc = datetime.now(timezone.utc)
        filter_params = {}
        filter_params["user_id"] = current_user.user_id
        filter_params["start_date"] = current_utc
        filter_params["days_to_add"] = obj.days_to_add
        if obj.plan_id is not None:
            filter_params["plan_id"] = obj.plan_id.strip()
        obj_result = await get_upcoming_activities_db(filter_params=filter_params, db=db)
        current_utc = datetime.now(timezone.utc)
        obj_output = []
        if obj_result is not None and len(obj_result) > 0:
            for row in obj_result:
                if row["entity_type"] == 1000 or row["entity_type"] == 2 or row["entity_type"] ==  999:
                    continue
                logger.info(f"The row values are {row}")
                format_user_time = format_date_time(str(row["start_date"]))
                dt = convert_user_time_to_utc(format_user_time, request_metadata["timezone"] )

                if dt < current_utc:
                    state = "Past Due"
                elif dt > current_utc:
                    state = "Coming Soon"
                else:
                    state = "In Progress"

                obj_x = UXUpcomingActivitiesResponse(
                    plan_id=str(row["user_plan_id"]),
                    plan_name=row["plan_name"],
                    objective_start_date= convert_to_user_timezone(dt, request_metadata["timezone"]).strftime("%Y-%m-%d %H:%M:%S"),
                    obj_current_state=state,
                    reminder_request=row["reminder_request"],
                    reminder_request_time=row["request_reminder_time"],
                    plan_activity=row["activity_desc"],
                    entity_id = row["entity_id"],
                    entity_type = row["entity_type"],
                    progress_measure=row["progress_percent"],
                    status_id=row["status_id"])

                obj_output.append(obj_x)
            rs = UXUpcomingActivitiesResponseRS(content=obj_output)
        else:
            rs = UXUpcomingActivitiesResponseRS(content=None)
        return rs
    
    except GeneralDataException as e:
        await db.rollback()
        logger.error(f"Database error when selecting upcoming activities: {str(e)}")
        raise GeneralDataException(
            f"Database error when selecting upcoming activities: {str(e)}",
            context={"detail": "Database error when selecting upcoming activities:"}
        )
    except Exception as e:
        logger.error(f"Database error when selecting upcoming activities:: {str(e)}")
        raise GeneralDataException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error when selecting upcoming activities")


async def get_created_plan_detail_svc(plan_id: str, db: AsyncSession, current_user: User, fmp_flag: Optional[str] = None):
    try:

        obj_routine = []
        obj_gg = []
        logger.info(f"Inside the function to extract the created plan for plan_id: {plan_id}")

    # Perform database operations
        filter_params = {}
        if fmp_flag is None:
            filter_params["user_id"] = str(current_user.user_id)
        filter_params["plan_id"] = plan_id
        obj_user_plan_db = await get_plan(filter_params=filter_params, db=db)
        if not obj_user_plan_db:
            raise GeneralDataException(
                "Error in extracting plan detail",
                 {"detail": f"There is no row for this plan id.{plan_id}"}
            )     
        if (len(obj_user_plan_db) > 1 ):
            raise GeneralDataException(
                    "Error in extracting plan detail",
                 {"detail": f"There is more than one row for this id .{plan_id}"}
            )
        filter_params["intent"] = "display"
        obj_goals =  await get_goal_builder(filter_params, db)
        root_id = None
        prev_plan_id = None
        if obj_goals:
            root_id = obj_goals[0].root_id
            prev_plan_id = obj_goals[0].prev_plan_id

        obj_user_plan_ux = UXUserPlanIdentifier(user_id = str(obj_user_plan_db[0].user_id),
                                              plan_id = str(obj_user_plan_db[0].plan_id),
                                              plan_name = obj_user_plan_db[0].plan_name,
                                              plan_type = obj_user_plan_db[0].plan_type,
                                              plan_goal = obj_user_plan_db[0].plan_goal,
                                              plan_end_date= obj_user_plan_db[0].plan_end_date,
                                              plan_start_date= obj_user_plan_db[0].plan_start_date,
                                              root_id=root_id,
                                              prev_plan_id=prev_plan_id)

        obj_routine_summary = await get_plan_routine_summary(filter_params=filter_params, db=db)
        obj_x = []
        if obj_routine_summary is not None and len(obj_routine_summary) > 0:

            for i in range(len(obj_routine_summary )):
                obj_x.append(obj_routine_summary[i].routine)
        obj_routine = RoutineSummary(summary_item=obj_x)
        obj_x = []
        obj_general_guidelines = await get_general_guidelines(filter_params=filter_params,db=db)
        if obj_general_guidelines is not None and len(obj_general_guidelines) > 0 :

            for i in range(len(obj_general_guidelines)):
                obj_x.append(obj_general_guidelines[i].guideline)
        obj_gg = GeneralRecommendationAndGuidelines(general_descripton=obj_x)

        obj_x = []
        obj_created_plan = await get_created_plan(filter_params, db)

        for i in range(len(obj_created_plan)):
            obj_x.append(IUXCreatedPlan.model_validate(obj_created_plan[i]))
        
        obj_prompt_response_for_user = PlanDetailForUserManagement(
                                                            plan_header= obj_user_plan_ux,
                                                            routine_summary= obj_routine,
                                                            general_recommendation_guideline = obj_gg,
                                                            created_plan=obj_x
                                                            )
        return obj_prompt_response_for_user
    
    except IntegrityException as e:
        logger.error(f"Some integrity error at the db level when retrieving all created plans: {str(e)}")
        raise IntegrityException(
            f"Some integrity error at the db level when retrieving all created plans: {str(e)}",
            context = {"detail": f"Some integrity error at the db level when retrieving all created plans: {str(e)}"}
        )
    except GeneralDataException as e:
        logger.error(f"Database error when retrieving all plans: {str(e)}")
        raise GeneralDataException(
            f"Database error when retrieving all plans: {str(e)}",
            context={"detail": f"Database error when retrieving all plans: {str(e)}"}
        )
    except Exception as e:
        logger.error(f"Unexpected error when retrieving all plans: {str(e)}")
        raise GeneralDataException(
            f"Unexpected error when retrieving all plans: {str(e)}",
            context={"detail" : f"Unexpected error when retrieving all plans: {str(e)}"}
        )

async def get_executable_plan_detail_svc(plan_id: str, db: AsyncSession, current_user: User):
    try:

        plan_item = []
        obj_weekly_objective_user = []
        obj_daily_objective_user = []
        obj_activities_user = []
        obj_executable_resultset = []
        obj_routine = []
        obj_gg = []
        logger.info(f"Inserting the user plan for user {current_user.user_id}")

    # Perform database operations
        filter_params = {}
        filter_params["user_id"] = current_user.user_id
        filter_params["plan_id"] = plan_id
        logger.info(f"The user id is {current_user.user_id} and plan_id: {plan_id}")

        obj_routine_summary = await get_plan_routine_summary(filter_params=filter_params, db=db)
        obj_x = []
        if obj_routine_summary is not None and len(obj_routine_summary) > 0:

            for i in range(len(obj_routine_summary )):
                obj_x.append(obj_routine_summary[i].routine)
        obj_routine = RoutineSummary(summary_item=obj_x)
        obj_x = []
        obj_general_guidelines = await get_general_guidelines(filter_params=filter_params,db=db)
        if obj_general_guidelines is not None and len(obj_general_guidelines) > 0 :

            for i in range(len(obj_general_guidelines)):
                obj_x.append(obj_general_guidelines[i].guideline)
        obj_gg = GeneralRecommendationAndGuidelines(general_descripton=obj_x)

        
        obj_executable_plan_detail = await get_executable_plan(filter_params=filter_params, db=db)
        for i in range(len(obj_executable_plan_detail)):
            obj_x = IExecutionPlanDetail(plan_id = str(obj_executable_plan_detail[i].plan_id),
                                            sequence_id=obj_executable_plan_detail[i].sequence_id,
                                            level_id=obj_executable_plan_detail[i].level_id,
                                            entity_id=str(obj_executable_plan_detail[i].entity_id),
                                            entity_type=obj_executable_plan_detail[i].entity_type,
                                            parent_id=obj_executable_plan_detail[i].parent_id,
                                            start_date=obj_executable_plan_detail[i].start_date,
                                            status_id=obj_executable_plan_detail[i].status_id,
                                            reminder_request=obj_executable_plan_detail[i].reminder_request,
                                            progress_measure=obj_executable_plan_detail[i].progress_measure,
                                            activity_desc=obj_executable_plan_detail[i].activity_desc  ,
                                            request_reminder_time=obj_executable_plan_detail[i].request_reminder_time
                                            )
            obj_executable_resultset.append(obj_x)
        
        return UXApprovedPlanDetail(plan_detail=obj_executable_resultset,
                                    routine_summary=obj_routine,
                                    general_guidelines=obj_gg)
    
    except IntegrityException as e:
        logger.error(f"Some integrity error at the db level when retrieving all exexcutable plans: {str(e)}")
        raise IntegrityException(
            f"Some integrity error at the db level when retrieving all exexcutable plans: {str(e)}",
            context = {"detail": f"Some integrity error at the db level when retrieving all exexcutable plans: {str(e)}"}
        )
    except GeneralDataException as e:
        logger.error(f"Database error when retrieving all exexcutable plans: {str(e)}")
        raise GeneralDataException(
            f"Database error when retrieving all exexcutable plans: {str(e)}",
            context={"detail": f"Database error when retrieving all exexcutable plans: {str(e)}"}
        )
    except Exception as e:
        logger.error(f"Unexpected error when retrieving all exexcutable plans: {str(e)}")
        raise GeneralDataException(
            f"Unexpected error when retrieving all exexcutable plans: {str(e)}",
            context={"detail" :f"Unexpected error when retrieving all exexcutable plans: {str(e)}"}
        )




async def pause_plan():
    """
    
    """


async def update_plan_header_svc(obj_plan: UXUserPlanUpdate, db: AsyncSession, current_user: User):
    try:

        update_filter = {}
        value_params = {}
        update_filter["plan_id"] = obj_plan.plan_id
        update_filter["user_id"] = current_user.user_id

        if obj_plan.follow_flag is not None:
            update_filter["follow_flag"] = obj_plan.follow_flag
        if obj_plan.private_flag is not None:
            update_filter["private_flag"] = obj_plan.private_flag

        obj_task_update = await update_plan(obj_plan.plan_id, update_filter, db)
        return obj_task_update
    
    except SQLAlchemyError as e:
        logger.error(f"Database error when updating the private or follow flag: {str(e)}")
        raise HTTPException(
            f"Database error when updating the private or follow flag: {str(e)}",
            detail=f"Database error when updating the private or follow flag: {str(e)}"
        )
    except IntegrityException as e:

        logger.error(f"IntegrityError when updating the private or follow flag: {str(e)}")
        raise IntegrityException(
            f"IntegrityError when updating the private or follow flag: {str(e)}",
            context = {"detail": f"IntegrityError when updating the private or follow flag: {str(e)}"}
        )
    except GeneralDataException as e:

        logger.error(f"Database error when updating the private or follow flag: {str(e)}")
        raise GeneralDataException(
            f"Database error when updating the private or follow flag: {str(e)}",
            context={"detail": f"Database error when updating the private or follow flag: {str(e)}"}
        )
    except TimeZoneException as e:
        logger.error(f"Some error with Date Manipulation when updating the private or follow flag: {str(e)}")
        raise GeneralDataException(
            f"Some error with Date Manipulation when updating the private or follow flag: {str(e)}",
            context={"detail": f"Some error with Date Manipulation when updating the private or follow flag: {str(e)}"}
        )
    except Exception as e:
        logger.error(f"Some general error when updating the private or follow flag: {str(e)}")
        raise GeneralDataException(
            message=f"Some general error when updating the private or follow flag: {str(e)}",
            context={"detail": f"Some general error when updating the private or follow flag: {str(e)}"})
    

async def get_child_tasks_svc(plan_id: UUID, entity_id: UUID, db: AsyncSession,                          
                        current_user: User ):
    
    try:
        filter_params = {}
        filter_params["user_id"] = current_user.user_id
        filter_params["plan_id"] = plan_id
        filter_params["parent_id"] = entity_id

        obj_routine_summary = await get_executable_plan(filter_params,db)
        obj_child_tasks = []
        for i in range(len(obj_routine_summary)):
            obj_child_tasks.append(IExecutionPlanDetail.model_validate(obj_routine_summary[i])) 
        return obj_child_tasks

    except SQLAlchemyError as e:
        logger.error(f"Database error when updating the private or follow flag: {str(e)}")
        raise HTTPException(
            f"Database error when updating the private or follow flag: {str(e)}",
            detail=f"Database error when updating the private or follow flag: {str(e)}"
        )
    except IntegrityException as e:

        logger.error(f"IntegrityError when updating the private or follow flag: {str(e)}")
        raise IntegrityException(
            f"IntegrityError when updating the private or follow flag: {str(e)}",
            context = {"detail": f"IntegrityError when updating the private or follow flag: {str(e)}"}
        )
    except GeneralDataException as e:

        logger.error(f"Database error when updating the private or follow flag: {str(e)}")
        raise GeneralDataException(
            f"Database error when updating the private or follow flag: {str(e)}",
            context={"detail": f"Database error when updating the private or follow flag: {str(e)}"}
        )
    except TimeZoneException as e:
        logger.error(f"Some error with Date Manipulation when updating the private or follow flag: {str(e)}")
        raise GeneralDataException(
            f"Some error with Date Manipulation when updating the private or follow flag: {str(e)}",
            context={"detail": f"Some error with Date Manipulation when updating the private or follow flag: {str(e)}"}
        )
    except Exception as e:
        logger.error(f"Some general error when updating the private or follow flag: {str(e)}")
        raise GeneralDataException(
            message=f"Some general error when updating the private or follow flag: {str(e)}",
            context={"detail": f"Some general error when updating the private or follow flag: {str(e)}"})
    


'''

async def build_approved_plan(obj_plan: UXPlanApprovalPL,  db: AsyncSession,current_user: User, request_metadata: Request):
    try:
        if obj_plan.plan_start_date is None:
            raise GeneralDataException(
                message="Plan Start Date is missing",
                context={"detail": "Required plan start date is missing"}
            ) 
        current_utc = datetime.now(timezone.utc)
        format_user_time = format_date_time(str(obj_plan.plan_start_date))
        user_time_in_otc = convert_user_time_to_utc(format_user_time, "America/Los_Angeles")

        if user_time_in_otc < current_utc:
            logger.error("The plan cannot start in the past")
            raise GeneralDataException(
            message= "Plan cannot be approved with the given date",
            context= {"detail": f" Plan cannot be updated with past date {obj_plan.plan_start_date}"}
            )
        filter_params = {}
        filter_params["plan_id"] = obj_plan.plan_id
        filter_params["user_id"] = current_user.user_id
        plan_resultset =  await get_plan(filter_params,db)

        if len(plan_resultset) < 0:
            raise GeneralDataException(
                message= f"Plan is not owned by the user {filter_params['plan_id']}",
                context={"detail": f"Plan is not owned by the user {filter_params['plan_id']}" }
            ) 

        del filter_params["user_id"] 

        obj_week_resultset = {}
        obj_daily_resultset = {}
        obj_activity_resultset = {}
        obj_week_resultset = await get_plan_weekly_detail(filter_params=filter_params, db=db)
        obj_daily_resultset = await get_plan_day_detail(filter_params=filter_params, db=db)
        obj_activity_resultset = await get_plan_activity_detail(filter_params=filter_params, db=db)
        week_obj_hash = {}
        day_obj_hash = {}
        if plan_resultset[0].plan_type == "Weekly":
            if len(obj_week_resultset) < 0:
                logger.error("The plan is a weekly plan, but no data in the week table {str(plan_resultset.plan_id)}")
                raise GeneralDataException(
                message= "The plan is a weekly plan, but no data in the week table",
                context= {"detail": f"The plan is a weekly plan, but no data in the week table {str(plan_resultset.plan_id)}"}
                )
            for i in range(len(obj_week_resultset)):
                if i == 0 :
                    dt_start_date = obj_plan.plan_start_date
                else:
                    dt_start_date = obj_execution_plan.start_date + timedelta(days=7)
                sequence_id = (i +1) * 10000
                print ("The entity id is ", obj_week_resultset[i].entity_id)
                obj_execution_plan = IExecutionPlanDetail(plan_id = obj_plan.plan_id,
                                                        sequence_id= sequence_id,
                                                        level_id=Level.ROOT,
                                                        entity_type = EntityType.WEEK,
                                                        parent_id=None,
                                                        entity_id = obj_week_resultset[i].entity_id,
                                                            start_date = dt_start_date,
                                                            status_id= PlanStatus.TO_BE_STARTED,
                                                            reminder_request = None,
                                                            progress_measure= 0.0,
                                                            activity_desc= obj_week_resultset[i].week_objective,
                                                            request_reminder_time= None
                                                        )
                
                obj_execution_plan_db = await insert_approved_plan(obj_execution_plan, db)
                week_obj_hash["week_number_" + str(obj_week_resultset[i].week_objective_sequence)] = {
                                    "start_date" : dt_start_date, 
                                    "sequence_id" :  sequence_id,
                                    "entity_id": obj_week_resultset[i].entity_id }
        if len(obj_daily_resultset) < 0:
                logger.error("The plan has no daily objective data {str(plan_resultset.plan_id)}")
                raise GeneralDataException(
                message= "The plan is a weekly plan, but no data for daily objective",
                context= {"detail": f"The plan is a weekly plan, but no data for daily objectives {str(plan_resultset.plan_id)}"}
                )
        for i in range(len(obj_daily_resultset)):
            if plan_resultset[0].plan_type == "Weekly":
                week_key = "week_number_" + str(obj_daily_resultset[i].week_objective_sequence)
                parent_id = week_obj_hash[week_key]["entity_id"]
                daily_exec_sequence_id = week_obj_hash[week_key]["sequence_id"] + ((i + 1)*100)
                dt_start_date = week_obj_hash[week_key]["start_date"] + timedelta(days=i)
                level_id = Level.BRANCH
            else:
                parent_id = None
                daily_exec_sequence_id = (i+1) * 10000
                dt_start_date = obj_plan.plan_start_date + timedelta(days=i)
                level_id = Level.ROOT

            obj_execution_plan = IExecutionPlanDetail(plan_id = obj_plan.plan_id,
                                            sequence_id= daily_exec_sequence_id,
                                            level_id=level_id,
                                            entity_type = EntityType.DAY,
                                            parent_id=parent_id,
                                            entity_id = obj_daily_resultset[i].entity_id,
                                            start_date = dt_start_date,
                                            status_id= PlanStatus.TO_BE_STARTED,
                                            reminder_request = None,
                                            progress_measure= 0.0,
                                            activity_desc = obj_daily_resultset[i].day_objective,
                                            request_reminder_time= None
                                            )
            print ("The day entity id is ", obj_daily_resultset[i].entity_id)
            obj_execution_plan_db = await insert_approved_plan(obj_execution_plan, db)
            day_obj_hash["week_day_number_" + str(obj_daily_resultset[i].week_objective_sequence) + "_" + str(obj_daily_resultset[i].day_objective_sequence) ] = {
                        "start_date" : dt_start_date, 
                        "sequence_id" :  daily_exec_sequence_id,
                        "entity_id": obj_daily_resultset[i].entity_id }
            
        for i in range(len(obj_activity_resultset)):
            day_key = "week_day_number_" + str(obj_activity_resultset[i].week_objective_sequence) + "_" + str(obj_activity_resultset[i].day_objective_sequence)
            if day_key in day_obj_hash and day_obj_hash[day_key]:
                obj_execution_plan = IExecutionPlanDetail(plan_id = obj_plan.plan_id,
                                                sequence_id= day_obj_hash[day_key]["sequence_id"] + i + 1,
                                                level_id=Level.LEAF,
                                                entity_type = EntityType.ACTIVITY,
                                                parent_id=day_obj_hash[day_key]["entity_id"],
                                                entity_id = obj_activity_resultset[i].activity_id,
                                                start_date = day_obj_hash[day_key]["sequence_id"],
                                                status_id= PlanStatus.NOT_APPLICABLE,
                                                reminder_request = None,
                                                progress_measure= 0.0,
                                                activity_desc = obj_activity_resultset[i].activity,
                                                request_reminder_time= obj_activity_resultset[i].suggest_time
                                                )
                obj_execution_plan_db = await insert_approved_plan(obj_execution_plan, db)
        value_params = {}
        value_params["plan_start_date"] = user_time_in_otc
        value_params["approved_by_user"] =  PlanStatus.APPROVED_BY_USER.value
        obj_update_plan = await update_plan(obj_plan.plan_id,value_params=value_params, db=db )
        obj_approved_plan = await get_executable_plan(filter_params=filter_params, db=db)
        obj_approved_plan_for_ux = []
        for i in range(len(obj_approved_plan)):
            x = IExecutionPlanDetail(
                plan_id = str(obj_approved_plan[i].plan_id),
                sequence_id= obj_approved_plan[i].sequence_id,
                level_id = obj_approved_plan[i].level_id,
                entity_id= str(obj_approved_plan[i].entity_id),
                entity_type= obj_approved_plan[i].entity_type,
                parent_id= str(obj_approved_plan[i].parent_id),
                start_date=obj_approved_plan[i].start_date,
                status_id=obj_approved_plan[i].status_id,
                reminder_request=obj_approved_plan[i].reminder_request,
                progress_measure=obj_approved_plan[i].progress_measure,
                activity_desc=obj_approved_plan[i].activity_desc,
                request_reminder_time= obj_approved_plan[i].request_reminder_time
            )
            obj_approved_plan_for_ux.append(x)
        return UXApprovedPlanDetail(plan_detail=obj_approved_plan_for_ux)
    except IntegrityException as e:

        logger.error(f"IntegrityError when inserting user plan: {str(e)}")
        raise IntegrityException(
            "Integrity error when inserting a user plan",
            context = {"detail": "This plan conflicts with an existing plan. Possible duplicate entry or foreign key constraint failure."}
        )
    except GeneralDataException as e:

        logger.error(f"Database error when inserting user plan: {str(e)}")
        raise GeneralDataException(
            "Data base error occured while inserting the executed plan",
            context={"detail": "Database error occurred while creating the user plan"}
        )
    except TimeZoneException as e:
        logger.error(f"Time manipulation error when inserting executed plan: {str(e)}")
        raise GeneralDataException(
            f"Time manipulation error when inserting executed plan: {str(e)}",
            context={"detail": f"Time manipulation error when inserting executed plan: {str(e)}"}
        )
    except Exception as e:
        logger.error(f"Unexpected error in executing the approved plan: {str(e)}")
        raise GeneralDataException(
            "Unexpected error occured formatting date",
            context={"detail" : "An unexpected error occurred while formatting the date"}
        )

        async def get_created_plan_detail_svc(plan_id: str, db: AsyncSession, current_user: User):
    try:

        plan_item = []
        obj_weekly_objective_user = []
        obj_daily_objective_user = []
        obj_activities_user = []
        obj_executable_resultset = []
        obj_routine = []
        obj_gg = []
        logger.info(f"Inside the function to extract the created plan for plan_id: {plan_id}")

    # Perform database operations
        filter_params = {}
        filter_params["user_id"] = str(current_user.user_id)
        filter_params["plan_id"] = plan_id
        obj_user_plan_db = await get_plan(filter_params=filter_params, db=db)
        if not obj_user_plan_db:
            raise GeneralDataException(
                "Error in extracting plan detail",
                 {"detail": f"There is no row for this plan id.{plan_id}"}
            )     
        if (len(obj_user_plan_db) > 1 ):
            raise GeneralDataException(
                    "Error in extracting plan detail",
                 {"detail": f"There is more than one row for this id .{plan_id}"}
            )
        obj_user_plan_ux = UXUserPlanIdentifier(user_id = str(obj_user_plan_db[0].user_id),
                                              plan_id = str(obj_user_plan_db[0].plan_id),
                                              plan_name = obj_user_plan_db[0].plan_name,
                                              plan_type = obj_user_plan_db[0].plan_type,
                                              plan_goal = obj_user_plan_db[0].plan_goal,
                                              plan_end_date= obj_user_plan_db[0].plan_end_date,
                                              plan_start_date= obj_user_plan_db[0].plan_start_date)

        obj_routine_summary = await get_plan_routine_summary(filter_params=filter_params, db=db)
        obj_x = []
        if obj_routine_summary is not None and len(obj_routine_summary) > 0:

            for i in range(len(obj_routine_summary )):
                obj_x.append(obj_routine_summary[i].routine)
        obj_routine = RoutineSummary(summary_item=obj_x)
        obj_x = []
        obj_general_guidelines = await get_general_guidelines(filter_params=filter_params,db=db)
        if obj_general_guidelines is not None and len(obj_general_guidelines) > 0 :

            for i in range(len(obj_general_guidelines)):
                obj_x.append(obj_general_guidelines[i].guideline)
        obj_gg = GeneralRecommendationAndGuidelines(general_descripton=obj_x)
        obj_created_plan = await get_created_plan(filter_params, db)

        for i in range(len(obj_created_plan)):
            obj_x = IUXCreatedPlan(obj_created_plan[i])
        obj_weekly_detail = await get_plan_weekly_detail(filter_params=filter_params, db=db)
        for i in range(len(obj_weekly_detail)):
            obj_x = WeeklyPlanIdentifier(week_number=obj_weekly_detail[i].week_number,
                                            week_text = obj_weekly_detail[i].week_text,
                                            week_objective_sequence=obj_weekly_detail[i].week_objective_sequence,
                                            plan_id=str(obj_weekly_detail[i].plan_id),
                                            weekly_objective=obj_weekly_detail[i].week_objective
                                            )
            obj_weekly_objective_user.append(obj_x)
        obj_daily_detail = await get_plan_day_detail(filter_params=filter_params,db=db)
        for i in range(len(obj_daily_detail)):
            obj_x = ActivityByDayIdentifier(day_number=obj_daily_detail[i].day_number,
                                            day_text= obj_daily_detail[i].day_text,
                                            daily_objective=obj_daily_detail[i].day_objective,
                                            suggested_time=obj_daily_detail[i].suggest_time,
                                            suggested_duration=obj_daily_detail[i].suggest_duration,
                                            plan_id=str(obj_daily_detail[i].plan_id),
                                            week_number=obj_daily_detail[i].week_number,
                                            week_objective_sequence=obj_daily_detail[i].week_objective_sequence,
                                            day_objective_sequence=obj_daily_detail[i].day_objective_sequence)
            obj_daily_objective_user.append(obj_x)
        obj_activity_detail = await get_plan_activity_detail(filter_params=filter_params, db=db)
        for i in range(len(obj_activity_detail)):
            obj_x = ActivityDetailIdentifier(activity=obj_activity_detail[i].activity,
                                                plan_id=str(obj_activity_detail[i].plan_id),
                                                week_number=obj_activity_detail[i].week_number,
                                                day_number=obj_activity_detail[i].day_number,
                                                suggest_duration=obj_activity_detail[i].suggest_duration,
                                                suggest_time=obj_activity_detail[i].suggest_time,
                                                activity_sequence=obj_activity_detail[i].activity_sequence,
                                                week_objective_sequence=obj_activity_detail[i].week_objective_sequence,
                                                day_objective_sequence=obj_activity_detail[i].day_objective_sequence,
                                                activity_id=str(obj_activity_detail[i].activity_id))
            obj_activities_user.append(obj_x)
        obj_prompt_response_for_user = PlanDetailForUserManagement(
                                                            plan_header= obj_user_plan_ux,
                                                            routine_summary= obj_routine,
                                                            general_recommendation_guideline = obj_gg,
                                                            Weekly_objectives= obj_weekly_objective_user,
                                                            daily_objectives= obj_daily_objective_user,
                                                            activities= obj_activities_user
                                                            )
        return obj_prompt_response_for_user
    
    except IntegrityException as e:
        logger.error(f"Some integrity error at the db level when retrieving all created plans: {str(e)}")
        raise IntegrityException(
            f"Some integrity error at the db level when retrieving all created plans: {str(e)}",
            context = {"detail": f"Some integrity error at the db level when retrieving all created plans: {str(e)}"}
        )
    except GeneralDataException as e:
        logger.error(f"Database error when retrieving all plans: {str(e)}")
        raise GeneralDataException(
            f"Database error when retrieving all plans: {str(e)}",
            context={"detail": f"Database error when retrieving all plans: {str(e)}"}
        )
    except Exception as e:
        logger.error(f"Unexpected error when retrieving all plans: {str(e)}")
        raise GeneralDataException(
            f"Unexpected error when retrieving all plans: {str(e)}",
            context={"detail" : f"Unexpected error when retrieving all plans: {str(e)}"}
        )
   

'''

