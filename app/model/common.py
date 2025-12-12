from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List, Union, Any
from datetime import datetime
from fastapi import HTTPException, status
from uuid import UUID



class GeneralRecommendationAndGuidelines(BaseModel):
    general_descripton: Optional[List[str]]

class RoutineSummary(BaseModel):
    summary_item: Optional[List[str]]


