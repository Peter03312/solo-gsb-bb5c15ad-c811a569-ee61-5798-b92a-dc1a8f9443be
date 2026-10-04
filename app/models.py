"""ORM 模型：素材、授权、发行申请及申请明细。"""
from datetime import datetime

from sqlalchemy import (Boolean, CheckConstraint, DateTime, ForeignKey, Index,
                        Integer, String, func)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Material(Base):
    """素材。"""

    __tablename__ = "materials"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Authorization(Base):
    """授权：某素材在指定地区、渠道、左闭右开时段 [start_at, end_at) 内可发行 max_count 次。"""

    __tablename__ = "authorizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    material_id: Mapped[int] = mapped_column(
        ForeignKey("materials.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    region: Mapped[str] = mapped_column(String(100), nullable=False)
    channel: Mapped[str] = mapped_column(String(100), nullable=False)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    max_count: Mapped[int] = mapped_column(Integer, nullable=False)
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    disabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    material: Mapped[Material] = relationship()

    __table_args__ = (
        CheckConstraint("end_at > start_at", name="ck_authorizations_window"),
        CheckConstraint("max_count >= 1", name="ck_authorizations_max_count"),
        CheckConstraint(
            "used_count >= 0 AND used_count <= max_count",
            name="ck_authorizations_used_count",
        ),
        Index("ix_authorizations_match", "material_id", "region", "channel"),
    )


class DistributionRequest(Base):
    """发行申请：整体通过（approved）后可撤销一次（revoked）。"""

    __tablename__ = "distribution_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    region: Mapped[str] = mapped_column(String(100), nullable=False)
    channel: Mapped[str] = mapped_column(String(100), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="approved", server_default="approved"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    items: Mapped[list["DistributionRequestItem"]] = relationship(
        back_populates="request", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint("status IN ('approved', 'revoked')", name="ck_distribution_requests_status"),
    )


class DistributionRequestItem(Base):
    """申请明细：每个素材占用的那份授权。"""

    __tablename__ = "distribution_request_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(
        ForeignKey("distribution_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    material_id: Mapped[int] = mapped_column(
        ForeignKey("materials.id", ondelete="RESTRICT"), nullable=False
    )
    authorization_id: Mapped[int] = mapped_column(
        ForeignKey("authorizations.id", ondelete="RESTRICT"), nullable=False
    )

    request: Mapped[DistributionRequest] = relationship(back_populates="items")
    authorization: Mapped[Authorization] = relationship(lazy="joined")
