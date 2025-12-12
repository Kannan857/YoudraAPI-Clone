
from sqlalchemy import select, update, delete
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import Integer, String, Boolean, Column, Table, DateTime, UUID, BigInteger
from sqlalchemy.sql import func
from typing import List, Optional, Dict, Any, Union
from app.data.dbinit import Base
from app.common.passwd import get_password_hash
from sqlalchemy.exc import SQLAlchemyError, MultipleResultsFound, NoResultFound, IntegrityError
from app.common.exception import DatabaseConnectionException, RecordNotFoundException, IntegrityException, MissingDataException, GeneralDataException
import structlog
from sqlalchemy.dialects import postgresql
import uuid

logger = structlog.get_logger()

class DBSupplementData(Base):
    __tablename__ = "user_plan_activity_helper_data"
    c_id = Column(BigInteger, primary_key=True)
    rec_id = Column(UUID(as_uuid=True))
    entity_id = Column(UUID(as_uuid=False), nullable=False)
    ext_site_url = Column(String, nullable=True)
    ext_site_title = Column(String, nullable=True)
    ext_site_keyword = Column(String, nullable=True)


async def get_data(db: AsyncSession, filter_params: dict) -> Optional[List[DBSupplementData]]:
    try:

        stmt = select(DBSupplementData)
        if filter_params:
            if filter_params.get("entity_id") is not None:
                print ("The entity id is ", filter_params["entity_id"])
                stmt = stmt.where(DBSupplementData.entity_id == filter_params["entity_id"])
        else:
            raise GeneralDataException(message="No filters given",
                                       context = "Trying to fetch rows from supplement data without providing filters")
        

        #print ("The statement is ", stmt.compile(compile_kwargs={"literal_binds": True}))
        #x = await get_sql_with_params(stmt)
        #print("The executable SQL is ", x )
        result = await db.execute(stmt)
        data = result.scalars().all()
        return data

    except IntegrityError as e:

        logger.error(f"IntegrityError when inserting user plan: {str(e)}")
        raise IntegrityException(
            "Integrity error when inserting a user plan",
            context = {"detail": "This plan conflicts with an existing plan. Possible duplicate entry or foreign key constraint failure."}
        )
    except SQLAlchemyError as e:

        logger.error(f"Database error when inserting user plan: {str(e)}")
        raise GeneralDataException(
            "Data base error occured while inserting the user plan",
            context={"detail": "Database error occurred while creating the user plan"}
        )
    except Exception as e:

        logger.error(f"Unexpected error in insert_plan: {str(e)}")
        raise GeneralDataException(
            "Unexpected error occured inserting plan",
            context={"detail" : "An unexpected error occurred while creating the user plan"}
        )
    



async def get_data_no_orm(db: AsyncSession, filter_params: dict) -> Optional[List[DBSupplementData]]:
    try:
        if not filter_params:
            raise GeneralDataException(
                message="No filters given",
                context="Trying to fetch rows without providing filters"
            )

        # Base SQL with DISTINCT
        sql = """
            SELECT DISTINCT 
                rec_id, 
                entity_id, 
                ext_site_url, 
                ext_site_title, 
                ext_site_keyword 
            FROM user_plan_activity_helper_data
        """
        params = {}

        # Add WHERE clause if entity_id exists
        if filter_params.get("entity_id"):
            sql += " WHERE entity_id = :entity_id"
            params["entity_id"] = str(filter_params["entity_id"])

        # Execute raw SQL
        result = await db.execute(text(sql), params)
        
        # Convert raw rows to ORM objects
        return [
            DBSupplementData(
                rec_id=row.rec_id,
                entity_id=row.entity_id,
                ext_site_url=row.ext_site_url,
                ext_site_title=row.ext_site_title,
                ext_site_keyword=row.ext_site_keyword
            ) for row in result
        ]
    except IntegrityError as e:

        logger.error(f"IntegrityError when inserting user plan: {str(e)}")
        raise IntegrityException(
            "Integrity error when inserting a user plan",
            context = {"detail": "This plan conflicts with an existing plan. Possible duplicate entry or foreign key constraint failure."}
        )
    except SQLAlchemyError as e:

        logger.error(f"Database error when inserting user plan: {str(e)}")
        raise GeneralDataException(
            "Data base error occured while inserting the user plan",
            context={"detail": "Database error occurred while creating the user plan"}
        )
    except Exception as e:

        logger.error(f"Unexpected error in insert_plan: {str(e)}")
        raise GeneralDataException(
            "Unexpected error occured inserting plan",
            context={"detail" : "An unexpected error occurred while creating the user plan"}
        )

async  def get_sql_with_params(statement, bind=None):
    if bind:
        compiler = statement.compile(bind=bind, compile_kwargs={"literal_binds": True})
    else:
        # Use PostgreSQL dialect which handles UUIDs better
        compiler = statement.compile(
            dialect=postgresql.dialect(), 
            compile_kwargs={"literal_binds": True}
        )
    
    try:
        # Try standard approach first
        return str(compiler)
    except (TypeError, NotImplementedError) as e:
        # Fallback for UUID handling
        compiled_sql = compiler.string
        if not compiler.params:
            return compiled_sql
            
        # Manual parameter substitution for debugging
        params = compiler.params
        for key, value in params.items():
            if isinstance(value, uuid.UUID):
                # Format UUID as string with quotes
                value_str = f"'{str(value)}'"
            else:
                value_str = f"'{value}'" if isinstance(value, str) else str(value)
                
            # Replace parameter placeholder with actual value
            placeholder = f":{key}"
            compiled_sql = compiled_sql.replace(placeholder, value_str)
            
        return compiled_sql