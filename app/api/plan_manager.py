from app.model.user_plan import UserPlanIdentifier, UserPlan, UXUserPlanUpdate, UXPlanApprovalPL, UXApprovedPlanDetail, UXUpdateApprovedPlan, UXUpcomingActivitiesRequest, UXUpcomingActivitiesResponseRS, UXUserPlanIdentifierRS
from sqlalchemy.ext.asyncio import AsyncSession
from app.data.dbinit import get_db
from app.data.user import User
from app.service.user import get_current_active_user
from app.common.exception import DatabaseConnectionException, RecordNotFoundException, IntegrityException, MissingDataException, GeneralDataException
from app.common.request_metadata import get_request_metadata
from app.common.messaging import get_rabbitmq_connection
import aio_pika
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from fastapi.responses import JSONResponse
from app.service.user_plan_approval import update_plan_header_svc
from app.service.plan_manager import (add_subscriber_svc, get_subscription_svc, get_subscriber_svc, get_fmp_plans)
from app.model.plan_manager import FmpSubscriberCreate, FmpSubscriberOut, FmpSubscriberUpdate, FmpSubscriberGet, FmpCountSummary
from typing import List, Optional
router = APIRouter()

import structlog
logger = structlog.get_logger()

@router.post("/enable_fmp/")
async def enable_follow_my_plan(plan_input: UXUserPlanUpdate, 
                                db: AsyncSession = Depends(get_db),
                                current_user: User = Depends(get_current_active_user) ):

    try:

        res =  await update_plan_header_svc(plan_input, db, current_user)
        return {"message" : f"flags updated successfully for plan {plan_input.plan_id}"}
    except DatabaseConnectionException as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unable to update the user plan with the flag inputs {e}",
            )
    except GeneralDataException as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                 detail=f"Unable to update the user plan with the flag inputs {e}",

            )
    except IntegrityException as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                 detail=f"Unable to update the user plan with the flag inputs {e}",
            )
    except Exception as e:
        logger.error(f"General Exception occured with enabling fmp {str(e)}")
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unable to update the user plan with the flag inputs {e}",
            )
    

    
@router.post("/subscribe_to_fmp/{plan_id}")
async def subscribe_to_fmp(plan_id: str,
                        db: AsyncSession = Depends(get_db), 
                        current_user: User = Depends(get_current_active_user)):
    try:

        fmp = FmpSubscriberCreate(plan_id=plan_id, user_id=current_user.user_id,is_active=1)
        return await add_subscriber_svc(db, fmp, current_user)
    except Exception as e:
        return HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unable to subscribe to fmp {str(e)}",
            ) 

@router.post("/get_my_subscriptions/")
async def get_my_subscriptions(fmp: FmpSubscriberGet,
                        db: AsyncSession = Depends(get_db), 
                        current_user: User = Depends(get_current_active_user)):
    try:
        ret = await get_subscription_svc(fmp, db, current_user)
        return ret
    except Exception as e:
        return HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unable to subscribe to fmp {str(e)}",
            ) 

@router.post("/get_my_subscribers/")
async def get_my_subscribers(fmp: FmpSubscriberGet,
                        db: AsyncSession = Depends(get_db), 
                        current_user: User = Depends(get_current_active_user)):
    try:
        ret = await get_subscriber_svc(fmp, db, current_user )
        return ret
    except Exception as e:
        return HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unable to subscribe to fmp {str(e)}",
            ) 

@router.get("/get_fmp_count/", response_model=Optional[List[FmpCountSummary]])
async def get_my_subscribers(
    db: AsyncSession = Depends(get_db), 
    current_user: User = Depends(get_current_active_user),
    limit: int = Query(10, ge=1, le=100),   # default 10, max 100
    offset: int = Query(0, ge=0)
):
    try:
        return await get_fmp_plans(db, current_user, limit, offset)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unable to subscribe to fmp {str(e)}",
        )
