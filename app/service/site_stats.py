from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update
from datetime import datetime
from fastapi import Request
from uuid import UUID
from app.data.site_stats import get_plan_count_by_type_db, insert_youdra_feedback
from app.data.user import User
from app.common.exception import IntegrityException, TimeZoneException, GeneralDataException
from app.model.site_stats import SiteStatsPlanCountByType, YoudraFeedback

import structlog

logger = structlog.get_logger()

async def get_plan_count_by_type_svc( db: AsyncSession , 
                               rs: Request):
    try:
        res = await get_plan_count_by_type_db(db)
        list_plan_count = []
        for i in range(len(res)):
            list_plan_count.append(SiteStatsPlanCountByType(plan_count=res[i].plan_type_count,
                                                            plan_category=res[i].plan_category)
            )
            
        return list_plan_count
    except IntegrityException as e:

        logger.error(f"IntegrityError when getting plan stats by type: {str(e)}")
        raise IntegrityException(
            f"IntegrityError when getting plan stats by type: {str(e)}",
            context = {"detail": f"IntegrityError when getting plan stats by type: {str(e)}"}
        )
    except GeneralDataException as e:

        logger.error(f"Database error when getting plan stats by type: {str(e)}")
        raise GeneralDataException(
            f"Database error when getting plan stats by type: {str(e)}",
            context={"detail": f"Database error when getting plan stats by type: {str(e)}"}
        )
    except TimeZoneException as e:
        logger.error(f"Time manipulation error getting plan stats by type: {str(e)}")
        raise GeneralDataException(
            "Time manipulation errorgetting plan stats by type: {str(e)}",
            context={"detail": "Time manipulation errorgetting plan stats by type: {str(e)}"}
        )
    except Exception as e:
        logger.error(f"Unexpected error getting plan stats by type: {str(e)}")
        raise GeneralDataException(
            f"Unexpected error getting plan stats by type: {str(e)}",
            context={"detail" : f"Unexpected error getting plan stats by type: {str(e)}"}
        )
    
async def insert_youdra_feedback_svc(feedback: YoudraFeedback, db: AsyncSession , 
                               current_user: User):
    try:
        feedback.user_id = current_user.user_id
        res = await insert_youdra_feedback(db, feedback)
        return res
    except IntegrityException as e:

        logger.error(f"IntegrityError when getting plan stats by type: {str(e)}")
        raise IntegrityException(
            f"IntegrityError when getting plan stats by type: {str(e)}",
            context = {"detail": f"IntegrityError when getting plan stats by type: {str(e)}"}
        )
    except GeneralDataException as e:

        logger.error(f"Database error when getting plan stats by type: {str(e)}")
        raise GeneralDataException(
            f"Database error when getting plan stats by type: {str(e)}",
            context={"detail": f"Database error when getting plan stats by type: {str(e)}"}
        )
    except TimeZoneException as e:
        logger.error(f"Time manipulation error getting plan stats by type: {str(e)}")
        raise GeneralDataException(
            "Time manipulation errorgetting plan stats by type: {str(e)}",
            context={"detail": "Time manipulation errorgetting plan stats by type: {str(e)}"}
        )
    except Exception as e:
        logger.error(f"Unexpected error getting plan stats by type: {str(e)}")
        raise GeneralDataException(
            f"Unexpected error getting plan stats by type: {str(e)}",
            context={"detail" : f"Unexpected error getting plan stats by type: {str(e)}"}
        )