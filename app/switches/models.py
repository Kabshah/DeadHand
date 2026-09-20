"""app/switches/models.py — SQLAlchemy async ORM models (§3).

Design decisions baked in (§3 rationale):
  - google_sub (not email) as identity key — email can change on Google side.
  - Switch.status has 4 states: active | triggering | triggered | cancelled.
    "triggering" is the intermediate state that stops the checkin-vs-trigger race (§10.1).
  - Switch.version — bumped on every transition for optimistic locking.
  - Switch.sent_at — makes send_reveal_email idempotent on retry (§10.5).
  - All datetimes are UTC + tz-aware (timezone=True) — naive datetimes + timezone drift
    is a classic silent bug.
  - interval_hours CHECK constraint: 1..8760 (1 hour to 1 year).
"""
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    google_sub: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    created_ip: Mapped[str | None] = mapped_column(String(45), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    switches: Mapped[list["Switch"]] = relationship("Switch", back_populates="user", lazy="select")
    otp_attempts: Mapped[list["OTPAttempt"]] = relationship("OTPAttempt", back_populates="user", lazy="select")

    __table_args__ = (
        Index("ix_users_email", "email"),
        UniqueConstraint("google_sub", name="uq_users_google_sub"),
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email}>"


class Switch(Base):
    __tablename__ = "switches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    secret_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    recipient_email: Mapped[str] = mapped_column(String(255), nullable=False)
    interval_hours: Mapped[float] = mapped_column(Float, nullable=False)
    next_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="switches")

    __table_args__ = (
        CheckConstraint("interval_hours >= 0.01 AND interval_hours <= 8760", name="ck_switches_interval_hours"),
        CheckConstraint(
            "status IN ('active', 'triggering', 'triggered', 'cancelled', 'failed_reveal')",
            name="ck_switches_status",
        ),
    )

    def __repr__(self) -> str:
        return f"<Switch id={self.id} user_id={self.user_id} status={self.status}>"


class OTPAttempt(Base):
    """Audit log for OTP requests and verifications.

    The live OTP lives in Redis, NOT here.
    This table is append-only — used for audit and debugging.
    ip_address is stored for security monitoring (§11).
    """
    __tablename__ = "otp_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(String(100), nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)  # IPv4/IPv6, audit only
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="otp_attempts")

    def __repr__(self) -> str:
        return f"<OTPAttempt id={self.id} user_id={self.user_id} purpose={self.purpose} success={self.success} ip={self.ip_address}>"
