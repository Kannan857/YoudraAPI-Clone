from app.service import user_prompt_meta_data
from app.service.user_plan_approval import  (build_approved_plan, 
                                             get_all_plans, 
                                             get_created_plan_detail_svc, 
                                             get_executable_plan_detail_svc, 
                                             get_upcoming_activities_svc, 
                                             update_approved_plan_dates, 
                                             set_reminder_svc, 
                                             update_objective_status_svc,
                                             get_child_tasks_svc
                                            )
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from fastapi.responses import JSONResponse
from app.model.user_prompt_response import (PlanDetailForUserManagement, 
                                            UXUserPromptInfo, 
                                            UXRevisionHistoryI,
                                            UXGoalBuilder)
from app.model.user_plan import (UserPlanIdentifier, 
                                 UserPlan, 
                                 UXPlanApprovalPL, 
                                 UXApprovedPlanDetail, 
                                 UXUpdateApprovedPlan, 
                                 UXUpcomingActivitiesRequest, 
                                 UXUpcomingActivitiesResponseRS, 
                                 UXUserPlanIdentifierRS,
                                 IExecutionPlanDetail)
from app.model.plan_manager import FmpSubscriberGet
from sqlalchemy.ext.asyncio import AsyncSession
from app.data.dbinit import get_db
from app.data.user import User
from app.service.user import get_current_active_user
from app.common.exception import DatabaseConnectionException, IntegrityException, GeneralDataException, UserNotFound, PlanIllegalText, PlanAlreadyApproved, PlanContextChange, NotEnoughInfoToGenerateGoal
from app.common.request_metadata import get_request_metadata
from app.common.messaging import get_rabbitmq_connection
from app.common.rewards_init import get_rewards_service
from app.service.rewards import RewardEarnedResponse, RewardsService
import aio_pika
from typing import Optional, List
from uuid import UUID
router = APIRouter()
import structlog

logger = structlog.get_logger()

@router.post("/createplan/", response_model=PlanDetailForUserManagement)
async def process_prompt(obj_user_prompt: UXUserPromptInfo, 
                         db: AsyncSession = Depends(get_db), 
                         current_user: User = Depends(get_current_active_user),
                         msg_connection: aio_pika.RobustConnection = Depends(get_rabbitmq_connection) ):
    """
    THE API works in the following manner.
    prompt_text - Use this field to assign the user entered query. 

    The response will have the following arrays

    plan_header: This will have all the information about the plan including plan_id, plan_type, plan_goal. Not all columns should be used for user display
    routine_summary: Each plan will have a routine summary to help the user understand what to expect. This is nothing but a list of bullet points. This will be there all plans
    general_recommendation_guideline: This is similar to the above. For example, let's say the user asked "Give me a plan to reduce weight". This section will give all the precautionary measures as a list of points.
    Weekly_objectives: If the plan is by week, this array will be populated otherwise it will be empty
    Note: A weekly plan will have objectives for each week and each week will have a set of objectives by day in the following array. 
    Followed by a set of activities for each daily objective in the activities array mentioned below. You will use the week_objective_sequence to order the list

    daily_objectives: If the plan is by week or by day, this array will be populated. 
    If it is a weekly plan, you will have the week_objective_sequence and day_objective_sequence to order the content.
    
    activities: This will have activities for objectives. If it is a weekly plan, you should use the week_object_sequence, day_objective_sequence , and activity sequence to order the activities
    if it is a daily plan, you will use day_objective_sequence and activity_Sequence to order.

    """

    try:
        return await user_prompt_meta_data.process_user_plan_prompt(obj_user_prompt, db, current_user, msg_connection )
    except PlanContextChange as e:
        raise HTTPException(
            status_code=422,
            detail=f"Context change detected: {e.reason}. Prompt: {e.prompt_text}"
        )
    except NotEnoughInfoToGenerateGoal as e:
        raise HTTPException(
            status_code=422,
            detail={"detail":f"Not enough information to generate goal: {e.reason}. Prompt: {e.prompt_text}", "code": "NOT_ENOUGH_INFORMATION"}
        )
    except PlanIllegalText as e:
        raise HTTPException(
            status_code=422,
            detail=f"Illegal text detected in the prompt text: {e.reason}. Prompt: {e.prompt_text}"
        )
    except DatabaseConnectionException as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=e.message,
            )
    except GeneralDataException as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f" Gerneral Data Error in processing user prompt: {e.message}",
            )
    except IntegrityException as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f" Integrity error in processing user prompt: {e.message}",
            )
    except Exception as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to process the user prompt",
            )

