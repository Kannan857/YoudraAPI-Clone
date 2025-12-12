from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Dict
from app.data.dbinit import get_db
from app.model.user import  UserCreate, User as UserSchema, UserUpdate
from app.data.user import User
from app.service.user import get_all_users,  create_new_user,  update_user_svc, get_user_by_email,get_current_active_user, google_login_svc, forgot_password_svc, reset_password_svc
from app.common.exception import DatabaseConnectionException, RecordNotFoundException, IntegrityException, MissingDataException, GeneralDataException
from app.common.request_metadata import get_request_metadata
from app.api.auth import Token
import aio_pika
from app.common.messaging import get_rabbitmq_connection

router = APIRouter()


@router.get("/getusers", response_model=List[UserSchema])
def read_users(
    skip: int = 0,
    limit: int = 100,
    is_active: Optional[bool] = None,
    role_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
    #current_user: User = Depends(check_user_role("admin"))
):
    """Get all users (admin only)"""
    # Prepare filter parameters
    try:
        filter_params: Dict = {}
        if is_active is not None:
            filter_params["is_active"] = is_active
        if role_id is not None:
            filter_params["role_id"] = role_id
            
        users = get_all_users(db, skip=skip, limit=limit, filter_params=filter_params)
        return users
    except DatabaseConnectionException as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unable to create user plan {e.message}",
            )
    except GeneralDataException as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                 detail=f"Unable to create user plan {e.message}",

            )
    except IntegrityException as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                 detail=f"Unable to create user plan {e.message}",
            )
    except Exception as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail= f"Unable to create user plan {e.message}",
            )


@router.post("/createuser", response_model=UserSchema, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db),
    request_metadata = Depends(get_request_metadata),
    msg_connection: aio_pika.RobustConnection = Depends(get_rabbitmq_connection)
):
    try:
        print ("Before calling create naew user")
        user_in = user_in.model_copy(update={'registration_type': "custom"})
        return await create_new_user( user_in, db, request_metadata, msg_connection)
    except DatabaseConnectionException as e:
        raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=e.message,
                headers={"WWW-Authenticate": "Bearer"},
            )
    except GeneralDataException as e:
        raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f" Gerneral Data Error : {e.message}",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except IntegrityException as e:
        raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f" Integrity error: {e.message}"
            )
    except Exception as e:
        raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password"
            )

@router.get("/me", response_model=UserSchema)
def read_current_user(
    current_user: User = Depends(get_current_active_user)
):
    """Get current user information"""
    try:
        return current_user
    except DatabaseConnectionException as e:
        raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=e.message
            )
    except GeneralDataException as e:
        raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f" Gerneral Data Error : {e.message}"
            )
    except IntegrityException as e:
        raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f" Integrity error: {e.message}"
            )
    except Exception as e:
        raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password"
            )

@router.put("/updateuser", response_model=UserSchema)
async def update_current_user(
    user_in: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Update current user information"""
    # If email is being updated, check it's not already taken
    try:
        if user_in.email and user_in.email != current_user.email:
            existing_user = await get_user_by_email(db, email=user_in.email)
            if existing_user:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already registered"
                )

        user = await update_user_svc(db, current_user.user_id,user_in)
        return user
    except DatabaseConnectionException as e:
        raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=e.message,
                headers={"WWW-Authenticate": "Bearer"},
            )
    except GeneralDataException as e:
        raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f" Gerneral Data Error : {e.message}",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except IntegrityException as e:
        raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f" Integrity error: {e.message}"
            )
    except Exception as e:
        raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Incorrect email or password"
            )


@router.put("/{user_id}", response_model=UserSchema)
def update_specific_user(
    user_id: str,
    user_in: UserUpdate,
    db: AsyncSession = Depends(get_db)
    #current_user: User = Depends(check_user_role("admin"))
):
    """Update a user (admin only)"""
    try:
        user = update_user_svc(db=db, user_id=user_id, user_update=user_in)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        return user
    except DatabaseConnectionException as e:
        raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=e.message
            )
    except GeneralDataException as e:
        raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f" Gerneral Data Error : {e.message}"
            )
    except IntegrityException as e:
        raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f" Integrity error: {e.message}"
            )
    except Exception as e:
        raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Incorrect email or password"
            )


@router.post("/login/google", response_model=Token)
async def google_login(
    token: str,  # ID token from Google frontend login
    db: AsyncSession = Depends(get_db),
    request_metadata = Depends(get_request_metadata),
    msg_connection: aio_pika.RobustConnection = Depends(get_rabbitmq_connection)
):
    try:
        # Verify the token

        access_token = await google_login_svc(token, db, request_metadata, msg_connection)
        return {"access_token": access_token, "token_type": "bearer"}

    except DatabaseConnectionException as e:
        raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f" Database error with google login {e.message}"
            )
    except GeneralDataException as e:
        raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f" Gerneral Data Error with google login: {e.message}"
            )
    except IntegrityException as e:
        raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f" Integrity error with google login: {e.message}"
            )
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid or expired token with google login")


@router.post("/auth/forgot-password")
async def forgot_password(email: str, db: AsyncSession = Depends(get_db)):
    try:
        res = await forgot_password_svc(email,db)
        return res
    except DatabaseConnectionException as e:
        raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f" Database error with forgot password {e.message}"
            )
    except GeneralDataException as e:
        raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f" Gerneral Data Error with forgot password: {e.message}"
            )
    except IntegrityException as e:
        raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f" Integrity error with forgot password: {e.message}"
            )
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid or expired token with forgot password")
    
@router.post("/auth/reset-password")
async def reset_password(token: str, new_password: str, db: AsyncSession = Depends(get_db)):
    try:
        res = await reset_password_svc(token, new_password, db)
        return res
    except DatabaseConnectionException as e:
        raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f" Database error when trying to reset the password {e.message}"
            )
    except GeneralDataException as e:
        raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f" Gerneral Data Error when trying to reset the password: {e.message}"
            )
    except IntegrityException as e:
        raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f" Integrity error when trying to reset the password: {e.message}"
            )
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid or expired token when trying to reset the password")
