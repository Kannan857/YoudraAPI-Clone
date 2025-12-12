from pydantic import BaseModel, field_validator
from uuid import UUID
from typing import Optional, Union, List
from datetime import datetime

class ProgressUpdateSummaryInput(BaseModel):
    plan_id: Optional[UUID] = None

class ProgressUpdateCreate(BaseModel):
    user_id: UUID
    entity_id: UUID
    plan_id: UUID
    progress_percent: int
    notes: Optional[str] = ""

class ProgressUpdateOut(BaseModel):
    entity_id: UUID
    progress_percent: Optional[float] = 0.00
    notes: Optional[str]
    plan_progress: Optional[float] = 0.00

    @field_validator("plan_progress", mode="before")
    @classmethod
    def format_plan_progress(cls, v):
        if v is None:
            return 0.00
        return round(float(v), 2)

class ProgressDailyDetail(BaseModel):
    entity_id: UUID
    parent_id: Optional[UUID] = None
    sequence_id: int
    activity_desc: str
    progress_percent: Optional[float] = 0.00

class ProgressWeeklyDetail(BaseModel):
    entity_id: UUID
    activity_desc: str
    sequence_id: int
    progress_percent: Optional[float] = 0.0
    milestone_25: Optional[int] = 0
    milestone_50: Optional[int] = 0
    milestone_75: Optional[int] = 0
    milestone_100: Optional[int] = 0    

class ProgressSummary(BaseModel):
    plan_id: UUID
    plan_name: str
    plan_type: str
    plan_progress_percent: Optional[float] = 0.0
    plan_milestone_25: Optional[int] = 0
    plan_milestone_50: Optional[int] = 0
    plan_milestone_75: Optional[int] = 0
    plan_milestone_100: Optional[int] = 0
    week_detail: Optional[List[ProgressWeeklyDetail]]
    day_detail: Optional[List[ProgressDailyDetail]]

