from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from typing import List, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.model.rewards import (
    UserRewardsResponse, RewardEarnedResponse, BadgeDefinition,
    RewardRule, RewardRuleCreate, BadgeDefinitionCreate,
    RewardEvent, MilestoneEvent, PlanCompletionEvent, PlanCreationEvent
)
from app.service.rewards import RewardsService
from app.data.rewards import RewardsDataLayer
from app.data.dbinit import get_db  # Assuming your existing DB dependency
from app.common.rewards_init import get_rewards_service

# Create the router
router = APIRouter()





@router.get("/user/{user_id}", response_model=UserRewardsResponse)
async def get_user_rewards(
    user_id: UUID,
    rewards_service: RewardsService = Depends(get_rewards_service)
):
    """Get comprehensive overview of user's rewards"""
    try:
        return await rewards_service.get_user_rewards_overview(user_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving user rewards: {str(e)}"
        )


@router.post("/process/milestone", response_model=RewardEarnedResponse)
async def process_milestone_reward(
    user_id: UUID,
    plan_id: UUID,
    milestone: int,
    background_tasks: BackgroundTasks,
    rewards_service: RewardsService = Depends(get_rewards_service)
):
    """Process milestone achievement and award rewards"""
    try:
        # Create milestone event
        event = MilestoneEvent(user_id=user_id, plan_id=plan_id, milestone=milestone)
        
        # Process immediately for user experience
        response = await rewards_service.process_reward_event(event)
        
        # Also add to background queue for audit/retry purposes
        background_tasks.add_task(
            rewards_service.enqueue_reward_processing, event
        )
        
        return response
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing milestone reward: {str(e)}"
        )


@router.post("/process/completion", response_model=RewardEarnedResponse)
async def process_completion_reward(
    user_id: UUID,
    plan_id: UUID,
    background_tasks: BackgroundTasks,
    rewards_service: RewardsService = Depends(get_rewards_service)
):
    """Process plan completion and award rewards"""
    try:
        response = await rewards_service.process_plan_completion(user_id, plan_id)
        
        # Add to background queue
        event = PlanCompletionEvent(user_id=user_id, plan_id=plan_id)
        background_tasks.add_task(
            rewards_service.enqueue_reward_processing, event
        )
        
        return response
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing completion reward: {str(e)}"
        )


@router.post("/process/creation", response_model=RewardEarnedResponse)
async def process_creation_reward(
    user_id: UUID,
    plan_id: UUID,
    background_tasks: BackgroundTasks,
    rewards_service: RewardsService = Depends(get_rewards_service)
):
    """Process plan creation and award rewards"""
    try:
        response = await rewards_service.process_plan_creation(user_id, plan_id)
        
        # Add to background queue
        event = PlanCreationEvent(user_id=user_id, plan_id=plan_id)
        background_tasks.add_task(
            rewards_service.enqueue_reward_processing, event
        )
        
        return response
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing creation reward: {str(e)}"
        )


@router.get("/leaderboard")
async def get_leaderboard(
    limit: int = 10,
    rewards_service: RewardsService = Depends(get_rewards_service)
):
    """Get points leaderboard"""
    try:
        return await rewards_service.get_leaderboard(limit=limit)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving leaderboard: {str(e)}"
        )


@router.get("/user/{user_id}/rank")
async def get_user_rank(
    user_id: UUID,
    rewards_service: RewardsService = Depends(get_rewards_service)
):
    """Get user's rank in the leaderboard"""
    try:
        return await rewards_service.get_user_rank(user_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving user rank: {str(e)}"
        )


# Admin endpoints for managing badges and rules
@router.get("/badges", response_model=List[BadgeDefinition])
async def get_badges(
    active_only: bool = True,
    rewards_service: RewardsService = Depends(get_rewards_service)
):
    """Get all badge definitions"""
    try:
        return await rewards_service.data_layer.get_badge_definitions(active_only=active_only)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving badges: {str(e)}"
        )


@router.post("/badges", response_model=BadgeDefinition)
async def create_badge(
    badge: BadgeDefinitionCreate,
    rewards_service: RewardsService = Depends(get_rewards_service)
):
    """Create a new badge definition"""
    try:
        return await rewards_service.data_layer.create_badge_definition(badge)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating badge: {str(e)}"
        )


