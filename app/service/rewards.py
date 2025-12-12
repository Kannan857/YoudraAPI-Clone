import asyncio
import logging
from datetime import datetime, date, timedelta, timezone
from typing import List, Optional, Dict, Any, Tuple
from uuid import UUID
from sqlalchemy.orm import Session

from app.model.rewards import (
    RewardEvent, MilestoneEvent, PlanCompletionEvent, PlanCreationEvent,
    RewardRule, UserPoints, UserBadge, BadgeDefinition,
    PointsTransactionCreate, UserBadgeCreate, RewardProcessingQueueCreate,
    UserStreakUpdate, RewardEarnedResponse, UserRewardsResponse,
    TransactionType, QueueStatus, RuleType
)
from app.data.rewards import RewardsDataLayer

logger = logging.getLogger(__name__)


class RewardsService:
    def __init__(self, data_layer: RewardsDataLayer):
        self.data_layer = data_layer
    
    async def process_reward_event(self, event: RewardEvent) -> RewardEarnedResponse:
        """
        Process a reward event and award points/badges accordingly
        """
        try:
            # Get applicable reward rules for this event
            rules = await self._get_applicable_rules(event)
            
            total_points_earned = 0
            badges_earned = []
            
            for rule in rules:
                # Check if user is eligible for this rule
                if await self._is_user_eligible_for_rule(event.user_id, rule, event):
                    # Award points
                    if rule.points_reward > 0:
                        await self._award_points(
                            event.user_id, 
                            rule.points_reward, 
                            rule.rule_id,
                            event
                        )
                        total_points_earned += rule.points_reward
                    
                    # Award badge if specified
                    if rule.badge_id:
                        badge = await self._award_badge(
                            event.user_id, 
                            rule.badge_id, 
                            rule.rule_id,
                            event
                        )
                        if badge:
                            badge_def = await self.data_layer.get_badge_definition_by_id(rule.badge_id)
                            if badge_def:
                                badges_earned.append(badge_def)
                    
                    logger.info(f"Awarded {rule.points_reward} points to user {event.user_id} for rule {rule.rule_name}")
            
            # Update user's total points
            updated_points = await self.data_layer.get_or_create_user_points(event.user_id)
            
            return RewardEarnedResponse(
                points_earned=total_points_earned,
                badges_earned=badges_earned,
                new_total_points=updated_points.total_points
            )
            
        except Exception as e:
            logger.error(f"Error processing reward event for user {event.user_id}: {str(e)}")
            raise
    
    async def process_milestone_progress(
        self, 
        user_id: UUID, 
        plan_id: UUID, 
        milestone_progress: Dict[str, int]
    ):
        """
        Process milestone progress updates and trigger rewards
        """
        events_to_process = []
        
        # Check each milestone (25, 50, 75, 100)
        for milestone_name, is_reached in milestone_progress.items():
            if is_reached == 1:  # Milestone just reached
                milestone_value = int(milestone_name.split('_')[1])  # Extract number from 'milestone_25'
                event = MilestoneEvent(
                    user_id=user_id,
                    plan_id=plan_id,
                    milestone=milestone_value
                )
                events_to_process.append(event)
        
        # Process all milestone events
        total_response = RewardEarnedResponse(
            points_earned=0,
            badges_earned=[],
            new_total_points=0
        )
        
        for event in events_to_process:
            response = await self.process_reward_event(event)
            total_response.points_earned += response.points_earned
            total_response.badges_earned.extend(response.badges_earned)
            total_response.new_total_points = response.new_total_points
        
        return total_response
    
    async def process_plan_completion(self, user_id: UUID, plan_id: UUID) -> RewardEarnedResponse:
        """
        Process plan completion and award rewards
        """
        event = PlanCompletionEvent(user_id=user_id, plan_id=plan_id)
        
        # Also check if this triggers any streak rewards
        await self._update_completion_streak(user_id)
        
        return await self.process_reward_event(event)
    
    async def process_plan_creation(self, user_id: UUID, plan_id: UUID) -> RewardEarnedResponse:
        """
        Process plan creation and award rewards
        """
        event = PlanCreationEvent(user_id=user_id, plan_id=plan_id)
        
        # Update activity streak
        await self._update_activity_streak(user_id)
        
        return await self.process_reward_event(event)
    
    async def get_user_rewards_overview(self, user_id: UUID) -> UserRewardsResponse:
        """
        Get comprehensive overview of user's rewards
        """
        user_points = await self.data_layer.get_or_create_user_points(user_id)
        badges = await self.data_layer.get_user_badges(user_id)
        recent_transactions = await self.data_layer.get_user_transactions(user_id, limit=20)
        streaks = await self.data_layer.get_user_streaks(user_id)
        
        return UserRewardsResponse(
            user_points=user_points,
            badges=badges,
            recent_transactions=recent_transactions,
            streaks=streaks
        )
    
    async def enqueue_reward_processing(self, event: RewardEvent):
        """
        Add reward event to processing queue for async processing
        """
        queue_item = RewardProcessingQueueCreate(
            user_id=event.user_id,
            event_type=event.event_type,
            event_data=event.event_data
        )
        return await self.data_layer.enqueue_reward_processing(queue_item)
    
    async def process_reward_queue(self, batch_size: int = 50):
        """
        Process pending reward events from queue
        """
        pending_items = await self.data_layer.get_pending_queue_items(limit=batch_size)
        
        for item in pending_items:
            try:
                # Reconstruct event from queue item
                event = RewardEvent(
                    user_id=item.user_id,
                    event_type=item.event_type,
                    event_data=item.event_data
                )
                
                # Process the event
                await self.process_reward_event(event)
                
                # Mark as processed
                await self.data_layer.update_queue_item_status(
                    item.queue_id, 
                    QueueStatus.PROCESSED
                )
                
                logger.info(f"Processed queue item {item.queue_id} for user {item.user_id}")
                
            except Exception as e:
                logger.error(f"Failed to process queue item {item.queue_id}: {str(e)}")
                
                # Mark as failed and increment attempts
                await self.data_layer.update_queue_item_status(
                    item.queue_id, 
                    QueueStatus.FAILED,
                    error_message=str(e)
                )
    
    # Private helper methods
    async def _get_applicable_rules(self, event: RewardEvent) -> List[RewardRule]:
        """
        Get reward rules that apply to this event
        """
        # Get rules by type
        if event.event_type == "milestone_reached":
            rules = await self.data_layer.get_reward_rules(rule_type=RuleType.MILESTONE)
        elif event.event_type == "plan_completed":
            rules = await self.data_layer.get_reward_rules(rule_type=RuleType.COMPLETION)
        elif event.event_type == "plan_created":
            rules = await self.data_layer.get_reward_rules(rule_type=RuleType.ACTIVITY)
        else:
            rules = await self.data_layer.get_reward_rules()
        
        # Filter rules based on trigger conditions
        applicable_rules = []
        for rule in rules:
            if await self._rule_matches_event(rule, event):
                applicable_rules.append(rule)
        
        return applicable_rules
    
    async def _rule_matches_event(self, rule: RewardRule, event: RewardEvent) -> bool:
        """
        Enhanced rule matching for specific reward conditions
        """
        trigger = rule.trigger_condition
        
        # Basic event type matching
        if trigger.get("event") != event.event_type:
            return False
        
        # First plan creation
        if (trigger.get("event") == "plan_created" and 
            trigger.get("is_first") == True):
            return event.event_data.get("is_first") == True
        
        # Fifth plan milestone
        if (trigger.get("event") == "plan_created" and 
            trigger.get("total_count") == 5):
            return event.event_data.get("total_count") == 5
        
        # Milestone matching
        if event.event_type == "milestone_reached":
            required_milestone = trigger.get("milestone")
            actual_milestone = event.event_data.get("milestone")
            if required_milestone and required_milestone != actual_milestone:
                return False
        
        # First completion
        if (trigger.get("event") == "plan_completed" and 
            trigger.get("is_first") == True):
            return event.event_data.get("is_first") == True
        
        # Third/Fifth completion milestones
        if (trigger.get("event") == "plan_completed" and 
            trigger.get("total_completed")):
            required_count = trigger.get("total_completed")
            actual_count = event.event_data.get("total_completed")
            if required_count != actual_count:
                return False
        
        return True
    
    async def _is_user_eligible_for_rule(
        self, 
        user_id: UUID, 
        rule: RewardRule, 
        event: RewardEvent
    ) -> bool:
        """
        Check if user is eligible for a specific rule
        """
        # Check cooldown
        if rule.cooldown_hours > 0:
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=rule.cooldown_hours)
            recent_transactions = await self.data_layer.get_user_transactions(
                user_id, limit=100
            )
            
            for transaction in recent_transactions:
                if (transaction.rule_id == rule.rule_id and 
                    transaction.created_at > cutoff_time):
                    return False
        
        # Check max occurrences
        if rule.max_occurrences:
            user_transactions = await self.data_layer.get_user_transactions(
                user_id, limit=1000
            )
            rule_usage_count = sum(
                1 for t in user_transactions 
                if t.rule_id == rule.rule_id
            )
            if rule_usage_count >= rule.max_occurrences:
                return False
        
        # Check if badge already earned (for badge-awarding rules)
        if rule.badge_id:
            has_badge = await self.data_layer.has_user_badge(user_id, rule.badge_id)
            if has_badge:
                return False
        
        return True
    
    async def _award_points(
        self, 
        user_id: UUID, 
        points: int, 
        rule_id: UUID,
        event: RewardEvent
    ):
        """
        Award points to user and create transaction record
        """
        # Update user points
        await self.data_layer.update_user_points(
            user_id, 
            points, 
            TransactionType.EARNED
        )
        
        # Create transaction record
        transaction = PointsTransactionCreate(
            user_id=user_id,
            rule_id=rule_id,
            points_change=points,
            transaction_type=TransactionType.EARNED,
            reference_entity_type=event.event_data.get("plan_id") and "plan" or None,
            reference_entity_id=event.event_data.get("plan_id") and UUID(event.event_data["plan_id"]) or None,
            description=f"Earned for {event.event_type}"
        )
        
        await self.data_layer.create_points_transaction(transaction)
    
    async def _award_badge(
        self, 
        user_id: UUID, 
        badge_id: UUID, 
        rule_id: UUID,
        event: RewardEvent
    ) -> Optional[UserBadge]:
        """
        Award badge to user
        """
        user_badge = UserBadgeCreate(
            user_id=user_id,
            badge_id=badge_id,
            rule_id=rule_id,
            reference_entity_type=event.event_data.get("plan_id") and "plan" or None,
            reference_entity_id=event.event_data.get("plan_id") and UUID(event.event_data["plan_id"]) or None
        )
        
        return await self.data_layer.award_badge(user_badge)
    
    async def _update_activity_streak(self, user_id: UUID):
        """
        Update user's daily activity streak
        """
        today = date.today()
        streak = await self.data_layer.get_or_create_user_streak(user_id, "daily_activity")
        
        if streak.last_activity_date == today:
            # Already recorded activity today
            return streak
        elif streak.last_activity_date == today - timedelta(days=1):
            # Consecutive day - increment streak
            new_streak = streak.current_streak + 1
            longest_streak = max(streak.longest_streak, new_streak)
            
            update = UserStreakUpdate(
                current_streak=new_streak,
                longest_streak=longest_streak,
                last_activity_date=today
            )
        else:
            # Streak broken - reset
            update = UserStreakUpdate(
                current_streak=1,
                longest_streak=streak.longest_streak,
                last_activity_date=today
            )
        
        return await self.data_layer.update_user_streak(
            user_id, "daily_activity", update
        )
    
    async def _update_completion_streak(self, user_id: UUID):
        """
        Update user's plan completion streak
        """
        today = date.today()
        streak = await self.data_layer.get_or_create_user_streak(user_id, "plan_completion")
        
        # For completion streaks, we might want weekly tracking
        # This is simplified - you might want more complex logic
        new_streak = streak.current_streak + 1
        longest_streak = max(streak.longest_streak, new_streak)
        
        update = UserStreakUpdate(
            current_streak=new_streak,
            longest_streak=longest_streak,
            last_activity_date=today
        )
        
        return await self.data_layer.update_user_streak(
            user_id, "plan_completion", update
        )
    
    async def get_leaderboard(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get points leaderboard
        """
        return await self.data_layer.get_leaderboard(limit=limit)
    
    async def get_user_rank(self, user_id: UUID) -> Dict[str, Any]:
        """
        Get user's rank in the leaderboard
        """
        user_points = await self.data_layer.get_or_create_user_points(user_id)
        
        # This is a simplified version - in production you might want to cache rankings
        leaderboard = await self.data_layer.get_leaderboard(limit=1000)
        
        user_rank = None
        for i, entry in enumerate(leaderboard):
            if entry["user_id"] == str(user_id):
                user_rank = i + 1
                break
        
        return {
            "user_id": str(user_id),
            "total_points": user_points.total_points,
            "rank": user_rank or len(leaderboard) + 1,
            "total_users": len(leaderboard)
        }
    async def process_plan_creation_rewards(self, user_id: UUID, plan_id: UUID) -> RewardEarnedResponse:
        """
        Specific logic for plan creation rewards
        """
        total_response = RewardEarnedResponse(points_earned=0, badges_earned=[], new_total_points=0)
        
        # Check if this is the first plan
        plan_count = await self._get_user_plan_count(user_id)
        is_first = (plan_count == 1)
        
        # Create appropriate events
        if is_first:
            # First plan creation event
            event = PlanCreationEvent(
                user_id=user_id,
                plan_id=plan_id,
                event_data={"is_first": True, "total_count": plan_count}
            )
        else:
            # Regular plan creation event
            event = PlanCreationEvent(
                user_id=user_id,
                plan_id=plan_id,
                event_data={"total_count": plan_count}
            )
        
        # Process the event
        response = await self.process_reward_event(event)
        total_response.points_earned += response.points_earned
        total_response.badges_earned.extend(response.badges_earned)
        total_response.new_total_points = response.new_total_points
        
        # Check for fifth plan milestone
        if plan_count == 5:
            milestone_event = PlanCreationEvent(
                user_id=user_id,
                plan_id=plan_id,
                event_data={"total_count": 5, "milestone": "fifth_plan"}
            )
            milestone_response = await self.process_reward_event(milestone_event)
            total_response.points_earned += milestone_response.points_earned
            total_response.badges_earned.extend(milestone_response.badges_earned)
            total_response.new_total_points = milestone_response.new_total_points
        
        return total_response
    
    async def process_plan_completion_rewards(self, user_id: UUID, plan_id: UUID) -> RewardEarnedResponse:
        """
        Specific logic for plan completion rewards
        """
        total_response = RewardEarnedResponse(points_earned=0, badges_earned=[], new_total_points=0)
        
        # Check completion count
        completion_count = await self._get_user_completion_count(user_id)
        is_first = (completion_count == 1)
        
        # Create appropriate events
        if is_first:
            # First completion
            event = PlanCompletionEvent(
                user_id=user_id,
                plan_id=plan_id,
                event_data={"is_first": True, "total_completed": completion_count}
            )
        else:
            # Regular completion
            event = PlanCompletionEvent(
                user_id=user_id,
                plan_id=plan_id,
                event_data={"total_completed": completion_count}
            )
        
        # Process the event
        response = await self.process_reward_event(event)
        total_response.points_earned += response.points_earned
        total_response.badges_earned.extend(response.badges_earned)
        total_response.new_total_points = response.new_total_points
        
        # Check for completion milestones
        if completion_count == 3:
            milestone_event = PlanCompletionEvent(
                user_id=user_id,
                plan_id=plan_id,
                event_data={"total_completed": 3, "milestone": "third_completion"}
            )
            milestone_response = await self.process_reward_event(milestone_event)
            total_response.points_earned += milestone_response.points_earned
            total_response.badges_earned.extend(milestone_response.badges_earned)
            total_response.new_total_points = milestone_response.new_total_points
        
        elif completion_count == 5:
            milestone_event = PlanCompletionEvent(
                user_id=user_id,
                plan_id=plan_id,
                event_data={"total_completed": 5, "milestone": "fifth_completion"}
            )
            milestone_response = await self.process_reward_event(milestone_event)
            total_response.points_earned += milestone_response.points_earned
            total_response.badges_earned.extend(milestone_response.badges_earned)
            total_response.new_total_points = milestone_response.new_total_points
        
        return total_response
    
    async def process_milestone_rewards(self, user_id: UUID, plan_id: UUID, milestone: int) -> RewardEarnedResponse:
        """
        Process specific milestone rewards (25%, 50%, 75%)
        """
        if milestone not in [25, 50, 75]:
            return RewardEarnedResponse(points_earned=0, badges_earned=[], new_total_points=0)
        
        # Check if already awarded for this plan
        if await self._milestone_already_awarded(user_id, plan_id, milestone):
            return RewardEarnedResponse(points_earned=0, badges_earned=[], new_total_points=0)
        
        # Create milestone event
        event = MilestoneEvent(
            user_id=user_id,
            plan_id=plan_id,
            milestone=milestone,
            event_data={"milestone": milestone, "plan_id": str(plan_id)}
        )
        
        return await self.process_reward_event(event)
    
    async def _get_user_plan_count(self, user_id: UUID) -> int:
        """Get total number of plans created by user"""
        # Assuming you have a data layer method for this
        # If not, you'll need to implement it in your RewardsDataLayer
        return await self.data_layer.get_user_plan_count(user_id)
    
    async def _get_user_completion_count(self, user_id: UUID) -> int:
        """Get total number of completed plans by user"""
        return await self.data_layer.get_user_completion_count(user_id)
    
    async def _milestone_already_awarded(self, user_id: UUID, plan_id: UUID, milestone: int) -> bool:
        """Check if milestone reward already awarded for this specific plan"""
        # This would need to be implemented in your data layer
        return await self.data_layer.milestone_already_awarded(user_id, plan_id, milestone)