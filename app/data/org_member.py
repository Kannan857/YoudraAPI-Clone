from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, UniqueConstraint, func, select, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import relationship

from app.data.dbinit import Base


class OrgMember(Base):
    __tablename__ = "org_member"

    member_id = Column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    org_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("organization.org_id"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("dreav_user.user_id"),
        nullable=True,
        index=True,
    )
    invited_by_user_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("dreav_user.user_id"),
        nullable=True,
    )
    email = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    role = Column(String, nullable=False, default="EMPLOYEE")
    status = Column(String, nullable=False, default="invited")
    consumes_seat = Column(Boolean, nullable=False, default=True)
    invite_token = Column(String, nullable=True, unique=True)
    invite_expires_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    org = relationship("Organization", backref="org_members")

    __table_args__ = (
        UniqueConstraint("org_id", "email", name="uq_org_member_email"),
    )


async def list_members(db: AsyncSession, org_id: UUID) -> List[OrgMember]:
    result = await db.execute(
        select(OrgMember).where(OrgMember.org_id == org_id).order_by(OrgMember.created_at.asc())
    )
    return result.scalars().all()


async def get_member_by_id(db: AsyncSession, org_id: UUID, member_id: UUID) -> Optional[OrgMember]:
    result = await db.execute(
        select(OrgMember).where(
            OrgMember.org_id == org_id,
            OrgMember.member_id == member_id,
        )
    )
    return result.scalar_one_or_none()


async def get_member_by_token(db: AsyncSession, token: str) -> Optional[OrgMember]:
    if not token:
        return None
    result = await db.execute(
        select(OrgMember).where(OrgMember.invite_token == token)
    )
    return result.scalar_one_or_none()


async def count_active_seat_members(db: AsyncSession, org_id: UUID) -> int:
    result = await db.execute(
        select(func.count(OrgMember.member_id)).where(
            OrgMember.org_id == org_id,
            OrgMember.status == "active",
            OrgMember.consumes_seat.is_(True),
        )
    )
    return result.scalar_one()
