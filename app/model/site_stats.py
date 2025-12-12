from pydantic import BaseModel
from typing import Optional, List, Any
from uuid import UUID


class SiteStatsPlanCountByType(BaseModel):
    plan_count: int
    plan_category: Optional[str] = "N/A"

class YoudraFeedback(BaseModel):
    feedback_type: str
    feedback_text: str
    user_id: Optional[UUID]
    