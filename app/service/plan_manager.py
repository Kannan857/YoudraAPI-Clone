from app.data.plan_manager import ( 
                                   get_users_by_plan_id, 
                                   add_subscriber,
                                   update_subscriber_status,
                                   get_subscriber_db,
                                   get_subscription_db,
                                   get_fmp_by_count
                                   )
from app.data.user_plan import get_plan
from app.model.user_plan import UserPlanIdentifier
from app.model.plan_manager import FmpSubscriberCreate, FmpSubscriberOut, FmpSubscriberUpdate, FmpSubscriberGet, FmpCountSummary
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from fastapi import HTTPException
from sqlalchemy import update
from datetime import datetime
from app.data.dbinit import get_db
from fastapi import Request
from uuid import UUID
from app.model.progress_mgmt import ProgressUpdateCreate, ProgressUpdateOut
from app.data.progress_mgmt import create_progress_update, get_progress_by_user_entity
from app.data.user import User
from app.common.exception import IntegrityException, TimeZoneException, GeneralDataException
import structlog

logger = structlog.get_logger()

async def add_subscriber_svc(db: AsyncSession, fmp: FmpSubscriberCreate, current_user: User):
    try:
        #check if the plan is enabled for fmp
        filter_params = {}
        filter_params["plan_id"] = fmp.plan_id
        obj_plan = await get_plan(filter_params,db)
        
        if obj_plan[0].follow_flag == 0:
            logger.error(f"The plan {fmp.plan_id} cannot be followed.")
            raise GeneralDataException(
                f"The plan {fmp.plan_id} cannot be followed.",
                context = {"add_subscriber_svc" : f"The plan {fmp.plan_id} cannot be followed."}

            )
        ret = await add_subscriber(db, fmp)
        return ret
    except GeneralDataException as e:

        logger.error(f"Database error when inserting progress update: {str(e)}")
        raise GeneralDataException(
            "Data base error occured while inserting the progress update",
            context={"detail": "Database error occurred while inserting progress update"}
        )
    except Exception as e:
        logger.error(f"Unexpected error in insertng progress update: {str(e)}")
        raise GeneralDataException(
            "Unexpected error occured while inserting progress update",
            context={"detail" : "An unexpected error occurred while formatting the date in inserting progress update"}
        )

async def get_subscriber_svc(fmp: FmpSubscriberGet, db: AsyncSession, current_user: User ):
    try:
        #check if the plan is enabled for fmp
        filter_params = {}
        filter_params["user_id"] = current_user.user_id
        if fmp.plan_id is not None:
            filter_params["plan_id"] = fmp.plan_id
        
        hsh = await get_subscriber_db(db, filter_params)
        return hsh
    except GeneralDataException as e:

        logger.error(f"Database error when inserting progress update: {str(e)}")
        raise GeneralDataException(
            "Data base error occured while inserting the progress update",
            context={"detail": "Database error occurred while inserting progress update"}
        )
    except Exception as e:
        logger.error(f"Unexpected error in insertng progress update: {str(e)}")
        raise GeneralDataException(
            "Unexpected error occured while inserting progress update",
            context={"detail" : "An unexpected error occurred while formatting the date in inserting progress update"}
        )

async def get_subscription_svc(fmp: FmpSubscriberGet, db: AsyncSession, current_user: User):
    try:
        filter_params = {}
        filter_params["user_id"] = current_user.user_id
        if fmp.plan_id is not None:
            filter_params["plan_id"] = fmp.plan_id
        return await get_subscription_db(db, filter_params)

    except GeneralDataException as e:

        logger.error(f"Database error when inserting progress update: {str(e)}")
        raise GeneralDataException(
            "Data base error occured while inserting the progress update",
            context={"detail": "Database error occurred while inserting progress update"}
        )
    except Exception as e:
        logger.error(f"Unexpected error in insertng progress update: {str(e)}")
        raise GeneralDataException(
            "Unexpected error occured while inserting progress update",
            context={"detail" : "An unexpected error occurred while formatting the date in inserting progress update"}
        )

async def get_fmp_plans(db: AsyncSession, current_user: User, limit: int, offset: int):
    try:
        ret = await get_fmp_by_count(db, current_user.user_id, limit, offset)

        obj_fmp_count_summary = [
            FmpCountSummary.model_validate(row) for row in ret
        ]
        return obj_fmp_count_summary


    except GeneralDataException as e:

        logger.error(f"Database error when inserting progress update: {str(e)}")
        raise GeneralDataException(
            "Data base error occured while inserting the progress update",
            context={"detail": "Database error occurred while inserting progress update"}
        )
    except Exception as e:
        logger.error(f"Unexpected error in insertng progress update: {str(e)}")
        raise GeneralDataException(
            "Unexpected error occured while inserting progress update",
            context={"detail" : "An unexpected error occurred while formatting the date in inserting progress update"}
        )