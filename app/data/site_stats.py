from sqlalchemy import select, update, delete
from sqlalchemy import text, String, Column, UUID
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from app.model.site_stats import YoudraFeedback
from app.common.exception import DatabaseConnectionException, RecordNotFoundException, IntegrityException, MissingDataException, GeneralDataException
import structlog
from app.data.dbinit import Base

logger = structlog.get_logger()

class DBYoudraFeedback(Base):
    __tablename__ = "youdra_feedback"
    entity_id = Column(UUID(as_uuid=True), primary_key=True, server_default=str("gen_random_uuid()"))
    feedback_type = Column(String, nullable=False)
    feedback_text = Column(String, nullable=False)
    user_id = Column(UUID(as_uuid=True))

async def get_plan_count_by_type_db(db: AsyncSession):
    try:

        # Base SQL with DISTINCT
        sql = """
            SELECT DISTINCT 
                count(1) as plan_type_count,
                plan_category
            FROM user_plan
            GROUP BY
                plan_category
            ORDER by
                plan_type_count desc

        """
        params = {}


        # Execute raw SQL
        result = await db.execute(text(sql))
        res = result.mappings().all()
        # Convert raw rows to ORM objects
        return res
    except IntegrityError as e:

        logger.error(f"IntegrityError when selecting plan count by plan_type and approved_by_user: {str(e)}")
        raise IntegrityException(
            f"IntegrityError when selecting plan count by plan_type and approved_by_user: {str(e)}",
            context = {"detail": f"IntegrityError when selecting plan count by plan_type and approved_by_user: {str(e)}"}
        )
    except SQLAlchemyError as e:

        logger.error(f"Database error when selecting plan count by plan_type and approved_by_user: {str(e)}")
        raise GeneralDataException(
            f"Database error when selecting plan count by plan_type and approved_by_user: {str(e)}",
            context={"detail": f"Database error when selecting plan count by plan_type and approved_by_user: {str(e)}"}
        )
    except Exception as e:

        logger.error(f"Unexpected error when selecting plan count by plan_type and approved_by_user: {str(e)}")
        raise GeneralDataException(
            f"Unexpected error when selecting plan count by plan_type and approved_by_user: {str(e)}",
            context={"detail" : f"Unexpected error when selecting plan count by plan_type and approved_by_user: {str(e)}"}
        )


async def insert_youdra_feedback(db: AsyncSession, feedback: YoudraFeedback) -> DBYoudraFeedback:
    """
    Insert a new feedback entry into the youdra_feedback table.
    
    Args:
        db (AsyncSession): SQLAlchemy async session.
        feedback (YoudraFeedback): Pydantic model containing feedback data.
    
    Returns:
        DBYoudraFeedback: The inserted SQLAlchemy model instance.
    """
    try:
        new_feedback = DBYoudraFeedback(
            feedback_type=feedback.feedback_type,
            feedback_text=feedback.feedback_text,
            user_id = feedback.user_id
        )
        db.add(new_feedback)
        return new_feedback

    except SQLAlchemyError as e:
        logger.error(f"Database error inserting feedback: {str(e)}")
        raise GeneralDataException("Database error while inserting feedback")