@router.post("/createtestplan/", response_model=UserPlanIdentifier)
async def create_test_plan(plan_input: UserPlan, db: AsyncSession = Depends(get_db), meta = Depends(get_request_metadata) ):
    """
    DO NOT USE THIS API. This was created for internal testing purposes and there is no guarantee that this will work
    """
    try:

        return await user_prompt_meta_data.create_user_plan(plan_input, db)
    except DatabaseConnectionException as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unable to create user plan {e.message}",
            )
    except GeneralDataException as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                 detail=f"Unable to create user plan {e.message}",

            )
    except IntegrityException as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                 detail=f"Unable to create user plan {e.message}",
            )
    except Exception as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unable to create user plan {e.message}",
            )

'''

async def api_build_approved_plan(plan_input: UXPlanApprovalPL, db: AsyncSession = Depends(get_db), 
                                  current_user: User = Depends(get_current_active_user),
                                  request_metadata = Depends(get_request_metadata)):
'''


@router.post("/approveplan/", response_model=UXApprovedPlanDetail)
async def api_build_approved_plan(plan_input: UXPlanApprovalPL, db: AsyncSession = Depends(get_db), 
                                  current_user: User = Depends(get_current_active_user),
                                  request_metadata = Depends(get_request_metadata),
                                  rewards_service: RewardsService = Depends(get_rewards_service)):

    """

    Understand this concept: A plan that is created (aka created plan) by the user will not be tracked until it is approved by the user.
    The plan will become executable plan once approved. Certain functionalities are applicable to only executable plan, which I will 
    describe in the appropriate API methods. 
    The intent of this method is to approve a previously created plan by the user.
    Plan id, and plan_start_date  are mandatory. The rest of the fields are optional for now

    """

    try:
        return await build_approved_plan(plan_input, db, current_user, request_metadata, rewards_service )
        #return await build_approved_plan(plan_input, db, current_user, request_metadata )
    except PlanAlreadyApproved as e:
        logger.error(f" Plan Already exists")
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail= f"Unable to approve the plan. The plan already exists",
            )
    except DatabaseConnectionException as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unable to create user plan {e.message}",
            )
    except GeneralDataException as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                 detail=f"Unable to create user plan {e.message}",

            )
    except IntegrityException as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                 detail=f"Unable to create user plan {e.message}",
            )
    except Exception as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail= f"Unable to create user plan {str(e)}",
            )

@router.post("/updateapprovedplandates/")
async def adjust_plan_dates(plan_input: UXUpdateApprovedPlan, db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(get_current_active_user),
                       request_metadata = Depends(get_request_metadata)):
    """
    Thie API is used to move an approved by the number of days mentioned by the user.

    If the user wants to move the entire (executable) plan by, say 5 days, the following fields are mandatory

    plan_id,
    days_to_move

    If the user wants to move a specific activity (in an executable plan) by a few days, then the following fields are mandatory
    plan_id,
    entity_id,
    sequence_id,
    days_to_move

    NOTE: You dont have to include the non-mandatory fields (aka optional fields)

    """
    try:
        
        nRet = await update_approved_plan_dates(plan_input, db, current_user, request_metadata)
        return JSONResponse(status_code=200, content={"detail": "Successfully completed"})
    except DatabaseConnectionException as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unable to create user plan {e.message}",
            )
    except GeneralDataException as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                 detail=f"Unable to create user plan {str(e)}",

            )
    except IntegrityException as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                 detail=f"Unable to create user plan {e.message}",
            )
    except Exception as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail= f"Unable to create user plan {str(e)}",
            )


