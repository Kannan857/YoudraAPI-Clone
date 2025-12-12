from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List, Any
from datetime import datetime
from uuid import UUID
from fastapi import HTTPException, status

# User schemas
class UserBase(BaseModel):
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_active: Optional[bool] = True
    registration_type: Optional[str] = None
    user_consent: Optional[str] = "yes"


class UserCreate(UserBase):
    password: str = Field(..., min_length=8)
    
    @field_validator('password')
    def password_strength(cls, v):
        if not any(char.isdigit() for char in v):
            raise ValueError('Password must contain at least one digit')
        if not any(char.isupper() for char in v):
            raise ValueError('Password must contain at least one uppercase letter')
        return v



class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_active: Optional[bool] = None
    registration_type: Optional[str] = None
    password: Optional[str] = None
    phone_country_code: Optional[str] = None
    phone_number: Optional[str] = None
    timezone: Optional[str] = None
    user_consent: Optional[str] = "yes"
    
    @field_validator('password')
    def password_strength(cls, v):
        if v is None:
            return v
        if not any(char.isdigit() for char in v):
            raise ValueError('Password must contain at least one digit')
        if not any(char.isupper() for char in v):
            raise ValueError('Password must contain at least one uppercase letter')
        return v



class User(UserBase):
    user_id: str
    timezone: Optional[str] = None
    created_dt: Optional[datetime] = None
    updated_dt: Optional[datetime] = None
    is_platform_admin: bool = False

    @field_validator('user_id', mode='before')
    @classmethod
    def validate_uuid(cls, value: Any) -> str:
        try:
            # If the value is already a UUID, convert it to string
            if isinstance(value, UUID):
                return str(value)
            
            # If it's a string, ensure it's valid UUID format and return as string
            if isinstance(value, str):
                try:
                    UUID(value)
                    return value
                except ValueError:
                    raise ValueError(f"Invalid UUID format: {value}")
                
            # If it's another type, try to convert to UUID first, then to string
            return str(UUID(str(value)))
        except (ValueError, TypeError, AttributeError) as e:
            # Pydantic validation errors will be automatically converted to HTTPException
            # with status code 422 by FastAPI
            error_type = type(e).__name__
            raise ValueError(f"Failed to convert value to UUID: {error_type}: {str(e)}")
        except Exception as e:
            # For unexpected errors, raise a 500 Internal Server Error
            # Note: This approach can be debated - in production you might want to log this
            # error instead of exposing exception details to the client
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unexpected server error when processing UUID: {str(e)}"
            )
    class Config:
        from_attributes = True
