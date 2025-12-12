# app/api/dependencies.py
from fastapi import Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession

from pydantic import BaseModel
from datetime import datetime, timedelta
from typing import Optional, Any, List
from app.common import passwd

from app.config.config import settings
from app.data.dbinit import get_db
from app.data.user import User
from app.model.user import User as MUser, UserCreate, UserUpdate
from app.common.exception import DatabaseConnectionException, RecordNotFoundException, IntegrityException, MissingDataException, GeneralDataException
from app.common.messaging import publish_message
from app.common.passwd import create_access_token, decode_jwt, get_password_hash

import structlog
import aio_pika
import uuid
from google.oauth2 import id_token
from google.auth.transport import requests
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import timedelta

from app.common.utility_functions import send_email, generate_password

from app.data.user import get_users,  create_user, update_user,  get_user_by_email


logger = structlog.get_logger()

def get_all_users(db:AsyncSession, skip, limit, filter_params)->List[User]:
    return get_users(db, skip=skip, limit=limit, filter_params=filter_params)

async def create_new_user(
    user_in: UserCreate,
    db: AsyncSession,
    request_metadata: Request,
    msg_connection: aio_pika.RobustConnection
):
    """Create a new user (public endpoint for registration)"""
    # Check if user already exists
    try:
        existing_user = await get_user_by_email(db, email=user_in.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        print ("Inside create new user function")
        res = await create_user(db=db, user=user_in, request_metadata=request_metadata)
        message = {}
        message["user_id"] = str(res.user_id)
        print(type(message["user_id"]))
        if isinstance(res.user_id, bytes):
            message["user_id"] = str(uuid.UUID(bytes=res.user_id))
        else:
            message["user_id"] = str(res.user_id)
        message["first_name"] = res.first_name
        message["last_name"] = res.last_name
        message["email"] = res.email
        message["task_type"] = f"new_user_email"
        
        await publish_message(message, msg_connection)

        return res
    except IntegrityException as e:

        logger.error(f"IntegrityError when inserting user plan: {str(e)}")
        raise IntegrityException(
            message="Integrity error when creating a new user",
            context = {"detail": "Error in creating a new user."}
        )
    except GeneralDataException as e:

        logger.error(f"Database error when creating a new: {str(e)}")
        raise GeneralDataException(
            "Data base error occured while creating a new user",
            context={"detail": "Database error occurred while creating new user"}
        )
    except Exception as e:
        logger.error(f"Some general error occured when creating a new user: {str(e)}")
        raise GeneralDataException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred when create a new user")


async def update_user_svc(
    db: AsyncSession,
    user_id: str, 
    user_in: UserUpdate) -> Optional[User]:
    try:
        user = await update_user(db=db, user_id=user_id, user_update=user_in)
        return user
    except IntegrityException as e:

        logger.error(f"IntegrityError when inserting user plan: {str(e)}")
        raise IntegrityException(
            "Integrity error when inserting a user plan",
            context = {"detail": "This plan conflicts with an existing plan. Possible duplicate entry or foreign key constraint failure."}
        )
    except GeneralDataException as e:

        logger.error(f"Database error when inserting user plan: {str(e)}")
        raise GeneralDataException(
            "Data base error occured while inserting the user plan",
            context={"detail": "Database error occurred while creating the user plan"}
        )
    except Exception as e:
        logger.error(f"Some general error occured when updating the approved user plan: {str(e)}")
        raise GeneralDataException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred while creating user plan")



async def update_specific_user(
    user_id: int,
    user_in: UserUpdate,
    db: AsyncSession
):
    """Update a user (admin only)"""
    try:
        user = await update_user(db=db, user_id=user_id, user_update=user_in)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        return user
    except IntegrityException as e:

        logger.error(f"IntegrityError when inserting user plan: {str(e)}")
        raise IntegrityException(
            "Integrity error when inserting a user plan",
            context = {"detail": "This plan conflicts with an existing plan. Possible duplicate entry or foreign key constraint failure."}
        )
    except GeneralDataException as e:

        logger.error(f"Database error when inserting user plan: {str(e)}")
        raise GeneralDataException(
            "Data base error occured while inserting the user plan",
            context={"detail": "Database error occurred while creating the user plan"}
        )
    except Exception as e:
        logger.error(f"Some general error occured when updating the approved user plan: {str(e)}")
        raise GeneralDataException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred while creating user plan")




# Token schema
class TokenData(BaseModel):
    sub: Optional[str] = None


async def authenticate_user(db: AsyncSession, email: str, password: str) -> Optional[User]:
    """Authenticate a user with email and password"""
    try:
        user = await get_user_by_email(db, email)
        if not user:
            return None
        if user.registration_type == 'google':
            logger.erro(f"Google user cannot be authenticated through Youdra authemtication {email}")
            raise GeneralDataException(
                f"Google user cannot be authenticated through Youdra authemtication {email}",
                context = {"detail": f"Google user cannot be authenticated through Youdra authemtication {email}"}
            )
        
        if not await passwd.verify_password(password, user.hashed_password):
            return None
        return user
    except IntegrityException as e:

        logger.error(f"IntegrityError when inserting user plan: {str(e)}")
        raise IntegrityException(
            "Integrity error when inserting a user plan",
            context = {"detail": "This plan conflicts with an existing plan. Possible duplicate entry or foreign key constraint failure."}
        )
    except GeneralDataException as e:

        logger.error(f"Database error when inserting user plan: {str(e)}")
        raise GeneralDataException(
            "Data base error occured while inserting the user plan",
            context={"detail": "Database error occurred while creating the user plan"}
        )
    except Exception as e:
        logger.error(f"Some general error occured when updating the approved user plan: {str(e)}")
        raise GeneralDataException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred while creating user plan")



async def get_current_user(
    token: str = Depends(passwd.oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not verify credentials",
    headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = passwd.decode_jwt(token=token)
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
        token_data = TokenData(sub=email)
    
        user = await get_user_by_email(db, email=token_data.sub)
        if user is None:
            raise credentials_exception
        
        return user
    except IntegrityException as e:

        logger.error(f"IntegrityError when inserting user plan: {str(e)}")
        raise IntegrityException(
            "Integrity error when inserting a user plan",
            context = {"detail": "This plan conflicts with an existing plan. Possible duplicate entry or foreign key constraint failure."}
        )
    except GeneralDataException as e:

        logger.error(f"Database error when inserting user plan: {str(e)}")
        raise GeneralDataException(
            "Data base error occured while inserting the user plan",
            context={"detail": "Database error occurred while creating the user plan"}
        )
    except Exception as e:
        logger.error(f"Some general error occured when updating the approved user plan: {str(e)}")
        raise GeneralDataException(
            message = f"error in getting the current user {str(e)}",
            context="Database error occurred while creating user plan")



async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Check if the current user is active"""
    try:
        if not current_user.is_active:
            raise HTTPException(status_code=400, detail="Inactive user")
        return current_user
    except IntegrityException as e:

        logger.error(f"IntegrityError when inserting user plan: {str(e)}")
        raise IntegrityException(
            "Integrity error when inserting a user plan",
            context = {"detail": "This plan conflicts with an existing plan. Possible duplicate entry or foreign key constraint failure."}
        )
    except GeneralDataException as e:

        logger.error(f"Database error when inserting user plan: {str(e)}")
        raise GeneralDataException(
            "Data base error occured while inserting the user plan",
            context={"detail": "Database error occurred while creating the user plan"}
        )
    except Exception as e:
        logger.error(f"Some general error occured when updating the approved user plan: {str(e)}")
        raise GeneralDataException(
            "Unable to get the active user",
            detail="Database error occurred while creating user plan")



async def google_login_svc(
    token: str,  # ID token from Google frontend login
    db: AsyncSession,
    request_metadata: Request,
    msg_connection: aio_pika.RobustConnection
):
    try:
        # Verify the token
        idinfo = id_token.verify_oauth2_token(token, requests.Request(), settings.GOOGLE_CLIENT_ID)

        # Extract the email and other info
        email = idinfo.get("email")
        name = idinfo.get("name")

        if not email:
            raise HTTPException(status_code=400, detail="Google token missing email")

        # Try fetching user from DB
        user = await get_user_by_email(db, email=email)

        # If not found, create a new user
        if not user:

            first_name, _, last_name = name.partition(" ")
            random_pwd = await generate_password(email, first_name)
            user_in = UserCreate(
                email=email,
                password=random_pwd,
                first_name=first_name or "Google",
                last_name=last_name or "User",
                registration_type="google",
                is_active=True
                )

            user = await create_new_user(user_in, db,request_metadata,msg_connection)

        # Generate your app’s JWT token
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = await create_access_token(
            data={"sub": user.email}, 
            expires_delta=access_token_expires
        )

        return access_token

    except IntegrityException as e:

        logger.error(f"IntegrityError with google login: {str(e)}")
        raise IntegrityException(
            "Integrity error when resetting password",
            context = {"detail": f"IntegrityError with google login: {str(e)}"}
        )
    except GeneralDataException as e:

        logger.error(f"Database Error with google login: {str(e)}")
        raise GeneralDataException(
            "Data base error occured with  google login",
            context={"detail": f"Database Error with google login: {str(e)}"}
        )
    except Exception as e:
        logger.error(f"Some general error occured with google login: {str(e)}")
        raise GeneralDataException(
            "Exception with Google login",
            detail=f"Some general error occured with Google Login: {str(e)}")


async def reset_password_svc(token: str, new_password: str, db: AsyncSession):
    try:
        payload = decode_jwt(token)
        email = payload.get("sub")
        if not email:
            raise HTTPException(status_code=400, detail="Invalid token")

        user = await get_user_by_email(db, email=email)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        #hashed_pw = get_password_hash(new_password)
        user_update = UserUpdate(password=new_password)
        await update_user(db, user.user_id, user_update)
        return {"msg": "Password updated successfully"}
    
    except IntegrityException as e:

        logger.error(f"IntegrityError with resetting password: {str(e)}")
        raise IntegrityException(
            "Integrity error when resetting password",
            context = {"detail": f"IntegrityError with resetting password: {str(e)}"}
        )
    except GeneralDataException as e:

        logger.error(f"Database Error with resetting password: {str(e)}")
        raise GeneralDataException(
            "Data base error occured with resetting password",
            context={"detail": f"Database Error with resetting password: {str(e)}"}
        )
    except Exception as e:
        logger.error(f"Some general error occured with resetting password: {str(e)}")
        raise GeneralDataException(
            "Exception with resetting password",
            detail=f"Some general error occured with resetting password: {str(e)}")

async def forgot_password_svc(email: str, db: AsyncSession):
    try:
        user = await get_user_by_email(db, email=email)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        token = await create_access_token(
            data={"sub": user.email}, expires_delta=timedelta(minutes=30)
        )
        template_id = 'd-80c86f6fb232412e993809229b084323'
        await send_email(user.first_name, user.email,token, template_id )
        return {"msg": "Password reset email sent"}
    
    except IntegrityException as e:

        logger.error(f"IntegrityError with forgot password: {str(e)}")
        raise IntegrityException(
            "Integrity error when inserting a user plan",
            context = {"detail": f"IntegrityError with forgot password: {str(e)}"}
        )
    except GeneralDataException as e:

        logger.error(f"Database Error with forgot password: {str(e)}")
        raise GeneralDataException(
            "Data base error occured with forgot password",
            context={"detail": f"Database Error with forgot password: {str(e)}"}
        )
    except Exception as e:
        logger.error(f"Some general error occured with forgot password: {str(e)}")
        raise GeneralDataException(
            "Exception with forgot password",
            detail=f"Some general error occured with forgot password: {str(e)}")