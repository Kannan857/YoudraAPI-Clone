from pydantic import BaseModel, Field
from uuid import UUID
from typing import Optional
from datetime import datetime

class FmpSubscriberCreate(BaseModel):
    plan_id: UUID
    user_id: UUID
    is_active: int = Field(..., ge=0, le=1)  # Assuming 0 or 1

class FmpSubscriberUpdate(BaseModel):
    is_active: int = Field(..., ge=0, le=1)

class FmpSubscriberOut(BaseModel):
    plan_id: UUID
    user_id: UUID
    subscribed_dt: Optional[datetime]
    is_active: int
    inserted_dt: Optional[datetime]
    updated_dt: Optional[datetime]

    class Config:
        orm_mode = True

class FmpSubscriberGet(BaseModel):
    plan_id: Optional[UUID] 

class FmpCountSummary(BaseModel):
    plan_id: UUID
    plan_name: Optional[str]
    follower_count: Optional[int] = 0
    user_id: Optional[UUID]
    first_name: Optional[str]
    last_name: Optional[str]
