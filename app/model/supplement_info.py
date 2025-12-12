from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List, Any
from datetime import datetime
from uuid import UUID
from fastapi import status

class testclass(BaseModel):
    name: str
    id: Optional[float]

class ISupplementDetail(BaseModel):
    site_title: str
    site_url: str
    entity_id: str
    site_keyword: str
    relevance_score: Optional[float]

class UXSupplementInput(BaseModel):
    """
    You can send only activity id 
    """
    plan_id: str
    activity_id: Optional[str]