@router.post("/setreminder/", response_model=UXApprovedPlanDetail)
async def set_reminder(plan_input: UXUpdateApprovedPlan, db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(get_current_active_user),
                       request_metadata = Depends(get_request_metadata)):
    """
    Thie API is used to set reminder for a specific task in an approved plan.

    following fields are mandatory

    plan_id,
    entity_id,
    sequence_id
    request_reminder, ( the value should be 1)
    request_reminder_time

    NOTE: Use HH:MM for request time where HH = 00 to 24. For example, to set a reminder for 3PM it should be 15:00

    """
    try:
        
        nRet = await set_reminder_svc(plan_input, db, current_user, request_metadata)
        return JSONResponse(status_code=200, content={"detail": "Successfully completed"})
    except DatabaseConnectionException as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unable to create user plan {e.message}",
            )
    except GeneralDataException as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                 detail=f"Unable to create user plan {str(e)}",

            )
    except IntegrityException as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                 detail=f"Unable to create user plan {e.message}",
            )
    except Exception as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail= f"Unable to create user plan {str(e)}",
            )

@router.post("/updateobjectivestatus/", response_model=UXApprovedPlanDetail)
async def set_objective_status(plan_input: UXUpdateApprovedPlan, db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(get_current_active_user),
                       request_metadata = Depends(get_request_metadata)):
    """
    Thie API is used to set the status for a specific task in an approved plan.

    following fields are mandatory

    plan_id,
    entity_id,
    sequence_id,
    status_id
    """
    
    try:
        
        nRet = await update_objective_status_svc(plan_input, db, current_user, request_metadata)
        return JSONResponse(status_code=200, content={"detail": "Successfully completed"})
    except DatabaseConnectionException as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unable to create user plan {e.message}",
            )
    except GeneralDataException as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                 detail=f"Unable to create user plan {str(e)}",

            )
    except IntegrityException as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                 detail=f"Unable to create user plan {e.message}",
            )
    except Exception as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail= f"Unable to create user plan {str(e)}",
            )

'''
@router.post("/getplanimpersonate/", response_model=UXUserPlanIdentifierRS)
async def get_plan_impersonate_api(fmp: FmpSubscriberGet, db: AsyncSession = Depends(get_db), 
                            current_user: User = Depends(get_current_active_user),
                            request_metadata = Depends(get_request_metadata)):
    try:
        return await get_plan_impersonate(db, fmp, current_user, request_metadata)
    except UserNotFound as e:
        raise e
    except DatabaseConnectionException as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unable to create user plan {e.message}",
            )
    except GeneralDataException as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                 detail=f"Unable to create user plan {e.message}",

            )
    except IntegrityException as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                 detail=f"Unable to create user plan {e.message}",
            )
    except Exception as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unable to create user plan {str(e)}",
            )
   
'''

@router.post("/getallplans/", response_model=UXUserPlanIdentifierRS)
async def get_approved_plan(db: AsyncSession = Depends(get_db), 
                            current_user: User = Depends(get_current_active_user),
                            request_metadata = Depends(get_request_metadata)):
    try:
        return await get_all_plans(db, current_user, request_metadata)
    except UserNotFound as e:
        raise e
    except DatabaseConnectionException as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unable to create user plan {e.message}",
            )
    except GeneralDataException as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                 detail=f"Unable to create user plan {e.message}",

            )
    except IntegrityException as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                 detail=f"Unable to create user plan {e.message}",
            )
    except Exception as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unable to create user plan {str(e)}",
            )
    
@router.post("/getupcomingactivities/", response_model=UXUpcomingActivitiesResponseRS)
async def get_executable_plan_activities(
                                        obj: UXUpcomingActivitiesRequest,
                                        db: AsyncSession = Depends(get_db), 
                                         current_user: User = Depends(get_current_active_user),
                                         request_metadata = Depends(get_request_metadata)):
    try:
        print (f"The plan id is {obj.plan_id}")
        return await get_upcoming_activities_svc(obj,db, current_user, request_metadata)
    except DatabaseConnectionException as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unable to create user plan {e.message}",
            )
    except GeneralDataException as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                 detail=f"Unable to create user plan {e.message}",

            )
    except IntegrityException as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                 detail=f"Unable to create user plan {e.message}",
            )
    except Exception as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unable to create user plan {str(e)}",
            )


