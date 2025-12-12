from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
from app.data.dbinit import get_db
from typing import List, Optional
from app.service.progress_mgmt import create_progress_update_svc, get_progress_by_user_entity_svc
from uuid import UUID
from app.model.progress_mgmt import  ProgressUpdateCreate, ProgressUpdateOut, ProgressSummary
from app.common.request_metadata import get_request_metadata
from app.service.user import get_current_active_user
from app.data.user import User
from app.model.site_stats import SiteStatsPlanCountByType, YoudraFeedback
from app.service.site_stats import get_plan_count_by_type_svc, insert_youdra_feedback_svc

router = APIRouter()


@router.post("/site/plancountbytype", response_model=Optional[List[SiteStatsPlanCountByType]])
async def get_plan_count_by_type ( 
                               db: AsyncSession = Depends(get_db), 
                               rs = Depends(get_request_metadata)):
    try:
        return await get_plan_count_by_type_svc(db, rs)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/site/insertfeedback")
async def insert_youdra_feedback_api ( feedback: YoudraFeedback,
                               db: AsyncSession = Depends(get_db), 
                               current_user: User = Depends(get_current_active_user)):
    try:
        return await insert_youdra_feedback_svc( feedback, db, current_user)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
