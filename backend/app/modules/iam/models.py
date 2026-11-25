from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class CompanyProfile(Base):
    __tablename__ = "company_profiles"
    __table_args__ = (
        CheckConstraint(
            "gstin ~ '^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$'",
            name="gstin_format",
        ),
        CheckConstraint("state_code ~ '^[0-9]{2}$'", name="state_code_format"),
        CheckConstraint("variance_tolerance_pct >= 0", name="tolerance_non_negative"),
        CheckConstraint(
            "valuation_method IN ('FIFO', 'WEIGHTED_AVERAGE', 'LAST_PRICE')",
            name="valuation_method_enum",
        ),
        CheckConstraint("is_singleton IS TRUE", name="singleton_true"),
        UniqueConstraint("is_singleton", name="uq_company_profiles_singleton"),
        {"schema": "iam"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    legal_name: Mapped[str] = mapped_column(String(200), nullable=False)
    gstin: Mapped[str] = mapped_column(String(15), nullable=False)
    state_name: Mapped[str] = mapped_column(String(80), nullable=False)
    state_code: Mapped[str] = mapped_column(String(2), nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    variance_tolerance_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, server_default="3.00"
    )
    valuation_method: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="FIFO"
    )
    is_singleton: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (
        CheckConstraint(
            "code IN ('SALESMAN', 'FACTORY_ADMIN', 'PRODUCTION_SUPERVISOR', 'ACCOUNTANT_AUDITOR', 'OWNER')",
            name="role_code_enum",
        ),
        {"schema": "iam"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    users: Mapped[list["User"]] = relationship(back_populates="role")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        Index("idx_users_role_active", "role_id", "is_active"),
        {"schema": "iam"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    role_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("iam.roles.id", ondelete="RESTRICT"), nullable=False
    )
    username: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True, unique=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    role: Mapped[Role] = relationship(back_populates="users")
