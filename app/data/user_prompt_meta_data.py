from app.model.user import UserCreate, UserUpdate
from app.model.user_prompt_meta_data import PromptMetaData
from sqlalchemy import select, update, delete
from sqlalchemy import Integer, String, Boolean, Column, Table, DateTime, UUID, Text
from sqlalchemy.sql import func
from typing import List, Optional, Dict, Any, Union
from app.data.dbinit import Base, get_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError, MultipleResultsFound, NoResultFound, IntegrityError
from fastapi import Depends
import structlog

from app.common.exception import DatabaseConnectionException, RecordNotFoundException, IntegrityException, MissingDataException, GeneralDataException


logger = structlog.get_logger()

class PromptMetaData(Base):
    __tablename__ = "prompt_site_criteria"
    id = Column(Integer, primary_key=True, index=True)
    prompt_type = Column(String,  nullable=False)
    prompt_detail = Column(Text, nullable=False)
    prompt_detail_gemini = Column(Text, nullable=True)
    is_active = Column(Boolean, default=False)
    prompt_version = Column(String, nullable=False)
    inserted_date = Column(DateTime(timezone=True), server_default=func.now())


async def get_prompt_metadata(
    filter_params: Optional[Dict[str, Any]], db: AsyncSession
) -> PromptMetaData:
    """Get multiple users with optional filtering"""
    try:
        #query = db.query(PromptMetaData)
        stmt = select(PromptMetaData)
        print ("After the print statement")
        if filter_params:
            if filter_params.get("is_active") is not None:
                stmt = stmt.where(PromptMetaData.is_active == filter_params["is_active"])
            if filter_params.get("prompt_type"):
                stmt = stmt.where(PromptMetaData.prompt_type == filter_params["prompt_type"])
            '''
            if filter_params.get("prompt_type"):
                prompt_types = (
                    filter_params["prompt_type"] 
                    if isinstance(filter_params["prompt_type"], list)
                    else [filter_params["prompt_type"]]
                )
                stmt = stmt.where(PromptMetaData.prompt_type.in_(prompt_types))'
            '''

        result = await db.execute(stmt)

        return  result.scalar_one()
    except IntegrityError as e:
        await db.rollback()
        logger.error(f"IntegrityError when updating executable plan: {str(e)}")
        raise IntegrityException(
            "Integrity error when updating executable plan",
            context = {"detail": f"Issue with updating the executable plan {str(e)}"}
        )
    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(f"Database error when updating executable plan: {str(e)}")
        raise GeneralDataException(
            "Data base error occured while inserting the executable plan",
            context={"detail": f"Database error when updating executable plan: {str(e)}"}
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"Database error when updating executable plan: {str(e)}")
        raise GeneralDataException(
            "Unexpected error occured updating the executable plan",
            context={"detail" : f"Database error when updating executable plan: {str(e)}"}
        )