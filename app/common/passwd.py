from jose import jwt, JWTError
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from app.config.config import settings
from pydantic import BaseModel
from datetime import datetime, timedelta, timezone
from typing import Optional, Any, List

# OAuth2 settings
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_PREFIX}/auth/token")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify that a plain password matches the hashed password"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Generate password hash from plain password"""
    return pwd_context.hash(password)

async def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a new JWT access token"""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    return await encode_jwt(to_encode)

def decode_jwt(token: str):
    credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not decode credentials",
    headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        print ("The token is ", token)
        return jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    except JWTError as e:
        print ("The error is ", str(e))
        raise credentials_exception

async def encode_jwt(to_encode):
    credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not encode credentials",
    headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        return jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")
    except JWTError:
        raise credentials_exception
