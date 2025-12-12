from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
from app.data.dbinit import get_db
from typing import List
from app.service.progress_mgmt import create_progress_update_svc, get_progress_by_user_entity_svc, get_plan_dashboard, get_plan_dashboard_detail, get_user_dashboard
from uuid import UUID
from app.model.progress_mgmt import  ProgressUpdateCreate, ProgressUpdateOut, ProgressUpdateSummaryInput
from app.common.request_metadata import get_request_metadata
from app.service.user import get_current_active_user
from app.data.user import User
from app.common.rewards_init import get_rewards_service
from app.service.rewards import RewardsService


router = APIRouter()

@router.post("/progress/update", response_model=ProgressUpdateOut)
async def post_progress_update(pro_update: ProgressUpdateCreate, 
                               db: AsyncSession = Depends(get_db), 
                               rs = Depends(get_request_metadata),
                               current_user: User = Depends(get_current_active_user),
                               rewards_service: RewardsService = Depends(get_rewards_service)):
    try:
        return await create_progress_update_svc(db, pro_update,rs, current_user)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

'''
@router.get("/progress/{entity_id}", response_model=ProgressSummary)
async def get_progress( db: AsyncSession = Depends(get_db),current_user: User = Depends(get_current_active_user), entity_id: UUID = None):
    try:    
        return await get_progress_by_user_entity_svc(db, current_user, entity_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
'''

@router.post("/progress/performanceheader")
async def post_progress_update( update_summary: ProgressUpdateSummaryInput,
                               db: AsyncSession = Depends(get_db), 
                               current_user: User = Depends(get_current_active_user)):
    try:
        return await get_plan_dashboard(update_summary, current_user, db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/progress/performancedetail/{plan_id}")
async def post_progress_update( 
                               db: AsyncSession = Depends(get_db), 
                               current_user: User = Depends(get_current_active_user), plan_id: UUID = None):
    try:
        return await get_plan_dashboard_detail(plan_id, current_user, db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/progress/userscoreboard")
async def user_scoreboard( 
                               db: AsyncSession = Depends(get_db), 
                               current_user: User = Depends(get_current_active_user)):
    try:
        return await get_user_dashboard(current_user, db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