@router.get("/rules", response_model=List[RewardRule])
async def get_reward_rules(
    rule_type: Optional[str] = None,
    active_only: bool = True,
    rewards_service: RewardsService = Depends(get_rewards_service)
):
    """Get all reward rules"""
    try:
        return await rewards_service.data_layer.get_reward_rules(
            rule_type=rule_type, 
            active_only=active_only
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving reward rules: {str(e)}"
        )


@router.post("/rules", response_model=RewardRule)
async def create_reward_rule(
    rule: RewardRuleCreate,
    rewards_service: RewardsService = Depends(get_rewards_service)
):
    """Create a new reward rule"""
    try:
        return await rewards_service.data_layer.create_reward_rule(rule)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating reward rule: {str(e)}"
        )


# Background task endpoint for processing queue
@router.post("/admin/process-queue")
async def process_reward_queue(
    background_tasks: BackgroundTasks,
    batch_size: int = 50,
    rewards_service: RewardsService = Depends(get_rewards_service)
):
    """Process pending reward events from queue (admin endpoint)"""
    background_tasks.add_task(
        rewards_service.process_reward_queue, batch_size
    )
    return {"message": "Queue processing started"}


# Integration helper for your existing plan endpoints
class RewardsIntegration:
    """
    Helper class to integrate rewards into your existing plan endpoints
    """
    
    def __init__(self, rewards_service: RewardsService):
        self.rewards_service = rewards_service
    
    async def handle_plan_creation(self, user_id: UUID, plan_id: UUID) -> RewardEarnedResponse:
        """Call this when a plan is created"""
        return await self.rewards_service.process_plan_creation(user_id, plan_id)
    
    async def handle_milestone_update(
        self, 
        user_id: UUID, 
        plan_id: UUID, 
        milestone_progress: dict
    ) -> RewardEarnedResponse:
        """
        Call this when milestone progress is updated
        milestone_progress should be like: {"milestone_25": 1, "milestone_50": 0, ...}
        """
        return await self.rewards_service.process_milestone_progress(
            user_id, plan_id, milestone_progress
        )
    
    async def handle_plan_completion(self, user_id: UUID, plan_id: UUID) -> RewardEarnedResponse:
        """Call this when a plan is completed (milestone_100 = 1)"""
        return await self.rewards_service.process_plan_completion(user_id, plan_id)


# Example of how to integrate into your existing endpoints:
"""
# In your existing plan endpoints, you would do something like:

@app.post("/plans")
async def create_plan(
    plan_data: PlanCreate,
    db: Session = Depends(get_db),
    rewards_service: RewardsService = Depends(get_rewards_service)
):
    # Your existing plan creation logic
    new_plan = create_plan_in_db(plan_data, db)
    
    # Award rewards for plan creation
    rewards_integration = RewardsIntegration(rewards_service)
    reward_response = await rewards_integration.handle_plan_creation(
        plan_data.user_id, new_plan.plan_id
    )
    
    # Return plan data along with rewards earned
    return {
        "plan": new_plan,
        "rewards_earned": reward_response
    }

@app.put("/plans/{plan_id}/progress")
async def update_progress(
    plan_id: UUID,
    progress_data: ProgressUpdate,
    db: Session = Depends(get_db),
    rewards_service: RewardsService = Depends(get_rewards_service)
):
    # Your existing progress update logic
    updated_progress = update_progress_in_db(plan_id, progress_data, db)
    
    # Check for milestone rewards
    milestone_progress = {
        "milestone_25": updated_progress.milestone_25,
        "milestone_50": updated_progress.milestone_50,
        "milestone_75": updated_progress.milestone_75,
        "milestone_100": updated_progress.milestone_100
    }
    
    rewards_integration = RewardsIntegration(rewards_service)
    reward_response = await rewards_integration.handle_milestone_update(
        progress_data.user_id, plan_id, milestone_progress
    )
    
    # Check for completion
    if updated_progress.milestone_100 == 1:
        completion_rewards = await rewards_integration.handle_plan_completion(
            progress_data.user_id, plan_id
        )
        # Combine rewards
        reward_response.points_earned += completion_rewards.points_earned
        reward_response.badges_earned.extend(completion_rewards.badges_earned)
    
    return {
        "progress": updated_progress,
        "rewards_earned": reward_response
    }

    # Instead of generic process_reward_event(), use specific methods:
reward_response = await rewards_service.process_plan_creation_rewards(user_id, plan_id)
milestone_response = await rewards_service.process_milestone_rewards(user_id, plan_id, 25)
completion_response = await rewards_service.process_plan_completion_rewards(user_id, plan_id)
"""