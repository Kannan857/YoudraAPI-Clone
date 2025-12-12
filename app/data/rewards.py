from sqlalchemy import Column, String, Integer, Boolean, DateTime, Date, Text, ForeignKey, JSON, CheckConstraint,text, select, true, update
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from datetime import timezone
import structlog
from app.common.exception import GeneralDataException, IntegrityException

Base = declarative_base()


class BadgeDefinitionORM(Base):
    __tablename__ = "badge_definitions"

    badge_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    badge_name = Column(String(256), nullable=False, unique=True)
    badge_description = Column(Text)
    badge_icon_url = Column(String(512))
    badge_category = Column(String(128))
    badge_rarity = Column(String(32), default='common')
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    reward_rules = relationship("RewardRuleORM", back_populates="badge_definition")
    user_badges = relationship("UserBadgeORM", back_populates="badge_definition")


class RewardRuleORM(Base):
    __tablename__ = "reward_rules"

    rule_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_name = Column(String(256), nullable=False)
    rule_type = Column(String(64), nullable=False)
    trigger_condition = Column(JSON, nullable=False)
    points_reward = Column(Integer, default=0)
    badge_id = Column(UUID(as_uuid=True), ForeignKey("badge_definitions.badge_id"))
    max_occurrences = Column(Integer)
    cooldown_hours = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    badge_definition = relationship("BadgeDefinitionORM", back_populates="reward_rules")
    points_transactions = relationship("PointsTransactionORM", back_populates="reward_rule")
    user_badges = relationship("UserBadgeORM", back_populates="reward_rule")


class UserPointsORM(Base):
    __tablename__ = "user_points"

    user_id = Column(UUID(as_uuid=True), primary_key=True)
    total_points = Column(Integer, default=0)
    available_points = Column(Integer, default=0)
    lifetime_earned = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Constraints
    __table_args__ = (
        CheckConstraint('total_points >= 0', name='check_non_negative_total_points'),
        CheckConstraint('available_points >= 0', name='check_non_negative_available_points'),
    )

    # Relationships
    points_transactions = relationship("PointsTransactionORM", back_populates="user_points")


class PointsTransactionORM(Base):
    __tablename__ = "points_transactions"

    transaction_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("user_points.user_id"), nullable=False)
    rule_id = Column(UUID(as_uuid=True), ForeignKey("reward_rules.rule_id"))
    points_change = Column(Integer, nullable=False)
    transaction_type = Column(String(32), nullable=False)
    reference_entity_type = Column(String(64))
    reference_entity_id = Column(UUID(as_uuid=True))
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user_points = relationship("UserPointsORM", back_populates="points_transactions")
    reward_rule = relationship("RewardRuleORM", back_populates="points_transactions")


class UserBadgeORM(Base):
    __tablename__ = "user_badges"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    badge_id = Column(UUID(as_uuid=True), ForeignKey("badge_definitions.badge_id"), nullable=False)
    rule_id = Column(UUID(as_uuid=True), ForeignKey("reward_rules.rule_id"))
    earned_at = Column(DateTime(timezone=True), server_default=func.now())
    reference_entity_type = Column(String(64))
    reference_entity_id = Column(UUID(as_uuid=True))

    # Unique constraint to prevent duplicate badges
    __table_args__ = (
        CheckConstraint('user_id IS NOT NULL', name='check_user_id_not_null'),
        # Note: You might want to add a unique constraint on (user_id, badge_id) 
        # but this depends on whether users can earn the same badge multiple times
    )

    # Relationships
    badge_definition = relationship("BadgeDefinitionORM", back_populates="user_badges")
    reward_rule = relationship("RewardRuleORM", back_populates="user_badges")


class RewardProcessingQueueORM(Base):
    __tablename__ = "reward_processing_queue"

    queue_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    event_type = Column(String(64), nullable=False)
    event_data = Column(JSON, nullable=False)
    status = Column(String(32), default='pending')
    attempts = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    processed_at = Column(DateTime(timezone=True))
    error_message = Column(Text)


