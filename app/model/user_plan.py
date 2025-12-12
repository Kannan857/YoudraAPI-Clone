from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from typing import Optional, List, Any, Union
from datetime import datetime
from uuid import UUID
from fastapi import HTTPException, status
from enum import Enum
from app.model.common import RoutineSummary, GeneralRecommendationAndGuidelines

class ActivityStatus(int, Enum):
    IN_PROGRESS = 1
    COMPLETED = 2
    NOT_STARTED = 0
    CANCELLED = -1


class UXUserPlanUpdate(BaseModel):
    plan_id: UUID
    private_flag: Optional[int]
    follow_flag: Optional[int]

class UserPlanApproval(BaseModel):
    plan_start_date: Optional[datetime]
    plan_end_date: Optional[datetime]
    approved_by_user: Optional[int] = 0
    class Config:
        from_attributes = True



class UserPlan(BaseModel):
    user_id: str
    plan_name: str
    plan_type: str
    plan_goal: str
    goal_duration: str
    plan_category: Optional[str]
    plan_status: Optional[int] = 0
    
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

class UserPlanIdentifier(UserPlan, UserPlanApproval):
    plan_id: str
    @field_validator('plan_id', mode='before')
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
    
class UXUserPlanIdentifier(BaseModel):
    plan_id: str
    root_id: Optional[UUID] = None
    prev_plan_id: Optional[UUID] = None
    user_id: str
    plan_name: str
    plan_type: str
    plan_goal: str
    plan_start_date: Optional[datetime]
    plan_end_date: Optional[datetime]
    approved_by_user: Optional[int] = 0
    private_flag: Optional[int] = 1
    follow_flag: Optional[int] = 0
    plan_status: Optional[int] = 0
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
    @field_validator('plan_id', mode='before')
    @classmethod
    def validate_plan_uuid(cls, value: Any) -> str:
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

class UXUserPlanIdentifierRS(BaseModel):
    content: Optional[List[UXUserPlanIdentifier]]

class UXPlanApprovalPL(BaseModel):
    plan_id: str
    plan_start_date: Optional[datetime]
    plan_end_date: Optional[datetime]
    approved_by_user: Optional[int] = 0
    @field_validator('plan_id', mode='before')
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

class IExecutionPlanDetail(BaseModel):
    plan_id: UUID
    sequence_id: int
    level_id: int
    entity_id: UUID
    entity_type: int
    parent_id: Optional[UUID] = None
    start_date: datetime
    status_id: int
    reminder_request: Optional[int] = 0
    progress_measure: Optional[float] = 0.0
    activity_desc: str
    request_reminder_time: Optional[str]
    class Config:
        from_attributes = True 
    
class UXApprovedPlanDetail(BaseModel):
    plan_detail: Optional[List[IExecutionPlanDetail]]
    routine_summary: Optional[RoutineSummary]
    general_guidelines: Optional[GeneralRecommendationAndGuidelines]


class UXUpdateApprovedPlan(BaseModel):
    plan_id: str
    entity_id: str
    sequence_id: int
    days_to_move: Optional[int] = 0
    change_reason: Optional[str] = "User Request"
    reminder_request: Optional[int] = 0
    request_reminder_time: Optional[str]
    status_id: Optional[int] = 0


class UXApprovedPlanUpdateReminder(BaseModel):
    plan_id: str
    entity_id: str
    reminder_request: int
    reminder_request_time: str
    @field_validator('plan_id', mode="before")
    def validate_parent_id(cls, v):
        if v is None or v == '' or v == "None":
            return None
        try:
              # If the value is already a UUID, convert it to string
            if isinstance(v, UUID):
                return str(v)
            
            # If it's a string, ensure it's valid UUID format and return as string
            if isinstance(v, str):
                try:
                    UUID(v)
                    return v
                except ValueError:
                    raise ValueError(f"Invalid UUID format: {v}")
                
            # If it's another type, try to convert to UUID first, then to string
            return str(UUID(str(v)))
        except ValueError:
            raise ValueError('parent_id must be a valid UUID string or None')

    @field_validator('entity_id', mode="before")
    def validate_entity_id(cls, v):
        if v is None or v == '' or v == "None":
            return None
        try:
              # If the value is already a UUID, convert it to string
            if isinstance(v, UUID):
                return str(v)
            
            # If it's a string, ensure it's valid UUID format and return as string
            if isinstance(v, str):
                try:
                    UUID(v)
                    return v
                except ValueError:
                    raise ValueError(f"Invalid UUID format: {v}")
                
            # If it's another type, try to convert to UUID first, then to string
            return str(UUID(str(v)))
        except ValueError:
            raise ValueError('parent_id must be a valid UUID string or None')

class UXUpcomingActivitiesRequest(BaseModel):
    plan_id: Optional[str]
    days_to_add: int
    @field_validator('plan_id', mode="before")
    def validate_parent_id(cls, v):
        if v is None or v == '' or v == "None":
            return None
        try:
              # If the value is already a UUID, convert it to string
            if isinstance(v, UUID):
                return str(v)
            
            # If it's a string, ensure it's valid UUID format and return as string
            if isinstance(v, str):
                try:
                    UUID(v)
                    return v
                except ValueError:
                    raise ValueError(f"Invalid UUID format: {v}")
                
            # If it's another type, try to convert to UUID first, then to string
            return str(UUID(str(v)))
        except ValueError:
            raise ValueError('parent_id must be a valid UUID string or None')

class UXUpcomingActivitiesResponse(BaseModel):
    plan_id: str
    plan_name: str
    plan_activity: str
    objective_start_date: str
    obj_current_state: str
    reminder_request: Optional[int]
    reminder_request_time: Optional[str]
    progress_measure: Optional[float] = 0.0
    entity_id: Optional[UUID]
    entity_type: int
    status_id: Optional[int] = 0

    @field_validator('plan_id', mode="before")
    def validate_parent_id(cls, v):
        if v is None or v == '' or v == "None":
            return None
        try:
              # If the value is already a UUID, convert it to string
            if isinstance(v, UUID):
                return str(v)
            
            # If it's a string, ensure it's valid UUID format and return as string
            if isinstance(v, str):
                try:
                    UUID(v)
                    return v
                except ValueError:
                    raise ValueError(f"Invalid UUID format: {v}")
                
            # If it's another type, try to convert to UUID first, then to string
            return str(UUID(str(v)))
        except ValueError:
            raise ValueError('parent_id must be a valid UUID string or None')

class UXUpcomingActivitiesResponseRS(BaseModel):
    content: Optional[list[UXUpcomingActivitiesResponse]]


class IUXCreatedPlan(BaseModel):
    plan_id: UUID
    entity_id: UUID
    sequence_id: int
    level_id: int
    entity_type: int
    parent_id: Optional[UUID] = None
    suggested_start_time: Optional[str] = None
    suggested_duration: Optional[str] = None
    status_id: Optional[int] = 0
    source_id: Optional[int] = 0
    entity_desc: str
    class Config:
        from_attributes = True

class ICreatedPlan(BaseModel):
    plan_id: UUID
    sequence_id: int
    level_id: int
    entity_type: int
    parent_id: Optional[UUID] = None
    suggested_start_time: Optional[str] = None
    suggested_duration: Optional[str] = None
    status_id: Optional[int] = 0
    source_id: Optional[int] = 0
    entity_desc: str