@router.post("/getcreatedplandetail/{plan_id}", response_model=PlanDetailForUserManagement)
async def get_created_plan_detail(plan_id: str,
                        db: AsyncSession = Depends(get_db), 
                        current_user: User = Depends(get_current_active_user)):
    try:
        return await get_created_plan_detail_svc(plan_id=plan_id, db=db, current_user=current_user)
    except DatabaseConnectionException as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unable to create user plan {e.message}",
            )
    except GeneralDataException as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                 detail=f"Unable to create user plan {e.message}",

            )
    except IntegrityException as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                 detail=f"Unable to create user plan {e.message}",
            )
    except Exception as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unable to create user plan {str(e)}",
            ) 


@router.post("/getfmpcreatedplandetail/{plan_id}", response_model=PlanDetailForUserManagement)
async def get_created_plan_detail(plan_id: str,
                        db: AsyncSession = Depends(get_db), 
                        current_user: User = Depends(get_current_active_user)):
    try:
        return await get_created_plan_detail_svc(plan_id=plan_id, db=db, current_user=current_user, fmp_flag="yes")
    except DatabaseConnectionException as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unable to create user plan {e.message}",
            )
    except GeneralDataException as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                 detail=f"Unable to create user plan {e.message}",

            )
    except IntegrityException as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                 detail=f"Unable to create user plan {e.message}",
            )
    except Exception as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unable to create user plan {str(e)}",
            ) 
    

@router.get("/getexecutedplandetail/{plan_id}", response_model=UXApprovedPlanDetail)
async def get_executed_plan_detail(plan_id: str,
                        db: AsyncSession = Depends(get_db), 
                        current_user: User = Depends(get_current_active_user)):
    try:
        return await get_executable_plan_detail_svc(plan_id=plan_id, db=db, current_user=current_user)
    except DatabaseConnectionException as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unable to create user plan {e.message}",
            )
    except GeneralDataException as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                 detail=f"Unable to create user plan {e.message}",

            )
    except IntegrityException as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                 detail=f"Unable to create user plan {e.message}",
            )
    except Exception as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unable to create user plan {str(e)}",
            ) 
    
@router.post("/getpromptrevisionhistory/", response_model=Optional[List[UXGoalBuilder]])
async def process_prompt(obj_input: UXRevisionHistoryI,
                         db: AsyncSession = Depends(get_db), 
                         current_user: User = Depends(get_current_active_user) ):
    
    try:
        filter_params = {}
        if obj_input.plan_id is not None:
            filter_params["plan_id"] = obj_input.plan_id
        if obj_input.root_id is not None:
            filter_params["root_id"] = obj_input.root_id
        return await user_prompt_meta_data.get_prompt_history_svc(filter_params, db, current_user)
    except DatabaseConnectionException as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unable to create user plan {e.message}",
            )
    except GeneralDataException as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                 detail=f"Unable to create user plan {e.message}",

            )
    except IntegrityException as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                 detail=f"Unable to create user plan {e.message}",
            )
    except Exception as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unable to create user plan {str(e)}",
        )

@router.get("/getchildtasks/{plan_id}/{entity_id}", response_model=Optional[List[IExecutionPlanDetail]])
async def get_child_tasks(
                        plan_id: UUID,
                        entity_id: UUID,
                        db: AsyncSession = Depends(get_db), 
                        current_user: User = Depends(get_current_active_user)):
    try:
        return await get_child_tasks_svc(plan_id, entity_id, db, current_user)
    
    except DatabaseConnectionException as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unable to create user plan {e.message}",
            )
    except GeneralDataException as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                 detail=f"Unable to create user plan {e.message}",

            )
    except IntegrityException as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                 detail=f"Unable to create user plan {e.message}",
            )
    except Exception as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unable to create user plan {str(e)}",
            ) 