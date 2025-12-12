from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List
from datetime import datetime



class PromptMetaData(BaseModel):
    id: int
    prompt_type: str
    prompt_detail: str
    is_active: bool
    prompt_version: str
    class Config:
        from_attributes = True