class UserStreakORM(Base):
    __tablename__ = "user_streaks"

    user_id = Column(UUID(as_uuid=True), primary_key=True)
    streak_type = Column(String(64), primary_key=True)
    current_streak = Column(Integer, default=0)
    longest_streak = Column(Integer, default=0)
    last_activity_date = Column(Date)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


from datetime import datetime, date
from typing import List, Optional, Dict, Any
from uuid import UUID
from sqlalchemy import and_, or_, func, desc, asc
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects.postgresql import insert

from app.model.rewards import (
    BadgeDefinition, BadgeDefinitionCreate,
    RewardRule, RewardRuleCreate,
    UserPoints, UserPointsCreate,
    PointsTransaction, PointsTransactionCreate,
    UserBadge, UserBadgeCreate, UserBadgeWithDetails,
    RewardProcessingQueue, RewardProcessingQueueCreate,
    UserStreak, UserStreakCreate, UserStreakUpdate,
    QueueStatus, TransactionType
)

# SQLAlchemy ORM Models (you'll need to create these based on your existing pattern)

logger = structlog.get_logger()

class RewardsDataLayer:
    
    def __init__(self, db_session: AsyncSession):
        self.db = db_session
    
    # Badge Definitions
    async def create_badge_definition(self, badge: BadgeDefinitionCreate) -> BadgeDefinition:
        try:
            db_badge = BadgeDefinitionORM(**badge.model_dump())
            self.db.add(db_badge)
            await self.db.commit()
            await self.db.refresh(db_badge)
            return BadgeDefinition.model_config(db_badge)
        except Exception as e:
            logger.error(f"Database error when updating executable plan: {str(e)}")
            raise GeneralDataException(
                "Unexpected error occured updating the executable plan",
                context={"detail" : f"Database error when updating executable plan: {str(e)}"}
            )
    


    async def get_badge_definitions(self, active_only: bool = True) -> List[BadgeDefinition]:
        try:
            stmt = select(BadgeDefinitionORM)
            if active_only:
                stmt = stmt.where(BadgeDefinitionORM.is_active == true())
            result = await self.db.execute(stmt)
            badges = result.scalars().all()
            return [BadgeDefinition.model_config(badge) for badge in badges]
        except Exception as e:
            logger.error(f"Database error when updating executable plan: {str(e)}")
            raise GeneralDataException(
                "Unexpected error occurred updating the executable plan",
                context={"detail": f"Database error when updating executable plan: {str(e)}"}
            )


    async def get_badge_definition_by_id(self, badge_id: UUID) -> Optional[BadgeDefinition]:
        try:
            stmt = select(BadgeDefinitionORM).where(BadgeDefinitionORM.badge_id == badge_id)
            result = await self.db.execute(stmt)
            badge = result.scalars().first()
            return BadgeDefinition.model_config(badge) if badge else None
        except Exception as e:
            logger.error(f"Database error when updating executable plan: {str(e)}")
            raise GeneralDataException(
                "Unexpected error occurred updating the executable plan",
                context={"detail": f"Database error when updating executable plan: {str(e)}"}
            )

    
    # Reward Rules
    async def create_reward_rule(self, rule: RewardRuleCreate) -> RewardRule:
        try:
            db_rule = RewardRuleORM(**rule.model_dump())
            self.db.add(db_rule)
            await self.db.commit()
            await self.db.refresh(db_rule)
            return RewardRule.model_config(db_rule)
        except Exception as e:
            logger.error(f"Database error when updating executable plan: {str(e)}")
            raise GeneralDataException(
                "Unexpected error occured updating the executable plan",
                context={"detail" : f"Database error when updating executable plan: {str(e)}"}
            )
    


    async def get_reward_rules(
        self, 
        rule_type: Optional[str] = None,
        active_only: bool = True
    ) -> List[RewardRule]:
        try:
            stmt = select(RewardRuleORM)
            # Build WHERE clauses
            if active_only:
                stmt = stmt.where(RewardRuleORM.is_active == True)
            if rule_type:
                stmt = stmt.where(RewardRuleORM.rule_type == rule_type)

            # Actually run the query
            result = await self.db.execute(stmt)
            rules = result.scalars().all()
            return [RewardRule.model_validate(rule) for rule in rules]
        except Exception as e:
            logger.error(f"Database error when retrieving reward rules: {str(e)}")
            raise GeneralDataException(
                "Database error when retrieving reward rules",
                context={"detail" : f"Database error when retrieving reward rules: {str(e)}"}
            )

    
    async def get_reward_rule_by_id(self, rule_id: UUID) -> Optional[RewardRule]:
            try:
                rule = self.db.query(RewardRuleORM).filter(
                    RewardRuleORM.rule_id == rule_id
                ).first()
                return RewardRule.model_validate(rule) if rule else None
            except Exception as e:
                logger.error(f"Database error when updating executable plan: {str(e)}")
                raise GeneralDataException(
                    "Unexpected error occured updating the executable plan",
                    context={"detail" : f"Database error when updating executable plan: {str(e)}"}
                )
    # User Points


    async def get_or_create_user_points(self, user_id: UUID) -> UserPoints:
        try:
            stmt = select(UserPointsORM).where(UserPointsORM.user_id == user_id)
            result = await self.db.execute(stmt)
            user_points = result.scalars().first()

            if not user_points:
                user_points = UserPointsORM(user_id=user_id)
                self.db.add(user_points)     # add() is sync, no await
                await self.db.commit()       # commit async
                await self.db.refresh(user_points)  # refresh async

            return UserPoints.model_validate(user_points)
        except Exception as e:
            logger.error(f"Database error when updating executable plan: {str(e)}")
            raise GeneralDataException(
                "Unexpected error occured updating the executable plan",
                context={"detail": f"Database error when updating executable plan: {str(e)}"}
            )



    async def update_user_points(
        self, 
        user_id: UUID, 
        points_change: int,
        transaction_type: TransactionType = TransactionType.EARNED
    ) -> UserPoints:
        try:
            user_points = await self.get_or_create_user_points(user_id)
            
            # Update points atomically
            if transaction_type == TransactionType.EARNED:
                user_points.total_points += points_change
                user_points.available_points += points_change
                user_points.lifetime_earned += points_change
            elif transaction_type == TransactionType.SPENT:
                user_points.available_points -= points_change
            elif transaction_type == TransactionType.ADJUSTED:
                user_points.total_points += points_change
                user_points.available_points += points_change
            
            user_points.updated_at = datetime.now(timezone.utc)
            
            # Update in database using async-compatible approach
            stmt = update(UserPointsORM).where(
                UserPointsORM.user_id == user_id
            ).values(
                total_points=user_points.total_points,
                available_points=user_points.available_points,
                lifetime_earned=user_points.lifetime_earned,
                updated_at=user_points.updated_at
            )
            
            await self.db.execute(stmt)
            await self.db.commit()
            return user_points
        except Exception as e:
            logger.error(f"Database error when updating user points: {str(e)}")
            raise GeneralDataException(
                "Unexpected error occurred updating user points",
                context={"detail": f"Database error when updating user points: {str(e)}"}
            )
    # Points Transactions
    async def create_points_transaction(
        self, 
        transaction: PointsTransactionCreate
    ) -> PointsTransaction:
        try:
            db_transaction = PointsTransactionORM(**transaction.model_dump())
            self.db.add(db_transaction)
            await self.db.commit()
            await self.db.refresh(db_transaction)
            return PointsTransaction.model_validate(db_transaction)
        except Exception as e:
            logger.error(f"Database error when updating executable plan: {str(e)}")
            raise GeneralDataException(
                "Unexpected error occured updating the executable plan",
                context={"detail" : f"Database error when updating executable plan: {str(e)}"}
            )


    async def get_user_transactions(
        self,
        user_id: UUID,
        limit: int = 50,
        offset: int = 0
    ) -> List[PointsTransaction]:
        try:
            stmt = (
                select(PointsTransactionORM)
                .where(PointsTransactionORM.user_id == user_id)
                .order_by(desc(PointsTransactionORM.created_at))
                .offset(offset)
                .limit(limit)
            )
            result = await self.db.execute(stmt)
            transactions = result.scalars().all()
            return [PointsTransaction.model_validate(t) for t in transactions]
        except Exception as e:
            logger.error(f"Database error when retrieving transaction points: {str(e)}")
            raise GeneralDataException(
                "Database error when retrieving transaction points",
                context={"detail": f"Database error when retrieving transaction points: {str(e)}"}
            )

    # User Badges
    async def award_badge(self, user_badge: UserBadgeCreate) -> Optional[UserBadge]:
        try:
            db_badge = UserBadgeORM(**user_badge.model_dump())
            self.db.add(db_badge)
            await self.db.commit()
            await self.db.refresh(db_badge)
            return UserBadge.model_validate(db_badge)
        except IntegrityError:
            # Badge already exists for user
            logger.error(f"Database error when retrieving transaction points: {str(e)}")
            raise GeneralDataException(
                "Database error when retrieving transaction points",
                context={"detail": f"Database error when retrieving transaction points: {str(e)}"}
            )
            return None
    


    async def get_user_badges(self, user_id: UUID) -> List[UserBadgeWithDetails]:
        try:
            stmt = (
                select(UserBadgeORM)
                .options(joinedload(UserBadgeORM.badge_definition))
                .where(UserBadgeORM.user_id == user_id)
                .order_by(desc(UserBadgeORM.earned_at))
            )
            result = await self.db.execute(stmt)
            badges = result.scalars().all()
            
            result_list = []
            for badge in badges:
                badge_data = UserBadgeWithDetails.model_validate(badge)
                if badge.badge_definition:
                    badge_data.badge_name = badge.badge_definition.badge_name
                    badge_data.badge_description = badge.badge_definition.badge_description
                    badge_data.badge_icon_url = badge.badge_definition.badge_icon_url
                    badge_data.badge_category = badge.badge_definition.badge_category
                    badge_data.badge_rarity = badge.badge_definition.badge_rarity
                result_list.append(badge_data)
                
            return result_list
        except Exception as e:
            logger.error(f"Database error when updating executable plan: {str(e)}")
            raise GeneralDataException(
                "Unexpected error occurred updating the executable plan",
                context={"detail" : f"Database error when updating executable plan: {str(e)}"}
            )

    


    async def has_user_badge(self, user_id: UUID, badge_id: UUID) -> bool:
        try:
            stmt = select(UserBadgeORM).where(
                and_(
                    UserBadgeORM.user_id == user_id,
                    UserBadgeORM.badge_id == badge_id
                )
            )
            result = await self.db.execute(stmt)
            badge = result.scalars().first()
            return badge is not None
        except Exception as e:
            logger.error(f"Database error when updating executable plan: {str(e)}")
            raise GeneralDataException(
                "Unexpected error occured updating the executable plan",
                context={"detail" : f"Database error when updating executable plan: {str(e)}"}
            )

    # Reward Processing Queue
    async def enqueue_reward_processing(
        self, 
        queue_item: RewardProcessingQueueCreate
    ) -> RewardProcessingQueue:
        try:
            db_item = RewardProcessingQueueORM(**queue_item.model_dump())
            self.db.add(db_item)
            await self.db.commit()
            await self.db.refresh(db_item)
            return RewardProcessingQueue.model_validate(db_item)
        except Exception as e:
            logger.error(f"Database error when updating executable plan: {str(e)}")
            raise GeneralDataException(
                "Unexpected error occured updating the executable plan",
                context={"detail" : f"Database error when updating executable plan: {str(e)}"}
            )
    async def get_pending_queue_items(self, limit: int = 100) -> List[RewardProcessingQueue]:
        try:
            items = self.db.query(RewardProcessingQueueORM).filter(
                RewardProcessingQueueORM.status == QueueStatus.PENDING
            ).order_by(asc(RewardProcessingQueueORM.created_at)).limit(limit).all()
            
            return [RewardProcessingQueue.model_validate(item) for item in items]
        except Exception as e:
            logger.error(f"Database error when updating executable plan: {str(e)}")
            raise GeneralDataException(
                "Unexpected error occured updating the executable plan",
                context={"detail" : f"Database error when updating executable plan: {str(e)}"}
            )
    async def update_queue_item_status(
        self, 
        queue_id: UUID, 
        status: QueueStatus,
        error_message: Optional[str] = None
    ):
        try:
            update_data = {
                "status": status,
                "processed_at": datetime.now(timezone.utc) if status != QueueStatus.PENDING else None
            }
            if error_message:
                update_data["error_message"] = error_message
            if status == QueueStatus.FAILED:
                # Increment attempts
                self.db.query(RewardProcessingQueueORM).filter(
                    RewardProcessingQueueORM.queue_id == queue_id
                ).update({"attempts": RewardProcessingQueueORM.attempts + 1})
            
            self.db.query(RewardProcessingQueueORM).filter(
                RewardProcessingQueueORM.queue_id == queue_id
            ).update(update_data)
            
            await self.db.commit()
        except Exception as e:
            logger.error(f"Database error when updating executable plan: {str(e)}")
            raise GeneralDataException(
                "Unexpected error occured updating the executable plan",
                context={"detail" : f"Database error when updating executable plan: {str(e)}"}
            )
    # User Streaks
    async def get_or_create_user_streak(
        self, 
        user_id: UUID, 
        streak_type: str
    ) -> UserStreak:
        try:
            streak = self.db.query(UserStreakORM).filter(
                and_(
                    UserStreakORM.user_id == user_id,
                    UserStreakORM.streak_type == streak_type
                )
            ).first()
            
            if not streak:
                streak = UserStreakORM(user_id=user_id, streak_type=streak_type)
                self.db.add(streak)
                await self.db.commit()
                await self.db.refresh(streak)
            
            return UserStreak.model_validate(streak)
        except Exception as e:
            logger.error(f"Database error when updating executable plan: {str(e)}")
            raise GeneralDataException(
                "Unexpected error occured updating the executable plan",
                context={"detail" : f"Database error when updating executable plan: {str(e)}"}
            )
        
    async def update_user_streak(
        self, 
        user_id: UUID, 
        streak_type: str, 
        update_data: UserStreakUpdate
    ) -> UserStreak:
        try:
            update_dict = {k: v for k, v in update_data.model_dump(exclude_unset=True).items()}
            update_dict["updated_at"] = datetime.now(timezone.utc)
            
            self.db.query(UserStreakORM).filter(
                and_(
                    UserStreakORM.user_id == user_id,
                    UserStreakORM.streak_type == streak_type
                )
            ).update(update_dict)
            
            await self.db.commit()
            return await self.get_or_create_user_streak(user_id, streak_type)
        except Exception as e:
            logger.error(f"Database error when updating executable plan: {str(e)}")
            raise GeneralDataException(
                "Unexpected error occured updating the executable plan",
                context={"detail" : f"Database error when updating executable plan: {str(e)}"}
            )
    async def get_user_streaks(self, user_id: UUID) -> List[UserStreak]:
        try:
            streaks = self.db.query(UserStreakORM).filter(
                UserStreakORM.user_id == user_id
            ).all()
            
            return [UserStreak.from_orm(streak) for streak in streaks]
        except Exception as e:
            logger.error(f"Database error when updating executable plan: {str(e)}")
            raise GeneralDataException(
                "Unexpected error occured updating the executable plan",
                context={"detail" : f"Database error when updating executable plan: {str(e)}"}
            )
    # Analytics and Performance Queries


    async def get_user_reward_summary(self, user_id: UUID) -> Dict[str, Any]:
        try:
            # Get user points
            user_points = await self.get_or_create_user_points(user_id)

            # Query badge counts by rarity with join
            stmt = (
                select(
                    BadgeDefinitionORM.badge_rarity,
                    func.count(UserBadgeORM.id).label("count")
                )
                .join(UserBadgeORM, UserBadgeORM.badge_id == BadgeDefinitionORM.badge_id)
                .where(UserBadgeORM.user_id == user_id)
                .group_by(BadgeDefinitionORM.badge_rarity)
            )
            result = await self.db.execute(stmt)
            badge_counts = result.all()

            # Get recent transactions asynchronously
            recent_transactions = await self.get_user_transactions(user_id, limit=10)

            # Get streaks asynchronously
            streaks = await self.get_user_streaks(user_id)

            return {
                "user_points": user_points,
                "badge_counts": {rarity: count for rarity, count in badge_counts},
                "recent_transactions": recent_transactions,
                "active_streaks": [s for s in streaks if s.current_streak > 0]
            }

        except Exception as e:
            logger.error(f"Database error when updating executable plan: {str(e)}")
            raise GeneralDataException(
                "Unexpected error occurred updating the executable plan",
                context={"detail": f"Database error when updating executable plan: {str(e)}"}
            )


    async def get_leaderboard(
        self, 
        limit: int = 10, 
        period: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        try:
            stmt = (
                select(
                    UserPointsORM.user_id,
                    UserPointsORM.total_points,
                    UserPointsORM.lifetime_earned
                )
                .order_by(desc(UserPointsORM.total_points))
                .limit(limit)
            )
            result = await self.db.execute(stmt)
            rows = result.all()

            return [
                {
                    "user_id": str(row.user_id),
                    "total_points": row.total_points,
                    "lifetime_earned": row.lifetime_earned
                }
                for row in rows
            ]

        except Exception as e:
            logger.error(f"Database error when updating executable plan: {str(e)}")
            raise GeneralDataException(
                "Unexpected error occurred updating the executable plan",
                context={"detail": f"Database error when updating executable plan: {str(e)}"}
            )

        
    async def get_user_plan_count(self, user_id: UUID) -> int:
        """Get total number of plans created by user"""
        try:
            query = text("""
                SELECT COUNT(*) as plan_count 
                FROM user_plan 
                WHERE 
                    user_id = :user_id and 
                    approved_by_user = 99
            """)
            result_proxy = await self.db.execute(query, {"user_id": user_id})
            result = result_proxy.fetchone()
            return result.plan_count if result else 0
    
        except Exception as e:
            logger.error(f"Database error adding subscriber: {str(e)}")
            raise GeneralDataException("Database error while adding subscriber")
        
    async def get_user_completion_count(self, user_id: UUID) -> int:
        try:
            """Get total number of completed plans by user"""
            query = text("""
                SELECT COUNT(*) as completion_count 
                FROM user_plan 
                WHERE user_id = :user_id AND plan_status = 100
            """)
            result = await self.db.execute(query, {"user_id": user_id}).fetchone()
            return result.completion_count if result else 0
        except Exception as e:
            logger.error(f"Database error when updating executable plan: {str(e)}")
            raise GeneralDataException(
                "Unexpected error occured updating the executable plan",
                context={"detail" : f"Database error when updating executable plan: {str(e)}"}
            )
        
    async def milestone_already_awarded(self, user_id: UUID, plan_id: UUID, milestone: int) -> bool:
        try:
            """Check if milestone reward already awarded for this plan"""
            query = text("""
                SELECT COUNT(*) as award_count 
                FROM user_rewards ur
                JOIN reward_rules rr ON ur.rule_id = rr.rule_id
                WHERE ur.user_id = :user_id 
                AND ur.plan_id = :plan_id 
                AND rr.rule_type = 'milestone'
                AND JSON_EXTRACT(rr.trigger_condition, '$.milestone') = :milestone
            """)
            result = await self.db.execute(query, {
                "user_id": user_id, 
                "plan_id": plan_id,
                "milestone": milestone
            }).fetchone()
            return (result.award_count if result else 0) > 0
        except Exception as e:
            logger.error(f"Database error when updating executable plan: {str(e)}")
            raise GeneralDataException(
                "Unexpected error occured updating the executable plan",
                context={"detail" : f"Database error when updating executable plan: {str(e)}"}
            )