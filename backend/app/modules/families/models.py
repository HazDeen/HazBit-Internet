from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.database.base import Base


class FamilyGroup(Base):
    __tablename__ = "family_groups"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    owner_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("app.users.id", ondelete="RESTRICT"), nullable=False
    )
    subscription_id: Mapped[UUID] = mapped_column(
        ForeignKey("app.subscriptions.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    member_limit: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FamilyInvitation(Base):
    __tablename__ = "family_invitations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    family_group_id: Mapped[UUID] = mapped_column(
        ForeignKey("app.family_groups.id", ondelete="CASCADE"), nullable=False
    )
    invited_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("app.users.id", ondelete="RESTRICT"), nullable=False
    )
    invited_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("app.users.id", ondelete="CASCADE")
    )
    invited_email: Mapped[str | None] = mapped_column(CITEXT)
    token_hash: Mapped[bytes] = mapped_column(nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class FamilyMember(Base):
    __tablename__ = "family_members"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    family_group_id: Mapped[UUID] = mapped_column(
        ForeignKey("app.family_groups.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("app.users.id", ondelete="RESTRICT"), nullable=False
    )
    invitation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("app.family_invitations.id", ondelete="SET NULL")
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    removed_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("app.users.id", ondelete="SET NULL")
    )
    remove_reason: Mapped[str | None] = mapped_column(Text)
