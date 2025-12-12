from app.model.user import UserCreate, UserUpdate
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import Integer, String, Boolean, Column, Table, DateTime, UUID
from sqlalchemy.sql import func
from fastapi import Request
from typing import List, Optional, Dict, Any, Union
from app.data.dbinit import Base
from app.common.passwd import get_password_hash

from sqlalchemy.exc import SQLAlchemyError, MultipleResultsFound, NoResultFound, IntegrityError
from app.common.exception import DatabaseConnectionException, RecordNotFoundException, IntegrityException, MissingDataException, GeneralDataException
import structlog



logger = structlog.get_logger()

class User(Base):
    __tablename__ = "dreav_user"
    user_id = Column(UUID(as_uuid=True), primary_key=True, server_default=str("uuid_generate_v4()"))
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    first_name = Column(String)
    last_name = Column(String)
    is_active = Column(Boolean, default=True)
    timezone = Column(String, nullable=True)
    registration_type = Column(String, nullable=True)
    phone_country_code = Column(String, nullable=True)
    phone_number = Column(String, nullable=True)
    user_consent = Column(String, nullable=True) # This should be revisited. By default, the value should be yes.
    created_dt = Column(DateTime(timezone=True), server_default=func.now())
    updated_dt = Column(DateTime(timezone=True), onupdate=func.now())
    is_platform_admin = Column(Boolean, default=False)
    


async def get_user(db: AsyncSession, user_id: int) -> Optional[User]:
    """Get a single user by ID"""
    result = await db.execute(select(User).filter(User.user_id == user_id))
    user = result.scalar_one_or_none()
    return user
    #return db.query(User).filter(User.user_id == user_id).first()


async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    """Get a single user by email"""
    try:
 
        result = await db.execute(select(User).filter(User.email == email))
        user = result.scalar_one_or_none()
        return user
        #return await db.query(User).filter(User.email == email).first()
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
async def get_users(
    db: AsyncSession, 
    skip: int = 0, 
    limit: int = 100,
    filter_params: Optional[Dict[str, Any]] = None
) -> List[User]:
    """Get multiple users with optional filtering"""
    try:

        query = db.query(User)
        # Apply filters if provided
        if filter_params:
            if filter_params.get("is_active") is not None:
                query = query.filter(User.is_active == filter_params["is_active"])
        
        return query.offset(skip).limit(limit).all()
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

async def create_user(db: AsyncSession, user: UserCreate, request_metadata: Request) -> User:
    """Create a new user"""
    try:

        print ("Before password creation")
        hashed_password = get_password_hash(user.password)
        print ("The hashed password is ", hashed_password)
        db_user = User(
            email=user.email,
            hashed_password=hashed_password,
            first_name=user.first_name,
            last_name=user.last_name,
            is_active=user.is_active,
            registration_type=user.registration_type,
            timezone=request_metadata["timezone"]
        )
        db.add(db_user)
        await db.flush()
        await db.refresh(db_user)
        return db_user
    except IntegrityError as e:

        logger.error(f"IntegrityError when updating executable plan: {str(e)}")
        raise IntegrityException(
            "Integrity error when updating executable plan",
            context = {"detail": f"Issue with updating the executable plan {str(e)}"}
        )
    except SQLAlchemyError as e:

        logger.error(f"Database error when updating executable plan: {str(e)}")
        raise GeneralDataException(
            "Data base error occured while inserting the executable plan",
            context={"detail": f"Database error when updating executable plan: {str(e)}"}
        )
    except Exception as e:

        logger.error(f"Database error when updating executable plan: {str(e)}")
        raise GeneralDataException(
            "Unexpected error occured updating the executable plan",
            context={"detail" : f"Database error when updating executable plan: {str(e)}"}
        )



async def update_user(
    db: AsyncSession, 
    user_id: str, 
    user_update: UserUpdate
) -> Optional[User]:
    """Update a user's information"""
    try:
        db_user = await get_user(db, user_id)
        if not db_user:
            return None
    
        # Convert to dict and remove None values
        update_data = user_update.model_dump(exclude_unset=True)
        
        # Hash the password if it's being updated
        if "password" in update_data:
            update_data["hashed_password"] = get_password_hash(update_data.pop("password"))
        
        # Update user attributes
        for key, value in update_data.items():
            setattr(db_user, key, value)
        
        await db.flush()
        await db.refresh(db_user)
        return db_user
    except IntegrityError as e:

        logger.error(f"IntegrityError when updating executable plan: {str(e)}")
        raise IntegrityException(
            "Integrity error when updating executable plan",
            context = {"detail": f"Issue with updating the executable plan {str(e)}"}
        )
    except SQLAlchemyError as e:

        logger.error(f"Database error when updating executable plan: {str(e)}")
        raise GeneralDataException(
            "Data base error occured while inserting the executable plan",
            context={"detail": f"Database error when updating executable plan: {str(e)}"}
        )
    except Exception as e:

        logger.error(f"Database error when updating executable plan: {str(e)}")
        raise GeneralDataException(
            "Unexpected error occured updating the executable plan",
            context={"detail" : f"Database error when updating executable plan: {str(e)}"}
        )




