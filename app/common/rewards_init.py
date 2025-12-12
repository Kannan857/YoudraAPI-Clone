from app.service.rewards import RewardsService
from app.data.rewards import RewardsDataLayer
from app.data.dbinit import get_db  # Assuming your existing DB dependency
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends, Request

async def get_rewards_service(db: AsyncSession = Depends(get_db)) -> RewardsService:
    """Dependency to get rewards service instance"""
    data_layer =  RewardsDataLayer(db)
    return RewardsService(data_layer)