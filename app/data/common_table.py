from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from app.data.dbinit import Base
import uuid
from sqlalchemy.future import select
from sqlalchemy import update, text
from sqlalchemy.ext.asyncio import AsyncSession





class ProgressUpdate(Base):

    __tablename__ = 'progress_update'

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=str("gen_random_uuid()"))
    plan_id = Column(UUID(as_uuid=True), nullable=False)
    entity_id = Column(UUID(as_uuid=True), nullable=False)  # The daily objective entity
    progress_percent = Column(Integer, nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True),  server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())