from datetime import datetime, date, timezone
from typing import Optional, Dict, Any, List, Literal
from uuid import UUID
from pydantic import BaseModel, Field
from enum import Enum


class BadgeRarity(str, Enum):
    COMMON = "common"
    RARE = "rare"
    EPIC = "epic"
    LEGENDARY = "legendary"


class BadgeCategory(str, Enum):
    MILESTONE = "milestone"
    STREAK = "streak"
    COMPLETION = "completion"
    ACTIVITY = "activity"
    SPECIAL = "special"


class RuleType(str, Enum):
    MILESTONE = "milestone"
    COMPLETION = "completion"
    STREAK = "streak"
    ACTIVITY = "activity"


class TransactionType(str, Enum):
    EARNED = "earned"
    SPENT = "spent"
    ADJUSTED = "adjusted"


class QueueStatus(str, Enum):
    PENDING = "pending"
    PROCESSED = "processed"
    FAILED = "failed"


# Badge Definition Models
class BadgeDefinitionBase(BaseModel):
    badge_name: str = Field(..., max_length=256)
    badge_description: Optional[str] = None
    badge_icon_url: Optional[str] = Field(None, max_length=512)
    badge_category: BadgeCategory
    badge_rarity: BadgeRarity = BadgeRarity.COMMON
    is_active: bool = True


class BadgeDefinitionCreate(BadgeDefinitionBase):
    pass


class BadgeDefinition(BadgeDefinitionBase):
    badge_id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Reward Rules Models
class RewardRuleBase(BaseModel):
    rule_name: str = Field(..., max_length=256)
    rule_type: RuleType
    trigger_condition: Dict[str, Any]
    points_reward: int = 0
    badge_id: Optional[UUID] = None
    max_occurrences: Optional[int] = None
    cooldown_hours: int = 0
    is_active: bool = True


class RewardRuleCreate(RewardRuleBase):
    pass


class RewardRule(RewardRuleBase):
    rule_id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# User Points Models
class UserPointsBase(BaseModel):
    total_points: int = 0
    available_points: int = 0
    lifetime_earned: int = 0


class UserPointsCreate(UserPointsBase):
    user_id: UUID


class UserPoints(UserPointsBase):
    user_id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Points Transaction Models
class PointsTransactionBase(BaseModel):
    points_change: int
    transaction_type: TransactionType
    reference_entity_type: Optional[str] = Field(None, max_length=64)
    reference_entity_id: Optional[UUID] = None
    description: Optional[str] = None


class PointsTransactionCreate(PointsTransactionBase):
    user_id: UUID
    rule_id: Optional[UUID] = None


class PointsTransaction(PointsTransactionBase):
    transaction_id: UUID
    user_id: UUID
    rule_id: Optional[UUID] = None
    created_at: datetime

    class Config:
        from_attributes = True


# User Badge Models
class UserBadgeBase(BaseModel):
    reference_entity_type: Optional[str] = Field(None, max_length=64)
    reference_entity_id: Optional[UUID] = None


class UserBadgeCreate(UserBadgeBase):
    user_id: UUID
    badge_id: UUID
    rule_id: Optional[UUID] = None


class UserBadge(UserBadgeBase):
    id: UUID
    user_id: UUID
    badge_id: UUID
    rule_id: Optional[UUID] = None
    earned_at: datetime
    
    class Config:
        from_attributes = True


class UserBadgeWithDetails(UserBadge):
    badge_name: str
    badge_description: Optional[str]
    badge_icon_url: Optional[str]
    badge_category: BadgeCategory
    badge_rarity: BadgeRarity


# Reward Processing Queue Models
class RewardProcessingQueueBase(BaseModel):
    event_type: str = Field(..., max_length=64)
    event_data: Dict[str, Any]


class RewardProcessingQueueCreate(RewardProcessingQueueBase):
    user_id: UUID


class RewardProcessingQueue(RewardProcessingQueueBase):
    queue_id: UUID
    user_id: UUID
    status: QueueStatus = QueueStatus.PENDING
    attempts: int = 0
    created_at: datetime
    processed_at: Optional[datetime] = None
    error_message: Optional[str] = None

    class Config:
        from_attributes = True


# User Streaks Models
class UserStreakBase(BaseModel):
    current_streak: int = 0
    longest_streak: int = 0
    last_activity_date: Optional[date] = None


class UserStreakCreate(UserStreakBase):
    user_id: UUID
    streak_type: str = Field(..., max_length=64)


class UserStreakUpdate(BaseModel):
    current_streak: Optional[int] = None
    longest_streak: Optional[int] = None
    last_activity_date: Optional[date] = None


class UserStreak(UserStreakBase):
    user_id: UUID
    streak_type: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Response Models
class UserRewardsResponse(BaseModel):
    user_points: UserPoints
    badges: List[UserBadgeWithDetails]
    recent_transactions: List[PointsTransaction]
    streaks: List[UserStreak]


class RewardEarnedResponse(BaseModel):
    points_earned: int
    badges_earned: List[BadgeDefinition]
    new_total_points: int


# Event Models for Reward Processing
class RewardEvent(BaseModel):
    user_id: UUID
    event_type: str
    event_data: Dict[str, Any]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MilestoneEvent(RewardEvent):
    event_type: Literal["milestone_reached"] = "milestone_reached"
    
    def __init__(self, user_id: UUID, plan_id: UUID, milestone: int, **kwargs):
        super().__init__(
            user_id=user_id,
            event_data={
                "plan_id": str(plan_id),
                "milestone": milestone
            },
            **kwargs
        )


class PlanCompletionEvent(RewardEvent):
    event_type: Literal["plan_completed"] = "plan_completed"
    
    def __init__(self, user_id: UUID, plan_id: UUID, **kwargs):
        super().__init__(
            user_id=user_id,
            event_data={
                "plan_id": str(plan_id)
            },
            **kwargs
        )


class PlanCreationEvent(RewardEvent):
    event_type: Literal["plan_created"] = "plan_created"
    
    def __init__(self, user_id: UUID, plan_id: UUID, **kwargs):
        super().__init__(
            user_id=user_id,
            plan_id=plan_id,
            **kwargs
        )
