from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List, Union, Any
from datetime import datetime
from fastapi import HTTPException, status
from uuid import UUID
from app.model.user_plan import UserPlanIdentifier, UXUserPlanIdentifier, IUXCreatedPlan
from app.model.common import RoutineSummary, GeneralRecommendationAndGuidelines

class WeeklyPlan(BaseModel):
    week_number: int
    week_text: str
    weekly_objective: str

    @field_validator('week_number', mode='before')
    @classmethod
    def extract_from_raw_data(cls, value, info):
        # If value is already provided, don't override it
        if value is not None:
            return value
        try:
            # Get the week_text from values dict
            week_text = info.data.get('week_text', '')
            
            # Check if week_text is empty
            if not week_text:
                raise ValueError("week_text is empty or not provided")
                
            # Split the text and extract the number
            parts = week_text.split("-")
            if len(parts) < 2:
                raise ValueError(f"week_text '{week_text}' does not contain the expected format 'X-Y'")
                
            # Convert to integer
            week_number = int(parts[1].strip())
            return week_number
            
        except ValueError as e:
            # Handle parsing errors with a clear message
            raise ValueError(f"Failed to extract week number: {str(e)}")
        except IndexError:
            # Handle index errors if split doesn't have enough parts
            raise ValueError(f"Invalid week_text format: '{week_text}'. Expected format like 'Week-1'")
        except Exception as e:
            # Catch any other unexpected errors
            error_type = type(e).__name__
            raise ValueError(f"Unexpected error extracting week number: {error_type}: {str(e)}")


class WeeklyPlanIdentifier(WeeklyPlan):
     plan_id: str
     week_objective_sequence: int

     @field_validator('plan_id', mode='before')
     @classmethod
     def validate_plan_id(cls, value: Any) -> str:
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
 
class Activity(BaseModel):
    activity: str

class ActivityDetail(Activity):
    plan_id: str
    week_number: int
    day_number: int
    suggest_time: Optional[str]
    suggest_duration: Optional[str]
    activity_sequence: int
    week_objective_sequence: int
    day_objective_sequence: int
    @field_validator('plan_id', mode='before')
    @classmethod
    def validate_plan_id(cls, value: Any) -> str:
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

class ActivityDetailIdentifier(ActivityDetail):
    activity_id: str
    @field_validator('activity_id', mode='before')
    @classmethod
    def validate_plan_id(cls, value: Any) -> str:
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

class ActivityWithNoTimeCriteria(BaseModel):
    daily_objective: str
    suggested_time: Optional[str]
    suggested_duration: Optional[str]
    activity_detail: list[Activity]

class MileStone(BaseModel):
    milestone_id: str
    milestone_desc: str
    activities: Optional[List[ActivityWithNoTimeCriteria]]

class ActivityWithNoTimeCriteriaIdentifier(ActivityWithNoTimeCriteria):
    plan_id: str
    @field_validator('plan_id', mode='before')
    @classmethod
    def validate_plan_id(cls, value: Any) -> str:
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
 
class ActivityByDay(BaseModel):
    day_number: int
    day_text: str
    daily_objective: str
    suggested_time: Optional[str]
    suggested_duration: Optional[str]
    @field_validator('day_number', mode='before')
    @classmethod
    def extract_from_raw_data(cls, value, info):
        # If value is already provided, don't override it
        if value is not None:
            return value
        try:
            # Get the week_text from values dict
            day_text = info.data.get('day_text', '')
            
            # Check if week_text is empty
            if not day_text:
                raise ValueError("week_text is empty or not provided")
                
            # Split the text and extract the number
            parts = day_text.split("-")
            if len(parts) < 2:
                raise ValueError(f"week_text '{day_text}' does not contain the expected format 'X-Y'")
                
            # Convert to integer
            day_number = int(parts[1].strip())
            return day_number
            
        except ValueError as e:
            # Handle parsing errors with a clear message
            raise ValueError(f"Failed to extract week number: {str(e)}")
        except IndexError:
            # Handle index errors if split doesn't have enough parts
            raise ValueError(f"Invalid week_text format: '{week_text}'. Expected format like 'Week-1'")
        except Exception as e:
            # Catch any other unexpected errors
            error_type = type(e).__name__
            raise ValueError(f"Unexpected error extracting week number: {error_type}: {str(e)}")

class ActivityByDayDetail(ActivityByDay):
    activity_detail: list[Activity]

class ActivityByDayIdentifier(ActivityByDay):
    plan_id: str
    week_number: int
    week_objective_sequence: int
    day_objective_sequence: int
    @field_validator('plan_id', mode='before')
    @classmethod
    def validate_plan_id(cls, value: Any) -> str:
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

class UXExecutableWeeklyPlanDetail(WeeklyPlanIdentifier):
    entity_id: str

class UXExecutableDailyPlanDetail(ActivityByDayIdentifier):
    entity_id: str

class WeeklyPlanWithDailyDetail(WeeklyPlan):
    dailyactivity: list[ActivityByDayDetail]



class UXGeneralRecommendationAndGuideline(GeneralRecommendationAndGuidelines):
    plan_id: str
    @field_validator('plan_id', mode='before')
    @classmethod
    def validate_plan_id(cls, value: Any) -> str:
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

class UXRoutineSummary(RoutineSummary):
    plan_id: str
    @field_validator('plan_id', mode='before')
    @classmethod
    def validate_plan_id(cls, value: Any) -> str:
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

class UXGoalBuilder(BaseModel):
    plan_id: UUID
    user_id: UUID
    prev_plan_id: Optional[UUID]
    session_id: Optional[UUID]
    root_id: UUID
    prompt_text: str
    plan_name: str
    revised_prompt_summary: Optional[str]
    llm_source: Optional[str]
    concatenated_prompt: Optional[str]
    created_dt: Optional[datetime]
    class Config:
        from_attributes = True

class UserPromptResponse(BaseModel):
    gender: str
    weight: str
    height: str
    Age: str
    PreExistingCondition: str
    PriorExpertise: str
    Occupation: str
    Goal: str
    ExplicitAskForGoal: str
    GoalDuration: str
    WorkHours: str
    IsWorkingFlag: str
    UserQuery: str
    LLMReason: str
    routine_summary: Optional[RoutineSummary]
    general_recommendation_guideline: Optional[GeneralRecommendationAndGuidelines]
    plan_name: str
    plan_type: str
    plan_category: Optional[str] = "N/A"
    plan: list[Union[MileStone,ActivityByDayDetail,WeeklyPlanWithDailyDetail]]


class PlanDetailForUserManagement(BaseModel):
    plan_header: UXUserPlanIdentifier
    routine_summary: Optional[RoutineSummary] = None
    general_recommendation_guideline: Optional[GeneralRecommendationAndGuidelines] = None
    created_plan: Optional[List[IUXCreatedPlan]] 
    plan_trail: Optional[UXGoalBuilder] = None

class UXUserPromptInfo(BaseModel):
    prompt_text: str
    root_id: Optional[UUID]
    prev_plan_id: Optional[UUID]

   
class UXRevisionHistoryI(BaseModel):
    plan_id: Optional[UUID]
    root_id: Optional[UUID]



